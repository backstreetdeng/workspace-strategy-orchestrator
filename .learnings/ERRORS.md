# Errors

Command failures and integration errors.

---

## [ERR-20260616-001] PowerShell here-doc syntax
**Logged**: 2026-06-16T17:04:00+08:00
**Priority**: low
**Status**: resolved

### Summary
Used Bash-style `python - <<'PY'` in PowerShell, causing a parser error.

### Details
PowerShell requires a here-string piped into Python, for example:
`@' ... '@ | python -`
This mistake recurred on 2026-06-17 while testing `StageStatus("warning")`; the follow-up command used the PowerShell-native form successfully.

### Suggested Action
Use PowerShell-native here-strings when running inline Python in this workspace.
---

## [ERR-20260616-002] Package import used script-style imports
**Logged**: 2026-06-16T17:05:00+08:00
**Priority**: medium
**Status**: resolved

### Summary
After archiving legacy workflow files, `import python_wrapper` failed because `__init__.py` used same-directory absolute imports.

### Details
Updated `python_wrapper/__init__.py` to use package-relative imports. Added relative/absolute fallback imports in `workflow_ai_orchestrator.py` and `sse_server.py`.

### Suggested Action
For package entry files, prefer relative imports and keep script-mode fallback only where the module is also run directly.
---

## [ERR-20260617-001] Market agent integration audit issues
**Logged**: 2026-06-17T08:39:52+08:00
**Priority**: high
**Status**: pending

### Summary
During the market strategy agent audit, several integration issues were confirmed: direct script execution can miss package paths, one market overview CLI path fails JSON serialization for Decimal values, the legacy workflow adapter can fail on `StageStatus("warning")`, and RAG document coverage is currently too narrow.

### Details
- Use `E:\AI\data\envs\car_agent_env\Scripts\python.exe` and prefer `python -m ...` from the `rag-engine` root.
- `market_data_query --action overview` reached the database but failed because Decimal values are not JSON serializable.
- `workflow_ai_orchestrator.py` is a legacy adapter and returned failure when quality emitted `warning`, which is not defined in `StageStatus`.
- PGVector contained only one uploaded document sample plus chat memory during the audit, so RAG results were not market-strategy grade.

### Suggested Action
Fix serialization and adapter enum issues, then expand the vector knowledge base with real market reports and policy documents before relying on RAG-backed strategic conclusions.
---

## [ERR-20260617-002] Default Python breaks RAG imports
**Logged**: 2026-06-17T10:06:00+08:00
**Priority**: high
**Status**: pending

### Summary
Running RAG/vector tools with the default system Python loads Pydantic 1.10.26 and breaks the current Ollama client import with `No module named 'pydantic.json_schema'`.

### Details
`E:\AI\data\envs\car_agent_env\Scripts\python.exe` uses Pydantic 2.13.4 and successfully initializes `pg-vector-search` and `HybridMarketAgent`. The default `python` on PATH uses `C:\Users\11489\AppData\Roaming\Python\Python39\site-packages\pydantic` version 1.10.26 and fails before retrieval.

### Suggested Action
Pin all market-agent runtime commands, API server launches, and tests to `E:\AI\data\envs\car_agent_env\Scripts\python.exe`, or align the default Python environment with `python_wrapper/requirements.txt` (`pydantic>=2.0.0`).
---

## [ERR-20260617-003] PowerShell Test-Path with Git quoted paths
**Logged**: 2026-06-17T15:48:00+08:00
**Priority**: low
**Status**: resolved

### Summary
While auditing untracked files, piping `git ls-files --others --exclude-standard` into `Test-Path` failed on Git-quoted paths containing escaped non-ASCII bytes.

### Details
PowerShell reported `Illegal characters in path` for quoted Git output such as filenames with octal escape sequences. The failure did not affect commits, but it made the file-size audit noisy.

### Suggested Action
For Git path audits in PowerShell, use `git -c core.quotepath=false ...` or parse NUL-delimited output instead of passing quoted Git path strings directly to filesystem cmdlets.
---
