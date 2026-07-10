"""
初始化向量库
加载政策文档、分块并存入ChromaDB
"""
from retrieval.document_loader import load_policy_documents
from retrieval.document_splitter import split_document_by_title, split_document_by_markdown_sections
from retrieval.vectorstores.chroma_store import clear, insert_chunks


def init_vector_store():

    # 清空向量库
    clear()

    """初始化向量库"""
    print("正在加载政策文档...")
    docs = load_policy_documents()
    print(f"已加载 {len(docs)} 个文档")

    all_chunks = []
    for doc in docs:
        print(f"正在切分文档: {doc['title']}")
        chunks = split_document_by_markdown_sections(doc["content"], doc["title"])
        all_chunks.extend(chunks)

    print(f"共切分成 {len(all_chunks)} 个文档块")

    print("正在存入向量库...")
    clear()
    insert_chunks(all_chunks, is_gray=False)
    print("向量库初始化完成！")


if __name__ == "__main__":
    print("正在初始化向量库...")
    init_vector_store()
