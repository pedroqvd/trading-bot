"""Polymarket data + execution client.

Two separate concerns:

1. **Gamma API** (public) — market discovery, metadata, historical prices.
2. **CLOB API** — order books, order placement, cancellation.
   For authenticated CLOB calls we delegate to the official `py-clob-client`
   when credentials are configured; otherwise we use public REST endpoints.
"""
from __future__ import annotations

import json
import time
from typing import Any, Iterable, Optional

import httpx

from app.config import settings
from app.data.schemas import BookLevel, MarketQuote, OrderBook
from app.monitoring.logger import get_logger
from app.monitoring.metrics import API_LATENCY
from app.utils.time_utils import parse_iso

log = get_logger(__name__)


class PolymarketAPIError(RuntimeError):
    pass


class PolymarketClient:
    def __init__(self) -> None:
        self._gamma = httpx.Client(
            base_url=settings.polymarket_gamma_url,
            timeout=httpx.Timeout(10.0, connect=5.0),
            headers={"User-Agent": "trading-bot/1.0"},
        )
        self._clob = httpx.Client(
            base_url=settings.polymarket_clob_url,
            timeout=httpx.Timeout(10.0, connect=5.0),
            headers={"User-Agent": "trading-bot/1.0"},
        )
        self._signed_client = None
        if settings.has_live_credentials:
            self._signed_client = self._build_signed_client()

    # -----------------------------------------------------------------------
    # Lifecycle
    # -----------------------------------------------------------------------
    def close(self) -> None:
        self._gamma.close()
        self._clob.close()

    def __enter__(self) -> "PolymarketClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -----------------------------------------------------------------------
    # Signed client (py-clob-client) — lazy import
    # -----------------------------------------------------------------------
    def _build_signed_client(self):
        try:
            from py_clob_client.client import ClobClient
            from py_clob_client.clob_types import ApiCreds
        except ImportError:  # pragma: no cover
            log.warning("polymarket.signed_client_unavailable",
                        reason="py_clob_client not installed")
            return None

        creds = ApiCreds(
            api_key=settings.polymarket_api_key,
            api_secret=settings.polymarket_api_secret,
            api_passphrase=settings.polymarket_api_passphrase,
        )
        client = ClobClient(
            host=settings.polymarket_clob_url,
            key=settings.polymarket_private_key,
            chain_id=settings.polymarket_chain_id,
            creds=creds,
            funder=settings.polymarket_funder_address,
            signature_type=1 if settings.polymarket_funder_address else 0,
        )
        return client

    @property
    def has_signed_client(self) -> bool:
        return self._signed_client is not None

    @property
    def signed(self):
        if self._signed_client is None:
            raise PolymarketAPIError("No Polymarket credentials configured")
        return self._signed_client

    # -----------------------------------------------------------------------
    # Gamma API
    # -----------------------------------------------------------------------
    def list_active_markets(self, limit: int = 200, offset: int = 0) -> list[dict]:
        """Fetch active binary markets ordered by 24h volume."""
        params = {
            "limit": limit,
            "offset": offset,
            "active": "true",
            "closed": "false",
            "archived": "false",
            "order": "volume24hr",
            "ascending": "false",
        }
        data = self._gamma_get("/markets", params=params)
        if isinstance(data, dict) and "data" in data:
            data = data["data"]
        return [m for m in data if self._is_binary(m)]

    def iter_active_markets(self, batch_size: int = 200, max_total: int = 1000) -> Iterable[dict]:
        offset = 0
        fetched = 0
        while fetched < max_total:
            batch = self.list_active_markets(limit=batch_size, offset=offset)
            if not batch:
                return
            for m in batch:
                yield m
                fetched += 1
                if fetched >= max_total:
                    return
            offset += batch_size

    def get_price_history(self, token_id: str, interval: str = "1h", fidelity: int = 60) -> list[dict]:
        """Return price history points for a token. Used for overreaction edge."""
        params = {"market": token_id, "interval": interval, "fidelity": fidelity}
        data = self._clob_get("/prices-history", params=params)
        if isinstance(data, dict):
            return data.get("history", [])
        return data or []

    @staticmethod
    def _is_binary(market: dict) -> bool:
        """Polymarket markets are nominally binary; filter defensively."""
        tokens = PolymarketClient._token_ids(market)
        return len(tokens) == 2 and bool(market.get("conditionId"))

    # -----------------------------------------------------------------------
    # CLOB — order books
    # -----------------------------------------------------------------------
    def get_orderbook(self, token_id: str) -> OrderBook:
        data = self._clob_get("/book", params={"token_id": token_id})
        return self._parse_book(data)

    def get_orderbooks(self, token_ids: list[str]) -> dict[str, OrderBook]:
        """Batch order book fetch via /books."""
        if not token_ids:
            return {}
        payload = [{"token_id": t} for t in token_ids]
        try:
            data = self._clob_post("/books", json=payload)
        except PolymarketAPIError:
            return {t: self.get_orderbook(t) for t in token_ids}
        out: dict[str, OrderBook] = {}
        for entry in (data or []):
            tid = entry.get("asset_id") or entry.get("token_id")
            if tid:
                out[tid] = self._parse_book(entry)
        # Fallback for any missing token
        for t in token_ids:
            if t not in out:
                try:
                    out[t] = self.get_orderbook(t)
                except PolymarketAPIError:
                    out[t] = OrderBook()
        return out

    @staticmethod
    def _parse_book(data: dict) -> OrderBook:
        if not data:
            return OrderBook()
        bids_raw = data.get("bids", [])
        asks_raw = data.get("asks", [])
        bids = [BookLevel(price=float(x.get("price", 0)), size=float(x.get("size", 0))) for x in bids_raw]
        asks = [BookLevel(price=float(x.get("price", 0)), size=float(x.get("size", 0))) for x in asks_raw]
        bids.sort(key=lambda l: l.price, reverse=True)
        asks.sort(key=lambda l: l.price)
        return OrderBook(bids=bids, asks=asks)

    # -----------------------------------------------------------------------
    # Quotes — high-level composition of market metadata + books
    # -----------------------------------------------------------------------
    def build_quote(self, market: dict, books: dict[str, OrderBook]) -> Optional[MarketQuote]:
        tokens = self._token_ids(market)
        if len(tokens) != 2:
            return None
        yes_id, no_id = self._order_tokens(market, tokens)
        yes_book = books.get(yes_id, OrderBook())
        no_book = books.get(no_id, OrderBook())
        end_date = None
        if market.get("endDate"):
            try:
                end_date = parse_iso(market["endDate"])
            except ValueError:
                end_date = None
        return MarketQuote(
            condition_id=market.get("conditionId", ""),
            slug=market.get("slug", ""),
            question=market.get("question", ""),
            yes_token_id=yes_id,
            no_token_id=no_id,
            yes_book=yes_book,
            no_book=no_book,
            volume_24h=float(market.get("volume24hr") or market.get("volume", 0) or 0),
            end_date=end_date,
            active=bool(market.get("active", True)),
            closed=bool(market.get("closed", False)),
            raw=market,
        )

    @staticmethod
    def _token_ids(market: dict) -> list[str]:
        raw = market.get("clobTokenIds")
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                raw = []
        if isinstance(raw, list):
            return [str(t) for t in raw]
        tokens = market.get("tokens") or []
        return [str(t.get("token_id")) for t in tokens if t.get("token_id")]

    @staticmethod
    def _order_tokens(market: dict, tokens: list[str]) -> tuple[str, str]:
        """Return (yes_token_id, no_token_id) honouring outcome labels when available."""
        outcomes = market.get("outcomes")
        if isinstance(outcomes, str):
            try:
                outcomes = json.loads(outcomes)
            except json.JSONDecodeError:
                outcomes = None
        if isinstance(outcomes, list) and len(outcomes) == 2:
            labels = [str(o).upper() for o in outcomes]
            if labels[0].startswith("N"):
                # order is [NO, YES]
                return tokens[1], tokens[0]
        return tokens[0], tokens[1]

    # -----------------------------------------------------------------------
    # HTTP helpers with metrics + retries
    # -----------------------------------------------------------------------
    def _gamma_get(self, path: str, params: dict | None = None) -> Any:
        return self._do_request(self._gamma, "GET", path, params=params, label=f"gamma:{path}")

    def _clob_get(self, path: str, params: dict | None = None) -> Any:
        return self._do_request(self._clob, "GET", path, params=params, label=f"clob:{path}")

    def _clob_post(self, path: str, json: Any | None = None) -> Any:
        return self._do_request(self._clob, "POST", path, json=json, label=f"clob:{path}")

    @staticmethod
    def _do_request(client: httpx.Client, method: str, path: str,
                    params: dict | None = None, json: Any | None = None,
                    label: str = "") -> Any:
        attempts = 0
        last_exc: Exception | None = None
        while attempts < 4:
            attempts += 1
            started = time.monotonic()
            try:
                resp = client.request(method, path, params=params, json=json)
                API_LATENCY.labels(endpoint=label).observe(time.monotonic() - started)
                if resp.status_code >= 500:
                    raise PolymarketAPIError(f"{label} → HTTP {resp.status_code}")
                if resp.status_code == 429:
                    time.sleep(2 ** attempts)
                    continue
                if resp.status_code >= 400:
                    raise PolymarketAPIError(f"{label} → HTTP {resp.status_code}: {resp.text[:200]}")
                if not resp.content:
                    return None
                return resp.json()
            except (httpx.HTTPError, PolymarketAPIError) as exc:
                last_exc = exc
                log.warning("polymarket.request_failed", label=label, attempt=attempts, error=str(exc))
                time.sleep(min(2 ** attempts, 16))
        raise PolymarketAPIError(f"{label} failed after {attempts} attempts: {last_exc}")
