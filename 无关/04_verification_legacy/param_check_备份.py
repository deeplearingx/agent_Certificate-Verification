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
    TOPK = 50
    BATCH_SIZE = 5
    max_workers = 5

# ===================== 1. 定义 Python 计算工具集 =====================

# 支持 6.6×10⁻⁹ 这类科学计数法的解析
SUPERSCRIPT_MAP = {
    '⁰': '0', '¹': '1', '²': '2', '³': '3', '⁴': '4',
    '⁵': '5', '⁶': '6', '⁷': '7', '⁸': '8', '⁹': '9',
    '⁻': '-', '⁺': '+',
}
# ===================== 新增：单位换算表 =====================
UNIT_MULTIPLIERS = {
    'T': 1e12, 'G': 1e9, 'M': 1e6, 'k': 1e3, 'K': 1e3, # 频率/电阻等
    'm': 1e-3, 'u': 1e-6, 'μ': 1e-6, 'n': 1e-9, 'p': 1e-12 # 电压/时间等
}

##识别KB的解析器
def norm_code(s: str) -> str:
    s = (s or "").strip()
    m = re.search(r"\b(JJ[GF]|GJB)\s*(\d+)", s, re.IGNORECASE)
    if m:
        return f"{m.group(1).upper()}{m.group(2)}"  # 无空格
    return re.sub(r"\s+", "", s).upper()



def extract_basis_code(criterion: str) -> Optional[str]:
    """
    统一忽略年份后缀：
    - JJG 237-2010 -> JJG 237
    - JJF 1234-2020 -> JJF 1234
    - GJB 7691-2012 -> GJB 7691
    """
    if not criterion:
        return None

    s = str(criterion)
    m = re.search(r"\b(JJ[GF]|GJB)\s*(\d+)(?:\s*-\s*\d{4})?\b", s, re.IGNORECASE)
    if not m:
        return None
    return f"{m.group(1).upper()} {m.group(2)}"




def parse_unicode_sci_number(s: str) -> Optional[float]:
    """
    解析类似：
      - 6.6×10⁻⁹
      - 3.2x10⁻⁶
      - 1.0*10⁻³
    返回 float，解析失败返回 None
    """
    if not s:
        return None

    # 允许 '×' / 'x' / 'X' / '*' 作为乘号
    m = re.search(r'([+-]?\d*\.?\d+)\s*[×xX*]\s*10\s*([\-+0-9⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻]+)', s)
    if not m:
        return None

    mantissa = float(m.group(1))
    exp_raw = m.group(2)

    # 上标指数 → 普通字符串
    exp_str = ''.join(SUPERSCRIPT_MAP.get(ch, ch) for ch in exp_raw)
    try:
        exp = int(exp_str)
    except ValueError:
        return None

    return mantissa * (10 ** exp)


