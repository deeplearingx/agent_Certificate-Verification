import os
import re
import time
import json
import chromadb
import torch
from pathlib import Path
from typing import List, Dict, Any
from sentence_transformers import SentenceTransformer
from langchain_app.checks.parameter.parser import parse_value_with_unit

from llama_index.core import VectorStoreIndex, StorageContext, Settings, get_response_synthesizer
from llama_index.core.schema import TextNode
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.vector_stores.chroma import ChromaVectorStore
from llama_index.core import PromptTemplate
from llama_index.core.postprocessor import SentenceTransformerRerank  # 新增重排序组件
from llama_index.llms.openai_like import OpenAILike
from llama_index.core import (
    VectorStoreIndex,
    Document,
    SimpleDirectoryReader,
    StorageContext,
    ServiceContext,
    set_global_service_context,
)
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.vector_stores.chroma import ChromaVectorStore
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.schema import TextNode
from llama_index.core.postprocessor import SentenceTransformerRerank  # 新增重排序组件
from llama_index.llms.openai_like import OpenAILike


device = "cuda" if torch.cuda.is_available() else "cpu"
print("当前设备：", device)
# =============================
#  1️⃣ 系统配置
# =============================



class Config:
    TXT_PATH = "chunks_plain_text.txt"           # 原始txt文件路径
    DB_DIR = "./chroma_db"                      # Chroma数据库存放路径
    EMBED_MODEL_PATH = r"D:\workspace\ai_learning\pythonProject\models\BAAI\bge-m3"
    RERANK_MODEL_PATH = r"D:\workspace\ai_learning\pythonProject\models\BAAI\bge-reranker-large"  # 新增重排序模型路径
    LLM_MODEL_PATH = r"/home/cw/llms/Qwen/Qwen1___5-1___8B-Chat"    # 重排序模型
    API_BASE = "https://api.deepseek.com/v1"    # DeepSeek API
    API_KEY = os.getenv("DEEPSEEK_API_KEY", "")

    TOP_K = 15
    RERANK_TOP_K = 10
    MIN_RERANK_SCORE = 0.35
    TEMPERATURE = 0.3

# ==============================
# 自定义 PromptTemplate
# ==============================
prompt_template = PromptTemplate(
    input_variables=["context_str", "query_str"],
    template="""
你是一个文档核验助手，请根据提供的文档内容回答用户问题。请务必列出所有匹配的条目，不要合并或省略。
每条记录请使用如下格式：
1. 仪器名称：...
   被测量：...
   测量范围：...
   不确定度：...
   特别说明：...
   生效日期：...

文档内容：
{context_str}

问题：
{query_str}

请严格按照上面的格式回答。
"""
)

# =============================
#  2️⃣ 文本解析器：解析校准能力文本
# =============================
# 辅助：清理两边引号与空白
def _clean(s: str) -> str:
    if s is None:
        return ""
    return str(s).strip().strip(' \t\n\r"“”')

# 辅助：简单规范化测量范围字符（去最外层括号，统一波浪符，尽量在数值和单位间留空格）
def _normalize_range(rng: str) -> str:
    if not rng:
        return ""
    r = rng.strip()
    # 去掉最外层成对括号
    if (r.startswith("(") and r.endswith(")")) or (r.startswith("（") and r.endswith("）")):
        r = r[1:-1].strip()
    # 统一波浪符
    r = r.replace("~", "～").replace("–", "～").replace("—", "～")
    # 在数字与单位之间加空格（简单尝试）
    r = re.sub(r"(?P<num>[\d\.\u3000\uFF0D\uFF0E\uFF1A\uFF1B\uFF01～\-]+)(?P<unit>[a-zA-Z%μμmcdKkΩΩdBμ/]+)", r"\1 \2", r)
    # 保持分段符号 ; 或 ; 的原样
    return r


