"""MinIO webhook: 接收 bucket 事件通知，触发灰度更新"""
import json
import logging
from urllib.parse import unquote_plus

from fastapi import APIRouter, Request, BackgroundTasks

from agents.workflows.webhook_workflow import process_policy_update, process_policy_delete

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/webhook/policy-update")
async def on_policy_update(request: Request, background_tasks: BackgroundTasks):
    """
    MinIO bucket notification webhook
    PUT 事件 → 灰度更新，DELETE 事件 → 直接删除
    """
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return {"status": "error", "message": "invalid json"}, 400

    # MinIO S3 event 格式：Records[].s3.object.key（URL 编码，需解码）
    records = body.get("Records", [])
    if not records:
        key = body.get("Key")
        if key:
            records = [{"s3": {"object": {"key": key}}}]

    created: dict[str, str] = {}   # file_name → etag
    deleted: set[str] = set()
    for record in records:
        event_name = record.get("eventName", "")
        obj = record.get("s3", {}).get("object", {})
        key = unquote_plus(obj.get("key", ""))
        etag = obj.get("eTag", "") or obj.get("etag", "")  # MinIO 用 eTag（驼峰）

        if not key or not key.endswith(".md"):
            continue

        if "ObjectRemoved" in event_name:
            deleted.add(key)
        else:
            created[key] = etag

        logger.info(f"MinIO 事件: {event_name} — {key}")

    for file_name, etag in created.items():
        background_tasks.add_task(process_policy_update, file_name, etag)
    for file_name in deleted:
        background_tasks.add_task(process_policy_delete, file_name)

    return {"status": "ok", "created": list(created.keys()), "deleted": list(deleted)}


@router.get("/webhook/health")
async def webhook_health():
    """webhook 健康检查"""
    return {"status": "ok"}
