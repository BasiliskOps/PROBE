"""Planet state tables from JPL ephemerides.

Every source produces the same table: heliocentric ICRF positions (km) and
velocities (km/s) for all eight planets on a fixed daily grid, which the
compiled trajectory code interpolates with cubic Hermite splines.

Sources:
- "horizons": JPL Horizons API, live (production default).
- "de421": JPL DE421 planetary ephemeris shipped as a pip package (offline).
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .constants import EMRAT, HORIZONS_ID, PLANETS

log = logging.getLogger(__name__)

HORIZONS_URL = "https://ssd.jpl.nasa.gov/api/horizons.api"
DE421_LAST_JD = 2469807.5  # 2050-01-01; DE421 coverage ends shortly after


@dataclass
class EphemerisTable:
    source: str
    jd0: float
    step: float  # days
    pos: np.ndarray  # (n_planets, n_steps, 3) km
    vel: np.ndarray  # (n_planets, n_steps, 3) km/s

    @property
    def jd_end(self) -> float:
        return self.jd0 + self.step * (self.pos.shape[1] - 1)

    def state(self, body: str, jd: float) -> tuple[np.ndarray, np.ndarray]:
        from .mga import hermite

        return hermite(self.pos, self.vel, PLANETS.index(body), self.jd0, self.step, jd)


def _de421_table(jd_start: float, jd_end: float, step: float) -> EphemerisTable:
    import de421
    from jplephem import Ephemeris

    eph = Ephemeris(de421)
    jd = np.arange(jd_start, jd_end + step, step)
    sun_p, sun_v = eph.position_and_velocity("sun", jd)
    pos = np.empty((len(PLANETS), len(jd), 3))
    vel = np.empty_like(pos)
    for i, name in enumerate(PLANETS):
        if name == "earth":
            emb_p, emb_v = eph.position_and_velocity("earthmoon", jd)
            moon_p, moon_v = eph.position_and_velocity("moon", jd)
            p = emb_p - moon_p / (1.0 + EMRAT)
            v = emb_v - moon_v / (1.0 + EMRAT)
        else:
            p, v = eph.position_and_velocity(name, jd)
        pos[i] = (p - sun_p).T
        vel[i] = ((v - sun_v) / 86400.0).T  # km/day -> km/s
    return EphemerisTable("JPL DE421", jd_start, step, pos, vel)


def parse_horizons_vectors(result_text: str) -> np.ndarray:
    """Rows of [jd, x, y, z, vx, vy, vz] from a Horizons CSV vector table."""
    start = result_text.index("$$SOE") + len("$$SOE")
    end = result_text.index("$$EOE")
    rows = []
    for line in result_text[start:end].strip().splitlines():
        parts = [p.strip() for p in line.split(",") if p.strip()]
        # JDTDB, calendar date, X, Y, Z, VX, VY, VZ
        rows.append([float(parts[0])] + [float(x) for x in parts[2:8]])
    return np.array(rows)


def _horizons_table(jd_start: float, jd_end: float, step: float, timeout: float = 30.0) -> EphemerisTable:
    import httpx

    n = int(round((jd_end - jd_start) / step)) + 1
    pos = np.empty((len(PLANETS), n, 3))
    vel = np.empty_like(pos)
    with httpx.Client(timeout=timeout) as client:
        for i, name in enumerate(PLANETS):
            params = {
                "format": "json",
                "COMMAND": f"'{HORIZONS_ID[name]}'",
                "OBJ_DATA": "NO",
                "MAKE_EPHEM": "YES",
                "EPHEM_TYPE": "VECTORS",
                "CENTER": "'500@10'",
                "REF_PLANE": "FRAME",
                "REF_SYSTEM": "ICRF",
                "VEC_TABLE": "2",
                "OUT_UNITS": "KM-S",
                "CSV_FORMAT": "YES",
                "VEC_LABELS": "NO",
                "TIME_TYPE": "TDB",
                "START_TIME": f"'JD{jd_start}'",
                "STOP_TIME": f"'JD{jd_start + step * (n - 1)}'",
                "STEP_SIZE": f"'{int(step)} d'",
            }
            r = client.get(HORIZONS_URL, params=params)
            r.raise_for_status()
            rows = parse_horizons_vectors(r.json()["result"])
            if len(rows) != n:
                raise ValueError(f"Horizons returned {len(rows)} rows for {name}, expected {n}")
            pos[i] = rows[:, 1:4]
            vel[i] = rows[:, 4:7]
    return EphemerisTable("JPL Horizons", jd_start, step, pos, vel)


def load_table(jd_start: float, jd_end: float, source: str = "horizons", cache_dir: Path | None = None,
               step: float = 1.0) -> EphemerisTable:
    """Daily table covering [jd_start, jd_end]. Horizons falls back to DE421 if unreachable."""
    jd_start = float(np.floor(jd_start)) - 0.5
    jd_end = float(np.ceil(jd_end)) + 0.5
    key = hashlib.sha1(f"{source}:{jd_start}:{jd_end}:{step}".encode()).hexdigest()[:16]
    path = cache_dir / f"ephem-{key}.npz" if cache_dir else None
    if path and path.exists():
        z = np.load(path, allow_pickle=False)
        return EphemerisTable(str(z["source"]), float(z["jd0"]), float(z["step"]), z["pos"], z["vel"])

    table = None
    if source == "horizons":
        try:
            table = _horizons_table(jd_start, jd_end, step)
        except Exception as exc:  # network, quota or format failure
            log.warning("Horizons unavailable (%s); using DE421", exc)
    if table is None:
        if jd_end > DE421_LAST_JD:
            raise ValueError("Mission window extends past DE421 coverage and Horizons is unreachable")
        table = _de421_table(jd_start, jd_end, step)

    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez(path, source=table.source, jd0=table.jd0, step=table.step, pos=table.pos, vel=table.vel)
    return table
