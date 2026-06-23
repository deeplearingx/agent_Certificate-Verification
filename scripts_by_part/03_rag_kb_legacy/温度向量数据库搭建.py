import os
import re
import time
import json
import zipfile
import xml.etree.ElementTree as ET
import chromadb
import torch
from pathlib import Path
from typing import List, Dict, Any, Optional

try:
    import pandas as pd
except ModuleNotFoundError:
    pd = None
from llama_index.core import VectorStoreIndex, StorageContext, Settings, get_response_synthesizer
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
# from llama_index.core.postprocessor import SentenceTransformerRerank  # 新增重排序组件（已注释）
from llama_index.llms.openai_like import OpenAILike
from llama_index.core import PromptTemplate
# ---------------------
# 环境与设备
# ---------------------
device = "cuda" if torch.cuda.is_available() else "cpu"
print("当前设备：", device)

# =============================
#  配置
# =============================
class Config:
    # TXT_PATH = "chunks_plain_text.txt"  # 主校准文本（保持原有路径）
    # DB_DIR = "./vector_db/cnas_calibration"  # 主校准向量数据库路径（已统一）
    EMBED_MODEL_PATH = "./models"

    TEMP_EXCEL = "./data/温度要求.xlsx"  # 温度 Excel 文件路径（你上传的）
    TEMP_DB_DIR = "./vector_db/temperature"  # 温度向量库路径
    # EMBED_MODEL_PATH = r"D:\workspace\ai_learning\pythonProject\models\BAAI\bge-m3"
    # RERANK_MODEL_PATH = r"D:\workspace\ai_learning\pythonProject\models\BAAI\bge-reranker-large"
    # LLM 模型配置（保持你原有使用方式）
    API_BASE = "https://api.deepseek.com/v1"
    API_KEY = os.getenv("DEEPSEEK_API_KEY", "")  # 请替换或设置环境变量

    TOP_K = 15
    # RERANK_TOP_K = 10
    # MIN_RERANK_SCORE = 0.00
    TEMPERATURE = 0.3

# =============================
# Prompt 模板（保持原样）
# =============================
# QA_TEMPLATE = (
#     "<|im_start|>system\n"
#     "你是一个文档核验助手，必须严格遵守以下规则：\n"
#     "1. 仅使用提供的文档内容回答问题。\n"
#     "2. 必须列出所有匹配的条目，不得合并或省略。\n"
#     "3. 回答格式需严格遵守以下格式：\n"
#     "   1. 仪器名称：...\n"
#     "      被测量：...\n"
#     "      测量范围：...\n"
#     "      不确定度：...\n"
#     "      特别说明：...\n"
#     "      生效日期：...\n"
#     "\n"
#     "文档内容（共 {context_count} 条）：\n"
#     "{context_str}\n"
#     "<|im_end|>\n"
#     "<|im_start|>user\n"
#     "问题：{query_str}\n"
#     "<|im_end|>\n"
#     "<|im_start|>assistant\n"
# )
# response_template = PromptTemplate(QA_TEMPLATE)

##解析cnAS.txt（已注释掉主校准向量数据库相关代码）
# =============================
#  2️⃣ 文本解析器：解析校准能力文本（已注释）
# =============================
# 辅助：清洗被测量（补全不闭合括号，去尾随标点）
# def _normalize_measured(m: str) -> str:
#     if not m:
#         return ""
#     s = m.strip()
#     # 如果左括号多于右括号，简单补右括号
#     if s.count("(") > s.count(")"):
#         s = s + ")"
#     # strip trailing punctuation
#     s = s.strip(" ,。；;")
#     return s

# # 主解析函数
# def parse_calibration_txt(txt_path: str) -> List[Dict[str, Any]]:
#     """
#     更鲁棒的解析器，返回 list of dict，字段：
#     '仪器名称','依据编号','被测量','测量范围','不确定度','特别说明','生效日期','raw_block'
#     """
#     raw = Path(txt_path).read_text(encoding="utf-8")
#     # 先以 --- 或 连续两个以上换行分段（兼容不同输入）
#     blocks = re.split(r"\n-{3,}\n|(?:\n\s*\n\s*\n)+", raw)

