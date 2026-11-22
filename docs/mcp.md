# MCP 工具接入

把 [Model Context Protocol](https://modelcontextprotocol.io) 服务器提供的工具接进 harness。
核心思路：**MCP 工具只是 `ToolRegistry` 里的普通条目**，`AgentLoop` 与 `ToolRegistry` 的核心逻辑不变。

## 为什么这样做

| 方案 | 评价 |
|---|---|
| 在 `AgentLoop` 里加 MCP 分支 | 循环会同时承担协议与调度两种职责，难测试 |
| 给 `ToolRegistry` 加 MCP 类型 | 注册表要知道传输、会话、重连，抽象泄漏 |
| **适配成普通工具条目（本方案）** | 循环零改动；超时、guard、审计全部复用现有能力 |

## 依赖

```toml
"mcp>=1.30,<2",
"mcpadapt>=0.1.20",
"websockets>=13",
```

`mcp` 固定在 2.0 以下：`mcpadapt` 0.1.x 仍按 mcp 1.x 的模块布局导入
（`mcp.client.streamable_http.streamablehttp_client`），装 2.x 会在 import 阶段直接失败。

## 配置

```toml
[[mcp.servers]]
name              = "filesystem"
command           = "npx.cmd"        # Windows 必须带 .cmd，裸 npx 会 WinError 193
args              = ["-y", "@modelcontextprotocol/server-filesystem", "E:/work"]
cwd               = "E:/work"        # 可选
enabled           = true
allowed_tools     = ["read_file", "list_directory"]   # 留空 = 暴露全部
guard_exempt      = true             # MCP 天然访问工作区外路径，默认豁免 path_guard
connect_timeout_s = 30
call_timeout_s    = 60
max_output_chars  = 4000
env               = { NODE_NO_WARNINGS = "1" }
```

字段说明：

| 字段 | 默认 | 作用 |
|---|---|---|
| `name` | 必填 | 命名空间前缀，同时用于报告与排障 |
| `command` / `args` | 必填 / 空 | 启动子进程的命令 |
| `env` | 空 | 在**白名单环境**之上追加；父进程的 `LLM_API_KEY` 不会传给子进程 |
| `allowed_tools` | 空 | 只暴露指定工具，避免几十个工具挤占系统提示 |
| `guard_exempt` | `true` | 跳过 `ToolRegistry.path_guard` |
| `connect_timeout_s` | 30 | 握手超时（`npx -y` 首次要下载，别设太小） |
| `call_timeout_s` | 60 | 单次 `tools/call` 超时，同时决定注册表超时下限 |
| `max_output_chars` | 4000 | 单次结果截断，防止一个 `read_file` 打爆上下文 |

## 使用

```bash
python scripts/run_agent.py --mcp-config examples/mcp.example.toml --task "读一下 README 的第一段"
```

启动时会打印挂载结果：

```
[mcp] filesystem: 2 tools
```

某个服务器起不来时不会影响其他服务器：

```
[mcp] filesystem: 2 tools; broken: FAILED (TimeoutError: ...)
```

代码方式：

```python
from mini_harness.mcp import load_mcp_config, mount_mcp

handle = mount_mcp(registry, load_mcp_config("mcp.toml"))
try:
    loop.run(task)
finally:
    handle.close()   # 必须调用，否则子进程残留
```

## 工具命名

`mcp__<server>__<tool>`，例如 `mcp__filesystem__read_file`。

- 非 `[A-Za-z0-9_-]` 字符替换为 `_`（OpenAI 函数名限制）
- 超过 64 字符时截断并追加 6 位哈希，避免同名冲突

## 结果与错误映射

| MCP 返回 | harness 侧表现 |
|---|---|
| `content: [text]` | 直接作为观察输出 |
| `content: [image]` | 占位文本 `[image image/png, ~N bytes omitted]`（`Message` 只支持文本） |
| `content: [resource]` | `[resource <uri>]` + 内嵌文本 |
| `isError: true` | 抛异常 → `ToolObservation(ok=False)`，模型能看到错误内容并自行重试 |
| 工具不存在 | `tool_not_found` |

## 实机验证（2026-11-22）

用官方 `@modelcontextprotocol/server-filesystem@2.4.0`（`node` 启动，根目录 `E:/work`）跑真实任务：

```
[mcp] fs: 3 tools            # read_text_file / list_directory / directory_tree
tool : mcp__fs__list_directory ok=True
tool : mcp__fs__read_text_file ok=True
status : finished
```

模型成功列出目录、读取 `docs/mcp.md` 并准确概括出全部 5 条已知限制。同一轮验证还覆盖了
错误路径：故意给相对路径时服务器返回 `ENOENT`，该错误被转成 `ok=False` 的观察结果，
模型据此说明“文件不存在”，没有中断运行。

**工具重结果较长的场景需要调大上下文预算**，否则结果会被外部化，模型看不到内容而反复重读：

```bash
python scripts/run_agent.py --provider env --mcp-config mcp.toml \
  --context-budget 12000 --externalize-chars 12000 --max-steps 6 --task "..."
```

## 已知限制

1. **只支持 stdio 传输**。HTTP/SSE 需要换 `MCPAdapt` 的传入形态，配置层尚未开放。
2. **无自动重连**。服务器崩溃后该服务器上的工具会持续失败，需要重启进程。`mount_mcp` 只做启动期隔离。
3. **超时线程不会被回收**。`ToolRegistry` 用线程池包裹调用，超时后工作线程仍阻塞在 MCP 响应上；单次运行可接受，长驻服务需要换成可取消的会话。
4. **不重试**。MCP 没有幂等键，重放写操作会产生重复副作用。
5. **子进程清理依赖 `close()`**。Windows 下若 MCP 服务器自己派生了子进程，`taskkill /T` 才是彻底方案；当前实现只关闭会话。

## 测试

```bash
pytest tests/test_mcp.py -q
```

用 `tests/fixtures/echo_server.py` 作为真实 stdio 服务器，覆盖：握手与工具发现、正常调用、
`isError`、未知工具、白名单过滤、重复挂载、坏服务器隔离、注册表超时下限、命名截断、内容展平、
配置校验。