def _normalize_range_token(token: str) -> str:
    """规范化单个范围端点，尽量保留原始表达习惯。"""
    if not token:
        return ""
    t = _clean(token)
    t = t.replace("~", "～").replace("–", "～").replace("—", "～")
    t = re.sub(r"(?P<num>[\d\.\u3000\uFF0D\uFF0E\uFF1A\uFF1B\uFF01～\-]+)(?P<unit>[a-zA-Z%μμmcdKkΩΩdBμ/]+)", r"\1 \2", t)
    return t.strip().strip(" ,。；;")


def _normalize_simple_range_piece(piece: str) -> str:
    """仅对单个二端范围做从小到大归一化。"""
    if not piece:
        return ""

    text = piece.strip()
    if not text or ("～" not in text and "~" not in text):
        return text

    cond_left_match = re.fullmatch(r"(?P<left>.+?)\((?P<cond>[^()]+)\)\s*(?P<sep>[～~])\s*(?P<right>.+)", text)
    cond_right_match = re.fullmatch(r"(?P<left>.+?)\s*(?P<sep>[～~])\s*(?P<right>.+?)\((?P<cond>[^()]+)\)", text)
    if cond_left_match or cond_right_match:
        match = cond_left_match or cond_right_match
        left_raw = _normalize_range_token(match.group("left"))
        right_raw = _normalize_range_token(match.group("right"))
        cond_raw = match.group("cond").strip()
        if left_raw and right_raw:
            left_cmp = re.split(r"[（(]", left_raw, maxsplit=1)[0].strip()
            right_cmp = re.split(r"[（(]", right_raw, maxsplit=1)[0].strip()
            left_val, _ = parse_value_with_unit(left_cmp, keep_sign=True)
            right_val, _ = parse_value_with_unit(right_cmp, keep_sign=True)
            if left_val is not None and right_val is not None and left_val > right_val:
                left_raw, right_raw = right_raw, left_raw
            return f"{left_raw}～{right_raw}({cond_raw})"

    if any(sep in text for sep in [",", "，", ";", "；"]):
        return text

    delim_pos = None
    depth = 0
    for idx, ch in enumerate(text):
        if ch in "（(":
            depth += 1
        elif ch in "）)":
            depth = max(0, depth - 1)
        elif depth == 0 and ch in "～~":
            delim_pos = idx
            break

    if delim_pos is None:
        return text

    left = _normalize_range_token(text[:delim_pos])
    right = _normalize_range_token(text[delim_pos + 1 :])
    if not left or not right:
        return text

    left_cmp = re.split(r"[（(]", left, maxsplit=1)[0].strip()
    right_cmp = re.split(r"[（(]", right, maxsplit=1)[0].strip()
    left_val, _ = parse_value_with_unit(left_cmp, keep_sign=True)
    right_val, _ = parse_value_with_unit(right_cmp, keep_sign=True)
    if left_val is None or right_val is None or left_val <= right_val:
        return f"{left}～{right}"
    return f"{right}～{left}"


def _normalize_range_order(rng: str) -> str:
    if not rng:
        return ""
    text = _normalize_range(rng)
    if not text:
        return ""

    def _normalize_inner_ranges(text_value: str) -> str:
        def _repl(match: re.Match) -> str:
            inner = match.group(1)
            normalized_inner = _normalize_simple_range_piece(inner)
            return f"({normalized_inner})"

        prev_value = None
        cur_value = text_value
        while prev_value != cur_value:
            prev_value = cur_value
            cur_value = re.sub(r"\(([^()]+)\)", _repl, cur_value)
        return cur_value

    top_level = _normalize_simple_range_piece(text)
    return _normalize_inner_ranges(top_level)

# 辅助：清洗被测量（补全不闭合括号，去尾随标点）
def _normalize_measured(m: str) -> str:
    if not m:
        return ""
    s = m.strip()
    # 如果左括号多于右括号，简单补右括号
    if s.count("(") > s.count(")"):
        s = s + ")"
    # strip trailing punctuation
    s = s.strip(" ,。；;")
    return s


