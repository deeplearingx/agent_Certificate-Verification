import os
import re
import time
import json
import chromadb
import torch
from pathlib import Path
from typing import List, Dict, Any
from sentence_transformers import SentenceTransformer

# 临时解决方案：禁用transformers的torch.load安全检查
os.environ['TRANSFORMERS_SKIP_TORCH_LOAD_SAFETY_CHECKS'] = 'true'

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
from llama_index.core import PromptTemplate
from langchain_app.checks.parameter.parser import parse_value_with_unit



device = "cuda" if torch.cuda.is_available() else "cpu"
print("当前设备：", device)


# =============================
#  1. 系统配置
# =============================


class Config:
    TXT_PATH = r"D:\workspace\ai大模型开发课\文档核验\document-verification-master\CNAS解析\output\页面提取自－认可的校准和测量能力范围(中文)-无线电+光学+时间频率(1).txt"  # 原始txt文件路径
    DB_DIR = "./vector_db/cnas_calibration"  # 主校准向量数据库路径（已统一）
    EMBED_MODEL_PATH = r"d:\workspace\ai大模型开发课\文档核验\document-verification-master\models"  # 本地句子嵌入模型
    RERANK_MODEL_PATH = r"d:\workspace\ai大模型开发课\文档核验\document-verification-master\models"  # 本地重排序模型
    LLM_MODEL_PATH = r"d:\workspace\ai大模型开发课\文档核验\document-verification-master\models"  # 本地语言模型
    API_BASE = "https://api.deepseek.com/v1"  # DeepSeek API
    API_KEY = os.getenv("DEEPSEEK_API_KEY", "")

    TOP_K = 70
    RERANK_TOP_K = 70
    MIN_RERANK_SCORE = 0.01
    TEMPERATURE = 0.3

def norm_code(s: str) -> str:
    s = (s or "").strip()
    m = re.search(r"\b(JJ[GF]|GJB)\s*(\d+)", s, re.IGNORECASE)
    if m:
        return f"{m.group(1).upper()}{m.group(2)}"  # [OK] 无空格
    return re.sub(r"\s+", "", s).upper()

def extract_basis_code(criterion: str):
    """
    从 '数字示波器检定规程 GJB 7691-2012' 提取 'GJB 7691'
    从 'JJG 237-2010' 提取 'JJG 237'
    """
    if not criterion:
        return None
    s = str(criterion)
    m = re.search(r"\b(JJ[GF]|GJB)\s*(\d+)(?:\s*-\s*\d{4})?\b", s, re.IGNORECASE)
    if not m:
        return None
    return f"{m.group(1).upper()}{m.group(2)}"  # [OK] 无空格

# ==============================
# 自定义 PromptTemplate
# ==============================

QA_TEMPLATE = (
    "<|im_start|>system\n"
    "你是一个文档核验助手，必须严格遵守以下规则：\n"
    "1. 仅使用提供的文档内容回答问题。\n"
    "2. 必须列出所有匹配的条目，不得合并或省略。\n"
    "3. 回答格式需严格遵守以下格式：\n"
    "   1. 仪器名称：...\n"
    "      被测量：...\n"
    "      测量范围：...\n"
    "      不确定度：...\n"
    "      特别说明：...\n"
    "      生效日期：...\n"
    "\n"
    "文档内容（共 {context_count} 条）：\n"
    "{context_str}\n"
    "<|im_end|>\n"
    "<|im_start|>user\n"
    "问题：{query_str}\n"
    "<|im_end|>\n"
    "<|im_start|>assistant\n"
)

response_template = PromptTemplate(QA_TEMPLATE)

