# 数据库模型
from sqlalchemy import Column, Integer, String, Text, DateTime, Float, func
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class ChatHistory(Base):
    """对话历史实体"""
    __tablename__ = "chat_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), nullable=False, index=True)
    user_id = Column(String(50), nullable=False)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class User(Base):
    """用户实体"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), nullable=False, unique=True)
    password_hash = Column(String(200), nullable=False)
    role = Column(String(20), nullable=False, default="user")
    created_at = Column(DateTime, server_default=func.now())


class RoleQuotaConfig(Base):
    """角色配额配置（管理员可调）"""
    __tablename__ = "role_quota_config"

    role = Column(String(20), primary_key=True)
    daily_requests = Column(Integer, nullable=False)
    daily_tokens = Column(Integer, nullable=False)
    rpm_requests = Column(Integer, nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class LLMCallLog(Base):
    """LLM 调用日志"""
    __tablename__ = "llm_call_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), nullable=False)
    session_id = Column(String(128), nullable=False)
    model_name = Column(String(64), nullable=False)
    model_type = Column(String(20), nullable=False)
    node_type = Column(String(20), nullable=False)
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    latency_ms = Column(Integer, default=0)
    cost = Column(Float, default=0.0)
    status = Column(String(10), default="success")
    error_msg = Column(String(256), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
