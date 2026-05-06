"""事件案卷 API：CRUD + 状态操作。"""

import logging
import re
import traceback
from datetime import datetime

import json as _json

from fastapi import APIRouter, Depends, Query, BackgroundTasks
from pydantic import BaseModel, field_validator
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.errors import NotFoundError
from app.core.state_machine import event_case_engine
from app.models.event_case import EventCase, EventSourceItem
from app.models.story_packet import StoryPacket
from app.models.claim_card import ClaimCard
from app.models.correction_ticket import CorrectionTicket
from app.models.user import User
from app.api.deps import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()

_WF_HAS_STATE_JSON: bool | None = None


# ── 请求/响应模型 ──

class EventCaseCreate(BaseModel):
    title: str
    summary: str | None = None
    description: str | None = None
    risk_level: str = "L0"
    desk: str | None = None
    region: str | None = None
    start_time: datetime | None = None
    tags: list = []
    topic_keywords: str | None = None


class EventCaseUpdate(BaseModel):
    title: str | None = None
    summary: str | None = None
    risk_level: str | None = None
    desk: str | None = None
    region: str | None = None
    tags: list | None = None


class TransitionRequest(BaseModel):
    target_state: str


class EventCaseResponse(BaseModel):
    id: str
    title: str
    summary: str | None
    status: str
    risk_level: str
    desk: str | None
    region: str | None
    start_time: datetime | None
    end_time: datetime | None
    tags: list
    timeline_data: list = []
    entity_graph_ref: str | None = None
    owner_id: str | None
    owner_display_name: str | None = None
    created_at: datetime
    updated_at: datetime
    story_packet_count: int = 0
    published_count: int = 0
    active_claim_count: int = 0
    correction_count: int = 0

    @field_validator("tags", "timeline_data", mode="before")
    @classmethod
    def _parse_json_list(cls, v):
        if isinstance(v, str):
            try:
                return _json.loads(v)
            except Exception:
                return []
        return v if v is not None else []

    model_config = {"from_attributes": True}


class SourceItemResponse(BaseModel):
    id: str
    event_case_id: str
    source_type: str
    url: str | None
    raw_content: str | None
    extracted_5w1h: dict | None = None
    risk_tags: list = []
    ingested_at: datetime

    @field_validator("risk_tags", mode="before")
    @classmethod
    def _parse_risk_tags(cls, v):
        if isinstance(v, str):
            try:
                return _json.loads(v)
            except Exception:
                return []
        return v if v is not None else []

    @field_validator("extracted_5w1h", mode="before")
    @classmethod
    def _parse_5w1h(cls, v):
        if isinstance(v, str):
            try:
                return _json.loads(v)
            except Exception:
                return None
        return v

    model_config = {"from_attributes": True}


class PaginatedResponse(BaseModel):
    items: list[EventCaseResponse]
    total: int
    page: int
    page_size: int


# ── 接口 ──

