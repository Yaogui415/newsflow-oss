"""Redaction & Risk Agent：脱敏与风险 Agent，负责三道脱敏门和风险评估。"""

import uuid
import json
import re
import hashlib
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Any

from app.core.config import settings


# PII 检测正则模式（中国特有）
PII_PATTERNS = {
    "phone": r"1[3-9]\d{9}",
    "id_card": r"\d{17}[\dXx]",
    "email": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
    "bank_card": r"\d{16,19}",
    "address": r"[\u4e00-\u9fa5]{2,}(省|市|区|县|镇|村|路|街|号|栋|单元|室)\d*",
    "passport": r"[GgEe]\d{8}",
    "plate_number": r"[京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼][A-Z][A-Z0-9]{5,6}",
}

# 敏感词类别
SENSITIVE_CATEGORIES = {
    "minor": ["未成年", "儿童", "少年", "学生", "小学", "中学", "幼儿"],
    "anonymous_source": ["知情人士", "消息人士", "匿名", "不愿透露姓名"],
    "legal_risk": ["涉嫌", "犯罪", "逮捕", "拘留", "审查", "调查"],
    "national_security": ["国家安全", "军事", "机密", "绝密", "国防"],
    "speculative": ["据称", "疑似", "可能", "或许", "传闻"],
}

CLICKBAIT_TERMS = ["震惊", "炸裂", "必看", "速看", "全网都在传", "惊天", "刷屏", "重磅", "沸腾"]
ABSOLUTIST_TERMS = ["实锤", "坐实", "铁证如山", "毫无疑问", "板上钉钉", "彻底证实"]
ATTRIBUTION_MARKERS = ["据", "表示", "称", "公告", "通报", "披露", "采访", "回应", "文件显示", "资料显示"]
RESPONSE_MARKERS = ["回应", "表示", "称", "未回应", "暂未回应", "拒绝置评", "联系", "求证"]
ALLEGATION_TERMS = ["涉嫌", "指控", "质疑", "违规", "违法", "腐败", "造假", "内幕交易", "利益输送"]


@dataclass
class PIIFinding:
    """PII 检测结果"""
    pii_type: str
    value: str
    position: tuple[int, int]
    masked_value: str

    def to_dict(self) -> dict:
        return {
            "pii_type": self.pii_type,
            "value": self.value[:4] + "***",  # 部分脱敏显示
            "position": list(self.position),
            "masked_value": self.masked_value,
        }


@dataclass
class RiskFinding:
    """风险发现"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    risk_type: str = ""
    severity: str = "medium"  # critical / high / medium / low
    location: str = ""
    description: str = ""
    recommendation: str = ""
    auto_fixable: bool = False
    suggested_fix: str | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.risk_type,
            "severity": self.severity,
            "location": self.location,
            "description": self.description,
            "recommendation": self.recommendation,
            "auto_fixable": self.auto_fixable,
            "suggested_fix": self.suggested_fix,
        }


@dataclass
class Gate1Result:
    """脱敏门1结果"""
    source_id: str
    pii_findings: list[PIIFinding] = field(default_factory=list)
    risk_tags: list[str] = field(default_factory=list)
    safe_copy_generated: bool = False
    original_stored_path: str | None = None

    def to_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "pii_count": len(self.pii_findings),
            "pii_findings": [f.to_dict() for f in self.pii_findings],
            "risk_tags": self.risk_tags,
            "safe_copy_generated": self.safe_copy_generated,
        }


@dataclass
class Gate3Result:
    """脱敏门3结果"""
    story_packet_id: str
    risk_findings: list[RiskFinding] = field(default_factory=list)
    blockers: list[dict] = field(default_factory=list)
    severity_summary: dict = field(default_factory=dict)
    can_proceed: bool = True

    def to_dict(self) -> dict:
        return {
            "story_packet_id": self.story_packet_id,
            "risk_findings": [f.to_dict() for f in self.risk_findings],
            "blockers": self.blockers,
            "severity_summary": self.severity_summary,
            "can_proceed": self.can_proceed,
        }


@dataclass
class RiskReport:
    """风险报告"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    story_packet_id: str = ""
    report_type: str = "risk"
    version: int = 1
    findings: list[RiskFinding] = field(default_factory=list)
    severity_summary: dict = field(default_factory=dict)
    blockers_generated: list[str] = field(default_factory=list)
    generated_at: datetime = field(default_factory=lambda: datetime.utcnow())

    def to_dict(self) -> dict:
        return {
            "report_id": self.id,
            "story_packet_id": self.story_packet_id,
            "report_type": self.report_type,
            "version": self.version,
            "scan_time": self.generated_at.isoformat(),
            "severity_summary": self.severity_summary,
            "findings": [f.to_dict() for f in self.findings],
            "blockers_generated": self.blockers_generated,
            "generated_by": "agent",
        }


