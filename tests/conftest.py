"""Offline facilitator so the 402 path is testable without network."""
import os

os.environ["X402_SYNC_ON_START"] = "true"

from x402.http import HTTPFacilitatorClient
from x402.schemas.responses import SupportedKind, SupportedResponse

HTTPFacilitatorClient.get_supported = lambda self: SupportedResponse(
    kinds=[SupportedKind(x402_version=2, scheme="exact", network=os.environ.get("X402_NETWORK", "eip155:84532"))]
)
