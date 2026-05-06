"""审批策略引擎：根据风险等级生成审批任务和签位。"""

import uuid
import json
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.approval_task import ApprovalTask
from app.models.review_bundle import ReviewBundle
from app.models.story_packet import StoryPacket
from app.models.user import User


@dataclass
class SignerSlot:
    """签位配置"""
    role: str
    user_id: str | None = None
    status: str = "pending"  # pending / signed / skipped
    signed_at: str | None = None

    def to_dict(self) -> dict:
        return {
            "role": self.role,
            "user_id": self.user_id,
            "status": self.status,
            "signed_at": self.signed_at,
        }


# 审批策略配置
APPROVAL_POLICIES = {
    "L0": {
        "editorial_review": {
            "required_signers": ["desk_editor"],
            "execution_mode": "any",  # any: 任一签即可, all: 全部签
            "sla_hours": 4,
        },
        "risk_review": {"skip": True},
        "channel_review": {
            "required_signers": ["desk_editor"],
            "execution_mode": "any",
            "sla_hours": 2,
        },
        "final_signoff": {
            "required_signers": ["desk_editor"],
            "execution_mode": "any",
            "sla_hours": 1,
        },
    },
    "L1": {
        "editorial_review": {
            "required_signers": ["desk_editor"],
            "execution_mode": "any",
            "sla_hours": 4,
        },
        "risk_review": {
            "required_signers": ["desk_editor"],
            "execution_mode": "any",
            "sla_hours": 4,
        },
        "channel_review": {
            "required_signers": ["desk_editor"],
            "execution_mode": "any",
            "sla_hours": 2,
        },
        "final_signoff": {
            "required_signers": ["desk_editor"],
            "execution_mode": "any",
            "sla_hours": 1,
        },
    },
    "L2": {
        "editorial_review": {
            "required_signers": ["desk_editor"],
            "execution_mode": "any",
            "sla_hours": 6,
        },
        "risk_review": {
            "required_signers": ["compliance_editor", "chief_editor"],
            "execution_mode": "all",
            "sla_hours": 8,
        },
        "channel_review": {
            "required_signers": ["desk_editor", "compliance_editor"],
            "execution_mode": "all",
            "sla_hours": 4,
        },
        "final_signoff": {
            "required_signers": ["chief_editor"],
            "execution_mode": "any",
            "sla_hours": 2,
        },
    },
    "L3": {
        "editorial_review": {
            "required_signers": ["desk_editor"],
            "execution_mode": "any",
            "sla_hours": 8,
        },
        "risk_review": {
            "required_signers": ["compliance_editor", "legal", "chief_editor"],
            "execution_mode": "all",
            "sla_hours": 24,
        },
        "channel_review": {
            "required_signers": ["desk_editor", "compliance_editor", "legal"],
            "execution_mode": "all",
            "sla_hours": 8,
        },
        "final_signoff": {
            "required_signers": ["chief_editor"],
            "execution_mode": "any",
            "sla_hours": 4,
        },
    },
}


