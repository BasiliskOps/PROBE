"""User-initiated checkout behind one interface, so the provider can be swapped."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.config import settings


@dataclass
class CheckoutSession:
    url: str
    session_id: str


class CheckoutProvider(ABC):
    @abstractmethod
    async def create_session(self, plan: str, customer_ref: str) -> CheckoutSession: ...

    @abstractmethod
    async def verify_webhook(self, payload: bytes, signature: str) -> dict: ...


class DevCheckout(CheckoutProvider):
    """Local stand-in until a real provider is chosen."""

    async def create_session(self, plan: str, customer_ref: str) -> CheckoutSession:
        return CheckoutSession(url=f"/checkout/dev?plan={plan}", session_id=f"dev-{customer_ref}")

    async def verify_webhook(self, payload: bytes, signature: str) -> dict:
        return {"event": "dev", "verified": False}


def get_checkout_provider() -> CheckoutProvider:
    providers = {"dev": DevCheckout}
    return providers[settings.checkout_provider]()