#     results: List[Dict[str, Any]] = []

#     # 匹配仪器标题行（兼容有无序号、带星号等）
#     instr_re = re.compile(
#         r"关于测量仪器[“\"]?(?P<instr>[^”\"\\n]+?)[”\"]?(?:（序号：(?P<idx>\d+)）)?[,，]?\s*其校准能力详情如下：",
#         flags=re.I | re.S
#     )

#     # 能力条目正则（宽松），把被测量、测量范围、不确定度、特别说明、生效日期都尽量抓出来（可选）
#     cap_re = re.compile(
#         r"对于被测量[“\"]?(?P<meas>.+?)[”\"]?[，,]\s*"
#         r"测量范围是[“\"]?(?P<range>.+?)[”\"]?(?:[，,；;。]|$)\s*"
#         r"(?:.*?扩展不确定度\s*\(k=2\)\s*为[“\"]?(?P<uncert>.+?)[”\"]?(?:[。；;]|$))?"
#         r"(?:.*?特别说明为[“\"]?(?P<note>.*?)[”\"]?(?:[。；;]|$))?"
#         r"(?:.*?生效日期为[“\"]?(?P<effective>.*?)[”\"]?(?:[。；;]|$))?",
#         flags=re.S
#     )

#     for block in blocks:
#         block = block.strip()
#         if not block:
#             continue

#         # 解析仪器名与序号与规范
#         instr_m = instr_re.search(block)
#         if instr_m:
#             instr_name = _clean(instr_m.group("instr"))
#             idx = instr_m.group("idx")
#             idx = int(idx) if idx and idx.isdigit() else None
#         else:
#             # 若未匹配到标题，尝试用首行作为仪器名
#             first_line = block.splitlines()[0].strip() if block.splitlines() else "未知仪器"
#             instr_name = _clean(first_line)
#             idx = None

#         # 校准规范（可选）
#         std_m = re.search(r"遵循的主要依据编号是[“\"]?(?P<std>[^”\n]+?)[”\"]?", block)
#         standard = _clean(std_m.group("std")) if std_m else ""

#         # 查找所有能力条目
#         found_any = False
#         for m in cap_re.finditer(block):
#             found_any = True
#             meas = _normalize_measured(_clean(m.group("meas") or ""))
#             rng = _normalize_range(_clean(m.group("range") or ""))
#             uncert = _clean(m.group("uncert") or "")
#             note = _clean(m.group("note") or "")
#             effective = _clean(m.group("effective") or "")

#             results.append({
#                 "仪器名称": instr_name,
#                 "序号": idx,
#                 "依据编号": standard,
#                 "被测量": meas,
#                 "测量范围": rng,
#                 "不确定度": uncert,
#                 "特别说明": note,
#                 "生效日期": effective,
#                 "raw_block": block[:400]
#             })

#         # 若cap_re没有找到条目，尝试按行逐句匹配（容错）
#         if not found_any:
#             lines = re.split(r'[。\n]+', block)
#             for line in lines:
#                 if "对于被测量" in line:
#                     m2 = cap_re.search(line)
#                     if m2:
#                         meas = _normalize_measured(_clean(m2.group("meas") or ""))
#                         rng = _normalize_range(_clean(m2.group("range") or ""))
#                         uncert = _clean(m2.group("uncert") or "")
#                         note = _clean(m2.group("note") or "")
#                         effective = _clean(m2.group("effective") or "")
#                         results.append({
#                             "仪器名称": instr_name,
#                             "序号": idx,
#                             "依据编号": standard,
#                             "被测量": meas,
#                             "测量范围": rng,
#                             "不确定度": uncert,
#                             "特别说明": note,
#                             "生效日期": effective,
#                             "raw_block": block[:400]
#                         })

#     # 输出统计日志（便于调试）
#     print(f"✅ parse_calibration_txt: 提取到 {len(results)} 条能力记录。")
#     return results

# # =============================
# #  构建CNAS文档节点（已注释）
# # =============================

