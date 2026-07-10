# 对话 API 路由
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.schemas.chat import ChatRequest
from services.security import get_current_user
from services.quota import check_quota
from agents.workflows.support_agent import chat_stream_impl
from infrastructure.database.session import SessionLocal, get_db
from infrastructure.database.mapper import ChatHistoryMapper
from infrastructure.cache.redis import redis_client

router = APIRouter()


@router.post("/chat")
async def chat(
    request: ChatRequest,
    user_id: str = Depends(get_current_user),
    quota_info: dict = Depends(check_quota),
    db: Session = Depends(get_db)
):
    """流式对话接口"""
    return await chat_stream_impl(user_id, request.message, request.sessionId, db)


@router.get("/history")
def get_history(session_id: str, user_id: str = Depends(get_current_user)):
    """获取指定会话的历史消息"""
    db = SessionLocal()
    mapper = ChatHistoryMapper(db)
    history = mapper.list_by_session_id(session_id)
    db.close()
    return history


@router.get("/sessions")
def get_sessions(user_id: str = Depends(get_current_user)):
    """获取用户的会话列表，含标题，按最后消息时间倒序"""
    db = SessionLocal()
    mapper = ChatHistoryMapper(db)
    sessions = mapper.list_session_ids_by_user_id(user_id)
    db.close()
    result = []
    for sid in sessions:
        title = redis_client.get(f"session_title:{sid}")
        result.append({"session_id": sid, "title": title or sid})
    return result
