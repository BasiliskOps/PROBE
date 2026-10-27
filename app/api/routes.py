from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


class MissionRequest(BaseModel):
    sentence: str


class Decision(BaseModel):
    decision_id: str
    choice: str


@router.post("/missions/design")
async def design_mission(req: MissionRequest):
    # Week 1: swarm planner -> launch window, gravity assists, delta-v budget, launch vehicle (JPL Horizons + pykep/poliastro)
    raise HTTPException(status_code=501, detail="mission design not built yet")


@router.get("/missions/{mission_id}")
async def get_mission(mission_id: str):
    raise HTTPException(status_code=501, detail="mission state not built yet")


@router.post("/missions/{mission_id}/decisions")
async def decide(mission_id: str, decision: Decision):
    raise HTTPException(status_code=501, detail="decision points not built yet")
