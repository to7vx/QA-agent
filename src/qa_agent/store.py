"""SQLite persistence for runs, per-test results, and the test-case library.

Local-first by design: the DB lives next to the reports at
<report_dir>/qa.db. Every write is best-effort from the caller's point of
view — a storage failure must never break a QA run.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    url TEXT NOT NULL DEFAULT '',
    provider TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT '',
    started_at TEXT,
    finished_at TEXT,
    status TEXT NOT NULL DEFAULT 'finished',
    cancelled INTEGER NOT NULL DEFAULT 0,
    total INTEGER NOT NULL DEFAULT 0,
    passed INTEGER NOT NULL DEFAULT 0,
    failed INTEGER NOT NULL DEFAULT 0,
    healed INTEGER NOT NULL DEFAULT 0,
    pass_rate REAL NOT NULL DEFAULT 0,
    markdown_path TEXT NOT NULL DEFAULT '',
    report_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS test_results (
    run_id TEXT NOT NULL,
    test_case_id TEXT NOT NULL,
    name TEXT NOT NULL,
    status TEXT NOT NULL,
    duration_ms REAL NOT NULL DEFAULT 0,
    healed INTEGER NOT NULL DEFAULT 0,
    error TEXT
);
CREATE INDEX IF NOT EXISTS idx_test_results_run ON test_results(run_id);
CREATE TABLE IF NOT EXISTS test_cases (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    scenario TEXT NOT NULL DEFAULT '',
    url TEXT NOT NULL DEFAULT '',
    file_path TEXT NOT NULL,
    code TEXT NOT NULL,
    origin TEXT NOT NULL DEFAULT 'composed',
    provider TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT '',
    tags_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

_FAIL_STATUSES = ("failed", "error")


class Store:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    # ------------------------------------------------------------------
    # Runs
    # ------------------------------------------------------------------

    def save_run(self, payload: dict) -> None:
        meta = payload.get("meta", {})
        report = payload.get("report") or {}
        run_id = meta.get("run_id") or report.get("id")
        if not run_id:
            return
        results = report.get("results", [])
        passed = sum(1 for r in results if r.get("status") == "passed")
        failed = sum(1 for r in results if r.get("status") in _FAIL_STATUSES)
        healed = sum(1 for r in results if r.get("healed"))
        total = len(results)
        with self._lock:
            self._conn.execute(
                """INSERT INTO runs (id, url, provider, model, started_at, finished_at,
                                     status, cancelled, total, passed, failed, healed,
                                     pass_rate, markdown_path, report_json)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                     url=excluded.url, provider=excluded.provider, model=excluded.model,
                     started_at=excluded.started_at, finished_at=excluded.finished_at,
                     status=excluded.status, cancelled=excluded.cancelled,
                     total=excluded.total, passed=excluded.passed, failed=excluded.failed,
                     healed=excluded.healed, pass_rate=excluded.pass_rate,
                     markdown_path=excluded.markdown_path, report_json=excluded.report_json""",
                (
                    run_id,
                    report.get("url", ""),
                    meta.get("provider", ""),
                    meta.get("model", ""),
                    report.get("started_at"),
                    report.get("finished_at"),
                    "cancelled" if meta.get("cancelled") else "finished",
                    1 if meta.get("cancelled") else 0,
                    total,
                    passed,
                    failed,
                    healed,
                    (passed / total * 100) if total else 0.0,
                    report.get("markdown_path", ""),
                    json.dumps(payload, default=str),
                ),
            )
            self._conn.execute("DELETE FROM test_results WHERE run_id = ?", (run_id,))
            self._conn.executemany(
                """INSERT INTO test_results (run_id, test_case_id, name, status,
                                             duration_ms, healed, error)
                   VALUES (?,?,?,?,?,?,?)""",
                [
                    (
                        run_id,
                        r.get("test_case_id", ""),
                        r.get("test_case_name", ""),
                        r.get("status", ""),
                        r.get("duration_ms", 0.0),
                        1 if r.get("healed") else 0,
                        r.get("error_message"),
                    )
                    for r in results
                ],
            )
            self._conn.commit()

    def list_runs(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM runs ORDER BY started_at DESC"
            ).fetchall()
        return [self._run_summary(row) for row in rows]

    def get_run(self, run_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT report_json FROM runs WHERE id = ?", (run_id,)
            ).fetchone()
        if row is None:
            return None
        try:
            return json.loads(row["report_json"])
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _run_summary(row: sqlite3.Row) -> dict:
        return {
            "run_id": row["id"],
            "url": row["url"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
            "provider": row["provider"],
            "model": row["model"],
            "cancelled": bool(row["cancelled"]),
            "total": row["total"],
            "passed": row["passed"],
            "failed": row["failed"],
            "healed": row["healed"],
            "pass_rate": row["pass_rate"],
            "status": row["status"],
        }

    # ------------------------------------------------------------------
    # Insights
    # ------------------------------------------------------------------

    def insights(self) -> dict:
        with self._lock:
            kpis_row = self._conn.execute(
                """SELECT COUNT(*) AS runs, COALESCE(SUM(total),0) AS tests_run,
                          COALESCE(AVG(pass_rate),0) AS pass_rate,
                          COALESCE(SUM(healed),0) AS healed,
                          COUNT(DISTINCT url) AS sites
                   FROM runs"""
            ).fetchone()
            trend_rows = self._conn.execute(
                """SELECT id, url, started_at, pass_rate, total
                   FROM runs ORDER BY started_at ASC LIMIT 60"""
            ).fetchall()
            flaky_rows = self._conn.execute(
                """SELECT name,
                          SUM(CASE WHEN status IN ('failed','error') THEN 1 ELSE 0 END) AS fails,
                          COUNT(*) AS runs
                   FROM test_results
                   GROUP BY name
                   HAVING fails > 0
                   ORDER BY fails DESC, runs DESC
                   LIMIT 8"""
            ).fetchall()
            healing_rows = self._conn.execute(
                "SELECT report_json FROM runs"
            ).fetchall()

        healing = {"healed": 0, "refused": 0, "failed": 0, "error": 0}
        for row in healing_rows:
            try:
                attempts = json.loads(row["report_json"])["report"].get("healing_attempts", [])
            except (json.JSONDecodeError, KeyError, TypeError):
                continue
            for a in attempts:
                outcome = a.get("outcome", "error")
                if outcome in healing:
                    healing[outcome] += 1

        return {
            "kpis": {
                "runs": kpis_row["runs"],
                "tests_run": kpis_row["tests_run"],
                "pass_rate": round(kpis_row["pass_rate"], 1),
                "healed": kpis_row["healed"],
                "sites": kpis_row["sites"],
            },
            "trend": [
                {
                    "run_id": r["id"],
                    "url": r["url"],
                    "date": r["started_at"],
                    "pass_rate": r["pass_rate"],
                    "total": r["total"],
                }
                for r in trend_rows
            ],
            "flakiest": [
                {"name": r["name"], "fails": r["fails"], "runs": r["runs"]}
                for r in flaky_rows
            ],
            "healing": healing,
        }

    # ------------------------------------------------------------------
    # Test-case library
    # ------------------------------------------------------------------

    def add_test_case(self, tc: dict) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT OR REPLACE INTO test_cases
                   (id, name, description, scenario, url, file_path, code,
                    origin, provider, model, tags_json)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    tc["id"],
                    tc["name"],
                    tc.get("description", ""),
                    tc.get("scenario", ""),
                    tc.get("url", ""),
                    tc["file_path"],
                    tc["code"],
                    tc.get("origin", "composed"),
                    tc.get("provider", ""),
                    tc.get("model", ""),
                    json.dumps(tc.get("tags", [])),
                ),
            )
            self._conn.commit()

    def list_test_cases(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                """SELECT id, name, description, scenario, url, file_path, origin,
                          provider, model, tags_json, created_at
                   FROM test_cases ORDER BY created_at DESC"""
            ).fetchall()
        return [self._tc_dict(row, with_code=False) for row in rows]

    def get_test_case(self, tc_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM test_cases WHERE id = ?", (tc_id,)
            ).fetchone()
        return self._tc_dict(row, with_code=True) if row else None

    def delete_test_case(self, tc_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM test_cases WHERE id = ?", (tc_id,))
            self._conn.commit()

    @staticmethod
    def _tc_dict(row: sqlite3.Row, with_code: bool) -> dict:
        data = {
            "id": row["id"],
            "name": row["name"],
            "description": row["description"],
            "scenario": row["scenario"],
            "url": row["url"],
            "file_path": row["file_path"],
            "origin": row["origin"],
            "provider": row["provider"],
            "model": row["model"],
            "tags": json.loads(row["tags_json"] or "[]"),
            "created_at": row["created_at"],
        }
        if with_code:
            data["code"] = row["code"]
        return data

    # ------------------------------------------------------------------
    # Legacy import
    # ------------------------------------------------------------------

    def import_legacy(self, report_dir: Path) -> int:
        """Import pre-v2 reports/<id>/report.json files not yet in the DB."""
        report_dir = Path(report_dir)
        if not report_dir.exists():
            return 0
        imported = 0
        for report_file in report_dir.glob("*/report.json"):
            run_id = report_file.parent.name
            with self._lock:
                exists = self._conn.execute(
                    "SELECT 1 FROM runs WHERE id = ?", (run_id,)
                ).fetchone()
            if exists:
                continue
            try:
                payload = json.loads(report_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            self.save_run(payload)
            imported += 1
        return imported
