"""种子数据 API：一键生成真实演示数据，解决空数据库问题。"""

import uuid
import json
import traceback
import logging
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from app.core.config import settings
from app.core.database import get_db
from app.core.security import hash_password
from app.models.user import User
from app.models.event_case import EventCase, EventSourceItem
from app.models.story_packet import StoryPacket
from app.models.claim_card import ClaimCard
from app.models.draft_version import DraftVersion
from app.models.evidence_pack import EvidencePack
from app.models.review_bundle import ReviewBundle
from app.models.approval_task import ApprovalTask
from app.models.risk_report import RiskReport
from app.models.channel_package import ChannelPackage
from app.models.audit_log import AuditLog
from app.models.decision_log import DecisionLog
from app.models.correction_ticket import CorrectionTicket
from app.models.organization import Organization

router = APIRouter()


def _now():
    return datetime.utcnow()


def _ago(hours=0, minutes=0):
    return _now() - timedelta(hours=hours, minutes=minutes)


@router.post("/seed/ai-generate", summary="AI生成真实事件种子数据")
async def ai_generate_seed(db: AsyncSession = Depends(get_db)):
    """调用 LLM 生成基于真实近期事件的种子数据。需要配置 LLM API Key。"""
    if not settings.DEBUG:
        return JSONResponse(status_code=403, content={"message": "仅开发环境可用"})

    api_key = settings.OPENAI_API_KEY
    if not api_key:
        return JSONResponse(status_code=400, content={"message": "请先配置 OPENAI_API_KEY"})

    try:
        return await _ai_seed_impl(db)
    except Exception as exc:
        logger.error(f"AI seed generation failed: {exc}")
        logger.error(traceback.format_exc())
        await db.rollback()
        return JSONResponse(status_code=500, content={"message": f"AI种子数据生成失败: {str(exc)}"})


async def _ai_seed_impl(db: AsyncSession):
    from langchain_openai import ChatOpenAI

    llm = ChatOpenAI(
        model=settings.LLM_MODEL,
        api_key=settings.OPENAI_API_KEY,
        base_url=settings.OPENAI_BASE_URL or None,
        temperature=0.7,
    )

    prompt = """你是一个新闻编辑部的AI助手。请生成3个基于真实近期热点的新闻事件种子数据，用于新闻生产管理系统的演示。

每个事件必须包含：
1. title: 事件标题（真实、具体）
2. summary: 事件摘要（50-100字）
3. risk_level: 风险等级 (L0/L1/L2/L3)
4. desk: 新闻条线 (财经/时政/社会/科技/国际)
5. region: 地区
6. tags: 标签数组
7. sources: 2-3个来源素材，每个含 source_type(rss/website/social_media/reporter_tip), url(可为null), content(原始内容50-100字), extracted_5w1h(who/what/when/where/why/how)
8. claims: 3-4个事实声明(claim_text), 含 risk_level, confidence_score(0-1), status(supported/disputed/insufficient)
9. story_packet: 一个报道任务包，含 title, content_type(in_depth/breaking/explainer), lead(导语), body(正文200-400字)
10. evidence_sources: 2-3个证据来源，含 type, title, source, credibility(权威官方/权威媒体/社交媒体/人工上传), url(可为null)
11. risk_findings: 1-2个风险发现，含 severity(L0-L3), category, description, suggestion

请选择当前中国社会关注的真实热点话题（如经济政策、科技发展、社会民生、环境问题等），数据要有真实感。

严格输出 JSON 数组格式，不要有其他文字：
[{event1}, {event2}, {event3}]"""

    resp = await llm.ainvoke(prompt)
    raw = resp.content.strip()
    # Strip markdown code fences (```json ... ``` or ``` ... ```)
    if raw.startswith("```"):
        first_newline = raw.find("\n")
        raw = raw[first_newline + 1:] if first_newline != -1 else raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3].strip()
    # Fallback: extract JSON array via regex
    try:
        events_data = json.loads(raw)
    except json.JSONDecodeError:
        import re
        match = re.search(r'\[[\s\S]*\]', raw)
        if match:
            events_data = json.loads(match.group())
        else:
            raise ValueError(f"LLM 返回内容无法解析为 JSON 数组: {raw[:200]}...")

    # Ensure users exist
    zhang = (await db.execute(select(User).where(User.username == "zhangzhubian"))).scalar_one_or_none()
    zhao = (await db.execute(select(User).where(User.username == "zhaojizhe"))).scalar_one_or_none()
    wang = (await db.execute(select(User).where(User.username == "wangjizhe"))).scalar_one_or_none()
    liu = (await db.execute(select(User).where(User.username == "liujizhe"))).scalar_one_or_none()

    if not zhang:
        return JSONResponse(status_code=400, content={"message": "请先运行基础种子数据 POST /seed"})

    owner_pool = [u for u in [zhang, zhao, wang, liu] if u]
    created_events = []
    created_packets = []
    created_claims_count = 0
    created_sources_count = 0

    for idx, ev in enumerate(events_data):
        owner = owner_pool[idx % len(owner_pool)]

        event = EventCase(
            title=ev.get("title", f"AI生成事件 {idx+1}"),
            summary=ev.get("summary", ""),
            status="active",
            risk_level=ev.get("risk_level", "L1"),
            desk=ev.get("desk", "财经"),
            region=ev.get("region", "全国"),
            tags=ev.get("tags", []),
            owner_id=owner.id,
            start_time=_ago(hours=idx * 12 + 6),
            created_at=_ago(hours=idx * 12 + 6),
            updated_at=_now(),
        )
        db.add(event)
        await db.flush()
        await db.refresh(event)
        created_events.append(event)

        # Sources
        for s in ev.get("sources", []):
            si = EventSourceItem(
                event_case_id=event.id,
                source_type=s.get("source_type", "rss"),
                url=s.get("url"),
                raw_content=s.get("content", ""),
                extracted_5w1h=s.get("extracted_5w1h", {}),
                risk_tags=s.get("risk_tags", []),
                ingested_at=_ago(hours=idx * 12 + 4),
            )
            db.add(si)
            created_sources_count += 1

        # Story Packet
        sp_data = ev.get("story_packet", {})
        packet = StoryPacket(
            event_case_id=event.id,
            title=sp_data.get("title", event.title + " 深度报道"),
            content_type=sp_data.get("content_type", "in_depth"),
            status="researching",
            risk_level=ev.get("risk_level", "L1"),
            owner_id=owner.id,
            desk=ev.get("desk", "财经"),
            deadline=_now() + timedelta(hours=24),
            created_at=_ago(hours=idx * 12 + 2),
            updated_at=_now(),
        )
        db.add(packet)
        await db.flush()
        await db.refresh(packet)
        created_packets.append(packet)

        # Draft
        draft = DraftVersion(
            story_packet_id=packet.id,
            version=1,
            title=sp_data.get("title", packet.title),
            lead=sp_data.get("lead", ""),
            body=sp_data.get("body", ""),
            word_count=len(sp_data.get("body", "")),
            created_by=owner.id,
            created_at=_ago(hours=idx * 12 + 1),
        )
        db.add(draft)

        # Claims
        for c in ev.get("claims", []):
            claim = ClaimCard(
                story_packet_id=packet.id,
                claim_text=c.get("claim_text", ""),
                risk_level=c.get("risk_level", "L0"),
                status=c.get("status", "supported"),
                confidence_score=c.get("confidence_score", 0.8),
                supporting_evidence=[],
                contradicting_evidence=[],
                missing_evidence=[],
            )
            db.add(claim)
            created_claims_count += 1

        # Evidence Pack
        ep_sources = []
        for es in ev.get("evidence_sources", []):
            ep_sources.append({
                "type": es.get("type", "公开数据"),
                "title": es.get("title", ""),
                "source": es.get("source", ""),
                "credibility": es.get("credibility", "网络来源"),
                "url": es.get("url"),
            })
        if ep_sources:
            ep = EvidencePack(
                story_packet_id=packet.id,
                version=1,
                sources=ep_sources,
                citation_anchors=[],
                completeness_score=0.65,
                created_by=owner.id,
            )
            db.add(ep)

        # Risk Report
        findings = []
        for rf in ev.get("risk_findings", []):
            findings.append({
                "severity": rf.get("severity", "L1"),
                "category": rf.get("category", "内容风险"),
                "description": rf.get("description", ""),
                "suggestion": rf.get("suggestion", ""),
            })
        if findings:
            rr = RiskReport(
                story_packet_id=packet.id,
                report_type="risk",
                version=1,
                findings=findings,
                severity_summary={"L3": 0, "L2": 0, "L1": len(findings), "L0": 0, "total": len(findings)},
                recommendations=[f.get("suggestion", "") for f in findings if f.get("suggestion")],
                generated_by="ai_seed",
                created_at=_now(),
            )
            db.add(rr)

        # Timeline
        event.timeline_data = [
            {"time": _ago(hours=idx * 12 + 6).isoformat(), "event": "AI采集发现事件线索", "actor": "Source Monitor Agent"},
            {"time": _ago(hours=idx * 12 + 5).isoformat(), "event": "自动分诊", "actor": "Triage Agent"},
            {"time": _ago(hours=idx * 12 + 4).isoformat(), "event": "线索聚合为事件", "actor": "Dedup & Cluster Agent"},
            {"time": _ago(hours=idx * 12 + 2).isoformat(), "event": "创建报道任务包", "actor": owner.display_name or owner.username},
            {"time": _ago(hours=idx * 12 + 1).isoformat(), "event": "AI生成初稿", "actor": "Drafting Agent"},
        ]

    await db.flush()
    await db.commit()

    return {
        "message": "AI种子数据生成成功",
        "seeded": True,
        "ai_generated": True,
        "stats": {
            "events": len(created_events),
            "story_packets": len(created_packets),
            "claim_cards": created_claims_count,
            "source_items": created_sources_count,
            "evidence_packs": len(created_events),
            "risk_reports": len(created_events),
        },
        "events": [{"id": e.id, "title": e.title} for e in created_events],
    }


