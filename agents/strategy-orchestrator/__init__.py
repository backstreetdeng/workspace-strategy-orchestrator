"""
Strategy Orchestrator - 市场战略智能体编排器

核心组件：
- executors/orchestrator.py: ReAct 循环执行器
- protocols/task_protocol.py: 任务传递协议
- evidence/evidence_ledger.py: 证据账本
- quality/quality_gate.py: 质量门禁
- quality/rollback_handler.py: 回退策略

使用示例：
```python
from agents.strategy_orchestrator import orchestrate_task, create_orchestrator

# 方式1: 便捷函数
result = orchestrate_task("分析比亚迪市场策略")

# 方式2: 创建编排器
orchestrator = create_orchestrator()
task = create_task_from_user_query("分析比亚迪市场策略")
result = orchestrator.execute(task)
```
"""

from .executors.orchestrator import (
    StrategyOrchestrator,
    create_orchestrator,
    orchestrate_task
)

from .protocols.task_protocol import (
    OrchestrationTask,
    OrchestrationResult,
    TaskType,
    OutputFormat,
    UserIntent,
    ContextState,
    EvidenceFeedback,
    create_task_from_user_query,
    get_task_tracker
)

from .evidence.evidence_ledger import (
    EvidenceLedger,
    Evidence,
    EvidenceSource,
    get_evidence_ledger,
    reset_evidence_ledger
)

from .quality.quality_gate import (
    QualityGate,
    QualityLevel,
    QualityCheckResult,
    get_quality_gate,
    generate_quality_report
)

from .quality.rollback_handler import (
    RollbackHandler,
    FallbackAction,
    FailureContext,
    FailureType,
    get_rollback_handler
)

__all__ = [
    # Orchestrator
    "StrategyOrchestrator",
    "create_orchestrator",
    "orchestrate_task",
    
    # Protocol
    "OrchestrationTask",
    "OrchestrationResult",
    "TaskType",
    "OutputFormat",
    "UserIntent",
    "ContextState",
    "EvidenceFeedback",
    "create_task_from_user_query",
    "get_task_tracker",
    
    # Evidence
    "EvidenceLedger",
    "Evidence",
    "EvidenceSource",
    "get_evidence_ledger",
    "reset_evidence_ledger",
    
    # Quality
    "QualityGate",
    "QualityLevel",
    "QualityCheckResult",
    "get_quality_gate",
    "generate_quality_report",
    
    # Rollback
    "RollbackHandler",
    "FallbackAction",
    "FailureContext",
    "FailureType",
    "get_rollback_handler",
]