"""Mission patch: an SVG badge drawn from the mission's actual trajectory."""
from __future__ import annotations

from html import escape

from app.astro.search import iso

from . import flight

PLANET_COLOR = {"mercury": "#b3a79a", "venus": "#e8c27a", "earth": "#4f8fdc", "mars": "#d0623b",
                "jupiter": "#d9a46c", "saturn": "#e3cf8f", "uranus": "#8fd3d8", "neptune": "#5873e0"}


ASTEROID_COLOR = "#A9B7C9"


def svg(m: dict, size: int = 600) -> str:
    flight.mission_table(m)  # registers an asteroid target with the body table
    pts = flight.track(m, points_per_year=60)
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    span = max(max(map(abs, xs)), max(map(abs, ys)), 1.2)
    c, rad = size / 2, size * 0.30

    def xy(p):
        return c + p[0] / span * rad, c - p[1] / span * rad

    path = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in map(xy, pts))
    det = m["detail"]
    bodies = []
    for b in dict.fromkeys(det["sequence"]):
        a = flight.BODY[b]["a_au"] / span * rad
        if a < rad * 1.15:
            bodies.append(f'<circle cx="{c}" cy="{c}" r="{a:.1f}" fill="none" stroke="{PLANET_COLOR.get(b, ASTEROID_COLOR)}" '
                          f'stroke-opacity="0.45" stroke-width="2"/>')
    end = xy(pts[-1])
    name = escape(m.get("persona", {}).get("name", "PROBE").upper())
    sb = m["spec"].get("small_body")
    label = sb["name"].split(" (")[0] if sb else m["spec"]["target"]
    target = escape(label.upper())
    dates = f"{iso(det['launch_jd'])[:4]}–{iso(det['arrival_jd'])[:4]}"
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" width="{size}" height="{size}">
<defs>
  <path id="top" d="M {c - size*0.40},{c} A {size*0.40},{size*0.40} 0 0 1 {c + size*0.40},{c}"/>
  <path id="bottom" d="M {c - size*0.43},{c} A {size*0.43},{size*0.43} 0 0 0 {c + size*0.43},{c}"/>
  <radialGradient id="sun"><stop offset="0" stop-color="#fff6d5"/><stop offset="1" stop-color="#f5a623"/></radialGradient>
</defs>
<circle cx="{c}" cy="{c}" r="{size*0.48}" fill="#10163A" stroke="#E2B04A" stroke-width="{size*0.02}"/>
<circle cx="{c}" cy="{c}" r="{size*0.355}" fill="#0A0F2B" stroke="#E2B04A" stroke-width="2"/>
{''.join(bodies)}
<circle cx="{c}" cy="{c}" r="{size*0.022}" fill="url(#sun)"/>
<path d="{path}" fill="none" stroke="#E2B04A" stroke-width="3" stroke-linecap="round"/>
<circle cx="{end[0]:.1f}" cy="{end[1]:.1f}" r="{size*0.014}" fill="{PLANET_COLOR.get(det['sequence'][-1], ASTEROID_COLOR)}"/>
<text font-family="Helvetica, Arial, sans-serif" font-weight="700" font-size="{size*0.07}" fill="#F1EEE6"
  letter-spacing="{size*0.008}"><textPath href="#top" startOffset="50%" text-anchor="middle">{name}</textPath></text>
<text font-family="Helvetica, Arial, sans-serif" font-weight="600" font-size="{size*0.042}" fill="#F1EEE6"
  letter-spacing="{size*0.006}"><textPath href="#bottom" startOffset="50%" text-anchor="middle">{target} {dates}</textPath></text>
</svg>"""
