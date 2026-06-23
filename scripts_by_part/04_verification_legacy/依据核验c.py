import os
import json
import re
import time
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed # 新增：支持并发

import chromadb
from chromadb.errors import NotFoundError
from sentence_transformers import SentenceTransformer
from openai import OpenAI


# ===================== 配置 =====================
class Config:
    DB_DIR = r"./vector_db/cnas_calibration"
    COLLECTION = "calibration_data"
    EMBED_MODEL_PATH = r"D:\workspace\ai_learning\pythonProject\models\BAAI\bge-m3"
    OUTPUT_DIR = "./reports"
    API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
    API_BASE = "https://api.deepseek.com"
    MODEL = "deepseek-chat"
    TEMPERATURE = 0.1
    MAX_TOKENS = 2048
    TOPK = 35
    BATCH_SIZE = 5
    max_workers = 5

# ===================== 1. 定义 Python 计算工具集 =====================

def parse_value_with_unit(val_str, base_val=None):
    """数值解析与单位折算工具"""
    if not val_str: return 0.0, "abs"
    s = str(val_str).strip().lower()
    m = re.search(r"([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)", s)
    if not m: return 0.0, "abs"
    num = float(m.group(1))

    is_rel = '%' in s or 'rel' in s
    if is_rel and base_val is not None:
        return abs(base_val * (num / 100.0)), "rel_converted"
    return num, "abs"


def verify_uncertainty_logic(measure_val, cert_u, kb_u):
    """【工具1】不确定度合规性校验: Cert_U >= KB_U -> PASS"""
    try:
        m_val, _ = parse_value_with_unit(measure_val)
        c_val, c_type = parse_value_with_unit(cert_u, m_val)
        k_val, k_type = parse_value_with_unit(kb_u, m_val)

        # 容差 1e-9
        if c_val >= (k_val - 1e-9):
            status = "PASS"
            reason = f"Cert({c_val:.6g}) >= KB({k_val:.6g})"
        else:
            status = "FAIL"
            reason = f"Cert({c_val:.6g}) < KB({k_val:.6g})"

        return json.dumps({"status": status, "reason": reason, "calc_type": "uncertainty"}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"status": "ERROR", "reason": str(e)}, ensure_ascii=False)


def verify_error_logic(error_val, limit_val):
    """【工具2】误差合规性校验: |Error| <= |Limit| -> PASS"""
    try:
        if not limit_val or limit_val.strip() in ["-", "/", "N/A", ""]:
            return json.dumps({"status": "PASS", "reason": "无允许误差限值(Skip)", "calc_type": "error"},
                              ensure_ascii=False)

        # 提取数值（取绝对值比较）
        e_val, _ = parse_value_with_unit(error_val)
        l_val, _ = parse_value_with_unit(limit_val)

        if abs(e_val) <= (abs(l_val) + 1e-9):
            status = "PASS"
            reason = f"|{e_val:.6g}| <= |{l_val:.6g}|"
        else:
            status = "FAIL"
            reason = f"|{e_val:.6g}| > |{l_val:.6g}|"

        return json.dumps({"status": status, "reason": reason, "calc_type": "error"}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"status": "ERROR", "reason": str(e)}, ensure_ascii=False)

#单位转换工具
def unit_convert_tool(val_str: str, impedance: float = 50.0):
    """
    【工具3】单位换算工具
    将 dBm, Vrms 等转换为 Vpp (峰峰值)，用于跟 KB 的量程 (通常是 Vpp) 进行比对。
    默认阻抗 50欧姆。
    """
    try:
        if not val_str: return "0"
        s = str(val_str).strip().lower()

        # 1. 提取数值
        m = re.search(r"([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)", s)
        if not m: return "Error: No number found"
        val = float(m.group(1))

        # 2. 识别单位并转换
        # 目标是统一转换为 Vpp
        result_vpp = 0.0

        if "dbm" in s:
            # dBm -> Vpp (需阻抗)
            # P(mW) = 10^(dBm/10)
            # P(W) = P(mW) / 1000
            # Vrms = sqrt(P(W) * R)
            # Vpp = Vrms * 2 * sqrt(2)
            p_mw = 10 ** (val / 10.0)
            p_w = p_mw / 1000.0
            v_rms = math.sqrt(p_w * impedance)
            result_vpp = v_rms * 2 * math.sqrt(2)

        elif "vrms" in s or ("v" in s and "rms" in s):
            # Vrms -> Vpp
            result_vpp = val * 2 * math.sqrt(2)

        elif "mv" in s:
            # mV -> V (简单单位换算，视为 Vpp)
            result_vpp = val / 1000.0

        elif "v" in s:
            # 假设已经是 V (Vpp)
            result_vpp = val

        else:
            return json.dumps({"error": f"Unknown unit in {s}"}, ensure_ascii=False)

        # 格式化输出
        return json.dumps({
            "original": val_str,
            "converted_vpp": f"{result_vpp:.4g}",
            "unit": "Vpp",
            "note": f"Based on {impedance} ohm impedance"
        }, ensure_ascii=False)

    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# 定义工具描述 Schema
TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "verify_uncertainty_logic",
            "description": "核验不确定度。规则：Cert_U >= KB_U 为合格。",
            "parameters": {
                "type": "object",
                "properties": {
                    "measure_val": {"type": "string", "description": "测量点数值"},
                    "cert_u": {"type": "string", "description": "证书不确定度"},
                    "kb_u": {"type": "string", "description": "KB要求不确定度"}
                },
                "required": ["measure_val", "cert_u", "kb_u"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "verify_error_logic",
            "description": "核验误差。规则：|实测误差| <= |允许误差| 为合格。若无允许误差，不要调用此工具。",
            "parameters": {
                "type": "object",
                "properties": {
                    "error_val": {"type": "string", "description": "证书实测误差"},
                    "limit_val": {"type": "string", "description": "证书允许误差/限值"}
                },
                "required": ["error_val", "limit_val"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "unit_convert_tool",
            "description": "数值单位换算工具。当证书单位(如 dBm, Vrms)与KB单位(如 Vpp, V)不一致时，必须调用此工具进行转换，严禁口算。",
            "parameters": {
                "type": "object",
                "properties": {
                    "val_str": {"type": "string", "description": "原始数值字符串，例如 '19.0 dBm' 或 '3.51 dBm'"},
                    "impedance": {"type": "number", "description": "阻抗值(欧姆)，默认50", "default": 50.0}
                },
                "required": ["val_str"]
            }
        }
    }

]


# ===================== 2. 基础辅助函数 (保持不变) =====================

def chunk_list(data: List[Any], size: int):
    for i in range(0, len(data), size): yield data[i:i + size]


def pick_first(text: str, *patterns: str) -> Optional[str]:
    if not text: return None
    for p in patterns:
        m = re.search(p, text, flags=re.IGNORECASE)
        if m: return m.group(1).strip()
    return None


def detect_uncertainty_info(text: str) -> Dict[str, Any]:
    info = {"type": None, "value": None, "raw": None}
    if not text: return info
    m_abs = re.search(r"\bU\s*=\s*([-\d\.]+)", text, flags=re.IGNORECASE)
    m_rel = re.search(r"\bU\s*rel\s*=\s*([\d\.]+)\s*%", text, flags=re.IGNORECASE)
    if m_abs:
        info["type"] = "U";
        info["value"] = float(m_abs.group(1));
        info["raw"] = m_abs.group(0)
    elif m_rel:
        info["type"] = "Urel";
        info["value"] = float(m_rel.group(1)) / 100.0;
        info["raw"] = m_rel.group(0)
    return info


def split_values_maybe_list(x) -> List[str]:
    if x is None: return []
    if isinstance(x, list): return [str(v) for v in x]
    return [p.strip() for p in re.split(r"[，,；;]\s*", str(x)) if p.strip()]


def parse_kb_entry(doc: str, meta: Dict[str, Any]) -> Dict[str, Any]:
    # 1. 提取仪器名称 (之前缺失的定义)
    instrument_name = meta.get("仪器名称") or pick_first(doc, r"仪器名称[：:]\s*(.+?)[。；]") or "N/A"

    # 2. 提取校准依据
    standard_name = meta.get("校准依据") or pick_first(doc, r"校准依据[：:]\s*(.+?)[。；\n]") or "N/A"

    # 3. 提取规程编号 (优化后的正则逻辑)
    # 匹配 JJG/JJF 开头，允许中间有空格，必须有数字
    file_code = pick_first(doc, r"(JJ[GF]\s*\d+(?:-\d{4})?)")

    # 如果正则没抓到，尝试从 standard_name 里再抓一次
    if not file_code and standard_name != "N/A":
        m = re.search(r"(JJ[GF]\s*\d+(?:-\d{4})?)", standard_name)
        if m:
            file_code = m.group(1)

    # 兜底逻辑：实在抓不到编号，就用规程名称代替，防止 N/A
    if not file_code:
        file_code = standard_name if standard_name != "N/A" else "未知规程"

    # 4. 提取被测量
    measured = pick_first(doc, r"被测量[：:]\s*(.+?)[。；]") or "N/A"

    # 5. 提取测量范围
    measure_range_text = pick_first(doc, r"测量范围[：:]\s*(.+?)[。；]") or "-"

    # 6. 提取不确定度
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
    table_lines = ["| 序号 | 仪器 | 规范(代号) | 被测量 | 测量范围摘录 | 不确定度 |",
                   "| --- | --- | --- | --- | --- | --- |"]
    for i, e in enumerate(entries[:top_k], 1):
        utype = e["uncertainty"].get("type", "N/A")
        uval = e["uncertainty"].get("value", "N/A")
        uinfo = f"{utype}={uval}" if uval != "N/A" else "N/A"
        table_lines.append(
            f"| {i} | {e['instrument_name']} | {e['standard_name']}/{e['file_code']} | {e['measured']} | {e['measure_range_text'][:60]} | {uinfo} |")
    return "\n".join(table_lines)


def query_kb(client: chromadb.Client, embedder: SentenceTransformer, collection_name: str, instrument_name: str,
             criterion: str, topk: int = 30) -> List[Dict[str, Any]]:
    print(f"\n📘 检索 KB: {instrument_name} {criterion}")
    m = re.search(r"(JJG\s*\d{3,}-\d{3,}|JJF\s*\d{3,}-\d{3,})", criterion)
    basis_code = m.group(1).replace(" ", "") if m else None
    query_text = f"{instrument_name} {basis_code}" if basis_code else f"{instrument_name} {criterion}".strip()
    try:
        coll = client.get_collection(collection_name)
    except Exception as e:
        print(f"❌ 加载集合失败：{e}");
        return []

    q_emb = embedder.encode([query_text]).tolist()
    res = coll.query(query_embeddings=q_emb, n_results=topk)
    docs = res.get("documents", [[]])[0] if res and res.get("documents") else []
    metas = res.get("metadatas", [[]])[0] if res and res.get("metadatas") else [{} for _ in docs]

    entries = []
    for d, m in zip(docs, metas): entries.append(parse_kb_entry(d, m))
    print(f"✅ 检索到 {len(entries)} 条")
    return entries


def collect_certificate_params(cert_root: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    从 JSON 结构中智能解析测量参数，保留参数名称与具体数据的对应关系。
    """
    out = []

    # 1. 获取依据参数字典
    # 假设 JSON 结构为: properties -> 证书列表 -> items -> properties -> 依据参数
    # cert_root 应该是 "依据参数" 的上一级或者本身包含 "依据参数" 键
    # 如果 cert_root 就是 properties 层级：
    basis_params = cert_root.get("依据参数", {})

    # 如果依据参数是列表（有些 schema 可能是列表），尝试兼容
    if isinstance(basis_params, list):
        # 这种情况比较少见，通常是 Dict
        print("⚠️ 警告：'依据参数' 是列表结构，尝试扁平化处理")
        # 暂不处理列表结构的依据参数，视具体 JSON 而定
        return []

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

        # 如果 row_count 为 0，说明可能都是单值（非列表），视为 1 行
        if row_count == 0:
            row_count = 1

        # 4. 将列式数据转换为行式数据
        for i in range(row_count):
            # 初始化这一行的记录，核心是将 JSON Key 作为参数名
            rec = {"param_name": project_name}

            # 遍历该项目下的所有字段（标称值、标准值、结论...）
            has_valid_data = False
            for field_key, field_val in fields_dict.items():
                val = None
                if isinstance(field_val, list):
                    # 如果是列表，取第 i 个；如果越界，填空字符串
                    if i < len(field_val):
                        val = str(field_val[i])
                        if val and val.lower() != "none" and val.strip() != "":
                            has_valid_data = True
                    else:
                        val = ""
                else:
                    # 如果是单值，每行都复制一份
                    val = str(field_val)
                    if val and val.lower() != "none" and val.strip() != "":
                        has_valid_data = True

                # 存入字典，Key 使用原始字段名（如 "标称值", "U"）
                rec[field_key] = val

            # 只有当这一行包含有效数据时才添加，避免添加全是空值的行
            if has_valid_data:
                out.append(rec)

    return out


# ===================== 3. 核心 Agent 流程 =====================

def run_agentic_batch(client: OpenAI, batch_params: List[Dict], kb_items: List[Dict],
                      instrument: str, criterion: str) -> str:
    # 1. 构造 KB 摘要
    kb_summary = []
    for k in kb_items:
        # --- 修改处：构造更健壮的 ID ---
        code = k.get('file_code', 'N/A')
        name = k.get('standard_name', '')

        # 如果 code 是 N/A，尝试用 name 里的 JJG/JJF
        if code == "N/A" or code == "未知规程":
            m = re.search(r"(JJ[GF]\s*\d+)", name)
            if m: code = m.group(1)

        # 构造显示用的 ID，例如 "JJG 237 (秒表检定规程)"
        display_id = f"{code}"
        if name and name != "N/A" and name != code:
            display_id += f" ({name})"
        # -----------------------------

        kb_summary.append({
            "id": display_id,  # 把这个复合 ID 传给 LLM
            "measured": k['measured'],
            "range": k['measure_range_text'],
            "uncertainty": k['uncertainty']
        })

    # System Prompt: 融合了逻辑规则和工具调用指令
    system_prompt = (
        "你是一名资深计量校准核验专家。你的任务是对传入的【测量参数批次】进行合规性核验。\n\n"

        "### 核心原则：KB选择策略 (KB Selection Strategy) - 最高优先级\n"
        "1. **依据一致性原则 (Basis Consistency)**：\n"
        "   - 首先检查证书的【依据】(Criterion) 中的规程代号（如 JJG 237）。\n"
        "   - 在选择 KB 条目时，**必须优先锁定**与证书依据代号一致的条目，若没有一致的KB条目，则终止核验流程。\n"
        "   - **案例警告**：如果证书依据是 'JJG 237'，测量点是 '日差'。即使 KB 中有 'JJG 488 瞬时日差测量仪' 且名字更像，你也**严禁**选择 JJG 488！你必须选择 'JJG 237' 下的 '时间' 或相关参数。\n"
        "   - **理由**：不同的规程对应不同的仪器等级，跨规程核验会导致判定标准错误。\n"
        "2. **范围覆盖优先**：\n"
        "   - 在满足上述“依据一致性”的前提下，选择范围能覆盖测量点的 KB。\n\n"
        " 3. **物理本质匹配 (Semantic Mapping)**\n"
        "   - 如果在正确规程中找不到名字完全一样的参数，请根据**物理计量常识**进行匹配。\n"
        "   - **思考逻辑**：\n"
        "     * “这个参数测量的物理量到底是什么？”\n"
        "     * “KB 里哪个参数覆盖了这个物理量的含义？”\n"
        "   - **典型场景举例（仅供参考，请举一反三）**：\n"
        "     * 证书写 **'日差' (Daily Rate)** -> 物理上是 **'时间' (Time)** 的累积误差 -> 匹配 KB 中的 **'时间'**。\n"
        "     * 证书写 **'幅度平坦度'** -> 物理上是 **'幅度'** 随频率的变化 -> 匹配 KB 中的 **'幅度'**。\n"
        "     * 证书写 **'频率准确度'** -> 物理上就是测 **'频率'** -> 匹配 KB 中的 **'频率'**。\n\n"

        "### 核验步骤 (数值比较时需调用工具)\n"
        "### 第一步：参数匹配与范围核验 (Range Check)\n"
        "1. **单位换算 (Critical)**：\n"
        "   - 若测量点单位（如 dBm, Vrms）与 KB 单位（如 V, Vpp）不一致，**必须先调用工具** `unit_convert_tool` 将其转换为 KB 单位。\n"
        "   - **严禁口算**！必须使用工具转换后的数值进行范围判断。\n"
        "2. **常规情况**：\n"
        "   - 确认测量点是否在 KB 范围内。\n"
        "   - **原则**：采用【闭区间】。若 测量值 = 范围上限 或 测量值 = 范围下限，均视为 Pass。\n"
        "3. **特殊映射（必须优先执行）**：\n"
        "   - **幅度平坦度**：若 KB 无此项，将其映射为“幅度”。\n"
        "   - **紫外能量 (Energy vs Irradiance)**：\n"
        "     - 场景：证书为能量 (J/cm², mJ/cm²)，KB 为辐照度 (W/cm², mW/cm²)。\n"
        "     - **操作**：**禁止**比对数值大小（因物理量纲不同）。\n"
        "     - **判定**：只要波段匹配（如同为 UV-365），直接判定 **Pass (Physics Mapped)**，并在说明中备注“基于辐照度能力覆盖能量参数”。\n\n"

        "### 第二步：误差判定 (Error Check)\n"
        "   - 若证书有明确的“允许误差”或“限值”：**必须调用工具** `verify_error_logic` 进行比对。\n"
        "   - **注意**：“修正系数”(Correction Factor) 不是误差，若无明确误差值，跳过此步（视为 Pass）。\n\n"

        "### 第三步：不确定度判定 (Uncertainty Check)\n"
        "   - **前置判断**：首先检查证书是否提供了有效的不确定度数值。\n"
        "   - **情况1：证书未提供不确定度** (如数值为 0, None, N/A, /, 空白)：\n"
        "     - **不要调用工具**，直接跳过此判定。\n"
        "     - 判定结果不受此影响（不要因此判 Failed），但必须在【说明】栏备注“证书未提供不确定度，跳过比对”。\n"
        "   - **情况2：证书和 KB 均有不确定度**：\n"
        "     - **必须调用工具** `verify_uncertainty_logic`。\n"
        "     - **禁止口算**！必须依赖工具返回的 PASS/FAIL 结果。\n"
        "     - 判定规则：Cert_U >= KB_U 为 Pass。\n\n"

        "### 输出格式要求 (Strict Output Format)\n"
        "请按 `param_name` 将结果分组。对于每一个不同的参数名称，输出一个独立的表格：\n\n"

        "### 输出格式\n"
        "输出 Markdown 表格，列包含：序号, 测量点, KB编号, 证书匹配项, 范围, 证书误差, 允许误差, 证书U, KB_U, 判定, 说明。\n"
        "在【说明】栏中，必须引用工具返回的计算依据。"
    )

    user_content = f"""
    ### 仪器信息
    仪器: {instrument}
    依据: {criterion}

    ### 知识库候选
    {json.dumps(kb_summary, ensure_ascii=False)}

    ### 待核验参数
    {json.dumps(batch_params, ensure_ascii=False)}
    """

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]

    # ================= 核心修改：支持多轮工具调用的循环 =================
    MAX_TURNS = 30  # 防止死循环，最多允许交互 10 轮

    for turn in range(MAX_TURNS):
        try:
            response = client.chat.completions.create(
                model=Config.MODEL,
                messages=messages,
                tools=TOOLS_SCHEMA,
                tool_choice="auto",
                temperature=Config.TEMPERATURE
            )
            msg = response.choices[0].message
        except Exception as e:
            return f"> 🚨 API 请求失败: {e}"

        tool_calls = msg.tool_calls

        # 情况 A: 模型想要调用工具
        if tool_calls:
            messages.append(msg)  # 必须将模型的“思考/调用请求”加入历史

            enforcement_notes = []

            # 处理这一轮所有的工具调用
            for tool_call in tool_calls:
                fname = tool_call.function.name
                args = json.loads(tool_call.function.arguments)
                tool_res = ""

                # 执行 Python 函数
                if fname == "verify_uncertainty_logic":
                    tool_res = verify_uncertainty_logic(args.get("measure_val"), args.get("cert_u"), args.get("kb_u"))
                    # 记录强制提示信息
                    try:
                        r = json.loads(tool_res)
                        enforcement_notes.append(
                            f"工具判定: {args.get('measure_val')} -> {r.get('status')} ({r.get('reason')})")
                    except:
                        pass

                elif fname == "verify_error_logic":
                    tool_res = verify_error_logic(args.get("error_val"), args.get("limit_val"))
                    try:
                        r = json.loads(tool_res)
                        enforcement_notes.append(
                            f"工具判定: 误差 {args.get('error_val')} -> {r.get('status')} ({r.get('reason')})")
                    except:
                        pass

                else:
                    tool_res = json.dumps({"error": "Unknown tool"})

                # 回填结果
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": fname,
                    "content": tool_res
                })

            # (可选) 可以在每轮工具执行后，再次提醒模型遵循工具结果
            # 但为了避免 Prompt 过长，DeepSeek 通常能自己理解 Tool Output
            # 这里我们仅在检测到工具结果时，打印日志即可
            # print(f"Batch Loop {turn}: Executed {len(tool_calls)} tools.")

            # --- 循环继续，进入下一轮 check，模型会看到工具结果并决定是继续调用还是输出文本 ---
            continue

        # 情况 B: 模型没有调用工具，直接返回了文本（最终报告）
        else:
            return msg.content

    return "> ⚠️ 超过最大交互轮数，未能生成完整报告。"

# ===================== 修改后的主流程 (支持并发) =====================

def run_llm_mode(json_file: str, cfg: Config) -> str:
    # 1. 加载数据
    data = json.load(open(json_file, "r", encoding="utf-8"))
    try:
        root = data["properties"]["证书列表"]["items"]["properties"]
    except KeyError:
        return "❌ JSON 结构错误"

    instrument_name = root.get("INSTRUMENT_NAME") or root.get("仪器名称") or "N/A"
    criteria_list = root.get("校准依据", []) or ["N/A"]
    all_cert_params = collect_certificate_params(root)

    print(f"📂 证书: {json_file}")
    print(f"📊 参数量: {len(all_cert_params)}")

    # 2. 初始化资源
    embedder = SentenceTransformer(cfg.EMBED_MODEL_PATH)
    chroma_client = chromadb.PersistentClient(path=cfg.DB_DIR)
    # 注意：OpenAI 客户端是线程安全的，可以在多线程中共享，或者在线程内新建
    client = OpenAI(api_key=cfg.API_KEY, base_url=cfg.API_BASE)

    report_lines = [
        "# CNAS 智能核验报告 (Agentic Mode - Parallel)",
        f"- 证书编号: {root.get('证书编号', 'N/A')}",
        f"- 仪器: {instrument_name}",
        f"- 时间: {os.popen('date /t').read().strip()}",
        ""
    ]

    # 3. 按依据循环 (通常依据较少，这里保持串行，内部 Batch 并行)
    for criterion in criteria_list:
        report_lines.append(f"## 依据: {criterion}")

        # 检索 KB (只需要做一次)
        kb_items = query_kb(chroma_client, embedder, cfg.COLLECTION, instrument_name, criterion)

        if kb_items:
            report_lines.append(build_table(kb_items, top_k=70))
        else:
            report_lines.append("> ⚠️ 未找到 KB 条目")

        report_lines.append("\n### 核验详情\n")

        # ================= 并发核心逻辑开始 =================

        # 准备任务列表
        tasks = []
        batches = list(chunk_list(all_cert_params, cfg.BATCH_SIZE))
        total_batches = len(batches)

        print(f"🚀 启动并发处理: 共 {total_batches} 个批次，线程数: {cfg.max_workers}")

        # 使用线程池
        with ThreadPoolExecutor(max_workers=cfg.max_workers) as executor:
            # 提交所有任务
            # 我们用字典记录 future 对应的 batch_index，以便最后按顺序重组报告
            future_to_index = {}

            for idx, batch in enumerate(batches):
                # 提交任务给 Agent
                future = executor.submit(
                    run_agentic_batch,
                    client,
                    batch,
                    kb_items,
                    instrument_name,
                    criterion
                )
                future_to_index[future] = idx + 1

            # 用于存储结果的字典，确保乱序执行后能顺序输出
            results_map = {}

            # 处理完成的任务
            for future in as_completed(future_to_index):
                idx = future_to_index[future]
                try:
                    content = future.result()
                    results_map[idx] = content
                    print(f"   ✅ Batch {idx}/{total_batches} 完成")
                except Exception as e:
                    error_msg = f"> 🚨 Batch {idx} 失败: {e}"
                    results_map[idx] = error_msg
                    print(error_msg)

        # ================= 并发结束，按顺序组装报告 =================

        for i in range(1, total_batches + 1):
            report_lines.append(f"#### 📌 Batch {i}")
            # 从结果字典里取，保证顺序不乱
            report_lines.append(results_map.get(i, "> 执行异常，无结果"))
            report_lines.append("\n---\n")

    return "\n".join(report_lines)

def main():
    # 请修改此处的文件名
    BASE_DIR = Path(r"D:\workspace\ai大模型开发课\文档核验\work_pdf\local_json")
    JSON_FILE = "1GA25005017-0001.json"
    JSON_PATH = str(BASE_DIR / JSON_FILE)

    cfg = Config()
    report = run_llm_mode(JSON_PATH, cfg)

    out_path = Path(cfg.OUTPUT_DIR) / f"Agent_Report_{Path(JSON_FILE).stem}.md"
    os.makedirs(cfg.OUTPUT_DIR, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    print(f"\n✅ 完成! 报告已保存: {out_path}")


if __name__ == "__main__":
    main()