# def create_nodes(parsed_data: List[dict]) -> List[TextNode]:
#     nodes = []
#     splitter = SentenceSplitter(chunk_size=512)

#     for item in parsed_data:
#         text = (
#             f"仪器名称：{item['仪器名称']}。\n"
#             f"依据编号：{item['依据编号']}。\n"
#             f"被测量：{item['被测量']}。\n"
#             f"测量范围：{item['测量范围']}。\n"
#             f"不确定度：{item['不确定度']}。"
#         )

#         chunks = splitter.split_text(text)
#         for chunk in chunks:
#             nodes.append(TextNode(text=chunk, metadata=item))
#     return nodes

# -------------------------
# 这里我们实现温度 Excel 解析与节点创建
# -------------------------
def _clean_temperature_cell(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def _extract_basis_code(text: str) -> str:
    match = re.search(r"\b(JJ[GF]|GJB)\s*(\d+)(?:\s*-\s*\d{4})?\b", text or "", re.IGNORECASE)
    if not match:
        return ""
    return f"{match.group(1).upper()} {match.group(2)}"


def _read_xlsx_rows_stdlib(excel_path: str) -> List[Dict[str, str]]:
    ns = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    rows: List[List[str]] = []
    with zipfile.ZipFile(excel_path) as zf:
        shared_strings: List[str] = []
        if "xl/sharedStrings.xml" in zf.namelist():
            shared_root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for si in shared_root.findall("a:si", ns):
                shared_strings.append("".join(node.text or "" for node in si.iterfind(".//a:t", ns)))

        sheet_root = ET.fromstring(zf.read("xl/worksheets/sheet1.xml"))
        for row in sheet_root.findall(".//a:sheetData/a:row", ns):
            values: List[str] = []
            for cell in row.findall("a:c", ns):
                cell_type = cell.get("t")
                value_node = cell.find("a:v", ns)
                value = ""
                if value_node is not None and value_node.text is not None:
                    value = value_node.text
                    if cell_type == "s":
                        value = shared_strings[int(value)]
                values.append(_clean_temperature_cell(value))
            rows.append(values)

    if not rows:
        return []

    header = rows[0]
    normalized_header = [name if name else f"__col_{idx}" for idx, name in enumerate(header)]
    return [
        {normalized_header[idx]: row[idx] if idx < len(row) else "" for idx in range(len(normalized_header))}
        for row in rows[1:]
    ]


def _read_temperature_excel_rows(excel_path: str) -> List[Dict[str, str]]:
    if pd is not None:
        df = pd.read_excel(excel_path, dtype=str)
        df.fillna("", inplace=True)
        normalized_columns = [
            str(col).strip() if str(col).strip() and not str(col).startswith("Unnamed:") else f"__col_{idx}"
            for idx, col in enumerate(df.columns)
        ]
        df.columns = normalized_columns
        return [
            {col: _clean_temperature_cell(row[col]) for col in normalized_columns}
            for _, row in df.iterrows()
        ]
    return _read_xlsx_rows_stdlib(excel_path)


def _row_value(row: Dict[str, str], *keys: str) -> str:
    for key in keys:
        value = _clean_temperature_cell(row.get(key, ""))
        if value:
            return value
    return ""


def _normalize_temperature_record(row: Dict[str, str]) -> Optional[Dict[str, str]]:
    instrument_name = _row_value(row, "INSTRUMENT_NAME", "仪器名称", "细类名称")
    file_name = _row_value(row, "FILE_NAME", "依据名称", "依据")
    file_code = _row_value(row, "FILE_CODE", "依据编号")
    if not file_code:
        file_code = _extract_basis_code(file_name)
    organization = _row_value(row, "认可组织")
    version_num = _row_value(row, "VERSION_NUM")
    sub_type_name = _row_value(row, "SUB_TYPE_NAME", "中类名称")
    category_type = _row_value(row, "类型", "大类名称")
    temp_requirement = _row_value(row, "温度要求", "温度")
    humidity_requirement = _row_value(row, "相对湿度要求", "相对湿度")
    max_temp_delta = _row_value(row, "最大温度变化范围", "最大温差", "__col_6")

    if not any((instrument_name, file_name, file_code, temp_requirement, humidity_requirement, max_temp_delta)):
        return None

    rec = {
        "类型": category_type,
        "INSTRUMENT_NAME": instrument_name,
        "FILE_CODE": file_code,
        "FILE_NAME": file_name,
        "认可组织": organization,
        "VERSION_NUM": version_num,
        "SUB_TYPE_NAME": sub_type_name,
        "温度要求": temp_requirement,
        "相对湿度要求": humidity_requirement,
        "最大温度变化范围": max_temp_delta,
    }
    rec["__text"] = (
        f"仪器名称 {instrument_name}，"
        f"依据编号 {file_code}，"
        f"依据名称 {file_name}，"
        f"温度要求 {temp_requirement}，"
        f"认可组织 {organization}，"
        f"相对湿度要求 {humidity_requirement}，"
        f"最大温度变化范围 {max_temp_delta}"
    )
    return rec


def parse_temperature_excel(excel_path: str) -> List[Dict[str, Any]]:
    """
    读取 Excel，并把每行转为 dict。
    兼容两类 schema：
    1. 旧版英文列：类型, INSTRUMENT_NAME, FILE_CODE, FILE_NAME, 认可组织, VERSION_NUM,
       SUB_TYPE_NAME, 温度要求, 相对湿度要求, 最大温度变化范围
    2. 当前真实 Excel：序号, 细类名称, 中类名称, 大类名称, 依据, 温度, <空列>, 相对湿度, 备注
    """
    rows = _read_temperature_excel_rows(excel_path)
    records = []
    for row in rows:
        rec = _normalize_temperature_record(row)
        if rec is not None:
            records.append(rec)
    print(f"✅ parse_temperature_excel: 解析到 {len(records)} 条温度记录。")
    return records

def create_temp_nodes(temp_records: List[Dict[str, Any]]) -> List[TextNode]:
    nodes: List[TextNode] = []
    splitter = SentenceSplitter(chunk_size=512)
    for rec in temp_records:
        text = rec.get("__text", "")
        if not text:
            # 如果没有文本拼接，则用 key:value 拼接
            text = "；".join([f"{k}：{v}" for k,v in rec.items() if k != "__text" and v != ""])
        chunks = splitter.split_text(text)
        for chunk in chunks:
            nodes.append(TextNode(text=chunk, metadata=rec))
    return nodes

# -------------------------
# 初始化模型（embedding, llm）
# -------------------------
def init_models():
    """初始化 embedding/llm（重排序器已注释）"""
    # Embedding
    embed_model = HuggingFaceEmbedding(
        model_name=Config.EMBED_MODEL_PATH,
    )

    # OpenAI-like LLM（DeepSeek）
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

    # reranker = SentenceTransformerRerank(
    #     model=Config.RERANK_MODEL_PATH,
    #     top_n=Config.RERANK_TOP_K
    # )

    Settings.embed_model = embed_model
    Settings.llm = llm

    # 验证embedding
    try:
        emb = embed_model.get_text_embedding("测试")
        print(f"Embedding维度验证：{len(emb)}")
    except Exception as e:
        print("⚠️ embedding 验证失败：", e)

    return embed_model, llm

# -------------------------
# 初始化/加载 向量库（主校准库与温度库）
# -------------------------
def init_vector_store(nodes: List[TextNode], embed_model, db_dir: str, collection_name: str) -> VectorStoreIndex:
    Path(db_dir).mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=db_dir)
    collection = client.get_or_create_collection(collection_name)
    vector_store = ChromaVectorStore(chroma_collection=collection)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    if collection.count() == 0:
        print(f"📥 数据库 {db_dir}（集合：{collection_name}）为空，正在构建索引...")
        index = VectorStoreIndex(nodes, storage_context=storage_context, embed_model=embed_model)
        index.storage_context.persist(persist_dir=db_dir)
        print(f"✅ 索引已建立完成：{db_dir}")
    else:
        print(f"📂 检测到已有索引（{db_dir}），直接加载。")
        index = VectorStoreIndex.from_vector_store(vector_store, embed_model=embed_model)

    return index

