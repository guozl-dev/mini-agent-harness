# AGENTS.md

本文件供 Codex CLI / Claude Code 等编码代理自动读取。修改本文件前请先确认与仓库现状一致。

## 交流与风格

- 始终用简体中文回复；代码、命令、日志、报错原文保持原样。
- 先给结论，再给依据；不确定的地方明确标注，不要编造测试结果或性能数字。
- 改动前说明将修改哪些文件、为什么；单点修复可直接动手。

## 项目定位

`mini-agent-harness` 是一个从零手写的轻量 Agent 运行时（不依赖 LangChain/LangGraph），
覆盖循环状态机、SQLite 三级持久化、上下文预算、工具治理、分层记忆、规划式召回、MCP 工具接入。

## 环境

- Python ≥ 3.11（本机虚拟环境为 `.venv`，Python 3.13）
- 依赖安装：`uv pip install -e ".[dev]"`（或 `pip install -e ".[dev]"`）
- 本机 PowerShell 下使用 `.venv\Scripts\python.exe`；CI 在 Linux 上直接 `python`

## 常用命令

```bash
# 测试（全量，约 30 秒）
.venv/Scripts/python.exe -m pytest -q

# 覆盖率门禁（CI 阈值 70）
.venv/Scripts/python.exe -m pytest --cov --cov-fail-under=70

# 静态检查
.venv/Scripts/python.exe -m ruff check src scripts tests

# 单任务运行（fake = 脚本化，免费；env = 真实模型，读 LLM_* 环境变量）
python scripts/run_agent.py --provider fake --task "报一下现在几点"
python scripts/run_agent.py --provider env --task "用一句话介绍你自己"

# 带 MCP 服务器运行
python scripts/run_agent.py --mcp-config examples/mcp.example.toml --context-budget 12000 --task "..."

# 离线演示
python scripts/demo_repair.py            # 修复靶场 bug
python scripts/demo_self_repair.py       # 给本仓库注入 bug 再自修
python scripts/eval_retrieval.py         # 检索评测 Hit@k / MRR
```

## 代码约定

- 源码 docstring 用英文，注释只在“为什么”不明显处写，避免解释“代码在做什么”。
- 类型注解齐全；行宽 100（ruff 配置见 `pyproject.toml`）。
- 新逻辑要有对应测试；测试放在 `tests/`，文件命名 `test_*.py`。
- 提交信息用约定式前缀：`feat:` / `fix:` / `chore:` / `docs:` / `test:`。

## 不可破坏的既有约束

1. **工具异常不外抛**：`ToolRegistry.execute` 必须把任何异常转成 `ok=False` 的观察结果，循环不能被打断。
2. **状态机语义**：`PLANNING → ACTING → OBSERVING → FINISHED/FAILED`；新增分支要同步 `state.py` 的持久化字段。
3. **测试不可为通过而改**：修 bug 时不得修改既有断言来“凑绿”；补丁校验层也会拒绝改测试。
4. **MCP 版本约束**：`mcp` 固定在 `<2`，因为 `mcpadapt 0.1.x` 依赖 mcp 1.x 的模块布局；`mcpadapt` 下限 0.1.19（0.1.20 要求 Python ≥3.12）。
5. **MCP 工具默认豁免路径守卫**：外部服务器本就访问工作区外路径，但配置文件只能来自本地可信来源。

## 安全

- 不要把 API Key、令牌写进仓库任何文件；运行期配置放在 `CODEX_HOME` / `~/.claude` / 用户环境变量。
- 不提交 `agent_runs.sqlite`、`agent_memory.sqlite`、`.env`、本地 `settings.local.json`。
- 涉及删除、批量重命名等破坏性操作前先确认，并优先使用可回滚方式。

## 文档

- `README.md`：总览与设计取舍
- `docs/getting-started.md`：首次使用
- `docs/mcp.md`：MCP 接入细节与已知限制
- `docs/roadmap.md`：阶段与验收标准
