# 文档加载
# 使用LlamaIndex加载政策文档（Markdown格式）
from pathlib import Path
from typing import List
from llama_index.core import SimpleDirectoryReader
from config.settings import settings


def load_policy_documents(data_dir: str = None) -> List[dict]:
    """
    使用LlamaIndex加载政策文档
    Args:
        data_dir: 政策文档目录，None则使用settings中的配置
    Returns:
        文档列表，格式: [{"title": "...", "content": "...", "file_path": "..."}]
    """
    if data_dir is None:
        data_dir = settings.policies_data_dir

    dir_path = Path(data_dir)
    if not dir_path.exists():
        print(f"警告：政策文档目录不存在: {dir_path}")
        return []

    reader = SimpleDirectoryReader(
        input_dir=str(dir_path),
        required_exts=[".md"],
        recursive=False,
        encoding="utf-8"
    )

    documents = reader.load_data()

    docs = []
    for doc in documents:
        file_path = Path(doc.metadata["file_path"])
        docs.append({
            "title": file_path.stem,
            "content": doc.text,
            "file_path": str(file_path)
        })

    return docs
