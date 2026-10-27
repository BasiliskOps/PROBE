from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from mcp.server.transport_security import TransportSecuritySettings

from app.api.routes import router as api_router
from app.config import settings
from app.mcp_server import mcp
from app.payments import build_x402_middleware

TEMPLATES = Jinja2Templates(directory=Path(__file__).parent / "templates")

PAID_ROUTES = {"POST /api/v1/missions/design": settings.price_mission_design}


def create_app() -> FastAPI:
    mcp_app = mcp.streamable_http_app(
        streamable_http_path="/",
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(
            allowed_hosts=[settings.public_host, f"{settings.public_host}:*"],
            allowed_origins=[f"https://{settings.public_host}", f"http://{settings.public_host}:*"],
        ),
    )
    app = FastAPI(title=settings.product_name, lifespan=lambda _app: mcp.session_manager.run())
    app.middleware("http")(build_x402_middleware(PAID_ROUTES))
    app.include_router(api_router, prefix="/api/v1")
    app.mount("/mcp", mcp_app)

    @app.get("/")
    async def index(request: Request):
        return TEMPLATES.TemplateResponse(request, "index.html", {"product_name": settings.product_name})

    @app.get("/healthz")
    async def healthz():
        return {"ok": True}

    return app


app = create_app()
