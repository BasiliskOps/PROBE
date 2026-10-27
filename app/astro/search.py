"""Launch window search: the next real launch window from a start date for a target.

For each candidate flyby sequence, the horizon is split into launch-date bins
and each bin is optimized with differential evolution over the full MGA-1DSM
design vector, then the best result of each bin is refined locally.

The cost is the wet mass the probe needs (rocket equation over every probe
burn, plus allowances and margin) divided by what the most capable cataloged
launcher can lift to the departure C3, with a penalty when the launch
asymptote declination is beyond what Cape Canaveral reaches due east. A cost
below 1 means the mission closes. The next window is the earliest bin whose
design closes and costs within a tolerance of the best design in the horizon.
"""
from __future__ import annotations

import math
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone

import numpy as np
from scipy.optimize import differential_evolution, minimize

from . import vehicles
from .constants import BODY, CAPTURE, DV_MARGIN, G0, INDEX, MOONS, MU_SUN, NAV_ALLOWANCE, PLANETS
from .ephemeris import EphemerisTable, load_table
from .mga import BIG, decode, evaluate

JD_UNIX = 2440587.5
DLA_LIMIT_DEG = 28.5  # declination reachable launching due east from Cape Canaveral

# Real sequence families: direct, Juno's dV-EGA (E-E-J), Clipper's MEGA (E-M-E-J),
# Galileo's VEEGA (E-V-E-E-J), and their analogues for the other targets.
SEQUENCES = {
    "mercury": [["earth", "venus", "mercury"], ["earth", "venus", "venus", "mercury"]],
    "venus": [["earth", "venus"]],
    "mars": [["earth", "mars"]],
    "jupiter": [["earth", "jupiter"], ["earth", "earth", "jupiter"], ["earth", "mars", "earth", "jupiter"],
                ["earth", "venus", "earth", "earth", "jupiter"]],
    "saturn": [["earth", "jupiter", "saturn"], ["earth", "earth", "saturn"],
               ["earth", "venus", "earth", "earth", "saturn"]],
    "uranus": [["earth", "jupiter", "uranus"], ["earth", "earth", "jupiter", "uranus"],
               ["earth", "saturn", "uranus"]],
    "neptune": [["earth", "jupiter", "neptune"], ["earth", "earth", "jupiter", "neptune"],
                ["earth", "saturn", "neptune"]],
}

RESONANT_LEG_DAYS = {"earth": (330.0, 1150.0), "venus": (200.0, 700.0), "mars": (600.0, 1400.0)}


def jd_from_dt(dt: datetime) -> float:
    return dt.timestamp() / 86400.0 + JD_UNIX


def dt_from_jd(jd: float) -> datetime:
    return datetime.fromtimestamp((jd - JD_UNIX) * 86400.0, tz=timezone.utc)


def iso(jd: float) -> str:
    return dt_from_jd(jd).strftime("%Y-%m-%d")


def hohmann_days(a1_au: float, a2_au: float) -> float:
    a = 0.5 * (a1_au + a2_au) * 1.495978707e8
    return math.pi * math.sqrt(a**3 / MU_SUN) / 86400.0


def leg_bounds(seq: list[str]) -> list[tuple[float, float]]:
    out = []
    for a, b in zip(seq, seq[1:]):
        if a == b:
            out.append(RESONANT_LEG_DAYS[a])
        else:
            h = hohmann_days(BODY[a]["a_au"], BODY[b]["a_au"])
            out.append((max(40.0, 0.35 * h), 2.2 * h))
    return out


def design_bounds(seq: list[str], t_lo: float, t_hi: float) -> list[tuple[float, float]]:
    vmax = math.sqrt(vehicles.max_c3())
    b = [(t_lo, t_hi), (0.0, 1.0), (0.0, 1.0), (0.5, vmax)]
    for i, tof in enumerate(leg_bounds(seq)):
        if i > 0:
            b += [(-math.pi, math.pi), (1.0, 30.0)]
        b += [(0.01, 0.99), tof]
    return b


