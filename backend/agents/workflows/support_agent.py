# 对话编排服务
# 整个对话流程的"指挥中心"：记忆管理、防注入检查、图调用、回复持久化
# presentation/chat.py 的路由只做参数绑定，真正的业务逻辑都在这里

import json
import re
from typing import Optional, AsyncGenerator

from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

from models.llm_providers.deepseek_client import create_llm
from models.prompts.system_prompts import SYSTEM_PROMPT, SESSION_TITLE_PROMPT
from config.constants import SESSION_TITLE_MAX_LEN, MEMORY_COMPRESS_THRESHOLD
from services.guard import check_message
from services.memory import compress_memory_async
from services.security import _tracking_ctx
from infrastructure.database.session import SessionLocal
from infrastructure.database.mapper import ChatHistoryMapper
from infrastructure.database.models import ChatHistory
from infrastructure.cache.redis import redis_client

from langgraph.graph import StateGraph, END
from agents.state.state import AgentState
from agents.nodes.agent_node import agent_node, tool_node, should_continue

from tools.citation import init_citation_ctx, get_citation_ctx


def create_agent_graph():
    """创建 ReAct 模式的 LangGraph 状态图（防注入守卫在 chat.py 层提前拦截）"""
    graph = StateGraph(AgentState)

    graph.add_node("agent", agent_node)
    graph.add_node("tools", tool_node)

    graph.set_entry_point("agent")

    graph.add_conditional_edges(
        "agent",
        should_continue,
        {"tools": "tools", "end": END}
    )

    graph.add_edge("tools", "agent")

    return graph.compile()


agent_graph = create_agent_graph()


def _build_citations(full_reply: str) -> list:
    """从 LLM 回答中解析引用编号，从 citation_map 提取元数据，生成引用来源列表。
    Args:
        full_reply: LLM 的完整回答文本
    Returns:
        引用来源列表 [{"id": 1, "title": "...", "file_name": "..."}, ...]
    """
    ctx = get_citation_ctx()
    if ctx is None or not ctx["map"]:
        return []

    # 匹配正文中所有 [n] 形式的引用编号
    cited_ids = set()
    for m in re.finditer(r'\[(\d+)\]', full_reply):
        cid = int(m.group(1))
        if cid in ctx["map"]:
            cited_ids.add(cid)

    if not cited_ids:
        # 如果 LLM 没有使用任何引用，但工具被调用过，
        # 则展示所有检索到的文档作为参考（给用户提供线索）
        cited_ids = set(ctx["map"].keys())

    items = []
    for cid in sorted(cited_ids):
        meta = ctx["map"][cid]
        items.append({
            "id": cid,
            "title": meta["title"],
            "file_name": meta["file_name"],
        })

    return items


def generate_session_title(message: str) -> str:
    """为新建会话生成标题，基于用户第一条问题。
    - 长度 ≤ 阈值 → 直接用原文
    - 否则 → 调 LLM 总结为短标题
    """
    if len(message) <= SESSION_TITLE_MAX_LEN:
        return message
    try:
        llm = create_llm()
        prompt = SESSION_TITLE_PROMPT.format(message=message)
        title = llm.invoke([HumanMessage(content=prompt)]).content.strip()
        return title[:SESSION_TITLE_MAX_LEN] if title else message[:SESSION_TITLE_MAX_LEN]
    except Exception:
        return message[:SESSION_TITLE_MAX_LEN] + "…"


