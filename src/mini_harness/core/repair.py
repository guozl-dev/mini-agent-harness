"""Repair loop: run tests -> ask the model for a structured patch -> apply -> rerun.

Safety rules:
- The model may only touch files listed in the workspace; test files are protected.
- Patches are full-file replacements described as JSON, which avoids fragile
  diff parsing and is easy to validate before writing.
- Every attempt is recorded so a demo can show the convergence trail.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..llm.provider import LLMProvider
from ..llm.types import Message
from .sandbox import SandboxRunner, SuiteResult

_SYSTEM_PROMPT = (
    "You are a test-driven repair agent. "
    "Analyse pytest failures and return ONLY JSON of the form "
    '{"files": [{"path": "relative/path.py", "content": "full file content"}]}. '
    "Never modify files under tests/. Always return complete file contents."
)


@dataclass
class RepairAttempt:
    attempt: int
    result: SuiteResult
    files_changed: list[str] = field(default_factory=list)


@dataclass
class RepairResult:
    status: str
    attempts: list[RepairAttempt]
    final: SuiteResult
    reason: str = ""


class RepairLoop:
    def __init__(
        self,
        provider: LLMProvider,
        project_dir: str | Path,
        *,
        max_attempts: int = 3,
        protected: Sequence[str] = ("tests",),
        sandbox: SandboxRunner | None = None,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        self.provider = provider
        self.project_dir = Path(project_dir).resolve()
        self.max_attempts = max_attempts
        self.protected = tuple(protected)
        self.sandbox = sandbox or SandboxRunner(self.project_dir)

    # -- public ---------------------------------------------------------
    def run(self) -> RepairResult:
        result = self.sandbox.run()
        attempts: list[RepairAttempt] = []
        if result.all_green:
            return RepairResult("finished", attempts, result, reason="already_green")

        for attempt_no in range(1, self.max_attempts + 1):
            response = self.provider.complete(self._prompt(result))
            try:
                patch = self._parse(response.content)
            except ValueError as exc:
                attempts.append(RepairAttempt(attempt_no, result, []))
                result = SuiteResult(
                    failed=result.failed,
                    errors=result.errors,
                    failures=result.failures,
                    output=f"{result.output}\ninvalid_patch: {exc}",
                )
                continue

            changed = self._apply(patch)
            result = self.sandbox.run()
            attempts.append(RepairAttempt(attempt_no, result, changed))
            if result.all_green:
                return RepairResult("finished", attempts, result)

        return RepairResult("failed", attempts, result, reason="max_attempts_exceeded")

    # -- internals ------------------------------------------------------
    def _prompt(self, result: SuiteResult) -> list[Message]:
        failures = "\n".join(f"- {f.test_id}: {f.message}" for f in result.failures[:10])
        files = sorted(
            str(path.relative_to(self.project_dir))
            for path in self.project_dir.rglob("*.py")
            if not any(part in self.protected for part in path.relative_to(self.project_dir).parts)
        )
        user = (
            f"Project: {self.project_dir.name}\n"
            f"Editable files: {', '.join(files)}\n\n"
            f"Failing tests ({len(result.failures)}):\n{failures}\n\n"
            "Return the corrected files as JSON."
        )
        return [Message(role="system", content=_SYSTEM_PROMPT), Message(role="user", content=user)]

    @staticmethod
    def _parse(content: str) -> dict[str, Any]:
        text = content.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            text = text.split("\n", 1)[1] if "\n" in text else text
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"not valid JSON: {exc}") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("files"), list):
            raise ValueError("missing files list")
        return payload

    def _apply(self, patch: dict[str, Any]) -> list[str]:
        changed: list[str] = []
        for entry in patch["files"]:
            if not isinstance(entry, dict):
                continue
            raw_path, content = entry.get("path"), entry.get("content")
            if not isinstance(raw_path, str) or not isinstance(content, str):
                continue
            if not self._is_safe(raw_path):
                continue
            target = (self.project_dir / raw_path).resolve()
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            changed.append(raw_path)
        return changed

    def _is_safe(self, raw_path: str) -> bool:
        candidate = Path(raw_path)
        if candidate.is_absolute() or ".." in candidate.parts:
            return False
        if any(part in self.protected for part in candidate.parts):
            return False
        target = (self.project_dir / candidate).resolve()
        return self.project_dir in target.parents or target == self.project_dir
