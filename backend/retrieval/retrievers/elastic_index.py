"""
Elasticsearch 索引管理：创建索引、文档入库、删除索引
支持 is_gray 元数据字段区分线上/灰度数据
"""
import ssl as _ssl
_orig_load_certs = _ssl.SSLContext.load_default_certs
def _safe_load_certs(self, purpose=_ssl.Purpose.SERVER_AUTH):
    try:
        return _orig_load_certs(self, purpose)
    except _ssl.SSLError:
        pass
_ssl.SSLContext.load_default_certs = _safe_load_certs

from typing import List, Optional
from elasticsearch import Elasticsearch
from config.settings import settings as app_settings
from retrieval.vectorstores.chroma_store import get_all_chunks

es = Elasticsearch(
    [f"http://{app_settings.es_host}:{app_settings.es_port}"],
    verify_certs=False,
)

INDEX_NAME = "policies"


def create_index(index_name: str = INDEX_NAME):
    """创建 ES 索引（若存在则先删除重建）"""
    if es.indices.exists(index=index_name):
        es.indices.delete(index=index_name)

    mapping = {
        "mappings": {
            "properties": {
                "id": {"type": "keyword"},
                "content": {"type": "text", "analyzer": "ik_max_word", "search_analyzer": "ik_smart"},
                "title": {"type": "text", "analyzer": "ik_max_word", "search_analyzer": "ik_smart"},
                "file_name": {"type": "keyword"},
                "chunk_idx": {"type": "integer"},
                "is_gray": {"type": "boolean"},
            }
        }
    }
    es.indices.create(index=index_name, body=mapping)
    print(f"ES 索引 '{index_name}' 创建成功")


def insert_chunks(index_name: str = INDEX_NAME, chunks: List[dict] = None, is_gray: bool = False):
    """
    将 chunks 写入 ES 索引
    Args:
        index_name: 目标索引名
        chunks: chunk 列表（省略则从 ChromaDB 读取）
        is_gray: is_gray 字段值
    """
    if chunks is None:
        chunks = get_all_chunks()

    if not chunks:
        print("没有 chunk 可写入")
        return

    docs = []
    for chunk in chunks:
        if "metadata" in chunk:
            # ChromaDB 格式: {id, content, metadata: {title, file_name, chunk_idx, ...}}
            meta = chunk["metadata"]
            chunk_id = chunk.get("id", f"{meta.get('file_name', '')}::{meta.get('chunk_idx', 0)}")
            content = chunk["content"]
            title = meta.get("title", "")
            file_name = meta.get("file_name", "")
            chunk_idx = meta.get("chunk_idx", 0)
        else:
            # Splitter 格式: {content, title, file_name, chunk_idx}
            file_name = chunk.get("file_name", "")
            chunk_idx = chunk.get("chunk_idx", 0)
            chunk_id = f"{file_name}::{chunk_idx}"
            content = chunk.get("content", "")
            title = chunk.get("title", "")

        docs.append({"index": {"_index": index_name, "_id": chunk_id}})
        docs.append({
            "id": chunk_id,
            "content": content,
            "title": title,
            "file_name": file_name,
            "chunk_idx": chunk_idx,
            "is_gray": is_gray,
        })

    es.bulk(body=docs)
    es.indices.refresh(index=index_name)
    print(f"已写入 {len(chunks)} 个 chunk 到 ES 索引 '{index_name}' (is_gray={is_gray})")


def delete_by_file(file_name: str, is_gray: Optional[bool] = None, index_name: str = INDEX_NAME):
    """按文件名删除 ES 文档，可选 is_gray 过滤"""
    must = [{"term": {"file_name": file_name}}]
    if is_gray is not None:
        must.append({"term": {"is_gray": is_gray}})
    es.delete_by_query(
        index=index_name,
        body={"query": {"bool": {"must": must}}}
    )
    es.indices.refresh(index=index_name)


def update_is_gray(file_name: str, from_value: bool, to_value: bool, index_name: str = INDEX_NAME):
    """将指定文件文档的 is_gray 从 from_value 更新为 to_value"""
    es.update_by_query(
        index=index_name,
        body={
            "query": {
                "bool": {
                    "must": [
                        {"term": {"file_name": file_name}},
                        {"term": {"is_gray": from_value}}
                    ]
                }
            },
            "script": {
                "source": f"ctx._source.is_gray = {str(to_value).lower()}",
                "lang": "painless"
            }
        }
    )
    es.indices.refresh(index=index_name)


def delete_index(index_name: str = INDEX_NAME):
    """删除 ES 索引"""
    if es.indices.exists(index=index_name):
        es.indices.delete(index=index_name)
        print(f"ES 索引 '{index_name}' 已删除")
    else:
        print(f"ES 索引 '{index_name}' 不存在")

def get_all_es_indices(es_client: Elasticsearch) -> list:
    """
    查询 Elasticsearch 中所有的索引名称
    Args:
        es_client: 已初始化的 Elasticsearch 客户端实例
    Returns:
        list: 所有索引名称列表
    """
    try:
        # 获取索引详情（JSON格式）
        indices_data = es_client.cat.indices(format="json")
        # 提取纯索引名称列表
        return [item["index"] for item in indices_data]
    except Exception as e:
        print(f"查询索引失败：{str(e)}")
        return []

if __name__ == "__main__":
    # all_indices = get_all_es_indices(es)
    # print("ES中所有索引：", all_indices)
    create_index()
    insert_chunks()
    # delete_index("policy_chunks")
    count = es.count(index=INDEX_NAME)["count"]
    print(f"\n验证: ES 索引中有 {count} 个文档")
