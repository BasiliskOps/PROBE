from mcp.server.mcpserver import MCPServer

from app.config import settings
from app.payments import build_mcp_paywall

mcp = MCPServer("probe", instructions=(
    "PROBE designs real space missions with real orbital mechanics and flies them in real time. "
    "design_mission takes one sentence and returns the launch window, route, gravity assists, propellant "
    "budget and launch vehicle, plus an owner token. Keep the token: mission_decide needs it."))
paid = build_mcp_paywall(settings.price_mission_design)


@mcp.tool()
@paid
async def design_mission(sentence: str) -> dict:
    """Design a real space mission from one sentence: next launch window, route, fuel budget, launch vehicle."""
    from app.api.routes import now_jd, public_view, run_design

    m, token = await run_design(sentence, plan="api")
    if m["status"] == "failed":
        return {"status": "failed", "error": m.get("error")}
    return {"owner_token": token, "mission": public_view(m, now_jd(), owner=True)}


@mcp.tool()
async def mission_status(mission_id: str) -> dict:
    """Where a probe is right now, what happens next, and any decision waiting on its owner."""
    from app.api.routes import now_jd, public_view
    from app.missions import store

    m = store.get(mission_id)
    if m is None:
        return {"status": "not_found"}
    return public_view(m, now_jd())


@mcp.tool()
async def mission_decide(mission_id: str, owner_token: str, decision_id: str, option_id: str) -> dict:
    """Answer an open decision point. Spending propellant now changes every later option."""
    from fastapi import HTTPException

    from app.api.routes import apply_decision

    try:
        return apply_decision(mission_id, decision_id, option_id, owner_token)
    except HTTPException as exc:
        return {"status": "rejected", "error": exc.detail}
