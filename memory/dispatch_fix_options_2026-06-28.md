# A Bug 修复方案记录（2026-06-28）

**问题根因**：orchestrator 把 specialist dispatch 包好放在 `state.dispatch_queue` → 暴露到 `pending_dispatches` 给 caller，但 caller（live_agent_server.py）只取 chat completions 的 `text`，根本没读 `pending_dispatches`。"准备好但没发出去"。

详见 `executors/orchestrator.py:344-347`（仅入队）和 `python_wrapper/live_agent_server.py:1026`（只取 text）。

---

## 方案 A（已选定 · 实施中）：orchestrator 自触发 sessions_send

**核心改动**：
- `executors/orchestrator.py` 主循环里，当 `tool_result.dispatch_request` 设置时，**立即调用** sessions_send，不再仅入队
- 新增方法 `_trigger_sessions_send(dispatch_request, state)`，通过 OpenClaw Gateway HTTP API (`/v1/chat/completions`) 触发对目标 Agent 的 dispatch
- 删除 `ReactState.dispatch_queue`，新增 `ReactState.dispatched_results` 用于观测
- 删除 `OrchestrationResult.pending_dispatches`，由 `dispatched_count` + 结果摘要替代
- `live_agent_server.py` **不需要改**（caller 这条路被旁路掉）

**优点**：
- 与用户原意"编排大脑自己发"对齐
- 与 caller 完全解耦，不依赖 chat completions 文本通道
- specialist 响应直接进 orchestrator 的 evidence ledger，无需 caller 中转

**缺点 / 风险**：
- orchestrator 需要持有 OPENCLAW_GATEWAY_TOKEN（环境变量）
- dispatch 同步等待，orchestrator 主循环会阻塞等 specialist 返回
- 如果 specialist 卡死，需要 timeout 兜底
- 单元测试需要 mock HTTP 调用

**实施日期**：2026-06-28 15:24

---

## 方案 B（备选 · A 失败时切换）：text 协议携带

**核心改动**：
- orchestrator 把 `pending_dispatches` 序列化成 JSON 块，附加到返回 text 末尾
- `live_agent_server.py` 解析这个 JSON 块后，逐个调 sessions_send 收集结果，再生成最终答案

**优点**：
- 兼容现有 chat completions 通道（不动协议）
- caller 明确知道要再调一次 specialist

**缺点 / 风险**：
- 增加 JSON 解析逻辑（正则或 try/except）
- caller 端也得改（涉及 `live_agent_server.py`，这是 live_agent_server 团队的工作空间，需要协调）
- text 长度膨胀

**触发条件**：方案 A 的 HTTP 调用失败 / token 不可用 / timeout 频繁触发。

---

## 方案 C（备选 · A 失败时切换）：WebSocket 推送

**核心改动**：
- orchestrator 通过 WebSocket 主动推 dispatch 给 live_agent_server.py
- live_agent_server.py 起 WS 服务端接收 dispatch 并执行 sessions_send

**优点**：
- 实时性强
- 不阻塞 orchestrator 主循环

**缺点 / 风险**：
- 大改架构（live_agent_server.py 加 WS 服务端 + 鉴权 + 重连）
- 涉及 live_agent_server 团队的工作空间，需要协调

**触发条件**：方案 A/B 都不满足性能 / 实时性要求时。

---

## 决策日志

| 时间 | 决策 | 理由 |
|---|---|---|
| 2026-06-28 15:21 | 老大批准方案 A | 与"编排大脑自己发"对齐，与 caller 解耦 |
| (待定) | A 测试通过则保留 | |
| (待定) | A 失败则回退 B | 兼容性最好 |
