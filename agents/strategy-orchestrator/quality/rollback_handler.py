"""
Rollback Handler - 回退策略处理器

处理各种失败情况的降级方案
"""

from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass
from enum import Enum
import logging


logger = logging.getLogger(__name__)


class FailureType(Enum):
    """失败类型"""
    SQL_UNAVAILABLE = "sql_unavailable"          # SQL 数据库不可用
    SQL_QUERY_FAILED = "sql_query_failed"         # SQL 查询失败
    RAG_UNAVAILABLE = "rag_unavailable"           # RAG 服务不可用
    RAG_NO_RESULTS = "rag_no_results"            # RAG 检索无结果
    SEARCH_NO_RESULTS = "search_no_results"       # 搜索无结果
    ANALYSIS_FAILED = "analysis_failed"           # 分析执行失败
    REPORT_FAILED = "report_failed"               # 报告生成失败
    LLM_FAILED = "llm_failed"                      # LLM 调用失败
    TIMEOUT = "timeout"                           # 超时
    UNKNOWN = "unknown"


@dataclass
class FallbackAction:
    """回退动作"""
    action_type: str              # action name
    description: str              # 描述
    retry_original: bool = False   # 是否重试原操作
    alternative: Optional[str] = None  # 替代方案
    reduced_confidence: float = 0.5  # 降级后的置信度


@dataclass
class FailureContext:
    """失败上下文"""
    failure_type: FailureType
    original_operation: str        # 原始操作
    error_message: str             # 错误信息
    evidence_so_far: Dict[str, Any] = None  # 到目前为止收集的证据
    user_intent: Dict[str, Any] = None     # 用户意图
    retry_count: int = 0


class RollbackHandler:
    """
    回退策略处理器
    
    为每种失败类型提供标准的回退动作
    """
    
    # 预定义回退策略
    STRATEGIES: Dict[FailureType, List[FallbackAction]] = {
        FailureType.SQL_UNAVAILABLE: [
            FallbackAction(
                action_type="try_rag",
                description="RAG 检索降级",
                retry_original=False,
                alternative="pg-vector-search",
                reduced_confidence=0.7
            ),
            FallbackAction(
                action_type="try_web_search",
                description="网络搜索降级",
                retry_original=False,
                alternative="web-search",
                reduced_confidence=0.6
            ),
            FallbackAction(
                action_type="proceed_with_partial",
                description="使用已有证据继续",
                retry_original=False,
                reduced_confidence=0.5
            ),
        ],
        
        FailureType.SQL_QUERY_FAILED: [
            FallbackAction(
                action_type="retry_with_simplified",
                description="简化 SQL 查询重试",
                retry_original=True,
                reduced_confidence=0.75
            ),
            FallbackAction(
                action_type="try_rag",
                description="RAG 检索降级",
                retry_original=False,
                alternative="pg-vector-search",
                reduced_confidence=0.7
            ),
            FallbackAction(
                action_type="use_historical",
                description="使用历史报告数据",
                retry_original=False,
                reduced_confidence=0.6
            ),
        ],
        
        FailureType.RAG_UNAVAILABLE: [
            FallbackAction(
                action_type="try_structured",
                description="仅使用结构化数据",
                retry_original=False,
                alternative="nl2sql-pg",
                reduced_confidence=0.8
            ),
            FallbackAction(
                action_type="try_web_search",
                description="网络搜索降级",
                retry_original=False,
                alternative="web-search",
                reduced_confidence=0.6
            ),
        ],
        
        FailureType.RAG_NO_RESULTS: [
            FallbackAction(
                action_type="expand_query",
                description="扩大检索范围重试",
                retry_original=True,
                reduced_confidence=0.75
            ),
            FallbackAction(
                action_type="try_synonyms",
                description="同义词扩展检索",
                retry_original=True,
                reduced_confidence=0.7
            ),
            FallbackAction(
                action_type="try_web_search",
                description="网络搜索降级",
                retry_original=False,
                alternative="web-search",
                reduced_confidence=0.6
            ),
        ],
        
        FailureType.SEARCH_NO_RESULTS: [
            FallbackAction(
                action_type="try_rag",
                description="RAG 检索降级",
                retry_original=False,
                alternative="pg-vector-search",
                reduced_confidence=0.7
            ),
            FallbackAction(
                action_type="proceed_with_partial",
                description="标注信息缺失继续",
                retry_original=False,
                reduced_confidence=0.5
            ),
        ],
        
        FailureType.ANALYSIS_FAILED: [
            FallbackAction(
                action_type="retry_simplified",
                description="简化分析重试",
                retry_original=True,
                reduced_confidence=0.7
            ),
            FallbackAction(
                action_type="use_basic_structure",
                description="使用基础结构输出",
                retry_original=False,
                reduced_confidence=0.6
            ),
        ],
        
        FailureType.REPORT_FAILED: [
            FallbackAction(
                action_type="return_structured",
                description="返回结构化结论",
                retry_original=False,
                reduced_confidence=0.7
            ),
            FallbackAction(
                action_type="return_natural",
                description="返回自然语言摘要",
                retry_original=False,
                reduced_confidence=0.6
            ),
        ],
        
        FailureType.LLM_FAILED: [
            FallbackAction(
                action_type="retry",
                description="LLM 重试",
                retry_original=True,
                reduced_confidence=0.75
            ),
            FallbackAction(
                action_type="proceed_without_llm",
                description="无 LLM 模式继续",
                retry_original=False,
                reduced_confidence=0.6
            ),
        ],
        
        FailureType.TIMEOUT: [
            FallbackAction(
                action_type="proceed_with_current",
                description="使用当前已收集证据继续",
                retry_original=False,
                reduced_confidence=0.6
            ),
        ],
        
        FailureType.UNKNOWN: [
            FallbackAction(
                action_type="log_and_proceed",
                description="记录错误并继续",
                retry_original=False,
                reduced_confidence=0.5
            ),
        ],
    }
    
    def __init__(self):
        self.failure_history: List[FailureContext] = []
        self.custom_strategies: Dict[FailureType, List[FallbackAction]] = {}
    
    def register_strategy(self, failure_type: FailureType, actions: List[FallbackAction]):
        """注册自定义回退策略"""
        self.custom_strategies[failure_type] = actions
    
    def get_fallback(
        self,
        failure_type: FailureType,
        context: FailureContext
    ) -> FallbackAction:
        """
        获取下一步回退动作
        
        根据失败类型和上下文，返回适当的回退动作
        """
        # 记录失败
        self.failure_history.append(context)
        
        # 获取策略（优先使用自定义策略）
        strategies = self.custom_strategies.get(failure_type) or self.STRATEGIES.get(failure_type, [])
        
        if not strategies:
            logger.warning(f"No fallback strategy for {failure_type}")
            return FallbackAction(
                action_type="none",
                description="无可用回退策略",
                reduced_confidence=0.3
            )
        
        # 根据重试次数选择策略
        retry_count = context.retry_count
        
        if retry_count >= len(strategies):
            # 所有策略都用过了，返回最后一个
            return strategies[-1]
        
        return strategies[retry_count]
    
    def should_stop(self, context: FailureContext, max_retries: int = 3) -> bool:
        """
        判断是否应该停止
        
        停止条件：
        1. 已尝试所有回退策略
        2. 证据严重不足
        3. 用户需要关键参数
        """
        failure_type = context.failure_type
        strategies = self.custom_strategies.get(failure_type) or self.STRATEGIES.get(failure_type, [])
        
        # 已尝试所有策略
        if context.retry_count >= len(strategies):
            return True
        
        # 超过最大重试次数
        if context.retry_count >= max_retries:
            return True
        
        # 证据严重不足
        evidence = context.evidence_so_far or {}
        if len(evidence.get("evidences", [])) == 0 and context.retry_count >= 1:
            return True
        
        return False
    
    def get_failure_summary(self) -> Dict[str, Any]:
        """获取失败历史摘要"""
        summary = {
            "total_failures": len(self.failure_history),
            "by_type": {},
            "recent": []
        }
        
        for fc in self.failure_history:
            ft = fc.failure_type.value
            summary["by_type"][ft] = summary["by_type"].get(ft, 0) + 1
        
        # 最近 5 个
        for fc in self.failure_history[-5:]:
            summary["recent"].append({
                "type": fc.failure_type.value,
                "operation": fc.original_operation,
                "error": fc.error_message[:100],
                "timestamp": len(self.failure_history) - self.failure_history.index(fc)
            })
        
        return summary


