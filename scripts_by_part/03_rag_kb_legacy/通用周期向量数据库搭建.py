import pandas as pd
import os
import time
import chromadb
import torch
from pathlib import Path
from typing import List, Dict, Any
from llama_index.core import VectorStoreIndex, StorageContext, Settings, get_response_synthesizer
from llama_index.vector_stores.chroma import ChromaVectorStore
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.core.schema import TextNode
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.postprocessor import SentenceTransformerRerank
from llama_index.llms.openai_like import OpenAILike

# ---------------------
# 环境与设备
# ---------------------
device = "cuda" if torch.cuda.is_available() else "cpu"
print("当前设备：", device)

# =============================
#  配置
# =============================
class Config:
    
    
    EMBED_MODEL_PATH = "./models"
    GENERAL_EXCEL = "./data/通用建议校准周期.xlsx"  # Excel 文件路径
    DB_DIR = "./vector_db/general_cycle"       # 向量数据库路径
    # EMBED_MODEL_PATH = r"D:\workspace\ai_learning\pythonProject\models\BAAI\bge-m3"
    # RERANK_MODEL_PATH = r"D:\workspace\ai_learning\pythonProject\models\BAAI\bge-reranker-large"
    API_BASE = "https://api.deepseek.com/v1"
    API_KEY = os.getenv("DEEPSEEK_API_KEY", "")  # 替换为你的 key
    TOP_K = 10
    RERANK_TOP_K = 5
    MIN_RERANK_SCORE = 0.0
    TEMPERATURE = 0.3

# =============================
# 模型初始化
# =============================
def init_models():
    """初始化 embedding / reranker / llm"""
    embed_model = HuggingFaceEmbedding(model_name=Config.EMBED_MODEL_PATH)
    llm = OpenAILike(
        model="deepseek-chat",
        api_base=Config.API_BASE,
        api_key=Config.API_KEY,
        context_window=128000,
        is_chat_model=True,
        is_function_calling_model=False,
        max_tokens=1024,
        temperature=Config.TEMPERATURE,
        top_p=0.7
    )
    # reranker = SentenceTransformerRerank(model=Config.RERANK_MODEL_PATH, top_n=Config.RERANK_TOP_K)

    Settings.embed_model = embed_model
    Settings.llm = llm

    try:
        emb = embed_model.get_text_embedding("测试")
        print(f"✅ 嵌入模型加载成功，维度：{len(emb)}")
    except Exception as e:
        print(f"⚠️ 嵌入模型验证失败：{e}")
    return embed_model, llm
    # return embed_model, llm, reranker

# =============================
# Excel 解析函数
# =============================
def parse_general_cycle_excel(excel_path: str) -> List[Dict[str, Any]]:
    """
    解析“通用-建议校准周期.xlsx”
    支持列名：
    序号, 细类名称, 中类名称, 大类名称, 依据, 建议校准周期
    """
    df = pd.read_excel(excel_path, dtype=str)
    df.fillna("", inplace=True)

    # 标准列映射
    col_map = {
        "序号": "序号",
        "细类名称": "细类名称",
        "中类名称": "中类名称",
        "大类名称": "大类名称",
        "依据": "依据",
        "建议校准周期": "建议校准周期"
    }

    missing_cols = [c for c in col_map.values() if c not in df.columns]
    if missing_cols:
        print(f"⚠️ Excel 缺少列：{missing_cols}")
    else:
        print("✅ 检测到完整列结构。")

    records = []
    for _, row in df.iterrows():
        rec = {c: str(row.get(c, "")) for c in col_map.values()}

        # 拼接语义文本
        rec["__text"] = (
            f"细类名称：{rec.get('细类名称', '')}；"
            f"中类名称：{rec.get('中类名称', '')}；"
            f"大类名称：{rec.get('大类名称', '')}；"
            f"依据：{rec.get('依据', '')}；"
            f"建议校准周期：{rec.get('建议校准周期', '')}"
        )
        records.append(rec)

    print(f"✅ 解析完成，共 {len(records)} 条记录。")
    return records

# =============================
# 构建节点
# =============================
def create_general_cycle_nodes(records: List[Dict[str, Any]]) -> List[TextNode]:
    nodes = []
    splitter = SentenceSplitter(chunk_size=512)
    for rec in records:
        text = rec.get("__text", "")
        if not text:
            text = "；".join([f"{k}：{v}" for k, v in rec.items() if v])
        for chunk in splitter.split_text(text):
            nodes.append(TextNode(text=chunk, metadata=rec))
    print(f"✅ 构建 {len(nodes)} 个文本节点。")
    return nodes

# =============================
# 初始化/加载 向量库
# =============================
def init_vector_store(nodes: List[TextNode], embed_model, db_dir: str, collection_name: str) -> VectorStoreIndex:
    Path(db_dir).mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=db_dir)
    collection = client.get_or_create_collection(collection_name)
    vector_store = ChromaVectorStore(chroma_collection=collection)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    if collection.count() == 0:
        print(f"📥 数据库为空，正在构建索引...")
        index = VectorStoreIndex(nodes, storage_context=storage_context, embed_model=embed_model)
        index.storage_context.persist(persist_dir=db_dir)
        print(f"✅ 索引已建立完成：{db_dir}")
    else:
        print(f"📂 检测到已有索引（{db_dir}），直接加载。")
        index = VectorStoreIndex.from_vector_store(vector_store, embed_model=embed_model)
    return index

# =============================
# 主函数
# =============================
def main():
    print("🚀 启动通用-校准周期向量数据库系统...\n")

    # ---------- 模型加载 ----------
    embed_model, llm = init_models()

    # ---------- Excel 解析 ----------
    if not Path(Config.GENERAL_EXCEL).exists():
        print(f"❌ 未找到 Excel 文件：{Config.GENERAL_EXCEL}")
        return

    records = parse_general_cycle_excel(Config.GENERAL_EXCEL)
    nodes = create_general_cycle_nodes(records)

    # ---------- 构建/加载向量库 ----------
    index = init_vector_store(nodes, embed_model, Config.DB_DIR, "general_cycle_data")
    retriever = index.as_retriever(similarity_top_k=Config.TOP_K)
    response_synthesizer = get_response_synthesizer(verbose=True)

    print("\n✅ 系统已就绪！输入关键词进行检索（输入 q 退出）")

    while True:
        query = input("\n❓ 请输入检索内容：").strip()
        if not query:
            continue
        if query.lower() in ["q", "quit", "exit"]:
            print("👋 退出系统，再见！")
            break

        start_time = time.time()
        results = retriever.retrieve(query)

        if not results:
            print("⚠️ 未找到匹配内容。")
            continue

        print(f"🔍 检索到 {len(results)} 条候选结果。")

        # 无需重排序，直接使用原结果
        filtered = results

        if not filtered:
            print("⚠️ 没有高相关度结果。")
            continue

        print("\n📚 前 5 条检索结果：")
        for i, node in enumerate(filtered[:5], 1):
            print(f"\n🧩 Top {i} | 相似度：{getattr(node, 'score', 0):.3f}")
            print(node.text[:300] + "...")

        print(f"\n⏱️ 耗时 {time.time() - start_time:.2f}s\n")

if __name__ == "__main__":
    main()

