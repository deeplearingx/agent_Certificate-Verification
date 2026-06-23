import os
import re
import time
import json
import chromadb
import torch
from pathlib import Path
from typing import List, Dict, Any
from sentence_transformers import SentenceTransformer

from llama_index.core import VectorStoreIndex, StorageContext, Settings
from llama_index.core.schema import TextNode
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.vector_stores.chroma import ChromaVectorStore
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.postprocessor import SentenceTransformerRerank
from llama_index.llms.openai_like import OpenAILike


# =============================
#  系统配置
# =============================

device = "cuda" if torch.cuda.is_available() else "cpu"
print("当前设备：", device)


class Config:
    TXT_PATH = "chunks_plain_text.txt"
    DB_DIR = "./chroma_db"
    EMBED_MODEL_PATH = r"D:\workspace\ai_learning\pythonProject\models\BAAI\bge-m3"
    RERANK_MODEL_PATH = r"D:\workspace\ai_learning\pythonProject\models\BAAI\bge-reranker-large"
    LLM_MODEL_PATH = r"/home/cw/llms/Qwen/Qwen1___5-1___8B-Chat"
    API_BASE = "https://api.deepseek.com/v1"
    API_KEY = os.getenv("DEEPSEEK_API_KEY", "")

    TOP_K = 10
    RERANK_TOP_K = 3
    MIN_RERANK_SCORE = 0.35
    TEMPERATURE = 0.3


# =============================
#  解析校准能力 TXT
# =============================

def _clean(s: str) -> str:
    if s is None:
        return ""
    return str(s).strip().strip(' \t\n\r"“”')


def parse_calibration_txt(txt_path: str) -> List[Dict[str, Any]]:
    """解析校准能力文本"""
    raw = Path(txt_path).read_text(encoding="utf-8")
    blocks = re.split(r"\n-{3,}\n|(?:\n\s*\n\s*\n)+", raw)

    results: List[Dict[str, Any]] = []

    instr_re = re.compile(
        r"关于测量仪器[“\"]?(?P<instr>[^”\"\\n]+?)[”\"]?(?:（序号：(?P<idx>\d+)）)?[,，]?\s*其校准能力详情如下：",
        flags=re.I | re.S
    )

    cap_re = re.compile(
        r"对于被测量[“\"]?(?P<meas>.+?)[”\"]?[，,]\s*测量范围是[“\"]?(?P<range>.+?)[”\"]?(?:[，,；;。]|$)\s*"
        r"(?:.*?扩展不确定度\s*\(k=2\)\s*为[“\"]?(?P<uncert>.+?)[”\"]?(?:[。；;]|$))?",
        flags=re.S
    )

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        instr_m = instr_re.search(block)
        instr_name = _clean(instr_m.group("instr")) if instr_m else "未知仪器"

        std_m = re.search(r"遵循的主要校准规范是[“\"]?(?P<std>[^”\n]+?)[”\"]?", block)
        standard = _clean(std_m.group("std")) if std_m else "未知规范"

        for m in cap_re.finditer(block):
            results.append({
            "仪器名称": instr_name,
            "校准规范": standard,
            "被测量": _clean(m.group("meas")),
            "测量范围": _clean(m.group("range")),
            "不确定度": _clean(m.group("uncert")),
            })

    print(f"✅ 已解析 {len(results)} 条校准能力记录。")
    return results


# =============================
#  构建节点
# =============================

def create_nodes(parsed_data: List[dict]) -> List[TextNode]:
    nodes = []
    splitter = SentenceSplitter(chunk_size=512)
    for item in parsed_data:
        text = (
            f"仪器名称：{item['仪器名称']}。\n"
            f"校准规范：{item['校准规范']}。\n"
            f"被测量：{item['被测量']}。\n"
            f"测量范围：{item['测量范围']}。\n"
            f"不确定度：{item['不确定度']}。"
        )
        for chunk in splitter.split_text(text):
            nodes.append(TextNode(text=chunk, metadata=item))
    return nodes


# =============================
#  初始化模型
# =============================

def init_models():
    embed_model = HuggingFaceEmbedding(model_name=Config.EMBED_MODEL_PATH)
    llm = OpenAILike(
        model="deepseek-chat",
        api_base=Config.API_BASE,
        api_key=Config.API_KEY,
        is_chat_model=True,
        max_tokens=1024,
        temperature=Config.TEMPERATURE
    )
    reranker = SentenceTransformerRerank(
        model=Config.RERANK_MODEL_PATH,
        top_n=Config.RERANK_TOP_K
    )
    Settings.embed_model = embed_model
    Settings.llm = llm
    test_embedding = embed_model.get_text_embedding("测试文本")
    print(f"Embedding 维度验证：{len(test_embedding)}")
    return embed_model, llm, reranker


