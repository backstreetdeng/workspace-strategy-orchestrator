# -*- coding: utf-8 -*-
"""P2 seven-step report migration tests."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ORCH_ROOT = ROOT / "agents" / "strategy-orchestrator"
if str(ORCH_ROOT) not in sys.path:
    sys.path.insert(0, str(ORCH_ROOT))

from evidence.evidence_ledger import Evidence  # noqa: E402
from executors.orchestrator import ReactState, StrategyOrchestrator  # noqa: E402
from planning.analysis_plan import build_analysis_plan  # noqa: E402
from protocols.task_protocol import create_task_from_user_query  # noqa: E402
from reporting.seven_step_report import build_seven_step_report  # noqa: E402
from tools.targeted_sql_pack import build_targeted_sql_evidences  # noqa: E402


def _targeted_pack_result() -> dict:
    return {
        "success": True,
        "query_mode": "targeted_sql_pack",
        "period_start": 202501,
        "period_end": 202506,
        "blocks": [
            {
                "name": "market_overview",
                "purpose": "TAM/SAM market base",
                "row_count": 1,
                "rows": [
                    {
                        "total_sales": 100000,
                        "brand_count": 8,
                        "model_count": 20,
                        "period_start": 202501,
                        "period_end": 202506,
                    }
                ],
            },
            {
                "name": "monthly_trend",
                "purpose": "monthly trend",
                "row_count": 2,
                "rows": [
                    {"month": 202505, "sales": 18000, "mom_pct": 5.2},
                    {"month": 202506, "sales": 22000, "mom_pct": 22.2},
                ],
            },
            {
                "name": "yoy_change",
                "purpose": "year-on-year comparison",
                "row_count": 2,
                "rows": [
                    {"period": "current", "sales": 100000, "yoy_pct": 30.0},
                    {"period": "previous_year", "sales": 77000},
                ],
            },
            {
                "name": "competitor_share",
                "purpose": "competitor share",
                "row_count": 2,
                "rows": [
                    {"brand": "BYD", "sales": 36000, "share_pct": 36.0},
                    {"brand": "Tesla", "sales": 24000, "share_pct": 24.0},
                ],
            },
            {
                "name": "target_brand_performance",
                "purpose": "target brand SOM",
                "row_count": 1,
                "rows": [{"brand": "BYD", "sales": 36000, "model_count": 3}],
            },
            {
                "name": "model_contribution",
                "purpose": "model contribution",
                "row_count": 2,
                "rows": [
                    {"model": "BYD Song Plus", "brand": "BYD", "sales": 21000, "power_type": "PHEV"},
                    {"model": "BYD Yuan Plus", "brand": "BYD", "sales": 15000, "power_type": "BEV"},
                ],
            },
            {
                "name": "power_mix",
                "purpose": "powertrain mix",
                "row_count": 2,
                "rows": [
                    {"power_type": "PHEV", "sales": 21000, "model_count": 1},
                    {"power_type": "BEV", "sales": 15000, "model_count": 1},
                ],
            },
            {
                "name": "price_and_config",
                "purpose": "price band and config",
                "row_count": 1,
                "rows": [
                    {
                        "model": "BYD Song Plus",
                        "maker": "BYD",
                        "energy_type": "PHEV",
                        "level": "SUV",
                        "guide_price": "150000-180000",
                        "price_band": "15-20万",
                    }
                ],
            },
        ],
    }


class P2SevenStepReportTest(unittest.TestCase):
    def test_orchestrator_returns_seven_step_report_and_insight_cards(self) -> None:
        orchestrator = StrategyOrchestrator()

        def fake_targeted_sql_pack(param, task, state):
            result = _targeted_pack_result()
            return {**result, "evidences": build_targeted_sql_evidences(result, state.analysis_plan)}

        def fake_nl2sql(param, task, state):
            return {
                "evidence": Evidence(
                    source="nl2sql-pg",
                    tool="fake_market_db",
                    claim="BYD structured sales evidence",
                    content="BYD sales 36000 and share 36%",
                    time_range=state.analysis_plan.time_range,
                    data_caliber="fake DB",
                    metrics=["sales", "share"],
                    coverage_dimensions=["time", "brand"],
                    coverage_score=0.75,
                    source_credibility=0.88,
                    confidence=0.8,
                )
            }

        def fake_rag(param, task, state):
            return {
                "evidence": Evidence(
                    source="rag",
                    tool="fake_vector_retriever",
                    claim="BYD strategic background",
                    content="industry report supports BYD cost and channel advantage",
                    time_range=state.analysis_plan.time_range,
                    data_caliber="vector retrieval",
                    coverage_dimensions=["industry report", "strategy"],
                    coverage_score=0.7,
                    source_credibility=0.72,
                    confidence=0.72,
                    source_url="https://example.com/byd-report.pdf",
                    source_date="2026-06-01",
                    source_grade="A",
                )
            }

        def fake_web(param, task, state):
            return {
                "evidence": Evidence(
                    source="web-search",
                    tool="fake_web",
                    claim="BYD recent market proof",
                    content="external article confirms recent product updates",
                    time_range=state.analysis_plan.time_range,
                    data_caliber="web search",
                    coverage_dimensions=["external validation"],
                    coverage_score=0.65,
                    source_credibility=0.7,
                    confidence=0.68,
                    source_url="https://example.com/byd-news",
                    source_date="2026-06-05",
                    source_grade="B",
                )
            }

        def fake_framework(param, task, state):
            return {
                "evidence": Evidence(
                    source="analysis-framework",
                    tool=param,
                    claim=f"framework analysis {param}",
                    content="framework inference based on accepted evidence",
                    time_range=state.analysis_plan.time_range,
                    data_caliber="inference from ledger evidence",
                    coverage_dimensions=["inference"],
                    coverage_score=0.55,
                    source_credibility=0.6,
                    confidence=0.62,
                )
            }

        orchestrator.register_tool("targeted-sql-pack", fake_targeted_sql_pack)
        orchestrator.register_tool("nl2sql-pg", fake_nl2sql)
        orchestrator.register_tool("rag", fake_rag)
        orchestrator.register_tool("web-search", fake_web)
        orchestrator.register_tool("analysis-framework", fake_framework)

        task = create_task_from_user_query(
            "Analyze BYD opportunity in China new energy SUV market",
            time_range="last 6 months",
            entities=["BYD"],
        )
        result = orchestrator.execute(task).to_dict()

        report = result["seven_step_report"]
        self.assertIn("七步法业务战略分析报告", report)
        for heading in [
            "第一步：问题定义与范围界定",
            "第二步：市场规模估算（TAM/SAM/SOM）",
            "第三步：竞品矩阵分析",
            "第四步：SWOT+ 分析",
            "第五步：Porter 五力模型",
            "第六步：商业模式拆解",
            "第七步：洞察报告生成",
        ]:
            self.assertIn(heading, report)
        self.assertIn("D1", report)
        self.assertIn("R1", report)
        self.assertIn("W1", report)
        self.assertGreaterEqual(len(result["insight_cards"]), 3)
        self.assertTrue(all("evidence_ids" in card for card in result["insight_cards"]))
        self.assertIn("quality_passed", result["quality_summary"])

    def test_report_generator_tool_uses_orchestrator_seven_step_builder(self) -> None:
        orchestrator = StrategyOrchestrator()
        task = create_task_from_user_query(
            "Analyze BYD opportunity",
            time_range="last 6 months",
            entities=["BYD"],
        )
        state = ReactState(analysis_plan=build_analysis_plan(task))
        evidence = build_targeted_sql_evidences(_targeted_pack_result(), state.analysis_plan)[0]
        orchestrator.evidence_ledger.add_evidence(
            source=evidence.source,
            tool=evidence.tool,
            claim=evidence.claim,
            content=evidence.content,
            time_range=evidence.time_range,
            metrics=evidence.metrics,
            data_caliber=evidence.data_caliber,
            source_credibility=evidence.source_credibility,
            coverage_dimensions=evidence.coverage_dimensions,
            coverage_score=evidence.coverage_score,
            confidence=evidence.confidence,
        )

        generated = orchestrator._tool_report_generate("", task, state)

        self.assertEqual(generated["report"], generated["seven_step_report"])
        self.assertIn("七步法业务战略分析报告", generated["seven_step_report"])
        self.assertTrue(generated["insight_cards"])

    def test_market_competition_question_does_not_use_target_som_template(self) -> None:
        task = create_task_from_user_query(
            "分析 2026 年中国新能源乘用车市场竞争格局",
            time_range="最近12个月",
            entities=["新能源乘用车"],
        )
        plan = build_analysis_plan(task).to_dict()
        evidence_store = {
            "D": [
                {
                    "id": "D1",
                    "claim": "targeted_sql_pack/market_overview: market base",
                    "content": 'block=market_overview; sample=[{"total_sales":868726,"brand_count":153,"model_count":426,"period_start":202601,"period_end":202602}]',
                    "data_caliber": "targeted_sql_pack; period=202601 - 202602",
                },
                {
                    "id": "D2",
                    "claim": "targeted_sql_pack/monthly_trend: monthly trend",
                    "content": 'block=monthly_trend; sample=[{"month":202601,"sales":416000,"mom_pct":-3.2},{"month":202602,"sales":452726,"mom_pct":8.8}]',
                    "data_caliber": "targeted_sql_pack; period=202601 - 202602",
                },
                {
                    "id": "D3",
                    "claim": "targeted_sql_pack/competitor_share: competitor share",
                    "content": 'block=competitor_share; sample=[{"brand":"比亚迪汽车工业有限公司","sales":142643,"share_pct":16.42,"model_count":46},{"brand":"浙江吉利汽车有限公司","sales":64192,"share_pct":7.39,"model_count":41},{"brand":"特斯拉汽车有限公司","sales":58610,"share_pct":6.75,"model_count":2},{"brand":"理想汽车","sales":42000,"share_pct":4.83,"model_count":5},{"brand":"重庆长安汽车股份有限公司","sales":39000,"share_pct":4.49,"model_count":28}]',
                    "data_caliber": "targeted_sql_pack; period=202601 - 202602",
                },
            ],
            "R": [{"id": "R1", "claim": "RAG行业报告", "content": "2026年新能源竞争加剧"}],
            "W": [],
            "A": [],
        }

        report = build_seven_step_report(
            task_id=task.task_id,
            question=task.user_intent.raw_query,
            analysis_plan=plan,
            evidence_store=evidence_store,
            confidence=0.749,
            confidence_details={
                "data_coverage_factor": 0.868,
                "rag_coverage_factor": 0.539,
                "source_credibility_factor": 0.793,
                "conflict_factor": 1.0,
                "confidence": 0.749,
            },
            quality_summary={"quality_passed": False, "failed_checks": [{"check": "web_evidence_missing"}]},
        )

        self.assertIn("市场竞争格局分析报告", report)
        self.assertIn("CR3=", report)
        self.assertIn("Top品牌/企业份额", report)
        self.assertIn("不使用目标对象/SOM模板", report)
        self.assertNotIn("目标销量约", report)
        self.assertNotIn("第二步：市场规模估算（TAM/SAM/SOM）", report)
        self.assertNotIn("- **目标对象**", report)


if __name__ == "__main__":
    unittest.main()