@dataclass
class MissionSpec:
    target: str  # planet or moon
    arrival: str = "orbit"  # "orbit" or "flyby"
    via: list[str] = field(default_factory=list)  # bodies the owner asked to pass
    dry_mass_kg: float = 1800.0
    isp_s: float = 323.0  # bipropellant main engine
    capture_period_days: float | None = None  # overrides the default capture orbit
    small_body: dict | None = None  # JPL SBDB target when flying to an asteroid

    @property
    def planet(self) -> str:
        if self.small_body:
            from .smallbody import key

            return key(self.small_body)
        return MOONS[self.target]["parent"] if self.target in MOONS else self.target


def candidate_sequences(spec: MissionSpec) -> list[list[str]]:
    if spec.small_body:
        from .smallbody import register

        k = register(spec.small_body)
        return [["earth", k], ["earth", "earth", k], ["earth", "mars", k]]
    seqs = SEQUENCES[spec.planet]
    want = [b for b in spec.via if b not in (spec.planet, "earth")]
    if want:
        keep = [s for s in seqs if all(b in s[1:-1] for b in want)]
        if not keep:
            ordered = sorted(set(want), key=lambda b: BODY[b]["a_au"])
            keep = [["earth", *ordered, spec.planet]]
        seqs = keep
    return seqs


def capture_params(spec: MissionSpec) -> tuple[bool, float, float]:
    if spec.small_body and spec.arrival != "flyby":
        # Rendezvous: match the asteroid's orbit and settle into a slow survey orbit.
        r = BODY[spec.planet]["radius"]
        return True, 3.0 * r, (spec.capture_period_days or 2.0) * 86400.0
    if spec.arrival == "flyby" or spec.planet not in CAPTURE:
        return False, 1.0, 1.0
    cap = CAPTURE[spec.planet]
    period = spec.capture_period_days or cap["period_days"]
    return True, cap["rp"], period * 86400.0


def tour_dv(spec: MissionSpec) -> float:
    return MOONS[spec.target]["tour_dv"] if spec.target in MOONS and spec.arrival == "orbit" else 0.0


def total_probe_dv(spec: MissionSpec, maneuver_dv_kms: float) -> float:
    return (maneuver_dv_kms + tour_dv(spec) + NAV_ALLOWANCE) * (1.0 + DV_MARGIN)


def launch_capability(c3: float) -> float:
    """Payload (kg) to this C3 on the most capable cataloged vehicle; 0 when out of range."""
    return max(vehicles.capacity_kg(v, max(c3, 0.0)) for v in vehicles.VEHICLES)


def design_cost(c3: float, dla_deg: float, maneuver_dv_kms: float, spec: MissionSpec) -> float:
    cap = launch_capability(c3)
    if cap <= 0.0:
        return 10.0 + c3 / 10.0
    dv = total_probe_dv(spec, maneuver_dv_kms)
    if dv > 15.0:  # far beyond any chemical probe
        return 10.0 + dv
    wet = spec.dry_mass_kg * math.exp(dv / (G0 * spec.isp_s))
    cost = wet / cap
    excess = abs(dla_deg) - DLA_LIMIT_DEG
    if excess > 0:
        cost *= 1.0 + (excess / 10.0) ** 2
    return cost


def budget(spec: MissionSpec, detail: dict) -> dict:
    maneuvers = detail["dsm_dv_kms"] + detail["arrival_dv_kms"]
    dv = total_probe_dv(spec, maneuvers)
    wet = spec.dry_mass_kg * math.exp(dv / (G0 * spec.isp_s))
    return {
        "dsm_dv_kms": detail["dsm_dv_kms"],
        "arrival_dv_kms": detail["arrival_dv_kms"],
        "tour_dv_kms": tour_dv(spec),
        "nav_dv_kms": NAV_ALLOWANCE,
        "margin_fraction": DV_MARGIN,
        "total_dv_kms": dv,
        "dry_mass_kg": spec.dry_mass_kg,
        "isp_s": spec.isp_s,
        "propellant_kg": wet - spec.dry_mass_kg,
        "wet_mass_kg": wet,
    }


