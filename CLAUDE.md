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

## Endpoints (stubs)

| Route | Price | Purpose |
|---|---|---|
| `POST /api/v1/missions/design` | x402, `PRICE_MISSION_DESIGN` (default $1.00) | One-sentence mission in, designed mission out |
| `GET /api/v1/missions/{id}` | free | Mission plan and current state |
| `POST /api/v1/missions/{id}/decisions` | free to owner | Answer a pending decision point |
| MCP `design_mission` | x402, same price | Agent version of mission design |
| MCP `mission_status` | free | Agent version of mission state |

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

- `app/main.py` — app factory, x402 middleware, MCP mount, web routes
- `app/api/routes.py` — REST endpoints
- `app/mcp_server.py` — MCP tools, paid ones wrapped with x402
- `app/payments/` — x402 rail and the abstract checkout provider
- `app/templates/` — Jinja2 + HTMX + Tailwind (CDN)
- `tests/` — smoke tests, including the 402 response on paid routes
