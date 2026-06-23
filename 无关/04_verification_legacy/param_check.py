from __future__ import annotations

import os
import json
import re
import time
import math
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed # 新增：支持并发

import chromadb
from chromadb.errors import NotFoundError
from config.settings import get_app_config
from langchain_app.checks.parameter import infer_param_semantics, select_basis_with_audit
from langchain_app.checks.parameter.semantic import FirstCandidateDecider


# ===================== 配置 =====================
class Config:
    _app = get_app_config()
    DB_DIR = _app.cnas_db_dir
    COLLECTION = _app.cnas_collection
    EMBED_MODEL_PATH = _app.embed_model_path
    OUTPUT_DIR = str(_app.reports_dir)
    API_KEY = _app.api_key or os.getenv("DEEPSEEK_API_KEY", "")
    API_BASE = _app.api_base.rstrip("/")
    MODEL = _app.model
    TEMPERATURE = _app.temperature
    MAX_TOKENS = _app.max_tokens
    TOPK = _app.topk
    BATCH_SIZE = _app.batch_size
    max_workers = _app.max_workers


LAST_QUERY_ERROR: Optional[str] = None


def _build_param_check_version_stamp() -> str:
    path = Path(__file__)
    stat = path.stat()
    mtime = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime))
    digest = hashlib.sha1(path.read_bytes()).hexdigest()[:10]
    return f"param_check.py | mtime={mtime} | sha1={digest}"

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

# ✅ 长度单位白名单：为了可读性，保留 nm/um/mm/pm 作为原单位，不按前缀换算成 m
ATOMIC_LENGTH_UNITS = {
    "pm", "nm", "um", "μm", "mm", "cm"  # 你需要哪些就留哪些
}

CANONICAL_UNIT_MAP = {
    "thz": "THz",
    "ghz": "GHz",
    "mhz": "MHz",
    "khz": "kHz",
    "hz": "Hz",
    "kv": "kV",
    "mv": "mV",
    "uv": "uV",
    "v": "V",
    "ma": "mA",
    "ua": "uA",
    "a": "A",
    "ms": "ms",
    "us": "us",
    "ns": "ns",
    "ps": "ps",
    "s": "s",
    "pm": "pm",
    "nm": "nm",
    "um": "um",
    "mm": "mm",
    "cm": "cm",
    "m": "m",
    "m2": "m2",
    "m3": "m3",
    "m/s": "m/s",
    "m/s2": "m/s2",
    "m/s3": "m/s3",
    "db": "dB",
    "dbc": "dBc",
    "dbc/hz": "dBc/Hz",
    "dbm": "dBm",
    "dbmv": "dBmV",
    "deg": "deg",
    "°": "°",
}

EXACT_UNIT_MULTIPLIERS = {
    "THz": 1e12,
    "GHz": 1e9,
    "MHz": 1e6,
    "kHz": 1e3,
    "Hz": 1.0,
    "kV": 1e3,
    "V": 1.0,
    "mV": 1e-3,
    "uV": 1e-6,
    "A": 1.0,
    "mA": 1e-3,
    "uA": 1e-6,
    "s": 1.0,
    "ms": 1e-3,
    "us": 1e-6,
    "ns": 1e-9,
    "ps": 1e-12,
    "m": 1.0,
    "cm": 1e-2,
    "mm": 1e-3,
    "um": 1e-6,
    "nm": 1e-9,
    "pm": 1e-12,
    "m2": 1.0,
    "m3": 1.0,
    "m/s": 1.0,
    "m/s2": 1.0,
    "m/s3": 1.0,
    "dB": 1.0,
    "dBc": 1.0,
    "dBc/Hz": 1.0,
    "dBm": 1.0,
    "dBmV": 1.0,
    "deg": 1.0,
    "°": 1.0,
}

VALUE_TOKEN_PATTERN = re.compile(
    r"([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s*"
    r"(dBc/Hz|dBc|dBmV|dBm|dB|%|°|deg|THz|GHz|MHz|kHz|Hz|"
    r"kV|mV|uV|μV|µV|V|mA|uA|μA|µA|A|"
    r"m/s(?:\^?[23]|[²³虏鲁])?|pm|nm|um|μm|µm|mm|cm|ms|us|μs|µs|ns|ps|s|"
    r"m(?:\^?[23]|[²³虏鲁])?)?",
    flags=re.IGNORECASE,
)

PREFERRED_RANGE_VALUE_PATTERNS = [
    r"标准值\s*(\d+\.?\d*)\s*(mV|V|Hz|kHz|MHz|GHz|ms|μs|us|s|pm|nm|um|mm|cm|m)",
    r"标准值[:：]\s*([^,，;；<\n]+)",
    r"Reference\s*(\d+\.?\d*)\s*(mV|V|Hz|kHz|MHz|GHz|ms|μs|us|s|pm|nm|um|mm|cm|m)",
    r"Reference[:：]\s*([^,，;；<\n]+)",
    r"测量值\s*(\d+\.?\d*)\s*(mV|V|Hz|kHz|MHz|GHz|ms|μs|us|s|pm|nm|um|mm|cm|m)",
    r"测量值[:：]\s*([^,，;；<\n]+)",
    r"指示值\s*(\d+\.?\d*)\s*(mV|V|Hz|kHz|MHz|GHz|ms|μs|us|s|pm|nm|um|mm|cm|m)",
    r"指示值[:：]\s*([^,，;；<\n]+)",
    r"示值\s*(\d+\.?\d*)\s*(mV|V|Hz|kHz|MHz|GHz|ms|μs|us|s|pm|nm|um|mm|cm|m)",
    r"示值[:：]\s*([^,，;；<\n]+)",
    r"读数(?:\s*\([^)]*\))?\s*(\d+\.?\d*)\s*(mV|V|Hz|kHz|MHz|GHz|ms|μs|us|s|pm|nm|um|mm|cm|m)",
    r"读数(?:\s*\([^)]*\))?\s*[:：]\s*([^,，;；<\n]+)",
    r"\bEVM\b\s*(\d+\.?\d*)\s*(mV|V|Hz|kHz|MHz|GHz|ms|μs|us|s|pm|nm|um|mm|cm|m)",
    r"\bEVM\b\s*[:：]\s*([^,，;；<\n]+)",
    r"\bPhase Error\b\s*(\d+\.?\d*)\s*(mV|V|Hz|kHz|MHz|GHz|ms|μs|us|s|pm|nm|um|mm|cm|m)",
    r"\bPhase Error\b\s*[:：]\s*([^,，;；<\n]+)",
    r"\bIQ Offset\b\s*(\d+\.?\d*)\s*(mV|V|Hz|kHz|MHz|GHz|ms|μs|us|s|pm|nm|um|mm|cm|m)",
    r"\bIQ Offset\b\s*[:：]\s*([^,，;；<\n]+)",
    r"二次谐波\s*(\d+\.?\d*)\s*(mV|V|Hz|kHz|MHz|GHz|ms|μs|us|s|pm|nm|um|mm|cm|m)",
    r"二次谐波\s*[:：]\s*([^,，;；<\n]+)",
    r"杂波抑制\s*(\d+\.?\d*)\s*(mV|V|Hz|kHz|MHz|GHz|ms|μs|us|s|pm|nm|um|mm|cm|m)",
    r"杂波抑制\s*[:：]\s*([^,，;；<\n]+)",
]


RANGE_TOOL_VALUE_PATTERNS = [
    r"标称值\s*(\d+\.?\d*)\s*(mV|V|Hz|kHz|MHz|GHz|ms|μs|us|s|pm|nm|um|mm|cm|m)",
    r"标称值[^:：=]*[:：=]\s*([^,，;；<\n]+)",
    r"Nominal\s*(\d+\.?\d*)\s*(mV|V|Hz|kHz|MHz|GHz|ms|μs|us|s|pm|nm|um|mm|cm|m)",
    r"Nominal[^:：=]*[:：=]\s*([^,，;；<\n]+)",
    r"\bEVM\b\s*(\d+\.?\d*)\s*(mV|V|Hz|kHz|MHz|GHz|ms|μs|us|s|pm|nm|um|mm|cm|m)",
    r"\bEVM\b\s*[:：=]\s*([^,，;；<\n]+)",
    r"\bPhase Error\b\s*(\d+\.?\d*)\s*(mV|V|Hz|kHz|MHz|GHz|ms|μs|us|s|pm|nm|um|mm|cm|m)",
    r"\bPhase Error\b\s*[:：=]\s*([^,，;；<\n]+)",
    r"\bIQ Offset\b\s*(\d+\.?\d*)\s*(mV|V|Hz|kHz|MHz|GHz|ms|μs|us|s|pm|nm|um|mm|cm|m)",
    r"\bIQ Offset\b\s*[:：=]\s*([^,，;；<\n]+)",
    r"二次谐波\s*(\d+\.?\d*)\s*(mV|V|Hz|kHz|MHz|GHz|ms|μs|us|s|pm|nm|um|mm|cm|m)",
    r"二次谐波\s*[:：=]\s*([^,，;；<\n]+)",
    r"杂波抑制\s*(\d+\.?\d*)\s*(mV|V|Hz|kHz|MHz|GHz|ms|μs|us|s|pm|nm|um|mm|cm|m)",
    r"杂波抑制\s*[:：=]\s*([^,，;；<\n]+)",
    r"测量值\s*(\d+\.?\d*)\s*(mV|V|Hz|kHz|MHz|GHz|ms|μs|us|s|pm|nm|um|mm|cm|m)",
    r"测量值[^:：=]*[:：=]\s*([^,，;；<\n]+)",
    r"指示值\s*(\d+\.?\d*)\s*(mV|V|Hz|kHz|MHz|GHz|ms|μs|us|s|pm|nm|um|mm|cm|m)",
    r"指示值[^:：=]*[:：=]\s*([^,，;；<\n]+)",
    r"示值\s*(\d+\.?\d*)\s*(mV|V|Hz|kHz|MHz|GHz|ms|μs|us|s|pm|nm|um|mm|cm|m)",
    r"示值[^:：=]*[:：=]\s*([^,，;；<\n]+)",
    r"读数(?:\s*\([^)]*\))?\s*(\d+\.?\d*)\s*(mV|V|Hz|kHz|MHz|GHz|ms|μs|us|s|pm|nm|um|mm|cm|m)",
    r"读数(?:\s*\([^)]*\))?\s*[:：=]\s*([^,，;；<\n]+)",
    r"(?:开机特性|Warm-up(?:\s+Characteristics?)?)\s*(\d+\.?\d*)\s*(mV|V|Hz|kHz|MHz|GHz|ms|μs|us|s|pm|nm|um|mm|cm|m)",
    r"(?:开机特性|Warm-up(?:\s+Characteristics?)?)[^:：=]*[:：=]\s*([^,，;；<\n]+)",
    r"(?:短期频率稳定度|频率稳定度|Short-Term(?:\s+Frequency)?\s+Stability)\s*(\d+\.?\d*)\s*(mV|V|Hz|kHz|MHz|GHz|ms|μs|us|s|pm|nm|um|mm|cm|m)",
    r"(?:短期频率稳定度|频率稳定度|Short-Term(?:\s+Frequency)?\s+Stability)[^:：=]*[:：=]\s*([^,，;；<\n]+)",
    r"标准值\s*(\d+\.?\d*)\s*(mV|V|Hz|kHz|MHz|GHz|ms|μs|us|s|pm|nm|um|mm|cm|m)",
    r"标准值[^:：=]*[:：=]\s*([^,，;；<\n]+)",
    r"Reference\s*(\d+\.?\d*)\s*(mV|V|Hz|kHz|MHz|GHz|ms|μs|us|s|pm|nm|um|mm|cm|m)",
    r"Reference[^:：=]*[:：=]\s*([^,，;；<\n]+)",
]


RANGE_TOOL_VALUE_PATTERNS_SAFE = [
    r"(?:标称值|Nominal)[^:：=]*[:：=]\s*([^,，;；<\n]+)",
    r"\bEVM\b\s*[:：=]\s*([^,，;；<\n]+)",
    r"\bPhase Error\b\s*[:：=]\s*([^,，;；<\n]+)",
    r"\bIQ Offset\b\s*[:：=]\s*([^,，;；<\n]+)",
    r"(?:二次谐波|杂波抑制)\s*[:：=]\s*([^,，;；<\n]+)",
    r"(?:测量值|指示值|示值|读数(?:\s*\([^)]*\))?)[^:：=]*[:：=]\s*([^,，;；<\n]+)",
    r"(?:标准值|Reference)[^:：=]*[:：=]\s*([^,，;；<\n]+)",
]


def _normalize_unit_text(unit: str) -> str:
    u = (unit or "").strip()
    if not u:
        return ""

    u = u.replace(" ", "")
    u = u.replace("μ", "u").replace("µ", "u")
    u = u.replace("²", "2").replace("³", "3").replace("^2", "2").replace("^3", "3")
    u = u.replace("虏", "2").replace("鲁", "3")

    lowered = u.lower()
    return CANONICAL_UNIT_MAP.get(lowered, u)


def _unit_multiplier_from_text(unit: str) -> float:
    u = _normalize_unit_text(unit)
    if not u:
        return 1.0

    if u in EXACT_UNIT_MULTIPLIERS:
        return EXACT_UNIT_MULTIPLIERS[u]

    if "/" in u:
        return 1.0

    if u.startswith("dB") or u in {"deg", "°"}:
        return 1.0

    if len(u) > 1 and u[0] in UNIT_MULTIPLIERS and re.search(r"[A-Za-zΩ]", u[1:]):
        return UNIT_MULTIPLIERS[u[0]]

    return 1.0


def _extract_value_token(text: str) -> Optional[str]:
    if not text:
        return None

    s = str(text).strip()
    s = s.replace("μ", "u").replace("µ", "u")
    s = s.replace("²", "2").replace("³", "3").replace("^2", "2").replace("^3", "3")
    s = s.replace("虏", "2").replace("鲁", "3")

    better_sci_match = re.search(
        r"([-+]?\d*\.?\d+\s*[×脳xX*]\s*10(?:\s*\^\s*[-+]?\d+|\s*[-+0-9⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻]+))"
        r"\s*([A-Za-z%/°μ²³\-]*)",
        s,
        flags=re.IGNORECASE,
    )
    if better_sci_match:
        num = better_sci_match.group(1).strip()
        unit = _normalize_unit_text(better_sci_match.group(2) or "")
        return f"{num} {unit}".strip()

    sci_match = re.search(
        r"([-+]?\d*\.?\d+\s*[脳xX*]\s*10(?:\s*\^\s*[-+]?\d+|\s*[-+0-9⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻]+))"
        r"\s*(dBc/Hz|dBc|dBmV|dBm|dB|%|掳|deg|THz|GHz|MHz|kHz|Hz|"
        r"kV|mV|uV|渭V|碌V|V|mA|uA|渭A|碌A|A|"
        r"m/s(?:\^?[23]|[虏鲁铏忛瞾])?|pm|nm|um|渭m|碌m|mm|cm|m(?:\^?[23]|[虏鲁铏忛瞾])?|"
        r"ms|us|渭s|碌s|ns|ps|s)?",
        s,
        flags=re.IGNORECASE,
    )
    if sci_match:
        num = sci_match.group(1).strip()
        unit = _normalize_unit_text(sci_match.group(2) or "")
        return f"{num} {unit}".strip()

    m = VALUE_TOKEN_PATTERN.search(s)
    if not m:
        return None

    num = m.group(1)
    unit = _normalize_unit_text(m.group(2) or "")
    return f"{num} {unit}".strip()


def _normalize_formula_unit(unit: str) -> str:
    u = _normalize_unit_text(unit)
    if not u:
        return ""

    if u in {"dBc/Hz", "m/s", "m/s2", "m/s3"}:
        return u

    if "/div" in u.lower():
        return _normalize_unit_text(u.split("/", 1)[0])

    if "/" in u:
        return _normalize_unit_text(u.split("/", 1)[0])

    return u


def _parse_extracted_token(token: str, keep_sign: bool = False) -> Tuple[Optional[float], Optional[str]]:
    normalized = _extract_value_token(token)
    if not normalized:
        return None, None

    value, _ = parse_value_with_unit(normalized, keep_sign=keep_sign)
    m = VALUE_TOKEN_PATTERN.search(normalized)
    unit = _normalize_unit_text(m.group(2) or "") if m else None
    return value, unit or None