# -------------------------
# 温度数值解析小工具（从字符串中提取数字/区间）
# -------------------------
def extract_numbers_from_str(s: str) -> List[float]:
    """
    尝试从字符串中提取所有可能的数值（支持负号、小数、范围格式等）
    返回浮点数列表（对于区间 '20-25' 返回 [20.0,25.0]）
    """
    if not s:
        return []
    # 将中文到英文符号统一
    s = s.replace("，", ",").replace("；", ";").replace("：", ":").replace("。", ".")
    # 找到带单位与不带单位的数字或范围
    nums = []
    # 先处理区间形式 like '20-25' 或 '20 至 25'
    for part in re.split(r'[;,/]', s):
        part = part.strip()
        # 匹配 20-25 or 20 ~ 25 或 20 至 25
        m = re.search(r'(-?\d+\.?\d*)\s*(?:-|～|~|至)\s*(-?\d+\.?\d*)', part)
        if m:
            try:
                nums.append(float(m.group(1)))
                nums.append(float(m.group(2)))
                continue
            except:
                pass
        # 单个数值
        m2 = re.search(r'(-?\d+\.?\d*)', part)
        if m2:
            try:
                nums.append(float(m2.group(1)))
            except:
                pass
    return nums

# -------------------------
# 温度相关问答的简单处理器
# -------------------------
def temperature_answer_handler(query: str, temp_records: List[Dict[str, Any]]):
    """
    如果 query 包含统计关键字（最高/最大/最低/平均/超过），则尝试直接根据 temp_records 里 '温度要求' 字段做数值统计并返回。
    否则返回 None（表示使用语义检索）
    """
    q = query.lower()
    # 常见统计词
    if any(k in q for k in ["最高", "最大", "max", "最热"]):
        # 找出所有温度字段可解析的最大值
        max_val = None
        max_rec = None
        for rec in temp_records:
            nums = extract_numbers_from_str(rec.get("温度要求", ""))
            if nums:
                local_max = max(nums)
                if max_val is None or local_max > max_val:
                    max_val = local_max
                    max_rec = rec
        if max_val is not None:
            return f"最高温度（从 '温度要求' 字段解析）: {max_val}。对应记录：{max_rec}"
        else:
            return "未能在温度字段中解析到数值。"

    if any(k in q for k in ["最低", "最小", "min"]):
        min_val = None
        min_rec = None
        for rec in temp_records:
            nums = extract_numbers_from_str(rec.get("温度要求", ""))
            if nums:
                local_min = min(nums)
                if min_val is None or local_min < min_val:
                    min_val = local_min
                    min_rec = rec
        if min_val is not None:
            return f"最低温度（从 '温度要求' 字段解析）: {min_val}。对应记录：{min_rec}"
        else:
            return "未能在温度字段中解析到数值。"

    if any(k in q for k in ["平均", "均值", "平均值", "mean"]):
        vals = []
        for rec in temp_records:
            nums = extract_numbers_from_str(rec.get("温度要求", ""))
            vals.extend(nums)
        if vals:
            avg = sum(vals) / len(vals)
            return f"温度平均值（基于温度要求字段解析）: {avg:.3f}"
        else:
            return "未能在温度字段中解析到数值。"

    # '超过 N' 类型
    m = re.search(r'超过\s*(-?\d+\.?\d*)', query)
    if m:
        threshold = float(m.group(1))
        matched = []
        for rec in temp_records:
            nums = extract_numbers_from_str(rec.get("温度要求", ""))
            # 若任一数值超过阈值，则认为匹配
            if any(n > threshold for n in nums):
                matched.append(rec)
        return f"找到 {len(matched)} 条记录满足温度要求超过 {threshold}：\n示例（最多10条）: {matched[:10]}"

    # 若没有匹配统计意图，返回 None 表示使用语义检索
    return None

