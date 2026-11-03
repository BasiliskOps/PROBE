# Ephemeris

Resource-bearing bodies of the local star system, mapped from published survey and mission data and ranked by expected water, metals and volatiles against the cost to reach them. A Lastelle AI project.

```
pip install -r requirements-collect.txt
python -m app.collect.run          # collect, rank, write site/data
python -m http.server -d site      # view the interface locally
python -m pytest -q tests          # core tests (full engine: pip install -r requirements.txt)
```

Sources: JPL Small-Body Database (query and lookup APIs), JPL DE421 planetary ephemeris, NASA Image and Video Library.
