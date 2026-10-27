"""Human-facing pages: one free probe per browser, mission pages, decisions by cookie."""
from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from app.api.routes import apply_decision, now_jd, public_view
from app.astro.search import iso
from app.config import settings
from app.missions import designer, store

TEMPLATES = Jinja2Templates(directory=Path(__file__).parent / "templates")
TEMPLATES.env.globals["iso"] = iso


def human(value) -> str:
    """'2026-11-15' or a Julian date -> 'Nov 15, 2026'."""
    from datetime import datetime

    d = datetime.strptime(iso(value) if isinstance(value, (int, float)) else value, "%Y-%m-%d")
    return f"{d:%b} {d.day}, {d.year}"


TEMPLATES.env.filters["human"] = human
router = APIRouter()
_tasks: set[asyncio.Task] = set()

COOKIE_FREE = "probe_free"


def _owner_cookie(mid: str) -> str:
    return f"probe_owner_{mid}"


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return TEMPLATES.TemplateResponse(request, "index.html", {"product_name": settings.product_name})


@router.post("/web/missions")
async def create(request: Request, sentence: str = Form(min_length=8, max_length=400)):
    used = int(request.cookies.get(COOKIE_FREE, "0") or 0)
    if used >= settings.free_probes_per_browser:
        return TEMPLATES.TemplateResponse(request, "_limit.html", {}, status_code=402)
    mid, token = store.create(sentence)
    task = asyncio.create_task(designer.design(mid, plan="free"))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    resp = Response(status_code=204, headers={"HX-Redirect": f"/m/{mid}"})
    if "hx-request" not in request.headers:
        resp = RedirectResponse(f"/m/{mid}", status_code=303)
    cookie = dict(httponly=True, samesite="lax", max_age=60 * 60 * 24 * 365 * 15,
                  secure=request.url.scheme == "https")
    resp.set_cookie(_owner_cookie(mid), token, **cookie)
    resp.set_cookie(COOKIE_FREE, str(used + 1), **cookie)
    return resp


def _view(request: Request, mid: str) -> tuple[dict, dict, bool]:
    m = store.get(mid)
    if m is None:
        raise HTTPException(status_code=404, detail="no such mission")
    owner = store.is_owner(mid, request.cookies.get(_owner_cookie(mid)))
    return m, public_view(m, now_jd(), owner=owner), owner


@router.get("/m/{mid}", response_class=HTMLResponse)
async def mission_page(request: Request, mid: str):
    m, v, owner = _view(request, mid)
    return TEMPLATES.TemplateResponse(request, "mission.html", {"v": v, "owner": owner, "messages": store.messages(mid)})


@router.get("/web/m/{mid}/panel", response_class=HTMLResponse)
async def panel(request: Request, mid: str):
    m, v, owner = _view(request, mid)
    resp = TEMPLATES.TemplateResponse(request, "_panel.html", {"v": v, "owner": owner, "messages": store.messages(mid)})
    if v["status"] not in ("designing",) and request.headers.get("hx-target") == "panel" and \
            request.query_params.get("was") == "designing":
        resp.headers["HX-Refresh"] = "true"  # trajectory just landed: reload so the sky draws it
    return resp


@router.post("/web/m/{mid}/decide", response_class=HTMLResponse)
async def decide(request: Request, mid: str, decision_id: str = Form(), option_id: str = Form()):
    error = None
    try:
        apply_decision(mid, decision_id, option_id, request.cookies.get(_owner_cookie(mid)))
    except HTTPException as exc:
        error = exc.detail
    m, v, owner = _view(request, mid)
    return TEMPLATES.TemplateResponse(request, "_panel.html",
                                      {"v": v, "owner": owner, "messages": store.messages(mid), "error": error})
