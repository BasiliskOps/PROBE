"""What an asteroid is probably made of, and what a probe measures when it gets there.

Composition is inferred from spectral class, falling back to albedo when no
class is measured, using meteorite analogs:
- carbonaceous (C, B, F, G and subclasses): hydrated CM/CI-like matrix. Water
  ranges follow Garenne et al. 2014, GCA, doi:10.1016/j.gca.2014.03.034
  (CM and CI matrix about 25 wt% "water", CR matrix about 11 wt%), scaled
  down for bulk rock.
- stony (S, Q, K, L, A): ordinary-chondrite-like, a few to ~20 wt% Fe-Ni metal.
- metallic (M, or X with albedo 0.1-0.3): iron-meteorite-like, metal-rich.
- enstatite (E, or X with albedo above 0.3), basaltic (V), primitive (P, D, T).
Metal is split into nickel, cobalt and platinum-group metals with
iron-meteorite ranges. Bulk densities are rounded class means in the spirit
of Carry 2012 (Planet. Space Sci. 73, 98), overridden by measured values.

Every number here is a prior with a range. Each asteroid gets one hidden
"true" composition drawn from those ranges, seeded by its designation, so
every probe that visits the same rock measures the same thing, with noise
that shrinks for closer and longer surveys.
"""
from __future__ import annotations

import hashlib
import math

import numpy as np

# (low, high) mass fractions; density g/cm^3
GROUPS = {
    "carbonaceous": {"label": "carbonaceous", "water": (0.04, 0.18), "carbon": (0.015, 0.045), "metal": (0.001, 0.02), "density": 1.4},
    "stony": {"label": "stony", "water": (0.0001, 0.003), "carbon": (0.0005, 0.003), "metal": (0.02, 0.20), "density": 2.7},
    "metallic": {"label": "metallic", "water": (0.0005, 0.01), "carbon": (0.0005, 0.005), "metal": (0.30, 0.90), "density": 3.6},
    "enstatite": {"label": "enstatite", "water": (0.0005, 0.005), "carbon": (0.001, 0.005), "metal": (0.10, 0.25), "density": 3.0},
    "basaltic": {"label": "basaltic", "water": (0.0002, 0.003), "carbon": (0.0002, 0.002), "metal": (0.001, 0.01), "density": 3.0},
    "primitive": {"label": "primitive", "water": (0.05, 0.30), "carbon": (0.03, 0.08), "metal": (0.001, 0.02), "density": 1.2},
}
METAL = {"nickel": (0.06, 0.12), "cobalt": (0.004, 0.007), "pgm": (5e-6, 5e-5)}  # fractions of the metal phase
TYPICAL_ALBEDO = {"carbonaceous": 0.06, "stony": 0.25, "metallic": 0.15, "enstatite": 0.45, "basaltic": 0.35,
                  "primitive": 0.05}

RESOURCES = ["water", "carbon", "iron", "nickel", "cobalt", "pgm"]
LABELS = {"water": "Water", "carbon": "Carbon and organics", "iron": "Iron", "nickel": "Nickel", "cobalt": "Cobalt",
          "pgm": "Platinum-group metals"}


def group_of(spectral_class: str | None, albedo: float | None) -> tuple[str, str]:
    """(group, basis) where basis says how the group was inferred."""
    c = (spectral_class or "").strip()
    head = c[:1].upper()
    if head in ("C", "B", "F", "G"):
        return "carbonaceous", f"spectral class {c}"
    if head in ("S", "Q", "K", "L", "A", "R", "O"):
        return "stony", f"spectral class {c}"
    if head == "M":
        return "metallic", f"spectral class {c}"
    if head == "E":
        return "enstatite", f"spectral class {c}"
    if head == "V":
        return "basaltic", f"spectral class {c}"
    if head in ("P", "D", "T"):
        return "primitive", f"spectral class {c}"
    if head == "X":
        if albedo is None:
            return "metallic", f"spectral class {c}, albedo unknown"
        if albedo < 0.1:
            return "primitive", f"spectral class {c} with albedo {albedo:.2f}"
        if albedo <= 0.3:
            return "metallic", f"spectral class {c} with albedo {albedo:.2f}"
        return "enstatite", f"spectral class {c} with albedo {albedo:.2f}"
    if albedo is not None:
        if albedo < 0.1:
            return "carbonaceous", f"albedo {albedo:.2f} only"
        if albedo <= 0.3:
            return "stony", f"albedo {albedo:.2f} only"
        return "enstatite", f"albedo {albedo:.2f} only"
    return "stony", "no spectral class or albedo; most common near-Earth type assumed"