@router.post("/seed-upgrade", summary="升级种子数据（补充组织和版本历史）")
async def seed_upgrade(db: AsyncSession = Depends(get_db)):
    """为已有种子数据补充组织关联和额外草稿版本。"""
    if not settings.DEBUG:
        return JSONResponse(status_code=403, content={"message": "仅开发环境可用"})
    try:
        upgraded = {}

        # 1. 创建组织（如不存在）
        existing_org = await db.execute(select(Organization).where(Organization.name == "newsflow_demo_org"))
        demo_org = existing_org.scalar_one_or_none()
        if not demo_org:
            zhang = (await db.execute(select(User).where(User.username == "zhangzhubian"))).scalar_one_or_none()
            if zhang:
                demo_org = Organization(
                    name="newsflow_demo_org",
                    display_name="NewsFlow 新闻编辑部",
                    description="AI驱动的新闻生产全流程管理演示团队",
                    owner_id=zhang.id,
                    invite_code="DEMO2025",
                    max_members=50,
                )
                db.add(demo_org)
                await db.flush()
                await db.refresh(demo_org)
                upgraded["org_created"] = True

        # 2. 关联所有用户到组织
        if demo_org:
            users = (await db.execute(select(User).where(User.org_id == None))).scalars().all()  # noqa: E711
            for u in users:
                u.org_id = demo_org.id
            upgraded["users_linked"] = len(users)

        # 3. 为并购深度稿补充版本历史 v1, v2
        first_packet = (await db.execute(
            select(StoryPacket).where(StoryPacket.title.contains("并购争议深度"))
        )).scalar_one_or_none()
        if first_packet:
            existing_versions = (await db.execute(
                select(func.count(DraftVersion.id)).where(DraftVersion.story_packet_id == first_packet.id)
            )).scalar() or 0
            if existing_versions < 3:
                zhao = (await db.execute(select(User).where(User.username == "zhaojizhe"))).scalar_one_or_none()
                if zhao:
                    v1 = DraftVersion(
                        story_packet_id=first_packet.id, version=1,
                        title="XX科技集团收购YY公司事件报道",
                        lead="XX科技集团宣布以82亿元收购YY公司，市场关注交易定价合理性。",
                        body="XX科技集团近日发布公告，拟以不超过82亿元收购YY公司100%股权。\n\nYY公司主要从事半导体芯片设计业务，2024年营业收入约15亿元。",
                        word_count=85, created_by=zhao.id, created_at=_ago(hours=48),
                    )
                    v2 = DraftVersion(
                        story_packet_id=first_packet.id, version=2,
                        title="某科技集团并购争议：关联交易疑云",
                        lead="XX科技集团82亿元收购案中，收购方与标的公司之间被发现存在未披露的关联关系。",
                        body="XX科技集团宣布以不超过82亿元收购YY公司100%股权，但本报记者调查发现，XX科技实控人张某与YY公司董事李某之间存在复杂的股权关联。\n\n工商登记资料显示，张某通过两家离岸公司间接持有YY公司供应商股权。\n\n市场人士对此交易的定价合理性提出质疑，并购溢价率约30%。",
                        word_count=142, created_by=zhao.id, created_at=_ago(hours=30),
                    )
                    db.add_all([v1, v2])
                    upgraded["draft_versions_added"] = 2

        await db.flush()
        await db.commit()
        return {"message": "种子数据升级成功", "upgraded": upgraded}
    except Exception as exc:
        logger.error(f"Seed upgrade failed: {exc}")
        logger.error(traceback.format_exc())
        await db.rollback()
        return JSONResponse(status_code=500, content={"message": f"升级失败: {str(exc)}"})


@router.post("/seed", summary="生成种子数据（仅开发环境）")
async def seed_demo_data(db: AsyncSession = Depends(get_db)):
    """生成真实演示数据，包括用户、事件案卷、报道任务包、Claim Cards、审批任务等。
    仅在 DEBUG=True 时可用，生产环境返回 403。
    """
    if not settings.DEBUG:
        return JSONResponse(
            status_code=403,
            content={
                "message": "种子数据接口仅在开发环境可用（DEBUG=True）",
                "seeded": False,
            },
        )
    try:
        return await _seed_impl(db)
    except Exception as exc:
        logger.error(f"Seed data generation failed: {exc}")
        logger.error(traceback.format_exc())
        await db.rollback()
        return JSONResponse(
            status_code=500,
            content={
                "message": f"种子数据生成失败: {str(exc)}",
                "seeded": False,
                "error_detail": str(exc),
            },
        )


