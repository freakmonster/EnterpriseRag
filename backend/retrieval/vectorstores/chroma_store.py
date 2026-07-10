# 向量检索
# 使用LlamaIndex + ChromaDB进行政策文档的向量存储和检索
# 通过 is_gray 元数据区分线上/灰度数据，支持 Nacos 控制渐进式流量分流
from typing import List, Optional

import chromadb
from dashscope.rerank.text_rerank import TextReRank
from llama_index.core import VectorStoreIndex, Settings
from llama_index.core.schema import TextNode
from llama_index.embeddings.dashscope import DashScopeEmbedding
from llama_index.vector_stores.chroma import ChromaVectorStore

from config.settings import settings as app_settings
from infrastructure.cache.redis import redis_client
from infrastructure.config.gray import gray_config
from infrastructure.observability.recorder import track_embedding
from services.security import _tracking_ctx

# LlamaIndex 全局 embedding 配置
Settings.embed_model = DashScopeEmbedding(
    model_name=app_settings.dashscope_embedding_model
)


def _track_rerank_inline(response):
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


def _track_embedding_inline(model_name: str, query_len: int):
    """记录 embedding 调用（估算 token = 查询字符数）"""
    ctx = _tracking_ctx.get()
    if not ctx or not ctx.get("user_id"):
        return
    track_embedding(
        user_id=ctx["user_id"],
        session_id=ctx.get("session_id") or "",
        model_name=model_name,
        model_type="embedding",
        node_type="query",
        input_tokens=query_len,  # 粗略估算
    )

# ChromaDB 持久化客户端
_chroma_client = chromadb.PersistentClient(path=app_settings.chroma_db_path)

# 固定 collection 名
COLLECTION_NAME = "policies"

# 模块加载时初始化
# embedding_function=None：禁用 ChromaDB 内置的 ONNX 本地 embedding，
# 本项目使用 LlamaIndex + DashScope API 生成向量，存入时已有 embedding
_collection = _chroma_client.get_or_create_collection(
    COLLECTION_NAME, embedding_function=None
)
_vs = ChromaVectorStore(chroma_collection=_collection)
index = VectorStoreIndex.from_vector_store(vector_store=_vs)


def insert_chunks(chunks: List[dict], is_gray: bool = False):
    """插入 chunks 到 collection（LlamaIndex 自动生成 embedding）"""
    if not chunks:
        return
    nodes = [
        TextNode(
            text=chunk["content"],
            metadata={
                "title": chunk.get("title", ""),
                "file_name": chunk["file_name"],
                "chunk_idx": chunk["chunk_idx"],
                "is_gray": is_gray,
            },
            id_=f"{chunk['file_name']}::{chunk['chunk_idx']}",
        )
        for chunk in chunks
    ]
    index.insert_nodes(nodes)


def delete_chunks_by_file(file_name: str, is_gray: Optional[bool] = None):
    """删除指定文件的 chunks，可选按 is_gray 过滤"""
    if is_gray is not None:
        where = {"$and": [{"file_name": file_name}, {"is_gray": is_gray}]}
    else:
        where = {"file_name": file_name}
    results = _collection.get(where=where)
    if results["ids"]:
        _collection.delete(ids=results["ids"])


def update_is_gray(file_name: str, from_value: bool, to_value: bool):
    """将指定文件 chunks 的 is_gray 从 from_value 更新为 to_value"""
    results = _collection.get(
        where={"$and": [{"file_name": file_name}, {"is_gray": from_value}]}
    )
    if not results["ids"]:
        return
    new_metadatas = []
    for meta in results["metadatas"]:
        new_meta = dict(meta)
        new_meta["is_gray"] = to_value
        new_metadatas.append(new_meta)
    _collection.update(ids=results["ids"], metadatas=new_metadatas)


def _get_gray_files() -> list:
    """读取 Redis 中的灰度文件名集合"""
    return list(redis_client.smembers("policies:gray:files"))


