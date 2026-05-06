"""Dedup & Cluster Agent：去重聚类 Agent，负责重复检测和事件聚合。"""

import uuid
import json
import hashlib
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from typing import Any

from langchain_openai import OpenAIEmbeddings

from app.core.config import settings
from app.agents.source_monitor import SourceItem


@dataclass
class Fingerprint:
    """文本指纹"""
    source_item_id: str
    text_hash: str  # SimHash/MinHash
    embedding: list[float] = field(default_factory=list)
    key_entities: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.utcnow())


@dataclass
class MatchCandidate:
    """匹配候选"""
    event_case_id: str
    similarity_score: float
    match_type: str  # semantic / entity / exact
    matched_entities: list[str] = field(default_factory=list)


@dataclass 
class ClusterDecision:
    """聚类判定结果"""
    decision: str  # merge_existing / new_event / suspect_duplicate
    event_case_id: str | None = None
    confidence: float = 0.0
    reason: str = ""


class DedupClusterAgent:
    """去重聚类 Agent"""

    def __init__(self):
        self.embeddings = OpenAIEmbeddings(
            model="text-embedding-3-small",
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL or None,
        )
        # 配置阈值
        self.auto_merge_threshold = 0.92
        self.suspect_duplicate_threshold = 0.78
        self.time_window_hours = 72
        self.min_shared_entities = 2
        
        # 内存中的向量索引（生产环境应使用 Milvus/Qdrant）
        self._vector_index: dict[str, dict] = {}

    def compute_text_hash(self, text: str) -> str:
        """计算文本哈希（简化的 SimHash）"""
        # 实际应使用 simhash 或 minhash 库
        normalized = " ".join(text.lower().split())
        return hashlib.sha256(normalized.encode()).hexdigest()[:16]

    async def compute_fingerprint(self, item: SourceItem) -> Fingerprint:
        """计算文本指纹和语义向量"""
        text_hash = self.compute_text_hash(item.content)
        
        # 计算语义向量
        embedding = []
        if item.content and len(item.content) > 20:
            try:
                embedding = await self.embeddings.aembed_query(item.content[:2000])
            except Exception:
                embedding = []
        
        # 提取关键实体
        key_entities = item.extracted_5w1h.get("key_entities", [])
        if item.extracted_5w1h.get("who"):
            key_entities.extend(item.extracted_5w1h["who"])
        
        return Fingerprint(
            source_item_id=item.id,
            text_hash=text_hash,
            embedding=embedding,
            key_entities=list(set(key_entities)),
            timestamp=item.ingested_at,
        )

    def _cosine_similarity(self, vec1: list[float], vec2: list[float]) -> float:
        """计算余弦相似度"""
        if not vec1 or not vec2 or len(vec1) != len(vec2):
            return 0.0
        
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = sum(a * a for a in vec1) ** 0.5
        norm2 = sum(b * b for b in vec2) ** 0.5
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return dot_product / (norm1 * norm2)

    async def find_candidates(
        self, fingerprint: Fingerprint, existing_events: list[dict]
    ) -> list[MatchCandidate]:
        """检索候选匹配"""
        candidates = []
        cutoff_time = datetime.utcnow() - timedelta(hours=self.time_window_hours)
        
        for event in existing_events:
            # 时间窗口过滤
            event_time = event.get("created_at")
            if event_time and isinstance(event_time, datetime):
                if event_time < cutoff_time:
                    continue
            
            # 语义相似度
            event_embedding = event.get("embedding", [])
            semantic_score = self._cosine_similarity(fingerprint.embedding, event_embedding)
            
            # 实体匹配
            event_entities = set(event.get("key_entities", []))
            shared_entities = set(fingerprint.key_entities) & event_entities
            entity_score = len(shared_entities) / max(len(fingerprint.key_entities), 1)
            
            # 综合得分
            combined_score = semantic_score * 0.7 + entity_score * 0.3
            
            if combined_score >= self.suspect_duplicate_threshold:
                match_type = "semantic" if semantic_score > entity_score else "entity"
                candidates.append(MatchCandidate(
                    event_case_id=event.get("id"),
                    similarity_score=combined_score,
                    match_type=match_type,
                    matched_entities=list(shared_entities),
                ))
        
        # 按相似度降序排序
        candidates.sort(key=lambda x: x.similarity_score, reverse=True)
        return candidates[:10]  # 返回 Top 10

    async def decide_cluster(
        self, item: SourceItem, candidates: list[MatchCandidate]
    ) -> ClusterDecision:
        """判定归属：已有事件 / 新事件 / 疑似重复"""
        if not candidates:
            return ClusterDecision(
                decision="new_event",
                confidence=1.0,
                reason="无匹配候选，创建新事件"
            )
        
        top_candidate = candidates[0]
        
        # 高置信度匹配 → 自动归入
        if top_candidate.similarity_score >= self.auto_merge_threshold:
            return ClusterDecision(
                decision="merge_existing",
                event_case_id=top_candidate.event_case_id,
                confidence=top_candidate.similarity_score,
                reason=f"高相似度匹配 ({top_candidate.similarity_score:.2f})，自动归入"
            )
        
        # 中置信度匹配 → 疑似重复
        if top_candidate.similarity_score >= self.suspect_duplicate_threshold:
            return ClusterDecision(
                decision="suspect_duplicate",
                event_case_id=top_candidate.event_case_id,
                confidence=top_candidate.similarity_score,
                reason=f"中等相似度 ({top_candidate.similarity_score:.2f})，需人工确认"
            )
        
        # 无足够匹配 → 新事件
        return ClusterDecision(
            decision="new_event",
            confidence=1.0 - top_candidate.similarity_score,
            reason="相似度不足，创建新事件"
        )

    async def index_event(self, event_id: str, embedding: list[float], key_entities: list[str]):
        """将事件加入索引"""
        self._vector_index[event_id] = {
            "id": event_id,
            "embedding": embedding,
            "key_entities": key_entities,
            "created_at": datetime.utcnow(),
        }

    async def get_indexed_events(self) -> list[dict]:
        """获取所有已索引事件（用于匹配）"""
        return list(self._vector_index.values())

    async def process(
        self, item: SourceItem, existing_events: list[dict] | None = None
    ) -> tuple[ClusterDecision, Fingerprint]:
        """完整处理流程"""
        # 1. 计算指纹
        fingerprint = await self.compute_fingerprint(item)
        
        # 2. 获取已有事件
        if existing_events is None:
            existing_events = await self.get_indexed_events()
        
        # 3. 查找候选
        candidates = await self.find_candidates(fingerprint, existing_events)
        
        # 4. 判定聚类
        decision = await self.decide_cluster(item, candidates)
        
        return decision, fingerprint


# 全局实例
dedup_cluster_agent = DedupClusterAgent()
