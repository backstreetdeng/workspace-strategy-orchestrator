# -*- coding: utf-8 -*-
"""Return-to-market tool for strategy-orchestrator.

Sends the final delivery package back to market_strategy (小市场) when
chain_status=pass. This closes the loop: strategy-orchestrator -> market_strategy.

Usage in strategy-orchestrator session:
    sessions_send(sessionKey="agent:market_strategy:main", message=<delivery_package_json>)
"""

from __future__ import annotations

import json
from typing import Any, Dict


def build_return_message(
    task_id: str,
    decision: str,
    answer_brief: str,
    facts: list,
    inferences: list,
    recommendations: list,
    risks: list,
    confidence: float,
    evidence_sources: list,
    missing_or_uncertain: list,
    agent_results: list,
    quality_gate: dict,
    execution_trace: list,
    next_steps: list,
    original_user_query: str = "",
    report_path: str = "",
) -> str:
    """Build the final delivery message to send back to market_strategy."""

    package = {
        "schema": "openclaw.market_strategy.delivery.v1",
        "task_id": task_id,
        "source": "strategy-orchestrator",
        "destination": "market_strategy",
        "chain_status": "pass",
        "original_user_query": original_user_query,
        "decision": decision,
        "answer_brief": answer_brief,
        "facts": facts,
        "inferences": inferences,
        "recommendations": recommendations,
        "risks": risks,
        "confidence": confidence,
        "evidence_sources": evidence_sources,
        "missing_or_uncertain": missing_or_uncertain,
        "agent_results": agent_results,
        "quality_gate": quality_gate,
        "execution_trace": execution_trace,
        "next_steps": next_steps,
        "report_path": report_path,
    }

    header = (
        "## 【编排专家 → 小市场】最终决策包\n\n"
        f"**task_id**: {task_id}\n"
        f"**chain_status**: ✅ pass\n\n"
    )

    summary_lines = [
        "---",
        "**最终结论**: " + answer_brief,
        f"**置信度**: {confidence}",
        f"**决策**: {decision}",
        "---",
    ]

    facts_lines = []
    if facts:
        facts_lines.append("\n**事实清单**:")
        for f in facts[:5]:
            facts_lines.append(f"  - {f}")

    inference_lines = []
    if inferences:
        inference_lines.append("\n**关键推断**:")
        for inf in inferences[:5]:
            inf_text = inf if isinstance(inf, str) else str(inf)
            inference_lines.append(f"  - {inf_text}")

    gaps_lines = []
    if missing_or_uncertain:
        gaps_lines.append("\n**数据缺口**:")
        for g in missing_or_uncertain[:5]:
            gaps_lines.append(f"  - {g}")

    sections = [
        header,
        *summary_lines,
        *facts_lines,
        *inference_lines,
        *gaps_lines,
        "\n---\n*此消息由 strategy-orchestrator 自动发送。如需完整结构化 JSON 包，请告知。*",
    ]

    return "\n".join(sections)


def build_return_json(package: Dict[str, Any]) -> str:
    """Build a compact JSON string for the return message."""
    return json.dumps(package, ensure_ascii=False, indent=2)
