"""工作流运行时持久化服务：持久化 workflow run 状态并驱动执行。"""
from __future__ import annotations

import json
import base64
from dataclasses import asdict
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.event_audit_service import event_audit_service

if TYPE_CHECKING:
    from app.agents.orchestrator import WorkflowState, WorkflowStage


CREATE_WORKFLOW_RUNS_SQL = """
CREATE TABLE IF NOT EXISTS workflow_runs (
    run_id TEXT PRIMARY KEY,
    event_case_id TEXT,
    story_packet_id TEXT,
    current_stage TEXT NOT NULL,
    status TEXT NOT NULL,
    state_json TEXT NOT NULL,
    last_error TEXT,
    created_by TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""


CREATE_WORKFLOW_EVENTS_SQL_SQLITE = """
CREATE TABLE IF NOT EXISTS workflow_run_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT,
    created_at TEXT NOT NULL
)
"""

CREATE_WORKFLOW_EVENTS_SQL_PG = """
CREATE TABLE IF NOT EXISTS workflow_run_events (
    id SERIAL PRIMARY KEY,
    run_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT,
    created_at TEXT NOT NULL
)
"""


def _get_orchestrator():
    """延迟导入 orchestrator 模块，避免在精简部署环境下崩溃。"""
    from app.agents.orchestrator import WorkflowState, WorkflowStage, orchestrator_agent
    return WorkflowState, WorkflowStage, orchestrator_agent


class WorkflowRuntimeService:
    async def ensure_tables(self, db: AsyncSession) -> None:
        from app.core.database import _is_sqlite
        events_sql = CREATE_WORKFLOW_EVENTS_SQL_SQLITE if _is_sqlite else CREATE_WORKFLOW_EVENTS_SQL_PG
        await db.execute(text(CREATE_WORKFLOW_RUNS_SQL))
        await db.execute(text(events_sql))

    @staticmethod
    def _serialize_state(state: WorkflowState) -> str:
        payload = asdict(state)
        payload["current_stage"] = state.current_stage.value if isinstance(state.current_stage, Enum) else state.current_stage
        payload["created_at"] = state.created_at.isoformat() if isinstance(state.created_at, datetime) else state.created_at
        payload["updated_at"] = state.updated_at.isoformat() if isinstance(state.updated_at, datetime) else state.updated_at
        return json.dumps(payload, ensure_ascii=False)

    @staticmethod
    def _deserialize_state(state_json: str) -> WorkflowState:
        from app.agents.orchestrator import WorkflowState, WorkflowStage

        data = json.loads(state_json)
        current_stage = data.get("current_stage")
        try:
            stage_enum = WorkflowStage(current_stage)
        except Exception:
            stage_enum = WorkflowStage.SOURCE_INGESTION

        created_at_raw = data.get("created_at")
        updated_at_raw = data.get("updated_at")

        created_at = datetime.fromisoformat(created_at_raw) if created_at_raw else datetime.utcnow()
        updated_at = datetime.fromisoformat(updated_at_raw) if updated_at_raw else datetime.utcnow()

        return WorkflowState(  # noqa: F811
            workflow_id=data.get("workflow_id"),
            event_case_id=data.get("event_case_id"),
            story_packet_id=data.get("story_packet_id"),
            current_stage=stage_enum,
            source_items=data.get("source_items", []),
            evidence_pack=data.get("evidence_pack"),
            claim_cards=data.get("claim_cards", []),
            event_graph=data.get("event_graph"),
            risk_report=data.get("risk_report"),
            draft_version=data.get("draft_version"),
            channel_packages=data.get("channel_packages", []),
            review_bundle=data.get("review_bundle"),
            approval_tasks=data.get("approval_tasks", []),
            blockers=data.get("blockers", []),
            human_decisions=data.get("human_decisions", []),
            error=data.get("error"),
            created_at=created_at,
            updated_at=updated_at,
        )

    @staticmethod
    def _infer_status(state: WorkflowState) -> str:
        from app.agents.orchestrator import WorkflowStage

        if state.error:
            return "failed"
        if state.blockers:
            return "blocked"
        if state.current_stage == WorkflowStage.COMPLETED:
            return "completed"
        if state.current_stage == WorkflowStage.FAILED:
            return "failed"
        return "running"

    async def _save_run_state(
        self,
        db: AsyncSession,
        state: WorkflowState,
        created_by: str | None = None,
    ) -> None:
        await self.ensure_tables(db)
        status = self._infer_status(state)
        now = datetime.utcnow().isoformat()
        await db.execute(
            text(
                """
                INSERT INTO workflow_runs (
                    run_id, event_case_id, story_packet_id, current_stage, status,
                    state_json, last_error, created_by, created_at, updated_at
                )
                VALUES (
                    :run_id, :event_case_id, :story_packet_id, :current_stage, :status,
                    :state_json, :last_error, :created_by, :created_at, :updated_at
                )
                ON CONFLICT(run_id) DO UPDATE SET
                    event_case_id = excluded.event_case_id,
                    story_packet_id = excluded.story_packet_id,
                    current_stage = excluded.current_stage,
                    status = excluded.status,
                    state_json = excluded.state_json,
                    last_error = excluded.last_error,
                    updated_at = excluded.updated_at
                """
            ),
            {
                "run_id": state.workflow_id,
                "event_case_id": state.event_case_id,
                "story_packet_id": state.story_packet_id,
                "current_stage": state.current_stage.value if isinstance(state.current_stage, Enum) else state.current_stage,
                "status": status,
                "state_json": self._serialize_state(state),
                "last_error": state.error,
                "created_by": created_by,
                "created_at": now,
                "updated_at": now,
            },
        )

    async def _append_event(self, db: AsyncSession, run_id: str, event_type: str, payload: dict | None = None) -> None:
        await self.ensure_tables(db)
        await db.execute(
            text(
                """
                INSERT INTO workflow_run_events (run_id, event_type, payload_json, created_at)
                VALUES (:run_id, :event_type, :payload_json, :created_at)
                """
            ),
            {
                "run_id": run_id,
                "event_type": event_type,
                "payload_json": json.dumps(payload or {}, ensure_ascii=False),
                "created_at": datetime.utcnow().isoformat(),
            },
        )

    async def create_run(
        self,
        db: AsyncSession,
        created_by: str,
        event_case_id: str | None = None,
        source_items: list[dict] | None = None,
    ) -> WorkflowState:
        from app.agents.orchestrator import orchestrator_agent

        state = await orchestrator_agent.create_workflow(event_case_id=event_case_id, source_items=source_items or [])
        await self._save_run_state(db, state, created_by=created_by)
        await self._append_event(db, state.workflow_id, "workflow_created", {
            "event_case_id": event_case_id,
            "source_items_count": len(source_items or []),
        })
        await event_audit_service.append_event(
            db,
            actor_id=created_by,
            actor_type="human",
            action="workflow_created",
            object_type="workflow_run",
            object_id=state.workflow_id,
            details={
                "event_case_id": event_case_id,
                "source_items_count": len(source_items or []),
                "current_stage": state.current_stage.value,
            },
        )
        return state

    async def list_runs_by_event(self, db: AsyncSession, event_case_id: str) -> list[dict]:
        await self.ensure_tables(db)
        rows = (
            await db.execute(
                text(
                    """
                    SELECT run_id, event_case_id, story_packet_id, current_stage, status,
                           state_json, last_error, created_by, created_at, updated_at
                    FROM workflow_runs
                    WHERE event_case_id = :event_case_id
                    ORDER BY created_at DESC
                    """
                ),
                {"event_case_id": event_case_id},
            )
        ).mappings().all()
        return [dict(r) for r in rows]

    async def get_run_row(self, db: AsyncSession, run_id: str):
        await self.ensure_tables(db)
        row = (
            await db.execute(
                text(
                    """
                    SELECT run_id, event_case_id, story_packet_id, current_stage, status,
                           state_json, last_error, created_by, created_at, updated_at
                    FROM workflow_runs
                    WHERE run_id = :run_id
                    """
                ),
                {"run_id": run_id},
            )
        ).mappings().first()
        return row

    async def list_events(self, db: AsyncSession, run_id: str, limit: int = 100) -> list[dict]:
        await self.ensure_tables(db)
        rows = (
            await db.execute(
                text(
                    """
                    SELECT id, run_id, event_type, payload_json, created_at
                    FROM workflow_run_events
                    WHERE run_id = :run_id
                    ORDER BY id DESC
                    LIMIT :limit
                    """
                ),
                {"run_id": run_id, "limit": limit},
            )
        ).mappings().all()

        result = []
        for row in rows:
            payload = row["payload_json"]
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except Exception:
                    payload = {}
            result.append({
                "id": row["id"],
                "run_id": row["run_id"],
                "event_type": row["event_type"],
                "payload": payload,
                "created_at": row["created_at"],
            })
        return result

    @staticmethod
    def encode_event_cursor(created_at: str, event_id: int) -> str:
        raw = f"{created_at}|{event_id}"
        return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("utf-8")

    @staticmethod
    def decode_event_cursor(cursor: str | None) -> tuple[str, int] | None:
        if not cursor:
            return None
        try:
            raw = base64.urlsafe_b64decode(cursor.encode("utf-8")).decode("utf-8")
            created_at, event_id = raw.split("|", 1)
            return created_at, int(event_id)
        except Exception:
            return None

    async def list_events_cursor_page(
        self,
        db: AsyncSession,
        run_id: str,
        *,
        cursor: str | None = None,
        limit: int = 100,
    ) -> dict:
        await self.ensure_tables(db)
        page_limit = max(1, min(limit, 200))
        fetch_limit = page_limit + 1
        params: dict = {
            "run_id": run_id,
            "limit": fetch_limit,
        }

        cursor_decoded = self.decode_event_cursor(cursor)
        cursor_clause = ""
        if cursor_decoded:
            cursor_created_at, cursor_id = cursor_decoded
            cursor_clause = "AND (created_at < :cursor_created_at OR (created_at = :cursor_created_at AND id < :cursor_id))"
            params["cursor_created_at"] = cursor_created_at
            params["cursor_id"] = cursor_id

        rows = list((
            await db.execute(
                text(
                    f"""
                    SELECT id, run_id, event_type, payload_json, created_at
                    FROM workflow_run_events
                    WHERE run_id = :run_id
                    {cursor_clause}
                    ORDER BY created_at DESC, id DESC
                    LIMIT :limit
                    """
                ),
                params,
            )
        ).mappings().all())

        has_more = len(rows) > page_limit
        page_rows = rows[:page_limit]

        items: list[dict] = []
        for row in page_rows:
            payload = row["payload_json"]
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except Exception:
                    payload = {}

            items.append(
                {
                    "id": row["id"],
                    "run_id": row["run_id"],
                    "event_type": row["event_type"],
                    "payload": payload,
                    "created_at": row["created_at"],
                }
            )

        next_cursor = None
        if has_more and items:
            last = items[-1]
            next_cursor = self.encode_event_cursor(last["created_at"], last["id"])

        return {
            "items": items,
            "next_cursor": next_cursor,
            "has_more": has_more,
            "limit": page_limit,
        }

    async def _hydrate_orchestrator(self, db: AsyncSession, run_id: str) -> WorkflowState:
        from app.agents.orchestrator import orchestrator_agent

        state = await orchestrator_agent.get_workflow(run_id)
        if state is not None:
            return state

        row = await self.get_run_row(db, run_id)
        if not row:
            raise ValueError(f"workflow run not found: {run_id}")

        persisted_state = self._deserialize_state(row["state_json"])
        orchestrator_agent._workflows[run_id] = persisted_state
        return persisted_state

    async def advance_run(self, db: AsyncSession, run_id: str) -> WorkflowState:
        from app.agents.orchestrator import orchestrator_agent

        await self._hydrate_orchestrator(db, run_id)
        state = await orchestrator_agent.advance_workflow(run_id)
        await self._save_run_state(db, state)
        await self._append_event(db, run_id, "workflow_advanced", {
            "current_stage": state.current_stage.value,
            "status": self._infer_status(state),
            "error": state.error,
        })
        await event_audit_service.append_event(
            db,
            actor_id=None,
            actor_type="system",
            action="workflow_advanced",
            object_type="workflow_run",
            object_id=run_id,
            details={
                "current_stage": state.current_stage.value,
                "status": self._infer_status(state),
                "error": state.error,
            },
        )
        return state

    async def submit_decision(
        self,
        db: AsyncSession,
        run_id: str,
        decision_type: str,
        action: str,
        reason: str | None = None,
        actor_id: str | None = None,
    ) -> WorkflowState:
        from app.agents.orchestrator import orchestrator_agent

        await self._hydrate_orchestrator(db, run_id)
        state = await orchestrator_agent.submit_human_decision(
            run_id,
            decision_type=decision_type,
            action=action,
            reason=reason,
        )
        await self._save_run_state(db, state)
        await self._append_event(db, run_id, "human_decision_submitted", {
            "decision_type": decision_type,
            "action": action,
            "reason": reason,
            "current_stage": state.current_stage.value,
            "status": self._infer_status(state),
        })
        await event_audit_service.append_event(
            db,
            actor_id=actor_id,
            actor_type="human",
            action="workflow_human_decision_submitted",
            object_type="workflow_run",
            object_id=run_id,
            details={
                "decision_type": decision_type,
                "action": action,
                "reason": reason,
                "current_stage": state.current_stage.value,
                "status": self._infer_status(state),
            },
        )
        return state


workflow_runtime_service = WorkflowRuntimeService()
