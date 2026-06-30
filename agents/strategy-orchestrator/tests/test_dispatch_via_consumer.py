"""A.Option A: verify orchestrator inline-triggers sessions_send via _trigger_sessions_send (no caller dependency)."""

import ast
from pathlib import Path

ORCH_ROOT = Path(r"C:\Users\11489\.openclaw\workspace-strategy-orchestrator")
ORCH_PATH = ORCH_ROOT / "agents" / "strategy-orchestrator" / "executors" / "orchestrator.py"

src = ORCH_PATH.read_text(encoding="utf-8")
tree = ast.parse(src)


def find_dataclass(tree, class_name):
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return node
    return None


def get_field_names(class_node):
    names = set()
    for f in class_node.body:
        if isinstance(f, ast.AnnAssign) and isinstance(f.target, ast.Name):
            names.add(f.target.id)
    return names


def find_function(tree, func_name):
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            return node
    return None


def get_field_type(class_node, field_name):
    for f in class_node.body:
        if isinstance(f, ast.AnnAssign) and isinstance(f.target, ast.Name) and f.target.id == field_name:
            return ast.unparse(f.annotation)
    return None


# ============================================================
# Test 1: ToolResult has dispatch_request AND dispatch_response
# ============================================================
tool_result_cls = find_dataclass(tree, "ToolResult")
assert tool_result_cls is not None, "ToolResult class not found"
tr_fields = get_field_names(tool_result_cls)
assert "dispatch_request" in tr_fields, f"ToolResult.dispatch_request missing; fields={tr_fields}"
dr_type = get_field_type(tool_result_cls, "dispatch_request")
assert "Dict" in dr_type and "Optional" in dr_type, f"dispatch_request must be Optional[Dict]; got {dr_type}"
assert "dispatch_response" in tr_fields, f"ToolResult.dispatch_response missing (Option A); fields={tr_fields}"
dresp_type = get_field_type(tool_result_cls, "dispatch_response")
assert "Dict" in dresp_type and "Optional" in dresp_type, f"dispatch_response must be Optional[Dict]; got {dresp_type}"
print("PASS test_tool_result_has_dispatch_request_and_response")


# ============================================================
# Test 2: ReactState has dispatched_results (not dispatch_queue)
# ============================================================
react_state_cls = find_dataclass(tree, "ReactState")
assert react_state_cls is not None, "ReactState class not found"
rs_fields = get_field_names(react_state_cls)
assert "dispatched_results" in rs_fields, f"ReactState.dispatched_results missing (Option A); fields={rs_fields}"
dr_type2 = get_field_type(react_state_cls, "dispatched_results")
assert "List" in dr_type2 and "Dict" in dr_type2, f"dispatched_results must be List[Dict]; got {dr_type2}"
assert "dispatch_queue" not in rs_fields, f"Old dispatch_queue should be REMOVED in Option A; fields={rs_fields}"
print("PASS test_react_state_has_dispatched_results_not_queue")


# ============================================================
# Test 3: _execute_step has dispatch_via detection
# ============================================================
exec_step = find_function(tree, "_execute_step")
assert exec_step is not None, "_execute_step function not found"
exec_src = ast.unparse(exec_step)
assert "dispatch_via" in exec_src, "_execute_step must reference dispatch_via"
assert ("\"sessions_send\"" in exec_src) or ("'sessions_send'" in exec_src), "_execute_step must check for sessions_send"
assert "dispatch_request" in exec_src, "_execute_step must produce dispatch_request"
assert "agent_id" in exec_src and "message" in exec_src, "_execute_step must extract agent_id and message"
print("PASS test_execute_step_consumes_dispatch_via")


# ============================================================
# Test 4: main loop INLINE-triggers _trigger_sessions_send (no queue append)
# ============================================================
full_source = ast.unparse(tree)
assert "_trigger_sessions_send" in full_source, "orchestrator must define _trigger_sessions_send method"
assert "state.dispatched_results.append" in full_source, "main loop must append to state.dispatched_results"
assert "state.dispatch_queue.append" not in full_source, "main loop must NOT append to state.dispatch_queue anymore (Option A)"
assert "dispatch_response = self._trigger_sessions_send" in full_source or "dispatch_response = self._trigger_sessions_send(" in full_source, "main loop must call _trigger_sessions_send"
print("PASS test_main_loop_inline_triggers_sessions_send")


# ============================================================
# Test 5: _trigger_sessions_send signature uses Gateway HTTP API
# ============================================================
trigger_fn = find_function(tree, "_trigger_sessions_send")
assert trigger_fn is not None, "_trigger_sessions_send function not found"
trigger_src = ast.unparse(trigger_fn)
assert "OPENCLAW_GATEWAY_BASE_URL" in trigger_src, "_trigger_sessions_send must read OPENCLAW_GATEWAY_BASE_URL"
assert "OPENCLAW_GATEWAY_TOKEN" in trigger_src, "_trigger_sessions_send must read OPENCLAW_GATEWAY_TOKEN"
assert "/v1/chat/completions" in trigger_src, "_trigger_sessions_send must call /v1/chat/completions"
assert "x-openclaw-session-key" in trigger_src, "_trigger_sessions_send must set x-openclaw-session-key header"
assert "urllib.request" in full_source or "urllib" in full_source, "must import urllib"
print("PASS test_trigger_sessions_send_uses_gateway_api")


# ============================================================
# Test 6: agent_tool_adapters.py produces dispatch_via (regression)
# ============================================================
adapter_path = ORCH_ROOT / "agents" / "strategy-orchestrator" / "tools" / "agent_tool_adapters.py"
adapter_src = adapter_path.read_text(encoding="utf-8")
assert "dispatch_via" in adapter_src, "agent_tool_adapters must produce dispatch_via"
assert "sessions_send_dispatch_package" in adapter_src, "agent_tool_adapters must use sessions_send_dispatch_package mode"
assert "No specialist analysis was executed" in adapter_src, "adapter must NOT execute specialist work"
print("PASS test_adapter_produces_dispatch_via")


print()
print("=" * 60)
print("Option A Unit Test: ALL 6 TESTS PASSED")
print("=" * 60)
print()
print("Summary:")
print("- ToolResult.dispatch_request + dispatch_response: OK")
print("- ReactState.dispatched_results (no dispatch_queue): OK")
print("- _execute_step consumes dispatch_via: OK")
print("- main loop inline-triggers _trigger_sessions_send: OK")
print("- _trigger_sessions_send uses Gateway HTTP API: OK")
print("- agent_tool_adapters produces dispatch_via: OK")
