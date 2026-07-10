"""灰度更新编排：MinIO webhook → Nacos 渐进式灰度 → 最终上线/回滚"""
from pathlib import Path

from infrastructure.cache.redis import redis_client
from infrastructure.config.gray import gray_config
from retrieval.document_splitter import split_document_by_markdown_sections
from retrieval.vectorstores.chroma_store import (
    insert_chunks as chroma_insert,
    delete_chunks_by_file as chroma_delete,
)
from infrastructure.storage.minio import download_file
from retrieval.retrievers.elastic_index import (
    insert_chunks as es_insert,
    delete_by_file as es_delete,
)

REDIS_GRAY_FILES_KEY = "policies:gray:files"
REDIS_ETAG_PREFIX = "policies:etag:"


def _stored_etag(file_name: str) -> str:
    """获取上次处理的 etag"""
    return redis_client.get(f"{REDIS_ETAG_PREFIX}{file_name}") or ""


def _store_etag(file_name: str, etag: str):
    """存储本次处理的 etag"""
    redis_client.set(f"{REDIS_ETAG_PREFIX}{file_name}", etag)


def init_policies():
    """首次全量初始化：加载本地 .md 文件 → 切分 → 写入 ChromaDB + ES (is_gray=False)"""
    from retrieval.document_loader import load_policy_documents
    from retrieval.vectorstores.chroma_store import clear as chroma_clear
    from retrieval.retrievers.elastic_index import create_index

    print("正在初始化 policies...")
    docs = load_policy_documents()
    all_chunks = []
    for doc in docs:
        chunks = split_document_by_markdown_sections(doc["content"], doc["title"])
        all_chunks.extend(chunks)

    chroma_clear()
    chroma_insert(all_chunks, is_gray=False)
    print(f"  ChromaDB: {len(all_chunks)} chunks (is_gray=False)")

    create_index()
    es_insert("policies", all_chunks, is_gray=False)
    print(f"  ES: {len(all_chunks)} chunks (is_gray=False)")

    # 确保 Nacos 配置处于正常模式
    gray_config.publish_config(gray_status=0, gray_ratio=10)
    # 清空灰度文件集
    redis_client.delete(REDIS_GRAY_FILES_KEY)

    print(f"初始化完成，共 {len(all_chunks)} chunks")
    return len(all_chunks)


def handle_file_update(file_name: str, etag: str = ""):
    """
    MinIO webhook 触发：
      ① etag 比对，内容未变则跳过
      ② 下载变更文件 → 切分 → 写入灰度数据 (is_gray=True)
      ③ 文件名加入 Redis Set: policies:gray:files
      ④ 存储 etag 防止重复处理

    此时：
      - 线上用户查 is_gray=False → 命中旧数据（不受影响）
      - 灰度流量走复杂条件 → 该文件命中新数据
    """
    title = Path(file_name).stem

    # etag 去重：内容未变更则跳过
    if etag and etag == _stored_etag(file_name):
        print(f"跳过: {file_name} (etag 未变更)")
        return

    content = download_file(file_name)
    new_chunks = split_document_by_markdown_sections(content, title)
    print(f"灰度更新: {file_name} → {len(new_chunks)} chunks")

    # 1. 清理旧的灰度数据
    chroma_delete(title, is_gray=True)
    es_delete(title, is_gray=True)

    # 2. 写入新灰度数据
    chroma_insert(new_chunks, is_gray=True)
    es_insert("policies", new_chunks, is_gray=True)

    # 3. 文件名加入灰度集
    redis_client.sadd(REDIS_GRAY_FILES_KEY, title)

    # 4. 存储 etag
    if etag:
        _store_etag(file_name, etag)

    # 5. 刷新灰度配置（感知 Nacos 最新设置）
    gray_config.refresh()

    print(f"  灰度 chunks 已写入 (is_gray=True)，文件已加入灰度集")


def finalize_promotion(file_name: str):
    """
    最终上线（ratio=100% 后执行）：
      ① 删旧 is_gray=False（已无流量命中）
      ② 重插新数据 is_gray=False
      ③ Nacos: gray_status → 0
      ④ 删旧灰度数据 is_gray=True
      ⑤ 清 Redis gray_files Set
    """
    title = Path(file_name).stem
    print(f"最终上线: {title}")

    # 重新切分（从 MinIO 下载最新版本）
    content = download_file(file_name)
    new_chunks = split_document_by_markdown_sections(content, title)

    # ① 删旧 is_gray=False
    chroma_delete(title, is_gray=False)
    es_delete(title, is_gray=False)
    print(f"  ① 旧数据已删除 (is_gray=False)")

    # ② 重插新数据 is_gray=False
    chroma_insert(new_chunks, is_gray=False)
    es_insert("policies", new_chunks, is_gray=False)
    print(f"  ② 新数据已重插 (is_gray=False)")

    # ③ Nacos: gray_status → 0（查询切回简单模式）
    gray_config.publish_config(gray_status=0, gray_ratio=0)
    print(f"  ③ Nacos gray_status → 0")

    # ④ 删旧灰度数据
    chroma_delete(title, is_gray=True)
    es_delete(title, is_gray=True)
    print(f"  ④ 旧灰度数据已删除 (is_gray=True)")

    # ⑤ 清 Redis
    redis_client.srem(REDIS_GRAY_FILES_KEY, title)
    print(f"  ⑤ Redis 灰度集已清理")


def rollback_file(file_name: str):
    """
    验证失败：清除灰度数据，旧数据不受影响
    """
    title = Path(file_name).stem
    print(f"回滚: {title}")

    chroma_delete(title, is_gray=True)
    es_delete(title, is_gray=True)
    redis_client.srem(REDIS_GRAY_FILES_KEY, title)
    print(f"  灰度数据已清除")


def handle_file_delete(file_name: str):
    """
    MinIO 文件被删除：
      - 若文件在灰度集中 → 仅删灰度数据 (is_gray=True)，保留旧数据（回滚行为）
      - 若不在灰度集中 → 删除所有数据（正常清理）
    同步清理 Redis 灰度集和 etag。
    """
    title = Path(file_name).stem
    is_gray = redis_client.sismember(REDIS_GRAY_FILES_KEY, title)

    if is_gray:
        print(f"删除(灰度回滚): {title}")
        chroma_delete(title, is_gray=True)
        es_delete(title, is_gray=True)
        redis_client.srem(REDIS_GRAY_FILES_KEY, title)
        redis_client.delete(f"{REDIS_ETAG_PREFIX}{file_name}")
        print(f"  灰度数据已清除，旧数据保留")
    else:
        print(f"删除: {title}")
        chroma_delete(title)
        es_delete(title)
        redis_client.srem(REDIS_GRAY_FILES_KEY, title)
        redis_client.delete(f"{REDIS_ETAG_PREFIX}{file_name}")
        print(f"  文件数据已全部清除")


if __name__ == "__main__":
    finalize_promotion("09测试文件.md")
