# PROBE

Type a mission in one sentence. An agent swarm designs it with real orbital mechanics against JPL ephemerides,
puts it on a real rocket in the next real launch window, and the probe flies it in real time, writing to its
owner at every milestone and asking for decisions that change the rest of the mission.

```
pip install -r requirements.txt
cp .env.example .env          # set ANTHROPIC_API_KEY; EPHEMERIS_SOURCE=de421 works offline
uvicorn app.main:app --reload
python -m pytest -q
```
