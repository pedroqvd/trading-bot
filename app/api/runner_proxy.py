"""Thread-safe wrapper that lets the API start/stop the trading runner.

The runner runs in a daemon thread so the FastAPI process can stay
responsive. We expose minimal control: start, stop, status. State that
survives restarts (positions, trades, equity) lives in Postgres — this
proxy only owns the *thread* lifecycle.
"""
from __future__ import annotations

import threading
from datetime import datetime
from typing import Optional

from app.config import settings
from app.monitoring.logger import get_logger

log = get_logger(__name__)


class RunnerProxy:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._thread: Optional[threading.Thread] = None
        self._runner = None
        self._started_at: Optional[datetime] = None
        self._last_error: Optional[str] = None
        # Exposed so the /markets route can serve the live snapshot without
        # going through the runner directly.
        self.snapshot_cache = None

    @property
    def running(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    @property
    def started_at(self) -> Optional[datetime]:
        return self._started_at

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error

    @property
    def runner(self):
        return self._runner

    # -----------------------------------------------------------------------
    def start(self) -> bool:
        with self._lock:
            if self.running:
                return False
            from app.runner import TradingRunner
            self._runner = TradingRunner()
            # Signal handlers only work in the main thread; skip when running
            # inside a FastAPI worker thread.
            self.snapshot_cache = self._runner.snapshot_cache
            self._started_at = datetime.utcnow()
            self._last_error = None
            self._thread = threading.Thread(
                target=self._wrapped_run, daemon=True, name="trading-runner",
            )
            self._thread.start()
            log.info("runner_proxy.started")
            return True

    def stop(self, timeout: float = 10.0) -> bool:
        with self._lock:
            if not self.running:
                return False
            self._runner._handle_shutdown()
            thread = self._thread
        if thread:
            thread.join(timeout=timeout)
        with self._lock:
            still_alive = thread.is_alive() if thread else False
            if not still_alive:
                if self._runner:
                    try:
                        self._runner.close()
                    except Exception:  # noqa: BLE001
                        pass
                self._thread = None
                self._runner = None
                log.info("runner_proxy.stopped")
                return True
            log.warning("runner_proxy.stop_timeout")
            return False

    # -----------------------------------------------------------------------
    def _wrapped_run(self) -> None:
        try:
            self._runner.run_forever()
        except Exception as exc:  # noqa: BLE001
            log.exception("runner_proxy.crashed")
            self._last_error = str(exc)


# Singleton — there is exactly one runner per process.
_PROXY = RunnerProxy()


def get_runner_proxy() -> RunnerProxy:
    return _PROXY
