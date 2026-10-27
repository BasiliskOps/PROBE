"""Physical constants and body data used by the trajectory engine.

Units: km, km/s, km^3/s^2. Gravitational parameters are JPL values.
"""

MU_SUN = 1.32712440018e11
AU_KM = 1.495978707e8
G0 = 9.80665e-3  # km/s^2
DAY_S = 86400.0
EMRAT = 81.30056907419062  # DE421 Earth/Moon mass ratio
OBLIQUITY_DEG = 23.4392911  # J2000 mean obliquity, for ICRF -> ecliptic display

# Index order is shared by every table in the engine.
PLANETS = ["mercury", "venus", "earth", "mars", "jupiter", "saturn", "uranus", "neptune"]
INDEX = {name: i for i, name in enumerate(PLANETS)}

HORIZONS_ID = {
    "mercury": "199",
    "venus": "299",
    "earth": "399",
    "mars": "499",
    "jupiter": "599",
    "saturn": "699",
    "uranus": "799",
    "neptune": "899",
}

# mu (km^3/s^2), equatorial radius (km), minimum flyby periapsis (km).
# Flyby floors: 300 km altitude for rocky planets, radiation/ring-safe radii for giants.
BODY = {
    "mercury": {"mu": 22031.86, "radius": 2439.7, "rp_min": 2439.7 + 200.0, "a_au": 0.387},
    "venus": {"mu": 324858.59, "radius": 6051.8, "rp_min": 6051.8 + 300.0, "a_au": 0.723},
    "earth": {"mu": 398600.4418, "radius": 6378.137, "rp_min": 6378.137 + 300.0, "a_au": 1.0},
    "mars": {"mu": 42828.37, "radius": 3396.19, "rp_min": 3396.19 + 200.0, "a_au": 1.524},
    "jupiter": {"mu": 126686534.0, "radius": 71492.0, "rp_min": 71492.0 * 6.0, "a_au": 5.203},
    "saturn": {"mu": 37931187.0, "radius": 60268.0, "rp_min": 60268.0 * 3.0, "a_au": 9.537},
    "uranus": {"mu": 5793939.0, "radius": 25559.0, "rp_min": 25559.0 * 1.5, "a_au": 19.19},
    "neptune": {"mu": 6836529.0, "radius": 24764.0, "rp_min": 24764.0 * 1.2, "a_au": 30.07},
}

# Capture orbit on arrival: periapsis radius (km) and orbital period (days).
CAPTURE = {
    "mercury": {"rp": 2439.7 + 400.0, "period_days": 0.5},
    "venus": {"rp": 6051.8 + 300.0, "period_days": 1.0},
    "mars": {"rp": 3396.19 + 400.0, "period_days": 1.03},
    "jupiter": {"rp": 71492.0 * 5.0, "period_days": 200.0},
    "saturn": {"rp": 60268.0 * 1.3, "period_days": 150.0},
    "uranus": {"rp": 25559.0 * 1.5, "period_days": 100.0},
    "neptune": {"rp": 24764.0 * 1.2, "period_days": 100.0},
}

# Moons that can be mission targets. Arrival is at the parent planet, then a
# tour allowance (km/s) covers the moon campaign after capture.
MOONS = {
    "io": {"parent": "jupiter", "tour_dv": 0.25},
    "europa": {"parent": "jupiter", "tour_dv": 0.20},
    "ganymede": {"parent": "jupiter", "tour_dv": 0.20},
    "callisto": {"parent": "jupiter", "tour_dv": 0.15},
    "titan": {"parent": "saturn", "tour_dv": 0.10},
    "enceladus": {"parent": "saturn", "tour_dv": 0.30},
    "triton": {"parent": "neptune", "tour_dv": 0.30},
    "phobos": {"parent": "mars", "tour_dv": 0.40},
}

NAV_ALLOWANCE = 0.10  # km/s for trajectory correction maneuvers across the cruise
DV_MARGIN = 0.10  # 10 % margin on all deterministic probe delta-v
