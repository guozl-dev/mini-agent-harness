"""Run a target project's test suite in an isolated copy and parse machine-readable results.

Why copy: pytest discovers config/rootdir upward, so running a target inside our
repo would pick up this project's settings. A temp copy guarantees a clean
rootdir and keeps the workspace untouched by the sandbox itself.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class TestFailure:
    test_id: str
    message: str
    file: str | None = None
    line: str | None = None


@dataclass
class SuiteResult:
    passed: int = 0
    failed: int = 0
    errors: int = 0
    failures: list[TestFailure] = field(default_factory=list)
    output: str = ""

    @property
    def all_green(self) -> bool:
        return self.failed == 0 and self.errors == 0


class SandboxRunner:
    """Executes ``pytest`` for a project directory, returning structured results."""

    def __init__(
        self,
        project_dir: str | Path,
        *,
        timeout_s: float = 120.0,
        python: str | None = None,
    ) -> None:
        self.project_dir = Path(project_dir).resolve()
        self.timeout_s = timeout_s
        self.python = python or sys.executable

    def run(self) -> SuiteResult:
        if not self.project_dir.is_dir():
            raise FileNotFoundError(self.project_dir)

        workdir = Path(tempfile.mkdtemp(prefix="harness-sandbox-"))
        target = workdir / "project"
        shutil.copytree(
            self.project_dir,
            target,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"),
        )
        report = workdir / "report.xml"

        try:
            proc = subprocess.run(
                [
                    self.python,
                    "-m",
                    "pytest",
                    "-q",
                    "-p",
                    "no:cacheprovider",
                    f"--junitxml={report}",
                ],
                cwd=target,
                capture_output=True,
                text=True,
                timeout=self.timeout_s,
            )
        except subprocess.TimeoutExpired:
            return SuiteResult(errors=1, output=f"sandbox timeout after {self.timeout_s}s")

        if not report.exists():
            return SuiteResult(
                errors=1,
                output=(proc.stdout or proc.stderr or "pytest produced no report")[-2000:],
            )
        return self._parse(report, proc.stdout)

    @staticmethod
    def _parse(report: Path, stdout: str) -> SuiteResult:
        root = ET.parse(report).getroot()
        result = SuiteResult(output=(stdout or "")[-2000:])
        total = 0
        skipped = 0
        for case in root.iter("testcase"):
            total += 1
            skipped += 1 if case.find("skipped") is not None else 0
            node = case.find("failure")
            kind = "failure"
            if node is None:
                node = case.find("error")
                kind = "error"
            if node is None:
                continue
            message = (node.get("message") or (node.text or "")).strip()
            result.failures.append(
                TestFailure(
                    test_id=f"{case.get('classname', '')}::{case.get('name', '')}",
                    message=message[:600],
                    file=node.get("file") or case.get("file"),
                    line=node.get("line"),
                )
            )
            if kind == "failure":
                result.failed += 1
            else:
                result.errors += 1
        result.passed = max(total - result.failed - result.errors - skipped, 0)
        return result
