# 引用来源上下文管理
# 使用 threading.Lock 保护的模块级 dict + contextvars.ContextVar 传递 session key
# 设计：检索工具改为 async def，ToolNode 会 await tool.ainvoke() 而非 asyncio.to_thread，
#       contextvars 在 async 上下文中正常传播，工具可通过 get_session_key() 获取 key
import contextvars
import threading
from typing import Dict, List, Optional

# 引用存储：key → {"counter": 0, "map": {id: {title, file_name, chunk_idx}}}
_storage: Dict[str, dict] = {}
_lock = threading.Lock()

# ContextVar 用于在 async 上下文中传递当前 session key
# 工具改为 async 后，不再经过线程池，ContextVar 可正常传播
_session_key: contextvars.ContextVar[str] = contextvars.ContextVar('citation_session_key', default='')


def init_storage(key: str) -> dict:
    """初始化引用存储，返回可变 dict"""
    ctx = {"counter": 0, "map": {}}
    with _lock:
        _storage[key] = ctx
    return ctx


def get_storage(key: str) -> Optional[dict]:
    """获取引用存储"""
    return _storage.get(key)


def cleanup_storage(key: str) -> None:
    """清理引用存储"""
    with _lock:
        _storage.pop(key, None)


def set_session_key(key: str) -> None:
    """设置当前 async 上下文中的 session key（在 astream_events 前调用）"""
    _session_key.set(key)


def get_session_key() -> str:
    """获取当前 async 上下文中的 session key"""
    return _session_key.get()


def format_and_record(docs: List[dict], key: str = "") -> str:
    """
    为检索结果分配全局唯一编号，记录到 storage，返回格式化文本。
    Args:
        docs: 检索结果列表，每项为 {"content": "...", "metadata": {"title": ..., "file_name": ..., "chunk_idx": ...}}
        key: 存储 key（通常为 session_id），为空则回退到纯文本拼接
    Returns:
        格式化文本，每块以 [n] 标题 开头
    """
    # 如果未显式传 key，从 ContextVar 读取（async 工具路径）
    effective_key = key or get_session_key()
    if not effective_key:
        return "\n\n".join([doc["content"] for doc in docs])

    with _lock:
        ctx = _storage.get(effective_key)
        if ctx is None:
            return "\n\n".join([doc["content"] for doc in docs])

        parts = []
        for doc in docs:
            ctx["counter"] += 1
            cid = ctx["counter"]
            meta = doc["metadata"]
            title = meta.get("title", meta.get("file_name", "未知文档"))
            ctx["map"][cid] = {
                "title": title,
                "file_name": meta.get("file_name", ""),
                "chunk_idx": meta.get("chunk_idx", 0),
            }
            parts.append(f"[{cid}] {title}\n{doc['content']}")

        return "\n\n".join(parts)
