"""Tests for realistic execution helpers (latency + dynamic slippage)."""
from app.config import settings
from app.data.schemas import BookLevel, OrderBook
from app.execution.realistic_execution import (
    LatencyBudget,
    apply_latency,
    dynamic_slippage_bps,
    sample_latency,
)


def _book(asks: list[tuple[float, float]]) -> OrderBook:
    return OrderBook(
        asks=[BookLevel(p, s) for p, s in asks],
        bids=[],
    )


def test_sample_latency_within_bounds():
    for _ in range(50):
        budget = sample_latency()
        assert isinstance(budget, LatencyBudget)
        assert settings.exec_latency_min_ms <= budget.sleep_ms <= settings.exec_latency_max_ms


def test_apply_latency_zero_is_noop():
    apply_latency(LatencyBudget(0, False))


def test_dynamic_slippage_grows_with_size():
    book = _book([(0.5, 100), (0.6, 100)])
    small = dynamic_slippage_bps(book=book, side="BUY", shares=5,
                                 realized_vol=0.0, base_bps=20)
    big = dynamic_slippage_bps(book=book, side="BUY", shares=80,
                               realized_vol=0.0, base_bps=20)
    assert big > small


def test_dynamic_slippage_grows_with_volatility():
    book = _book([(0.5, 100)])
    calm = dynamic_slippage_bps(book=book, side="BUY", shares=10,
                                realized_vol=0.001, base_bps=20)
    wild = dynamic_slippage_bps(book=book, side="BUY", shares=10,
                                realized_vol=0.10, base_bps=20)
    assert wild > calm


def test_dynamic_slippage_respects_disabled_flag(monkeypatch):
    monkeypatch.setattr(settings, "exec_dynamic_slippage_enabled", False)
    book = _book([(0.5, 100)])
    bps = dynamic_slippage_bps(book=book, side="BUY", shares=80,
                               realized_vol=0.10, base_bps=15)
    assert bps == 15