def detect_failure_type(error: Exception, operation: str) -> FailureType:
    """
    根据错误和操作检测失败类型
    """
    error_str = str(error).lower()
    operation_lower = operation.lower()
    
    # 数据库相关
    if "psycopg2" in str(type(error).__module__) or "connection" in error_str:
        if "syntax" in error_str or "sql" in error_str:
            return FailureType.SQL_QUERY_FAILED
        return FailureType.SQL_UNAVAILABLE
    
    # RAG 相关
    if "rag" in operation_lower or "vector" in operation_lower:
        if "no results" in error_str or "empty" in error_str:
            return FailureType.RAG_NO_RESULTS
        if "unavailable" in error_str or "failed" in error_str:
            return FailureType.RAG_UNAVAILABLE
    
    # 搜索相关
    if "search" in operation_lower:
        if "no results" in error_str or "empty" in error_str:
            return FailureType.SEARCH_NO_RESULTS
    
    # 分析相关
    if "analysis" in operation_lower or "analyze" in operation_lower:
        return FailureType.ANALYSIS_FAILED
    
    # 报告相关
    if "report" in operation_lower:
        return FailureType.REPORT_FAILED
    
    # LLM 相关
    if "llm" in operation_lower or "openai" in error_str or "anthropic" in error_str:
        return FailureType.LLM_FAILED
    
    # 超时
    if "timeout" in error_str or "timed out" in error_str:
        return FailureType.TIMEOUT
    
    return FailureType.UNKNOWN


# 全局处理器实例
_rollback_handler: RollbackHandler = None


def get_rollback_handler() -> RollbackHandler:
    global _rollback_handler
    if _rollback_handler is None:
        _rollback_handler = RollbackHandler()
    return _rollback_handler