@router.get("", response_model=PaginatedResponse, summary="事件案卷列表", description="分页获取事件案卷列表，支持按状态、风险等级、版面筛选。")
async def list_events(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = None,
    risk_level: str | None = None,
    desk: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(EventCase).where(EventCase.archived_at.is_(None))
    count_query = select(func.count(EventCase.id)).where(EventCase.archived_at.is_(None))

    # 团队隔离：同org内可见，无org只能看自己的
    if current_user.org_id:
        org_member_ids = (await db.execute(
            select(User.id).where(User.org_id == current_user.org_id)
        )).scalars().all()
        query = query.where(EventCase.owner_id.in_(org_member_ids))
        count_query = count_query.where(EventCase.owner_id.in_(org_member_ids))
    else:
        query = query.where(EventCase.owner_id == current_user.id)
        count_query = count_query.where(EventCase.owner_id == current_user.id)

    if status:
        query = query.where(EventCase.status == status)
        count_query = count_query.where(EventCase.status == status)
    if risk_level:
        query = query.where(EventCase.risk_level == risk_level)
        count_query = count_query.where(EventCase.risk_level == risk_level)
    if desk:
        query = query.where(EventCase.desk == desk)
        count_query = count_query.where(EventCase.desk == desk)

    total = (await db.execute(count_query)).scalar() or 0
    query = query.order_by(EventCase.updated_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    raw_events = list(result.scalars().all())

    # Compute aggregated counts per event
    enriched = []
    for ev in raw_events:
        sp_count = await db.scalar(
            select(func.count(StoryPacket.id)).where(
                StoryPacket.event_case_id == ev.id,
                StoryPacket.status != "archived",
            )
        ) or 0
        pub_count = await db.scalar(
            select(func.count(StoryPacket.id)).where(
                StoryPacket.event_case_id == ev.id,
                StoryPacket.status == "published",
            )
        ) or 0
        # active claims = claims in visible, non-archived packets
        sp_ids_result = await db.execute(
            select(StoryPacket.id).where(
                StoryPacket.event_case_id == ev.id,
                StoryPacket.status != "archived",
            )
        )
        sp_ids = [r[0] for r in sp_ids_result.fetchall()]
        claim_count = 0
        if sp_ids:
            claim_count = await db.scalar(
                select(func.count(ClaimCard.id)).where(ClaimCard.story_packet_id.in_(sp_ids))
            ) or 0
        correction_count = await db.scalar(
            select(func.count(CorrectionTicket.id)).where(CorrectionTicket.event_case_id == ev.id)
        ) or 0

        resp = EventCaseResponse.model_validate(ev)
        resp.story_packet_count = sp_count
        resp.published_count = pub_count
        resp.active_claim_count = claim_count
        resp.correction_count = correction_count
        if ev.owner_id:
            owner = await db.get(User, ev.owner_id)
            resp.owner_display_name = owner.display_name if owner else None
        enriched.append(resp)

    return PaginatedResponse(items=enriched, total=total, page=page, page_size=page_size)


def _resolve_llm_key(user_key: str | None) -> str:
    """Resolve effective LLM API key: user override > global config."""
    return user_key or settings.OPENAI_API_KEY or ""


def _create_temp_llm(api_key: str):
    """Create a temporary ChatOpenAI instance (thread-safe, does not modify global singleton)."""
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(
        model=settings.LLM_MODEL,
        api_key=api_key,
        base_url=settings.OPENAI_BASE_URL or None,
        temperature=0.1,
    )


async def _log_stage(db, event_audit_service, event_id: str, wf_id: str,
                     agent_name: str, summary: str, extra: dict | None = None,
                     stage_action: str = "pipeline_stage"):
    """Helper: append audit log for a pipeline stage AND update event timeline_data.
    stage_action should match frontend PIPELINE_STAGES keys when representing a
    completed stage (e.g. 'source_ingest', 'dedup_cluster', 'triage', etc.)."""
    details = {
        "agent_name": agent_name,
        "summary": summary,
        "workflow_run_id": _normalize_id(wf_id),
    }
    if extra:
        details.update(extra)
    details = _json_safe(details)
    try:
        await event_audit_service.append_event(
            db, actor_id=None, actor_type="agent",
            action=stage_action, object_type="event_case", object_id=_normalize_id(event_id),
            details=details,
        )
    except Exception as audit_exc:
        logger.warning(f"append_event failed for event {event_id}: {audit_exc}")
    # 同时更新 event timeline_data
    try:
        event_obj = await db.get(EventCase, event_id)
        if event_obj:
            import json as _json
            existing = []
            if event_obj.timeline_data:
                if isinstance(event_obj.timeline_data, str):
                    existing = _json.loads(event_obj.timeline_data)
                elif isinstance(event_obj.timeline_data, list):
                    existing = event_obj.timeline_data
            existing.append({
                "time": datetime.utcnow().isoformat(),
                "event": summary,
                "actor": agent_name,
            })
            event_obj.timeline_data = _json.dumps(existing, ensure_ascii=False)
    except Exception:
        pass  # 时间线更新失败不影响主流程


async def _workflow_run_has_state_json(db: AsyncSession) -> bool:
    global _WF_HAS_STATE_JSON
    if _WF_HAS_STATE_JSON is not None:
        return _WF_HAS_STATE_JSON

    from sqlalchemy import text as sa_text

    try:
        dialect_name = db.bind.dialect.name if db.bind and db.bind.dialect else ""
    except Exception:
        dialect_name = ""

    try:
        if dialect_name == "sqlite":
            rows = (await db.execute(sa_text("PRAGMA table_info(workflow_runs)"))).mappings().all()
            _WF_HAS_STATE_JSON = any((r.get("name") or "") == "state_json" for r in rows)
        else:
            row = (await db.execute(
                sa_text("SELECT 1 FROM information_schema.columns "
                        "WHERE table_name = 'workflow_runs' AND column_name = 'state_json' LIMIT 1")
            )).first()
            _WF_HAS_STATE_JSON = row is not None
    except Exception:
        _WF_HAS_STATE_JSON = False

    return _WF_HAS_STATE_JSON


async def _update_workflow_run_state(
    db: AsyncSession,
    run_id: str,
    stage: str,
    status: str,
    now: str,
    state_json: str,
    story_packet_id: str | None = None,
):
    from sqlalchemy import text as sa_text

    supports_state_json = await _workflow_run_has_state_json(db)
    if supports_state_json:
        try:
            if story_packet_id is None:
                await db.execute(
                    sa_text("UPDATE workflow_runs SET current_stage = :stage, status = :status, "
                            "state_json = :sj, updated_at = :now WHERE run_id = :rid"),
                    {"stage": stage, "status": status, "sj": state_json, "now": now, "rid": run_id},
                )
            else:
                await db.execute(
                    sa_text("UPDATE workflow_runs SET current_stage = :stage, status = :status, "
                            "story_packet_id = COALESCE(:sp_id, story_packet_id), "
                            "state_json = :sj, updated_at = :now WHERE run_id = :rid"),
                    {
                        "stage": stage,
                        "status": status,
                        "sp_id": story_packet_id,
                        "sj": state_json,
                        "now": now,
                        "rid": run_id,
                    },
                )
            return
        except Exception as state_exc:
            logger.warning(
                f"workflow_runs state_json update failed for run {run_id}, fallback to basic update: {state_exc}"
            )
            global _WF_HAS_STATE_JSON
            _WF_HAS_STATE_JSON = False

    if story_packet_id is None:
        await db.execute(
            sa_text("UPDATE workflow_runs SET current_stage = :stage, status = :status, "
                    "updated_at = :now WHERE run_id = :rid"),
            {"stage": stage, "status": status, "now": now, "rid": run_id},
        )
    else:
        await db.execute(
            sa_text("UPDATE workflow_runs SET current_stage = :stage, status = :status, "
                    "story_packet_id = COALESCE(:sp_id, story_packet_id), "
                    "updated_at = :now WHERE run_id = :rid"),
            {"stage": stage, "status": status, "sp_id": story_packet_id, "now": now, "rid": run_id},
        )


def _normalize_id(value) -> str | None:
    return str(value) if value is not None else None


def _json_safe(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    return str(value)


async def _get_next_draft_version(db, sp_id: str) -> int:
    """获取指定 StoryPacket 的下一个草稿版本号"""
    from sqlalchemy import text as sa_text
    result = await db.execute(
        sa_text("SELECT COALESCE(MAX(version), 0) + 1 as next_v FROM draft_versions WHERE story_packet_id = :sp_id"),
        {"sp_id": sp_id},
    )
    row = result.mappings().first()
    return row["next_v"] if row else 1


def _summarize_source_payloads(source_items: list[dict]) -> str:
    lines = []
    for idx, item in enumerate(source_items[:8], 1):
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        extracted = item.get("extracted_5w1h") if isinstance(item.get("extracted_5w1h"), dict) else {}
        source_name = metadata.get("source_name") or metadata.get("feed_title") or item.get("source_type") or "来源"
        title = metadata.get("title") or item.get("title") or extracted.get("summary") or item.get("url") or f"来源 {idx}"
        summary = item.get("content") or item.get("raw_content") or extracted.get("summary") or ""
        url = item.get("url") or "无"
        lines.append(f"{idx}. [{source_name}] {title}\n摘要：{str(summary)[:220]}\n链接：{url}")
    return "\n\n".join(lines)


def _summarize_source_rows(source_rows: list[EventSourceItem]) -> str:
    payloads = []
    for row in source_rows:
        payloads.append({
            "source_type": row.source_type,
            "url": row.url,
            "raw_content": row.raw_content,
            "metadata": {
                "title": ((row.extracted_5w1h or {}).get("summary") if isinstance(row.extracted_5w1h, dict) else None) or row.url,
            },
            "extracted_5w1h": row.extracted_5w1h if isinstance(row.extracted_5w1h, dict) else {},
        })
    return _summarize_source_payloads(payloads)


def _infer_source_credibility(source_type: str | None, *, url: str | None = None, metadata: dict | None = None) -> str:
    meta = metadata or {}
    source_name = str(meta.get("source_name") or meta.get("feed_title") or "").lower()
    link = str(url or "").lower()

    if source_type == "upload":
        return "人工上传"
    if source_type == "reporter_tip":
        return "记者线索"
    if source_type == "social_media":
        return "社交媒体"

    official_markers = ["gov.cn", "court", "法院", "证监会", "上交所", "深交所", "政府", "regulator"]
    media_markers = ["新华社", "人民网", "央视", "财新", "澎湃", "sina", "sohu", "163.com", "thepaper", "xinhuanet"]

    if any(marker in source_name or marker in link for marker in official_markers):
        return "官方/监管"
    if any(marker in source_name or marker in link for marker in media_markers):
        return "主流媒体"
    if source_type in {"rss", "website"}:
        return "公开网络来源"
    return "网络来源"


async def _generate_structured_draft(
    llm,
    *,
    event_title: str,
    story_packet_title: str,
    content_type: str,
    angle: str | None,
    source_summary: str,
    verified_claims: list[dict],
    risk_advice: str | None = None,
) -> dict:
    from app.agents.drafting import DraftingAgent

    evidence_parts = [
        f"事件标题：{event_title}",
        f"任务包标题：{story_packet_title}",
    ]
    if angle:
        evidence_parts.append(f"报道角度/关键词：{angle}")
    if source_summary:
        evidence_parts.append(f"来源摘要：\n{source_summary}")
    if verified_claims:
        evidence_parts.append(
            "事实卡：\n" + "\n".join(
                f"- [{c.get('status', 'unknown')}] {c.get('claim_text', '')}"
                for c in verified_claims[:8]
            )
        )

    drafting = DraftingAgent(llm=llm)
    draft_output = await drafting.generate_draft(
        angle=angle or event_title,
        audience="一般读者",
        content_type=content_type or "in_depth",
        evidence_summary="\n\n".join(evidence_parts),
        verified_claims=verified_claims,
        risk_advice=risk_advice or "坚持中性、可归因、可核查的新闻写法；对尚未完全证实的信息明确保留。",
    )

    title = (draft_output.title or story_packet_title).strip()
    lead = (draft_output.lead or "").strip()
    body = (draft_output.body or "").strip()

    if not body:
        fact_lines = [f"- {c.get('claim_text', '')}" for c in verified_claims[:6] if c.get('claim_text')]
        body_sections = []
        if fact_lines:
            body_sections.append("目前可确认的核心事实包括：\n" + "\n".join(fact_lines))
        if source_summary:
            body_sections.append("现有来源与线索摘要：\n" + source_summary[:1200])
        body = "\n\n".join(body_sections) or f"{event_title} 相关线索已进入核查流程，后续将根据新增证据继续补充。"

    if not lead:
        lead = next((c.get("claim_text", "").strip() for c in verified_claims if c.get("claim_text")), "")
    if not lead:
        lead = (source_summary.splitlines()[0].replace("摘要：", "").strip() if source_summary else f"{event_title} 相关线索已进入核查流程。")

    claim_anchor_map = draft_output.claim_anchor_map or await drafting.build_claim_anchor_map(body, verified_claims)

    return {
        "title": title,
        "lead": lead,
        "body": body,
        "body_html": draft_output.body_html or drafting._to_html(body),
        "claim_anchor_map": claim_anchor_map,
        "word_count": len(body),
    }


async def _assess_event_triage(
    llm,
    *,
    event_case_id: str,
    title: str,
    summary: str,
    source_payloads: list[dict],
):
    from app.agents.triage import TriageAgent

    primary = source_payloads[0] if source_payloads else {}
    extracted = primary.get("extracted_5w1h") if isinstance(primary.get("extracted_5w1h"), dict) else {}
    risk_tags = sorted({
        tag
        for item in source_payloads
        for tag in (item.get("risk_tags") or [])
        if isinstance(tag, str)
    })
    triage_agent = TriageAgent(llm=llm)
    return await triage_agent.assess({
        "id": event_case_id,
        "title": title,
        "summary": summary,
        "extracted_5w1h": extracted,
        "sources": source_payloads,
        "risk_tags": risk_tags,
    })


async def _generate_verified_claims_from_sources(
    llm,
    *,
    source_payloads: list[dict],
    max_claims: int = 6,
) -> list[dict]:
    from app.agents.verification import VerificationAgent

    verification_agent = VerificationAgent(llm=llm)
    normalized_sources = [
        {
            **item,
            "credibility": item.get("credibility") or _infer_source_credibility(
                item.get("source_type"),
                url=item.get("url"),
                metadata=item.get("metadata") if isinstance(item.get("metadata"), dict) else {},
            ),
        }
        for item in source_payloads
    ]
    decomposition_text = "\n\n".join(
        f"来源{i}. 标题：{item.get('title') or ((item.get('metadata') or {}).get('title')) or '未命名来源'}\n"
        f"摘要：{item.get('content') or item.get('raw_content') or ''}\n"
        f"链接：{item.get('url') or '无'}"
        for i, item in enumerate(normalized_sources[:8], 1)
    )
    claims = await verification_agent.decompose_claims(decomposition_text[:5000])
    verified_claims = []
    for claim in claims[:max_claims]:
        result = await verification_agent.verify_claim(claim, normalized_sources)
        normalized_status = {
            "contradicted": "disputed",
            "unverified": "insufficient",
        }.get(result.status, result.status)
        verified_claims.append({
            "id": claim.get("id"),
            "claim_text": claim.get("claim_text", ""),
            "risk_level": claim.get("risk_level", "L0"),
            "status": normalized_status,
            "confidence_score": result.confidence_score,
            "supporting_evidence": result.supporting_evidence,
            "contradicting_evidence": result.contradicting_evidence,
            "missing_evidence": result.missing_evidence,
        })
    return verified_claims


async def _scan_newsroom_risk(*, draft_content: str, evidence_summary: str | None = None) -> dict:
    from app.agents.redaction_risk import redaction_risk_agent

    gate_result = await redaction_risk_agent.gate3_full_scan(
        draft_content=draft_content,
        evidence_summary=evidence_summary,
    )
    severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "L3": 0, "L2": 0, "L1": 0, "L0": 0}
    severity_map = {"critical": "L3", "high": "L2", "medium": "L1", "low": "L0"}
    findings = []
    recommendations = []
    for finding in gate_result.risk_findings:
        severity_counts[finding.severity] = severity_counts.get(finding.severity, 0) + 1
        mapped = severity_map.get(finding.severity, "L1")
        severity_counts[mapped] = severity_counts.get(mapped, 0) + 1
        item = {
            "severity": mapped,
            "raw_severity": finding.severity,
            "category": finding.risk_type,
            "description": finding.description,
            "issue": finding.description,
            "location": finding.location,
            "suggestion": finding.recommendation,
        }
        findings.append(item)
        if finding.recommendation:
            recommendations.append(finding.recommendation)

    severity_counts["total"] = len(findings)
    return {
        "findings": findings,
        "severity_summary": severity_counts,
        "recommendations": recommendations,
        "blockers": gate_result.blockers,
        "can_proceed": gate_result.can_proceed,
    }


async def _validate_stage_prerequisites(db: AsyncSession, current_stage: str, story_packet_id: str | None) -> str | None:
    if not story_packet_id:
        return None

    from app.models.claim_card import ClaimCard
    from app.models.channel_package import ChannelPackage
    from app.models.draft_version import DraftVersion
    from app.models.evidence_pack import EvidencePack

    if current_stage in {"editorial_review", "risk_review"}:
        latest_draft = (await db.execute(
            select(DraftVersion)
            .where(DraftVersion.story_packet_id == story_packet_id)
            .order_by(DraftVersion.version.desc())
            .limit(1)
        )).scalars().first()
        if not latest_draft or not (((latest_draft.body or "").strip()) or ((latest_draft.lead or "").strip())):
            return "当前任务包缺少正文草稿，不能继续推进。"

        evidence_count = await db.scalar(
            select(func.count(EvidencePack.id)).where(EvidencePack.story_packet_id == story_packet_id)
        ) or 0
        claim_count = await db.scalar(
            select(func.count(ClaimCard.id)).where(ClaimCard.story_packet_id == story_packet_id)
        ) or 0
        if evidence_count == 0 and claim_count == 0:
            return "当前任务包缺少 Claim Cards / Evidence Pack，不能继续推进。"

    if current_stage in {"channel_adaptation", "channel_review", "human_gate_publish", "publish"}:
        channel_count = await db.scalar(
            select(func.count(ChannelPackage.id)).where(ChannelPackage.story_packet_id == story_packet_id)
        ) or 0
        if channel_count == 0:
            return "当前任务包缺少渠道稿件，不能继续推进。"

    return None


async def _trigger_ai_collection(event_id: str, event_title: str, user_id: str, topic_keywords: str | None = None):
    """异步触发 AI Agent 全流水线：采集 → 去重 → 分诊 → 创建SP → 证据包 → Claims → 草稿 → 风险扫描。
    人工节点（立项/签发）处暂停，等待用户操作。"""
    from app.core.database import async_session_factory
    from app.services.workflow_runtime_service import workflow_runtime_service
    from app.services.event_audit_service import event_audit_service
    from app.agents.source_monitor import SourceMonitorAgent, SourceItem
    from app.services.user_llm_settings import user_llm_settings_service
    from app.models.story_packet import StoryPacket
    from app.models.claim_card import ClaimCard
    from app.models.evidence_pack import EvidencePack
    from app.models.draft_version import DraftVersion
    from app.models.risk_report import RiskReport
    from sqlalchemy import text as sa_text

    try:
        async with async_session_factory() as db:
            # ── 0. Resolve API key (thread-safe: create temp instance) ──
            setting = await user_llm_settings_service.get_user_setting(db, user_id=user_id, include_raw_key=True)
            api_key = _resolve_llm_key(setting.get("api_key"))
            if not api_key:
                logger.warning(f"No LLM API key for event {event_id}, skipping AI collection")
                return

            temp_llm = _create_temp_llm(api_key)
            agent = SourceMonitorAgent(llm=temp_llm)  # isolated instance, no global mutation

            # ── 1. Create workflow run ──
            state = await workflow_runtime_service.create_run(
                db=db, created_by=user_id, event_case_id=event_id,
            )
            wf_id = state.workflow_id
            keywords = topic_keywords or event_title

            await _log_stage(db, event_audit_service, event_id, wf_id,
                             "Source Monitor", f"AI Agent 开始采集关键词 [{keywords}] 相关线索",
                             {"trigger": "auto_on_create", "topic_keywords": keywords})
            await db.commit()

            # ── 2. SOURCE_INGESTION: collect sources ──
            collected_items = []
            try:
                raw_items = await agent.collect_by_keywords(keywords, max_items=5)
                for raw_item in raw_items:
                    try:
                        source_item = await agent.process(raw_item)
                    except Exception:
                        source_item = None

                    if not source_item:
                        fallback_title = (raw_item.metadata or {}).get("title") if isinstance(raw_item.metadata, dict) else None
                        fallback_summary = (raw_item.raw_content or "").strip()
                        source_item = SourceItem(
                            source_type=raw_item.source_type,
                            url=raw_item.url,
                            title=fallback_title,
                            content=fallback_summary[:500],
                            extracted_5w1h={"summary": (fallback_title or fallback_summary[:120] or raw_item.url or "线索")},
                            risk_tags=[],
                            metadata=raw_item.metadata if isinstance(raw_item.metadata, dict) else {},
                        )

                    if source_item:
                        db_item = EventSourceItem(
                            event_case_id=event_id,
                            source_type=source_item.source_type, url=source_item.url,
                            raw_content=source_item.content[:10000] if source_item.content else None,
                            extracted_5w1h=source_item.extracted_5w1h, risk_tags=source_item.risk_tags,
                        )
                        collected_items.append(source_item)
                    else:
                        db_item = EventSourceItem(
                            event_case_id=event_id,
                            source_type=raw_item.source_type, url=raw_item.url,
                            raw_content=(raw_item.raw_content or "")[:10000],
                            extracted_5w1h={}, risk_tags=[],
                        )
                    db.add(db_item)

                await db.flush()
                await _log_stage(db, event_audit_service, event_id, wf_id,
                             "Source Monitor", f"采集完成，共获取 {len(collected_items)} 条线索",
                             {"collected_count": len(collected_items)},
                             stage_action="source_ingestion")
                await db.commit()
            except Exception as e:
                logger.warning(f"Source collection failed for {event_id}: {e}")
                await db.rollback()  # session may be dirty after failed flush
                await _log_stage(db, event_audit_service, event_id, wf_id,
                                 "Source Monitor", f"采集失败: {e}", {"error": str(e)},
                                 stage_action="source_ingestion")
                now = datetime.utcnow().isoformat()
                await db.execute(
                    sa_text("UPDATE workflow_runs SET status = 'failed', last_error = :err, updated_at = :now WHERE run_id = :run_id"),
                    {"err": str(e)[:500], "now": now, "run_id": wf_id},
                )
                await db.commit()
                return

            if not collected_items:
                logger.info(f"No sources collected for {event_id}, pipeline stops")
                await _log_stage(db, event_audit_service, event_id, wf_id,
                                 "Source Monitor", "采集完成但未获取到有效线索，流水线终止",
                                 stage_action="source_ingestion")
                now = datetime.utcnow().isoformat()
                await db.execute(
                    sa_text("UPDATE workflow_runs SET status = 'completed', current_stage = 'source_ingestion', updated_at = :now WHERE run_id = :run_id"),
                    {"now": now, "run_id": wf_id},
                )
                await db.commit()
                return

            # ── 3. DEDUP_CLUSTER (simulated — deduplicate by title) ──
            unique_titles = set()
            deduped = []
            for item in collected_items:
                title = (item.extracted_5w1h or {}).get("summary", item.content[:30]) if item else ""
                if title not in unique_titles:
                    unique_titles.add(title)
                    deduped.append(item)
            await _log_stage(db, event_audit_service, event_id, wf_id,
                             "Dedup & Cluster", f"去重聚合完成，{len(collected_items)} 条 → {len(deduped)} 条",
                             stage_action="dedup_cluster")
            await db.commit()

            # ── 4. TRIAGE (use LLM to assess risk) ──
            triage_risk = "L1"
            try:
                triage_report = await _assess_event_triage(
                    temp_llm,
                    event_case_id=event_id,
                    title=event_title,
                    summary=keywords,
                    source_payloads=[
                        {
                            "title": item.title,
                            "content": item.content,
                            "url": item.url,
                            "extracted_5w1h": item.extracted_5w1h,
                            "risk_tags": item.risk_tags,
                            "source_type": item.source_type,
                        }
                        for item in deduped
                    ],
                )
                triage_risk = triage_report.risk_level or "L1"
            except Exception:
                pass
            # Update event risk_level & status
            event_obj = await db.get(EventCase, event_id)
            if event_obj:
                event_obj.risk_level = triage_risk
                if event_obj.status == "candidate":
                    event_obj.status = "active"
            await _log_stage(db, event_audit_service, event_id, wf_id,
                             "Triage Agent", f"智能分诊完成，风险等级: {triage_risk}",
                             stage_action="triage")
            await db.commit()

            # ── helper: update workflow_run via SQL (keeping state_json in sync) ──
            _wf_sp_id: str | None = None  # track story_packet_id for workflow_run

            async def _update_wf_stage(stage: str, status: str = "running"):
                now = datetime.utcnow().isoformat()
                state_json = _json.dumps({
                    "workflow_id": _normalize_id(wf_id), "event_case_id": _normalize_id(event_id),
                    "story_packet_id": _normalize_id(_wf_sp_id),
                    "current_stage": stage, "updated_at": now,
                })
                await _update_workflow_run_state(
                    db,
                    run_id=str(wf_id),
                    stage=stage,
                    status=status,
                    now=now,
                    state_json=state_json,
                    story_packet_id=_normalize_id(_wf_sp_id),
                )

            # ── 5. HUMAN_GATE_PROJECT — pause here, user decides whether to create SP ──
            await _log_stage(db, event_audit_service, event_id, wf_id,
                             "Orchestrator", "等待人工立项决策（可在 Agent 工作流面板手动推进）",
                             {"stage": "human_gate_project", "action_required": True})
            await _update_wf_stage("human_gate_project", "running")
            await db.commit()

            # ── 6. AUTO-CREATE Story Packet + downstream (if risk >= L1, skip human gate) ──
            # For demo/auto mode: auto-create SP when risk is non-trivial
            if triage_risk in ("L1", "L2", "L3"):
                # Create Story Packet
                sp = StoryPacket(
                    event_case_id=event_id,
                    title=f"{event_title} 深度报道",
                    content_type="in_depth",
                    status="researching",
                    risk_level=triage_risk,
                    owner_id=user_id,
                    desk=event_obj.desk if event_obj else "财经",
                )
                db.add(sp)
                await db.flush()
                await db.refresh(sp)
                _wf_sp_id = sp.id  # noqa: F841 — read by _update_wf_stage closure
                await _log_stage(db, event_audit_service, event_id, wf_id,
                                 "Orchestrator", f"自动立项，创建报道任务包: {sp.title}",
                                 {"story_packet_id": sp.id})

                # ── 7. Evidence Structuring — create evidence pack from collected sources ──
                ep_sources = []
                for item in deduped:
                    ep_sources.append({
                        "type": item.source_type,
                        "title": (item.extracted_5w1h or {}).get("summary", "")[:60] or item.url or "线索",
                        "source": item.url or "AI采集",
                        "credibility": _infer_source_credibility(item.source_type, url=item.url, metadata=item.metadata),
                        "url": item.url,
                    })
                ep = EvidencePack(
                    story_packet_id=sp.id, version=1,
                    sources=ep_sources, citation_anchors=[],
                    completeness_score=min(0.3 + 0.15 * len(ep_sources), 0.9),
                    created_by=user_id,
                )
                db.add(ep)
                await _log_stage(db, event_audit_service, event_id, wf_id,
                                 "Evidence Structuring Agent", f"证据包生成完成，含 {len(ep_sources)} 条来源",
                                 stage_action="evidence_structuring")

                source_payloads = [
                    {
                        "title": item.title,
                        "content": item.content,
                        "raw_content": item.content,
                        "url": item.url,
                        "source_type": item.source_type,
                        "risk_tags": item.risk_tags,
                        "metadata": item.metadata,
                        "extracted_5w1h": item.extracted_5w1h,
                    }
                    for item in deduped
                ]
                try:
                    verified_claims = await _generate_verified_claims_from_sources(
                        temp_llm,
                        source_payloads=source_payloads,
                    )
                except Exception as e:
                    logger.warning(f"Claims generation failed: {e}")
                    verified_claims = []

                claim_objs = []
                for c in verified_claims:
                    claim = ClaimCard(
                        story_packet_id=sp.id,
                        claim_text=c.get("claim_text", ""),
                        risk_level=c.get("risk_level", "L0"),
                        status=c.get("status", "insufficient"),
                        confidence_score=c.get("confidence_score", 0.8),
                        supporting_evidence=c.get("supporting_evidence", []),
                        contradicting_evidence=c.get("contradicting_evidence", []),
                        missing_evidence=c.get("missing_evidence", []),
                    )
                    db.add(claim)
                    claim_objs.append(claim)
                await db.flush()
                verified_claims = [
                    {
                        "id": claim.id,
                        "claim_text": claim.claim_text,
                        "risk_level": claim.risk_level,
                        "status": claim.status,
                        "confidence_score": claim.confidence_score,
                        "supporting_evidence": claim.supporting_evidence,
                        "contradicting_evidence": claim.contradicting_evidence,
                        "missing_evidence": claim.missing_evidence,
                    }
                    for claim in claim_objs
                ]
                await _log_stage(db, event_audit_service, event_id, wf_id,
                                 "Evidence Structuring Agent", f"生成 {len(verified_claims)} 个事实声明 (Claim Cards)",
                                 stage_action="verification")
                await db.commit()

                # ── 8b. Relationship Map — extract entity relationships from collected data ──
                entity_set = set()
                for item in deduped:
                    w5h = item.extracted_5w1h or {}
                    for key in ("who", "where", "what"):
                        val = w5h.get(key)
                        if val and isinstance(val, str) and len(val) > 1:
                            entity_set.add(val)
                if entity_set:
                    entity_graph = [{"entity": e, "type": "auto_extracted"} for e in list(entity_set)[:20]]
                    if event_obj:
                        event_obj.entity_graph_ref = _json.dumps(entity_graph, ensure_ascii=False)
                await _log_stage(db, event_audit_service, event_id, wf_id,
                                 "Relationship Investigation Agent",
                                 f"关系图谱提取完成，发现 {len(entity_set)} 个实体",
                                 stage_action="relationship_map")

                # ── 8c. Redaction Gate 2 — mid-pipeline PII / sensitivity check ──
                pii_count = 0
                for item in deduped:
                    pii_count += len([t for t in (item.risk_tags or []) if t.startswith("pii:")])
                gate2_pass = pii_count == 0
                await _log_stage(db, event_audit_service, event_id, wf_id,
                                 "Redaction & Risk Agent",
                                 f"脱敏门2审查完成，{'通过' if gate2_pass else f'发现 {pii_count} 项PII风险标记，需人工处理'}",
                                 stage_action="redaction_gate2")

                if not gate2_pass:
                    await _update_wf_stage("human_supplement", "running")
                    await _log_stage(db, event_audit_service, event_id, wf_id,
                                     "Orchestrator",
                                     f"脱敏门2未通过（{pii_count} 项PII），流水线暂停在人工补充阶段，等待处理后继续",
                                     {"stage": "human_supplement", "pii_count": pii_count})
                    await db.commit()
                    logger.info(f"Pipeline paused at human_supplement for event {event_id} (PII={pii_count})")
                    return  # stop here — user must advance via workflow-advance API

                await db.commit()

                source_summary = _summarize_source_payloads([
                    {
                        "source_type": item.source_type,
                        "url": item.url,
                        "content": item.content,
                        "metadata": item.metadata,
                        "extracted_5w1h": item.extracted_5w1h,
                    }
                    for item in deduped
                ])
                draft_payload = await _generate_structured_draft(
                    temp_llm,
                    event_title=event_title,
                    story_packet_title=sp.title,
                    content_type=sp.content_type,
                    angle=keywords,
                    source_summary=source_summary,
                    verified_claims=verified_claims,
                )

                next_ver = await _get_next_draft_version(db, sp.id)
                draft = DraftVersion(
                    story_packet_id=sp.id, version=next_ver,
                    title=draft_payload["title"], lead=draft_payload["lead"], body=draft_payload["body"],
                    body_html=draft_payload["body_html"], claim_anchor_map=draft_payload["claim_anchor_map"],
                    word_count=draft_payload["word_count"], created_by=user_id,
                )
                db.add(draft)
                await _log_stage(db, event_audit_service, event_id, wf_id,
                                 "Drafting Agent", f"初稿生成完成，{draft_payload['word_count']} 字",
                                 stage_action="drafting")
                await db.commit()

                body = draft_payload["body"]

                risk_scan = await _scan_newsroom_risk(
                    draft_content=body,
                    evidence_summary=source_summary,
                )

                if risk_scan["findings"]:
                    rr = RiskReport(
                        story_packet_id=sp.id, report_type="risk", version=1,
                        findings=risk_scan["findings"], severity_summary=risk_scan["severity_summary"],
                        recommendations=risk_scan["recommendations"],
                        generated_by="agent",
                    )
                    db.add(rr)
                    await _log_stage(db, event_audit_service, event_id, wf_id,
                                    "Redaction & Risk Agent", f"风险扫描完成，发现 {len(risk_scan['findings'])} 个风险点",
                                    stage_action="risk_scan")
                    await db.commit()

                # ── 11. Redaction Gate 3 — final PII check on generated draft ──
                gate3_issues = []
                pii_patterns = {
                    "phone": r'1[3-9]\d{9}',
                    "id_card": r'\d{17}[\dXx]',
                    "email": r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z]{2,}',
                }
                for pii_name, pattern in pii_patterns.items():
                    if re.search(pattern, body):
                        gate3_issues.append(pii_name)
                high_risk = any(f.get("severity") in ("L2", "L3") for f in findings)
                gate3_pass = len(gate3_issues) == 0 and not high_risk
                gate3_msg = "通过" if gate3_pass else f"发现 {len(gate3_issues)} 项PII + {'高' if high_risk else '低'}风险"
                await _log_stage(db, event_audit_service, event_id, wf_id,
                                 "Redaction & Risk Agent",
                                 f"脱敏门3（终稿审查）完成，{gate3_msg}",
                                 {"gate3_issues": gate3_issues, "high_risk": high_risk},
                                 stage_action="redaction_gate3")
                await db.commit()

                # Update SP status
                sp.status = "drafting"
                # Update workflow_run - blocked if gate3 failed
                wf_status = "running" if gate3_pass else "blocked"
                await _update_wf_stage("editorial_review", wf_status)
                await _log_stage(db, event_audit_service, event_id, wf_id,
                                 "Orchestrator",
                                 f"全自动流水线完成，{'等待编辑审核' if gate3_pass else '⚠️ 脱敏门3未通过，需人工确认风险后继续'}",
                                 {"stage": "editorial_review", "story_packet_id": sp.id,
                                  "gate3_pass": gate3_pass, "blocked": not gate3_pass})
                await db.commit()
                logger.info(f"Full pipeline completed for event {event_id}, SP {sp.id}")
            else:
                # L0 risk: pipeline pauses at human gate, waiting for manual decision
                await _log_stage(db, event_audit_service, event_id, wf_id,
                                 "Orchestrator",
                                 f"风险等级 {triage_risk}，自动流水线在立项节点暂停，等待人工决策是否立项",
                                 {"stage": "human_gate_project", "risk_level": triage_risk})
                await db.commit()
                logger.info(f"Pipeline paused at human_gate_project for L0 event {event_id}")

    except Exception as exc:
        logger.error(f"Failed to trigger AI collection for event {event_id}: {exc}")
        logger.error(traceback.format_exc())
        # Try to mark workflow_run as failed so it doesn't stay 'running' forever
        try:
            from app.core.database import async_session_factory as _asf
            from sqlalchemy import text as _sa_text
            async with _asf() as err_db:
                await err_db.execute(
                    _sa_text("UPDATE workflow_runs SET status = 'failed', last_error = :err, updated_at = :now "
                             "WHERE event_case_id = :eid AND status = 'running'"),
                    {"err": str(exc)[:500], "now": datetime.utcnow().isoformat(), "eid": event_id},
                )
                await err_db.commit()
        except Exception:
            pass  # best-effort


@router.post("", response_model=EventCaseResponse, summary="创建事件案卷", description="创建新事件案卷，初始状态为 candidate。owner 自动设为当前用户。创建后异步触发 AI Agent 采集流程。")
async def create_event(
    req: EventCaseCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    event = EventCase(
        title=req.title,
        summary=req.description or req.summary,
        risk_level=req.risk_level,
        desk=req.desk,
        region=req.region,
        start_time=req.start_time,
        tags=req.tags,
        owner_id=current_user.id,
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)

    # 异步触发 AI Agent 采集流程
    background_tasks.add_task(
        _trigger_ai_collection,
        event.id,
        event.title,
        current_user.id,
        topic_keywords=req.topic_keywords,
    )

    return event


async def _get_visible_event_ids(db: AsyncSession, current_user: User) -> list[str]:
    if current_user.org_id:
        visible_owner_ids = list((await db.execute(
            select(User.id).where(User.org_id == current_user.org_id)
        )).scalars().all())
        if not visible_owner_ids:
            visible_owner_ids = [current_user.id]
    else:
        visible_owner_ids = [current_user.id]

    return list((await db.execute(
        select(EventCase.id).where(EventCase.owner_id.in_(visible_owner_ids))
    )).scalars().all())


async def _assert_event_visible(db: AsyncSession, event: EventCase, current_user: User):
    visible_event_ids = await _get_visible_event_ids(db, current_user)
    if event.id not in visible_event_ids:
        raise NotFoundError("事件案卷", str(event.id))


@router.get("/archived/list", response_model=list[EventCaseResponse], summary="已归档事件列表", description="获取已归档（已删除）的事件案卷列表。")
async def list_archived_events(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.org_id:
        org_member_ids = (await db.execute(
            select(User.id).where(User.org_id == current_user.org_id)
        )).scalars().all()
        owner_filter = EventCase.owner_id.in_(org_member_ids)
    else:
        owner_filter = EventCase.owner_id == current_user.id
    result = await db.execute(
        select(EventCase)
        .where(EventCase.archived_at.isnot(None))
        .where(owner_filter)
        .order_by(EventCase.archived_at.desc())
    )
    return list(result.scalars().all())


@router.post("/{event_id}/collect", summary="手动触发AI采集", description="对已有事件手动触发 AI Agent 采集流程。可指定关键词。")
async def trigger_event_collection(
    event_id: str,
    background_tasks: BackgroundTasks,
    keywords: str | None = Query(None, description="采集关键词，不传则使用事件标题"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from sqlalchemy import text as sa_text

    event = await db.get(EventCase, event_id)
    if not event or event.archived_at:
        raise NotFoundError("事件案卷", str(event_id))
    await _assert_event_visible(db, event, current_user)

    # Guard: prevent duplicate concurrent runs
    existing = (await db.execute(
        sa_text("SELECT run_id FROM workflow_runs WHERE event_case_id = :eid AND status = 'running' LIMIT 1"),
        {"eid": event_id},
    )).mappings().first()
    if existing:
        return {"message": "该事件已有正在运行的采集流程，请等待完成后再试", "event_id": event_id, "running_run_id": existing["run_id"]}

    background_tasks.add_task(
        _trigger_ai_collection,
        event.id,
        event.title,
        current_user.id,
        topic_keywords=keywords or event.title,
    )
    return {"message": f"AI采集已触发，关键词: {keywords or event.title}", "event_id": event_id}


@router.post("/{event_id}/advance-gate", summary="人工推进立项闸口",
             description="当 AI 流水线在 human_gate_project 阶段暂停时，人工确认立项并继续后续流程（创建SP→证据包→Claims→草稿→风控）。")
async def advance_human_gate(
    event_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from sqlalchemy import text as sa_text

    event = await db.get(EventCase, event_id)
    if not event or event.archived_at:
        raise NotFoundError("事件案卷", str(event_id))
    await _assert_event_visible(db, event, current_user)

    # Find the workflow_run that is at human_gate_project and still running
    row = (await db.execute(
        sa_text("SELECT run_id FROM workflow_runs WHERE event_case_id = :eid AND current_stage = 'human_gate_project' AND status = 'running' LIMIT 1"),
        {"eid": event_id},
    )).mappings().first()
    if not row:
        return {"message": "没有处于人工立项闸口的工作流实例", "event_id": event_id, "advanced": False}

    run_id = row["run_id"]
    background_tasks.add_task(
        _advance_past_gate, event_id, event.title, current_user.id, run_id,
    )
    return {"message": "已确认立项，后续流水线正在启动", "event_id": event_id, "run_id": run_id, "advanced": True}


# ── 可推进的人工阶段 ──
_ADVANCEABLE_STAGES = {
    "human_supplement": {"next": "__bg_supplement", "label": "人工补充"},
    "editorial_review": {"next": "risk_review", "label": "编辑审核"},
    "risk_review": {"next": "channel_adaptation", "label": "风险审核"},
    "channel_adaptation": {"next": "channel_review", "label": "渠道适配"},
    "channel_review": {"next": "human_gate_publish", "label": "渠道审核"},
    "human_gate_publish": {"next": "publish", "label": "发布闸口"},
    "publish": {"next": "post_publish_monitor", "label": "发布"},
    "post_publish_monitor": {"next": "completed", "label": "发布后监测"},
}


@router.post("/{event_id}/workflow-advance", summary="推进工作流阶段",
             description="通用推进接口：支持从 human_supplement / editorial_review / risk_review 推进到下一阶段。")
async def advance_workflow_stage(
    event_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from sqlalchemy import text as sa_text
    from app.services.event_audit_service import event_audit_service
    from app.models.channel_package import ChannelPackage
    from app.models.draft_version import DraftVersion
    from app.services.user_llm_settings import user_llm_settings_service

    event = await db.get(EventCase, event_id)
    if not event or event.archived_at:
        raise NotFoundError("事件案卷", str(event_id))
    await _assert_event_visible(db, event, current_user)

    # Find running or blocked workflow_run at an advanceable stage
    row = (await db.execute(
        sa_text("SELECT run_id, current_stage, story_packet_id FROM workflow_runs "
                "WHERE event_case_id = :eid AND status IN ('running', 'blocked') LIMIT 1"),
        {"eid": event_id},
    )).mappings().first()
    if not row:
        return {"message": "没有可推进的工作流实例", "event_id": event_id, "advanced": False}

    stage = row["current_stage"]
    cfg = _ADVANCEABLE_STAGES.get(stage)
    if not cfg:
        return {"message": f"当前阶段 [{stage}] 不支持人工推进", "event_id": event_id, "advanced": False}

    run_id = row["run_id"]
    prerequisite_error = await _validate_stage_prerequisites(db, stage, row.get("story_packet_id"))
    if prerequisite_error:
        return {"message": prerequisite_error, "event_id": event_id, "run_id": run_id, "advanced": False}

    if cfg["next"] == "__bg_supplement":
        # human_supplement → needs background task to run drafting + risk_scan
        background_tasks.add_task(
            _continue_from_supplement, event_id, event.title, current_user.id, run_id,
        )
        return {"message": "人工补充已确认，继续生成稿件", "event_id": event_id, "run_id": run_id, "advanced": True}
    else:
        # Simple stage transition (editorial_review → risk_review, risk_review → completed)
        next_stage = cfg["next"]
        next_status = "completed" if next_stage == "completed" else "running"
        now = datetime.utcnow().isoformat()
        sj = _json.dumps({"workflow_id": _normalize_id(run_id), "event_case_id": _normalize_id(event_id),
                           "story_packet_id": _normalize_id(row.get("story_packet_id")),
                           "current_stage": next_stage, "updated_at": now})
        await _update_workflow_run_state(
            db,
            run_id=str(run_id),
            stage=next_stage,
            status=next_status,
            now=now,
            state_json=sj,
        )
        await _log_stage(
            db, event_audit_service, event_id, run_id,
            "Orchestrator", f"{cfg['label']}审核通过，推进到 {next_stage}",
            stage_action="pipeline_stage",
        )
        # Update SP status to match workflow progression
        sp_id = row.get("story_packet_id")
        if sp_id:
            sp_obj = await db.get(StoryPacket, sp_id)
            if sp_obj:
                # Stage side-effects for real downstream linkage
                if next_stage == "channel_adaptation":
                    try:
                        from app.agents.channel_adaptation import channel_adaptation_agent
                        latest_draft = (await db.execute(
                            select(DraftVersion)
                            .where(DraftVersion.story_packet_id == sp_id)
                            .order_by(DraftVersion.version.desc())
                            .limit(1)
                        )).scalars().first()

                        created = 0
                        if latest_draft:
                            existing_types = set((await db.execute(
                                select(ChannelPackage.channel_type)
                                .where(ChannelPackage.story_packet_id == sp_id)
                            )).scalars().all())
                            target_channels = ["website", "wechat", "weibo"]
                            missing_channels = [c for c in target_channels if c not in existing_types]

                            outputs_map: dict[str, dict] = {}
                            if missing_channels:
                                try:
                                    setting = await user_llm_settings_service.get_user_setting(
                                        db, user_id=current_user.id, include_raw_key=True,
                                    )
                                    api_key = _resolve_llm_key(setting.get("api_key"))
                                    if api_key:
                                        llm_backup = channel_adaptation_agent.llm
                                        channel_adaptation_agent.llm = _create_temp_llm(api_key)
                                        try:
                                            outputs = await channel_adaptation_agent.batch_adapt(
                                                source_draft_id=latest_draft.id,
                                                original_title=latest_draft.title or event.title,
                                                original_content=(latest_draft.body or "")[:4000],
                                                channels=missing_channels,
                                                risk_level=sp_obj.risk_level or "L1",
                                            )
                                            outputs_map = {o.channel_type: o.to_dict() for o in outputs}
                                        finally:
                                            channel_adaptation_agent.llm = llm_backup
                                except Exception as adapt_exc:
                                    logger.warning(f"Channel adaptation AI failed for run {run_id}: {adapt_exc}")

                                for channel in missing_channels:
                                    out = outputs_map.get(channel)
                                    content_payload = {
                                        "title": (out or {}).get("title") or (latest_draft.title or event.title),
                                        "body": ((out or {}).get("content") or {}).get("body") or (latest_draft.body or "")[:2000],
                                        "meta": out or {},
                                    }
                                    db.add(ChannelPackage(
                                        story_packet_id=sp_id,
                                        source_draft_id=latest_draft.id,
                                        channel_type=channel,
                                        status=(out or {}).get("status", "draft"),
                                        content=content_payload,
                                        drift_score=(out or {}).get("drift_score"),
                                        drift_threshold=0.30,
                                        platform_rules_check=((out or {}).get("compliance_result") or {}),
                                        owner_id=current_user.id,
                                    ))
                                    created += 1

                        await _log_stage(
                            db, event_audit_service, event_id, run_id,
                            "Channel Adaptation Agent", f"渠道适配完成，新增 {created} 个渠道包",
                            {"story_packet_id": sp_id, "created_channel_packages": created},
                            stage_action="channel_adaptation",
                        )
                    except Exception as side_exc:
                        logger.warning(f"Channel adaptation side-effect failed for run {run_id}: {side_exc}")

                if next_stage == "publish":
                    try:
                        packages = list((await db.execute(
                            select(ChannelPackage).where(ChannelPackage.story_packet_id == sp_id)
                        )).scalars().all())
                        pub_time = datetime.utcnow()
                        for pkg in packages:
                            pkg.status = "published"
                            pkg.published_at = pub_time
                            if not pkg.published_url:
                                pkg.published_url = f"https://newsflow.local/{pkg.channel_type}/{pkg.id}"
                        await _log_stage(
                            db, event_audit_service, event_id, run_id,
                            "Publish Agent", f"发布完成，渠道数 {len(packages)}",
                            {"story_packet_id": sp_id, "published_channel_count": len(packages)},
                            stage_action="publish",
                        )
                    except Exception as side_exc:
                        logger.warning(f"Publish side-effect failed for run {run_id}: {side_exc}")

                if next_stage == "post_publish_monitor":
                    await _log_stage(
                        db, event_audit_service, event_id, run_id,
                        "Post Publish Monitor", "发布后监测已启动",
                        {"story_packet_id": sp_id},
                        stage_action="post_publish_monitor",
                    )

                sp_status_map = {
                    "risk_review": "risk_review",
                    "channel_adaptation": "channel_packaging",
                    "channel_review": "channel_review",
                    "human_gate_publish": "ready_to_publish",
                    "publish": "published",
                    "post_publish_monitor": "monitoring",
                    "completed": "monitoring",
                }
                new_sp_status = sp_status_map.get(next_stage)
                if new_sp_status:
                    sp_obj.status = new_sp_status
        await db.commit()
        return {"message": f"{cfg['label']}通过，已推进到 {next_stage}",
                "event_id": event_id, "run_id": run_id, "stage": next_stage, "advanced": True}


async def _continue_from_supplement(event_id: str, event_title: str, user_id: str, wf_id: str):
    """从 human_supplement 继续：drafting → risk_scan → gate3 → editorial_review。"""
    from app.core.database import async_session_factory
    from app.services.event_audit_service import event_audit_service
    from app.services.user_llm_settings import user_llm_settings_service
    from app.models.draft_version import DraftVersion
    from app.models.risk_report import RiskReport
    from sqlalchemy import text as sa_text

    try:
        async with async_session_factory() as db:
            setting = await user_llm_settings_service.get_user_setting(db, user_id=user_id, include_raw_key=True)
            api_key = _resolve_llm_key(setting.get("api_key"))
            if not api_key:
                now = datetime.utcnow().isoformat()
                await db.execute(
                    sa_text("UPDATE workflow_runs SET status = 'failed', last_error = :err, updated_at = :now WHERE run_id = :rid"),
                    {"err": "无可用 LLM API Key", "now": now, "rid": wf_id},
                )
                await db.commit()
                return

            temp_llm = _create_temp_llm(api_key)

            # Load workflow run to get story_packet_id
            run_row = (await db.execute(
                sa_text("SELECT story_packet_id FROM workflow_runs WHERE run_id = :rid"),
                {"rid": wf_id},
            )).mappings().first()
            sp_id = run_row["story_packet_id"] if run_row else None
            if not sp_id:
                now = datetime.utcnow().isoformat()
                await db.execute(
                    sa_text("UPDATE workflow_runs SET status = 'failed', last_error = :err, updated_at = :now WHERE run_id = :rid"),
                    {"err": "无关联任务包，无法生成稿件", "now": now, "rid": wf_id},
                )
                await db.commit()
                return

            from app.models.story_packet import StoryPacket
            sp = await db.get(StoryPacket, sp_id)

            await _log_stage(db, event_audit_service, event_id, wf_id,
                             "Orchestrator", "人工补充完成，继续生成稿件")

            # helper
            async def _update_wf_s(stage: str, status: str = "running"):
                now = datetime.utcnow().isoformat()
                sj = _json.dumps({"workflow_id": _normalize_id(wf_id), "event_case_id": _normalize_id(event_id),
                                  "story_packet_id": _normalize_id(sp_id), "current_stage": stage, "updated_at": now})
                await _update_workflow_run_state(
                    db,
                    run_id=str(wf_id),
                    stage=stage,
                    status=status,
                    now=now,
                    state_json=sj,
                )

            source_rows = (await db.execute(
                select(EventSourceItem).where(EventSourceItem.event_case_id == event_id)
            )).scalars().all()
            claim_rows = (await db.execute(
                select(ClaimCard).where(ClaimCard.story_packet_id == sp_id)
            )).scalars().all()
            verified_claims = [
                {
                    "id": claim.id,
                    "claim_text": claim.claim_text,
                    "risk_level": claim.risk_level,
                    "status": claim.status,
                    "confidence_score": claim.confidence_score,
                }
                for claim in claim_rows
            ]
            draft_payload = await _generate_structured_draft(
                temp_llm,
                event_title=event_title,
                story_packet_title=sp.title if sp else event_title,
                content_type=sp.content_type if sp else "in_depth",
                angle=event_title,
                source_summary=_summarize_source_rows(source_rows),
                verified_claims=verified_claims,
            )
            next_ver = await _get_next_draft_version(db, sp_id)
            db.add(DraftVersion(
                story_packet_id=sp_id, version=next_ver, title=draft_payload["title"],
                lead=draft_payload["lead"], body=draft_payload["body"],
                body_html=draft_payload["body_html"], claim_anchor_map=draft_payload["claim_anchor_map"],
                word_count=draft_payload["word_count"], created_by=user_id,
            ))
            await _log_stage(db, event_audit_service, event_id, wf_id,
                             "Drafting Agent", f"初稿生成完成（v{next_ver}），{draft_payload['word_count']} 字",
                             stage_action="drafting")
            await db.commit()

            body = draft_payload["body"]

            risk_scan = await _scan_newsroom_risk(
                draft_content=body,
                evidence_summary=_summarize_source_rows(source_rows),
            )
            findings = risk_scan["findings"]
            if findings:
                db.add(RiskReport(
                    story_packet_id=sp_id, report_type="risk", version=1,
                    findings=findings, severity_summary=risk_scan["severity_summary"],
                    recommendations=risk_scan["recommendations"],
                    generated_by="ai_pipeline",
                ))
            await _log_stage(db, event_audit_service, event_id, wf_id,
                             "Redaction & Risk Agent", f"风险扫描完成，发现 {len(findings)} 项风险",
                             stage_action="risk_scan")
            await db.commit()

            # Gate 3
            gate3_issues = []
            pii_patterns = {"phone": r'1[3-9]\d{9}', "id_card": r'\d{17}[\dXx]',
                            "email": r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z]{2,}'}
            for pii_name, pattern in pii_patterns.items():
                if re.search(pattern, body):
                    gate3_issues.append(pii_name)
            high_risk = any(f.get("severity") in ("L2", "L3") for f in findings)
            gate3_pass = len(gate3_issues) == 0 and not high_risk
            gate3_msg = "通过" if gate3_pass else f"发现 {len(gate3_issues)} 项PII + {'高' if high_risk else '低'}风险"
            await _log_stage(db, event_audit_service, event_id, wf_id,
                             "Redaction & Risk Agent", f"脱敏门3（终稿审查）完成，{gate3_msg}",
                             {"gate3_issues": gate3_issues, "high_risk": high_risk},
                             stage_action="redaction_gate3")

            if sp:
                sp.status = "drafting"
            wf_status = "running" if gate3_pass else "blocked"
            await _update_wf_s("editorial_review", wf_status)
            await _log_stage(db, event_audit_service, event_id, wf_id,
                             "Orchestrator",
                             f"人工补充后流水线完成，{'等待编辑审核' if gate3_pass else '⚠️ 脱敏门3未通过，需人工确认风险后继续'}",
                             {"stage": "editorial_review", "story_packet_id": sp_id,
                              "gate3_pass": gate3_pass, "blocked": not gate3_pass})
            await db.commit()
            logger.info(f"Supplement pipeline completed for event {event_id}")

    except Exception as exc:
        logger.error(f"_continue_from_supplement failed for event {event_id}: {exc}")
        logger.error(traceback.format_exc())
        try:
            from app.core.database import async_session_factory as _asf
            from sqlalchemy import text as _t
            async with _asf() as err_db:
                await err_db.execute(
                    _t("UPDATE workflow_runs SET status = 'failed', last_error = :err, updated_at = :now WHERE run_id = :rid"),
                    {"err": str(exc)[:500], "now": datetime.utcnow().isoformat(), "rid": wf_id},
                )
                await err_db.commit()
        except Exception:
            pass


async def _advance_past_gate(event_id: str, event_title: str, user_id: str, wf_id: str):
    """在 human_gate_project 后继续执行下游流水线：SP → 证据包 → Claims → 关系图谱 → 脱敏门2 → 草稿 → 风控。"""
    from app.core.database import async_session_factory
    from app.services.event_audit_service import event_audit_service
    from app.services.user_llm_settings import user_llm_settings_service
    from app.models.story_packet import StoryPacket
    from app.models.claim_card import ClaimCard
    from app.models.evidence_pack import EvidencePack
    from app.models.draft_version import DraftVersion
    from app.models.risk_report import RiskReport
    from sqlalchemy import text as sa_text

    try:
        async with async_session_factory() as db:
            # Resolve LLM
            setting = await user_llm_settings_service.get_user_setting(db, user_id=user_id, include_raw_key=True)
            api_key = _resolve_llm_key(setting.get("api_key"))
            if not api_key:
                logger.warning(f"No LLM API key for advance-gate {event_id}")
                now = datetime.utcnow().isoformat()
                await db.execute(
                    sa_text("UPDATE workflow_runs SET status = 'failed', last_error = :err, updated_at = :now WHERE run_id = :rid"),
                    {"err": "无可用 LLM API Key", "now": now, "rid": wf_id},
                )
                await db.commit()
                return

            temp_llm = _create_temp_llm(api_key)

            # Load event and existing source items
            event_obj = await db.get(EventCase, event_id)
            if not event_obj:
                now = datetime.utcnow().isoformat()
                await db.execute(
                    sa_text("UPDATE workflow_runs SET status = 'failed', last_error = :err, updated_at = :now WHERE run_id = :rid"),
                    {"err": "事件案卷不存在", "now": now, "rid": wf_id},
                )
                await db.commit()
                return
            keywords = event_obj.title

            source_rows = (await db.execute(
                select(EventSourceItem).where(EventSourceItem.event_case_id == event_id)
            )).scalars().all()
            if not source_rows:
                await _log_stage(db, event_audit_service, event_id, wf_id,
                                 "Orchestrator", "人工立项通过，但无已采集线索，无法继续")
                now = datetime.utcnow().isoformat()
                await db.execute(
                    sa_text("UPDATE workflow_runs SET status = 'failed', last_error = :err, updated_at = :now WHERE run_id = :rid"),
                    {"err": "无已采集线索，无法继续", "now": now, "rid": wf_id},
                )
                await db.commit()
                return

            await _log_stage(db, event_audit_service, event_id, wf_id,
                             "Orchestrator", "人工立项决策通过，开始创建报道任务包及后续流程")

            # helper
            _wf_sp_id: str | None = None

            async def _update_wf(stage: str, status: str = "running"):
                now = datetime.utcnow().isoformat()
                sj = _json.dumps({"workflow_id": _normalize_id(wf_id), "event_case_id": _normalize_id(event_id),
                                  "story_packet_id": _normalize_id(_wf_sp_id), "current_stage": stage, "updated_at": now})
                await _update_workflow_run_state(
                    db,
                    run_id=str(wf_id),
                    stage=stage,
                    status=status,
                    now=now,
                    state_json=sj,
                    story_packet_id=_normalize_id(_wf_sp_id),
                )

            # Create Story Packet
            sp = StoryPacket(
                event_case_id=event_id,
                title=f"{event_title} 深度报道",
                content_type="in_depth", status="researching",
                risk_level=event_obj.risk_level or "L1",
                owner_id=user_id,
                desk=event_obj.desk or "综合",
            )
            db.add(sp)
            await db.flush()
            await db.refresh(sp)
            _wf_sp_id = sp.id
            await _log_stage(db, event_audit_service, event_id, wf_id,
                             "Orchestrator", f"创建报道任务包: {sp.title}", {"story_packet_id": sp.id})

            # Evidence Pack from existing sources
            ep_sources = []
            for si in source_rows:
                w5h = si.extracted_5w1h if isinstance(si.extracted_5w1h, dict) else {}
                ep_sources.append({
                    "type": si.source_type, "title": w5h.get("summary", "")[:60] or si.url or "线索",
                    "source": si.url or "AI采集",
                    "credibility": _infer_source_credibility(si.source_type, url=si.url, metadata={}),
                    "url": si.url,
                })
            ep = EvidencePack(
                story_packet_id=sp.id, version=1,
                sources=ep_sources, citation_anchors=[],
                completeness_score=min(0.3 + 0.15 * len(ep_sources), 0.9),
                created_by=user_id,
            )
            db.add(ep)
            await _log_stage(db, event_audit_service, event_id, wf_id,
                             "Evidence Structuring Agent", f"证据包生成完成，含 {len(ep_sources)} 条来源",
                             stage_action="evidence_structuring")

            try:
                verified_claims = await _generate_verified_claims_from_sources(
                    temp_llm,
                    source_payloads=[
                        {
                            "title": ((si.extracted_5w1h or {}).get("summary") if isinstance(si.extracted_5w1h, dict) else None) or si.url,
                            "content": si.raw_content,
                            "raw_content": si.raw_content,
                            "url": si.url,
                            "source_type": si.source_type,
                            "risk_tags": si.risk_tags,
                            "metadata": {},
                            "extracted_5w1h": si.extracted_5w1h if isinstance(si.extracted_5w1h, dict) else {},
                        }
                        for si in source_rows
                    ],
                )
            except Exception as e:
                logger.warning(f"Claims generation failed (advance): {e}")
                verified_claims = []
            for c in verified_claims:
                db.add(ClaimCard(
                    story_packet_id=sp.id,
                    claim_text=c.get("claim_text", ""), risk_level=c.get("risk_level", "L0"),
                    status=c.get("status", "insufficient"), confidence_score=c.get("confidence_score", 0.8),
                    supporting_evidence=c.get("supporting_evidence", []),
                    contradicting_evidence=c.get("contradicting_evidence", []),
                    missing_evidence=c.get("missing_evidence", []),
                ))
            await _log_stage(db, event_audit_service, event_id, wf_id,
                            "Evidence Structuring Agent", f"生成 {len(verified_claims)} 个事实声明",
                            stage_action="verification")
            await db.commit()

            # Relationship map
            entity_set = set()
            for si in source_rows:
                w5h = si.extracted_5w1h if isinstance(si.extracted_5w1h, dict) else {}
                for key in ("who", "where", "what"):
                    val = w5h.get(key)
                    if val and isinstance(val, str) and len(val) > 1:
                        entity_set.add(val)
            if entity_set and event_obj:
                event_obj.entity_graph_ref = _json.dumps(
                    [{"entity": e, "type": "auto_extracted"} for e in list(entity_set)[:20]], ensure_ascii=False)
            await _log_stage(db, event_audit_service, event_id, wf_id,
                             "Relationship Investigation Agent", f"关系图谱提取完成，发现 {len(entity_set)} 个实体",
                             stage_action="relationship_map")

            # Redaction gate 2
            pii_count = 0
            for si in source_rows:
                for t in (si.risk_tags or []):
                    if isinstance(t, str) and t.startswith("pii:"):
                        pii_count += 1
            gate2_pass = pii_count == 0
            await _log_stage(db, event_audit_service, event_id, wf_id,
                             "Redaction & Risk Agent",
                             f"脱敏门2审查完成，{'通过' if gate2_pass else f'发现 {pii_count} 项PII风险标记，需人工处理'}",
                             stage_action="redaction_gate2")

            if not gate2_pass:
                await _update_wf("human_supplement", "running")
                await _log_stage(db, event_audit_service, event_id, wf_id,
                                 "Orchestrator",
                                 f"脱敏门2未通过（{pii_count} 项PII），流水线暂停在人工补充阶段",
                                 {"stage": "human_supplement", "pii_count": pii_count})
                await db.commit()
                logger.info(f"advance-gate paused at human_supplement for {event_id}")
                return

            await db.commit()

            verified_claims = [
                {
                    "id": claim.id,
                    "claim_text": claim.claim_text,
                    "risk_level": claim.risk_level,
                    "status": claim.status,
                    "confidence_score": claim.confidence_score,
                }
                for claim in (await db.execute(
                    select(ClaimCard).where(ClaimCard.story_packet_id == sp.id)
                )).scalars().all()
            ]
            draft_payload = await _generate_structured_draft(
                temp_llm,
                event_title=event_title,
                story_packet_title=sp.title,
                content_type=sp.content_type,
                angle=event_title,
                source_summary=_summarize_source_rows(source_rows),
                verified_claims=verified_claims,
            )
            next_ver = await _get_next_draft_version(db, sp.id)
            db.add(DraftVersion(
                story_packet_id=sp.id, version=next_ver, title=draft_payload["title"],
                lead=draft_payload["lead"], body=draft_payload["body"],
                body_html=draft_payload["body_html"], claim_anchor_map=draft_payload["claim_anchor_map"],
                word_count=draft_payload["word_count"], created_by=user_id,
            ))
            await _log_stage(db, event_audit_service, event_id, wf_id,
                             "Drafting Agent", f"初稿生成完成（v{next_ver}），{draft_payload['word_count']} 字",
                             stage_action="drafting")
            await db.commit()

            body = draft_payload["body"]

            risk_scan = await _scan_newsroom_risk(
                draft_content=body,
                evidence_summary=_summarize_source_rows(source_rows),
            )
            findings = risk_scan["findings"]
            if findings:
                db.add(RiskReport(
                    story_packet_id=sp.id, report_type="risk", version=1,
                    findings=findings, severity_summary=risk_scan["severity_summary"],
                    recommendations=risk_scan["recommendations"],
                    generated_by="ai_pipeline",
                ))
            await _log_stage(db, event_audit_service, event_id, wf_id,
                             "Redaction & Risk Agent", f"风险扫描完成，发现 {len(findings)} 项风险",
                             stage_action="risk_scan")
            await db.commit()

            # Redaction gate 3 — final PII check on draft
            gate3_issues = []
            pii_patterns = {
                "phone": r'1[3-9]\d{9}',
                "id_card": r'\d{17}[\dXx]',
                "email": r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z]{2,}',
            }
            for pii_name, pattern in pii_patterns.items():
                if re.search(pattern, body):
                    gate3_issues.append(pii_name)
            high_risk = any(f.get("severity") in ("L2", "L3") for f in findings)
            gate3_pass = len(gate3_issues) == 0 and not high_risk
            gate3_msg = "通过" if gate3_pass else f"发现 {len(gate3_issues)} 项PII + {'高' if high_risk else '低'}风险"
            await _log_stage(db, event_audit_service, event_id, wf_id,
                             "Redaction & Risk Agent", f"脱敏门3（终稿审查）完成，{gate3_msg}",
                             {"gate3_issues": gate3_issues, "high_risk": high_risk},
                             stage_action="redaction_gate3")
            await db.commit()

            sp.status = "drafting"
            wf_status = "running" if gate3_pass else "blocked"
            await _update_wf("editorial_review", wf_status)
            await _log_stage(db, event_audit_service, event_id, wf_id,
                             "Orchestrator",
                             f"人工立项后流水线完成，{'等待编辑审核' if gate3_pass else '⚠️ 脱敏门3未通过，需人工确认风险后继续'}",
                             {"stage": "editorial_review", "story_packet_id": sp.id,
                              "gate3_pass": gate3_pass, "blocked": not gate3_pass})
            await db.commit()
            logger.info(f"Advance-gate pipeline completed for event {event_id}, SP {sp.id}")

    except Exception as exc:
        logger.error(f"advance_past_gate failed for event {event_id}: {exc}")
        logger.error(traceback.format_exc())
        try:
            from app.core.database import async_session_factory as _asf
            from sqlalchemy import text as _t
            async with _asf() as err_db:
                await err_db.execute(
                    _t("UPDATE workflow_runs SET status = 'failed', last_error = :err, updated_at = :now WHERE run_id = :rid"),
                    {"err": str(exc)[:500], "now": datetime.utcnow().isoformat(), "rid": wf_id},
                )
                await err_db.commit()
        except Exception:
            pass


@router.get("/{event_id}", response_model=EventCaseResponse, summary="事件案卷详情", description="获取单个事件案卷详情，已归档的案卷返回 404。")
async def get_event(
    event_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    event = await db.get(EventCase, event_id)
    if not event or event.archived_at:
        raise NotFoundError("事件案卷", str(event_id))
    await _assert_event_visible(db, event, current_user)
    resp = EventCaseResponse.model_validate(event)
    if event.owner_id:
        owner = await db.get(User, event.owner_id)
        resp.owner_display_name = owner.display_name if owner else None
    return resp


@router.get("/{event_id}/agent-activities", summary="事件Agent活动", description="获取指定事件的Agent工作流活动记录。")
async def get_event_agent_activities(
    event_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    import json as _json
    from app.models.audit_log import AuditLog

    event = await db.get(EventCase, event_id)
    if not event:
        raise NotFoundError("事件案卷", str(event_id))
    await _assert_event_visible(db, event, current_user)

    # 查找直接关联到这个事件的 agent 日志
    result = await db.execute(
        select(AuditLog)
        .where(AuditLog.actor_type == "agent")
        .where(AuditLog.object_id == event_id)
        .order_by(AuditLog.created_at.asc())
    )
    logs = list(result.scalars().all())

    # 也查找关联到该事件下 story_packet 的日志
    sp_ids_result = await db.execute(
        select(StoryPacket.id).where(StoryPacket.event_case_id == event_id)
    )
    sp_ids = [r[0] for r in sp_ids_result.fetchall()]
    if sp_ids:
        sp_logs = await db.execute(
            select(AuditLog)
            .where(AuditLog.actor_type == "agent")
            .where(AuditLog.object_id.in_(sp_ids))
            .order_by(AuditLog.created_at.asc())
        )
        logs.extend(sp_logs.scalars().all())

    # 按时间排序
    logs.sort(key=lambda x: x.created_at)

    activities = []
    for log in logs:
        details = log.details
        if isinstance(details, str):
            try:
                details = _json.loads(details)
            except Exception:
                details = {}
        if not isinstance(details, dict):
            details = {}
        activities.append({
            "id": log.id,
            "timestamp": log.created_at.isoformat() if log.created_at else None,
            "agent_name": details.get("agent_name", "Unknown Agent"),
            "action": log.action,
            "object_type": log.object_type,
            "object_id": log.object_id,
            "summary": details.get("summary", f"{details.get('agent_name', 'Agent')} 执行 {log.action}"),
            "ai_model": log.ai_model,
            "tokens": log.ai_token_usage if isinstance(log.ai_token_usage, dict) else (
                _json.loads(log.ai_token_usage) if isinstance(log.ai_token_usage, str) else None
            ),
            "details": details,
        })

    return activities


@router.patch("/{event_id}", response_model=EventCaseResponse, summary="更新事件案卷", description="部分更新事件案卷字段（title/summary/risk_level/desk/region/tags）。")
async def update_event(
    event_id: str,
    req: EventCaseUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    event = await db.get(EventCase, event_id)
    if not event or event.archived_at:
        raise NotFoundError("事件案卷", str(event_id))
    await _assert_event_visible(db, event, current_user)
    update_data = req.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(event, field, value)
    await db.commit()
    await db.refresh(event)
    return event


@router.get("/{event_id}/workflow-runs", summary="事件关联工作流实例", description="获取事件关联的所有 AI Agent 工作流实例。")
async def get_event_workflow_runs(
    event_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.services.workflow_runtime_service import workflow_runtime_service

    event = await db.get(EventCase, event_id)
    if not event or event.archived_at:
        raise NotFoundError("事件案卷", str(event_id))
    await _assert_event_visible(db, event, current_user)

    runs = await workflow_runtime_service.list_runs_by_event(db, event_id)
    result = []
    for row in runs:
        state_json = row.get("state_json", "{}")
        if isinstance(state_json, str):
            try:
                state_json = _json.loads(state_json)
            except Exception:
                state_json = {}
        result.append({
            "run_id": row["run_id"],
            "event_case_id": row["event_case_id"],
            "story_packet_id": row.get("story_packet_id"),
            "current_stage": row["current_stage"],
            "status": row["status"],
            "last_error": row.get("last_error"),
            "created_by": row.get("created_by"),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "state": state_json,
        })
    return result


@router.get("/{event_id}/sources", response_model=list[SourceItemResponse], summary="事件关联来源线索", description="获取事件关联的所有来源线索（Source Monitor Agent 采集的原始素材）。")
async def get_event_sources(
    event_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    event = await db.get(EventCase, event_id)
    if not event or event.archived_at:
        raise NotFoundError("事件案卷", str(event_id))
    await _assert_event_visible(db, event, current_user)
    result = await db.execute(
        select(EventSourceItem)
        .where(EventSourceItem.event_case_id == event_id)
        .order_by(EventSourceItem.ingested_at.desc())
    )
    return list(result.scalars().all())


@router.post("/{event_id}/transition", response_model=EventCaseResponse, summary="事件案卷状态迁移", description="通过声明式状态机引擎推进事件状态。合法迁移路径由引擎校验。")
async def transition_event(
    event_id: str,
    req: TransitionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    event = await db.get(EventCase, event_id)
    if not event or event.archived_at:
        raise NotFoundError("事件案卷", str(event_id))
    await _assert_event_visible(db, event, current_user)

    await event_case_engine.attempt_transition(
        obj=event,
        target_state=req.target_state,
        actor=current_user,
        db=db,
    )

    await db.commit()
    await db.refresh(event)
    return event


@router.delete("/{event_id}", response_model=dict, summary="删除事件案卷", description="软删除（归档）事件案卷。")
async def delete_event(
    event_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    event = await db.get(EventCase, event_id)
    if not event:
        raise NotFoundError("事件案卷", str(event_id))
    await _assert_event_visible(db, event, current_user)
    event.archived_at = datetime.utcnow()
    await db.commit()
    return {"message": "已删除", "id": event_id}


@router.post("/{event_id}/restore", response_model=EventCaseResponse, summary="恢复事件案卷", description="恢复已删除的事件案卷。")
async def restore_event(
    event_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    event = await db.get(EventCase, event_id)
    if not event:
        raise NotFoundError("事件案卷", str(event_id))
    await _assert_event_visible(db, event, current_user)
    event.archived_at = None
    await db.commit()
    await db.refresh(event)
    return event
