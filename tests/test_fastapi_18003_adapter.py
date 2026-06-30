# -*- coding: utf-8 -*-
"""Tests for the OpenClaw Gateway web chat adapter on port 18003."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi_18003_adapter.gateway_client import openclaw_session_key  # noqa: E402
from fastapi_18003_adapter.main import build_market_agent_message, callback  # noqa: E402
from fastapi_18003_adapter.models import CallbackPayload, ChatRequest  # noqa: E402
from fastapi_18003_adapter.session_manager import session_manager  # noqa: E402


class FastApi18003AdapterTest(unittest.IsolatedAsyncioTestCase):
    def test_market_agent_message_carries_callback_contract(self) -> None:
        message = build_market_agent_message(
            ChatRequest(
                question="分析零跑商业模式",
                analysis_type="business_analysis",
                time_range="最近6个月",
                session_id="web-test-1",
            )
        )

        self.assertIn('"source": "chat.html"', message)
        self.assertIn('"session_id": "web-test-1"', message)
        self.assertIn('"callback_url": "http://127.0.0.1:18003/callback"', message)
        self.assertIn("sessions_send", message)
        self.assertIn("strategy-orchestrator", message)

    def test_openclaw_session_key_is_stable(self) -> None:
        self.assertEqual(
            openclaw_session_key("market_strategy", "web session 1"),
            "agent:market_strategy:web:chat:web-session-1",
        )

    async def test_callback_pushes_complete_event_with_defaults(self) -> None:
        session_id = "unit-callback-complete"
        await session_manager.get_or_create(session_id)

        result = await callback(
            CallbackPayload(
                session_id=session_id,
                event={"phase": "Complete", "answer": "最终报告"},
            )
        )
        item = await session_manager.pop(session_id, timeout=0.1)

        self.assertEqual(result["ok"], True)
        self.assertEqual(item["event"], "complete")
        self.assertEqual(item["data"]["success"], True)
        self.assertEqual(item["data"]["quality_passed"], True)
        self.assertEqual(item["data"]["report"], "最终报告")


if __name__ == "__main__":
    unittest.main()
