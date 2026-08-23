# 政策原文 API 路由
import re
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, HTTPException

router = APIRouter()

POLICIES_DIR = Path(__file__).parent.parent.parent / "data" / "policies"


def _parse_title(content: str, file_name: str) -> str:
    """提取文档标题：取首个一级标题，缺失时回退为文件名（去掉编号前缀与扩展名）"""
    for line in content.split("\n"):
        m = re.match(r"^#\s+(.+)", line)
        if m:
            return m.group(1).strip()
    return Path(file_name).stem


@router.get("/policies")
def list_policies():
    """返回政策文档清单（文件名、标题、章节数、更新时间）"""
    if not POLICIES_DIR.is_dir():
        return {"items": []}
    items = []
    for file_path in sorted(POLICIES_DIR.glob("*.md")):
        content = file_path.read_text(encoding="utf-8")
        section_count = sum(1 for line in content.split("\n") if re.match(r"^##\s+", line))
        mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
        items.append({
            "file_name": file_path.stem,
            "title": _parse_title(content, file_path.name),
            "section_count": section_count,
            "updated_at": mtime.strftime("%Y-%m-%d"),
        })
    return {"items": items}


@router.get("/policy/{file_name:path}")
def get_policy(file_name: str):
    """返回政策文件的完整 Markdown 内容及二级标题切分信息"""
    file_path = POLICIES_DIR / file_name

    # 安全检查：防止路径穿越
    try:
        file_path = file_path.resolve()
        POLICIES_DIR.resolve()
        if not str(file_path).startswith(str(POLICIES_DIR.resolve())):
            raise HTTPException(status_code=403, detail="禁止访问")
    except Exception:
        raise HTTPException(status_code=400, detail="无效的文件名")

    # 容错：file_name 可能不含 .md 扩展名（元数据中存储的 file_name 来自 stem）
    if not file_path.exists() or not file_path.is_file():
        file_path_md = POLICIES_DIR / (file_name + ".md")
        if file_path_md.exists() and file_path_md.is_file():
            file_path = file_path_md
        else:
            raise HTTPException(status_code=404, detail="政策文件不存在")

    content = file_path.read_text(encoding="utf-8")

    # 解析所有 ## 二级标题的行号
    lines = content.split("\n")
    sections = []
    for i, line in enumerate(lines):
        m = re.match(r"^##\s+(.+)", line)
        if m:
            sections.append({"title": m.group(1).strip(), "line": i})

    return {"content": content, "sections": sections, "title": _parse_title(content, file_path.name)}
