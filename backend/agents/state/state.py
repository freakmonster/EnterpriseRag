# LangGraph状态定义
from typing import TypedDict, Annotated, Sequence
from langchain_core.messages import BaseMessage
import operator


class AgentState(TypedDict):
    """Agent执行过程中的状态数据"""
    messages: Annotated[Sequence[BaseMessage], operator.add]
    user_id: str
    session_id: str
