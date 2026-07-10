# 引用来源上下文管理
# 使用 contextvars.ContextVar 在线程/协程间传递 citation_map 和计数器
# 模式与 services/security.py 中的 _tracking_ctx 一致
import contextvars
from typing import Dict, List, Optional

# 引用上下文：存储全局计数器 + 编号→元数据映射表
# 格式: {"counter": 0, "map": {1: {"title": "...", "file_name": "...", "chunk_idx": 0}, ...}}
_citation_ctx: contextvars.ContextVar = contextvars.ContextVar('citation', default=None)


def init_citation_ctx() -> Dict:
    """初始化引用上下文，返回可变 dict"""
    ctx = {"counter": 0, "map": {}}
    _citation_ctx.set(ctx)
    return ctx


def get_citation_ctx() -> Optional[Dict]:
    """获取当前引用上下文"""
    return _citation_ctx.get()


def format_and_record(docs: List[dict]) -> str:
    """
    为检索结果分配全局唯一编号，记录到 citation_map，返回格式化文本。
    Args:
        docs: 检索结果列表，每项为 {"content": "...", "metadata": {"title": ..., "file_name": ..., "chunk_idx": ...}}
    Returns:
        格式化文本，每块以 [n] 标题 开头
    """
    ctx = _citation_ctx.get()
    if ctx is None:
        # 无引用上下文时回退到原始行为（纯文本拼接）
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
