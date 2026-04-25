"""Entry point for `python -m app.api_main`."""
from __future__ import annotations

import uvicorn

from app.config import settings


def main() -> None:
    uvicorn.run(
        "app.api.app:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
        log_config=None,
    )


if __name__ == "__main__":
    main()