class ApprovalService:
    """审批策略服务"""

    def get_policy(self, risk_level: str, approval_stage: str) -> dict | None:
        """获取审批策略"""
        level_policy = APPROVAL_POLICIES.get(risk_level, APPROVAL_POLICIES["L0"])
        return level_policy.get(approval_stage)

    def should_skip_stage(self, risk_level: str, approval_stage: str) -> bool:
        """判断是否跳过该审批阶段"""
        policy = self.get_policy(risk_level, approval_stage)
        if not policy:
            return True
        return policy.get("skip", False)

    def create_signer_slots(self, policy: dict) -> list[dict]:
        """根据策略创建签位列表"""
        required_signers = policy.get("required_signers", [])
        return [SignerSlot(role=role).to_dict() for role in required_signers]

    async def assign_signers(
        self,
        signer_slots: list[dict],
        desk: str | None,
        db: AsyncSession
    ) -> list[dict]:
        """
        为签位分配具体用户
        优先分配同部门的用户
        """
        for slot in signer_slots:
            role = slot["role"]
            # 查找符合角色的用户
            result = await db.execute(
                select(User)
                .where(User.is_active == True)
            )
            users = result.scalars().all()
            
            for user in users:
                # 解析用户角色
                user_roles = user.roles
                if isinstance(user_roles, str):
                    try:
                        user_roles = json.loads(user_roles)
                    except:
                        user_roles = []
                
                if role in user_roles:
                    slot["user_id"] = user.id
                    break
        
        return signer_slots

    async def create_approval_task(
        self,
        review_bundle: ReviewBundle,
        story_packet: StoryPacket,
        approval_stage: str,
        db: AsyncSession
    ) -> ApprovalTask | None:
        """
        创建审批任务
        
        Args:
            review_bundle: 送审快照包
            story_packet: 报道任务包
            approval_stage: 审批阶段
            db: 数据库会话
        
        Returns:
            ApprovalTask 或 None（如果跳过该阶段）
        """
        risk_level = story_packet.risk_level
        
        # 检查是否跳过
        if self.should_skip_stage(risk_level, approval_stage):
            return None
        
        policy = self.get_policy(risk_level, approval_stage)
        if not policy:
            return None
        
        # 创建签位
        signer_slots = self.create_signer_slots(policy)
        signer_slots = await self.assign_signers(
            signer_slots, story_packet.desk, db
        )
        
        # 计算 SLA 截止时间
        sla_hours = policy.get("sla_hours", 24)
        sla_deadline = datetime.utcnow() + timedelta(hours=sla_hours)
        
        # 创建任务
        task = ApprovalTask(
            id=str(uuid.uuid4()),
            review_bundle_id=review_bundle.id,
            approval_stage=approval_stage,
            status="pending",
            policy_rule=json.dumps(policy, ensure_ascii=False),
            signer_slots=json.dumps(signer_slots, ensure_ascii=False),
            execution_mode=policy.get("execution_mode", "any"),
            sla_deadline=sla_deadline,
            assigned_at=datetime.utcnow(),
        )
        db.add(task)
        await db.flush()
        
        return task

    async def check_all_signers_approved(
        self, task: ApprovalTask
    ) -> bool:
        """检查是否所有签位都已签署"""
        signer_slots = task.signer_slots
        if isinstance(signer_slots, str):
            signer_slots = json.loads(signer_slots)
        
        execution_mode = task.execution_mode
        
        if execution_mode == "any":
            # 任一签即可
            return any(s.get("status") == "signed" for s in signer_slots)
        else:
            # 全部签
            return all(s.get("status") in ("signed", "skipped") for s in signer_slots)

    async def record_signature(
        self,
        task: ApprovalTask,
        signer_id: str,
        signer_role: str,
        action: str,
        db: AsyncSession
    ) -> bool:
        """
        记录签署
        
        Returns:
            是否完成所有签署
        """
        signer_slots = task.signer_slots
        if isinstance(signer_slots, str):
            signer_slots = json.loads(signer_slots)
        
        # 更新签位状态
        for slot in signer_slots:
            if slot["role"] == signer_role:
                slot["status"] = "signed" if action == "approve" else action
                slot["user_id"] = signer_id
                slot["signed_at"] = datetime.utcnow().isoformat()
                break
        
        task.signer_slots = json.dumps(signer_slots, ensure_ascii=False)
        
        # 检查是否完成
        return await self.check_all_signers_approved(task)

    def get_next_stage(self, current_stage: str, risk_level: str) -> str | None:
        """获取下一个审批阶段"""
        stage_order = [
            "editorial_review",
            "risk_review",
            "channel_review",
            "final_signoff",
        ]
        
        try:
            current_idx = stage_order.index(current_stage)
        except ValueError:
            return None
        
        # 查找下一个非跳过的阶段
        for next_stage in stage_order[current_idx + 1:]:
            if not self.should_skip_stage(risk_level, next_stage):
                return next_stage
        
        return None


approval_service = ApprovalService()