def parse_value_with_unit(val_str, base_val=None, keep_sign: bool = False):
    """
    数值解析与单位折算工具 (增强版)
    - 支持 Unicode 科学计数法：6.6×10⁻⁹
    - 支持单位前缀：k/M/G/m/u/μ/n/p
    - 支持相对不确定度：
        * 0.5%   -> base * 0.005  (当 base_val 存在)
        * Urel=8e-9 -> base * 8e-9 (当 base_val 存在)
      并且当 base_val 不存在时：
        * 0.5% 返回 0.005（fraction），避免被当作 0.5
    - keep_sign=True 时保留正负号（用于误差单边阈值判断）
    """

    # 1) 缺失/无效
    if val_str is None:
        return None, "missing"
    s = str(val_str).strip()
    # ✅ 修正 OCR 常见大小写错误，避免 MV/UV 被当成倍率前缀 M/U
    s = re.sub(r"\bMV\b", "mV", s)
    s = re.sub(r"\bUV\b", "uV", s)
    s = re.sub(r"\bKV\b", "kV", s)

        # ✅ 修正频率单位大小写：mhz/ghz/khz -> MHz/GHz/kHz
    s = re.sub(r"\bmhz\b", "MHz", s, flags=re.IGNORECASE)
    s = re.sub(r"\bghz\b", "GHz", s, flags=re.IGNORECASE)
    s = re.sub(r"\bkhz\b", "kHz", s, flags=re.IGNORECASE)
    s = re.sub(r"\bhz\b",  "Hz",  s, flags=re.IGNORECASE)



    if s == "" or s in ["-", "/", "N/A", "n/a", "None", "none"]:
        return None, "missing"

    s_lower = s.lower()
    has_percent = "%" in s_lower
    is_rel_keyword = ("urel" in s_lower) or ("u rel" in s_lower) or ("rel" in s_lower)

    # 2) 提取数值（保留符号）
    num = None
    sci_val = parse_unicode_sci_number(s)
    if sci_val is not None:
        num = sci_val
    else:
        m = re.search(r"([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)", s)
        if m:
            num = float(m.group(1))

    if num is None:
        return None, "missing"

    # 3) 单位前缀倍率（避免 % 进入倍率逻辑）
    multiplier = 1.0
    if not has_percent:
        # 去掉数字部分后剩余单位串
        unit_part = re.sub(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", "", s).strip()
        if unit_part:
            # 允许形如 "MHz" / " mV" / "μs" / "kHz"
            # 找第一个字母前缀
            first_char = unit_part[0]
            if first_char in UNIT_MULTIPLIERS:
                multiplier = UNIT_MULTIPLIERS[first_char]

    signed_val = num * multiplier
    abs_or_signed = signed_val if keep_sign else abs(signed_val)

    # 4) 相对不确定度换算（有 base_val 时直接转绝对值）
    if base_val is not None:
        if has_percent:
            # 0.5% -> base * 0.005
            v = base_val * (num / 100.0)
            return (v if keep_sign else abs(v)), "rel_percent_converted"
        if is_rel_keyword:
            # Urel=8e-9 -> base * 8e-9
            v = base_val * num
            return (v if keep_sign else abs(v)), "rel_coef_converted"

    # 5) 没有 base_val，但遇到百分数：返回 fraction，避免 0.5% 被当 0.5
    if base_val is None and has_percent:
        v = num / 100.0
        return (v if keep_sign else abs(v)), "percent_fraction"

    return abs_or_signed, "abs"



def to_plain_decimal(x: Optional[float], max_digits: int = 12) -> str:
    """
    将浮点数转为“非科学计数法”的字符串，如：
    6.6e-09 -> '0.0000000066'
    0.000066 -> '0.000066'
    """
    if x is None:
        return ""
    # 先用 g 避免太长
    s = f"{x:.{max_digits}g}"
    if "e" in s or "E" in s:
        # 再转成定点小数，然后去掉多余的 0
        s = f"{x:.{max_digits}f}".rstrip("0").rstrip(".")
    return s





def parse_single_sided_limit(limit_str: str):
    """
    解析单边限值，例如:
      "<-75", "<= -75.0 dBc/Hz", ">0.1", ">= +3"
    返回: (op, threshold)  其中 op in {"<", "<=", ">", ">="}
    解析失败返回 None
    """
    if not limit_str:
        return None
    s = str(limit_str).strip().lower()

    m = re.search(r"(<=|>=|<|>)\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)", s)
    if not m:
        return None

    op = m.group(1)
    thr = float(m.group(2))
    return op, thr


def parse_range_limit(limit_str: str):
    """
    解析区间限值，例如:
      "-0.2~+0.1", "(-0.2, +0.1)", "-0.2 ～ 0.1"
    返回: (lower, upper) 或 None
    """
    if not limit_str:
        return None
    s = str(limit_str).strip().lower()

    # 尽量找两个数字
    nums = re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", s)
    if len(nums) < 2:
        return None
    a, b = float(nums[0]), float(nums[1])
    lower, upper = min(a, b), max(a, b)
    return lower, upper


def parse_symmetric_limit(limit_str: str):
    """
    解析对称容差，例如:
      "±0.1", "+/-0.1", "0.1"
    返回: limit(>=0) 或 None
    """
    if not limit_str:
        return None
    s = str(limit_str).strip().lower()

    m = re.search(r"([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)", s)
    if not m:
        return None
    return abs(float(m.group(1)))


def verify_error_logic(error_val, limit_val):
    """
    误差/限值合规性校验：支持
      1) 单边阈值：<, <=, >, >=（含≤≥）
      2) 区间：a~b / a～b / (a,b) / a,b
      3) 对称容差：±L 或 L
    并且：误差值与限值都支持单位前缀(k/M/m/u/μ/n/p)换算，避免出现
      abs(-200) <= 10  这种“误差单位换算了但限值没换算”的错判。
    """

    def _is_empty(v) -> bool:
        if v is None:
            return True
        s = str(v).strip()
        return s in ["", "-", "/", "N/A", "NA", "None", "none"]

    def _normalize_symbols(s: str) -> str:
        # 统一中文/全角符号
        s = (s or "").strip()
        s = s.replace("≤", "<=").replace("≥", ">=")
        s = s.replace("＋", "+").replace("﹢", "+")
        s = s.replace("—", "-").replace("−", "-")
        s = s.replace("～", "~")
        return s

    def _parse_number_with_unit(text: str, keep_sign: bool = False) -> Optional[float]:
        """
        把 '10.0 kΩ' / '±10kΩ' / '<= -75 dBc/Hz' 这类字符串解析成数值（含前缀倍率）
        注意：这里的单位本身(Ω/V/Hz)不做维度换算，只处理前缀倍率(k/M/m/u/μ/n/p)。
        """
        if _is_empty(text):
            return None
        s = _normalize_symbols(str(text))
        # 去掉常见装饰
        s = s.replace("±", "")
        # 对单边阈值，去掉比较符号，保留数字+单位
        s = re.sub(r"^\s*(<=|>=|<|>)\s*", "", s)

        # 直接用你现成的 parse_value_with_unit（它会处理 k/M/m/u/μ/n/p）
        v, _t = parse_value_with_unit(s, base_val=None, keep_sign=keep_sign)
        return v

    try:
        # 0) 无限值：跳过
        if _is_empty(limit_val):
            return json.dumps(
                {"status": "PASS", "reason": "无允许误差限值(Skip)", "calc_type": "error"},
                ensure_ascii=False
            )

        # 1) 误差值：必须保留符号
        e_val = _parse_number_with_unit(error_val, keep_sign=True)
        if e_val is None:
            return json.dumps(
                {"status": "ERROR", "reason": f"误差缺失：error_val='{error_val}'", "calc_type": "error"},
                ensure_ascii=False
            )

        s = _normalize_symbols(str(limit_val)).strip().lower()

        # ========== 1) 单边阈值：<, <=, >, >= ==========
        # 允许类似 "<= -75 dBc/Hz" / ">=+3" / "< 10 kΩ"
        m = re.search(r"(<=|>=|<|>)\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)", s)
        if m:
            op = m.group(1)
            # 直接把整串喂进去（含单位），确保 k/M 等被解析
            thr = _parse_number_with_unit(s, keep_sign=False)
            if thr is None:
                return json.dumps(
                    {"status": "ERROR", "reason": f"单边限值解析失败：limit_val='{limit_val}'", "calc_type": "error"},
                    ensure_ascii=False
                )

            if op == "<":
                ok = e_val < (thr + 1e-9)
            elif op == "<=":
                ok = e_val <= (thr + 1e-9)
            elif op == ">":
                ok = e_val > (thr - 1e-9)
            else:  # >=
                ok = e_val >= (thr - 1e-9)

            return json.dumps(
                {
                    "status": "PASS" if ok else "FAIL",
                    "reason": f"{to_plain_decimal(e_val)} {op} {to_plain_decimal(thr)}",
                    "calc_type": "error"
                },
                ensure_ascii=False
            )

        # ========== 2) 区间：a~b / (a,b) / a,b ==========
        # 支持：
        #   "800 kΩ～1.2 MΩ"
        #   "(-0.2, +0.1)"
        #   "-0.2~0.1"
        # 注意：端点可能带不同前缀（kΩ vs MΩ），因此不能只提数字，必须逐端点解析。
        if re.search(r"[~(),，,]", s):
            # 尽量切成两段端点字符串
            # 先去掉括号
            s2 = s.replace("(", "").replace(")", "")
            parts = re.split(r"[~，,]", s2)
            parts = [p.strip() for p in parts if p.strip()]
            if len(parts) >= 2:
                a = _parse_number_with_unit(parts[0], keep_sign=True)
                b = _parse_number_with_unit(parts[1], keep_sign=True)
                if a is not None and b is not None:
                    lower, upper = (a, b) if a <= b else (b, a)
                    ok = (e_val >= (lower - 1e-9)) and (e_val <= (upper + 1e-9))
                    return json.dumps(
                        {
                            "status": "PASS" if ok else "FAIL",
                            "reason": f"{to_plain_decimal(lower)} <= {to_plain_decimal(e_val)} <= {to_plain_decimal(upper)}",
                            "calc_type": "error"
                        },
                        ensure_ascii=False
                    )
            # 如果区间解析失败，继续走对称容差兜底

        # ========== 3) 对称容差：±L 或 L ==========
        # 这里也必须支持单位前缀：如 "±10.0 kΩ"
        lim = _parse_number_with_unit(s, keep_sign=False)
        if lim is None:
            return json.dumps(
                {"status": "ERROR", "reason": f"允许误差解析失败：limit_val='{limit_val}'", "calc_type": "error"},
                ensure_ascii=False
            )

        ok = abs(e_val) <= (lim + 1e-9)
        return json.dumps(
            {
                "status": "PASS" if ok else "FAIL",
                "reason": f"abs({to_plain_decimal(e_val)}) <= {to_plain_decimal(lim)}",
                "calc_type": "error"
            },
            ensure_ascii=False
        )

    except Exception as e:
        return json.dumps({"status": "ERROR", "reason": str(e), "calc_type": "error"}, ensure_ascii=False)



UNIT_CONVERT_DISCLAIMER = "所有单位换算结果基于正弦波假设，模糊单位默认按 Vpp 处理，仅用于工程量程评估。"
#单位转换工具
def unit_convert_tool(val_str: str, impedance: float = 50.0):
    """
    KB 专用 · 宽容型工程换算器
    - 统一输出 Vpp
    - 全部假设为正弦波
    - V / mV 默认视为 Vpp
    - dBm / dBmV 默认 50Ω
    """

    try:
        if not val_str:
            return json.dumps({"error": "empty val_str"}, ensure_ascii=False)

        s = val_str.strip().lower()

        # 提取数值
        m = re.search(r"([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)", s)
        if not m:
            return json.dumps({"error": "No numeric value found"}, ensure_ascii=False)

        val = float(m.group(1))
        vpp = None
        note = []

        # ---------- 功率单位 ----------
        if "dbm" in s and "dbmv" not in s:
            p_w = 10 ** (val / 10.0) / 1000.0
            vrms = math.sqrt(p_w * impedance)
            vpp = vrms * 2 * math.sqrt(2)
            note.append("dBm assumed into resistive load")

        elif "dbmv" in s:
            vrms = (10 ** (val / 20.0)) * 1e-3
            vpp = vrms * 2 * math.sqrt(2)
            note.append("dBmV referenced to 1 mVrms")

        # ---------- RMS ----------
        elif "vrms" in s or ("v" in s and "rms" in s):
            vpp = val * 2 * math.sqrt(2)
            note.append("Vrms assumed sine wave")

        # ---------- Peak ----------
        elif "vpk" in s or "vp" in s:
            vpp = val * 2
            note.append("Peak voltage assumed")

        # ---------- 电压（宽容默认） ----------
        elif "mv" in s:
            vpp = val / 1000.0
            note.append("mV treated as Vpp (engineering default)")

        elif "v" in s:
            vpp = val
            note.append("V treated as Vpp (engineering default)")

        # ---------- 无单位 ----------
        else:
            vpp = val
            note.append("Unitless value treated as Vpp")

        return json.dumps({
            "original": val_str,
            "converted_vpp": f"{vpp:.4g}",
            "unit": "Vpp",
            "assumptions": note,
            "impedance": f"{impedance} Ω"
        }, ensure_ascii=False)

    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)
    
