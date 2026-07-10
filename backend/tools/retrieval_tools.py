# 检索工具
from dashscope import TextReRank
from langchain_core.tools import tool

from retrieval.retrievers.bm25_retriever import bm25_search
from retrieval.vectorstores.chroma_store import search, search_no_rerank
from config.settings import settings
from infrastructure.observability.recorder import track_embedding
from services.security import _tracking_ctx
from tools.citation import format_and_record


@tool
def simple_retrieve_policy(query: str) -> str:
    """搜索公司政策文档，回答用户关于政策、规定、制度的问题。
    用于简单的或简单口语化的用户问题，对问题进行简单的直接改写 或者 HyDE 改写作为参数传入即可
    Args:
        query: 改写后的用户的问题，如"请假需要提前几天申请？"
    """
    print("提问：", query)
    results = search(query, top_k=3)
    return format_and_record(results)

@tool
def es_retrieve_policy(query: str) -> str:
    """搜索公司政策文档，回答用户关于政策、规定、制度问题。
    用于复杂、需要跨多个文档搜索的用户问题，仅做 ES 检索（关键词）。
    你需要先调用工具，查看 BM25 改写指导.txt
    Args:
        query: BM25 改写后的句子
    """
    print("提问：", query)
    results = bm25_search(query, top_k=3)
    return format_and_record(results)

@tool
def complex_retrieve_policy(vec_queries: list, bm25_query: str) -> str:
    """搜索公司政策文档，回答用户关于政策、规定、制度的问题。
    用于复杂的、需要跨多个文档搜索的用户问题，包含向量检索和 ES 检索（关键词）。
    你需要先调用工具，查看 多Query改写指导.txt 和 BM25 改写指导.txt
    Args:
        vec_queries: 多 query 改写后的 query 列表，用于向量检索
        bm25_query: BM25 改写后的句子
    """
    results = multi_retrieve_v2(vec_queries, bm25_query)
    return format_and_record(results)


def _track_rerank(response):
    """记录 rerank 调用的 token 消耗"""
    ctx = _tracking_ctx.get()
    if not ctx or not ctx.get("user_id"):
        return
    usage = response.usage
    track_embedding(
        user_id=ctx["user_id"],
        session_id=ctx.get("session_id") or "",
        model_name="qwen3-vl-rerank",
        model_type="rerank",
        node_type="query",
        input_tokens=usage.input_tokens or 0,
    )


def multi_retrieve_v2(vec_queries, bm25_query, retrieve_top_k=10, rerank_top_k=2) -> list:
    """
    每个query独立检索+用自己的query精排，各取top2，合并去重
    """
    seen = set()
    merged_docs = []

    # 向量检索：3个扩展query，每个独立检索+精排
    for query in vec_queries:
        vec_results = search_no_rerank(query, 5)
        if vec_results:
            # 用该query精排
            doc_texts = [doc["content"] for doc in vec_results]
            response = TextReRank.call(
                model="qwen3-vl-rerank",
                query=query,
                documents=doc_texts,
                top_n=2,
                api_key=settings.dashscope_api_key,
            )
            _track_rerank(response)
            for result in response.output.results:
                idx = result.index
                if idx < len(vec_results):
                    doc = vec_results[idx]
                    key = (doc["metadata"]["file_name"], doc["metadata"]["chunk_idx"])
                    if key not in seen:
                        seen.add(key)
                        merged_docs.append(doc)

    # BM25检索：1个query，独立检索+精排
    es_results = bm25_search(bm25_query, 10)
    if es_results:
        doc_texts = [doc["content"] for doc in es_results]
        response = TextReRank.call(
            model="qwen3-vl-rerank",
            query=vec_queries[0],
            documents=doc_texts,
            top_n=2,
            api_key=settings.dashscope_api_key,
        )
        _track_rerank(response)
        for result in response.output.results:
            idx = result.index
            if idx < len(es_results):
                doc = es_results[idx]
                key = (doc["metadata"]["file_name"], doc["metadata"]["chunk_idx"])
                if key not in seen:
                    seen.add(key)
                    merged_docs.append(doc)

    return merged_docs