async def _seed_impl(db: AsyncSession):
    # 检查是否已有数据
    existing_events = await db.scalar(select(func.count(EventCase.id)))
    if existing_events and existing_events > 0:
        return {"message": "数据库已有数据，跳过种子数据生成", "seeded": False}

    # ── 1. 创建用户 ──
    users_data = [
        {"username": "zhangzhubian", "display_name": "张主编", "email": "zhang@newsflow.com",
         "roles": ["chief_editor", "admin"], "desk": "财经"},
        {"username": "lizhangbian", "display_name": "李编辑", "email": "li@newsflow.com",
         "roles": ["desk_editor"], "desk": "财经"},
        {"username": "wangjizhe", "display_name": "王记者", "email": "wang@newsflow.com",
         "roles": ["reporter"], "desk": "时政"},
        {"username": "zhaojizhe", "display_name": "赵记者", "email": "zhao@newsflow.com",
         "roles": ["reporter"], "desk": "财经"},
        {"username": "liujizhe", "display_name": "刘记者", "email": "liu@newsflow.com",
         "roles": ["reporter"], "desk": "社会"},
        {"username": "chenfengkong", "display_name": "陈风控", "email": "chen@newsflow.com",
         "roles": ["compliance_editor"], "desk": None},
    ]

    user_map = {}
    for u in users_data:
        existing = await db.execute(select(User).where(User.username == u["username"]))
        user = existing.scalar_one_or_none()
        if not user:
            user = User(
                username=u["username"],
                display_name=u["display_name"],
                email=u["email"],
                hashed_password=hash_password("newsflow123"),
                roles=u["roles"],
                desk=u["desk"],
            )
            db.add(user)
            await db.flush()
            await db.refresh(user)
        user_map[u["username"]] = user

    zhang = user_map["zhangzhubian"]
    li = user_map["lizhangbian"]
    wang = user_map["wangjizhe"]
    zhao = user_map["zhaojizhe"]
    liu = user_map["liujizhe"]
    chen = user_map["chenfengkong"]

    # ── 1b. 创建演示组织并关联用户 ──
    existing_org = await db.execute(select(Organization).where(Organization.name == "newsflow_demo_org"))
    demo_org = existing_org.scalar_one_or_none()
    if not demo_org:
        demo_org = Organization(
            name="newsflow_demo_org",
            display_name="NewsFlow 新闻编辑部",
            description="AI驱动的新闻生产全流程管理演示团队，覆盖财经、时政、社会、科技等多个新闻条线。",
            owner_id=zhang.id,
            invite_code="DEMO2025",
            max_members=50,
        )
        db.add(demo_org)
        await db.flush()
        await db.refresh(demo_org)

    # 将所有演示用户关联到该组织
    for u in user_map.values():
        u.org_id = demo_org.id
    await db.flush()

    # ── 2. 创建事件案卷 ──
    events_data = [
        {
            "title": "某科技集团并购争议案",
            "summary": "关于XX科技集团收购YY公司的系列报道，涉及利益冲突和监管问题。多家媒体跟进，监管部门已介入初步调查。",
            "status": "active",
            "risk_level": "L3",
            "desk": "财经",
            "region": "全国",
            "tags": ["调查", "匿名源", "并购"],
            "owner": zhang,
            "start_time": _ago(hours=72),
        },
        {
            "title": "省级审计报告数据解读",
            "summary": "某省2025年度审计报告公布，揭示多项财政违规问题，涉及教育、医疗等民生领域资金使用不当。",
            "status": "active",
            "risk_level": "L1",
            "desk": "时政",
            "region": "华东",
            "tags": ["数据", "解读"],
            "owner": wang,
            "start_time": _ago(hours=48),
        },
        {
            "title": "城市内涝舆情后续跟进",
            "summary": "近期暴雨导致多城市严重内涝，市民安全受到威胁。舆论关注城市排水系统建设问题。",
            "status": "monitoring",
            "risk_level": "L2",
            "desk": "社会",
            "region": "华南",
            "tags": ["跟进", "民生"],
            "owner": liu,
            "start_time": _ago(hours=120),
        },
        {
            "title": "新能源汽车补贴政策解读",
            "summary": "国务院发布新一轮新能源汽车补贴调整方案，行业格局面临重大变化。",
            "status": "monitoring",
            "risk_level": "L0",
            "desk": "财经",
            "region": "全国",
            "tags": ["政策", "解释性"],
            "owner": zhao,
            "start_time": _ago(hours=168),
        },
        {
            "title": "跨境电商税收新规影响分析",
            "summary": "海关总署发布跨境电商进口税收新规，预计影响数百万中小卖家。",
            "status": "active",
            "risk_level": "L1",
            "desk": "财经",
            "region": "全国",
            "tags": ["政策", "财经"],
            "owner": zhao,
            "start_time": _ago(hours=24),
        },
        {
            "title": "AI芯片出口管制升级",
            "summary": "美国商务部宣布扩大AI芯片出口管制范围，中国半导体产业链面临新挑战。",
            "status": "triaging",
            "risk_level": "L2",
            "desk": "科技",
            "region": "全球",
            "tags": ["国际", "科技"],
            "owner": zhang,
            "start_time": _ago(hours=6),
        },
        {
            "title": "医保基金监管专项行动",
            "summary": "国家医保局启动新一轮医保基金监管专项行动，重点查处欺诈骗保行为。",
            "status": "active",
            "risk_level": "L1",
            "desk": "社会",
            "region": "全国",
            "tags": ["民生", "监管"],
            "owner": liu,
            "start_time": _ago(hours=36),
        },
        {
            "title": "上市公司财报季异常波动",
            "summary": "A股多家上市公司发布业绩预警，市场关注财务真实性问题。",
            "status": "candidate",
            "risk_level": "L0",
            "desk": "财经",
            "region": "全国",
            "tags": ["财经", "数据"],
            "owner": None,
            "start_time": _ago(hours=2),
        },
    ]

    event_objects = []
    for e in events_data:
        event = EventCase(
            title=e["title"],
            summary=e["summary"],
            status=e["status"],
            risk_level=e["risk_level"],
            desk=e["desk"],
            region=e["region"],
            tags=e["tags"],
            owner_id=e["owner"].id if e["owner"] else None,
            start_time=e["start_time"],
            created_at=e["start_time"],
            updated_at=_ago(minutes=10 + len(event_objects) * 15),
        )
        db.add(event)
        await db.flush()
        await db.refresh(event)
        event_objects.append(event)

    ev_binggou = event_objects[0]
    ev_shenji = event_objects[1]
    ev_neilao = event_objects[2]
    ev_xinnengyuan = event_objects[3]
    ev_kuajing = event_objects[4]
    ev_chip = event_objects[5]
    ev_yibao = event_objects[6]
    ev_caibao = event_objects[7]

    # ── 3. 创建 Story Packets ──
    packets_data = [
        # 并购案 - 3个任务包
        {
            "event": ev_binggou, "title": "某科技集团并购争议深度稿",
            "content_type": "in_depth", "status": "risk_review",
            "risk_level": "L3", "owner": zhao, "desk": "财经",
            "deadline": _now() + timedelta(hours=4),
        },
        {
            "event": ev_binggou, "title": "并购案快讯稿",
            "content_type": "breaking", "status": "published",
            "risk_level": "L1", "owner": wang, "desk": "财经",
            "deadline": None,
        },
        {
            "event": ev_binggou, "title": "并购案视频解读脚本",
            "content_type": "video_script", "status": "drafting",
            "risk_level": "L2", "owner": zhao, "desk": "财经",
            "deadline": _now() + timedelta(hours=8),
        },
        # 审计报告 - 2个任务包
        {
            "event": ev_shenji, "title": "省级审计报告数据解读",
            "content_type": "explainer", "status": "editorial_review",
            "risk_level": "L1", "owner": wang, "desk": "时政",
            "deadline": _now() + timedelta(hours=6),
        },
        {
            "event": ev_shenji, "title": "审计报告快讯",
            "content_type": "breaking", "status": "published",
            "risk_level": "L0", "owner": wang, "desk": "时政",
            "deadline": None,
        },
        # 内涝 - 3个任务包（深度报道已进入发布后监测）
        {
            "event": ev_neilao, "title": "城市内涝深度报道",
            "content_type": "in_depth", "status": "monitoring",
            "risk_level": "L2", "owner": liu, "desk": "社会",
            "deadline": None,
        },
        {
            "event": ev_neilao, "title": "内涝跟进：排水系统调查",
            "content_type": "in_depth", "status": "published",
            "risk_level": "L1", "owner": liu, "desk": "社会",
            "deadline": None,
        },
        {
            "event": ev_neilao, "title": "内涝快讯",
            "content_type": "breaking", "status": "published",
            "risk_level": "L0", "owner": liu, "desk": "社会",
            "deadline": None,
        },
        # 新能源 - 2个已发布
        {
            "event": ev_xinnengyuan, "title": "新能源汽车补贴政策解读稿",
            "content_type": "explainer", "status": "published",
            "risk_level": "L0", "owner": zhao, "desk": "财经",
            "deadline": None,
        },
        {
            "event": ev_xinnengyuan, "title": "补贴政策快讯",
            "content_type": "breaking", "status": "published",
            "risk_level": "L0", "owner": zhao, "desk": "财经",
            "deadline": None,
        },
        # 跨境电商 - 1个进行中
        {
            "event": ev_kuajing, "title": "跨境电商税收新规深度分析",
            "content_type": "in_depth", "status": "researching",
            "risk_level": "L1", "owner": zhao, "desk": "财经",
            "deadline": _now() + timedelta(hours=12),
        },
        # AI芯片 - 1个刚创建
        {
            "event": ev_chip, "title": "AI芯片出口管制影响评估",
            "content_type": "in_depth", "status": "created",
            "risk_level": "L2", "owner": zhang, "desk": "科技",
            "deadline": _now() + timedelta(hours=24),
        },
        # 医保基金 - 2个任务包
        {
            "event": ev_yibao, "title": "医保基金监管专项行动深度报道",
            "content_type": "in_depth", "status": "researching",
            "risk_level": "L1", "owner": liu, "desk": "社会",
            "deadline": _now() + timedelta(hours=18),
        },
        {
            "event": ev_yibao, "title": "医保骗保典型案例快讯",
            "content_type": "breaking", "status": "drafting",
            "risk_level": "L1", "owner": liu, "desk": "社会",
            "deadline": _now() + timedelta(hours=6),
        },
        # 上市公司财报 - 1个候选
        {
            "event": ev_caibao, "title": "A股财报季异常波动分析",
            "content_type": "explainer", "status": "created",
            "risk_level": "L0", "owner": zhao, "desk": "财经",
            "deadline": _now() + timedelta(hours=48),
        },
    ]

    packet_objects = []
    for p in packets_data:
        packet = StoryPacket(
            event_case_id=p["event"].id,
            title=p["title"],
            content_type=p["content_type"],
            status=p["status"],
            risk_level=p["risk_level"],
            owner_id=p["owner"].id,
            desk=p["desk"],
            deadline=p["deadline"],
            created_at=_ago(hours=48 + len(packet_objects) * 3),
            updated_at=_ago(minutes=5 + len(packet_objects) * 10),
        )
        db.add(packet)
        await db.flush()
        await db.refresh(packet)
        packet_objects.append(packet)

    sp_binggou_depth = packet_objects[0]
    sp_shenji = packet_objects[3]

    # ── 4. Claim Cards（为并购深度稿和审计稿创建） ──
    claims_binggou = [
        {"text": "并购金额约 82 亿元人民币", "risk": "L0", "status": "supported", "conf": 0.94,
         "support": [{"title": "公司并购公告原文", "source": "上交所"}], "contra": [], "missing": []},
        {"text": "标的公司主要资产分布于三省", "risk": "L0", "status": "supported", "conf": 0.88,
         "support": [{"title": "工商登记资料", "source": "国家企业信用信息公示系统"}], "contra": [], "missing": []},
        {"text": "实控人存在关联交易", "risk": "L3", "status": "disputed", "conf": 0.45,
         "support": [{"title": "知情人士证言", "source": "独家采访"}],
         "contra": [{"title": "公司声明", "source": "公司公告"}], "missing": []},
        {"text": "并购溢价率约30%", "risk": "L0", "status": "supported", "conf": 0.91,
         "support": [{"title": "公告数据", "source": "上交所"}], "contra": [], "missing": []},
        {"text": "涉及内幕交易嫌疑", "risk": "L3", "status": "insufficient", "conf": 0.32,
         "support": [], "contra": [], "missing": [{"title": "监管调查结果", "source": "证监会"}]},
        {"text": "监管部门已介入调查", "risk": "L2", "status": "supported", "conf": 0.76,
         "support": [{"title": "官方消息", "source": "证监会网站"}], "contra": [], "missing": []},
    ]

    for c in claims_binggou:
        claim = ClaimCard(
            story_packet_id=sp_binggou_depth.id,
            claim_text=c["text"],
            risk_level=c["risk"],
            status=c["status"],
            confidence_score=c["conf"],
            supporting_evidence=c["support"],
            contradicting_evidence=c["contra"],
            missing_evidence=c["missing"],
        )
        db.add(claim)

    claims_shenji = [
        {"text": "审计发现违规资金使用金额达 5.2 亿元", "risk": "L1", "status": "supported", "conf": 0.92},
        {"text": "涉及 12 个地市级单位", "risk": "L0", "status": "supported", "conf": 0.95},
        {"text": "教育领域资金挪用最为严重", "risk": "L1", "status": "supported", "conf": 0.87},
        {"text": "部分资金流向已查明", "risk": "L0", "status": "supported", "conf": 0.78},
    ]

    for c in claims_shenji:
        claim = ClaimCard(
            story_packet_id=sp_shenji.id,
            claim_text=c["text"],
            risk_level=c["risk"],
            status=c["status"],
            confidence_score=c["conf"],
            supporting_evidence=[],
            contradicting_evidence=[],
            missing_evidence=[],
        )
        db.add(claim)

    # ── 5. Draft Versions ──
    # 并购深度稿 v1 - AI 初稿
    draft_v1 = DraftVersion(
        story_packet_id=sp_binggou_depth.id,
        version=1,
        title="XX科技集团收购YY公司事件报道",
        lead="XX科技集团宣布以82亿元收购YY公司，市场关注交易定价合理性。",
        body="XX科技集团近日发布公告，拟以不超过82亿元收购YY公司100%股权。\n\n"
             "YY公司主要从事半导体芯片设计业务，2024年营业收入约15亿元。"
             "本次交易构成重大资产重组，需经股东大会审议。",
        word_count=85,
        created_by=zhao.id,
        created_at=_ago(hours=48),
    )
    db.add(draft_v1)

    # 并购深度稿 v2 - 记者补充调查内容
    draft_v2 = DraftVersion(
        story_packet_id=sp_binggou_depth.id,
        version=2,
        title="某科技集团并购争议：关联交易疑云",
        lead="XX科技集团82亿元收购案中，收购方与标的公司之间被发现存在未披露的关联关系。",
        body="XX科技集团宣布以不超过82亿元收购YY公司100%股权，但本报记者调查发现，"
             "XX科技实控人张某与YY公司董事李某之间存在复杂的股权关联。\n\n"
             "工商登记资料显示，张某通过两家离岸公司间接持有YY公司供应商股权。"
             "这一关联关系在并购公告中并未充分披露。\n\n"
             "市场人士对此交易的定价合理性提出质疑，并购溢价率约30%。",
        word_count=142,
        created_by=zhao.id,
        created_at=_ago(hours=30),
    )
    db.add(draft_v2)

    # 并购深度稿 v3 - 当前版本（加入监管信息）
    draft1 = DraftVersion(
        story_packet_id=sp_binggou_depth.id,
        version=3,
        title="某科技集团并购争议深度调查",
        lead="知情人士透露，XX科技集团在此次并购交易中存在多项未披露的关联交易，涉及金额高达数十亿元。",
        body="根据工商登记资料显示，YY科技的实际控制人张某，与XX集团董事会成员李某存在多层股权关联。"
             "这一关联关系在并购公告中并未充分披露。\n\n"
             "本报记者获取的内部文件显示，并购交易中涉及至少三家关联公司的资金往来，"
             "交易结构较为复杂。监管部门已于上周启动初步调查程序。\n\n"
             "一位接近监管层的人士表示，目前调查重点集中在并购定价合理性和信息披露完整性两个方面。"
             "该交易涉及金额约82亿元人民币，溢价率约30%。",
        word_count=186,
        created_by=zhao.id,
        created_at=_ago(hours=6),
    )
    db.add(draft1)

    draft2 = DraftVersion(
        story_packet_id=sp_shenji.id,
        version=1,
        title="省级审计报告揭示多项财政违规",
        lead="某省2025年度审计报告正式公布，揭示涉及教育、医疗等民生领域的多项资金使用违规问题。",
        body="审计结果显示，全省共发现违规资金使用金额达5.2亿元，涉及12个地市级单位。\n\n"
             "其中，教育领域资金挪用问题最为突出，占违规总额的38%。"
             "部分地区将教育专项经费用于非教育目的的基础设施建设。",
        word_count=98,
        created_by=wang.id,
    )
    db.add(draft2)

    # ── 6. Review Bundles + Approval Tasks ──
    # 并购深度稿 - 风险审核中
    bundle1 = ReviewBundle(
        story_packet_id=sp_binggou_depth.id,
        bundle_type="risk",
        bundle_hash="sha256_demo_hash_binggou_risk",
        status="active",
        submitted_by=zhao.id,
        submit_note="并购深度稿提交风险审核",
        created_at=_ago(hours=2),
    )
    db.add(bundle1)
    await db.flush()
    await db.refresh(bundle1)

    task1 = ApprovalTask(
        review_bundle_id=bundle1.id,
        approval_stage="risk_review",
        status="pending",
        signer_slots=[
            {"user_id": chen.id, "role": "compliance_editor", "status": "pending"},
            {"user_id": zhang.id, "role": "chief_editor", "status": "pending"},
        ],
        execution_mode="sequential",
        sla_deadline=_now() - timedelta(minutes=12),  # 已超时
        created_at=_ago(hours=2),
    )
    db.add(task1)

    # 审计稿 - 编辑审核中
    bundle2 = ReviewBundle(
        story_packet_id=sp_shenji.id,
        bundle_type="editorial",
        bundle_hash="sha256_demo_hash_shenji_editorial",
        status="active",
        submitted_by=wang.id,
        submit_note="审计解读稿提交编辑审核",
        created_at=_ago(hours=1),
    )
    db.add(bundle2)
    await db.flush()
    await db.refresh(bundle2)

    task2 = ApprovalTask(
        review_bundle_id=bundle2.id,
        approval_stage="editorial_review",
        status="pending",
        signer_slots=[
            {"user_id": li.id, "role": "desk_editor", "status": "pending"},
        ],
        execution_mode="sequential",
        sla_deadline=_now() + timedelta(hours=1, minutes=22),
        created_at=_ago(hours=1),
    )
    db.add(task2)

    # 新能源稿 - 最终签发
    bundle3 = ReviewBundle(
        story_packet_id=packet_objects[8].id,  # 新能源解读稿
        bundle_type="final",
        bundle_hash="sha256_demo_hash_xinnengyuan_final",
        status="active",
        submitted_by=zhao.id,
        submit_note="新能源解读稿提交最终签发",
        created_at=_ago(minutes=30),
    )
    db.add(bundle3)
    await db.flush()
    await db.refresh(bundle3)

    task3 = ApprovalTask(
        review_bundle_id=bundle3.id,
        approval_stage="final_review",
        status="pending",
        signer_slots=[
            {"user_id": zhang.id, "role": "chief_editor", "status": "pending"},
        ],
        execution_mode="sequential",
        sla_deadline=_now() + timedelta(hours=3, minutes=10),
        created_at=_ago(minutes=30),
    )
    db.add(task3)

    # ── 7. Event Source Items（展示 Source Monitor Agent 采集的原始线索） ──
    source_items_data = [
        # 并购案 - 多来源
        {"event": ev_binggou, "source_type": "rss", "url": "https://finance.sina.com.cn/stock/s/2025-03-28/doc-xxxxxx.shtml",
         "raw_content": "XX科技集团宣布以约82亿元收购YY公司100%股权，交易预计在二季度完成。",
         "extracted_5w1h": {"who": "XX科技集团", "what": "收购YY公司", "when": "2025年Q2", "where": "上海", "why": "战略扩张", "how": "现金+股票"},
         "risk_tags": ["上市公司", "大额交易"], "time_offset": 72},
        {"event": ev_binggou, "source_type": "website", "url": "https://www.sse.com.cn/disclosure/xxxx",
         "raw_content": "上交所公告：XX科技（600XXX）关于重大资产重组的提示性公告。并购标的YY公司主要从事半导体设计业务。",
         "extracted_5w1h": {"who": "XX科技", "what": "重大资产重组公告", "when": "2025-03-27", "where": "上交所", "why": "信息披露", "how": "公告形式"},
         "risk_tags": ["监管公告", "半导体"], "time_offset": 70},
        {"event": ev_binggou, "source_type": "reporter_tip", "url": None,
         "raw_content": "知情人士透露，XX科技实控人张某与YY公司董事李某存在未披露的股权关联，涉及三家离岸公司。",
         "extracted_5w1h": {"who": "张某、李某", "what": "未披露关联交易", "when": "近期", "where": "不详", "why": "利益输送嫌疑", "how": "离岸公司"},
         "risk_tags": ["匿名源", "关联交易", "L3风险"], "time_offset": 48},
        {"event": ev_binggou, "source_type": "social_media", "url": "https://weibo.com/xxxxx",
         "raw_content": "#XX科技并购# 有股民发现XX科技在公告前一周异常放量，疑似内幕交易。@证监会 请关注",
         "extracted_5w1h": {"who": "股民", "what": "质疑内幕交易", "when": "公告前一周", "where": "微博", "why": "异常放量", "how": "社交媒体举报"},
         "risk_tags": ["舆情", "内幕交易嫌疑"], "time_offset": 36},
        # 审计报告
        {"event": ev_shenji, "source_type": "rss", "url": "https://www.audit.gov.cn/xxxx",
         "raw_content": "某省审计厅发布2025年度审计工作报告，揭示违规资金使用5.2亿元，涉及12个地市级单位。",
         "extracted_5w1h": {"who": "某省审计厅", "what": "发布审计报告", "when": "2025年3月", "where": "某省", "why": "年度审计", "how": "审计报告"},
         "risk_tags": ["政府公开数据"], "time_offset": 48},
        {"event": ev_shenji, "source_type": "upload", "url": None,
         "raw_content": "[PDF] 某省2025年度审计工作报告全文（共128页），含详细数据表格和案例分析。",
         "extracted_5w1h": {"who": "审计厅", "what": "完整审计报告", "when": "2025", "where": "某省", "why": "数据支撑", "how": "PDF文档"},
         "risk_tags": ["原始文档"], "time_offset": 46},
        # 内涝
        {"event": ev_neilao, "source_type": "rss", "url": "https://news.qq.com/xxxxx",
         "raw_content": "华南多城遭遇特大暴雨，广州、深圳部分区域内涝严重，交通瘫痪。",
         "extracted_5w1h": {"who": "华南多城市民", "what": "严重内涝", "when": "近日", "where": "广州、深圳", "why": "特大暴雨", "how": "排水系统超负荷"},
         "risk_tags": ["民生", "紧急"], "time_offset": 120},
        # 医保基金
        {"event": ev_yibao, "source_type": "rss", "url": "https://www.nhsa.gov.cn/xxxxx",
         "raw_content": "国家医保局通报：2025年一季度查处欺诈骗保案件1847起，追回医保基金3.2亿元。",
         "extracted_5w1h": {"who": "国家医保局", "what": "通报骗保案件查处情况", "when": "2025年Q1", "where": "全国", "why": "专项行动", "how": "行政处罚+司法移送"},
         "risk_tags": ["政府数据", "民生"], "time_offset": 36},
        {"event": ev_yibao, "source_type": "website", "url": "https://www.thepaper.cn/xxxxx",
         "raw_content": "澎湃新闻调查：某三甲医院通过虚假住院、分解收费等方式骗取医保基金超2000万元。",
         "extracted_5w1h": {"who": "某三甲医院", "what": "骗取医保基金", "when": "2024-2025", "where": "某省会城市", "why": "利益驱动", "how": "虚假住院、分解收费"},
         "risk_tags": ["调查报道", "骗保"], "time_offset": 30},
        # 跨境电商
        {"event": ev_kuajing, "source_type": "rss", "url": "https://www.customs.gov.cn/xxxxx",
         "raw_content": "海关总署公告2025年第XX号：关于调整跨境电商零售进口商品清单及税率的公告。",
         "extracted_5w1h": {"who": "海关总署", "what": "调整跨境电商税率", "when": "2025-04-01起", "where": "全国", "why": "规范行业", "how": "调整税率和清单"},
         "risk_tags": ["政策文件"], "time_offset": 24},
        # AI芯片
        {"event": ev_chip, "source_type": "rss", "url": "https://www.reuters.com/technology/xxxxx",
         "raw_content": "U.S. Commerce Department expands AI chip export controls, adding new restrictions on advanced GPU sales to China.",
         "extracted_5w1h": {"who": "美国商务部", "what": "扩大AI芯片出口管制", "when": "2025-03-30", "where": "美国", "why": "国家安全", "how": "出口管制条例"},
         "risk_tags": ["国际", "敏感"], "time_offset": 6},
        {"event": ev_chip, "source_type": "rss", "url": "https://www.miit.gov.cn/xxxxx",
         "raw_content": "工信部回应芯片出口管制：中国半导体产业具备自主可控能力，将加大研发投入。",
         "extracted_5w1h": {"who": "工信部", "what": "回应芯片管制", "when": "2025-03-30", "where": "北京", "why": "官方回应", "how": "新闻发布会"},
         "risk_tags": ["官方回应", "政策"], "time_offset": 4},
    ]

    for s in source_items_data:
        si = EventSourceItem(
            event_case_id=s["event"].id,
            source_type=s["source_type"],
            url=s["url"],
            raw_content=s["raw_content"],
            extracted_5w1h=s["extracted_5w1h"],
            risk_tags=s["risk_tags"],
            ingested_at=_ago(hours=s["time_offset"]),
        )
        db.add(si)

    # ── 8. Evidence Packs（展示证据结构化 Agent 输出） ──
    ep_binggou = EvidencePack(
        story_packet_id=sp_binggou_depth.id,
        version=2,
        sources=[
            {"type": "公告", "title": "XX科技重大资产重组提示性公告", "source": "上交所", "credibility": "high", "url": "https://www.sse.com.cn/disclosure/xxxx"},
            {"type": "采访", "title": "知情人士证言（匿名）", "source": "独家采访", "credibility": "medium", "protection_level": "confidential"},
            {"type": "公开数据", "title": "工商登记资料", "source": "国家企业信用信息公示系统", "credibility": "high", "url": "https://www.gsxt.gov.cn"},
            {"type": "社交媒体", "title": "股民举报异常交易", "source": "微博", "credibility": "low", "needs_verification": True},
        ],
        citation_anchors=[
            {"claim_index": 0, "source_index": 0, "anchor_text": "并购金额约82亿元"},
            {"claim_index": 2, "source_index": 1, "anchor_text": "实控人存在关联交易"},
            {"claim_index": 5, "source_index": 0, "anchor_text": "监管部门已介入调查"},
        ],
        completeness_score=0.72,
        created_by=zhao.id,
    )
    db.add(ep_binggou)

    ep_shenji = EvidencePack(
        story_packet_id=sp_shenji.id,
        version=1,
        sources=[
            {"type": "官方文件", "title": "某省2025年度审计工作报告", "source": "审计厅官网", "credibility": "high"},
            {"type": "数据", "title": "违规资金明细表", "source": "审计报告附件", "credibility": "high"},
        ],
        citation_anchors=[
            {"claim_index": 0, "source_index": 0, "anchor_text": "违规资金5.2亿元"},
            {"claim_index": 1, "source_index": 1, "anchor_text": "涉及12个地市级单位"},
        ],
        completeness_score=0.88,
        created_by=wang.id,
    )
    db.add(ep_shenji)

    # ── 9. Risk Reports（展示 Redaction & Risk Agent 输出） ──
    rr_binggou = RiskReport(
        story_packet_id=sp_binggou_depth.id,
        report_type="risk",
        version=1,
        findings=[
            {"severity": "L3", "category": "法律风险", "description": "文中涉及'内幕交易嫌疑'表述，尚无监管定性结论，存在名誉权诉讼风险",
             "suggestion": "建议改为'市场质疑异常交易行为'并注明'截至发稿，监管部门尚未发布调查结论'"},
            {"severity": "L2", "category": "信源保护", "description": "'知情人士'引用涉及具体交易细节，信源可被推断识别",
             "suggestion": "模糊化处理，避免提及具体离岸公司数量等可识别信息"},
            {"severity": "L1", "category": "数据准确", "description": "并购溢价率30%需交叉验证",
             "suggestion": "补充对标交易溢价率区间，增加背景说明"},
        ],
        severity_summary={"L3": 1, "L2": 1, "L1": 1, "L0": 0, "total": 3},
        recommendations=["建议增加公司回应", "建议增加独立分析师评论", "法律条款引用需审慎"],
        generated_by="agent",
        created_at=_ago(hours=3),
    )
    db.add(rr_binggou)

    rr_shenji = RiskReport(
        story_packet_id=sp_shenji.id,
        report_type="risk",
        version=1,
        findings=[
            {"severity": "L1", "category": "数据引用", "description": "审计报告数据引用准确，但需注明数据截止时间",
             "suggestion": "补充'数据截至2024年12月31日'"},
        ],
        severity_summary={"L3": 0, "L2": 0, "L1": 1, "L0": 0, "total": 1},
        recommendations=["建议补充地方政府回应"],
        generated_by="agent",
        created_at=_ago(hours=2),
    )
    db.add(rr_shenji)

    # ── 10. Channel Packages（展示已发布稿件的多渠道适配） ──
    await db.flush()
    # 先获取内涝深度稿的 draft
    neilao_draft = DraftVersion(
        story_packet_id=packet_objects[5].id,  # 内涝深度
        version=2,
        title="城市内涝深度调查：排水系统欠账谁来买单？",
        lead="连续暴雨致华南多城严重内涝，暴露城市排水基础设施建设长期欠账问题。",
        body="记者实地调查发现，广州市某区排水管网设计标准仍沿用上世纪90年代标准...（全文约2800字）",
        word_count=2800,
        created_by=liu.id,
    )
    db.add(neilao_draft)
    await db.flush()
    await db.refresh(neilao_draft)

    cp_wechat = ChannelPackage(
        story_packet_id=packet_objects[5].id,
        source_draft_id=neilao_draft.id,
        channel_type="wechat_mp",
        status="published",
        content={"title": "暴雨后的城市之痛：排水系统欠账谁来买单？", "summary": "连续暴雨致多城内涝，记者深入调查城市排水困局",
                 "cover_image": "auto_generated", "word_count": 2500, "reading_time_min": 8},
        drift_score=0.08,
        platform_rules_check={"title_length": "pass", "content_length": "pass", "sensitive_words": "pass"},
        published_at=_ago(hours=96),
        published_url="https://mp.weixin.qq.com/s/xxxxx",
        owner_id=liu.id,
        created_at=_ago(hours=100),
    )
    db.add(cp_wechat)

    cp_app = ChannelPackage(
        story_packet_id=packet_objects[5].id,
        source_draft_id=neilao_draft.id,
        channel_type="app_push",
        status="published",
        content={"title": "深度 | 城市内涝深度调查", "push_summary": "暴雨后的城市之痛",
                 "word_count": 2800, "has_video": False, "has_infographic": True},
        drift_score=0.05,
        platform_rules_check={"push_title_length": "pass", "content_check": "pass"},
        published_at=_ago(hours=95),
        owner_id=liu.id,
        created_at=_ago(hours=100),
    )
    db.add(cp_app)

    cp_weibo = ChannelPackage(
        story_packet_id=packet_objects[5].id,
        source_draft_id=neilao_draft.id,
        channel_type="weibo",
        status="published",
        content={"title": "#城市内涝调查# 暴雨后的城市之痛", "text": "连续暴雨致华南多城严重内涝。记者实地调查发现...",
                 "char_count": 140, "has_images": True, "image_count": 3},
        drift_score=0.15,
        platform_rules_check={"char_limit": "pass", "hashtag": "pass"},
        published_at=_ago(hours=95),
        owner_id=liu.id,
        created_at=_ago(hours=100),
    )
    db.add(cp_weibo)

    # ── 11. Decision Logs（展示已完成的签发决策记录） ──
    # 为内涝深度稿创建已完成的审批记录
    bundle_neilao = ReviewBundle(
        story_packet_id=packet_objects[5].id,
        bundle_type="final",
        bundle_hash="sha256_demo_hash_neilao_final",
        status="completed",
        submitted_by=liu.id,
        submit_note="内涝深度稿提交最终签发",
        created_at=_ago(hours=102),
    )
    db.add(bundle_neilao)
    await db.flush()
    await db.refresh(bundle_neilao)

    task_neilao = ApprovalTask(
        review_bundle_id=bundle_neilao.id,
        approval_stage="final_review",
        status="completed",
        signer_slots=[
            {"user_id": zhang.id, "role": "chief_editor", "status": "approved"},
        ],
        execution_mode="sequential",
        sla_deadline=_ago(hours=100),
        created_at=_ago(hours=102),
    )
    db.add(task_neilao)
    await db.flush()
    await db.refresh(task_neilao)

    dl_neilao = DecisionLog(
        approval_task_id=task_neilao.id,
        review_bundle_id=bundle_neilao.id,
        signer_id=zhang.id,
        signer_role="chief_editor",
        action="approve",
        decision_reason="事实充分、逻辑清晰，可发布。",
        created_at=_ago(hours=100),
    )
    db.add(dl_neilao)

    # ── 12. Audit Logs（DB 审计轨迹） ──
    audit_entries = [
        {"actor_type": "agent", "action": "source_ingestion", "object_type": "event_source_item", "object_id": ev_binggou.id,
         "details": {"agent_name": "Source Monitor", "source_type": "rss", "url": "https://finance.sina.com.cn/stock/s/2025-03-28/doc-xxxxxx.shtml", "summary": "采集到XX科技并购公告相关新闻"},
         "time_offset": 72},
        {"actor_type": "agent", "action": "source_ingestion", "object_type": "event_source_item", "object_id": ev_binggou.id,
         "details": {"agent_name": "Source Monitor", "source_type": "website", "summary": "采集到上交所并购公告原文"},
         "time_offset": 70},
        {"actor_type": "agent", "action": "dedup_cluster", "object_type": "event_case", "object_id": ev_binggou.id,
         "details": {"agent_name": "Dedup & Cluster", "merged_count": 3, "cluster_id": "cluster_binggou_001", "summary": "将3条相关线索聚合为并购争议事件簇"},
         "ai_model": "gpt-4o-mini", "tokens": {"input": 1200, "output": 350}, "time_offset": 69},
        {"actor_type": "agent", "action": "triage", "object_type": "event_case", "object_id": ev_binggou.id,
         "details": {"agent_name": "Triage Agent", "risk_level": "L3", "recommended_desk": "财经", "priority": "urgent", "summary": "自动分诊：L3高风险，涉及上市公司关联交易，建议财经组跟进"},
         "ai_model": "gpt-4o-mini", "tokens": {"input": 800, "output": 200}, "time_offset": 68},
        {"actor_type": "agent", "action": "evidence_structuring", "object_type": "evidence_pack", "object_id": sp_binggou_depth.id,
         "details": {"agent_name": "证据结构化", "sources_processed": 4, "claims_generated": 6, "summary": "从4条来源中提取6个核心事实声明，生成证据包v2"},
         "ai_model": "gpt-4o", "tokens": {"input": 3500, "output": 1800}, "time_offset": 48},
        {"actor_type": "agent", "action": "verification", "object_type": "claim_card", "object_id": sp_binggou_depth.id,
         "details": {"agent_name": "核验 Agent", "claims_verified": 6, "supported": 3, "disputed": 1, "insufficient": 1, "summary": "完成6项事实核验：3项有充分支撑，1项存在争议，1项证据不足"},
         "ai_model": "gpt-4o", "tokens": {"input": 4200, "output": 2100}, "time_offset": 44},
        {"actor_type": "agent", "action": "relationship_map", "object_type": "event_case", "object_id": ev_binggou.id,
         "details": {"agent_name": "关系调查", "entities_found": 8, "relationships_found": 12, "key_finding": "发现实控人张某与标的公司董事李某通过3家离岸公司存在关联", "summary": "绘制实体关系图谱，发现8个关键实体和12条关系链"},
         "ai_model": "gpt-4o", "tokens": {"input": 2800, "output": 1500}, "time_offset": 42},
        {"actor_type": "agent", "action": "drafting", "object_type": "draft_version", "object_id": sp_binggou_depth.id,
         "details": {"agent_name": "Drafting", "version": 3, "word_count": 186, "summary": "基于证据包和Claim Cards生成深度调查稿v3"},
         "ai_model": "gpt-4o", "tokens": {"input": 5000, "output": 3200}, "time_offset": 24},
        {"actor_type": "agent", "action": "risk_scan", "object_type": "risk_report", "object_id": sp_binggou_depth.id,
         "details": {"agent_name": "Redaction & Risk", "findings_count": 3, "max_severity": "L3", "summary": "发现3项风险：1项L3法律风险、1项L2信源保护、1项L1数据准确性问题"},
         "ai_model": "gpt-4o", "tokens": {"input": 3000, "output": 1200}, "time_offset": 12},
        # 审计稿相关
        {"actor_type": "agent", "action": "source_ingestion", "object_type": "event_source_item", "object_id": ev_shenji.id,
         "details": {"agent_name": "Source Monitor", "source_type": "rss", "summary": "采集到省级审计报告发布消息"},
         "time_offset": 48},
        {"actor_type": "agent", "action": "triage", "object_type": "event_case", "object_id": ev_shenji.id,
         "details": {"agent_name": "Triage Agent", "risk_level": "L1", "recommended_desk": "时政", "summary": "自动分诊：L1中低风险，政府公开数据解读，建议时政组跟进"},
         "ai_model": "gpt-4o-mini", "tokens": {"input": 600, "output": 150}, "time_offset": 47},
        {"actor_type": "agent", "action": "evidence_structuring", "object_type": "evidence_pack", "object_id": sp_shenji.id,
         "details": {"agent_name": "证据结构化", "sources_processed": 2, "claims_generated": 4, "summary": "从审计报告中提取4个核心数据点"},
         "ai_model": "gpt-4o-mini", "tokens": {"input": 2000, "output": 800}, "time_offset": 36},
        # 内涝 - 已完成全链路
        {"actor_type": "agent", "action": "source_ingestion", "object_type": "event_source_item", "object_id": ev_neilao.id,
         "details": {"agent_name": "Source Monitor", "source_type": "rss", "summary": "采集到华南暴雨内涝相关新闻"},
         "time_offset": 120},
        {"actor_type": "agent", "action": "dedup_cluster", "object_type": "event_case", "object_id": ev_neilao.id,
         "details": {"agent_name": "Dedup & Cluster", "merged_count": 4, "summary": "将4条暴雨与城市内涝线索聚合为持续跟进事件"},
         "ai_model": "gpt-4o-mini", "tokens": {"input": 900, "output": 220}, "time_offset": 119},
        {"actor_type": "agent", "action": "triage", "object_type": "event_case", "object_id": ev_neilao.id,
         "details": {"agent_name": "Triage Agent", "risk_level": "L2", "recommended_desk": "社会", "summary": "自动分诊：L2中高风险，涉及公共安全与民生，建议社会组持续跟进"},
         "ai_model": "gpt-4o-mini", "tokens": {"input": 760, "output": 190}, "time_offset": 118},
        {"actor_type": "agent", "action": "evidence_structuring", "object_type": "evidence_pack", "object_id": packet_objects[5].id,
         "details": {"agent_name": "证据结构化", "sources_processed": 5, "claims_generated": 7, "summary": "从多地通报、积水数据和现场图片中整理7条核心事实"},
         "ai_model": "gpt-4o-mini", "tokens": {"input": 2600, "output": 1100}, "time_offset": 112},
        {"actor_type": "agent", "action": "verification", "object_type": "claim_card", "object_id": packet_objects[5].id,
         "details": {"agent_name": "核验 Agent", "claims_verified": 7, "supported": 6, "disputed": 1, "summary": "完成7项事实核验，其中6项有充分支撑，1项需持续跟进"},
         "ai_model": "gpt-4o-mini", "tokens": {"input": 2800, "output": 1200}, "time_offset": 108},
        {"actor_type": "agent", "action": "drafting", "object_type": "draft_version", "object_id": packet_objects[5].id,
         "details": {"agent_name": "Drafting", "version": 4, "word_count": 1680, "summary": "基于证据包和核验结果生成内涝深度稿终版"},
         "ai_model": "gpt-4o", "tokens": {"input": 4200, "output": 2400}, "time_offset": 104},
        {"actor_type": "agent", "action": "risk_scan", "object_type": "risk_report", "object_id": packet_objects[5].id,
         "details": {"agent_name": "Redaction & Risk", "findings_count": 1, "max_severity": "L1", "summary": "完成风险扫描，仅保留1项措辞级提醒，已修订"},
         "ai_model": "gpt-4o-mini", "tokens": {"input": 2100, "output": 760}, "time_offset": 102},
        {"actor_type": "agent", "action": "channel_adapt", "object_type": "channel_package", "object_id": packet_objects[5].id,
         "details": {"agent_name": "Channel Adapt", "channels": ["wechat_mp", "app_push", "weibo"], "summary": "为内涝深度稿生成3个渠道版本（微信公众号、APP推送、微博）"},
         "ai_model": "gpt-4o-mini", "tokens": {"input": 2500, "output": 1800}, "time_offset": 101},
        {"actor_type": "agent", "action": "post_monitor", "object_type": "story_packet", "object_id": packet_objects[5].id,
         "details": {"agent_name": "Post Monitor", "status": "monitoring", "engagement": {"views": 128000, "shares": 3200, "comments": 890}, "sentiment": "mostly_neutral", "factcheck_alerts": 0, "summary": "发布后监测：12.8万阅读、3200转发，未发现事实争议"},
         "time_offset": 72},
        # 新能源 - 已发布并持续监测
        {"actor_type": "agent", "action": "source_ingestion", "object_type": "event_source_item", "object_id": ev_xinnengyuan.id,
         "details": {"agent_name": "Source Monitor", "source_type": "rss", "summary": "采集到新能源汽车补贴政策调整新闻与政策原文"},
         "time_offset": 168},
        {"actor_type": "agent", "action": "dedup_cluster", "object_type": "event_case", "object_id": ev_xinnengyuan.id,
         "details": {"agent_name": "Dedup & Cluster", "merged_count": 3, "summary": "将政策解读、行业点评和部委通报聚合为统一事件"},
         "ai_model": "gpt-4o-mini", "tokens": {"input": 640, "output": 150}, "time_offset": 167},
        {"actor_type": "agent", "action": "triage", "object_type": "event_case", "object_id": ev_xinnengyuan.id,
         "details": {"agent_name": "Triage Agent", "risk_level": "L0", "recommended_desk": "财经", "summary": "自动分诊：L0低风险，适合解释性与快讯双稿并行"},
         "ai_model": "gpt-4o-mini", "tokens": {"input": 520, "output": 120}, "time_offset": 166},
        {"actor_type": "agent", "action": "evidence_structuring", "object_type": "evidence_pack", "object_id": packet_objects[8].id,
         "details": {"agent_name": "证据结构化", "sources_processed": 3, "claims_generated": 5, "summary": "从政策条文、部委答记者问和行业数据中整理5条关键事实"},
         "ai_model": "gpt-4o-mini", "tokens": {"input": 1900, "output": 820}, "time_offset": 164},
        {"actor_type": "agent", "action": "drafting", "object_type": "draft_version", "object_id": packet_objects[8].id,
         "details": {"agent_name": "Drafting", "version": 2, "word_count": 1120, "summary": "生成新能源汽车补贴政策解读稿终版"},
         "ai_model": "gpt-4o", "tokens": {"input": 2600, "output": 1500}, "time_offset": 160},
        {"actor_type": "agent", "action": "channel_adapt", "object_type": "channel_package", "object_id": packet_objects[8].id,
         "details": {"agent_name": "Channel Adapt", "channels": ["wechat_mp", "app_push"], "summary": "为新能源政策解读稿生成公众号与APP推送版本"},
         "ai_model": "gpt-4o-mini", "tokens": {"input": 1800, "output": 960}, "time_offset": 156},
        {"actor_type": "agent", "action": "post_monitor", "object_type": "story_packet", "object_id": packet_objects[8].id,
         "details": {"agent_name": "Post Monitor", "status": "monitoring", "engagement": {"views": 86000, "shares": 1900, "comments": 420}, "sentiment": "positive", "factcheck_alerts": 0, "summary": "发布后监测：传播稳定，用户关注补贴对象与退坡节奏"},
         "time_offset": 150},
        # AI芯片 - 刚开始
        {"actor_type": "agent", "action": "source_ingestion", "object_type": "event_source_item", "object_id": ev_chip.id,
         "details": {"agent_name": "Source Monitor", "source_type": "rss", "source_count": 2, "summary": "采集到2条AI芯片出口管制相关线索（路透社+工信部）"},
         "time_offset": 6},
        {"actor_type": "agent", "action": "dedup_cluster", "object_type": "event_case", "object_id": ev_chip.id,
         "details": {"agent_name": "Dedup & Cluster", "merged_count": 2, "summary": "将2条线索聚合为AI芯片管制事件"},
         "ai_model": "gpt-4o-mini", "tokens": {"input": 500, "output": 120}, "time_offset": 5},
        {"actor_type": "agent", "action": "triage", "object_type": "event_case", "object_id": ev_chip.id,
         "details": {"agent_name": "Triage Agent", "risk_level": "L2", "recommended_desk": "科技", "summary": "自动分诊：L2中高风险，涉及国际敏感话题，建议科技组跟进"},
         "ai_model": "gpt-4o-mini", "tokens": {"input": 700, "output": 180}, "time_offset": 4},
    ]

    for a in audit_entries:
        log = AuditLog(
            actor_type=a["actor_type"],
            action=a["action"],
            object_type=a["object_type"],
            object_id=a["object_id"],
            details=a["details"],
            ai_model=a.get("ai_model"),
            ai_token_usage=a.get("tokens"),
            created_at=_ago(hours=a["time_offset"]),
        )
        db.add(log)

    # ── 13. 填充 audit_agent 内存日志（Dashboard Agent Activity 展示用） ──
    from app.agents.audit import audit_agent, AuditEntry as AE
    for a in audit_entries:
        entry = AE(
            timestamp=_ago(hours=a["time_offset"]),
            actor_type=a["actor_type"],
            action=a["action"],
            object_type=a["object_type"],
            object_id=a["object_id"],
            details=a["details"],
            ai_model=a.get("ai_model"),
            ai_token_usage=a.get("tokens"),
        )
        audit_agent._audit_logs.append(entry)

    # ── 14. 添加实体关系图谱数据 ──
    ev_binggou.entity_graph_ref = json.dumps({
        "nodes": [
            {"id": "n1", "label": "XX科技集团", "type": "company", "role": "收购方", "risk": "L3"},
            {"id": "n2", "label": "YY公司", "type": "company", "role": "标的公司", "risk": "L1"},
            {"id": "n3", "label": "张某（实控人）", "type": "person", "role": "XX科技实控人", "risk": "L3"},
            {"id": "n4", "label": "李某（董事）", "type": "person", "role": "YY公司董事", "risk": "L2"},
            {"id": "n5", "label": "Alpha Holdings Ltd", "type": "offshore", "role": "离岸公司A", "risk": "L3"},
            {"id": "n6", "label": "Beta Ventures Ltd", "type": "offshore", "role": "离岸公司B", "risk": "L3"},
            {"id": "n7", "label": "Gamma Capital Ltd", "type": "offshore", "role": "离岸公司C", "risk": "L2"},
            {"id": "n8", "label": "证监会", "type": "regulator", "role": "监管机构", "risk": "L0"},
        ],
        "edges": [
            {"source": "n3", "target": "n1", "label": "实际控制", "type": "control"},
            {"source": "n4", "target": "n2", "label": "担任董事", "type": "position"},
            {"source": "n1", "target": "n2", "label": "收购（82亿元）", "type": "transaction"},
            {"source": "n3", "target": "n5", "label": "持股70%", "type": "ownership"},
            {"source": "n3", "target": "n6", "label": "持股100%", "type": "ownership"},
            {"source": "n4", "target": "n6", "label": "持股30%（隐名）", "type": "hidden_ownership"},
            {"source": "n4", "target": "n7", "label": "持股60%", "type": "ownership"},
            {"source": "n5", "target": "n7", "label": "关联交易", "type": "transaction"},
            {"source": "n6", "target": "n2", "label": "供应商关系", "type": "business"},
            {"source": "n8", "target": "n1", "label": "立案调查", "type": "regulation"},
            {"source": "n8", "target": "n3", "label": "关注", "type": "regulation"},
            {"source": "n5", "target": "n6", "label": "资金往来", "type": "fund_flow"},
        ],
        "summary": "关系调查 Agent 发现：XX科技实控人张某与YY公司董事李某通过3家离岸公司存在未披露的股权关联。其中 Beta Ventures Ltd 同时由张某和李某持有，涉嫌关联交易利益输送。",
        "key_findings": [
            "张某通过 Alpha Holdings 和 Beta Ventures 间接持有 YY 公司供应商股权",
            "李某在 Beta Ventures 持有30%隐名股权，未在并购公告中披露",
            "Alpha Holdings 与 Gamma Capital 之间存在异常资金往来",
            "证监会已对XX科技立案调查",
        ],
    }, ensure_ascii=False)

    ev_neilao.entity_graph_ref = json.dumps({
        "nodes": [
            {"id": "n1", "label": "广州市水务局", "type": "gov", "role": "主管部门", "risk": "L1"},
            {"id": "n2", "label": "深圳市水务局", "type": "gov", "role": "主管部门", "risk": "L1"},
            {"id": "n3", "label": "XX排水工程公司", "type": "company", "role": "承建商", "risk": "L2"},
            {"id": "n4", "label": "YY市政设计院", "type": "company", "role": "设计单位", "risk": "L1"},
            {"id": "n5", "label": "某区住建局", "type": "gov", "role": "属地管理", "risk": "L2"},
            {"id": "n6", "label": "受灾居民", "type": "group", "role": "利益相关方", "risk": "L0"},
        ],
        "edges": [
            {"source": "n1", "target": "n3", "label": "招标委托", "type": "contract"},
            {"source": "n4", "target": "n3", "label": "设计方案", "type": "business"},
            {"source": "n5", "target": "n3", "label": "监管验收", "type": "regulation"},
            {"source": "n3", "target": "n6", "label": "工程影响", "type": "impact"},
            {"source": "n1", "target": "n5", "label": "行政管辖", "type": "hierarchy"},
        ],
        "summary": "城市排水基础设施涉及多个政府部门和承建商，设计标准沿用90年代旧标准。",
    }, ensure_ascii=False)

    # ── 15. Correction Tickets（勘误记录） ──
    # 内涝深度报道 - 已关闭勘误
    ct_neilao = CorrectionTicket(
        story_packet_id=packet_objects[5].id,
        event_case_id=ev_neilao.id,
        source_publish_id=cp_wechat.id,
        trigger_reason="读者反馈：文中提到'广州市某区排水管网设计标准沿用上世纪90年代标准'，实际该区2018年已完成部分管网升级改造，表述不够准确。",
        impact_scope="微信公众号版本、APP版本",
        proposed_fix="修改为'广州市某区部分老城区排水管网仍沿用上世纪90年代设计标准，尽管2018年已启动部分升级改造，但覆盖率不足40%'",
        status="corrected",
        owner_id=liu.id,
        closed_at=_ago(hours=48),
        created_at=_ago(hours=72),
        updated_at=_ago(hours=48),
    )
    db.add(ct_neilao)

    # 并购案快讯 - 开放中勘误
    ct_binggou = CorrectionTicket(
        story_packet_id=packet_objects[1].id,  # 并购案快讯稿
        event_case_id=ev_binggou.id,
        trigger_reason="并购金额表述为'约82亿元'，但公告原文为'不超过82亿元'，存在差异。需核实准确表述。",
        impact_scope="已发布快讯稿",
        proposed_fix="将'约82亿元'改为'不超过82亿元（含）'，并补充'最终交易金额以审计评估为准'",
        status="open",
        owner_id=wang.id,
        created_at=_ago(hours=6),
        updated_at=_ago(hours=6),
    )
    db.add(ct_binggou)

    # ── 15b. 为已发布稿件添加 draft versions ──
    # 新能源解读稿 draft
    draft_xinnengyuan = DraftVersion(
        story_packet_id=packet_objects[8].id,
        version=2,
        title="新能源汽车补贴政策深度解读：谁是赢家？",
        lead="国务院最新发布的新能源汽车补贴调整方案，将深刻改变行业竞争格局。",
        body="根据最新政策，2025年起新能源汽车购置补贴标准将进行结构性调整。\n\n"
             "一、补贴标准变化\n"
             "纯电动乘用车补贴从每辆1.26万元下调至0.84万元，降幅约33%。\n"
             "插电式混合动力车型补贴从每辆0.48万元下调至0.336万元。\n\n"
             "二、行业影响\n"
             "头部企业凭借规模优势有望消化补贴退坡影响，但中小品牌面临较大成本压力。\n"
             "分析人士预计，未来12个月内或有3-5家新能源品牌退出市场。\n\n"
             "三、消费者影响\n"
             "终端售价预计上涨3%-8%，但电池技术进步有望部分抵消成本上升。",
        word_count=280,
        is_frozen=True,
        created_by=zhao.id,
        created_at=_ago(hours=170),
    )
    db.add(draft_xinnengyuan)

    # 并购案快讯 draft
    draft_binggou_kuaixun = DraftVersion(
        story_packet_id=packet_objects[1].id,
        version=1,
        title="XX科技集团宣布82亿元收购YY公司",
        lead="XX科技集团（600XXX）今日公告，拟以不超过82亿元收购YY公司100%股权。",
        body="XX科技集团今日晚间发布公告，公司拟通过发行股份及支付现金的方式，"
             "收购YY公司100%股权，交易对价不超过82亿元人民币。\n\n"
             "YY公司主要从事半导体芯片设计业务，2024年营业收入约15亿元。"
             "本次交易构成重大资产重组，尚需股东大会审议及监管部门审批。",
        word_count=120,
        is_frozen=True,
        created_by=wang.id,
        created_at=_ago(hours=60),
    )
    db.add(draft_binggou_kuaixun)

    # ── 15c. 更多 Decision Logs（签发历史记录） ──
    # 并购快讯的签发记录
    bundle_binggou_kuaixun = ReviewBundle(
        story_packet_id=packet_objects[1].id,
        bundle_type="editorial",
        bundle_hash="sha256_demo_hash_binggou_kuaixun_ed",
        status="completed",
        submitted_by=wang.id,
        submit_note="并购快讯稿提交编辑审核",
        created_at=_ago(hours=58),
    )
    db.add(bundle_binggou_kuaixun)
    await db.flush()
    await db.refresh(bundle_binggou_kuaixun)

    task_binggou_kuaixun = ApprovalTask(
        review_bundle_id=bundle_binggou_kuaixun.id,
        approval_stage="editorial_review",
        status="completed",
        signer_slots=[
            {"user_id": li.id, "role": "desk_editor", "status": "approved"},
        ],
        execution_mode="sequential",
        sla_deadline=_ago(hours=56),
        created_at=_ago(hours=58),
    )
    db.add(task_binggou_kuaixun)
    await db.flush()
    await db.refresh(task_binggou_kuaixun)

    dl_binggou_kuaixun = DecisionLog(
        approval_task_id=task_binggou_kuaixun.id,
        review_bundle_id=bundle_binggou_kuaixun.id,
        signer_id=li.id,
        signer_role="desk_editor",
        action="approve",
        decision_reason="快讯事实清楚、引用准确，同意发布。",
        created_at=_ago(hours=57),
    )
    db.add(dl_binggou_kuaixun)

    # 新能源稿最终签发 decision log（task3 已存在，补充 decision_log）
    dl_xinnengyuan = DecisionLog(
        approval_task_id=task3.id,
        review_bundle_id=bundle3.id,
        signer_id=zhang.id,
        signer_role="chief_editor",
        action="approve",
        decision_reason="政策解读稿数据翔实、表述客观，同意发布。",
        created_at=_ago(minutes=15),
    )
    db.add(dl_xinnengyuan)
    # 更新 task3 状态为 approved
    task3.status = "approved"

    # ── 15d. 补充缺失的 Decision Logs（Issue 10） ──

    # 审计报告快讯（packet_objects[4]）签发记录
    bundle_shenji_kuaixun = ReviewBundle(
        story_packet_id=packet_objects[4].id,
        bundle_type="editorial",
        bundle_hash="sha256_demo_hash_shenji_kuaixun_ed",
        status="completed",
        submitted_by=wang.id,
        submit_note="审计报告快讯提交编辑审核",
        created_at=_ago(hours=44),
    )
    db.add(bundle_shenji_kuaixun)
    await db.flush()
    await db.refresh(bundle_shenji_kuaixun)

    task_shenji_kuaixun = ApprovalTask(
        review_bundle_id=bundle_shenji_kuaixun.id,
        approval_stage="editorial_review",
        status="completed",
        signer_slots=[{"user_id": li.id, "role": "desk_editor", "status": "approved"}],
        execution_mode="sequential",
        sla_deadline=_ago(hours=42),
        created_at=_ago(hours=44),
    )
    db.add(task_shenji_kuaixun)
    await db.flush()
    await db.refresh(task_shenji_kuaixun)

    dl_shenji_kuaixun = DecisionLog(
        approval_task_id=task_shenji_kuaixun.id,
        review_bundle_id=bundle_shenji_kuaixun.id,
        signer_id=li.id,
        signer_role="desk_editor",
        action="approve",
        decision_reason="审计数据引用准确，快讯格式规范，同意发布。",
        created_at=_ago(hours=43),
    )
    db.add(dl_shenji_kuaixun)

    # 补贴政策快讯（packet_objects[9]）签发记录
    bundle_butie_kuaixun = ReviewBundle(
        story_packet_id=packet_objects[9].id,
        bundle_type="editorial",
        bundle_hash="sha256_demo_hash_butie_kuaixun_ed",
        status="completed",
        submitted_by=zhao.id,
        submit_note="补贴政策快讯提交编辑审核",
        created_at=_ago(hours=130),
    )
    db.add(bundle_butie_kuaixun)
    await db.flush()
    await db.refresh(bundle_butie_kuaixun)

    task_butie_kuaixun = ApprovalTask(
        review_bundle_id=bundle_butie_kuaixun.id,
        approval_stage="editorial_review",
        status="completed",
        signer_slots=[{"user_id": li.id, "role": "desk_editor", "status": "approved"}],
        execution_mode="sequential",
        sla_deadline=_ago(hours=128),
        created_at=_ago(hours=130),
    )
    db.add(task_butie_kuaixun)
    await db.flush()
    await db.refresh(task_butie_kuaixun)

    dl_butie_kuaixun = DecisionLog(
        approval_task_id=task_butie_kuaixun.id,
        review_bundle_id=bundle_butie_kuaixun.id,
        signer_id=li.id,
        signer_role="desk_editor",
        action="approve",
        decision_reason="快讯内容准确、及时，同意发布。",
        created_at=_ago(hours=129),
    )
    db.add(dl_butie_kuaixun)

    # 内涝跟进：排水系统调查（packet_objects[6]）签发记录
    bundle_neilao_paishui = ReviewBundle(
        story_packet_id=packet_objects[6].id,
        bundle_type="final",
        bundle_hash="sha256_demo_hash_neilao_paishui_final",
        status="completed",
        submitted_by=liu.id,
        submit_note="排水系统调查稿提交最终签发",
        created_at=_ago(hours=98),
    )
    db.add(bundle_neilao_paishui)
    await db.flush()
    await db.refresh(bundle_neilao_paishui)

    task_neilao_paishui = ApprovalTask(
        review_bundle_id=bundle_neilao_paishui.id,
        approval_stage="final_review",
        status="completed",
        signer_slots=[{"user_id": zhang.id, "role": "chief_editor", "status": "approved"}],
        execution_mode="sequential",
        sla_deadline=_ago(hours=96),
        created_at=_ago(hours=98),
    )
    db.add(task_neilao_paishui)
    await db.flush()
    await db.refresh(task_neilao_paishui)

    dl_neilao_paishui = DecisionLog(
        approval_task_id=task_neilao_paishui.id,
        review_bundle_id=bundle_neilao_paishui.id,
        signer_id=zhang.id,
        signer_role="chief_editor",
        action="approve",
        decision_reason="《内涝跟进：排水系统调查》调查深入、数据详实，同意发布。",
        created_at=_ago(hours=97),
    )
    db.add(dl_neilao_paishui)

    # 内涝快讯（packet_objects[7]）签发记录
    bundle_neilao_kuaixun = ReviewBundle(
        story_packet_id=packet_objects[7].id,
        bundle_type="editorial",
        bundle_hash="sha256_demo_hash_neilao_kuaixun_ed",
        status="completed",
        submitted_by=liu.id,
        submit_note="内涝快讯提交编辑审核",
        created_at=_ago(hours=106),
    )
    db.add(bundle_neilao_kuaixun)
    await db.flush()
    await db.refresh(bundle_neilao_kuaixun)

    task_neilao_kuaixun = ApprovalTask(
        review_bundle_id=bundle_neilao_kuaixun.id,
        approval_stage="editorial_review",
        status="completed",
        signer_slots=[{"user_id": li.id, "role": "desk_editor", "status": "approved"}],
        execution_mode="sequential",
        sla_deadline=_ago(hours=104),
        created_at=_ago(hours=106),
    )
    db.add(task_neilao_kuaixun)
    await db.flush()
    await db.refresh(task_neilao_kuaixun)

    dl_neilao_kuaixun = DecisionLog(
        approval_task_id=task_neilao_kuaixun.id,
        review_bundle_id=bundle_neilao_kuaixun.id,
        signer_id=li.id,
        signer_role="desk_editor",
        action="approve",
        decision_reason="《内涝快讯》信息准确，时效性好，同意发布。",
        created_at=_ago(hours=105),
    )
    db.add(dl_neilao_kuaixun)


    # ── 16. 添加事件时间线数据 ──
    ev_binggou.timeline_data = [
        {"time": _ago(hours=72).isoformat(), "event": "RSS监控发现并购新闻", "actor": "Source Monitor Agent"},
        {"time": _ago(hours=70).isoformat(), "event": "采集上交所公告原文", "actor": "Source Monitor Agent"},
        {"time": _ago(hours=69).isoformat(), "event": "3条线索聚合为事件簇", "actor": "Dedup & Cluster Agent"},
        {"time": _ago(hours=68).isoformat(), "event": "自动分诊为L3高风险", "actor": "Triage Agent"},
        {"time": _ago(hours=66).isoformat(), "event": "张主编立项，指派赵记者", "actor": "张主编"},
        {"time": _ago(hours=48).isoformat(), "event": "收到记者独家线索", "actor": "王记者"},
        {"time": _ago(hours=48).isoformat(), "event": "生成证据包v2", "actor": "证据结构化 Agent"},
        {"time": _ago(hours=44).isoformat(), "event": "完成6项事实核验", "actor": "核验 Agent"},
        {"time": _ago(hours=42).isoformat(), "event": "绘制实体关系图谱", "actor": "关系调查 Agent"},
        {"time": _ago(hours=24).isoformat(), "event": "生成深度调查稿v3", "actor": "Drafting Agent"},
        {"time": _ago(hours=12).isoformat(), "event": "风险扫描发现3项问题", "actor": "Redaction & Risk Agent"},
        {"time": _ago(hours=2).isoformat(), "event": "提交风险审核", "actor": "赵记者"},
    ]

    ev_neilao.timeline_data = [
        {"time": _ago(hours=120).isoformat(), "event": "RSS监控发现暴雨内涝新闻", "actor": "Source Monitor Agent"},
        {"time": _ago(hours=118).isoformat(), "event": "自动分诊为L2中高风险", "actor": "Triage Agent"},
        {"time": _ago(hours=116).isoformat(), "event": "刘记者认领，开始采写", "actor": "刘记者"},
        {"time": _ago(hours=108).isoformat(), "event": "实地采访排水系统", "actor": "刘记者"},
        {"time": _ago(hours=104).isoformat(), "event": "生成深度调查稿", "actor": "Drafting Agent"},
        {"time": _ago(hours=102).isoformat(), "event": "提交最终签发", "actor": "刘记者"},
        {"time": _ago(hours=100).isoformat(), "event": "张主编签发通过", "actor": "张主编"},
        {"time": _ago(hours=100).isoformat(), "event": "生成3个渠道版本", "actor": "Channel Adapt Agent"},
        {"time": _ago(hours=96).isoformat(), "event": "全渠道发布完成", "actor": "系统"},
        {"time": _ago(hours=72).isoformat(), "event": "发布后监测：12.8万阅读", "actor": "Post Monitor Agent"},
    ]

    # 审计报告时间线
    ev_shenji.timeline_data = [
        {"time": _ago(hours=48).isoformat(), "event": "RSS监控发现审计报告发布", "actor": "Source Monitor Agent"},
        {"time": _ago(hours=47).isoformat(), "event": "自动分诊为L1风险", "actor": "Triage Agent"},
        {"time": _ago(hours=46).isoformat(), "event": "上传审计报告PDF全文", "actor": "王记者"},
        {"time": _ago(hours=36).isoformat(), "event": "生成4个核心事实声明", "actor": "证据结构化 Agent"},
        {"time": _ago(hours=24).isoformat(), "event": "生成数据解读稿v1", "actor": "Drafting Agent"},
        {"time": _ago(hours=1).isoformat(), "event": "提交编辑审核", "actor": "王记者"},
    ]

    # 新能源时间线
    ev_xinnengyuan.timeline_data = [
        {"time": _ago(hours=168).isoformat(), "event": "RSS监控发现补贴政策新闻", "actor": "Source Monitor Agent"},
        {"time": _ago(hours=166).isoformat(), "event": "自动分诊为L0低风险", "actor": "Triage Agent"},
        {"time": _ago(hours=160).isoformat(), "event": "赵记者认领，开始调研", "actor": "赵记者"},
        {"time": _ago(hours=140).isoformat(), "event": "生成政策解读稿v2", "actor": "Drafting Agent"},
        {"time": _ago(hours=130).isoformat(), "event": "提交最终签发", "actor": "赵记者"},
        {"time": _ago(hours=128).isoformat(), "event": "张主编签发通过", "actor": "张主编"},
        {"time": _ago(hours=127).isoformat(), "event": "全渠道发布完成", "actor": "系统"},
    ]

    # 跨境电商时间线
    ev_kuajing.timeline_data = [
        {"time": _ago(hours=24).isoformat(), "event": "RSS监控发现海关新规公告", "actor": "Source Monitor Agent"},
        {"time": _ago(hours=23).isoformat(), "event": "自动分诊为L1风险", "actor": "Triage Agent"},
        {"time": _ago(hours=22).isoformat(), "event": "赵记者认领，开始深度分析", "actor": "赵记者"},
    ]

    # AI芯片时间线
    ev_chip.timeline_data = [
        {"time": _ago(hours=6).isoformat(), "event": "RSS监控发现路透社芯片管制报道", "actor": "Source Monitor Agent"},
        {"time": _ago(hours=5).isoformat(), "event": "聚合2条相关线索", "actor": "Dedup & Cluster Agent"},
        {"time": _ago(hours=4).isoformat(), "event": "自动分诊为L2中高风险", "actor": "Triage Agent"},
        {"time": _ago(hours=4).isoformat(), "event": "采集工信部回应", "actor": "Source Monitor Agent"},
    ]

    # 医保时间线
    ev_yibao.timeline_data = [
        {"time": _ago(hours=36).isoformat(), "event": "RSS监控发现医保局通报", "actor": "Source Monitor Agent"},
        {"time": _ago(hours=35).isoformat(), "event": "自动分诊为L1风险", "actor": "Triage Agent"},
        {"time": _ago(hours=34).isoformat(), "event": "刘记者认领，开始调查", "actor": "刘记者"},
        {"time": _ago(hours=30).isoformat(), "event": "采集澎湃新闻调查报道", "actor": "Source Monitor Agent"},
        {"time": _ago(hours=28).isoformat(), "event": "开始深度报道写作", "actor": "刘记者"},
    ]

    # ── 17. Workflow Runs（AI Agent 工作流实例，展示事件详情页 Agent 流水线） ──
    from app.services.workflow_runtime_service import workflow_runtime_service
    await workflow_runtime_service.ensure_tables(db)

    workflow_runs_data = [
        {
            "run_id": str(uuid.uuid4()),
            "event_case_id": ev_binggou.id,
            "story_packet_id": sp_binggou_depth.id,
            "current_stage": "editorial_review",
            "status": "blocked",  # 脱敏门3未通过，blocked 状态演示
            "state_json": json.dumps({"workflow_id": "wf_binggou", "current_stage": "editorial_review", "event_case_id": ev_binggou.id, "gate3_pass": False, "blocked": True}, ensure_ascii=False),
            "last_error": None,
            "created_by": zhao.id,
            "created_at": _ago(hours=72).isoformat(),
            "updated_at": _ago(hours=2).isoformat(),
        },
        {
            "run_id": str(uuid.uuid4()),
            "event_case_id": ev_neilao.id,
            "story_packet_id": packet_objects[5].id,
            "current_stage": "completed",
            "status": "completed",
            "state_json": json.dumps({"workflow_id": "wf_neilao", "current_stage": "completed", "event_case_id": ev_neilao.id}, ensure_ascii=False),
            "last_error": None,
            "created_by": liu.id,
            "created_at": _ago(hours=120).isoformat(),
            "updated_at": _ago(hours=72).isoformat(),
        },
        {
            "run_id": str(uuid.uuid4()),
            "event_case_id": ev_shenji.id,
            "story_packet_id": sp_shenji.id,
            "current_stage": "editorial_review",
            "status": "running",
            "state_json": json.dumps({"workflow_id": "wf_shenji", "current_stage": "editorial_review", "event_case_id": ev_shenji.id}, ensure_ascii=False),
            "last_error": None,
            "created_by": wang.id,
            "created_at": _ago(hours=48).isoformat(),
            "updated_at": _ago(hours=1).isoformat(),
        },
        {
            "run_id": str(uuid.uuid4()),
            "event_case_id": ev_chip.id,
            "story_packet_id": None,
            "current_stage": "human_gate_project",  # L0风险，等待人工立项决策
            "status": "running",
            "state_json": json.dumps({"workflow_id": "wf_chip", "current_stage": "human_gate_project", "event_case_id": ev_chip.id, "risk_level": "L0"}, ensure_ascii=False),
            "last_error": None,
            "created_by": None,
            "created_at": _ago(hours=6).isoformat(),
            "updated_at": _ago(hours=4).isoformat(),
        },
        {
            "run_id": str(uuid.uuid4()),
            "event_case_id": ev_xinnengyuan.id,
            "story_packet_id": packet_objects[8].id,
            "current_stage": "completed",
            "status": "completed",
            "state_json": json.dumps({"workflow_id": "wf_xinnengyuan", "current_stage": "completed", "event_case_id": ev_xinnengyuan.id}, ensure_ascii=False),
            "last_error": None,
            "created_by": zhao.id,
            "created_at": _ago(hours=168).isoformat(),
            "updated_at": _ago(hours=127).isoformat(),
        },
        {
            "run_id": str(uuid.uuid4()),
            "event_case_id": ev_yibao.id,
            "story_packet_id": packet_objects[12].id,  # 医保深度稿
            "current_stage": "human_supplement",  # 脱敏门2未通过，等待人工补充
            "status": "running",
            "state_json": json.dumps({"workflow_id": "wf_yibao", "current_stage": "human_supplement", "event_case_id": ev_yibao.id, "pii_count": 2}, ensure_ascii=False),
            "last_error": None,
            "created_by": liu.id,
            "created_at": _ago(hours=36).isoformat(),
            "updated_at": _ago(hours=8).isoformat(),
        },
    ]

    for wf in workflow_runs_data:
        await db.execute(
            text(
                """
                INSERT INTO workflow_runs (
                    run_id, event_case_id, story_packet_id, current_stage, status,
                    state_json, last_error, created_by, created_at, updated_at
                ) VALUES (
                    :run_id, :event_case_id, :story_packet_id, :current_stage, :status,
                    :state_json, :last_error, :created_by, :created_at, :updated_at
                )
                ON CONFLICT(run_id) DO NOTHING
                """
            ),
            wf,
        )

    await db.flush()
    await db.commit()

    return {
        "message": "种子数据生成成功",
        "seeded": True,
        "stats": {
            "users": len(users_data),
            "organizations": 1,
            "events": len(events_data),
            "story_packets": len(packets_data),
            "claim_cards": len(claims_binggou) + len(claims_shenji),
            "evidence_packs": 2,
            "risk_reports": 2,
            "channel_packages": 3,
            "source_items": len(source_items_data),
            "audit_logs": len(audit_entries),
            "approval_tasks": 10,
            "decision_logs": 7,
            "correction_tickets": 2,
            "draft_versions": 6,
            "workflow_runs": 6,  # 包含 blocked, human_gate_project, human_supplement 等状态演示
        },
        "login_info": {
            "username": "zhangzhubian",
            "password": "newsflow123",
            "note": "所有用户密码均为 newsflow123",
        },
        "demo_guide": {
            "全链路体验建议": [
                "1. 登录后查看 Dashboard，观察 Agent 活动时间线和 SLA 告警",
                "2. 点击事件案卷 > '某科技集团并购争议案' 查看完整时间线和多来源线索",
                "3. 点击任务包 > '某科技集团并购争议深度稿' 查看 Claim Cards 和风险报告",
                "4. 前往签发中心查看待签发任务和 SLA 告警",
                "5. 查看 '城市内涝深度报道' 体验已完成全链路（采集→核验→签发→发布→监测）",
            ],
        },
    }


