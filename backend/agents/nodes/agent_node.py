# LangGraph节点实现 - ReAct模式
from typing import Literal
from langgraph.prebuilt import ToolNode

from models.llm_providers.deepseek_client import create_llm
from tools.registry import tools


def agent_node(state):
    """Agent节点：调用LLM决定下一步"""
    llm = create_llm().bind_tools(tools)
    messages = state["messages"]
    response = llm.invoke(messages)
    return {"messages": [response]}


def should_continue(state) -> Literal["tools", "end"]:
    """路由：判断是否需要调用工具"""
    messages = state["messages"]
    last_message = messages[-1]
    if last_message.tool_calls:
        return "tools"
    return "end"


tool_node = ToolNode(tools, handle_tool_errors=True)
