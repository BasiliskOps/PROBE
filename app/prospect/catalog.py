"""Live asteroid catalog from the JPL Small-Body Database query API.

https://ssd-api.jpl.nasa.gov/doc/sbdb_query.html
Two feeds:
- characterized: asteroids with a measured spectral class (SMASSII or Tholen),
  the targets whose composition we can infer best;
- new NEOs: near-Earth asteroids with short observation arcs, which is how
  fresh discoveries show up. The house fleet watches this one.
Results are cached on disk and refreshed daily.
"""
from __future__ import annotations

import json
import logging
import math
import time
from pathlib import Path

import httpx

from app.config import settings

log = logging.getLogger(__name__)

SBDB_QUERY = "https://ssd-api.jpl.nasa.gov/sbdb_query.api"
FIELDS = ["pdes", "full_name", "epoch", "a", "e", "i", "om", "w", "ma", "H", "diameter", "albedo",
          "spec_B", "spec_T", "neo", "pha", "class", "first_obs", "data_arc"]
CACHE_TTL_S = 24 * 3600
FIXTURE = Path(__file__).parent / "fixture_sbdb.json"


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def diameter_from_h(h: float, albedo: float) -> float:
    """Effective diameter (km) from absolute magnitude and geometric albedo."""
    return 1329.0 / math.sqrt(albedo) * 10 ** (-h / 5.0)


def normalize(row: dict) -> dict | None:
    el = {k: _num(row.get(k)) for k in ("epoch", "a", "e", "i", "om", "w", "ma", "H", "diameter", "albedo",
                                         "data_arc")}
    if None in (el["epoch"], el["a"], el["e"], el["i"], el["om"], el["w"], el["ma"]) or el["e"] >= 0.99:
        return None
    spec = (row.get("spec_B") or row.get("spec_T") or "").strip() or None
    measured = el["diameter"] is not None
    albedo = el["albedo"]
    if el["diameter"] is None:
        if el["H"] is None:
            return None
        guess = albedo if albedo else 0.14  # mean NEO albedo when unmeasured
        el["diameter"] = diameter_from_h(el["H"], guess)
    name = (row.get("full_name") or row.get("pdes") or "").strip()
    return {
        "id": str(row["pdes"]).strip(), "name": name, "epoch": el["epoch"], "a": el["a"], "e": el["e"],
        "i": el["i"], "om": el["om"], "w": el["w"], "ma": el["ma"], "H": el["H"],
        "diameter_km": el["diameter"], "diameter_measured": measured, "albedo": albedo,
        "spectral_class": spec, "taxonomy": "SMASSII" if row.get("spec_B") else ("Tholen" if row.get("spec_T") else None),
        "neo": row.get("neo") == "Y", "pha": row.get("pha") == "Y", "orbit_class": row.get("class"),
        "first_obs": row.get("first_obs"), "data_arc_days": el["data_arc"],
    }


def _query(params: dict) -> list[dict]:
    q = {"fields": ",".join(FIELDS), "full-prec": "true", **params}
    r = httpx.get(SBDB_QUERY, params=q, timeout=60)
    r.raise_for_status()
    body = r.json()
    rows = [dict(zip(body["fields"], d)) for d in body.get("data", [])]
    return [t for t in (normalize(x) for x in rows) if t]


_backoff_until: dict[str, float] = {}
BACKOFF_S = 600


def _cached(name: str, fetch) -> list[dict]:
    path = Path(settings.data_dir) / f"catalog-{name}.json"
    if path.exists() and time.time() - path.stat().st_mtime < CACHE_TTL_S:
        return json.loads(path.read_text())
    try:
        if time.time() < _backoff_until.get(name, 0):
            raise RuntimeError("backing off after a failed fetch")
        rows = fetch()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(rows))
        return rows
    except Exception as exc:
        if time.time() >= _backoff_until.get(name, 0):
            log.warning("SBDB %s unavailable (%s); retrying in %d s", name, exc, BACKOFF_S)
            _backoff_until[name] = time.time() + BACKOFF_S
        if path.exists():
            return json.loads(path.read_text())
        return [t for t in json.loads(FIXTURE.read_text()) if name != "new-neos" or t.get("neo")]


def characterized() -> list[dict]:
    """Asteroids with a measured spectral class."""
    cdata = json.dumps({"OR": ["spec_B|DF", "spec_T|DF"]})
    return _cached("characterized", lambda: _query({"sb-kind": "a", "sb-cdata": cdata}))


def new_neos(max_arc_days: int = 30, max_h: float = 24.0) -> list[dict]:
    """Recently discovered near-Earth asteroids large enough to matter (H <= max_h, roughly 30+ m)."""
    cdata = json.dumps({"AND": [f"data_arc|LE|{max_arc_days}", f"H|LE|{max_h}"]})
    return _cached("new-neos", lambda: _query({"sb-group": "neo", "sb-cdata": cdata}))


def all_targets() -> list[dict]:
    seen, out = set(), []
    for t in characterized() + new_neos():
        if t["id"] not in seen:
            seen.add(t["id"])
            out.append(t)
    return out


def find(query: str) -> dict | None:
    """Match an asteroid by number, designation or name, e.g. '101955', 'Bennu', '2024 YR4'."""
    q = query.strip().lower()
    for t in all_targets():
        names = {t["id"].lower(), t["name"].lower(), t["name"].lower().strip("()")}
        if q in names or any(q == part.strip("()") for part in t["name"].lower().split()):
            return t
    return None
