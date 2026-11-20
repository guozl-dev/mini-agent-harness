"""SQLite-backed run/step/tool_call persistence.

Design notes:
- Every step saves a full message snapshot, which makes crash recovery a plain
  "reload the last snapshot and continue" (no event replay needed).
- Three tables mirror the three audit questions: what run, which step, what tool.
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

RunStatus = Literal["running", "finished", "failed"]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id          TEXT PRIMARY KEY,
    task        TEXT NOT NULL,
    status      TEXT NOT NULL,
    result      TEXT,
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS steps (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      TEXT NOT NULL,
    step_no     INTEGER NOT NULL,
    state       TEXT NOT NULL,
    messages    TEXT NOT NULL,
    created_at  REAL NOT NULL,
    UNIQUE (run_id, step_no)
);
CREATE TABLE IF NOT EXISTS tool_calls (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      TEXT NOT NULL,
    step_no     INTEGER NOT NULL,
    name        TEXT NOT NULL,
    arguments   TEXT NOT NULL,
    ok          INTEGER NOT NULL,
    output      TEXT,
    error       TEXT,
    created_at  REAL NOT NULL
);
"""


@dataclass
class StepRecord:
    step_no: int
    state: str
    messages: list[dict[str, Any]]


@dataclass
class ToolCallRecord:
    step_no: int
    name: str
    arguments: dict[str, Any]
    ok: bool
    output: str | None = None
    error: str | None = None


@dataclass
class RunRecord:
    id: str
    task: str
    status: RunStatus
    steps: list[StepRecord] = field(default_factory=list)
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    result: str | None = None


class StateStore:
    """Thin SQLite wrapper; ``":memory:"`` is the default for tests."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self._path = str(path)
        if self._path != ":memory:":
            Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self._path)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(_SCHEMA)
        self._db.commit()

    # -- writes ---------------------------------------------------------
    def create_run(self, task: str) -> str:
        run_id = uuid.uuid4().hex
        now = time.time()
        self._db.execute(
            "INSERT INTO runs (id, task, status, created_at, updated_at) VALUES (?,?,?,?,?)",
            (run_id, task, "running", now, now),
        )
        self._db.commit()
        return run_id

    def save_step(
        self, run_id: str, step_no: int, state: str, messages: list[dict[str, Any]]
    ) -> None:
        now = time.time()
        self._db.execute(
            "INSERT OR REPLACE INTO steps (run_id, step_no, state, messages, created_at)"
            " VALUES (?,?,?,?,?)",
            (run_id, step_no, state, json.dumps(messages, ensure_ascii=False), now),
        )
        self._db.execute("UPDATE runs SET updated_at=? WHERE id=?", (now, run_id))
        self._db.commit()

    def record_tool_call(
        self,
        run_id: str,
        step_no: int,
        name: str,
        arguments: dict[str, Any],
        *,
        ok: bool,
        output: str | None = None,
        error: str | None = None,
    ) -> None:
        self._db.execute(
            "INSERT INTO tool_calls (run_id, step_no, name, arguments, ok, output, error,"
            " created_at) VALUES (?,?,?,?,?,?,?,?)",
            (
                run_id,
                step_no,
                name,
                json.dumps(arguments, ensure_ascii=False),
                int(ok),
                output,
                error,
                time.time(),
            ),
        )
        self._db.commit()

    def finish_run(self, run_id: str, status: RunStatus, result: str | None = None) -> None:
        self._db.execute(
            "UPDATE runs SET status=?, result=?, updated_at=? WHERE id=?",
            (status, result, time.time(), run_id),
        )
        self._db.commit()

    # -- reads ----------------------------------------------------------
    def get_run(self, run_id: str) -> RunRecord:
        row = self._db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(f"unknown run: {run_id}")
        steps = [
            StepRecord(step_no=r["step_no"], state=r["state"], messages=json.loads(r["messages"]))
            for r in self._db.execute(
                "SELECT * FROM steps WHERE run_id=? ORDER BY step_no", (run_id,)
            )
        ]
        calls = [
            ToolCallRecord(
                step_no=r["step_no"],
                name=r["name"],
                arguments=json.loads(r["arguments"]),
                ok=bool(r["ok"]),
                output=r["output"],
                error=r["error"],
            )
            for r in self._db.execute(
                "SELECT * FROM tool_calls WHERE run_id=? ORDER BY id", (run_id,)
            )
        ]
        return RunRecord(
            id=row["id"],
            task=row["task"],
            status=row["status"],
            steps=steps,
            tool_calls=calls,
            result=row["result"],
        )

    def close(self) -> None:
        self._db.close()