def _split_measure_range_segments(rng: str) -> List[str]:
    """
    将多段测量范围拆成独立段。
    仅在最外层分隔符处切分，避免把括号内条件切开。
    """
    if not rng:
        return []

    text = _normalize_range(rng)
    if not text:
        return []

    segments: List[str] = []
    buffer: List[str] = []
    depth = 0
    for ch in text:
        if ch in "（(":
            depth += 1
            buffer.append(ch)
            continue
        if ch in "）)":
            depth = max(0, depth - 1)
            buffer.append(ch)
            continue
        if ch in ",，;；" and depth == 0:
            segment = "".join(buffer).strip().strip(" ,。；;")
            if segment:
                segments.append(segment)
            buffer = []
            continue
        buffer.append(ch)

    tail = "".join(buffer).strip().strip(" ,。；;")
    if tail:
        segments.append(tail)
    return segments

# 主解析函数
def parse_calibration_txt(txt_path: str) -> List[Dict[str, Any]]:
    """
    更鲁棒的解析器，返回 list of dict，字段：
    '仪器名称','校准规范','被测量','测量范围','不确定度','特别说明','生效日期','raw_block'
    """
    raw = Path(txt_path).read_text(encoding="utf-8")
    # 先以 --- 或 连续两个以上换行分段（兼容不同输入）
    blocks = re.split(r"\n-{3,}\n|(?:\n\s*\n\s*\n)+", raw)

    results: List[Dict[str, Any]] = []

    # 匹配仪器标题行（兼容有无序号、带星号等）
    instr_re = re.compile(
        r"关于测量仪器[“\"]?(?P<instr>[^”\"\\n]+?)[”\"]?(?:（序号：(?P<idx>\d+)）)?[,，]?\s*其校准能力详情如下：",
        flags=re.I | re.S
    )

    # 能力条目正则（宽松），把被测量、测量范围、不确定度、特别说明、生效日期都尽量抓出来（可选）
    cap_re = re.compile(
        r"对于被测量[“\"]?(?P<meas>[^”\"]+)[”\"]?[，,]\s*"
        r"测量范围是[“\"]?(?P<range>[^”\"]+)[”\"]?[，,。;\s]*"
        r"(?:扩展不确定度\s*\(k=2\)\s*为[“\"]?(?P<uncert>[^”\"]*)[”\"]?[。；;，,]*)?"
        r"(?:\s*特别说明为[“\"]?(?P<note>[^”\"]*)[”\"]?[。；;，,]*)?"
        r"(?:\s*生效日期为[“\"]?(?P<effective>[^”\"]*)[”\"]?[。；;，,]*)?",
        flags=re.S
    )

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        # 解析仪器名与序号与规范
        instr_m = instr_re.search(block)
        if instr_m:
            instr_name = _clean(instr_m.group("instr"))
            idx = instr_m.group("idx")
            idx = int(idx) if idx and idx.isdigit() else None
        else:
            # 若未匹配到标题，尝试用首行作为仪器名
            first_line = block.splitlines()[0].strip() if block.splitlines() else "未知仪器"
            instr_name = _clean(first_line)
            idx = None

        # 校准规范（可选）
        std_m = re.search(r"遵循的主要校准规范是[“\"]?(?P<std>[^”\n]+?)[”\"]?", block)
        standard = _clean(std_m.group("std")) if std_m else ""

        # 查找所有能力条目
        # 行级兜底：补抓块级正则漏掉的能力条目
        parsed_line_texts = set()

        for m in cap_re.finditer(block):
            meas = _normalize_measured(_clean(m.group("meas") or ""))
            rng = _normalize_range_order(_clean(m.group("range") or ""))
            rng_segments = _split_measure_range_segments(rng)
            rng_segments_text = "?".join(rng_segments)
            rng_segments_json = json.dumps(rng_segments, ensure_ascii=False)
            uncert = _clean(m.group("uncert") or "")
            note = _clean(m.group("note") or "")
            effective = _clean(m.group("effective") or "")

            
            results.append({
            "测发器名称": instr_name,
            "序号": idx,
            "校准规范": standard,
            "被测量": meas,
            "测量范围": rng,
            "测量范围分段": rng_segments_text,
            "measure_range_segments_json": rng_segments_json,
            "measure_range_segment_count": len(rng_segments),
            "不确定度": uncert,
            "特别说明": note,
            "生效日期": effective,
            "raw_block": block[:400]
            })

        for line in [ln.strip() for ln in block.splitlines() if ln.strip()]:
            if "对于被测量" not in line:
                continue
            m2 = cap_re.search(line)
            if not m2:
                continue

            meas = _normalize_measured(_clean(m2.group("meas") or ""))
            rng = _normalize_range_order(_clean(m2.group("range") or ""))
            rng_segments = _split_measure_range_segments(rng)
            rng_segments_text = "、".join(rng_segments)
            rng_segments_json = json.dumps(rng_segments, ensure_ascii=False)
            uncert = _clean(m2.group("uncert") or "")
            note = _clean(m2.group("note") or "")
            effective = _clean(m2.group("effective") or "")

            
            results.append({
            "测发器名称": instr_name,
            "序号": idx,
            "校准规范": standard,
            "被测量": meas,
            "测量范围": rng,
            "测量范围分段": rng_segments_text,
            "measure_range_segments_json": rng_segments_json,
            "measure_range_segment_count": len(rng_segments),
            "不确定度": uncert,
            "特别说明": note,
            "生效日期": effective,
            "raw_block": block[:400]
            })

    print(f"✅ parse_calibration_txt: 提取到 {len(results)} 条能力记录。")
    return results


