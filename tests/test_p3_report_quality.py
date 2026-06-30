# -*- coding: utf-8 -*-
import sys, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
ORCH_ROOT = ROOT / "agents" / "strategy-orchestrator"
if str(ORCH_ROOT) not in sys.path:
    sys.path.insert(0, str(ORCH_ROOT))
from evidence.evidence_ledger import Evidence, EvidenceLedger
from executors.orchestrator import StrategyOrchestrator
from planning.analysis_plan import build_analysis_plan
from protocols.task_protocol import create_task_from_user_query
from quality.quality_gate import get_quality_gate
from tools.targeted_sql_pack import build_targeted_sql_evidences

class P3ReportQualityTest(unittest.TestCase):

    def _register_targeted_sql_pack(self, orchestrator):
        def fake_targeted_sql_pack(p, t, s):
            result = {
                "success": True,
                "query_mode": "targeted_sql_pack",
                "period_start": 202503,
                "period_end": 202602,
                "blocks": [
                    {"name": "market_overview", "purpose": "market base", "row_count": 1, "rows": [{"total_sales": 1000000}]},
                    {"name": "monthly_trend", "purpose": "monthly trend", "row_count": 2, "rows": [{"month": 202601, "sales": 90000}, {"month": 202602, "sales": 110000}]},
                    {"name": "yoy_change", "purpose": "yoy", "row_count": 2, "rows": [{"period": "current", "sales": 200000}, {"period": "previous_year", "sales": 150000}]},
                    {"name": "competitor_share", "purpose": "competitor share", "row_count": 2, "rows": [{"brand": "BYD", "sales": 250000}, {"brand": "Tesla", "sales": 90000}]},
                    {"name": "target_brand_performance", "purpose": "target brand", "row_count": 1, "rows": [{"brand": "BYD", "sales": 250000}]},
                    {"name": "model_contribution", "purpose": "model contribution", "row_count": 1, "rows": [{"model": "BYD model", "sales": 120000}]},
                    {"name": "power_mix", "purpose": "power mix", "row_count": 1, "rows": [{"power_type": "BEV", "sales": 250000}]},
                    {"name": "price_and_config", "purpose": "price config", "row_count": 1, "rows": [{"model": "BYD model", "price_band": "100k-200k"}]},
                ],
            }
            return {**result, "evidences": build_targeted_sql_evidences(result, s.analysis_plan)}

        orchestrator.register_tool("targeted-sql-pack", fake_targeted_sql_pack)

    def test_confidence_uses_p3_four_factor_model(self):
        ledger = EvidenceLedger()
        ledger.add_evidence(
            source="nl2sql-pg", tool="market_db",
            claim="BYD sales and share",
            content="BYD last 12 months sales 1M units, share 25%",
            time_range="last 12 months",
            data_caliber="passenger car structured sales DB",
            metrics=["sales", "share", "trend", "model", "powertrain", "price"],
            coverage_dimensions=["time_range", "caliber"],
            coverage_score=0.9, source_credibility=0.88, confidence=0.86)
        ledger.add_evidence(
            source="rag", tool="vector_retriever",
            claim="BYD strategic background",
            content="industry report shows BYD strengthening cost advantage",
            time_range="user time_range: last 12 months",
            data_caliber="vector retrieval doc summary caliber",
            coverage_dimensions=["industry report", "trend explanation"],
            coverage_score=0.7, source_credibility=0.72, confidence=0.72)
        confidence, details = ledger.calculate_overall_confidence()
        self.assertGreater(confidence, 0.6)
        for key in ("data_coverage_factor", "rag_coverage_factor",
                    "source_credibility_factor", "conflict_factor", "model"):
            self.assertIn(key, details)

    def test_quality_gate_requires_caliber_and_confidence_factors(self):
        result = {
            "user_intent": {"raw_query": "analyze BYD market strategy",
             "time_range": "last 12 months", "entities": ["BYD"]},
            "answer": "Analysis scope last 12 months for BYD evidence ledger E1",
            "facts": [{"claim": "BYD sales and share", "content": "1M units share 25%",
             "source": "nl2sql-pg", "time_range": "last 12 months",
             "data_caliber": "passenger car structured sales DB",
             "confidence": 0.86, "evidence": {"evidence_id": "E1"}}],
            "inferences": [{"claim": "share gap is core barrier",
             "source": "analysis-framework", "confidence": 0.65,
             "evidence": {"evidence_id": "E1"}}],
            "confidence": 0.74,
            "confidence_details": {"data_coverage_factor": 0.9, "rag_coverage_factor": 0.65,
             "source_credibility_factor": 0.8, "conflict_factor": 1.0},
            "evidence_sources": [{"source": "nl2sql-pg", "tool": "market_db",
             "claim": "BYD sales and share", "time_range": "last 12 months",
             "data_caliber": "passenger car structured sales DB"}],
            "evidence_ledger": {"summary": {"overall_confidence": 0.74},
             "evidences": [{"evidence_id": "E1"}]},
            "missing_or_uncertain": [],
            "next_steps": ["add competitor segment breakdown"],
        }
        passed, checks = get_quality_gate().run_all(result)
        failed = [item.check_name for item in checks if not item.passed]
        self.assertTrue(passed, failed)

    def test_market_competition_strategy_fails_without_external_evidence(self):
        task = create_task_from_user_query(
            "分析 2026 年中国新能源乘用车市场竞争格局",
            time_range="最近12个月",
            entities=["新能源乘用车"],
        )
        plan = build_analysis_plan(task).to_dict()
        result = {
            "user_intent": task.user_intent.to_dict(),
            "analysis_plan": plan,
            "answer": "分析 2026年 新能源乘用车 市场竞争格局，包含D1竞品份额和CR3。",
            "facts": [{"claim": "market size", "content": "868726 units",
                       "source": "nl2sql-pg", "time_range": "2026年",
                       "data_caliber": "targeted_sql_pack", "confidence": 0.8,
                       "evidence": {"evidence_id": "D1"}}],
            "inferences": [{"claim": "competition remains fragmented",
                            "source": "analysis-framework", "confidence": 0.65,
                            "evidence": {"evidence_id": "D2"}}],
            "confidence": 0.749,
            "confidence_details": {"data_coverage_factor": 0.868, "rag_coverage_factor": 0.539,
                                   "source_credibility_factor": 0.793, "conflict_factor": 1.0},
            "evidence_sources": [
                {"source": "nl2sql-pg", "tool": "targeted_sql_pack",
                 "claim": "targeted_sql_pack/competitor_share", "time_range": "2026年",
                 "data_caliber": "targeted_sql_pack; period=202601 - 202602"},
                {"source": "rag", "tool": "fake_vector",
                 "claim": "RAG industry report", "time_range": "2026年",
                 "data_caliber": "vector retrieval"},
            ],
            "evidence_store": {
                "D": [{"id": "D1", "claim": "targeted_sql_pack/competitor_share",
                       "content": "block=competitor_share; sample=[]",
                       "data_caliber": "targeted_sql_pack; period=202601 - 202602"}],
                "R": [{"id": "R1", "claim": "RAG industry report"}],
                "W": [],
                "A": [],
            },
            "evidence_ledger": {"summary": {"overall_confidence": 0.749},
                                "evidences": [{"evidence_id": "D1"}, {"evidence_id": "R1"}]},
            "missing_or_uncertain": [],
            "next_steps": ["补充外部网页来源"],
        }

        passed, checks = get_quality_gate().run_all(result)
        failed = [item.check_name for item in checks if not item.passed]

        self.assertFalse(passed)
        self.assertIn("answer_strategy_evidence_requirements", failed)

    def test_orchestrator_p3_quality_payload(self):
        orchestrator = StrategyOrchestrator()
        self._register_targeted_sql_pack(orchestrator)
        def fake_nl2sql(p, t, s):
            return {"evidence": Evidence(source="nl2sql-pg", tool="fake_market_db",
                claim="structured query BYD sales", content="1M units share 25%",
                time_range=t.user_intent.time_range,
                data_caliber="passenger car structured sales DB",
                metrics=["sales","share","trend","model","powertrain","price"],
                coverage_dimensions=["time_range","caliber"],
                coverage_score=0.9, source_credibility=0.88, confidence=0.86)}
        def fake_rag(p, t, s):
            return {"evidence": Evidence(source="rag", tool="fake_vector_retriever",
                claim="RAG BYD strategic background",
                content="industry report shows BYD strengthening cost advantage",
                time_range="user " + t.user_intent.time_range,
                data_caliber="vector retrieval caliber",
                coverage_dimensions=["industry report","trend"],
                coverage_score=0.7, source_credibility=0.72, confidence=0.72)}
        def fake_framework(p, t, s):
            return {"evidence": Evidence(source="analysis-framework", tool=p,
                claim="framework Porter", content="based on entered evidence",
                time_range=t.user_intent.time_range,
                data_caliber="inference caliber",
                coverage_dimensions=["inference"],
                coverage_score=0.6, source_credibility=0.60, confidence=0.65)}
        orchestrator.register_tool("nl2sql-pg", fake_nl2sql)
        orchestrator.register_tool("rag", fake_rag)
        orchestrator.register_tool("analysis-framework", fake_framework)
        task = create_task_from_user_query(
            "analyze BYD last 12 months market strategy",
            time_range="last 12 months", entities=["BYD"])
        result = orchestrator.execute(task).to_dict()
        self.assertIn("evidence_ledger", result)
        self.assertIn("quality_passed", result)
        self.assertTrue(result["quality_passed"], result.get("failed_quality_checks"))
        self.assertIn("data_coverage_factor", result["confidence_details"])
        self.assertIn("confidence", result["confidence_details"])

    def test_tavily_web_search_quality_metadata(self):
        orchestrator = StrategyOrchestrator()
        self._register_targeted_sql_pack(orchestrator)
        def fake_nl2sql(p, t, s):
            return {"evidence": Evidence(source="nl2sql-pg", tool="fake", claim="struct",
                content="BYD data", time_range=t.user_intent.time_range,
                data_caliber="DB", metrics=["sales"],
                coverage_dimensions=["t"], coverage_score=0.9,
                source_credibility=0.88, confidence=0.86)}
        def fake_rag(p, t, s):
            return {"evidence": Evidence(source="rag", tool="fake", claim="RAG",
                content="industry", time_range="user",
                data_caliber="RAG cal", coverage_dimensions=["report"],
                coverage_score=0.7, source_credibility=0.72, confidence=0.72)}
        def fake_framework(p, t, s):
            return {"evidence": Evidence(source="analysis-framework", tool=p, claim="SWOT",
                content="based on evidence", time_range=t.user_intent.time_range,
                data_caliber="inference", coverage_dimensions=["inf"],
                coverage_score=0.6, source_credibility=0.60, confidence=0.65)}
        orchestrator.register_tool("nl2sql-pg", fake_nl2sql)
        orchestrator.register_tool("rag", fake_rag)
        orchestrator.register_tool("analysis-framework", fake_framework)

        class FakeTavilyResult:
            def __call__(self, query, max_results=6):
                return {"query": query, "answer": "BYD market noticed",
                 "results": [{"title": "BYD market 2026",
                   "url": "https://www.autohome.com.cn/news/2026/06/byd-market.html",
                   "content": "BYD market share continues to be watched"}]}
        orchestrator._run_tavily_search = FakeTavilyResult()

        task = create_task_from_user_query(
            "evaluate BYD last 12 months market opportunity",
            time_range="last 12 months", entities=["BYD"])
        result = orchestrator.execute(task).to_dict()
        web_evidence = [item for item in result["evidence_ledger"]["evidences"]
                       if item.get("source") == "web-search"]
        self.assertTrue(web_evidence, "web-search evidence should be present")
        item = web_evidence[0]
        self.assertEqual(item["source_url"],
            "https://www.autohome.com.cn/news/2026/06/byd-market.html")
        self.assertIn("2026", item["source_date"])
        self.assertGreaterEqual(item["coverage_score"], 0.5)
        self.assertIn("source_grade=A", item["content"])
        self.assertIn("rejection_reason=accepted", item["content"])

    def test_rag_evidence_has_url_date_grade(self):
        orchestrator = StrategyOrchestrator()
        self._register_targeted_sql_pack(orchestrator)
        def fake_nl2sql(p, t, s):
            return {"evidence": Evidence(source="nl2sql-pg", tool="fake", claim="struct",
                content="data", time_range="last 12m",
                data_caliber="DB", metrics=["sales"],
                coverage_dimensions=["t"], coverage_score=0.9,
                source_credibility=0.88, confidence=0.86)}
        def fake_rag(p, t, s):
            return {"evidence": Evidence(source="rag", tool="fake_vector_retriever",
                claim="RAG BYD strategic background",
                content="industry report shows BYD strengthening cost advantage",
                time_range="user " + t.user_intent.time_range,
                data_caliber="vector retrieval caliber",
                coverage_dimensions=["industry report","trend"],
                coverage_score=0.7, source_credibility=0.72, confidence=0.72,
                source_url="https://example.com/byd-report.pdf",
                source_date="2026-06-01",
                source_grade="A")}
        def fake_framework(p, t, s):
            return {"evidence": Evidence(source="analysis-framework", tool=p, claim="fw",
                content="done", time_range="last 12m",
                data_caliber="inf", coverage_dimensions=["inf"],
                coverage_score=0.6, source_credibility=0.60, confidence=0.65)}
        orchestrator.register_tool("nl2sql-pg", fake_nl2sql)
        orchestrator.register_tool("rag", fake_rag)
        orchestrator.register_tool("analysis-framework", fake_framework)
        task = create_task_from_user_query(
            "BYD near 6 months market strategy",
            time_range="near 6 months", entities=["BYD"])
        result = orchestrator.execute(task).to_dict()
        rag_evidence = [item for item in result["evidence_ledger"]["evidences"]
                       if item.get("source") == "rag"]
        self.assertTrue(rag_evidence, "rag evidence should be present")
        item = rag_evidence[0]
        self.assertIn("source_url", item)
        self.assertIn("source_date", item)
        self.assertIn("source_grade", item)

if __name__ == "__main__":
    unittest.main()
