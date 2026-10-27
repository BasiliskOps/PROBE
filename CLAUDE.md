# PROBE

Aerospace product in the DATA PRODUCTS project.

## Product spec

- A user types a mission in one sentence, for example "send a probe to Europa that photographs Jupiter on the way."
- An agent swarm designs it with real orbital mechanics: the next real launch window from today, gravity assists and the fuel budget computed against JPL Horizons ephemerides with open astrodynamics libraries such as pykep or poliastro, and a real launch vehicle.
- The probe then flies in real time through the actual solar system, so a Europa mission takes years and arrives on a real date.
- It messages its owner in character at each milestone: course corrections, flybys, arrival.
- At set points it asks the owner for a decision, such as spending fuel on a detour or saving it, and each choice changes the rest of the mission.
- A three.js view shows where the probe is right now among the real planets. Every mission gets a shareable patch and a flythrough clip for X.
- The model wakes only at milestones to keep running costs low.
- Pricing: one free probe; $9.99 a month for a fleet and decision points; about $1 per mission design over the API for agents.
- Incumbents with room to compete: NASA's Trajectory Browser (free, expert, precomputed paths), NASA Eyes (NASA's own missions only), and Universe Sandbox and Kerbal (fictional missions).
- Launch post: Damien's own probe to Europa with its flythrough and arrival date, timed to the next Starship flight.

## Endpoints

| Route | Price | Purpose |
|---|---|---|
| `POST /api/v1/missions/design` | x402, `PRICE_MISSION_DESIGN` (default $1.00) | One-sentence mission in, designed mission and owner token out |
| `GET /api/v1/missions/{id}` | free | Plan, live state, timeline, open decisions |
| `GET /api/v1/missions/{id}/track` | free | Trajectory polyline (ecliptic AU, with Julian dates) and current position |
| `GET /api/v1/missions/{id}/messages` | free | The probe's letters |
| `GET /api/v1/missions/{id}/patch.svg` | free | Mission patch drawn from the real trajectory |
| `POST /api/v1/missions/{id}/decisions` | owner token (`X-Owner-Token`), fleet or API plan | Answer an open decision point |
| `GET /api/v1/sky` | free | Planet positions and orbits right now |
| MCP `design_mission` | x402, same price | Agent version of mission design |
| MCP `mission_status` | free | Agent version of mission state |
| MCP `mission_decide` | owner token | Agent version of a decision |
| `GET /`, `GET /m/{id}` | free | Web: one free probe per browser, mission page with the live sky |

## How the engine works

- `app/astro/ephemeris.py`: heliocentric ICRF planet tables from JPL Horizons (live, production) or the JPL DE421 kernel (offline, tests, fallback when Horizons is unreachable). The source is recorded on every mission.
- `app/astro/mga.py`: MGA-1DSM trajectories (one deep-space maneuver per leg, unpowered flybys), Izzo Lambert arcs via lamberthub, compiled with numba. pykep's only PyPI wheel (3.0.1) is broken (missing data file), so it is not used.
- `app/astro/search.py`: launch window search. Differential evolution per route and launch-date bin, then a local polish. Cost is required wet mass over launcher capability at that C3, with a declination penalty past 28.5°. "Soonest" picks the earliest window within 15 % of the best design in a three-year horizon.
- `app/astro/vehicles.py`: Falcon 9, New Glenn, Falcon Heavy (both modes) and Vulcan VC6S payload-to-C3 curves from NASA launch vehicle data. Never extrapolated. Starship and SLS are absent because no C3 curve is published.
- `tests/test_astro.py` rediscovers Europa Clipper's Mars-Earth gravity-assist trajectory inside its real launch period. Keep that test passing.

## Swarm, flight and decisions

- `app/swarm/intent.py` (sentence to mission spec), `app/swarm/agents.py` (persona, flight director brief, milestone voice). Each forces one tool call and has a deterministic fallback. Models: `MODEL_AGENTS`, `MODEL_VOICE`.
- `app/missions/designer.py` runs intent, the parallel trajectory search and the agents; `app/missions/flight.py` computes position, timeline, orbit crossings and decisions from the stored design vector.
- Decisions are physically costed. A closer flyby re-solves everything downstream (arrival date may move); a faster capture orbit costs the real extra insertion burn. Spending comes out of the 10 % delta-v margin, choices are charged at the recomputed cost, and silence keeps the propellant.
- `app/waker.py` calls the voice model only when a milestone is due (in-process loop every `WAKER_INTERVAL_S`, or `python -m app.waker` from cron), and posts to the mission's `notify_url` if one was given.

## Not built yet

- Flythrough clip for X. Fleet subscription checkout (the dev provider is a stand-in, and the free probe is limited per browser by cookie). Wiring the MCP paywall decorator to `x402.mcp`.

## Stack rules (binding)

- FastAPI with Jinja2 templates and HTMX. Tailwind, HTMX and three.js load from a CDN only. No npm, React or JS build tools.
- Free-tier cloud only. No Supabase, Neon, Vercel or similar defaults.
- Every capability is exposed twice: a REST API under `/api/v1` and an MCP server at `/mcp`. Agents pay per call over x402 (USDC). User-initiated checkout is supported through `app/payments/checkout.py`, which keeps the payment provider behind one interface.
- Built with Claude models and Claude agent swarms only.
- Project constraints live in the DATA PRODUCTS project docs `claude/constraints.md` and `claude/idea-ledger.md`. Apply every constraint exactly as written.

## Launch gate

Run the `security-audit` skill (`.claude/skills/security-audit/`) against the full repo before every launch and every public deploy. No launch ships with an open high or critical finding.

## Skills in this repo

- `.claude/skills/security-audit/` — Cloudflare security-audit skill (MIT, license kept in the folder).
- `.claude/skills/product-brainstorming/` — Anthropic knowledge-work-plugins (Apache-2.0, license kept in the folder).
- `.claude/skills/evaluating-startup-ideas/` and `.claude/skills/idea-validation/` — Refound AI lenny-skills (MIT, license kept in each folder).

## Layout

- `app/main.py` — app factory, x402 middleware, MCP mount, static files, waker loop
- `app/astro/` — ephemerides, trajectories, launch window search, vehicles
- `app/swarm/` — Claude client and agents
- `app/missions/` — design orchestration, flight state and decisions, SQLite store, patch
- `app/api/routes.py` — REST endpoints; `app/web.py` — web pages
- `app/mcp_server.py` — MCP tools, paid ones wrapped with x402
- `app/payments/` — x402 rail and the abstract checkout provider
- `app/templates/`, `app/static/sky.js` — Jinja2 + HTMX + Tailwind and three.js (CDN)
- `tests/` — engine validation, pipeline, agents, 402 on paid routes
