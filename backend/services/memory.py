# 记忆管理领域服务 — 对话压缩
import json
import threading

from langchain_core.messages import HumanMessage

from config.constants import MEMORY_COMPRESS_THRESHOLD, MEMORY_KEEP_LAST_N
from models.llm_providers.deepseek_client import create_llm
from models.prompts.system_prompts import MEMORY_COMPRESS_PROMPT
from infrastructure.cache.redis import redis_client
from services.security import _tracking_ctx


def compress_memory_async(memory_key: str, user_id: str, session_id: str):
    """超过阈值条消息时，将历史对话压缩为一条摘要，异步执行不阻塞响应。

    压缩策略：保留最后 N 条，前面的全部用 LLM 总结成一条 SUMMARY。
    Redis Lua 脚本原子替换整个列表，避免并发问题。

    Args:
        memory_key: Redis key，格式 "{user_id}:{session_id}"
        user_id: 当前用户 ID
        session_id: 当前会话 ID
    """
    import contextvars
    ctx_copy = contextvars.copy_context()

    def task():
        # 设置追踪上下文，让 cost tracking callback 能记录这次 LLM 调用
        _tracking_ctx.set({"user_id": user_id, "session_id": session_id, "node_type": "compress"})

        memory_items = redis_client.lrange(memory_key, 0, -1)
        if len(memory_items) <= MEMORY_COMPRESS_THRESHOLD:
            return

        # 保留最后 N 条消息，前面的全部压缩
        split_idx = max(0, len(memory_items) - MEMORY_KEEP_LAST_N)
        to_summarize = memory_items[:split_idx]
        to_keep = memory_items[split_idx:]

        # 组装历史文本，调用 LLM 生成摘要
        history_text = "\n".join([
            f"{json.loads(item)['role']}: {json.loads(item)['content']}"
            for item in to_summarize
        ])
        summary_prompt = MEMORY_COMPRESS_PROMPT.format(history_text=history_text)
        llm = create_llm()
        summary = llm.invoke([HumanMessage(content=summary_prompt)]).content

        # Lua 脚本：原子地删除旧列表 + 写入摘要 + 保留最后 N 条
        lua_script = """
                    redis.call('DEL', KEYS[1])
                    for i=1, #ARGV do
                        redis.call('RPUSH', KEYS[1], ARGV[i])
                    end
                    """
        new_items = [json.dumps({"role": "SUMMARY", "content": summary}, ensure_ascii=False)] + to_keep
        redis_client.eval(lua_script, 1, memory_key, *new_items)

    # contextvars.copy_context().run() 确保后台线程能读取到调用方的上下文
    thread = threading.Thread(target=ctx_copy.run, args=(task,), daemon=True)
    thread.start()
