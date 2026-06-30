# 工作空间架构地图

更新时间：2026-06-17

这份文件用于说明 `workspace-market` 的当前架构边界：谁负责用户入口，谁负责复杂任务编排，谁只是方法库、桥接层或展示层。

## 一、当前架构结论

当前工作空间已经从“Python / Prose 固定流程模拟编排”整理为“Agent 自主决策编排”。

最终职责链路是：

```text
用户 / 飞书 / WebChat
  -> market_strategy_agent
     - 接收用户问题
     - 判断任务边界
     - 简单问题直接回答
     - 复杂市场分析转交 strategy-orchestrator
     - 汇总结构化结果并面向用户解释
  -> strategy-orchestrator
     - 执行 Plan -> Act -> Observe -> Reflect -> Re-plan
     - 调度 data-agent / analysis-agent / report-agent / Skills
     - 维护证据账本、置信度、缺口和回退策略
  -> 专业能力层
     - Skills、数据库、RAG、搜索、报告生成、分析框架
  -> 展示 / API 辅助层
     - SSE、上传服务、旧 API 兼容，只展示或转发，不做业务决策
```

一句话边界：

- `market_strategy_agent` 是用户入口和最终解释者。
- `strategy-orchestrator` 是复杂任务的自主编排大脑。
- `workflows/market_analysis.prose` 是市场分析方法论和质量契约，不是流程控制器。
- `python_wrapper/` 是桥接和兼容层，不是业务调度大脑。
- `sse_server.py` 是展示 / API 层，不控制分析流程。

## 二、核心文件定位

| 文件 / 目录 | 当前定位 | 说明 |
|-------------|----------|------|
| `AGENTS.md` | 主 Agent 工作规范 | 定义入口职责、分流规则、复杂任务调用协议 |
| `SOUL.md` | 主 Agent 身份与行为原则 | 包含事实准确性、记忆和自我成长规则 |
| `MEMORY.md` | 核心记忆索引 | 记录长期架构原则、任务索引和历史认知 |
| `memory/` | 可恢复记忆层 | 每日日志、架构地图、长期任务执行记录 |
| `agents/strategy-orchestrator/` | 复杂任务编排 Agent | 负责复杂市场分析的动态调度和证据闭环 |
| `workflows/market_analysis.prose` | 方法论 / 契约 | 给编排 Agent 提供领域约束、工具建议、质量门禁 |
| `python_wrapper/` | 适配 / 兼容 / 服务封装 | Skill bridge、SSE/event bridge、上传和旧 API |
| `skills/` | 专业能力单元 | intent-classifier、nl2sql-pg、pg-vector-search 等 |
| `references/` | 分析知识库 | 框架、模板、数据源说明 |
| `share/` | 共享资料 | 协作记录、阶段文档、外部共享材料 |

## 三、workflows/ 目录

当前保留：

- `market_analysis.prose`：市场分析编排契约。它描述问题类型、证据要求、工具建议、报告结构和质量门禁。
- `bak/`：历史工作流、旧 Python 脚本和备份文件归档。

重要边界：

- `market_analysis.prose` 不负责逐步执行任务。
- `market_analysis.prose` 不替代 `strategy-orchestrator` 做动态决策。
- `market_analysis.prose` 不应被当作 Python pipeline 的配置文件。

## 四、agents/strategy-orchestrator

`strategy-orchestrator` 是复杂市场分析任务的自主编排中枢。

它接收三层输入：

- 用户意图层：原始问题、目标输出、时间范围、品牌/车型/市场、用户约束。
- 上下文层：当前计划、已调用工具、参数、中间结果、未完成事项。
- 证据反馈层：工具返回、来源、可信度、缺失字段、冲突和错误。

它的核心循环：

```text
Plan -> Act -> Observe -> Reflect -> Re-plan
```

它停止的条件：

- 证据足够支撑回答。
- 关键参数缺失，需要主 Agent 追问用户。
- 工具失败且无可用替代。
- 达到最大循环次数，输出低置信度结果和缺口。

## 五、python_wrapper/ 目录

当前定位：过渡期适配层和服务封装层。

保留文件：

