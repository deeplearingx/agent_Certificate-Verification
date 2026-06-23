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
    BATCH_SIZE = 5

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
    """
    修正版：适配 '依据参数' -> '项目名' -> '字段列表' 的结构
    """
    out = []

    # 1. 获取依据参数字典
    # 注意：JSON 中是 "依据参数": { "2 输出频率": {...}, ... }
    basis_params = cert_root.get("依据参数", {})

    if not basis_params:
        print("⚠️ 警告：'依据参数' 为空或未找到")
        return []

    # 2. 遍历每一个检测项目（例如 "2 输出频率", "3 正弦波输出幅度"）
    for project_name, fields_dict in basis_params.items():
        if not isinstance(fields_dict, dict):
            continue

        # 3. 确定这个项目下有多少个测试点（行数）
        # 方法：找到所有列表中最长的那个长度
        row_count = 0
        for key, val in fields_dict.items():
            if isinstance(val, list):
                row_count = max(row_count, len(val))

        if row_count == 0:
            continue

        # 4. 将列式数据转换为行式数据
        for i in range(row_count):
            # 初始化这一行的记录
            rec = {"param_name": project_name}  # 比如 "2 输出频率"

            # 遍历该项目下的所有字段（标称值、标准值、结论...）
            for field_key, field_val in fields_dict.items():
                # 如果是列表，取第 i 个；如果是单个值，直接用；如果越界，填 None
                val = None
                if isinstance(field_val, list):
                    if i < len(field_val):
                        val = str(field_val[i])
                else:
                    val = str(field_val)

                # 存入字典
                rec[field_key] = val

            # 5. 补充标准化字段供 LLM 识别 (映射你的 JSON 字段到 Prompt 需要的字段)
            # Prompt 通常需要: 量程, 标称值, 标准值, 误差, 允许误差, U(k=2)
            # 这里做一个简单的映射，保留原始键值，LLM 也能看懂

            # 将处理好的一行数据加入列表
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

        "### 核心判定流程（请严格按顺序执行）\n\n"

        "#### 第一步：参数匹配与 KB 优选策略 (KB Selection)\n"
            "当有多条 KB 条目匹配当前参数（如都有'辐照度'）时，请严格遵守以下**优选逻辑**：\n"
            "1. **范围覆盖优先**：\n"
            "   - 优先选择 **[范围包含测量点]** 的 KB 条目。\n"
            "   - **反例**：不要因为 KB #11 的名字叫 'UV-365' (更像) 就死盯着它，如果它的范围 (0-20) 不够，而 KB #3 'UV A1' (0-100) 能覆盖，**必须选择 KB #3**。\n"
            "2. **波段兼容性**：\n"
            "   - 承认通用波段包含特定波段。例如：'UV A1' 或 'UV A' 的范围通常可以覆盖 'UV-365'。\n"
            "3. **禁止过早 Failed**：\n"
            "   - 如果选中的 KB 导致范围超差 (Failed)，请立即检查列表中是否还有其他匹配项能让结果变 Pass。如果有，**切换 KB 并判定为 Pass**。\n\n"
        "#### 第二步：误差判定 (Error Check)\n"
            "   - **前提**：只有当证书中明确列出了“允许误差”、“MPE”或“限值”字段时，才进行此项比对。\n"
            "   - **无限值处理（关键）**：\n"
            "     - 若证书未给出允许误差（即“允许误差”栏为空或-），**绝对禁止**根据实测误差的大小自行判定 Failed。\n"
            "     - **修正系数逻辑**：如果证书包含“修正系数”(Correction Factor/Calibration Factor)，实测值与标准值偏差大是**正常现象**（系数正是为了修正此偏差）。\n"
            "     - **判定指令**：在此情况下，请直接判定 **Pass**，并在说明中备注“无允许误差限值，仅提供修正数据”。"
            "禁止自行计算误差："
            "如果证书源数据中包含“误差”、“示值误差”或“Error”字段，请直接提取。"
            "如果源数据中没有明确的误差字段（只有标准值和示值），请在“证书误差”列填“-”，不要自己做减法运算，防止计算错误。\n\n"
            

        "#### 第一步：参数匹配与范围核验 (Range Check)\n"
        "1. **常规情况**：\n"
        "   - 确认测量点是否在 KB 范围内。\n"
        "   - **原则**：采用【闭区间】。若 测量值 = 范围上限 或 测量值 = 范围下限，均视为 Pass。\n"
        "2. **特殊映射（必须优先执行）**：\n"
        "   - **幅度平坦度**：若 KB 无此项，将其映射为“幅度”。\n"
        "   - **紫外能量 (Energy vs Irradiance)**：\n"
        "     - 场景：证书为能量 (J/cm², mJ/cm²)，KB 为辐照度 (W/cm², mW/cm²)。\n"
        "     - **操作**：**禁止**比对数值大小（因物理量纲不同）。\n"
        "     - **判定**：只要波段匹配（如同为 UV-365），直接判定 **Pass (Physics Mapped)**，并在说明中备注“基于辐照度能力覆盖能量参数”。\n\n"

        "#### 第二步：误差判定 (Error Check)\n"
        "   - 若证书有明确的“允许误差”或“限值”：检查 |实测误差| 是否 ≤ |允许误差|。\n"
        "   - **注意**：“修正系数”(Correction Factor) 不是误差，若无明确误差值，跳过此步。\n\n"

        "#### 第三步：不确定度判定 (Uncertainty Check - 核心)\n"
        "**目标**：判断证书的不确定度 (Cert_U) 是否合格。合格标准是 Cert_U 的能力“差于”或“等于” KB_U。\n"
        "**数学规则**：数值上必须 **Cert_U ≥ KB_U**。\n\n"

        "请执行 **3步计算法**：\n"
        "1. **识别单位**：判断 Cert_U 和 KB_U 是绝对值 ($U$) 还是相对值 ($U_{rel}, \\%$ )。\n"
        "2. **单位归一化**：\n"
        "   - **情形 A (同类)**：都是 % 或都是绝对值。-> **直接提取数字比大小**。\n"
        "     - *特例提醒*：Cert=10%, KB=9.5%。因 10.0 >= 9.5，判定 **Pass**。\n"
        "   - **情形 B (混合)**：一个是 %，一个是绝对值。-> **必须折算**！\n"
        "     - 公式：$U_{折算} = 测量点数值 \\times U_{rel}(\\%)$ \n"
        "     - 示例：测量点 100V, KB=0.1V, Cert=0.2%。计算 100*0.002=0.2V。因 0.2V ≥ 0.1V，判定 **Pass**。\n"
        "3. **得出结论**：\n"
        "   - 符合 ≥ 关系 -> **Pass**。\n"
        "   - 不符合 -> **Failed**。\n\n"

        "### 兜底逻辑 (Self-Check)\n"
        "如果 KB 中找不到对应参数（如“幅度平坦度”无匹配项），但证书中明确列出了“允许误差”且实测误差符合要求：\n"
        "- 请判定为 **Pass (Self-Check)**。\n"
        "- 说明栏备注：KB无匹配，依据证书限值自校通过。\n\n"

        "### 输出格式\n"
        "对于当前批次的每个参数，输出如下表格（Markdown）：\n"
        "#### 参数名：[例如：幅度平坦度]\n"
        "| 序号 | 测量点 | KB编号 | 证书匹配项 | 知识库范围 | 证书误差 | 允许误差 | 证书U | KB_U | 判定 | 说明 |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
        "| 1 | 5000 mJ/cm² | ... | 辐照度 | 0.01~20mW | - | - | 10% | 9.5% | Pass | 能量/辐照度跨参数验证；U(10%)>=KB(9.5%)符合要求 |\n"
        "| 2 | 100 V | ... | ... | ... | ... | ... | 0.2% | 0.1V | Pass | U折算:100*0.2%=0.2V，0.2V≥0.1V，合格 |\n"
        "(Failed项请加粗)"
        "**注意**：'KB编号'列请填写真实的规程代号（如 JJG 879-2015），**不要**填写 KB_1, KB_2 这样的序号。"
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
    # 1. 加载 JSON
    data = json.load(open(json_file, "r", encoding="utf-8"))

    # 修正 Root 路径定位
    try:
        # 你的 JSON 结构是 properties -> 证书列表 -> items -> properties
        root = data["properties"]["证书列表"]["items"]["properties"]
    except KeyError as e:
        print(f"❌ JSON 结构解析失败，找不到键: {e}")
        return ""

    # ... (后续代码不变) ...
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
        report_lines.append("### 1. 向量库命中简表 ")
        if not kb_items:
            report_lines.append("> ⚠️ 无命中。")
        else:
            # 报告里只展示 Top 10 给人类看，但传给 LLM 是全部  top_k设置为30，这里显示全部
            report_lines.append(build_table(kb_items, top_k=30))

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
    # 1. 定义路径 (使用 pathlib 拼接)
    BASE_DIR = Path(r"D:\workspace\ai大模型开发课\文档核验\work_pdf\local_json")
    JSON_FILENAME = "2GB25008338-0003.json"
    JSON_PATH = str(BASE_DIR / JSON_FILENAME)
    cfg = Config()
    print(f"📂 加载证书：{JSON_PATH}")
    report = run_llm_mode(JSON_PATH, cfg)

    # 输出文件
    os.makedirs(cfg.OUTPUT_DIR, exist_ok=True)
    try:
        data = json.load(open(JSON_PATH, "r", encoding="utf-8"))
        root = data["properties"]["证书列表"]["items"]["properties"]
        cert_id = root.get("证书编号", "unknown")
    except Exception:
        cert_id = "unknown"
    out_path = Path(cfg.OUTPUT_DIR) / f"LLM_CNAs_{cert_id}.md"
    out_path.write_text(report, encoding="utf-8")
    print(f"\n📝 核验报告已生成：{out_path.resolve()}")

if __name__ == "__main__":
    main()

