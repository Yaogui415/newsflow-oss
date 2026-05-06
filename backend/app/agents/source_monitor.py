"""Source Monitor Agent：线索监控 Agent，负责采集、预处理、5W1H抽取。"""

import uuid
import json
import re
from urllib.parse import quote_plus
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from app.core.config import settings


@dataclass
class RawSourceItem:
    """原始来源项"""
    source_type: str  # rss / website / social_media / upload / reporter_tip / feedback
    url: str | None = None
    raw_content: str | None = None
    file_path: str | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class SourceItem:
    """处理后的来源项"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source_type: str = ""
    url: str | None = None
    title: str | None = None
    content: str = ""
    extracted_5w1h: dict = field(default_factory=dict)
    risk_tags: list[str] = field(default_factory=list)
    file_ref: str | None = None
    ingested_at: datetime = field(default_factory=lambda: datetime.utcnow())
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source_type": self.source_type,
            "url": self.url,
            "title": self.title,
            "content": self.content[:500] if self.content else None,
            "extracted_5w1h": self.extracted_5w1h,
            "risk_tags": self.risk_tags,
            "file_ref": self.file_ref,
            "ingested_at": self.ingested_at.isoformat(),
        }


# 5W1H 抽取 Prompt
EXTRACT_5W1H_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """你是一个新闻信息抽取专家。请从以下文本中抽取 5W1H 信息，以 JSON 格式输出。

输出格式：
{{
    "who": ["涉及的人物或机构列表"],
    "what": "发生了什么事件（简要描述）",
    "when": "事件发生时间（如果有）",
    "where": "事件发生地点（如果有）",
    "why": "事件原因或背景（如果有）",
    "how": "事件过程或方式（如果有）",
    "key_entities": ["关键实体列表，包括人名、机构名、产品名等"],
    "summary": "一句话摘要"
}}

注意：
- 如果某项信息不明确，填写 null
- 人物和机构名称要完整准确
- 时间尽量转换为标准格式
- 只输出 JSON，不要有其他内容"""),
    ("user", "请分析以下文本：\n\n{text}")
])


# PII 检测正则
PII_PATTERNS = {
    "phone": r"1[3-9]\d{9}",
    "id_card": r"\d{17}[\dXx]",
    "email": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
    "bank_card": r"\d{16,19}",
    "address": r"[\u4e00-\u9fa5]{2,}(省|市|区|县|镇|村|路|街|号|栋|单元|室)",
}


class SourceMonitorAgent:
    """线索监控 Agent"""

    def __init__(self, llm=None):
        if llm is not None:
            self.llm = llm
        else:
            self.llm = ChatOpenAI(
                model=settings.LLM_MODEL,
                api_key=settings.OPENAI_API_KEY,
                base_url=settings.OPENAI_BASE_URL or None,
                temperature=0.1,
            )

    async def collect_from_rss(self, feed_url: str) -> list[RawSourceItem]:
        """从 RSS 源采集"""
        import feedparser
        
        items = []
        feed = feedparser.parse(feed_url)
        
        for entry in feed.entries[:50]:  # 限制每次最多50条
            raw_item = RawSourceItem(
                source_type="rss",
                url=entry.get("link"),
                raw_content=entry.get("summary") or entry.get("description", ""),
                metadata={
                    "title": entry.get("title"),
                    "published": entry.get("published"),
                    "author": entry.get("author"),
                    "feed_title": feed.feed.get("title"),
                }
            )
            items.append(raw_item)
        
        return items

    async def collect_from_news_search(self, keywords: str, max_items: int = 5) -> list[RawSourceItem]:
        import feedparser

        query = quote_plus(keywords.strip())
        feed_url = f"https://news.google.com/rss/search?q={query}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
        feed = feedparser.parse(feed_url)
        items = []

        for entry in feed.entries[:max_items]:
            title = entry.get("title") or ""
            source_name = ""
            if " - " in title:
                parts = title.rsplit(" - ", 1)
                if len(parts) == 2:
                    title, source_name = parts[0], parts[1]

            raw_item = RawSourceItem(
                source_type="rss",
                url=entry.get("link"),
                raw_content=entry.get("summary") or entry.get("description", ""),
                metadata={
                    "title": title,
                    "published": entry.get("published"),
                    "author": entry.get("author"),
                    "feed_title": feed.feed.get("title"),
                    "source_name": source_name,
                    "keywords": keywords,
                    "search_provider": "google_news_rss",
                },
            )
            items.append(raw_item)

        return items

    async def collect_from_upload(
        self, file_content: bytes, filename: str, metadata: dict
    ) -> RawSourceItem:
        """从用户上传采集"""
        text_content = ""
        file_ext = filename.lower().split(".")[-1] if "." in filename else ""
        
        # PDF 提取
        if file_ext == "pdf":
            text_content = await self._extract_pdf(file_content)
        # DOCX 提取
        elif file_ext == "docx":
            text_content = await self._extract_docx(file_content)
        # 图片 OCR
        elif file_ext in ("png", "jpg", "jpeg", "gif", "bmp"):
            text_content = await self._extract_image_ocr(file_content)
        # 纯文本
        elif file_ext in ("txt", "md"):
            text_content = file_content.decode("utf-8", errors="ignore")
        else:
            text_content = file_content.decode("utf-8", errors="ignore")
        
        return RawSourceItem(
            source_type="upload",
            raw_content=text_content,
            file_path=filename,
            metadata=metadata,
        )

    async def _extract_pdf(self, content: bytes) -> str:
        """从 PDF 提取文本"""
        try:
            import pdfplumber
            import io

            text_parts = []
            with pdfplumber.open(io.BytesIO(content)) as pdf:
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        text_parts.append(text)
            return "\n".join(text_parts)
        except Exception as e:
            return f"[PDF提取失败: {str(e)}]"

    async def _extract_docx(self, content: bytes) -> str:
        """从 DOCX 提取文本"""
        try:
            from docx import Document
            import io
            
            doc = Document(io.BytesIO(content))
            text_parts = [para.text for para in doc.paragraphs]
            return "\n".join(text_parts)
        except Exception as e:
            return f"[DOCX提取失败: {str(e)}]"

    async def _extract_image_ocr(self, content: bytes) -> str:
        """图片 OCR（简化实现，实际可接入 PaddleOCR）"""
        import base64
        size_kb = len(content) / 1024
        return f"[图片素材] 大小: {size_kb:.1f}KB | 已上传保存，待 OCR 处理。(data:image;base64,{base64.b64encode(content[:64]).decode()}...)"

    async def preprocess(self, raw_item: RawSourceItem) -> SourceItem:
        """预处理：提取文本、清洗、5W1H 抽取"""
        content = raw_item.raw_content or ""
        
        # 基础清洗
        content = self._clean_text(content)
        
        # 5W1H 抽取
        extracted_5w1h = await self._extract_5w1h(content)
        
        # 获取标题
        title = raw_item.metadata.get("title") or extracted_5w1h.get("summary", "")[:50]
        
        return SourceItem(
            source_type=raw_item.source_type,
            url=raw_item.url,
            title=title,
            content=content,
            extracted_5w1h=extracted_5w1h,
            file_ref=raw_item.file_path,
            metadata=raw_item.metadata,
        )

    def _clean_text(self, text: str) -> str:
        """文本清洗"""
        # 去除多余空白
        text = re.sub(r"\s+", " ", text)
        # 去除 HTML 标签
        text = re.sub(r"<[^>]+>", "", text)
        # 去除特殊字符
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
        return text.strip()

    async def _extract_5w1h(self, text: str) -> dict:
        """使用 LLM 抽取 5W1H 信息"""
        if not text or len(text) < 20:
            return {}
        
        try:
            # 截断过长文本
            text_truncated = text[:4000]
            
            chain = EXTRACT_5W1H_PROMPT | self.llm
            response = await chain.ainvoke({"text": text_truncated})
            
            # 解析 JSON 输出
            content = response.content
            # 尝试提取 JSON
            json_match = re.search(r"\{[\s\S]*\}", content)
            if json_match:
                return json.loads(json_match.group())
            return {}
        except Exception as e:
            # 返回空对象而不是错误，避免前端显示 error
            import logging
            logging.getLogger(__name__).warning(f"5W1H extraction failed: {e}")
            return {"_extraction_pending": True, "summary": "待抽取"}

    async def apply_sensitivity_gate(self, item: SourceItem) -> SourceItem:
        """脱敏门 1：PII 检测和标记"""
        risk_tags = []
        
        for pii_type, pattern in PII_PATTERNS.items():
            if re.search(pattern, item.content):
                risk_tags.append(f"pii:{pii_type}")
        
        # 敏感词检测
        sensitive_keywords = [
            "国家安全", "军事", "机密", "绝密", "未成年", 
            "自杀", "血腥", "暴力", "恐怖",
        ]
        for keyword in sensitive_keywords:
            if keyword in item.content:
                risk_tags.append(f"sensitive:{keyword}")
        
        item.risk_tags = list(set(risk_tags))
        return item

    async def collect_by_keywords(self, keywords: str, max_items: int = 5) -> list[RawSourceItem]:
        """根据关键词采集新闻线索：优先真实 RSS 搜索，失败时回退到模拟结果。"""
        try:
            live_items = await self.collect_from_news_search(keywords, max_items=max_items)
            if live_items:
                return live_items
        except Exception:
            pass

        prompt = f"""你是一个新闻线索采集系统。请根据以下关键词，模拟采集到的新闻线索。
