"""
Quality Gate - 质量门禁

交付前必须通过的检查清单
"""

from typing import Dict, List, Any, Tuple, Callable
from dataclasses import dataclass
from enum import Enum
import json


class QualityLevel(Enum):
    """质量等级"""
    EXCELLENT = "excellent"    # 优秀
    GOOD = "good"              # 良好
    ACCEPTABLE = "acceptable"  # 可接受
    POOR = "poor"              # 较差
    FAILED = "failed"          # 不合格


@dataclass
class QualityCheckResult:
    """质量检查结果"""
    check_name: str
    passed: bool
    level: QualityLevel
    message: str
    details: Dict[str, Any] = None
    suggestions: List[str] = None
    
    def __post_init__(self):
        if self.details is None:
            self.details = {}
        if self.suggestions is None:
            self.suggestions = []


class QualityGate:
    """
    质量门禁
    
    执行多维度质量检查，确保输出满足质量要求
    """
    
    def __init__(self):
        self.checks: List[Callable] = []
        self._register_default_checks()
    
    def _register_default_checks(self):
        """注册默认检查项"""
        self.checks = [
            self._check_answer_relevance,
            self._check_scope_clarity,
            self._check_source_citation,
            self._check_answer_strategy_evidence_requirements,
            self._check_evidence_ledger_output,
            self._check_data_caliber_and_time_range,
            self._check_fact_inference_separation,
            self._check_confidence_statement,
            self._check_confidence_factor_model,
            self._check_uncertainty_disclosure,
            self._check_nofabrication,
            self._check_next_steps,
        ]
    
    def run_all(self, result: Dict[str, Any]) -> Tuple[bool, List[QualityCheckResult]]:
        """
        运行所有质量检查
        
        Args:
            result: OrchestrationResult.to_dict() 的结果
            
        Returns:
            (all_passed, check_results)
        """
        check_results = []
        for check in self.checks:
            try:
                check_result = check(result)
                check_results.append(check_result)
            except Exception as e:
                check_results.append(QualityCheckResult(
                    check_name=check.__name__,
                    passed=False,
                    level=QualityLevel.POOR,
                    message=f"检查执行出错: {str(e)}"
                ))
        
        all_passed = all(r.passed for r in check_results)
        return all_passed, check_results
    
    def run_critical_only(self, result: Dict[str, Any]) -> Tuple[bool, List[QualityCheckResult]]:
        """只运行关键检查"""
        critical_checks = [
            self._check_answer_relevance,
            self._check_nofabrication,
            self._check_confidence_statement,
        ]
        
        check_results = []
        for check in critical_checks:
            try:
                check_result = check(result)
                check_results.append(check_result)
            except Exception as e:
                check_results.append(QualityCheckResult(
                    check_name=check.__name__,
                    passed=False,
                    level=QualityLevel.POOR,
                    message=f"检查执行出错: {str(e)}"
                ))
        
        all_passed = all(r.passed for r in check_results)
        return all_passed, check_results
    
    def _check_answer_relevance(self, result: Dict[str, Any]) -> QualityCheckResult:
        """检查1: 是否回答了用户原始问题"""
        user_query = result.get("user_intent", {}).get("raw_query", "")
        answer = result.get("answer", "")
        
        if not answer:
            return QualityCheckResult(
                check_name="answer_relevance",
                passed=False,
                level=QualityLevel.POOR,
                message="没有生成任何答案"
            )
        
        if not user_query:
            return QualityCheckResult(
                check_name="answer_relevance",
                passed=True,
                level=QualityLevel.GOOD,
                message="无法验证相关性（无原始问题）"
            )
        
        # 中文不能按单字符遍历后再用 len>=2 过滤；这里提取连续中文词、
        # 英文/数字词，并补充实体和分析计划目标，避免偏题答案被误判通过。
        keywords = self._extract_relevance_keywords(user_query, result)
        matched = sum(1 for k in keywords if k in answer)
        match_rate = matched / len(keywords) if keywords else 0.5
        
        if match_rate >= 0.5:
            level = QualityLevel.EXCELLENT if match_rate >= 0.8 else QualityLevel.GOOD
            return QualityCheckResult(
                check_name="answer_relevance",
                passed=True,
                level=level,
                message=f"答案相关性良好（匹配率 {match_rate:.0%}）",
                details={"match_rate": match_rate}
            )
        else:
            return QualityCheckResult(
                check_name="answer_relevance",
                passed=False,
                level=QualityLevel.POOR,
                message=f"答案与问题相关性低（匹配率 {match_rate:.0%}）",
                details={"match_rate": match_rate}
            )
    
    def _extract_relevance_keywords(self, user_query: str, result: Dict[str, Any]) -> List[str]:
        """Extract stable Chinese/English relevance terms from query and plan."""
        import re

        stopwords = {
            "分析", "研究", "报告", "看看", "一下", "帮我", "请", "如何", "什么",
            "市场", "汽车", "乘用车", "中国",
            "analyze", "analysis", "research", "report", "market", "strategy",
            "evaluate", "assessment", "study", "trend", "opportunity",
        }
        terms: List[str] = []
        for token in re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9][A-Za-z0-9+\-_.]{1,}", user_query or ""):
            if token not in stopwords and token.lower() not in stopwords and token not in terms:
                terms.append(token)

        intent = result.get("user_intent") or {}
        for entity in intent.get("entities") or []:
            if entity and str(entity) not in terms:
                terms.append(str(entity))

        plan = result.get("analysis_plan") or {}
        for key in ("target_brand", "market_scope", "price_band", "power_type", "time_range"):
            value = plan.get(key)
            if value and str(value) not in terms:
                terms.append(str(value))

        return terms[:12]

    def _check_scope_clarity(self, result: Dict[str, Any]) -> QualityCheckResult:
        """检查2: 是否说明了分析范围和时间范围"""
        user_intent = result.get("user_intent", {})
        answer = result.get("answer", "")
        
        time_range = user_intent.get("time_range", "unknown")
        entities = user_intent.get("entities", [])
        
        # 检查答案是否提到时间范围
        time_mentioned = time_range != "unknown" and time_range in answer
        
        # 检查答案是否提到实体
        entities_mentioned = all(e in answer for e in entities) if entities else True
        
        if time_mentioned and entities_mentioned:
            return QualityCheckResult(
                check_name="scope_clarity",
                passed=True,
                level=QualityLevel.GOOD,
                message="分析范围和时间范围已说明"
            )
        else:
            missing = []
            if not time_mentioned:
                missing.append(f"时间范围（当前设置：{time_range}）")
            if not entities_mentioned:
                missing.append(f"实体（{entities}）")
            
            return QualityCheckResult(
                check_name="scope_clarity",
                passed=False,
                level=QualityLevel.ACCEPTABLE,
                message=f"分析范围部分缺失: {', '.join(missing)}",
                details={"missing": missing}
            )
    
    def _check_source_citation(self, result: Dict[str, Any]) -> QualityCheckResult:
        """检查3: 是否列出了主要数据来源"""
        evidence_sources = result.get("evidence_sources", [])
        
        if not evidence_sources:
            return QualityCheckResult(
                check_name="source_citation",
                passed=False,
                level=QualityLevel.POOR,
                message="没有列出任何证据来源"
            )
        
        # 检查来源多样性
        source_types = set(s.get("source") for s in evidence_sources if s.get("source"))
        
        if len(source_types) >= 2:
            return QualityCheckResult(
                check_name="source_citation",
                passed=True,
                level=QualityLevel.EXCELLENT,
                message=f"多源证据（共 {len(source_types)} 种来源）",
                details={"source_types": list(source_types)}
            )
        elif len(source_types) == 1:
            return QualityCheckResult(
                check_name="source_citation",
                passed=True,
                level=QualityLevel.ACCEPTABLE,
                message=f"单一来源: {list(source_types)[0]}",
                details={"source_types": list(source_types)}
            )
        else:
            return QualityCheckResult(
                check_name="source_citation",
                passed=False,
                level=QualityLevel.POOR,
                message="证据来源不明确"
            )

    def _check_answer_strategy_evidence_requirements(self, result: Dict[str, Any]) -> QualityCheckResult:
        """检查: answer strategy 必需证据是否满足。"""
        plan = result.get("analysis_plan") or {}
        strategy = plan.get("answer_strategy") or {}
        if not strategy:
            return QualityCheckResult(
                check_name="answer_strategy_evidence_requirements",
                passed=True,
                level=QualityLevel.ACCEPTABLE,
                message="未写入 answer strategy，跳过策略证据检查"
            )

        is_market_structure = (
            strategy.get("subject_kind") == "market"
            and not strategy.get("is_target_specific")
            and any("竞争" in str(item) or "Top品牌" in str(item) for item in strategy.get("must_answer", []))
        )
        if not is_market_structure:
            return QualityCheckResult(
                check_name="answer_strategy_evidence_requirements",
                passed=True,
                level=QualityLevel.GOOD,
                message="当前 answer strategy 不要求市场竞争结构专项证据"
            )

        store = result.get("evidence_store") or {}
        d_items = store.get("D") or []
        r_items = store.get("R") or []
        w_items = store.get("W") or []
        has_competitor_share = any("competitor_share" in str(item) for item in d_items)
        missing = []
        if not has_competitor_share:
            missing.append("缺少 Top品牌/企业份额结构化证据")
        if len(r_items) < 2:
            missing.append("RAG 行业/战略文档补证少于 2 条")
        if not w_items:
            missing.append("缺少外部网页/实时公开来源补证")

        if missing:
            return QualityCheckResult(
                check_name="answer_strategy_evidence_requirements",
                passed=False,
                level=QualityLevel.ACCEPTABLE,
                message="answer strategy 必需证据未满足: " + "；".join(missing),
                details={
                    "missing": missing,
                    "answer_strategy": strategy,
                    "evidence_counts": {
                        "D": len(d_items),
                        "R": len(r_items),
                        "W": len(w_items),
                    },
                },
                suggestions=[
                    "补齐竞品份额、RAG行业文档和外部公开来源后再提升为质量通过",
                    "若外部来源不可用，应将报告显式降级为待验证分析",
                ],
            )

        return QualityCheckResult(
            check_name="answer_strategy_evidence_requirements",
            passed=True,
            level=QualityLevel.EXCELLENT,
            message="answer strategy 要求的竞争结构证据已满足",
            details={"evidence_counts": {"D": len(d_items), "R": len(r_items), "W": len(w_items)}}
        )
    
    def _check_fact_inference_separation(self, result: Dict[str, Any]) -> QualityCheckResult:
        """检查4: 是否区分了事实和推断"""
        facts = result.get("facts", [])
        inferences = result.get("inferences", [])
        answer = result.get("answer", "")
        
        # 有事实但无推断可能是正常的
        # 无事实有推断是有问题的
        
        if not facts and not inferences:
            return QualityCheckResult(
                check_name="fact_inference_separation",
                passed=False,
                level=QualityLevel.POOR,
                message="没有区分事实和推断"
            )
        
        if facts and not inferences:
            return QualityCheckResult(
                check_name="fact_inference_separation",
                passed=True,
                level=QualityLevel.GOOD,
                message="有事实数据，未涉及推断"
            )
        
        if facts and inferences:
            # 检查推断是否有 evidence 支持
            unsupported = [inf for inf in inferences if not inf.get("evidence")]
            if unsupported:
                return QualityCheckResult(
                    check_name="fact_inference_separation",
                    passed=False,
                    level=QualityLevel.ACCEPTABLE,
                    message=f"有 {len(unsupported)} 条推断缺乏证据支撑",
                    suggestions=["为推断添加证据引用"]
                )
            
            return QualityCheckResult(
                check_name="fact_inference_separation",
                passed=True,
                level=QualityLevel.EXCELLENT,
                message="事实和推断已区分，且推断有证据支撑"
            )
        
        if inferences and not facts:
            return QualityCheckResult(
                check_name="fact_inference_separation",
                passed=False,
                level=QualityLevel.POOR,
                message="全为推断，缺乏事实支撑"
            )
        
        return QualityCheckResult(
            check_name="fact_inference_separation",
            passed=False,
            level=QualityLevel.POOR,
            message="无法判断事实/推断分离"
        )

    def _check_evidence_ledger_output(self, result: Dict[str, Any]) -> QualityCheckResult:
        """检查: 是否输出证据账本"""
        ledger = result.get("evidence_ledger") or {}
        evidences = ledger.get("evidences") or []
        summary = ledger.get("summary") or {}

        if not ledger:
            return QualityCheckResult(
                check_name="evidence_ledger_output",
                passed=False,
                level=QualityLevel.FAILED,
                message="没有输出证据账本"
            )

        if not evidences:
            return QualityCheckResult(
                check_name="evidence_ledger_output",
                passed=False,
                level=QualityLevel.FAILED,
                message="证据账本为空"
            )

        if "overall_confidence" not in summary:
            return QualityCheckResult(
                check_name="evidence_ledger_output",
                passed=False,
                level=QualityLevel.POOR,
                message="证据账本缺少总体置信度摘要"
            )

        return QualityCheckResult(
            check_name="evidence_ledger_output",
            passed=True,
            level=QualityLevel.EXCELLENT,
            message=f"已输出证据账本，共 {len(evidences)} 条证据",
            details={"evidence_count": len(evidences)}
        )

    def _check_data_caliber_and_time_range(self, result: Dict[str, Any]) -> QualityCheckResult:
        """检查: 关键事实是否说明数据口径和时间范围"""
        facts = result.get("facts") or []
        evidence_sources = result.get("evidence_sources") or []

        source_facts = list(facts) + list(evidence_sources)
        if not source_facts:
            return QualityCheckResult(
                check_name="data_caliber_and_time_range",
                passed=False,
                level=QualityLevel.FAILED,
                message="没有可检查的数据事实或证据来源"
            )

        missing_time = []
        missing_caliber = []
        for item in source_facts:
            source = item.get("source")
            if source not in ("nl2sql-pg", "rag", "web-search", "external-api"):
                continue
            if not item.get("time_range") or item.get("time_range") == "unknown":
                missing_time.append(item.get("claim") or source)
            if not item.get("data_caliber") or item.get("data_caliber") == "unknown":
                missing_caliber.append(item.get("claim") or source)

        if missing_time or missing_caliber:
            return QualityCheckResult(
                check_name="data_caliber_and_time_range",
                passed=False,
                level=QualityLevel.POOR,
                message=f"存在 {len(missing_time)} 条缺时间范围、{len(missing_caliber)} 条缺数据口径的关键证据",
                details={
                    "missing_time_range": missing_time[:5],
                    "missing_data_caliber": missing_caliber[:5],
                },
                suggestions=["为每条关键事实补充 time_range 和 data_caliber"]
            )

        return QualityCheckResult(
            check_name="data_caliber_and_time_range",
            passed=True,
            level=QualityLevel.GOOD,
            message="关键事实已说明时间范围和数据口径"
        )
    
    def _check_confidence_statement(self, result: Dict[str, Any]) -> QualityCheckResult:
        """检查5: 是否说明了置信度"""
        confidence = result.get("confidence", None)
        confidence_details = result.get("confidence_details", {})
        
        if confidence is None:
            return QualityCheckResult(
                check_name="confidence_statement",
                passed=False,
                level=QualityLevel.POOR,
                message="没有给出置信度评估"
            )
        
        if not isinstance(confidence, (int, float)):
            return QualityCheckResult(
                check_name="confidence_statement",
                passed=False,
                level=QualityLevel.POOR,
                message=f"置信度格式错误: {type(confidence)}"
            )
        
        if confidence < 0 or confidence > 1:
            return QualityCheckResult(
                check_name="confidence_statement",
                passed=False,
                level=QualityLevel.POOR,
                message=f"置信度超出范围: {confidence}"
            )
        
        if confidence >= 0.8:
            level = QualityLevel.EXCELLENT
            message = "置信度高"
        elif confidence >= 0.6:
            level = QualityLevel.GOOD
            message = "置信度中等"
        elif confidence >= 0.4:
            level = QualityLevel.ACCEPTABLE
            message = "置信度较低"
        else:
            level = QualityLevel.POOR
            message = "置信度低，建议补充证据"
        
        details = {"confidence": confidence}
        if confidence_details:
            details.update(confidence_details)
        
        return QualityCheckResult(
            check_name="confidence_statement",
            passed=True,
            level=level,
            message=f"置信度评估: {confidence:.0%} ({message})",
            details=details
        )

    def _check_confidence_factor_model(self, result: Dict[str, Any]) -> QualityCheckResult:
        """检查: 置信度是否由 P3 四因子共同计算"""
        details = result.get("confidence_details") or {}
        required = [
            "data_coverage_factor",
            "rag_coverage_factor",
            "source_credibility_factor",
            "conflict_factor",
        ]
        missing = [item for item in required if item not in details]

        if missing:
            return QualityCheckResult(
                check_name="confidence_factor_model",
                passed=False,
                level=QualityLevel.FAILED,
                message=f"置信度缺少四因子计算详情: {', '.join(missing)}",
                details={"missing": missing},
                suggestions=["使用数据覆盖、RAG 覆盖、来源可信度、冲突程度共同计算置信度"]
            )

        return QualityCheckResult(
            check_name="confidence_factor_model",
            passed=True,
            level=QualityLevel.EXCELLENT,
            message="置信度已包含数据覆盖、RAG 覆盖、来源可信度和冲突程度四因子",
            details={k: details.get(k) for k in required}
        )
    
    def _check_uncertainty_disclosure(self, result: Dict[str, Any]) -> QualityCheckResult:
        """检查6: 是否说明了不确定性和缺口"""
        missing_or_uncertain = result.get("missing_or_uncertain", [])
        answer = result.get("answer", "")
        
        # 如果置信度低，应该有不确定性说明
        confidence = result.get("confidence", 1.0)
        
        if confidence >= 0.7:
            # 高置信度，可以没有不确定性说明
            return QualityCheckResult(
                check_name="uncertainty_disclosure",
                passed=True,
                level=QualityLevel.GOOD,
                message="高置信度，不确定性已在置信度中体现"
            )
        
        # 中低置信度必须有不确定性说明
        if missing_or_uncertain:
            return QualityCheckResult(
                check_name="uncertainty_disclosure",
                passed=True,
                level=QualityLevel.ACCEPTABLE,
                message=f"已说明 {len(missing_or_uncertain)} 项不确定性",
                details={"items": missing_or_uncertain}
            )
        else:
            return QualityCheckResult(
                check_name="uncertainty_disclosure",
                passed=False,
                level=QualityLevel.POOR,
                message=f"置信度 {confidence:.0%} 但未说明不确定性"
            )
    
    def _check_nofabrication(self, result: Dict[str, Any]) -> QualityCheckResult:
        """检查7: 是否有无来源的编造数据"""
        answer = result.get("answer", "")
        evidence_sources = result.get("evidence_sources", [])
        facts = result.get("facts", [])
        
        # 检查答案中是否有明显的数据陈述
        import re
        data_patterns = [
            r"\d+\.?\d*%",  # 百分比
            r"\d{1,3}(?:,\d{3})+(?:\.\d+)?",  # 大数字
            r"\d+\.?\d*\s*(?:万辆|万辆|万辆)",  # 销量单位
        ]
        
        data_claims = []
        for pattern in data_patterns:
            matches = re.findall(pattern, answer)
            data_claims.extend(matches)
        
        # 如果答案中有数据，但没有任何来源
        if data_claims and not evidence_sources:
            return QualityCheckResult(
                check_name="nofabrication",
                passed=False,
                level=QualityLevel.FAILED,
                message="答案包含数据但无任何来源引用",
                suggestions=["为所有数据添加来源"]
            )
        
        # 如果有数据但没有 facts，可能是问题
        if data_claims and not facts:
            return QualityCheckResult(
                check_name="nofabrication",
                passed=True,
                level=QualityLevel.ACCEPTABLE,
                message="有数据但未结构化，建议补充"
            )
        
        return QualityCheckResult(
            check_name="nofabrication",
            passed=True,
            level=QualityLevel.EXCELLENT,
            message="未发现无来源数据"
        )
    
    def _check_next_steps(self, result: Dict[str, Any]) -> QualityCheckResult:
        """检查8: 是否给出可执行的下一步"""
        next_steps = result.get("next_steps", [])
        
        if not next_steps:
            return QualityCheckResult(
                check_name="next_steps",
                passed=False,
                level=QualityLevel.ACCEPTABLE,
                message="没有给出下一步建议"
            )
        
        # 检查下一步是否具体
        generic_steps = ["继续分析", "进一步研究", "更多数据"]
        is_generic = all(any(g in s for g in generic_steps) for s in next_steps)
        
        if is_generic:
            return QualityCheckResult(
                check_name="next_steps",
                passed=True,
                level=QualityLevel.ACCEPTABLE,
                message="下一步建议较笼统",
                suggestions=["使下一步更具体可执行"]
            )
        
        return QualityCheckResult(
            check_name="next_steps",
            passed=True,
            level=QualityLevel.GOOD,
            message=f"提供了 {len(next_steps)} 项具体下一步建议"
        )


def generate_quality_report(check_results: List[QualityCheckResult]) -> str:
    """生成质量报告"""
    lines = ["=" * 50, "质量检查报告", "=" * 50, ""]
    
    passed_count = sum(1 for r in check_results if r.passed)
    total_count = len(check_results)
    
    lines.append(f"通过: {passed_count}/{total_count}")
    lines.append("")
    
    for result in check_results:
        status = "✅" if result.passed else "❌"
        level_emoji = {
            "excellent": "🟢",
            "good": "🔵",
            "acceptable": "🟡",
            "poor": "🟠",
            "failed": "🔴"
        }.get(result.level.value, "⚪")
        
        lines.append(f"{status} [{result.level.value.upper()}] {result.check_name}")
        lines.append(f"   {result.message}")
        
        if result.suggestions:
            lines.append(f"   建议: {'; '.join(result.suggestions)}")
        lines.append("")
    
    return "\n".join(lines)


# 全局质量门禁实例
_quality_gate: QualityGate = None


def get_quality_gate() -> QualityGate:
    global _quality_gate
    if _quality_gate is None:
        _quality_gate = QualityGate()
    return _quality_gate