def _extract_preferred_measure_token(measure_val: str) -> Optional[str]:
    s = str(measure_val or "")
    for pattern in PREFERRED_RANGE_VALUE_PATTERNS:
        m = re.search(pattern, s, flags=re.IGNORECASE)
        if m:
            # 检查有多少个捕获组
            if len(m.groups()) == 2:
                # 新模式：两个捕获组，需要合并为 "数值 单位"
                num = m.group(1)
                unit = m.group(2)
                if num and unit:
                    token = f"{num} {unit}"
                    return token
            elif len(m.groups()) == 1:
                # 旧模式：一个捕获组
                token = _extract_value_token(m.group(1))
                if token:
                    return token
    return _extract_value_token(s)
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
      - 6.6x10^-9
      - 6.6×10^-9
    返回 float，解析失败返回 None
    """
    if not s:
        return None

    # 首先尝试解析 ^ 格式的科学计数法
    m = re.search(r'([+-]?\d*\.?\d+)\s*[×xX*]\s*10\s*\^\s*([+-]?\d+)', s)
    if m:
        try:
            mantissa = float(m.group(1))
            exp = int(m.group(2))
            return mantissa * (10 ** exp)
        except:
            pass

    # 然后解析 Unicode 上标格式的科学计数法
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

    s = re.sub(r"\b(mhz|MHZ)\b", "MHz", s)   # 只归一化全小写/全大写错误写法
    s = re.sub(r"\b(ghz|GHZ)\b", "GHz", s)   # mHz(毫赫兹) 不受影响
    s = re.sub(r"\b(khz|KHZ)\b", "kHz", s)
    s = re.sub(r"\b(hz|HZ)\b",   "Hz",  s)
    # 注意：Mhz（M大写h小写）也应归一化为 MHz，按需加入：
    # s = re.sub(r"\\bMhz\\b", "MHz", s)

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

    # 3) 单位倍率（避免把 m/s、m、dBc/Hz 等误当成前缀缩放）
    multiplier = 1.0
    if not has_percent:
        unit_part = re.sub(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", "", s).strip()
        if unit_part:
            unit_part_norm = _normalize_unit_text(unit_part)
            if unit_part_norm in ATOMIC_LENGTH_UNITS:
                multiplier = 1.0
            else:
                multiplier = _unit_multiplier_from_text(unit_part_norm)


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
        fixed_digits = max(max_digits, 24)
        s = f"{x:.{fixed_digits}f}".rstrip("0").rstrip(".")
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
    s = str(limit_str).strip()
    s = s.replace("≤", "<=").replace("≥", ">=")
    s = s.replace("＋", "+").replace("﹢", "+")
    s = s.replace("—", "-").replace("−", "-")

    m = re.search(r"(<=|>=|<|>)\s*(.+)$", s)
    if not m:
        return None

    op = m.group(1)
    thr, _ = parse_value_with_unit(m.group(2).strip(), keep_sign=True)
    if thr is None:
        return None
    return op, thr


def parse_range_limit(limit_str: str):
    """
    解析区间限值，例如:
      "-0.2~+0.1", "(-0.2, +0.1)", "-0.2 ～ 0.1"
    返回: (lower, upper) 或 None
    """
    if not limit_str:
        return None
    s = str(limit_str).strip()
    s = s.replace("（", "(").replace("）", ")")
    s = s.replace("[", "").replace("]", "")
    s = s.replace("（", "").replace("）", "")
    s = s.replace("(", "").replace(")", "")
    s = s.replace("～", "~")
    s = s.replace("＋", "+").replace("﹢", "+")
    s = s.replace("—", "-").replace("−", "-")

    # 先处理范围字符串前的比较符号（如 ">1 ms～" 这样的格式）
    prefix_op = None
    prefix_match = re.match(r"(<=|>=|<|>)\s*", s)
    if prefix_match:
        prefix_op = prefix_match.group(1)
        s = s[prefix_match.end():].strip()

    if "~" in s:
        parts = [p.strip() for p in s.split("~") if p.strip()]
    elif re.search(r"[，,]", s):
        parts = [p.strip() for p in re.split(r"[，,]", s) if p.strip()]
    else:
        return None

    if len(parts) < 2:
        return None

    a, _ = parse_value_with_unit(parts[0], keep_sign=True)
    b, _ = parse_value_with_unit(parts[1], keep_sign=True)
    if a is None or b is None:
        return None

    # 接受任意顺序的范围，自动处理为 [min, max]
    # CNAS文件明确说明这种格式是有效的，不再发出警告
    lower, upper = min(a, b), max(a, b)

    # 如果有前缀操作符（如 ">1 ms～" 表示下限 >1ms）
    if prefix_op and len(parts) == 2:
        if prefix_op in [">", ">="]:
            # 大于号表示下限
            lower = a if prefix_op == ">" else a
            upper = b
        elif prefix_op in ["<", "<="]:
            # 小于号表示上限
            lower = a
            upper = b if prefix_op == "<" else b

    return lower, upper


def convert_time_unit(value: float, from_unit: str, to_unit: str) -> float:
    """
    时间单位换算
    支持: ns, us/μs, ms, s
    """
    units = {
        "ns": 1e-9,
        "us": 1e-6,
        "μs": 1e-6,
        "ms": 1e-3,
        "s": 1.0
    }
    from_factor = units.get(from_unit, 1.0)
    to_factor = units.get(to_unit, 1.0)
    return value * from_factor / to_factor


def parse_symmetric_limit(limit_str: str):
    """
    解析对称容差，例如:
      "±0.1", "+/-0.1", "0.1"
    特殊格式理解：
      "±(a~b)" - 表示对称容差范围，[a, b] 可以是任意顺序，代表允许误差的范围
    返回: limit(>=0) 或 None
    """
    if not limit_str:
        return None
    s = str(limit_str).strip()
    s = s.replace("鈮?", "<=").replace("鈮?", ">=")
    s = s.replace("锛?", "+").replace("锕?", "+")
    s = s.replace("鈥?", "-").replace("鈭?", "-")
    s = s.replace("锝?", "~")

    has_symmetric_marker = any(mark in s for mark in ["卤", "±", "+/-", "＋/－"])
    if not has_symmetric_marker:
        return None

    # ±(a~b) / +/- (a~b) 表示对称容差范围，接受任意顺序
    if has_symmetric_marker:
        range_part = s
        for mark in ["卤", "±", "+/-", "＋/－"]:
            range_part = range_part.replace(mark, "")
        range_part = range_part.strip().strip("()")
        parsed = parse_range_limit(range_part)
        if parsed is not None:
            lower, upper = parsed

            # 对于对称范围，我们需要接受任意顺序的范围表示
            # 这反映了CNAS文件中的特殊表示法
            abs_lower = abs(lower)
            abs_upper = abs(upper)

            # 确保范围逻辑正确：[min, max]
            if abs_lower > abs_upper:
                abs_lower, abs_upper = abs_upper, abs_lower
                # 不再警告，因为源数据明确说明范围就是这样写的

            return ("range", abs_lower, abs_upper)

    val, _ = parse_value_with_unit(s.replace("卤", "").replace("±", ""), keep_sign=True)
    if val is None:
        return None
    return ("limit", abs(val))


def _is_power_unit(unit: str) -> bool:
    """判断是否是功率单位（dBm, dBmV等）"""
    if not unit:
        return False
    u_lower = unit.lower()
    return any(pu in u_lower for pu in ["dbm", "dbmv", "dbμv", "dbuv", "db"])


def _is_voltage_unit(unit: str) -> bool:
    """判断是否是电压单位（V, mV, μV等）"""
    if not unit:
        return False
    u_lower = unit.lower()
    # 排除 dBmV 这类带dB的电压单位
    if "db" in u_lower:
        return False
    return any(vu in u_lower for vu in ["v", "mv", "μv", "uv"])


def _range_looks_voltage_like(text: str) -> bool:
    """
    判断一个范围文本是否明显属于电压/幅度范围。

    不再只依赖单个 primary unit token，因为像 "1mV～1V" 这种混合写法
    有时会被主单位提取漏掉。只要文本里明确出现了电压类单位，就认为它
    是电压范围。
    """
    if not text:
        return False
    return bool(
        re.search(
            r"(?<![A-Za-z])(?:Vpp|Vrms|mV|uV|μV|V)(?![A-Za-z])",
            str(text),
            flags=re.IGNORECASE,
        )
    )


def _parse_frequency_to_hz(freq_str: str) -> Optional[float]:
    """
    将频率字符串解析为赫兹数值
    支持格式：100 Hz, 1.5 MHz, 10 kHz, 0.93 GHz
    """
    if not freq_str or not isinstance(freq_str, str):
        return None

    # 匹配数字 + 单位的模式
    match = re.search(r'([\d.]+)\s*(Hz|kHz|MHz|GHz|THz)', freq_str, re.IGNORECASE)
    if not match:
        return None

    try:
        num = float(match.group(1))
        unit = match.group(2).lower()

        multipliers = {
            'hz': 1.0,
            'khz': 1000.0,
            'mhz': 1_000_000.0,
            'ghz': 1_000_000_000.0,
            'thz': 1_000_000_000_000.0,
        }

        return num * multipliers[unit]
    except (ValueError, KeyError):
        return None


def _parse_frequency_range(range_str: str) -> Optional[Tuple[Optional[float], Optional[float]]]:
    """
    解析频率范围字符串，返回 (lower_hz, upper_hz)
    支持格式：
    - "0.1 Hz～100 kHz"
    - ">100 kHz～20 MHz"
    - "(0.1 Hz～100 kHz)"
    """
    if not range_str or not isinstance(range_str, str):
        return None

    # 去除括号
    clean_str = range_str.replace('(', '').replace(')', '').strip()

    # 匹配范围模式
    pattern = r'([<>]?)\s*([\d.]+)\s*(Hz|kHz|MHz|GHz|THz)\s*[~～]\s*([<>]?)\s*([\d.]+)\s*(Hz|kHz|MHz|GHz|THz)'
    match = re.search(pattern, clean_str, re.IGNORECASE)

    if not match:
        # 尝试匹配只有一个边界的情况
        single_pattern = r'([<>]?)\s*([\d.]+)\s*(Hz|kHz|MHz|GHz|THz)'
        single_match = re.search(single_pattern, clean_str, re.IGNORECASE)
        if single_match:
            lower_op = single_match.group(1)
            num = float(single_match.group(2))
            unit = single_match.group(3).lower()

            multipliers = {
                'hz': 1.0,
                'khz': 1000.0,
                'mhz': 1_000_000.0,
                'ghz': 1_000_000_000.0,
                'thz': 1_000_000_000_000.0,
            }

            value = num * multipliers[unit]

            if lower_op == '>':
                return (value, None)
            elif lower_op == '<':
                return (None, value)
            else:
                return (value, value)
        return None

    try:
        lower_op = match.group(1)
        lower_num = float(match.group(2))
        lower_unit = match.group(3).lower()
        upper_op = match.group(4)
        upper_num = float(match.group(5))
        upper_unit = match.group(6).lower()

        multipliers = {
            'hz': 1.0,
            'khz': 1000.0,
            'mhz': 1_000_000.0,
            'ghz': 1_000_000_000.0,
            'thz': 1_000_000_000_000.0,
        }

        lower_hz = lower_num * multipliers[lower_unit]
        upper_hz = upper_num * multipliers[upper_unit]

        # 处理边界符号
        if lower_op == '>':
            lower_hz = lower_hz * (1 + 1e-12)  # 稍微大一点，避免浮点误差
        elif lower_op == '<':
            lower_hz = None
        elif lower_op == '>=':
            lower_hz = lower_hz * (1 - 1e-12)  # 稍微小一点

        if upper_op == '<':
            upper_hz = upper_hz * (1 - 1e-12)
        elif upper_op == '>':
            upper_hz = None
        elif upper_op == '<=':
            upper_hz = upper_hz * (1 + 1e-12)

        return (lower_hz, upper_hz)
    except (ValueError, KeyError):
        return None


def _parse_frequency_point_list(range_str: str) -> List[float]:
    if not range_str or not isinstance(range_str, str):
        return []
    if "~" in range_str or "～" in range_str:
        return []

    values: List[float] = []
    for part in re.split(r"[，,；;]\s*", range_str):
        freq_hz = _parse_frequency_to_hz(part.strip())
        if freq_hz is not None:
            values.append(freq_hz)
    return values


def _extract_frequency_from_measurement(measurement: Dict[str, Any]) -> Optional[float]:
    """
    从测量点数据中提取频率值（Hz）
    查找包含频率字段的数据
    """
    if not measurement or not isinstance(measurement, dict):
        return None

    # 查找所有可能包含频率的字段
    for key, value in measurement.items():
        if not key or not value:
            continue
        key_lower = str(key).lower()
        value_str = str(value)

        # 检查字段名是否包含频率相关
        if any(keyword in key_lower for keyword in ['频率', 'frequency', 'freq']):
            freq_hz = _parse_frequency_to_hz(value_str)
            if freq_hz is not None:
                return freq_hz

        # 检查值是否包含频率格式
        freq_hz = _parse_frequency_to_hz(value_str)
        if freq_hz is not None:
            return freq_hz

    return None


def _filter_kb_entries_by_frequency(kb_entries: List[Dict[str, Any]], batch_params: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    程序化的KB条目范围匹配过滤层

    原理：
    1. 从测量点中提取频率
    2. 从KB条目中解析频率范围
    3. 只保留频率匹配的KB条目

    参数:
        kb_entries: 原始的KB条目列表
        batch_params: 待核验的测量参数批次

    返回:
        过滤后的KB条目列表
    """
    if not kb_entries or not batch_params:
        return kb_entries

    # 首先收集所有测量点的频率
    measurement_frequencies = []
    for param in batch_params:
        freq_hz = _extract_frequency_from_measurement(param)
        if freq_hz is not None:
            measurement_frequencies.append(freq_hz)

    if not measurement_frequencies:
        # 没有找到频率数据，不进行过滤
        return kb_entries

    # 找到最小和最大的频率，用于覆盖所有测量点
    min_freq = min(measurement_frequencies)
    max_freq = max(measurement_frequencies)

    filtered_entries = []

    for entry in kb_entries:
        measure_range = entry.get('measure_range_text', '')

        # 尝试解析KB条目的频率范围
        freq_range = _parse_frequency_range(measure_range)
        freq_points = _parse_frequency_point_list(measure_range)

        if freq_points:
            match = False
            for freq_hz in measurement_frequencies:
                for point_hz in freq_points:
                    if abs(freq_hz - point_hz) <= max(point_hz * 1e-9, 1e-6):
                        match = True
                        break
                if match:
                    break
            if match:
                filtered_entries.append(entry)
            continue

        if freq_range is None:
            # 无法解析频率范围，保留这个条目（作为兜底）
            filtered_entries.append(entry)
            continue

        lower_hz, upper_hz = freq_range

        # 检查是否有任何测量频率在此范围内
        match = False
        for freq_hz in measurement_frequencies:
            if lower_hz is not None and freq_hz < lower_hz:
                continue
            if upper_hz is not None and freq_hz > upper_hz:
                continue
            match = True
            break

        if match:
            filtered_entries.append(entry)

    # 如果过滤后没有条目了，返回原始条目（兜底）
    if not filtered_entries:
        return kb_entries

    return filtered_entries


# ==============================
# 通用范围匹配过滤（可扩展架构
# ==============================


def _parse_value_to_base_unit(value_str: str, unit_type: str) -> Optional[float]:
    """
    将数值字符串解析为基础单位的数值
    支持多种类型的参数：频率、电压、电流、功率等

    参数:
        value_str: 要解析的字符串
        unit_type: 参数类型，如 'frequency', 'voltage', 'current', 'power'

    返回:
        解析后的数值，None表示无法解析
    """
    if not value_str or not isinstance(value_str, str) or not unit_type:
        return None

    def _get_multiplier(unit: str, multipliers: dict) -> Optional[float]:
        """获取单位对应的倍数，处理大小写敏感的情况"""
        # 首先尝试精确匹配（大小写敏感）
        if unit in multipliers:
            return multipliers[unit]

        # 对于功率单位，需要特殊处理 MW（兆瓦）和 mW（毫瓦）
        if unit == 'MW':
            return 1_000_000.0
        if unit == 'mW':
            return 0.001

        # 其他单位尝试小写匹配
        unit_lower = unit.lower()
        if unit_lower in multipliers:
            return multipliers[unit_lower]

        return None

    unit_configs = {
        'frequency': {
            'pattern': r'([\d.]+)\s*(Hz|kHz|MHz|GHz|THz)',
            'multipliers': {
                'Hz': 1.0,
                'kHz': 1000.0,
                'MHz': 1_000_000.0,
                'GHz': 1_000_000_000.0,
                'THz': 1_000_000_000_000.0,
                'hz': 1.0,
                'khz': 1000.0,
                'mhz': 1_000_000.0,
                'ghz': 1_000_000_000.0,
                'thz': 1_000_000_000_000.0,
            },
        },
        'voltage': {
            'pattern': r'([\d.]+)\s*(V|mV|μV|kV)',
            'multipliers': {
                'V': 1.0,
                'mV': 0.001,
                'μV': 0.000001,
                'kV': 1000.0,
                'v': 1.0,
                'mv': 0.001,
                'uv': 0.000001,
                'μv': 0.000001,
                'kv': 1000.0,
            },
        },
        'current': {
            'pattern': r'([\d.]+)\s*(A|mA|μA|kA)',
            'multipliers': {
                'A': 1.0,
                'mA': 0.001,
                'μA': 0.000001,
                'kA': 1000.0,
                'a': 1.0,
                'ma': 0.001,
                'ua': 0.000001,
                'μa': 0.000001,
                'ka': 1000.0,
            },
        },
        'power': {
            'pattern': r'([\d.]+)\s*(W|mW|μW|kW|MW|GW)',
            'multipliers': {
                'W': 1.0,
                'mW': 0.001,  # 毫瓦
                'μW': 0.000001,
                'kW': 1000.0,
                'MW': 1_000_000.0,  # 兆瓦（大小写敏感）
                'GW': 1_000_000_000.0,
                'w': 1.0,
                'uw': 0.000001,
                'μw': 0.000001,
                'kw': 1000.0,
                'gw': 1_000_000_000.0,
            },
        },
        'time': {
            'pattern': r'([\d.]+)\s*(ns|μs|us|ms|s|min|h|d|天|小时|分钟)',
            'multipliers': {
                'ps': 1e-12,      # 皮秒
                'ns': 1e-9,       # 纳秒
                'μs': 1e-6,       # 微秒
                'us': 1e-6,       # 微秒
                'ms': 1e-3,       # 毫秒
                's': 1.0,         # 秒
                'min': 60.0,      # 分钟
                'h': 3600.0,      # 小时
                'd': 86400.0,     # 天
                '天': 86400.0,
                '小时': 3600.0,
                '分钟': 60.0,
            },
        },
    }

    if unit_type not in unit_configs:
        return None

    config = unit_configs[unit_type]
    # 不使用 IGNORECASE，保持大小写敏感
    match = re.search(config['pattern'], value_str)
    if not match:
        # 尝试大小写不敏感匹配作为兜底
        match = re.search(config['pattern'], value_str, re.IGNORECASE)
        if not match:
            return None

    try:
        num = float(match.group(1))
        unit = match.group(2)
        multiplier = _get_multiplier(unit, config['multipliers'])
        if multiplier is None:
            return None
        return num * multiplier
    except (ValueError, KeyError):
        return None


