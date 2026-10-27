"""SQLite persistence. Missions are stored as JSON documents; messages are rows."""
from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import threading
import time
from pathlib import Path

from app.config import settings

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None

SCHEMA = """
create table if not exists missions (
    id text primary key,
    owner_hash text not null,
    status text not null,
    created_at real not null,
    doc text not null
);
create table if not exists messages (
    id integer primary key autoincrement,
    mission_id text not null,
    event_id text not null,
    jd real not null,
    kind text not null,
    text text not null,
    created_at real not null,
    unique (mission_id, event_id)
);
create index if not exists messages_mission on messages (mission_id, jd);
create table if not exists surveys (
    id integer primary key autoincrement,
    mission_id text not null,
    target_id text not null,
    jd real not null,
    doc text not null,
    unique (mission_id, target_id)
);
create index if not exists surveys_target on surveys (target_id);
create table if not exists meta (key text primary key, value text not null);
"""


def conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        path = Path(settings.data_dir)
        path.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(path / "probe.db", check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.executescript(SCHEMA)
    return _conn


def reset(path: Path | None = None) -> None:
    """Point the store at a fresh database (tests)."""
    global _conn
    _conn = None
    if path is not None:
        settings.data_dir = path


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create(sentence: str) -> tuple[str, str]:
    mid = secrets.token_urlsafe(9)
    token = secrets.token_urlsafe(24)
    doc = {"id": mid, "sentence": sentence, "status": "designing", "created_at": time.time()}
    with _lock:
        conn().execute("insert into missions values (?, ?, ?, ?, ?)",
                       (mid, _hash(token), "designing", doc["created_at"], json.dumps(doc)))
        conn().commit()
    return mid, token


def get(mid: str) -> dict | None:
    row = conn().execute("select doc from missions where id = ?", (mid,)).fetchone()
    return json.loads(row["doc"]) if row else None


def save(m: dict) -> None:
    with _lock:
        conn().execute("update missions set doc = ?, status = ? where id = ?", (json.dumps(m), m["status"], m["id"]))
        conn().commit()


def is_owner(mid: str, token: str | None) -> bool:
    if not token:
        return False
    row = conn().execute("select owner_hash from missions where id = ?", (mid,)).fetchone()
    return bool(row) and secrets.compare_digest(row["owner_hash"], _hash(token))


def active() -> list[dict]:
    rows = conn().execute("select doc from missions where status in ('ready', 'in_flight', 'arrived')").fetchall()
    return [json.loads(r["doc"]) for r in rows]


def add_message(mid: str, event_id: str, jd: float, kind: str, text: str) -> bool:
    with _lock:
        cur = conn().execute(
            "insert or ignore into messages (mission_id, event_id, jd, kind, text, created_at) values (?,?,?,?,?,?)",
            (mid, event_id, jd, kind, text, time.time()))
        conn().commit()
    return cur.rowcount == 1


def messaged(mid: str) -> set[str]:
    return {r["event_id"] for r in conn().execute("select event_id from messages where mission_id = ?", (mid,))}


def messages(mid: str) -> list[dict]:
    rows = conn().execute("select event_id, jd, kind, text from messages where mission_id = ? order by jd desc, id desc",
                          (mid,)).fetchall()
    return [dict(r) for r in rows]


def add_survey(mid: str, target_id: str, jd: float, doc: dict) -> bool:
    with _lock:
        cur = conn().execute("insert or ignore into surveys (mission_id, target_id, jd, doc) values (?,?,?,?)",
                             (mid, target_id, jd, json.dumps(doc)))
        conn().commit()
    return cur.rowcount == 1


def surveys(target_id: str | None = None) -> list[dict]:
    if target_id:
        rows = conn().execute("select mission_id, target_id, jd, doc from surveys where target_id = ? order by jd",
                              (target_id,)).fetchall()
    else:
        rows = conn().execute("select mission_id, target_id, jd, doc from surveys order by jd").fetchall()
    return [{"mission_id": r["mission_id"], "target_id": r["target_id"], "jd": r["jd"], **json.loads(r["doc"])}
            for r in rows]


def recent(limit: int = 12) -> list[dict]:
    rows = conn().execute("select doc from missions where status in ('ready','in_flight','arrived') "
                          "order by created_at desc limit ?", (limit,)).fetchall()
    return [json.loads(r["doc"]) for r in rows]


def get_meta(key: str, default: str | None = None) -> str | None:
    row = conn().execute("select value from meta where key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_meta(key: str, value: str) -> None:
    with _lock:
        conn().execute("insert into meta (key, value) values (?, ?) on conflict(key) do update set value = excluded.value",
                       (key, value))
        conn().commit()


def targeted_ids(plan: str | None = None) -> set[str]:
    out = set()
    for m in active():
        if (plan is None or m.get("plan") == plan) and m.get("spec", {}).get("small_body"):
            out.add(m["spec"]["small_body"]["id"])
    return out
