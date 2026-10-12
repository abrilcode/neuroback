"""Pseudonymous session storage.

The 2023 app used each patient's *name* as a SQL table name built with an f-string
(SQL injection; names with spaces, accents or duplicates broke it) and kept names next to
EEG in plain files. Here participants only ever exist as random pseudonyms, every query
is parameterised, and the schema is fixed. Keep any pseudonym-to-person key offline.
"""

from __future__ import annotations

import json
import secrets
import sqlite3
import time
from pathlib import Path

import numpy as np

SCHEMA = """
CREATE TABLE IF NOT EXISTS participants (
    pid TEXT PRIMARY KEY,
    created_at REAL NOT NULL,
    age_band TEXT,
    screening_passed INTEGER NOT NULL DEFAULT 0,
    consent_at REAL
);
CREATE TABLE IF NOT EXISTS sessions (
    session_id INTEGER PRIMARY KEY AUTOINCREMENT,
    pid TEXT NOT NULL REFERENCES participants(pid) ON DELETE CASCADE,
    started_at REAL NOT NULL,
    iaf_hz REAL,
    config_json TEXT,
    data_dir TEXT
);
"""


def new_pseudonym() -> str:
    return "P-" + secrets.token_hex(3).upper()


class Store:
    def __init__(self, root: Path | str = "neuroback-data"):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.root / "neuroback.db")
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript(SCHEMA)

    def add_participant(self, age_band: str | None, screening_passed: bool, consent: bool) -> str:
        pid = new_pseudonym()
        self.db.execute(
            "INSERT INTO participants (pid, created_at, age_band, screening_passed, consent_at) VALUES (?, ?, ?, ?, ?)",
            (pid, time.time(), age_band, int(screening_passed), time.time() if consent else None),
        )
        self.db.commit()
        return pid

    def participants(self) -> list[tuple]:
        return self.db.execute("SELECT pid, age_band, screening_passed FROM participants ORDER BY created_at").fetchall()

    def can_stimulate(self, pid: str) -> bool:
        row = self.db.execute("SELECT screening_passed, consent_at FROM participants WHERE pid = ?", (pid,)).fetchone()
        return bool(row and row[0] and row[1])

    def save_session(self, pid: str, eeg: np.ndarray, fs: float, events: list[dict], iaf: float | None, config: dict) -> int:
        cur = self.db.execute(
            "INSERT INTO sessions (pid, started_at, iaf_hz, config_json) VALUES (?, ?, ?, ?)",
            (pid, time.time(), iaf, json.dumps(config)),
        )
        sid = int(cur.lastrowid)
        out = self.root / pid / f"session-{sid:04d}"
        out.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(out / "eeg.npz", eeg=np.asarray(eeg, dtype=np.float32), fs=fs)
        (out / "events.json").write_text(json.dumps(events, indent=1))
        self.db.execute("UPDATE sessions SET data_dir = ? WHERE session_id = ?", (str(out), sid))
        self.db.commit()
        return sid

    def sessions(self, pid: str) -> list[tuple]:
        return self.db.execute(
            "SELECT session_id, started_at, iaf_hz, data_dir FROM sessions WHERE pid = ? ORDER BY session_id", (pid,)
        ).fetchall()

    def delete_participant(self, pid: str) -> None:
        """Right to erasure: removes the participant, their sessions and data files."""
        import shutil

        self.db.execute("DELETE FROM participants WHERE pid = ?", (pid,))
        self.db.commit()
        shutil.rmtree(self.root / pid, ignore_errors=True)
