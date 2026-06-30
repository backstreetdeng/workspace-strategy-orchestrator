"""Real unit test: verify Fix-1 token fallback works.
Strategy: monkey-patch urllib.request.urlopen, then exec the function
source. We need to manually dedent the function properly.
"""
import ast
import os
import sys
import textwrap
import urllib.error
import urllib.request
from pathlib import Path

ORCH_PATH = Path(r"C:\Users\11489\.openclaw\workspace-strategy-orchestrator\agents\strategy-orchestrator\executors\orchestrator.py")
src = ORCH_PATH.read_text(encoding="utf-8")
tree = ast.parse(src)

# Find _trigger_sessions_send function
trigger_fn = None
for node in ast.walk(tree):
    if isinstance(node, ast.FunctionDef) and node.name == "_trigger_sessions_send":
        trigger_fn = node
        break

if trigger_fn is None:
    print("FAIL: _trigger_sessions_send not found")
    sys.exit(1)

# Use ast.unparse and then dedent properly
fn_src = ast.unparse(trigger_fn)
# ast.unparse produces valid Python without indentation (since we extracted just the function)
# But "self" parameter is in signature, which is fine for module-level function
# We need to keep the function body but remove the class-method indentation

# ast.unparse gives us this format:
# def _trigger_sessions_send(self, *, dispatch_request, state) -> Dict[str, Any]:
#     target_agent_id = ...
#     ...
# So the body is already at proper indentation (4 spaces). Perfect.

module_code = """
import urllib.error as urllib_error
import urllib.request as urllib_request
import json
import time
import os
import urllib

""" + fn_src + """

# Bind to a class method-like
def trigger(self, dispatch_request, state):
    return _trigger_sessions_send(self, dispatch_request=dispatch_request, state=state)
"""

# Monkey-patch urlopen to capture what's actually called
captured_calls = []

def fake_urlopen(req, timeout=None):
    captured_calls.append({
        "url": req.full_url,
        "method": req.method,
        "headers": dict(req.headers),
    })
    # Simulate a 401 to verify token was sent
    raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, None)

import urllib.request as _ur
_ur.urlopen = fake_urlopen

# Execute the module
namespace = {
    "__builtins__": __builtins__,
    "urllib_error": urllib.error,
    "urllib_request": _ur,
    "json": __import__("json"),
    "time": __import__("time"),
    "os": os,
    "Any": object,
    "Dict": dict,
    "ReactState": type("ReactState", (), {}),
}
exec(module_code, namespace)
trigger = namespace["trigger"]

print("=" * 60)
print("Fix-1 Token Fallback Real Unit Test")
print("=" * 60)

# Test 1: env var set → use env token (not fallback)
print("--- Test 1: env var SET ---")
os.environ["OPENCLAW_GATEWAY_TOKEN"] = "env_token_abc"
captured_calls.clear()
try:
    result = trigger(None, {"agent_id": "report-agent", "message": "test", "source_tool": "test"}, None)
except urllib.error.HTTPError:
    pass
auth = captured_calls[0]["headers"].get("Authorization", "") if captured_calls else ""
if "env_token_abc" in auth:
    print("PASS: env token used in HTTP request")
    print("   Authorization header: " + auth[:80])
elif "2ec777c61f588861712e0d7d9da2cf909fb2b4f45c954be9" in auth:
    print("FAIL: should use env token, not fallback")
    print("   Authorization header: " + auth[:80])
    sys.exit(1)
else:
    print("FAIL: no expected token found in Authorization")
    print("   Authorization header: " + auth[:80])
    print("   captured_calls: " + str(captured_calls))
    sys.exit(1)

# Test 2: env var NOT set → use fallback
print("--- Test 2: env var NOT SET ---")
del os.environ["OPENCLAW_GATEWAY_TOKEN"]
captured_calls.clear()
try:
    result = trigger(None, {"agent_id": "report-agent", "message": "test", "source_tool": "test"}, None)
except urllib.error.HTTPError:
    pass
auth = captured_calls[0]["headers"].get("Authorization", "") if captured_calls else ""
if "2ec777c61f588861712e0d7d9da2cf909fb2b4f45c954be9" in auth:
    print("PASS: fallback token used when env var unset")
    print("   Authorization header: " + auth[:80])
else:
    print("FAIL: should use fallback, not found")
    print("   Authorization header: " + auth[:80])
    sys.exit(1)

# Test 3: env var empty string → use fallback
print("--- Test 3: env var empty string ---")
os.environ["OPENCLAW_GATEWAY_TOKEN"] = ""
captured_calls.clear()
try:
    result = trigger(None, {"agent_id": "report-agent", "message": "test", "source_tool": "test"}, None)
except urllib.error.HTTPError:
    pass
auth = captured_calls[0]["headers"].get("Authorization", "") if captured_calls else ""
if "2ec777c61f588861712e0d7d9da2cf909fb2b4f45c954be9" in auth:
    print("PASS: fallback token used when env var empty")
    print("   Authorization header: " + auth[:80])
else:
    print("FAIL: should use fallback, not found")
    print("   Authorization header: " + auth[:80])
    sys.exit(1)

print("=" * 60)
print("Fix-1 Token Fallback: ALL 3 TESTS PASSED")
print("=" * 60)