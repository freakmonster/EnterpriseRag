# 文档分块
# 使用LlamaIndex把政策文档切分成小块，用于向量检索
import re
from typing import List
from llama_index.core.node_parser import SentenceSplitter


def clean_text(text: str) -> str:
    """
    清理文本格式，优化向量检索质量
    - 合并连续换行
    - 去除行首尾空格
    - 保留段落结构
    """
    # 替换 \r\n 为 \n
    text = text.replace("\r\n", "\n")

    # 合并 3 个以上连续换行为 2 个
    text = re.sub(r"\n{3,}", "\n\n", text)

    # 去除每行首尾空格
    lines = [line.strip() for line in text.split("\n")]

    # 重新拼接，过滤空行（但保留段落分隔）
    cleaned_lines = []
    for line in lines:
        if line:
            cleaned_lines.append(line)
        elif cleaned_lines and cleaned_lines[-1] != "":  # 避免连续空行
            cleaned_lines.append("")

    return "\n".join(cleaned_lines)


def split_document_by_title(content: str, title: str) -> List[dict]:
    """
    使用LlamaIndex的SentenceSplitter切分文档
    Args:
        content: 文档内容
        title: 文档标题
    Returns:
        文档块列表，格式: [{"title": "...", "content": "...", "file_name": "...", "chunk_idx": i}]
    """
    # 先清理文本
    content = clean_text(content)

    splitter = SentenceSplitter(
        chunk_size=500,
        chunk_overlap=100,
    )

    chunks = splitter.split_text(content)

    result = []
    for i, chunk_content in enumerate(chunks):
        result.append({
            "title": f"{title} - 第{i+1}段",
            "content": chunk_content,
            "file_name": title,
            "chunk_idx": i
        })

    return result


def split_document_by_markdown_sections(content: str, title: str) -> List[dict]:
    """
    按照Markdown文档的二级标题(##)切分文档
    Args:
        content: 文档内容
        title: 文档标题
    Returns:
        文档块列表，格式: [{"title": "...", "content": "...", "file_name": "...", "chunk_idx": i}]
    """
    content = clean_text(content)

    # 找到所有二级标题的位置
    lines = content.split('\n')
    section_positions = []  # [(line_index, section_title), ...]

    for i, line in enumerate(lines):
        match = re.match(r'^##\s+(.+)$', line)
        if match:
            section_positions.append((i, match.group(1).strip()))

    # 按二级标题切分内容
    chunks = []
    num_sections = len(section_positions)

    for idx, (line_no, section_title) in enumerate(section_positions):
        # 当前section的起始行
        start_line = line_no

        # 下一个section的起始行（或文件末尾）
        if idx + 1 < num_sections:
            end_line = section_positions[idx + 1][0]
        else:
            end_line = len(lines)

        # 提取当前section的内容（包含二级标题行）
        section_lines = lines[start_line:end_line]
        section_content = '\n'.join(section_lines).strip()

        if section_content:
            chunks.append({
                "title": f"{title} - {section_title}",
                "content": section_content,
                "file_name": title,
                "chunk_idx": len(chunks)
            })

    # 如果没有二级标题，整个文档作为一个chunk
    if not chunks:
        chunks.append({
            "title": f"{title} - 全文",
            "content": content,
            "file_name": title,
            "chunk_idx": 0
        })

    return chunks
