"""API v1 路由汇总。"""

from fastapi import APIRouter

from app.core.config import settings
from app.api.v1 import (
    auth, events, story_packets, approvals, sources, dashboard,
    workflows, evidence_packs, channel_packages, correction_tickets,
    review_bundles, risk_reports, claim_cards, organizations,
)

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["认证"])
api_router.include_router(events.router, prefix="/events", tags=["事件案卷"])
api_router.include_router(story_packets.router, prefix="/story-packets", tags=["报道任务包"])
api_router.include_router(approvals.router, prefix="/approvals", tags=["签发中心"])
api_router.include_router(sources.router, prefix="/sources", tags=["线索来源"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["今日概览"])
api_router.include_router(workflows.router, prefix="/workflows", tags=["工作流"])
api_router.include_router(evidence_packs.router, prefix="/evidence-packs", tags=["证据包"])
api_router.include_router(channel_packages.router, prefix="/channel-packages", tags=["渠道包"])
api_router.include_router(correction_tickets.router, prefix="/correction-tickets", tags=["勘误单"])
api_router.include_router(review_bundles.router, prefix="/review-bundles", tags=["送审快照包"])
api_router.include_router(risk_reports.router, prefix="/risk-reports", tags=["风险报告"])
api_router.include_router(claim_cards.router, prefix="/claim-cards", tags=["事实卡"])
api_router.include_router(organizations.router, prefix="/orgs", tags=["团队管理"])

# 开发工具路由仅在 DEBUG 模式下注册
if settings.DEBUG:
    from app.api.v1 import seed
    api_router.include_router(seed.router, prefix="/dev", tags=["开发工具"])
