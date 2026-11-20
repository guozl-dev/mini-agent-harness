"""Offline demo: repair a buggy project end to end.

Default uses a scripted FakeProvider (zero cost, deterministic). Pass
``--provider env`` to let a real model do the repair (needs LLM_BASE_URL /
LLM_API_KEY / LLM_MODEL exported).

Usage:
    python scripts/demo_repair.py
    python scripts/demo_repair.py --provider env --target examples/buggy_project
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mini_harness.core.repair import RepairLoop  # noqa: E402
from mini_harness.llm.provider import (  # noqa: E402
    FakeProvider,
    OpenAICompatibleProvider,
    ProviderError,
)

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


def build_provider(kind: str):
    if kind == "env":
        return OpenAICompatibleProvider.from_env()
    scripted = json.dumps({"files": [{"path": "buggy_calc.py", "content": FIXED}]})
    return FakeProvider([scripted])


def main() -> int:
    parser = argparse.ArgumentParser(description="repair a buggy project until tests are green")
    parser.add_argument("--provider", choices=["fake", "env"], default="fake")
    parser.add_argument("--target", default=str(ROOT / "examples" / "buggy_project"))
    parser.add_argument("--max-attempts", type=int, default=2)
    args = parser.parse_args()

    target = Path(args.target).resolve()
    if not target.is_dir():
        print(f"[error] target not found: {target}", file=sys.stderr)
        return 2

    workspace = Path(tempfile.mkdtemp(prefix="repair-demo-")) / target.name
    shutil.copytree(target, workspace)

    try:
        provider = build_provider(args.provider)
    except ProviderError as exc:
        print(f"[config error] {exc}", file=sys.stderr)
        return 2

    loop = RepairLoop(provider, workspace, max_attempts=args.max_attempts)
    result = loop.run()

    print(f"provider: {args.provider}")
    print(f"status  : {result.status}")
    for attempt in result.attempts:
        print(
            f"attempt {attempt.attempt}: failed={attempt.result.failed} "
            f"changed={attempt.files_changed}"
        )
    print(f"final   : passed={result.final.passed} failed={result.final.failed}")
    return 0 if result.status == "finished" else 1


if __name__ == "__main__":
    raise SystemExit(main())
