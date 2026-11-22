# mini-agent-harness

一个**可审计、可恢复、可控**的轻量 Agent 运行时（Harness），从零实现，不依赖 LangChain / LangGraph 等编排框架。

> 目标：让 Agent 的四个核心问题都有明确答案——**loop 怎么转、状态放哪、上下文怎么裁、工具边界画在哪**。

## 状态

| 阶段 | 内容 | 状态 |
|---|---|---|
| Phase 0 | 工程底座 + LLM Provider 抽象层（重试/超时/结构化输出/fake provider） | ✅ 已完成 |
| Phase 1 | Harness 内核：任务循环状态机、SQLite 状态持久化、上下文预算裁剪、工具 allowlist | ✅ 已完成 |
| Phase 2 | AI 自闭环：pytest 沙箱 → 机器可读反馈 → 改码 → 重跑直到全绿（可演示） | ✅ 已完成 |
| Phase 3 | 分层记忆：工作/情景/长期 + 离线巩固 + 遗忘与污染防护 | ✅ 已完成 |
| Phase 4 | 规划式召回（超越向量 top-k）+ 工程纪律（e2e/mock/覆盖率门槛/CI 门禁）+ v0.1.0 | ✅ 已完成 |
| Phase 5 | MCP 工具接入：stdio 服务器挂载、工具命名空间、白名单、失败隔离 | ✅ 已完成 |

## 设计取舍（为什么不用现成框架）

1. **可控性**：框架封装了 loop 与状态，出问题时无法定位是模型、编排还是上下文的问题；本项目的每一层都可单测。
2. **可恢复**：状态显式落 SQLite（run/step/tool_call 三级），进程崩溃可从断点续跑。
3. **MCP 只复用协议层**：直接用官方 `mcp` SDK 与 `mcpadapt` 的会话/同步桥，但不引入任何 agent 框架——外部工具进到 harness 后仍是 `ToolRegistry` 的普通条目，循环保持透明、可单测。
3. **可治理**：工具走 allowlist + 超时 + 越界写拦截，异常一律转为"观察结果"回传模型，不让异常击穿 loop。
4. **可测试**：LLM 接口化 + FakeProvider，CI 零成本、确定性、可离线。

## 快速开始

> 完整上手文档（环境准备、真实模型配置、常见问题）：**[docs/getting-started.md](docs/getting-started.md)**

```bash
uv venv && uv pip install -e ".[dev]"   # 或 python -m venv .venv && pip install -e ".[dev]"
python -m pytest                        # 期望 57 passed

python scripts/demo_repair.py           # 自闭环修复演示（零成本，可直接录屏）
python scripts/demo_self_repair.py      # 给本仓库注入 bug，再让 harness 修好它
python scripts/eval_retrieval.py        # 检索评测：naive vs planned
python scripts/run_agent.py             # 跑一个 agent 任务（默认 FakeProvider）
python scripts/chat.py                  # 多轮聊天模式（REPL，带记忆）
```

接真实模型：导出 `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` 后，
`python scripts/run_agent.py --provider env --task "用一句话介绍你自己"`，
或让真模型来修 bug：`python scripts/demo_self_repair.py --provider env`。

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
  mcp/
    config.py      # 解析 [[mcp.servers]]：命令、环境白名单、超时、工具白名单
    adapter.py     # MCP 工具 → ToolRegistry 条目（命名空间 / 内容展平 / isError 转观察）
    mount.py       # 逐服务器启动、失败隔离、生命周期关闭
    sandbox.py     # pytest 沙箱：临时副本执行，解析 junit-xml 为结构化失败
    repair.py      # RepairLoop：结构化补丁 → 校验（禁改测试/禁路径穿越）→ 重跑收敛
    memory.py      # 分层记忆：情景/长期 + 离线巩固（幂等）+ 遗忘 + 冲突挂起
    retrieval.py   # 朴素 top-k 基线 vs 规划式召回（子查询 + 关键词 + 合并重排）
    evaluation.py  # 检索评测：Hit@k / MRR + Markdown 报表
    textutil.py    # 共享 bigram 相似度（记忆与检索复用，避免口径分裂）
examples/buggy_project/   # 演示靶场：3 个故意写坏的缺陷
examples/mcp.example.toml # MCP 服务器配置样例
docs/mcp.md               # MCP 接入说明（配置/命名/安全/限制）
evals/                    # 检索评测语料与用例（8 篇文档 / 7 题）
scripts/demo_repair.py    # 离线演示：脚本化 provider，零成本可复现
scripts/demo_self_repair.py # 自修演示：给本仓库注入 bug，再让 harness 修复
scripts/eval_retrieval.py # 检索评测：naive 与 planned 的命中率对比
scripts/run_agent.py      # 命令行入口：--provider fake|env，跑单个任务
scripts/chat.py           # 多轮聊天 REPL：历史 + 上下文裁剪 + 记忆召回 + /remember
scripts/run_demo.bat      # Windows 双击运行修复演示
docs/getting-started.md   # 首次使用指南（环境/配置/验证/排错）
docs/release-checklist.md # 发布前脱敏与安全检查清单
.github/workflows/self-repair.yml # 手动触发：在 CI 里跑自修演示（可选真模型）
.github/workflows/secret-scan.yml # 每次 push/PR 用 gitleaks 扫描密钥泄露
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

