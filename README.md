# mini-agent-harness

一个**可审计、可恢复、可控**的轻量 Agent 运行时（Harness），从零实现，不依赖 LangChain / LangGraph 等编排框架。

> 目标：让 Agent 的四个核心问题都有明确答案——**loop 怎么转、状态放哪、上下文怎么裁、工具边界画在哪**。

## 状态

| 阶段 | 内容 | 状态 |
|---|---|---|
| Phase 0 | 工程底座 + LLM Provider 抽象层（重试/超时/结构化输出/fake provider） | ✅ 已完成 |
| Phase 1 | Harness 内核：任务循环状态机、SQLite 状态持久化、上下文预算裁剪、工具 allowlist | ✅ 已完成 |
| Phase 2 | AI 自闭环：pytest 沙箱 → 机器可读反馈 → 改码 → 重跑直到全绿（可演示） | ⬜ 计划中 |
| Phase 3 | 分层记忆：工作/情景/长期 + 离线巩固 + 遗忘与污染防护 | ⬜ 计划中 |
| Phase 4 | 规划式召回（超越向量 top-k）+ 工程纪律（e2e/mock/覆盖率门槛/CI 门禁）+ v0.1.0 | ⬜ 计划中 |

## 设计取舍（为什么不用现成框架）

1. **可控性**：框架封装了 loop 与状态，出问题时无法定位是模型、编排还是上下文的问题；本项目的每一层都可单测。
2. **可恢复**：状态显式落 SQLite（run/step/tool_call 三级），进程崩溃可从断点续跑。
3. **可治理**：工具走 allowlist + 超时 + 越界写拦截，异常一律转为"观察结果"回传模型，不让异常击穿 loop。
4. **可测试**：LLM 接口化 + FakeProvider，CI 零成本、确定性、可离线。

## 快速开始

```bash
uv venv && uv pip install -e ".[dev]"   # 或 pip install -e ".[dev]"
cp .env.example .env                    # 填入模型 API Key（可选）
pytest
```

## 目录结构

```
src/mini_harness/
  llm/
    types.py       # Message / ToolSpec / ChatResponse 等数据模型（pydantic）
    provider.py    # Provider 抽象 + OpenAI 兼容实现（重试/超时）+ FakeProvider
  core/
    loop.py        # AgentLoop 状态机：PLANNING→ACTING→OBSERVING→FINISHED/FAILED
    state.py       # SQLite 三级持久化：runs / steps / tool_calls（支持断点续跑）
    context.py     # 上下文预算三级策略：externalize → summarize → hard trim
    tools.py       # 工具注册 + allowlist + 超时 + 路径越界拦截（异常转观察结果）
tests/
docs/roadmap.md    # 四阶段路线与验收标准
.github/workflows/ci.yml
```

## 最小示例

```python
from mini_harness.core.loop import AgentLoop
from mini_harness.core.state import StateStore
from mini_harness.core.tools import ToolRegistry
from mini_harness.llm.provider import FakeProvider
from mini_harness.llm.types import ToolSpec

registry = ToolRegistry(timeout_s=3)
registry.register(
    ToolSpec(name="echo", description="echo text", parameters={"type": "object"}),
    lambda text: f"echo:{text}",
)
loop = AgentLoop(FakeProvider(["hello from the harness"]), tools=registry, store=StateStore())

result = loop.run("say hello")
print(result.status, result.steps, result.content)   # finished 1 hello from the harness
print(loop.history(result.run_id).tool_calls)        # 每次工具调用都有审计记录
```

## License

MIT © 2026 guozl-dev
