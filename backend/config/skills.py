"""
Warm up skills: 将skills目录下的改写指导文件加载到Redis（string类型）
"""
from pathlib import Path

from infrastructure.cache.redis import redis_client

SKILLS_DIR = Path(__file__).parent

FILES = [
    ("多Query改写指导.txt", "skill:guide:multiquery"),
    ("BM25改写指导.txt", "skill:guide:bm25"),
]

# 文件名 → Redis key 映射，供 get_skill_content 本地兜底使用
_FILE_TO_REDIS_KEY = {filename: redis_key for filename, redis_key in FILES}
_REDIS_KEY_TO_FILE = {redis_key: filename for filename, redis_key in FILES}


def warm_up():
    """将改写指导文件加载到Redis"""
    success = 0
    for filename, redis_key in FILES:
        try:
            content = _read_file(filename)
            redis_client.set(redis_key, content)
            print(f"已加载: {filename} -> {redis_key} ({len(content)} 字符)")
            success += 1
        except FileNotFoundError:
            print(f"文件不存在: {SKILLS_DIR / filename}")
        except Exception as e:
            print(f"加载失败 {filename}: {e}")

    print(f"\n完成: {success}/{len(FILES)} 个文件已加载到Redis")


def get_skill_content(redis_key: str) -> str:
    """获取skill内容：优先Redis，未命中则读本地文件并写回Redis"""
    content = redis_client.get(redis_key)
    if content:
        return content
    filename = _REDIS_KEY_TO_FILE.get(redis_key)
    if filename:
        content = _read_file(filename)
        redis_client.set(redis_key, content)
    return content


def _read_file(filename: str) -> str:
    """从本地文件读取skill内容"""
    return (SKILLS_DIR / filename).read_text(encoding="utf-8")


if __name__ == "__main__":
    warm_up()