class Objective:
    """Picklable objective for one sequence."""

    def __init__(self, seq, table: EphemerisTable, spec: MissionSpec):
        self.seq_idx = np.array([table.names.index(s) for s in seq], dtype=np.int64)
        self.table = table
        self.spec = spec
        self.capture, self.cap_rp, self.cap_period = capture_params(spec)
        self.mus = np.array([BODY[p]["mu"] for p in table.names])
        self.rpmins = np.array([BODY[p]["rp_min"] for p in table.names])

    def __call__(self, x):
        try:
            ok, c3, dla, dv, _ = evaluate(np.asarray(x, dtype=float), self.seq_idx, self.mus, self.rpmins,
                                          self.table.pos, self.table.vel, self.table.jd0, self.table.step,
                                          MU_SUN, self.capture, self.cap_rp, self.cap_period)
        except Exception:
            return BIG
        if not ok:
            return BIG
        return design_cost(c3, dla, dv, self.spec)


def _optimize_bin(args):
    seq, t_lo, t_hi, table, spec, seed, maxiter = args
    f = Objective(seq, table, spec)
    bounds = design_bounds(seq, t_lo, t_hi)
    res = differential_evolution(f, bounds, popsize=12, maxiter=maxiter, tol=1e-9, seed=seed, polish=False,
                                 updating="deferred", init="sobol", mutation=(0.5, 1.0), recombination=0.9)
    loc = minimize(f, res.x, method="Powell", bounds=bounds, options={"maxfev": 4000, "xtol": 1e-6})
    x, cost = (loc.x, loc.fun) if loc.fun < res.fun else (res.x, res.fun)
    return seq, [float(v) for v in x], float(cost)


def evaluate_design(seq, x, table, spec) -> dict:
    capture, cap_rp, cap_period = capture_params(spec)
    detail = decode(x, seq, table, MU_SUN, capture, cap_rp, cap_period)
    bud = budget(spec, detail)
    lv = vehicles.select_vehicle(detail["c3_km2s2"], bud["wet_mass_kg"])
    return {"sequence": seq, "x": list(x), "cost": float(Objective(seq, table, spec)(np.asarray(x))),
            "detail": detail, "budget": bud, "vehicle": lv}


def find_windows(spec: MissionSpec, start: datetime, horizon_days: float = 1100.0, bin_days: float = 180.0,
                 source: str = "horizons", cache_dir=None, workers: int = 2, maxiter: int = 250,
                 tolerance: float = 0.15, priority: str = "soonest") -> dict:
    """Search the horizon and return the next launch window plus the best alternative per sequence."""
    seqs = candidate_sequences(spec)
    t0 = jd_from_dt(start)
    longest = max(sum(b for _, b in leg_bounds(s)) for s in seqs)
    table = load_table(t0 - 2, t0 + horizon_days + longest + 2, source=source, cache_dir=cache_dir)
    if spec.small_body:
        from .smallbody import extend

        table = extend(table, spec.small_body)

    jobs = []
    n_bins = max(1, int(math.ceil(horizon_days / bin_days)))
    for s_i, seq in enumerate(seqs):
        for b in range(n_bins):
            lo = t0 + b * bin_days
            hi = min(t0 + horizon_days, lo + bin_days)
            jobs.append((seq, lo, hi, table, spec, 1000 * s_i + b, maxiter))

    if workers > 1:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(_optimize_bin, jobs))
    else:
        results = [_optimize_bin(j) for j in jobs]

    designs = [evaluate_design(seq, x, table, spec) for seq, x, cost in results if cost < 1.0]
    feasible = [d for d in designs if d["vehicle"] is not None]
    if not feasible:
        return {"status": "infeasible", "ephemeris_source": table.source, "searched": len(jobs), "designs": []}
    best = min(d["cost"] for d in feasible)
    if priority == "fastest":
        chosen = min(feasible, key=lambda d: d["detail"]["arrival_jd"] - d["detail"]["launch_jd"])
    elif priority == "heaviest":
        chosen = min(feasible, key=lambda d: d["cost"])
    else:  # soonest: the next window that is nearly as good as the best one
        ok = sorted((d for d in feasible if d["cost"] <= best * (1.0 + tolerance)), key=lambda d: d["x"][0])
        chosen = ok[0]
    alts = {}
    for d in sorted(feasible, key=lambda d: d["cost"]):
        alts.setdefault("-".join(d["sequence"]), d)
    return {"status": "ok", "ephemeris_source": table.source, "searched": len(jobs), "design": chosen,
            "alternatives": [d for d in alts.values() if d is not chosen], "best_cost": best, "table": table}
