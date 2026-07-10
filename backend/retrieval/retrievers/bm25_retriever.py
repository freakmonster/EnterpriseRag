"""
Elasticsearch BM25 关键词检索
返回格式与向量检索保持一致，便于多路召回融合
查询默认过滤 is_gray=False（线上数据），支持 Nacos 控制渐进式流量分流
"""
from typing import List, Optional
from elasticsearch import Elasticsearch
from config.settings import settings as app_settings
from infrastructure.cache.redis import redis_client
from infrastructure.config.gray import gray_config

es = Elasticsearch(
    [f"http://{app_settings.es_host}:{app_settings.es_port}"],
    verify_certs=False,
)

INDEX_NAME = "policies"


def _get_gray_files() -> list:
    """读取 Redis 中的灰度文件名集合"""
    return list(redis_client.smembers("policies:gray:files"))


def _build_filter_clause(gray_traffic: bool) -> dict:
    """
    构建 ES 过滤条件

    gray_traffic=False: {"term": {"is_gray": False}}
    gray_traffic=True: 灰度文件走 is_gray=True，其余走 is_gray=False
    """
    if not gray_traffic:
        return {"term": {"is_gray": False}}

    gray_files = _get_gray_files()
    if not gray_files:
        return {"term": {"is_gray": False}}

    return {
        "bool": {
            "should": [
                {
                    "bool": {
                        "must": [
                            {"term": {"is_gray": False}},
                            {"bool": {"must_not": {"terms": {"file_name": gray_files}}}},
                        ]
                    }
                },
                {
                    "bool": {
                        "must": [
                            {"term": {"is_gray": True}},
                            {"terms": {"file_name": gray_files}},
                        ]
                    }
                },
            ],
            "minimum_should_match": 1,
        }
    }


def bm25_search(query: str, top_k: int = 3, is_gray: Optional[bool] = None) -> List[dict]:
    """
    BM25 关键词检索
    Args:
        query: 用户问题
        top_k: 返回文档数
        is_gray: None=通过 Nacos 自动分流, True=强制灰度, False=强制线上
    Returns:
        文档列表，格式: [{"content": "...", "metadata": {"file_name": "...", "chunk_idx": 0, ...}}, ...]
    """
    if is_gray is None:
        is_gray = gray_config.is_gray_traffic()

    filter_clause = _build_filter_clause(is_gray)

    body = {
        "query": {
            "bool": {
                "must": [
                    {
                        "match": {
                            "content": {
                                "query": query,
                                "operator": "or",
                            }
                        }
                    },
                    filter_clause,
                ]
            }
        },
        "size": top_k,
    }

    response = es.search(index=INDEX_NAME, body=body)

    results = []
    for hit in response["hits"]["hits"]:
        source = hit["_source"]
        results.append({
            "content": source["content"],
            "metadata": {
                "title": source.get("title", ""),
                "file_name": source.get("file_name", ""),
                "chunk_idx": source.get("chunk_idx", 0),
            }
        })

    return results


if __name__ == "__main__":
    query = "公司上班打卡规定"
    print(f"查询: {query}")
    results = bm25_search(query, top_k=3)
    print(f"命中 {len(results)} 条:")
    for i, doc in enumerate(results):
        print(f"\n{i+1}. {doc['metadata']['file_name']} | chunk_idx={doc['metadata']['chunk_idx']}")
        print(f"   内容: {doc['content'][:100]}...")
