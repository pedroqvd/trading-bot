"""Tests for the portfolio optimiser + categoriser."""
from datetime import timedelta

from app.config import settings
from app.database import session_scope
from app.database.models import Market, Position, PositionStatus, Side
from app.portfolio.categorizer import categorise
from app.portfolio.portfolio_optimizer import PortfolioOptimizer
from app.utils.time_utils import utcnow


def _seed_market(condition_id: str, question: str, slug: str = "") -> int:
    with session_scope() as session:
        m = Market(
            condition_id=condition_id, slug=slug or condition_id,
            question=question, yes_token_id="1", no_token_id="2",
        )
        session.add(m)
        session.flush()
        return m.id


def _seed_open_position(strategy: str, market_id: int, *, entry_size_usd: float, side: Side = Side.YES):
    with session_scope() as session:
        session.add(Position(
            market_id=market_id, strategy=strategy, side=side,
            status=PositionStatus.OPEN,
            entry_price=0.5, entry_size_usd=entry_size_usd,
            shares=entry_size_usd / 0.5,
            opened_at=utcnow() - timedelta(minutes=10),
        ))


def test_categoriser_recognises_politics():
    assert categorise("Will Trump win the election?", "trump-election") == "politics"


def test_categoriser_recognises_crypto():
    assert categorise("Will Bitcoin hit $100k?", "btc-100k") == "crypto"


def test_categoriser_falls_back_to_other():
    assert categorise("Generic event with no keywords", "generic") == "other"


def test_optimizer_blocks_when_strategy_alloc_exhausted():
    market_id = _seed_market("0xa", "Politics market")
    # Overreaction allocation is 40% of equity = 4000 at 10000 equity
    _seed_open_position("overreaction", market_id, entry_size_usd=4500)
    opt = PortfolioOptimizer()
    throttle = opt.evaluate(
        strategy="overreaction", condition_id="0xb",
        side=Side.YES, question="Politics A", slug="pa",
        equity_usd=10_000,
    )
    assert throttle.blocked
    assert "allocation" in throttle.reason


def test_optimizer_blocks_when_category_cap_hit():
    cat_cap = 10_000 * settings.portfolio_max_category_exposure_pct
    m1 = _seed_market("0x1", "Trump election market 1")
    m2 = _seed_market("0x2", "Biden election market 2")
    _seed_open_position("overreaction", m1, entry_size_usd=cat_cap / 2 + 1)
    _seed_open_position("momentum", m2, entry_size_usd=cat_cap / 2 + 1)
    opt = PortfolioOptimizer()
    throttle = opt.evaluate(
        strategy="momentum", condition_id="0x3",
        side=Side.YES, question="Election update", slug="el-up",
        equity_usd=10_000,
    )
    assert throttle.blocked
    assert "category" in throttle.reason


def test_optimizer_throttles_when_correlated_bucket_loaded():
    # Same category + same direction → correlated exposure halves the multiplier.
    m1 = _seed_market("0x10", "Bitcoin moves up", slug="btc-1")
    _seed_market("0x11", "Ethereum moves up", slug="eth-1")
    cat_cap = 100_000 * settings.portfolio_max_category_exposure_pct
    _seed_open_position("overreaction", m1, entry_size_usd=cat_cap * 0.6, side=Side.YES)
    opt = PortfolioOptimizer()
    throttle = opt.evaluate(
        strategy="overreaction", condition_id="0x12",
        side=Side.YES, question="Solana moves up", slug="sol-1",
        equity_usd=100_000,
    )
    assert not throttle.blocked
    assert throttle.multiplier <= settings.portfolio_correlated_throttle_pct + 1e-6


def test_optimizer_clean_path_returns_unit_multiplier():
    opt = PortfolioOptimizer()
    throttle = opt.evaluate(
        strategy="overreaction", condition_id="0xz",
        side=Side.YES, question="Random sports market",
        slug="sport-x", equity_usd=10_000,
    )
    assert not throttle.blocked
    assert throttle.multiplier == 1.0
