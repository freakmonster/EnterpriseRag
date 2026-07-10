"""Webhook 业务编排：MinIO 事件 → 灰度更新处理"""
from retrieval.gray_updater import handle_file_update, handle_file_delete


async def process_policy_update(file_name: str, etag: str):
    """处理政策文件更新 (PUT)"""
    await handle_file_update(file_name, etag)


def process_policy_delete(file_name: str):
    """处理政策文件删除 (DELETE)"""
    handle_file_delete(file_name)
