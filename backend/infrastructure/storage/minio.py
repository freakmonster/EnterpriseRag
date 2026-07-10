"""MinIO policy file storage — upload/download/list .md files"""
from io import BytesIO
from pathlib import Path

from minio import Minio
from minio.error import S3Error

from config.settings import settings

minio_client = Minio(
    settings.minio_host,
    access_key=settings.minio_access_key,
    secret_key=settings.minio_secret_key,
    secure=False,
)

BUCKET = settings.minio_bucket_policies
POLICIES_DIR = Path(settings.policies_data_dir)


def ensure_bucket():
    """确保 bucket 存在，不存在则创建"""
    if not minio_client.bucket_exists(BUCKET):
        minio_client.make_bucket(BUCKET)
        print(f"已创建 bucket: {BUCKET}")
    else:
        print(f"Bucket 已存在: {BUCKET}")


def upload_policy_file(object_name: str, content: str | bytes):
    """上传单个 policy 文件到 MinIO"""
    if isinstance(content, str):
        data = BytesIO(content.encode("utf-8"))
    else:
        data = BytesIO(content)
    minio_client.put_object(BUCKET, object_name, data, length=data.getbuffer().nbytes,
                            content_type="text/markdown")
    print(f"已上传: {object_name}")


def upload_all_policies():
    """将 data/policies/ 下所有 .md 文件上传到 MinIO"""
    ensure_bucket()
    for md_file in POLICIES_DIR.glob("*.md"):
        content = md_file.read_text(encoding="utf-8")
        upload_policy_file(md_file.name, content)


def download_file(object_name: str) -> str:
    """从 MinIO 下载 .md 文件，返回文本内容"""
    try:
        response = minio_client.get_object(BUCKET, object_name)
        return response.read().decode("utf-8")
    finally:
        if "response" in dir():
            response.close()
            response.release_conn()


def list_files() -> list[str]:
    """列出 bucket 中所有 object 名称"""
    objects = minio_client.list_objects(BUCKET)
    return [obj.object_name for obj in objects]


if __name__ == "__main__":
    # upload_all_policies()
    print("文件列表:", list_files())
