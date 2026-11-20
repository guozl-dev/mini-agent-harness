"""Phase 2 tests: repair loop convergence, guard rails and failure modes."""

from __future__ import annotations

import json

from mini_harness.core.repair import RepairLoop
from mini_harness.core.sandbox import SandboxRunner
from mini_harness.llm.provider import FakeProvider

BUGGY = "def add(a, b):\n    return a - b\n"
FIXED = "def add(a, b):\n    return a + b\n"
TEST = "from calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n"


def _project(tmp_path):
    (tmp_path / "calc.py").write_text(BUGGY, encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_calc.py").write_text(TEST, encoding="utf-8")
    return tmp_path


def _patch(path: str, content: str) -> str:
    return json.dumps({"files": [{"path": path, "content": content}]})


def test_repair_converges_and_records_attempt(tmp_path) -> None:
    project = _project(tmp_path)
    loop = RepairLoop(FakeProvider([_patch("calc.py", FIXED)]), project, max_attempts=2)

    result = loop.run()

    assert result.status == "finished"
    assert len(result.attempts) == 1
    assert result.attempts[0].files_changed == ["calc.py"]
    assert result.final.all_green is True
    assert (project / "calc.py").read_text(encoding="utf-8") == FIXED


def test_repair_refuses_to_touch_test_files(tmp_path) -> None:
    project = _project(tmp_path)
    evil = _patch("tests/test_calc.py", "def test_add():\n    assert True\n")
    loop = RepairLoop(FakeProvider([evil]), project, max_attempts=1)

    result = loop.run()

    assert result.status == "failed"
    assert result.attempts[0].files_changed == []
    assert (project / "tests" / "test_calc.py").read_text(encoding="utf-8") == TEST


def test_repair_refuses_path_traversal(tmp_path) -> None:
    project = _project(tmp_path)
    outside = tmp_path.parent / "outside.py"
    loop = RepairLoop(
        FakeProvider([_patch("../outside.py", "print('pwned')\n")]), project, max_attempts=1
    )

    result = loop.run()

    assert result.status == "failed"
    assert outside.exists() is False


def test_repair_survives_invalid_model_output(tmp_path) -> None:
    project = _project(tmp_path)
    loop = RepairLoop(FakeProvider(["sorry, no json here"]), project, max_attempts=2)

    result = loop.run()

    assert result.status == "failed"
    assert result.reason == "max_attempts_exceeded"
    assert len(result.attempts) == 2


def test_already_green_project_short_circuits(tmp_path) -> None:
    project = _project(tmp_path)
    (project / "calc.py").write_text(FIXED, encoding="utf-8")
    provider = FakeProvider(["should never be called"])
    loop = RepairLoop(provider, project, max_attempts=2)

    result = loop.run()

    assert result.status == "finished"
    assert result.reason == "already_green"
    assert result.attempts == []
    assert provider.calls == []


def test_sandbox_reuse_with_custom_runner(tmp_path) -> None:
    project = _project(tmp_path)
    runner = SandboxRunner(project)
    loop = RepairLoop(
        FakeProvider([_patch("calc.py", FIXED)]), project, max_attempts=1, sandbox=runner
    )

    result = loop.run()

    assert result.status == "finished"
