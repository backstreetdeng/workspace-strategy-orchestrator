# -*- coding: utf-8 -*-
"""Skill-guided planning and framework analysis for strategy-orchestrator.

This adapter makes the automotive-strategy-analysis Skill an executable
contract inside the orchestrator. It does not replace an LLM planner; it gives
the orchestrator a deterministic Skill-grounded fallback when no LLM provider is
configured.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

try:
    from evidence.evidence_ledger import Evidence
except ImportError:  # pragma: no cover - package import path variant
    from ..evidence.evidence_ledger import Evidence


SKILL_RELATIVE_PATH = Path("skills") / "automotive-strategy-analysis" / "SKILL.md"


SEVEN_STAGE_CONTRACT = [
    {
        "id": "problem_definition",
        "label": "问题定义与范围界定",
        "tool_step": "phase-tracker:problem_definition",
        "required_output": "scope.md",
    },
    {
        "id": "path_design",
        "label": "分析路径设计",
        "tool_step": "phase-tracker:analysis_path_design",
        "required_output": "analysis_plan.md",
    },
    {
        "id": "data_collection",
        "label": "多源数据采集",
        "tool_step": "targeted-sql-pack:skill_required_market_metrics",
        "required_output": "raw_data.json",
    },
    {
        "id": "data_validation",
        "label": "数据验证与冲突处理",
        "tool_step": "rag:skill_context_and_validation",
        "required_output": "data_quality.md",
    },
    {
        "id": "framework_analysis",
        "label": "专业框架分析",
        "tool_step": "analysis-framework:automotive_strategy_seven_stage",
        "required_output": "framework_analysis.md",
    },
    {
        "id": "insight_synthesis",
        "label": "洞察综合与战略建议",
        "tool_step": "report-generator:seven_step_business_report",
        "required_output": "strategy_report.md",
    },
    {
        "id": "quality_review",
        "label": "报告复核与交付",
        "tool_step": "report-agent:quality_review",
        "required_output": "quality_review.md",
    },
]


class SkillGuidedPlanner:
    """Generate ReAct steps from an optional LLM provider and the Skill contract."""

    def __init__(
        self,
        workspace_root: Path,
        llm_plan_provider: Optional[Callable[[Dict[str, Any]], Sequence[str]]] = None,
    ) -> None:
        self.workspace_root = Path(workspace_root)
        self.skill_path = self.workspace_root / SKILL_RELATIVE_PATH
        self.llm_plan_provider = llm_plan_provider

    def build_plan(self, task: Any, state: Any) -> Dict[str, Any]:
        context = self._build_context(task, state)
        provider_steps: List[str] = []
        provider_error = ""
        if self.llm_plan_provider is not None:
            try:
                provider_steps = [str(step) for step in self.llm_plan_provider(context) if str(step).strip()]
            except Exception as exc:  # keep fallback alive
                provider_error = str(exc)

        skill_steps = self._skill_fallback_steps(context)
        steps = provider_steps or skill_steps
        return {
            "source": "llm_provider" if provider_steps else "automotive_strategy_skill",
            "steps": steps,
            "provider_error": provider_error,
            "skill_path": str(self.skill_path),
            "stage_contract": SEVEN_STAGE_CONTRACT,
            "context": context,
        }

    def _build_context(self, task: Any, state: Any) -> Dict[str, Any]:
        plan = getattr(state, "analysis_plan", None)
        intent = getattr(task, "user_intent", None)
        return {
            "task_type": getattr(getattr(task, "task_type", None), "value", str(getattr(task, "task_type", ""))),
            "raw_query": getattr(intent, "raw_query", ""),
            "time_range": getattr(intent, "time_range", ""),
            "entities": list(getattr(intent, "entities", []) or []),
            "constraints": list(getattr(intent, "constraints", []) or []),
            "analysis_plan": plan.to_dict() if hasattr(plan, "to_dict") else {},
            "completed_steps": list(getattr(state, "completed_steps", []) or []),
            "evidence_gaps": list(getattr(state, "evidence_gaps", []) or []),
        }

    def _skill_fallback_steps(self, context: Dict[str, Any]) -> List[str]:
        constraints = set(context.get("constraints") or [])
        query = str(context.get("raw_query") or "")
        task_type = str(context.get("task_type") or "")
        steps: List[str] = ["targeted-sql-pack:skill_required_market_metrics"]

        if "no-rag" not in constraints:
            steps.append("rag:skill_context_and_validation")

        if _needs_web(query, task_type) and "no-web" not in constraints:
            steps.append("web-search:skill_external_validation")

        if "no-framework" not in constraints:
            steps.append("analysis-framework:automotive_strategy_seven_stage")

        if _needs_competitor_agent(query, task_type):
            steps.append("competitor-analyst:competitive_positioning")

        if _needs_cost_agent(query):
            steps.append("cost-analyst:cost_pricing_assessment")

        if "no-report" not in constraints:
            steps.append("report-generator:seven_step_business_report")
            steps.append("report-generator-agent:quality_review")

        return steps


def build_framework_analysis(
    *,
    framework: str,
    task: Any,
    state: Any,
    evidence_report: Dict[str, Any],
    workspace_root: Path,
) -> Dict[str, Any]:
    """Apply the seven-stage Skill contract to accepted evidence."""
    plan = getattr(state, "analysis_plan", None)
    plan_dict = plan.to_dict() if hasattr(plan, "to_dict") else {}
    intent = getattr(task, "user_intent", None)
    skill_path = Path(workspace_root) / SKILL_RELATIVE_PATH
    skill_excerpt = _read_skill_excerpt(skill_path)
    evidence_counts = dict(evidence_report.get("by_source") or {})
    confidence = (evidence_report.get("summary") or {}).get("overall_confidence", 0)

    stage_outputs = []
    for stage in SEVEN_STAGE_CONTRACT:
        status = _stage_status(stage["id"], evidence_counts)
        stage_outputs.append(
            {
                **stage,
                "status": status,
                "evidence_basis": _stage_evidence_basis(stage["id"], evidence_counts),
            }
        )

    limitations = _framework_limitations(evidence_counts)
    content = (
        f"Framework={framework}; target={plan_dict.get('target_brand') or plan_dict.get('market_scope')}; "
        f"time_range={plan_dict.get('time_range')}; skill={skill_path}; "
        f"evidence_counts={evidence_counts}; stages="
        + "; ".join(f"{item['label']}:{item['status']}" for item in stage_outputs)
    )

    evidence = Evidence(
        source="analysis-framework",
        tool="automotive-strategy-analysis",
        claim=f"七阶段Skill框架分析: {framework}",
        content=content,
        time_range=plan_dict.get("time_range") or getattr(intent, "time_range", "unknown"),
        metrics=list(plan_dict.get("required_data_fields") or []),
        data_caliber="automotive-strategy-analysis七阶段Skill契约；基于已入账证据的分析推断",
        source_url=str(skill_path),
        source_grade="methodology",
        source_credibility=0.68,
        coverage_dimensions=[
            "问题定义",
            "路径设计",
            "数据采集",
            "数据验证",
            "框架分析",
            "洞察综合",
            "报告复核",
        ],
        coverage_score=_framework_coverage_score(evidence_counts),
        confidence=min(0.78, max(0.45, float(confidence or 0) * 0.9 + 0.12)),
        limitations=limitations,
    )

    return {
        "framework": framework,
        "skill_path": str(skill_path),
        "skill_excerpt": skill_excerpt,
        "stage_outputs": stage_outputs,
        "evidence_counts": evidence_counts,
        "limitations": limitations,
        "evidence": evidence,
    }


def _needs_web(query: str, task_type: str) -> bool:
    return any(token in query for token in ["最新", "近期", "政策", "新闻", "舆情", "发布", "2026"]) or (
        task_type in {"policy_impact", "opportunity_assessment", "comprehensive_research"}
    )


def _needs_competitor_agent(query: str, task_type: str) -> bool:
    return task_type == "competitor_analysis" or any(
        token in query for token in ["竞品", "竞争", "对标", "格局", "份额", "矩阵"]
    )


def _needs_cost_agent(query: str) -> bool:
    return any(token in query for token in ["成本", "价格", "定价", "毛利", "盈利", "ROI", "投资回报"])


def _read_skill_excerpt(path: Path, max_chars: int = 1200) -> str:
    try:
        return path.read_text(encoding="utf-8")[:max_chars]
    except Exception:
        return ""


def _stage_status(stage_id: str, counts: Dict[str, int]) -> str:
    structured = counts.get("nl2sql-pg", 0)
    rag = counts.get("rag", 0)
    web = counts.get("web-search", 0)
    analysis = counts.get("analysis-framework", 0)
    if stage_id in {"problem_definition", "path_design"}:
        return "complete"
    if stage_id == "data_collection":
        return "complete" if structured else "gap"
    if stage_id == "data_validation":
        return "complete" if (structured and (rag or web)) else "partial"
    if stage_id == "framework_analysis":
        return "complete" if structured else "partial"
    if stage_id in {"insight_synthesis", "quality_review"}:
        return "ready" if structured and (rag or web or analysis) else "needs_more_evidence"
    return "partial"


def _stage_evidence_basis(stage_id: str, counts: Dict[str, int]) -> List[str]:
    if stage_id == "data_collection":
        return ["nl2sql-pg"] if counts.get("nl2sql-pg", 0) else []
    if stage_id == "data_validation":
        return [src for src in ["nl2sql-pg", "rag", "web-search"] if counts.get(src, 0)]
    if stage_id in {"framework_analysis", "insight_synthesis", "quality_review"}:
        return [src for src in ["nl2sql-pg", "rag", "web-search", "analysis-framework"] if counts.get(src, 0)]
    return ["user_intent", "analysis_plan"]


def _framework_limitations(counts: Dict[str, int]) -> List[str]:
    limitations = []
    if not counts.get("nl2sql-pg", 0):
        limitations.append("缺少结构化市场数据，框架分析只能作为低置信度假设")
    if not counts.get("rag", 0):
        limitations.append("缺少RAG行业报告/政策材料补证")
    if not counts.get("web-search", 0):
        limitations.append("缺少外部网页实时补证")
    return limitations


def _framework_coverage_score(counts: Dict[str, int]) -> float:
    score = 0.30
    if counts.get("nl2sql-pg", 0):
        score += 0.30
    if counts.get("rag", 0):
        score += 0.18
    if counts.get("web-search", 0):
        score += 0.12
    if counts.get("analysis-framework", 0):
        score += 0.05
    return min(score, 0.85)
