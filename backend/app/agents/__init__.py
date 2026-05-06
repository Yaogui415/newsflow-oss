"""Agent 模块导出（延迟导入，避免在精简部署环境下因缺少 ML 依赖而崩溃）。"""

__all__ = [
    "source_monitor_agent",
    "dedup_cluster_agent",
    "triage_agent",
    "evidence_structuring_agent",
    "relationship_investigation_agent",
    "verification_agent",
    "redaction_risk_agent",
    "audit_agent",
    "drafting_agent",
    "channel_adaptation_agent",
    "orchestrator_agent",
    "post_publish_monitor",
]


def __getattr__(name: str):
    """Lazy import：仅在实际使用时才导入对应 agent 模块。"""
    _map = {
        "source_monitor_agent": ("app.agents.source_monitor", "source_monitor_agent"),
        "dedup_cluster_agent": ("app.agents.dedup_cluster", "dedup_cluster_agent"),
        "triage_agent": ("app.agents.triage", "triage_agent"),
        "evidence_structuring_agent": ("app.agents.evidence_structuring", "evidence_structuring_agent"),
        "relationship_investigation_agent": ("app.agents.relationship_investigation", "relationship_investigation_agent"),
        "verification_agent": ("app.agents.verification", "verification_agent"),
        "redaction_risk_agent": ("app.agents.redaction_risk", "redaction_risk_agent"),
        "audit_agent": ("app.agents.audit", "audit_agent"),
        "drafting_agent": ("app.agents.drafting", "drafting_agent"),
        "channel_adaptation_agent": ("app.agents.channel_adaptation", "channel_adaptation_agent"),
        "orchestrator_agent": ("app.agents.orchestrator", "orchestrator_agent"),
        "post_publish_monitor": ("app.agents.post_publish_monitor", "post_publish_monitor"),
    }
    if name in _map:
        import importlib
        module_path, attr = _map[name]
        mod = importlib.import_module(module_path)
        return getattr(mod, attr)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
