"""Walk-forward validation harness.

Splits the tick history into train/test folds, re-fits any tunable parameters
on the train fold (currently: overreaction_move_pct, reversion_target) and
evaluates on the held-out test fold. The overall out-of-sample performance is
the aggregation of the per-fold test results — this guards against overfitting
a single static parameter set to historical noise.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Iterable, Sequence

from app.config import settings
from backtest.engine import BacktestEngine, BacktestReport, HistoricalTick


@dataclass
class FoldResult:
    fold: int
    params: dict
    train_report: BacktestReport
    test_report: BacktestReport


class WalkForwardValidator:
    def __init__(
        self,
        ticks: Sequence[HistoricalTick],
        n_folds: int = 5,
        move_grid: Iterable[float] = (0.05, 0.08, 0.1, 0.12, 0.15),
        reversion_grid: Iterable[float] = (0.3, 0.5, 0.7),
    ) -> None:
        assert n_folds >= 2
        self.ticks = sorted(ticks, key=lambda t: t.ts)
        self.n_folds = n_folds
        self.move_grid = list(move_grid)
        self.reversion_grid = list(reversion_grid)

    def run(self) -> list[FoldResult]:
        results: list[FoldResult] = []
        fold_size = len(self.ticks) // (self.n_folds + 1)
        for fold in range(self.n_folds):
            train = self.ticks[: (fold + 1) * fold_size]
            test = self.ticks[(fold + 1) * fold_size: (fold + 2) * fold_size]
            if not train or not test:
                break
            best_params, best_train = self._grid_search(train)
            test_report = self._eval(test, best_params)
            results.append(FoldResult(fold=fold, params=best_params,
                                      train_report=best_train, test_report=test_report))
        return results

    def _grid_search(self, ticks: Sequence[HistoricalTick]) -> tuple[dict, BacktestReport]:
        best: tuple[dict, BacktestReport] | None = None
        for move, reversion in itertools.product(self.move_grid, self.reversion_grid):
            params = {
                "overreaction_move_pct": move,
                "overreaction_reversion_target": reversion,
            }
            rep = self._eval(ticks, params)
            score = rep.total_pnl_usd
            if best is None or score > best[1].total_pnl_usd:
                best = (params, rep)
        return best  # type: ignore[return-value]

    def _eval(self, ticks: Sequence[HistoricalTick], params: dict) -> BacktestReport:
        # Temporarily override settings via monkey-patch-safe attribute sets
        original = {k: getattr(settings, k) for k in params}
        try:
            for k, v in params.items():
                object.__setattr__(settings, k, v)
            engine = BacktestEngine(ticks)
            return engine.run()
        finally:
            for k, v in original.items():
                object.__setattr__(settings, k, v)