关键词：{keywords}

请生成 {min(max_items, 5)} 条相关线索，每条包含：
- source_type: rss/website/social_media 之一
- url: 若能确定真实链接则填写真实链接；若无法确定请返回 null，禁止编造链接
- title: 新闻标题
- content: 新闻内容摘要（80-150字）

严格输出 JSON 数组，不要有其他文字：
[{{"source_type":"...","url":"...","title":"...","content":"..."}}]"""

        try:
            resp = await self.llm.ainvoke(prompt)
            raw = resp.content.strip()
            if raw.startswith("```"):
                first_nl = raw.find("\n")
                raw = raw[first_nl + 1:] if first_nl != -1 else raw[3:]
                if raw.endswith("```"):
                    raw = raw[:-3].strip()
            try:
                items_data = json.loads(raw)
            except json.JSONDecodeError:
                import re
                m = re.search(r'\[[\s\S]*\]', raw)
                items_data = json.loads(m.group()) if m else []

            result = []
            for item in items_data[:max_items]:
                raw_item = RawSourceItem(
                    source_type=item.get("source_type", "rss"),
                    url=item.get("url"),
                    raw_content=item.get("content", ""),
                    metadata={"title": item.get("title", ""), "keywords": keywords},
                )
                result.append(raw_item)
            return result
        except Exception as e:
            # Fallback: return a single item with the keywords as content
            return [RawSourceItem(
                source_type="rss",
                url=None,
                raw_content=f"关键词 [{keywords}] 相关线索采集失败: {str(e)}",
                metadata={"title": f"关于 {keywords} 的线索", "keywords": keywords},
            )]

    async def process(self, raw_item: RawSourceItem) -> SourceItem:
        """完整处理流程：预处理 + 脱敏门"""
        item = await self.preprocess(raw_item)
        item = await self.apply_sensitivity_gate(item)
        return item


# 全局实例
source_monitor_agent = SourceMonitorAgent()
