# PROBE

Send a probe to prospect the solar system for water, nickel, cobalt and platinum-group metals. Targets come live
from NASA JPL's asteroid catalog. Each probe flies real orbital mechanics on a fast mission clock, surveys what it
finds and adds it to a shared atlas. A house fleet launches its own prospectors at newly discovered asteroids.

```
pip install -r requirements.txt
cp .env.example .env          # set ANTHROPIC_API_KEY; EPHEMERIS_SOURCE=de421 works offline
uvicorn app.main:app --reload
python -m pytest -q
```
