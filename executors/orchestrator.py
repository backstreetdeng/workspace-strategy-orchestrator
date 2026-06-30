"""
Strategy Orchestrator - 自主编排执行器

ReAct 循环实现：
- Plan: 理解问题，拆解任务，选择工具
- Act: 调用能力
- Observe: 读取结果
- Reflect: 判断是否足够
- Re-plan: 调整或终止
"""

import json
import logging
import importlib.util
import os
import re
import time
import urllib.error
import urllib.request
from typing import Dict, List, Any, Optional, Callable, Tuple
from datetime import datetime
from dataclasses import dataclass, field
from pathlib import Path

# 导入协议和组件
import sys
import os

# 尝试导入（如果不存在则创建 mock）
from protocols.task_protocol import (
    OrchestrationTask,
    OrchestrationResult,
    TaskType,
    OutputFormat,
    create_task_from_user_query
)
from evidence.evidence_ledger import (
    EvidenceLedger,
    Evidence,
    get_evidence_ledger,
    reset_evidence_ledger
)
from evidence.evidence_factory import (
    build_sql_evidence,
    build_rag_evidence,
)
from quality.quality_gate import (
    QualityGate,
    get_quality_gate,
    generate_quality_report
)
from quality.rollback_handler import (
    RollbackHandler,
    FailureContext,
    FailureType,
    detect_failure_type,
    get_rollback_handler
)
from planning.analysis_plan import (
    AnalysisPlan,
    build_analysis_plan
)
from planning.seven_step_phases import (
    AnalysisPhase,
    PhaseTracker,
)
from reporting.seven_step_report import (
    build_insight_cards,
    build_seven_step_report,
)
from tools.targeted_sql_pack import (
    REQUIRED_TARGETED_SQL_BLOCKS,
    build_targeted_sql_evidences,
    missing_required_blocks,
    run_targeted_sql_pack,
)
from tools.skill_strategy_adapter import (
    SkillGuidedPlanner,
    build_framework_analysis,
)
from tools.agent_tool_adapters import run_specialist_agent
logger = logging.getLogger(__name__)


@dataclass
class ToolResult:
    """工具执行结果"""
    tool_name: str
    success: bool
    result: Any = None
    error: str = None
    execution_time: float = 0.0
    evidence: Evidence = None
    evidences: List[Evidence] = field(default_factory=list)
    # A.1: 当工具返回 dispatch_via="sessions_send" 时，记录待 dispatch 请求
    # 由 main loop 触发 sessions_send（_trigger_sessions_send），caller 不再参与
    dispatch_request: Optional[Dict[str, Any]] = None
    # A.2: main loop inline-trigger 后填充 specialist 的响应（None 表示未 dispatch）
    dispatch_response: Optional[Dict[str, Any]] = None


@dataclass
class ReactState:
    """ReAct 循环状态"""
    cycle: int = 0
    analysis_plan: Optional[AnalysisPlan] = None
    current_plan: List[str] = field(default_factory=list)
    completed_steps: List[str] = field(default_factory=list)
    tool_results: List[ToolResult] = field(default_factory=list)
    replan_queue: List[str] = field(default_factory=list)
    reflection: Dict[str, Any] = field(default_factory=dict)
    replan_history: List[Dict[str, Any]] = field(default_factory=list)
    evidence_gaps: List[str] = field(default_factory=list)
    reflection_history: List[Dict[str, Any]] = field(default_factory=list)
    confidence_trajectory: List[float] = field(default_factory=list)
    stagnation_count: int = 0
    current_phase: str = AnalysisPhase.PROBLEM_DEFINITION.value
    phase_history: List[Dict[str, Any]] = field(default_factory=list)
    required_outputs: Dict[str, bool] = field(default_factory=dict)
    is_complete: bool = False
    stop_reason: str = ""
    should_stop: bool = False
    # A.3: orchestrator inline-triggered sessions_send 结果列表
    dispatched_results: List[Dict[str, Any]] = field(default_factory=list)


# ============================================================
# FastAPI 18003 /callback HTTP 推送 (2026-06-29 大管家补全)
# ============================================================
# 协议来源：E:\openclaw\knowledge\MyVault\文档\AI项目研究\AI智能体Skill改造\chat.html接入OpenClaw网关-完整方案.md
# 推送端点：${callback_url}（默认 http://127.0.0.1:18003/callback）
# Payload schema:
#   {"session_id": "...", "event": {...phase, stage, status, summary, ...}}
# FastAPI main.py 的 _normalize_callback_event() 会按 session_id 自动入队，由 SSE 推到 chat.html。
# 这是一条 fire-and-forget 通道：失败不影响 ReAct 主循环。
DEFAULT_CALLBACK_BASE_URL = os.environ.get(
    "ORCHESTRATOR_CALLBACK_BASE_URL", "http://127.0.0.1:18003"
).rstrip("/")
CALLBACK_HTTP_TIMEOUT_SECONDS = float(os.environ.get("ORCHESTRATOR_CALLBACK_TIMEOUT", "5"))


