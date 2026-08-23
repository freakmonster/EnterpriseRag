# DB 写入 + 手动埋点函数
# record_llm_call: 同步版，供同步上下文使用（tools.py 的 rerank 埋点）
# async_record_llm_call: 异步版，把同步 DB 写丢进线程池，不阻塞事件循环
import asyncio
import json
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from infrastructure.database.session import SessionLocal
from infrastructure.database.models import LLMCallLog


_pricing = None

# 北京时间（DeepSeek 峰谷计费以北京时间为准）
CN_TZ = ZoneInfo("Asia/Shanghai")


def _load_pricing():
    global _pricing
    if _pricing is None:
        path = Path(__file__).parent / "pricing.json"
        _pricing = json.loads(path.read_text(encoding="utf-8"))


def _is_peak(when: datetime) -> bool:
    """判断是否为高峰时段：工作日（周一至周五）9:00-12:00、14:00-18:00，其余含周末为低谷"""
    if when.weekday() >= 5:  # 周六、周日全天低谷价
        return False
    t = when.time()
    return (time(9, 0) <= t < time(12, 0)) or (time(14, 0) <= t < time(18, 0))


def _calc_cost(
    model_name: str,
    input_tokens: int,
    output_tokens: int,
    cache_hit_tokens: int = 0,
    when: datetime | None = None,
) -> float:
    """按模型价格计算成本。

    新格式（dict）：区分高峰/低谷 + 缓存命中/未命中，例如 deepseek-v4-flash。
    旧格式（数字）：固定单价，输入/输出直接相乘（如 embedding / rerank）。
    """
    _load_pricing()
    price = _pricing.get(model_name)
    if not price:
        return 0.0
    when = when or datetime.now(CN_TZ)
    peak = _is_peak(when)
    if isinstance(price.get("input"), dict):
        cache_miss = max(input_tokens - cache_hit_tokens, 0)
        in_price = price["input"]["peak" if peak else "offpeak"]
        hit_price = price["input_cache_hit"]["peak" if peak else "offpeak"]
        out_price = price["output"]["peak" if peak else "offpeak"]
        return (cache_miss * in_price + cache_hit_tokens * hit_price + output_tokens * out_price) / 1000
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
    cache_hit_tokens: int = 0,
    cache_miss_tokens: int | None = None,
):
    """同步写入（供 tools.py 等同步上下文调用）"""
    cache_miss = input_tokens - cache_hit_tokens if cache_miss_tokens is None else cache_miss_tokens
    _sync_write(
        user_id=user_id, session_id=session_id,
        model_name=model_name, model_type=model_type, node_type=node_type,
        input_tokens=input_tokens, output_tokens=output_tokens,
        input_cache_hit_tokens=cache_hit_tokens, input_cache_miss_tokens=cache_miss,
        latency_ms=latency_ms,
        cost=_calc_cost(model_name, input_tokens, output_tokens, cache_hit_tokens),
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
    cache_hit_tokens: int = 0,
    cache_miss_tokens: int | None = None,
):
    """异步写入：把同步 DB 操作丢进线程池，不阻塞事件循环"""
    cache_miss = input_tokens - cache_hit_tokens if cache_miss_tokens is None else cache_miss_tokens
    cost = _calc_cost(model_name, input_tokens, output_tokens, cache_hit_tokens)
    # functools.partial + **kwargs 避免 run_in_executor 传参问题
    from functools import partial
    fn = partial(_sync_write,
        user_id=user_id, session_id=session_id,
        model_name=model_name, model_type=model_type, node_type=node_type,
        input_tokens=input_tokens, output_tokens=output_tokens,
        input_cache_hit_tokens=cache_hit_tokens, input_cache_miss_tokens=cache_miss,
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