## MCP 工具接入

把 MCP 服务器的工具接进 harness，**循环与注册表核心逻辑零改动**——适配层把每个 MCP 工具注册成普通条目。

```toml
[[mcp.servers]]
name = "filesystem"
command = "npx.cmd"                 # Windows 必须带 .cmd
args = ["-y", "@modelcontextprotocol/server-filesystem", "E:/work"]
allowed_tools = ["read_file", "list_directory"]
connect_timeout_s = 60
call_timeout_s = 60
```

```bash
python scripts/run_agent.py --mcp-config examples/mcp.example.toml --task "读一下 README"
# [mcp] filesystem: 2 tools
```

- 工具命名 `mcp__<server>__<tool>`，超长自动截断加哈希
- `isError` 转成 `ok=False` 的观察结果，模型能看到错误并自行重试
- 子进程环境走白名单，父进程的 `LLM_API_KEY` 不会传给第三方服务器
- 单台服务器启动失败只记录在报告里，不影响其他服务器

详见 [docs/mcp.md](docs/mcp.md)。

## AI 自闭环演示（离线可复现）

```bash
python scripts/demo_repair.py
```

输出：

```
status : finished
attempt 1: failed=0 changed=['buggy_calc.py']
final  : passed=3 failed=0
```

流程：沙箱跑 pytest（临时副本，不污染仓库）→ 解析 junit-xml 得到结构化失败 →
模型返回结构化补丁 JSON → 校验（**禁止修改 tests/、禁止路径穿越**）→ 写回 → 重跑，
直到全绿或达最大尝试次数。替换为真实模型只需把 `FakeProvider` 换成
`OpenAICompatibleProvider(base_url, api_key, model)`。

### 修自己的仓库（更有说服力）

```bash
python scripts/demo_self_repair.py            # 脚本化补丁，零成本
python scripts/demo_self_repair.py --provider env   # 真模型来修
```

输出：

```
injected bug: src/mini_harness/core/evaluation.py (hit_rate denominator off by one)
status     : finished
attempt 1: failed=0 changed=['src/mini_harness/core/evaluation.py']
final      : passed=57 failed=0
restored   : True
```

做的是：把仓库复制到临时目录 → 故意改坏 `hit_rate` 的计算 → 让 harness 自己发现、
修补、重跑到全绿，最后校验源码已还原。这就是 JD 里“你负责的模块里 AI 自己收敛”
的最小可演示版本。

也可以在 GitHub Actions 里跑：**Actions → Self-Repair Demo → Run workflow**，
选 `fake`（无需密钥）或 `env`（需先在仓库 Settings → Secrets 里配置
`LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL`）。

## 分层记忆（Phase 3）

三层结构与三条保护：

| 层 | 载体 | 说明 |
|---|---|---|
| 工作记忆 | `ContextManager` | 当前对话窗口，预算裁剪（不外置存储） |
| 情景记忆 | SQLite `episodes` | 每次会话/运行的任务与结果摘要 |
| 长期记忆 | SQLite `facts` | 带 `key`/`confidence`/`source` 的稳定事实 |

```python
from mini_harness.core.memory import MemoryStore

memory = MemoryStore("memory.sqlite")
memory.add_episode("s1", "用户说：以后回答先给结论")
memory.consolidate("s1", summarizer)      # 情景 → 长期事实（幂等，重复执行返回 0）
memory.recall("回答偏好")                  # 命中后 hits/last_used_at 自动更新
memory.forget(ttl_days=30, max_facts=50)  # 过期归档 + 容量上限
```

- **离线巩固幂等**：只处理未巩固的 episode，重复调用不产生重复事实；
- **遗忘**：TTL 过期 + 容量裁剪（按 hits/confidence 排序，低分先归档）；
- **污染防护**：同一 `key` 的事实冲突时**不静默覆盖**，新事实以 `pending` 状态挂起并可审计；
- `AgentLoop(memory=...)` 会在运行时自动注入 `[记忆]` 块，并在运行结束后写入 episode。

## 规划式召回评测（Phase 4）

```bash
python scripts/eval_retrieval.py
```

| Retriever | Hit@3 | MRR | Cases |
|---|---|---|---|
| naive-topk | 14% | 0.14 | 7 |
| planned | 100% | 1.00 | 7 |

语料 8 篇、评测集 7 题（刻意包含多跳与同义改写），**小样本、仅用于回归对比**，不代表线上效果。
规划式召回 = LLM 拆子查询 + 关键词召回 + 多路合并重排；朴素方案是单次 bigram 相似度 top-k。

## License

MIT © 2026 guozl-dev