#添加查询函数
def query_measurement(parsed_data: List[dict], target_measurement: str):
    """从 parsed_data（parse_calibration_txt 的返回）中查找所有包含 target_measurement 的记录"""
    results = [
        {
            "仪器名称": item.get("仪器名称"),
            "被测量": item.get("被测量"),
            "测量范围": item.get("测量范围"),
            "不确定度": item.get("不确定度"),
            "特别说明": item.get("特别说明"),
            "生效日期": item.get("生效日期")
        }
        for item in parsed_data if target_measurement in (item.get("被测量") or "")
    ]

    print(f"查到 {len(results)} 条匹配 “{target_measurement}” 的记录。")
    return results
# =============================
#  3️⃣ 构建文档节点
# =============================

def create_nodes(parsed_data: List[dict]) -> List[TextNode]:
    nodes = []
    splitter = SentenceSplitter(chunk_size=512)

    for item in parsed_data:
        range_segments_text = item.get("measure_range_segments_json", "")
        text = (
            f"仪器名称：{item['仪器名称']}。\n"
            f"校准规范：{item['校准规范']}。\n"
            f"被测量：{item['被测量']}。\n"
            f"测量范围：{item['测量范围']}。\n"
        )
        if range_segments_text:
            text += f"测量范围分段：{item.get('测量范围分段', '')}。\n"
        text += (
            f"不确定度：{item['不确定度']}。"
        )

        chunks = splitter.split_text(text)
        for chunk in chunks:
            nodes.append(TextNode(text=chunk, metadata=item))
    return nodes


# =============================
#  4️⃣ 初始化模型
# =============================

