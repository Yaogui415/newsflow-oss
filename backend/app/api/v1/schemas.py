"""API v1 共享响应模型。"""

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    code: str
    message: str
    status: int
    details: dict
