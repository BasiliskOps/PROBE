# PROBE

Aerospace product in the DATA PRODUCTS project.

## Product spec

Direction set by Damien on 2026-10-27: PROBE is a living prospecting layer for the solar system.

- Users send probes to investigate the solar system for critical resources: water and volatiles (propellant gases), iron, nickel, cobalt, carbon and platinum-group metals. One sentence in, for example "find water on a near-Earth asteroid".
- Targets come live from the JPL Small-Body Database (orbits, spectral class, albedo, diameter). The planner ranks asteroids by expected resource against reach; the engine designs a real trajectory (JPL ephemerides, gravity assists, deep-space maneuvers, propellant budget, a real launch vehicle's published performance). Launches are simulated; nothing depends on a launch provider.
- Probes fly on a mission clock (`MISSION_CLOCK`, default 30 mission days per real day), rendezvous or fly by, survey, and report measured tonnage with uncertainty. Measurements are simulated from catalog data and spectral class with meteorite analogs, one hidden truth per asteroid, so every probe that visits the same rock converges on the same answer.
- Every survey feeds a shared atlas (`/api/v1/atlas`) that tightens as more probes visit.
- The house fleet launches PROBE's own prospectors at newly discovered near-Earth asteroids from the live JPL feed, daily.
- Each probe has a character and writes to its owner at milestones; decision points spend or save propellant and change the rest of the mission. The model wakes only at milestones.
- Planets and the major moons remain valid destinations.
- Pricing: one free probe; $9.99 a month for a fleet and decision points; about $1 per mission design over the API for agents.
- Incumbents: Asterank (free asteroid value database, static estimates, no missions); NASA Eyes on Asteroids (visualization only). Industry prospecting services are not consumer products.

## Endpoints

| Route | Price | Purpose |
|---|---|---|
| `POST /api/v1/missions/design` | x402, `PRICE_MISSION_DESIGN` (default $1.00) | One-sentence mission in, designed mission and owner token out |
| `GET /api/v1/missions/{id}` | free | Plan, live state, timeline, open decisions |
| `GET /api/v1/missions/{id}/track` | free | Trajectory polyline (ecliptic AU, with Julian dates) and current position |
| `GET /api/v1/missions/{id}/messages` | free | The probe's letters |
| `GET /api/v1/missions/{id}/patch.svg` | free | Mission patch drawn from the real trajectory |
| `POST /api/v1/missions/{id}/decisions` | owner token (`X-Owner-Token`), fleet or API plan | Answer an open decision point |
| `GET /api/v1/sky?jd=` | free | Planet positions and orbits now, or at a mission date |
| `GET /api/v1/targets?resource=&region=` | free | Best prospecting targets in the live JPL catalog |
| `GET /api/v1/atlas` | free | Every surveyed asteroid with the combined estimate across probes |
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

## Prospecting

- `app/prospect/catalog.py`: JPL SBDB query API (characterized asteroids, newly discovered NEOs), cached daily, backs off when unreachable, falls back to `fixture_sbdb.json` (seven real asteroids, offline seed for tests and development only).
- `app/astro/smallbody.py`: SBDB elements to ICRF states; asteroids are appended to ephemeris tables as extra rows so the MGA engine flies to them.
- `app/prospect/composition.py`: spectral class to composition group, priors with ranges (sources in the docstring), hidden truth per asteroid, survey noise (rendezvous 10 %, flyby 35 %), inverse-variance combination.
- `app/prospect/planner.py` and `fleet.py`: target ranking and the daily house fleet.
- `tests/test_prospect.py` rediscovers OSIRIS-REx's Earth-Earth-Bennu trajectory. Keep it passing.

## Swarm, flight and decisions

- `app/swarm/intent.py` (sentence to mission spec), `app/swarm/agents.py` (persona, flight director brief, milestone voice). Each forces one tool call and has a deterministic fallback. Models: `MODEL_AGENTS`, `MODEL_VOICE`.
- `app/missions/designer.py` runs intent, the parallel trajectory search and the agents; `app/missions/flight.py` computes position, timeline, orbit crossings and decisions from the stored design vector.
- Decisions are physically costed. A closer flyby re-solves everything downstream (arrival date may move); a faster capture orbit costs the real extra insertion burn. Spending comes out of the 10 % delta-v margin, choices are charged at the recomputed cost, and silence keeps the propellant.
- `app/waker.py` calls the voice model only when a milestone is due (in-process loop every `WAKER_INTERVAL_S`, or `python -m app.waker` from cron), and posts to the mission's `notify_url` if one was given.

## Not built yet

- Asteroid-specific decision points (flyby decisions apply when a route has a flyby). Flythrough clip for X. Fleet subscription checkout (the dev provider is a stand-in, and the free probe is limited per browser by cookie). Wiring the MCP paywall decorator to `x402.mcp`.

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
- `app/prospect/` — JPL asteroid catalog, composition and surveys, target planner, house fleet
- `app/api/routes.py` — REST endpoints; `app/web.py` — web pages
- `app/mcp_server.py` — MCP tools, paid ones wrapped with x402
- `app/payments/` — x402 rail and the abstract checkout provider
- `app/templates/`, `app/static/sky.js` — Jinja2 + HTMX + Tailwind and three.js (CDN)
- `tests/` — engine validation, pipeline, agents, 402 on paid routes
