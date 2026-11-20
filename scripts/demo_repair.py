"""Offline demo: repair a buggy project end to end.

Runs with a scripted FakeProvider so it costs nothing and is deterministic —
swap in OpenAICompatibleProvider to use a real model against your own project.

Usage:
    python scripts/demo_repair.py
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mini_harness.core.repair import RepairLoop  # noqa: E402
from mini_harness.llm.provider import FakeProvider  # noqa: E402

FIXED = '''"""Calculator with the three defects repaired."""


def add(a: float, b: float) -> float:
    return a + b


def divide(a: float, b: float) -> float:
    if b == 0:
        raise ValueError("division by zero")
    return a / b


def average(values: list[float]) -> float:
    if not values:
        raise ValueError("empty sequence")
    return round(sum(values) / len(values), 2)
'''


def main() -> int:
    workspace = Path(tempfile.mkdtemp(prefix="repair-demo-")) / "buggy_project"
    shutil.copytree(ROOT / "examples" / "buggy_project", workspace)

    scripted = json.dumps({"files": [{"path": "buggy_calc.py", "content": FIXED}]})
    loop = RepairLoop(FakeProvider([scripted]), workspace, max_attempts=2)
    result = loop.run()

    print(f"status : {result.status}")
    for attempt in result.attempts:
        print(
            f"attempt {attempt.attempt}: failed={attempt.result.failed} "
            f"changed={attempt.files_changed}"
        )
    print(f"final  : passed={result.final.passed} failed={result.final.failed}")
    return 0 if result.status == "finished" else 1


if __name__ == "__main__":
    raise SystemExit(main())