def _http_event_callback(callback_url: str, session_id: str) -> Callable[[Dict[str, Any]], None]:
    """工厂函数：返回一个把编排专家 ReAct 事件 POST 到 FastAPI 18003 /callback 的回调。

    使用方式：
        create_orchestrator(
            callback_url="http://127.0.0.1:18003",
            session_id="<uuid>",
        )

    设计原则：
    - fire-and-forget：POST 失败只 logger.warning，绝不抛异常打断 ReAct
    - 超时短（默认 5s），避免阻塞主循环
    - 单线程复用同一 Request 对象模式不可行（线程不安全），所以每次新建
    """
    if not callback_url or not session_id:
        raise ValueError("callback_url 和 session_id 都必须非空")

    target_url = callback_url.rstrip("/") + "/callback"

    def _post(event: Dict[str, Any]) -> None:
        try:
            payload = json.dumps(
                {"session_id": session_id, "event": event},
                ensure_ascii=False,
                default=str,
            ).encode("utf-8")
            req = urllib.request.Request(
                target_url,
                data=payload,
                headers={"Content-Type": "application/json; charset=utf-8"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=CALLBACK_HTTP_TIMEOUT_SECONDS) as resp:
                _ = resp.read()  # 排空 body，让连接复用
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
            logger.warning(
                "callback POST failed (session_id=%s, phase=%s): %s",
                session_id,
                event.get("phase", "?"),
                exc,
            )
        except Exception:
            logger.exception("callback POST unexpected failure (session_id=%s)", session_id)

    return _post


class StrategyOrchestrator:
    """
    战略编排器

    核心职责：
    1. 接收主 Agent 的任务
    2. 执行 ReAct 循环
    3. 维护证据账本
    4. 控制质量门禁
    5. 处理回退逻辑
    """

    def __init__(
        self,
        event_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        llm_plan_provider: Optional[Callable[[Dict[str, Any]], List[str]]] = None,
    ):
        self.evidence_ledger = get_evidence_ledger()
        self.quality_gate = get_quality_gate()
        self.rollback_handler = get_rollback_handler()
        self.phase_tracker = PhaseTracker()
        self.event_callback = event_callback
        self.workspace_root = Path(__file__).resolve().parents[3]
        self.skill_planner = SkillGuidedPlanner(
            workspace_root=self.workspace_root,
            llm_plan_provider=llm_plan_provider,
        )
        
        # 工具注册表
        self._tools: Dict[str, Callable] = {}
        self._register_default_tools()

    def _emit_event(
        self,
        phase: str,
        stage: str,
        status: str,
        summary: str,
        detail: Any = None,
        **extra: Any,
    ) -> None:
        """Emit a bounded execution event for live UI streaming."""
        if not self.event_callback:
            return
        event = {
            "phase": phase,
            "stage": stage,
            "status": status,
            "summary": summary,
            "detail": detail,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        }
        event.update(extra)
        try:
            self.event_callback(event)
        except Exception:
            logger.exception("orchestrator event callback failed")
    
    @property
    def tool_registry(self):
        return self
    
    def register_tool(self, name, tool_func):
        self._tools[name] = tool_func
    
    def _register_default_tools(self):
        """注册默认工具"""
        # 这里注册实际可用的工具
        # 在实际运行时会通过配置注入
        
        # 结构化数据查询
        self._tools["targeted-sql-pack"] = self._tool_targeted_sql_pack
        self._tools["targeted_sql_pack"] = self._tool_targeted_sql_pack
        self._tools["nl2sql-pg"] = self._tool_nl2sql
        
        # RAG 检索
        self._tools["pg-vector-search"] = self._tool_rag_retrieve
        self._tools["rag"] = self._tool_rag_retrieve
        
        # 分析框架
        self._tools["analysis-framework"] = self._tool_analysis_framework
        self._tools["pest"] = self._tool_pest
        self._tools["swot"] = self._tool_swot
        self._tools["porter"] = self._tool_porter
        self._tools["4p"] = self._tool_4p
        
        # 报告生成（统一指向 sessions_send 路径，由 run_specialist_agent → AGENT_ALIAS → report-agent 真正调度）
        self._tools["report-generator"] = self._tool_report_generator_agent
        self._tools["report-agent"] = self._tool_report_generator_agent
        self._tools["report-generator-agent"] = self._tool_report_generator_agent
        
        # 搜索
        self._tools["web-search"] = self._tool_web_search

        # 方法论状态追踪
        self._tools["phase-tracker"] = self._tool_phase_tracker
        self._tools["phase_tracker"] = self._tool_phase_tracker

        # 专业子 Agent 工具适配
        self._tools["competitor-analyst"] = self._tool_competitor_analyst
        self._tools["cost-analyst"] = self._tool_cost_analyst
    
    def register_tool(self, name: str, tool_func: Callable):
        """注册工具"""
        self._tools[name] = tool_func
    
    def execute(self, task: OrchestrationTask) -> OrchestrationResult:
        """
        执行编排任务
        
        Main entry point for 主 Agent
        """
        logger.info(f"Starting orchestration for task: {task.task_id}")
        
        # 重置证据账本（新任务）
        reset_evidence_ledger()
        self.evidence_ledger = get_evidence_ledger()
        
        # 初始化 ReAct 状态
        state = ReactState()
        state.analysis_plan = build_analysis_plan(task)
        self._emit_event(
            "Plan",
            "stage2",
            "done",
            (
                "已形成统一分析计划："
                f"市场={state.analysis_plan.market_scope}；"
                f"时间={state.analysis_plan.time_range}；"
                f"品牌={state.analysis_plan.target_brand or '未指定'}；"
                f"价格带={state.analysis_plan.price_band or '未指定'}"
            ),
            detail=state.analysis_plan.to_dict() if hasattr(state.analysis_plan, "to_dict") else state.analysis_plan,
        )
        
        # 执行 ReAct 循环
        result = self._run_react_loop(task, state)
        
        # 质量检查
        self._emit_event("Quality", "stage4", "running", "正在执行质量门禁和证据完整性检查")
        result = self._apply_quality_gate(result)
        self._emit_event(
            "Quality",
            "stage4",
            "done" if result.quality_passed else "warning",
            (
                "质量门禁通过"
                if result.quality_passed
                else f"质量门禁未通过：{len(result.failed_quality_checks or [])} 项需要关注"
            ),
            detail=result.failed_quality_checks,
        )
        
        logger.info(f"Orchestration complete: {result.task_id}, cycles={result.cycles_used}")
        
        return result
    
    def _run_react_loop(
        self,
        task: OrchestrationTask,
        state: ReactState
    ) -> OrchestrationResult:
        """
        执行 ReAct 循环
        
        循环直到：
        1. 达到最大循环次数
        2. 证据足够
        3. 需要向用户追问
        4. 所有工具都失败
        """
        max_cycles = task.max_react_cycles
        
        while state.cycle < max_cycles and not state.should_stop:
            state.cycle += 1
            logger.info(f"Cycle {state.cycle}/{max_cycles}")
            self._emit_event(
                "Cycle",
                "stage3",
                "running",
                f"开始第 {state.cycle}/{max_cycles} 轮 ReAct：准备规划下一批工具调用",
                cycle=state.cycle,
            )
            
            # ===== Plan =====
            plan = self._plan(task, state)
            state.current_plan = plan
            logger.info(f"Plan: {plan}")
            self._emit_event(
                "Plan",
                "stage3",
                "done" if plan else "warning",
                "本轮计划：" + ("、".join(plan) if plan else "反思后没有新的可执行步骤"),
                detail={"cycle": state.cycle, "plan": plan},
                cycle=state.cycle,
            )
            if not plan:
                state.should_stop = True
                state.stop_reason = "No further steps after reflection"
                self._emit_event(
                    "Stop",
                    "stage4",
                    "warning",
                    state.stop_reason,
                    cycle=state.cycle,
                )
                break
            
            # ===== Act =====
            for step in plan:
                if state.should_stop:
                    break
                
                self._emit_event(
                    "Act",
                    "stage3",
                    "running",
                    f"正在调用工具：{step}",
                    detail={"cycle": state.cycle, "step": step},
                    cycle=state.cycle,
                )
                tool_result = self._execute_step(step, task, state)
                state.tool_results.append(tool_result)
                # A.4: orchestrator inline-trigger sessions_send (Option A)
                if tool_result.dispatch_request:
                    tool_result.dispatch_request["created_at_cycle"] = state.cycle
                    dispatch_response = self._trigger_sessions_send(
                        dispatch_request=tool_result.dispatch_request,
                        state=state,
                    )
                    tool_result.dispatch_response = dispatch_response
                    target_agent_id = tool_result.dispatch_request.get("agent_id")
                    state.dispatched_results.append({
                        "request": tool_result.dispatch_request,
                        "response": dispatch_response,
                        "cycle": state.cycle,
                        "step": step,
                    })
                    response_text = dispatch_response.get("text", "") if dispatch_response.get("ok") else ""
                    self._emit_event(
                        "Act",
                        "stage3",
                        "dispatched" if dispatch_response.get("ok") else "dispatch_failed",
                        (
                            "specialist dispatch to " + str(target_agent_id) + ": OK ("
                            + str(len(response_text)) + " chars)"
                            if dispatch_response.get("ok")
                            else "specialist dispatch to " + str(target_agent_id) + ": FAIL " + str(dispatch_response.get("error"))
                        ),
                        detail={
                            "cycle": state.cycle,
                            "step": step,
                            "target_agent_id": target_agent_id,
                            "source_tool": tool_result.dispatch_request.get("source_tool"),
                            "dispatch_ok": dispatch_response.get("ok", False),
                            "session_key": dispatch_response.get("session_key"),
                            "response_chars": len(response_text),
                            "duration_seconds": dispatch_response.get("duration_seconds"),
                        },
                        cycle=state.cycle,
                    )
                evidence_count = len(tool_result.evidences or []) + (1 if tool_result.evidence else 0)
                self._emit_event(
                    "Observe",
                    "stage3",
                    "done" if tool_result.success else "warning",
                    (
                        f"{step} 返回："
                        f"{'成功' if tool_result.success else '失败'}；"
                        f"耗时 {tool_result.execution_time:.1f}s；"
                        f"新增证据 {evidence_count} 条"
                    ),
                    detail={
                        "cycle": state.cycle,
                        "step": step,
                        "tool": tool_result.tool_name,
                        "success": tool_result.success,
                        "error": tool_result.error,
                        "execution_time": round(tool_result.execution_time, 3),
                        "evidence_count": evidence_count,
                    },
                    cycle=state.cycle,
                )
                
                # 记录证据
                evidences_to_add = list(tool_result.evidences or [])
                if tool_result.evidence:
                    evidences_to_add.append(tool_result.evidence)
                for evidence in evidences_to_add:
                    self.evidence_ledger.add_evidence(
                        source=evidence.source,
                        tool=evidence.tool,
                        claim=evidence.claim,
                        content=evidence.content,
                        time_range=evidence.time_range,
                        metrics=evidence.metrics,
                        data_caliber=evidence.data_caliber,
                        source_url=evidence.source_url,
                        source_date=evidence.source_date,
                        source_grade=evidence.source_grade,
                        source_credibility=evidence.source_credibility,
                        coverage_dimensions=evidence.coverage_dimensions,
                        coverage_score=evidence.coverage_score,
                        confidence=evidence.confidence,
                        limitations=evidence.limitations
                    )
                    self._emit_event(
                        "Evidence",
                        "stage3",
                        "done",
                        f"证据入账：[{evidence.source}/{evidence.tool}] {evidence.claim}",
                        detail={
                            "cycle": state.cycle,
                            "source": evidence.source,
                            "tool": evidence.tool,
                            "claim": evidence.claim,
                            "confidence": evidence.confidence,
                            "time_range": evidence.time_range,
                            "data_caliber": evidence.data_caliber,
                            "source_url": evidence.source_url,
                            "source_grade": evidence.source_grade,
                        },
                        cycle=state.cycle,
                    )
                
                # 记录已完成步骤
                state.completed_steps.append(step)
                
                # 检查是否应该停止
                if self._check_stop_conditions(task, state):
                    state.should_stop = True
                    break
            
            # ===== Observe & Reflect =====
            self._observe_and_reflect(task, state)
            self._emit_event(
                "Reflect",
                "stage4",
                "done" if not state.reflection.get("is_stagnant") else "warning",
                (
                    f"第 {state.cycle} 轮反思："
                    f"置信度 {float(state.reflection.get('overall_confidence') or 0):.1%}；"
                    f"新增证据 {state.reflection.get('new_evidence_count', 0)} 条；"
                    f"缺口 {len(state.reflection.get('evidence_gaps') or [])} 项；"
                    f"冲突 {len(state.reflection.get('conflicts') or [])} 项"
                ),
                detail=state.reflection,
                cycle=state.cycle,
            )

            # ===== Seven-step phase tracking =====
            self.run_phase(state.current_phase, task, state)
            
            # ===== Re-plan =====
            if not state.should_stop:
                self._replan(task, state)
                last_replan = state.replan_history[-1] if state.replan_history else None
                if last_replan and last_replan.get("cycle") == state.cycle:
                    self._emit_event(
                        "Re-plan",
                        "stage4",
                        "running",
                        f"基于反思重规划：{last_replan.get('reason')} -> {', '.join(last_replan.get('next_plan') or [])}",
                        detail=last_replan,
                        cycle=state.cycle,
                    )
                else:
                    self._emit_event(
                        "Re-plan",
                        "stage4",
                        "done",
                        "当前证据状态无需新增重规划步骤",
                        cycle=state.cycle,
                    )
        
        if not state.stop_reason and state.cycle >= max_cycles and not state.is_complete:
            state.stop_reason = "Max cycles reached"
            self._emit_event(
                "Stop",
                "stage4",
                "warning",
                state.stop_reason,
                cycle=state.cycle,
            )
        
        # ===== 构建结果 =====
        self._emit_event("Report", "stage5", "running", "正在汇总证据账本并生成业务报告")
        return self._build_result(task, state)
    
    def _plan(
        self,
        task: OrchestrationTask,
        state: ReactState
    ) -> List[str]:
        """
        Plan 阶段：理解问题，拆解任务，选择工具
        """
        if state.replan_queue:
            queued = list(state.replan_queue)
            state.replan_queue.clear()
            return queued

        plan_payload = self.skill_planner.build_plan(task, state)
        plan = list(plan_payload.get("steps") or [])
        self._emit_event(
            "Plan",
            "stage3",
            "done" if plan else "warning",
            (
                "已由 "
                f"{plan_payload.get('source')} 生成本轮分析计划；"
                f"步骤数={len(plan)}"
            ),
            detail={
                "source": plan_payload.get("source"),
                "provider_error": plan_payload.get("provider_error"),
                "skill_path": plan_payload.get("skill_path"),
                "stage_contract": plan_payload.get("stage_contract"),
                "raw_plan": plan,
            },
            cycle=state.cycle,
        )
        return [step for step in plan if not self._step_succeeded(state, step)]
    
    def _execute_step(
        self,
        step: str,
        task: OrchestrationTask,
        state: ReactState
    ) -> ToolResult:
        """
        Act 阶段：执行单个步骤
        """
        import time
        start_time = time.time()
        
        # 解析步骤 (tool:param)
        if ":" in step:
            tool_name, param = step.split(":", 1)
        else:
            tool_name, param = step, ""
        
        # 获取工具
        tool_func = self._tools.get(tool_name)
        
        if not tool_func:
            return ToolResult(
                tool_name=tool_name,
                success=False,
                error=f"Tool not found: {tool_name}",
                execution_time=time.time() - start_time
            )
        
        try:
            # 调用工具
            result = tool_func(param, task, state)
            
            # 从结果中提取 evidence
            evidence = None
            evidences = []
            if isinstance(result, dict) and 'evidence' in result:
                evidence = result['evidence']
            if isinstance(result, dict) and 'evidences' in result:
                evidences = result.get('evidences') or []
            result_success = True
            result_error = None
            if isinstance(result, dict) and result.get("success") is False:
                result_success = False
                result_error = str(result.get("error") or "Tool returned success=False")

            # A.2: 检测 dispatch_via 字段，构造 dispatch_request
            # 当 specialist tool 返回 dispatch_via="sessions_send" 时，记录待 dispatch 请求
            dispatch_request = None
            if isinstance(result, dict) and result.get("dispatch_via") == "sessions_send":
                target_agent_id = result.get("agent_id")
                message = result.get("message")
                if target_agent_id and message:
                    dispatch_request = {
                        "agent_id": target_agent_id,
                        "message": message,
                        "task_package": result.get("task_package"),
                        "source_tool": tool_name,
                        "created_at_cycle": 0,  # main loop 填入真实 cycle
                    }

            return ToolResult(
                tool_name=tool_name,
                success=result_success,
                result=result,
                evidence=evidence,
                evidences=evidences,
                error=result_error,
                execution_time=time.time() - start_time,
                dispatch_request=dispatch_request,
            )

        except Exception as e:
            # 捕获异常，返回失败
            failure_type = detect_failure_type(e, tool_name)
            return ToolResult(
                tool_name=tool_name,
                success=False,
                error=str(e),
                execution_time=time.time() - start_time
            )

    def _trigger_sessions_send(
        self,
        *,
        dispatch_request: Dict[str, Any],
        state: ReactState,
    ) -> Dict[str, Any]:
        """Option A: orchestrator directly triggers sessions_send to specialist agent.

        Uses OpenClaw Gateway HTTP API (/v1/chat/completions) to dispatch
        a message to the target Agent. Returns the specialist's response package.

        Args:
            dispatch_request: dict from agent_tool_adapters.run_specialist_agent().
                Must contain: agent_id, message, task_package (optional), source_tool.
            state: ReactState (for logging context only).

        Returns:
            dict with keys:
                - ok: bool
                - agent_id: str
                - session_key: str
                - text: str (specialist's response)
                - error: str (if failed)
                - duration_seconds: float
                - source_tool: str

        Raises:
            Does not raise; all errors are captured in the returned dict.
        """
        target_agent_id = dispatch_request.get("agent_id")
        message = dispatch_request.get("message", "")
        source_tool = dispatch_request.get("source_tool", "")

        if not target_agent_id or not message:
            return {
                "ok": False,
                "agent_id": target_agent_id,
                "error": "missing agent_id or message in dispatch_request",
                "source_tool": source_tool,
            }

        gateway_base = os.environ.get("OPENCLAW_GATEWAY_BASE_URL", "http://127.0.0.1:18789")
        # Fix-1 (2026-06-28 老大授权): token fallback 复用 18003 adapter 的 gateway_client.py
        # 默认 token 来自 fastapi_18003_adapter/gateway_client.py:OPENCLAW_GATEWAY_TOKEN_DEFAULT
        # 避免 agent 进程环境变量未设置时 _trigger_sessions_send 优雅失败
        _DEFAULT_OPENCLAW_GATEWAY_TOKEN = "2ec777c61f588861712e0d7d9da2cf909fb2b4f45c954be9"
        gateway_token = os.environ.get("OPENCLAW_GATEWAY_TOKEN") or _DEFAULT_OPENCLAW_GATEWAY_TOKEN
        timeout_seconds = float(os.environ.get("OPENCLAW_DISPATCH_TIMEOUT_SECONDS", "180"))

        if not gateway_token:
            return {
                "ok": False,
                "agent_id": target_agent_id,
                "error": "OPENCLAW_GATEWAY_TOKEN not configured",
                "source_tool": source_tool,
            }

        session_key = "agent:" + str(target_agent_id) + ":main"
        payload = {
            "model": "openclaw/" + str(target_agent_id),
            "messages": [{"role": "user", "content": message}],
            "user": "strategy-orchestrator",
            "temperature": 0.2,
            "stream": False,
        }

        start = time.time()
        try:
            request = urllib.request.Request(
                gateway_base + "/v1/chat/completions",
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers={
                    "Authorization": "Bearer " + gateway_token,
                    "Content-Type": "application/json",
                    "x-openclaw-session-key": session_key,
                },
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                raw = response.read().decode("utf-8")
                data = json.loads(raw)
            text_out = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
            return {
                "ok": bool(text_out),
                "agent_id": target_agent_id,
                "session_key": session_key,
                "text": text_out,
                "source_tool": source_tool,
                "duration_seconds": round(time.time() - start, 3),
            }
        except urllib.error.HTTPError as e:
            return {
                "ok": False,
                "agent_id": target_agent_id,
                "session_key": session_key,
                "error": "HTTP " + str(e.code) + ": " + str(e.reason),
                "source_tool": source_tool,
                "duration_seconds": round(time.time() - start, 3),
            }
        except Exception as e:
            return {
                "ok": False,
                "agent_id": target_agent_id,
                "session_key": session_key,
                "error": str(e),
                "source_tool": source_tool,
                "duration_seconds": round(time.time() - start, 3),
            }

    def _observe_and_reflect(
        self,
        task: OrchestrationTask,
        state: ReactState
    ):
        """
        Observe & Reflect 阶段：判断证据是否足够
        """
        # 统计成功/失败
        success_count = sum(1 for r in state.tool_results if r.success)
        total_count = len(state.tool_results)
        
        # 获取证据账本状态
        overall_conf, conf_details = self.evidence_ledger.calculate_overall_confidence()
        
        logger.info(f"Evidence status: {success_count}/{total_count} tools succeeded")
        logger.info(f"Overall confidence: {overall_conf}")
        
        # 检查冲突
        conflicts = self.evidence_ledger.get_conflicts()
        if conflicts:
            logger.warning(f"Found {len(conflicts)} evidence conflicts")
        
        structured_blocks = self._structured_blocks_seen(state)
        missing_blocks = self._missing_targeted_sql_blocks(task, state)
        missing_sources = self._missing_evidence_sources(task, state)
        state.evidence_gaps = []
        if missing_blocks:
            state.evidence_gaps.append("missing_targeted_sql_blocks:" + ",".join(missing_blocks))
        if missing_sources:
            state.evidence_gaps.append("missing_sources:" + ",".join(missing_sources))

        previous_conf = state.confidence_trajectory[-1] if state.confidence_trajectory else None
        previous_evidence_count = (
            state.reflection_history[-1].get("evidence_count", 0)
            if state.reflection_history
            else 0
        )
        evidence_count = len(self.evidence_ledger.evidences)
        confidence_delta = (
            overall_conf - previous_conf
            if previous_conf is not None
            else overall_conf
        )
        confidence_improved = (
            confidence_delta >= 0.02
            if previous_conf is not None
            else overall_conf > 0
        )
        new_evidence_count = max(0, evidence_count - previous_evidence_count)
        repeated_plan = any(
            prior.get("current_plan") == state.current_plan
            for prior in state.reflection_history[-2:]
        )

        if previous_conf is not None and not confidence_improved:
            state.stagnation_count += 1
        else:
            state.stagnation_count = 0

        is_stagnant = bool(previous_conf is not None and not confidence_improved)
        # P1: Track when stagnation first started
        if is_stagnant and state.stagnation_count == 1:
            state.stagnation_start_cycle = state.cycle
        elif not is_stagnant:
            state.stagnation_start_cycle = 0

        # P1 Enhancement: stagnation severity tracking and richer strategic_alert
        if is_stagnant and state.stagnation_count >= 2:
            strategic_alert_severity = 'critical'
            stagnation_duration = state.stagnation_count
            conf_traj = state.confidence_trajectory[-3:] if state.confidence_trajectory else []
            strategic_alert = (
                f'[CRITICAL] 连续{stagnation_duration}轮置信度无明显提升(轨迹:{conf_traj})，'
                '常规补证失效；应立即切换证据策略，例如从结构化SQL转向RAG深挖、历史趋势或带降级说明的部分结论。'
            )
            pivot_recommendation = (
                'FORCE_PIVOT: 连续补证失效，建议(1)RAG深挖上下文(2)Web搜索外部验证(3)带降级部分结论'
            )
        elif is_stagnant:
            strategic_alert_severity = 'warning'
            strategic_alert = (
                f'[WARNING] 本轮置信度未提升(stagnation={state.stagnation_count}轮)；'
                '下一轮应补充不同来源或不同口径证据，避免重复执行同类步骤。'
            )
            pivot_recommendation = (
                'WARN: 下轮补充不同来源或口径；若仍无效，触发强制切换。'
            )
        else:
            strategic_alert_severity = 'none'
            pivot_recommendation = ''
            strategic_alert = ''

        phase_snapshot = self.phase_tracker.phase_tracker(state)
        state.confidence_trajectory.append(round(overall_conf, 4))

        state.reflection = {
            "cycle": state.cycle,
            "current_plan": list(state.current_plan),
            "successful_tools": [r.tool_name for r in state.tool_results if r.success],
            "failed_tools": [
                {"tool": r.tool_name, "error": r.error}
                for r in state.tool_results
                if not r.success
            ],
            "overall_confidence": overall_conf,
            "confidence_details": conf_details,
            "confidence_trajectory": list(state.confidence_trajectory),
            "confidence_delta": round(confidence_delta, 4),
            "confidence_improved": confidence_improved,
            "evidence_count": evidence_count,
            "new_evidence_count": new_evidence_count,
            "plan_effective": confidence_improved and new_evidence_count > 0,
            "repeated_plan": repeated_plan,
            "is_stagnant": is_stagnant,
            "stagnation_count": state.stagnation_count,
            "stagnation_start_cycle": getattr(state, "stagnation_start_cycle", 0),
            "strategic_alert": strategic_alert,
            "strategic_alert_severity": strategic_alert_severity,
            "pivot_recommendation": pivot_recommendation,
            "next_phase": phase_snapshot.get("next_phase"),
            "current_phase": state.current_phase,
            "phase_requirements_met": phase_snapshot.get("phase_requirements_met", False),
            "phase_missing_requirements": phase_snapshot.get("missing_requirements", []),
            "phase_requirements_status": phase_snapshot.get("requirements_status", {}),
            "structured_blocks": structured_blocks,
            "missing_targeted_sql_blocks": missing_blocks,
            "missing_sources": missing_sources,
            "conflicts": conflicts,
            "evidence_gaps": list(state.evidence_gaps),
        }
        state.reflection_history.append(dict(state.reflection))

        # 判断是否足够
        # 标准：
        # 1. 至少有 2 个工具成功
        # 2. 置信度 >= 0.6
        # 3. 没有高严重性冲突
        # 4. targeted_sql_pack 的关键结构化 block 不缺失
        has_high_conflict = any(c.get("severity") == "high" for c in conflicts)
        
        if success_count >= 2 and overall_conf >= 0.6 and not has_high_conflict and not missing_blocks:
            state.is_complete = True
            state.should_stop = True
            state.stop_reason = "Sufficient evidence collected"
            logger.info("Evidence sufficient, marking complete")
        
        # 检查是否需要追问用户
        missing = self._check_missing_critical_evidence(task, state)
        if missing:
            state.stop_reason = f"Missing critical info: {missing}"
            logger.warning(f"Missing critical evidence: {missing}")
    
    def _replan(
        self,
        task: OrchestrationTask,
        state: ReactState
    ):
        """
        Re-plan 阶段：调整计划
        """
        if state.reflection.get("is_stagnant"):
            self._strategic_replan(task, state)
            if state.replan_queue:
                logger.info(f"Strategic re-plan: {state.replan_queue}")
                return

        replan_steps: List[str] = []

        missing_blocks = self._missing_targeted_sql_blocks(task, state)
        if missing_blocks:
            replan_steps.append("targeted-sql-pack:fill_missing_blocks")

        missing_sources = self._missing_evidence_sources(task, state)
        if "rag" in missing_sources:
            replan_steps.append("rag:fill_document_gap")
        if "web-search" in missing_sources:
            replan_steps.append("web-search:fill_external_gap")

        if replan_steps:
            state.replan_queue = self._dedupe_replan_steps(replan_steps, state, allow_failed_retry=True)
            state.replan_history.append(
                {
                    "cycle": state.cycle,
                    "reason": "evidence_gaps",
                    "gaps": list(state.evidence_gaps),
                    "next_plan": list(state.replan_queue),
                }
            )
            logger.info(f"Re-plan for evidence gaps: {state.replan_queue}")
            return

        # 如果有失败的步骤，尝试回退
        failed_results = [r for r in state.tool_results if not r.success]
        
        if failed_results:
            last_failure = failed_results[-1]
            
            # 获取回退策略
            failure_context = FailureContext(
                failure_type=detect_failure_type(Exception(last_failure.error or ""), last_failure.tool_name),
                original_operation=last_failure.tool_name,
                error_message=last_failure.error or "Unknown error",
                evidence_so_far=self.evidence_ledger.generate_report(),
                user_intent=task.user_intent.to_dict() if task.user_intent else {},
                retry_count=len(failed_results) - 1
            )
            
            fallback = self.rollback_handler.get_fallback(
                failure_context.failure_type,
                failure_context
            )
            
            # 如果需要停止，设置停止标志
            if self.rollback_handler.should_stop(failure_context):
                state.should_stop = True
                state.stop_reason = "All fallback strategies exhausted"
                return
            
            # 否则记录回退动作
            logger.info(f"Fallback action: {fallback.action_type}")
            fallback_step = self._fallback_step_for_tool(last_failure.tool_name)
            if fallback_step:
                state.replan_queue = self._dedupe_replan_steps([fallback_step], state, allow_failed_retry=True)
                state.replan_history.append(
                    {
                        "cycle": state.cycle,
                        "reason": "tool_failure",
                        "failed_tool": last_failure.tool_name,
                        "fallback_action": fallback.action_type,
                        "next_plan": list(state.replan_queue),
                    }
                )

    def _strategic_replan(
        self,
        task: OrchestrationTask,
        state: ReactState
    ) -> None:
        """当常规补证没有提升置信度时，切换证据策略。"""
        stagnation_count = int(state.reflection.get("stagnation_count", 0) or 0)
        missing_sources = self._missing_evidence_sources(task, state)
        state.current_plan = []

        if stagnation_count >= 2:
            if "rag" in missing_sources or task.task_type != TaskType.SIMPLE_QUERY:
                pivot_step = "rag:deep_context"
                pivot_type = "force_rag_pivot"
            elif "web-search" in missing_sources:
                pivot_step = "web-search:external_validation"
                pivot_type = "force_web_pivot"
            else:
                pivot_step = "report-generator:proceed_with_partial"
                pivot_type = "proceed_with_partial"
            message = "Evidence collection stagnant after 2+ cycles"
        elif stagnation_count >= 1:
            pivot_step = "rag:deep_context"
            pivot_type = "add_rag_depth"
            message = "Confidence did not improve in the last cycle"
        else:
            return

        state.replan_queue = self._dedupe_replan_steps(
            [pivot_step],
            state,
            allow_failed_retry=True,
        )
        state.replan_history.append(
            {
                "cycle": state.cycle,
                "reason": "strategic_pivot",
                "pivot_type": pivot_type,
                "message": message,
                "stagnation_count": stagnation_count,
                "confidence_trajectory": list(state.confidence_trajectory),
                "next_plan": list(state.replan_queue),
            }
        )

    def run_phase(
        self,
        phase: str,
        task: OrchestrationTask,
        state: ReactState
    ) -> Tuple[bool, str, List[str]]:
        """执行七步法阶段门禁，并记录阶段推进历史。"""
        moved_any = False
        reasons: List[str] = []
        starting_phase = state.current_phase

        # 一个 ReAct 周期可能一次性补齐多个阶段的输出，允许连续推进到首个缺口。
        for _ in range(7):
            moved, next_phase, phase_reasons, required_outputs = self.phase_tracker.run_phase(
                state.current_phase,
                task,
                state,
                extra_outputs=state.required_outputs,
            )
            state.required_outputs = dict(required_outputs)
            phase_info = self.phase_tracker.phase_tracker(
                state,
                extra_outputs=state.required_outputs,
            )
            history_item = {
                "cycle": state.cycle,
                "from_phase": state.current_phase,
                "to_phase": next_phase,
                "moved_forward": moved,
                "reasons": list(phase_reasons),
                "requirements_status": dict(required_outputs),
                "missing_requirements": phase_info.get("missing_requirements", []),
            }
            state.phase_history.append(history_item)
            reasons.extend(phase_reasons)

            if not moved:
                for item in history_item["missing_requirements"]:
                    gap = f"phase_missing:{state.current_phase}:{item}"
                    if gap not in state.evidence_gaps:
                        state.evidence_gaps.append(gap)
                break

            moved_any = True
            state.current_phase = next_phase
            if next_phase == AnalysisPhase.SELF_REVIEW.value:
                break

        phase_snapshot = self.phase_tracker.phase_tracker(
            state,
            extra_outputs=state.required_outputs,
        )
        if state.reflection:
            state.reflection.update(
                {
                    "current_phase": state.current_phase,
                    "phase_from": starting_phase,
                    "next_phase": phase_snapshot.get("next_phase"),
                    "phase_requirements_met": phase_snapshot.get("phase_requirements_met", False),
                    "phase_missing_requirements": phase_snapshot.get("missing_requirements", []),
                    "phase_requirements_status": phase_snapshot.get("requirements_status", {}),
                    "phase_history": list(state.phase_history),
                }
            )
            if state.reflection_history:
                state.reflection_history[-1] = dict(state.reflection)

        return moved_any, state.current_phase, reasons
    
    def _check_stop_conditions(
        self,
        task: OrchestrationTask,
        state: ReactState
    ) -> bool:
        """检查停止条件"""
        # 证据已足够
        if state.is_complete:
            state.stop_reason = "Evidence sufficient"
            return True
        
        # 检查缺失关键信息
        missing = self._check_missing_critical_evidence(task, state)
        if missing and not self._has_pending_structured_step(state):
            state.stop_reason = f"Missing critical: {missing}"
            return True
        
        return False

    def _has_pending_structured_step(self, state: ReactState) -> bool:
        """判断当前计划里是否还有未执行的结构化数据步骤。"""
        completed = set(state.completed_steps)
        return any(
            step not in completed and ("nl2sql" in step or "targeted-sql-pack" in step)
            for step in state.current_plan
        )

    def _step_succeeded(self, state: ReactState, step: str) -> bool:
        tool_name = step.split(":", 1)[0]
        return any(r.tool_name == tool_name and r.success for r in state.tool_results)

    def _structured_blocks_seen(self, state: ReactState) -> List[str]:
        blocks = []
        for result in state.tool_results:
            if result.tool_name != "targeted-sql-pack" or not isinstance(result.result, dict):
                continue
            for block in result.result.get("blocks", []) or []:
                name = block.get("name")
                if name and name not in blocks:
                    blocks.append(name)
        return blocks

    def _latest_targeted_sql_result(self, state: ReactState) -> Optional[Dict[str, Any]]:
        for result in reversed(state.tool_results):
            if result.tool_name == "targeted-sql-pack" and isinstance(result.result, dict):
                return result.result
        return None

    def _missing_targeted_sql_blocks(self, task: OrchestrationTask, state: ReactState) -> List[str]:
        plan = state.analysis_plan or build_analysis_plan(task)
        target_brand = plan.target_brand if plan else None
        latest = self._latest_targeted_sql_result(state)
        if latest is None:
            return list(REQUIRED_TARGETED_SQL_BLOCKS if target_brand else REQUIRED_TARGETED_SQL_BLOCKS[:4])
        return missing_required_blocks(latest, target_brand=target_brand)

    def _missing_evidence_sources(self, task: OrchestrationTask, state: ReactState) -> List[str]:
        sources = {
            evidence.source
            for evidence in self.evidence_ledger.evidences.values()
        }
        missing = []
        if "rag" not in sources and task.task_type != TaskType.SIMPLE_QUERY:
            missing.append("rag")
        overall_conf, _ = self.evidence_ledger.calculate_overall_confidence()
        needs_external = task.task_type in {
            TaskType.OPPORTUNITY_ASSESSMENT,
            TaskType.COMPREHENSIVE_RESEARCH,
            TaskType.COMPETITOR_ANALYSIS,
        }
        if needs_external and overall_conf < 0.70 and "web-search" not in sources:
            missing.append("web-search")
        return missing

    def _dedupe_replan_steps(
        self,
        steps: List[str],
        state: ReactState,
        allow_failed_retry: bool = False,
    ) -> List[str]:
        deduped = []
        for step in steps:
            if step in deduped:
                continue
            if not allow_failed_retry and self._step_succeeded(state, step):
                continue
            deduped.append(step)
        return deduped

    def _fallback_step_for_tool(self, tool_name: str) -> Optional[str]:
        if tool_name == "targeted-sql-pack":
            return "nl2sql-pg:get_basic_data"
        if tool_name == "nl2sql-pg":
            return "targeted-sql-pack:core_market_metrics"
        if tool_name == "rag":
            return "web-search:fill_document_gap"
        if tool_name == "web-search":
            return None
        return None
    
    def _check_missing_critical_evidence(
        self,
        task: OrchestrationTask,
        state: ReactState
    ) -> Optional[str]:
        """检查缺失的关键证据"""
        # 如果用户问题涉及具体品牌/车型但没有结构化数据
        entities = task.user_intent.entities if task.user_intent else []
        has_structured = any(
            ("nl2sql" in r.tool_name or r.tool_name == "targeted-sql-pack") and r.success
            for r in state.tool_results
        )
        
        if entities and not has_structured:
            return "Brand/model data required but not available"
        
        return None
    
    def _build_result(
        self,
        task: OrchestrationTask,
        state: ReactState
    ) -> OrchestrationResult:
        """构建最终结果"""
        # 从证据账本生成结果
        report = self.evidence_ledger.generate_report()
        analysis_plan = state.analysis_plan or build_analysis_plan(task)
        analysis_plan_dict = analysis_plan.to_dict()
        evidence_store = self._build_evidence_store(report)
        
        # 构建 facts 和 inferences
        facts = []
        inferences = []
        
        for evidence in self.evidence_ledger.evidences.values():
            evidence_ref = {
                "evidence_id": evidence.evidence_id,
                "source": evidence.source,
                "tool": evidence.tool,
                "claim": evidence.claim,
                "confidence": evidence.confidence,
                "time_range": evidence.time_range,
                "data_caliber": evidence.data_caliber,
                "source_grade": evidence.source_grade,
            }
            if evidence.source in ["nl2sql-pg", "rag"]:
                facts.append({
                    "claim": evidence.claim,
                    "content": evidence.content[:200],
                    "source": evidence.source,
                    "confidence": evidence.confidence,
                    "time_range": evidence.time_range,
                    "data_caliber": evidence.data_caliber,
                    "evidence": evidence_ref
                })
            else:
                inferences.append({
                    "claim": evidence.claim,
                    "source": evidence.source,
                    "confidence": evidence.confidence,
                    "evidence": evidence_ref
                })
        
        # 识别机会和风险
        opportunities = self._identify_opportunities(report)
        risks = self._identify_risks(report)
        
        # 置信度
        overall_conf, conf_details = self.evidence_ledger.calculate_overall_confidence()
        
        # 构建 answer
        answer = self._build_answer(task, report, opportunities, risks)
        
        # 冲突
        conflicts = self.evidence_ledger.get_conflicts()
        missing_or_uncertain = []
        
        if conflicts:
            missing_or_uncertain.append(f"存在 {len(conflicts)} 项证据冲突")
        
        if overall_conf < 0.7:
            missing_or_uncertain.append("总体置信度低于70%，需要补充更高质量证据后再用于决策")

        if not state.is_complete:
            missing_or_uncertain.append("证据可能不够完整")

        insight_cards = build_insight_cards(
            analysis_plan=analysis_plan_dict,
            evidence_store=evidence_store,
            confidence=overall_conf,
            reflection=state.reflection,
            quality_summary={},
        )
        seven_step_report = build_seven_step_report(
            task_id=task.task_id,
            question=task.user_intent.raw_query if task.user_intent else "",
            analysis_plan=analysis_plan_dict,
            evidence_store=evidence_store,
            confidence=overall_conf,
            confidence_details=conf_details,
            insight_cards=insight_cards,
            reflection=state.reflection,
            quality_summary={},
            missing_or_uncertain=missing_or_uncertain,
        )
        
        return OrchestrationResult(
            task_id=task.task_id,
            success=state.is_complete or overall_conf >= 0.5,
            user_intent=task.user_intent.to_dict() if task.user_intent else {},
            analysis_plan=analysis_plan_dict,
            answer=answer,
            facts=facts,
            inferences=inferences,
            recommendations=self._generate_recommendations(report, opportunities),
            risks=risks,
            confidence=overall_conf,
            confidence_details=conf_details,
            evidence_sources=[
                {
                    "evidence_id": e.evidence_id,
                    "source": e.source,
                    "tool": e.tool,
                    "claim": e.claim,
                    "time_range": e.time_range,
                    "data_caliber": e.data_caliber,
                    "source_url": e.source_url,
                    "source_date": e.source_date,
                    "source_grade": e.source_grade,
                    "confidence": e.confidence,
                }
                for e in self.evidence_ledger.evidences.values()
            ],
            evidence_ledger=report,
            evidence_store=evidence_store,
            seven_step_report=seven_step_report,
            insight_cards=insight_cards,
            reflection=state.reflection,
            replan_history=state.replan_history,
            dispatched_results=[
                {
                    "target_agent_id": (d.get("request") or {}).get("agent_id"),
                    "source_tool": (d.get("request") or {}).get("source_tool"),
                    "cycle": d.get("cycle"),
                    "step": d.get("step"),
                    "ok": (d.get("response") or {}).get("ok", False),
                    "error": (d.get("response") or {}).get("error"),
                    "duration_seconds": (d.get("response") or {}).get("duration_seconds"),
                    "response_chars": len((d.get("response") or {}).get("text", "") or "") if (d.get("response") or {}).get("ok") else 0,
                }
                for d in state.dispatched_results
            ],
            dispatched_count=len(state.dispatched_results),
            dispatched_ok_count=sum(1 for d in state.dispatched_results if (d.get("response") or {}).get("ok")),
            missing_or_uncertain=missing_or_uncertain,
            next_steps=self._generate_next_steps(task, state),
            errors=[r.error for r in state.tool_results if not r.success and r.error],
            stop_reason=state.stop_reason,
            cycles_used=state.cycle
        )
    
    def _apply_quality_gate(self, result: OrchestrationResult) -> OrchestrationResult:
        """应用质量门禁"""
        result_dict = result.to_dict()
        passed, checks = self.quality_gate.run_all(result_dict)
        failed_checks = [
            {
                "check": item.check_name,
                "level": getattr(item.level, "value", str(item.level)),
                "message": item.message,
                "suggestions": item.suggestions,
            }
            for item in checks
            if not item.passed
        ]

        result.quality_passed = passed
        result.failed_quality_checks = failed_checks
        result.quality_summary = {
            "quality_passed": passed,
            "total_checks": len(checks),
            "passed_checks": sum(1 for item in checks if item.passed),
            "failed_checks": failed_checks,
        }
        result.insight_cards = build_insight_cards(
            analysis_plan=result.analysis_plan,
            evidence_store=result.evidence_store,
            confidence=result.confidence,
            reflection=result.reflection,
            quality_summary=result.quality_summary,
        )
        result.seven_step_report = build_seven_step_report(
            task_id=result.task_id,
            question=result.user_intent.get("raw_query", ""),
            analysis_plan=result.analysis_plan,
            evidence_store=result.evidence_store,
            confidence=result.confidence,
            confidence_details=result.confidence_details,
            insight_cards=result.insight_cards,
            reflection=result.reflection,
            quality_summary=result.quality_summary,
            missing_or_uncertain=result.missing_or_uncertain,
        )
        
        if not passed:
            logger.warning("Quality gate not passed")
        
        return result
    
    # ===== 工具实现 =====

    def _tool_phase_tracker(self, param: str, task: OrchestrationTask, state: ReactState) -> Dict:
        """返回当前七步法阶段状态，供外部 trace 和调试查看。"""
        snapshot = self.phase_tracker.phase_tracker(
            state,
            extra_outputs=state.required_outputs,
        )
        return {
            "success": True,
            "phase_state": snapshot,
            "phase_history": list(state.phase_history),
            "required_outputs": dict(state.required_outputs),
        }
    
    def _tool_targeted_sql_pack(self, param: str, task: OrchestrationTask, state: ReactState) -> Dict:
        """Run the orchestrator-owned targeted SQL pack."""
        analysis_plan = state.analysis_plan or build_analysis_plan(task)
        try:
            data = self._run_targeted_sql_pack(analysis_plan)
            return {
                **data,
                "evidences": build_targeted_sql_evidences(data, analysis_plan),
            }
        except Exception as exc:
            logger.error(f"targeted_sql_pack failed: {exc}")
            failed = {
                "success": False,
                "error": str(exc),
                "query_mode": "targeted_sql_pack",
                "blocks": [],
                "results": [],
            }
            return {
                **failed,
                "evidences": build_targeted_sql_evidences(failed, analysis_plan),
            }

    def _run_targeted_sql_pack(self, analysis_plan: AnalysisPlan) -> Dict[str, Any]:
        return run_targeted_sql_pack(analysis_plan)

    def _tool_nl2sql(self, param: str, task: OrchestrationTask, state: ReactState) -> Dict:
        """结构化数据查询工具"""
        try:
            # 导入实际的数据库查询模块
            sys.path.insert(0, r"E:\AI\data\envs\car_agent_env\ai-decision\rag-engine")
            from market_strategy.knowledge_base import MarketKnowledgeBase
            
            kb = MarketKnowledgeBase()
            analysis_plan = state.analysis_plan or build_analysis_plan(task)
            time_range = analysis_plan.time_range
            
            # 根据参数决定查询类型
            if "brand" in param.lower():
                data = kb.get_sales_by_brand(
                    time_range=time_range,
                    top_n=20
                )
            elif "trend" in param.lower():
                data = kb.get_sales_trend()
            elif "overview" in param.lower() or "market" in param.lower():
                data = kb.get_market_overview(
                    time_range=time_range
                )
            else:
                data = kb.get_data_summary()
            
            kb.close()
            
            # 返回证据
            return {
                "data": data,
                "evidence": build_sql_evidence(
                    param=param,
                    data=data,
                    time_range=time_range,
                    user_intent=task.user_intent
                )
            }
        
        except Exception as e:
            logger.error(f"nl2sql tool failed: {e}")
            raise
    
    def _tool_rag_retrieve(self, param: str, task: OrchestrationTask, state: ReactState) -> Dict:
        """RAG 检索工具（带过滤和 rejected evidence 追踪）"""
        try:
            sys.path.insert(0, r"E:\AI\data\envs\car_agent_env\ai-decision\rag-engine")
            from retrieval.retriever import retrieve

            analysis_plan = state.analysis_plan or build_analysis_plan(task)
            query = analysis_plan.rag_query or (task.user_intent.raw_query if task.user_intent else param)

            # === 从 analysis_plan 构建 RAG 过滤条件 ===
            metadata_filter = {}
            if analysis_plan.target_brand:
                metadata_filter["brand"] = analysis_plan.target_brand

            # 解析时间范围 → 限制只检索近期文档
            time_limit = None
            if analysis_plan.time_range:
                import re
                m = re.search(r"(\d+)\s*个月", analysis_plan.time_range)
                if m:
                    time_limit = int(m.group(1))

            # 调用 retrieve（宽召回 top_k=20，后续过滤）
            raw_results = retrieve(
                query=query,
                top_k=20,
                metadata_filter=metadata_filter if metadata_filter else None,
                min_score=0.30   # 最低相似度阈值
            )

            # === 质量过滤：品牌/时间/主题一致性 ===
            rejected_evidence = []
            filtered_results = []
            for r in raw_results:
                meta = r.get("metadata", {})
                reasons = []

                # 品牌过滤：用户指定了品牌，检索结果却不相关
                if analysis_plan.target_brand and analysis_plan.target_brand not in r["document"]:
                    reasons.append(f"品牌『{analysis_plan.target_brand}』在文档中未出现")

                # 时间过滤：只保留近期文档（允许部分命中）
                if time_limit and meta.get("publish_date"):
                    try:
                        doc_year = int(str(meta["publish_date"])[:4])
                        import datetime
                        current_year = datetime.datetime.now().year
                        if current_year - doc_year > 2:
                            reasons.append(f"文档日期 {meta['publish_date']} 超过 2 年")
                    except (ValueError, TypeError):
                        pass

                # 来源可信度过滤：低质量来源
                source = meta.get("source", "")
                low_quality_sources = ["论坛", "个人博客", "未知名来源"]
                if source in low_quality_sources:
                    reasons.append(f"来源『{source}』可信度低")

                if reasons:
                    rejected_evidence.append({
                        "document": r["document"][:200],
                        "score": r["score"],
                        "source": source,
                        "rejection_reason": "; ".join(reasons)
                    })
                else:
                    filtered_results.append(r)

            # 最多保留 top_k=5
            results = filtered_results[:5]

            # === 构建证据（带 URL/日期/来源等级）===
            contents = [r["document"][:300] for r in results]
            evidence_content = "; ".join(contents)

            # 来源等级
            def _grade_source(src: str) -> str:
                high = ["乘联会", "中汽协", "国家统计局", "工信部", "发改委", "财政部", "咨询机构"]
                medium = ["汽车之家", "易车", "懂车帝", "盖世汽车", "第一财经"]
                for h in high:
                    if h in src:
                        return "high"
                for m in medium:
                    if m in src:
                        return "medium"
                return "low"

            evidence_list = []
            for r in results:
                meta = r.get("metadata", {})
                src = meta.get("source", "未知名来源")
                evidence_list.append({
                    "source_url": meta.get("file_name", ""),
                    "source_date": meta.get("publish_date", ""),
                    "source_grade": _grade_source(src),
                    "source_credibility": {"high": 0.85, "medium": 0.70, "low": 0.50}.get(_grade_source(src), 0.60),
                    "coverage_dimensions": ["行业报告", "政策背景", "趋势解释"],
                    "content": r["document"][:300]
                })

            return {
                "results": results,
                "rejected_evidence": rejected_evidence,
                "evidence": build_rag_evidence(
                    results=results,
                    query=query,
                    time_range=analysis_plan.time_range,
                    user_intent=task.user_intent
                ),
                "evidence_details": evidence_list
            }

        except Exception as e:
            logger.error(f"RAG tool failed: {e}")
            raise
    def _tool_analysis_framework(self, param: str, task: OrchestrationTask, state: ReactState) -> Dict:
        """Run the automotive-strategy-analysis seven-stage Skill contract."""
        report_context = self.evidence_ledger.generate_report()
        return build_framework_analysis(
            framework=param or "automotive_strategy_seven_stage",
            task=task,
            state=state,
            evidence_report=report_context,
            workspace_root=self.workspace_root,
        )
    
    def _tool_pest(self, param: str, task: OrchestrationTask, state: ReactState) -> Dict:
        return self._tool_analysis_framework("pest", task, state)
    
    def _tool_swot(self, param: str, task: OrchestrationTask, state: ReactState) -> Dict:
        return self._tool_analysis_framework("swot", task, state)
    
    def _tool_porter(self, param: str, task: OrchestrationTask, state: ReactState) -> Dict:
        return self._tool_analysis_framework("porter", task, state)
    
    def _tool_4p(self, param: str, task: OrchestrationTask, state: ReactState) -> Dict:
        return self._tool_analysis_framework("4p", task, state)
    
    def _tool_report_generate(self, param: str, task: OrchestrationTask, state: ReactState) -> Dict:
        """报告生成工具"""
        report = self._generate_markdown_report(task, state)
        report_context = self.evidence_ledger.generate_report()
        evidence_store = self._build_evidence_store(report_context)
        overall_conf, conf_details = self.evidence_ledger.calculate_overall_confidence()
        analysis_plan = (state.analysis_plan or build_analysis_plan(task)).to_dict()
        insight_cards = build_insight_cards(
            analysis_plan=analysis_plan,
            evidence_store=evidence_store,
            confidence=overall_conf,
            reflection=state.reflection,
            quality_summary={},
        )
        return {
            "report": report,
            "seven_step_report": report,
            "insight_cards": insight_cards,
            "confidence_details": conf_details,
            "evidence": Evidence(
                source="report-generator",
                tool="report",
                claim="报告已生成",
                content=report[:200],
                data_caliber="基于证据账本的报告生成结果，非新增事实来源",
                source_credibility=0.55,
                coverage_dimensions=["报告"],
                coverage_score=0.50,
                confidence=0.7
            )
        }

    def _tool_competitor_analyst(self, param: str, task: OrchestrationTask, state: ReactState) -> Dict:
        """Expose agents/competitor-analyst as an orchestrator-managed tool."""
        return run_specialist_agent(
            agent_id="competitor-analyst",
            param=param,
            task=task,
            state=state,
            workspace_root=self.workspace_root,
            evidence_report=self.evidence_ledger.generate_report(),
        )

    def _tool_cost_analyst(self, param: str, task: OrchestrationTask, state: ReactState) -> Dict:
        """Expose agents/cost-analyst as an orchestrator-managed tool."""
        return run_specialist_agent(
            agent_id="cost-analyst",
            param=param,
            task=task,
            state=state,
            workspace_root=self.workspace_root,
            evidence_report=self.evidence_ledger.generate_report(),
        )

    def _tool_report_generator_agent(self, param: str, task: OrchestrationTask, state: ReactState) -> Dict:
        """Expose agents/report-generator as a report QA specialist."""
        return run_specialist_agent(
            agent_id="report-generator",
            param=param,
            task=task,
            state=state,
            workspace_root=self.workspace_root,
            evidence_report=self.evidence_ledger.generate_report(),
        )
    
    def _tool_web_search(self, param: str, task: OrchestrationTask, state: ReactState) -> Dict:
        """Tavily 网络搜索工具。"""
        analysis_plan = state.analysis_plan or build_analysis_plan(task)
        query = analysis_plan.tavily_query or self._build_tavily_query(param, task)
        try:
            raw = self._run_tavily_search(query=query, max_results=6)
        except Exception as exc:
            fallback = Evidence(
                source="web-search",
                tool="tavily-search",
                claim=f"Tavily 检索失败: {query[:80]}",
                content=str(exc),
                time_range="实时外部检索；未获取到可用结果",
                data_caliber="Tavily 外部网页检索口径；本次调用失败",
                source_credibility=0.20,
                coverage_dimensions=["外部补证"],
                coverage_score=0.05,
                confidence=0.2,
                limitations=[f"Tavily 调用失败: {exc}"]
            )
            return {
                "success": False,
                "query": query,
                "results": [],
                "rejected": [],
                "evidences": [fallback],
                "error": str(exc),
            }

        filtered = self._filter_tavily_results(raw, task)
        evidences = self._build_tavily_evidences(query, filtered, task)
        if not evidences:
            rejected_summary = "; ".join(
                f"{item.get('reason')}:{item.get('title') or item.get('url')}"
                for item in filtered.get("rejected", [])[:5]
            ) or "Tavily 未返回合格网页证据"
            evidences = [
                Evidence(
                    source="web-search",
                    tool="tavily-search",
                    claim=f"Tavily 外部补证无合格结果: {query[:80]}",
                    content=rejected_summary,
                    time_range="实时外部检索；无合格结果",
                    data_caliber="Tavily 外部网页检索口径；低质量或实体不匹配结果已剔除",
                    source_credibility=0.25,
                    coverage_dimensions=["外部补证"],
                    coverage_score=0.10,
                    confidence=0.25,
                    limitations=["无合格 Tavily 结果", rejected_summary[:180]]
                )
            ]

        return {
            "success": True,
            "query": query,
            "raw_count": filtered.get("raw_count", 0),
            "results": filtered.get("accepted", []),
            "rejected": filtered.get("rejected", []),
            "rejected_count": len(filtered.get("rejected", [])),
            "evidences": evidences,
        }

    def _run_tavily_search(self, query: str, max_results: int = 6) -> Dict[str, Any]:
        """调用本地 tavily-search skill。"""
        workspace_root = Path(__file__).resolve().parents[3]
        tavily_script = workspace_root / "skills" / "tavily-search" / "scripts" / "tavily_search.py"
        if not tavily_script.exists():
            raise RuntimeError(f"tavily_search.py not found: {tavily_script}")

        spec = importlib.util.spec_from_file_location("workspace_tavily_search", tavily_script)
        if spec is None or spec.loader is None:
            raise RuntimeError("cannot load tavily_search.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.tavily_search(
            query=query,
            max_results=max(1, min(max_results, 10)),
            include_answer=True,
            search_depth="basic",
        )

    def _build_evidence_store(self, report: Dict[str, Any]) -> Dict[str, Any]:
        """Build business-facing D/R/W evidence ids from the ledger."""
        store = {"D": [], "R": [], "W": [], "A": []}
        counters = {"D": 0, "R": 0, "W": 0, "A": 0}
        source_to_bucket = {
            "nl2sql-pg": "D",
            "rag": "R",
            "web-search": "W",
        }
        for evidence in report.get("evidences", []) or []:
            bucket = source_to_bucket.get(evidence.get("source"), "A")
            counters[bucket] += 1
            item = {
                "id": f"{bucket}{counters[bucket]}",
                "evidence_id": evidence.get("evidence_id"),
                "source": evidence.get("source"),
                "tool": evidence.get("tool"),
                "claim": evidence.get("claim"),
                "content": evidence.get("content"),
                "time_range": evidence.get("time_range"),
                "data_caliber": evidence.get("data_caliber"),
                "source_url": evidence.get("source_url"),
                "source_date": evidence.get("source_date"),
                "source_grade": evidence.get("source_grade"),
                "confidence": evidence.get("confidence"),
                "coverage_score": evidence.get("coverage_score"),
                "adoption_status": "accepted",
                "rejection_reason": self._extract_rejection_reason(evidence),
                "business_support": self._business_support_label(bucket),
            }
            store[bucket].append(item)
        store["summary"] = {
            "structured": len(store["D"]),
            "rag": len(store["R"]),
            "web": len(store["W"]),
            "analysis": len(store["A"]),
        }
        return store

    def _extract_rejection_reason(self, evidence: Dict[str, Any]) -> str:
        limitations = evidence.get("limitations") or []
        if not limitations:
            return ""
        return "; ".join(str(item) for item in limitations if item)

    def _business_support_label(self, bucket: str) -> str:
        return {
            "D": "结构化市场指标支撑",
            "R": "业务文档/政策/行业报告支撑",
            "W": "外部实时网页补证",
            "A": "分析框架推断支撑",
        }.get(bucket, "证据支撑")

    def _build_tavily_query(self, param: str, task: OrchestrationTask) -> str:
        # Fallback path for callers that do not pass ReactState.
        intent = task.user_intent
        raw_query = intent.raw_query if intent else ""
        time_range = intent.time_range if intent else ""
        entities = " ".join(intent.entities or []) if intent else ""
        topic = param.replace("_", " ") if param else "market strategy"
        terms = "销量 交付 市场份额 竞品 战略 政策"
        return " ".join(part for part in [entities, raw_query, time_range, topic, terms] if part)

    def _filter_tavily_results(self, raw: Dict[str, Any], task: OrchestrationTask) -> Dict[str, Any]:
        rows = raw.get("results") or []
        entities = task.user_intent.entities if task.user_intent else []
        accepted = []
        rejected = []
        for item in rows:
            normalized = self._normalize_tavily_item(item)
            haystack = " ".join([
                normalized.get("title", ""),
                normalized.get("url", ""),
                normalized.get("snippet", ""),
            ])
            source_grade = self._source_grade(normalized.get("url", ""), normalized.get("title", ""))
            entity_ok = True if not entities else self._contains_any(haystack, entities)
            if source_grade == "C":
                reason = "low_quality_source"
            elif not entity_ok:
                reason = "entity_mismatch"
            else:
                reason = ""

            normalized["source_grade"] = source_grade
            normalized["source_date"] = self._infer_source_date(
                normalized.get("title", ""),
                normalized.get("snippet", ""),
                normalized.get("url", ""),
            )
            normalized["coverage_score"] = self._web_coverage_score(normalized, task, entity_ok)
            normalized["source_credibility"] = self._source_credibility_from_grade(source_grade)

            if reason:
                rejected_item = dict(normalized)
                rejected_item["rejection_reason"] = reason
                rejected.append(rejected_item)
            else:
                normalized["rejection_reason"] = ""
                accepted.append(normalized)

        return {
            "raw_count": len(rows),
            "accepted": accepted,
            "rejected": rejected,
            "answer": raw.get("answer"),
        }

    def _normalize_tavily_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "title": str(item.get("title") or ""),
            "url": str(item.get("url") or item.get("link") or ""),
            "snippet": str(item.get("snippet") or item.get("content") or ""),
        }

    def _build_tavily_evidences(
        self,
        query: str,
        filtered: Dict[str, Any],
        task: OrchestrationTask
    ) -> List[Evidence]:
        evidences = []
        time_range = task.user_intent.time_range if task.user_intent else "实时外部检索"
        rejected_summary = self._rejected_summary(filtered.get("rejected", []))
        for item in filtered.get("accepted", [])[:5]:
            grade = item.get("source_grade") or "B"
            coverage_score = item.get("coverage_score", 0.5)
            credibility = item.get("source_credibility", 0.55)
            limitations = []
            if rejected_summary:
                limitations.append(f"剔除结果: {rejected_summary[:180]}")
            if item.get("source_date") == "unknown":
                limitations.append("未识别到来源日期")
            evidences.append(
                Evidence(
                    source="web-search",
                    tool="tavily-search",
                    claim=f"Tavily 外部补证: {item.get('title') or query[:80]}",
                    content=(
                        f"title={item.get('title')}; url={item.get('url')}; "
                        f"date={item.get('source_date')}; source_grade={grade}; "
                        f"rejection_reason={item.get('rejection_reason', '') or 'accepted'}; "
                        f"snippet={item.get('snippet')[:500]}"
                    ),
                    time_range=f"{time_range}; source_date={item.get('source_date')}",
                    data_caliber="Tavily 外部网页检索口径；按实体匹配和来源等级过滤",
                    source_url=item.get("url", ""),
                    source_date=item.get("source_date", ""),
                    source_grade=grade,
                    source_credibility=credibility,
                    coverage_dimensions=["外部补证", "URL", "来源日期", "来源等级", "剔除原因"],
                    coverage_score=coverage_score,
                    confidence=round(min(0.85, 0.35 * credibility + 0.45 * coverage_score + 0.20), 3),
                    limitations=limitations,
                )
            )
        return evidences

    def _source_grade(self, url: str, title: str = "") -> str:
        probe = f"{url} {title}".lower()
        high_quality_domains = [
            "caam.org.cn",
            "cpcaauto.com",
            "gov.cn",
            "miit.gov.cn",
            "xinhuanet.com",
            "reuters.com",
            "autohome.com.cn",
            "yiche.com",
            "d1ev.com",
            "gasgoo.com",
            "stcn.com",
            "bydglobal.com",
            "tesla.cn",
            "mi.com",
        ]
        low_quality_domains = [
            "guba.eastmoney.com",
            "xueqiu.com",
            "stock",
            "forecast",
        ]
        if any(domain in probe for domain in high_quality_domains):
            return "A"
        if any(domain in probe for domain in low_quality_domains):
            return "C"
        return "B"

    def _source_credibility_from_grade(self, grade: str) -> float:
        return {"A": 0.85, "B": 0.62, "C": 0.30}.get(grade, 0.50)

    def _infer_source_date(self, *parts: Any) -> str:
        text = " ".join(str(part or "") for part in parts)
        match = re.search(r"20\d{2}(?:[-/.年]\d{1,2}(?:[-/.月]\d{1,2}日?)?)?", text)
        if not match:
            return "unknown"
        return (
            match.group(0)
            .replace("年", "-")
            .replace("月", "-")
            .replace("日", "")
            .replace("/", "-")
            .replace(".", "-")
        )

    def _contains_any(self, text: str, needles: List[str]) -> bool:
        text_lower = (text or "").lower()
        for needle in needles or []:
            if not needle:
                continue
            if needle.isascii():
                if re.search(rf"(?<![A-Za-z0-9]){re.escape(needle.lower())}(?![A-Za-z0-9])", text_lower):
                    return True
            elif needle in text:
                return True
        return False

    def _web_coverage_score(self, item: Dict[str, Any], task: OrchestrationTask, entity_ok: bool) -> float:
        haystack = " ".join([item.get("title", ""), item.get("snippet", ""), item.get("url", "")])
        theme_terms = ["销量", "交付", "市场", "份额", "竞品", "价格", "政策", "战略", "出口", "渠道"]
        theme_hits = sum(1 for term in theme_terms if term in haystack)
        score = 0.25 + min(0.35, theme_hits * 0.07)
        if entity_ok:
            score += 0.20
        if item.get("source_date") and item.get("source_date") != "unknown":
            score += 0.10
        if item.get("source_grade") == "A":
            score += 0.10
        return round(max(0.05, min(1.0, score)), 3)

    def _rejected_summary(self, rejected: List[Dict[str, Any]]) -> str:
        if not rejected:
            return ""
        parts = []
        for item in rejected[:5]:
            label = item.get("title") or item.get("url") or "untitled"
            parts.append(f"{item.get('rejection_reason')}:{label[:60]}")
        return "; ".join(parts)
    
    # ===== 辅助方法 =====
    
    def _identify_opportunities(self, report: Dict) -> List[Dict]:
        """识别机会点"""
        opportunities = []
        # 简化实现，实际应该基于证据分析
        return opportunities
    
    def _identify_risks(self, report: Dict) -> List[Dict]:
        """识别风险"""
        risks = []
        # 检查冲突
        conflicts = self.evidence_ledger.get_conflicts()
        if conflicts:
            risks.append({
                "item": "存在证据冲突",
                "probability": "中",
                "impact": "中",
                "mitigation": "需要交叉验证"
            })
        return risks
    
    def _generate_recommendations(self, report: Dict, opportunities: List[Dict]) -> List[str]:
        """生成建议"""
        recs = []
        if opportunities:
            recs.append("建议深入分析识别的机会点")
        recs.append("建议收集更多结构化数据以提高置信度")
        return recs
    
    def _generate_next_steps(self, task: OrchestrationTask, state: ReactState) -> List[str]:
        """生成下一步"""
        steps = []
        if not state.is_complete:
            steps.append("补充更多证据")
        steps.append("建议进行深度竞品分析")
        steps.append("建议引入政策数据分析")
        return steps
    
    def _build_answer(
        self,
        task: OrchestrationTask,
        report: Dict,
        opportunities: List[Dict],
        risks: List[Dict]
    ) -> str:
        """构建自然语言答案"""
        conf = report.get("summary", {}).get("overall_confidence", 0)
        intent = task.user_intent
        analysis_plan = build_analysis_plan(task)
        time_range = intent.time_range if intent else "unknown"
        entities = intent.entities if intent else []
        
        answer_parts = []
        
        # 基本信息
        answer_parts.append(f"基于现有证据的分析（置信度: {conf:.0%}）")
        answer_parts.append(f"分析范围: {time_range}")
        if entities:
            answer_parts.append("涉及对象: " + "、".join(entities))
        answer_parts.append(
            "统一分析计划: "
            f"品牌={analysis_plan.target_brand or '未指定'}；"
            f"市场={analysis_plan.market_scope}；"
            f"时间={analysis_plan.time_range}"
        )
        answer_parts.append("")
        
        # 证据来源
        sources = report.get("by_source", {})
        if sources:
            source_list = [f"{k}: {v}条" for k, v in sources.items() if v > 0]
            if source_list:
                answer_parts.append("数据来源: " + ", ".join(source_list))
                answer_parts.append("")

        confidence_details = report.get("summary", {}).get("confidence_details", {})
        if confidence_details:
            answer_parts.append("置信度计算:")
            answer_parts.append(
                "- 数据覆盖={data:.0%}，RAG覆盖={rag:.0%}，来源可信度={source:.0%}，冲突系数={conflict:.0%}".format(
                    data=confidence_details.get("data_coverage_factor", 0),
                    rag=confidence_details.get("rag_coverage_factor", 0),
                    source=confidence_details.get("source_credibility_factor", 0),
                    conflict=confidence_details.get("conflict_factor", 0),
                )
            )
            answer_parts.append("")

        evidences = report.get("evidences", [])
        fact_evidences = [
            e for e in evidences
            if e.get("source") in ["nl2sql-pg", "rag"]
        ]
        inference_evidences = [
            e for e in evidences
            if e.get("source") not in ["nl2sql-pg", "rag"]
        ]

        if fact_evidences:
            answer_parts.append("事实依据:")
            for evidence in fact_evidences[:4]:
                content = self._summarize_evidence_content(evidence.get("content", ""))
                answer_parts.append(
                    f"- [{evidence.get('source')}] {evidence.get('claim')}: {content}"
                )
                answer_parts.append(
                    f"  口径: {evidence.get('data_caliber', 'unknown')}；时间范围: {evidence.get('time_range', 'unknown')}"
                )
            answer_parts.append("")

        if inference_evidences:
            answer_parts.append("分析判断:")
            for evidence in inference_evidences[:4]:
                answer_parts.append(
                    f"- [{evidence.get('source')}] {evidence.get('claim')} "
                    f"(置信度 {evidence.get('confidence', 0):.0%})"
                )
            answer_parts.append("")

        if evidences:
            answer_parts.append("证据账本:")
            for idx, evidence in enumerate(evidences[:8], 1):
                answer_parts.append(
                    f"- E{idx} | {evidence.get('source')} | {evidence.get('claim')} | "
                    f"置信度 {evidence.get('confidence', 0):.0%} | "
                    f"口径 {evidence.get('data_caliber', 'unknown')} | "
                    f"时间 {evidence.get('time_range', 'unknown')}"
                )
            if len(evidences) > 8:
                answer_parts.append(f"- 另有 {len(evidences) - 8} 条证据见 evidence_ledger 字段")
            answer_parts.append("")
        
        # 机会和风险
        if opportunities:
            answer_parts.append("识别到的机会:")
            for opp in opportunities:
                answer_parts.append(f"- {opp.get('item', 'N/A')}")
            answer_parts.append("")
        
        if risks:
            answer_parts.append("风险提示:")
            for risk in risks:
                answer_parts.append(f"- {risk.get('item', 'N/A')}: {risk.get('mitigation', '')}")
            answer_parts.append("")
        
        return "\n".join(answer_parts)

    def _summarize_evidence_content(self, content: str, max_len: int = 160) -> str:
        """压缩证据内容，避免答案只展示原始长 JSON/表格。"""
        if not content:
            return "无摘要"
        structured_summary = self._summarize_structured_content(content)
        if structured_summary:
            return structured_summary
        compact = " ".join(str(content).split())
        if len(compact) <= max_len:
            return compact
        return compact[:max_len].rstrip() + "..."

    def _summarize_structured_content(self, content: str) -> str:
        """为常见 SQL 结果生成紧凑摘要。"""
        import re

        text = str(content)

        brand_rows = re.findall(
            r"'brand': '([^']+)', 'sales': (\d+), 'model_count': (\d+), 'share': ([\d.]+)",
            text
        )
        if brand_rows:
            items = []
            for brand, sales, model_count, share in brand_rows[:3]:
                items.append(
                    f"{brand}销量{int(sales):,}辆、份额{float(share):.2f}%、车型{model_count}款"
                )
            return "；".join(items)

        total_sales = re.search(r"'total_sales': (\d+)", text)
        avg_monthly = re.search(r"'avg_monthly_sales': Decimal\('([^']+)'\)", text)
        brand_count = re.search(r"'brand_count': (\d+)", text)
        model_count = re.search(r"'model_count': (\d+)", text)
        if total_sales:
            parts = [f"总销量{int(total_sales.group(1)):,}辆"]
            if avg_monthly:
                parts.append(f"月均销量{float(avg_monthly.group(1)):,.0f}辆")
            if brand_count:
                parts.append(f"覆盖品牌{brand_count.group(1)}个")
            if model_count:
                parts.append(f"覆盖车型{model_count.group(1)}个")
            return "，".join(parts)

        return ""
    
    def _generate_markdown_report(
        self,
        task: OrchestrationTask,
        state: ReactState
    ) -> str:
        """生成七步法 Markdown 报告。"""
        report = self.evidence_ledger.generate_report()
        evidence_store = self._build_evidence_store(report)
        overall_conf, conf_details = self.evidence_ledger.calculate_overall_confidence()
        analysis_plan = (state.analysis_plan or build_analysis_plan(task)).to_dict()
        insight_cards = build_insight_cards(
            analysis_plan=analysis_plan,
            evidence_store=evidence_store,
            confidence=overall_conf,
            reflection=state.reflection,
            quality_summary={},
        )
        missing_or_uncertain = []
        if report.get("conflicts"):
            missing_or_uncertain.append(f"存在 {len(report.get('conflicts') or [])} 项证据冲突")
        if overall_conf < 0.7:
            missing_or_uncertain.append("总体置信度低于70%，需要补充更高质量证据后再用于决策")
        if not state.is_complete:
            missing_or_uncertain.append("证据可能不够完整")
        return build_seven_step_report(
            task_id=task.task_id,
            question=task.user_intent.raw_query if task.user_intent else "",
            analysis_plan=analysis_plan,
            evidence_store=evidence_store,
            confidence=overall_conf,
            confidence_details=conf_details,
            insight_cards=insight_cards,
            reflection=state.reflection,
            quality_summary={},
            missing_or_uncertain=missing_or_uncertain,
        )


def create_orchestrator(
    event_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    llm_plan_provider: Optional[Callable[[Dict[str, Any]], List[str]]] = None,
    callback_url: Optional[str] = None,
    session_id: Optional[str] = None,
) -> StrategyOrchestrator:
    """创建编排器实例

    2026-06-29 大管家补全：支持 callback_url + session_id 两个新参数。
    - 若调用方显式传入 event_callback，优先使用（向后兼容）
    - 若未传 event_callback 但传了 callback_url+session_id，自动构造 HTTP POST 回调
      把 ReAct 事件推送到 FastAPI 18003 /callback 端点
    - 都不传则没有回调（向后兼容原有调用方式）
    """
    if event_callback is None and callback_url and session_id:
        event_callback = _http_event_callback(callback_url, session_id)
        logger.info(
            "orchestrator HTTP callback enabled: %s/callback (session_id=%s)",
            callback_url.rstrip("/"),
            session_id,
        )
    return StrategyOrchestrator(
        event_callback=event_callback,
        llm_plan_provider=llm_plan_provider,
    )


def orchestrate_task(
    query: str,
    time_range: str = "最近12个月",
    entities: List[str] = None,
    target_output: OutputFormat = OutputFormat.NATURAL_LANGUAGE,
    event_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    callback_url: Optional[str] = None,
    session_id: Optional[str] = None,
) -> OrchestrationResult:
    """
    便捷函数：直接编排用户查询

    主 Agent 调用此函数。

    2026-06-29 大管家补全：新增 callback_url + session_id 两个可选参数。
    透传给 create_orchestrator()，由其构造 HTTP 回调函数。
    """
    # 创建任务
    task = create_task_from_user_query(
        query=query,
        target_output=target_output,
        time_range=time_range,
        entities=entities
    )

    # 执行编排
    orchestrator = create_orchestrator(
        event_callback=event_callback,
        callback_url=callback_url,
        session_id=session_id,
    )
    result = orchestrator.execute(task)

    return result