# =============================
#  初始化向量数据库
# =============================

def init_vector_store(nodes: List[TextNode], embed_model):
    Path(Config.DB_DIR).mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=Config.DB_DIR)
    collection = client.get_or_create_collection("calibration_data")
    vector_store = ChromaVectorStore(chroma_collection=collection)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    if collection.count() == 0:
        print("📥 数据库为空，正在构建索引...")
        index = VectorStoreIndex(nodes, storage_context=storage_context, embed_model=embed_model)
        index.storage_context.persist(persist_dir=Config.DB_DIR)
    else:
        print("📂 检测到已有索引，直接加载。")
        index = VectorStoreIndex.from_vector_store(vector_store, embed_model=embed_model)
    return index


# =============================
# 查询函数（参数化）
# =============================
def query_calibration(parsed_data: List[Dict[str, Any]], std: str, meas: str):
    """
    在解析结果中查找指定校准规范和被测量
    """
    def normalize_text(s: str) -> str:
        if not s:
            return ""
        s = s.strip().lower()
        s = re.sub(r"\s+", "", s)  # 去掉空格
        return s

    std_norm = normalize_text(std)
    meas_norm = normalize_text(meas)

    results = []
    for item in parsed_data:
        std_text = normalize_text(item.get("校准规范", ""))
        meas_text = normalize_text(item.get("被测量", ""))
        if std_norm in std_text and meas_norm in meas_text:
            results.append(item)

    print(f"🔍 在规范「{std}」下查到 {len(results)} 条关于「{meas}」的记录。")
    return results

# =============================
# 示例调用
# =============================
def run_query(std: str, meas: str):
    # Step1. 解析文本
    parsed_data = parse_calibration_txt(Config.TXT_PATH)

    # Step2. 查询
    matched = query_calibration(parsed_data, std, meas)
    if not matched:
        print("⚠️ 未找到匹配记录。\n")
        return

    # Step3. 输出匹配内容
    for i, item in enumerate(matched, 1):
        print(f"{i}. 仪器名称: {item['仪器名称']}")
        print(f"   被测量: {item['被测量']}")
        print(f"   测量范围: {item['测量范围']}")
        print(f"   不确定度: {item['不确定度']}")
        print("-" * 50)

# =============================
#  主程序入口（参数化查询版，使用方法二）
# =============================

# =============================
#  主程序入口（RAG 查询版）
# =============================
def main_rag(query_text: str = None):
    # Step0. 初始化模型
    embed_model, llm, reranker = init_models()

    # Step1. 解析 TXT
    parsed_data = parse_calibration_txt(Config.TXT_PATH)
    nodes = create_nodes(parsed_data)

    # Step2. 构建索引
    index = init_vector_store(nodes, embed_model)
    retriever = index.as_retriever(similarity_top_k=Config.TOP_K)

    # Step3. 如果传入 query_text，则直接查询；否则进入交互式
    if query_text:
        query_engine = index.as_query_engine(retriever=retriever)
        response = query_engine.query(query_text)

        # 输出回答和匹配文档
        print("\n🧭 回答：", response.response.strip())
        if hasattr(response, "source_nodes"):
            print("\n📘 匹配文档内容：")
            for i, node in enumerate(response.source_nodes, 1):
                print(f"{i}. {node.text}")
                print("-" * 50)
        return

    # 交互式模式
    print("\n📡 校准能力 RAG 查询系统已启动！")
    while True:
        user_input = input("请输入查询（或 exit 退出）：").strip()
        if user_input.lower() in {"exit", "quit"}:
            break
        try:
            query_engine = index.as_query_engine(retriever=retriever)
            response = query_engine.query(user_input)
            print("\n🧭 回答：", response.response.strip())
            if hasattr(response, "source_nodes"):
                print("\n📘 匹配文档内容：")
                for i, node in enumerate(response.source_nodes, 1):
                    print(f"{i}. {node.text}")
                    print("-" * 50)
        except Exception as e:
            print("❌ 查询错误：", e)

# =============================
# 调用示例
# =============================
if __name__ == "__main__":
    # 示例1：直接传入查询文本
    main_rag("请查询 JJF 1462-2014 直流电子负载校准规范 对 电流 的测量要求")
    main_rag("请查询 光谱照度计校准规范 JJF 1989 对 波长 的测量要求")

