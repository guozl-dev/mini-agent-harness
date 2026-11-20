# 路线与验收标准

| 阶段 | 目标 | 关键产出 | 验收 |
|---|---|---|---|
| Phase 0 | 工程底座 | Provider 抽象层（重试/超时/结构化输出）+ FakeProvider + CI | `pytest` 全绿；切换 provider 只改一行配置 |
| Phase 1 | Harness 内核 | `AgentLoop` 状态机、`StateStore`（SQLite）、`ContextManager`（预算裁剪/滚动摘要）、`ToolRegistry`（allowlist/超时） | 状态机全路径单测；断点恢复可复现；越权调用被拒 |
| Phase 2 | AI 自闭环 | `SandboxRunner`（pytest JSON 解析）+ `RepairLoop`（patch 应用与收敛判定）+ 演示靶场 | 靶场 ≥2 个 bug 自动修复；步数 ≤5；越界 patch 被拒 |
| Phase 3 | 分层记忆 | 工作/情景/长期三层 + 离线巩固（摘要去重写回）+ 遗忘与污染防护 | 跨会话记忆可召回；污染注入不静默覆盖；巩固幂等 |
| Phase 4 | 检索与发布 | 规划式召回（计划 → 多路 → 合并重排）+ 评测对比 + e2e/mock + 覆盖率门槛 + CI 门禁 + v0.1.0 | 规划式召回命中率优于 naive top-k；CI 全绿；README 回答四问 |

## 设计四问（每个阶段都要能回答）

1. **loop 怎么转**：状态机迁移路径 + 终止条件枚举 + 双预算（步数/token）。
2. **状态放哪**：SQLite 三级表（run/step/tool_call），支持断点续跑与审计。
3. **上下文怎么裁**：硬截断 → 滚动摘要 → 工具结果外置，三级策略按预算自动升级。
4. **工具边界画在哪**：allowlist + 参数 schema 校验 + 路径越界拦截 + 异常转观察结果。
