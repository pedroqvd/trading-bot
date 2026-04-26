"""GET /markets — current universe snapshot from the in-memory cache."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.runner_proxy import get_runner_proxy

router = APIRouter(tags=["markets"], prefix="/markets")


class MarketSummary(BaseModel):
    condition_id: str
    slug: str
    question: str
    yes_bid: Optional[float]
    yes_ask: Optional[float]
    no_bid: Optional[float]
    no_ask: Optional[float]
    yes_mid: Optional[float]
    no_mid: Optional[float]
    yes_liquidity: Optional[float]
    no_liquidity: Optional[float]
    volume_24h: Optional[float]


class MarketsResponse(BaseModel):
    count: int
    refreshed_at: Optional[datetime]
    is_stale: bool
    markets: list[MarketSummary]


@router.get("", response_model=MarketsResponse)
def list_markets() -> MarketsResponse:
    proxy = get_runner_proxy()
    snapshot = proxy.snapshot_cache.latest() if proxy.snapshot_cache is not None else None

    if snapshot is None or snapshot.refreshed_at is None:
        return MarketsResponse(count=0, refreshed_at=None, is_stale=True, markets=[])

    return MarketsResponse(
        count=len(snapshot.quotes),
        refreshed_at=snapshot.refreshed_at,
        is_stale=snapshot.is_stale,
        markets=[
            MarketSummary(
                condition_id=q.condition_id,
                slug=q.slug,
                question=q.question,
                yes_bid=q.yes_bid,
                yes_ask=q.yes_ask,
                no_bid=q.no_bid,
                no_ask=q.no_ask,
                yes_mid=q.yes_mid,
                no_mid=q.no_mid,
                yes_liquidity=q.yes_liquidity,
                no_liquidity=q.no_liquidity,
                volume_24h=q.volume_24h,
            )
            for q in snapshot.quotes
        ],
    )