# =============================
#  2. 文本解析器：解析校准能力文本
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

    # 多段范围、枚举列表和明显的复合表达式不在这里处理。
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
    """
    将可比较的双端范围按从小到大规范化。

    说明：
    - 仅处理明确的二端范围，如 `10 s～10 μs`、`<0.5 ns～40 ps`
    - 对于列表、多段条件、无法解析的表达式，保持原样
    - 仅在左右端均可解析且左端大于右端时交换顺序
    """
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

    # 先按顶层分隔符处理整个片段，再对括号内部的简单范围做归一化。
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
    仅在最外层分隔符处切分，避免把括号内的条件误切开。
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
    改进版解析器：
    - 确保校准依据（标准规范）被提取
    - 返回的字段包括中文原始字段
    """
    raw = Path(txt_path).read_text(encoding="utf-8")
    blocks = re.split(r"\n-{3,}\n|(?:\n\s*\n\s*\n)+", raw)

    results: List[Dict[str, Any]] = []

    # 仪器名正则
    instr_re = re.compile(
        r"关于测量仪器[“\"]?(?P<instr>[^”\"\\n]+?)[”\"]?(?:（序号：(?P<idx>\d+)）)?[,，]?\s*其校准能力详情如下：",
        flags=re.I | re.S
    )

    # 能力条目正则
    cap_re = re.compile(
        r"对于被测量[“\"]?(?P<meas>[^”\"]+)[”\"]?[，,]\s*"
        r"测量范围是[“\"]?(?P<range>[^”\"]+)[”\"]?[，,。;\s]*"
        r"(?:扩展不确定度\s*\(k=2\)\s*为[“\"]?(?P<uncert>[^”\"]*)[”\"]?[。；;，,]*)?"
        r"(?:\s*特别说明为[“\"]?(?P<note>[^”\"]*)[”\"]?[。；;，,]*)?"
        r"(?:\s*生效日期为[“\"]?(?P<effective>[^”\"]*)[”\"]?[。；;，,]*)?",
        flags=re.S
    )

    # 校准依据正则（重点改进）
    std_re = re.compile(
        r"(遵循|依据|标准规范)[的]*主要校准(?:依据|规范)是[“\"]?(?P<std>[^”\n]+)[”\"]?",
        flags=re.I
    )

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        # 仪器名称
        instr_m = instr_re.search(block)
        instr_name = _clean(instr_m.group("instr")) if instr_m else _clean(block.splitlines()[0] if block.splitlines() else "未知仪器")
        idx = int(instr_m.group("idx")) if instr_m and instr_m.group("idx") and instr_m.group("idx").isdigit() else None

        # 校准依据（标准规范）
        std_m = std_re.search(block)
        standard = _clean(std_m.group("std")) if std_m else "未知规范"  # 如果没有提取到，默认填“未知规范”

        # 能力条目
        # 行级兜底：补抓块级正则漏掉的能力条目
        basis_code = extract_basis_code(standard)
        file_code = basis_code if basis_code else "未知规程"
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
            "仪器名称": instr_name,
            "序号": idx,
            "校准依据": standard,
            "file_code": file_code,
            "standard_name": standard,
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

    print(f"parse_calibration_txt_fix: 提取到 {len(results)} 条能力记录。")
    return results



# 添加查询函数
# def query_measurement(parsed_data: List[dict], target_measurement: str):
#     """从 parsed_data（parse_calibration_txt 的返回）中查找所有包含 target_measurement 的记录"""
#     results = [
#         {
#             "仪器名称": item.get("仪器名称"),
#             "被测量": item.get("被测量"),
#             "校准依据": item.get("校准依据"),
#             "测量范围": item.get("测量范围"),
#             "不确定度": item.get("不确定度"),
#             "特别说明": item.get("特别说明"),
#             "生效日期": item.get("生效日期")
#         }
#         for item in parsed_data if target_measurement in (item.get("被测量") or "")
#     ]
#
#     print(f"查到 {len(results)} 条匹配 “{target_measurement}” 的记录。")
#     return results


# =============================
#  3. 构建文档节点
# =============================

def create_nodes(parsed_data: List[dict]) -> List[TextNode]:
    nodes = []
    splitter = SentenceSplitter(chunk_size=512)

    for item in parsed_data:
        instrument_name = item.get("仪器名称") or item.get("测发器名称") or ""
        range_segments = item.get("measure_range_segments_json", "")
        text = (
            f"仪器名称：{instrument_name}。\n"
            f"校准依据：{item['校准依据']}。\n"
            f"规程代号：{item.get('file_code','')}。\n"   # [OK] 可选增强
            f"被测量：{item['被测量']}。\n"
            f"测量范围：{item['测量范围']}。\n"
        )
        if range_segments:
            text += f"测量范围分段：{item.get('测量范围分段', '')}。\n"
        text += (
            f"不确定度：{item['不确定度']}。"
        )


        chunks = splitter.split_text(text)
        for chunk in chunks:
            nodes.append(TextNode(text=chunk, metadata=item))
    return nodes


# =============================
#  4. 初始化模型
# =============================

# ================== 初始化模型 ==================
def init_models():
    """初始化模型并验证"""

    # Embedding模型
    embed_model = HuggingFaceEmbedding(
        model_name=Config.EMBED_MODEL_PATH,
        device=device,
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
        top_n=Config.RERANK_TOP_K,
        device=device,
    )

    Settings.embed_model = embed_model
    Settings.llm = llm

    # 验证模型
    test_embedding = embed_model.get_text_embedding("测试文本")
    print(f"Embedding维度验证：{len(test_embedding)}")

    return embed_model, llm, reranker  # 返回重排序器


# =============================
#  5. 向量数据库初始化 / 加载
# =============================

def init_vector_store(nodes: List[TextNode], embed_model):
    Path(Config.DB_DIR).mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=Config.DB_DIR)
    collection = client.get_or_create_collection("calibration_data")
    vector_store = ChromaVectorStore(chroma_collection=collection)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    # 如果数据库为空则重新索引
    if collection.count() == 0:
        print("[IN] 数据库为空，正在构建索引...")
        index = VectorStoreIndex(nodes, storage_context=storage_context, embed_model=embed_model)
        index.storage_context.persist(persist_dir=Config.DB_DIR)
        print("[OK] 索引已建立完成。")
    else:
        print("[DB] 检测到已有索引，直接加载。")
        index = VectorStoreIndex.from_vector_store(vector_store, embed_model=embed_model)

    return index


# =============================
#  6. 主程序：RAG问答系统
# =============================

def main():
    print("[START] 初始化模型中，请稍候...")
    embed_model, llm, reranker = init_models()  # 初始化embedding、LLM、重排序器

    # 解析文本文件（只需执行一次）
    if not Path(Config.TXT_PATH).exists():
        print(f"[ERROR] 找不到文件：{Config.TXT_PATH}")
        return

    print(f"\n[FILE] 正在解析文档：{Config.TXT_PATH}")
    parsed_data = parse_calibration_txt(Config.TXT_PATH)
    nodes = create_nodes(parsed_data)

    print("\n[INDEX] 初始化向量数据库...")
    start_time = time.time()
    index = init_vector_store(nodes, embed_model)
    print(f"[OK] 索引加载完成，用时 {time.time() - start_time:.2f}s")

    # 构建检索器与响应生成器
    retriever = index.as_retriever(similarity_top_k=Config.TOP_K)
    response_synthesizer = get_response_synthesizer(
        text_qa_template=response_template,
        verbose=True
    )

    print("\n[OK] 系统已准备就绪！输入问题开始检索（输入 q 退出）")

    while True:
        query = input("\n[Q] 请输入问题：").strip()
        if not query:
            continue
        if query.lower() in ["q", "quit", "exit"]:
            print("[BYE] 退出系统，再见！")
            break

        start_time = time.time()

        # Step 1.：初始检索
        initial_nodes = retriever.retrieve(query)
        retrieval_time = time.time() - start_time
        print(f"[SEARCH] 检索到 {len(initial_nodes)} 条候选结果。")

        # Step 2.：重排序
        reranked_nodes = reranker.postprocess_nodes(initial_nodes, query_str=query)
        rerank_time = time.time() - start_time - retrieval_time

        # Step 3.：过滤
        filtered_nodes = [
            node for node in reranked_nodes if node.score >= Config.MIN_RERANK_SCORE
        ]
        print(f"[FILTER] 过滤后剩余 {len(filtered_nodes)} 条结果（阈值 = {Config.MIN_RERANK_SCORE}）")

        if not filtered_nodes:
            print("[WARN] 未找到与问题相关的文档内容，请尝试换个提问方式。")
            continue

        # Step 4.：生成回答
        response = response_synthesizer.synthesize(
            query, nodes=filtered_nodes
        )
        synthesis_time = time.time() - start_time - retrieval_time - rerank_time

        print("\n[ANSWER] ==== 智能助手回答 ====")
        print(response.response.strip())

        print("\n[REF] ==== 支持依据 ====")
        for i, node in enumerate(filtered_nodes[:70], 1):
            meta = node.metadata
            print(f"[{i}] 仪器名称：{meta.get('仪器名称', '未知')} | 被测量：{meta.get('被测量', '')}")
            print(f"    校准依据：{meta.get('校准依据', '')} ")
            print(f"    测量范围：{meta.get('测量范围', '')}")
            print(f"    不确定度：{meta.get('不确定度', '')}")
            print(f"    特别说明：{meta.get('特别说明', '')}")
            print(f"    生效日期：{meta.get('生效日期', '')}")
            print("-" * 60)

        print(f"\n[TIME] 性能统计：检索 {retrieval_time:.2f}s | 重排 {rerank_time:.2f}s | 合成 {synthesis_time:.2f}s")


if __name__ == "__main__":
    main()

