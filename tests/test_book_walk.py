from app.data.schemas import BookLevel, OrderBook
from app.execution.book_walk import (
    plan_arbitrage_execution,
    walk_book_for_notional,
    walk_book_for_shares,
)


def _book(asks: list[tuple[float, float]], bids: list[tuple[float, float]] | None = None) -> OrderBook:
    return OrderBook(
        asks=[BookLevel(p, s) for p, s in asks],
        bids=[BookLevel(p, s) for p, s in (bids or [])],
    )


def test_walk_top_level_only():
    book = _book(asks=[(0.5, 100), (0.6, 100)])
    fill = walk_book_for_shares(book, "BUY", 50)
    assert abs(fill.avg_price - 0.5) < 1e-9
    assert fill.filled_shares == 50
    assert not fill.exhausted


def test_walk_consumes_multiple_levels_with_vwap():
    book = _book(asks=[(0.5, 50), (0.6, 50)])
    fill = walk_book_for_shares(book, "BUY", 100)
    expected_avg = (50 * 0.5 + 50 * 0.6) / 100
    assert abs(fill.avg_price - expected_avg) < 1e-9
    assert fill.filled_shares == 100
    assert fill.levels_consumed == 2


def test_walk_marks_exhausted_when_book_too_thin():
    book = _book(asks=[(0.5, 10)])
    fill = walk_book_for_shares(book, "BUY", 100)
    assert fill.exhausted
    assert fill.filled_shares == 10


def test_walk_for_notional_handles_partial_top():
    book = _book(asks=[(0.5, 100)])
    fill = walk_book_for_notional(book, "BUY", 25)
    assert fill.filled_notional == 25
    assert fill.filled_shares == 50  # 25 / 0.5
    assert not fill.exhausted


def test_arb_plan_zero_when_book_too_thin():
    yes_book = _book(asks=[(0.50, 5)])
    no_book = _book(asks=[(0.40, 5)])
    plan = plan_arbitrage_execution(yes_book, no_book, target_bonds=100,
                                    safety_multiplier=1.1, min_profit_per_bond=0.02)
    assert plan.exhausted


def test_arb_plan_returns_vwap_and_confidence():
    yes_book = _book(asks=[(0.45, 100), (0.46, 100)])
    no_book = _book(asks=[(0.40, 100), (0.41, 100)])
    plan = plan_arbitrage_execution(yes_book, no_book, target_bonds=50,
                                    safety_multiplier=1.1, min_profit_per_bond=0.02)
    assert not plan.exhausted
    assert plan.bonds == 50
    # Both books have ample top depth for 55 shares (50 × 1.1 safety) → top level VWAP only
    assert abs(plan.yes_avg_price - 0.45) < 1e-3
    assert abs(plan.no_avg_price - 0.40) < 1e-3
    assert plan.profit_per_bond > 0.10
    assert 0 < plan.confidence <= 1.0
