"""Asteroids as trajectory targets.

Orbits come from JPL Small-Body Database osculating elements (heliocentric
ecliptic J2000, AU and degrees). They are propagated as two-body Kepler
orbits and appended to an ephemeris table as extra rows, so the same MGA
engine that flies to planets flies to asteroids.
"""
from __future__ import annotations

import math

import numpy as np

from .constants import AU_KM, BODY, MU_SUN, OBLIQUITY_DEG
from .ephemeris import EphemerisTable
from .mga import kepler

G_KM = 6.674e-20  # km^3 / (kg s^2)
_EPS = math.radians(OBLIQUITY_DEG)


def key(target: dict) -> str:
    return f"sb:{target['id']}"


def _ecl_to_eq(v: np.ndarray) -> np.ndarray:
    x, y, z = v
    return np.array([x, y * math.cos(_EPS) - z * math.sin(_EPS), y * math.sin(_EPS) + z * math.cos(_EPS)])


def state_at_epoch(el: dict) -> tuple[np.ndarray, np.ndarray, float]:
    """ICRF equatorial position (km) and velocity (km/s) at the elements' epoch."""
    a = el["a"] * AU_KM
    e, i = el["e"], math.radians(el["i"])
    om, w, M = math.radians(el["om"]), math.radians(el["w"]), math.radians(el["ma"])
    E = M if e < 0.8 else math.pi
    for _ in range(50):
        d = (E - e * math.sin(E) - M) / (1 - e * math.cos(E))
        E -= d
        if abs(d) < 1e-12:
            break
    nu = 2 * math.atan2(math.sqrt(1 + e) * math.sin(E / 2), math.sqrt(1 - e) * math.cos(E / 2))
    p = a * (1 - e * e)
    r = p / (1 + e * math.cos(nu))
    r_pf = np.array([r * math.cos(nu), r * math.sin(nu), 0.0])
    v_pf = math.sqrt(MU_SUN / p) * np.array([-math.sin(nu), e + math.cos(nu), 0.0])
    co, so, ci, si, cw, sw = math.cos(om), math.sin(om), math.cos(i), math.sin(i), math.cos(w), math.sin(w)
    R = np.array([
        [co * cw - so * sw * ci, -co * sw - so * cw * ci, so * si],
        [so * cw + co * sw * ci, -so * sw + co * cw * ci, -co * si],
        [sw * si, cw * si, ci],
    ])
    return _ecl_to_eq(R @ r_pf), _ecl_to_eq(R @ v_pf), float(el["epoch"])


def state(el: dict, jd: float) -> tuple[np.ndarray, np.ndarray]:
    r0, v0, epoch = state_at_epoch(el)
    return kepler(r0, v0, (jd - epoch) * 86400.0, MU_SUN)


def register(target: dict) -> str:
    """Add the asteroid to the body registry used by the trajectory engine."""
    k = key(target)
    radius = max(target["diameter_km"] / 2.0, 0.005)
    mass = target.get("mass_kg") or 4.0 / 3.0 * math.pi * (radius * 1000) ** 3 * 2000.0
    BODY[k] = {"mu": max(G_KM * mass, 1e-12), "radius": radius, "rp_min": radius + 1.0, "a_au": target["a"],
               "label": target["name"], "small_body": True}
    return k


def extend(table: EphemerisTable, target: dict) -> EphemerisTable:
    """A copy of the table with the asteroid appended as an extra body row."""
    k = register(target)
    if k in table.names:
        return table
    n = table.pos.shape[1]
    r0, v0, epoch = state_at_epoch(target)
    pos = np.empty((1, n, 3))
    vel = np.empty((1, n, 3))
    r, v = kepler(r0, v0, (table.jd0 - epoch) * 86400.0, MU_SUN)
    step = table.step * 86400.0
    for j in range(n):
        pos[0, j], vel[0, j] = r, v
        r, v = kepler(r, v, step, MU_SUN)
    return EphemerisTable(table.source, table.jd0, table.step, np.concatenate([table.pos, pos]),
                          np.concatenate([table.vel, vel]), names=[*table.names, k])
