"""FastAPI application factory."""
from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import require_api_key
from app.api.routes import bot as bot_routes
from app.api.routes import equity as equity_routes
from app.api.routes import markets as markets_routes
from app.api.routes import metrics as metrics_routes
from app.api.routes import positions as positions_routes
from app.api.routes import risk as risk_routes
from app.api.routes import trades as trades_routes
from app.config import settings
from app.database import init_db
from app.monitoring.logger import configure_logging


def create_app() -> FastAPI:
    configure_logging()
    init_db()

    app = FastAPI(
        title="Polymarket Trading Bot API",
        version="2.0.0",
        description="Read + control surface for the trading engine.",
    )

    origins = (
        ["*"]
        if settings.api_cors_origins.strip() == "*"
        else [o.strip() for o in settings.api_cors_origins.split(",") if o.strip()]
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # /health is always open (liveness probe).  Everything else requires an
    # API key when API_KEY is configured.
    auth = Depends(require_api_key)
    app.include_router(metrics_routes.router, dependencies=[auth])
    app.include_router(equity_routes.router, dependencies=[auth])
    app.include_router(positions_routes.router, dependencies=[auth])
    app.include_router(trades_routes.router, dependencies=[auth])
    app.include_router(bot_routes.router, dependencies=[auth])
    app.include_router(risk_routes.router, dependencies=[auth])
    app.include_router(markets_routes.router, dependencies=[auth])

    @app.get("/health", tags=["meta"])
    def health() -> dict:
        return {"status": "ok", "version": "2.0.0"}

    return app


app = create_app()
