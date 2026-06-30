# -*- coding: utf-8 -*-
"""P1 analysis-plan migration tests."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ORCH_ROOT = ROOT / "agents" / "strategy-orchestrator"
if str(ORCH_ROOT) not in sys.path:
    sys.path.insert(0, str(ORCH_ROOT))

from evidence.evidence_ledger import Evidence  # noqa: E402
from executors.orchestrator import ReactState, StrategyOrchestrator, ToolResult  # noqa: E402
from planning.analysis_plan import build_analysis_plan  # noqa: E402
from planning.seven_step_phases import AnalysisPhase  # noqa: E402
from protocols.task_protocol import create_task_from_user_query  # noqa: E402
from tools.targeted_sql_pack import build_targeted_sql_evidences, _period_from_time_range  # noqa: E402


class P1AnalysisPlanTest(unittest.TestCase):
    def test_analysis_plan_explicit_year_overrides_default_time_range(self) -> None:
        task = create_task_from_user_query(
            "分析 2026 年中国新能源乘用车市场竞争格局",
            time_range="最近12个月",
            entities=["新能源乘用车"],
        )

        plan = build_analysis_plan(task)

        self.assertEqual(plan.time_range, "2026年")
        self.assertEqual(plan.month_count, 12)
        self.assertIn("2026年", plan.rag_query)
        self.assertIn("新能源乘用车", plan.market_scope)
        self.assertFalse(plan.answer_strategy["is_target_specific"])
        self.assertEqual(plan.answer_strategy["subject_kind"], "market")
        self.assertIn("SOM/目标销量模板", plan.answer_strategy["must_not_use"])
        self.assertIn("CR3/CR5/CR10集中度", plan.required_data_fields)
        self.assertNotIn("目标品牌或车型/SOM", plan.required_data_fields)

    def test_explicit_year_maps_to_ytd_sql_window(self) -> None:
        self.assertEqual(
            _period_from_time_range(max_month=202602, time_range="2026年"),
            (202601, 202602, 202501, 202502),
        )

    def test_analysis_plan_normalizes_brand_and_time_range(self) -> None:
        task = create_task_from_user_query(
            "小米汽车近半年进入中国新能源SUV市场机会分析",
            time_range="最近12个月",
            entities=["小米"],
        )

        plan = build_analysis_plan(task)

        self.assertEqual(plan.target_brand, "小米")
        self.assertEqual(plan.time_range, "最近6个月")
        self.assertIn("小米", plan.brand_aliases)
        self.assertIn("新能源SUV", plan.market_scope)
        self.assertIn("小米", plan.rag_query)
        self.assertIn("最近6个月", plan.tavily_query)

    def test_orchestrator_tools_share_analysis_plan_and_emit_drw_store(self) -> None:
        orchestrator = StrategyOrchestrator()
        seen = []

        def assert_plan(task, state):
            self.assertIsNotNone(state.analysis_plan)
            self.assertEqual(state.analysis_plan.target_brand, "小米")
            self.assertEqual(state.analysis_plan.time_range, "最近6个月")
            self.assertIn("新能源SUV", state.analysis_plan.market_scope)
            seen.append(state.analysis_plan.to_dict())

        def fake_nl2sql(param, task, state):
            assert_plan(task, state)
            return {
                "evidence": Evidence(
                    source="nl2sql-pg",
                    tool="fake_market_db",
                    claim="结构化数据查询: 小米销量与份额",
                    content="小米最近6个月销量120000辆，覆盖SU7/YU7",
                    time_range=state.analysis_plan.time_range,
                    data_caliber="乘用车结构化销量数据库口径",
                    metrics=["销量", "份额", "趋势", "车型", "动力", "价格"],
                    coverage_dimensions=["时间范围", "口径"],
                    coverage_score=0.9,
                    source_credibility=0.88,
                    confidence=0.86,
                )
            }

        def fake_targeted_sql_pack(param, task, state):
            assert_plan(task, state)
            result = {
                "success": True,
                "query_mode": "targeted_sql_pack",
                "period_start": 202509,
                "period_end": 202602,
                "blocks": [
                    {"name": "market_overview", "purpose": "TAM/SAM market base", "row_count": 1, "rows": [{"total_sales": 100000, "brand_count": 8, "model_count": 20}]},
                    {"name": "monthly_trend", "purpose": "monthly trend", "row_count": 2, "rows": [{"month": 202601, "sales": 9000}, {"month": 202602, "sales": 11000, "mom_pct": 22.2}]},
                    {"name": "yoy_change", "purpose": "year-on-year comparison", "row_count": 2, "rows": [{"period": "current", "sales": 20000, "yoy_pct": 30.0}, {"period": "previous_year", "sales": 15384}]},
                    {"name": "competitor_share", "purpose": "competitor share", "row_count": 2, "rows": [{"brand": "小米", "sales": 20000, "share_pct": 20.0}, {"brand": "比亚迪", "sales": 30000, "share_pct": 30.0}]},
                    {"name": "target_brand_performance", "purpose": "target brand SOM", "row_count": 1, "rows": [{"brand": "小米", "sales": 20000, "model_count": 3}]},
                    {"name": "model_contribution", "purpose": "model contribution", "row_count": 2, "rows": [{"model": "小米SU7", "sales": 14000}, {"model": "小米YU7", "sales": 6000}]},
                    {"name": "power_mix", "purpose": "powertrain mix", "row_count": 1, "rows": [{"power_type": "纯电动", "sales": 20000}]},
                    {"name": "price_and_config", "purpose": "price band and config", "row_count": 1, "rows": [{"model": "小米SU7", "price_band": "20-30万"}]},
                ],
            }
            return {**result, "evidences": build_targeted_sql_evidences(result, state.analysis_plan)}

        def fake_rag(param, task, state):
            assert_plan(task, state)
            self.assertIn("小米", state.analysis_plan.rag_query)
            return {
                "evidence": Evidence(
                    source="rag",
                    tool="fake_vector_retriever",
                    claim="RAG 检索: 小米战略背景",
                    content="小米汽车相关业务文档支持品牌进入策略分析",
                    time_range=f"用户问题时间范围: {state.analysis_plan.time_range}；文档发布日期以元数据为准",
                    data_caliber="向量检索文档摘要口径",
                    coverage_dimensions=["行业报告", "趋势解释"],
                    coverage_score=0.7,
                    source_credibility=0.72,
                    confidence=0.72,
                )
            }

        def fake_web(param, task, state):
            assert_plan(task, state)
            self.assertIn("小米", state.analysis_plan.tavily_query)
            return {
                "evidences": [
                    Evidence(
                        source="web-search",
                        tool="fake_tavily",
                        claim="Tavily 外部补证: 小米交付动态",
                        content="title=小米汽车交付动态; url=https://www.mi.com/auto/news; date=2026-06; source_grade=A; rejection_reason=accepted",
                        time_range=f"{state.analysis_plan.time_range}; source_date=2026-06",
                        data_caliber="Tavily 外部网页检索口径；按实体匹配和来源等级过滤",
                        source_url="https://www.mi.com/auto/news",
                        source_date="2026-06",
                        source_credibility=0.85,
                        coverage_dimensions=["外部补证", "URL", "来源日期", "来源等级", "剔除原因"],
                        coverage_score=0.8,
                        confidence=0.78,
                    )
                ]
            }

        def fake_framework(param, task, state):
            assert_plan(task, state)
            return {
                "evidence": Evidence(
                    source="analysis-framework",
                    tool="swot",
                    claim="框架分析: 小米机会判断",
                    content="基于D/R/W证据形成SWOT判断",
                    time_range=state.analysis_plan.time_range,
                    data_caliber="基于已入账证据的分析框架推断",
                    coverage_dimensions=["推断", "战略框架"],
                    coverage_score=0.6,
                    source_credibility=0.60,
                    confidence=0.65,
                )
            }

        orchestrator.register_tool("targeted-sql-pack", fake_targeted_sql_pack)
        orchestrator.register_tool("nl2sql-pg", fake_nl2sql)
        orchestrator.register_tool("rag", fake_rag)
        orchestrator.register_tool("web-search", fake_web)
        orchestrator.register_tool("analysis-framework", fake_framework)

        task = create_task_from_user_query(
            "小米汽车近半年进入中国新能源SUV市场机会分析",
            time_range="最近12个月",
            entities=["小米"],
        )
        result = orchestrator.execute(task).to_dict()

        self.assertGreaterEqual(len(seen), 3)
        self.assertEqual(result["analysis_plan"]["target_brand"], "小米")
        self.assertEqual(result["analysis_plan"]["time_range"], "最近6个月")
        self.assertGreaterEqual(result["evidence_store"]["summary"]["structured"], 8)
        self.assertEqual(result["evidence_store"]["summary"]["rag"], 1)
        self.assertEqual(result["evidence_store"]["summary"]["web"], 1)
        self.assertEqual(result["evidence_store"]["D"][0]["id"], "D1")
        self.assertEqual(result["evidence_store"]["R"][0]["id"], "R1")
        self.assertEqual(result["evidence_store"]["W"][0]["id"], "W1")
        targeted_claims = [item["claim"] for item in result["evidence_store"]["D"]]
        self.assertTrue(any("monthly_trend" in claim for claim in targeted_claims))
        self.assertTrue(any("yoy_change" in claim for claim in targeted_claims))
        self.assertTrue(any("model_contribution" in claim for claim in targeted_claims))
        self.assertTrue(any("price_and_config" in claim for claim in targeted_claims))

    def test_reflection_replans_when_targeted_sql_blocks_are_missing(self) -> None:
        orchestrator = StrategyOrchestrator()
        calls = {"targeted": 0}

        def fake_targeted_sql_pack(param, task, state):
            calls["targeted"] += 1
            complete_blocks = [
                {"name": "market_overview", "purpose": "TAM/SAM market base", "row_count": 1, "rows": [{"total_sales": 100000}]},
                {"name": "monthly_trend", "purpose": "monthly trend", "row_count": 2, "rows": [{"month": 202601, "sales": 9000}, {"month": 202602, "sales": 11000}]},
                {"name": "yoy_change", "purpose": "year-on-year comparison", "row_count": 2, "rows": [{"period": "current", "sales": 20000}, {"period": "previous_year", "sales": 15000}]},
                {"name": "competitor_share", "purpose": "competitor share", "row_count": 2, "rows": [{"brand": "小米", "sales": 20000}, {"brand": "比亚迪", "sales": 30000}]},
                {"name": "target_brand_performance", "purpose": "target brand SOM", "row_count": 1, "rows": [{"brand": "小米", "sales": 20000}]},
                {"name": "model_contribution", "purpose": "model contribution", "row_count": 1, "rows": [{"model": "小米SU7", "sales": 20000}]},
                {"name": "power_mix", "purpose": "powertrain mix", "row_count": 1, "rows": [{"power_type": "纯电动", "sales": 20000}]},
                {"name": "price_and_config", "purpose": "price band and config", "row_count": 1, "rows": [{"model": "小米SU7", "price_band": "20-30万"}]},
            ]
            blocks = complete_blocks[:4] if calls["targeted"] == 1 else complete_blocks
            result = {
                "success": True,
                "query_mode": "targeted_sql_pack",
                "period_start": 202509,
                "period_end": 202602,
                "blocks": blocks,
            }
            return {**result, "evidences": build_targeted_sql_evidences(result, state.analysis_plan)}

        def fake_nl2sql(param, task, state):
            return {"evidence": Evidence(
                source="nl2sql-pg", tool="fake_market_db", claim="ad hoc SQL",
                content="小米销量 20000", time_range=state.analysis_plan.time_range,
                data_caliber="fake DB", metrics=["销量"],
                coverage_dimensions=["时间范围", "口径"], coverage_score=0.75,
                source_credibility=0.88, confidence=0.8)}

        orchestrator.register_tool("targeted-sql-pack", fake_targeted_sql_pack)
        orchestrator.register_tool("nl2sql-pg", fake_nl2sql)
        task = create_task_from_user_query(
            "小米最近半年销量数据",
            time_range="最近6个月",
            entities=["小米"],
        )
        task.max_react_cycles = 2
        result = orchestrator.execute(task).to_dict()

        self.assertEqual(calls["targeted"], 2)
        self.assertEqual(result["cycles_used"], 2)
        self.assertTrue(result["replan_history"])
        self.assertIn("model_contribution", result["reflection"]["structured_blocks"])
        self.assertEqual(result["reflection"]["missing_targeted_sql_blocks"], [])

    def test_reflection_detects_stagnation_and_strategic_alert(self) -> None:
        orchestrator = StrategyOrchestrator()
        calls = {"targeted": 0}

        def incomplete_targeted_sql_pack(param, task, state):
            calls["targeted"] += 1
            result = {
                "success": True,
                "query_mode": "targeted_sql_pack",
                "period_start": 202601,
                "period_end": 202602,
                "blocks": [
                    {"name": "market_overview", "purpose": "market base", "row_count": 1, "rows": [{"total_sales": 100000}]},
                    {"name": "monthly_trend", "purpose": "monthly trend", "row_count": 2, "rows": [{"month": 202601, "sales": 45000}, {"month": 202602, "sales": 55000}]},
                    {"name": "yoy_change", "purpose": "year-on-year", "row_count": 2, "rows": [{"period": "current", "sales": 100000}, {"period": "previous_year", "sales": 90000}]},
                    {"name": "competitor_share", "purpose": "competitor share", "row_count": 1, "rows": [{"brand": "TestBrand", "sales": 100000}]},
                ],
            }
            return {**result, "evidences": build_targeted_sql_evidences(result, state.analysis_plan)}

        def stable_nl2sql(param, task, state):
            return {"evidence": Evidence(
                source="nl2sql-pg", tool="fake_market_db", claim="stable sales",
                content="stable structured evidence", time_range=state.analysis_plan.time_range,
                data_caliber="fake DB", metrics=["sales"],
                coverage_dimensions=["time_range"], coverage_score=0.7,
                source_credibility=0.88, confidence=0.8)}

        orchestrator.register_tool("targeted-sql-pack", incomplete_targeted_sql_pack)
        orchestrator.register_tool("nl2sql-pg", stable_nl2sql)
        task = create_task_from_user_query(
            "TestBrand sales data",
            time_range="last 2 months",
            entities=["TestBrand"],
        )
        task.max_react_cycles = 2

        result = orchestrator.execute(task).to_dict()

        self.assertEqual(calls["targeted"], 2)
        self.assertTrue(result["reflection"]["is_stagnant"])
        self.assertGreaterEqual(result["reflection"]["stagnation_count"], 1)
        self.assertTrue(result["reflection"]["strategic_alert"])
        self.assertTrue(
            any(item["reason"] == "strategic_pivot" for item in result["replan_history"]),
            result["replan_history"],
        )

    def test_phase_tracker_enforces_requirements_before_advancing(self) -> None:
        orchestrator = StrategyOrchestrator()
        task = create_task_from_user_query(
            "Analyze TestBrand market strategy",
            time_range="last 12 months",
            entities=["TestBrand"],
        )
        state = ReactState(analysis_plan=build_analysis_plan(task))
        state.tool_results = [
            ToolResult(
                tool_name="targeted-sql-pack",
                success=True,
                result={
                    "blocks": [
                        {"name": "market_overview", "row_count": 1},
                        {"name": "monthly_trend", "row_count": 1},
                        {"name": "yoy_change", "row_count": 1},
                        {"name": "competitor_share", "row_count": 1},
                    ]
                },
            )
        ]
        state.reflection = {"overall_confidence": 0.65, "evidence_gaps": [], "conflicts": []}

        moved, phase, reasons = orchestrator.run_phase(state.current_phase, task, state)

        self.assertTrue(moved)
        self.assertEqual(phase, AnalysisPhase.DATA_COLLECTION.value)
        self.assertIn("missing:rag_context", reasons)
        self.assertEqual(state.current_phase, AnalysisPhase.DATA_COLLECTION.value)

        state.tool_results.append(ToolResult(tool_name="rag", success=True, result={"results": ["context"]}))
        state.completed_steps.append("analysis-framework:trend_analysis")
        moved, phase, reasons = orchestrator.run_phase(state.current_phase, task, state)

        self.assertTrue(moved)
        self.assertEqual(phase, AnalysisPhase.REPORT_GENERATION.value)
        self.assertIn("missing:answer_drafted", reasons)
        self.assertEqual(state.current_phase, AnalysisPhase.REPORT_GENERATION.value)


if __name__ == "__main__":
    unittest.main()
