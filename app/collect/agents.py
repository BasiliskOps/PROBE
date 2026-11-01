"""Collection agents. Each one owns a single published source and returns records
with provenance. They run concurrently under app.collect.run.

Agents collect only. Nothing here generates, estimates or rewrites data; a
failed source returns an empty result and a recorded error so the run still
publishes what the other sources returned.

Sources:
- JPL Small-Body Database query API: orbits, spectral class, albedo, diameter.
  https://ssd-api.jpl.nasa.gov/doc/sbdb_query.html
- JPL Small-Body Database lookup API: measured physical parameters with their
  literature references. https://ssd-api.jpl.nasa.gov/doc/sbdb.html
- JPL DE421 planetary ephemeris (offline kernel): planet states, reduced to
  osculating elements for display.
- NASA Image and Video Library API: published mission imagery of bodies
  visited by spacecraft. https://images.nasa.gov/docs/images.nasa.gov_api_docs.pdf
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import time
from datetime import datetime, timezone

import httpx
import numpy as np

from app.astro.constants import AU_KM, BODY, EMRAT, MU_SUN, OBLIQUITY_DEG, PLANETS
from app.prospect import catalog

log = logging.getLogger(__name__)

SBDB_LOOKUP = "https://ssd-api.jpl.nasa.gov/sbdb.api"
NASA_IMAGES = "https://images-api.nasa.gov/search"
UA = {"User-Agent": "Lastelle-Probe/1.0 (+https://lastelle.ai)"}

# Bodies imaged at close range by spacecraft, with the mission that did it.
# Published mission history; used only to decide which bodies to request imagery for.
VISITED = {
    "1": "Dawn", "4": "Dawn", "21": "Rosetta", "243": "Galileo", "253": "NEAR Shoemaker",
    "433": "NEAR Shoemaker", "951": "Galileo", "2867": "Rosetta", "4179": "Chang'e 2",
    "5535": "Stardust", "9969": "Deep Space 1", "25143": "Hayabusa", "65803": "DART",
    "101955": "OSIRIS-REx", "152830": "Lucy", "162173": "Hayabusa2", "52246": "Lucy",
}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _result(name: str, source: str, records, error: str | None = None, started: float | None = None) -> dict:
    return {"agent": name, "source": source, "retrieved_at": _now(), "records": records,
            "count": len(records) if hasattr(records, "__len__") else None, "error": error,
            "seconds": round(time.time() - started, 2) if started else None}


async def catalog_agent(max_neo_h: float = 20.0) -> dict:
    """Asteroids with a measured spectral class, plus near-Earth asteroids roughly 300 m and larger."""
    started = time.time()

    def fetch():
        spec = json.dumps({"OR": ["spec_B|DF", "spec_T|DF"]})
        neo = json.dumps({"AND": [f"H|LE|{max_neo_h}"]})
        a = catalog._query({"sb-kind": "a", "sb-cdata": spec})
        b = catalog._query({"sb-group": "neo", "sb-cdata": neo})
        seen, out = set(), []
        for t in a + b:
            if t["id"] not in seen:
                seen.add(t["id"])
                out.append(t)
        return out

    try:
        rows = await asyncio.to_thread(fetch)
        return _result("catalog", catalog.SBDB_QUERY, rows, started=started)
    except Exception as exc:  # recorded, never fatal
        log.warning("catalog agent failed: %s", exc)
        return _result("catalog", catalog.SBDB_QUERY, [], str(exc), started)


def parse_phys(body: dict) -> dict:
    """Measured physical parameters from an SBDB lookup, each with its reference."""
    out = {}
    for p in body.get("phys_par", []) or []:
        name = p.get("name")
        if name in ("GM", "density", "diameter", "albedo", "rot_per", "spec_B", "spec_T", "H"):
            out[name] = {"value": p.get("value"), "units": p.get("units"), "sigma": p.get("sigma"),
                         "ref": p.get("ref"), "notes": p.get("notes")}
    return out


async def physical_agent(ids: list[str], concurrency: int = 4) -> dict:
    """Measured physical parameters (mass, density, rotation) for the leading candidates."""
    started = time.time()
    sem = asyncio.Semaphore(concurrency)
    out: dict[str, dict] = {}
    errors = 0

    async with httpx.AsyncClient(timeout=30, headers=UA) as client:
        async def one(sid: str):
            nonlocal errors
            async with sem:
                try:
                    r = await client.get(SBDB_LOOKUP, params={"sstr": sid, "phys-par": "1"})
                    r.raise_for_status()
                    phys = parse_phys(r.json())
                    if phys:
                        out[sid] = phys
                except Exception:
                    errors += 1
                await asyncio.sleep(0.25)  # stay polite to JPL

        await asyncio.gather(*(one(i) for i in ids))
    err = f"{errors} lookups failed" if errors else None
    return _result("physical", SBDB_LOOKUP, out, err, started)


def _elements(r: np.ndarray, v: np.ndarray) -> dict:
    """Heliocentric ecliptic osculating elements from a state vector (km, km/s)."""
    h = np.cross(r, v)
    rn, vn = np.linalg.norm(r), np.linalg.norm(v)
    a = 1.0 / (2.0 / rn - vn ** 2 / MU_SUN)
    ev = np.cross(v, h) / MU_SUN - r / rn
    e = float(np.linalg.norm(ev))
    i = math.degrees(math.acos(h[2] / np.linalg.norm(h)))
    n = np.array([-h[1], h[0], 0.0])
    nn = np.linalg.norm(n)
    om = math.degrees(math.atan2(n[1], n[0])) % 360
    w = math.degrees(math.acos(max(-1.0, min(1.0, float(n @ ev) / (nn * e)))))
    if ev[2] < 0:
        w = 360 - w
    nu = math.acos(max(-1.0, min(1.0, float(ev @ r) / (e * rn))))
    if float(r @ v) < 0:
        nu = 2 * math.pi - nu
    E = 2 * math.atan2(math.sqrt(1 - e) * math.sin(nu / 2), math.sqrt(1 + e) * math.cos(nu / 2))
    M = math.degrees(E - e * math.sin(E)) % 360
    return {"a": a / AU_KM, "e": e, "i": i, "om": om, "w": w, "ma": M}


async def ephemeris_agent(jd: float) -> dict:
    """Planet osculating elements at jd from the JPL DE421 kernel."""
    started = time.time()

    def compute():
        import de421
        from jplephem import Ephemeris

        eph = Ephemeris(de421)
        eps = math.radians(OBLIQUITY_DEG)
        rot = np.array([[1, 0, 0], [0, math.cos(eps), math.sin(eps)], [0, -math.sin(eps), math.cos(eps)]])
        sun_p, sun_v = eph.position_and_velocity("sun", jd)
        rows = []
        for name in PLANETS:
            if name == "earth":
                emb_p, emb_v = eph.position_and_velocity("earthmoon", jd)
                moon_p, moon_v = eph.position_and_velocity("moon", jd)
                p, v = emb_p - moon_p / (1.0 + EMRAT), emb_v - moon_v / (1.0 + EMRAT)
            else:
                p, v = eph.position_and_velocity(name, jd)
            r = rot @ (np.ravel(p) - np.ravel(sun_p))
            vel = rot @ (np.ravel(v) - np.ravel(sun_v)) / 86400.0  # km/day -> km/s
            rows.append({"id": name, "name": name.title(), "epoch": jd, "radius_km": BODY[name]["radius"],
                         **_elements(r, vel)})
        return rows

    try:
        return _result("ephemeris", "JPL DE421", await asyncio.to_thread(compute), started=started)
    except Exception as exc:
        log.warning("ephemeris agent failed: %s", exc)
        return _result("ephemeris", "JPL DE421", [], str(exc), started)


NOT_IMAGERY = ("logo", "patch", "insignia", "poster", "artist", "illustration", "concept")


def _match(item: dict, names: list[str]) -> bool:
    d = (item.get("data") or [{}])[0]
    title = (d.get("title") or "").lower()
    if any(w in title for w in NOT_IMAGERY):
        return False
    text = f"{title} {' '.join(d.get('keywords') or [])}".lower()
    return any(n.lower() in text for n in names)


async def imagery_agent(bodies: list[dict], per_body: int = 6) -> dict:
    """Published mission imagery for bodies visited by spacecraft."""
    started = time.time()
    out: dict[str, list] = {}
    errors = 0
    async with httpx.AsyncClient(timeout=30, headers=UA) as client:
        for b in bodies:
            mission = VISITED.get(b["id"])
            if not mission:
                continue
            short = b["name"].replace(b["id"], "").split("(")[0].strip() or b["name"]
            try:
                r = await client.get(NASA_IMAGES, params={"q": f"{short} {mission}", "media_type": "image"})
                r.raise_for_status()
                items = [it for it in r.json().get("collection", {}).get("items", []) if _match(it, [short])]
                imgs = []
                for it in items[:per_body]:
                    d = it["data"][0]
                    thumb = next((l["href"] for l in it.get("links", []) if l.get("rel") == "preview"), None)
                    if thumb and thumb.startswith("https://images-assets.nasa.gov/"):
                        imgs.append({"title": d.get("title"), "nasa_id": d.get("nasa_id"),
                                     "date": (d.get("date_created") or "")[:10], "center": d.get("center"),
                                     "thumb": thumb, "page": f"https://images.nasa.gov/details/{d.get('nasa_id')}"})
                if imgs:
                    out[b["id"]] = {"mission": mission, "images": imgs}
            except Exception:
                errors += 1
            await asyncio.sleep(0.25)
    return _result("imagery", NASA_IMAGES, out, f"{errors} queries failed" if errors else None, started)
