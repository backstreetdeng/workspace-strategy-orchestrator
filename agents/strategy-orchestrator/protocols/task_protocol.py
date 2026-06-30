"""
Task Protocol - 主 Agent → Orchestrator 任务传递协议

定义主 Agent 和 strategy-orchestrator 之间的任务传递格式。
"""

import json
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from enum import Enum
import uuid


class TaskType(Enum):
    """任务类型"""
    MARKET_TREND = "market_trend"           # 市场趋势分析
    COMPETITOR_ANALYSIS = "competitor_analysis"  # 竞品分析
    POLICY_IMPACT = "policy_impact"        # 政策影响评估
    OPPORTUNITY_ASSESSMENT = "opportunity_assessment"  # 市场机会评估
    COMPREHENSIVE_RESEARCH = "comprehensive_research"  # 综合研究
    SIMPLE_QUERY = "simple_query"          # 简单查询
    UNKNOWN = "unknown"


class TaskPriority(Enum):
    """任务优先级"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class OutputFormat(Enum):
    """期望输出格式"""
    NATURAL_LANGUAGE = "natural_language"   # 自然语言解释
    STRUCTURED_REPORT = "structured_report"  # 结构化报告
    TABLE = "table"                        # 表格
    COMPARISON = "comparison"              # 对比分析
    OPPORTUNITY_LIST = "opportunity_list"  # 机会清单


@dataclass
class UserIntent:
    """
    用户意图层
    关注：用户到底想解决什么问题
    """
    raw_query: str                          # 原始问题
    target_output: OutputFormat            # 期望输出格式
    time_range: str = "最近12个月"          # 时间范围
    entities: List[str] = field(default_factory=list)  # 涉及的实体：品牌/车型/市场/价格带
    constraints: List[str] = field(default_factory=list)  # 用户约束
    history_summary: str = ""               # 历史会话摘要
    user_preferences: Dict[str, Any] = field(default_factory=dict)  # 用户偏好
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "raw_query": self.raw_query,
            "target_output": self.target_output.value if isinstance(self.target_output, OutputFormat) else self.target_output,
            "time_range": self.time_range,
            "entities": self.entities,
            "constraints": self.constraints,
            "history_summary": self.history_summary,
            "user_preferences": self.user_preferences
        }


@dataclass
class ContextState:
    """
    上下文层
    关注：任务现在走到哪一步
    """
    current_plan: List[str] = field(default_factory=list)  # 当前计划步骤
    completed_steps: List[str] = field(default_factory=list)  # 已完成步骤
    tools_used: List[Dict[str, Any]] = field(default_factory=list)  # 已调用工具
    intermediate_results: List[Dict[str, Any]] = field(default_factory=list)  # 中间结果
    remaining_steps: List[str] = field(default_factory=list)  # 未完成步骤
    quality_requirements: Dict[str, bool] = field(default_factory=dict)  # 质量要求
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EvidenceFeedback:
    """
    证据反馈层
    关注：现有证据是否足够支撑结论
    """
    last_results: List[Dict[str, Any]] = field(default_factory=list)  # 最近工具返回
    missing_fields: List[str] = field(default_factory=list)  # 缺失字段
    conflicts: List[Dict[str, Any]] = field(default_factory=list)  # 冲突证据
    errors: List[str] = field(default_factory=list)  # 错误信息
    confidence: Optional[float] = None  # 当前置信度
    evidence_sufficient: bool = False   # 证据是否充分
    gaps: List[str] = field(default_factory=list)  # 证据缺口
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class OrchestrationTask:
    """
    完整的编排任务
    包含三层输入 + 元数据
    """
    task_id: str                           # 任务唯一 ID
    task_type: TaskType                    # 任务类型
    priority: TaskPriority = TaskPriority.MEDIUM
    
    # 三层输入
    user_intent: UserIntent = None
    context_state: ContextState = None
    evidence_feedback: EvidenceFeedback = None
    
    # 元数据
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    parent_task_id: Optional[str] = None   # 父任务 ID（用于子任务）
    max_react_cycles: int = 3              # 最大 ReAct 循环次数
    
    def __post_init__(self):
        if self.user_intent is None:
            self.user_intent = UserIntent(raw_query="", target_output=OutputFormat.NATURAL_LANGUAGE)
        if self.context_state is None:
            self.context_state = ContextState()
        if self.evidence_feedback is None:
            self.evidence_feedback = EvidenceFeedback()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_type": self.task_type.value if isinstance(self.task_type, TaskType) else self.task_type,
            "priority": self.priority.value if isinstance(self.priority, TaskPriority) else self.priority,
            "user_intent": self.user_intent.to_dict() if self.user_intent else None,
            "context_state": self.context_state.to_dict() if self.context_state else None,
            "evidence_feedback": self.evidence_feedback.to_dict() if self.evidence_feedback else None,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "parent_task_id": self.parent_task_id,
            "max_react_cycles": self.max_react_cycles
        }
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'OrchestrationTask':
        task = cls(
            task_id=data.get("task_id", str(uuid.uuid4())),
            task_type=TaskType(data.get("task_type", "unknown")),
            priority=TaskPriority(data.get("priority", "medium"))
        )
        
        if "user_intent" in data:
            task.user_intent = UserIntent(**data["user_intent"])
        if "context_state" in data:
            task.context_state = ContextState(**data["context_state"])
        if "evidence_feedback" in data:
            task.evidence_feedback = EvidenceFeedback(**data["evidence_feedback"])
        
        task.created_at = data.get("created_at", task.created_at)
        task.updated_at = data.get("updated_at", task.updated_at)
        task.parent_task_id = data.get("parent_task_id")
        task.max_react_cycles = data.get("max_react_cycles", 3)
        
        return task
    
    @classmethod
    def from_json(cls, json_str: str) -> 'OrchestrationTask':
        data = json.loads(json_str)
        return cls.from_dict(data)


@dataclass
class OrchestrationResult:
    """
    Orchestrator → 主 Agent 的返回结果
    """
    task_id: str                           # 对应的任务 ID
    success: bool
    user_intent: Dict[str, Any] = field(default_factory=dict)  # 原始用户意图
    analysis_plan: Dict[str, Any] = field(default_factory=dict)  # 统一分析计划
    answer: str = ""                        # 结构化结论
    facts: List[Dict[str, Any]] = field(default_factory=list)  # 事实
    inferences: List[Dict[str, Any]] = field(default_factory=list)  # 推断
    recommendations: List[str] = field(default_factory=list)  # 建议
    risks: List[Dict[str, Any]] = field(default_factory=list)  # 风险
    confidence: float = 0.0               # 总体置信度
    confidence_details: Dict[str, Any] = field(default_factory=dict)  # 置信度详情
    evidence_sources: List[Dict[str, Any]] = field(default_factory=list)  # 证据来源
    evidence_ledger: Dict[str, Any] = field(default_factory=dict)  # 证据账本
    evidence_store: Dict[str, Any] = field(default_factory=dict)  # D/R/W 业务证据编号
    seven_step_report: str = ""              # 七步法业务战略报告
    insight_cards: List[Dict[str, Any]] = field(default_factory=list)  # 业务洞察卡片
    reflection: Dict[str, Any] = field(default_factory=dict)  # ReAct 反思摘要
    replan_history: List[Dict[str, Any]] = field(default_factory=list)  # 重规划记录
    quality_passed: bool = False          # 质量门禁是否通过
    quality_summary: Dict[str, Any] = field(default_factory=dict)  # 质量门禁摘要
    failed_quality_checks: List[Dict[str, Any]] = field(default_factory=list)  # 未通过项
    missing_or_uncertain: List[str] = field(default_factory=list)  # 不确定/缺失
    next_steps: List[str] = field(default_factory=list)  # 下一步建议
    errors: List[str] = field(default_factory=list)  # 执行中的错误
    stop_reason: str = ""                   # 停止原因
    cycles_used: int = 0                    # 使用的 ReAct 循环次数
    # A.Option A: orchestrator inline-triggered sessions_send 摘要（取代旧 pending_dispatches）
    dispatched_results: List[Dict[str, Any]] = field(default_factory=list)
    dispatched_count: int = 0
    dispatched_ok_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


def create_task_from_user_query(
    query: str,
    target_output: OutputFormat = OutputFormat.NATURAL_LANGUAGE,
    time_range: str = "最近12个月",
    entities: List[str] = None,
    constraints: List[str] = None
) -> OrchestrationTask:
    """
    从用户查询创建编排任务
    
    主 Agent 调用此函数创建传递给 orchestrator 的任务
    """
    # 自动识别任务类型
    task_type = _classify_task_type(query)
    
    # 识别优先级
    priority = _classify_priority(query, task_type)
    
    # 提取实体
    if entities is None:
        entities = _extract_entities(query)
    
    task = OrchestrationTask(
        task_id=str(uuid.uuid4()),
        task_type=task_type,
        priority=priority,
        user_intent=UserIntent(
            raw_query=query,
            target_output=target_output,
            time_range=time_range,
            entities=entities,
            constraints=constraints or []
        )
    )
    
    return task


def _classify_task_type(query: str) -> TaskType:
    """根据查询内容分类任务类型"""
    query_lower = query.lower()
    
    if any(kw in query_lower for kw in ["趋势", "增长", "下滑", "增速", "渗透率", "trend", "growth", "decline"]):
        return TaskType.MARKET_TREND
    elif any(kw in query_lower for kw in ["竞品", "竞争", "对比", "品牌", "车型比较", "competitor", "competitive", "compare", "comparison"]):
        return TaskType.COMPETITOR_ANALYSIS
    elif any(kw in query_lower for kw in ["政策", "补贴", "法规", "标准", "关税", "policy", "subsidy", "regulation", "tariff"]):
        return TaskType.POLICY_IMPACT
    elif any(kw in query_lower for kw in ["机会", "进入", "投资", "市场空间", "tam", "sam", "opportunity", "evaluate", "assessment", "enter"]):
        return TaskType.OPPORTUNITY_ASSESSMENT
    elif any(kw in query_lower for kw in ["分析", "研究", "报告", "综合", "全面", "analyze", "analysis", "research", "report", "strategy"]):
        return TaskType.COMPREHENSIVE_RESEARCH
    elif any(kw in query_lower for kw in ["多少", "排名", "数据", "销量", "how many", "ranking", "data", "sales"]):
        return TaskType.SIMPLE_QUERY
    else:
        return TaskType.UNKNOWN


def _classify_priority(query: str, task_type: TaskType) -> TaskPriority:
    """分类任务优先级"""
    query_lower = query.lower()
    
    if any(kw in query_lower for kw in ["紧急", "立刻", "马上", "现在"]):
        return TaskPriority.CRITICAL
    elif any(kw in query_lower for kw in ["重要", "关键", "核心"]):
        return TaskPriority.HIGH
    elif task_type == TaskType.SIMPLE_QUERY:
        return TaskPriority.LOW
    else:
        return TaskPriority.MEDIUM


def _extract_entities(query: str) -> List[str]:
    """从查询中提取实体（品牌/车型/市场）"""
    # 常见的品牌
    brands = ["比亚迪", "特斯拉", "吉利", "长安", "长城", "上汽", "广汽", "蔚来", "小鹏", "理想",
              "大众", "丰田", "本田", "日产", "奔驰", "宝马", "奥迪", "现代", "起亚"]
    
    entities = []
    for brand in brands:
        if brand in query:
            entities.append(brand)
    
    # 简单的车型提取（带"某车型"或"某品牌+某车型"模式）
    import re
    model_pattern = r'([A-Za-z0-9]+\s*[A-Za-z0-9]+)\s*(?:SUV|轿车|MPV|车型|款)'
    models = re.findall(model_pattern, query)
    entities.extend(models)
    
    return list(set(entities))


# 任务状态追踪
class TaskTracker:
    """任务状态追踪器"""
    
    def __init__(self):
        self._tasks: Dict[str, OrchestrationTask] = {}
        self._results: Dict[str, OrchestrationResult] = {}
    
    def add_task(self, task: OrchestrationTask):
        self._tasks[task.task_id] = task
    
    def get_task(self, task_id: str) -> Optional[OrchestrationTask]:
        return self._tasks.get(task_id)
    
    def update_task(self, task: OrchestrationTask):
        task.updated_at = datetime.now().isoformat()
        self._tasks[task.task_id] = task
    
    def set_result(self, result: OrchestrationResult):
        self._results[result.task_id] = result
    
    def get_result(self, task_id: str) -> Optional[OrchestrationResult]:
        return self._results.get(task_id)
    
    def list_pending_tasks(self) -> List[OrchestrationTask]:
        return [t for t in self._tasks.values() if t.task_id not in self._results]
    
    def clear(self):
        self._tasks.clear()
        self._results.clear()


# 全局追踪器
_task_tracker: Optional[TaskTracker] = None


def get_task_tracker() -> TaskTracker:
    global _task_tracker
    if _task_tracker is None:
        _task_tracker = TaskTracker()
    return _task_tracker