# -------------------------
# 主函数（整合）
# -------------------------
def main():
    print("🚀 初始化模型中，请稍候...")
    embed_model, llm = init_models()

    # # ---------- 主校准文本解析（保持你的原逻辑） ----------
    # if Path(Config.TXT_PATH).exists():
    #     print(f"\n📄 正在解析文档：{Config.TXT_PATH}")
    #     # 你原来的 parse_calibration_txt & create_nodes 函数放好后调用
    #     parsed_data = parse_calibration_txt(Config.TXT_PATH)  # 请确保该函数在文件中可用
    #     nodes_calib = create_nodes(parsed_data)  # 请确保该函数在文件中可用
    # else:
    #     print(f"⚠️ 找不到主 TXT: {Config.TXT_PATH}，校准库将跳过构建。")
    #     parsed_data = []
    #     nodes_calib = []
    #
    # # ---------- 初始化校准向量库 ----------
    # if nodes_calib:
    #     index_calib = init_vector_store(nodes_calib, embed_model, Config.DB_DIR, "cnas_calibration_data")
    #     retriever_calib = index_calib.as_retriever(similarity_top_k=Config.TOP_K)
    # else:
    #     index_calib = None
    #     retriever_calib = None
    #
    # # ---------- 解析温度 Excel 并构建温度向量库 ----------
    # temp_records = []
    # if Path(Config.TEMP_EXCEL).exists():
    #     print(f"\n🌡️ 正在解析温度 Excel：{Config.TEMP_EXCEL}")
    #     temp_records = parse_temperature_excel(Config.TEMP_EXCEL)
    #     nodes_temp = create_temp_nodes(temp_records)
    #     index_temp = init_vector_store(nodes_temp, embed_model, Config.TEMP_DB_DIR, "temperature_data")
    #     retriever_temp = index_temp.as_retriever(similarity_top_k=Config.TOP_K)
    # else:
    #     print("⚠️ 未找到温度.xlsx，跳过温度数据库加载。")
    #     retriever_temp = None
    #
    # # ---------- 构建 response_synthesizer（用于生成最终回答） ----------
    # response_synthesizer = get_response_synthesizer(
    #     # text_qa_template=response_template,
    #     verbose=True
    # )
    #
    # print("\n✅ 系统已准备就绪！输入问题开始检索（输入 q 退出）")
    #
    # while True:
    #     query = input("\n❓ 请输入问题：").strip()
    #     if not query:
    #         continue
    #     if query.lower() in ["q", "quit", "exit"]:
    #         print("👋 退出系统，再见！")
    #         break
    #
    #     # 先判断是否属于温度类问题（关键词路由）
    #     if retriever_temp and any(k in query for k in ["温度", "湿度", "环境", "℃", "K", "最大温度", "温度要求"]):
    #         # 先尝试直接用数值统计处理器
    #         stat_ans = temperature_answer_handler(query, temp_records)
    #         if stat_ans is not None:
    #             print("\n🌡️ 温度统计结果：")
    #             print(stat_ans)
    #             continue
    #
    #         # 否则使用语义检索 + 重排 + LLM 生成回答
    #         print("🌡️ 使用温度知识库进行语义检索...")
    #         initial_nodes = retriever_temp.retrieve(query)
    #     else:
    #         # 使用校准库
    #         if not retriever_calib:
    #             print("⚠️ 未加载校准知识库，也未检测到温度数据库。无法检索。")
    #             continue
    #         initial_nodes = retriever_calib.retrieve(query)
    #
    #     # 下面与原逻辑一致：重排序 -> 过滤 -> 合成
    #     start_time = time.time()
    #     print(f"🔍 检索到 {len(initial_nodes)} 条候选结果。")
    #
    #     # 重排序
    #     try:
    #         reranked_nodes = reranker.postprocess_nodes(initial_nodes, query_str=query)
    #     except Exception as e:
    #         print("⚠️ 重排序失败，使用初始检索结果：", e)
    #         reranked_nodes = initial_nodes
    #
    #     # 过滤
    #     filtered_nodes = [node for node in reranked_nodes if getattr(node, "score", 0) >= Config.MIN_RERANK_SCORE]
    #     print(f"🎯 过滤后剩余 {len(filtered_nodes)} 条结果（阈值 = {Config.MIN_RERANK_SCORE}）")
    #
    #     if not filtered_nodes:
    #         print("⚠️ 未找到与问题相关的文档内容，请尝试换个提问方式。")
    #         continue
    #
    #     # 合成回答（传入过滤后的节点）
    #     try:
    #         response = response_synthesizer.synthesize(query, nodes=filtered_nodes)
    #         print("\n🧾 ==== 智能助手回答 ====")
    #         print(response.response.strip())
    #     except Exception as e:
    #         print("❌ 合成回答失败：", e)
    #         # fallback: 打印前几条 metadata 作为参考
    #         print("\n📚 ==== 支持依据（降级展示） ====")
    #         for i, node in enumerate(filtered_nodes[:5], 1):
    #             meta = node.metadata
    #             print(f"[{i}] {meta}")
    #         continue
    #
    #     # 显示支持依据简要
    #     print("\n📚 ==== 支持依据 ====")
    #     for i, node in enumerate(filtered_nodes[:5], 1):
    #         meta = node.metadata
    #         print(f"[{i}] 仪器名称：{meta.get('仪器名称', meta.get('INSTRUMENT_NAME', '未知'))} | 被测量：{meta.get('被测量', '')}")
    #         print(f"    测量范围：{meta.get('测量范围', '')}")
    #         print(f"    不确定度：{meta.get('不确定度', '')}")
    #         print(f"    特别说明：{meta.get('特别说明', '')}")
    #         print(f"    生效日期：{meta.get('生效日期', '')}")
    #         print("-" * 60)
    #
    #     print(f"\n⏱️ 性能统计：用时 {time.time() - start_time:.2f}s")


  # ---------- 跳过校准文本 ----------
    print("🧊 跳过校准库，仅加载温度数据库。")
    retriever_calib = None

    # ---------- 解析温度 Excel 并构建温度向量库 ----------
    temp_records = []
    if Path(Config.TEMP_EXCEL).exists():
        print(f"\n🌡️ 正在解析温度 Excel：{Config.TEMP_EXCEL}")
        temp_records = parse_temperature_excel(Config.TEMP_EXCEL)
        nodes_temp = create_temp_nodes(temp_records)
        index_temp = init_vector_store(nodes_temp, embed_model, Config.TEMP_DB_DIR, "temperature_data")
        retriever_temp = index_temp.as_retriever(similarity_top_k=Config.TOP_K)
    else:
        print("⚠️ 未找到温度.xlsx，跳过温度数据库加载。")
        retriever_temp = None

    # ---------- response_synthesizer ----------
    response_synthesizer = get_response_synthesizer(verbose=True)
    print("\n✅ 系统已准备就绪！输入问题开始检索（输入 q 退出）")

    while True:
        query = input("\n❓ 请输入问题：").strip()
        if not query:
            continue
        if query.lower() in ["q", "quit", "exit"]:
            print("👋 退出系统，再见！")
            break

        if not retriever_temp:
            print("⚠️ 温度数据库未加载，无法检索。")
            continue

        # 🔍 强制所有问题都走温度库
        stat_ans = temperature_answer_handler(query, temp_records)
        if stat_ans is not None:
            print("\n🌡️ 温度统计结果：")
            print(stat_ans)
            continue

        print("🌡️ 使用温度知识库进行语义检索...")
        initial_nodes = retriever_temp.retrieve(query)
 # ✅ 输出检索结果
        if not initial_nodes:
            print("⚠️ 没有检索到相似内容。")
        else:
            print(f"🔍 共检索到 {len(initial_nodes)} 条结果，展示前 {min(5, len(initial_nodes))} 条：")
            for i, node in enumerate(initial_nodes[:5]):
                score = getattr(node, "score", None)
                score_text = f"{score:.3f}" if score is not None else "N/A"
                print(f"\n🧩 第 {i+1} 条结果（相似度 = {score_text}）：")
                # 兼容不同对象结构（node.text 或 node.node.text）
                text = getattr(node, "text", None) or getattr(getattr(node, "node", None), "text", "")
                print(text[:300] if text else "⚠️ 无法读取文本内容。")

if __name__ == "__main__":
    main()

