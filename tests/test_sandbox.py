"""Phase 2 tests: sandbox execution and machine-readable failure parsing."""

from __future__ import annotations

from mini_harness.core.sandbox import SandboxRunner

BUGGY = "def add(a, b):\n    return a - b\n"
FIXED = "def add(a, b):\n    return a + b\n"
TEST = "from calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n"


def _project(tmp_path):
    (tmp_path / "calc.py").write_text(BUGGY, encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_calc.py").write_text(TEST, encoding="utf-8")
    return tmp_path


def test_sandbox_reports_failures_with_messages(tmp_path) -> None:
    project = _project(tmp_path)

    result = SandboxRunner(project).run()

    assert result.failed == 1
    assert result.all_green is False
    assert result.failures[0].test_id.endswith("test_add")
    assert "assert" in result.failures[0].message.lower()


def test_sandbox_reports_green_after_fix(tmp_path) -> None:
    project = _project(tmp_path)
    (project / "calc.py").write_text(FIXED, encoding="utf-8")

    result = SandboxRunner(project).run()

    assert result.all_green is True
    assert result.passed == 1
    assert result.failures == []


def test_sandbox_does_not_mutate_the_source_project(tmp_path) -> None:
    project = _project(tmp_path)
    before = (project / "calc.py").read_text(encoding="utf-8")

    SandboxRunner(project).run()

    assert (project / "calc.py").read_text(encoding="utf-8") == before
