# funding (dormant)

Held for a future mission-funding layer, where people back missions Lastelle actually flies. Nothing in `app/` imports this package, and none of it is deployed.

Contents carried over from the original build: the mission designer and flight state (`missions/`), the per-call payment rail and checkout interface (`payments/`), the milestone waker, the mission web pages and API (`web.py`, `api/`, `mcp_server.py`, `templates/`, `static/`), the persona and intent agents (`swarm/`), and the house fleet (`fleet.py`). It still runs as before with `uvicorn funding.main:app`, and its tests live in `funding/tests/`.

Public investment in missions is a regulated securities offering in the US. Counsel reviews this layer before any part of it goes live.