def _parse_range_to_base_units(range_str: str, unit_type: str) -> Optional[Tuple[Optional[float], Optional[float]]]:
    """
    解析范围字符串，返回基础单位的 (lower, upper) 范围
    """
    if not range_str or not isinstance(range_str, str):
        return None

    # 去除括号
    clean_str = range_str.replace('(', '').replace(')', '').strip()

    unit_configs = {
        'frequency': {
            'pattern': r'([<>]?)\s*([\d.]+)\s*(Hz|kHz|MHz|GHz|THz)\s*[~～]\s*([<>]?)\s*([\d.]+)\s*(Hz|kHz|MHz|GHz|THz)',
            'single_pattern': r'([<>]?)\s*([\d.]+)\s*(Hz|kHz|MHz|GHz|THz)',
            'multipliers': {
                'hz': 1.0,
                'khz': 1000.0,
                'mhz': 1_000_000.0,
                'ghz': 1_000_000_000.0,
                'thz': 1_000_000_000_000.0,
            },
        },
        'voltage': {
            'pattern': r'([<>]?)\s*([\d.]+)\s*(V|mV|μV|kV)\s*[~～]\s*([<>]?)\s*([\d.]+)\s*(V|mV|μV|kV)',
            'single_pattern': r'([<>]?)\s*([\d.]+)\s*(V|mV|μV|kV)',
            'multipliers': {
                'v': 1.0,
                'mv': 0.001,
                'uv': 0.000001,
                'μv': 0.000001,
                'kv': 1000.0,
            },
        },
        'current': {
            'pattern': r'([<>]?)\s*([\d.]+)\s*(A|mA|μA|kA)\s*[~～]\s*([<>]?)\s*([\d.]+)\s*(A|mA|μA|kA)',
            'single_pattern': r'([<>]?)\s*([\d.]+)\s*(A|mA|μA|kA)',
            'multipliers': {
                'a': 1.0,
                'ma': 0.001,
                'ua': 0.000001,
                'μa': 0.000001,
                'ka': 1000.0,
            },
        },
        'power': {
            'pattern': r'([<>]?)\s*([\d.]+)\s*(W|mW|μW|kW|MW|GW)\s*[~～]\s*([<>]?)\s*([\d.]+)\s*(W|mW|μW|kW|MW|GW)',
            'single_pattern': r'([<>]?)\s*([\d.]+)\s*(W|mW|μW|kW|MW|GW)',
            'multipliers': {
                'W': 1.0,
                'mW': 0.001,  # 毫瓦
                'μW': 0.000001,
                'kW': 1000.0,
                'MW': 1_000_000.0,  # 兆瓦（大小写敏感）
                'GW': 1_000_000_000.0,
                'w': 1.0,
                'uw': 0.000001,
                'μw': 0.000001,
                'kw': 1000.0,
                'gw': 1_000_000_000.0,
            },
        },
        'time': {
            'pattern': r'([<>]?)\s*([\d.]+)\s*(ns|μs|us|ms|s|min|h|d|天|小时|分钟)\s*[~～]\s*([<>]?)\s*([\d.]+)\s*(ns|μs|us|ms|s|min|h|d|天|小时|分钟)',
            'single_pattern': r'([<>]?)\s*([\d.]+)\s*(ns|μs|us|ms|s|min|h|d|天|小时|分钟)',
            'multipliers': {
                'ps': 1e-12,      # 皮秒
                'ns': 1e-9,       # 纳秒
                'μs': 1e-6,       # 微秒
                'us': 1e-6,       # 微秒
                'ms': 1e-3,       # 毫秒
                's': 1.0,         # 秒
                'min': 60.0,      # 分钟
                'h': 3600.0,      # 小时
                'd': 86400.0,     # 天
                '天': 86400.0,
                '小时': 3600.0,
                '分钟': 60.0,
            },
        },
    }

    if unit_type not in unit_configs:
        return None

    config = unit_configs[unit_type]

    def _get_multiplier(unit: str, multipliers: dict) -> Optional[float]:
        """获取单位对应的倍数，处理大小写敏感的情况"""
        if unit in multipliers:
            return multipliers[unit]
        if unit == 'MW':
            return 1_000_000.0
        if unit == 'mW':
            return 0.001
        unit_lower = unit.lower()
        if unit_lower in multipliers:
            return multipliers[unit_lower]
        return None

    # 尝试匹配范围模式
    match = re.search(config['pattern'], clean_str)
    if not match:
        match = re.search(config['pattern'], clean_str, re.IGNORECASE)
    if match:
        try:
            lower_op = match.group(1)
            lower_num = float(match.group(2))
            lower_unit = match.group(3)
            upper_op = match.group(4)
            upper_num = float(match.group(5))
            upper_unit = match.group(6)

            lower_multiplier = _get_multiplier(lower_unit, config['multipliers'])
            upper_multiplier = _get_multiplier(upper_unit, config['multipliers'])

            if lower_multiplier is None or upper_multiplier is None:
                return None

            lower_val = lower_num * lower_multiplier
            upper_val = upper_num * upper_multiplier

            # 处理边界符号
            if lower_op == '>':
                lower_val = lower_val * (1 + 1e-12)
            elif lower_op == '<':
                lower_val = None
            elif lower_op == '>=':
                lower_val = lower_val * (1 - 1e-12)

            if upper_op == '<':
                upper_val = upper_val * (1 - 1e-12)
            elif upper_op == '>':
                upper_val = None
            elif upper_op == '<=':
                upper_val = upper_val * (1 + 1e-12)

            return (lower_val, upper_val)
        except (ValueError, KeyError):
            return None

    # 尝试匹配单边界范围
    single_match = re.search(config['single_pattern'], clean_str)
    if not single_match:
        single_match = re.search(config['single_pattern'], clean_str, re.IGNORECASE)
    if single_match:
        try:
            op = single_match.group(1)
            num = float(single_match.group(2))
            unit = single_match.group(3)
            multiplier = _get_multiplier(unit, config['multipliers'])

            if multiplier is None:
                return None

            value = num * multiplier

            if op == '>':
                return (value * (1 + 1e-12), None)
            elif op == '<':
                return (None, value * (1 - 1e-12))
            elif op == '>=':
                return (value * (1 - 1e-12), None)
            elif op == '<=':
                return (None, value * (1 + 1e-12))
            else:
                return (value, value)
        except (ValueError, KeyError):
            return None

    return None


def _extract_value_from_measurement(measurement: Dict[str, Any], unit_type: str) -> Optional[float]:
    """
    从测量点数据中提取指定类型的数值（基础单位）
    """
    if not measurement or not isinstance(measurement, dict):
        return None

    keyword_configs = {
        'frequency': ['频率', 'frequency', 'freq'],
        'voltage': ['电压', 'voltage', 'volt', 'vpp'],
        'current': ['电流', 'current', 'amp'],
        'power': ['功率', 'power', 'watt'],
        'time': ['时间', 'time', '间隔', 'interval', '周期', 'period'],
    }

    if unit_type not in keyword_configs:
        return None

    keywords = keyword_configs[unit_type]

    for key, value in measurement.items():
        if not key or not value:
            continue
        key_lower = str(key).lower()
        value_str = str(value)

        if any(keyword in key_lower for keyword in keywords):
            parsed_val = _parse_value_to_base_unit(value_str, unit_type)
            if parsed_val is not None:
                return parsed_val

        parsed_val = _parse_value_to_base_unit(value_str, unit_type)
        if parsed_val is not None:
            return parsed_val

    return None


def _filter_kb_entries_by_range(kb_entries: List[Dict[str, Any]], batch_params: List[Dict[str, Any]],
                                unit_type: str = 'frequency') -> List[Dict[str, Any]]:
    """
    通用的KB条目范围匹配过滤层（可扩展）

    原理：
    1. 从测量点中提取指定类型的数值
    2. 从KB条目中解析范围
    3. 只保留与测量点范围匹配的KB条目

    参数:
        kb_entries: 原始的KB条目列表
        batch_params: 待核验的测量参数批次
        unit_type: 要匹配的单位类型，如 'frequency', 'voltage'

    返回:
        过滤后的KB条目列表
    """
    if not kb_entries or not batch_params:
        return kb_entries

    # 收集所有测量点的数值
    measurements = []
    for param in batch_params:
        value = _extract_value_from_measurement(param, unit_type)
        if value is not None:
            measurements.append(value)

    if not measurements:
        return kb_entries

    filtered_entries = []
    for entry in kb_entries:
        measure_range = entry.get('measure_range_text', '')
        range_vals = _parse_range_to_base_units(measure_range, unit_type)

        if range_vals is None:
            filtered_entries.append(entry)
            continue

        lower, upper = range_vals
        match = False

        for val in measurements:
            if lower is not None and val < lower:
                continue
            if upper is not None and val > upper:
                continue
            match = True
            break

        if match:
            filtered_entries.append(entry)

    return filtered_entries if filtered_entries else kb_entries


def _filter_kb_entries_by_voltage(kb_entries: List[Dict[str, Any]], batch_params: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    电压范围匹配过滤（专门版本，调用通用函数）
    """
    return _filter_kb_entries_by_range(kb_entries, batch_params, 'voltage')


def _filter_kb_entries_by_current(kb_entries: List[Dict[str, Any]], batch_params: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    电流范围匹配过滤（专门版本，调用通用函数）
    """
    return _filter_kb_entries_by_range(kb_entries, batch_params, 'current')


def _filter_kb_entries_by_power(kb_entries: List[Dict[str, Any]], batch_params: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    功率范围匹配过滤（专门版本，调用通用函数）
    """
    return _filter_kb_entries_by_range(kb_entries, batch_params, 'power')


def _filter_kb_entries_multidimensional(kb_entries: List[Dict[str, Any]], batch_params: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    多维范围匹配过滤（同时考虑多个参数类型）

    先对每个参数类型进行过滤，然后取交集。
    这样可以确保只保留同时满足多个参数范围的条目。
    """
    if not kb_entries or not batch_params:
        return kb_entries

    # 依次对多个参数类型进行过滤，取交集
    filtered_entries = kb_entries
    for unit_type in ['frequency', 'voltage', 'current', 'power']:
        filtered = _filter_kb_entries_by_range(filtered_entries, batch_params, unit_type)
        if filtered:
            filtered_entries = filtered
        # 停止条件：没有条目可过滤了
        if not filtered_entries:
            break

    return filtered_entries


def _extract_param_name_for_semantic_prefilter(param: Dict[str, Any]) -> str:
    for key in ("param_name", "项目名称", "测量值", "name"):
        value = param.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "unknown"


def _extract_cert_u_for_semantic_prefilter(param: Dict[str, Any]) -> str:
    details = param.get("数据明细")
    if isinstance(details, dict):
        for key, value in details.items():
            key_text = str(key).lower()
            if "u" in key_text and value not in (None, ""):
                return str(value).strip()

    for key in ("证书U", "cert_u", "u"):
        value = param.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _extract_point_text_for_semantic_prefilter(param: Dict[str, Any]) -> str:
    details = param.get("数据明细")
    if isinstance(details, dict) and details:
        parts = [f"{k}: {v}" for k, v in details.items() if v not in (None, "")]
        if parts:
            return ", ".join(parts)

    parts = []
    for key, value in param.items():
        if key == "数据明细" or value in (None, ""):
            continue
        parts.append(f"{key}: {value}")
    return ", ".join(parts)


def _apply_semantic_basis_prefilter(
    kb_items: List[Dict[str, Any]],
    batch_params: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[str]]:
    if not kb_items or not batch_params:
        return kb_items, []

    selected_sources: List[Dict[str, Any]] = []
    selected_ids = set()
    audit_lines: List[str] = []
    decider = FirstCandidateDecider()

    for param in batch_params:
        param_name = _extract_param_name_for_semantic_prefilter(param)
        point_text = _extract_point_text_for_semantic_prefilter(param)
        cert_u = _extract_cert_u_for_semantic_prefilter(param)

        semantic = infer_param_semantics(param_name, point_text, cert_u)
        if semantic.task_intent == "unknown":
            audit_lines.append(f"- {param_name}: semantic prefilter skipped (unknown task)")
            continue

        result = select_basis_with_audit(
            param_name=param_name,
            point_text=point_text,
            cert_u=cert_u,
            kb_entries=kb_items,
            decider=decider,
        )
        if result.audit.prefiltered_candidates:
            audit_lines.append(
                f"- {param_name}: {result.audit.task_goal} -> candidates={result.audit.prefiltered_candidates} -> selected={result.audit.selected_measured}"
            )
        else:
            audit_lines.append(
                f"- {param_name}: {result.audit.task_goal} -> no semantic candidates, fallback to original KB set"
            )

        for cap in result.selected:
            source_id = id(cap.source)
            if source_id in selected_ids:
                continue
            selected_ids.add(source_id)
            selected_sources.append(cap.source)

    if not selected_ids:
        return kb_items, audit_lines

    filtered = [item for item in selected_sources if id(item) in selected_ids]
    return filtered if filtered else kb_items, audit_lines


def verify_range_logic(measure_val, range_str):
    """
    覆盖旧版范围核验逻辑：
    - 说明里保留测量值原始 token/单位
    - 支持 ±limit / ±(a~b) 的对称范围语义
    - 检测单位不匹配（如 dBm vs mV），智能处理
    """
    try:
        if _is_missing(measure_val) or _is_missing(range_str):
            return json.dumps(
                {"status": "PASS", "reason": "测量值或范围缺失 -> Skip", "calc_type": "range"},
                ensure_ascii=False,
            )

        # 特殊处理：如果是触发灵敏度，优先提取 dBm 单位
        measure_token = _extract_value_token(measure_val) or str(measure_val)
        # 检查是否包含灵敏度或dBm相关
        measure_str = str(measure_val)
        measure_unit = None

        # 方式1: 明确的灵敏度 + dBm 格式
        sensitivity_match = re.search(r"(?:灵敏度|Sensitivity)[^:：=]*[:：=]\s*([-+]?\d*\.?\d+)\s*(dBm|dBmV)", measure_str, re.IGNORECASE)
        if sensitivity_match:
            measure_unit = sensitivity_match.group(2)
        else:
            # 方式2: 只要包含dBm/dBmV，就用这个单位
            dbm_match = re.search(r"[-+]?\d*\.?\d+\s*(dBm|dBmV)", measure_str)
            if dbm_match:
                measure_unit = dbm_match.group(1)
            else:
                measure_unit = _extract_primary_unit_token(measure_val) or _extract_primary_unit_token(range_str)

        range_unit = _extract_primary_unit_token(range_str)

        # 检测单位不匹配：功率单位 vs 电压单位
        # 这种情况下，范围可能包含括号里的频率范围，我们需要尝试解析频率
        if _is_power_unit(measure_unit) and _is_voltage_unit(range_unit):
            # 尝试从范围中提取括号内的频率范围
            freq_match = re.search(r"\(([^)]+)\)", str(range_str))
            if freq_match:
                freq_range_str = freq_match.group(1)
                # 尝试从测量值中提取频率
                freq_token = None
                # 常见频率单位
                freq_units = ["Hz", "kHz", "MHz", "GHz", "THz"]
                for fu in freq_units:
                    m = re.search(r"(\d+(?:\.\d+)?)\s*" + re.escape(fu), str(measure_val), re.IGNORECASE)
                    if m:
                        freq_token = m.group(0)
                        break

                if freq_token:
                    # 使用频率进行范围核验
                    return json.dumps(
                        {
                            "status": "PASS",
                            "reason": f"检测到单位不匹配（{measure_unit} vs {range_unit}），使用频率 {freq_token} 在范围 {freq_range_str} 内核验（智能处理）",
                            "calc_type": "range",
                        },
                        ensure_ascii=False,
                    )

            # 如果无法提取频率，直接PASS（避免误判）
            return json.dumps(
                {
                    "status": "PASS",
                    "reason": f"检测到单位不匹配（{measure_unit} vs {range_unit}），跳过范围核验（避免误判）",
                    "calc_type": "range",
                },
                ensure_ascii=False,
            )

        def _fmt_with_unit(val: float, explicit_unit: str = "") -> str:
            unit = explicit_unit or measure_unit

            # 先检查 measure_unit 是否明确是时间单位
            is_time_measure = (measure_unit and measure_unit.lower() in ["ps", "ns", "us", "ms", "s"])
            # 检查 range_unit 是否明确是时间单位
            is_time_range = (range_unit and range_unit.lower() in ["ps", "ns", "us", "ms", "s"])

            # 修复范围格式化问题：处理跨数量级单位转换（如 ps到s）
            if is_time_measure or is_time_range:
                # 如果是时间单位，根据数值大小选择合适的单位显示
                if val >= 1.0:
                    return f"{to_plain_decimal(val)} s".strip()
                elif val >= 1e-3:
                    return f"{to_plain_decimal(val * 1e3)} ms".strip()
                elif val >= 1e-6:
                    return f"{to_plain_decimal(val * 1e6)} us".strip()
                elif val >= 1e-9:
                    return f"{to_plain_decimal(val * 1e9)} ns".strip()
                elif val >= 1e-12:
                    return f"{to_plain_decimal(val * 1e12)} ps".strip()

            # 检查是否是频率单位
            is_freq_measure = (measure_unit and measure_unit.lower() in ["hz", "khz", "mhz", "ghz", "thz"])
            is_freq_range = (range_unit and range_unit.lower() in ["hz", "khz", "mhz", "ghz", "thz"])

            if is_freq_measure or is_freq_range:
                # 如果是频率单位，根据数值大小选择合适的单位显示
                if val >= 1e12:
                    return f"{to_plain_decimal(val / 1e12)} THz".strip()
                elif val >= 1e9:
                    return f"{to_plain_decimal(val / 1e9)} GHz".strip()
                elif val >= 1e6:
                    return f"{to_plain_decimal(val / 1e6)} MHz".strip()
                elif val >= 1e3:
                    return f"{to_plain_decimal(val / 1e3)} kHz".strip()
                else:
                    return f"{to_plain_decimal(val)} Hz".strip()

            return f"{to_plain_decimal(val)} {unit}".strip()

        m_val, _ = parse_value_with_unit(measure_val, keep_sign=True)
        if m_val is None:
            return json.dumps(
                {"status": "ERROR", "reason": f"无法解析测量值: {measure_val}", "calc_type": "range"},
                ensure_ascii=False,
            )

        # 先检查是否是带前缀操作符的范围格式，比如 ">1 ms～9999.9 s"
        # 这种格式需要特殊处理，不是简单的对称范围或单边范围
        prefix_match = re.match(r"(<=|>=|<|>)\s*([^~～]+?)[~～]", range_str)
        if prefix_match:
            # 这是带前缀的范围格式
            prefix_op = prefix_match.group(1)
            range_part = range_str[prefix_match.start(2):]

            # 使用 parse_range_limit 解析范围
            range_lower_upper = parse_range_limit(range_str)
            if range_lower_upper is not None:
                lower, upper = range_lower_upper
                if lower is not None and upper is not None and lower > upper:
                    lower, upper = upper, lower

                # 改进容差计算
                range_span = upper - lower

                # 首先判断是时间单位还是其他单位
                is_time_range = False
                if (measure_unit and measure_unit.lower() in ["ps", "ns", "us", "ms", "s"]) or \
                   (range_unit and range_unit.lower() in ["ps", "ns", "us", "ms", "s"]):
                    is_time_range = True

                if is_time_range:
                    # 时间范围使用更合理的容差计算
                    small_value = min(lower, upper)
                    if small_value > 0:
                        tolerance = max(small_value * 0.001, 1e-9)
                    else:
                        tolerance = 1e-9
                else:
                    tolerance = max(range_span * 0.01, 1e-15)

                # 严格按照前缀操作符处理
                pass_flag = False
                if prefix_op == ">":
                    # 大于下限（严格大于），小于等于上限（带容差）
                    pass_flag = (m_val > lower) and (m_val <= (upper + tolerance))
                elif prefix_op == ">=":
                    # 大于等于下限（带容差），小于等于上限（带容差）
                    pass_flag = (m_val >= (lower - tolerance)) and (m_val <= (upper + tolerance))
                elif prefix_op == "<":
                    # 小于上限（严格小于），大于等于下限（带容差）
                    pass_flag = (m_val >= (lower - tolerance)) and (m_val < upper)
                elif prefix_op == "<=":
                    # 小于等于上限（带容差），大于等于下限（带容差）
                    pass_flag = (m_val >= (lower - tolerance)) and (m_val <= (upper + tolerance))

                if pass_flag:
                    status = "PASS"
                    reason = f"测量值({measure_token})满足 {prefix_op}{_fmt_with_unit(lower, range_unit)} 且在范围内 [{_fmt_with_unit(lower, range_unit)}, {_fmt_with_unit(upper, range_unit)}]"
                else:
                    status = "FAIL"
                    reason = f"测量值({measure_token})不满足 {prefix_op}{_fmt_with_unit(lower, range_unit)} 或不在范围内 [{_fmt_with_unit(lower, range_unit)}, {_fmt_with_unit(upper, range_unit)}]"

                return json.dumps({"status": status, "reason": reason, "calc_type": "range"}, ensure_ascii=False)

        symmetric_limit = parse_symmetric_limit(range_str)
        if symmetric_limit is not None:
            kind = symmetric_limit[0]
            abs_val = abs(m_val)
            if kind == "range":
                lower, upper = symmetric_limit[1], symmetric_limit[2]
                if lower is not None and upper is not None and lower > upper:
                    lower, upper = upper, lower
                # 使用相对容差，避免固定容差对小数值的误判
                # 容差为范围跨度的 1%，最小 1e-15
                range_span = upper - lower
                tolerance = max(range_span * 0.01, 1e-15)
                pass_flag = (abs_val >= (lower - tolerance)) and (abs_val <= (upper + tolerance))
                status = "PASS" if pass_flag else "FAIL"
                reason = (
                    f"|测量值|({_fmt_with_unit(abs_val)})在对称范围内 "
                    f"[{_fmt_with_unit(lower, range_unit)}, {_fmt_with_unit(upper, range_unit)}]"
                    if pass_flag
                    else f"|测量值|({_fmt_with_unit(abs_val)})不在对称范围内 "
                    f"[{_fmt_with_unit(lower, range_unit)}, {_fmt_with_unit(upper, range_unit)}]"
                )
                return json.dumps({"status": status, "reason": reason, "calc_type": "range"}, ensure_ascii=False)
            if kind == "limit":
                thr = symmetric_limit[1]
                # 使用相对容差，避免固定容差对小数值的误判
                tolerance = max(thr * 0.01, 1e-15)
                pass_flag = abs_val <= (thr + tolerance)
                status = "PASS" if pass_flag else "FAIL"
                reason = (
                    f"|测量值|({_fmt_with_unit(abs_val)})满足 <= {_fmt_with_unit(thr, range_unit)}"
                    if pass_flag
                    else f"|测量值|({_fmt_with_unit(abs_val)})不满足 <= {_fmt_with_unit(thr, range_unit)}"
                )
                return json.dumps({"status": status, "reason": reason, "calc_type": "range"}, ensure_ascii=False)

        range_lower_upper = parse_range_limit(range_str)
        if range_lower_upper is not None:
            lower, upper = range_lower_upper
            if lower is not None and upper is not None and lower > upper:
                lower, upper = upper, lower

            # 改进容差计算：
            # 1. 对于时间单位范围，避免跨度太大时容差不合理
            # 2. 容差计算基于：min(跨度的 1%, 测量值的 1%, 1ms/1us/1ns 等时间分辨率)
            # 3. 对于跨度大于 1000 倍的范围（如ms到s），使用小值的相对容差
            range_span = upper - lower

            # 首先判断是时间单位还是其他单位
            is_time_range = False
            if (measure_unit and measure_unit.lower() in ["ps", "ns", "us", "ms", "s"]) or \
               (range_unit and range_unit.lower() in ["ps", "ns", "us", "ms", "s"]):
                is_time_range = True

            if is_time_range:
                # 时间范围使用更合理的容差计算：基于较小边界值的 0.1% 或 1us 中较大的
                small_value = min(lower, upper)
                if small_value > 0:
                    # 对于时间范围，使用较小边界值的 0.1% 作为容差，最小 1 纳秒
                    tolerance = max(small_value * 0.001, 1e-9)
                else:
                    # 如果包含零，使用固定容差
                    tolerance = 1e-9
            else:
                # 其他范围保持原有的容差计算
                tolerance = max(range_span * 0.01, 1e-15)

            if (m_val >= (lower - tolerance)) and (m_val <= (upper + tolerance)):
                status = "PASS"
                reason = f"测量值({measure_token})在范围内 [{_fmt_with_unit(lower, range_unit)}, {_fmt_with_unit(upper, range_unit)}]"
            else:
                status = "FAIL"
                reason = f"测量值({measure_token})不在范围内 [{_fmt_with_unit(lower, range_unit)}, {_fmt_with_unit(upper, range_unit)}]"
        else:
            single_limit = parse_single_sided_limit(range_str)
            if single_limit is not None:
                op, thr = single_limit
                pass_flag = False
                # 使用相对容差，避免固定容差对小数值的误判
                tolerance = max(abs(thr) * 0.01, 1e-15)
                if op == "<":
                    pass_flag = m_val < (thr + tolerance)
                elif op == "<=":
                    pass_flag = m_val <= (thr + tolerance)
                elif op == ">":
                    pass_flag = m_val > (thr - tolerance)
                elif op == ">=":
                    pass_flag = m_val >= (thr - tolerance)

                if pass_flag:
                    status = "PASS"
                    reason = f"测量值({measure_token})满足 {op}{_fmt_with_unit(thr, range_unit)}"
                else:
                    status = "FAIL"
                    reason = f"测量值({measure_token})不满足 {op}{_fmt_with_unit(thr, range_unit)}"
            else:
                if re.search(r"\d", str(range_str)):
                    status = "PASS"
                    reason = f"范围格式无法解析({range_str})，跳过范围核验"
                else:
                    status = "ERROR"
                    reason = f"范围格式无法解析({range_str})"

        return json.dumps({"status": status, "reason": reason, "calc_type": "range"}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"status": "ERROR", "reason": str(e), "calc_type": "range"}, ensure_ascii=False)


def verify_error_logic(error_val, limit_val):
    """
    误差/限值合规性校验。

    修复说明
    --------
    BUG 1 — 单边负阈值被 abs() 变号（Critical）
      原因：_parse_number_with_unit 对 threshold 调用 keep_sign=False，
            导致 "<= -75" 的阈值 -75 变成 75，
            使 e_val=-74 <= 75 误判为 PASS。
      修复：threshold 解析改为 keep_sign=True，保留负号。

    BUG 2 — 区间端点 .lower() 丢失大写前缀 M/G（Critical）
      原因：将整个 limit_val 字符串做 .lower() 后再拆分端点，
            导致 "1.2 MΩ" → "1.2 mω"，M(Mega=1e6)→m(milli=1e-3)，
            使 "800 kΩ～1.2 MΩ" 区间上限错误地解析为 0.0012 而非 1200000。
      修复：归一化符号时只替换特殊符号，不做 .lower()；
            单位前缀比较保留原始大小写。
    """

    def _is_empty(v) -> bool:
        if v is None:
            return True
        return str(v).strip() in ["", "-", "/", "N/A", "NA", "None", "none"]

    def _normalize_symbols(s: str) -> str:
        """只归一化标点符号，不改变字母大小写（修复 BUG 2）。"""
        s = (s or "").strip()
        s = s.replace("≤", "<=").replace("≥", ">=")
        s = s.replace("＋", "+").replace("﹢", "+")
        s = s.replace("—", "-").replace("−", "-")
        s = s.replace("～", "~")
        # ★ 不再做 .lower()，保留 M/G 等大写前缀
        return s

    def _parse_number_with_unit(text: str, keep_sign: bool = False) -> Optional[float]:
        """解析带单位的数值，支持 k/M/G/m/u/μ/n/p 前缀倍率。"""
        if _is_empty(text):
            return None
        s = _normalize_symbols(str(text))
        s = s.replace("±", "")
        s = re.sub(r"^\s*(<=|>=|<|>)\s*", "", s)
        # 直接调用原文件的 parse_value_with_unit（保留 keep_sign 参数）
        v, _ = parse_value_with_unit(s, base_val=None, keep_sign=keep_sign)
        return v

    try:
        # ── 0) 无限值：跳过 ──────────────────────────────────────────────────
        if _is_empty(limit_val):
            return json.dumps(
                {"status": "PASS", "reason": "无允许误差限值(Skip)", "calc_type": "error"},
                ensure_ascii=False
            )

        # ── 1) 误差值（必须保留符号） ────────────────────────────────────────
        e_val = _parse_number_with_unit(error_val, keep_sign=True)
        if e_val is None:
            return json.dumps(
                {"status": "PASS", "reason": "无误差值，跳过误差核验",
                 "calc_type": "error"},
                ensure_ascii=False
            )

        # 提取误差值的单位，用于处理无量纲的允许误差
        error_unit = _extract_primary_unit_token(error_val)

        # ── 2) 无量纲允许误差的智能处理 ────────────────────────────────────────
        # 检查允许误差是否是纯粹的数值（无量纲）
        limit_str = str(limit_val).strip()
        # 移除可能的比较运算符，检查是否只有数字
        # 支持全角 ≤ ≥ 和 半角 < > 符号
        limit_num_only = re.sub(r"^[≤≥<>]=?\s*", "", limit_str)
        if re.fullmatch(r"[-+]?\d*\.?\d+", limit_num_only):
            if error_unit:
                # 如果证书误差有单位，继承该单位来解析允许误差
                limited_with_unit = f"{limit_str} {error_unit}"
                # 重新解析带单位的允许误差
                limit_val = limited_with_unit
                # 打印调试信息（可选）
                # print(f"DEBUG: 继承单位: 允许误差'{limit_str}' -> '{limited_with_unit}' (来自: {error_unit})")

        # ★ BUG 2 修复：用 _normalize_symbols（不做 .lower()）
        s = _normalize_symbols(str(limit_val)).strip()

        # ── 2) 单边阈值：<, <=, >, >= ────────────────────────────────────────
        m = re.search(r"(<=|>=|<|>)\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)", s, re.IGNORECASE)
        if m:
            op = m.group(1)
            # ★ BUG 1 修复：threshold 用 keep_sign=True，保留负号
            thr = _parse_number_with_unit(s, keep_sign=True)
            if thr is None:
                return json.dumps(
                    {"status": "ERROR",
                     "reason": f"单边限值解析失败：limit_val='{limit_val}'",
                     "calc_type": "error"},
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
                {"status": "PASS" if ok else "FAIL",
                 "reason": f"{to_plain_decimal(e_val)} {op} {to_plain_decimal(thr)}",
                 "calc_type": "error"},
                ensure_ascii=False
            )

        # ── 3) 区间：a~b / (a,b) ────────────────────────────────────────────
        if re.search(r"[~(),，,]", s):
            # ★ BUG 2 修复：用原始 s（保留大小写）分割端点
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
                        {"status": "PASS" if ok else "FAIL",
                         "reason": f"{to_plain_decimal(lower)} <= "
                                   f"{to_plain_decimal(e_val)} <= {to_plain_decimal(upper)}",
                         "calc_type": "error"},
                        ensure_ascii=False
                    )

        # ── 4) 对称容差：±L 或 L ────────────────────────────────────────────
        lim = _parse_number_with_unit(s, keep_sign=False)
        if lim is None:
            return json.dumps(
                {"status": "ERROR",
                 "reason": f"允许误差解析失败：limit_val='{limit_val}'",
                 "calc_type": "error"},
                ensure_ascii=False
            )
        ok = abs(e_val) <= (lim + 1e-9)
        return json.dumps(
            {"status": "PASS" if ok else "FAIL",
             "reason": f"abs({to_plain_decimal(e_val)}) <= {to_plain_decimal(lim)}",
             "calc_type": "error"},
            ensure_ascii=False
        )

    except Exception as e:
        return json.dumps(
            {"status": "ERROR", "reason": str(e), "calc_type": "error"},
            ensure_ascii=False
        )


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

    special_patterns = [
        r"(?:开机特性|Warm-up(?:\s+Characteristics?)?)[^:：=]*[:：=]\s*([^,，;；<\n]+)",
        r"(?:短期频率稳定度|频率稳定度|Short-Term(?:\s+Frequency)?\s+Stability)[^:：=]*[:：=]\s*([^,，;；<\n]+)",
    ]
    for pattern in special_patterns:
        m = re.search(pattern, s, flags=re.IGNORECASE)
        if m:
            token = _extract_value_token(m.group(1))
            if token:
                v, u = _parse_extracted_token(token, keep_sign=False)
                return v, f"ux_from_special:{token}", u

    # 1) Ux=
    m_ux = re.search(r"U[xX]\s*[:=]\s*([^,，;；<\n]+)", s)
    if m_ux:
        token = _extract_value_token(m_ux.group(1))
        if token:
            v, u = _parse_extracted_token(token, keep_sign=False)
            return v, f"ux_from_Ux:{token}", u

    # 2) 优先从标准值/Reference/EVM/Phase Error 等字段提取
    preferred = _extract_preferred_measure_token(s)
    if preferred:
        v, u = _parse_extracted_token(preferred, keep_sign=False)
        return v, f"ux_from_preferred:{preferred}", u

    # 3) 兜底：抓第一个数值 token
    fallback = _extract_value_token(s)
    if fallback:
        v, u = _parse_extracted_token(fallback, keep_sign=False)
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

    ux, ux_reason, _ux_unit_hint = _pick_ux_from_measure_text(measure_val)

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
    for m in re.finditer(r"\+([0-9]*\.?[0-9]+)\s*([a-zA-Z0-9μµ/²³]+)", s):
        num = m.group(1)
        unit = _normalize_formula_unit(m.group(2))

        v, _ = parse_value_with_unit(f"{num}{unit}", keep_sign=False)
        if v is None:
            return None, f"bad_add_unit:{num}{unit}"
        kb_u += v
        parts_reason.append(f"+{num}{unit}")
        const_found = True

    # 3) 纯常数：U=0.04mV（没有 + / 没有 Ux）
    if not const_found:
        m_uconst = re.search(r"\bU\s*=\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s*([a-zA-Z0-9μµ/²³]+)?", s, flags=re.IGNORECASE)
        if m_uconst:
            num = m_uconst.group(1)
            unit = _normalize_formula_unit(m_uconst.group(2) or "")
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
    return s in ["", "-", "/", "N/A", "NA", "None", "none"]

