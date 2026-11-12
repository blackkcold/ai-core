"""SQLite state, shared quota reservation, time-bounded cache and usage ledger.

Reservations happen transactionally before dispatch, even when the request
fails. Counters are provider-global to prevent tenant switching from avoiding
the caller's own configured provider quota. They are NOT vendor billing data.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path

from .errors import BudgetExceeded


class Store:
    def __init__(self, path: str = ":memory:", *, clock=None):
        self.clock = clock or time.time
        self.path = str(path)
        if path != ":memory:":
            Path(path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, timeout=10, isolation_level=None, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        with self.lock:
            self.db.execute("PRAGMA busy_timeout=10000")
            self.db.execute("CREATE TABLE IF NOT EXISTS quotas (provider TEXT NOT NULL, "
                            "kind TEXT NOT NULL, window TEXT NOT NULL, used INTEGER NOT NULL, "
                            "PRIMARY KEY(provider, kind, window))")
            self.db.execute("CREATE TABLE IF NOT EXISTS attempts (id TEXT PRIMARY KEY, "
                            "tenant TEXT NOT NULL, provider TEXT NOT NULL, at INTEGER NOT NULL, "
                            "status TEXT NOT NULL)")
            self.db.execute("CREATE INDEX IF NOT EXISTS attempts_tenant_idx ON attempts(tenant,at)")
            self.db.execute("CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, "
                            "value TEXT NOT NULL, expires INTEGER NOT NULL)")
            self.db.execute("CREATE TABLE IF NOT EXISTS cooldowns (provider TEXT PRIMARY KEY, "
                            "until INTEGER NOT NULL)")
            self.db.execute("CREATE TABLE IF NOT EXISTS llm_usage (id TEXT PRIMARY KEY, "
                            "tenant TEXT NOT NULL, provider TEXT NOT NULL, model TEXT NOT NULL, "
                            "input_tokens INTEGER, output_tokens INTEGER, at INTEGER NOT NULL)")

    def close(self):
        with self.lock:
            self.db.close()

    @staticmethod
    def _window(timestamp: int, kind: str) -> str:
        return time.strftime("%Y-%m-%d" if kind == "day" else "%Y-%m", time.gmtime(timestamp))

    def reserve(self, provider: str, tenant: str, daily_limit: int, monthly_limit: int | None = None) -> str:
        now = int(self.clock())
        windows = [("day", self._window(now, "day"), daily_limit)]
        if monthly_limit is not None:
            windows.append(("month", self._window(now, "month"), monthly_limit))
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                for kind, window, limit in windows:
                    if limit < 0:
                        raise BudgetExceeded("negative quota configuration")
                    row = self.db.execute("SELECT used FROM quotas WHERE provider=? AND kind=? AND window=?",
                                          (provider, kind, window)).fetchone()
                    if row is not None and row["used"] >= limit or limit == 0:
                        raise BudgetExceeded("local search " + kind + " quota reached for " + provider)
                for kind, window, _ in windows:
                    self.db.execute("INSERT INTO quotas(provider,kind,window,used) VALUES(?,?,?,1) "
                                    "ON CONFLICT(provider,kind,window) DO UPDATE SET used=used+1",
                                    (provider, kind, window))
                attempt = uuid.uuid4().hex
                self.db.execute("INSERT INTO attempts(id,tenant,provider,at,status) VALUES(?,?,?,?,?)",
                                (attempt, tenant, provider, now, "dispatched"))
                self.db.execute("COMMIT")
                return attempt
            except Exception:
                self.db.execute("ROLLBACK")
                raise

    def finish(self, attempt: str, status: str):
        with self.lock:
            self.db.execute("UPDATE attempts SET status=? WHERE id=?", (status[:40], attempt))

    def usage(self, tenant: str | None = None) -> list[dict]:
        with self.lock:
            if tenant is None:
                rows = self.db.execute("SELECT provider,status,COUNT(*) AS calls FROM attempts "
                                       "GROUP BY provider,status ORDER BY provider,status").fetchall()
            else:
                rows = self.db.execute("SELECT provider,status,COUNT(*) AS calls FROM attempts "
                                       "WHERE tenant=? GROUP BY provider,status ORDER BY provider,status",
                                       (tenant,)).fetchall()
        return [dict(row) for row in rows]

    def record_llm(self, tenant: str, provider: str, model: str,
                   input_tokens: int | None, output_tokens: int | None):
        with self.lock:
            self.db.execute("INSERT INTO llm_usage VALUES (?,?,?,?,?,?,?)", (
                uuid.uuid4().hex, tenant, provider, model, input_tokens, output_tokens, int(self.clock())))

    def llm_usage(self, tenant: str | None = None) -> list[dict]:
        sql = ("SELECT provider,model,COUNT(*) AS calls, "
               "SUM(input_tokens) AS input_tokens,SUM(output_tokens) AS output_tokens FROM llm_usage ")
        args = ()
        if tenant is not None:
            sql += "WHERE tenant=? "
            args = (tenant,)
        sql += "GROUP BY provider,model ORDER BY provider,model"
        with self.lock:
            return [dict(r) for r in self.db.execute(sql, args).fetchall()]

    def cache_get(self, key: str):
        with self.lock:
            row = self.db.execute("SELECT value FROM cache WHERE key=? AND expires>?",
                                  (key, int(self.clock()))).fetchone()
        return json.loads(row["value"]) if row else None

    def cache_put(self, key: str, value: dict, ttl_seconds: int):
        if ttl_seconds <= 0:
            return
        with self.lock:
            self.db.execute("INSERT INTO cache(key,value,expires) VALUES(?,?,?) ON CONFLICT(key) "
                            "DO UPDATE SET value=excluded.value,expires=excluded.expires",
                            (key, json.dumps(value, ensure_ascii=False),
                             int(self.clock()) + ttl_seconds))

    def quota_snapshot(self, provider: str) -> dict:
        now = int(self.clock())
        with self.lock:
            counts = {}
            for kind in ("day", "month"):
                window = self._window(now, kind)
                row = self.db.execute(
                    "SELECT used FROM quotas WHERE provider=? AND kind=? AND window=?",
                    (provider, kind, window)).fetchone()
                counts["used_today" if kind == "day" else "used_this_month"] = (
                    row["used"] if row else 0)
        counts["cooldown_seconds"] = self.cooldown(provider)
        return counts

    def cooldown(self, provider: str) -> int:
        with self.lock:
            row = self.db.execute("SELECT until FROM cooldowns WHERE provider=?", (provider,)).fetchone()
        return max(0, row["until"] - int(self.clock())) if row else 0

    def set_cooldown(self, provider: str, seconds: int):
        with self.lock:
            self.db.execute("INSERT INTO cooldowns VALUES(?,?) ON CONFLICT(provider) DO UPDATE "
                            "SET until=excluded.until",
                            (provider, int(self.clock()) + max(1, min(86400, seconds))))
