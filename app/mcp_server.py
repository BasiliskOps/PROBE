from mcp.server.mcpserver import MCPServer

from app.config import settings
from app.payments import build_mcp_paywall

mcp = MCPServer("probe")
paid = build_mcp_paywall(settings.price_mission_design)


@mcp.tool()
@paid
async def design_mission(sentence: str) -> dict:
    """Design a real space mission from one sentence: launch window, trajectory, fuel budget, launch vehicle."""
    return {"status": "not_built"}


@mcp.tool()
async def mission_status(mission_id: str) -> dict:
    """Where a probe is right now and what happens next."""
    return {"status": "not_built", "mission_id": mission_id}