@router.delete("/clear", summary="清空所有Demo数据")
@router.post("/clear", summary="清空所有Demo数据（兼容POST）")
async def clear_demo_data(db: AsyncSession = Depends(get_db)):
    """清空所有事件、任务包、工作流等数据（保留用户和组织）。仅开发环境可用。"""
    if not settings.DEBUG:
        return JSONResponse(status_code=403, content={"message": "仅开发环境可用"})

    # 按外键依赖顺序删除
    tables = [
        "workflow_runs", "audit_logs", "decision_logs", "correction_tickets",
        "channel_packages", "approval_tasks", "review_bundles", "risk_reports",
        "claim_cards", "evidence_packs", "draft_versions", "event_source_items",
        "story_packets", "event_cases",
    ]
    deleted_counts: dict[str, int] = {}
    skipped_tables: dict[str, str] = {}

    for table in tables:
        try:
            result = await db.execute(text(f"DELETE FROM {table}"))
            await db.commit()
            deleted_counts[table] = int(result.rowcount or 0)
        except Exception as e:
            await db.rollback()
            msg = str(e)
            if "UndefinedTableError" in msg or "does not exist" in msg or "no such table" in msg:
                skipped_tables[table] = "table_not_found"
                logger.warning(f"Skip clearing table [{table}] because it does not exist")
                continue
            logger.error(f"Clear demo data failed at table [{table}]: {e}")
            return JSONResponse(status_code=500, content={"message": f"清空失败: {e}", "failed_table": table})

    return {
        "message": "Demo数据已清空",
        "deleted": deleted_counts,
        "skipped": skipped_tables,
        "note": "用户和组织数据已保留，可重新运行 /seed 生成新数据",
    }
