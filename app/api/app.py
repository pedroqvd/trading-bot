"""FastAPI application factory."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import bot as bot_routes
from app.api.routes import equity as equity_routes
from app.api.routes import metrics as metrics_routes
from app.api.routes import positions as positions_routes
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

    app.include_router(metrics_routes.router)
    app.include_router(equity_routes.router)
    app.include_router(positions_routes.router)
    app.include_router(trades_routes.router)
    app.include_router(bot_routes.router)

    @app.get("/health", tags=["meta"])
    def health() -> dict:
        return {"status": "ok", "version": "2.0.0"}

    return app


app = create_app()
