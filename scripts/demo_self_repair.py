"""Self-repair demo: inject a bug into a copy of THIS repo, then let the harness fix it.

This mirrors the job description's "your own module, AI runs the tests, reads the
feedback, patches the code and converges — demonstrable live".

Usage:
    python scripts/demo_self_repair.py                     # scripted provider, free
    python scripts/demo_self_repair.py --provider env      # real model
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

BUG_PATH = "src/mini_harness/core/evaluation.py"
HEALTHY_LINE = '"hit_rate": hits / total,'
BROKEN_LINE = '"hit_rate": hits / (total + 1),'
IGNORE = shutil.ignore_patterns(
    ".git", ".venv", "venv", "__pycache__", "*.pyc", ".pytest_cache", "*.sqlite", "*.egg-info"
)


def build_provider(kind: str, healthy_source: str):
    if kind == "env":
        return OpenAICompatibleProvider.from_env()
    scripted = json.dumps({"files": [{"path": BUG_PATH, "content": healthy_source}]})
    return FakeProvider([scripted])


def main() -> int:
    parser = argparse.ArgumentParser(description="inject a bug into a repo copy and repair it")
    parser.add_argument("--provider", choices=["fake", "env"], default="fake")
    parser.add_argument("--max-attempts", type=int, default=3)
    args = parser.parse_args()

    healthy_source = (ROOT / BUG_PATH).read_text(encoding="utf-8")
    if HEALTHY_LINE not in healthy_source:
        print(f"[error] anchor line not found in {BUG_PATH}", file=sys.stderr)
        return 2

    workspace = Path(tempfile.mkdtemp(prefix="self-repair-")) / ROOT.name
    shutil.copytree(ROOT, workspace, ignore=IGNORE)

    broken_source = healthy_source.replace(HEALTHY_LINE, BROKEN_LINE)
    (workspace / BUG_PATH).write_text(broken_source, encoding="utf-8")
    print(f"injected bug: {BUG_PATH} (hit_rate denominator off by one)")

    try:
        provider = build_provider(args.provider, healthy_source)
    except ProviderError as exc:
        print(f"[config error] {exc}", file=sys.stderr)
        return 2

    loop = RepairLoop(provider, workspace, max_attempts=args.max_attempts)
    result = loop.run()

    repaired = (workspace / BUG_PATH).read_text(encoding="utf-8") == healthy_source
    print(f"provider   : {args.provider}")
    print(f"status     : {result.status}")
    for attempt in result.attempts:
        print(
            f"attempt {attempt.attempt}: failed={attempt.result.failed} "
            f"changed={attempt.files_changed}"
        )
    print(f"final      : passed={result.final.passed} failed={result.final.failed}")
    print(f"restored   : {repaired}")
    return 0 if result.status == "finished" and repaired else 1


if __name__ == "__main__":
    raise SystemExit(main())
