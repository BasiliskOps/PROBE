"""x402 per-call billing for REST routes and MCP tools."""
from __future__ import annotations

from x402.http import HTTPFacilitatorClient
from x402.http.middleware.fastapi import payment_middleware
from x402 import x402ResourceServer
from x402.mechanisms.evm.exact import register_exact_evm_server

from app.config import settings


def _server() -> x402ResourceServer:
    server = x402ResourceServer(HTTPFacilitatorClient())
    register_exact_evm_server(server, settings.x402_network)
    return server


def _accepts(price: str) -> dict:
    return {
        "scheme": "exact",
        "payTo": settings.x402_pay_to,
        "price": price,
        "network": settings.x402_network,
    }


def build_x402_middleware(paid_routes: dict[str, str]):
    """paid_routes maps "METHOD /path" to a price string like "$1.00"."""
    routes = {route: {"accepts": _accepts(price)} for route, price in paid_routes.items()}
    return payment_middleware(routes, _server(), sync_facilitator_on_start=settings.x402_sync_on_start)


def build_mcp_paywall(price: str):
    """Returns a decorator for paid MCP tools. Wired to x402.mcp in week 1, once the wallet and facilitator are live."""
    def decorator(fn):
        fn.__x402_price__ = price
        return fn
    return decorator
