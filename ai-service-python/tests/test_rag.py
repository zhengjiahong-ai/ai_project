# 导入核心RAG类
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)

from core.rag_vector_db import LiteratureRAG

if __name__ == "__main__":
    # 初始化RAG
    rag = LiteratureRAG()

    print("当前向量库数量：", rag.get_db_stats())

    # 测试1：添加文献（替换为你的实际文献路径）
    test_file_path = "./test_literature.pdf"  # 建议把测试文献放在ai-service-python目录下
    try:
        # 补充文献元数据
        metadata = {
            "title": "测试学术文献",
            "author": "测试作者",
            "publish_year": 2024,
            "field": "计算机科学"
        }
        chunk_num = rag.add_literature_to_db(test_file_path, metadata)
        print(f"✅ 成功入库{chunk_num}个文献片段")
        print(f"📊 当前向量库总片段数：{rag.get_db_stats()}")
    except Exception as e:
        print(f"❌ 入库失败：{e}")

    # 测试2：检索（模拟深度分析层需求）
    test_query = "What is the core contribution of this article?"
    retrieve_results = rag.retrieve(test_query, top_k=3)
    print("\n🔍 检索结果：")
    for idx, res in enumerate(retrieve_results):
        print(f"\nTop{idx + 1} | 相似度：{res['similarity']:.4f}")
        print(f"文本片段：{res['text'][:200]}...")  # 只显示前200字符，避免过长
        print(f"元数据：{res['metadata']}")

    # 测试3：metadata 过滤检索
    print("\n🔎 测试 metadata 过滤（author=测试作者）:")
    filtered_results = rag.retrieve(
        test_query,
        top_k=3,
        filter_metadata={"author": "测试作者"}
    )

    for idx, res in enumerate(filtered_results):
        print(f"\nFiltered Top{idx + 1} | 相似度：{res['similarity']:.4f}")
        print(f"文本片段：{res['text'][:200]}...")
        print(f"元数据：{res['metadata']}")