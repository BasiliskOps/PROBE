"""Test environment: offline JPL kernel, a throwaway database, a small fast search,
and an offline x402 facilitator so the 402 path is testable without network."""
import os
import tempfile

os.environ["X402_SYNC_ON_START"] = "true"
os.environ["EPHEMERIS_SOURCE"] = "de421"
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="probe-test-")
os.environ["SEARCH_HORIZON_DAYS"] = "800"
os.environ["SEARCH_WORKERS"] = "1"
os.environ["SEARCH_MAXITER"] = "120"
os.environ["ANTHROPIC_API_KEY"] = ""

from x402.http import HTTPFacilitatorClient  # noqa: E402
from x402.schemas.responses import SupportedKind, SupportedResponse  # noqa: E402

HTTPFacilitatorClient.get_supported = lambda self: SupportedResponse(
    kinds=[SupportedKind(x402_version=2, scheme="exact", network=os.environ.get("X402_NETWORK", "eip155:84532"))]
)
