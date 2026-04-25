"""Decoupled market-data ingestion.

The trading runner consumes a *snapshot* from this layer rather than driving
the API itself. That gives us:

  • independent ingestion cadence (faster than trading cadence)
  • a single point of caching for the FastAPI layer to expose
  • a clean swap-in point for a future websocket source

Concurrency model:
  • A background `IngestionLoop.run()` thread refreshes the universe every
    `interval_seconds` and writes both into the DB (via `MarketStore`) and
    into an in-memory `SnapshotCache`.
  • The trading runner reads `SnapshotCache.latest()` — never blocks on HTTP.
  • The API layer reads the same cache for `/markets`-style endpoints.

This module intentionally has no FastAPI dependency.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, Optional

from app.data.market_store import MarketStore
from app.data.polymarket_client import PolymarketClient
from app.data.schemas import MarketQuote
from app.monitoring.logger import get_logger
from app.utils.time_utils import utcnow

log = get_logger(__name__)


@dataclass
class Snapshot:
    quotes: list[MarketQuote] = field(default_factory=list)
    refreshed_at: Optional[datetime] = None
    duration_ms: int = 0

    @property
    def is_stale(self) -> bool:
        if self.refreshed_at is None:
            return True
        return (utcnow() - self.refreshed_at).total_seconds() > 120


class SnapshotCache:
    """Thread-safe single-slot cache for the most recent universe snapshot."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._snapshot = Snapshot()

    def update(self, quotes: Iterable[MarketQuote], duration_ms: int) -> None:
        with self._lock:
            self._snapshot = Snapshot(
                quotes=list(quotes),
                refreshed_at=utcnow(),
                duration_ms=duration_ms,
            )

    def latest(self) -> Snapshot:
        with self._lock:
            return self._snapshot


class IngestionLoop:
    """Background polling loop. Optional — runner can also drive ingestion inline."""

    def __init__(
        self,
        client: PolymarketClient,
        store: MarketStore,
        cache: SnapshotCache,
        *,
        interval_seconds: int = 30,
        max_markets: int = 500,
    ) -> None:
        self.client = client
        self.store = store
        self.cache = cache
        self.interval_seconds = interval_seconds
        self.max_markets = max_markets
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    # -----------------------------------------------------------------------
    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="ingestion")
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=timeout)
        self._thread = None

    def _loop(self) -> None:
        while not self._stop.is_set():
            started = time.monotonic()
            try:
                quotes = self.store.refresh_universe(max_markets=self.max_markets)
                self.cache.update(quotes, duration_ms=int((time.monotonic() - started) * 1000))
            except Exception:  # noqa: BLE001
                log.exception("ingestion.failed")
            self._stop.wait(self.interval_seconds)
