# -*- coding: utf-8 -*-
"""Agent-dispatch planning contracts for strategy-orchestrator.

The previous version treated automotive-strategy-analysis as an executable
Skill inside the orchestrator. That made the orchestrator an executor. This
module now produces controlled handoff steps and task packages for real
execution agents.
"""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence


ANALYSIS_AGENT_SKILL_PATH = (
    Path(r"C:\Users\11489\.openclaw\workspace-analysis-agent")
    / "skills"
    / "automotive-strategy-analysis"
    / "SKILL.md"
)


SEVEN_STAGE_CONTRACT = [
    {
        "id": "problem_definition",
        "label": "Problem definition and scope boundary",
        "owner": "strategy-orchestrator",
        "required_output": "scope",
    },
    {
        "id": "path_design",
        "label": "Analysis path design",
        "owner": "strategy-orchestrator",
        "required_output": "analysis_plan",
    },
    {
        "id": "data_collection",
        "label": "Multi-source data collection",
        "owner": "data-agent",
        "dispatch_step": "data-agent:collect_market_evidence",
        "required_output": "data_package",
    },
    {
        "id": "data_validation",
        "label": "Data validation and conflict handling",
        "owner": "data-agent",
        "dispatch_step": "data-agent:validate_sources_and_conflicts",
        "required_output": "validated_data_package",
    },
    {
        "id": "framework_analysis",
        "label": "Strategy framework analysis",
        "owner": "analysis-agent",
        "dispatch_step": "analysis-agent:automotive_strategy_analysis",
        "required_output": "strategy_analysis_package",
    },
    {
        "id": "insight_synthesis",
        "label": "Insight synthesis and strategic recommendation",
        "owner": "strategy-orchestrator",
        "required_output": "decision_package",
    },
    {
        "id": "report_generation",
        "label": "Professional report generation",
        "owner": "report-agent",
        "dispatch_step": "report-agent:generate_professional_report",
        "required_output": "report_package",
    },
    {
        "id": "quality_review",
        "label": "Quality gate and final handback",
        "owner": "strategy-orchestrator",
        "required_output": "quality_review",
    },
]


class SkillGuidedPlanner:
    """Build a controlled agent-dispatch plan.

    ``llm_plan_provider`` is retained only for compatibility, but its output is
    normalized into the same three execution agents. It must not introduce
    direct Skill/tool execution steps.
    """

    def __init__(
        self,
        workspace_root: Path,
        llm_plan_provider: Optional[Callable[[Dict[str, Any]], Sequence[str]]] = None,
    ) -> None:
        self.workspace_root = Path(workspace_root)
        self.skill_path = ANALYSIS_AGENT_SKILL_PATH
        self.llm_plan_provider = llm_plan_provider

    def build_plan(self, task: Any, state: Any) -> Dict[str, Any]:
        context = self._build_context(task, state)
        provider_steps: List[str] = []
        provider_error = ""
        if self.llm_plan_provider is not None:
            try:
                provider_steps = _normalize_steps(self.llm_plan_provider(context))
            except Exception as exc:
                provider_error = str(exc)

        steps = provider_steps or self._dispatch_fallback_steps(context)
        return {
            "source": "agent_dispatch_contract",
            "steps": steps,
            "provider_error": provider_error,
            "analysis_agent_skill_path": str(self.skill_path),
            "stage_contract": SEVEN_STAGE_CONTRACT,
            "context": context,
            "dispatch_rule": (
                "Use sessions_send(agentId=...) for data-agent, analysis-agent, "
                "and report-agent. Do not run their Skills inside strategy-orchestrator."
            ),
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
            "analysis_type": getattr(intent, "analysis_type", "") or "",
            "analysis_plan": _to_plain(plan),
            "completed_steps": list(getattr(state, "completed_steps", []) or []),
            "evidence_gaps": list(getattr(state, "evidence_gaps", []) or []),
        }

    def _dispatch_fallback_steps(self, context: Dict[str, Any]) -> List[str]:
        constraints = set(context.get("constraints") or [])
        steps: List[str] = []
        if "no-data" not in constraints:
            steps.append("data-agent:collect_market_evidence")
            steps.append("data-agent:validate_sources_and_conflicts")
        if "no-framework" not in constraints:
            steps.append("analysis-agent:automotive_strategy_analysis")
        if "no-report" not in constraints:
            steps.append("report-agent:generate_professional_report")
        return steps


