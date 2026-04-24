"""Backtest CLI.

Usage:
  python -m backtest.run --ticks path/to/ticks.csv
  python -m backtest.run --db --since 2025-01-01
  python -m backtest.run --walk-forward --folds 5 --ticks ticks.csv

CSV schema:
  ts,condition_id,slug,question,yes_token_id,no_token_id,yes_bid,yes_ask,no_bid,no_ask,volume_24h,depth_usd
"""
from __future__ import annotations

import csv
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable

import click

from app.database import session_scope
from app.database.models import Market, Quote
from app.monitoring.logger import configure_logging, get_logger
from backtest.engine import BacktestEngine, HistoricalTick
from backtest.walk_forward import WalkForwardValidator

log = get_logger(__name__)


def _load_csv(path: Path) -> list[HistoricalTick]:
    ticks: list[HistoricalTick] = []
    with path.open() as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            ticks.append(HistoricalTick(
                ts=datetime.fromisoformat(row["ts"]),
                condition_id=row["condition_id"],
                slug=row.get("slug", ""),
                question=row.get("question", ""),
                yes_token_id=row.get("yes_token_id", ""),
                no_token_id=row.get("no_token_id", ""),
                yes_bid=float(row["yes_bid"]),
                yes_ask=float(row["yes_ask"]),
                no_bid=float(row["no_bid"]),
                no_ask=float(row["no_ask"]),
                volume_24h=float(row.get("volume_24h", 0) or 0),
                depth_usd=float(row.get("depth_usd", 1000) or 1000),
            ))
    return ticks


def _load_from_db(since: datetime | None) -> list[HistoricalTick]:
    ticks: list[HistoricalTick] = []
    with session_scope() as session:
        from sqlalchemy import select
        stmt = select(Quote, Market).join(Market, Quote.market_id == Market.id)
        if since is not None:
            stmt = stmt.where(Quote.ts >= since)
        for quote, market in session.execute(stmt):
            if quote.yes_bid is None or quote.no_bid is None:
                continue
            ticks.append(HistoricalTick(
                ts=quote.ts,
                condition_id=market.condition_id,
                slug=market.slug,
                question=market.question,
                yes_token_id=market.yes_token_id or "",
                no_token_id=market.no_token_id or "",
                yes_bid=quote.yes_bid or 0.0,
                yes_ask=quote.yes_ask or 0.0,
                no_bid=quote.no_bid or 0.0,
                no_ask=quote.no_ask or 0.0,
                volume_24h=quote.volume_24h or 0.0,
                depth_usd=(quote.yes_liquidity or 0.0) + (quote.no_liquidity or 0.0),
            ))
    return ticks


@click.command()
@click.option("--ticks", "ticks_path", type=click.Path(path_type=Path), default=None,
              help="CSV file of historical ticks.")
@click.option("--db", is_flag=True, help="Load ticks from the configured database.")
@click.option("--since", type=click.DateTime(), default=None, help="Filter ticks after this timestamp.")
@click.option("--walk-forward", is_flag=True, help="Run walk-forward validation instead of single run.")
@click.option("--folds", type=int, default=5)
def main(ticks_path: Path | None, db: bool, since: datetime | None,
         walk_forward: bool, folds: int) -> None:
    configure_logging()
    if not ticks_path and not db:
        raise click.UsageError("Either --ticks or --db must be provided")

    ticks: Iterable[HistoricalTick]
    if ticks_path:
        ticks = _load_csv(ticks_path)
    else:
        ticks = _load_from_db(since)

    ticks = list(ticks)
    if not ticks:
        log.error("backtest.no_ticks")
        sys.exit(1)

    log.info("backtest.loaded", ticks=len(ticks))

    if walk_forward:
        validator = WalkForwardValidator(ticks, n_folds=folds)
        results = validator.run()
        summary = []
        for r in results:
            summary.append({
                "fold": r.fold,
                "params": r.params,
                "train_pnl": r.train_report.total_pnl_usd,
                "test_pnl": r.test_report.total_pnl_usd,
                "test_trades": r.test_report.trades,
                "test_winrate": r.test_report.win_rate,
                "test_expectancy": r.test_report.expectancy_usd,
            })
        print(json.dumps(summary, indent=2, default=str))
        return

    engine = BacktestEngine(ticks)
    report = engine.run()
    out = {
        "trades": report.trades,
        "wins": report.wins,
        "losses": report.losses,
        "win_rate": report.win_rate,
        "expectancy_usd": report.expectancy_usd,
        "profit_factor": report.profit_factor,
        "total_pnl_usd": report.total_pnl_usd,
        "final_equity": report.equity_curve[-1][1] if report.equity_curve else None,
    }
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