def _build_where_clause(gray_traffic: bool) -> dict:
    """
    构建 ChromaDB where 过滤条件

    gray_traffic=False (正常/线上流量):
      {"is_gray": False}

    gray_traffic=True (灰度流量):
      灰度文件走新版本(is_gray=True)，非灰度文件走旧版本(is_gray=False)
      {
        "$or": [
          {"$and": [{"is_gray": False}, {"file_name": {"$nin": gray_files}}]},
          {"$and": [{"is_gray": True},  {"file_name": {"$in":  gray_files}}]}
        ]
      }
    """
    if not gray_traffic:
        return {"is_gray": False}

    gray_files = _get_gray_files()
    if not gray_files:
        return {"is_gray": False}

    return {
        "$or": [
            {"$and": [{"is_gray": False}, {"file_name": {"$nin": gray_files}}]},
            {"$and": [{"is_gray": True}, {"file_name": {"$in": gray_files}}]},
        ]
    }


def search(query: str, top_k: int = 5, is_gray: Optional[bool] = None) -> List[dict]:
    """
    搜索相关文档（向量初检 → DashScope Rerank → 返回 top_k）

    Args:
        is_gray: None=通过 Nacos 自动分流, True=强制灰度, False=强制线上
    """
    if is_gray is None:
        is_gray = gray_config.is_gray_traffic()

    where = _build_where_clause(is_gray)
    query_embedding = Settings.embed_model.get_text_embedding(query)
    _track_embedding_inline("text-embedding-v2", len(query))

    results = _collection.query(
        query_embeddings=[query_embedding],
        n_results=max(top_k * 2, 10),
        where=where,
    )

    doc_texts = results["documents"][0] if results["documents"] else []
    doc_metadatas = results["metadatas"][0] if results["metadatas"] else []

    if not doc_texts:
        return []

    response = TextReRank.call(
        model="qwen3-vl-rerank",
        query=query,
        documents=doc_texts,
        top_n=min(top_k, len(doc_texts)),
        api_key=app_settings.dashscope_api_key,
    )
    _track_rerank_inline(response)

    reranked = []
    for result in response.output.results:
        idx = result.index
        if idx < len(doc_texts):
            reranked.append({
                "content": doc_texts[idx],
                "metadata": doc_metadatas[idx],
            })

    return reranked[:top_k]


def search_no_rerank(query: str, top_k: int = 5, is_gray: Optional[bool] = None) -> List[dict]:
    """
    搜索相关文档（纯向量检索，无精排）

    Args:
        is_gray: None=通过 Nacos 自动分流, True=强制灰度, False=强制线上
    """
    if is_gray is None:
        is_gray = gray_config.is_gray_traffic()

    where = _build_where_clause(is_gray)
    query_embedding = Settings.embed_model.get_text_embedding(query)
    _track_embedding_inline("text-embedding-v2", len(query))

    results = _collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        where=where,
    )

    doc_texts = results["documents"][0] if results["documents"] else []
    doc_metadatas = results["metadatas"][0] if results["metadatas"] else []

    return [
        {"content": text, "metadata": meta}
        for text, meta in zip(doc_texts, doc_metadatas)
    ]


def get_all_chunks(is_gray: bool = False) -> List[dict]:
    """获取全量 chunk"""
    results = _collection.get(where={"is_gray": is_gray})
    return [
        {"id": id_, "content": content, "metadata": metadata}
        for id_, content, metadata in zip(
            results["ids"], results["documents"], results["metadatas"]
        )
    ]


def get_chunks_by_file(file_name: str, is_gray: bool = False) -> List[dict]:
    """获取指定文档的 chunk"""
    results = _collection.get(
        where={"$and": [{"file_name": file_name}, {"is_gray": is_gray}]}
    )
    return [
        {"id": id_, "content": content, "metadata": metadata}
        for id_, content, metadata in zip(
            results["ids"], results["documents"], results["metadatas"]
        )
    ]


def clear():
    """清空 collection"""
    existing_ids = _collection.get()["ids"]
    if existing_ids:
        _collection.delete(ids=existing_ids)
