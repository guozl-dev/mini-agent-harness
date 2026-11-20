"""Phase 1 tests: run/step/tool_call persistence."""

from __future__ import annotations

from mini_harness.core.state import StateStore


def _message(role: str, content: str) -> dict[str, str]:
    return {"role": role, "content": content}


def test_create_run_and_read_back() -> None:
    store = StateStore()
    run_id = store.create_run("整理本周测试报告")

    record = store.get_run(run_id)

    assert record.id == run_id
    assert record.task == "整理本周测试报告"
    assert record.status == "running"
    assert record.steps == []
    assert record.tool_calls == []


def test_step_snapshots_and_tool_calls_are_ordered() -> None:
    store = StateStore()
    run_id = store.create_run("demo")

    store.save_step(run_id, 1, "planning", [_message("system", "s"), _message("user", "u")])
    store.save_step(run_id, 2, "observing", [_message("system", "s"), _message("user", "u")])
    store.record_tool_call(
        run_id, 1, "echo", {"text": "hi"}, ok=True, output="hi"
    )
    store.record_tool_call(
        run_id, 2, "boom", {}, ok=False, error="ValueError: boom"
    )
    store.finish_run(run_id, "finished", "done")

    record = store.get_run(run_id)

    assert [step.step_no for step in record.steps] == [1, 2]
    assert record.steps[1].state == "observing"
    assert record.tool_calls[0].name == "echo"
    assert record.tool_calls[0].ok is True
    assert record.tool_calls[1].error == "ValueError: boom"
    assert record.status == "finished"
    assert record.result == "done"


def test_persisted_store_survives_reopen(tmp_path) -> None:
    db_path = tmp_path / "harness.sqlite"
    store = StateStore(db_path)
    run_id = store.create_run("persist me")
    store.save_step(run_id, 1, "finished", [_message("assistant", "ok")])
    store.close()

    reopened = StateStore(db_path)
    record = reopened.get_run(run_id)

    assert record.task == "persist me"
    assert record.steps[0].messages[0]["content"] == "ok"