def _pick_ux_from_measure_text(measure_val: str) -> Tuple[Optional[float], str, Optional[str]]:
    """
    返回 (ux_value, ux_reason, ux_unit_hint)
    ux_unit_hint 示例：'MHz' / 'mV' / 'Hz' / 'V' / 'us' 等
    """
    if not measure_val:
        return None, "ux_missing", None

    s = str(measure_val)

    def _parse_num_unit(num: str, unit: str) -> Tuple[Optional[float], Optional[str]]:
        unit = (unit or "").strip()
        v, _ = parse_value_with_unit(f"{num}{unit}", keep_sign=False)
        # unit_hint 只保留“前缀+单位”的样子（如 MHz / mV / Hz / us）
        if unit:
            # 规范化
            u = unit.replace("μ", "u")
            u = {"khz": "kHz", "mhz": "MHz", "ghz": "GHz", "hz": "Hz",
                 "mv": "mV", "uv": "uV", "v": "V"}.get(u.lower(), u)
            return v, u
        return v, None

    # 1) Ux=
    m_ux = re.search(r"U[xX]\s*[:=]\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s*([a-zA-Zμ]+)?", s)
    if m_ux:
        v, u = _parse_num_unit(m_ux.group(1), m_ux.group(2) or "")
        return v, f"ux_from_Ux:{m_ux.group(1)}{m_ux.group(2) or ''}", u

    # 2) 标准值/测量值等
    for key in ["标准值", "测量值", "示值", "读数", "标准器值"]:
        m = re.search(rf"{key}\s*[:：]\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s*([a-zA-Zμ]+)?", s)
        if m:
            v, u = _parse_num_unit(m.group(1), m.group(2) or "")
            return v, f"ux_from_{key}:{m.group(1)}{m.group(2) or ''}", u

    # 3) 兜底：尝试从“同一段”里抓一个 数字+单位（优先 MHz/GHz/kHz/Hz，其次 mV/uV/V）
    m = re.search(r"([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s*(GHz|MHz|kHz|Hz|mV|uV|μV|V|ms|us|μs|ns|ps)\b", s, flags=re.IGNORECASE)
    if m:
        v, u = _parse_num_unit(m.group(1), m.group(2))
        return v, "ux_fallback_num_unit", u

    # 4) 最后才取第一个数字（无单位）
    v, _ = parse_value_with_unit(s, keep_sign=False)
    return v, "ux_fallback_first_number", None




def calc_u_formula(expr: str, measure_val: str) -> Tuple[Optional[float], str]:
    """
    解析并计算公式型不确定度：
      - U=0.1%Ux+0.04mV
      - U=0.1%Ux
      - U=0.04mV
      - U=0.1%Ux+0.04mV+0.02mV
    返回 (kb_u_abs, reason)
    """
    if not expr:
        return None, "expr_missing"

    s = str(expr).strip().replace(" ", "")
    # 兼容全角/中文符号
    s = s.replace("％", "%").replace("＋", "+").replace("﹢", "+")
    s = s.replace("—", "-").replace("−", "-")
    s = s.replace("×", "*")

    # 必须至少“像不确定度表达式”
    looks_like = ("u=" in s.lower()) or ("urel=" in s.lower()) or ("Ux" in s) or ("ux" in s) or ("%" in s) or ("+" in s)
    if not looks_like:
        return None, "not_formula"

    ux, ux_reason = _pick_ux_from_measure_text(measure_val)

    kb_u = 0.0
    parts_reason = []

    # 1) a%Ux（可选）
    m_pct = re.search(r"([0-9]*\.?[0-9]+)%U[xX]", s)
    if m_pct:
        if ux is None:
            return None, f"need_Ux_but_missing ({ux_reason})"
        a_pct = float(m_pct.group(1)) / 100.0
        kb_u += ux * a_pct
        parts_reason.append(f"{a_pct}*Ux")

    # 2) + 常数项（可多个）
    const_found = False
    for m in re.finditer(r"\+([0-9]*\.?[0-9]+)\s*([a-zA-Zμ/]+)", s):
        num = m.group(1)
        unit = m.group(2)
        # 截断复合单位 mV/div -> mV
        unit = re.split(r"[^a-zA-Zμ]", unit)[0]
        # 常见大小写归一（避免 MV 被当成 mega）
        unit = unit.replace("MV", "mV").replace("UV", "uV").replace("KV", "kV")

        v, _ = parse_value_with_unit(f"{num}{unit}", keep_sign=False)
        if v is None:
            return None, f"bad_add_unit:{num}{unit}"
        kb_u += v
        parts_reason.append(f"+{num}{unit}")
        const_found = True

    # 3) 纯常数：U=0.04mV（没有 + / 没有 Ux）
    if not const_found:
        m_uconst = re.search(r"\bU\s*=\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s*([a-zA-Zμ/]+)?", s, flags=re.IGNORECASE)
        if m_uconst:
            num = m_uconst.group(1)
            unit = m_uconst.group(2) or ""
            unit = re.split(r"[^a-zA-Zμ]", unit)[0]
            unit = unit.replace("MV", "mV").replace("UV", "uV").replace("KV", "kV")
            v, _ = parse_value_with_unit(f"{num}{unit}", keep_sign=False)
            if v is None:
                return None, f"bad_U_const:{num}{unit}"
            kb_u += v
            parts_reason.append(f"U={num}{unit}")

    if kb_u == 0.0 and not parts_reason:
        return None, "formula_parse_empty"

    reason = f"U_formula({ux_reason}): {' '.join(parts_reason)} -> {to_plain_decimal(kb_u)}"
    return kb_u, reason

def _is_missing(x) -> bool:
    if x is None: return True
    s = str(x).strip()
    return s in ["", "-", "/", "N/A", "NA", "None", "none", "0"]

