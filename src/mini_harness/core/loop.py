"""The agent loop: a small explicit state machine with persistence.

States: PLANNING -> ACTING -> OBSERVING -> (PLANNING | FINISHED | FAILED)

- PLANNING: assemble context, call the model.
- ACTING:   execute requested tools through the registry.
- OBSERVING: append tool observations, persist a step snapshot.
- Exit:     no tool calls -> FINISHED; step budget exhausted -> FAILED.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ..llm.provider import LLMProvider
from ..llm.types import Message
from .context import ContextManager
from .memory import MemoryStore
from .state import RunRecord, StateStore
from .tools import ToolRegistry


class LoopState(StrEnum):
    PLANNING = "planning"
    ACTING = "acting"
    OBSERVING = "observing"
    FINISHED = "finished"
    FAILED = "failed"


@dataclass
class RunResult:
    run_id: str
    status: str
    steps: int
    content: str


class AgentLoop:
    def __init__(
        self,
        provider: LLMProvider,
        *,
        tools: ToolRegistry | None = None,
        store: StateStore | None = None,
        context: ContextManager | None = None,
        memory: MemoryStore | None = None,
        max_steps: int = 8,
        system_prompt: str = "You are a careful agent. Use tools when needed.",
    ) -> None:
        if max_steps < 1:
            raise ValueError("max_steps must be >= 1")
        self.provider = provider
        self.tools = tools
        self.store = store or StateStore()
        self.context = context or ContextManager()
        self.memory = memory
        self.max_steps = max_steps
        self.system_prompt = system_prompt
        self.state: LoopState = LoopState.PLANNING

    # -- public ---------------------------------------------------------
    def run(self, task: str) -> RunResult:
        run_id = self.store.create_run(task)
        messages = [Message(role="system", content=self.system_prompt)]
        if self.memory is not None:
            block = self.memory.context_block(task)
            if block:
                messages.append(Message(role="system", content=block))
        messages.append(Message(role="user", content=task))
        result = self._drive(run_id, messages, start_step=1)
        if self.memory is not None and result.status == "finished":
            self.memory.add_episode(run_id, f"task: {task}\nresult: {result.content}")
        return result

    def resume(self, run_id: str) -> RunResult:
        record = self.store.get_run(run_id)
        if record.status != "running":
            return RunResult(run_id, record.status, len(record.steps), record.result or "")
        last = record.steps[-1]
        messages = [Message(**payload) for payload in last.messages]
        return self._drive(run_id, messages, start_step=last.step_no + 1)

    # -- internals ------------------------------------------------------
    def _drive(self, run_id: str, messages: list[Message], *, start_step: int) -> RunResult:
        for step_no in range(start_step, self.max_steps + 1):
            self.state = LoopState.PLANNING
            prepared = self.context.assemble(messages)
            specs = self.tools.specs() if self.tools else None
            response = self.provider.complete(prepared, specs)
            messages.append(Message(role="assistant", content=response.content))

            if not response.has_tool_calls:
                self.state = LoopState.FINISHED
                self._persist(run_id, step_no, messages)
                self.store.finish_run(run_id, "finished", response.content)
                return RunResult(run_id, "finished", step_no, response.content)

            self.state = LoopState.ACTING
            observations: list[Message] = []
            assert self.tools is not None  # has_tool_calls implies a registry
            for call in response.tool_calls:
                observation = self.tools.execute(call)
                self.store.record_tool_call(
                    run_id,
                    step_no,
                    call.name,
                    call.arguments,
                    ok=observation.ok,
                    output=observation.output or None,
                    error=observation.error or None,
                )
                observations.append(
                    Message(
                        role="tool",
                        content=observation.output if observation.ok else observation.error,
                        name=call.name,
                        tool_call_id=call.id,
                    )
                )
            self.state = LoopState.OBSERVING
            messages.extend(observations)
            self._persist(run_id, step_no, messages)

        self.state = LoopState.FAILED
        self.store.finish_run(run_id, "failed", "max_steps_exceeded")
        return RunResult(run_id, "failed", self.max_steps, "max_steps_exceeded")

    def _persist(self, run_id: str, step_no: int, messages: list[Message]) -> None:
        snapshot = [m.model_dump(exclude_none=True) for m in messages]
        self.store.save_step(run_id, step_no, self.state.value, snapshot)

    def history(self, run_id: str) -> RunRecord:
        return self.store.get_run(run_id)
