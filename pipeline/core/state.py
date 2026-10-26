"""SQLite state: state.db (runs/steps/cache/usage) and library.db (techplan §5.7)."""

import json
import sqlite3
from pathlib import Path

STATE_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    manifest TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    status TEXT NOT NULL DEFAULT 'running'
);
CREATE TABLE IF NOT EXISTS steps (
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    step TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    artifact TEXT,
    error TEXT,
    updated_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (run_id, step)
);
CREATE TABLE IF NOT EXISTS cache (
    key TEXT PRIMARY KEY,
    ptype TEXT NOT NULL,
    provider TEXT NOT NULL,
    response TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    ptype TEXT NOT NULL,
    provider TEXT NOT NULL,
    cost_usd REAL NOT NULL DEFAULT 0,
    tokens INTEGER NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);
"""

LIBRARY_SCHEMA = """
CREATE TABLE IF NOT EXISTS channels (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    style_notes TEXT DEFAULT '',
    language TEXT DEFAULT 'ru',
    palette TEXT DEFAULT '',
    links TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS episodes (
    run_id TEXT PRIMARY KEY,
    channel_id TEXT NOT NULL,
    topic TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    published_video_id TEXT,
    notes TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS topics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'idea',
    source TEXT DEFAULT '',
    score REAL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS "references" (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    path TEXT NOT NULL,
    notes TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scope TEXT NOT NULL,
    ref_id TEXT,
    body TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);
"""


class StateDB:
    """Run/step checkpoints, provider cache and usage accounting."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(STATE_SCHEMA)

    def close(self):
        self.conn.close()

    # runs -------------------------------------------------------------------
    def create_run(self, run_id: str, manifest: dict):
        self.conn.execute(
            "INSERT OR REPLACE INTO runs(run_id, manifest) VALUES (?, ?)",
            (run_id, json.dumps(manifest, ensure_ascii=False)),
        )
        self.conn.commit()

    def get_run(self, run_id: str) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()

    def set_run_status(self, run_id: str, status: str):
        self.conn.execute("UPDATE runs SET status=? WHERE run_id=?", (status, run_id))
        self.conn.commit()

    # steps ------------------------------------------------------------------
    def set_step(self, run_id: str, step: str, status: str, artifact: str | None = None, error: str | None = None):
        self.conn.execute(
            "INSERT OR REPLACE INTO steps(run_id, step, status, artifact, error, updated_at)"
            " VALUES (?, ?, ?, ?, ?, datetime('now'))",
            (run_id, step, status, artifact, error),
        )
        self.conn.commit()

    def get_step(self, run_id: str, step: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM steps WHERE run_id=? AND step=?", (run_id, step)
        ).fetchone()

    def is_step_done(self, run_id: str, step: str) -> bool:
        row = self.get_step(run_id, step)
        return bool(row and row["status"] == "done" and row["artifact"] and Path(row["artifact"]).exists())

    def reset_steps_from(self, run_id: str, from_step: str, steps_order: list[str]) -> None:
        """Invalidate a step and all downstream steps so they re-run."""
        if from_step in steps_order:
            idx = steps_order.index(from_step)
            to_reset = steps_order[idx:]
            placeholders = ",".join("?" for _ in to_reset)
            self.conn.execute(
                f"DELETE FROM steps WHERE run_id=? AND step IN ({placeholders})",
                (run_id, *to_reset),
            )
            self.conn.commit()

    def list_runs(self) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM runs ORDER BY created_at DESC").fetchall()

    # cache ------------------------------------------------------------------
    def cache_get(self, key: str) -> str | None:
        row = self.conn.execute("SELECT response FROM cache WHERE key=?", (key,)).fetchone()
        return row["response"] if row else None

    def cache_put(self, key: str, ptype: str, provider: str, response: str):
        self.conn.execute(
            "INSERT OR REPLACE INTO cache(key, ptype, provider, response) VALUES (?, ?, ?, ?)",
            (key, ptype, provider, response),
        )
        self.conn.commit()

    # usage ------------------------------------------------------------------
    def usage_add(self, run_id: str, ptype: str, provider: str, cost_usd: float = 0.0, tokens: int = 0):
        self.conn.execute(
            "INSERT INTO usage(run_id, ptype, provider, cost_usd, tokens) VALUES (?, ?, ?, ?, ?)",
            (run_id, ptype, provider, cost_usd, tokens),
        )
        self.conn.commit()

    def usage_spent(self, run_id: str) -> float:
        row = self.conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0) AS s FROM usage WHERE run_id=?", (run_id,)
        ).fetchone()
        return float(row["s"])

    def usage_tokens(self, run_id: str) -> int:
        row = self.conn.execute(
            "SELECT COALESCE(SUM(tokens), 0) AS s FROM usage WHERE run_id=?", (run_id,)
        ).fetchone()
        return int(row["s"])


class LibraryDB:

    """Channel profiles, episodes, topic bank, references, notes (techplan §5.7)."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(LIBRARY_SCHEMA)

    def close(self):
        self.conn.close()

    def upsert_channel(self, channel_id: str, name: str, description: str = "", language: str = "ru"):
        self.conn.execute(
            "INSERT OR REPLACE INTO channels(id, name, description, language) VALUES (?, ?, ?, ?)",
            (channel_id, name, description, language),
        )
        self.conn.commit()

    def upsert_episode(self, run_id: str, channel_id: str, topic: str, status: str = "draft"):
        self.conn.execute(
            "INSERT OR REPLACE INTO episodes(run_id, channel_id, topic, status) VALUES (?, ?, ?, ?)",
            (run_id, channel_id, topic, status),
        )
        self.conn.commit()

    def set_episode_published(self, run_id: str, video_id: str):
        self.conn.execute(
            "UPDATE episodes SET published_video_id=?, status='published' WHERE run_id=?",
            (video_id, run_id),
        )
        self.conn.commit()

    def add_topic(self, channel_id: str, title: str, status: str = "idea", source: str = "") -> int:
        cur = self.conn.execute(
            "INSERT INTO topics(channel_id, title, status, source) VALUES (?, ?, ?, ?)",
            (channel_id, title, status, source),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def add_note(self, scope: str, ref_id: str | None, body: str) -> int:
        cur = self.conn.execute(
            "INSERT INTO notes(scope, ref_id, body) VALUES (?, ?, ?)", (scope, ref_id, body)
        )
        self.conn.commit()
        return int(cur.lastrowid)