# ================== 初始化模型 ==================
def init_models():
    """初始化模型并验证"""

    # Embedding模型
    embed_model = HuggingFaceEmbedding(
        model_name=Config.EMBED_MODEL_PATH,
    )

    # LLM
    # llm = HuggingFaceLLM(
    #     model_name=Config.LLM_MODEL_PATH,
    #     tokenizer_name=Config.LLM_MODEL_PATH,
    #     model_kwargs={
    #         "trust_remote_code": True,
    #     },
    #     tokenizer_kwargs={"trust_remote_code": True},
    #     generate_kwargs={"temperature": 0.3}
    # )

    # openai_like
    llm = OpenAILike(
        model="deepseek-chat",  # 可选模型：glm-4, glm-3-turbo, characterglm等
        api_base="https://api.deepseek.com/v1",  # 关键！必须指定此端点
        api_key="",
        context_window=128000,  # 按需调整（glm-4实际支持128K）
        is_chat_model=True,
        is_function_calling_model=False,  # GLM暂不支持函数调用
        max_tokens=1024,  # 最大生成token数（按需调整）
        temperature=0.3,  # 推荐范围 0.1~1.0
        top_p=0.7  # 推荐范围 0.5~1.0
    )

    # 初始化重排序器（新增）
    reranker = SentenceTransformerRerank(
        model=Config.RERANK_MODEL_PATH,
        top_n=Config.RERANK_TOP_K
    )



    Settings.embed_model = embed_model
    Settings.llm = llm

    # 验证模型
    test_embedding = embed_model.get_text_embedding("测试文本")
    print(f"Embedding维度验证：{len(test_embedding)}")

    return embed_model, llm, reranker  # 返回重排序器


# =============================
#  5️⃣ 向量数据库初始化 / 加载
# =============================

def init_vector_store(nodes: List[TextNode], embed_model):
    Path(Config.DB_DIR).mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=Config.DB_DIR)
    collection = client.get_or_create_collection("calibration_data")
    vector_store = ChromaVectorStore(chroma_collection=collection)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    # 如果数据库为空则重新索引
    if collection.count() == 0:
        print("📥 数据库为空，正在构建索引...")
        index = VectorStoreIndex(nodes, storage_context=storage_context, embed_model=embed_model)
        index.storage_context.persist(persist_dir=Config.DB_DIR)
        print("✅ 索引已建立完成。")
    else:
        print("📂 检测到已有索引，直接加载。")
        index = VectorStoreIndex.from_vector_store(vector_store, embed_model=embed_model)

    return index


# =============================
#  6️⃣ 主程序：RAG问答系统
# =============================

def main():
    embed_model,llm ,reranker = init_models()

    # embed_model = embed_model.to(device)
    # reranker = reranker.to(device)

    # Step 1. 解析txt
    parsed_data = parse_calibration_txt(Config.TXT_PATH)
    nodes = create_nodes(parsed_data)


    #查询测试：
    # 例如查询频带宽度（或输入你要查的被测量）
    res = query_measurement(parsed_data, "频带宽度")
    for r in res:
        print(r)


    # Step 2. 建立或加载索引
    index = init_vector_store(nodes, embed_model)
    retriever = index.as_retriever(similarity_top_k=Config.TOP_K)

    # Step 3. 进入交互循环
    print("\n📡 文档核验系统启动成功！（输入 'exit' 退出）\n")

    while True:
        query = input("❓请输入问题：").strip()
        if query.lower() in {"exit", "quit"}:
            break

        start = time.time()
        retrieved = retriever.retrieve(query)

        reranked = reranker.postprocess_nodes(retrieved, query_str=query)

        filtered = [n for n in reranked if n.score >= Config.MIN_RERANK_SCORE]

        if not filtered:
            print("⚠️ 未找到匹配信息，请尝试换个问法。\n")
            continue

        response = index.as_query_engine().query(query)
        elapsed = time.time() - start

        print(f"\n🧭 回答：{response.response.strip()}")
        print(f"⏱️ 耗时：{elapsed:.2f}s")
        print(f"📚 引用条数：{len(filtered)}")
        for i, n in enumerate(filtered, 1):
            meta = n.metadata
            print(f"  {i}. {meta.get('仪器名称')} | {meta.get('被测量')} | {meta.get('测量范围')}| {meta.get('不确定度')}")
        print("-" * 60)


if __name__ == "__main__":
    main()

