#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
send_complete_callback.py - 修复 complete callback 的字段缺失问题。

**Bug**: 之前 complete callback 只发了 summary + confidence=0，前端 chat.html 拿不到完整报告。
**修复**: 使用 callback_client.py 的 --event-json 字段，传递 report / confidence / sources /
         missing_or_uncertain / evidence_count / quality_passed / execution_time，
         确保前端 renderComplete() 能正确渲染。

用法:
    python tools/send_complete_callback.py \
        --session-id <session_id> \
        --report-path <md_or_txt> \
        --confidence 0.62 \
        --sources 'CarNewsChina' 'China EV DataTracker' 'JAIA' 'Sina' \
        --missing-or-uncertain 'CPCA/CAAM 一手数据未直连' \
        --evidence-count 18 \
        --execution-time 1438 \
        [--summary '任务完成...'] \
        [--report-path-extra <other>]

退出码:
    0 = 成功
    2 = 参数错误 / 文件读取失败
    3 = 推送失败
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CALLBACK_CLIENT = (
    WORKSPACE_ROOT.parent / "workspace-market" / "fastapi_18003_adapter" / "callback_client.py"
)


def read_report(report_path: Path) -> str:
    if not report_path.exists():
        raise FileNotFoundError(f"报告文件不存在: {report_path}")
    return report_path.read_text(encoding="utf-8", errors="replace")


def build_event_json(
    *,
    report: str,
    confidence: float,
    sources: list,
    missing_or_uncertain: list,
    evidence_count: int,
    quality_passed: bool,
    execution_time: float | None,
    success: bool,
    agent: str,
) -> dict:
    event: dict = {
        "report": report,
        "confidence": confidence,
        "sources": sources,
        "missing_or_uncertain": missing_or_uncertain,
        "evidence_count": evidence_count,
        "quality_passed": quality_passed,
        "success": success,
        "agent": agent,
    }
    if execution_time is not None:
        event["execution_time"] = execution_time
    return event


def post_via_callback_client(
    *,
    session_id: str,
    callback_url: str,
    event: dict,
    summary: str,
    client_script: Path,
    timeout: float = 30.0,
) -> dict:
    """Invoke callback_client.py with --event-json."""
    cmd = [
        sys.executable,
        str(client_script),
        "--session-id", session_id,
        "--callback-url", callback_url,
        "--event-type", "complete",
        "--phase", "Complete",
        "--status", "done",
        "--agent", event.get("agent", "strategy-orchestrator"),
        "--summary", summary,
        "--event-json", json.dumps(event, ensure_ascii=False),
        "--timeout", str(timeout),
    ]
    print(f"[send_complete_callback] exec: {client_script.name}", file=sys.stderr)
    print(f"[send_complete_callback] event size: report={len(event['report'])} chars", file=sys.stderr)

    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=timeout + 5)
    if result.returncode != 0:
        print(f"[send_complete_callback] callback_client exit {result.returncode}", file=sys.stderr)
        print(f"stdout: {result.stdout}", file=sys.stderr)
        print(f"stderr: {result.stderr}", file=sys.stderr)
        raise RuntimeError(f"callback_client failed (exit {result.returncode})")

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"ok": True, "raw": result.stdout}


def main() -> int:
    parser = argparse.ArgumentParser(description="Send a corrected complete callback with full report payload.")
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--callback-url", default="http://127.0.0.1:18003/callback")
    parser.add_argument("--report-path", required=True, type=Path, help="完整 Markdown 报告路径")
    parser.add_argument("--confidence", required=True, type=float, help="整体置信度，0.0-1.0")
    parser.add_argument(
        "--sources",
        nargs="+",
        default=["CarNewsChina", "China EV DataTracker", "JAIA", "Sina"],
        help="证据来源列表",
    )
    parser.add_argument(
        "--missing-or-uncertain",
        nargs="+",
        default=[
            "CPCA/CAAM 一手数据未直连",
            "王朝/海洋各车型销量分布待补",
            "海外分国家数据待补",
        ],
        help="缺口/不确定性列表",
    )
    parser.add_argument("--evidence-count", type=int, default=18, help="证据条数 (Fact)")
    parser.add_argument("--execution-time", type=float, default=None, help="任务总耗时（秒）")
    parser.add_argument("--quality-passed", action="store_true", default=True)
    parser.add_argument("--agent", default="strategy-orchestrator")
    parser.add_argument(
        "--summary",
        default="任务完成，完整报告已通过 report 字段返回前端。",
        help="简短 summary（与 report 字段独立）",
    )
    parser.add_argument("--client-script", type=Path, default=DEFAULT_CALLBACK_CLIENT)
    parser.add_argument("--timeout", type=float, default=30.0)

    args = parser.parse_args()

    try:
        report_text = read_report(args.report_path)
    except FileNotFoundError as e:
        print(f"[error] {e}", file=sys.stderr)
        return 2

    event = build_event_json(
        report=report_text,
        confidence=args.confidence,
        sources=args.sources,
        missing_or_uncertain=args.missing_or_uncertain,
        evidence_count=args.evidence_count,
        quality_passed=args.quality_passed,
        execution_time=args.execution_time,
        success=True,
        agent=args.agent,
    )

    try:
        result = post_via_callback_client(
            session_id=args.session_id,
            callback_url=args.callback_url,
            event=event,
            summary=args.summary,
            client_script=args.client_script,
            timeout=args.timeout,
        )
    except (subprocess.TimeoutExpired, RuntimeError) as e:
        print(f"[error] {e}", file=sys.stderr)
        return 3

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
