import os
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import chromadb
from chromadb.errors import NotFoundError
from sentence_transformers import SentenceTransformer
from llama_index.llms.openai_like import OpenAILike
from llama_index.core.base.llms.types import ChatMessage, MessageRole


# ===================== 配置 =====================
class Config:
    DB_DIR = r"./vector_db/cnas_calibration"
    COLLECTION = "calibration_data"
    EMBED_MODEL_PATH = r"D:\workspace\ai_learning\pythonProject\models\BAAI\bge-m3"
    OUTPUT_DIR = "./reports"
    OUTPUT_REPORT = "cnas_llm_verification_report.md"
    API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
    API_BASE = "https://api.deepseek.com/v1"
    MODEL = "deepseek-chat"
    TEMPERATURE = 0.2
    MAX_TOKENS = 1800
    TOPK = 30
    # 新增：控制每次传给大模型核验的参数个数
    # 建议设为 1~3，越小越精确，但调用次数会变多
    BATCH_SIZE = 2

# ===================== 工具函数 =====================
#切片，把证书的参数字段切分
def chunk_list(data: List[Any], size: int):
    """将列表 data 切分成大小为 size 的多个子列表"""
    for i in range(0, len(data), size):
        yield data[i:i + size]


def pick_first(text: str, *patterns: str) -> Optional[str]:
    if not text:
        return None
    for p in patterns:
        m = re.search(p, text, flags=re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return None

def parse_range_from_text(s: str) -> Optional[Tuple[float, float]]:
    if not s:
        return None
    text = s.replace("（", "(").replace("）", ")").replace("～", "~").replace("—", "-")
    m = re.search(r"\((-?\d+\.?\d*)\s*[~\-]\s*(-?\d+\.?\d*)\)", text)
    if not m:
        m = re.search(r"(-?\d+\.?\d*)\s*[~\-]\s*(-?\d+\.?\d*)", text)
    if not m:
        return None
    a, b = float(m.group(1)), float(m.group(2))
    return (min(a, b), max(a, b))

def detect_uncertainty_info(text: str) -> Dict[str, Any]:
    info = {"type": None, "value": None, "raw": None}
    if not text:
        return info
    m_abs = re.search(r"\bU\s*=\s*([-\d\.]+)", text, flags=re.IGNORECASE)
    m_rel = re.search(r"\bU\s*rel\s*=\s*([\d\.]+)\s*%", text, flags=re.IGNORECASE)
    if m_abs:
        info["type"] = "U"
        info["value"] = float(m_abs.group(1))
        info["raw"] = m_abs.group(0)
    elif m_rel:
        info["type"] = "Urel"
        info["value"] = float(m_rel.group(1)) / 100.0
        info["raw"] = m_rel.group(0)
    return info

def split_values_maybe_list(x) -> List[str]:
    if x is None:
        return []
    if isinstance(x, list):
        return [str(v) for v in x]
    return [p.strip() for p in re.split(r"[，,；;]\s*", str(x)) if p.strip()]

# ===================== KB 解析 =====================
def parse_kb_entry(doc: str, meta: Dict[str, Any]) -> Dict[str, Any]:
    instrument_name = meta.get("仪器名称") or pick_first(doc, r"仪器名称[：:]\s*(.+?)[。；]") or "N/A"
    standard_name = meta.get("校准依据") or pick_first(doc, r"校准依据[：:]\s*(.+?)[。；]") or "N/A"
    file_code = pick_first(doc, r"(JJG\s*\d{3,}-\d{3,}|\bJJF\s*\d{3,}-\d{3,})") or "N/A"
    measured = pick_first(doc, r"被测量[：:]\s*(.+?)[。；]") or "N/A"
    measure_range_text = pick_first(doc, r"测量范围[：:]\s*(.+?)[。；]") or "-"
    uncertainty = detect_uncertainty_info(doc)
    return {
        "instrument_name": instrument_name,
        "standard_name": standard_name,
        "file_code": file_code,
        "measured": measured,
        "measure_range_text": measure_range_text,
        "uncertainty": uncertainty,
        "raw": doc,
        "meta": meta or {},
    }

def build_table(entries: List[Dict[str, Any]], top_k: int = 10) -> str:
    table_lines = [
        "| 序号 | 仪器 | 规范(代号) | 被测量 | 测量范围摘录 | 不确定度 |",
        "| --- | --- | --- | --- | --- | --- |"
    ]
    for i, e in enumerate(entries[:top_k], 1):
        utype = e["uncertainty"].get("type", "N/A")
        uval = e["uncertainty"].get("value", "N/A")
        uinfo = f"{utype}={uval}" if uval != "N/A" else "N/A"
        table_lines.append(
            f"| {i} | {e['instrument_name']} | {e['standard_name']}/{e['file_code']} | "
            f"{e['measured']} | {e['measure_range_text'][:60]} | {uinfo} |"
        )
    return "\n".join(table_lines)

def query_kb(client: chromadb.Client, embedder: SentenceTransformer,
             collection_name: str, instrument_name: str, criterion: str,
             topk: int = 30) -> List[Dict[str, Any]]:
    print(f"\n📘 开始知识库检索：仪器名称='{instrument_name}'，校准依据='{criterion}'")
    m = re.search(r"(JJG\s*\d{3,}-\d{3,}|JJF\s*\d{3,}-\d{3,})", criterion)
    basis_code = m.group(1).replace(" ", "") if m else None
    query_text = f"{instrument_name} {basis_code}" if basis_code else f"{instrument_name} {criterion}".strip()
    try:
        coll = client.get_collection(collection_name)
    except Exception as e:
        print(f"❌ 加载集合失败：{e}")
        return []

    q_emb = embedder.encode([query_text]).tolist()
    res = coll.query(query_embeddings=q_emb, n_results=topk)
    docs = res.get("documents", [[]])[0] if res and res.get("documents") else []
    metas = res.get("metadatas", [[]])[0] if res and res.get("metadatas") else [{} for _ in docs]

    entries = []
    for d, m in zip(docs, metas):
        entries.append(parse_kb_entry(d, m))
    print(f"✅ 检索到 {len(entries)} 条结果")
    if entries:
        print("🔹 前 10 条结果示例：")
        for i, e in enumerate(entries[:10]):
            print(f"   {i+1}. {e['instrument_name']} - {e['measured']} - {e['uncertainty']}")
    return entries

# ===================== 证书参数处理 =====================
def collect_certificate_params(cert_root: Dict[str, Any]) -> List[Dict[str, Any]]:
    out = []
    meas_list = cert_root.get("依据参数", {}).get("测量参数", []) or []
    for item in meas_list:
        if not isinstance(item, dict):
            continue
        for pname, pfields in item.items():
            if not isinstance(pfields, dict):
                continue
            rec = {
                "param_name": pname,
                "量程": pfields.get("量程"),
                "频率": pfields.get("频率"),
                "标准值": split_values_maybe_list(pfields.get("标准值")),
                "标称值": split_values_maybe_list(pfields.get("标称值")),
                "误差": split_values_maybe_list(pfields.get("误差")),
                "允许误差": split_values_maybe_list(pfields.get("允许误差")),
                "结论": pfields.get("结论"),
                "U(k=2)": split_values_maybe_list(pfields.get("U(k=2)")),
            }
            out.append(rec)
    return out

# ===================== LLM =====================
def init_llm(cfg: Config):
    return OpenAILike(
        model=cfg.MODEL,
        api_base=cfg.API_BASE,
        api_key=cfg.API_KEY,
        is_chat_model=True,
        temperature=cfg.TEMPERATURE,
        max_tokens=cfg.MAX_TOKENS,
    )


def build_llm_messages(instrument_name: str, criterion: str, kb_items: List[Dict[str, Any]],
                       cert_params: List[Dict[str, Any]], context: str) -> List[ChatMessage]:
    system_prompt = (
        "你是一名资深计量/校准质量核验专家。你正在对一份校准证书进行**分批次**核验。\n"
        "当前输入的是该证书中的**部分测量参数**。\n\n"

        "### 输入数据说明\n"
        "1. **KB_Candidates**：知识库标准参考列表（全量参考库）。\n"
        "2. **Certificate_Params (Batch)**：当前批次待核验的参数列表（可能包含多个数值点）。\n"
        "   *请自动解析字段中包含的多值字符串（如 '10Hz, 20Hz...'）。*\n\n"

        "### 任务要求\n"
        "请直接针对当前批次的参数执行核验，无需重复输出通用的背景介绍。请执行：\n"
        "1. **依据匹配**：简要确认参数是否在 KB 范围内。\n"
        "2. **数值核验（核心）**：\n"
        "   - 匹配 KB 中的 `measured` 和 `measure_range_text`。\n"
        "   - 提取证书数值（标称值 > 标准值 > 量程\频率）。\n"
        "   - 比对不确定度：若证书 U(k=2) 存在且有效，必须 Cert_U ≥ KB_U。\n"
        "3. **结论判定**：|误差| ≤ |允许误差| 且 |U| ≤ |允许误差|/3 (若U存在)。\n\n"

        "### 输出格式\n"
        "对于当前批次的每个参数，输出如下表格（Markdown）：\n"
        "#### 参数名：[例如：幅度平坦度]\n"
        "| 序号 | 测量点 | 匹配KB项 | KB范围 | 证书误差 | 允许误差 | 证书U | KB_U(折算) | 判定 | 说明 |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
        "| ... | ... | ... | ... | ... | ... | ... | ... | ... | ... |\n"
        "(如果没有问题，简要总结；如果有 Failed 项，请加粗说明)"
    )

    # KB 数据处理
    kb_payload = []
    for e in kb_items:
        kb_payload.append({
            "measured": e.get("measured"),
            "measure_range_text": e.get("measure_range_text"),
            "uncertainty": e.get("uncertainty"),
            "standard_name": e.get("standard_name"),
            # 为了节省 token，如果 KB 条目太多，可以只传 instrument_name 一次，
            # 但为了准确性，建议保留
        })

    user_prompt = {
        "context": context,
        "instrument_from_json": instrument_name,
        "criterion": criterion,
        "kb_candidates": kb_payload,  # 依然传入 30 条，保证能查到
        "certificate_params_batch": cert_params  # 这里只是切片后的几个参数
    }

    return [
        ChatMessage(role=MessageRole.SYSTEM, content=system_prompt),
        ChatMessage(role=MessageRole.USER, content=json.dumps(user_prompt, ensure_ascii=False, indent=2)),
    ]

# ===================== 主流程 =====================
def run_llm_mode(json_file: str, cfg: Config) -> str:
    # 1. 加载并解析 JSON
    data = json.load(open(json_file, "r", encoding="utf-8"))
    root = data["properties"]["证书列表"]["items"]["properties"]
    instrument_name = root.get("INSTRUMENT_NAME") or root.get("仪器名称") or "N/A"
    criteria_list = root.get("校准依据", []) or ["N/A"]
    context = f"{root.get('委托单位名称', 'N/A')}-{root.get('客户地址', 'N/A')}"

    # 提取所有参数
    all_cert_params = collect_certificate_params(root)
    print(f"📊 共提取到 {len(all_cert_params)} 个测量参数项，准备分批核验...")

    # 2. 初始化模型和向量库
    print(f"🧠 加载语义模型：{cfg.EMBED_MODEL_PATH}")
    embedder = SentenceTransformer(cfg.EMBED_MODEL_PATH)
    client = chromadb.PersistentClient(path=cfg.DB_DIR)
    llm = init_llm(cfg)

    # 3. 初始化报告头部
    report_lines = [
        "# LLM 驱动的 CNAS 校准核验报告（分批处理版）",
        f"- 证书编号：{root.get('证书编号', 'N/A')}",
        f"- 仪器名称：**{instrument_name}**",
        f"- 总参数量：{len(all_cert_params)} 个",
        f"- 核验时间：{os.popen('date /t').read().strip()}",
        ""
    ]

    # 4. 针对每个校准依据进行循环
    for criterion in criteria_list:
        report_lines.append(f"## 依据：{criterion}")

        # 4.1 检索知识库 (KB) - 对整个依据只需要检索一次
        # 注意：这里我们保持检索 30 条，给 LLM 足够的上下文库
        kb_items = query_kb(client, embedder, cfg.COLLECTION, instrument_name, criterion, topk=cfg.TOPK)

        report_lines.append(f"> 📘 检索条件：仪器='{instrument_name}', 依据='{criterion}'")
        report_lines.append("### 1. 向量库命中简表 (Top 10)")
        if not kb_items:
            report_lines.append("> ⚠️ 无命中。")
        else:
            # 报告里只展示 Top 10 给人类看，但传给 LLM 是全部
            report_lines.append(build_table(kb_items, top_k=10))

        report_lines.append("\n### 2. 大模型参数核验详情\n")

        # 4.2 核心逻辑：对参数进行切片循环 (Slicing Loop)
        batch_count = 0
        total_batches = (len(all_cert_params) + cfg.BATCH_SIZE - 1) // cfg.BATCH_SIZE

        for batch_params in chunk_list(all_cert_params, cfg.BATCH_SIZE):
            batch_count += 1
            print(f"   ⏳ 正在处理第 {batch_count}/{total_batches} 批次 (本批 {len(batch_params)} 个参数)...")

            # 构造 Prompt，只传入当前的 batch_params
            messages = build_llm_messages(
                instrument_name,
                criterion,
                kb_items,  # 传入完整的 KB 上下文
                batch_params,  # 传入切片后的证书参数
                context
            )

            try:
                resp = llm.chat(messages=messages)
                content = resp.message.content.strip()

                # 优化输出：给每个批次加一个小标题，防止混淆
                report_lines.append(f"\n#### 📌 第 {batch_count} 批次核验结果\n")
                report_lines.append(content)
                report_lines.append("\n---\n")

            except Exception as e:
                err_msg = f"> 🚨 第 {batch_count} 批次 LLM 调用失败：{e}"
                print(err_msg)
                report_lines.append(err_msg)

    return "\n".join(report_lines)

def main():
    json_file = "2GB25009792-0001.json"
    cfg = Config()
    print(f"📂 加载证书：{json_file}")
    report = run_llm_mode(json_file, cfg)

    # 输出文件
    os.makedirs(cfg.OUTPUT_DIR, exist_ok=True)
    try:
        data = json.load(open(json_file, "r", encoding="utf-8"))
        root = data["properties"]["证书列表"]["items"]["properties"]
        cert_id = root.get("证书编号", "unknown")
    except Exception:
        cert_id = "unknown"
    out_path = Path(cfg.OUTPUT_DIR) / f"LLM_CNAs_{cert_id}.md"
    out_path.write_text(report, encoding="utf-8")
    print(f"\n📝 核验报告已生成：{out_path.resolve()}")

if __name__ == "__main__":
    main()

