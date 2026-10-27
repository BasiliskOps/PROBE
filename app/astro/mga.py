"""Multiple gravity assist trajectories with one deep-space maneuver per leg (MGA-1DSM).

This is the standard formulation used for interplanetary design (Vasile and
De Pascale 2006; Izzo, pykep). Design vector, all times in days:

    x = [t0, u, v, vinf,  eta_1, T_1,  beta_2, rp_2, eta_2, T_2,  ...]

- t0: launch epoch (Julian date, TDB)
- u, v in [0, 1]: direction of the departure hyperbolic excess velocity in
  the ICRF equatorial frame, so its latitude is the launch asymptote
  declination (DLA)
- vinf: departure hyperbolic excess speed (km/s); C3 = vinf^2
- eta_i in (0, 1): fraction of leg i flown before its deep-space maneuver
- T_i: leg flight time
- beta_i, rp_i: plane angle and periapsis radius (in units of the safe minimum)
  of the unpowered flyby that starts leg i

Each leg coasts on a Kepler orbit for eta*T, burns, then follows a Lambert arc
(Izzo 2015, via lamberthub) to the next planet. Flybys are unpowered patched
conics. All compiled with numba.
"""
from __future__ import annotations

import math

import numpy as np
from lamberthub import izzo2015
from numba import njit

BIG = 1.0e6


@njit(cache=True)
def hermite(pos, vel, b, jd0, step, jd):
    x = (jd - jd0) / step
    i = int(math.floor(x))
    n = pos.shape[1]
    r = np.full(3, np.nan)
    v = np.full(3, np.nan)
    if i < 0 or i + 1 >= n:
        return r, v
    s = x - i
    h = step * 86400.0
    s2 = s * s
    s3 = s2 * s
    h00 = 2 * s3 - 3 * s2 + 1
    h10 = s3 - 2 * s2 + s
    h01 = -2 * s3 + 3 * s2
    h11 = s3 - s2
    d00 = 6 * s2 - 6 * s
    d10 = 3 * s2 - 4 * s + 1
    d01 = -6 * s2 + 6 * s
    d11 = 3 * s2 - 2 * s
    for k in range(3):
        p0 = pos[b, i, k]
        p1 = pos[b, i + 1, k]
        m0 = vel[b, i, k] * h
        m1 = vel[b, i + 1, k] * h
        r[k] = h00 * p0 + h10 * m0 + h01 * p1 + h11 * m1
        v[k] = (d00 * p0 + d10 * m0 + d01 * p1 + d11 * m1) / h
    return r, v


@njit(cache=True)
def _norm(a):
    return math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2])


@njit(cache=True)
def _cross(a, b):
    out = np.empty(3)
    out[0] = a[1] * b[2] - a[2] * b[1]
    out[1] = a[2] * b[0] - a[0] * b[2]
    out[2] = a[0] * b[1] - a[1] * b[0]
    return out


@njit(cache=True)
def _stumpff(z):
    if z > 1e-8:
        s = math.sqrt(z)
        return (1 - math.cos(s)) / z, (s - math.sin(s)) / (s * s * s)
    if z < -1e-8:
        s = math.sqrt(-z)
        return (math.cosh(s) - 1) / (-z), (math.sinh(s) - s) / (s * s * s)
    return 0.5 - z / 24.0, 1.0 / 6.0 - z / 120.0


@njit(cache=True)
def kepler(r0, v0, dt, mu):
    """Two-body state after dt seconds (universal variables, Curtis alg. 3.3/3.4)."""
    r0n = _norm(r0)
    vr0 = (r0[0] * v0[0] + r0[1] * v0[1] + r0[2] * v0[2]) / r0n
    v2 = v0[0] * v0[0] + v0[1] * v0[1] + v0[2] * v0[2]
    alpha = 2.0 / r0n - v2 / mu
    sqmu = math.sqrt(mu)
    chi = sqmu * abs(alpha) * dt
    if abs(alpha) < 1e-12:
        chi = sqmu * dt / r0n
    for _ in range(100):
        z = alpha * chi * chi
        c, s = _stumpff(z)
        f = (r0n * vr0 / sqmu) * chi * chi * c + (1 - alpha * r0n) * chi ** 3 * s + r0n * chi - sqmu * dt
        fp = (r0n * vr0 / sqmu) * chi * (1 - alpha * chi * chi * s) + (1 - alpha * r0n) * chi * chi * c + r0n
        d = f / fp
        chi -= d
        if abs(d) < 1e-8:
            break
    z = alpha * chi * chi
    c, s = _stumpff(z)
    f = 1 - chi * chi / r0n * c
    g = dt - chi ** 3 / sqmu * s
    r = f * r0 + g * v0
    rn = _norm(r)
    fdot = sqmu / (rn * r0n) * (alpha * chi ** 3 * s - chi)
    gdot = 1 - chi * chi / rn * c
    v = fdot * r0 + gdot * v0
    return r, v


@njit(cache=True)
def flyby(vin_rel, vplanet, rp, beta, mu):
    """Outgoing planet-relative velocity of an unpowered hyperbolic flyby."""
    vmag = _norm(vin_rel)
    e = 1.0 + rp * vmag * vmag / mu
    delta = 2.0 * math.asin(1.0 / e)
    b1 = vin_rel / vmag
    b2 = _cross(b1, vplanet)
    b2 = b2 / _norm(b2)
    b3 = _cross(b1, b2)
    return vmag * (math.cos(delta) * b1 + math.sin(delta) * math.cos(beta) * b2
                   + math.sin(delta) * math.sin(beta) * b3)