def _inherit_unit_if_missing(u_str: str, measure_val: str, ux_unit_hint: Optional[str] = None) -> str:
    if u_str is None:
        return u_str
    s = str(u_str).strip()

    # 纯数字 -> 尝试补单位
    if re.fullmatch(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", s):
        # ✅ 最高优先级：用“Ux 对应的单位”
        if ux_unit_hint:
            return f"{s} {ux_unit_hint}"

        mv = str(measure_val or "")

        # 退化方案：再从整行继承（你原来的逻辑）
        m = re.search(r"\b([kKmMgG]?Hz)\b", mv, flags=re.IGNORECASE)
        if m:
            unit = {"khz": "kHz", "mhz": "MHz", "ghz": "GHz", "hz": "Hz"}.get(m.group(1).lower(), m.group(1))
            return f"{s} {unit}"

        m = re.search(r"\b([mMuUμ]?V)\b", mv, flags=re.IGNORECASE)
        if m:
            unit = m.group(1).replace("μ", "u")
            unit = {"mv": "mV", "uv": "uV", "v": "V"}.get(unit.lower(), unit)
            return f"{s} {unit}"

        m = re.search(r"\b([pnuμm]?s)\b", mv, flags=re.IGNORECASE)
        if m:
            unit = m.group(1).replace("μ", "u")
            return f"{s} {unit}"

    return s





def verify_uncertainty_logic(measure_val, cert_u, kb_u) -> str:
    """
    【工具1】不确定度合规性校验: Cert_U >= KB_U -> PASS

    返回 JSON 字符串：
    {
      "status": "PASS/FAIL/ERROR",
      "reason": "...",
      "calc_type": "uncertainty"
    }
    """
    try:
        if _is_missing(cert_u):
            return json.dumps({
                "status": "PASS",
                "reason": "证书未提供不确定度 -> Skip",
                "calc_type": "uncertainty"
            }, ensure_ascii=False)
        m_val, _ = parse_value_with_unit(measure_val)
        
        ux_val, _ux_reason, ux_unit_hint = _pick_ux_from_measure_text(measure_val)
        base_for_rel = ux_val if ux_val is not None else m_val

        cert_u_norm = _inherit_unit_if_missing(cert_u, measure_val, ux_unit_hint=ux_unit_hint)
        c_val, c_type = parse_value_with_unit(cert_u_norm, base_for_rel)

        # 先尝试公式型 U（如 U=0.1%Ux+0.04mV）
        k_val = None
        k_reason = None
        k_formula_val, k_formula_reason = calc_u_formula(kb_u, measure_val)
        if k_formula_val is not None:
            k_val = k_formula_val
            k_reason = k_formula_reason
        else:   
            k_val, k_type = parse_value_with_unit(kb_u, base_for_rel)
            k_reason = f"parsed:{k_type}"


        # 任意一方缺失，直接视为 ERROR（而不是把缺失当 0）
        if c_val is None or k_val is None:
            return json.dumps({
                "status": "ERROR",
                "reason": f"证书U或KB_U缺失：cert_u='{cert_u}', kb_u='{kb_u}'",
                "calc_type": "uncertainty"
            }, ensure_ascii=False)

        # 容差 1e-9
        if c_val >= (k_val - 1e-9):
            status = "PASS"
            reason = f"Cert({to_plain_decimal(c_val)}) >= KB({to_plain_decimal(k_val)}) ({k_reason})"
        else:
            status = "FAIL"
            reason = f"Cert({to_plain_decimal(c_val)}) < KB({to_plain_decimal(k_val)}) ({k_reason})"


        return json.dumps({
            "status": status,
            "reason": reason,
            "calc_type": "uncertainty"
        }, ensure_ascii=False)

    except Exception as e:
        return json.dumps({
            "status": "ERROR",
            "reason": str(e),
            "calc_type": "uncertainty"
        }, ensure_ascii=False)

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
                "description": (
                  "核验误差/限值："
                  "①若limit包含<,<=,>,>=（含≤≥），按不等式直接比较；"
                  "②若limit为区间a~b，按a<=error<=b；"
                  "③否则为对称容差(±L或L)，按abs(error)<=L。"
                  "输出的PASS/FAIL必须完全以本工具返回的status为准，禁止自行推导。"
                ),
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
    """
    从 KB 文本中提取不确定度信息。
    支持：
      - U = 0.00123
      - U = 0.28%          (注意：这是“相对百分数写在U里”，不当公式)
      - Urel = 0.5 %
      - Urel=6.6×10⁻⁹
      - U = 0.1%Ux+0.04mV  (公式型)
    """
    info = {"type": "N/A", "value": "N/A", "raw": None, "value_display": None}
    if not text:
        return info

    m_rel = re.search(r"U\s*rel\s*=\s*([^，,。；;]+)", text, flags=re.IGNORECASE)
    m_abs = re.search(r"\bU\s*=\s*([^，,。；;]+)", text, flags=re.IGNORECASE)

    # -------- 优先 Urel --------
    if m_rel:
        raw_val = m_rel.group(1).strip()
        has_percent = "%" in raw_val

        num = parse_unicode_sci_number(raw_val)
        if num is None:
            m_num = re.search(r"([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)", raw_val)
            num = float(m_num.group(1)) if m_num else None

        if num is None:
            return info

        if has_percent:
            frac = num / 100.0
            info["type"] = "Urel"
            info["value"] = frac                 # 计算用：0.0028
            info["value_display"] = f"{num}%"
            info["raw"] = m_rel.group(0)
            return info
        else:
            info["type"] = "Urel"
            info["value"] = num
            info["value_display"] = str(num)
            info["raw"] = m_rel.group(0)
            return info

    # -------- 再处理 U --------
    if m_abs:
        raw_val = m_abs.group(1).strip()

        # ✅ 只有 Ux/ux 或 + 才视为公式
        is_formula = (("Ux" in raw_val) or ("ux" in raw_val) or ("+" in raw_val))

        if is_formula:
            info["type"] = "U_FORMULA"
            info["value"] = raw_val              # 保留公式原串
            info["value_display"] = raw_val
            info["raw"] = m_abs.group(0)
            return info

        # ✅ 非公式：允许是纯数字，也允许是百分数(如 0.28%)
        # 1) 先试 unicode 科学计数法
        num = parse_unicode_sci_number(raw_val)

        # 2) 若不是 unicode 科学计数法，尝试普通数字
        if num is None:
            m_num = re.search(r"([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)", raw_val)
            num = float(m_num.group(1)) if m_num else None

        # 3) 如果连数字都没有（比如 raw_val="0.28%" 其实能抓到 0.28，不会进这里）
        if num is None:
            # 兜底：把原串保留下来，后续 parse_value_with_unit(base_val) 仍可能处理
            info["type"] = "U"
            info["value"] = raw_val
            info["value_display"] = raw_val
            info["raw"] = m_abs.group(0)
            return info

        # 4) 这里不把 % 转 fraction（因为 U 本身可能是百分数表达）
        #    让后续 parse_value_with_unit(cert_u/kb_u, base_val) 来决定是否转绝对值
        info["type"] = "U"
        info["value"] = raw_val                  # ✅ 保留原串（例如 "0.28%" 或 "0.00123"）
        info["value_display"] = raw_val
        info["raw"] = m_abs.group(0)
        return info

    # ✅ 必须兜底 return
    return info

def ensure_dict(x) -> Dict[str, Any]:
    """把 metadata 强制变成 dict（兼容 str / None / 乱七八糟类型）"""
    if x is None:
        return {}
    if isinstance(x, dict):
        return x
    # Chroma/LlamaIndex 有时会把 metadata 序列化成 JSON 字符串
    if isinstance(x, str):
        s = x.strip()
        if not s:
            return {}
        try:
            obj = json.loads(s)
            return obj if isinstance(obj, dict) else {}
        except Exception:
            return {}
    return {}  # 其他类型一律丢弃

def ensure_uncertainty(u, doc_text: str) -> Dict[str, Any]:
    """确保 uncertainty 一定是 dict。否则回退到从 doc 里抽取。"""
    if isinstance(u, dict):
        return u
    # 如果 meta 里存的是字符串（比如 "Urel=..." 或 "0.28%"），就别信它，直接用 doc 抽
    return detect_uncertainty_info(doc_text)




def split_values_maybe_list(x) -> List[str]:
    if x is None: return []
    if isinstance(x, list): return [str(v) for v in x]
    return [p.strip() for p in re.split(r"[，,；;]\s*", str(x)) if p.strip()]


# def parse_kb_entry(doc: str, meta: Dict[str, Any]) -> Dict[str, Any]:
#     # 1. 提取仪器名称 (之前缺失的定义)
#     instrument_name = meta.get("仪器名称") or pick_first(doc, r"仪器名称[：:]\s*(.+?)[。；]") or "N/A"
#     file_code = meta.get("file_code") or meta.get("规程代号") or None

#     # 2. 提取校准依据
#     standard_name = meta.get("校准依据") or pick_first(doc, r"校准依据[：:]\s*(.+?)[。；\n]") or "N/A"

#     # 3. 提取规程编号 (优化后的正则逻辑)
#     # 匹配 JJG/JJF 开头，允许中间有空格，必须有数字
#     file_code = pick_first(doc, r"\b(JJ[GF]|GJB)\s*\d+(?:\s*-\s*\d{4})?\b")
#     if file_code:
#         # 统一标准化：只保留 前缀 + 数字，忽略年份
#         m = re.search(r"\b(JJ[GF]|GJB)\s*(\d+)", file_code, re.IGNORECASE)
#         file_code = f"{m.group(1).upper()} {m.group(2)}" if m else file_code

#     # 如果正则没抓到，尝试从 standard_name 里再抓一次
#     if not file_code and standard_name != "N/A":
#         m = re.search(r"\b(JJ[GF]|GJB)\s*(\d+)(?:\s*-\s*\d{4})?\b", standard_name, re.IGNORECASE)
#         if m:
#             file_code = f"{m.group(1).upper()} {m.group(2)}"

#     # 兜底逻辑：实在抓不到编号，就用规程名称代替，防止 N/A
#     if not file_code:
#         file_code = standard_name if standard_name != "N/A" else "未知规程"

#     # 4. 提取被测量
#     measured = pick_first(doc, r"被测量[：:]\s*(.+?)[。；]") or "N/A"

#     # 5. 提取测量范围
#     measure_range_text = pick_first(doc, r"测量范围[：:]\s*(.+?)[。；]") or "-"

#     # 6. 提取不确定度
#     uncertainty = detect_uncertainty_info(doc)

#     return {
#         "instrument_name": instrument_name,
#         "standard_name": standard_name,
#         "file_code": file_code,
#         "measured": measured,
#         "measure_range_text": measure_range_text,
#         "uncertainty": uncertainty,
#         "raw": doc,
#         "meta": meta or {},
#     }

def parse_kb_entry(doc: str, meta: Dict[str, Any]) -> Dict[str, Any]:
    print("DEBUG parse_kb_entry | type(doc):", type(doc), "type(meta):", type(meta))
    meta = ensure_dict(meta)  # ✅ 根治：不管传进来是啥，先变 dict

    # 1) 仪器名称
    instrument_name = (
        meta.get("仪器名称")
        or meta.get("instrument_name")
        or pick_first(doc, r"仪器名称[：:]\s*(.+?)(?:[。；\n]|$)")
        or "N/A"
    )

    # 2) 校准依据（标准名称）
    standard_name = (
        meta.get("standard_name")
        or meta.get("校准依据")
        or pick_first(doc, r"校准依据[：:]\s*(.+?)(?:[。；\n]|$)")
        or "N/A"
    )

    # 3) 规程代号 file_code
    file_code = meta.get("file_code") or meta.get("规程代号") or None

    # 3.1) meta 没给 -> doc 抓
    if not file_code:
        fc = pick_first(doc, r"\b(JJ[GF]|GJB)\s*\d+(?:\s*-\s*\d{4})?\b")
        if fc:
            m = re.search(r"\b(JJ[GF]|GJB)\s*(\d+)", fc, re.IGNORECASE)
            file_code = f"{m.group(1).upper()} {m.group(2)}" if m else fc

    # 3.2) doc 也没抓到 -> standard_name 抓
    if (not file_code) and standard_name != "N/A":
        m = re.search(r"\b(JJ[GF]|GJB)\s*(\d+)(?:\s*-\s*\d{4})?\b", standard_name, re.IGNORECASE)
        if m:
            file_code = f"{m.group(1).upper()} {m.group(2)}"

    # 3.3) 兜底
    if not file_code:
        file_code = standard_name if standard_name != "N/A" else "未知规程"

    # 4) 被测量
    measured = (
        meta.get("被测量")
        or meta.get("measured")
        or pick_first(doc, r"被测量[：:]\s*(.+?)(?:[。；\n]|$)")
        or "N/A"
    )

    # 5) 测量范围
    measure_range_text = (
        meta.get("测量范围")
        or meta.get("measure_range_text")
        or pick_first(doc, r"测量范围[：:]\s*(.+?)(?:[。；\n]|$)")
        or "-"
    )

    # 6) 不确定度：强制 dict
    raw_u = meta.get("不确定度") or meta.get("uncertainty")
    uncertainty = ensure_uncertainty(raw_u, doc)  # ✅ 根治 build_table 的 .get 报错

    return {
        "instrument_name": instrument_name,
        "standard_name": standard_name,
        "file_code": file_code,
        "measured": measured,
        "measure_range_text": measure_range_text,
        "uncertainty": uncertainty,
        "raw": doc,
        "meta": meta,
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
             criterion: str, topk: int = 50) -> List[Dict[str, Any]]:
    """
    根据仪器名和依据，在向量数据库中检索相关的 KB 条目。
    """
    print(f"\n📘 [Retrieval] 正在检索: {instrument_name} {criterion}")

    # 1. 构造查询词
    # m = re.search(r"(JJ[GF]\s*\d+(?:-\d{4})?)", criterion, re.IGNORECASE)
    # if m:
    #     basis_code = m.group(1).replace(" ", "")
    #     query_text = f"{instrument_name} {basis_code}"
    # else:
    #     query_text = f"{instrument_name} {criterion}".strip()

    basis_code = extract_basis_code(criterion)  # e.g. "GJB 7691" / "JJG 237"
    if basis_code:
        # query_text = f"{instrument_name} {norm_code(basis_code)}"
        query_text = f"{instrument_name} {norm_code(basis_code)} 规程代号 {norm_code(basis_code)}"


    else:
        query_text = f"{instrument_name} {criterion}".strip()

    # 2. 获取集合
    try:
        coll = client.get_collection(collection_name)
    except Exception as e:
        print(f"❌ 加载集合失败：{e}")
        return []

    # 3. 检索
    q_emb = embedder.encode([query_text]).tolist()

    try:
        res = coll.query(
            query_embeddings=q_emb,
            n_results=topk,  # ✅ 使用传入的 topk
            include=["documents", "metadatas"]
        )
    except Exception as e:
        print(f"❌ ChromaDB 查询异常: {e}")
        return []

    docs = res.get("documents", [[]])[0] if res and res.get("documents") else []
    metas = res.get("metadatas", [[]])[0] if res and res.get("metadatas") else [{} for _ in docs]

    entries = []
    for d, m in zip(docs, metas):
        entries.append(parse_kb_entry(d, m))

    print(f"✅ 检索完成，共找到 {len(entries)} 条 (Top-K={topk})")
    return entries

##添加匹配不到就返回核验不通过 的强制后处理函数
def enforce_kb_missing_fail(md: str) -> str:
    """
    兜底修正：若表格行 KB编号=无/N/A，则判定必须 FAIL
    适配你的输出列：序号, 测量点, KB编号, 证书匹配项, 范围, 证书误差, 允许误差, 证书U, KB_U, 判定, 说明
    """
    if not md or "|" not in md:
        return md

    lines = md.splitlines()
    out = []
    in_table = False
    header_cols = []
    idx_kb = idx_judge = idx_note = None

    def split_row(line: str) -> List[str]:
        # 去掉首尾空格/首尾竖线，再按竖线切
        raw = line.strip()
        if raw.startswith("|"): raw = raw[1:]
        if raw.endswith("|"): raw = raw[:-1]
        return [c.strip() for c in raw.split("|")]

    for line in lines:
        # 识别表头行（包含 KB编号 和 判定）
        if line.strip().startswith("|") and ("KB编号" in line) and ("判定" in line):
            in_table = True
            header_cols = split_row(line)
            # 建索引
            def find_idx(name: str):
                try:
                    return header_cols.index(name)
                except ValueError:
                    return None
            idx_kb = find_idx("KB编号")
            idx_judge = find_idx("判定")
            idx_note = find_idx("说明")
            out.append(line)
            continue

        # 表格分隔线（|---|---|）
        if in_table and re.match(r"^\s*\|\s*-{2,}", line):
            out.append(line)
            continue

        # 表格数据行
        if in_table and line.strip().startswith("|") and (idx_kb is not None) and (idx_judge is not None):
            cols = split_row(line)
            # 行长度不足则原样输出
            if len(cols) <= max(idx_kb, idx_judge):
                out.append(line)
                continue

            kb_no = cols[idx_kb].strip()
            judge = cols[idx_judge].strip().upper()

            kb_missing = kb_no in {"无", "N/A", "NA", "-", ""}

            if kb_missing:
                # 强制 FAIL
                cols[idx_judge] = "FAIL"
                # 补说明（不能含 |）
                if idx_note is not None and idx_note < len(cols):
                    note = cols[idx_note].strip()
                    add = "KB无对应参数 -> 判定FAIL（不允许按PASS或Skip处理）"
                    if add not in note:
                        cols[idx_note] = (note + "；" + add).strip("；").strip()
                # 重组行
                out.append("| " + " | ".join(cols) + " |")
            else:
                out.append(line)
            continue

        # 离开表格（遇到空行或非表格行都可能结束；这里简单处理：遇到非表格行就结束表格态）
        if in_table and not line.strip().startswith("|"):
            in_table = False

        out.append(line)

    return "\n".join(out)


def enforce_point_id(md: str) -> str:
    """
    后处理 Markdown 表格中的【点位】列：
    - 如果点位为空 / N/A
    - 且同一行（尤其是“测量点”列）中出现 CHx / ch x / CH x
    - 则强制将点位补为标准化后的 CHx

    适配表头包含：点位、测量点
    """

    if not md or "|" not in md:
        return md

    lines = md.splitlines()
    out = []
    in_table = False
    header_cols = []
    idx_point = idx_measure = None

    def split_row(line: str):
        raw = line.strip()
        if raw.startswith("|"):
            raw = raw[1:]
        if raw.endswith("|"):
            raw = raw[:-1]
        return [c.strip() for c in raw.split("|")]

    for line in lines:
        # 识别表头（必须同时包含 点位 和 测量点）
        if line.strip().startswith("|") and ("点位" in line) and ("测量点" in line):
            in_table = True
            header_cols = split_row(line)

            def find_idx(name: str):
                try:
                    return header_cols.index(name)
                except ValueError:
                    return None

            idx_point = find_idx("点位")
            idx_measure = find_idx("测量点")

            out.append(line)
            continue

        # 表格分隔线
        if in_table and re.match(r"^\s*\|\s*-{2,}", line):
            out.append(line)
            continue

        # 表格数据行
        if in_table and line.strip().startswith("|") and idx_point is not None:
            cols = split_row(line)

            if len(cols) <= idx_point:
                out.append(line)
                continue

            point_val = cols[idx_point].strip()

            # 判断是否需要补点位
            need_fill = point_val in {"", "-", "N/A", "NA", "n/a"}

            if need_fill:
                search_text = " ".join(cols)
                m = re.search(r"\bch\s*([0-9]+)\b", search_text, flags=re.IGNORECASE)
                if m:
                    ch = f"CH{m.group(1)}"
                    cols[idx_point] = ch
                    out.append("| " + " | ".join(cols) + " |")
                else:
                    out.append(line)
            else:
                out.append(line)

            continue

        # 退出表格状态
        if in_table and not line.strip().startswith("|"):
            in_table = False

        out.append(line)

    return "\n".join(out)


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
                      instrument: str, criterion: str, cfg: Any) -> str:

    # ================= 🚀 优化 1：KB 列表重排序 =================
    # 将 KB 条目按“被测量名称”排序，确保同名参数（如不同频段的电平）在列表中紧挨着出现
    # 这样 LLM 在阅读时能一次性看到所有可能的范围选项，防止“看到第一个就停”
    sorted_kb_items = sorted(kb_items, key=lambda x: x['measured'])

    # 构造 KB 摘要
    kb_summary = []
    for k in sorted_kb_items:
        code = k.get('file_code', 'N/A')
        name = k.get('standard_name', '')
        if code == "N/A" or code == "未知规程":
            m = re.search(r"\b(JJ[GF]|GJB)\s*(\d+)", name, re.IGNORECASE)
            if m:
                code = f"{m.group(1).upper()} {m.group(2)}"

        display_id = f"{code}"
        if name and name != "N/A" and name != code:
            display_id += f" ({name})"
