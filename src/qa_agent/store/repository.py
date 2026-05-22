"""Owner-scoped repository.

Every method takes ``owner_id`` and filters by it, so there is no code path
that returns another tenant's data. (Postgres RLS is the second line of
defense, added via migration.)

Persistence model:
- ``create_run`` / ``mark_running`` / ``mark_failed`` track lifecycle.
- ``apply_event`` appends a ``run_events`` row — this is what the SSE endpoint
  replays so a client that connects mid-run (or reloads) can rebuild live state.
- ``finalize_run`` writes the authoritative structured Report (flows, test
  cases, results, healing) plus denormalized counts in one transaction.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from ..models import Report
from .engine import Database
from .mappers import (
    flow_to_orm,
    healing_to_orm,
    orm_to_report,
    result_to_orm,
    test_case_to_orm,
)
from .models_orm import (
    HealingAttemptORM,
    RunEventORM,
    RunORM,
)


class _EventLike(Protocol):
    # Read-only (property) members so subtypes with narrower types — e.g.
    # ProgressEvent's Literal phase/status — satisfy the protocol covariantly.
    @property
    def seq(self) -> int: ...
    @property
    def ts(self) -> datetime: ...
    @property
    def phase(self) -> str: ...
    @property
    def status(self) -> str: ...
    @property
    def message(self) -> str: ...
    @property
    def data(self) -> dict[str, Any]: ...


def _utcnow() -> datetime:
    return datetime.now(UTC)


class RunRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    # --- lifecycle ---------------------------------------------------------

    def create_run(
        self,
        *,
        run_id: str,
        owner_id: str,
        url: str,
        model: str,
        headless: bool = True,
        mode: str = "single",
        auth_profile_id: str | None = None,
    ) -> None:
        with self.db.session() as s:
            s.add(
                RunORM(
                    id=run_id,
                    owner_id=owner_id,
                    url=url,
                    model=model,
                    headless=headless,
                    mode=mode,
                    auth_profile_id=auth_profile_id,
                    status="queued",
                    created_at=_utcnow(),
                )
            )

    # A run can never leave a terminal state — guards against a late
    # mark_running/mark_failed overwriting a finished run.
    _TERMINAL_STATES = ("succeeded", "failed", "cancelled")

    def mark_running(self, *, run_id: str, owner_id: str) -> None:
        self._update_run(
            run_id, owner_id, _only_if_not_terminal=True, status="running", started_at=_utcnow()
        )

    def mark_failed(self, *, run_id: str, owner_id: str, error: str) -> None:
        self._update_run(
            run_id,
            owner_id,
            _only_if_not_terminal=True,
            status="failed",
            finished_at=_utcnow(),
            error=error[:2000],
        )

    def _update_run(
        self, run_id: str, owner_id: str, _only_if_not_terminal: bool = False, **fields: Any
    ) -> None:
        with self.db.session() as s:
            run = s.get(RunORM, run_id)
            if run is None or run.owner_id != owner_id:
                return
            if _only_if_not_terminal and run.status in self._TERMINAL_STATES:
                return
            for k, v in fields.items():
                setattr(run, k, v)

    # --- events (SSE replay) ----------------------------------------------

    def apply_event(self, *, run_id: str, owner_id: str, event: _EventLike) -> None:
        with self.db.session() as s:
            run = s.get(RunORM, run_id)
            if run is None or run.owner_id != owner_id:
                return
            s.add(
                RunEventORM(
                    run_id=run_id,
                    owner_id=owner_id,
                    seq=event.seq,
                    ts=event.ts,
                    phase=event.phase,
                    status=event.status,
                    message=event.message,
                    data=dict(event.data or {}),
                )
            )

    def get_events_since(
        self, *, run_id: str, owner_id: str, after_seq: int = -1
    ) -> list[dict[str, Any]]:
        with self.db.session() as s:
            rows = (
                s.execute(
                    select(RunEventORM)
                    .where(
                        RunEventORM.run_id == run_id,
                        RunEventORM.owner_id == owner_id,
                        RunEventORM.seq > after_seq,
                    )
                    .order_by(RunEventORM.seq)
                )
                .scalars()
                .all()
            )
            return [
                {
                    "seq": r.seq,
                    "ts": r.ts.isoformat() if r.ts else None,
                    "phase": r.phase,
                    "status": r.status,
                    "message": r.message,
                    "data": r.data,
                }
                for r in rows
            ]

    # --- finalize ----------------------------------------------------------

    def finalize_run(
        self,
        *,
        owner_id: str,
        report: Report,
        markdown_body: str = "",
        ai_analysis: str = "",
    ) -> None:
        """Persist the full structured report + denormalized counts."""
        with self.db.session() as s:
            run = s.get(RunORM, report.id)
            if run is None or run.owner_id != owner_id:
                raise PermissionError(f"run {report.id} not owned by {owner_id}")

            run.status = "succeeded"
            run.url = report.url
            run.started_at = report.started_at
            run.finished_at = report.finished_at or _utcnow()
            run.total = report.total
            run.passed = report.passed
            run.failed = report.failed
            run.pass_rate = report.pass_rate
            run.tokens_in = report.usage.tokens_in
            run.tokens_out = report.usage.tokens_out
            run.cost_usd = report.usage.cost_usd
            run.markdown_path = report.markdown_path
            run.markdown_body = markdown_body
            run.ai_analysis = ai_analysis

            # Children are owned by this run; replace wholesale (idempotent).
            run.flows.clear()
            run.test_cases.clear()
            run.results.clear()
            run.healing_attempts.clear()
            s.flush()

            # Flow / test ids come from the LLM and can collide within a run
            # (composite PK is (id, run_id)); a dup would abort the whole
            # transaction. Dedupe defensively — keep the first occurrence.
            seen_flow_ids: set[str] = set()
            for flow in report.flows:
                if flow.id in seen_flow_ids:
                    continue
                seen_flow_ids.add(flow.id)
                s.add(flow_to_orm(flow, run_id=report.id, owner_id=owner_id))
            seen_tc_ids: set[str] = set()
            for tc in report.test_cases:
                if tc.id in seen_tc_ids:
                    continue
                seen_tc_ids.add(tc.id)
                s.add(test_case_to_orm(tc, run_id=report.id, owner_id=owner_id))
            for res in report.results:
                s.add(result_to_orm(res, run_id=report.id, owner_id=owner_id))
            for h in report.healing_attempts:
                s.add(healing_to_orm(h, run_id=report.id, owner_id=owner_id))

    # --- reads -------------------------------------------------------------

    def get_report(self, *, run_id: str, owner_id: str) -> Report | None:
        with self.db.session() as s:
            run = self._load_run(s, run_id, owner_id)
            return orm_to_report(run) if run else None

    def get_run_row(self, *, run_id: str, owner_id: str) -> dict[str, Any] | None:
        with self.db.session() as s:
            run = self._load_run(s, run_id, owner_id)
            return self._run_summary(run) if run else None

    def list_runs(self, *, owner_id: str, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        with self.db.session() as s:
            rows = (
                s.execute(
                    select(RunORM)
                    .where(RunORM.owner_id == owner_id)
                    .order_by(RunORM.created_at.desc())
                    .limit(limit)
                    .offset(offset)
                )
                .scalars()
                .all()
            )
            return [self._run_summary(r) for r in rows]

    # --- analytics ---------------------------------------------------------

    def summary(self, *, owner_id: str) -> dict[str, Any]:
        with self.db.session() as s:
            total_runs = (
                s.scalar(
                    select(func.count()).select_from(RunORM).where(RunORM.owner_id == owner_id)
                )
                or 0
            )
            agg = s.execute(
                select(
                    func.coalesce(func.sum(RunORM.total), 0),
                    func.coalesce(func.sum(RunORM.passed), 0),
                    func.coalesce(func.sum(RunORM.failed), 0),
                    func.coalesce(func.sum(RunORM.tokens_in), 0),
                    func.coalesce(func.sum(RunORM.tokens_out), 0),
                    func.coalesce(func.sum(RunORM.cost_usd), 0.0),
                ).where(RunORM.owner_id == owner_id, RunORM.status == "succeeded")
            ).one()
            tests_total, tests_passed, tests_failed = int(agg[0]), int(agg[1]), int(agg[2])
            tokens_in, tokens_out, cost_usd = int(agg[3]), int(agg[4]), float(agg[5])
            heals = (
                s.scalar(
                    select(func.count())
                    .select_from(HealingAttemptORM)
                    .where(
                        HealingAttemptORM.owner_id == owner_id,
                        HealingAttemptORM.outcome == "healed",
                    )
                )
                or 0
            )
            return {
                "total_runs": int(total_runs),
                "tests_total": tests_total,
                "tests_passed": tests_passed,
                "tests_failed": tests_failed,
                "overall_pass_rate": (tests_passed / tests_total * 100) if tests_total else 0.0,
                "successful_heals": int(heals),
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "cost_usd": cost_usd,
            }

    def pass_rate_trend(self, *, owner_id: str, limit: int = 30) -> list[dict[str, Any]]:
        with self.db.session() as s:
            rows = (
                s.execute(
                    select(RunORM)
                    .where(RunORM.owner_id == owner_id, RunORM.status == "succeeded")
                    .order_by(RunORM.created_at.desc())
                    .limit(limit)
                )
                .scalars()
                .all()
            )
            return [
                {
                    "run_id": r.id,
                    "url": r.url,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "pass_rate": r.pass_rate,
                    "total": r.total,
                    "passed": r.passed,
                    "failed": r.failed,
                }
                for r in reversed(rows)  # chronological for charting
            ]

    def healing_stats(self, *, owner_id: str) -> dict[str, int]:
        with self.db.session() as s:
            rows = s.execute(
                select(HealingAttemptORM.outcome, func.count())
                .where(HealingAttemptORM.owner_id == owner_id)
                .group_by(HealingAttemptORM.outcome)
            ).all()
            return {outcome: int(count) for outcome, count in rows}

    # --- helpers -----------------------------------------------------------

    def _load_run(self, s, run_id: str, owner_id: str) -> RunORM | None:
        run = s.execute(
            select(RunORM)
            .where(RunORM.id == run_id, RunORM.owner_id == owner_id)
            .options(
                selectinload(RunORM.flows),
                selectinload(RunORM.test_cases),
                selectinload(RunORM.results),
                selectinload(RunORM.healing_attempts),
            )
        ).scalar_one_or_none()
        return run

    @staticmethod
    def _run_summary(run: RunORM) -> dict[str, Any]:
        return {
            "id": run.id,
            "url": run.url,
            "status": run.status,
            "mode": run.mode,
            "model": run.model,
            "created_at": run.created_at.isoformat() if run.created_at else None,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            "total": run.total,
            "passed": run.passed,
            "failed": run.failed,
            "pass_rate": run.pass_rate,
            "tokens_in": run.tokens_in,
            "tokens_out": run.tokens_out,
            "cost_usd": run.cost_usd,
            "error": run.error,
        }
