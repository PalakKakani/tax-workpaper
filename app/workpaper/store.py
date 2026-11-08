"""Append-only event store.

Every action anyone takes is one event. Nothing is ever updated or deleted:
an undo is a new event that reverses an earlier one. Each event carries the hash
of the previous one, so any tampering with history breaks the chain (verify()).

SQLite by default; set DATABASE_URL=postgres://... to use Postgres in production.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone

DB_URL = os.environ.get("DATABASE_URL", "")
SQLITE_PATH = os.environ.get("SQLITE_PATH", os.path.join(os.path.dirname(__file__), "..", "data", "workpaper.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
  seq        INTEGER PRIMARY KEY {autoinc},
  id         TEXT NOT NULL UNIQUE,
  at         TEXT NOT NULL,
  actor      TEXT NOT NULL,
  type       TEXT NOT NULL,
  target     TEXT,
  payload    TEXT NOT NULL,
  batch      TEXT,
  prev_hash  TEXT NOT NULL,
  hash       TEXT NOT NULL
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _digest(prev: str, at: str, actor: str, type_: str, target: str | None, payload: str) -> str:
    return hashlib.sha256("|".join([prev, at, actor, type_, target or "", payload]).encode()).hexdigest()


class EventStore:
    def __init__(self, url: str = DB_URL, sqlite_path: str = SQLITE_PATH):
        self.lock = threading.Lock()
        self.pg = url.startswith("postgres")
        if self.pg:
            import psycopg  # type: ignore

            self.conn = psycopg.connect(url, autocommit=True)
            self.ph = "%s"
            with self.conn.cursor() as c:
                c.execute(SCHEMA.replace("INTEGER PRIMARY KEY {autoinc}", "BIGSERIAL PRIMARY KEY"))
        else:
            os.makedirs(os.path.dirname(sqlite_path), exist_ok=True)
            self.conn = sqlite3.connect(sqlite_path, check_same_thread=False)
            self.ph = "?"
            self.conn.executescript(SCHEMA.format(autoinc="AUTOINCREMENT"))
            self.conn.commit()

    def _q(self, sql: str, args: tuple = ()) -> list[tuple]:
        sql = sql.replace("?", self.ph)
        if self.pg:
            with self.conn.cursor() as c:
                c.execute(sql, args)
                return c.fetchall() if c.description else []
        cur = self.conn.execute(sql, args)
        rows = cur.fetchall()
        self.conn.commit()
        return rows

    def all(self) -> list[dict]:
        rows = self._q("SELECT seq,id,at,actor,type,target,payload,batch,prev_hash,hash FROM events ORDER BY seq")
        return [dict(seq=r[0], id=r[1], at=r[2], actor=r[3], type=r[4], target=r[5], payload=json.loads(r[6]),
                     batch=r[7], prev_hash=r[8], hash=r[9]) for r in rows]

    def append(self, actor: str, type_: str, payload: dict, target: str | None = None, batch: str | None = None,
               at: str | None = None) -> dict:
        with self.lock:
            last = self._q("SELECT hash FROM events ORDER BY seq DESC LIMIT 1")
            prev = last[0][0] if last else "genesis"
            at = at or now_iso()
            body = json.dumps(payload, sort_keys=True)
            h = _digest(prev, at, actor, type_, target, body)
            eid = "evt-" + uuid.uuid4().hex[:10]
            self._q("INSERT INTO events (id,at,actor,type,target,payload,batch,prev_hash,hash) VALUES (?,?,?,?,?,?,?,?,?)",
                    (eid, at, actor, type_, target, body, batch, prev, h))
            seq = self._q("SELECT seq FROM events WHERE id=?", (eid,))[0][0]
            return dict(seq=seq, id=eid, at=at, actor=actor, type=type_, target=target, payload=payload, batch=batch, prev_hash=prev, hash=h)

    def verify(self) -> dict:
        prev = "genesis"
        for e in self.all():
            body = json.dumps(e["payload"], sort_keys=True)
            if e["prev_hash"] != prev or _digest(prev, e["at"], e["actor"], e["type"], e["target"], body) != e["hash"]:
                return {"ok": False, "broken_at": e["seq"]}
            prev = e["hash"]
        return {"ok": True, "events": len(self.all())}

    def reset(self) -> None:
        with self.lock:
            self._q("DELETE FROM events")
