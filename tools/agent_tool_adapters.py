# -*- coding: utf-8 -*-
"""Dispatch contracts for real specialist agents.

strategy-orchestrator must not simulate specialist work in Python. This module
keeps the old ``run_specialist_agent`` entrypoint only as a compatibility layer:
it builds a structured task package that the orchestrator should send to a real
OpenClaw Agent with ``sessions_send(agentId=...)``.
"""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Dict


AGENT_ALIAS = {
    "data-agent": "data-agent",
    "analysis-agent": "analysis-agent",
    "report-agent": "report-agent",
    "competitor-analyst": "analysis-agent",
    "cost-analyst": "analysis-agent",
    "report-generator": "report-agent",
    "report-generator-agent": "report-agent",
}


SPECIALIST_RETURN_CONTRACT = {
    "facts": [],
    "inferences": [],
    "evidence_sources": [],
    "confidence": None,
    "gaps": [],
    "conflicts": [],
    "errors": [],
}


def run_specialist_agent(
    *,
    agent_id: str,
    param: str,
    task: Any,
    state: Any,
    workspace_root: Path,
    evidence_report: Dict[str, Any],
) -> Dict[str, Any]:
    """Build a sessions_send task package for a real specialist agent.

    The previous version fabricated competitor/cost/report outputs locally.
    That made Python a hidden execution brain. This version only prepares the
    handoff contract; the caller must send ``message`` to ``target_agent_id``.
    """

    target_agent_id = AGENT_ALIAS.get(agent_id)
    if not target_agent_id:
        raise ValueError(f"Unknown specialist agent alias: {agent_id}")

    task_package = _build_task_package(
        requested_agent_alias=agent_id,
        target_agent_id=target_agent_id,
        param=param,
        task=task,
        state=state,
        workspace_root=workspace_root,
        evidence_report=evidence_report,
    )
    message = _format_sessions_send_message(task_package)
    return {
        "agent_id": target_agent_id,
        "requested_agent_alias": agent_id,
        "mode": "sessions_send_dispatch_package",
        "dispatch_via": "sessions_send",
        "send_instruction": f"sessions_send(agentId='{target_agent_id}', message=<message>)",
        "message": message,
        "task_package": task_package,
        "return_contract": SPECIALIST_RETURN_CONTRACT,
        "note": "No specialist analysis was executed in Python.",
    }


def _build_task_package(
    *,
    requested_agent_alias: str,
    target_agent_id: str,
    param: str,
    task: Any,
    state: Any,
    workspace_root: Path,
    evidence_report: Dict[str, Any],
) -> Dict[str, Any]:
    intent = getattr(task, "user_intent", None)
    plan = getattr(state, "analysis_plan", None)
    task_id = (
        getattr(task, "task_id", None)
        or getattr(state, "task_id", None)
        or getattr(intent, "task_id", None)
        or "strategy-orchestrator-dispatch"
    )
    return {
        "schema": "openclaw.market_strategy.specialist_task.v1",
        "task_id": str(task_id),
        "from_agent": "strategy-orchestrator",
        "target_agent_id": target_agent_id,
        "requested_agent_alias": requested_agent_alias,
        "requested_capability": param,
        "original_question": getattr(intent, "raw_query", ""),
        "target_output": _target_output_for(target_agent_id, requested_agent_alias),
        "time_range": getattr(intent, "time_range", ""),
        "entities": list(getattr(intent, "entities", []) or []),
        "constraints": list(getattr(intent, "constraints", []) or []),
        "analysis_plan": _to_plain(plan),
        "context_state": {
            "completed_steps": list(getattr(state, "completed_steps", []) or []),
            "evidence_gaps": list(getattr(state, "evidence_gaps", []) or []),
            "tool_result_count": len(getattr(state, "tool_results", []) or []),
            "workspace_root": str(workspace_root),
        },
        "evidence_report": evidence_report or {},
        "return_contract": SPECIALIST_RETURN_CONTRACT,
        "quality_requirements": {
            "separate_facts_and_inferences": True,
            "include_evidence_sources": True,
            "include_confidence": True,
            "include_gaps_conflicts_errors": True,
            "do_not_contact_user_directly": True,
            "return_to": "strategy-orchestrator",
        },
    }


def _target_output_for(target_agent_id: str, alias: str) -> str:
    if target_agent_id == "data-agent":
        return "structured data package with facts, sources, confidence, gaps, conflicts, and errors"
    if target_agent_id == "analysis-agent":
        return f"structured strategy analysis package for {alias}"
    if target_agent_id == "report-agent":
        return "professional report package based only on provided data, analysis, and evidence ledger"
    return "structured specialist result package"


def _format_sessions_send_message(task_package: Dict[str, Any]) -> str:
    return (
        "你是被 strategy-orchestrator 调度的执行专家。请严格按以下 JSON 任务包执行，"
        "只返回结构化结果，不直接联系小市场或用户。\n\n"
        "```json\n"
        f"{json.dumps(task_package, ensure_ascii=False, indent=2)}\n"
        "```"
    )


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
