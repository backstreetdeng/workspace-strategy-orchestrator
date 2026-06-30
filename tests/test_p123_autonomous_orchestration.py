# -*- coding: utf-8 -*-
"""P1/P2/P3 autonomous market-agent regression tests."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ORCH_ROOT = ROOT / "agents" / "strategy-orchestrator"
if str(ORCH_ROOT) not in sys.path:
    sys.path.insert(0, str(ORCH_ROOT))

from evidence.evidence_ledger import Evidence  # noqa: E402
from executors.orchestrator import StrategyOrchestrator, create_orchestrator  # noqa: E402
from protocols.task_protocol import create_task_from_user_query  # noqa: E402
from tools.targeted_sql_pack import build_targeted_sql_evidences  # noqa: E402


def _targeted_sql_pack_result() -> dict:
    return {
        "success": True,
        "query_mode": "targeted_sql_pack",
        "period_start": 202501,
        "period_end": 202512,
        "blocks": [
            {"name": "market_overview", "purpose": "market base", "row_count": 1,
             "rows": [{"total_sales": 1200000, "brand_count": 12, "model_count": 48}]},
            {"name": "monthly_trend", "purpose": "trend", "row_count": 2,
             "rows": [{"month": 202511, "sales": 98000}, {"month": 202512, "sales": 112000}]},
            {"name": "yoy_change", "purpose": "yoy", "row_count": 2,
             "rows": [{"period": "current", "sales": 1200000}, {"period": "previous_year", "sales": 1000000}]},
            {"name": "competitor_share", "purpose": "share", "row_count": 4,
             "rows": [
                 {"brand": "比亚迪", "sales": 320000, "share_pct": 26.7},
                 {"brand": "特斯拉", "sales": 150000, "share_pct": 12.5},
                 {"brand": "吉利", "sales": 130000, "share_pct": 10.8},
                 {"brand": "理想", "sales": 90000, "share_pct": 7.5},
             ]},
            {"name": "target_brand_performance", "purpose": "target", "row_count": 1,
             "rows": [{"brand": "比亚迪", "sales": 320000, "model_count": 8}]},
            {"name": "model_contribution", "purpose": "model", "row_count": 2,
             "rows": [
                 {"model": "宋PLUS", "brand": "比亚迪", "sales": 120000, "power_type": "PHEV"},
                 {"model": "元PLUS", "brand": "比亚迪", "sales": 90000, "power_type": "BEV"},
             ]},
            {"name": "power_mix", "purpose": "power", "row_count": 2,
             "rows": [{"power_type": "PHEV", "sales": 680000}, {"power_type": "BEV", "sales": 520000}]},
            {"name": "price_and_config", "purpose": "price", "row_count": 1,
             "rows": [{"model": "宋PLUS", "maker": "比亚迪", "price_band": "15-20万", "energy_type": "PHEV"}]},
        ],
    }


def _register_fake_evidence_tools(orchestrator: StrategyOrchestrator) -> None:
    def fake_targeted_sql_pack(param, task, state):
        result = _targeted_sql_pack_result()
        return {**result, "evidences": build_targeted_sql_evidences(result, state.analysis_plan)}

    def fake_rag(param, task, state):
        return {
            "evidences": [
                Evidence(
                    source="rag",
                    tool="golden_vector_retriever",
                    claim="RAG行业报告与政策背景",
                    content="行业报告显示新能源SUV价格带竞争加剧，头部品牌通过成本和渠道优势扩大份额。",
                    time_range=state.analysis_plan.time_range,
                    data_caliber="黄金测试RAG摘要口径",
                    source_url="https://example.com/industry-report",
                    source_date="2026-06-01",
                    source_grade="A",
                    source_credibility=0.74,
                    coverage_dimensions=["行业报告", "政策背景", "趋势解释"],
                    coverage_score=0.74,
                    confidence=0.74,
                ),
                Evidence(
                    source="rag",
                    tool="golden_vector_retriever",
                    claim="RAG竞品战略背景",
                    content="第二份行业材料显示头部品牌通过新品节奏、渠道效率和价格策略形成竞争分层。",
                    time_range=state.analysis_plan.time_range,
                    data_caliber="黄金测试RAG摘要口径",
                    source_url="https://example.com/competitor-report",
                    source_date="2026-06-08",
                    source_grade="A",
                    source_credibility=0.74,
                    coverage_dimensions=["竞品战略", "竞争梯队", "趋势解释"],
                    coverage_score=0.72,
                    confidence=0.72,
                ),
            ]
        }

    def fake_web(param, task, state):
        return {
            "evidence": Evidence(
                source="web-search",
                tool="golden_web_search",
                claim="外部网页实时补证",
                content="外部公开报道验证车企近期产品、价格和竞争动作。",
                time_range=state.analysis_plan.time_range,
                data_caliber="黄金测试网页检索口径",
                source_url="https://example.com/market-news",
                source_date="2026-06-10",
                source_grade="A",
                source_credibility=0.70,
                coverage_dimensions=["外部补证", "近期动作"],
                coverage_score=0.70,
                confidence=0.70,
            )
        }

    orchestrator.register_tool("targeted-sql-pack", fake_targeted_sql_pack)
    orchestrator.register_tool("rag", fake_rag)
    orchestrator.register_tool("web-search", fake_web)


class P123AutonomousOrchestrationTest(unittest.TestCase):
    def test_llm_provider_can_generate_plan(self):
        def llm_provider(context):
            return [
                "targeted-sql-pack:llm_market_metrics",
                "analysis-framework:llm_strategy_frame",
                "report-generator-agent:quality_review",
            ]

        orchestrator = create_orchestrator(llm_plan_provider=llm_provider)
        task = create_task_from_user_query("分析比亚迪市场策略", entities=["比亚迪"])
        state = type("State", (), {
            "replan_queue": [],
            "analysis_plan": None,
            "completed_steps": [],
            "evidence_gaps": [],
            "tool_results": [],
            "cycle": 1,
        })()
        state.analysis_plan = __import__("planning.analysis_plan", fromlist=["build_analysis_plan"]).build_analysis_plan(task)
        plan = orchestrator._plan(task, state)
        self.assertEqual(plan[0], "targeted-sql-pack:llm_market_metrics")
        self.assertIn("report-generator-agent:quality_review", plan)

    def test_skill_fallback_plan_routes_specialist_agents(self):
        orchestrator = StrategyOrchestrator()
        task = create_task_from_user_query(
            "评估15-20万新能源SUV机会、定价和成本风险",
            time_range="最近12个月",
            entities=["新能源SUV", "15-20万"],
        )
        state = type("State", (), {
            "replan_queue": [],
            "analysis_plan": None,
            "completed_steps": [],
            "evidence_gaps": [],
            "tool_results": [],
            "cycle": 1,
        })()
        state.analysis_plan = __import__("planning.analysis_plan", fromlist=["build_analysis_plan"]).build_analysis_plan(task)
        plan = orchestrator._plan(task, state)
        self.assertIn("analysis-framework:automotive_strategy_seven_stage", plan)
        self.assertIn("cost-analyst:cost_pricing_assessment", plan)
        self.assertIn("report-generator-agent:quality_review", plan)

    def test_golden_questions_have_evidence_confidence_and_quality_gate(self):
        cases = json.loads((ROOT / "tests" / "golden_market_questions.json").read_text(encoding="utf-8"))
        for case in cases:
            with self.subTest(case=case["id"]):
                events = []
                orchestrator = StrategyOrchestrator(event_callback=events.append)
                _register_fake_evidence_tools(orchestrator)
                task = create_task_from_user_query(
                    case["query"],
                    time_range=case["time_range"],
                    entities=case["entities"],
                )
                result = orchestrator.execute(task).to_dict()
                completed_tools = {
                    (event.get("detail") or {}).get("step", "").split(":", 1)[0]
                    for event in events
                    if event.get("phase") == "Act"
                }
                completed_tools.update({item.get("tool") for item in result["evidence_ledger"].get("evidences", [])})
                completed_tools.update({item.get("source") for item in result["evidence_ledger"].get("evidences", [])})

                for tool in case["expected_tools"]:
                    self.assertIn(tool, completed_tools, f"{case['id']} missing {tool}")

                self.assertIn("evidence_ledger", result)
                self.assertGreaterEqual(len(result["evidence_ledger"].get("evidences", [])), 4)
                self.assertIn("data_coverage_factor", result["confidence_details"])
                self.assertIn("source_credibility_factor", result["confidence_details"])
                self.assertTrue(
                    "七步法业务战略分析报告" in result["seven_step_report"]
                    or "市场竞争格局分析报告" in result["seven_step_report"]
                )
                self.assertTrue(result["quality_passed"], result.get("failed_quality_checks"))
                self.assertTrue(any(event.get("phase") == "Plan" for event in events))


if __name__ == "__main__":
    unittest.main()
