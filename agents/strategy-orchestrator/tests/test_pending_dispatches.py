"""A.Option A: verify OrchestrationResult exposes dispatched_results (replaces old pending_dispatches)."""

import ast
from pathlib import Path

ORCH_ROOT = Path(r"C:\Users\11489\.openclaw\workspace-strategy-orchestrator")
ORCH_PATH = ORCH_ROOT / "agents" / "strategy-orchestrator" / "executors" / "orchestrator.py"
TP_PATH = ORCH_ROOT / "agents" / "strategy-orchestrator" / "protocols" / "task_protocol.py"
PROTOCOL_PATH = TP_PATH


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


def get_field_type(class_node, field_name):
    for f in class_node.body:
        if isinstance(f, ast.AnnAssign) and isinstance(f.target, ast.Name) and f.target.id == field_name:
            return ast.unparse(f.annotation)
    return None


# Test 1: OrchestrationResult exposes new dispatched_results fields
tp_src = PROTOCOL_PATH.read_text(encoding="utf-8")
tp_tree = ast.parse(tp_src)
result_cls = find_dataclass(tp_tree, "OrchestrationResult")
assert result_cls is not None, "OrchestrationResult class not found"
result_fields = get_field_names(result_cls)
assert "dispatched_results" in result_fields, f"OrchestrationResult.dispatched_results missing; fields={result_fields}"
dr_type = get_field_type(result_cls, "dispatched_results")
assert "List" in dr_type and "Dict" in dr_type, f"dispatched_results must be List[Dict]; got {dr_type}"
assert "dispatched_count" in result_fields, f"OrchestrationResult.dispatched_count missing; fields={result_fields}"
assert "dispatched_ok_count" in result_fields, f"OrchestrationResult.dispatched_ok_count missing; fields={result_fields}"
assert "pending_dispatches" not in result_fields, "Old pending_dispatches must be REMOVED (Option A)"
print("PASS test_orchestration_result_has_dispatched_results")


# Test 2: _build_result populates dispatched_results from state.dispatched_results
orch_src = ORCH_PATH.read_text(encoding="utf-8")
assert "dispatched_results=" in orch_src and "state.dispatched_results" in orch_src, \
    "_build_result must populate dispatched_results from state.dispatched_results"
assert "dispatched_count=len(state.dispatched_results)" in orch_src, "_build_result must compute dispatched_count"
assert "dispatched_ok_count=" in orch_src, "_build_result must compute dispatched_ok_count"
assert "pending_dispatches=list(state.dispatch_queue)" not in orch_src, "old pending_dispatches line must be REMOVED"
print("PASS test_build_result_populates_dispatched_results")


# Test 3: ToolResult and ReactState regression check
orch_tree = ast.parse(orch_src)
tool_result_cls = find_dataclass(orch_tree, "ToolResult")
tr_fields = get_field_names(tool_result_cls)
assert "dispatch_request" in tr_fields, "Regression: ToolResult.dispatch_request must still exist"
assert "dispatch_response" in tr_fields, "Regression: ToolResult.dispatch_response must exist"
react_state_cls = find_dataclass(orch_tree, "ReactState")
rs_fields = get_field_names(react_state_cls)
assert "dispatched_results" in rs_fields, "Regression: ReactState.dispatched_results must exist"
assert "dispatch_queue" not in rs_fields, "Regression: dispatch_queue must be REMOVED"
print("PASS test_tool_result_and_react_state_regression")


print()
print("=" * 60)
print("Option A (dispatched_results) Unit Test: ALL 3 TESTS PASSED")
print("=" * 60)
print()
print("Summary:")
print("- OrchestrationResult.dispatched_results + count fields: OK")
print("- _build_result populates from state.dispatched_results: OK")
print("- ToolResult/ReactState new schema: OK")
