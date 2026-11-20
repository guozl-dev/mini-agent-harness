"""Tool registry with allowlist, path guard, timeout and error-to-observation.

Key rule: **exceptions never escape**. A failing tool becomes an observation the
model can react to, instead of crashing the loop.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass
from typing import Any

from ..llm.types import ToolCall, ToolSpec

ToolFn = Callable[..., str]
Guard = Callable[[ToolCall], None]


@dataclass
class ToolObservation:
    name: str
    ok: bool
    output: str = ""
    error: str = ""
    duration_ms: int = 0


class ToolRegistry:
    def __init__(self, *, timeout_s: float = 5.0, guard: Guard | None = None) -> None:
        self.timeout_s = timeout_s
        self.guard = guard
        self._tools: dict[str, tuple[ToolSpec, ToolFn, bool]] = {}

    def register(self, spec: ToolSpec, fn: ToolFn, *, allowed: bool = True) -> None:
        if spec.name in self._tools:
            raise ValueError(f"tool already registered: {spec.name}")
        self._tools[spec.name] = (spec, fn, allowed)

    def specs(self, *, only_allowed: bool = True) -> list[ToolSpec]:
        return [
            spec
            for spec, _, allowed in self._tools.values()
            if allowed or not only_allowed
        ]

    def execute(self, call: ToolCall) -> ToolObservation:
        started = time.perf_counter()
        entry = self._tools.get(call.name)
        if entry is None:
            return self._fail(call, "tool_not_found", started)
        spec, fn, allowed = entry
        if not allowed:
            return self._fail(call, "tool_not_allowed", started)
        if self.guard is not None:
            try:
                self.guard(call)
            except Exception as exc:  # noqa: BLE001 - surfaced as observation
                return self._fail(call, f"guard_rejected: {exc}", started)

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(fn, **call.arguments)
            try:
                output = future.result(timeout=self.timeout_s)
            except FutureTimeout:
                return self._fail(call, f"timeout after {self.timeout_s}s", started)
            except TypeError as exc:
                return self._fail(call, f"bad_arguments: {exc}", started)
            except Exception as exc:  # noqa: BLE001 - surfaced as observation
                return self._fail(call, f"{type(exc).__name__}: {exc}", started)

        return ToolObservation(
            name=call.name,
            ok=True,
            output=str(output),
            duration_ms=int((time.perf_counter() - started) * 1000),
        )

    def _fail(self, call: ToolCall, error: str, started: float) -> ToolObservation:
        return ToolObservation(
            name=call.name,
            ok=False,
            error=error,
            duration_ms=int((time.perf_counter() - started) * 1000),
        )

    @staticmethod
    def path_guard(root: str) -> Guard:
        """Reject calls whose string arguments escape ``root`` (防越界写)."""
        from pathlib import Path

        base = Path(root).resolve()

        def _guard(call: ToolCall) -> None:
            for value in call.arguments.values():
                if not isinstance(value, str):
                    continue
                candidate = Path(value)
                if ("/" in value or "\\" in value) and not candidate.is_absolute():
                    resolved = (base / candidate).resolve()
                    if base not in resolved.parents and resolved != base:
                        raise PermissionError(f"path escapes workspace: {value}")

        return _guard


def _unused(_: Any) -> None:  # pragma: no cover - keeps typing import meaningful
    return None
