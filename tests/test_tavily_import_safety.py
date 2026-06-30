# -*- coding: utf-8 -*-
"""Regression tests for importing the Tavily CLI helper inside the server.

The orchestrator loads this helper with importlib. Importing it must not mutate
process-wide stdout/stderr, otherwise Uvicorn/SSE can later fail with
`I/O operation on closed file`.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TAVILY_SCRIPT = ROOT / "skills" / "tavily-search" / "scripts" / "tavily_search.py"


class TavilyImportSafetyTest(unittest.TestCase):
    def test_import_does_not_replace_stdio(self) -> None:
        old_stdout = sys.stdout
        old_stderr = sys.stderr

        spec = importlib.util.spec_from_file_location(
            "workspace_tavily_search_import_test",
            TAVILY_SCRIPT,
        )
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        self.assertIs(sys.stdout, old_stdout)
        self.assertIs(sys.stderr, old_stderr)


if __name__ == "__main__":
    unittest.main()
