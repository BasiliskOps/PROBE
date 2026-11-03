# PROBE (repository name only)

"Probe" is the repository name. It never appears in anything public: page titles, copy, metadata or file names served to visitors. Public-facing, this is Ephemeris, the Lastelle AI instrument that locates and plots the bodies of the local system. The Cloudflare Worker keeps the internal name `lastelle-atlas`.

## What it is

Direction set by Damien on 2026-11-01. A collection swarm pulls published survey and mission data on the small bodies of the local star system, a deterministic ranking scores them by expected resource yield against the cost to reach them, and a Three.js interface plots the result on a model of the system. It is the first piece of Lastelle's aerospace work, which reaches toward a wider network of sensors and probes held in orbit around the planets.

Serious instrument, no game layer. No simulated missions, personas, letters, subscriptions or payments in the core.

## Core layout

- `app/collect/agents.py` — collection agents, one per published source, run concurrently:
  - catalog: JPL SBDB query API (spectrally characterized asteroids plus near-Earth asteroids with H <= 20)
  - physical: JPL SBDB lookup API, measured GM, density, diameter and rotation with literature references, for the leading candidates and visited bodies
  - ephemeris: JPL DE421 kernel, planet osculating elements (ecliptic J2000)
  - imagery: NASA Image and Video Library API, mission imagery for spacecraft-visited bodies (logos, patches and illustrations filtered out)
- `app/collect/run.py` — orchestrates a run and writes `site/data/system.json` and `site/data/manifest.json` (per-agent status, counts, timing, method).
- `app/prospect/rank.py` — deterministic ranking over `composition.prior` and `planner.reach_dv_kms`.
- `app/prospect/` and `app/astro/` — catalog parsing, composition priors, reach estimate, and the trajectory engine (kept for future mission design).
- `site/` — static interface: `index.html`, `style.css`, `app.js` (three.js 0.170 from jsDelivr via import map), `_headers` (CSP with a hash for the inline import map; regenerate the hash if the import map changes), brand assets.
- `.github/workflows/collect.yml` — daily collection run at 03:17 UTC, commits `site/data` when it changes.
- `wrangler.jsonc` — Cloudflare Workers static assets serving `site/`; Workers Builds redeploys on every push.

## Data rules (binding)

- Agents collect only. No language model generates, estimates or rewrites any number in the data path.
- Every published value traces to a source: SBDB record link per body, references on measured parameters, NASA page per image, agent provenance in the manifest.
- A run with an empty catalog refuses to publish.
- Copy states estimates as estimates with their range. No absolutes, no revenue or capability claims.

## funding/ (dormant)

The original mission designer, flight state, persona agents, waker, web pages, REST and MCP API, house fleet and payment rail live in `funding/`, held for a future layer where people back missions Lastelle flies. Nothing in `app/` imports it and nothing deploys it. Its tests are in `funding/tests/`. See `funding/README.md`.

## Tests

- `python -m pytest -q tests` — core (collection, ranking, Europa Clipper trajectory rediscovery).
- `python -m pytest -q funding/tests` — dormant layer, including the OSIRIS-REx Earth-Earth-Bennu rediscovery. Keep both green.

## Stack rules (binding)

- No npm, React or JS build tools in what ships. three.js loads from a CDN only.
- Free-tier cloud only. No Supabase, Neon, Vercel or similar defaults.
- Built with Claude models and Claude agent swarms only.

## Launch gate

Run the `security-audit` skill (`.claude/skills/security-audit/`) against the full repo before every launch and every public deploy. No launch ships with an open high or critical finding.
