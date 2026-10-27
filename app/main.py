import asyncio
import contextlib
import logging

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from mcp.server.transport_security import TransportSecuritySettings

from app.api.routes import router as api_router
from app.config import settings
from app.mcp_server import mcp
from app.payments import build_x402_middleware
from app.web import router as web_router

PAID_ROUTES = {"POST /api/v1/missions/design": settings.price_mission_design}

logging.basicConfig(level=logging.INFO)


def create_app(run_waker: bool = True) -> FastAPI:
    mcp_app = mcp.streamable_http_app(
        streamable_http_path="/",
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(
            allowed_hosts=[settings.public_host, f"{settings.public_host}:*"],
            allowed_origins=[f"https://{settings.public_host}", f"http://{settings.public_host}:*"],
        ),
    )

    @contextlib.asynccontextmanager
    async def lifespan(_app):
        from app import waker

        task = asyncio.create_task(waker.run_forever(settings.waker_interval_s)) if run_waker else None
        async with mcp.session_manager.run():
            yield
        if task:
            task.cancel()

    app = FastAPI(title=settings.product_name, lifespan=lifespan)
    app.middleware("http")(build_x402_middleware(PAID_ROUTES))
    app.include_router(api_router, prefix="/api/v1")
    app.include_router(web_router)
    app.mount("/mcp", mcp_app)
    app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")

    @app.get("/healthz")
    async def healthz():
        return {"ok": True}

    return app


app = create_app()