def build_framework_analysis(
    *,
    framework: str,
    task: Any,
    state: Any,
    evidence_report: Dict[str, Any],
    workspace_root: Path,
) -> Dict[str, Any]:
    """Return an analysis-agent dispatch package instead of executing analysis."""

    intent = getattr(task, "user_intent", None)
    plan = getattr(state, "analysis_plan", None)
    task_package = {
        "schema": "openclaw.market_strategy.analysis_task.v1",
        "task_id": str(getattr(task, "task_id", None) or getattr(state, "task_id", None) or "strategy-analysis-dispatch"),
        "from_agent": "strategy-orchestrator",
        "target_agent_id": "analysis-agent",
        "requested_capability": framework,
        "original_question": getattr(intent, "raw_query", ""),
        "target_output": "structured strategy analysis package",
        "time_range": getattr(intent, "time_range", ""),
        "entities": list(getattr(intent, "entities", []) or []),
        "constraints": list(getattr(intent, "constraints", []) or []),
        "analysis_plan": _to_plain(plan),
        "evidence_report": evidence_report or {},
        "skill_reference": str(ANALYSIS_AGENT_SKILL_PATH),
        "return_contract": {
            "facts_used": [],
            "inferences": [],
            "framework_outputs": {},
            "evidence_sources": [],
            "confidence": None,
            "gaps": [],
            "conflicts": [],
            "errors": [],
        },
        "quality_requirements": {
            "use_only_provided_or_sourced_evidence": True,
            "separate_facts_and_inferences": True,
            "return_to": "strategy-orchestrator",
        },
    }
    return {
        "framework": framework,
        "mode": "sessions_send_dispatch_package",
        "agent_id": "analysis-agent",
        "dispatch_via": "sessions_send",
        "send_instruction": "sessions_send(agentId='analysis-agent', message=<message>)",
        "message": _format_sessions_send_message(task_package),
        "task_package": task_package,
        "stage_outputs": _stage_outputs_for_dispatch(),
        "limitations": ["Analysis was not executed in Python; dispatch to analysis-agent is required."],
    }


def _normalize_steps(raw_steps: Sequence[Any]) -> List[str]:
    normalized: List[str] = []
    for raw in raw_steps or []:
        step = str(raw or "").strip()
        if not step:
            continue
        prefix = step.split(":", 1)[0]
        if prefix in {"targeted-sql-pack", "nl2sql-pg", "pg-vector-search", "rag", "web-search"}:
            mapped = "data-agent:collect_market_evidence"
        elif prefix in {"analysis-framework", "automotive-strategy-analysis", "competitor-analyst", "cost-analyst"}:
            mapped = "analysis-agent:automotive_strategy_analysis"
        elif prefix in {"report-generator", "report-generator-agent"}:
            mapped = "report-agent:generate_professional_report"
        elif prefix in {"data-agent", "analysis-agent", "report-agent"} and ":" in step:
            mapped = step
        else:
            continue
        if mapped not in normalized:
            normalized.append(mapped)
    return normalized


def _format_sessions_send_message(task_package: Dict[str, Any]) -> str:
    return (
        "你是 strategy-orchestrator 调度的战略分析专家。请严格按 JSON 任务包执行，"
        "返回结构化战略分析包，不直接联系小市场或用户。\n\n"
        "```json\n"
        f"{json.dumps(task_package, ensure_ascii=False, indent=2)}\n"
        "```"
    )


def _stage_outputs_for_dispatch() -> List[Dict[str, Any]]:
    outputs: List[Dict[str, Any]] = []
    for stage in SEVEN_STAGE_CONTRACT:
        outputs.append(
            {
                **stage,
                "status": "dispatch_required" if stage.get("owner") in {"data-agent", "analysis-agent", "report-agent"} else "orchestrator_owned",
            }
        )
    return outputs


def _to_plain(value: Any) -> Any:
    if value is None:
        return {}
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _to_plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_plain(item) for item in value]
    return str(value)
