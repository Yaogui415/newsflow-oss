"""来源管理 API：线索采集、上传处理。"""

import json
from datetime import datetime

from fastapi import APIRouter, Depends, UploadFile, File, Form
from pydantic import BaseModel, field_validator
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.config import settings
from app.core.errors import NotFoundError
from app.models.event_case import EventCase, EventSourceItem
from app.models.story_packet import StoryPacket
from app.models.user import User
from app.api.deps import get_current_user
from app.services.user_llm_settings import user_llm_settings_service

router = APIRouter()


class SourceItemResponse(BaseModel):
    id: str
    event_case_id: str | None
    source_type: str
    url: str | None
    title: str | None
    raw_content: str | None
    file_ref: str | None
    extracted_5w1h: dict | None
    risk_tags: list
    agent_summary: str | None
    credibility_tier: str | None = None
    credibility_score: float | None = None
    ingested_at: datetime

    @field_validator("risk_tags", mode="before")
    @classmethod
    def _parse_risk_tags(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return []
        return v if v is not None else []

    @field_validator("extracted_5w1h", mode="before")
    @classmethod
    def _parse_5w1h(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return None
        return v

    model_config = {"from_attributes": True}


class ProcessedSourceResponse(BaseModel):
    source_item: SourceItemResponse
    cluster_decision: dict | None = None
    triage_report: dict | None = None


class RSSFeedRequest(BaseModel):
    feed_url: str
    desk: str | None = None


class PaginatedSourceResponse(BaseModel):
    items: list[SourceItemResponse]
    total: int
    page: int
    page_size: int


def _normalize_json_value(value, default):
    if value is None:
        return default
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return default
    return value


def _infer_source_credibility(source_type: str | None, url: str | None, extracted_5w1h: dict | None) -> tuple[str, float]:
    title = str((extracted_5w1h or {}).get("title") or (extracted_5w1h or {}).get("summary") or "").lower()
    link = str(url or "").lower()

    if source_type == "upload":
        return "人工上传", 0.88
    if source_type == "reporter_tip":
        return "记者线索", 0.55
    if source_type == "social_media":
        return "社交媒体", 0.32

    official_markers = ["gov.cn", "court", "法院", "证监会", "上交所", "深交所", "政府", "regulator"]
    mainstream_markers = ["新华社", "人民网", "央视", "财新", "澎湃", "sina", "sohu", "163.com", "thepaper", "xinhuanet"]

    if any(marker in title or marker in link for marker in official_markers):
        return "官方/监管", 0.96
    if any(marker in title or marker in link for marker in mainstream_markers):
        return "主流媒体", 0.82
    if source_type in {"rss", "website"}:
        return "公开网络来源", 0.62
    return "网络来源", 0.45


def _to_source_item_response(item: EventSourceItem) -> SourceItemResponse:
    extracted_5w1h = _normalize_json_value(item.extracted_5w1h, {})
    risk_tags = _normalize_json_value(item.risk_tags, [])
    if not isinstance(extracted_5w1h, dict):
        extracted_5w1h = {}
    if not isinstance(risk_tags, list):
        risk_tags = []

    agent_summary = extracted_5w1h.get("summary") if isinstance(extracted_5w1h, dict) else None
    credibility_tier, credibility_score = _infer_source_credibility(item.source_type, item.url, extracted_5w1h)

    return SourceItemResponse(
        id=item.id,
        event_case_id=item.event_case_id,
        source_type=item.source_type,
        url=item.url,
        title=extracted_5w1h.get("title") if isinstance(extracted_5w1h, dict) else None,
        raw_content=item.raw_content,
        file_ref=item.file_ref,
        extracted_5w1h=extracted_5w1h,
        risk_tags=risk_tags,
        agent_summary=agent_summary,
        credibility_tier=credibility_tier,
        credibility_score=credibility_score,
        ingested_at=item.ingested_at,
    )


async def _get_visibility_scope(db: AsyncSession, current_user: User) -> tuple[list[str], list[str], list[str]]:
    if current_user.org_id:
        visible_owner_ids = list((await db.execute(
            select(User.id).where(User.org_id == current_user.org_id)
        )).scalars().all())
        if not visible_owner_ids:
            visible_owner_ids = [current_user.id]
    else:
        visible_owner_ids = [current_user.id]

    visible_event_ids = list((await db.execute(
        select(EventCase.id).where(EventCase.owner_id.in_(visible_owner_ids))
    )).scalars().all())

    visible_story_packet_ids = list((await db.execute(
        select(StoryPacket.id).where(
            (StoryPacket.owner_id.in_(visible_owner_ids)) |
            (StoryPacket.event_case_id.in_(visible_event_ids))
        )
    )).scalars().all())

    return visible_owner_ids, visible_event_ids, visible_story_packet_ids


async def _assert_event_visible(db: AsyncSession, event: EventCase, current_user: User):
    _, visible_event_ids, _ = await _get_visibility_scope(db, current_user)
    if event.id not in visible_event_ids:
        raise NotFoundError("事件案卷", str(event.id))


async def _assert_story_packet_visible(db: AsyncSession, packet: StoryPacket, current_user: User):
    _, _, visible_story_packet_ids = await _get_visibility_scope(db, current_user)
    if packet.id not in visible_story_packet_ids:
        raise NotFoundError("报道任务包", str(packet.id))


async def _assert_source_visible(db: AsyncSession, item: EventSourceItem, current_user: User):
    _, visible_event_ids, _ = await _get_visibility_scope(db, current_user)
    if item.event_case_id not in visible_event_ids:
        raise NotFoundError("素材", str(item.id))


async def _resolve_event_case_id(
    db: AsyncSession,
    current_user: User,
    event_case_id: str | None,
    story_packet_id: str | None,
    desk: str | None,
    fallback_title: str,
    fallback_summary: str,
) -> str:
    packet = None
    if story_packet_id:
        packet = await db.get(StoryPacket, story_packet_id)
        if not packet:
            raise NotFoundError("报道任务包", str(story_packet_id))
        await _assert_story_packet_visible(db, packet, current_user)

    if event_case_id:
        event = await db.get(EventCase, event_case_id)
        if not event or event.archived_at:
            raise NotFoundError("事件案卷", str(event_case_id))
        await _assert_event_visible(db, event, current_user)
        if packet and not packet.event_case_id:
            packet.event_case_id = event.id
        return event.id

    if packet and packet.event_case_id:
        event = await db.get(EventCase, packet.event_case_id)
        if not event or event.archived_at:
            raise NotFoundError("事件案卷", str(packet.event_case_id))
        await _assert_event_visible(db, event, current_user)
        return event.id

    auto_event = EventCase(
        title=packet.title if packet else fallback_title,
        summary=fallback_summary,
        status="candidate",
        risk_level="L0",
        desk=desk or (packet.desk if packet else None),
        owner_id=current_user.id,
    )
    db.add(auto_event)
    await db.flush()
    if packet and not packet.event_case_id:
        packet.event_case_id = auto_event.id
    return auto_event.id


async def _apply_user_llm_key(db: AsyncSession, user_id: str) -> None:
    from app.agents.source_monitor import source_monitor_agent

    setting = await user_llm_settings_service.get_user_setting(db, user_id=user_id, include_raw_key=True)
    key = setting.get("api_key") or settings.OPENAI_API_KEY
    if not key:
        return

    if hasattr(source_monitor_agent, "llm") and hasattr(source_monitor_agent.llm, "api_key"):
        source_monitor_agent.llm.api_key = key


@router.post("/upload", response_model=ProcessedSourceResponse, summary="上传文件采集")
async def upload_source(
    file: UploadFile = File(...),
    event_case_id: str | None = Form(None),
    story_packet_id: str | None = Form(None),
    desk: str = Form(None),
    reporter_note: str = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """上传文件并处理：PDF/DOCX/图片/文本"""
    await _apply_user_llm_key(db, current_user.id)

    content = await file.read()
    
    # 采集处理（带容错：Agent 不可用时仍保存原始记录）
    from app.agents.source_monitor import source_monitor_agent
    import logging as _logging

    source_item = None
    agent_error = None
    try:
        raw_item = await source_monitor_agent.collect_from_upload(
            file_content=content,
            filename=file.filename,
            metadata={"desk": desk, "reporter_note": reporter_note, "uploader": current_user.id}
        )
        source_item = await source_monitor_agent.process(raw_item)
    except Exception as e:
        agent_error = str(e)
        _logging.getLogger(__name__).warning("Agent 处理上传失败，将保存原始记录: %s", agent_error)

    resolved_event_case_id = await _resolve_event_case_id(
        db=db,
        current_user=current_user,
        event_case_id=event_case_id,
        story_packet_id=story_packet_id,
        desk=desk,
        fallback_title=f"素材导入：{file.filename}",
        fallback_summary=reporter_note or "由上传素材自动创建",
    )
    
    # 存入数据库
    if source_item:
        db_item = EventSourceItem(
            event_case_id=resolved_event_case_id,
            source_type=source_item.source_type,
            url=source_item.url,
            raw_content=source_item.content[:10000] if source_item.content else None,
            extracted_5w1h=source_item.extracted_5w1h,
            file_ref=source_item.file_ref,
            risk_tags=source_item.risk_tags,
        )
    else:
        db_item = EventSourceItem(
            event_case_id=resolved_event_case_id,
            source_type="upload",
            url=None,
            raw_content=content.decode("utf-8", errors="replace")[:10000] if content else None,
            extracted_5w1h={},
            file_ref=file.filename,
            risk_tags=[],
        )
    db.add(db_item)
    await db.flush()
    await db.refresh(db_item)
    
    return ProcessedSourceResponse(
        source_item=_to_source_item_response(db_item),
    )


@router.post("/rss", response_model=list[dict], summary="从RSS源采集")
async def collect_from_rss(
    req: RSSFeedRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """从指定RSS源采集线索"""
    await _apply_user_llm_key(db, current_user.id)

    from app.agents.source_monitor import source_monitor_agent

    raw_items = await source_monitor_agent.collect_from_rss(req.feed_url)
    
    results = []
    for raw_item in raw_items[:10]:  # 限制单次处理数量
        source_item = await source_monitor_agent.process(raw_item)
        results.append(source_item.to_dict())
    
    return results


@router.post("/manual", response_model=ProcessedSourceResponse, summary="手动提交线索")
async def submit_manual_source(
    event_case_id: str = Form(None),
    story_packet_id: str | None = Form(None),
    url: str = Form(None),
    content: str = Form(...),
    title: str = Form(None),
    desk: str = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """手动粘贴内容提交线索"""
    await _apply_user_llm_key(db, current_user.id)

    from app.agents.source_monitor import source_monitor_agent, RawSourceItem

    raw_item = RawSourceItem(
        source_type="reporter_tip",
        url=url,
        raw_content=content,
        metadata={"title": title, "desk": desk, "submitter": current_user.id}
    )
    
    source_item = await source_monitor_agent.process(raw_item)

    resolved_event_case_id = await _resolve_event_case_id(
        db=db,
        current_user=current_user,
        event_case_id=event_case_id,
        story_packet_id=story_packet_id,
        desk=desk,
        fallback_title=title or "手动提交线索",
        fallback_summary=(content[:120] if content else "由手动线索提交自动创建"),
    )
    
    # 存入数据库
    db_item = EventSourceItem(
        event_case_id=resolved_event_case_id,
        source_type=source_item.source_type,
        url=source_item.url,
        raw_content=source_item.content[:10000] if source_item.content else None,
        extracted_5w1h=source_item.extracted_5w1h,
        risk_tags=source_item.risk_tags,
    )
    db.add(db_item)
    await db.flush()
    await db.refresh(db_item)
    
    return ProcessedSourceResponse(
        source_item=_to_source_item_response(db_item),
    )


@router.get("/items", response_model=PaginatedSourceResponse, summary="素材列表")
async def list_source_items(
    page: int = 1,
    page_size: int = 20,
    event_case_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _, visible_event_ids, _ = await _get_visibility_scope(db, current_user)
    if not visible_event_ids:
        return PaginatedSourceResponse(items=[], total=0, page=page, page_size=page_size)

    query = select(EventSourceItem)
    count_query = select(func.count(EventSourceItem.id))
    query = query.where(EventSourceItem.event_case_id.in_(visible_event_ids))
    count_query = count_query.where(EventSourceItem.event_case_id.in_(visible_event_ids))

    if event_case_id:
        query = query.where(EventSourceItem.event_case_id == event_case_id)
        count_query = count_query.where(EventSourceItem.event_case_id == event_case_id)

    total = (await db.execute(count_query)).scalar() or 0
    query = query.order_by(EventSourceItem.ingested_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    items = list(result.scalars().all())

    return PaginatedSourceResponse(
        items=[_to_source_item_response(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/items/{source_item_id}", response_model=SourceItemResponse, summary="素材详情")
async def get_source_item(
    source_item_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = await db.get(EventSourceItem, source_item_id)
    if not item:
        raise NotFoundError("素材", str(source_item_id))
    await _assert_source_visible(db, item, current_user)
    return _to_source_item_response(item)