- `skill_caller.py`：Python 到本地 Skills 的兼容调用器。
- `sse_server.py`：FastAPI + SSE 展示 / API 层。
- `upload_server.py`：文档上传 API。
- `document_processor.py`：文档解析、切块、向量化、PGVector 入库辅助能力。
- `config.py`、`requirements.txt`、`__init__.py`：配置、依赖和包入口。
- `workflow_ai_orchestrator.py`：遗留 / 过渡执行适配器，保留给 API 演示和兼容路径使用。
- `bak/`：旧流程和重复服务归档。

重要边界：

- `workflow_ai_orchestrator.py` 当前仍包含硬编码阶段逻辑，因此只能视为 legacy adapter / transition executor。
- 新架构下，复杂市场分析的业务决策不应继续下沉到 `python_wrapper`。
- 如果 API 或前端仍调用 `run_market_analysis_ai()`，这是兼容路径，不代表最终架构主线。
- 后续重构目标是逐步减少这里的业务阶段判断，让它只负责事件桥接、工具适配和旧接口兼容。

## 六、当前实际调用链与目标调用链

当前兼容 API 调用链：

```text
前端 / API
  -> python_wrapper/sse_server.py
  -> run_market_analysis_ai()
  -> python_wrapper/workflow_ai_orchestrator.py
  -> python_wrapper/skill_caller.py
  -> skills/*
```

这条链路可用于演示和兼容，但不应被描述为最终业务大脑。

目标复杂任务调用链：

```text
用户问题
  -> market_strategy_agent
  -> strategy-orchestrator
  -> data-agent / analysis-agent / report-agent / Skills
  -> strategy-orchestrator 汇总证据、置信度和缺口
  -> market_strategy_agent 面向用户解释
```

## 七、核心技能与资料

核心 Skills：

- `skills/intent-classifier`：识别问题类型。
- `skills/nl2sql-pg`：查询结构化市场数据。
- `skills/pg-vector-search`：检索行业报告、政策和历史资料。
- `skills/automotive-strategy-analysis`：PEST、波特五力、SWOT、4P 等框架分析。
- `skills/report-generator`：生成结构化报告。

知识库：

- `references/frameworks/`：分析框架。
- `references/templates/`：报告模板。
- `references/data-sources/`：数据源说明。

专业 Agent：

- `agents/market-analyst`：市场分析专家。
- `agents/competitor-analyst`：竞品分析专家。
- `agents/cost-analyst`：成本分析专家。
- `agents/report-generator`：报告生成专家。

## 八、已归档内容

`workflows/bak/`：

- `car_analysis_workflow.py`：旧 Python 固定流程，保留为历史参考。
- `debug_workflow.py`：旧 Skill 调试脚本。
- `market_analysis.prose.*.bak`：历史 OpenProse 版本。
- `bak.txt`、`建议.txt`：早期备份和设计建议。

`python_wrapper/bak/`：

- `workflow.py`：旧固定 Python 主流程。
- `stage_connectors.py`：旧阶段衔接器。
- `upload_service.py`：与 `upload_server.py` 重叠的旧上传服务。
- `sse_server.log`：旧运行日志。

归档文件不作为当前架构依据。

## 九、后续整理建议

P1：

- 已完成：更新 `python_wrapper` 中残留的“AI 编排层 / Workflow Orchestrator 是主控”等说明，统一改为“过渡适配器 / 兼容路径”。
- 已完成：更新可恢复执行记录，标注 T5/T6/T7 完成。

P2：

- 对 `workflow_ai_orchestrator.py` 做下一阶段代码级降级：把硬编码阶段逻辑拆成 adapter 或废弃路径。
- 让复杂市场分析默认走 `strategy-orchestrator`。

P3：

- 统一 `MEMORY.md` 里 2026-06-04 的历史阶段描述，标注其为旧架构认知，不再代表当前 v3.0。
- 清理演示页面和共享文档索引。

## 十、ADR-001：自主决策 Agent 调度方案

决策日期：2026-06-16

结论：复杂市场分析任务的自主编排主责交给 `strategy-orchestrator`。

原因：

- 复杂任务需要状态、证据账本、工具回退和多轮反思循环。
- 主 Agent 应专注用户入口、边界判断和最终解释。
- `python_wrapper` 适合做桥接和兼容，不适合做业务决策大脑。
- `market_analysis.prose` 更适合作为方法论和质量契约，而不是确定性流程控制器。

标准输出要求：

- 区分事实、推断、建议和不确定性。
- 标注数据来源、时间范围和置信度。
- 工具失败或证据不足时必须降级说明。
- 复杂任务必须可恢复，有检查点和下一步动作。
