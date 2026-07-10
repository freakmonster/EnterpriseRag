# 技能查看工具
from langchain_core.tools import tool

from config.skills import get_skill_content


@tool
def view_file(file1: int, file2: int) -> str:
    """查看改写指导文件
    Args:
        file1: 多Query改写指导，需要查看填1，否则填0
        file2: BM25 改写指导，需要查看填1，否则填0
    """
    parts = []
    if file1 == 1:
        content = get_skill_content("skill:guide:multiquery")
        parts.append(f"【多Query改写指导】\n{content}" if content else
                     "【多Query改写指导】\n（文件未找到）")
    if file2 == 1:
        content = get_skill_content("skill:guide:bm25")
        parts.append(f"【BM25改写指导】\n{content}" if content else
                     "【BM25改写指导】\n（文件未找到）")
    if not parts:
        return "未选择查看任何文件"
    return "\n\n".join(parts)
