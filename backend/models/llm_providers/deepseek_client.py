# LLM 工厂 — 统一管理模型实例创建
from langchain_openai import ChatOpenAI

from config.settings import settings
from infrastructure.observability.callback import tracking_callback


def create_llm(temperature: float = 0.7) -> ChatOpenAI:
    """统一 LLM 工厂，参数化 temperature，自动挂载成本追踪回调"""
    return ChatOpenAI(
        model=settings.deepseek_model,
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        temperature=temperature,
        callbacks=[tracking_callback],
    )