def _rng(*parts: str) -> np.random.Generator:
    seed = int.from_bytes(hashlib.sha256("|".join(parts).encode()).digest()[:8], "big")
    return np.random.default_rng(seed)


def _logu(rng, lo: float, hi: float) -> float:
    return float(math.exp(rng.uniform(math.log(lo), math.log(hi))))


def _mid(lo: float, hi: float) -> float:
    return math.sqrt(lo * hi)


def mass_kg(target: dict, group: str, diameter_km: float | None = None) -> float:
    if target.get("mass_kg") and diameter_km is None:
        return float(target["mass_kg"])
    d = diameter_km or target["diameter_km"]
    rho = (target.get("density") or GROUPS[group]["density"]) * 1000.0
    return 4.0 / 3.0 * math.pi * (d * 500.0) ** 3 * rho


def _tonnes(fractions: dict, mass: float) -> dict:
    metal = fractions["metal"]
    return {
        "water": fractions["water"] * mass / 1000.0,
        "carbon": fractions["carbon"] * mass / 1000.0,
        "iron": metal * (1 - fractions["nickel"] - fractions["cobalt"]) * mass / 1000.0,
        "nickel": metal * fractions["nickel"] * mass / 1000.0,
        "cobalt": metal * fractions["cobalt"] * mass / 1000.0,
        "pgm": metal * fractions["pgm"] * mass / 1000.0,
    }


def prior(target: dict) -> dict:
    """Catalog-only estimate: what we expect before any probe arrives."""
    group, basis = group_of(target.get("spectral_class"), target.get("albedo"))
    g = GROUPS[group]
    f = {k: _mid(*g[k]) for k in ("water", "carbon", "metal")}
    f.update({k: _mid(*METAL[k]) for k in METAL})
    m = mass_kg(target, group)
    return {"group": group, "basis": basis, "mass_kg": m, "tonnes": _tonnes(f, m), "fractions": f,
            "spread": 3.0, "diameter_km": target["diameter_km"]}


def truth(target: dict) -> dict:
    """The asteroid's hidden composition, the same for every probe."""
    group, _ = group_of(target.get("spectral_class"), target.get("albedo"))
    rng = _rng("truth", target["id"])
    g = GROUPS[group]
    f = {k: _logu(rng, *g[k]) for k in ("water", "carbon", "metal")}
    f.update({k: _logu(rng, *METAL[k]) for k in METAL})
    d_sigma = 0.05 if target.get("diameter_measured") else 0.25
    d = target["diameter_km"] * math.exp(rng.normal(0.0, d_sigma))
    return {"group": group, "fractions": f, "diameter_km": d}


# Relative 1-sigma measurement noise by survey mode.
NOISE = {"rendezvous": {"fraction": 0.10, "diameter": 0.02}, "flyby": {"fraction": 0.35, "diameter": 0.08}}


def survey(target: dict, mode: str, probe_id: str) -> dict:
    """One probe's measurements of the asteroid."""
    t = truth(target)
    n = NOISE[mode]
    rng = _rng("survey", target["id"], probe_id)
    f = {k: v * math.exp(rng.normal(0.0, n["fraction"])) for k, v in t["fractions"].items()}
    d = t["diameter_km"] * math.exp(rng.normal(0.0, n["diameter"]))
    m = mass_kg({**target, "mass_kg": None}, t["group"], diameter_km=d)
    return {"mode": mode, "group": t["group"], "diameter_km": d, "mass_kg": m, "fractions": f,
            "tonnes": _tonnes(f, m), "sigma": n["fraction"]}


def combine(surveys: list[dict]) -> dict:
    """Inverse-variance mean (in log space) of every survey of one asteroid."""
    if not surveys:
        return {}
    w = np.array([1.0 / s["sigma"] ** 2 for s in surveys])
    out = {}
    for k in surveys[0]["tonnes"]:
        logs = np.array([math.log(max(s["tonnes"][k], 1e-30)) for s in surveys])
        out[k] = float(math.exp((w * logs).sum() / w.sum()))
    sigma = float(1.0 / math.sqrt(w.sum()))
    return {"tonnes": out, "relative_uncertainty": sigma, "surveys": len(surveys)}