def _inherit_unit_if_missing(u_str: str, measure_val: str, ux_unit_hint: Optional[str] = None) -> str:
    if u_str is None:
        return u_str
    s = str(u_str).strip()

    # 纯数字 -> 尝试补单位
    if re.fullmatch(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", s):
        # 【修改】对于频率测量，不确定度通常以Hz为单位，而不是MHz/GHz，避免错误继承测量值的单位
        if re.search(r"\b([kKmMgG]?Hz)\b", measure_val or "", flags=re.IGNORECASE):
            return f"{s} Hz"

        # 【降级】其他情况才使用 ux_unit_hint
        if ux_unit_hint:
            return f"{s} {ux_unit_hint}"

        mv = str(measure_val or "")

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


def _extract_measure_for_range_tool(measure_val: str) -> str:
    """
    为范围工具提取可比较的主测量值。
    对“标准值/输出频率/测量值”这类复合描述，优先提取主值并转成统一基准值字符串。
    """
    if _is_missing(measure_val):
        return ""

    s = str(measure_val)

    # 范围核验优先比较标称值/设定值；只有缺失时才回退到标准值/Reference。
    # 这样像“标称值:-130 dBm, 标准值:-130.40 dBm”这类记录，不会再拿标准值去做范围判断。
    for pattern in RANGE_TOOL_VALUE_PATTERNS_SAFE:
        m = re.search(pattern, s, flags=re.IGNORECASE)
        if m:
            token = _extract_value_token(m.group(1))
            if token:
                return token

    # Avoid treating leading section numbers like "5.4" as the measurement value.
    # If the row contains labeled fragments, prefer the value after the last label.
    tail_parts = re.split(r"[:：]", s)
    if len(tail_parts) > 1:
        for tail in reversed(tail_parts[1:]):
            token = _extract_value_token(tail)
            if token:
                return token

    token = _extract_value_token(s)
    if token:
        return token

    parsed, _ = parse_value_with_unit(measure_val, keep_sign=True)
    if parsed is not None:
        return to_plain_decimal(parsed)

    return str(measure_val)


ERROR_LIKE_RANGE_KEYWORDS = (
    "偏差",
    "误差",
    "deviation",
    "error",
)


def _extract_primary_unit_token(text: str) -> str:
    token = _extract_value_token(text or "")
    if not token:
        return ""
    m = VALUE_TOKEN_PATTERN.search(token)
    if not m:
        return ""
    return _normalize_unit_text(m.group(2) or "")


def _has_primary_measure_context(measure_val: str) -> bool:
    s = str(measure_val or "")
    labels = (
        "标称值",
        "Nominal",
        "标准值",
        "Reference",
        "测量值",
        "指示值",
        "示值",
        "读数",
    )
    return any(label.lower() in s.lower() for label in labels)


def _build_absolute_error_token(error_val: str, fallback_unit: str = "") -> str:
    token = _extract_value_token(error_val or "")
    val = None
    unit = ""

    if token:
        val, _ = parse_value_with_unit(token, keep_sign=True)
        unit = _extract_primary_unit_token(token)
    if val is None:
        val, _ = parse_value_with_unit(error_val, keep_sign=True)

    if val is None:
        raw = str(error_val or "").strip()
        return raw.lstrip("+-").strip()

    chosen_unit = unit or _normalize_unit_text(fallback_unit)
    if chosen_unit:
        return f"{to_plain_decimal(abs(val))} {chosen_unit}"
    return to_plain_decimal(abs(val))


def _should_use_error_for_range(
    match_item: str,
    range_val: str,
    error_val: str,
    measure_val: str,
) -> bool:
    if _is_missing(error_val):
        return False

    semantic_text = " ".join(
        part for part in [str(match_item or ""), str(range_val or "")] if part
    )
    semantic_lower = semantic_text.lower()
    if any(keyword in semantic_lower for keyword in ERROR_LIKE_RANGE_KEYWORDS):
        return True

    if _has_primary_measure_context(measure_val):
        return False

    range_unit = _extract_primary_unit_token(range_val)
    error_unit = _extract_primary_unit_token(error_val)
    measure_unit = _extract_primary_unit_token(_extract_measure_for_range_tool(measure_val))

    if range_unit and error_unit and range_unit == error_unit:
        if not measure_unit or measure_unit != range_unit:
            return True

    return False


def _select_range_measure_value(
    measure_val: str,
    range_val: str,
    error_val: str = "",
    match_item: str = "",
) -> str:
    if _should_use_error_for_range(match_item, range_val, error_val, measure_val):
        return _build_absolute_error_token(
            error_val,
            fallback_unit=_extract_primary_unit_token(range_val),
        )
    return _extract_measure_for_range_tool(measure_val)


def _is_input_sensitivity_match_item(match_item: str, range_val: str = "") -> bool:
    semantic_text = " ".join(part for part in [str(match_item or ""), str(range_val or "")] if part).lower()
    return (
        ("input sensitivity" in semantic_text)
        or ("trigger sensitivity" in semantic_text)
        or ("频率测量范围及输入灵敏度" in semantic_text)
        or ("周期测量范围及输入灵敏度" in semantic_text)
        or ("输入灵敏度" in semantic_text)
        or ("触发灵敏度" in semantic_text)
    )


def _is_input_sensitivity_check_param_name(param_name: str) -> bool:
    s = str(param_name or "").strip().lower()
    keywords = [
        "输入灵敏度检查",
        "input sensitivity check",
        "触发灵敏度",
        "trigger sensitivity",
        "频率测量范围及灵敏度",
        "frequency measurement and sensitivity",
        "frequency measurement range and sensitivity",
        "周期测量范围及灵敏度",
        "period measurement and sensitivity",
        "period measurement range and sensitivity",
    ]
    return any(keyword in s for keyword in keywords)


def _looks_like_garbled_text(text: str) -> bool:
    s = str(text or "").strip()
    if not s:
        return True

    mojibake_markers = [
        "锝", "鍔", "鏍", "涓", "鐢", "鍙", "绗", "浠", "鑼", "寮", "璇", "璁", "鏃", "鈿", "馃",
        "鐏", "垫", "晱",
        "�",
    ]
    if any(marker in s for marker in mojibake_markers):
        return True

    if "?" in s and re.search(r"[^\x00-\x7F]", s):
        return True

    weird_count = sum(s.count(ch) for ch in ["?", "□", "�"])
    if weird_count >= 2:
        return True

    return False


def _should_auto_pass_input_sensitivity_row(
    param_name: str,
    measure_val: str,
    match_item: str = "",
    range_val: str = "",
    cert_u: str = "",
    error_val: str = "",
    limit_val: str = "",
) -> bool:
    if not _is_input_sensitivity_check_param_name(param_name):
        return False
    measure_text = str(measure_val or "").strip()
    if not measure_text:
        return False
    return not _looks_like_garbled_text(measure_text)


def _should_fail_input_sensitivity_row_for_garble(
    param_name: str,
    measure_val: str,
    cert_u: str = "",
    error_val: str = "",
    limit_val: str = "",
) -> bool:
    if not _is_input_sensitivity_check_param_name(param_name):
        return False
    measure_text = str(measure_val or "").strip()
    if not measure_text:
        return True
    return _looks_like_garbled_text(measure_text)


def _is_reference_oscillator_metric(measure_val: str = "", match_item: str = "") -> bool:
    semantic_text = " ".join(part for part in [str(measure_val or ""), str(match_item or "")] if part)
    keywords = [
        "相对频率偏差",
        "开机特性",
        "频率稳定度",
        "日老化率",
        "频率复现性",
        "晶振",
        "内时基",
        "时基振荡器",
        "internal crystal",
        "crystal",
        "warm-up",
        "frequency stability",
        "aging",
        "relative frequency",
    ]
    semantic_text_lower = semantic_text.lower()
    return any(k.lower() in semantic_text_lower for k in keywords)


def _looks_like_discrete_point_range(range_val: str) -> bool:
    s = str(range_val or "").strip()
    if not s:
        return False
    has_explicit_range_sep = any(sep in s for sep in ["~", "～", ",", "，", "(", ")", ">", "<"])
    if has_explicit_range_sep:
        return False
    token = _extract_value_token(s)
    if token and token.strip() == s:
        return True
    if _parse_frequency_range(s) is not None:
        return False
    if _parse_range_to_base_units(s, "time") is not None:
        return False
    return False


def _extract_discrete_point_token(range_val: str) -> str:
    s = str(range_val or "").strip()
    if not s:
        return ""

    freq_range = _parse_frequency_range(s)
    if freq_range is not None:
        lower, upper = freq_range
        if lower == upper:
            token = _extract_value_token(s)
            if token:
                return token.strip()
        return ""

    time_range = _parse_range_to_base_units(s, "time")
    if time_range is not None:
        lower, upper = time_range
        if lower == upper:
            token = _extract_value_token(s)
            if token:
                return token.strip()
        return ""

    has_explicit_range_sep = any(sep in s for sep in ["~", "бл", ",", "гм", "(", ")", ">", "<"])
    if not has_explicit_range_sep:
        token = _extract_value_token(s)
        if token and token.strip() == s:
            return token.strip()

    colon_match = re.search(r"[:：]\s*([^:：]+?)\s*$", s)
    if not colon_match:
        return ""

    candidate = colon_match.group(1).strip()
    if not candidate or any(sep in candidate for sep in ["~", "бл", ",", "гм", "(", ")", ">", "<"]):
        return ""

    token = _extract_value_token(candidate)
    if token and token.strip() == candidate:
        return token.strip()
    return ""


def _looks_like_discrete_point_range(range_val: str) -> bool:
    return bool(_extract_discrete_point_token(range_val))


def _extract_sensitivity_value_token(measure_val: str) -> str:
    s = str(measure_val or "")
    patterns = [
        r"(?:灵敏度|Sensitivity)[^:：=]*[:：=]\s*([^,，;；<\n]+)",
        r"(?:trigger level|threshold)[^:：=]*[:：=]\s*([^,，;；<\n]+)",
    ]
    for pattern in patterns:
        m = re.search(pattern, s, flags=re.IGNORECASE)
        if m:
            token = _extract_value_token(m.group(1))
            if token:
                return token

    candidates = re.findall(r"[-+]?\d*\.?\d+\s*(?:dBmV|dBm|mV|uV|μV|V|Vrms|Vpp)", s, flags=re.IGNORECASE)
    freq_like = re.findall(r"[-+]?\d*\.?\d+\s*(?:Hz|kHz|MHz|GHz|THz|ms|us|μs|ns|ps|s)", s, flags=re.IGNORECASE)
    freq_like_set = {c.lower() for c in freq_like}
    for candidate in candidates:
        if candidate.lower() not in freq_like_set:
            token = _extract_value_token(candidate)
            if token:
                return token
    return ""


def _convert_sensitivity_token_for_range(token: str, outer_range: str) -> Tuple[str, List[str]]:
    note_parts: List[str] = []
    if not token:
        return "", note_parts

    token_unit = _extract_primary_unit_token(token)
    range_unit = _extract_primary_unit_token(outer_range)
    if _is_power_unit(token_unit) and (_is_voltage_unit(range_unit) or _range_looks_voltage_like(outer_range)):
        raw = unit_convert_tool(token)
        try:
            payload = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            payload = {}
        converted_vpp = payload.get("converted_vpp")
        converted_unit = payload.get("unit") or "Vpp"
        if converted_vpp not in (None, ""):
            converted = f"{converted_vpp} {converted_unit}"
            assumptions = payload.get("assumptions") or []
            if assumptions:
                note_parts.append(f"单位换算：{token} -> {converted}（{', '.join(map(str, assumptions))}）")
            else:
                note_parts.append(f"单位换算：{token} -> {converted}")
            return converted, note_parts
    return token, note_parts


def _verify_input_sensitivity_composite_range(measure_val: str, range_val: str) -> Dict[str, Any]:
    range_text = str(range_val or "")
    outer_range = re.sub(r"\([^)]*\)", "", range_text).strip()
    axis_match = re.search(r"\(([^)]*)\)", range_text)
    axis_range = axis_match.group(1).strip() if axis_match else ""

    axis_measure = ""
    axis_kind = None
    if _parse_frequency_range(axis_range) is not None:
        axis_kind = "frequency"
        axis_measure = _extract_measure_for_range_tool(measure_val)
    elif _parse_range_to_base_units(axis_range, "time") is not None:
        axis_kind = "time"
        axis_measure = _extract_measure_for_range_tool(measure_val)

    sensitivity_token = _extract_sensitivity_value_token(measure_val)
    converted_token, conversion_notes = _convert_sensitivity_token_for_range(sensitivity_token, outer_range)

    axis_payload = None
    amp_payload = None

    if axis_range and axis_measure:
        axis_payload = json.loads(verify_range_logic(axis_measure, axis_range))
    if outer_range and converted_token:
        amp_payload = json.loads(verify_range_logic(converted_token, outer_range))

    if axis_payload is None and amp_payload is None:
        return {
            "status": "REVIEW",
            "reason": "复合输入灵敏度范围无法完整解析，需要人工复核",
            "calc_type": "range",
        }

    statuses = [p.get("status", "").upper() for p in [axis_payload, amp_payload] if p]
    if "FAIL" in statuses or "ERROR" in statuses:
        status = "FAIL"
    elif "REVIEW" in statuses:
        status = "REVIEW"
    else:
        status = "PASS"

    reason_parts: List[str] = []
    if axis_payload is not None:
        axis_label = "频率范围核验" if axis_kind == "frequency" else "周期范围核验"
        reason_parts.append(f"{axis_label}:{axis_payload.get('status')}({axis_payload.get('reason')})")
    if amp_payload is not None:
        reason_parts.append(f"电平范围核验:{amp_payload.get('status')}({amp_payload.get('reason')})")
    reason_parts.extend(conversion_notes)
    return {
        "status": status,
        "reason": "；".join(reason_parts) if reason_parts else "复合输入灵敏度范围核验完成",
        "calc_type": "range",
    }


def _normalize_match_item_for_row(
    match_item: str,
    measure_val: str,
    range_val: str,
    error_val: str = "",
) -> str:
    item = str(match_item or "").strip()
    if not item:
        return item

    semantic_text = " ".join(
        part for part in [item, str(measure_val or ""), str(range_val or "")] if part
    ).lower()
    if ("功率" not in semantic_text) and ("power" not in semantic_text):
        return item

    range_text = str(range_val or "").lower()
    error_text = str(error_val or "").lower()
    measure_text = str(measure_val or "").lower()

    has_dbm_range = "dbm" in range_text
    has_db_range = ("db" in range_text) and not has_dbm_range
    has_dbm_measure = "dbm" in measure_text
    has_db_error = ("db" in error_text) and ("dbm" not in error_text)

    if has_dbm_range and has_dbm_measure:
        return "功率范围"
    if has_db_range and has_db_error:
        return "功率偏差"

    return item


def _measure_prefers_relative_u(measure_val: str) -> bool:
    s = str(measure_val or "")
    keywords = [
        "相对频率偏差",
        "频率稳定度",
        "日老化率",
        "频率复现性",
        "相对",
    ]
    return any(k in s for k in keywords)


def _detect_uncertainty_kind(u_str: str, measure_val: str = "") -> str:
    if u_str is None:
        return "UNKNOWN"
    s = str(u_str).strip()
    if not s or s in ["N/A", "NA", "-", "/", "None", "none"]:
        return "UNKNOWN"

    s_lower = s.lower()
    if "urel" in s_lower or "u rel" in s_lower:
        return "UREL"

    if re.search(r"\bu\s*=", s_lower):
        raw = re.split(r"=", s, maxsplit=1)[1].strip() if "=" in s else s
        if ("ux" in raw.lower()) or ("+" in raw):
            return "U_FORMULA"
        return "U"

    if re.search(r"(GHz|MHz|kHz|Hz|mV|uV|μV|V|ms|us|μs|ns|ps|s)\b", s, flags=re.IGNORECASE):
        return "U"

    if "%" in s:
        return "UREL" if _measure_prefers_relative_u(measure_val) else "U"

    if _measure_prefers_relative_u(measure_val):
        return "UREL"

    return "U"


def _parse_urel_uncertainty(u_str: str) -> Tuple[Optional[float], str]:
    if _is_missing(u_str):
        return None, "missing"

    s = str(u_str).strip()
    s = re.sub(r"^\s*U\s*rel\s*=\s*", "", s, flags=re.IGNORECASE)
    s = re.sub(r"^\s*Urel\s*=\s*", "", s, flags=re.IGNORECASE)

    if "%" in s:
        num = parse_unicode_sci_number(s)
        if num is None:
            m = re.search(r"([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)", s)
            num = float(m.group(1)) if m else None
        if num is None:
            return None, "missing"
        return abs(num / 100.0), "rel_percent"

    val, val_type = parse_value_with_unit(s, base_val=None)
    return val, f"rel_direct:{val_type}"


def _parse_absolute_uncertainty(
    u_str: str,
    measure_val: str,
    base_for_rel: Optional[float],
    ux_unit_hint: Optional[str],
) -> Tuple[Optional[float], str]:
    norm = _inherit_unit_if_missing(u_str, measure_val, ux_unit_hint=ux_unit_hint)
    parse_base = None if "%" in str(norm or "") else base_for_rel
    val, val_type = parse_value_with_unit(norm, parse_base)
    return val, val_type





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
        cert_kind = _detect_uncertainty_kind(cert_u, measure_val)
        kb_kind = _detect_uncertainty_kind(kb_u, measure_val)

        # 提取不确定度的单位信息
        def extract_unit(u_str):
            s = str(u_str)
            # 先尝试匹配复杂单位，如dBm, dBmV等
            complex_unit_match = re.search(r"(dBm|dBmV)", s, re.IGNORECASE)
            if complex_unit_match:
                return complex_unit_match.group(1).lower()
            # 匹配简单单位，如 Hz, kHz, MHz, GHz, mV, V, dB 等
            simple_unit_match = re.search(r"(Hz|kHz|MHz|GHz|THz|mV|V|μV|kV|dB)", s, re.IGNORECASE)
            if simple_unit_match:
                return simple_unit_match.group(1).lower()
            return None

        cert_unit = extract_unit(cert_u)
        kb_unit = extract_unit(kb_u)

        # 如果都是相对不确定度，直接比较
        if cert_kind == "UREL" and kb_kind == "UREL":
            c_val, c_type = _parse_urel_uncertainty(cert_u)
            k_val, k_type = _parse_urel_uncertainty(kb_u)
            k_reason = f"same_kind_urel:{k_type}"
        else:
            # 检查是否为绝对不确定度且单位不匹配
            if cert_kind == "U" and kb_kind == "U" and cert_unit and kb_unit and cert_unit != kb_unit:
                # 检查是否是可转换的单位（如都是电压单位或都是频率单位）
                is_convertible = False
                # 电压单位组
                voltage_units = {'mv', 'v', 'μv', 'kv'}
                if cert_unit in voltage_units and kb_unit in voltage_units:
                    is_convertible = True
                # 频率单位组
                freq_units = {'hz', 'khz', 'mhz', 'ghz', 'thz'}
                if cert_unit in freq_units and kb_unit in freq_units:
                    is_convertible = True
                # 功率单位组
                power_units = {'dbm', 'dbmv'}
                if cert_unit in power_units and kb_unit in power_units:
                    is_convertible = True
                # dB单位特殊处理 - dB通常是相对单位，不能直接和绝对单位比较
                if (cert_unit == 'db' and kb_unit != 'db') or (kb_unit == 'db' and cert_unit != 'db'):
                    is_convertible = False

                if not is_convertible:
                    return json.dumps({
                        "status": "REVIEW",
                        "reason": f"不确定度单位不匹配且无法转换（Cert: {cert_unit} vs KB: {kb_unit}），需要人工核验",
                        "calc_type": "uncertainty"
                    }, ensure_ascii=False)

            if cert_kind == "UREL":
                c_val, c_type = _parse_urel_uncertainty(cert_u)
                c_val = (c_val * base_for_rel) if (c_val is not None and base_for_rel is not None) else c_val
                c_type = "rel_to_abs"
            else:
                c_val, c_type = _parse_absolute_uncertainty(cert_u, measure_val, base_for_rel, ux_unit_hint)

            if kb_kind == "U_FORMULA":
                k_formula_val, k_formula_reason = calc_u_formula(kb_u, measure_val)
            else:
                k_formula_val, k_formula_reason = (None, None)
            if k_formula_val is not None:
                k_val = k_formula_val
                k_reason = k_formula_reason
            elif kb_kind == "UREL":
                k_rel, k_type = _parse_urel_uncertainty(kb_u)
                k_val = (k_rel * base_for_rel) if (k_rel is not None and base_for_rel is not None) else k_rel
                k_reason = "parsed:rel_coef_converted"
            else:
                k_val, k_type = _parse_absolute_uncertainty(kb_u, measure_val, base_for_rel, ux_unit_hint)
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
            "name": "verify_range_logic",
            "description": "核验测量值是否在范围要求内。支持：①区间(如1ns~10s)；②单边限制(如<10, ≥5)。必须严格按照工具返回的 PASS/FAIL 判定，禁止自行口算范围！",
            "parameters": {
                "type": "object",
                "properties": {
                    "measure_val": {"type": "string", "description": "测量值(含单位)"},
                    "range_str": {"type": "string", "description": "范围要求(如1ns~10s, <10s, ≥10KHz等)"}
                },
                "required": ["measure_val", "range_str"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "verify_uncertainty_logic",
            "description": "核验不确定度。规则：Cert_U >= KB_U 为合格，必须严格按该项目规则判断。",
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
            # 优化显示：使用科学计数法，保留2位有效数字
            if 1e-12 <= abs(num) < 1e-6:
                info["value_display"] = "{:.1e}".format(num)
            elif abs(num) < 1e-12:
                info["value_display"] = "{:.2e}".format(num)
            else:
                info["value_display"] = "{:.4g}".format(num)
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




def validate_kb_range(range_str: str) -> bool:
    """
    验证知识库范围的有效性
    """
    try:
        parsed = parse_range_limit(range_str)
        if parsed:
            lower, upper = parsed
            if lower > upper:
                raise ValueError(f"Invalid range: lower bound {lower} > upper bound {upper}")
            # 检查范围是否合理（例如，不能有负数下限的对称范围）
            if lower < 0 and upper > 0:
                print(f"Warning: Range crosses zero: {lower} ~ {upper}")
            return True
        return False
    except Exception as e:
        print(f"Error validating range '{range_str}': {e}")
        return False


def validate_kb_entry(entry: Dict[str, Any]) -> bool:
    """
    验证知识库条目的完整性和正确性
    """
    try:
        # 检查基本字段
        required_fields = ["file_code", "measured", "measure_range_text"]
        for field in required_fields:
            if field not in entry:
                raise KeyError(f"Missing required field: {field}")

        # 验证范围
        if not validate_kb_range(entry.get("measure_range_text", "")):
            raise ValueError(f"Invalid range in entry: {entry['measure_range_text']}")

        return True
    except Exception as e:
        print(f"Error validating KB entry: {e}")
        return False


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
    if len(entries) > top_k:
        table_lines.append("")
        table_lines.append(
            f"> 注：上表仅预览前 {top_k} 条，实际后续核验使用的是当前依据命中的全部 {len(entries)} 条 KB 条目。"
        )
    return "\n".join(table_lines)


def _count_statuses_from_table_lines(table_lines: List[str]) -> Tuple[int, int, int]:
    pass_count = 0
    fail_count = 0
    total_count = 0
    status_idx = None

    for line in table_lines:
        if not line.startswith("|"):
            continue

        cols = [s.strip() for s in line.strip().strip("|").split("|")]
        if "判定" in cols:
            try:
                status_idx = cols.index("判定")
            except ValueError:
                status_idx = None
            continue

        if status_idx is None:
            continue
        if all(set(c) <= {"-",
 ":", " "} for c in cols):
            continue
        if status_idx >= len(cols):
            continue

        status = cols[status_idx].upper()
        if status == "PASS":
            pass_count += 1
            total_count += 1
        elif status == "FAIL":
            fail_count += 1
            total_count += 1

    return pass_count, fail_count, total_count


def _build_summary_lines_from_table(table_lines: List[str]) -> List[str]:
    summary = _summarize_table_statuses(table_lines)
    pass_count = summary["pass"]
    fail_count = summary["fail"]
    review_count = summary.get("review", 0)
    total_count = summary["total"]

    if total_count == 0:
        return [
            "**核验总结：**",
            "- 本批次未解析到可统计的 PASS/FAIL 测量点",
            "- 总体判定：N/A",
        ]

    # 总体判定：只有FAIL数量为0且REVIEW数量为0才判定为PASS
    overall = "PASS" if (fail_count == 0 and review_count == 0) else "FAIL"
    lines = [
        "**核验总结：**",
        f"- 本批次共 {total_count} 个测量点，PASS {pass_count} 个，FAIL {fail_count} 个" + (f"，REVIEW {review_count} 个" if review_count > 0 else ""),
        f"- 总体判定：{overall}",
    ]
    return lines


def _extract_param_name(line: str) -> Optional[str]:
    raw = (line or "").strip()
    m = re.match(r"^#{2,6}\s*参数[:：]\s*(.+?)\s*$", raw)
    if m:
        return m.group(1).strip()
    m = re.match(r"^#{2,6}\s*核验结果[:：]\s*(.+?)\s*$", raw)
    if m:
        return m.group(1).strip()
    if raw.startswith("**参数名称：") and raw.endswith("**"):
        return raw[len("**参数名称："):-2].strip()
    if raw.startswith("**参数名称："):
        return raw.replace("**参数名称：", "", 1).strip("* ").strip()
    return None


def _merge_table_lines(existing: List[str], new_lines: List[str]) -> List[str]:
    if not existing:
        return list(new_lines)
    if not new_lines:
        return list(existing)

    merged = list(existing[:2]) if len(existing) >= 2 else list(existing)
    seen = set()
    for line in merged[2:]:
        if line.startswith("|"):
            seen.add(line)

    for line in existing[2:]:
        if line.startswith("|") and line not in seen:
            merged.append(line)
            seen.add(line)

    start_idx = 2 if len(new_lines) >= 2 else 0
    for line in new_lines[start_idx:]:
        if line.startswith("|") and line not in seen:
            merged.append(line)
            seen.add(line)

    return merged


def enforce_batch_summary_from_table(md: str, expected_param_names: Optional[List[str]] = None) -> str:
    if not md or "|" not in md:
        return md

    lines = md.splitlines()
    out = []
    current_param = None
    current_table = []
    in_table = False
    summary_inserted = False
    skip_old_summary = False
    fallback_param = expected_param_names[0] if expected_param_names and len(expected_param_names) == 1 else None

    def flush_summary_if_needed():
        nonlocal summary_inserted
        if current_param and current_table and not summary_inserted:
            out.extend(_build_summary_lines_from_table(current_table))
            summary_inserted = True

    for line in lines:
        stripped = line.strip()
        extracted_param = _extract_param_name(stripped)
        if extracted_param:
            flush_summary_if_needed()
            current_param = extracted_param
            current_table = []
            in_table = False
            summary_inserted = False
            skip_old_summary = False
            out.append(line)
            continue

        if (
            stripped.startswith("**核验总结：**")
            or stripped.startswith("**核验总结**：")
            or stripped.startswith("**核验总结**:")
            or stripped.startswith("**核验总结：")
            or stripped.startswith("## 核验总结")
        ):
            flush_summary_if_needed()
            skip_old_summary = True
            continue

        if skip_old_summary:
            if (
                stripped == "---"
                or stripped.startswith("#### ")
                or re.match(r"^#{2,6}\s*参数[:：]", stripped)
                or re.match(r"^#{2,6}\s*核验结果[:：]", stripped)
                or stripped.startswith("**参数名称：")
            ):
                skip_old_summary = False
            else:
                continue

        if stripped.startswith("|") and ("序号" in stripped or "点位" in stripped):
            in_table = True
            if not current_param and fallback_param:
                current_param = fallback_param
            current_table = [line]
            out.append(line)
            continue

        if in_table and stripped.startswith("|"):
            current_table.append(line)
            out.append(line)
            continue

        if in_table and not stripped.startswith("|"):
            in_table = False
            flush_summary_if_needed()

        out.append(line)

    flush_summary_if_needed()
    return "\n".join(out)


def _unique_param_names(batch: List[Dict[str, Any]]) -> List[str]:
    names: List[str] = []
    seen = set()
    for item in batch:
        name = str(item.get("param_name", "")).strip()
        if name and name not in seen:
            names.append(name)
            seen.add(name)
    return names


def _collect_param_tables(
    batch_contents: List[str],
    batch_expected_params: Optional[Dict[int, List[str]]] = None,
) -> Dict[str, List[str]]:
    param_to_table: Dict[str, List[str]] = {}

    for batch_idx, batch_content in enumerate(batch_contents, 1):
        current_param = None
        in_table = False
        table_lines: List[str] = []
        expected = (batch_expected_params or {}).get(batch_idx, [])
        fallback_param = expected[0] if len(expected) == 1 else None

        for raw_line in batch_content.splitlines():
            line = raw_line.strip()

            extracted_param = _extract_param_name(line)
            if extracted_param:
                if current_param and in_table and table_lines:
                    normalized_param = _normalize_param_name_for_merge(current_param)
                    if normalized_param in param_to_table:
                        param_to_table[normalized_param] = _merge_table_lines(param_to_table[normalized_param], table_lines)
                    else:
                        param_to_table[normalized_param] = table_lines
                current_param = extracted_param
                in_table = False
                table_lines = []
                continue

            if line.startswith("|") and ("序号" in line or "点位" in line):
                in_table = True
                if not current_param and fallback_param:
                    current_param = fallback_param
                table_lines = [line]
                continue

            if in_table and line:
                if line.startswith("|"):
                    if line not in table_lines:
                        table_lines.append(line)
                else:
                    in_table = False
                    if current_param and table_lines:
                        normalized_param = _normalize_param_name_for_merge(current_param)
                        if normalized_param in param_to_table:
                            param_to_table[normalized_param] = _merge_table_lines(param_to_table[normalized_param], table_lines)
                        else:
                            param_to_table[normalized_param] = table_lines

        if current_param and in_table and table_lines:
            normalized_param = _normalize_param_name_for_merge(current_param)
            if normalized_param in param_to_table:
                param_to_table[normalized_param] = _merge_table_lines(param_to_table[normalized_param], table_lines)
            else:
                param_to_table[normalized_param] = table_lines

    return param_to_table


def _find_status_column_index(cols: List[str]) -> Optional[int]:
    for idx, col in enumerate(cols):
        col_text = col.strip()
        normalized = col_text.lower()
        if col_text == "\u5224\u5b9a" or normalized == "status":
            return idx
    return None


def _find_kb_code_column_index(cols: List[str]) -> Optional[int]:
    for idx, col in enumerate(cols):
        col_text = col.strip()
        normalized = col_text.lower()
        if col_text == "KB\u7f16\u53f7" or normalized in {"kb code", "kb_code"}:
            return idx
    return None


def _find_note_column_index(cols: List[str]) -> Optional[int]:
    for idx, col in enumerate(cols):
        col_text = col.strip()
        normalized = col_text.lower()
        if col_text == "\u8bf4\u660e" or normalized in {"note", "reason"}:
            return idx
    return None


def _is_kb_missing_fail(status: str, kb_code: str, note: str) -> bool:
    if status != "FAIL":
        return False

    kb_text = str(kb_code or "").strip()
    kb_upper = kb_text.upper()
    note_text = str(note or "").strip()
    if kb_text in {"", "-", "/", "\u65e0"}:
        return True
    if kb_upper in {"N/A", "NA", "NONE"}:
        return True
    if "\u65e0\u5bf9\u5e94\u53c2\u6570" in note_text:
        return True
    if "KB" in note_text and "\u672a\u8986\u76d6" in note_text:
        return True
    return False


def _summarize_table_statuses(table_lines: List[str]) -> Dict[str, int]:
    summary = {
        "pass": 0,
        "fail": 0,
        "review": 0,
        "total": 0,
        "kb_missing_fail": 0,
        "real_fail": 0,
    }
    status_idx = None
    kb_idx = None
    note_idx = None

    for line in table_lines:
        if not line.startswith("|"):
            continue

        cols = [s.strip() for s in line.strip().strip("|").split("|")]
        maybe_status_idx = _find_status_column_index(cols)
        if maybe_status_idx is not None:
            status_idx = maybe_status_idx
            kb_idx = _find_kb_code_column_index(cols)
            note_idx = _find_note_column_index(cols)
            continue

        if status_idx is None:
            continue
        if all(set(c) <= {"-", ":", " "} for c in cols):
            continue
        if status_idx >= len(cols):
            continue

        status = cols[status_idx].upper()
        if status == "PASS":
            summary["pass"] += 1
            summary["total"] += 1
            continue
        if status == "REVIEW":
            summary["review"] += 1
            summary["total"] += 1
            continue
        if status != "FAIL":
            continue

        kb_code = cols[kb_idx] if kb_idx is not None and kb_idx < len(cols) else ""
        note = cols[note_idx] if note_idx is not None and note_idx < len(cols) else ""
        summary["fail"] += 1
        summary["total"] += 1
        if _is_kb_missing_fail(status, kb_code, note):
            summary["kb_missing_fail"] += 1
        else:
            summary["real_fail"] += 1

    return summary


def _count_statuses_from_table_lines(table_lines: List[str]) -> Tuple[int, int, int]:
    summary = _summarize_table_statuses(table_lines)
    return summary["pass"], summary["fail"], summary["total"]


def _looks_like_table_header(line: str) -> bool:
    stripped = (line or "").strip()
    if not stripped.startswith("|"):
        return False
    return any(token in stripped for token in ("\u5e8f\u53f7", "\u70b9\u4f4d", "搴忓彿", "鐐逛綅"))


def _looks_like_summary_heading(line: str) -> bool:
    stripped = (line or "").strip()
    prefixes = (
        "**\u6838\u9a8c\u603b\u7ed3",
        "## \u6838\u9a8c\u603b\u7ed3",
        "**鏍搁獙鎬荤粨",
        "## 鏍搁獙鎬荤粨",
    )
    return any(stripped.startswith(prefix) for prefix in prefixes)


def _extract_param_name(line: str) -> Optional[str]:
    raw = (line or "").strip()
    heading_labels = [
        "\u53c2\u6570",
        "\u53c2\u6570\u7ec4",
        "\u6838\u9a8c\u7ed3\u679c",
    ]
    for label in heading_labels:
        m = re.match(rf"^#{{2,6}}\s*{re.escape(label)}[:：\s]*(.+?)\s*$", raw)
        if m:
            return m.group(1).strip()

    bold_labels = [
        "\u53c2\u6570\u540d\u79f0",
        "\u53c2\u6570\u7ec4",
    ]
    for label in bold_labels:
        for prefix in (f"**{label}：", f"**{label}:"):
            if raw.startswith(prefix) and raw.endswith("**"):
                return raw[len(prefix):-2].strip()
            if raw.startswith(prefix):
                return raw[len(prefix):].strip("* ").strip()
    return None


def _build_fallback_param_name(expected_param_names: Optional[List[str]]) -> Optional[str]:
    names: List[str] = []
    seen = set()
    for name in expected_param_names or []:
        text = str(name or "").strip()
        if text and text not in seen:
            names.append(text)
            seen.add(text)

    if not names:
        return None
    if len(names) == 1:
        return names[0]
    return " / ".join(names)


def _normalize_param_part_name(part_name: str) -> str:
    text = str(part_name or "").strip()
    if not text:
        return ""

    text = re.sub(r"<br\s*/?>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()

    number = ""
    body = text
    m = re.match(r"^([0-9]+(?:\.[0-9]+)*)\s+(.+)$", text)
    if m:
        number = m.group(1).strip()
        body = m.group(2).strip()

    body = re.sub(r"\([^)]*\)", "", body)
    body = re.sub(r"（[^）]*）", "", body)
    body = re.sub(r"\s+", " ", body).strip(" -_/")

    if number and body:
        return f"{number} {body}"
    return body or text


def _normalize_param_name_for_merge(param_name: str) -> str:
    text = str(param_name or "").strip()
    if not text:
        return ""

    parts = [p.strip() for p in re.split(r"\s*/\s*", text) if p.strip()]
    if not parts:
        return text

    normalized_parts = [_normalize_param_part_name(part) for part in parts]
    normalized_parts = [part for part in normalized_parts if part]
    if not normalized_parts:
        return text

    return " / ".join(normalized_parts)


def enforce_batch_summary_from_table(md: str, expected_param_names: Optional[List[str]] = None) -> str:
    if not md or "|" not in md:
        return md

    lines = md.splitlines()
    out = []
    current_param = None
    current_table = []
    in_table = False
    summary_inserted = False
    skip_old_summary = False
    fallback_param = _build_fallback_param_name(expected_param_names)

    def flush_summary_if_needed():
        nonlocal summary_inserted
        if current_param and current_table and not summary_inserted:
            out.extend(_build_summary_lines_from_table(current_table))
            summary_inserted = True

    for line in lines:
        stripped = line.strip()
        extracted_param = _extract_param_name(stripped)
        if extracted_param:
            flush_summary_if_needed()
            current_param = extracted_param
            current_table = []
            in_table = False
            summary_inserted = False
            skip_old_summary = False
            out.append(line)
            continue

        if (
            stripped.startswith("**鏍搁獙鎬荤粨锛?*")
            or stripped.startswith("**鏍搁獙鎬荤粨**锛?")
            or stripped.startswith("**鏍搁獙鎬荤粨**:")
            or stripped.startswith("**鏍搁獙鎬荤粨锛?")
            or stripped.startswith("## 鏍搁獙鎬荤粨")
        ):
            flush_summary_if_needed()
            skip_old_summary = True
            continue

        if skip_old_summary:
            if stripped == "---" or stripped.startswith("#### ") or _extract_param_name(stripped):
                skip_old_summary = False
            else:
                continue

        if stripped.startswith("|") and ("搴忓彿" in stripped or "鐐逛綅" in stripped):
            in_table = True
            if not current_param and fallback_param:
                current_param = fallback_param
            current_table = [line]
            out.append(line)
            continue

        if in_table and stripped.startswith("|"):
            current_table.append(line)
            out.append(line)
            continue

        if in_table and not stripped.startswith("|"):
            in_table = False
            flush_summary_if_needed()

        out.append(line)

    flush_summary_if_needed()
    return "\n".join(out)


def _collect_param_tables(
    batch_contents: List[str],
    batch_expected_params: Optional[Dict[int, List[str]]] = None,
) -> Dict[str, List[str]]:
    param_to_table: Dict[str, List[str]] = {}

    for batch_idx, batch_content in enumerate(batch_contents, 1):
        current_param = None
        in_table = False
        table_lines: List[str] = []
        expected = (batch_expected_params or {}).get(batch_idx, [])
        fallback_param = _build_fallback_param_name(expected)

        for raw_line in batch_content.splitlines():
            line = raw_line.strip()

            extracted_param = _extract_param_name(line)
            if extracted_param:
                if current_param and in_table and table_lines:
                    normalized_param = _normalize_param_name_for_merge(current_param)
                    if normalized_param in param_to_table:
                        param_to_table[normalized_param] = _merge_table_lines(param_to_table[normalized_param], table_lines)
                    else:
                        param_to_table[normalized_param] = table_lines
                current_param = extracted_param
                in_table = False
                table_lines = []
                continue

            if line.startswith("|") and ("搴忓彿" in line or "鐐逛綅" in line):
                in_table = True
                if not current_param and fallback_param:
                    current_param = fallback_param
                table_lines = [line]
                continue

            if in_table and line:
                if line.startswith("|"):
                    if line not in table_lines:
                        table_lines.append(line)
                else:
                    in_table = False
                    if current_param and table_lines:
                        normalized_param = _normalize_param_name_for_merge(current_param)
                        if normalized_param in param_to_table:
                            param_to_table[normalized_param] = _merge_table_lines(param_to_table[normalized_param], table_lines)
                        else:
                            param_to_table[normalized_param] = table_lines

        if current_param and in_table and table_lines:
            normalized_param = _normalize_param_name_for_merge(current_param)
            if normalized_param in param_to_table:
                param_to_table[normalized_param] = _merge_table_lines(param_to_table[normalized_param], table_lines)
            else:
                param_to_table[normalized_param] = table_lines

    return param_to_table


def _find_status_column_index(cols: List[str]) -> Optional[int]:
    for idx, col in enumerate(cols):
        text = col.strip()
        normalized = text.lower()
        if text == "\u5224\u5b9a" or normalized == "status":
            return idx
    return None


def _find_kb_code_column_index(cols: List[str]) -> Optional[int]:
    for idx, col in enumerate(cols):
        text = col.strip()
        normalized = text.lower()
        if text == "KB\u7f16\u53f7" or normalized in {"kb code", "kb_code"}:
            return idx
    return None


def _find_note_column_index(cols: List[str]) -> Optional[int]:
    for idx, col in enumerate(cols):
        text = col.strip()
        normalized = text.lower()
        if text == "\u8bf4\u660e" or normalized in {"note", "reason"}:
            return idx
    return None


def _is_kb_missing_fail(status: str, kb_code: str, note: str) -> bool:
    if status != "FAIL":
        return False

    kb_text = str(kb_code or "").strip()
    kb_upper = kb_text.upper()
    note_text = str(note or "").strip()
    if kb_text in {"", "-", "/", "\u65e0"}:
        return True
    if kb_upper in {"N/A", "NA", "NONE"}:
        return True
    if "\u65e0\u5bf9\u5e94\u53c2\u6570" in note_text:
        return True
    if "KB" in note_text and "\u672a\u8986\u76d6" in note_text:
        return True
    return False


def _summarize_table_statuses(table_lines: List[str]) -> Dict[str, int]:
    summary = {
        "pass": 0,
        "fail": 0,
        "review": 0,
        "total": 0,
        "kb_missing_fail": 0,
        "real_fail": 0,
    }
    status_idx = None
    kb_idx = None
    note_idx = None

    for line in table_lines:
        if not line.startswith("|"):
            continue

        cols = [s.strip() for s in line.strip().strip("|").split("|")]
        maybe_status_idx = _find_status_column_index(cols)
        if maybe_status_idx is not None:
            status_idx = maybe_status_idx
            kb_idx = _find_kb_code_column_index(cols)
            note_idx = _find_note_column_index(cols)
            continue

        if status_idx is None:
            continue
        if all(set(c) <= {"-", ":", " "} for c in cols):
            continue
        if status_idx >= len(cols):
            continue

        status = cols[status_idx].upper()
        if status == "PASS":
            summary["pass"] += 1
            summary["total"] += 1
            continue
        if status == "REVIEW":
            summary["review"] += 1
            summary["total"] += 1
            continue
        if status != "FAIL":
            continue

        kb_code = cols[kb_idx] if kb_idx is not None and kb_idx < len(cols) else ""
        note = cols[note_idx] if note_idx is not None and note_idx < len(cols) else ""
        summary["fail"] += 1
        summary["total"] += 1
        if _is_kb_missing_fail(status, kb_code, note):
            summary["kb_missing_fail"] += 1
        else:
            summary["real_fail"] += 1

    return summary


def _count_statuses_from_table_lines(table_lines: List[str]) -> Tuple[int, int, int]:
    summary = _summarize_table_statuses(table_lines)
    return summary["pass"], summary["fail"], summary["total"]


def _looks_like_table_header(line: str) -> bool:
    stripped = (line or "").strip()
    if not stripped.startswith("|"):
        return False
    return any(token in stripped for token in ("\u5e8f\u53f7", "\u70b9\u4f4d"))


def _looks_like_summary_heading(line: str) -> bool:
    stripped = (line or "").strip()
    return (
        stripped.startswith("**\u6838\u9a8c\u603b\u7ed3")
        or stripped.startswith("## \u6838\u9a8c\u603b\u7ed3")
        or stripped.startswith("**\u603b\u7ed3")
        or stripped.startswith("## \u603b\u7ed3")
    )


def _extract_param_name(line: str) -> Optional[str]:
    raw = (line or "").strip()
    heading_labels = [
        "\u53c2\u6570\u7ec4",
        "\u53c2\u6570",
    ]
    for label in heading_labels:
        m = re.match(
            rf"^#{{2,6}}\s*{re.escape(label)}\s*(?:[:\uFF1A]\s*)?(.+?)\s*$",
            raw,
        )
        if m:
            param_name = m.group(1).strip()
            # 过滤掉常见的非参数名称，如"汇总"、"总结"等
            if param_name in ["汇总", "总结", "统计", "详情"]:
                continue
            return param_name

    for label in ("\u53c2\u6570\u540d\u79f0", "\u53c2\u6570\u7ec4"):
        for prefix in (f"**{label}\uFF1A", f"**{label}:"):
            if raw.startswith(prefix) and raw.endswith("**"):
                return raw[len(prefix):-2].strip()
            if raw.startswith(prefix):
                return raw[len(prefix):].strip("* ").strip()
    return None


def _build_fallback_param_name(expected_param_names: Optional[List[str]]) -> Optional[str]:
    names: List[str] = []
    seen = set()
    for name in expected_param_names or []:
        text = str(name or "").strip()
        if text and text not in seen:
            names.append(text)
            seen.add(text)

    if not names:
        return None
    if len(names) == 1:
        return names[0]
    return " / ".join(names)


def enforce_batch_summary_from_table(md: str, expected_param_names: Optional[List[str]] = None) -> str:
    if not md or "|" not in md:
        return md

    lines = md.splitlines()
    out = []
    current_param = None
    current_table = []
    in_table = False
    summary_inserted = False
    skip_old_summary = False
    fallback_param = _build_fallback_param_name(expected_param_names)

    def flush_summary_if_needed():
        nonlocal summary_inserted
        if current_param and current_table and not summary_inserted:
            out.extend(_build_summary_lines_from_table(current_table))
            summary_inserted = True

    for line in lines:
        stripped = line.strip()
        extracted_param = _extract_param_name(stripped)
        if extracted_param:
            flush_summary_if_needed()
            current_param = extracted_param
            current_table = []
            in_table = False
            summary_inserted = False
            skip_old_summary = False
            out.append(line)
            continue

        if _looks_like_summary_heading(stripped):
            flush_summary_if_needed()
            skip_old_summary = True
            continue

        if skip_old_summary:
            if stripped == "---" or stripped.startswith("#### ") or _extract_param_name(stripped):
                skip_old_summary = False
            else:
                continue

        if _looks_like_table_header(stripped):
            in_table = True
            if not current_param and fallback_param:
                current_param = fallback_param
            current_table = [line]
            out.append(line)
            continue

        if in_table and stripped.startswith("|"):
            current_table.append(line)
            out.append(line)
            continue

        if in_table and not stripped.startswith("|"):
            in_table = False
            flush_summary_if_needed()

        out.append(line)

    flush_summary_if_needed()
    return "\n".join(out)


def _collect_param_tables(
    batch_contents: List[str],
    batch_expected_params: Optional[Dict[int, List[str]]] = None,
) -> Dict[str, List[str]]:
    param_to_table: Dict[str, List[str]] = {}

    for batch_idx, batch_content in enumerate(batch_contents, 1):
        current_param = None
        in_table = False
        table_lines: List[str] = []
        expected = (batch_expected_params or {}).get(batch_idx, [])
        fallback_param = _build_fallback_param_name(expected)

        for raw_line in batch_content.splitlines():
            line = raw_line.strip()

            extracted_param = _extract_param_name(line)
            if extracted_param:
                if current_param and in_table and table_lines:
                    normalized_param = _normalize_param_name_for_merge(current_param)
                    if normalized_param in param_to_table:
                        param_to_table[normalized_param] = _merge_table_lines(param_to_table[normalized_param], table_lines)
                    else:
                        param_to_table[normalized_param] = table_lines
                current_param = extracted_param
                in_table = False
                table_lines = []
                continue

            if _looks_like_table_header(line):
                in_table = True
                if not current_param and fallback_param:
                    current_param = fallback_param
                table_lines = [line]
                continue

            if in_table and line:
                if line.startswith("|"):
                    if line not in table_lines:
                        table_lines.append(line)
                else:
                    in_table = False
                    if current_param and table_lines:
                        normalized_param = _normalize_param_name_for_merge(current_param)
                        if normalized_param in param_to_table:
                            param_to_table[normalized_param] = _merge_table_lines(param_to_table[normalized_param], table_lines)
                        else:
                            param_to_table[normalized_param] = table_lines

        if current_param and in_table and table_lines:
            normalized_param = _normalize_param_name_for_merge(current_param)
            if normalized_param in param_to_table:
                param_to_table[normalized_param] = _merge_table_lines(param_to_table[normalized_param], table_lines)
            else:
                param_to_table[normalized_param] = table_lines

    return param_to_table


def query_kb(coll, embedder: SentenceTransformer, instrument_name: str,
             criterion: str, topk: int = 50) -> List[Dict[str, Any]]:
    """
    根据仪器名和依据，在向量数据库中检索相关的 KB 条目。
    """
    print(f"\n📘 [Retrieval] 正在检索: {instrument_name} {criterion}")
    global LAST_QUERY_ERROR
    LAST_QUERY_ERROR = None

    # 1. 构造查询词
    basis_code = extract_basis_code(criterion)  # e.g. "GJB 7691" / "JJG 237"
    if basis_code:
        query_text = f"{norm_code(basis_code)} {criterion}"
    else:
        query_text = f"{instrument_name} {criterion}".strip()

    # 3. 检索 - 添加重试和错误处理
    q_emb = embedder.encode([query_text]).tolist()
    max_retries = 3
    delay = 1
    basis_code_norm = norm_code(basis_code) if basis_code else None
    requested_n_results = topk
    if basis_code_norm:
        try:
            requested_n_results = max(int(coll.count()), topk)
        except Exception:
            requested_n_results = topk

    for retry in range(max_retries):
        try:
            res = coll.query(
                query_embeddings=q_emb,
                n_results=requested_n_results,
                include=["documents", "metadatas"]
            )
            break  # 查询成功，跳出循环
        except Exception as e:
            print(f"❌ 第 {retry + 1}/{max_retries} 次查询失败: {e}")
            if retry == max_retries - 1:
                LAST_QUERY_ERROR = f"ChromaDB 查询异常 (重试 {max_retries} 次失败): {e}"
                print(f"❌ ChromaDB 查询异常: {e}")
                return []
            import time
            time.sleep(delay)
            delay *= 2  # 指数退避

    # 4. 结果处理

    docs = res.get("documents", [[]])[0] if res and res.get("documents") else []
    metas = res.get("metadatas", [[]])[0] if res and res.get("metadatas") else [{} for _ in docs]

    entries = []
    for d, m in zip(docs, metas):
        entries.append(parse_kb_entry(d, m))

    if basis_code_norm:
        filtered_entries = [
            entry for entry in entries
            if norm_code(entry.get("file_code")) == basis_code_norm
        ]
        if filtered_entries:
            print(f"✅ 按依据 {basis_code} 过滤后，共返回 {len(filtered_entries)} 条 KB 条目")
            return filtered_entries

    print(f"✅ 检索完成，共找到 {len(entries)} 条 (requested={requested_n_results})")
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
                    m_band = re.search(r"\bband\s*([0-9]+)\b", search_text, flags=re.IGNORECASE)
                    if m_band:
                        band = f"Band {m_band.group(1)}"
                        cols[idx_point] = band
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


def enforce_uncertainty_by_tool(md: str) -> str:
    """
    后处理：逐行复算范围/误差/不确定度，确保表格判定与工具结果一致。
    规则：
      - 任一工具返回 FAIL：该行【判定】强制置为 FAIL
      - 若三类工具均无 FAIL 且存在有效工具判定：该行【判定】置为 PASS
      - 若该行本来就因 KB 缺失等原因是 FAIL，且没有任何有效工具可覆盖，则保留 FAIL
      - 说明列追加：范围/误差/不确定度工具判定
    适配表头列名：
      序号, 点位, 测量点, KB编号, 证书匹配项, 范围, 证书误差, 允许误差, 证书U, KB_U, 判定, 说明
    """

    if not md or "|" not in md:
        return md

    def split_row(line: str):
        raw = line.strip()
        if raw.startswith("|"):
            raw = raw[1:]
        if raw.endswith("|"):
            raw = raw[:-1]
        return [c.strip() for c in raw.split("|")]

    def join_row(cols):
        return "| " + " | ".join(cols) + " |"

    def is_missing_cell(s: str) -> bool:
        ss = (s or "").strip()
        return ss in {"", "-", "N/A", "NA", "无", "none", "None", "/"}

    def is_status_like_cell(s: str) -> bool:
        ss = (s or "").strip().upper()
        return ss in {"PASS", "FAIL", "ERROR", "REVIEW", "N/A", "NA", "无法判定"}

    lines = md.splitlines()
    out = []

    in_table = False
    current_param_name = ""
    header_cols = []
    idx_measure = idx_match = idx_range = idx_error = idx_limit = idx_cert_u = idx_kb_u = idx_judge = idx_note = idx_kb = None

    for line in lines:
        stripped_line = line.strip()

        m_param = re.match(r"^#{2,6}\s*参数[:：]\s*(.+?)\s*$", stripped_line, flags=re.IGNORECASE)
        if m_param:
            current_param_name = m_param.group(1).strip()

        # 识别表头（必须包含这些关键列）
        if stripped_line.startswith("|") and ("测量点" in line) and ("判定" in line):
            in_table = True
            header_cols = split_row(line)

            def find_idx(name: str):
                try:
                    return header_cols.index(name)
                except ValueError:
                    return None

            idx_measure = find_idx("测量点")
            idx_match = find_idx("证书匹配项")
            idx_range = find_idx("范围")
            idx_error = find_idx("证书误差")
            idx_limit = find_idx("允许误差")
            idx_cert_u = find_idx("证书U")
            idx_kb_u = find_idx("KB_U")
            idx_judge = find_idx("判定")
            idx_note = find_idx("说明")
            idx_kb = find_idx("KB编号")

            out.append(line)
            continue

        # 分隔线
        if in_table and re.match(r"^\s*\|\s*-{2,}", line):
            out.append(line)
            continue

        # 数据行
        if in_table and line.strip().startswith("|"):
            cols = split_row(line)
            # 列长度保护
            valid_indexes = [i for i in [idx_measure, idx_match, idx_range, idx_error, idx_limit, idx_cert_u, idx_kb_u, idx_judge, idx_note, idx_kb] if i is not None]
            if not valid_indexes:
                out.append(line)
                continue
            max_need = max(valid_indexes)
            if len(cols) <= max_need:
                out.append(line)
                continue

            measure_val = cols[idx_measure] if idx_measure is not None else ""
            match_item = cols[idx_match] if idx_match is not None else ""
            range_val = cols[idx_range] if idx_range is not None else ""
            error_val = cols[idx_error] if idx_error is not None else ""
            limit_val = cols[idx_limit] if idx_limit is not None else ""
            cert_u = cols[idx_cert_u] if idx_cert_u is not None else ""
            kb_u = cols[idx_kb_u] if idx_kb_u is not None else ""
            judge = (cols[idx_judge] if idx_judge is not None else "").strip().upper()
            kb_code = cols[idx_kb] if idx_kb is not None else ""
            note = cols[idx_note] if idx_note is not None else ""

            match_item = _normalize_match_item_for_row(
                match_item,
                measure_val,
                range_val,
                error_val=error_val,
            )
            if idx_match is not None:
                cols[idx_match] = match_item

            if (
                idx_range is not None
                and _is_reference_oscillator_metric(measure_val, match_item)
                and _looks_like_discrete_point_range(range_val)
            ):
                discrete_point = _extract_discrete_point_token(range_val) or range_val
                cols[idx_range] = "N/A"
                range_val = "N/A"
                point_note = f"适用点:{discrete_point}"
                if idx_note is not None and idx_note < len(cols):
                    if point_note not in cols[idx_note]:
                        cols[idx_note] = (cols[idx_note] + "；" + point_note).strip("；").strip()
                        note = cols[idx_note]

            tool_statuses: List[str] = []
            note_additions: List[str] = []

            effective_param_name = current_param_name or measure_val

            if _is_input_sensitivity_check_param_name(effective_param_name):
                if idx_kb is not None:
                    cols[idx_kb] = "N/A"
                if idx_match is not None:
                    cols[idx_match] = "N/A"
                if idx_range is not None:
                    cols[idx_range] = "N/A"
                if idx_kb_u is not None:
                    cols[idx_kb_u] = "N/A"

                if _should_fail_input_sensitivity_row_for_garble(
                    effective_param_name,
                    measure_val,
                    cert_u=cert_u,
                    error_val=error_val,
                    limit_val=limit_val,
                ):
                    business_note = "按业务规则：输入灵敏度类参数仅检查文本是否存在乱码；当前检测到乱码或异常文本，跳过依据核验并判定FAIL"
                    if idx_judge is not None:
                        cols[idx_judge] = "FAIL"
                else:
                    business_note = "按业务规则：输入灵敏度类参数仅检查文本是否存在乱码；当前文本正常，跳过依据核验并判定PASS"
                    if idx_judge is not None:
                        cols[idx_judge] = "PASS"

                if idx_note is not None and idx_note < len(cols):
                    cols[idx_note] = business_note
                out.append(join_row(cols))
                continue

            def add_tool_note(prefix: str, payload: Dict[str, Any]):
                status = (payload.get("status") or "").upper()
                reason = str(payload.get("reason") or "").replace("|", "¦").strip()
                note_additions.append(f"{prefix}:{status}({reason})")
                if status in {"PASS", "FAIL", "ERROR", "REVIEW"}:
                    tool_statuses.append(status)

            # 修复：删除Agent添加的不当的"不确定度需人工复核"备注
            # 因为verify_uncertainty_logic工具已经能正确处理绝对和相对不确定度的比较
            # 使用正则表达式删除所有类似的备注
            note = re.sub(r"不确定度需人工复核[：:][^；]+?；?", "", note)

            if not is_missing_cell(range_val) and not is_status_like_cell(range_val):
                range_measure = _select_range_measure_value(
                    measure_val,
                    range_val,
                    error_val=error_val,
                    match_item=match_item,
                )
                try:
                    if _is_input_sensitivity_match_item(match_item, range_val):
                        range_res = _verify_input_sensitivity_composite_range(measure_val, range_val)
                    else:
                        range_res = verify_range_logic(range_measure, range_val)
                    add_tool_note("范围工具判定", json.loads(range_res) if isinstance(range_res, str) else range_res)
                except Exception as e:
                    note_additions.append(f"范围工具判定:ERROR({str(e).replace('|', '¦')})")

            if not is_missing_cell(limit_val):
                try:
                    error_res = verify_error_logic(error_val, limit_val)
                    add_tool_note("误差工具判定", json.loads(error_res) if isinstance(error_res, str) else error_res)
                except Exception as e:
                    note_additions.append(f"误差工具判定:ERROR({str(e).replace('|', '¦')})")

            if not is_missing_cell(kb_u):
                try:
                    tool_res = verify_uncertainty_logic(measure_val, cert_u, kb_u)
                    add_tool_note("不确定度工具判定", json.loads(tool_res) if isinstance(tool_res, str) else tool_res)
                except Exception as e:
                    note_additions.append(f"不确定度工具判定:ERROR({str(e).replace('|', '¦')})")

            if idx_note is not None and idx_note < len(cols):
                merged_note = note
                for add in note_additions:
                    if add not in merged_note:
                        merged_note = (merged_note + "；" + add).strip("；").strip()
                cols[idx_note] = merged_note
            else:
                merged_note = note

            kb_missing_forces_fail = is_missing_cell(kb_code)

            if idx_judge is not None:
                if kb_missing_forces_fail:
                    cols[idx_judge] = "FAIL"
                elif "FAIL" in tool_statuses or "ERROR" in tool_statuses:
                    cols[idx_judge] = "FAIL"
                elif "REVIEW" in tool_statuses:
                    cols[idx_judge] = "REVIEW"
                elif tool_statuses:
                    cols[idx_judge] = "PASS"
                elif judge == "FAIL" and is_missing_cell(kb_code):
                    cols[idx_judge] = "FAIL"
                elif judge in {"PASS", "FAIL", "REVIEW"}:
                    cols[idx_judge] = judge

            out.append(join_row(cols))
            continue

        # 退出表格
        if in_table and not line.strip().startswith("|"):
            in_table = False

        out.append(line)

    return "\n".join(out)


def collect_certificate_params(cert_root: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    兼容两种证书参数结构：
    1) 新版（行式）：依据参数_中间数据 = [{项目名称, 数据明细{...}}, ...]
    2) 旧版（列式）：依据参数 = {项目: {列名: [..] 或 单值}, ...}

    输出：List[Dict]，每个 dict 表示一个“测量点/行”，至少包含 param_name 字段。
    """
    out: List[Dict[str, Any]] = []

    # -------------------------
    # 1) 优先：行式结构
    # -------------------------
    rows = cert_root.get("依据参数_中间数据")
    if isinstance(rows, list) and rows:
        for item in rows:
            if not isinstance(item, dict):
                continue
            project = (item.get("项目名称") or item.get("测量值") or "").strip()
            details = item.get("数据明细")

            if not project or not isinstance(details, dict) or not details:
                continue

            rec = {"param_name": project}
            has_valid = False
            for k, v in details.items():
                if k is None:
                    continue
                kk = str(k).strip()
                if not kk:
                    continue
                vv = "" if v is None else str(v).strip()
                rec[kk] = vv
                if vv and vv.lower() != "none":
                    has_valid = True

            # if has_valid:
            #     out.append(rec)
            out.append(rec)  # ✅ 不管有没有有效数据都加进来，交给后续逻辑处理

        if out:
            return out  # ✅ 行式能解析到就直接返回

    # -------------------------
    # 2) 回退：旧的列式结构（你原来的逻辑）
    # -------------------------
    basis_params = cert_root.get("依据参数", {})
    if isinstance(basis_params, list):
        print("⚠️ 警告：'依据参数' 是列表结构，当前不处理")
        return []

    if not isinstance(basis_params, dict) or not basis_params:
        print("⚠️ 警告：'依据参数' 为空或未找到（也没有 '依据参数_中间数据'）")
        return []

    for project_name, fields_dict in basis_params.items():
        if not isinstance(fields_dict, dict):
            continue

        row_count = 0
        for _, val in fields_dict.items():
            if isinstance(val, list):
                row_count = max(row_count, len(val))
        if row_count == 0:
            row_count = 1

        for i in range(row_count):
            rec = {"param_name": project_name}
            has_valid_data = False

            for field_key, field_val in fields_dict.items():
                if isinstance(field_val, list):
                    val = str(field_val[i]) if i < len(field_val) else ""
                else:
                    val = str(field_val)

                val = "" if val is None else str(val).strip()
                rec[field_key] = val
                if val and val.lower() != "none":
                    has_valid_data = True

            if has_valid_data:
                out.append(rec)

    return out



# ===================== 3. 核心 Agent 流程 =====================

def run_agentic_batch(client: OpenAI, batch_params: List[Dict], kb_items: List[Dict],
                      instrument: str, criterion: str, cfg: Any) -> str:

    # ================= 🚀 优化 1：KB 列表范围过滤 =================
    # 在传递给 LLM 之前，先通过程序化方法过滤掉明显不匹配的频率范围条目
    # 只保留与测量点频率匹配的 KB 条目
    filtered_kb_items = _filter_kb_entries_by_frequency(kb_items, batch_params)
    filtered_kb_items, semantic_audit_lines = _apply_semantic_basis_prefilter(filtered_kb_items, batch_params)
    print(f"✅ KB 条目过滤：从 {len(kb_items)} 条过滤到 {len(filtered_kb_items)} 条")
    if semantic_audit_lines:
        print("🧭 语义预筛摘要:")
        for line in semantic_audit_lines[:8]:
            print(f"  {line}")
        if len(semantic_audit_lines) > 8:
            print(f"  ... 其余 {len(semantic_audit_lines) - 8} 条未展开")

    # ================= 🚀 优化 2：KB 列表重排序 =================
    # 将 KB 条目按“被测量名称”排序，确保同名参数（如不同频段的电平）在列表中紧挨着出现
    # 这样 LLM 在阅读时能一次性看到所有可能的范围选项，防止“看到第一个就停”
    sorted_kb_items = sorted(filtered_kb_items, key=lambda x: x['measured'])

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
        "   - **典型错误案例警告（频率范围匹配）**：\n"
        "     * 测量点：`-5 dBm`\n"
        "     * 错误KB：范围 `-90 ～ -50 dBm` (因为 -5 > -50，不在此范围内)\n"
        "     * 正确KB：范围 `-50 ～ 0 dBm` (因为 -5 在此范围内)\n"
        "     * **如果你选择了错误的KB并声称‘范围：Pass’，这是严重逻辑错误！**\n"
        "   - **频率范围匹配特别注意**：\n"
        "     * 必须正确解析频率单位（Hz、kHz、MHz、GHz）的量级关系\n"
        "     * 1 GHz = 1000 MHz，1 MHz = 1000 kHz，1 kHz = 1000 Hz\n"
        "     * 在匹配时，必须将所有频率值转换为相同单位后再比较\n"
        "     * 对于 `>20 MHz～2 GHz` 这样的范围，要正确理解为大于20MHz且小于等于2GHz\n"
        
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
        "     * **案例**：测量点 0dBm, Cert_U=0.16。KB_A(0~30, U=0.22), KB_B(-50~0, U=0.16)。因为 0.16 >= 0.22 不成立，而 0.16 >= 0.16 成立，所以应优先选择 KB_B。\n"
        "2. **双重范围匹配 (Dual Range Matching) - 严厉警告！**：\n"
        "   - 许多射频参数（如电平、失真、相位噪声）同时受 **频率** 和 **数值(幅度)** 的限制。\n"
        "   - **必须同时满足两个条件**才能选择该 KB 条目：\n"
        "     * 条件 A: 测量点的【频率】在 KB 的频率范围内。\n"
        "     * 条件 B: 测量点的【数值】在 KB 的数值范围内。\n"
        "   - **错误案例**：测量点 `2300 MHz, -10 dBm`。\n"
        "     * 错误KB: `(-80~-50)dBm (1.3~26.5 GHz)` -> 虽然频率匹配，但数值 -10 不在 -80~-50 内 -> **严禁选择！**\n"
        "     * 正确KB: `(-10~10)dBm (1.3~26.5 GHz)` -> 频率匹配，数值 -10 也在 -10~10 内 -> **正确！**\n"
        "   - 如果一条KB仅频率匹配但数值不匹配，**跳过它**，继续寻找下一条！\n"
        "3. **范围核验必须调用工具 (Critical!)**：\n"
        "   - **严禁口算范围判断！** 必须调用 `verify_range_logic` 工具进行范围核验。\n"
        "   - 即使范围看起来很明显（如 100s vs 10s），也必须通过工具确认。\n"
        "   - 工具会正确处理闭区间判断（包括边界值）。\n"
        "4. **单位换算 (Critical)**：\n"
        "   - 若测量点单位（如 dBm, Vrms）与 KB 单位（如 V, Vpp）不一致，**必须先调用工具** `unit_convert_tool` 将其转换为 KB 单位。\n"
        "   - **严禁口算**！必须使用工具转换后的数值进行范围判断。\n"
        "5. **常规情况**：\n"
        "   - 调用 `verify_range_logic` 工具确认测量点是否在 KB 范围内。\n"
        "   - **原则**：采用【闭区间】。若 测量值 = 范围上限 或 测量值 = 范围下限，均视为 Pass。\n"
        "6. **特殊映射（必须优先执行）**：\n"
        "   - **幅度平坦度**：若 KB 无此项，将其映射为“幅度”。\n"
        "   - **紫外能量 (Energy vs Irradiance)**：\n"
        "     - 场景：证书为能量 (J/cm², mJ/cm²)，KB 为辐照度 (W/cm², mW/cm²)。\n"
        "     - **操作**：**禁止**比对数值大小（因物理量纲不同）。\n"
        "     - **判定**：只要波段匹配（如同为 UV-365），直接判定 **Pass (Physics Mapped)**，并在说明中备注“基于辐照度能力覆盖能量参数”。\n\n"

        "### 第二步：误差判定 (Error Check)\n"
        "   - **重要说明**：证书的“允许范围”、“合格范围”或“Limit”字段（如 ≤-15）与“允许误差”同列展示，优先写入【允许误差】列。\n"
        "   - 若证书未提供该项、但 KB 中提供了允许误差信息，则可使用 KB 限值；若两侧都未提供，则该列填 N/A，且跳过误差核验（视为 Pass）。\n"

        "   - 若证书有明确的“允许误差”或“限值”：**必须调用工具** `verify_error_logic` 进行比对。\n"
        "   - **注意**：“修正系数”(Correction Factor) 不是误差，若无明确误差值，跳过此步（视为 Pass）。\n\n"

        "### 第三步：不确定度判定 (Uncertainty Check)\n"
        "   - **前置判断**：首先检查证书是否提供了有效的不确定度数值。\n"
        "   - **情况1：证书未提供不确定度** (如数值为 0, None, N/A, /, 空白)：\n"
        "     - **不要调用工具**，直接跳过此判定。\n"
        "     - 判定结果不受此影响（不要因此判 Failed），但必须在【说明】栏备注“证书未提供不确定度，跳过比对”。\n"
        "   - **情况2：证书和 KB 均有不确定度**：\n"
        "     - **必须调用工具** `verify_uncertainty_logic`。\n"
        "     - **禁止口算**！必须依赖工具返回的结果。\n"
        "     - 工具可能返回三种状态：\n"
        "       * PASS：Cert_U >= KB_U，判定为通过\n"
        "       * FAIL：Cert_U < KB_U，判定为失败\n"
        "       * REVIEW：不确定度单位不匹配且无法转换，需要人工核验\n"
        "     - 当工具返回REVIEW时，【判定】列填REVIEW，【说明】列备注工具返回的原因，并标记为需要人工复核。\n\n"
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

    def _force_finalize(current_messages: List[Dict[str, Any]]) -> str:
        finalize_messages = list(current_messages)
        finalize_messages.append({
            "role": "user",
            "content": (
                "停止继续调用工具。现在必须直接输出最终 Markdown 结果。\n"
                "要求：\n"
                "1. 只输出最终结果，不要继续分析过程。\n"
                "2. 每个参数必须输出一个表格，列为：序号, 点位, 测量点, KB编号, 证书匹配项, 范围, 证书误差, 允许误差, 证书U, KB_U, 判定, 说明。\n"
                "3. 判定和说明必须严格沿用前面工具返回的结果，禁止改写工具结论。\n"
                "4. 如果已有足够工具结果，优先生成完整表格；不要再请求补充信息。"
            )
        })
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=finalize_messages,
                temperature=0.0,
            )
            content = response.choices[0].message.content
            if content:
                return content
        except Exception as e:
            return f"> 🚨 Batch 最终收口失败: {e}"
        return "> ⚠️ 超过最大交互轮数，且最终收口未生成内容。"

    # ================= 核心修改：支持多轮工具调用的循环 =================
    MAX_TURNS = 15  # 优化：从 50 轮减少到 15 轮，避免无限循环
    turn_count = 0

    # ✅ 获取 UI 配置参数
    model_name = getattr(cfg, 'MODEL', 'deepseek-chat')
    temp_val = getattr(cfg, 'TEMPERATURE', 0.1)

    for turn in range(MAX_TURNS):
        turn_count += 1
        try:
            start_call_time = time.time()
            response = client.chat.completions.create(
                model=model_name, # ✅ 使用传入的配置
                messages=messages,
                tools=TOOLS_SCHEMA,
                tool_choice="auto",

                temperature=temp_val # ✅ 使用传入的配置
            )
            call_duration = time.time() - start_call_time
            msg = response.choices[0].message
            print(f">>> LLM call {turn+1} ({call_duration:.1f}s)", flush=True)
        except Exception as e:
            return f"> 🚨 API 请求失败: {e}"

        tool_calls = msg.tool_calls

        # 情况 A: 模型想要调用工具
        if tool_calls:
            if turn_count % 2 == 0:  # 优化：每 2 轮打印一次，减少输出
                print(f">>> 第 {turn+1} 轮工具调用", flush=True)
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

                elif fname == "verify_range_logic":
                    tool_res = verify_range_logic(args.get("measure_val"), args.get("range_str"))
                    try:
                        r = json.loads(tool_res)
                        enforcement_notes.append(
                            f"范围核验: {args.get('measure_val')} -> {r.get('status')} ({r.get('reason')})")
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
            # ✅ 强制回灌：要求模型在最终表格里“逐行照抄”工具 status
            if enforcement_notes:
                messages.append({
                    "role": "user",
                    "content": (
                        "下面是工具的最终判定结果（必须逐行照抄到表格的【判定】和【说明】，"
                        "禁止自行推导/口算/改写不等式）：\n" +
                        "\n".join(enforcement_notes)
                    )
                })

            # --- 循环继续 ---
            continue


        # 情况 B: 模型没有调用工具，直接返回了文本（最终报告）
        else:
            return msg.content

    return _force_finalize(messages)


def run_llm_mode(json_file: str, cfg, stop_event=None,embedder_obj=None) -> str:
    """
    执行 LLM 参数核验的主流程 (支持并发与中断)
    """

    # 🛑 0.【关键】初始刹车检查
    if stop_event and stop_event.is_set():
        print("🛑 [ParamCheck] 任务在初始化阶段被终止")
        return "⚠️ 核验任务已由用户在初始化阶段取消。"

    # 直接使用 get_app_config() 获取配置，避免任何路径编码问题
    app_config = get_app_config()
    current_top_k = getattr(cfg, 'TOPK', app_config.topk)
    max_w = getattr(cfg, 'max_workers', app_config.max_workers)

    data = json.load(open(json_file, "r", encoding="utf-8"))
    try:
        root = data["properties"]["证书列表"]["items"]["properties"]
    except KeyError:
        return "❌ JSON 结构错误"

    instrument_name = root.get("INSTRUMENT_NAME") or root.get("仪器名称") or "N/A"
    criteria_list = root.get("校准依据", []) or ["N/A"]
    all_cert_params = collect_certificate_params(data)

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
        print(f"🧠 [ParamCheck] 正在加载语义模型: {app_config.embed_model_path}")
        from sentence_transformers import SentenceTransformer

        embedder = SentenceTransformer(app_config.embed_model_path)

    # 直接使用 app_config 获取数据库路径，避免编码问题
    from kb.chroma_client import get_collection
    collection = get_collection(app_config.cnas_db_dir, app_config.cnas_collection)
 
    from llm.client import create_openai_client

    client = create_openai_client(api_key=app_config.api_key, api_base=app_config.api_base)

    report_lines = [
        "# CNAS 智能核验报告 (Agentic Mode - Parallel)",
        f"- 证书编号: {root.get('证书编号', 'N/A')}",
        f"- 仪器: {instrument_name}",
        f"- 时间: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 参数核验版本: {_build_param_check_version_stamp()}",
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
            collection,
            embedder,
            instrument_name,
            criterion,
            topk=current_top_k  # <--- 修改在这里
        )
        if LAST_QUERY_ERROR:
            report_lines.append("### ❌ 核验终止（知识库访问失败）")
            report_lines.append(
                f"- 证书依据: {criterion}\n"
                f"- 结果: 参数核验所需的 Chroma 向量库无法正常访问，当前不是“无匹配数据”，而是“索引读取失败”。\n"
                f"- 诊断信息: {LAST_QUERY_ERROR}\n"
                f"- 处理建议: 请检查/重建 `{app_config.cnas_db_dir}` 下的向量库索引后再重试。"
            )
            report_lines.append("\n---\n")
            continue
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
            preview_count = min(len(kb_items), 10)
            print(f"📄 [Preview] 检索到的知识库内容（预览 {preview_count} 条，实际核验使用全部 {len(kb_items)} 条）:")
            print(f"   依据: {criterion}")
            print("-" * 60)

            # 控制台只预览前几条，避免刷屏；后续核验仍使用该依据下的全部条目
            for i, item in enumerate(kb_items[:preview_count], 1):
                # 获取信息，处理过长文本
                std = item.get('file_code', 'N/A')
                measured = item.get('measured', 'N/A')
                rng = item.get('measure_range_text', '-')
                # 如果范围文本太长，截断一下
                if len(rng) > 50: rng = rng[:47] + "..."

                print(f"  {i:02d}. [{std}] {measured} | 范围: {rng}")

            if len(kb_items) > preview_count:
                print(f"  ... 其余 {len(kb_items) - preview_count} 条未在控制台展开，但已纳入后续核验。")

            print("=" * 60 + "\n")
        else:
            print(f"\n⚠️ [Warning] 未检索到关于 '{criterion}' 的知识库条目！\n")
        # ==============================================================

        # ================= 并发核心逻辑开始 =================

        # 优化 Batch 划分策略：确保同一个参数的所有测量点被分到同一个Batch中
        param_groups = {}
        for param in all_cert_params:
            param_name = param.get('param_name', 'unknown')
            if param_name not in param_groups:
                param_groups[param_name] = []
            param_groups[param_name].append(param)

        # 重新生成 Batches
        batches = []
        batch_param_names_map: Dict[int, List[str]] = {}
        current_batch = []

        for param_name, points in param_groups.items():
            if len(current_batch) + len(points) > app_config.batch_size:
                batches.append(current_batch)
                batch_param_names_map[len(batches)] = _unique_param_names(current_batch)
                current_batch = []
            current_batch.extend(points)

        if current_batch:
            batches.append(current_batch)
            batch_param_names_map[len(batches)] = _unique_param_names(current_batch)

        total_batches = len(batches)

        # 性能优化：动态调整线程池大小
        if max_w > 5:
            max_w = min(max_w, 5)
            print(f"⚠️ 自动优化线程数：从 {max_w} 减少到 5，避免API限流")

        print(f"🚀 启动并发处理: 共 {total_batches} 个批次，线程数: {max_w}")
        print(f"📊 参数分组: {list(param_groups.keys())}")

        # 性能监控：记录每个 batch 的开始时间
        batch_start_time = [time.time() for _ in range(total_batches + 1)]

        # 使用线程池
        with ThreadPoolExecutor(max_workers=max_w) as executor:
            future_to_index = {}

            # 提交任务
            for idx, batch in enumerate(batches):
                batch_start_time[idx + 1] = time.time()
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
                        start_time = batch_start_time[idx]
                        content = future.result(timeout=600)  # 10分钟超时
                        duration = time.time() - start_time

                        content = enforce_kb_missing_fail(content)  # ✅ 兜底强制：KB缺失行 => FAIL
                        content = enforce_point_id(content)
                        # ✅ 加这一行
                        content = enforce_uncertainty_by_tool(content)
                        content = enforce_batch_summary_from_table(
                            content,
                            expected_param_names=batch_param_names_map.get(idx, []),
                        )

                        results_map[idx] = content
                        print(f"   ✅ Batch {idx}/{total_batches} 完成 ({duration:.1f}s)")
                    except Exception as e:
                        error_msg = f"> 🚨 Batch {idx} 失败：{e}"
                        print(error_msg)
                        results_map[idx] = error_msg
                        # 如果是严重错误，也可以选择在这里 return 终止整个流程

            except Exception as e:
                print(f"❌ 线程池异常: {e}")

        # ================= 并发结束，先收集所有表格数据 =================

        # 🛑 再次检查，防止组装报告时浪费时间
        if stop_event and stop_event.is_set(): return "⚠️ 任务已终止"

        print("📊 正在整理所有结果并去重...")

        # 收集所有 Batch 的结果
        all_batch_contents = []
        for i in range(1, total_batches + 1):
            all_batch_contents.append(results_map.get(i, "> 任务被取消或执行异常"))

        # 提取和解析所有表格
        param_to_table = _collect_param_tables(all_batch_contents, batch_expected_params=batch_param_names_map)

        # ================= 最终报告生成 =================
        report_lines.append("\n---\n\n# 📋 最终依据参数核验结果汇总")
        report_lines.append("## 核验范围")
        report_lines.append(f"- 仪器: {instrument_name}")
        report_lines.append(f"- 依据: {criterion}")
        report_lines.append(f"- 参数量: {len(param_groups)} 个")
        report_lines.append(f"- 总测量点数: {len(all_cert_params)} 个")
        report_lines.append("")

        # 统计结果
        pass_count = 0
        fail_count = 0
        total_count = 0
        kb_missing_fail_count = 0
        real_fail_count = 0

        for param_name, table_lines in param_to_table.items():
            # 构建包含参数标题和表格的Markdown片段
            param_md = f"### 参数：{param_name}\n" + "\n".join(table_lines)
            # 再次应用后处理函数，确保业务规则被正确执行
            param_md_processed = enforce_uncertainty_by_tool(param_md)

            # 将处理后的内容添加到报告中
            report_lines.extend(param_md_processed.splitlines())
            report_lines.append("")

            # 重新解析处理后的表格用于统计
            processed_table_lines = []
            in_processed_table = False
            for line in param_md_processed.splitlines():
                if line.startswith("|"):
                    if not in_processed_table:
                        in_processed_table = True
                    processed_table_lines.append(line)
                elif in_processed_table:
                    break

            param_summary = _summarize_table_statuses(processed_table_lines or table_lines)
            pass_count += param_summary["pass"]
            fail_count += param_summary["fail"]
            total_count += param_summary["total"]
            kb_missing_fail_count += param_summary["kb_missing_fail"]
            real_fail_count += param_summary["real_fail"]

        report_lines.append("---")
        report_lines.append("## 📊 最终核验统计")
        report_lines.append(f"- **通过(PASS)**: {pass_count} 个测量点")
        report_lines.append(f"- **失败(FAIL)**: {fail_count} 个测量点")
        # 计算需要人工复核的数量
        review_count = 0
        for param_name, table_lines in param_to_table.items():
            param_summary = _summarize_table_statuses(table_lines)
            review_count += param_summary.get("review", 0)
        if review_count > 0:
            report_lines.append(f"- **需人工复核(REVIEW)**: {review_count} 个测量点")
        report_lines.append(f"- **总数**: {total_count} 个测量点")
        report_lines.append("")
        report_lines.insert(-1, f"- **KB未覆盖型失败**: {kb_missing_fail_count} 个测量点")
        report_lines.insert(-1, f"- **真实核验失败**: {real_fail_count} 个测量点")

        pending_count = max(len(all_cert_params) - total_count, 0)
        if pending_count > 0:
            report_lines.append(f"- **未完成**: {pending_count} 个测量点")
            report_lines.append("")

        if total_count > 0:
            pass_rate = (pass_count / total_count) * 100
            report_lines.append(f"- **通过率**: {pass_rate:.1f}%")

        # 按原逻辑保留 Batch 详细报告（可选，这里保留用于调试）
        report_lines.append("\n---\n\n# 📄 Batch 详细报告")
        for i in range(1, total_batches + 1):
            report_lines.append(f"#### 📌 Batch {i}")
            report_lines.append(results_map.get(i, "> 任务被取消或执行异常"))
            report_lines.append("\n---\n")

    return "\n".join(report_lines)



# def main():
#     # 请修改此处的文件名
#     BASE_DIR = Config._app.local_json_dir
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
    BASE_DIR = Config._app.local_json_dir
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