class RedactionRiskAgent:
    """脱敏与风险 Agent"""

    def __init__(self):
        self._source_vault_aliases: dict[str, str] = {}  # alias -> description

    def _mask_pii(self, value: str, pii_type: str) -> str:
        """生成脱敏后的值"""
        if pii_type == "phone":
            return value[:3] + "****" + value[-4:]
        elif pii_type == "id_card":
            return value[:6] + "********" + value[-4:]
        elif pii_type == "email":
            parts = value.split("@")
            if len(parts) == 2:
                return parts[0][:2] + "***@" + parts[1]
            return "***@***.com"
        elif pii_type == "bank_card":
            return value[:4] + " **** **** " + value[-4:]
        else:
            if len(value) > 4:
                return value[:2] + "*" * (len(value) - 4) + value[-2:]
            return "***"

    def _detect_pii(self, text: str) -> list[PIIFinding]:
        """检测文本中的 PII"""
        findings = []
        for pii_type, pattern in PII_PATTERNS.items():
            for match in re.finditer(pattern, text):
                value = match.group()
                masked = self._mask_pii(value, pii_type)
                findings.append(PIIFinding(
                    pii_type=pii_type,
                    value=value,
                    position=(match.start(), match.end()),
                    masked_value=masked,
                ))
        return findings

    def _detect_sensitive_categories(self, text: str) -> list[str]:
        """检测敏感词类别"""
        tags = []
        for category, keywords in SENSITIVE_CATEGORIES.items():
            for keyword in keywords:
                if keyword in text:
                    tags.append(f"sensitive:{category}")
                    break
        return tags

    def _redact_text(self, text: str, findings: list[PIIFinding]) -> str:
        """对文本进行脱敏处理"""
        # 按位置倒序排列，避免位置偏移
        sorted_findings = sorted(findings, key=lambda f: f.position[0], reverse=True)
        result = text
        for finding in sorted_findings:
            start, end = finding.position
            result = result[:start] + finding.masked_value + result[end:]
        return result

    async def gate1_scan(self, source_id: str, content: str) -> Gate1Result:
        """脱敏门1：材料进入时的 PII 扫描和安全副本生成"""
        # PII 检测
        pii_findings = self._detect_pii(content)

        # 敏感类别检测
        risk_tags = self._detect_sensitive_categories(content)

        # 如果发现 PII，标记需要生成安全副本
        safe_copy_needed = len(pii_findings) > 0

        return Gate1Result(
            source_id=source_id,
            pii_findings=pii_findings,
            risk_tags=risk_tags,
            safe_copy_generated=safe_copy_needed,
        )

    async def generate_safe_copy(self, content: str, findings: list[PIIFinding]) -> str:
        """生成脱敏后的安全副本"""
        return self._redact_text(content, findings)

    async def gate2_verify(self, content: str) -> dict:
        """脱敏门2：验证 AI 工作副本已完成脱敏"""
        # 检查是否还有残留 PII
        residual_pii = self._detect_pii(content)
        return {
            "verified": len(residual_pii) == 0,
            "residual_pii_count": len(residual_pii),
            "residual_types": list(set(f.pii_type for f in residual_pii)),
        }

    async def gate3_full_scan(
        self,
        draft_content: str,
        evidence_summary: str | None = None,
        channel_contents: list[str] | None = None,
    ) -> Gate3Result:
        """脱敏门3：送审前全面风险扫描"""
        findings = []
        blockers = []

        # 合并所有内容
        all_content = draft_content
        if evidence_summary:
            all_content += "\n" + evidence_summary
        if channel_contents:
            all_content += "\n" + "\n".join(channel_contents)

        # 1. PII 残留检查
        pii_findings = self._detect_pii(all_content)
        if pii_findings:
            findings.append(RiskFinding(
                risk_type="pii_exposure",
                severity="high",
                location="multiple",
                description=f"发现 {len(pii_findings)} 处 PII 残留",
                recommendation="请完成脱敏处理后再送审",
                auto_fixable=True,
            ))
            blockers.append({
                "blocker_id": f"BLK-{uuid.uuid4().hex[:8]}",
                "type": "pii_exposure",
                "severity": "critical",
                "description": "存在 PII 残留，必须脱敏后再送审",
                "resolved": False,
            })

        # 2. 敏感内容检查
        sensitive_tags = self._detect_sensitive_categories(all_content)
        for tag in sensitive_tags:
            category = tag.split(":")[1] if ":" in tag else tag
            severity = "critical" if category in ("minor", "national_security") else "high"
            findings.append(RiskFinding(
                risk_type=f"sensitive_content_{category}",
                severity=severity,
                location="content",
                description=f"内容涉及敏感类别：{category}",
                recommendation=f"请确认 {category} 相关内容已做适当处理",
            ))

        # 3. 推断性语言检查
        speculative_patterns = [
            (r"涉嫌\w+", "涉嫌", "high"),
            (r"据称\w+", "据称", "medium"),
            (r"疑似\w+", "疑似", "medium"),
            (r"可能\w+", "可能", "low"),
        ]
        for pattern, keyword, severity in speculative_patterns:
            matches = re.findall(pattern, all_content)
            if matches:
                findings.append(RiskFinding(
                    risk_type="speculative_language",
                    severity=severity,
                    location="content",
                    description=f"发现推断性表述：'{keyword}'",
                    recommendation="请确认措辞准确性，必要时弱化表述",
                ))

        matched_clickbait = [term for term in CLICKBAIT_TERMS if term in all_content]
        if matched_clickbait:
            findings.append(RiskFinding(
                risk_type="clickbait_language",
                severity="medium",
                location="content",
                description=f"发现疑似标题党/耸动表达：{', '.join(matched_clickbait[:5])}",
                recommendation="请改为克制、准确、非情绪化表述",
            ))

        matched_absolutist = [term for term in ABSOLUTIST_TERMS if term in all_content]
        if matched_absolutist:
            findings.append(RiskFinding(
                risk_type="trial_by_headline",
                severity="high",
                location="content",
                description=f"发现审判式或绝对化表述：{', '.join(matched_absolutist[:5])}",
                recommendation="请改为有归因、可核查、保留边界的新闻措辞",
            ))

        has_allegation = any(term in all_content for term in ALLEGATION_TERMS)
        has_attribution = any(marker in all_content for marker in ATTRIBUTION_MARKERS)
        has_response = any(marker in all_content for marker in RESPONSE_MARKERS)

        if has_allegation and not has_attribution:
            findings.append(RiskFinding(
                risk_type="missing_attribution",
                severity="high",
                location="content",
                description="涉及指控/质疑/违规等高风险表述，但缺少明确归因来源",
                recommendation="为关键判断补充来源、主体和证据归因，避免把说法写成事实",
            ))

        if has_allegation and not has_response:
            findings.append(RiskFinding(
                risk_type="missing_balance",
                severity="medium",
                location="content",
                description="涉及争议或指控，但文本中缺少当事方回应/求证信息",
                recommendation="补充对方回应、官方口径，或明确说明截至目前仍未获得回应",
            ))

        # 4. Source Vault 泄露检查
        leakage_alerts = await self.check_source_vault_leakage(all_content)
        for alert in leakage_alerts:
            findings.append(RiskFinding(
                risk_type="source_vault_leakage",
                severity="critical",
                location=alert.get("location", "content"),
                description=alert.get("description", "可能泄露匿名源身份"),
                recommendation="立即移除可能暴露匿名源的信息",
            ))
            blockers.append({
                "blocker_id": f"BLK-{uuid.uuid4().hex[:8]}",
                "type": "source_vault_leakage",
                "severity": "critical",
                "description": "可能泄露匿名源身份",
                "resolved": False,
            })

        # 汇总严重程度
        severity_summary = {
            "critical": sum(1 for f in findings if f.severity == "critical"),
            "high": sum(1 for f in findings if f.severity == "high"),
            "medium": sum(1 for f in findings if f.severity == "medium"),
            "low": sum(1 for f in findings if f.severity == "low"),
        }

        # 判断是否可以继续
        can_proceed = len(blockers) == 0

        return Gate3Result(
            story_packet_id="",
            risk_findings=findings,
            blockers=blockers,
            severity_summary=severity_summary,
            can_proceed=can_proceed,
        )

    async def check_source_vault_leakage(self, text: str) -> list[dict]:
        """检查文本是否泄露 Source Vault 中的真实身份"""
        alerts = []

        # 检查是否包含可能暴露匿名源的模式
        exposure_patterns = [
            r"知情人士.*?在.*?任职",
            r"消息人士.*?部门",
            r"匿名.*?透露",
            r"不愿透露姓名.*?表示",
        ]

        for pattern in exposure_patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                alerts.append({
                    "location": "content",
                    "description": f"可能泄露匿名源身份：'{match[:30]}...'",
                    "matched_text": match,
                })

        return alerts

    async def generate_risk_report(
        self, story_packet_id: str, gate3_result: Gate3Result
    ) -> RiskReport:
        """生成风险报告"""
        return RiskReport(
            story_packet_id=story_packet_id,
            findings=gate3_result.risk_findings,
            severity_summary=gate3_result.severity_summary,
            blockers_generated=[b["blocker_id"] for b in gate3_result.blockers],
        )

    async def generate_blockers(self, gate3_result: Gate3Result) -> list[dict]:
        """基于风险扫描结果生成阻塞项"""
        return gate3_result.blockers

    def register_source_vault_alias(self, alias: str, description: str):
        """注册 Source Vault 别名（用于泄露检测）"""
        self._source_vault_aliases[alias] = description


# 全局实例
redaction_risk_agent = RedactionRiskAgent()
