"""Bot status + control endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from app.api.runner_proxy import RunnerProxy, get_runner_proxy
from app.api.schemas import BotControlResponse, BotStatus
from app.config import settings
from app.database import session_scope
from app.database.models import EquitySnapshot, Position, PositionStatus

router = APIRouter(tags=["bot"], prefix="/bot")


def _proxy() -> RunnerProxy:
    return get_runner_proxy()


@router.get("/status", response_model=BotStatus)
def status(proxy: RunnerProxy = Depends(_proxy)) -> BotStatus:
    with session_scope() as session:
        latest = session.execute(
            select(EquitySnapshot).order_by(EquitySnapshot.ts.desc()).limit(1)
        ).scalar_one_or_none()
        last_ts = latest.ts if latest else None
        equity = float(latest.equity_usd) if latest else float(settings.capital_usd)
        open_count = session.execute(
            select(func.count(Position.id)).where(Position.status == PositionStatus.OPEN)
        ).scalar_one() or 0

    return BotStatus(
        running=proxy.running,
        started_at=proxy.started_at,
        last_loop_at=last_ts,
        last_error=proxy.last_error,
        open_positions=int(open_count),
        equity_usd=equity,
        dry_run=settings.dry_run,
        live_trading_enabled=settings.live_trading_enabled,
    )


@router.post("/start", response_model=BotControlResponse)
def start(proxy: RunnerProxy = Depends(_proxy)) -> BotControlResponse:
    started = proxy.start()
    if started:
        return BotControlResponse(running=True, message="runner started")
    return BotControlResponse(running=proxy.running, message="runner already running")


@router.post("/stop", response_model=BotControlResponse)
def stop(proxy: RunnerProxy = Depends(_proxy)) -> BotControlResponse:
    stopped = proxy.stop()
    if stopped:
        return BotControlResponse(running=False, message="runner stopped")
    return BotControlResponse(running=proxy.running,
                              message="runner was not running" if not proxy.running
                              else "stop timed out")
