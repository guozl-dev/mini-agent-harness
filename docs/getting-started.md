# 快速开始（Getting Started）

面向第一次接触本项目的人：从零下载 → 装环境 → 跑起来 → 接真实模型。全程约 10 分钟。

---

## 0. 这个项目是什么

一个**从零实现、可审计的轻量 Agent 运行时（Harness）**：任务循环状态机、SQLite 状态持久化、上下文预算裁剪、工具权限治理、pytest 自闭环修复、分层记忆、规划式召回。

不依赖 LangChain / LangGraph，代码量小（约 1.6k 行 Python），适合阅读源码、二次开发或作为面试作品。

---

## 1. 环境要求

| 项 | 要求 | 说明 |
|---|---|---|
| Python | **3.11+**（已在 3.13 验证） | 使用了 `StrEnum`、`X | None` 语法，3.10 及以下不支持 |
| Git | 任意较新版本 | 用于 clone；也可以直接下载 ZIP |
| 网络 | 能访问 PyPI | 国内建议用镜像（见 3.2） |
| 可选 | [uv](https://docs.astral.sh/uv/) | 更快的依赖管理，非必需 |

操作系统：Windows 10/11、macOS、Linux 均可。Windows 上命令示例用 **Git Bash**（PowerShell 写法见 5.2）。

---

## 2. 获取项目

```bash
# 方式一：SSH（需已配置 SSH key）
git clone git@github.com:guozl-dev/mini-agent-harness.git
cd mini-agent-harness

# 方式二：HTTPS
git clone https://github.com/guozl-dev/mini-agent-harness.git
cd mini-agent-harness

# 方式三：浏览器下载
# 仓库页 → Code → Download ZIP → 解压后进入目录
```

> Windows 建议放在短路径下（如 `D:\code\mini-agent-harness`），避免超长路径导致工具报错。

---

## 3. 安装依赖

### 3.1 方式 A：uv（推荐，最快）

```bash
uv venv
uv pip install -e ".[dev]"
```

### 3.2 方式 B：venv + pip（零额外依赖）

```bash
# Windows（Git Bash）
python -m venv .venv
source .venv/Scripts/activate

# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate

# 安装（国内网络建议加镜像）
pip install -e ".[dev]" -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 3.3 安装内容说明

| 包 | 用途 |
|---|---|
| `pydantic` | 数据模型与校验（Message / ToolSpec / ChatResponse） |
| `httpx` | 调用 OpenAI 兼容接口 |
| `pytest`、`pytest-cov` | 测试与覆盖率 |
| `ruff` | 代码检查与格式 |

安装完成后 `mini_harness` 以**可编辑模式**（`-e`）装进环境，改源码立即生效。

---

## 4. 验证安装

```bash
python -m pytest                 # 期望：56 passed
python -m ruff check .           # 期望：All checks passed!
python -m pytest --cov           # 期望：覆盖率约 93%
```

看到 `56 passed` 即表示环境完全就绪（不需要任何 API Key，测试全部走 FakeProvider）。

---

## 5. 配置真实模型（可选）

不配置也能用（演示脚本全用 FakeProvider，零成本）。要接真实模型，设置三个环境变量：

| 变量 | 含义 | 示例 |
|---|---|---|
| `LLM_BASE_URL` | OpenAI 兼容接口地址（**带 /v1**） | `https://api.deepseek.com/v1` |
| `LLM_API_KEY` | 你的 API Key | `sk-xxxx` |
| `LLM_MODEL` | 模型名 | `deepseek-chat` |
| `LLM_TIMEOUT`（可选） | 单次请求超时（秒） | `60` |
| `LLM_MAX_RETRIES`（可选） | 重试次数 | `3` |

### 5.1 变量怎么写

```bash
# Git Bash / macOS / Linux
export LLM_BASE_URL="https://api.deepseek.com/v1"
export LLM_API_KEY="sk-你的key"
export LLM_MODEL="deepseek-chat"
```

```powershell
# Windows PowerShell
$env:LLM_BASE_URL = "https://api.deepseek.com/v1"
$env:LLM_API_KEY  = "sk-你的key"
$env:LLM_MODEL    = "deepseek-chat"
```

### 5.2 关于 `.env` 文件（当前限制）

仓库提供 `.env.example` 作为**配置示例**，但代码**不会自动读取** `.env`（刻意不引入额外依赖）。二选一：

```bash
# 方案一：手动 source（Git Bash 可用）
cp .env.example .env   # 然后编辑 .env 填真实值
set -a; source .env; set +a
```

```python
# 方案二：代码里显式传入（无需环境变量）
from mini_harness.llm.provider import OpenAICompatibleProvider
provider = OpenAICompatibleProvider(
    base_url="https://api.deepseek.com/v1",
    api_key="sk-xxx",
    model="deepseek-chat",
)
```

---

## 6. 启动并验证「项目可用」

三条命令，从易到难：

### 6.1 自闭环修复演示（不花钱，30 秒）

```bash
python scripts/demo_repair.py
```

期望输出：

```
status : finished
attempt 1: failed=0 changed=['buggy_calc.py']
final  : passed=3 failed=0
```

含义：沙箱跑测试发现 3 个失败 → 模型返回结构化补丁 → 校验后写回 → 重跑全绿。

### 6.2 检索评测对比（不花钱，5 秒）

```bash
python scripts/eval_retrieval.py
```

期望输出：

```
| Retriever  | Hit@3 | MRR  | Cases |
| naive-topk |   14% | 0.14 |     7 |
| planned    |  100% | 1.00 |     7 |
```

同时会写出 `docs/retrieval_eval.md`。

### 6.3 跑一个真实任务（可接真实模型）

```bash
# 默认 FakeProvider（零成本验证链路）
python scripts/run_agent.py

# 接真实模型（需先按第 5 节导出环境变量）
python scripts/run_agent.py --provider env --task "用一句话介绍你自己"
```

期望输出：

```
status : finished
steps  : 2
answer : ...
tool   : now ok=True output=2026-11-20T18:35:17
run_id : 9d47aa2e...
```

`agent_runs.sqlite`（运行审计）与 `agent_memory.sqlite`（记忆）会自动生成在项目根目录，可随时删除。

---

## 7. 作为库嵌入自己的项目

```python
from mini_harness.core.loop import AgentLoop
from mini_harness.core.memory import MemoryStore
from mini_harness.core.state import StateStore
from mini_harness.core.tools import ToolRegistry
from mini_harness.llm.provider import OpenAICompatibleProvider
from mini_harness.llm.types import ToolSpec

provider = OpenAICompatibleProvider.from_env()      # 或直接传参
tools = ToolRegistry(timeout_s=5)
tools.register(
    ToolSpec(name="now", description="返回当前时间", parameters={"type": "object"}),
    lambda: "2026-11-20 18:00",
)
loop = AgentLoop(
    provider,
    tools=tools,
    store=StateStore("runs.sqlite"),
    memory=MemoryStore("memory.sqlite"),
    max_steps=6,
)
result = loop.run("现在几点？")
print(result.status, result.steps, result.content)
for call in loop.history(result.run_id).tool_calls:
    print(call.name, call.ok, call.output)
```

---

## 8. 常见问题处理

| 现象 | 原因 | 解决 |
|---|---|---|
| `ModuleNotFoundError: mini_harness` | 没装或没激活虚拟环境 | 激活 venv 后执行 `pip install -e ".[dev]"` |
| `pytest: command not found` | 脚本目录不在 PATH | 用 `python -m pytest` |
| `pip` 安装极慢 / 超时 | 直连 PyPI 慢 | 加 `-i https://pypi.tuna.tsinghua.edu.cn/simple` |
| `ProviderError: missing environment variables` | 没导出 `LLM_*` | 按第 5 节导出，或改用 `--provider fake` |
| 401 / Unauthorized | Key 错误或 `BASE_URL` 少了 `/v1` | 检查两者；DeepSeek 为 `https://api.deepseek.com/v1` |
| `sqlite3.OperationalError: database is locked` | 多进程共用同一 db | 输出到不同路径，或先 `store.close()` |
| Windows 终端中文乱码 | 控制台编码非 UTF-8 | `chcp 65001`，或改用 Windows Terminal |
| git 提示 `LF will be replaced by CRLF` | 跨平台换行符 | 可安全忽略；统一可设 `git config --global core.autocrlf input` |
| `SyntaxError` 在 `StrEnum` | Python < 3.11 | 升级到 3.11+ |
| 演示脚本修改了示例项目 | 正常：示例会被改动 | `git checkout -- examples/` 还原 |

---

## 9. 新人阅读路线（约 30 分钟）

1. `README.md` → 了解定位与四阶段
2. `docs/roadmap.md` → 四个设计问题（loop/状态/裁剪/边界）
3. `src/mini_harness/core/loop.py`（约 130 行）→ 状态机主干
4. `python scripts/demo_repair.py` → 看自闭环实际效果
5. `tests/test_loop.py` → 看状态机如何被验证
6. `src/mini_harness/core/memory.py` → 记忆三保护

---

## 10. 当前缺口（建议后续补充，含文件位置）

| 缺口 | 影响 | 建议补充位置 |
|---|---|---|
| 无命令行入口（`mini-harness` 命令） | 使用者只能 `python scripts/...` | `pyproject.toml` 增加 `[project.scripts]`；新增 `src/mini_harness/cli.py` |
| `.env` 不会自动加载 | 每次需手动 export | 新增 `src/mini_harness/config.py` + 可选依赖 `python-dotenv`（`pyproject.toml`） |
| 无 Dockerfile | 无法容器化一键运行 | 根目录新增 `Dockerfile`（python:3.12-slim + `pip install -e .`） |
| 无 Makefile / dev 脚本 | 常用命令要记 | 根目录 `Makefile`，或 `scripts/dev.ps1` / `dev.sh` |
| README 无徽章与演示 GIF | 转化率低、说服力弱 | `README.md` 顶部 + `docs/assets/demo.gif` |
| 未标记 `py.typed` | 第三方 mypy 无法识别类型 | 新增空文件 `src/mini_harness/py.typed` |
| 评测语料仅 8 篇 / 7 题 | 指标参考性有限 | `evals/corpus.json`、`evals/cases.json` 扩充 |
| 无 CONTRIBUTING / Issue 模板 | 协作规范缺失（个人项目可暂缓） | `.github/CONTRIBUTING.md`、`.github/ISSUE_TEMPLATE/` |

> 本次已补齐：`OpenAICompatibleProvider.from_env()`（`src/mini_harness/llm/provider.py`）与命令行入口脚本 `scripts/run_agent.py`，并补了对应测试。

---

## 11. 清理

```bash
rm -rf .venv agent_runs.sqlite agent_memory.sqlite   # 删除环境与运行产物
```
