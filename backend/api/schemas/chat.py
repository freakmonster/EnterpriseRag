from pydantic import BaseModel, Field
from typing import Optional


class ChatRequest(BaseModel):
    """前端发来的对话请求"""
    message: str = Field(..., description="用户消息内容")
    sessionId: Optional[str] = Field(None, description="会话ID，可选，用于会话续传")
