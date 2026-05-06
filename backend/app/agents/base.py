"""Agent 基类：定义所有 Agent 的公共接口和行为规范。"""

import uuid
import hashlib
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings


class AgentResult:
    """Agent 执行结果的标准封装。"""

    def __init__(
        self,
        success: bool,
        data: Any = None,
        error: str | None = None,
        ai_usage: dict | None = None,
    ):
        self.success = success
        self.data = data
        self.error = error
        self.ai_usage = ai_usage  # {model, prompt_hash, input_tokens, output_tokens, latency_ms}


class BaseAgent(ABC):
    """
    所有专业 Agent 的基类。

    规范：
    - 每个 Agent 必须定义明确的输入/输出 Schema
    - 每个 Agent 必须有独立的错误处理和超时机制
    - 每个 Agent 的 LLM 调用必须记录 prompt、response、token 用量
    - LLM 输出永远只是"辅助建议"，不是"自动决策"
    """

    agent_name: str = "base"
    default_model: str = settings.LLM_DEFAULT_MODEL
    default_temperature: float = settings.LLM_TEMPERATURE_DEFAULT
    max_retries: int = 2
    timeout_seconds: int = 300

    @abstractmethod
    async def execute(self, **kwargs) -> AgentResult:
        """执行 Agent 的核心逻辑。子类必须实现。"""
        ...

    def _build_ai_usage_record(
        self,
        model: str,
        prompt_template_id: str,
        input_tokens: int,
        output_tokens: int,
        latency_ms: int,
    ) -> dict:
        """构建 AI 使用记录，用于审计日志。"""
        return {
            "agent_name": self.agent_name,
            "model": model,
            "prompt_template_id": prompt_template_id,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "latency_ms": latency_ms,
            "timestamp": datetime.utcnow().isoformat(),
        }

    @staticmethod
    def _hash_prompt(prompt: str) -> str:
        """计算 Prompt 哈希，用于审计追溯。"""
        return hashlib.sha256(prompt.encode()).hexdigest()[:16]

    @staticmethod
    def _sanitize_input(text: str) -> str:
        """
        输入消毒：防止来源材料中的 Prompt 注入。
        （问题 5 修改意见落实）
        """
        boundary = f"<user_content id='{uuid.uuid4().hex[:8]}'>"
        boundary_end = "</user_content>"
        sanitized = text.replace(boundary, "").replace(boundary_end, "")
        return f"{boundary}\n{sanitized}\n{boundary_end}"
