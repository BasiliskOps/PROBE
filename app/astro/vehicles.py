"""Launch vehicles with published escape performance.

Payload (kg) versus launch energy C3 (km^2/s^2), from NASA Launch Vehicle
Performance data as tabulated in "Launch Vehicle Market and Future State",
Planetary Decadal Survey briefing, July 7, 2021 (values rounded down to 100 kg):
https://www.nationalacademies.org/index.php/cdn/materials/9fba0b9e-71c1-41b1-bf6d-7fe23f7c54b2

Starship and SLS are left out because no C3 performance curve has been
published for them. A vehicle is never extrapolated past its last data point.
"""
from __future__ import annotations

import numpy as np

SOURCE = "NASA LVPS via Planetary Decadal Survey launch vehicle briefing, 2021-07-07"

# Ordered from smallest to largest, so the first vehicle that fits is chosen.
VEHICLES = [
    {"name": "Falcon 9 (recoverable)", "provider": "SpaceX", "c3": [0, 10], "kg": [3310, 2220]},
    {"name": "New Glenn", "provider": "Blue Origin", "c3": [0, 10, 20], "kg": [7100, 4900, 2300]},
    {"name": "Falcon Heavy (recoverable)", "provider": "SpaceX", "c3": [0, 10, 20, 40, 55],
     "kg": [6690, 5130, 3845, 1805, 660]},
    {"name": "Vulcan VC6S", "provider": "ULA", "c3": [0, 10, 20, 40, 55], "kg": [10800, 9100, 7600, 5100, 3600]},
    {"name": "Falcon Heavy (expendable)", "provider": "SpaceX", "c3": [0, 10, 20, 40, 55],
     "kg": [15010, 12345, 10115, 6640, 4690]},
]


def capacity_kg(vehicle: dict, c3: float) -> float:
    """Payload to the given C3, or 0 when the C3 is outside the published curve."""
    c3s = vehicle["c3"]
    if c3 < c3s[0] or c3 > c3s[-1]:
        return 0.0
    return float(np.interp(c3, c3s, vehicle["kg"]))


def select_vehicle(c3: float, wet_mass_kg: float, margin: float = 0.05) -> dict | None:
    need = wet_mass_kg * (1.0 + margin)
    for v in VEHICLES:
        cap = capacity_kg(v, max(c3, 0.0))
        if cap >= need:
            return {"name": v["name"], "provider": v["provider"], "capacity_kg": round(cap),
                    "margin_kg": round(cap - wet_mass_kg), "source": SOURCE}
    return None


def max_c3() -> float:
    return max(v["c3"][-1] for v in VEHICLES)
