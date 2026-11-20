"""Layered memory: working (in-context) + episodic (session log) + long-term (facts).

Design notes:
- **Working memory** is the live message window and is owned by ``ContextManager``;
  this module never duplicates it.
- **Episodic memory** stores per-session summaries in SQLite; consolidation turns
  them into long-term facts and marks them done, which makes the job idempotent.
- **Long-term memory** stores facts with ``key`` + ``confidence`` + ``source``。
  Conflicts on the same key are **not overwritten silently** — the new fact is
  stored with ``status='pending'`` and a ``conflict_of`` pointer for review.
- Recall is keyword/bigram overlap + confidence; swap in a vector index later
  without changing the public API.
"""

from __future__ import annotations

import json
import re
import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS facts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    text          TEXT NOT NULL,
    key           TEXT,
    source        TEXT NOT NULL DEFAULT 'manual',
    confidence    REAL NOT NULL DEFAULT 0.8,
    status        TEXT NOT NULL DEFAULT 'active',
    hits          INTEGER NOT NULL DEFAULT 0,
    conflict_of   INTEGER,
    created_at    REAL NOT NULL,
    last_used_at  REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS episodes (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id     TEXT NOT NULL,
    content        TEXT NOT NULL,
    created_at     REAL NOT NULL,
    consolidated   INTEGER NOT NULL DEFAULT 0
);
"""

_SIMILARITY_DEDUPE = 0.85


@dataclass
class Fact:
    id: int
    text: str
    key: str | None
    source: str
    confidence: float
    status: str
    hits: int


def _bigrams(text: str) -> set[str]:
    cleaned = re.sub(r"[\s\W_]+", "", text.lower())
    return {cleaned[i : i + 2] for i in range(len(cleaned) - 1)} or {cleaned}


def _similarity(left: str, right: str) -> float:
    a, b = _bigrams(left), _bigrams(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


class MemoryStore:
    def __init__(self, path: str | Path = ":memory:") -> None:
        self._path = str(path)
        if self._path != ":memory:":
            Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self._path)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(_SCHEMA)
        self._db.commit()

    # -- episodic -------------------------------------------------------
    def add_episode(self, session_id: str, content: str) -> int:
        cursor = self._db.execute(
            "INSERT INTO episodes (session_id, content, created_at) VALUES (?,?,?)",
            (session_id, content, time.time()),
        )
        self._db.commit()
        return int(cursor.lastrowid or 0)

    # -- long-term ------------------------------------------------------
    def add_fact(
        self,
        text: str,
        *,
        key: str | None = None,
        source: str = "manual",
        confidence: float = 0.8,
    ) -> Fact:
        now = time.time()
        for row in self._db.execute(
            "SELECT * FROM facts WHERE status='active' AND key IS ?", (key,)
        ):
            if _similarity(row["text"], text) >= _SIMILARITY_DEDUPE:
                return self._to_fact(row)
            if key is not None:
                # Same key, different value: keep the old fact, park the new one.
                cursor = self._db.execute(
                    "INSERT INTO facts (text, key, source, confidence, status, conflict_of,"
                    " created_at, last_used_at) VALUES (?,?,?,?,'pending',?,?,?)",
                    (text, key, source, confidence, row["id"], now, now),
                )
                self._db.commit()
                return self._get(int(cursor.lastrowid or 0))

        cursor = self._db.execute(
            "INSERT INTO facts (text, key, source, confidence, status, created_at,"
            " last_used_at) VALUES (?,?,?,?,'active',?,?)",
            (text, key, source, confidence, now, now),
        )
        self._db.commit()
        return self._get(int(cursor.lastrowid or 0))

    def recall(self, query: str, *, limit: int = 5, min_score: float = 0.1) -> list[Fact]:
        scored: list[tuple[float, sqlite3.Row]] = []
        for row in self._db.execute("SELECT * FROM facts WHERE status='active'"):
            score = _similarity(query, row["text"]) + (0.2 if row["key"] else 0.0)
            if score >= min_score:
                scored.append((score * float(row["confidence"]), row))
        scored.sort(key=lambda item: (item[0], item[1]["hits"]), reverse=True)
        picked = [row for _, row in scored[:limit]]
        now = time.time()
        for row in picked:
            self._db.execute(
                "UPDATE facts SET hits=hits+1, last_used_at=? WHERE id=?", (now, row["id"])
            )
        self._db.commit()
        return [self._get(int(row["id"])) for row in picked]

    def forget(
        self, *, max_facts: int = 50, ttl_days: float = 30.0, now: float | None = None
    ) -> int:
        """Archive stale facts, then trim the active set to ``max_facts``."""
        current = time.time() if now is None else now
        cutoff = current - ttl_days * 86400
        archived = self._db.execute(
            "UPDATE facts SET status='archived' WHERE status='active' AND last_used_at < ?",
            (cutoff,),
        ).rowcount
        active = list(
            self._db.execute(
                "SELECT id FROM facts WHERE status='active'"
                " ORDER BY (hits + confidence) DESC, last_used_at DESC"
            )
        )
        excess = max(len(active) - max_facts, 0)
        for row in active[len(active) - excess :]:
            self._db.execute("UPDATE facts SET status='archived' WHERE id=?", (row["id"],))
        self._db.commit()
        return archived + excess

    def pending_conflicts(self) -> list[Fact]:
        return [
            self._to_fact(row)
            for row in self._db.execute("SELECT * FROM facts WHERE status='pending' ORDER BY id")
        ]

    def list_facts(self, *, status: str = "active") -> list[Fact]:
        return [
            self._to_fact(row)
            for row in self._db.execute(
                "SELECT * FROM facts WHERE status=? ORDER BY id", (status,)
            )
        ]

    # -- consolidation --------------------------------------------------
    def consolidate(self, session_id: str, summarizer: Callable[[str], str]) -> int:
        """Turn unconsolidated episodes into facts. Idempotent by design."""
        rows = list(
            self._db.execute(
                "SELECT * FROM episodes WHERE session_id=? AND consolidated=0 ORDER BY id",
                (session_id,),
            )
        )
        if not rows:
            return 0
        transcript = "\n".join(f"- {row['content']}" for row in rows)
        raw = summarizer(
            "从以下会话记录中提炼稳定的用户事实，返回 JSON 数组："
            '[{"text": "...", "key": "可选唯一键"}]\n\n' + transcript
        )
        known_ids = {row["id"] for row in self._db.execute("SELECT id FROM facts")}
        written = 0
        for item in self._parse_facts(raw):
            text = item.get("text")
            if not isinstance(text, str) or not text.strip():
                continue
            fact = self.add_fact(
                text.strip(),
                key=item.get("key") if isinstance(item.get("key"), str) else None,
                source=f"episode:{session_id}",
                confidence=0.7,
            )
            if fact.id not in known_ids:
                known_ids.add(fact.id)
                written += 1
        self._db.executemany(
            "UPDATE episodes SET consolidated=1 WHERE id=?", [(row["id"],) for row in rows]
        )
        self._db.commit()
        return written

    # -- helpers --------------------------------------------------------
    @staticmethod
    def _parse_facts(raw: str) -> list[dict[str, Any]]:
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            text = text.split("\n", 1)[1] if "\n" in text else text
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return []
        if not isinstance(payload, list):
            return []
        return [item for item in payload if isinstance(item, dict)]

    def context_block(self, query: str, *, limit: int = 5) -> str:
        facts = self.recall(query, limit=limit)
        if not facts:
            return ""
        lines = "\n".join(f"- {fact.text}" for fact in facts)
        return f"[记忆] 已知的稳定事实：\n{lines}"

    def _get(self, fact_id: int) -> Fact:
        row = self._db.execute("SELECT * FROM facts WHERE id=?", (fact_id,)).fetchone()
        if row is None:
            raise KeyError(fact_id)
        return self._to_fact(row)

    @staticmethod
    def _to_fact(row: sqlite3.Row) -> Fact:
        return Fact(
            id=row["id"],
            text=row["text"],
            key=row["key"],
            source=row["source"],
            confidence=float(row["confidence"]),
            status=row["status"],
            hits=int(row["hits"]),
        )

    def close(self) -> None:
        self._db.close()

    def __enter__(self) -> MemoryStore:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def __del__(self) -> None:  # pragma: no cover - safety net for tests/scripts
        try:
            self._db.close()
        except Exception:  # noqa: BLE001 - already closed or never opened
            pass