##=====  实现urel标识符的保留，防止丢失后被识别为绝对值 =======####
        u = k.get("uncertainty") or {}
        ut = (u.get("type") or "").strip().upper()
        uv = u.get("value")
        uv_disp = u.get("value_display")

        def _is_valid(v) -> bool:
            if v is None:
                return False
            s = str(v).strip()
            return s not in ["", "N/A", "NA", "-", "None", "none", "/"]

        # ========== 1) 展示用：kb_u_str ==========
        if ut == "UREL" and _is_valid(uv):
            shown = uv_disp if _is_valid(uv_disp) else str(uv)  # 优先 0.28%
            kb_u_str = f"Urel={shown}"
        elif ut == "U" and _is_valid(uv):
            shown = uv_disp if _is_valid(uv_disp) else str(uv)
            kb_u_str = f"U={shown}"
        elif ut in ["U_FORMULA", "FORMULA"] and _is_valid(uv):
            # uv 应该是类似 "0.1%Ux+0.04mV"
            kb_u_str = f"U={uv}"
        else:
            kb_u_str = "N/A"

        # ========== 2) 计算用：kb_u_calc ==========
        if ut == "UREL" and _is_valid(uv):
            # uv 可能是 0.0028(正确fraction) 也可能是 0.28(百分数数字) 或 "0.28%"(字符串)
            uv_norm = uv
            try:
                # "0.28%" -> 0.0028
                if isinstance(uv_norm, str) and "%" in uv_norm:
                    uv_norm = float(re.search(r"[-+]?\d*\.?\d+", uv_norm).group()) / 100.0
                # 0.28 -> 0.0028 （经验规则：>1 当作异常；0.01~1 可能是百分数数字）
                elif isinstance(uv_norm, (int, float)) and (0 < uv_norm <= 1.0):
                    # 这里不动：0.0028/0.1 都是合理系数
                    pass
                elif isinstance(uv_norm, (int, float)) and (1.0 < uv_norm <= 100.0):
                    uv_norm = uv_norm / 100.0
            except Exception:
                pass

            kb_u_calc = f"Urel={uv_norm}"

        elif ut == "U" and _is_valid(uv):
            kb_u_calc = f"U={uv}"
        elif ut in ["U_FORMULA", "FORMULA"] and _is_valid(uv):
            # 让 verify_uncertainty_logic 走 calc_u_formula(expr, measure_val)
            kb_u_calc = f"U={uv}"
        else:
            kb_u_calc = "N/A"

        kb_summary.append({
            "id": display_id,
            "measured": k.get("measured"),
            "range": k.get("measure_range_text"),
            "kb_u_str": kb_u_str,
            "kb_u_calc": kb_u_calc,
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
    
        "2. **数值范围精准匹配 (Precise Range Matching)**：\n"
        "   - 当有多个同名参数（如'电平'）但范围不同时，**必须**选择数值包含测量点的那个条目。\n"
        "   - **严禁**选择范围不匹配的条目。如果测量点不在条目范围内，绝对不能选它！\n"
        "   - KB 中经常包含同一个参数的多个分段（例如‘电平’可能有 -90~-50 和 -50~0 两条）。\n"
        "   - **你必须遍历所有同名条目！**\n"
        "   - **禁止偷懒**：如果第一个同名条目的范围不匹配（例如测量点 -8 不在 -90~-50 内），**不要立即判错**！\n"
        "   - **继续往下找**！直到找到一个范围覆盖该测量点（如 -50~0）的条目。\n"
        "   - 只有当**所有**同名条目的范围都不包含测量点时，才判定为 FAIL (范围)。\n"
        "   - **典型错误案例警告**：\n"
        "     * 测量点：`-5 dBm`\n"
        "     * 错误KB：范围 `-90 ～ -50 dBm` (因为 -5 > -50，不在此范围内)\n"
        "     * 正确KB：范围 `-50 ～ 0 dBm` (因为 -5 在此范围内)\n"
        "     * **如果你选择了错误的KB并声称‘范围：Pass’，这是严重逻辑错误！**\n"
        
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
        "### 第一步：KB选择与范围核验 (Selection & Range)\n"
        "1. **KB优选与边界处理 (Critical)**：\n"
        "   - **优先匹配**：选择数值范围包含测量点的 KB 条目。\n"
        "   - **边界重叠处理**：如果测量点（如 0 dBm）同时落在两个 KB 范围的边界上（例如 A: -50~0, B: 0~30）：\n"
        "     * **必须** 检查两个 KB 的不确定度要求。\n"
        "     * **优先选择** 那个能让 `Cert_U >= KB_U` 成立（即判定为 Pass）的条目。\n"
        "     * **案例**：测量点 0dBm, Cert_U=0.16。KB_A(0~30, U=0.22), KB_B(-50~0, U=0.16)。因为 0.16 < 0.22 (Fail) 但 0.16 >= 0.16 (Pass)，**必须选择 KB_B**。\n"
        "2. **双重范围匹配 (Dual Range Matching) - 严厉警告！**：\n"
        "   - 许多射频参数（如电平、失真、相位噪声）同时受 **频率** 和 **数值(幅度)** 的限制。\n"
        "   - **必须同时满足两个条件**才能选择该 KB 条目：\n"
        "     * 条件 A: 测量点的【频率】在 KB 的频率范围内。\n"
        "     * 条件 B: 测量点的【数值】在 KB 的数值范围内。\n"
        "   - **错误案例**：测量点 `2300 MHz, -10 dBm`。\n"
        "     * 错误KB: `(-80~-50)dBm (1.3~26.5 GHz)` -> 虽然频率匹配，但数值 -10 不在 -80~-50 内 -> **严禁选择！**\n"
        "     * 正确KB: `(-10~10)dBm (1.3~26.5 GHz)` -> 频率匹配，数值 -10 也在 -10~10 内 -> **正确！**\n"
        "   - 如果一条KB仅频率匹配但数值不匹配，**跳过它**，继续寻找下一条！\n"
        "3. **单位换算 (Critical)**：\n"
        "   - 若测量点单位（如 dBm, Vrms）与 KB 单位（如 V, Vpp）不一致，**必须先调用工具** `unit_convert_tool` 将其转换为 KB 单位。\n"
        "   - **严禁口算**！必须使用工具转换后的数值进行范围判断。\n"
        "4. **常规情况**：\n"
        "   - 确认测量点是否在 KB 范围内。\n"
        "   - **原则**：采用【闭区间】。若 测量值 = 范围上限 或 测量值 = 范围下限，均视为 Pass。\n"
        "5. **特殊映射（必须优先执行）**：\n"
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
        "调用 verify_uncertainty_logic 时，KB_U 必须使用 kb_u_calc 字段，禁止使用 kb_u_str。\n\n"

        "### 输出格式要求 (Strict Output Format)\n"
        "请按 `param_name` 将结果分组。对于每一个不同的参数名称，输出一个独立的表格：\n\n"
        
        
        "### 强制失败规则（KB缺失即失败）\n"
        "- 若在【正确规程】的 KB 候选中，找不到与当前参数物理量匹配的“被测量(measured)”条目（即无法选出KB编号/范围/KB_U），则该测量点【判定必须为 FAIL】。\n"
        "- 此时：KB编号填“无”，范围填“N/A”，KB_U填“N/A”，说明必须写“KB无对应参数 -> 判定FAIL（不允许按PASS或Skip处理）”。\n"
       
        "### 点位列生成规则（必须遵守）"
        "- 你必须为每一行生成【点位】列，用于定位具体测试点（如通道/频率/端口/档位）。"
        "- 生成顺序（从高到低）："
        "  1) 若该行任意字段的“值”出现模式 CH\\d+（如 CH3、ch3、CH 3），点位输出为标准化后的 CHx（例如 CH3）。"
        "  2) 否则若存在字段名包含“通道”或“channel”或等价含义，取其值并标准化为 CHx。"
        "  3) 否则若能从该行提取到频率（值或字段名包含 Hz/kHz/MHz/GHz/freq/frequency/频率），点位输出该频率（保留原单位）。"
        "  4) 否则点位输出 N/A。"
        "- 【点位】必须尽量短且唯一定位该点；【测量点】保持详细描述（偏转因数、标准值等）。"
        


        "### 输出格式\n"
        "输出 Markdown 表格，列包含：序号, 点位, 测量点, KB编号, 证书匹配项, 范围, 证书误差, 允许误差, 证书U, KB_U, 判定, 说明。\n"
        "**注意：在【说明】列中，严禁使用竖线符号 '|'，请使用 'abs()' 表示绝对值，以免破坏表格结构。**\n"        
        "在【说明】栏中，必须引用工具返回的计算依据，并且指出选择了哪条KB以及选择理由。"
        "当你引用 unit_convert_tool 的输出时，必须把 tool 输出中的 md_note 原样写入【说明】列。\n"
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

    # ✅ 获取 UI 配置参数
    model_name = getattr(cfg, 'MODEL', 'deepseek-chat')
    temp_val = getattr(cfg, 'TEMPERATURE', 0.1)

    for turn in range(MAX_TURNS):
        try:
            response = client.chat.completions.create(
                model=model_name, # ✅ 使用传入的配置
                messages=messages,
                tools=TOOLS_SCHEMA,
                tool_choice="auto",
                
                temperature=temp_val # ✅ 使用传入的配置
            )
            msg = response.choices[0].message
            # print(f">>> LLM returned: content_len={len(msg.content or '')}, tool_calls={len(msg.tool_calls or [])}",
            #       flush=True)
        except Exception as e:
            return f"> 🚨 API 请求失败: {e}"

        tool_calls = msg.tool_calls

        # 情况 A: 模型想要调用工具
        if tool_calls:
            print(">>> ENTER tool_calls branch", flush=True)
            messages.append(msg)  # 必须将模型的“思考/调用请求”加入历史

            enforcement_notes = []

            # 处理这一轮所有的工具调用
            for tool_call in tool_calls:

                fname = tool_call.function.name
                # print(f">>> TOOL_CALL fname={fname} args={tool_call.function.arguments}", flush=True)
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
                    # print(">>> TOOL_OUT verify_error_logic:", tool_res)
                    try:
                        r = json.loads(tool_res)
                        enforcement_notes.append(
                            f"工具判定: 误差 {args.get('error_val')} -> {r.get('status')} ({r.get('reason')})")
                    except:
                        pass


                elif fname == "unit_convert_tool":
                    raw_tool_res = unit_convert_tool(args.get("val_str"), args.get("impedance", 50.0))
                    # ✅ 将免责声明写入 tool 输出，确保 LLM 写入 MD 的说明中
                    try:
                        obj = json.loads(raw_tool_res) if isinstance(raw_tool_res, str) else raw_tool_res
                        if isinstance(obj, dict):
                            obj["md_note"] = UNIT_CONVERT_DISCLAIMER


                            tool_res = json.dumps(obj, ensure_ascii=False)
                        else:
                            # 不是 dict（极少见），直接拼文本
                            tool_res = f"{raw_tool_res}\n\n{UNIT_CONVERT_DISCLAIMER}"
                    except Exception:
                        # raw_tool_res 不是 JSON，就直接拼文本
                        tool_res = f"{raw_tool_res}\n\n{UNIT_CONVERT_DISCLAIMER}"
                    try:
                        enforcement_notes.append(f"单位换算: {args.get('val_str')} -> {tool_res}")
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


def run_llm_mode(json_file: str, cfg: Config, stop_event=None,embedder_obj=None) -> str:
    """
    执行 LLM 参数核验的主流程 (支持并发与中断)
    """

    # 🛑 0.【关键】初始刹车检查
    if stop_event and stop_event.is_set():
        print("🛑 [ParamCheck] 任务在初始化阶段被终止")
        return "⚠️ 核验任务已由用户在初始化阶段取消。"

    # 1. 加载数据
    # 从 cfg 实例获取参数，防止 cfg 是类对象时的属性缺失
    current_top_k = getattr(cfg, 'TOPK', 50)
    max_w = getattr(cfg, 'max_workers', 5)

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
    print(f"⚙️ 配置: TopK={current_top_k}, MaxWorkers={max_w}")

    # 2. 初始化资源
    # 建议：如果 app.py 传入了 shared_embedder，这里可以优化（目前保持原样）
    # 如果传入了现成的模型对象，就直接用，否则再自己加载
    if embedder_obj:
        print("⚡ [ParamCheck] 使用共享的语义模型")
        embedder = embedder_obj
    else:
        print(f"🧠 [ParamCheck] 正在加载语义模型: {cfg.EMBED_MODEL_PATH}")
        embedder = SentenceTransformer(cfg.EMBED_MODEL_PATH)

    chroma_client = chromadb.PersistentClient(path=cfg.DB_DIR)
    # embedder = SentenceTransformer(cfg.EMBED_MODEL_PATH)
 
    client = OpenAI(api_key=cfg.API_KEY, base_url=cfg.API_BASE)

    report_lines = [
        "# CNAS 智能核验报告 (Agentic Mode - Parallel)",
        f"- 证书编号: {root.get('证书编号', 'N/A')}",
        f"- 仪器: {instrument_name}",
        f"- 时间: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        ""
    ]

    # 3. 按依据循环
    for criterion in criteria_list:

        # 🛑 1.【关键】循环间刹车检查
        if stop_event and stop_event.is_set():
            return "⚠️ 核验任务已由用户手动终止。"

        report_lines.append(f"## 依据: {criterion}")

        # ✅ 2.【关键】修复 Top-K 传参
        # 必须显式传入 topk 参数，否则函数会用默认值 50
        kb_items = query_kb(
            chroma_client,
            embedder,
            cfg.COLLECTION,
            instrument_name,
            criterion,
            topk=current_top_k  # <--- 修改在这里
        )
        #强制返回逻辑:若匹配不到相应依据，则返回fail
        basis_code = extract_basis_code(criterion)
        basis_code_norm = norm_code(basis_code) if basis_code else None

        if basis_code_norm:
            # 仅保留 file_code 与依据一致的 KB
            kb_items_same_basis = [
                it for it in kb_items
                if norm_code(it.get("file_code")) == basis_code_norm
            ]

            # 如果 file_code 抓取不稳定，再补一层：从 standard_name 再抓一次比对
            if not kb_items_same_basis:
                for it in kb_items:
                    std_name = it.get("standard_name", "")
                    m2 = re.search(r"\b(JJ[GF]|GJB)\s*(\d+)(?:\s*-\s*\d{4})?\b", std_name, re.IGNORECASE)
                    if m2:
                        picked = f"{m2.group(1).upper()} {m2.group(2)}"  # 忽略年份
                        if norm_code(picked) == basis_code_norm:
                            kb_items_same_basis.append(it)

            # 如果仍然为空：直接跳过该依据核验，输出 ERROR
            if not kb_items_same_basis:
                report_lines.append("### ❌ 核验终止（依据一致性失败）")
                report_lines.append(
                    f"- 证书依据: {criterion}\n"
                    f"- 提取规程代号: {basis_code}\n"
                    f"- 结果: 知识库中找不到与该规程一致的条目，因此**跳过核验并返回 ERROR**。\n"
                    f"- 处理建议: 请补充/导入 {basis_code} 对应的 KB 条目后再核验。"
                )
                report_lines.append("\n---\n")
                continue  # ✅ 关键：直接进入下一个 criterion

            # ✅ 用“同规程过滤后的 KB”覆盖原 kb_items，禁止 LLM 看到别的规程
            kb_items = kb_items_same_basis
        else:
            # 若证书依据里连 JJG/JJF 代号都提取不到：建议也直接 ERROR（看你业务是否允许）
            report_lines.append("### ❌ 核验终止（依据代号无法解析）")
            report_lines.append(
                f"- 证书依据: {criterion}\n"
                f"- 结果: 无法从依据中解析 JJG/JJF 规程代号，系统不允许跨规程自动核验，因此返回 ERROR。"
            )
            report_lines.append("\n---\n")
            continue



        # ================= 🚀 新增：在控制台打印检索结果 =================
        if kb_items:
            print("\n" + "=" * 60)
            print(f"📄 [Preview] 检索到的知识库内容 (Top-{len(kb_items)}):")
            print(f"   依据: {criterion}")
            print("-" * 60)

            # 遍历打印每一条，为了防止刷屏太长，可以只打印前 10 条或者简化内容
            for i, item in enumerate(kb_items, 1):
                # 获取信息，处理过长文本
                std = item.get('file_code', 'N/A')
                measured = item.get('measured', 'N/A')
                rng = item.get('measure_range_text', '-')
                # 如果范围文本太长，截断一下
                if len(rng) > 50: rng = rng[:47] + "..."

                print(f"  {i:02d}. [{std}] {measured} | 范围: {rng}")

            print("=" * 60 + "\n")
        else:
            print(f"\n⚠️ [Warning] 未检索到关于 '{criterion}' 的知识库条目！\n")
        # ==============================================================

        # ================= 并发核心逻辑开始 =================

        batches = list(chunk_list(all_cert_params, cfg.BATCH_SIZE))
        total_batches = len(batches)

        print(f"🚀 启动并发处理: 共 {total_batches} 个批次，线程数: {max_w}")

        # 使用线程池
        with ThreadPoolExecutor(max_workers=max_w) as executor:
            future_to_index = {}

            # 提交任务
            for idx, batch in enumerate(batches):
                # 🛑 提交前检查，避免无意义提交
                if stop_event and stop_event.is_set(): break

                future = executor.submit(
                    run_agentic_batch,
                    client,
                    batch,
                    kb_items,
                    instrument_name,
                    criterion,
                    cfg
                )
                future_to_index[future] = idx + 1

            # 用于存储结果
            results_map = {}

            # 处理完成的任务
            try:
                for future in as_completed(future_to_index):

                    # 🛑 3.【核心】并发时的急刹车
                    # 只要检测到停止信号，立刻杀死线程池
                    if stop_event and stop_event.is_set():
                        print("🛑 [ParamCheck] 接到终止指令，正在强制清理线程池...")
                        executor.shutdown(wait=False, cancel_futures=True)
                        return "⚠️ 核验任务已由用户手动终止 (并发阶段)。"

                    idx = future_to_index[future]
                    try:
                        content = future.result()

                        content = enforce_kb_missing_fail(content)  # ✅ 兜底强制：KB缺失行 => FAIL
                        content = enforce_point_id(content)

                        results_map[idx] = content
                        print(f"   ✅ Batch {idx}/{total_batches} 完成")
                    except Exception as e:
                        error_msg = f"> 🚨 Batch {idx} 失败：{e}"
                        print(error_msg)
                        results_map[idx] = error_msg
                        # 如果是严重错误，也可以选择在这里 return 终止整个流程

            except Exception as e:
                print(f"❌ 线程池异常: {e}")

        # ================= 并发结束，按顺序组装报告 =================

        # 🛑 再次检查，防止组装报告时浪费时间
        if stop_event and stop_event.is_set(): return "⚠️ 任务已终止"

        for i in range(1, total_batches + 1):
            report_lines.append(f"#### 📌 Batch {i}")
            report_lines.append(results_map.get(i, "> 任务被取消或执行异常"))
            report_lines.append("\n---\n")

    return "\n".join(report_lines)



# def main():
#     # 请修改此处的文件名
#     BASE_DIR = Path(r"D:\workspace\ai大模型开发课\文档核验\work_pdf\local_json")
#     JSON_FILE = "1GA25005017-0001.json"
#     JSON_PATH = str(BASE_DIR / JSON_FILE)
#
#     cfg = Config()
#     report = run_llm_mode(JSON_PATH, cfg)
#
#     out_path = Path(cfg.OUTPUT_DIR) / f"Agent_Report_{Path(JSON_FILE).stem}.md"
#     os.makedirs(cfg.OUTPUT_DIR, exist_ok=True)
#     out_path.write_text(report, encoding="utf-8")
#     print(f"\n✅ 完成! 报告已保存: {out_path}")
#
#
# if __name__ == "__main__":
#     main()



def main():
    # 请修改此处的文件名
    BASE_DIR = Path(r"D:\workspace\ai大模型开发课\文档核验\work_pdf\local_json")
    JSON_FILE = "1GA25003260-0015.json"
    JSON_PATH = str(BASE_DIR / JSON_FILE)

    cfg = Config()
    report = run_llm_mode(JSON_PATH, cfg)

    out_path = Path(cfg.OUTPUT_DIR) / f"Agent_Report_{Path(JSON_FILE).stem}.md"
    os.makedirs(cfg.OUTPUT_DIR, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    print(f"\n✅ 完成! 报告已保存: {out_path}")


if __name__ == "__main__":
    main()
