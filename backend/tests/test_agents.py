"""Agent 模块集成测试。"""

import pytest
import asyncio
from datetime import datetime


class TestSourceMonitorAgent:
    """Source Monitor Agent 测试"""

    @pytest.mark.asyncio
    async def test_collect_from_rss(self):
        from app.agents import source_monitor_agent
        result = await source_monitor_agent.collect_from_rss(
            "https://example.com/feed",
            "test_source"
        )
        assert result is not None

    @pytest.mark.asyncio
    async def test_extract_5w1h(self):
        from app.agents import source_monitor_agent
        content = "据报道，XX公司于2026年3月27日宣布完成重大并购交易，涉及金额10亿元。"
        result = await source_monitor_agent.extract_5w1h(content)
        assert result is not None
        assert hasattr(result, 'who')
        assert hasattr(result, 'what')


class TestDedupClusterAgent:
    """Dedup & Cluster Agent 测试"""

    @pytest.mark.asyncio
    async def test_process_source(self):
        from app.agents import dedup_cluster_agent
        result = await dedup_cluster_agent.process_source(
            "XX公司并购案最新进展",
            "source_001"
        )
        assert result is not None
        assert hasattr(result, 'decision')


class TestTriageAgent:
    """Triage Agent 测试"""

    @pytest.mark.asyncio
    async def test_assess_event(self):
        from app.agents import triage_agent
        result = await triage_agent.assess_event(
            "重大企业并购涉及内幕交易",
            "event_001"
        )
        assert result is not None
        assert hasattr(result, 'risk_level')
        assert result.risk_level in ['L0', 'L1', 'L2', 'L3']


class TestEvidenceStructuringAgent:
    """Evidence Structuring Agent 测试"""

    @pytest.mark.asyncio
    async def test_extract_from_source(self):
        from app.agents import evidence_structuring_agent
        result = await evidence_structuring_agent.extract_from_source(
            "source_001",
            "XX公司CEO张某在发布会上表示，此次并购符合公司战略规划。"
        )
        assert result is not None


class TestVerificationAgent:
    """Verification Agent 测试"""

    @pytest.mark.asyncio
    async def test_decompose_claims(self):
        from app.agents import verification_agent
        claims = await verification_agent.decompose_claims(
            "XX公司以10亿元收购YY公司，交易将于下月完成。"
        )
        assert isinstance(claims, list)


class TestRedactionRiskAgent:
    """Redaction & Risk Agent 测试"""

    @pytest.mark.asyncio
    async def test_gate1_scan(self):
        from app.agents import redaction_risk_agent
        result = await redaction_risk_agent.gate1_scan(
            "知情人士透露，张三（手机号：13812345678）参与了此次交易。"
        )
        assert result is not None
        assert hasattr(result, 'pii_detected')
        assert len(result.pii_detected) > 0  # 应检测到手机号


class TestDraftingAgent:
    """Drafting Agent 测试"""

    @pytest.mark.asyncio
    async def test_plan_structure(self):
        from app.agents import drafting_agent
        result = await drafting_agent.plan_structure(
            "breaking",
            "XX公司完成重大并购"
        )
        assert result is not None
        assert result.content_type == "breaking"


class TestChannelAdaptationAgent:
    """Channel Adaptation Agent 测试"""

    @pytest.mark.asyncio
    async def test_check_platform_compliance(self):
        from app.agents import channel_adaptation_agent
        result = await channel_adaptation_agent.check_platform_compliance(
            "这是一个测试标题",
            "这是测试正文内容",
            "weibo"
        )
        assert result is not None
        assert hasattr(result, 'compliant')


class TestOrchestratorAgent:
    """Orchestrator Agent 测试"""

    @pytest.mark.asyncio
    async def test_create_workflow(self):
        from app.agents import orchestrator_agent
        state = await orchestrator_agent.create_workflow(
            event_case_id="ec_001",
            source_items=[{"id": "s1", "content": "测试内容"}]
        )
        assert state is not None
        assert state.workflow_id is not None
        assert state.event_case_id == "ec_001"

    @pytest.mark.asyncio
    async def test_get_sla_status(self):
        from app.agents import orchestrator_agent
        state = await orchestrator_agent.create_workflow()
        sla = await orchestrator_agent.get_sla_status(state.workflow_id)
        assert sla is not None
        assert "status" in sla


class TestPostPublishMonitor:
    """Post Publish Monitor 测试"""

    @pytest.mark.asyncio
    async def test_start_monitoring(self):
        from app.agents import post_publish_monitor
        task = await post_publish_monitor.start_monitoring(
            story_packet_id="sp_001",
            event_case_id="ec_001",
            keywords=["XX公司", "并购"],
            risk_level="L2"
        )
        assert task is not None
        assert task["status"] == "active"
        assert task["duration_days"] == 90  # L2 风险应为 90 天

    @pytest.mark.asyncio
    async def test_create_correction_ticket(self):
        from app.agents import post_publish_monitor
        ticket = await post_publish_monitor.create_correction_ticket(
            story_packet_id="sp_001",
            trigger_reason="发现事实错误",
            trigger_source="读者反馈",
            impact_scope="正文第三段",
            proposed_fix="修正金额数据"
        )
        assert ticket is not None
        assert ticket.status == "pending"


class TestAuditAgent:
    """Audit Agent 测试"""

    @pytest.mark.asyncio
    async def test_log_action(self):
        from app.agents import audit_agent
        entry = await audit_agent.log_action(
            actor_id="user_001",
            actor_type="human",
            action="approve",
            object_type="story_packet",
            object_id="sp_001"
        )
        assert entry is not None
        assert entry.action == "approve"

    @pytest.mark.asyncio
    async def test_verify_chain_integrity(self):
        from app.agents import audit_agent
        # 添加几条记录
        await audit_agent.log_action("u1", "human", "create", "sp", "001")
        await audit_agent.log_action("u1", "human", "update", "sp", "001")
        
        is_valid = await audit_agent.verify_chain_integrity()
        assert is_valid is True


# 集成测试场景
class TestIntegrationScenarios:
    """集成测试场景"""

    @pytest.mark.asyncio
    async def test_it01_source_to_triage(self):
        """IT-01: 线索采集→去重→聚类→Triage"""
        from app.agents import source_monitor_agent, dedup_cluster_agent, triage_agent

        # 1. 采集线索
        content = "重大新闻：XX公司宣布收购YY公司"
        
        # 2. 去重聚类
        cluster_result = await dedup_cluster_agent.process_source(content, "s001")
        assert cluster_result.decision in ["new_event", "merge", "skip"]
        
        # 3. Triage 评估
        triage_result = await triage_agent.assess_event(content, "ec001")
        assert triage_result.risk_level in ["L0", "L1", "L2", "L3"]

    @pytest.mark.asyncio
    async def test_it03_draft_to_precheck(self):
        """IT-03: 写稿→脱敏门3→送审预检"""
        from app.agents import drafting_agent, redaction_risk_agent

        # 1. 生成初稿
        draft = await drafting_agent.generate_draft(
            angle="客观报道",
            audience="一般读者",
            content_type="breaking",
            evidence_summary="XX公司完成并购",
            verified_claims=[{"id": "c1", "claim_text": "交易金额10亿"}],
        )
        assert draft.title or draft.body

        # 2. 脱敏门3扫描
        if draft.body:
            gate3 = await redaction_risk_agent.gate3_full_scan(draft.body)
            assert gate3 is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
