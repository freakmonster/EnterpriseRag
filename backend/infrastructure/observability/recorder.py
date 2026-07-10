# DB 写入 + 手动埋点函数
# record_llm_call: 同步版，供同步上下文使用（tools.py 的 rerank 埋点）
# async_record_llm_call: 异步版，把同步 DB 写丢进线程池，不阻塞事件循环
import asyncio
import json
from pathlib import Path

from infrastructure.database.session import SessionLocal
from infrastructure.database.models import LLMCallLog


_pricing = None


def _load_pricing():
    global _pricing
    if _pricing is None:
        path = Path(__file__).parent / "pricing.json"
        _pricing = json.loads(path.read_text(encoding="utf-8"))


def _calc_cost(model_name: str, input_tokens: int, output_tokens: int) -> float:
    _load_pricing()
    price = _pricing.get(model_name)
    if not price:
        return 0.0
    return (input_tokens * price["input"] + output_tokens * price["output"]) / 1000


def _sync_write(**kwargs):
    """同步 DB 写入，会被 run_in_executor 丢到线程池执行"""
    db = SessionLocal()
    try:
        log = LLMCallLog(**kwargs)
        db.add(log)
        db.commit()
    finally:
        db.close()


def record_llm_call(
    user_id: str,
    session_id: str,
    model_name: str,
    model_type: str,
    node_type: str,
    input_tokens: int,
    output_tokens: int,
    latency_ms: int,
    status: str = "success",
    error_msg: str | None = None,
):
    """同步写入（供 tools.py 等同步上下文调用）"""
    _sync_write(
        user_id=user_id, session_id=session_id,
        model_name=model_name, model_type=model_type, node_type=node_type,
        input_tokens=input_tokens, output_tokens=output_tokens,
        latency_ms=latency_ms,
        cost=_calc_cost(model_name, input_tokens, output_tokens),
        status=status, error_msg=error_msg,
    )


async def async_record_llm_call(
    user_id: str,
    session_id: str,
    model_name: str,
    model_type: str,
    node_type: str,
    input_tokens: int,
    output_tokens: int,
    latency_ms: int,
    status: str = "success",
    error_msg: str | None = None,
):
    """异步写入：把同步 DB 操作丢进线程池，不阻塞事件循环"""
    cost = _calc_cost(model_name, input_tokens, output_tokens)
    # functools.partial + **kwargs 避免 run_in_executor 传参问题
    from functools import partial
    fn = partial(_sync_write,
        user_id=user_id, session_id=session_id,
        model_name=model_name, model_type=model_type, node_type=node_type,
        input_tokens=input_tokens, output_tokens=output_tokens,
        latency_ms=latency_ms, cost=cost,
        status=status, error_msg=error_msg,
    )
    await asyncio.get_running_loop().run_in_executor(None, fn)


def track_embedding(
    user_id: str,
    session_id: str,
    model_name: str,
    model_type: str,
    node_type: str,
    input_tokens: int,
):
    """手动记录 DashScope SDK 调用（同步上下文，不走 LangChain callback）"""
    record_llm_call(
        user_id=user_id, session_id=session_id,
        model_name=model_name, model_type=model_type, node_type=node_type,
        input_tokens=input_tokens, output_tokens=0, latency_ms=0,
    )