async def chat_stream_impl(
    userId: str,
    message: str,
    sessionId: Optional[str],
    db: Session
):
    """流式对话的完整编排，返回 SSE StreamingResponse。

    流程：
    1. 从 Redis 加载历史记忆，构建 LangChain 消息列表
    2. 拼接 System Prompt（公司政策问答顾问角色定义）
    3. 保存用户消息到 MySQL
    4. 调用防注入守卫 → 命中则直接返回拒答
    5. 走 LangGraph ReAct 图（agent ⇄ tools），流式 yield LLM token
    6. 保存助手回复到 MySQL + Redis
    7. 超过阈值触发异步记忆压缩

    Args:
        userId: JWT 解析出的用户 ID
        message: 用户输入
        sessionId: 会话 ID，None 则自动生成
        db: 数据库会话（由 FastAPI Depends 注入）
    """
    # ── 1. 初始化会话 ─────────────────────────────────
    session_id = sessionId or f"sess_{userId}_{id(userId)}"
    memory_key = f"{userId}:{session_id}"

    # 新建会话时生成并存储标题
    if not sessionId:
        title = generate_session_title(message)
        redis_client.set(f"session_title:{session_id}", title)

    # ── 2. 加载历史记忆 ───────────────────────────────
    messages = []
    memory_items = redis_client.lrange(memory_key, 0, -1)
    for item in memory_items:
        msg = json.loads(item)
        if msg["role"] == "USER":
            messages.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "ASSISTANT":
            messages.append(AIMessage(content=msg["content"]))
        elif msg["role"] == "SUMMARY":
            # 压缩后的摘要以 SystemMessage 形式注入，帮助 LLM 理解上下文
            messages.append(SystemMessage(content="历史对话摘要：" + msg["content"]))

    # ── 3. 系统提示词 ─────────────────────────────────
    messages.append(SystemMessage(content=SYSTEM_PROMPT))
    messages.append(HumanMessage(content=message))

    # ── 4. 构建图初始状态 + 保存用户消息 ──────────────
    initial_state = {
        "messages": messages,
        "user_id": userId,
        "session_id": session_id,
    }

    user_msg = ChatHistory(
        session_id=session_id, user_id=userId, role="USER", content=message,
        title=title if not sessionId else None  # 仅新建会话时写入标题
    )
    mapper = ChatHistoryMapper(db)
    mapper.save(user_msg)

    async def generate() -> AsyncGenerator[str, None]:
        """SSE 流生成器：逐 token yield 给前端"""
        full_reply = ""
        try:
            # ── 5. 防注入守卫（在图外运行，不污染 astream_events） ──
            is_safe, guard_reply = check_message(message)
            if not is_safe:
                full_reply = guard_reply
                yield f"data: {json.dumps({'type': 'content', 'content': guard_reply}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'type': 'end', 'session_id': session_id}, ensure_ascii=False)}\n\n"
                # 保存 guard 回复
                assistant_msg = ChatHistory(session_id=session_id, user_id=userId, role="ASSISTANT", content=guard_reply)
                mapper.save(assistant_msg)
                redis_client.rpush(memory_key, json.dumps({"role": "USER", "content": message}, ensure_ascii=False))
                redis_client.rpush(memory_key, json.dumps({"role": "ASSISTANT", "content": guard_reply}, ensure_ascii=False))
                return

            # ── 5.5 初始化引用上下文 ────────────────────────
            init_citation_ctx()

            # ── 6. ReAct 图执行（流式） ──
            # 设置追踪上下文，cost tracking callback 据此记录 token/成本
            _tracking_ctx.set({"user_id": userId, "session_id": session_id, "node_type": "agent"})
            async for event in agent_graph.astream_events(initial_state, version="v2", config={"recursion_limit": 8}):
                if event["event"] == "on_chat_model_stream":
                    chunk = event["data"]["chunk"].content
                    if chunk:
                        full_reply += chunk
                        yield f"data: {json.dumps({'type': 'content', 'content': chunk}, ensure_ascii=False)}\n\n"

            # ── 6.5 生成引用来源 ──────────────────────────
            citation_items = _build_citations(full_reply)
            if citation_items:
                yield f"data: {json.dumps({'type': 'citations', 'items': citation_items}, ensure_ascii=False)}\n\n"

            # ── 7. 持久化 ──────────────────────────────
            assistant_msg = ChatHistory(session_id=session_id, user_id=userId, role="ASSISTANT", content=full_reply, citations=citation_items if citation_items else None)
            mapper.save(assistant_msg)
            # Redis 记忆：用户消息 + 助手回复（含引用来源）
            redis_client.rpush(memory_key, json.dumps({"role": "USER", "content": message}, ensure_ascii=False))
            redis_client.rpush(memory_key, json.dumps({"role": "ASSISTANT", "content": full_reply, "citations": citation_items}, ensure_ascii=False))

            # ── 8. 触发记忆压缩 ─────────────────────────
            if redis_client.llen(memory_key) > MEMORY_COMPRESS_THRESHOLD:
                compress_memory_async(memory_key, userId, session_id)

            yield f"data: {json.dumps({'type': 'end', 'session_id': session_id}, ensure_ascii=False)}\n\n"

        except Exception as e:
            print(f"聊天接口异常：{str(e)}")
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"}
    )
