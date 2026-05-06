"""Executes generated Playwright test files and collects results."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

from .models import TestCase, TestResult, TestStatus


class Executor:
    def run(self, test_cases: list[TestCase]) -> list[TestResult]:
        """Run each test file with pytest and return structured results."""
        return [self._run_one(tc) for tc in test_cases]

    def _run_one(self, tc: TestCase) -> TestResult:
        path = Path(tc.file_path)
        if not path.exists():
            return TestResult(
                test_case_id=tc.id,
                test_case_name=tc.name,
                status=TestStatus.ERROR,
                error_message=f"Test file not found: {path}",
            )

        start = time.monotonic()
        proc = subprocess.run(
            ["pytest", str(path), "-v", "--tb=short", "--no-header"],
            capture_output=True,
            text=True,
        )
        duration_ms = (time.monotonic() - start) * 1000

        passed = proc.returncode == 0
        return TestResult(
            test_case_id=tc.id,
            test_case_name=tc.name,
            status=TestStatus.PASSED if passed else TestStatus.FAILED,
            duration_ms=duration_ms,
            error_message=proc.stderr if not passed else None,
            stdout=proc.stdout,
            stderr=proc.stderr,
        )
