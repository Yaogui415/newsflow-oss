"""风险/脱敏报告 API：CRUD。"""

import json as _json

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, field_validator
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.errors import NotFoundError
from app.models.channel_package import ChannelPackage
from app.models.event_case import EventCase
from app.models.risk_report import RiskReport
from app.models.story_packet import StoryPacket
from app.models.user import User
from app.api.deps import get_current_user

router = APIRouter()


# ── 请求/响应模型 ──

class RiskReportCreate(BaseModel):
    story_packet_id: str | None = None
    channel_package_id: str | None = None
    report_type: str  # "risk" | "redaction"
    findings: list = []
    severity_summary: dict | None = None
    recommendations: list | None = None
    generated_by: str = "system"  # "system" | "human"


class RiskReportUpdate(BaseModel):
    findings: list | None = None
    severity_summary: dict | None = None
    recommendations: list | None = None
    reviewed_by: str | None = None


class RiskReportResponse(BaseModel):
    id: str
    story_packet_id: str | None
    channel_package_id: str | None
    report_type: str
    version: int
    findings: list
    severity_summary: dict | None = None
    recommendations: list | None = None
    generated_by: str
    reviewed_by: str | None
    created_at: datetime | None

    @field_validator("findings", "recommendations", mode="before")
    @classmethod
    def _parse_list(cls, v):
        if isinstance(v, str):
            try:
                return _json.loads(v)
            except Exception:
                return []
        return v if v is not None else []

    @field_validator("severity_summary", mode="before")
    @classmethod
    def _parse_dict(cls, v):
        if isinstance(v, str):
            try:
                return _json.loads(v)
            except Exception:
                return None
        return v

    model_config = {"from_attributes": True}


class PaginatedRRResponse(BaseModel):
    items: list[RiskReportResponse]
    total: int
    page: int
    page_size: int


async def _get_visibility_scope(db: AsyncSession, current_user: User) -> tuple[list[str], list[str], list[str], list[str]]:
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

    if visible_story_packet_ids:
        visible_channel_package_ids = list((await db.execute(
            select(ChannelPackage.id).where(ChannelPackage.story_packet_id.in_(visible_story_packet_ids))
        )).scalars().all())
    else:
        visible_channel_package_ids = []

    return visible_owner_ids, visible_event_ids, visible_story_packet_ids, visible_channel_package_ids


async def _assert_report_visible(db: AsyncSession, report: RiskReport, current_user: User):
    _, _, visible_story_packet_ids, visible_channel_package_ids = await _get_visibility_scope(db, current_user)
    visible = (
        (report.story_packet_id and report.story_packet_id in visible_story_packet_ids) or
        (report.channel_package_id and report.channel_package_id in visible_channel_package_ids)
    )
    if not visible:
        raise NotFoundError("风险报告", str(report.id))


# ── 端点 ──

@router.get("", response_model=PaginatedRRResponse, summary="风险报告列表")
async def list_risk_reports(
    story_packet_id: str | None = None,
    channel_package_id: str | None = None,
    report_type: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _, _, visible_story_packet_ids, visible_channel_package_ids = await _get_visibility_scope(db, current_user)
    if not visible_story_packet_ids and not visible_channel_package_ids:
        return PaginatedRRResponse(items=[], total=0, page=page, page_size=page_size)

    query = select(RiskReport)
    count_query = select(func.count(RiskReport.id))
    base_visibility = or_(
        RiskReport.story_packet_id.in_(visible_story_packet_ids),
        RiskReport.channel_package_id.in_(visible_channel_package_ids),
    )
    query = query.where(base_visibility)
    count_query = count_query.where(base_visibility)

    if story_packet_id:
        query = query.where(RiskReport.story_packet_id == story_packet_id)
        count_query = count_query.where(RiskReport.story_packet_id == story_packet_id)
    if channel_package_id:
        query = query.where(RiskReport.channel_package_id == channel_package_id)
        count_query = count_query.where(RiskReport.channel_package_id == channel_package_id)
    if report_type:
        query = query.where(RiskReport.report_type == report_type)
        count_query = count_query.where(RiskReport.report_type == report_type)

    total = (await db.execute(count_query)).scalar() or 0
    query = query.order_by(RiskReport.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    items = list(result.scalars().all())

    return PaginatedRRResponse(items=items, total=total, page=page, page_size=page_size)


@router.post("", response_model=RiskReportResponse, summary="创建风险报告")
async def create_risk_report(
    req: RiskReportCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 计算版本号
    count_query = select(func.count(RiskReport.id))
    if req.story_packet_id:
        count_query = count_query.where(
            RiskReport.story_packet_id == req.story_packet_id,
            RiskReport.report_type == req.report_type,
        )
    elif req.channel_package_id:
        count_query = count_query.where(
            RiskReport.channel_package_id == req.channel_package_id,
            RiskReport.report_type == req.report_type,
        )
    existing = (await db.execute(count_query)).scalar() or 0

    report = RiskReport(
        story_packet_id=req.story_packet_id,
        channel_package_id=req.channel_package_id,
        report_type=req.report_type,
        version=existing + 1,
        findings=req.findings,
        severity_summary=req.severity_summary,
        recommendations=req.recommendations,
        generated_by=req.generated_by,
    )
    db.add(report)
    await db.flush()
    await db.refresh(report)
    return report


@router.get("/{report_id}", response_model=RiskReportResponse, summary="风险报告详情")
async def get_risk_report(
    report_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    report = await db.get(RiskReport, report_id)
    if not report:
        raise NotFoundError("风险报告", report_id)
    await _assert_report_visible(db, report, current_user)
    return report


@router.patch("/{report_id}", response_model=RiskReportResponse, summary="更新风险报告")
async def update_risk_report(
    report_id: str,
    req: RiskReportUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    report = await db.get(RiskReport, report_id)
    if not report:
        raise NotFoundError("风险报告", report_id)
    await _assert_report_visible(db, report, current_user)

    for field, value in req.model_dump(exclude_unset=True).items():
        setattr(report, field, value)

    await db.flush()
    await db.refresh(report)
    return report
