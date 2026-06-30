# -*- coding: utf-8 -*-
"""Runtime helper tests for the live frontend bridge."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from python_wrapper.live_agent_server import (  # noqa: E402
    AnalyzeRequest,
    _classify_entry_route,
    _installed_skill_inventory,
    _is_direct_response_query,
    _normalize_time_range,
    _openclaw_session_key,
    _run_analysis,
)


class LiveBridgeRuntimeTest(unittest.TestCase):
    def test_question_year_overrides_default_time_input(self) -> None:
        self.assertEqual(
            _normalize_time_range(
                "分析 2026 年中国新能源乘用车市场竞争格局",
                "最近12个月",
            ),
            "2026年",
        )

    def test_meta_help_query_is_direct_route_but_uses_market_agent_session(self) -> None:
        self.assertTrue(_is_direct_response_query("你能做什么？"))
        route = _classify_entry_route("你能做什么？")
        self.assertEqual(route["route"], "capability_help")

        calls = []

        def fake_chat(**kwargs):
            calls.append(kwargs)
            return {
                "ok": True,
                "text": "我是小市场，可以帮你做市场分析。",
                "session_key": _openclaw_session_key(kwargs["agent_id"], kwargs["session_id"]),
                "agent_id": kwargs["agent_id"],
            }

        with patch("python_wrapper.live_agent_server._openclaw_agent_chat", side_effect=fake_chat):
            result = _run_analysis(AnalyzeRequest(question="你能做什么？", session_id="browser-1"))

        self.assertEqual(calls[0]["agent_id"], "market_strategy")
        self.assertEqual(calls[0]["session_id"], "browser-1")
        self.assertEqual(result["analysis_type"], "capability_help")
        self.assertEqual(result["stop_reason"], "openclaw_market_agent_completed")
        self.assertIn("我是小市场", result["report"])

    def test_complex_policy_query_routes_to_strategy_orchestrator_session(self) -> None:
        calls = []

        def fake_chat(**kwargs):
            calls.append(kwargs)
            return {
                "ok": True,
                "text": "# 策略分析结果\n\n事实、推断、置信度已分离。",
                "session_key": _openclaw_session_key(kwargs["agent_id"], kwargs["session_id"]),
                "agent_id": kwargs["agent_id"],
            }

        with patch("python_wrapper.live_agent_server._openclaw_agent_chat", side_effect=fake_chat):
            result = _run_analysis(
                AnalyzeRequest(
                    question="分析补贴退坡对新能源SUV市场的政策影响",
                    analysis_type="policy",
                    time_range="最近6个月",
                    session_id="browser-2",
                )
            )

        self.assertEqual(calls[0]["agent_id"], "strategy-orchestrator")
        self.assertEqual(calls[0]["session_id"], "browser-2")
        self.assertIn('"action": "orchestrate"', calls[0]["message"])
        self.assertIn('"analysis_type": "policy_impact"', calls[0]["message"])
        self.assertEqual(result["analysis_type"], "policy_impact")
        self.assertEqual(result["stop_reason"], "openclaw_strategy_orchestrator_completed")
        self.assertIn("策略分析结果", result["report"])

    def test_non_forced_market_query_uses_market_agent_session(self) -> None:
        calls = []

        def fake_chat(**kwargs):
            calls.append(kwargs)
            return {
                "ok": True,
                "text": "普通市场趋势问题先由当前小市场会话处理。",
                "session_key": _openclaw_session_key(kwargs["agent_id"], kwargs["session_id"]),
                "agent_id": kwargs["agent_id"],
            }

        with patch("python_wrapper.live_agent_server._openclaw_agent_chat", side_effect=fake_chat):
            result = _run_analysis(
                AnalyzeRequest(
                    question="简单说下新能源车市场趋势",
                    analysis_type="market",
                    session_id="browser-3",
                )
            )

        self.assertEqual(calls[0]["agent_id"], "market_strategy")
        self.assertEqual(result["stop_reason"], "openclaw_market_agent_completed")

    def test_skill_inventory_can_still_read_local_skills_for_fallback(self) -> None:
        skills = _installed_skill_inventory()
        skill_names = {item["name"] for item in skills}
        self.assertIn("automotive-strategy-analysis", skill_names)

    def test_session_key_is_stable_and_sanitized(self) -> None:
        self.assertEqual(
            _openclaw_session_key("strategy-orchestrator", "web session 1"),
            "agent:strategy-orchestrator:web:chat:web-session-1",
        )


if __name__ == "__main__":
    unittest.main()
