from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from tradex.auto.engine import default_engine
from tradex.auto.profiles import available_profiles
from tradex.auto.worker import worker

router = APIRouter()


class HaltRequest(BaseModel):
    confirmation: str
    reason: str = "automation emergency halt"


@router.get("/api/auto/health")
def auto_health() -> dict:
    return worker.health()


@router.get("/api/auto/profiles")
def auto_profiles() -> dict:
    return {"profiles": [profile.to_dict() for profile in available_profiles().values()]}


@router.get("/api/auto/runs")
def auto_runs() -> dict:
    engine = default_engine()
    return {"runs": engine.store.runs()}


@router.get("/api/auto/status")
def auto_status() -> dict:
    engine = default_engine()
    drill_id = engine.store.latest_drill_id()
    if drill_id is None:
        raise HTTPException(status_code=404, detail="No automation run has been created")
    return engine.status(drill_id)


@router.post("/api/auto/halt")
def auto_halt(request: HaltRequest) -> dict:
    if request.confirmation != "HALT":
        raise HTTPException(status_code=400, detail="confirmation must be HALT")
    engine = default_engine()
    drill_id = engine.store.latest_drill_id()
    if drill_id is None:
        raise HTTPException(status_code=404, detail="No automation run has been created")
    engine.halt(drill_id, request.reason)
    return {"run_id": drill_id, "status": "HALTED"}