@njit(cache=True)
def capture_dv(vinf, mu, rp, period_s):
    a = (mu * (period_s / (2.0 * math.pi)) ** 2) ** (1.0 / 3.0)
    if a <= rp:
        a = rp
    return math.sqrt(vinf * vinf + 2.0 * mu / rp) - math.sqrt(mu * (2.0 / rp - 1.0 / a))


@njit(cache=True)
def departure_vector(u, v, vinf):
    theta = 2.0 * math.pi * u
    phi = math.acos(2.0 * v - 1.0) - math.pi / 2.0
    out = np.empty(3)
    out[0] = vinf * math.cos(phi) * math.cos(theta)
    out[1] = vinf * math.cos(phi) * math.sin(theta)
    out[2] = vinf * math.sin(phi)
    return out, math.degrees(phi)


@njit(cache=True)
def evaluate(x, seq, mus, rpmins, pos, vel, jd0, step, mu_sun, capture, cap_rp, cap_period_s):
    """Returns (ok, c3, dla_deg, probe_dv_kms, vinf_arr). ok = 0.0 when the trajectory is invalid."""
    n = seq.shape[0] - 1
    t = x[0]
    r, vp = hermite(pos, vel, seq[0], jd0, step, t)
    if math.isnan(r[0]):
        return 0.0, 0.0, 0.0, 0.0, 0.0
    vinf_vec, dla = departure_vector(x[1], x[2], x[3])
    v = vp + vinf_vec
    total = 0.0
    vin_rel = np.zeros(3)
    k = 4
    for i in range(n):
        if i > 0:
            beta = x[k]
            rp = x[k + 1] * rpmins[seq[i]]
            k += 2
            v = vp + flyby(vin_rel, vp, rp, beta, mus[seq[i]])
        eta = x[k]
        T = x[k + 1]
        k += 2
        r_dsm, v_dsm = kepler(r, v, eta * T * 86400.0, mu_sun)
        t2 = t + T
        r2, vp2 = hermite(pos, vel, seq[i + 1], jd0, step, t2)
        if math.isnan(r2[0]) or math.isnan(r_dsm[0]):
            return 0.0, 0.0, 0.0, 0.0, 0.0
        v1, v2 = izzo2015(mu_sun, r_dsm, r2, (1.0 - eta) * T * 86400.0, 0, True, True, 35, 1e-5, 1e-7)
        total += _norm(v1 - v_dsm)
        vin_rel = v2 - vp2
        r = r2
        vp = vp2
        t = t2
    vinf_arr = _norm(vin_rel)
    if capture:
        total += capture_dv(vinf_arr, mus[seq[n]], cap_rp, cap_period_s)
    if math.isnan(total):
        return 0.0, 0.0, 0.0, 0.0, 0.0
    return 1.0, x[3] * x[3], dla, total, vinf_arr


def decode(x, seq_names, table, mu_sun, capture, cap_rp, cap_period_s):
    """Full mission geometry for a design vector: arcs, maneuvers and flybys."""
    from .constants import BODY, PLANETS

    x = np.asarray(x, dtype=float)
    seq = [PLANETS.index(s) for s in seq_names]
    t = float(x[0])
    r, vp = hermite(table.pos, table.vel, seq[0], table.jd0, table.step, t)
    vinf_vec, dla = departure_vector(x[1], x[2], x[3])
    v = vp + vinf_vec
    arcs, dsms, flybys = [], [], []
    vin_rel = None
    k = 4
    for i in range(len(seq) - 1):
        if i > 0:
            body = seq_names[i]
            beta, rp = float(x[k]), float(x[k + 1]) * BODY[body]["rp_min"]
            k += 2
            v = vp + flyby(vin_rel, vp, rp, beta, BODY[body]["mu"])
            flybys.append({"body": body, "jd": t, "vinf_kms": float(np.linalg.norm(vin_rel)),
                           "periapsis_km": rp, "altitude_km": rp - BODY[body]["radius"]})
        eta, T = float(x[k]), float(x[k + 1])
        k += 2
        t_dsm = t + eta * T
        arcs.append({"jd_start": t, "jd_end": t_dsm, "r0_km": r.tolist(), "v0_kms": v.tolist(),
                     "leg": i, "from": seq_names[i], "to": seq_names[i + 1]})
        r_dsm, v_dsm = kepler(r, v, eta * T * 86400.0, mu_sun)
        t2 = t + T
        r2, vp2 = hermite(table.pos, table.vel, seq[i + 1], table.jd0, table.step, t2)
        v1, v2 = izzo2015(mu_sun, r_dsm, r2, (1.0 - eta) * T * 86400.0, 0, True, True, 35, 1e-5, 1e-7)
        dsms.append({"jd": t_dsm, "leg": i, "dv_kms": float(np.linalg.norm(v1 - v_dsm))})
        arcs.append({"jd_start": t_dsm, "jd_end": t2, "r0_km": r_dsm.tolist(), "v0_kms": v1.tolist(),
                     "leg": i, "from": seq_names[i], "to": seq_names[i + 1]})
        vin_rel = v2 - vp2
        r, vp, t = r2, vp2, t2
    vinf_arr = float(np.linalg.norm(vin_rel))
    target = seq_names[-1]
    arr = float(capture_dv(vinf_arr, BODY[target]["mu"], cap_rp, cap_period_s)) if capture else 0.0
    return {
        "sequence": list(seq_names),
        "launch_jd": float(x[0]),
        "arrival_jd": t,
        "c3_km2s2": float(x[3] ** 2),
        "vinf_dep_kms": float(x[3]),
        "dla_deg": float(dla),
        "arcs": arcs,
        "dsms": dsms,
        "flybys": flybys,
        "vinf_arr_kms": vinf_arr,
        "arrival_dv_kms": arr,
        "dsm_dv_kms": float(sum(d["dv_kms"] for d in dsms)),
    }
