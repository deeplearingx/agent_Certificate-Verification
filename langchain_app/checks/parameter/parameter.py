#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
参数与不确定度核验模块 - 主入口文件

与原始 param_check.py 功能兼容，使用统一的 LangChain 架构
"""

import json
import re
import time
import hashlib
import math
import importlib
import logging
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Sequence, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

# 本地导入
from langchain_app.utils import get_app_config, AppConfig, coerce_app_config
from langchain_app.core import LLMClient, VerificationReport
from langchain_app.core.llm_client import describe_llm_exception
from . import parser_core as _parser_core_module
from . import parser_domain as _parser_domain_module
from . import retrieval as _retrieval_module
from . import semantic as _semantic_module
from . import rules as _rules_module
from . import planner as _planner_module
from . import selector as _selector_module
from . import validator as _validator_module
from . import reporter as _reporter_module
from .parser_core import (
    parse_value_with_unit,
    extract_basis_code,
    norm_code,
    parse_unicode_sci_number,
    _extract_value_token,
    _normalize_unit_text,
    _unit_multiplier_from_text,
    VALUE_TOKEN_PATTERN,
    SUPERSCRIPT_MAP,
    CANONICAL_UNIT_MAP,
    EXACT_UNIT_MULTIPLIERS,
    UNIT_MULTIPLIERS,
    ATOMIC_LENGTH_UNITS,
    PREFERRED_RANGE_VALUE_PATTERNS,
    RANGE_TOOL_VALUE_PATTERNS,
    RANGE_TOOL_VALUE_PATTERNS_SAFE,
)
from .parser_domain import (
    _parse_frequency_range,
    _parse_frequency_point_list,
    _is_power_unit,
    _is_voltage_unit,
)
from .contracts import (
    contract_source_header,
    contract_source_value,
    infer_semantic_subtype,
    normalize_parameter_contract,
    subtype_agent_eligible,
    subtype_text_option,
    subtype_comparison_mode,
    subtype_probe_role,
)
from .retrieval import (
    search_calibration_data,
    select_best_kb_entries,
    filter_kb_entries,
    parse_kb_entry,
)
from .semantic import (
    infer_param_semantics,
    KbCapability,
    select_basis_with_audit,
    semantic_filter_basis_entries,
    _extract_frequency_hz_from_text,
)
from .planner import (
    SemanticAuditorRequestResult,
    assess_replay_improvement,
    parameter_semantic_auditor_candidate_limit,
    parameter_semantic_auditor_confidence_threshold,
    parameter_semantic_auditor_max_calls,
    parameter_semantic_auditor_mode,
    build_candidate_summaries,
    build_raw_field_summary,
    live_mode_allows_takeover,
    model_dump_compat,
    planner_candidate_limit,
    planner_mode,
    request_semantic_auditor_decision,
    PlannerRequestResult,
    request_planner_decision,
    should_trigger_planner,
    validate_semantic_auditor_decision,
    validate_planner_decision,
)
from .rules import FALLBACK_SCORE_RULES
from .rules import SEMANTIC_RULE_REGISTRY, SEMANTIC_TARGET_WHITELIST
from .validator import (
    extract_primary_unit_token,
    verify_range_logic,
    verify_error_logic,
    verify_uncertainty_logic,
)
from .reporter import (
    build_param_table,
    build_batch_summary_table,
    enforce_kb_missing_fail,
    enforce_uncertainty_by_tool,
    enforce_batch_summary_from_table,
    extract_param_names_from_table,
)


LAST_QUERY_ERROR: Optional[str] = None
logger = logging.getLogger(__name__)
_RUNTIME_BINDING_LOCK = Lock()
_RUNTIME_DEPENDENCY_MODULES = {
    "parser_core": _parser_core_module,
    "parser_domain": _parser_domain_module,
    "retrieval": _retrieval_module,
    "semantic": _semantic_module,
    "rules": _rules_module,
    "planner": _planner_module,
    "selector": _selector_module,
    "validator": _validator_module,
    "reporter": _reporter_module,
}
_RUNTIME_BINDING_SYMBOLS = {
    "parser_core": (
        "parse_value_with_unit",
        "extract_basis_code",
        "norm_code",
        "parse_unicode_sci_number",
        "_extract_value_token",
        "_normalize_unit_text",
        "_unit_multiplier_from_text",
        "VALUE_TOKEN_PATTERN",
        "SUPERSCRIPT_MAP",
        "CANONICAL_UNIT_MAP",
        "EXACT_UNIT_MULTIPLIERS",
        "UNIT_MULTIPLIERS",
        "ATOMIC_LENGTH_UNITS",
        "PREFERRED_RANGE_VALUE_PATTERNS",
        "RANGE_TOOL_VALUE_PATTERNS",
        "RANGE_TOOL_VALUE_PATTERNS_SAFE",
    ),
    "parser_domain": (
        "_parse_frequency_range",
        "_parse_frequency_point_list",
    ),
    "retrieval": (
        "search_calibration_data",
        "select_best_kb_entries",
        "filter_kb_entries",
        "parse_kb_entry",
    ),
    "semantic": (
        "infer_param_semantics",
        "KbCapability",
        "select_basis_with_audit",
        "semantic_filter_basis_entries",
        "_extract_frequency_hz_from_text",
    ),
    "rules": (
        "FALLBACK_SCORE_RULES",
        "SEMANTIC_RULE_REGISTRY",
        "SEMANTIC_TARGET_WHITELIST",
    ),
    "planner": (
        "SemanticAuditorRequestResult",
        "build_candidate_summaries",
        "build_raw_field_summary",
        "live_mode_allows_takeover",
        "model_dump_compat",
        "parameter_semantic_auditor_candidate_limit",
        "parameter_semantic_auditor_confidence_threshold",
        "parameter_semantic_auditor_max_calls",
        "parameter_semantic_auditor_mode",
        "planner_candidate_limit",
        "planner_mode",
        "request_semantic_auditor_decision",
        "request_planner_decision",
        "should_trigger_planner",
        "validate_semantic_auditor_decision",
        "validate_planner_decision",
    ),
    "validator": (
        "verify_range_logic",
        "verify_error_logic",
        "verify_uncertainty_logic",
    ),
    "reporter": (
        "build_param_table",
        "build_batch_summary_table",
        "enforce_kb_missing_fail",
        "enforce_uncertainty_by_tool",
        "enforce_batch_summary_from_table",
        "extract_param_names_from_table",
    ),
}
_RUNTIME_RELOAD_ORDER = (
    "parser_core",
    "parser_domain",
    "rules",
    "planner",
    "selector",
    "semantic",
    "retrieval",
    "validator",
    "reporter",
)
_RUNTIME_SOURCE_SIGNATURE: Optional[Tuple[Tuple[str, int], ...]] = None
PARAM_RESULT_TABLE_HEADER = [
    "序号",
    "点位",
    "测量点",
    "测试条件",
    "KB编号",
    "KB条目",
    "证书匹配项",
    "范围",
    "证书误差",
    "允许误差",
    "证书U",
    "KB_U",
    "判定",
    "说明",
]

STANDARD_PARAMETER_PARSE_SOURCES = frozenset({"html_table", "html_table_inline"})


@dataclass
class EvaluationRecord:
    basis_code: str
    batch_label: str
    batch_index: int
    row_index: int
    cert_index: int
    param_name: str
    point_key: str
    match_value: str
    point_value: str
    status: str
    reason: str
    semantic_target: str = ""
    semantic_subtype: str = ""
    axis_family: str = ""
    axis_value: str = ""
    selected_candidate_id: str = ""
    candidate_target: str = ""
    candidate_primary_quantity: str = ""
    selected_target_relation: str = ""
    range_result: Dict[str, Any] = field(default_factory=dict)
    error_result: Dict[str, Any] = field(default_factory=dict)
    u_result: Dict[str, Any] = field(default_factory=dict)
    anomaly_flags: Tuple[str, ...] = field(default_factory=tuple)
    review_reason_type: str = ""
    planner_summary: Dict[str, Any] = field(default_factory=dict)
    semantic_auditor_summary: Dict[str, Any] = field(default_factory=dict)
    display_fields: Dict[str, str] = field(default_factory=dict)


@dataclass
class ParamCheckRow:
    basis_code: str
    batch_label: str
    batch_index: int
    row_index: int
    cert_index: int
    param_name: str
    point_key: str
    match_value: str
    point_value: str
    status: str
    reason: str
    kb_code: str
    kb_item: str
    range_text: str
    cert_error: str
    limit_text: str
    cert_u: str
    kb_u: str
    raw_row: Dict[str, str]
    review_reason_type: str = ""
    evaluation_record: Optional[EvaluationRecord] = None


@dataclass
class BatchExecutionResult:
    markdown: str
    rows: List[ParamCheckRow] = field(default_factory=list)
    planner_traces: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class PlannerExecutionResult:
    selection_result: Any
    selected_candidate: Optional[Any]
    selected_kb: Optional[KbCapability]
    selection_context: str
    note: str = ""
    trace: Optional[Dict[str, Any]] = None


@dataclass
class SemanticAuditorExecutionResult:
    selection_result: Any
    selected_candidate: Optional[Any] = None
    selected_kb: Optional[KbCapability] = None
    applied: bool = False
    note: str = ""
    trace: Optional[Dict[str, Any]] = None


@dataclass
class LLMAuditorBudget:
    max_calls: int
    used_calls: int = 0
    lock: Lock = field(default_factory=Lock)

    def try_consume(self) -> bool:
        with self.lock:
            if self.used_calls >= self.max_calls:
                return False
            self.used_calls += 1
            return True


def _runtime_dependency_paths() -> List[Path]:
    paths: List[Path] = [Path(__file__).resolve()]
    for module in _RUNTIME_DEPENDENCY_MODULES.values():
        file_path = getattr(module, "__file__", None)
        if not file_path:
            continue
        path = Path(file_path).resolve()
        if path not in paths:
            paths.append(path)
    return paths


def _runtime_source_signature() -> Tuple[Tuple[str, int], ...]:
    signature: List[Tuple[str, int]] = []
    for path in _runtime_dependency_paths():
        try:
            signature.append((str(path), path.stat().st_mtime_ns))
        except FileNotFoundError:
            continue
    return tuple(signature)


def _rebind_runtime_symbols() -> None:
    namespace = globals()
    for module_name, symbol_names in _RUNTIME_BINDING_SYMBOLS.items():
        module = _RUNTIME_DEPENDENCY_MODULES[module_name]
        for symbol_name in symbol_names:
            namespace[symbol_name] = getattr(module, symbol_name)


def _refresh_runtime_dependency_bindings(force: bool = False) -> None:
    """
    长驻进程里每次执行前刷新内部依赖绑定，避免出现
    parameter.py 已加载但 selector/validator 仍是旧版本的混合状态。
    """
    global _RUNTIME_SOURCE_SIGNATURE

    current_signature = _runtime_source_signature()
    if not force and current_signature == _RUNTIME_SOURCE_SIGNATURE:
        return

    with _RUNTIME_BINDING_LOCK:
        current_signature = _runtime_source_signature()
        if not force and current_signature == _RUNTIME_SOURCE_SIGNATURE:
            return

        for module_name in _RUNTIME_RELOAD_ORDER:
            module = _RUNTIME_DEPENDENCY_MODULES[module_name]
            _RUNTIME_DEPENDENCY_MODULES[module_name] = importlib.reload(module)

        _rebind_runtime_symbols()
        _RUNTIME_SOURCE_SIGNATURE = _runtime_source_signature()


def _coerce_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, str):
        text = value.strip()
        return text or default
    if isinstance(value, (int, float)):
        return str(value)
    return str(value)


def _escape_markdown_table_cell(value: Any) -> str:
    text = _coerce_text(value, "")
    if not text:
        return ""
    text = text.replace("\\", "\\\\")
    text = text.replace("\r\n", "<br>").replace("\n", "<br>").replace("\r", "<br>")
    text = text.replace("|", "\\|")
    return text
    if isinstance(value, list):
        parts = [_coerce_text(item) for item in value]
        joined = "; ".join(part for part in parts if part)
        return joined or default
    if isinstance(value, dict):
        for key in ("value", "text", "raw", "content", "data"):
            text = _coerce_text(value.get(key))
            if text:
                return text
        parts = []
        for key in ("type", "value"):
            item = value.get(key)
            if item not in (None, ""):
                parts.append(f"{key}={item}")
        return ", ".join(parts) if parts else default
    text = str(value).strip()
    return text or default


def _normalize_key_for_match(text: Any) -> str:
    return re.sub(r"\s+", "", _coerce_text(text).lower())


def _normalized_fields_for_llm(param: Dict[str, Any]) -> Dict[str, str]:
    normalized = {}
    contract = _get_parameter_contract(param)
    for key, value in contract.items():
        if key in {"schema_version", "source_headers", "needs_disambiguation"}:
            continue
        text = _coerce_text(value)
        if text:
            normalized[key] = text
    for key, value in _get_normalized_mapping(param).items():
        text = _coerce_text(value)
        if text:
            normalized[key] = text

    extracted_fields = {
        "measure_value": _extract_param_measure_value(param),
        "reference_value": _extract_param_reference_value(param),
        "error_value": _extract_param_error_value(param),
        "point_value": _extract_param_point_value(param),
        "limit_value": _extract_param_limit_value(param),
        "cert_u": _extract_param_cert_u(param),
    }
    for key, value in extracted_fields.items():
        text = _coerce_text(value)
        if text:
            normalized[key] = text
    return normalized


def _planner_raw_field_source(param: Dict[str, Any]) -> Dict[str, Any]:
    source = _get_detail_mapping(param)
    if source:
        return source
    if not isinstance(param, dict):
        return {}
    return {
        key: value
        for key, value in param.items()
        if not str(key).startswith("__") and not isinstance(value, (dict, list, tuple))
    }


def _planner_trace_output_path(json_file: str, cfg: AppConfig) -> Path:
    return cfg.final_reports_dir / "_planner_traces" / f"Report_{Path(json_file).stem}.json"


def _write_planner_trace_sidecar(
    *,
    json_file: str,
    cfg: AppConfig,
    traces: List[Dict[str, Any]],
) -> Optional[Path]:
    if not traces:
        return None

    output_path = _planner_trace_output_path(json_file, cfg)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "json_file": json_file,
        "planner_mode": planner_mode(cfg),
        "trace_count": len(traces),
        "traces": traces,
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def _build_planner_trace_id(
    *,
    criterion: str,
    batch_index: int,
    cert_index: int,
    param_name: str,
) -> str:
    raw = "|".join(
        [
            _coerce_text(extract_basis_code(criterion) or criterion or "N/A"),
            str(batch_index),
            str(cert_index),
            _coerce_text(param_name) or "unknown",
        ]
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _merge_condition_text(existing: str, planner_condition_text: str) -> str:
    parts: List[str] = []
    seen = set()
    for raw in (existing, planner_condition_text):
        for piece in _coerce_text(raw).split(";"):
            text = _coerce_text(piece)
            if not text:
                continue
            norm = _normalize_key_for_match(text)
            if norm in seen:
                continue
            seen.add(norm)
            parts.append(text)
    return "; ".join(parts)


def _validate_planner_bound_value(target: str, value: str) -> bool:
    text = _coerce_text(value)
    if not text:
        return False
    if target in {"point_value", "condition_value", "signal_condition", "modulation_condition"}:
        return True
    if target == "frequency_condition":
        return _extract_frequency_hz_from_text(text) is not None
    parsed, _ = parse_value_with_unit(text, keep_sign=True)
    if parsed is not None:
        return True
    return _extract_frequency_hz_from_text(text) is not None


def _is_missing_like_planner_binding_value(value: Any) -> bool:
    text = _coerce_text(value).strip()
    if not text:
        return True
    normalized = re.sub(r"\s+", "", text).lower()
    return normalized in {
        "n/a",
        "na",
        "n\\a",
        "none",
        "null",
        "nil",
        "未知",
        "未提供",
        "无",
        "--",
        "—",
    }


def _apply_planner_field_bindings(
    *,
    decision: Any,
    param: Dict[str, Any],
) -> Tuple[bool, str, Dict[str, str], str]:
    raw_source = _planner_raw_field_source(param)
    if not raw_source:
        return False, "planner raw field source unavailable", {}, ""

    bindings = model_dump_compat(decision).get("field_bindings") or {}
    if not bindings:
        return True, "planner field bindings empty", {}, ""

    bound_values: Dict[str, str] = {}
    condition_parts: List[str] = []
    skipped_headers: List[str] = []
    for target, source_header in bindings.items():
        value = _coerce_text(raw_source.get(source_header))
        if _is_missing_like_planner_binding_value(value):
            skipped_headers.append(f"{target} <- {source_header}")
            continue
        if not _validate_planner_bound_value(target, value):
            return False, f"planner field binding invalid: {target} <- {source_header}", {}, ""
        bound_values[target] = value
        if target == "condition_value":
            condition_parts.append(f"条件: {value}")
        elif target == "frequency_condition":
            condition_parts.append(f"频率: {value}")
        elif target == "offset_condition":
            condition_parts.append(f"偏置: {value}")
        elif target == "signal_condition":
            condition_parts.append(f"信号: {value}")
        elif target == "modulation_condition":
            condition_parts.append(f"调制: {value}")

    if skipped_headers:
        return True, f"planner field bindings accepted (skipped empty: {', '.join(skipped_headers)})", bound_values, "; ".join(condition_parts)
    return True, "planner field bindings accepted", bound_values, "; ".join(condition_parts)


def _build_planner_selection_context(
    *,
    original_point_blob: str,
    point_value: str,
    measure_value: str,
    reference_value: str,
    error_value: str,
    planner_condition_text: str,
) -> str:
    return " ".join(
        part
        for part in [
            f"点位:{point_value}" if point_value and point_value != "N/A" else "",
            f"测量值:{measure_value}" if measure_value else "",
            f"标准值:{reference_value}" if reference_value else "",
            f"误差:{error_value}" if error_value else "",
            planner_condition_text,
            original_point_blob,
        ]
        if part
    ).strip()


def _is_db_resolution_text(text: str) -> bool:
    lowered = _coerce_text(text).lower()
    if not lowered or "dbm" in lowered:
        return False
    return "db" in lowered


def _is_plain_hz_error(text: str) -> bool:
    lowered = _coerce_text(text).lower()
    if not lowered or "hz" not in lowered:
        return False
    return not any(unit in lowered for unit in ("khz", "mhz", "ghz", "thz"))


def _planner_replay_subtype(
    *,
    param_name: str,
    semantic_target: str,
    measure_value: str,
    reference_value: str,
    error_value: str,
    point_value: str,
) -> str:
    lowered_name = _coerce_text(param_name).lower()
    if semantic_target == "frequency_accuracy":
        if (
            any(token in lowered_name for token in ("rf cw frequency", "载波频率", "carrier frequency"))
            and (_extract_frequency_hz_from_text(reference_value) is not None or _extract_frequency_hz_from_text(measure_value) is not None)
            and _is_plain_hz_error(error_value)
        ):
            return "carrier_frequency_error"
        if any(token in lowered_name for token in ("时基", "参考频率", "timebase", "reference frequency")):
            return "timebase_accuracy"
        if _coerce_text(reference_value).lower() == "10 mhz":
            return "timebase_accuracy"
        return ""
    if semantic_target == "power_accuracy":
        if any(token in lowered_name for token in ("resolution", "分辨力")) and any(
            _is_db_resolution_text(value)
            for value in (measure_value, reference_value, error_value, point_value)
        ):
            return "power_resolution"
        if any(token in lowered_name for token in ("偏差", "error", "deviation")):
            return "power_error"
        if any("dbm" in _coerce_text(value).lower() for value in (measure_value, reference_value, point_value)):
            return "power_range"
        return ""
    return ""


def _planner_candidate_subtype(candidate: Any, semantic_target: str) -> str:
    measured = _coerce_text(getattr(candidate, "measured", ""))
    source = getattr(candidate, "source", {}) or {}
    text = " ".join(
        part
        for part in (
            measured,
            _coerce_text(source.get("measure_range_text")),
            _coerce_text(source.get("raw")),
            _coerce_text(source.get("raw_block")),
        )
        if part
    ).lower()
    if semantic_target == "frequency_accuracy":
        if any(token in text for token in ("载波频率偏差", "carrier frequency", "载波")):
            return "carrier_frequency_error"
        if any(token in text for token in ("时基准确度", "timebase", "10mhz", "10 mhz")):
            return "timebase_accuracy"
        return ""
    if semantic_target == "power_accuracy":
        if any(token in text for token in ("功率分辨力", "power resolution", "分辨力")):
            return "power_resolution"
        if any(token in text for token in ("功率偏差", "power deviation", "偏差")):
            return "power_error"
        if any(token in text for token in ("功率范围", "power range", "电平", "dBm".lower())):
            return "power_range"
        return ""
    return ""


def _planner_same_basis_candidate_pool(
    *,
    kb_items: List[Dict[str, Any]],
    criterion: str,
) -> List[Tuple[Any, Dict[str, Any]]]:
    from .selector import normalize_kb_candidate

    basis_code_norm = norm_code(extract_basis_code(criterion) or criterion or "")
    pool: List[Tuple[Any, Dict[str, Any]]] = []
    for entry in kb_items:
        candidate = normalize_kb_candidate(entry)
        if basis_code_norm and norm_code(getattr(candidate, "basis_code", "")) != basis_code_norm:
            continue
        pool.append((candidate, entry))
    return pool


def _planner_candidate_summaries_with_same_basis_pool(
    *,
    selection_result: Any,
    same_basis_pool: List[Tuple[Any, Dict[str, Any]]],
    limit: int,
) -> List[Dict[str, str]]:
    base_summaries = build_candidate_summaries(selection_result, limit=limit)
    same_basis_candidates = [candidate for candidate, _ in same_basis_pool]
    if not same_basis_candidates:
        return base_summaries

    merged_source = SimpleNamespace(
        ranked_candidates=list(getattr(selection_result, "ranked_candidates", []) or []),
        basis_candidates=same_basis_candidates,
    )
    return build_candidate_summaries(merged_source, limit=max(limit, len(base_summaries)))


def _planner_prior_entries(
    *,
    same_basis_pool: List[Tuple[Any, Dict[str, Any]]],
    candidate_ids: List[str],
    semantic_target: str,
    replay_subtype: str,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    ordered_ids = [_coerce_text(candidate_id) for candidate_id in candidate_ids if _coerce_text(candidate_id)]
    candidate_map = {candidate.candidate_id: (candidate, entry) for candidate, entry in same_basis_pool}
    matched_pairs: List[Tuple[Any, Dict[str, Any]]] = [
        candidate_map[candidate_id] for candidate_id in ordered_ids if candidate_id in candidate_map
    ]
    matched_ids = [candidate.candidate_id for candidate, _ in matched_pairs]
    subtype_matched_pairs: List[Tuple[Any, Dict[str, Any]]] = []
    if replay_subtype:
        subtype_matched_pairs = [
            (candidate, entry)
            for candidate, entry in matched_pairs
            if _planner_candidate_subtype(candidate, semantic_target) == replay_subtype
        ]
    active_pairs = subtype_matched_pairs or matched_pairs
    metadata = {
        "requested_candidate_ids": ordered_ids,
        "matched_candidate_ids": matched_ids,
        "active_candidate_ids": [candidate.candidate_id for candidate, _ in active_pairs],
        "replay_subtype": replay_subtype,
        "subtype_filtered": bool(replay_subtype and subtype_matched_pairs),
    }
    return [entry for _, entry in active_pairs], metadata


def _planner_candidate_target_preference(
    *,
    same_basis_pool: List[Tuple[Any, Dict[str, Any]]],
    candidate_ids: List[str],
) -> str:
    ordered_ids = [_coerce_text(candidate_id) for candidate_id in candidate_ids if _coerce_text(candidate_id)]
    if not ordered_ids:
        return ""
    candidate_map = {candidate.candidate_id: candidate for candidate, _ in same_basis_pool}
    matched_targets = {
        _coerce_text(getattr(candidate_map[candidate_id], "capability_target", ""))
        for candidate_id in ordered_ids
        if candidate_id in candidate_map and _coerce_text(getattr(candidate_map[candidate_id], "capability_target", ""))
    }
    return matched_targets.pop() if len(matched_targets) == 1 else ""


def _planner_replay_result_summary(selection_result: Any) -> Dict[str, Any]:
    if selection_result is None:
        return {
            "selected_candidate_id": "",
            "rationale": "",
            "semantic_target": "",
            "ranked_candidate_ids": [],
        }
    return {
        "selected_candidate_id": _coerce_text(getattr(selection_result, "selected_candidate_id", "")),
        "rationale": _coerce_text(getattr(selection_result.audit, "rationale", "")),
        "semantic_target": _coerce_text(getattr(selection_result.cert_point, "semantic_target", "")),
        "semantic_subtype": _coerce_text(getattr(selection_result.cert_point, "semantic_subtype", "")),
        "ranked_candidate_ids": [
            _coerce_text(getattr(candidate, "candidate_id", "")) for candidate in (getattr(selection_result, "ranked_candidates", []) or [])
        ],
    }


def _planner_note_lines(summary: Dict[str, Any]) -> List[str]:
    if not summary:
        return []
    candidate_ids = summary.get("planner_candidate_ids") or []
    candidate_text = ", ".join(candidate_ids) if candidate_ids else "N/A"
    confidence = summary.get("planner_confidence")
    confidence_text = "N/A"
    if isinstance(confidence, (int, float)):
        confidence_text = f"{float(confidence):.2f}"
    takeover_score = summary.get("planner_takeover_score")
    takeover_threshold = summary.get("planner_takeover_threshold")
    takeover_score_text = "N/A"
    if isinstance(takeover_score, (int, float)):
        takeover_score_text = str(int(takeover_score))
        if isinstance(takeover_threshold, (int, float)):
            takeover_score_text = f"{takeover_score_text}/{int(takeover_threshold)}"
    return [
        f"`planner_mode` {_coerce_text(summary.get('planner_mode'), 'shadow')}",
        f"`planner_action` {_coerce_text(summary.get('planner_action'), 'abstain')}",
        f"`planner_semantic_target` {_coerce_text(summary.get('planner_semantic_target'), 'N/A') or 'N/A'}",
        f"`planner_semantic_subtype` {_coerce_text(summary.get('planner_semantic_subtype'), 'N/A') or 'N/A'}",
        f"`planner_candidate_ids` {candidate_text}",
        f"`planner_confidence` {confidence_text}",
        f"`contract_confidence` {_coerce_text(summary.get('contract_confidence'), 'N/A') or 'N/A'}",
        f"`disambiguation_used` {_coerce_text(summary.get('disambiguation_used'), 'False') or 'False'}",
        f"`planner_reason` {_coerce_text(summary.get('planner_reason'), 'N/A') or 'N/A'}",
        f"`planner_takeover_score` {takeover_score_text}",
        f"`planner_parser_risk` {_coerce_text(summary.get('planner_parser_risk'), 'N/A') or 'N/A'}",
        f"`planner_takeover_basis` {_coerce_text(summary.get('planner_takeover_basis'), 'deterministic_retained') or 'deterministic_retained'}",
    ]


def _planner_client_state(
    *,
    cfg: AppConfig,
    llm_client: Optional[LLMClient],
    llm_client_error: Optional[Dict[str, str]],
) -> Dict[str, Any]:
    init_error = dict(llm_client_error or {})
    if llm_client is not None:
        return {"available": True, "init_error": init_error}
    if init_error:
        return {"available": False, "init_error": init_error}
    if not getattr(cfg, "use_llm_verification", False):
        return {
            "available": False,
            "init_error": {
                "error_stage": "client_missing",
                "error_code": "LLMDisabled",
                "error_message": "llm verification disabled",
            },
        }
    if not _coerce_text(getattr(cfg, "api_key", "")):
        return {
            "available": False,
            "init_error": {
                "error_stage": "client_missing",
                "error_code": "MissingAPIKey",
                "error_message": "api key missing",
            },
        }
    return {"available": False, "init_error": {}}


def _planner_summary_reason(
    *,
    request_result: PlannerRequestResult,
    validation_reason: str,
    client_state: Dict[str, Any],
) -> str:
    init_error = dict(client_state.get("init_error") or {})
    if init_error:
        stage = _coerce_text(init_error.get("error_stage"))
        code = _coerce_text(init_error.get("error_code"))
        message = _coerce_text(init_error.get("error_message"))
        if stage == "client_missing":
            if code == "LLMDisabled":
                return "planner client unavailable: llm disabled"
            if code == "MissingAPIKey":
                return "planner client unavailable: api key missing"
            return f"planner client unavailable: {message or code or 'unknown'}"
        if stage == "client_init":
            detail = message or code or "unknown"
            return f"planner init failed: {detail}"
    if not request_result.request_ok:
        stage = _coerce_text(request_result.error_stage)
        code = _coerce_text(request_result.error_code)
        if stage == "structured_parse":
            return f"planner structured parse failed: {code or 'unknown'}"
        if stage == "client_init":
            return f"planner init failed: {code or 'unknown'}"
        if stage == "client_missing":
            return f"planner client unavailable: {code or 'unknown'}"
        return f"planner request failed: {code or 'unknown'}"
    if validation_reason.startswith("planner "):
        return f"planner decision rejected: {validation_reason.removeprefix('planner ')}"
    return validation_reason


def _attach_planner_summary(
    selection_result: Any,
    *,
    trace_id: str,
    planner_summary: Dict[str, Any],
) -> Any:
    if selection_result is None:
        return None
    audit = getattr(selection_result, "audit", None)
    if audit is None:
        return selection_result
    return replace(
        selection_result,
        audit=replace(
            audit,
            planner_trace_id=trace_id,
            planner_summary=dict(planner_summary),
        ),
    )


def _semantic_auditor_note_lines(summary: Dict[str, Any]) -> List[str]:
    return [
        f"`semantic_auditor_mode` {_coerce_text(summary.get('semantic_auditor_mode'), 'shadow')}",
        f"`semantic_auditor_action` {_coerce_text(summary.get('semantic_auditor_action'), 'abstain')}",
        f"`semantic_auditor_issue_type` {_coerce_text(summary.get('semantic_auditor_issue_type'), 'N/A') or 'N/A'}",
        f"`semantic_auditor_suggested_target` {_coerce_text(summary.get('semantic_auditor_suggested_target'), 'N/A') or 'N/A'}",
        f"`semantic_auditor_target_preference` {_coerce_text(summary.get('semantic_auditor_target_preference'), 'N/A') or 'N/A'}",
        f"`semantic_auditor_confidence` {_coerce_text(summary.get('semantic_auditor_confidence'), '0') or '0'}",
        f"`semantic_auditor_takeover_basis` {_coerce_text(summary.get('semantic_auditor_takeover_basis'), 'shadow_retained') or 'shadow_retained'}",
        f"`semantic_auditor_replay_selected_candidate_id` {_coerce_text(summary.get('semantic_auditor_replay_selected_candidate_id'), 'N/A') or 'N/A'}",
        f"`semantic_auditor_replay_rationale` {_coerce_text(summary.get('semantic_auditor_replay_rationale'), 'N/A') or 'N/A'}",
        f"`semantic_auditor_signals` {', '.join(summary.get('semantic_auditor_signals') or []) or 'N/A'}",
        f"`semantic_auditor_reason` {_coerce_text(summary.get('semantic_auditor_reason'), 'N/A') or 'N/A'}",
    ]


def _semantic_auditor_summary_reason(
    *,
    request_result: SemanticAuditorRequestResult,
    validation_reason: str,
    client_state: Dict[str, Any],
) -> str:
    init_error = dict(client_state.get("init_error") or {})
    if init_error:
        stage = _coerce_text(init_error.get("error_stage"))
        code = _coerce_text(init_error.get("error_code"))
        message = _coerce_text(init_error.get("error_message"))
        if stage == "client_missing":
            if code == "LLMDisabled":
                return "semantic auditor client unavailable: llm disabled"
            if code == "MissingAPIKey":
                return "semantic auditor client unavailable: api key missing"
            return f"semantic auditor client unavailable: {message or code or 'unknown'}"
        if stage == "client_init":
            detail = message or code or "unknown"
            return f"semantic auditor init failed: {detail}"
    if not request_result.request_ok:
        stage = _coerce_text(request_result.error_stage)
        code = _coerce_text(request_result.error_code)
        if stage == "structured_parse":
            return f"semantic auditor structured parse failed: {code or 'unknown'}"
        if stage == "client_init":
            return f"semantic auditor init failed: {code or 'unknown'}"
        if stage == "client_missing":
            return f"semantic auditor client unavailable: {code or 'unknown'}"
        return f"semantic auditor request failed: {code or 'unknown'}"
    if validation_reason.startswith("semantic auditor "):
        return f"semantic auditor decision rejected: {validation_reason.removeprefix('semantic auditor ')}"
    return validation_reason


def _attach_semantic_auditor_summary(
    selection_result: Any,
    *,
    trace_id: str,
    summary: Dict[str, Any],
) -> Any:
    if selection_result is None:
        return None
    audit = getattr(selection_result, "audit", None)
    if audit is None:
        return selection_result
    return replace(
        selection_result,
        audit=replace(
            audit,
            semantic_auditor_trace_id=trace_id,
            semantic_auditor_summary=dict(summary),
        ),
    )


def _build_semantic_auditor_trace_id(
    *,
    criterion: str,
    batch_index: int,
    cert_index: int,
    param_name: str,
) -> str:
    raw = "|".join(
        [
            "semantic_auditor",
            _coerce_text(extract_basis_code(criterion) or criterion or "N/A"),
            str(batch_index),
            str(cert_index),
            _coerce_text(param_name) or "unknown",
        ]
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _semantic_auditor_replay_subtype(
    *,
    selection_result: Any,
    suggested_subtype: str,
) -> str:
    current_subtype = _coerce_text(getattr(getattr(selection_result, "cert_point", None), "semantic_subtype", ""))
    hint = _coerce_text(suggested_subtype)
    if current_subtype and hint and current_subtype != hint:
        return current_subtype
    return current_subtype or hint


def _semantic_auditor_has_substantive_improvement(
    *,
    selection_result: Any,
    retry_result: Any,
    suspicion_signals: Sequence[str],
) -> Tuple[bool, str]:
    if retry_result is None or getattr(retry_result, "selected_candidate", None) is None:
        return False, "semantic replay produced no candidate"

    original_candidate = getattr(selection_result, "selected_candidate", None)
    retry_candidate = getattr(retry_result, "selected_candidate", None)
    original_relation = _coerce_text(getattr(getattr(selection_result, "audit", None), "selected_target_relation", ""))
    retry_relation = _coerce_text(getattr(getattr(retry_result, "audit", None), "selected_target_relation", ""))
    original_rationale = _coerce_text(getattr(getattr(selection_result, "audit", None), "rationale", "")).lower()
    retry_rationale = _coerce_text(getattr(getattr(retry_result, "audit", None), "rationale", ""))

    if original_candidate is None and retry_candidate is not None:
        if (
            "unknown semantic" in original_rationale
            or "same basis but no compatible candidate" in original_rationale
        ):
            return True, "semantic replay resolved missing candidate"

    if original_relation == "fallback_cross_target" and retry_relation == "exact":
        return True, "semantic replay promoted fallback target to exact target"

    if "uncertainty_only_incompatibility" in set(suspicion_signals) and retry_relation == "exact":
        return True, "semantic replay resolved uncertainty-only incompatibility with exact target"

    return False, retry_rationale or "semantic replay did not materially improve selection"


def _semantic_auditor_signal_list(
    *,
    selection_result: Any,
    parser_meta: Dict[str, Any],
    selected_kb: Optional[KbCapability],
    range_result: Optional[Dict[str, Any]],
    error_result: Optional[Dict[str, Any]],
    u_result: Optional[Dict[str, Any]],
) -> List[str]:
    if selection_result is None:
        return []
    signals: List[str] = []
    audit = getattr(selection_result, "audit", None)
    cert_point = getattr(selection_result, "cert_point", None)
    rationale = _coerce_text(getattr(audit, "rationale", "")).lower()
    section_rule = _coerce_text(parser_meta.get("section_hint_rule") or parser_meta.get("section_rule")).lower()
    semantic_target = _coerce_text(getattr(cert_point, "semantic_target", "")).lower()
    unit_family = _coerce_text(getattr(cert_point, "unit_family", "")).lower()
    if _coerce_text(getattr(audit, "selected_target_relation", "")) == "fallback_cross_target":
        signals.append("fallback_cross_target")
    if section_rule and section_rule != "unknown" and semantic_target and semantic_target != "unknown" and section_rule != semantic_target:
        signals.append("semantic_section_conflict")
    if selected_kb is not None:
        candidate_target = _coerce_text(getattr(selected_kb, "capability_target", "")).lower()
        if candidate_target and semantic_target and candidate_target != semantic_target:
            signals.append("candidate_target_mismatch")
    notes = tuple(getattr(cert_point, "normalization_notes", ()) or ())
    if any("unit family mismatch" in _coerce_text(note).lower() for note in notes) or "unit family mismatch" in rationale:
        signals.append("unit_family_mismatch")
    if rationale.startswith("same basis but no compatible candidate") or rationale.startswith("same basis missing kb subtype"):
        signals.append("candidate_gap")
    if (
        range_result is not None
        and error_result is not None
        and u_result is not None
        and _coerce_text(range_result.get("status")) == "PASS"
        and _coerce_text(error_result.get("status")) == "PASS"
        and _coerce_text(u_result.get("status")) in {"REVIEW", "FAIL"}
    ):
        signals.append("uncertainty_only_incompatibility")
    if unit_family == "unknown":
        signals.append("unknown_unit_family")
    return list(dict.fromkeys(signal for signal in signals if signal))


_SEMANTIC_AUDITOR_REPLAYABLE_SIGNALS = frozenset(
    {
        "candidate_gap",
        "fallback_cross_target",
        "semantic_section_conflict",
        "candidate_target_mismatch",
        "unit_family_mismatch",
        "unknown_unit_family",
    }
)


def _semantic_auditor_review_is_replayable(
    *,
    signals: Sequence[str],
    source_anomaly: Optional[Dict[str, Any]] = None,
    semantic_ambiguity: Optional[Dict[str, Any]] = None,
) -> bool:
    if dict(source_anomaly or {}).get("detected"):
        return False

    signal_set = {signal for signal in signals if _coerce_text(signal)}
    replayable_signals = signal_set & _SEMANTIC_AUDITOR_REPLAYABLE_SIGNALS

    if dict(semantic_ambiguity or {}).get("detected") and not replayable_signals:
        return False

    return bool(replayable_signals)


def _should_trigger_semantic_auditor(
    *,
    selection_result: Any,
    parser_meta: Dict[str, Any],
    cfg: AppConfig,
    selected_kb: Optional[KbCapability],
    range_result: Optional[Dict[str, Any]],
    error_result: Optional[Dict[str, Any]],
    u_result: Optional[Dict[str, Any]],
    source_anomaly: Optional[Dict[str, Any]] = None,
    semantic_ambiguity: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, List[str]]:
    if parameter_semantic_auditor_mode(cfg) == "off":
        return False, []
    if selection_result is None:
        return False, []
    if str(parser_meta.get("llm_fallback_applied") or "").strip():
        return False, []
    if _coerce_text(parser_meta.get("section_hint_rule") or parser_meta.get("section_rule")).lower() == "unknown":
        return False, []
    cert_point = getattr(selection_result, "cert_point", None)
    if _coerce_text(getattr(cert_point, "semantic_target", "")).lower() == "unknown":
        return False, []
    signals = _semantic_auditor_signal_list(
        selection_result=selection_result,
        parser_meta=parser_meta,
        selected_kb=selected_kb,
        range_result=range_result,
        error_result=error_result,
        u_result=u_result,
    )
    if not _semantic_auditor_review_is_replayable(
        signals=signals,
        source_anomaly=source_anomaly,
        semantic_ambiguity=semantic_ambiguity,
    ):
        return False, signals
    try:
        min_signals = int(getattr(cfg, "llm_suspicion_min_signals", 2) or 2)
    except (TypeError, ValueError):
        min_signals = 2
    replayable_count = len(set(signals) & _SEMANTIC_AUDITOR_REPLAYABLE_SIGNALS)
    return replayable_count >= max(1, min_signals), signals


def _run_parameter_semantic_auditor(
    *,
    llm_client: Optional[LLMClient],
    llm_client_error: Optional[Dict[str, str]],
    cfg: AppConfig,
    criterion: str,
    batch_index: int,
    param: Dict[str, Any],
    param_name: str,
    selection_result: Any,
    parser_meta: Dict[str, Any],
    normalized_fields: Dict[str, str],
    point_blob: str,
    selection_context: str,
    selected_kb: Optional[KbCapability],
    kb_items: List[Dict[str, Any]],
    measure_val: str,
    reference_val: str,
    error_val: str,
    point_value: str,
    range_result: Optional[Dict[str, Any]],
    error_result: Optional[Dict[str, Any]],
    u_result: Optional[Dict[str, Any]],
    source_anomaly: Optional[Dict[str, Any]] = None,
    semantic_ambiguity: Optional[Dict[str, Any]] = None,
    budget: Optional[LLMAuditorBudget] = None,
) -> SemanticAuditorExecutionResult:
    should_run, signals = _should_trigger_semantic_auditor(
        selection_result=selection_result,
        parser_meta=parser_meta,
        cfg=cfg,
        selected_kb=selected_kb,
        range_result=range_result,
        error_result=error_result,
        u_result=u_result,
        source_anomaly=source_anomaly,
        semantic_ambiguity=semantic_ambiguity,
    )
    if not should_run:
        return SemanticAuditorExecutionResult(
            selection_result=selection_result,
            selected_candidate=getattr(selection_result, "selected_candidate", None),
            selected_kb=selected_kb,
        )

    if budget is not None and not budget.try_consume():
        return SemanticAuditorExecutionResult(
            selection_result=selection_result,
            selected_candidate=getattr(selection_result, "selected_candidate", None),
            selected_kb=selected_kb,
        )

    trace_id = _build_semantic_auditor_trace_id(
        criterion=criterion,
        batch_index=batch_index,
        cert_index=int(param.get("__cert_index", 0) or 0),
        param_name=param_name,
    )
    mode = parameter_semantic_auditor_mode(cfg)
    client_state = _planner_client_state(cfg=cfg, llm_client=llm_client, llm_client_error=llm_client_error)
    candidate_summaries = build_candidate_summaries(
        selection_result,
        limit=parameter_semantic_auditor_candidate_limit(cfg),
    )
    request_result = request_semantic_auditor_decision(
        llm_client=llm_client,
        criterion=criterion,
        param_name=param_name,
        section_label=param_name,
        point_text=point_blob,
        parser_meta=parser_meta,
        normalized_fields=normalized_fields,
        parameter_contract=_get_parameter_contract(param),
        selection_audit=dict(vars(getattr(selection_result, "audit", None))) if getattr(selection_result, "audit", None) is not None else {},
        candidate_summaries=candidate_summaries,
        semantic_whitelist=SEMANTIC_TARGET_WHITELIST,
        suspicion_signals=signals,
    )
    validation_ok, validation_reason, sanitized = validate_semantic_auditor_decision(
        request_result=request_result,
        semantic_whitelist=SEMANTIC_TARGET_WHITELIST,
        candidate_summaries=candidate_summaries,
    )
    decision_payload = sanitized or request_result.decision
    summary = {
        "semantic_auditor_mode": mode,
        "semantic_auditor_action": _coerce_text(getattr(decision_payload, "action", "")) or ("invalid" if not validation_ok else "abstain"),
        "semantic_auditor_suggested_target": _coerce_text(getattr(decision_payload, "suggested_semantic_target", "")),
        "semantic_auditor_target_preference": _coerce_text(getattr(decision_payload, "suggested_candidate_target_preference", "")),
        "semantic_auditor_issue_type": _coerce_text(getattr(decision_payload, "suspected_issue_type", "")),
        "semantic_auditor_confidence": float(getattr(decision_payload, "confidence", 0.0) or 0.0),
        "semantic_auditor_reason": _coerce_text(getattr(decision_payload, "reason", "") or getattr(decision_payload, "abstain_reason", "")),
        "semantic_auditor_signals": list(signals),
        "semantic_auditor_applied": False,
        "semantic_auditor_takeover_basis": "shadow_retained",
        "semantic_auditor_replay_selected_candidate_id": "",
        "semantic_auditor_replay_rationale": "",
    }
    if not summary["semantic_auditor_reason"]:
        summary["semantic_auditor_reason"] = _semantic_auditor_summary_reason(
            request_result=request_result,
            validation_reason=validation_reason,
            client_state=client_state,
        )

    trace = {
        "trace_kind": "semantic_auditor",
        "trace_id": trace_id,
        "planner_mode": planner_mode(cfg),
        "semantic_auditor_mode": mode,
        "basis_code": criterion,
        "batch_index": batch_index,
        "cert_index": int(param.get("__cert_index", 0) or 0),
        "param_name": param_name,
        "suspicion_signals": list(signals),
        "deterministic": {
            "selected_candidate_id": _coerce_text(getattr(selection_result, "selected_candidate_id", "")),
            "semantic_target": _coerce_text(getattr(getattr(selection_result, "cert_point", None), "semantic_target", "")),
            "selected_target_relation": _coerce_text(getattr(getattr(selection_result, "audit", None), "selected_target_relation", "")),
        },
        "parser_meta": parser_meta,
        "normalized_fields": normalized_fields,
        "candidate_summaries": candidate_summaries,
        "client": client_state,
        "request": {
            "ok": request_result.request_ok,
            "error_stage": _coerce_text(request_result.error_stage),
            "error_code": _coerce_text(request_result.error_code),
            "error_message": _coerce_text(request_result.error_message),
        },
        "decision": model_dump_compat(request_result.decision),
        "validation": {
            "accepted": validation_ok,
            "reason": validation_reason,
        },
        "summary": summary,
    }
    selected_candidate = getattr(selection_result, "selected_candidate", None)
    replay_result = None
    replay_selected_kb = selected_kb
    if (
        mode == "live"
        and sanitized is not None
        and sanitized.action == "suggest"
        and float(sanitized.confidence or 0.0) >= parameter_semantic_auditor_confidence_threshold(cfg)
    ):
        replay_result = select_basis_with_audit(
            param_name=param_name,
            point_text=selection_context,
            cert_u=_extract_param_cert_u(param),
            kb_entries=kb_items,
            basis_code=criterion,
            section_label=param_name,
            measure_value=measure_val,
            reference_value=reference_val,
            error_value=error_val,
            point_value=point_value if point_value != "N/A" else "",
            parameter_contract=_get_parameter_contract(param),
            parser_meta=_get_parser_meta(param),
            semantic_target_override=sanitized.suggested_semantic_target,
            semantic_subtype_hint=_semantic_auditor_replay_subtype(
                selection_result=selection_result,
                suggested_subtype=sanitized.suggested_semantic_subtype,
            ),
            candidate_target_preference=_coerce_text(sanitized.suggested_candidate_target_preference),
            override_note=f"Semantic auditor suggestion accepted: {sanitized.suggested_semantic_target}",
        )
        replay_selected_kb = replay_result.selected[0] if getattr(replay_result, "selected", None) else None
        summary["semantic_auditor_replay_selected_candidate_id"] = _coerce_text(
            getattr(replay_result, "selected_candidate_id", "")
        )
        summary["semantic_auditor_replay_rationale"] = _coerce_text(
            getattr(getattr(replay_result, "audit", None), "rationale", "")
        )
        accepted, gate_reason = _semantic_auditor_has_substantive_improvement(
            selection_result=selection_result,
            retry_result=replay_result,
            suspicion_signals=signals,
        )
        trace["replay"] = {
            "selected_candidate_id": _coerce_text(getattr(replay_result, "selected_candidate_id", "")),
            "rationale": _coerce_text(getattr(getattr(replay_result, "audit", None), "rationale", "")),
            "semantic_target": _coerce_text(getattr(getattr(replay_result, "cert_point", None), "semantic_target", "")),
            "selected_target_relation": _coerce_text(getattr(getattr(replay_result, "audit", None), "selected_target_relation", "")),
            "candidate_target_preference": _coerce_text(sanitized.suggested_candidate_target_preference),
        }
        trace["live"] = {
            "allowed": bool(accepted),
            "reason": gate_reason,
        }
        if accepted:
            summary["semantic_auditor_applied"] = True
            summary["semantic_auditor_takeover_basis"] = "live_replay_takeover"
            if not summary["semantic_auditor_reason"]:
                summary["semantic_auditor_reason"] = gate_reason
            trace["summary"] = summary
            attached_result = _attach_semantic_auditor_summary(replay_result, trace_id=trace_id, summary=summary)
            return SemanticAuditorExecutionResult(
                selection_result=attached_result,
                selected_candidate=getattr(replay_result, "selected_candidate", None),
                selected_kb=replay_selected_kb,
                applied=True,
                note=_format_explanation_block(_semantic_auditor_note_lines(summary)),
                trace=trace,
            )
        summary["semantic_auditor_takeover_basis"] = "live_replay_rejected"
        if not summary["semantic_auditor_reason"]:
            summary["semantic_auditor_reason"] = gate_reason

    attached_result = _attach_semantic_auditor_summary(selection_result, trace_id=trace_id, summary=summary)
    return SemanticAuditorExecutionResult(
        selection_result=attached_result,
        selected_candidate=selected_candidate,
        selected_kb=selected_kb,
        applied=False,
        note=_format_explanation_block(_semantic_auditor_note_lines(summary)),
        trace=trace,
    )


def _run_parameter_planner(
    *,
    llm_client: Optional[LLMClient],
    llm_client_error: Optional[Dict[str, str]],
    cfg: AppConfig,
    criterion: str,
    batch_index: int,
    param: Dict[str, Any],
    param_name: str,
    selection_result: Any,
    kb_items: List[Dict[str, Any]],
    point_blob: str,
    selection_context: str,
    normalized_fields: Dict[str, str],
    parser_meta: Dict[str, Any],
    measure_val: str,
    reference_val: str,
    error_val: str,
    point_value: str,
) -> PlannerExecutionResult:
    default_selected_candidate = getattr(selection_result, "selected_candidate", None)
    default_selected_kb = selection_result.selected[0] if getattr(selection_result, "selected", None) else None

    if not should_trigger_planner(selection_result=selection_result, cfg=cfg, llm_client=llm_client):
        return PlannerExecutionResult(
            selection_result=selection_result,
            selected_candidate=default_selected_candidate,
            selected_kb=default_selected_kb,
            selection_context=selection_context,
        )

    trace_id = _build_planner_trace_id(
        criterion=criterion,
        batch_index=batch_index,
        cert_index=int(param.get("__cert_index", 0) or 0),
        param_name=param_name,
    )
    mode = planner_mode(cfg)
    client_state = _planner_client_state(cfg=cfg, llm_client=llm_client, llm_client_error=llm_client_error)
    raw_field_summary = build_raw_field_summary(_planner_raw_field_source(param))
    same_basis_pool = _planner_same_basis_candidate_pool(kb_items=kb_items, criterion=criterion)
    candidate_limit = planner_candidate_limit(cfg)
    candidate_summaries = _planner_candidate_summaries_with_same_basis_pool(
        selection_result=selection_result,
        same_basis_pool=same_basis_pool,
        limit=max(candidate_limit, min(len(same_basis_pool), 50)),
    )
    request_result = request_planner_decision(
        llm_client=llm_client,
        criterion=criterion,
        param_name=param_name,
        section_label=param_name,
        parser_meta=parser_meta,
        normalized_fields=normalized_fields,
        raw_field_summary=raw_field_summary,
        deterministic_rationale=_coerce_text(getattr(selection_result.audit, "rationale", "")),
        candidate_summaries=candidate_summaries,
        semantic_whitelist=SEMANTIC_TARGET_WHITELIST,
    )
    validation_ok, validation_reason, sanitized_decision = validate_planner_decision(
        request_result=request_result,
        semantic_whitelist=SEMANTIC_TARGET_WHITELIST,
        raw_field_summary=raw_field_summary,
        candidate_summaries=candidate_summaries,
    )

    trace: Dict[str, Any] = {
        "trace_id": trace_id,
        "planner_mode": mode,
        "basis_code": criterion,
        "batch_index": batch_index,
        "cert_index": int(param.get("__cert_index", 0) or 0),
        "param_name": param_name,
        "deterministic": {
            "rationale": _coerce_text(getattr(selection_result.audit, "rationale", "")),
            "semantic_target": _coerce_text(getattr(selection_result.cert_point, "semantic_target", "")),
            "semantic_subtype": _coerce_text(getattr(selection_result.cert_point, "semantic_subtype", "")),
            "contract_confidence": float(getattr(selection_result.cert_point, "contract_confidence", 0.0) or 0.0),
            "disambiguation_used": bool(getattr(selection_result.cert_point, "needs_disambiguation", False)),
            "selected_candidate_id": _coerce_text(getattr(selection_result, "selected_candidate_id", "")),
        },
        "parser_meta": parser_meta,
        "normalized_fields": normalized_fields,
        "raw_field_summary": raw_field_summary,
        "candidate_summaries": candidate_summaries,
        "client": client_state,
        "request": {
            "ok": request_result.request_ok,
            "error_stage": _coerce_text(request_result.error_stage),
            "error_code": _coerce_text(request_result.error_code),
            "error_message": _coerce_text(request_result.error_message),
        },
        "decision": model_dump_compat(request_result.decision),
        "validation": {
            "accepted": validation_ok,
            "reason": validation_reason,
        },
    }

    decision_payload = sanitized_decision or request_result.decision
    summary = {
        "planner_mode": mode,
        "planner_action": _coerce_text(getattr(decision_payload, "action", "")) or ("invalid" if not validation_ok else "abstain"),
        "planner_semantic_target": _coerce_text(getattr(decision_payload, "semantic_target", "")),
        "planner_semantic_subtype": _coerce_text(getattr(selection_result.cert_point, "semantic_subtype", "")),
        "planner_candidate_ids": list(getattr(decision_payload, "candidate_ids", []) or []),
        "planner_confidence": float(getattr(decision_payload, "confidence", 0.0) or 0.0),
        "contract_confidence": float(getattr(selection_result.cert_point, "contract_confidence", 0.0) or 0.0),
        "disambiguation_used": bool(getattr(selection_result.cert_point, "needs_disambiguation", False)),
        "planner_reason": _coerce_text(
            getattr(decision_payload, "reason", "")
            or getattr(decision_payload, "abstain_reason", "")
        ),
        "planner_takeover_score": None,
        "planner_takeover_threshold": None,
        "planner_parser_risk": "",
        "planner_takeover_basis": "deterministic_retained",
    }
    if not summary["planner_reason"]:
        summary["planner_reason"] = _planner_summary_reason(
            request_result=request_result,
            validation_reason=validation_reason,
            client_state=client_state,
        )

    if not request_result.request_ok or not validation_ok:
        logger.warning(
            "Planner issue trace_id=%s param=%s basis=%s stage=%s code=%s",
            trace_id,
            param_name,
            criterion,
            _coerce_text(request_result.error_stage or (client_state.get("init_error") or {}).get("error_stage") or "validation"),
            _coerce_text(request_result.error_code or (client_state.get("init_error") or {}).get("error_code") or validation_reason),
        )

    if not validation_ok or sanitized_decision is None:
        attached_result = _attach_planner_summary(selection_result, trace_id=trace_id, planner_summary=summary)
        trace["summary"] = summary
        return PlannerExecutionResult(
            selection_result=attached_result,
            selected_candidate=default_selected_candidate,
            selected_kb=default_selected_kb,
            selection_context=selection_context,
            note=_format_explanation_block(_planner_note_lines(summary)),
            trace=trace,
        )

    if sanitized_decision.action == "abstain":
        attached_result = _attach_planner_summary(selection_result, trace_id=trace_id, planner_summary=summary)
        trace["summary"] = summary
        return PlannerExecutionResult(
            selection_result=attached_result,
            selected_candidate=default_selected_candidate,
            selected_kb=default_selected_kb,
            selection_context=selection_context,
            note=_format_explanation_block(_planner_note_lines(summary)),
            trace=trace,
        )

    binding_ok, binding_reason, bound_values, planner_condition_text = _apply_planner_field_bindings(
        decision=sanitized_decision,
        param=param,
    )
    trace["bindings"] = {
        "accepted": binding_ok,
        "reason": binding_reason,
        "values": bound_values,
        "planner_condition_text": planner_condition_text,
    }
    if not binding_ok:
        summary["planner_reason"] = binding_reason
        attached_result = _attach_planner_summary(selection_result, trace_id=trace_id, planner_summary=summary)
        trace["summary"] = summary
        return PlannerExecutionResult(
            selection_result=attached_result,
            selected_candidate=default_selected_candidate,
            selected_kb=default_selected_kb,
            selection_context=selection_context,
            note=_format_explanation_block(_planner_note_lines(summary)),
            trace=trace,
        )

    planned_measure_val = bound_values.get("measure_value", measure_val)
    planned_reference_val = bound_values.get("reference_value", reference_val)
    planned_error_val = bound_values.get("error_value", error_val)
    planned_point_val = bound_values.get("point_value", point_value if point_value != "N/A" else "")
    planned_selection_context = _build_planner_selection_context(
        original_point_blob=point_blob,
        point_value=planned_point_val,
        measure_value=planned_measure_val,
        reference_value=planned_reference_val,
        error_value=planned_error_val,
        planner_condition_text=planner_condition_text,
    )
    replay_subtype = _planner_replay_subtype(
        param_name=param_name,
        semantic_target=sanitized_decision.semantic_target,
        measure_value=planned_measure_val,
        reference_value=planned_reference_val,
        error_value=planned_error_val,
        point_value=planned_point_val,
    )
    same_basis_entries = [entry for _, entry in same_basis_pool]
    formal_replay_trace: Dict[str, Any] = {
        "semantic_target": sanitized_decision.semantic_target,
        "replay_subtype": replay_subtype,
        "used_planner_candidates": False,
        "fallback_reason": "",
        "same_basis_candidate_count": len(same_basis_entries),
    }
    replay_target_preference = _planner_candidate_target_preference(
        same_basis_pool=same_basis_pool,
        candidate_ids=list(getattr(sanitized_decision, "candidate_ids", []) or []),
    )
    if replay_target_preference:
        formal_replay_trace["candidate_target_preference"] = replay_target_preference

    retry_result = None
    if sanitized_decision.candidate_ids:
        planner_prior_entries, planner_prior_meta = _planner_prior_entries(
            same_basis_pool=same_basis_pool,
            candidate_ids=list(sanitized_decision.candidate_ids),
            semantic_target=sanitized_decision.semantic_target,
            replay_subtype=replay_subtype,
        )
        formal_replay_trace["planner_candidate_pool"] = planner_prior_meta
        if planner_prior_entries:
            planner_prior_result = select_basis_with_audit(
                param_name=param_name,
                point_text=planned_selection_context,
                cert_u=_extract_param_cert_u(param),
                kb_entries=planner_prior_entries,
                basis_code=criterion,
                section_label=param_name,
                measure_value=planned_measure_val,
                reference_value=planned_reference_val,
                error_value=planned_error_val,
                point_value=planned_point_val,
                parameter_contract=_get_parameter_contract(param),
                parser_meta=_get_parser_meta(param),
                semantic_target_override=sanitized_decision.semantic_target,
                candidate_target_preference=replay_target_preference,
                override_note=f"Planner semantic suggestion accepted: {sanitized_decision.semantic_target}",
            )
            formal_replay_trace["planner_candidate_replay"] = _planner_replay_result_summary(planner_prior_result)
            if getattr(planner_prior_result, "selected_candidate", None) is not None:
                retry_result = planner_prior_result
                formal_replay_trace["used_planner_candidates"] = True
            else:
                formal_replay_trace["fallback_reason"] = "planner nominated candidates produced no compatible candidate"
        else:
            formal_replay_trace["fallback_reason"] = "planner candidate ids not found in same-basis pool"
    else:
        formal_replay_trace["fallback_reason"] = "planner candidate ids unavailable"

    if retry_result is None:
        retry_result = select_basis_with_audit(
            param_name=param_name,
            point_text=planned_selection_context,
            cert_u=_extract_param_cert_u(param),
            kb_entries=same_basis_entries or kb_items,
            basis_code=criterion,
            section_label=param_name,
            measure_value=planned_measure_val,
            reference_value=planned_reference_val,
            error_value=planned_error_val,
            point_value=planned_point_val,
            parameter_contract=_get_parameter_contract(param),
            parser_meta=_get_parser_meta(param),
            semantic_target_override=sanitized_decision.semantic_target,
            candidate_target_preference=replay_target_preference,
            override_note=f"Planner semantic suggestion accepted: {sanitized_decision.semantic_target}",
        )
        formal_replay_trace["same_basis_replay"] = _planner_replay_result_summary(retry_result)

    retry_candidate = getattr(retry_result, "selected_candidate", None)
    retry_selected_kb = retry_result.selected[0] if getattr(retry_result, "selected", None) else None
    formal_replay_trace.update(_planner_replay_result_summary(retry_result))
    trace["formal_replay"] = formal_replay_trace
    trace["retry"] = {
        "selected_candidate_id": formal_replay_trace["selected_candidate_id"],
        "rationale": formal_replay_trace["rationale"],
        "semantic_target": formal_replay_trace["semantic_target"],
    }

    assessment = assess_replay_improvement(
        selection_result=selection_result,
        retry_result=retry_result,
        decision=sanitized_decision,
        parser_meta=parser_meta,
        validation_ok=validation_ok and binding_ok,
        replay_used_planner_candidates=bool(formal_replay_trace.get("used_planner_candidates")),
        fallback_reason=_coerce_text(formal_replay_trace.get("fallback_reason")),
        cfg=cfg,
    )
    trace["assessment"] = model_dump_compat(assessment)

    live_allowed, live_reason, assessment = live_mode_allows_takeover(
        cfg=cfg,
        assessment=assessment,
    )
    trace["live"] = {
        "allowed": live_allowed,
        "reason": live_reason,
    }
    summary.update(
        {
            "planner_takeover_score": assessment.score,
            "planner_takeover_threshold": assessment.threshold,
            "planner_parser_risk": assessment.parser_risk,
            "planner_takeover_basis": "deterministic_retained",
        }
    )
    if live_allowed:
        summary["planner_takeover_basis"] = (
            "nominated_replay"
            if assessment.nominated_match and bool(formal_replay_trace.get("used_planner_candidates"))
            else "same_basis_fallback"
        )

    if mode == "shadow":
        summary["planner_reason"] = (
            sanitized_decision.reason
            or f"shadow formal replay selected {trace['retry']['selected_candidate_id'] or '无候选'}"
        )
    elif live_allowed:
        summary["planner_reason"] = sanitized_decision.reason or live_reason
    else:
        summary["planner_reason"] = sanitized_decision.reason or live_reason

    trace["summary"] = summary

    if live_allowed:
        trace["final"] = {
            "selected_candidate_id": _coerce_text(getattr(retry_result, "selected_candidate_id", "")),
            "selection_source": "formal_replay",
        }
        attached_retry_result = _attach_planner_summary(
            retry_result,
            trace_id=trace_id,
            planner_summary=summary,
        )
        return PlannerExecutionResult(
            selection_result=attached_retry_result,
            selected_candidate=retry_candidate,
            selected_kb=retry_selected_kb,
            selection_context=planned_selection_context,
            note=_format_explanation_block(_planner_note_lines(summary)),
            trace=trace,
        )

    trace["final"] = {
        "selected_candidate_id": _coerce_text(getattr(selection_result, "selected_candidate_id", "")),
        "selection_source": "deterministic",
    }
    attached_result = _attach_planner_summary(selection_result, trace_id=trace_id, planner_summary=summary)
    return PlannerExecutionResult(
        selection_result=attached_result,
        selected_candidate=default_selected_candidate,
        selected_kb=default_selected_kb,
        selection_context=selection_context,
            note=_format_explanation_block(_planner_note_lines(summary)),
            trace=trace,
        )




def _extract_alias_value(
    mapping: Dict[str, Any],
    aliases: List[str],
    *,
    contains_all: Optional[List[str]] = None,
    excludes: Optional[List[str]] = None,
) -> str:
    if not isinstance(mapping, dict):
        return ""

    for alias in aliases:
        text = _coerce_text(mapping.get(alias))
        if text:
            return text

    alias_norms = [_normalize_key_for_match(alias) for alias in aliases if alias]
    contains_all = [token.lower() for token in (contains_all or []) if token]
    excludes = [token.lower() for token in (excludes or []) if token]

    for key, value in mapping.items():
        key_norm = _normalize_key_for_match(key)
        if excludes and any(token in key_norm for token in excludes):
            continue
        if contains_all and not all(token in key_norm for token in contains_all):
            continue
        if alias_norms and any(alias_norm and alias_norm in key_norm for alias_norm in alias_norms):
            text = _coerce_text(value)
            if text:
                return text
    return ""


def _get_detail_mapping(param: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(param, dict):
        return {}
    for key in ("数据明细", "明细", "detail", "details", "测量明细"):
        value = param.get(key)
        if isinstance(value, dict):
            return value
    return {}


def _get_normalized_mapping(param: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(param, dict):
        return {}
    for key in ("__normalized_fields", "normalized_fields"):
        value = param.get(key)
        if isinstance(value, dict):
            return value
    return {}


def _sanitize_cert_u_text(value: Any) -> str:
    text = _coerce_text(value)
    if not text:
        return ""
    stripped = re.sub(r"^\s*(?:P|F|PASS|FAIL|--)\b[:：]?\s*", "", text, flags=re.IGNORECASE).strip()
    return stripped or text


def _repair_legacy_reference_oscillator_contract(contract: Dict[str, Any]) -> Dict[str, Any]:
    normalized = normalize_parameter_contract(contract)
    semantic_target = _coerce_text(normalized.get("semantic_target")).lower()
    semantic_subtype = _coerce_text(normalized.get("semantic_subtype")).lower()
    unit_family = _coerce_text(normalized.get("unit_family")).lower()
    if (
        semantic_target == "reference_oscillator"
        and semantic_subtype == "frequency_stability"
        and unit_family == "time"
        and _coerce_text(normalized.get("error_value"))
    ):
        normalized["unit_family"] = "frequency"
    cert_u = _sanitize_cert_u_text(normalized.get("cert_u"))
    if cert_u:
        normalized["cert_u"] = cert_u
    return normalized


def _get_parameter_contract(param: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(param, dict):
        return {}
    for key in ("__parameter_contract", "parameter_contract"):
        value = param.get(key)
        if isinstance(value, dict):
            return _repair_legacy_reference_oscillator_contract(value)
    return {}


def _get_parser_meta(param: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(param, dict):
        return {}
    value = param.get("__parser_meta")
    return value if isinstance(value, dict) else {}


def _get_document_parser_meta(cert_root: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(cert_root, dict):
        return {}
    value = cert_root.get("__document_parser_meta")
    return value if isinstance(value, dict) else {}


def _is_nonstandard_parameter_parse_source(parse_source: Any) -> bool:
    source = _coerce_text(parse_source, "")
    return bool(source and source not in STANDARD_PARAMETER_PARSE_SOURCES)


def _is_structured_flat_reference_oscillator_param(param: Dict[str, Any]) -> bool:
    parser_meta = _get_parser_meta(param)
    if _coerce_text(parser_meta.get("parse_source")) != "flat_text_reference_oscillator":
        return False
    if _coerce_text(parser_meta.get("section_rule")).lower() != "reference_oscillator":
        return False

    normalized = param.get("__normalized_fields")
    if not isinstance(normalized, dict):
        return False

    error_value = _coerce_text(normalized.get("error_value"))
    if not error_value:
        return False

    support_value = any(
        _coerce_text(normalized.get(field_name))
        for field_name in ("limit_value", "cert_u", "result_flag")
    )
    if not support_value:
        return False

    nominal_like = any(
        _coerce_text(normalized.get(field_name))
        for field_name in ("measure_value", "reference_value", "nominal_value")
    )
    point_like = _coerce_text(normalized.get("point_value"))
    param_name = _normalize_key_for_match(param.get("测量值") or param.get("项目名称") or "")

    if "开机特性" in param_name or "warmup" in param_name:
        return nominal_like
    if "相对频率偏差" in param_name or "relativefrequencydeviation" in param_name:
        return nominal_like
    if "短期频率稳定度" in param_name or "shortterm" in param_name or "stability" in param_name:
        return bool(point_like or nominal_like)
    return bool(point_like or nominal_like)


def _row_uses_standard_parameter_layout(param: Dict[str, Any]) -> bool:
    parse_source = _coerce_text(_get_parser_meta(param).get("parse_source"), "")
    if parse_source in STANDARD_PARAMETER_PARSE_SOURCES:
        return True
    return _is_structured_flat_reference_oscillator_param(param)


def _resolve_document_parameter_review_reason(
    cert_root: Dict[str, Any],
    params: List[Dict[str, Any]],
) -> str:
    document_meta = _get_document_parser_meta(cert_root)
    nonstandard_sources: List[str] = []

    if params and all(_row_uses_standard_parameter_layout(param) for param in params):
        return ""

    if document_meta.get("has_nonstandard_parameter_layout"):
        raw_sources = document_meta.get("nonstandard_parameter_parse_sources") or document_meta.get(
            "parameter_parse_sources"
        ) or []
        if isinstance(raw_sources, list):
            nonstandard_sources.extend(
                sorted(
                    {
                        _coerce_text(source, "")
                        for source in raw_sources
                        if _is_nonstandard_parameter_parse_source(source)
                    }
                )
            )
        review_reason = _coerce_text(document_meta.get("parameter_review_reason"))
        if review_reason:
            return review_reason

    if not nonstandard_sources:
        nonstandard_sources = sorted(
            {
                _coerce_text(_get_parser_meta(param).get("parse_source"), "")
                for param in params
                if not _row_uses_standard_parameter_layout(param)
                and _is_nonstandard_parameter_parse_source(_get_parser_meta(param).get("parse_source"))
            }
        )

    if not nonstandard_sources:
        return ""

    source_text = ", ".join(nonstandard_sources)
    return (
        "参数区未按标准表格形态解析"
        f"（parse_source={source_text}），为避免自动误判，当前跳过参数自动核验，建议人工核验"
    )


def _build_measure_context_from_detail(detail: Dict[str, Any], param_name: str = "") -> str:
    if not isinstance(detail, dict) or not detail:
        return ""

    primary_tokens = []
    pn = _normalize_key_for_match(param_name)
    if "灵敏度" in pn or "sensitivity" in pn:
        primary_tokens.extend(["灵敏度", "sensitivity"])
    if "偏差" in pn or "deviation" in pn:
        primary_tokens.extend(["偏差", "deviation"])
    if any(token in pn for token in ("功率", "power", "电平", "level")) and not primary_tokens:
        primary_tokens.extend(["功率", "power", "电平", "level"])
    if "频率" in pn and not primary_tokens:
        primary_tokens.extend(["频率", "frequency"])
    if "周期" in pn and not primary_tokens:
        primary_tokens.extend(["周期", "period", "time"])

    support_keys = []
    primary_value = ""
    support_values = []
    for key, value in detail.items():
        text = _coerce_text(value)
        if not text:
            continue
        key_norm = _normalize_key_for_match(key)
        if any(token in key_norm for token in ("limit", "范围", "结论", "passfail", "uncert", "不确定", "u(")):
            continue
        if not primary_value and primary_tokens and any(token in key_norm for token in primary_tokens):
            primary_value = text
            continue
        support_keys.append(key)
        support_values.append(text)

    if not primary_value:
        for key, value in detail.items():
            text = _coerce_text(value)
            if not text:
                continue
            key_norm = _normalize_key_for_match(key)
            if any(token in key_norm for token in ("frequency", "频率", "灵敏度", "sensitivity", "偏差", "deviation", "示值", "测量值", "结果", "输出")):
                primary_value = text
                break

    pieces = [primary_value] if primary_value else []
    pieces.extend(support_values)
    return "; ".join(piece for piece in pieces if piece)


def _extract_param_condition_text(param: Dict[str, Any]) -> str:
    contract = _get_parameter_contract(param)
    contract_condition_value = contract_source_value(contract, "condition_value")
    if contract_condition_value:
        header = contract_source_header(contract, "condition_value")
        label = header or contract_source_value(contract, "condition_axis") or "条件"
        return f"{label}: {contract_condition_value}"

    source = _get_detail_mapping(param) or param
    if not isinstance(source, dict) or not source:
        return ""

    param_name = _coerce_text(param.get("param_name") or param.get("项目名称") or param.get("测量值") or param.get("name"))
    param_name_norm = _normalize_key_for_match(param_name)
    prefers_condition_display = any(
        token in param_name_norm
        for token in (
            "功率",
            "power",
            "电平",
            "level",
            "灵敏度",
            "sensitivity",
            "调制",
            "modulation",
            "phase noise",
            "相位噪声",
            "dynamic range",
            "动态范围",
            "spurious",
            "杂散",
        )
    )
    if not prefers_condition_display:
        return ""

    point_value = _extract_param_point_value(param)
    match_value = _extract_param_measure_value(param)
    reference_value = _extract_param_reference_value(param)
    error_value = _extract_param_error_value(param)
    cert_u = _extract_param_cert_u(param)
    used_values = {
        _coerce_text(point_value).lower(),
        _coerce_text(match_value).lower(),
        _coerce_text(reference_value).lower(),
        _coerce_text(error_value).lower(),
        _coerce_text(cert_u).lower(),
    }

    candidates: List[Tuple[str, str, str]] = []
    alias_groups = (
        ("信号", ("信号", "Signal", "signal", "系统", "System", "system", "制式", "模式", "Mode", "mode")),
        ("频率", ("频率", "Frequency", "frequency", "输出频率", "测试频率", "测量频率", "载波频率", "Carrier Frequency")),
        ("调制", ("调制", "Modulation", "modulation")),
        ("带宽", ("带宽", "Bandwidth", "bandwidth", "RBW", "VBW")),
        ("载波", ("载波", "Carrier", "carrier")),
    )

    for display_label, aliases in alias_groups:
        value = _extract_alias_value(
            source,
            list(aliases),
            excludes=["limit", "range", "uncert", "u(", "误差", "error", "标准值", "reference", "点位", "point"],
        )
        value_text = _coerce_text(value)
        if not value_text:
            continue
        normalized_value = value_text.lower()
        if normalized_value in used_values:
            if display_label != "频率":
                continue
            if _coerce_text(match_value).lower() != normalized_value:
                continue
        candidates.append((display_label, value_text, _normalize_key_for_match(display_label)))

    seen_labels = set()
    parts: List[str] = []
    for display_label, value_text, label_key in candidates:
        if label_key in seen_labels:
            continue
        seen_labels.add(label_key)
        parts.append(f"{display_label}: {value_text}")
    return "; ".join(parts)


def _extract_param_measure_value(param: Dict[str, Any]) -> str:
    contract = _get_parameter_contract(param)
    contract_measure = contract_source_value(contract, "measure_value")
    if contract_measure:
        return contract_measure

    normalized = _get_normalized_mapping(param)
    parser_meta = _get_parser_meta(param)
    section_rule = _coerce_text(parser_meta.get("section_rule"))
    param_name = _coerce_text(param.get("param_name") or param.get("项目名称") or param.get("测量值") or param.get("name"))
    param_name_lower = param_name.lower()
    prefers_metric_as_measure = (
        section_rule in {"modulation_quality", "phase_noise", "spectral_purity"}
        or any(
            token in param_name_lower
            for token in (
                "signal quality",
                "信号质量",
                "phase noise",
                "相位噪声",
                "spectral purity",
                "signal purity",
                "信号纯度",
            )
        )
    )
    is_power_like = _is_power_like_param_name(param_name)

    normalized_reference = _coerce_text(normalized.get("reference_value"))
    normalized_point = _coerce_text(normalized.get("point_value"))
    normalized_measure = _coerce_text(normalized.get("measure_value"))
    if (
        prefers_metric_as_measure
        and normalized_measure
        and normalized_reference
        and _looks_like_condition_frequency_value(normalized_measure)
        and not _looks_like_condition_frequency_value(normalized_reference)
    ):
        return normalized_reference
    if is_power_like:
        if (
            normalized_measure
            and normalized_reference
            and _looks_like_condition_frequency_value(normalized_measure)
            and _looks_like_power_value(normalized_reference)
        ):
            return normalized_reference
        if _looks_like_power_value(normalized_reference):
            return normalized_reference
        if _looks_like_power_value(normalized_point):
            return normalized_point
    if normalized_measure:
        return normalized_measure
    if _point_value_can_serve_as_measure(
        param,
        normalized_point,
        reference_value=normalized_reference,
        error_value=_coerce_text(normalized.get("error_value")),
    ):
        return normalized_point

    source = _get_detail_mapping(param) or param
    if not isinstance(source, dict):
        return ""

    is_reference_like = _is_reference_oscillator_param_name(param_name)

    # 先取“实际被测量值”，不要把点位/通道当作测量值。
    if is_reference_like:
        value = _extract_reference_oscillator_frequency_value(source)
        if not value:
            value = _extract_frequency_token_from_text(param_name)
        if value:
            return value
        preferred_alias_groups = (
            ["指示值", "Indicated", "indicated", "显示值", "示值"],
            ["测量值", "Measurement Value", "measured", "Measured", "测量结果", "结果", "输出", "读数"],
            ["周期", "Period", "时间间隔", "Time Interval"],
            ["值", "Value"],
        )
    else:
        preferred_alias_groups = (
            ["标准值", "Reference", "reference", "Nominal", "Nominal Value", "标称值"],
            ["指示值", "Indicated", "indicated", "显示值", "示值"],
            ["测量值", "Measurement Value", "measured", "Measured", "测量结果", "结果", "输出", "读数"],
            ["频率", "Frequency", "输出频率", "测试频率", "测量频率"],
            ["周期", "Period", "时间间隔", "Time Interval"],
            ["值", "Value"],
        )
    for aliases in preferred_alias_groups:
        value = _extract_alias_value(
            source,
            aliases,
            excludes=["limit", "range", "uncert", "u(", "channel", "band", "点位", "通道"],
        )
        if value and not _is_point_only_value(value):
            if is_reference_like and any(token in aliases for token in ("频率", "Frequency", "测试频率", "测量频率")):
                if not _is_plausible_reference_oscillator_frequency(value):
                    continue
            return value

    return _extract_alias_value(
        source,
        ["测量值", "测量点", "测量结果", "结果", "输出", "值"],
        excludes=["limit", "range", "uncert", "u(", "channel", "band", "点位", "通道"],
    )


def _header_looks_like_condition_axis(header_text: Any) -> bool:
    normalized = _normalize_key_for_match(header_text)
    if not normalized:
        return False
    condition_tokens = (
        "range",
        "量程",
        "频率",
        "frequency",
        "band",
        "channel",
        "通道",
        "point",
        "点位",
        "档位",
        "port",
        "gate time",
        "gatetime",
        "时间",
        "time interval",
        "condition",
        "signal",
        "system",
        "mode",
        "item",
        "项目",
    )
    return any(token in normalized for token in condition_tokens)


def _value_looks_like_condition_axis(text: str) -> bool:
    value = _coerce_text(text)
    if not value:
        return False
    lowered = value.lower()
    if any(marker in value for marker in ("~", "～", "至", "—", "–")):
        return True
    if any(marker in lowered for marker in (">=", "<=", ">", "<", " to ")):
        return True
    if re.search(r"\b(?:ch|channel|band|port)\s*\d+\b", lowered):
        return True
    if any(token in lowered for token in ("gate time", "rbw", "vbw")):
        return True
    if _parse_frequency_range(value) is not None:
        return True
    if re.search(r"\d", value) and any(unit in lowered for unit in ("ps", "ns", "us", "μs", "ms", "min", "h", "hr", "hour")):
        return True
    if len(_parse_frequency_point_list(value)) > 1:
        return True
    return False


def _point_value_can_serve_as_measure(
    param: Dict[str, Any],
    point_value: str,
    *,
    reference_value: str = "",
    error_value: str = "",
) -> bool:
    point_text = _coerce_text(point_value)
    if not point_text or _is_point_only_value(point_text):
        return False
    if _value_looks_like_condition_axis(point_text):
        return False

    parser_meta = _get_parser_meta(param)
    header_rules = parser_meta.get("header_rules") if isinstance(parser_meta, dict) else {}
    point_header = header_rules.get("point_value") if isinstance(header_rules, dict) else ""
    if _header_looks_like_condition_axis(point_header):
        return False

    contract = _get_parameter_contract(param)
    row_shape = _coerce_text(contract.get("row_shape"))
    if (
        row_shape in {"nominal_reference_error_u", "item_nominal_reference_error_u"}
        and _coerce_text(reference_value)
        and _coerce_text(error_value)
    ):
        return False
    return True


def _extract_param_reference_value(param: Dict[str, Any]) -> str:
    contract = _get_parameter_contract(param)
    contract_reference = contract_source_value(contract, "reference_value")
    if contract_reference:
        return contract_reference

    normalized = _get_normalized_mapping(param)
    normalized_reference = _coerce_text(normalized.get("reference_value"))
    if normalized_reference:
        return normalized_reference

    source = _get_detail_mapping(param) or param
    if not isinstance(source, dict):
        return ""

    param_name = _coerce_text(param.get("param_name") or param.get("项目名称") or param.get("测量值") or param.get("name"))
    is_reference_like = _is_reference_oscillator_param_name(param_name)

    if is_reference_like:
        value = _extract_reference_oscillator_frequency_value(source)
        if not value:
            value = _extract_frequency_token_from_text(param_name)
        if value:
            return value
        preferred_aliases = (
            ["标准值", "Reference", "reference"],
            ["标称值", "Nominal", "nominal", "Nominal Value"],
            ["周期", "Period", "时间间隔", "Time Interval"],
        )
    else:
        preferred_aliases = (
            ["标准值", "Reference", "reference"],
            ["标称值", "Nominal", "nominal", "Nominal Value"],
            ["频率", "Frequency", "输出频率", "测试频率", "测量频率"],
            ["周期", "Period", "时间间隔", "Time Interval"],
        )

    for aliases in preferred_aliases:
        value = _extract_alias_value(
            source,
            aliases,
            excludes=["limit", "range", "uncert", "u(", "channel", "band", "点位", "通道"],
        )
        if value and not _is_point_only_value(value):
            if is_reference_like and any(token in aliases for token in ("频率", "Frequency", "测试频率", "测量频率")):
                if not _is_plausible_reference_oscillator_frequency(value):
                    continue
            return value
    return ""


def _is_reference_oscillator_param_name(param_name: str) -> bool:
    text = _coerce_text(param_name).lower()
    if not text:
        return False
    tokens = (
        "时基",
        "time base",
        "timebase",
        "reference oscillator",
        "reference",
        "warm-up",
        "warm up",
        "开机特性",
        "frequency stability",
        "short-term stability",
        "relative frequency deviation",
        "相对频率偏差",
        "频率稳定度",
        "短期频率稳定度",
        "日老化率",
        "日频率波动",
        "日频率漂移率",
        "频率复现性",
        "内时基",
        "晶振",
        "内晶振",
        "内部晶振",
        "oscillator",
    )
    return any(token in text for token in tokens)


def _is_plausible_reference_oscillator_frequency(text: str) -> bool:
    """Reference oscillator values should usually be in MHz/GHz class, not plain 1 Hz noise."""
    freq_hz = _extract_frequency_hz_from_text(text)
    if freq_hz is None:
        return False
    return abs(freq_hz) >= 1e5


def _extract_frequency_token_from_text(text: str) -> str:
    raw = _coerce_text(text)
    if not raw:
        return ""
    match = re.search(r"([-+]?\d*\.?\d+\s*(?:THz|GHz|MHz|kHz|Hz))", raw, flags=re.IGNORECASE)
    if not match:
        return ""
    token = match.group(1).strip()
    return token if _is_plausible_reference_oscillator_frequency(token) else ""


def _extract_reference_oscillator_frequency_value(source: Dict[str, Any]) -> str:
    if not isinstance(source, dict):
        return ""

    explicit_alias_groups = (
        ([
            "内晶振输出频率",
            "内部晶振输出频率",
            "晶振频率",
            "内部晶振频率",
            "输出频率",
            "频率输出",
            "时基频率",
            "internal crystal output frequency",
            "internal crystal frequency",
            "reference oscillator frequency",
        ], True),
        ([
            "标准值",
            "Reference",
            "reference",
            "标称值",
            "Nominal",
            "nominal",
            "Nominal Value",
        ], True),
        ([
            "指示值",
            "Indicated",
            "indicated",
            "显示值",
            "示值",
        ], False),
        ([
            "测量值",
            "Measurement Value",
            "measured",
            "Measured",
            "测量结果",
            "结果",
            "输出",
            "读数",
        ], False),
        ([
            "频率",
            "Frequency",
            "测试频率",
            "测量频率",
        ], True),
    )

    for aliases, require_plausible in explicit_alias_groups:
        value = _extract_alias_value(
            source,
            aliases,
            excludes=["limit", "range", "uncert", "u(", "channel", "band", "点位", "通道"],
        )
        if value and not _is_point_only_value(value):
            if require_plausible and not _is_plausible_reference_oscillator_frequency(value):
                continue
            return value
    return ""


def _extract_param_error_value(param: Dict[str, Any]) -> str:
    contract = _get_parameter_contract(param)
    contract_error = contract_source_value(contract, "error_value")
    if contract_error:
        return contract_error

    normalized = _get_normalized_mapping(param)
    normalized_error = _coerce_text(normalized.get("error_value"))
    if normalized_error:
        return normalized_error

    param_name = _coerce_text(param.get("param_name") or param.get("项目名称") or param.get("测量值") or param.get("name"))
    if _is_power_like_param_name(param_name):
        derived_power_error = _derive_power_error_from_point_and_reference(param)
        if derived_power_error:
            return derived_power_error

    source = _get_detail_mapping(param) or param
    if not isinstance(source, dict):
        return ""

    is_reference_like = _is_reference_oscillator_param_name(param_name)

    alias_groups = []
    if is_reference_like:
        alias_groups.extend(
            [
                ["开机特性", "Warm-up Characteristics", "warm-up characteristics", "warm up characteristics"],
                ["短期频率稳定度", "Short-Term Stability", "frequency stability", "Stability"],
                ["相对频率偏差", "Relative Frequency Deviation", "relative frequency deviation"],
                ["频率复现性", "reproducibility"],
                ["日老化率", "aging", "ageing"],
            ]
        )
    alias_groups.extend(
        [
            ["灵敏度", "Sensitivity"],
            ["偏差", "Deviation"],
            ["误差", "Error"],
            ["测量值", "结果", "输出", "示值", "读数", "值"],
        ]
    )

    for aliases in alias_groups:
        excludes = ["limit", "range", "uncert", "u("]
        if aliases == ["测量值", "结果", "输出", "示值", "读数", "值"]:
            excludes.extend(["reference", "标准值", "标称值", "nominal"])
        value = _extract_alias_value(source, aliases, excludes=excludes)
        if value:
            return value

    return ""


def _normalize_point_value(value: Any) -> str:
    text = _coerce_text(value)
    if not text:
        return ""
    ch_match = re.search(r"\bCH\s*([0-9]+)\b", text, flags=re.IGNORECASE)
    if ch_match:
        return f"CH{ch_match.group(1)}"
    return text


def _extract_param_point_value(param: Dict[str, Any]) -> str:
    contract = _get_parameter_contract(param)
    contract_item = contract_source_value(contract, "item_label")
    if contract_item:
        return _normalize_point_value(contract_item)

    normalized = _get_normalized_mapping(param)
    normalized_point = _coerce_text(normalized.get("point_value"))
    if normalized_point:
        return _normalize_point_value(normalized_point)

    source = _get_detail_mapping(param) or param
    if not isinstance(source, dict):
        return ""

    parser_meta = _get_parser_meta(param)
    section_rule = _coerce_text(parser_meta.get("section_rule"))
    param_name = _coerce_text(param.get("param_name") or param.get("项目名称") or param.get("测量值") or param.get("name"))
    param_name_lower = param_name.lower()

    for aliases in (
        ["点位", "Point", "point"],
        ["通道", "Channel", "channel"],
        ["偏置", "Offset", "offset"],
        ["取样时间", "Gate Time", "gate time", "闸门时间"],
        ["可调节功率值", "Slider Power value", "slider power value", "设定值", "Setting", "power setting", "set level"],
        ["Band", "band"],
        ["档位", "档", "Range", "range"],
        ["端口", "Port", "port"],
    ):
        value = _extract_alias_value(source, aliases)
        if value:
            return _normalize_point_value(value)

    if section_rule in {"modulation_quality", "spectral_purity"} or any(
        token in param_name_lower
        for token in ("signal quality", "信号质量", "spectral purity", "信号纯度")
    ):
        value = _extract_alias_value(
            source,
            ["被测量", "Measured", "measured", "参数", "Parameter", "parameter", "项目", "Item", "item"],
        )
        if value:
            return _normalize_point_value(value)

    for key, value in source.items():
        key_norm = _normalize_key_for_match(key)
        if any(token in key_norm for token in ("点位", "point", "通道", "channel", "偏置", "offset", "band", "档位", "port")):
            text = _normalize_point_value(value)
            if text:
                return text
    return ""


def _is_power_like_param_name(param_name: str) -> bool:
    text = _coerce_text(param_name).lower()
    if not text:
        return False
    return any(token in text for token in ("功率", "power", "电平", "level"))


def _looks_like_power_value(text: str) -> bool:
    value = _coerce_text(text).lower()
    if not value:
        return False
    return bool(re.search(r"\b(?:dbm|db|w|mw|uv|mv|v)\b", value))


def _looks_like_condition_frequency_value(text: str) -> bool:
    value = _coerce_text(text).lower()
    if not value:
        return False
    if "dbc/hz" in value or "/hz" in value:
        return False
    return bool(re.search(r"[-+]?\d+(?:\.\d+)?\s*(?:g|m|k)?hz\b", value))


def _format_delta_value(delta: float, unit: str) -> str:
    rounded = 0.0 if abs(delta) < 1e-15 else delta
    return f"{rounded:.12g} {unit}".strip()


def _derive_power_error_from_point_and_reference(param: Dict[str, Any]) -> str:
    point_value = _extract_param_point_value(param)
    reference_value = _extract_param_reference_value(param)
    if not point_value or not reference_value:
        return ""

    point_num, _ = parse_value_with_unit(point_value, keep_sign=True)
    ref_num, _ = parse_value_with_unit(reference_value, keep_sign=True)
    if point_num is None or ref_num is None:
        return ""

    if not (_looks_like_power_value(point_value) and _looks_like_power_value(reference_value)):
        return ""
    if re.search(r"\b(?:db|dbm)\b", f"{point_value} {reference_value}", flags=re.IGNORECASE):
        return _format_delta_value(ref_num - point_num, "dB")
    return _format_delta_value(ref_num - point_num, "")


def _is_point_only_value(value: Any) -> bool:
    text = _normalize_point_value(value)
    if not text:
        return False
    normalized = _normalize_key_for_match(text)
    if normalized in {"a", "b", "c", "d", "e", "lower", "upper", "high", "low"}:
        return True
    if re.fullmatch(r"(ch|channel|band)\d*", normalized):
        return True
    if normalized in {"通道", "channel", "band", "点位", "point"}:
        return True
    return False


def _extract_param_limit_value(param: Dict[str, Any]) -> str:
    contract = _get_parameter_contract(param)
    contract_limit = contract_source_value(contract, "limit_value")
    if contract_limit:
        return contract_limit

    normalized = _get_normalized_mapping(param)
    normalized_limit = _coerce_text(normalized.get("limit_value"))
    if normalized_limit:
        return normalized_limit

    source = _get_detail_mapping(param) or param
    if not isinstance(source, dict):
        return ""

    return _extract_alias_value(
        source,
        [
            "允许误差",
            "允许范围",
            "最大允许误差",
            "误差限值",
            "限值",
            "容差",
            "允差",
            "Limit",
            "limit",
        ],
        excludes=["kb"],
    )


def _is_reference_frequency_param(param_name: str, point_text: str, cert_u: str = "") -> bool:
    text = " ".join(part for part in [str(param_name or ""), str(point_text or ""), str(cert_u or "")] if part).lower()
    keywords = [
        "relative frequency deviation",
        "相对频率偏差",
        "warm-up",
        "warm up",
        "开机特性",
        "frequency stability",
        "short-term stability",
        "频率稳定度",
        "短期频率稳定度",
        "crystal",
        "晶振",
        "晶振频率",
        "internal crystal",
        "internal crystal output frequency",
        "internal crystal frequency",
        "内晶振",
        "内部晶振",
        "reference oscillator",
    ]
    return any(keyword in text for keyword in keywords)


def _candidate_matches_frequency_point(point_text: str, kb_source: Dict[str, Any]) -> bool:
    point_freq_hz = _extract_frequency_hz_from_text(point_text)
    if point_freq_hz is None:
        return True
    if not isinstance(kb_source, dict):
        return False

    segment_values = kb_source.get("measure_range_segments")
    if isinstance(segment_values, str):
        try:
            loaded_segments = json.loads(segment_values)
            if isinstance(loaded_segments, list):
                segment_values = loaded_segments
        except Exception:
            segment_values = [part.strip() for part in re.split(r"[；;]", segment_values) if part.strip()]
    elif isinstance(segment_values, tuple):
        segment_values = list(segment_values)

    candidate_texts = [
        *([_coerce_text(seg) for seg in segment_values] if isinstance(segment_values, list) else []),
        _coerce_text(kb_source.get("measure_range_segments_text")),
        _coerce_text(kb_source.get("measure_range_text")),
        _coerce_text(kb_source.get("measure_range")),
        _coerce_text(kb_source.get("range")),
        _coerce_text(kb_source.get("raw")),
        _coerce_text(kb_source.get("raw_block")),
    ]
    saw_explicit_frequency_axis = False
    for text in candidate_texts:
        if not text:
            continue
        try:
            freq_range = _parse_frequency_range(text)
        except Exception:
            freq_range = None
        if freq_range and freq_range[0] is not None and freq_range[1] is not None:
            saw_explicit_frequency_axis = True
            if freq_range[0] <= point_freq_hz <= freq_range[1]:
                return True
        points = _parse_frequency_point_list(text)
        if points:
            saw_explicit_frequency_axis = True
            for candidate_freq in points:
                if abs(point_freq_hz - candidate_freq) <= max(1.0, abs(candidate_freq) * 1e-12):
                    return True
    if not saw_explicit_frequency_axis:
        return True
    return False


def _format_kb_measured_display(kb_measured: str, kb_range: str, capability_target: str = "") -> str:
    kb_measured = _coerce_text(kb_measured, "N/A") or "N/A"
    kb_range = _coerce_text(kb_range, "N/A") or "N/A"
    if capability_target == "input_sensitivity" and kb_range != "N/A":
        if any(token in kb_range.lower() for token in ("hz", "khz", "mhz", "ghz")):
            return "频率测量范围及输入灵敏度"
        if any(token in kb_range.lower() for token in ("ps", "ns", "us", "ms", "s")):
            return "周期测量范围及输入灵敏度"
    if kb_measured == "频率" and kb_range != "N/A":
        return f"{kb_measured}（{kb_range}）"
    return kb_measured


def _extract_param_cert_u(param: Dict[str, Any]) -> str:
    contract = _get_parameter_contract(param)
    contract_u = contract_source_value(contract, "cert_u")
    if contract_u:
        return _sanitize_cert_u_text(contract_u)

    normalized = _get_normalized_mapping(param)
    normalized_u = _sanitize_cert_u_text(normalized.get("cert_u"))
    if normalized_u:
        return normalized_u

    source = _get_detail_mapping(param) or param
    if not isinstance(source, dict):
        return ""

    def _prefix_uncertainty_text(raw: str, prefix: str) -> str:
        text = _sanitize_cert_u_text(raw)
        if not text:
            return ""
        lower = text.lower()
        if lower.startswith("urel=") or lower.startswith("u=") or "%" in text:
            return text
        return f"{prefix}{text}" if prefix else text

    key_prefix_map = {
        "不确定度": "",
        "证书u": "U=",
        "u(k=2)": "U=",
        "urel(k=2)": "Urel=",
        "urel": "Urel=",
        "u": "U=",
    }
    for key, value in source.items():
        key_norm = _normalize_key_for_match(key)
        if key_norm in key_prefix_map:
            text = _prefix_uncertainty_text(value, key_prefix_map[key_norm])
            if text:
                return text
    return ""


def _is_plain_cert_u_header(header_text: Any) -> bool:
    normalized = _normalize_key_for_match(header_text)
    if not normalized or normalized.startswith("urel"):
        return False
    return normalized == "u" or re.fullmatch(r"u\([^)]*\)", normalized) is not None


def _resolve_effective_probe_subtype(
    selected_kb: KbCapability,
    *,
    param: Optional[Dict[str, Any]],
    measure_val: str = "",
    error_val: str = "",
    reference_val: str = "",
) -> str:
    current = _coerce_text(getattr(selected_kb, "semantic_subtype", ""))
    if current and current != "__default__":
        return current

    contract = _get_parameter_contract(param) if param is not None else {}
    contract_subtype = _coerce_text(contract.get("semantic_subtype"))
    if contract_subtype and contract_subtype != "__default__":
        return contract_subtype

    source = getattr(selected_kb, "source", None) or {}
    param_name = ""
    if isinstance(param, dict):
        param_name = _coerce_text(param.get("param_name") or param.get("项目名称") or param.get("测量值"))
    measured_text = _coerce_text(getattr(selected_kb, "measured", "")) or _coerce_text(source.get("measured"))
    candidate_text = " ".join(
        part
        for part in (
            measured_text,
            _coerce_text(source.get("measure_range_text") or source.get("measure_range")),
            _coerce_text(source.get("raw") or source.get("raw_block")),
        )
        if part
    )
    inferred, _, _ = infer_semantic_subtype(
        _coerce_text(getattr(selected_kb, "capability_target", "")),
        section_label=param_name,
        item_label=contract_source_value(contract, "item_label") or measured_text,
        condition_axis=contract_source_value(contract, "condition_axis"),
        condition_value=contract_source_value(contract, "condition_value"),
        nominal_value=contract_source_value(contract, "nominal_value"),
        reference_value=contract_source_value(contract, "reference_value") or _coerce_text(reference_val),
        measure_value=contract_source_value(contract, "measure_value") or _coerce_text(measure_val),
        error_value=contract_source_value(contract, "error_value") or _coerce_text(error_val),
        limit_value=contract_source_value(contract, "limit_value"),
        unit_family=_coerce_text(getattr(selected_kb, "unit_family", ""))
        or contract_source_value(contract, "unit_family")
        or "unknown",
        candidate_text=candidate_text,
    )
    return inferred or current or contract_subtype


def _resolve_uncertainty_probe_value(
    param: Dict[str, Any],
    measure_val: str,
    error_val: str,
    *,
    selected_kb: Optional[KbCapability] = None,
    reference_val: str = "",
) -> str:
    """
    证书列头是 plain U 且解析器标记 unit_inherited=true 时，
    U 的量纲应继承结果列，而不是标称/参考值列。
    """
    if selected_kb is not None:
        effective_subtype = _resolve_effective_probe_subtype(
            selected_kb,
            param=param,
            measure_val=measure_val,
            error_val=error_val,
            reference_val=reference_val,
        )
        role = subtype_probe_role(
            selected_kb.capability_target,
            effective_subtype,
            "uncertainty_probe_role",
            "measure_value",
        )
        contract = _get_parameter_contract(param)
        role_map = {
            "measure_value": contract_source_value(contract, "measure_value") or _coerce_text(measure_val),
            "error_value": contract_source_value(contract, "error_value") or _coerce_text(error_val),
            "reference_value": contract_source_value(contract, "reference_value") or _coerce_text(reference_val),
            "condition_value": contract_source_value(contract, "condition_value"),
        }
        role_value = _coerce_text(role_map.get(role))
        if role_value:
            return role_value

    parser_meta = _get_parser_meta(param)
    if not parser_meta:
        return measure_val

    header_rules = parser_meta.get("header_rules")
    cert_u_header = header_rules.get("cert_u") if isinstance(header_rules, dict) else ""
    if not _is_plain_cert_u_header(cert_u_header):
        return measure_val

    inherited_probe = _coerce_text(error_val)
    if parser_meta.get("unit_inherited"):
        return inherited_probe or measure_val

    # 兼容旧 JSON：开机特性这类 reference_oscillator 单值结果行可能还未补上
    # unit_inherited 标记，但 cert_u/plain U 与 error_value 的从属关系已经明确。
    section_rule = _coerce_text(parser_meta.get("section_rule"))
    has_error_header = bool(_coerce_text(header_rules.get("error_value"))) if isinstance(header_rules, dict) else False
    if inherited_probe and not _coerce_text(measure_val) and section_rule == "reference_oscillator" and has_error_header:
        return inherited_probe

    param_name = _coerce_text(param.get("param_name") or param.get("项目名称") or param.get("测量值"))
    if inherited_probe and not _coerce_text(measure_val) and _is_reference_oscillator_param_name(param_name):
        return inherited_probe

    return measure_val


def _uncertainty_representation_kind(text: str) -> str:
    raw = _coerce_text(text)
    if not raw:
        return "unknown"

    lowered = raw.lower()
    if "urel" in lowered or "%" in raw:
        return "relative"

    unit = extract_primary_unit_token(raw)
    if _is_power_unit(unit):
        return "power_db"
    if _is_voltage_unit(unit):
        return "voltage_linear"
    if unit.lower() in {"a", "ma", "ua", "μa"}:
        return "current_linear"
    if unit.lower() in {"hz", "khz", "mhz", "ghz", "thz"}:
        return "frequency_linear"
    if unit.lower() in {"s", "ms", "us", "μs", "ns", "ps", "s/d", "s/m"}:
        return "time_linear"
    return "unknown"


def _evaluate_reference_measure_error_consistency(
    reference_value: str,
    measure_value: str,
    error_value: str,
) -> Dict[str, Any]:
    reference_text = _coerce_text(reference_value)
    measure_text = _coerce_text(measure_value)
    error_text = _coerce_text(error_value)
    if not reference_text or not measure_text or not error_text:
        return {"detected": False, "reason": ""}

    reference_kind = _uncertainty_representation_kind(reference_text)
    measure_kind = _uncertainty_representation_kind(measure_text)
    error_kind = _uncertainty_representation_kind(error_text)
    comparable_kinds = {
        "frequency_linear",
        "time_linear",
        "voltage_linear",
        "current_linear",
    }
    if (
        reference_kind not in comparable_kinds
        or measure_kind not in comparable_kinds
        or error_kind not in comparable_kinds
        or reference_kind != measure_kind
        or reference_kind != error_kind
    ):
        return {"detected": False, "reason": ""}

    reference_num, _ = parse_value_with_unit(reference_text, keep_sign=True)
    measure_num, _ = parse_value_with_unit(measure_text, keep_sign=True)
    error_num, _ = parse_value_with_unit(error_text, keep_sign=True)
    if reference_num is None or measure_num is None or error_num is None:
        return {"detected": False, "reason": ""}

    expected_error = measure_num - reference_num
    observed_error = error_num
    tolerance = max(
        1e-12,
        abs(expected_error) * 5e-3,
        abs(observed_error) * 5e-3,
    )
    if math.isclose(expected_error, observed_error, rel_tol=0.0, abs_tol=tolerance):
        return {"detected": False, "reason": ""}

    reason = (
        "parser/source anomaly: normalized reference/measure/error are inconsistent "
        f"(measure-reference={expected_error:.12g}, error={observed_error:.12g})"
    )
    return {
        "detected": True,
        "reason": reason,
        "expected_error": expected_error,
        "observed_error": observed_error,
        "tolerance": tolerance,
    }


def _resolve_uncertainty_comparability(
    selection_result: Any,
    selected_kb: Optional[KbCapability],
    *,
    cert_u: str,
    kb_u: str,
    probe_value: str,
) -> Dict[str, Any]:
    if selection_result is None or selected_kb is None:
        return {"comparable": True, "decision": "compare", "reason": ""}

    cert_point = getattr(selection_result, "cert_point", None)
    audit = getattr(selection_result, "audit", None)
    cert_target = _coerce_text(getattr(cert_point, "semantic_target", ""))
    cert_subtype = _coerce_text(getattr(cert_point, "semantic_subtype", ""))
    candidate_target = _coerce_text(getattr(selected_kb, "capability_target", ""))
    candidate_subtype = _coerce_text(getattr(selected_kb, "semantic_subtype", ""))
    selected_target_relation = _coerce_text(getattr(audit, "selected_target_relation", ""))
    used_fallback = bool(getattr(audit, "used_fallback_candidate_target", False))

    cert_mode = subtype_comparison_mode(cert_target, cert_subtype, "")
    candidate_mode = subtype_comparison_mode(candidate_target, candidate_subtype, "")
    cert_u_policy = subtype_text_option(cert_target, cert_subtype, "uncertainty_policy", "")

    if (
        used_fallback
        and selected_target_relation == "fallback_cross_target"
        and cert_target == "period_accuracy"
        and candidate_target == "period_range"
        and cert_mode == "limit_error"
        and candidate_mode == "range_measure"
        and _coerce_text(cert_u)
        and _coerce_text(kb_u)
        and _coerce_text(probe_value)
    ):
        reason = (
            "period_accuracy fallback to period_range candidate; "
            "candidate uncertainty belongs to range capability and is not directly comparable"
        )
        return {
            "comparable": False,
            "decision": "review_skip",
            "reason": reason,
            "selected_target_relation": selected_target_relation,
            "cert_mode": cert_mode,
            "candidate_mode": candidate_mode,
        }

    if (
        cert_u_policy == "representation_sensitive_skip"
        and cert_target == candidate_target
        and _coerce_text(cert_u)
        and _coerce_text(kb_u)
    ):
        cert_repr = _uncertainty_representation_kind(cert_u)
        kb_repr = _uncertainty_representation_kind(kb_u)
        if (
            cert_repr != "unknown"
            and kb_repr != "unknown"
            and cert_repr != kb_repr
        ):
            reason = (
                "candidate uncertainty uses a different representation from certificate uncertainty; "
                "skip direct uncertainty comparison"
            )
            return {
                "comparable": False,
                "decision": "skip_compare",
                "reason": reason,
                "selected_target_relation": selected_target_relation,
                "cert_mode": cert_mode,
                "candidate_mode": candidate_mode,
                "cert_repr": cert_repr,
                "kb_repr": kb_repr,
            }

    return {
        "comparable": True,
        "decision": "compare",
        "reason": "",
        "selected_target_relation": selected_target_relation,
        "cert_mode": cert_mode,
        "candidate_mode": candidate_mode,
    }


def _evaluate_selected_kb_results(
    *,
    selection_result: Any,
    selected_candidate: Optional[Any],
    selected_kb: KbCapability,
    param: Dict[str, Any],
    measure_val: str,
    reference_val: str,
    error_val: str,
    cert_u: str,
) -> Dict[str, Any]:
    kb_source = selected_candidate.source if selected_candidate is not None else (selected_kb.source or {})
    kb_range = _coerce_text(kb_source.get("measure_range_text")) or "N/A"
    kb_error = _extract_kb_error_limit(
        kb_source,
        strict_keys_only=bool(selected_kb and selected_kb.capability_target == "reference_oscillator"),
    )
    kb_u = _format_uncertainty_text(kb_source.get("uncertainty"))
    kb_code = _coerce_text(kb_source.get("file_code"), "N/A") or "N/A"
    kb_measured = _format_kb_measured_display(
        kb_source.get("measured"),
        kb_range,
        selected_kb.capability_target if selected_kb else "",
    )
    explicit_limit_text = _extract_param_limit_value(param)
    display_limit = explicit_limit_text or "N/A"
    contract = _get_parameter_contract(param)
    explicit_limit = bool(
        contract_source_value(contract, "limit_value")
        or _coerce_text(_get_normalized_mapping(param).get("limit_value"))
    )
    if (
        selected_kb.capability_target == "reference_oscillator"
        and not explicit_limit
        and _is_plausible_reference_oscillator_frequency(display_limit)
    ):
        display_limit = "N/A"
    limit_for_check = explicit_limit_text
    range_probe_value = _resolve_range_probe_value(
        selected_kb,
        measure_val,
        error_val,
        param=param,
        reference_val=reference_val,
    )
    semantic_ambiguity = _evaluate_reference_oscillator_probe_ambiguity(
        param=param,
        selected_kb=selected_kb,
        selected_candidate=selected_candidate,
        range_probe_value=range_probe_value,
        reference_val=reference_val,
        measure_val=measure_val,
    )
    uncertainty_probe_value = _resolve_uncertainty_probe_value(
        param,
        measure_val,
        error_val,
        selected_kb=selected_kb,
        reference_val=reference_val,
    )
    uncertainty_gate = _resolve_uncertainty_comparability(
        selection_result,
        selected_kb,
        cert_u=cert_u,
        kb_u=kb_u,
        probe_value=uncertainty_probe_value,
    )
    source_anomaly = _evaluate_reference_measure_error_consistency(
        reference_val,
        measure_val,
        error_val,
    )

    if _is_input_sensitivity_match_item(kb_measured, kb_range):
        range_result = _verify_input_sensitivity_composite_range(
            measure_val,
            error_val,
            kb_range,
        )
    else:
        range_result = json.loads(
            verify_range_logic(range_probe_value, kb_range, selected_candidate=selected_candidate)
        )
    range_result = _maybe_override_reference_oscillator_range_result(
        param=param,
        selected_kb=selected_kb,
        selected_candidate=selected_candidate,
        range_probe_value=range_probe_value,
        range_result=range_result,
        semantic_ambiguity=semantic_ambiguity,
        reference_val=reference_val,
        measure_val=measure_val,
    )
    error_result = json.loads(verify_error_logic(error_val, limit_for_check, measure_val))
    if uncertainty_gate.get("decision") == "review_skip":
        if (
            not source_anomaly.get("detected")
            and range_result.get("status") == "PASS"
            and error_result.get("status") == "PASS"
        ):
            u_result = {
                "status": "PASS",
                "reason": (
                    "period_accuracy fallback_cross_target accepted by policy; "
                    + _coerce_text(uncertainty_gate.get("reason"))
                    + ", so uncertainty comparison was skipped"
                ),
                "comparison_mode": "skip_compare_by_policy",
                "calc_type": "uncertainty",
            }
        else:
            u_result = {
                "status": "REVIEW",
                "reason": uncertainty_gate.get("reason"),
                "comparison_mode": "review_skip",
                "calc_type": "uncertainty",
            }
    elif uncertainty_gate.get("decision") == "skip_compare":
        u_result = {
            "status": "PASS",
            "reason": uncertainty_gate.get("reason"),
            "comparison_mode": "skip_compare",
            "calc_type": "uncertainty",
        }
    else:
        u_result = json.loads(verify_uncertainty_logic(uncertainty_probe_value, cert_u, kb_u))

    return {
        "kb_source": kb_source,
        "kb_range": kb_range,
        "kb_error": kb_error,
        "kb_u": kb_u,
        "kb_code": kb_code,
        "kb_measured": kb_measured,
        "display_limit": display_limit,
        "limit_for_check": limit_for_check,
        "range_probe_value": range_probe_value,
        "uncertainty_probe_value": uncertainty_probe_value,
        "uncertainty_gate": uncertainty_gate,
        "source_anomaly": source_anomaly,
        "semantic_ambiguity": semantic_ambiguity,
        "range_result": range_result,
        "error_result": error_result,
        "u_result": u_result,
    }


def _resolve_selected_kb_status(
    range_result: Dict[str, Any],
    error_result: Dict[str, Any],
    u_result: Dict[str, Any],
    source_anomaly: Dict[str, Any],
    semantic_ambiguity: Optional[Dict[str, Any]] = None,
) -> str:
    statuses = {
        range_result.get("status"),
        error_result.get("status"),
        u_result.get("status"),
    }
    if "FAIL" in statuses:
        return "FAIL"
    if "REVIEW" in statuses:
        return "REVIEW"
    if source_anomaly.get("detected"):
        return "REVIEW"
    if dict(semantic_ambiguity or {}).get("detected"):
        return "REVIEW"
    return "PASS"


def _reference_oscillator_explicit_frequency_probes(
    *,
    param: Dict[str, Any],
    reference_val: str,
    measure_val: str,
) -> List[str]:
    contract = _get_parameter_contract(param)
    detail_source = _get_detail_mapping(param) or param
    probes = [
        _coerce_text(contract_source_value(contract, "condition_value")),
        _coerce_text(contract_source_value(contract, "nominal_value")),
        _coerce_text(contract_source_value(contract, "reference_value")) or _coerce_text(reference_val),
        _coerce_text(contract_source_value(contract, "measure_value")) or _coerce_text(measure_val),
        _extract_reference_oscillator_frequency_value(detail_source if isinstance(detail_source, dict) else {}),
    ]
    normalized: List[str] = []
    for probe in probes:
        text = _coerce_text(probe)
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def _evaluate_reference_oscillator_probe_ambiguity(
    *,
    param: Dict[str, Any],
    selected_kb: Optional[KbCapability],
    selected_candidate: Optional[Any],
    range_probe_value: str,
    reference_val: str,
    measure_val: str,
) -> Dict[str, Any]:
    if not selected_kb or selected_kb.capability_target != "reference_oscillator":
        return {"detected": False, "reason": ""}

    source = selected_candidate.source if selected_candidate is not None else (selected_kb.source or {})
    candidate_range = _coerce_text(source.get("measure_range_text") or source.get("measure_range"))
    if not candidate_range or _coerce_text(range_probe_value) != candidate_range:
        return {"detected": False, "reason": ""}

    explicit_probes = _reference_oscillator_explicit_frequency_probes(
        param=param,
        reference_val=reference_val,
        measure_val=measure_val,
    )
    if any(_is_plausible_reference_oscillator_frequency(probe) for probe in explicit_probes if probe):
        return {"detected": False, "reason": ""}

    return {
        "detected": True,
        "reason": (
            "reference oscillator frequency point is ambiguous: certificate lacks a plausible MHz/GHz probe, "
            "so range verification cannot safely fall back to KB applicability points"
        ),
    }


def _maybe_override_reference_oscillator_range_result(
    *,
    param: Dict[str, Any],
    selected_kb: Optional[KbCapability],
    selected_candidate: Optional[Any],
    range_probe_value: str,
    range_result: Dict[str, Any],
    semantic_ambiguity: Dict[str, Any],
    reference_val: str,
    measure_val: str,
) -> Dict[str, Any]:
    if not selected_kb or selected_kb.capability_target != "reference_oscillator":
        return range_result
    if not dict(semantic_ambiguity or {}).get("detected"):
        return range_result
    if _coerce_text(range_result.get("status")) != "PASS":
        return range_result

    source = selected_candidate.source if selected_candidate is not None else (selected_kb.source or {})
    candidate_range = _coerce_text(source.get("measure_range_text") or source.get("measure_range"))
    if not candidate_range or _coerce_text(range_probe_value) != candidate_range:
        return range_result

    explicit_probes = _reference_oscillator_explicit_frequency_probes(
        param=param,
        reference_val=reference_val,
        measure_val=measure_val,
    )
    low_freq_probe = next(
        (
            probe
            for probe in explicit_probes
            if probe
            and _extract_frequency_hz_from_text(probe) is not None
            and not _is_plausible_reference_oscillator_frequency(probe)
        ),
        "",
    )
    if not low_freq_probe:
        return range_result

    return {
        "status": "REVIEW",
        "reason": (
            "范围核验:REVIEW("
            f"证书仅给出低频显示/输出 {low_freq_probe}，无法确认其对应的认可晶振输出频点；"
            f"KB适用频点={candidate_range})"
        ),
        "calc_type": "range",
    }


def _is_carrier_frequency_error_capability(selected_kb: Optional[KbCapability]) -> bool:
    if not selected_kb or selected_kb.capability_target != "frequency_accuracy":
        return False
    source = selected_kb.source or {}
    text = " ".join(
        part
        for part in (
            _coerce_text(getattr(selected_kb, "measured", "")),
            _coerce_text(source.get("measure_range_text")),
            _coerce_text(source.get("raw")),
            _coerce_text(source.get("raw_block")),
        )
        if part
    ).lower()
    return any(token in text for token in ("载波频率偏差", "carrier frequency deviation", "carrier_frequency_deviation"))


def _absolute_probe_text(value: str) -> str:
    raw = _coerce_text(value)
    if not raw:
        return ""
    parsed, _ = parse_value_with_unit(raw, keep_sign=True)
    if parsed is None:
        return raw
    unit = extract_primary_unit_token(raw)
    return f"{abs(parsed):.12g} {unit}".strip() if unit else f"{abs(parsed):.12g}"


def _resolve_range_probe_value(
    selected_kb: Optional[KbCapability],
    measure_val: str,
    error_val: str,
    *,
    param: Optional[Dict[str, Any]] = None,
    reference_val: str = "",
) -> str:
    measure_probe = _coerce_text(measure_val)
    error_probe = _coerce_text(error_val)
    reference_probe = _coerce_text(reference_val)

    if not selected_kb:
        return measure_probe
    if selected_kb.capability_target == "period_range":
        return reference_probe or measure_probe
    if param is not None:
        contract = _get_parameter_contract(param)
        effective_subtype = _resolve_effective_probe_subtype(
            selected_kb,
            param=param,
            measure_val=measure_val,
            error_val=error_val,
            reference_val=reference_val,
        )
        if (
            selected_kb.capability_target == "frequency_accuracy"
            and effective_subtype == "timebase_accuracy"
        ):
            for probe in _reference_oscillator_explicit_frequency_probes(
                param=param,
                reference_val=reference_val,
                measure_val=measure_val,
            ):
                if _is_plausible_reference_oscillator_frequency(probe):
                    return probe
        if (
            selected_kb.capability_target == "frequency_accuracy"
            and effective_subtype == "carrier_frequency_error"
        ):
            absolute_error_probe = _absolute_probe_text(
                contract_source_value(contract, "error_value") or error_probe
            )
            if absolute_error_probe:
                return absolute_error_probe
        if selected_kb.capability_target == "reference_oscillator":
            source = selected_kb.source or {}
            candidate_range = _coerce_text(source.get("measure_range_text") or source.get("measure_range"))
            candidate_frequency_probe = _extract_frequency_token_from_text(candidate_range)
            if candidate_frequency_probe:
                condition_probe = _coerce_text(contract_source_value(contract, "condition_value"))
                if condition_probe:
                    return condition_probe
                return candidate_range
            if not candidate_range:
                condition_probe = _coerce_text(contract_source_value(contract, "condition_value"))
                if condition_probe:
                    return condition_probe
                for probe in (reference_probe, measure_probe):
                    if _is_plausible_reference_oscillator_frequency(probe):
                        return probe
        role_name = "range_probe_role"
        if (
            selected_kb.capability_target == "reference_oscillator"
            and subtype_comparison_mode(selected_kb.capability_target, effective_subtype, "") == "reference_metric"
        ):
            source = selected_kb.source or {}
            candidate_range = _coerce_text(source.get("measure_range_text") or source.get("measure_range"))
            if not _extract_frequency_token_from_text(candidate_range):
                role_name = "error_probe_role"
        role = subtype_probe_role(
            selected_kb.capability_target,
            effective_subtype,
            role_name,
            "measure_value",
        )
        role_map = {
            "measure_value": contract_source_value(contract, "measure_value") or measure_probe,
            "error_value": contract_source_value(contract, "error_value") or error_probe,
            "reference_value": contract_source_value(contract, "reference_value") or reference_probe,
            "condition_value": (
                contract_source_value(contract, "condition_value")
                or contract_source_value(contract, "item_label")
                or reference_probe
                or measure_probe
            ),
        }
        role_value = _coerce_text(role_map.get(role))
        if role_value:
            return role_value
    if selected_kb.capability_target == "reference_oscillator":
        source = selected_kb.source or {}
        candidate_range = _coerce_text(source.get("measure_range_text") or source.get("measure_range"))
        candidate_frequency_probe = _extract_frequency_token_from_text(candidate_range)
        if candidate_frequency_probe:
            return candidate_frequency_probe
        for probe in (reference_probe, measure_probe):
            if _is_plausible_reference_oscillator_frequency(probe):
                return probe
        return error_probe or reference_probe or measure_probe
    if _is_carrier_frequency_error_capability(selected_kb):
        if _is_plain_hz_error(error_probe):
            return _absolute_probe_text(error_probe)
        return error_probe or measure_probe
    if selected_kb.result_quantity == "power_error":
        return error_probe or measure_probe
    source = selected_kb.source or {}
    measured_text = _coerce_text(source.get("measured")).lower()
    if selected_kb.capability_target == "dynamic_range" and any(
        token in measured_text for token in ("伪距分辨力", "pseudorange resolution", "伪距率分辨力", "pseudorange rate resolution")
    ):
        return error_probe or measure_probe
    return measure_probe


def _is_input_sensitivity_match_item(match_item: str, range_val: str = "") -> bool:
    semantic_text = " ".join(part for part in [str(match_item or ""), str(range_val or "")] if part).lower()
    keywords = [
        "input_sensitivity",
        "frequency_measurement_range_and_input_sensitivity",
        "period_measurement_range_and_input_sensitivity",
        "频率测量范围及输入灵敏度",
        "周期测量范围及输入灵敏度",
        "输入灵敏度",
        "trigger sensitivity",
        "sensitivity",
    ]
    return any(keyword.lower() in semantic_text for keyword in keywords)


def _looks_like_garbled_text(text: str) -> bool:
    s = str(text or "").strip()
    if not s:
        return True

    mojibake_markers = [
        "锝", "鍔", "鏍", "涓", "鐢", "鍙", "绗", "浠", "鑼", "寮", "璇", "璁", "鏃", "鈿", "馃",
        "鐏", "垫", "晱", "�",
    ]
    if any(marker in s for marker in mojibake_markers):
        return True
    if "?" in s and re.search(r"[^\x00-\x7F]", s):
        return True
    weird_count = sum(s.count(ch) for ch in ["?", "□", "�"])
    return weird_count >= 2


def _is_input_sensitivity_check_param_name(param_name: str) -> bool:
    text = _coerce_text(param_name).lower()
    if not text:
        return False
    return any(
        token in text
        for token in (
            "input sensitivity",
            "trigger sensitivity",
            "frequency measurement and sensitivity",
            "frequency measurement range and sensitivity",
            "frequency measurement range and input sensitivity",
            "period measurement and sensitivity",
            "period measurement range and sensitivity",
            "period measurement range and input sensitivity",
            "输入灵敏度",
            "触发灵敏度",
            "灵敏度",
            "频率测量范围及输入灵敏度",
            "频率测量范围及灵敏度",
            "周期测量范围及输入灵敏度",
            "周期测量范围及灵敏度",
        )
    )


def _should_auto_pass_input_sensitivity_row(
    param_name: str,
    measure_val: str,
    *,
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
    *,
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


def _resolve_input_sensitivity_business_override(
    *,
    param_name: str,
    selection_result: Any,
    measure_val: str,
    cert_u: str,
    error_val: str,
    limit_val: str,
) -> Optional[Tuple[str, str]]:
    cert_point = getattr(selection_result, "cert_point", None) if selection_result is not None else None
    semantic_target = _coerce_text(getattr(cert_point, "semantic_target", ""))
    if semantic_target != "input_sensitivity" and not _is_input_sensitivity_check_param_name(param_name):
        return None

    if _should_fail_input_sensitivity_row_for_garble(
        param_name,
        measure_val,
        cert_u=cert_u,
        error_val=error_val,
        limit_val=limit_val,
    ):
        return (
            "FAIL",
            "按业务规则：输入灵敏度类参数仅检查文本是否存在乱码；当前检测到乱码或异常文本，跳过依据核验并判定FAIL",
        )

    if _should_auto_pass_input_sensitivity_row(
        param_name,
        measure_val,
        cert_u=cert_u,
        error_val=error_val,
        limit_val=limit_val,
    ):
        return (
            "PASS",
            "按业务规则：输入灵敏度类参数仅检查文本是否存在乱码；当前文本正常，跳过依据核验并判定PASS",
        )
    return None


def _extract_sensitivity_token(text: str) -> str:
    s = str(text or "")
    if not s:
        return ""

    patterns = [
        r"(?:灵敏度|Sensitivity|trigger level|threshold)[^:：]*[:：]\s*([^,，;\n]+)",
        r"([-+]?\d*\.?\d+\s*(?:dBmV|dBm|mV|uV|渭V|V|Vrms|Vpp))",
    ]
    for pattern in patterns:
        match = re.search(pattern, s, flags=re.IGNORECASE)
        if not match:
            continue
        token = _extract_value_token(match.group(1))
        if token:
            return token
    return ""


def _convert_sensitivity_token_for_range(token: str, outer_range: str) -> Tuple[str, List[str]]:
    notes: List[str] = []
    if not token:
        return "", notes

    raw = str(token).strip()
    num_match = re.search(r"([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)", raw)
    if not num_match:
        return token, notes

    parsed_value = float(num_match.group(1))
    unit_match = re.search(r"(dBmV|dBm|dB)\b", raw, re.IGNORECASE)
    token_unit = _normalize_unit_text(unit_match.group(1) if unit_match else "")
    token_unit_lower = token_unit.lower()

    if token_unit_lower in {"dbm", "dbmv"}:
        if token_unit_lower == "dbm":
            power_w = 10 ** (parsed_value / 10.0) / 1000.0
            vrms = math.sqrt(power_w * 50.0)
            vpp = vrms * 2.0 * math.sqrt(2.0)
            notes.append(f"单位换算：{token} -> {vpp:.6g} V")
            return f"{vpp:.6g} V", notes

        vrms = (10 ** (parsed_value / 20.0)) * 1e-3
        vpp = vrms * 2.0 * math.sqrt(2.0)
        notes.append(f"单位换算：{token} -> {vpp:.6g} V")
        return f"{vpp:.6g} V", notes

    if token_unit_lower in {"db", "dbc", "dbc/hz"}:
        notes.append(f"保留原值：{token}")
        return token, notes

    return token, notes


def _verify_input_sensitivity_composite_range(
    frequency_val: str,
    sensitivity_val: str,
    range_val: str,
) -> Dict[str, Any]:
    range_text = str(range_val or "")
    outer_range = re.sub(r"\([^)]*\)", "", range_text).strip()
    axis_match = re.search(r"\(([^)]*)\)", range_text)
    axis_range = axis_match.group(1).strip() if axis_match else ""

    axis_payload = None
    amp_payload = None

    if axis_range and frequency_val:
        axis_payload = json.loads(verify_range_logic(frequency_val, axis_range))

    sensitivity_token = _extract_sensitivity_token(sensitivity_val)
    if not sensitivity_token:
        sensitivity_token = _extract_sensitivity_token(frequency_val)
    converted_token, conversion_notes = _convert_sensitivity_token_for_range(sensitivity_token, outer_range)

    if outer_range and converted_token:
        converted_numeric, _ = parse_value_with_unit(converted_token, keep_sign=True)
        outer_parts = [part.strip() for part in re.split(r"[~～,，]", outer_range) if part.strip()]
        if converted_numeric is not None and len(outer_parts) >= 2:
            lower_val, _ = parse_value_with_unit(outer_parts[0], keep_sign=True)
            upper_val, _ = parse_value_with_unit(outer_parts[1], keep_sign=True)
            if lower_val is not None and upper_val is not None:
                lower, upper = (lower_val, upper_val) if lower_val <= upper_val else (upper_val, lower_val)
                tolerance = max(abs(upper - lower) * 0.01, 1e-15)
                pass_flag = (converted_numeric >= (lower - tolerance)) and (converted_numeric <= (upper + tolerance))
                amp_payload = {
                    "status": "PASS" if pass_flag else "FAIL",
                    "reason": (
                        f"测量值({converted_token})在范围内 [{outer_parts[0]}, {outer_parts[1]}]"
                        if pass_flag
                        else f"测量值({converted_token})不在范围内 [{outer_parts[0]}, {outer_parts[1]}]"
                    ),
                    "calc_type": "range",
                }

        if amp_payload is None:
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
        reason_parts.append(f"频率范围核验:{axis_payload.get('status')}({axis_payload.get('reason')})")
    if amp_payload is not None:
        reason_parts.append(f"电平范围核验:{amp_payload.get('status')}({amp_payload.get('reason')})")
    reason_parts.extend(conversion_notes)
    return {
        "status": status,
        "reason": "；".join(reason_parts) if reason_parts else "复合输入灵敏度范围核验完成",
        "calc_type": "range",
    }


def _fallback_select_kb_entry(
    param_name: str,
    measure_val: str,
    error_val: str,
    cert_u: str,
    kb_items: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    query_parts = [
        _coerce_text(param_name),
        _coerce_text(measure_val),
        _coerce_text(error_val),
        _coerce_text(cert_u),
    ]
    query_norm = _normalize_key_for_match(" ".join(part for part in query_parts if part))
    if not query_norm or not kb_items:
        return None

    best_item = None
    best_score = 0.0
    for item in kb_items:
        candidate_parts = [
            _coerce_text(item.get("measured")),
            _coerce_text(item.get("standard_name")),
            _coerce_text(item.get("file_code")),
            _coerce_text(item.get("measure_range_segments_text")),
            _coerce_text(item.get("measure_range_text")),
            _coerce_text(item.get("error_limit_text")),
            _format_uncertainty_text(item.get("uncertainty")),
            _coerce_text(item.get("raw")),
        ]
        candidate_norm = _normalize_key_for_match(" ".join(part for part in candidate_parts if part))
        if not candidate_norm:
            continue

        score = 0.0
        if query_norm in candidate_norm or candidate_norm in query_norm:
            score += 5.0
        query_tokens = set(re.findall(r"[a-z0-9\u4e00-\u9fff]+", query_norm))
        candidate_tokens = set(re.findall(r"[a-z0-9\u4e00-\u9fff]+", candidate_norm))
        score += float(len(query_tokens & candidate_tokens))

        if any(token in query_norm for token in ["frequencymeasurement", "频率测量", "frequency measurement"]):
            if any(token in candidate_norm for token in ["periodmeasurement", "周期测量", "period measurement", "period_range", "周期"]):
                score += FALLBACK_SCORE_RULES["frequency_measurement"]["period_penalty"]
            if any(token in candidate_norm for token in ["frequency_range", "frequency", "频率"]):
                score += FALLBACK_SCORE_RULES["frequency_measurement"]["frequency_bonus"]
        if any(token in query_norm for token in ["periodmeasurement", "周期测量", "period measurement"]):
            if any(token in candidate_norm for token in ["frequencymeasurement", "频率测量", "frequency measurement", "frequency_range", "频率"]):
                score += FALLBACK_SCORE_RULES["period_measurement"]["frequency_penalty"]
            if any(token in candidate_norm for token in ["period_range", "period", "周期"]):
                score += FALLBACK_SCORE_RULES["period_measurement"]["period_bonus"]

        if any(token in query_norm for token in ["frequencymeasurementrange", "频率测量范围", "frequency range", "频率范围"]):
            if any(token in candidate_norm for token in ["input_sensitivity", "sensitivity", "灵敏度", "触发"]):
                score += FALLBACK_SCORE_RULES["frequency_measurement_range"]["sensitivity_penalty"]
            if any(token in candidate_norm for token in ["frequency_range", "frequency", "频率"]):
                score += FALLBACK_SCORE_RULES["frequency_measurement_range"]["frequency_bonus"]
        if any(token in query_norm for token in ["periodmeasurementrange", "周期测量范围", "period range", "周期范围"]):
            if any(token in candidate_norm for token in ["input_sensitivity", "sensitivity", "灵敏度", "触发"]):
                score += FALLBACK_SCORE_RULES["period_measurement_range"]["sensitivity_penalty"]
            if any(token in candidate_norm for token in ["period_range", "period", "周期"]):
                score += FALLBACK_SCORE_RULES["period_measurement_range"]["period_bonus"]
        if any(token in query_norm for token in ["sensitivity", "灵敏度", "trigger", "触发"]):
            if any(token in candidate_norm for token in ["input_sensitivity", "sensitivity", "灵敏度", "触发"]):
                score += FALLBACK_SCORE_RULES["sensitivity"]["sensitivity_bonus"]
            if any(token in candidate_norm for token in ["frequency_range", "frequency", "频率", "period_range", "period", "周期"]):
                score += FALLBACK_SCORE_RULES["sensitivity"]["non_sensitivity_penalty"]
        if score > best_score:
            best_score = score
            best_item = item

    return best_item if best_score > 0 else None


def _extract_kb_error_limit(source: Dict[str, Any], *, strict_keys_only: bool = False) -> str:
    if not isinstance(source, dict):
        return "N/A"

    for key in (
        "error_limit_text",
        "limit_text",
        "允许误差",
        "允许范围",
        "限值",
        "最大允许误差",
        "误差限值",
        "limit",
        "Limit",
    ):
        text = _coerce_text(source.get(key))
        if text:
            return text

    meta = source.get("meta") or source.get("metadata") or {}
    if isinstance(meta, dict):
        for key in (
            "error_limit_text",
            "limit_text",
            "允许误差",
            "允许范围",
            "限值",
            "最大允许误差",
            "误差限值",
            "limit",
            "Limit",
        ):
            text = _coerce_text(meta.get(key))
            if text:
                return text

    if strict_keys_only:
        return "N/A"

    raw = _coerce_text(source.get("raw"))
    if raw:
        patterns = [
            r"(?:最大允许误差|允许误差|误差限值|限值|limit)[：:\s]*([^。\n;；]+)",
            r"(?:误差|偏差)[：:\s]*([^。\n;；]+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, raw, re.IGNORECASE)
            if match:
                return match.group(1).strip()

        keyword_lines = []
        for line in raw.splitlines():
            line_text = _coerce_text(line)
            if not line_text:
                continue
            lowered = line_text.lower()
            if any(token in lowered for token in ("允许误差", "误差限值", "最大允许误差", "限值", "容差", "允差", "limit", "偏差")):
                keyword_lines.append(line_text)
        for line_text in keyword_lines:
            match = re.search(r"[：:]\s*([^。\n;；]+)", line_text)
            if match:
                candidate = match.group(1).strip()
                if candidate and not re.search(r"^\s*(n/?a|na|无|未知)\s*$", candidate, re.IGNORECASE):
                    return candidate
            if re.search(r"[≤≥<>]=?\s*[-+]?\d", line_text):
                return line_text.strip()

    return "N/A"


def _format_uncertainty_text(value: Any) -> str:
    if isinstance(value, dict):
        display = _coerce_text(value.get("value_display"))
        if display:
            return display
        raw = _coerce_text(value.get("value") or value.get("text") or value.get("raw"))
        if raw:
            return raw
        u_type = _coerce_text(value.get("type")).lower()
        if u_type in {"rel", "urel", "relative"}:
            prefix = "Urel="
        elif u_type in {"u", "absolute"}:
            prefix = "U="
        else:
            prefix = ""
        fallback = _coerce_text(value.get("expr") or value.get("formula"))
        if fallback:
            return f"{prefix}{fallback}" if prefix and not fallback.startswith(prefix) else fallback
    return _coerce_text(value, "N/A") or "N/A"


def _format_normalized_axis_value(value: Optional[float], axis_family: Optional[str]) -> str:
    if value is None:
        return "N/A"
    if axis_family == "frequency_band":
        return f"{value:.12g} Hz"
    if axis_family == "period_band":
        return f"{value:.12g} s"
    return f"{value:.12g}"


def _format_candidate_band_summary(candidate: Any) -> str:
    if candidate is None:
        return "N/A"
    axis_family = getattr(candidate, "condition_axis", None)
    band_kind = getattr(candidate, "band_kind", "none")
    if band_kind == "discrete":
        points = getattr(candidate, "discrete_points", ()) or ()
        display = ", ".join(_format_normalized_axis_value(point, axis_family) for point in points[:8])
        if len(points) > 8:
            display += ", ..."
        return display or "N/A"
    if band_kind == "range":
        lower = getattr(candidate, "band_lower", None)
        upper = getattr(candidate, "band_upper", None)
        return f"[{_format_normalized_axis_value(lower, axis_family)}, {_format_normalized_axis_value(upper, axis_family)}]"
    return "N/A"


def _audit_axis_labels_for_candidate(candidate: Any) -> Tuple[str, str]:
    if candidate is None:
        return "`测量点归一化` ", "`KB范围归一化` "

    capability_target = getattr(candidate, "capability_target", "")
    result_quantity = getattr(candidate, "result_quantity", "")
    axis_family = getattr(candidate, "condition_axis", None)

    if capability_target == "power_accuracy" and result_quantity in {"power_value", "power_error"}:
        if axis_family == "frequency_band":
            return "`频率轴归一化` ", "`候选频段归一化` "
        if axis_family == "period_band":
            return "`时间轴归一化` ", "`候选区间归一化` "

    return "`测量点归一化` ", "`KB范围归一化` "


def _format_cert_axis_for_candidate(
    candidate: Any,
    measure_value: str,
    reference_value: str,
    point_value: str,
    point_text: str,
) -> str:
    if candidate is None:
        return "N/A"
    axis_family = getattr(candidate, "condition_axis", None)
    capability_target = getattr(candidate, "capability_target", "")
    raw_inputs = (measure_value, reference_value, point_value, point_text)
    if capability_target in {"reference_oscillator", "period_range"}:
        raw_inputs = (reference_value, measure_value, point_value, point_text)
    for raw in raw_inputs:
        text = _coerce_text(raw)
        if not text or text == "N/A":
            continue
        if axis_family == "frequency_band":
            parsed = _extract_frequency_hz_from_text(text)
            if parsed is not None:
                return _format_normalized_axis_value(parsed, axis_family)
        elif axis_family == "period_band":
            parsed = _selector_module._extract_time_axis_from_text(text)
            if parsed is not None:
                return _format_normalized_axis_value(parsed, axis_family)
    return "N/A"


def _format_explanation_block(lines: List[str], max_len: int = 1200) -> str:
    cleaned = [_coerce_text(line) for line in lines if _coerce_text(line)]
    if not cleaned:
        return ""
    text = "<br>".join(cleaned)
    if len(text) <= max_len:
        return text
    truncated = text[:max_len].rstrip()
    if not truncated.endswith("..."):
        truncated += "..."
    return truncated


def _format_reason_summary(lines: List[str], max_len: int = 320) -> str:
    cleaned = [_coerce_text(line) for line in lines if _coerce_text(line)]
    if not cleaned:
        return ""
    text = "；".join(cleaned)
    if len(text) <= max_len:
        return text
    truncated = text[:max_len].rstrip()
    if not truncated.endswith("..."):
        truncated += "..."
    return truncated


def _simplify_review_reason_text(reason: str) -> str:
    text = _normalize_review_reason_text(reason)
    lowered = text.lower()
    if not text:
        return ""
    if any(
        token in lowered
        for token in (
            "same basis but no compatible candidate",
            "same basis missing kb subtype",
            "no candidate directly matches",
            "no compatible candidate",
            "kb无对应参数",
        )
    ):
        return "同规程下没有可直接匹配的KB条目，需人工核验"
    if "missing required fields" in lowered:
        return "证书缺少关键字段，需人工核验"
    if "unknown semantic" in lowered:
        return "参数语义不明确，需人工核验"
    if "unit family mismatch" in lowered:
        return "参数单位类型不匹配，需人工核验"
    if "fallback_cross_target" in lowered or "candidate uncertainty not directly comparable" in lowered:
        return "候选能力项可回退，但不确定度暂时无法直接比较，需人工核验"
    if "parser/source anomaly" in lowered or "source anomaly" in lowered:
        return "证书源数据前后不一致，需人工核验"
    return text


def _extract_comparison_from_reason(reason: str) -> Tuple[str, str]:
    text = _coerce_text(reason)
    if not text:
        return "", ""
    body_match = re.search(r":[A-Z]+\((.*)\)$", text)
    body = body_match.group(1) if body_match else text
    body = body.split("；", 1)[0].strip()

    discrete_pairs = (
        " 命中 KB 离散点 ",
        " 未命中 KB 离散点 ",
        " 在 ",
        " 不在 ",
        " <= ",
        " >= ",
        " < ",
        " > ",
        " 不满足 ",
    )
    for token in discrete_pairs:
        if token in body:
            left, right = body.split(token, 1)
            return left.strip(), right.strip()
    return "", ""


def _format_scalar_or_interval(value: Any) -> str:
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return f"[{value[0]}, {value[1]}]"
    text = _coerce_text(value)
    return text


def _summarize_range_check(result: Dict[str, Any]) -> str:
    payload = dict(result or {})
    status = _coerce_text(payload.get("status")).upper()
    reason = _coerce_text(payload.get("reason"))
    lowered = reason.lower()
    if not status:
        return ""
    if "skip" in lowered:
        return "范围信息不足，已跳过"

    compared_value, compared_target = _extract_comparison_from_reason(reason)
    if "对称范围核验" in reason or "对称限值核验" in reason:
        prefix = {
            "PASS": "指标值在允许区间内",
            "FAIL": "指标值超出允许区间",
            "REVIEW": "指标值需人工确认",
            "ERROR": "指标值解析失败",
        }.get(status, "")
        if compared_value and compared_target:
            return f"{prefix}（指标值: {compared_value}；允许区间: {compared_target}）"
        return prefix

    if "离散点" in reason:
        prefix = {
            "PASS": "频点符合",
            "FAIL": "频点未命中KB点集",
            "REVIEW": "频点需人工确认",
            "ERROR": "频点解析失败",
        }.get(status, "")
        if compared_value and compared_target:
            return f"{prefix}（频点: {compared_value}；点集: {compared_target}）"
        return prefix

    prefix = {
        "PASS": "范围符合",
        "FAIL": "范围不符合",
        "REVIEW": "范围需人工确认",
        "ERROR": "范围解析失败",
    }.get(status, "")
    if compared_value and compared_target:
        target_label = "允许区间" if compared_target.startswith("[") else "要求"
        return f"{prefix}（对比值: {compared_value}；{target_label}: {compared_target}）"
    return prefix


def _summarize_error_check(result: Dict[str, Any]) -> str:
    payload = dict(result or {})
    status = _coerce_text(payload.get("status")).upper()
    reason = _coerce_text(payload.get("reason")).lower()
    if not status:
        return ""
    if "skip" in reason:
        return "误差项缺少证书允许误差，已跳过"

    err_display = _format_scalar_or_interval(payload.get("error_value"))
    limit_display = _format_scalar_or_interval(payload.get("limit_value"))
    prefix = {
        "PASS": "误差符合",
        "FAIL": "误差超出允许误差",
        "REVIEW": "误差需人工确认",
        "ERROR": "误差解析失败",
    }.get(status, "")
    if err_display and limit_display:
        label = "允许区间" if limit_display.startswith("[") else "允许误差"
        return f"{prefix}（对比值: {err_display}；{label}: {limit_display}）"
    return prefix


def _summarize_uncertainty_check(result: Dict[str, Any]) -> str:
    payload = dict(result or {})
    status = _coerce_text(payload.get("status")).upper()
    reason = _coerce_text(payload.get("reason")).lower()
    if not status:
        return ""
    if "skip compare" in reason or "skipped" in reason:
        return "不确定度按规则跳过比较"
    if "not directly comparable" in reason or "需人工核验" in reason:
        return "不确定度暂时无法直接比较，需人工确认"

    cert_display = _coerce_text(payload.get("cert_u_display")) or _coerce_text(payload.get("cert_u"))
    kb_display = _coerce_text(payload.get("kb_u_display")) or _coerce_text(payload.get("kb_u"))
    prefix = {
        "PASS": "不确定度符合",
        "FAIL": "不确定度不满足要求",
        "REVIEW": "不确定度需人工确认",
        "ERROR": "不确定度解析失败",
    }.get(status, "")
    if cert_display and kb_display:
        return f"{prefix}（证书U: {cert_display}；要求: {kb_display}）"
    return prefix


def _summarize_check_result(label: str, result: Optional[Dict[str, Any]]) -> str:
    payload = dict(result or {})
    status = _coerce_text(payload.get("status")).upper()
    reason = _coerce_text(payload.get("reason")).lower()
    if not status:
        return ""

    if label == "范围":
        return _summarize_range_check(payload)

    if label == "误差":
        return _summarize_error_check(payload)

    if label == "不确定度":
        return _summarize_uncertainty_check(payload)

    return ""


def _summarize_source_anomaly(source_anomaly: Dict[str, Any]) -> str:
    if not dict(source_anomaly or {}).get("detected"):
        return ""
    return "证书源数据前后不一致，需人工确认"


def _summarize_semantic_ambiguity(semantic_ambiguity: Dict[str, Any]) -> str:
    if not dict(semantic_ambiguity or {}).get("detected"):
        return ""
    return "证书条件不够明确，需人工确认"


def _resolve_match_display_value(
    selected_kb: Optional[KbCapability],
    measure_value: str,
    range_probe_value: str,
) -> str:
    probe_text = _coerce_text(range_probe_value)
    measure_text = _coerce_text(measure_value)
    if selected_kb and selected_kb.capability_target == "period_range" and probe_text:
        return probe_text
    return measure_text or probe_text


def _normalize_merge_token(value: Any) -> str:
    text = _coerce_text(value, "")
    if not text or text.upper() == "N/A":
        return ""
    parsed, unit = parse_value_with_unit(text, keep_sign=True)
    if parsed is not None:
        unit_text = _normalize_unit_text(unit) if unit else ""
        return f"{parsed:.12g}{unit_text}".lower()
    return re.sub(r"\s+", "", text).lower()


def _param_signature_payload(param: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(param, dict):
        return {}
    return {k: v for k, v in param.items() if not str(k).startswith("__")}


def _build_point_key(
    *,
    param: Dict[str, Any],
    param_name: str,
    match_value: str,
    point_value: str,
    measure_value: str,
) -> str:
    param_token = _normalize_merge_token(param_name) or "unknown"
    key_parts: List[str] = [param_token]

    match_token = _normalize_merge_token(match_value)
    point_token = _normalize_merge_token(point_value)
    measure_token = _normalize_merge_token(measure_value)

    if match_token:
        key_parts.append(f"match:{match_token}")
    else:
        if point_token:
            key_parts.append(f"point:{point_token}")
        if measure_token:
            key_parts.append(f"measure:{measure_token}")

    if len(key_parts) == 1:
        signature = hashlib.sha1(
            json.dumps(_param_signature_payload(param), ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()[:12]
        key_parts.append(f"raw:{signature}")

    cert_index = param.get("__cert_index")
    if cert_index is not None:
        key_parts.append(f"idx:{cert_index}")

    return "|".join(key_parts)


def _build_table_row_dict(
    *,
    point_value: str,
    param_name: str,
    condition_text: str = "",
    kb_code: str,
    kb_item: str,
    match_value: str,
    range_text: str,
    cert_error: str,
    limit_text: str,
    cert_u: str,
    kb_u: str,
    status: str,
    reason: str,
) -> Dict[str, str]:
    return {
        "点位": _coerce_text(point_value, "N/A") or "N/A",
        "测量点": _coerce_text(param_name, "unknown") or "unknown",
        "测试条件": _coerce_text(condition_text, "N/A") or "N/A",
        "KB编号": _coerce_text(kb_code, "无") or "无",
        "KB条目": _coerce_text(kb_item, "N/A") or "N/A",
        "证书匹配项": _coerce_text(match_value, "N/A") or "N/A",
        "范围": _coerce_text(range_text, "N/A") or "N/A",
        "证书误差": _coerce_text(cert_error, "N/A") or "N/A",
        "允许误差": _coerce_text(limit_text, "N/A") or "N/A",
        "证书U": _coerce_text(cert_u, "N/A") or "N/A",
        "KB_U": _coerce_text(kb_u, "N/A") or "N/A",
        "判定": _coerce_text(status, "REVIEW") or "REVIEW",
        "说明": _coerce_text(reason),
    }


def _normalize_record_anomaly_flags(flags: Sequence[str]) -> Tuple[str, ...]:
    normalized: List[str] = []
    for flag in flags:
        text = _coerce_text(flag)
        if text and text not in normalized:
            normalized.append(text)
    return tuple(normalized)


def _resolve_structured_review_reason_type(
    *,
    status: str,
    anomaly_flags: Sequence[str],
    reason: str,
) -> str:
    if _coerce_text(status).upper() != "REVIEW":
        return ""
    flags = set(_normalize_record_anomaly_flags(anomaly_flags))
    if "kb_missing" in flags:
        return "kb_coverage_gap"
    if "source_anomaly" in flags:
        return "source_field_gap"
    if "reference_probe_ambiguity" in flags:
        return "semantic_ambiguity"
    if "fallback_cross_target" in flags:
        return "semantic_ambiguity"
    return _classify_review_reason(reason)


def _build_evaluation_record(
    *,
    basis_code: str,
    batch_label: str,
    batch_index: int,
    row_index: int,
    cert_index: int,
    param_name: str,
    point_key: str,
    match_value: str,
    point_value: str,
    status: str,
    reason: str,
    semantic_target: str = "",
    semantic_subtype: str = "",
    axis_family: str = "",
    axis_value: str = "",
    selected_candidate_id: str = "",
    candidate_target: str = "",
    candidate_primary_quantity: str = "",
    selected_target_relation: str = "",
    range_result: Optional[Dict[str, Any]] = None,
    error_result: Optional[Dict[str, Any]] = None,
    u_result: Optional[Dict[str, Any]] = None,
    anomaly_flags: Sequence[str] = (),
    planner_summary: Optional[Dict[str, Any]] = None,
    semantic_auditor_summary: Optional[Dict[str, Any]] = None,
    display_fields: Optional[Dict[str, str]] = None,
    review_reason_type: str = "",
) -> EvaluationRecord:
    normalized_status = _coerce_text(status, "REVIEW") or "REVIEW"
    normalized_reason = _coerce_text(reason)
    normalized_flags = _normalize_record_anomaly_flags(anomaly_flags)
    resolved_review_reason_type = review_reason_type or _resolve_structured_review_reason_type(
        status=normalized_status,
        anomaly_flags=normalized_flags,
        reason=normalized_reason,
    )
    rendered_fields = dict(display_fields or {})
    rendered_fields["判定"] = normalized_status
    rendered_fields["说明"] = normalized_reason
    return EvaluationRecord(
        basis_code=basis_code,
        batch_label=batch_label,
        batch_index=batch_index,
        row_index=row_index,
        cert_index=cert_index,
        param_name=param_name,
        point_key=point_key,
        match_value=match_value,
        point_value=point_value,
        status=normalized_status,
        reason=normalized_reason,
        semantic_target=_coerce_text(semantic_target),
        semantic_subtype=_coerce_text(semantic_subtype),
        axis_family=_coerce_text(axis_family),
        axis_value=_coerce_text(axis_value),
        selected_candidate_id=_coerce_text(selected_candidate_id),
        candidate_target=_coerce_text(candidate_target),
        candidate_primary_quantity=_coerce_text(candidate_primary_quantity),
        selected_target_relation=_coerce_text(selected_target_relation),
        range_result=dict(range_result or {}),
        error_result=dict(error_result or {}),
        u_result=dict(u_result or {}),
        anomaly_flags=normalized_flags,
        review_reason_type=resolved_review_reason_type,
        planner_summary=dict(planner_summary or {}),
        semantic_auditor_summary=dict(semantic_auditor_summary or {}),
        display_fields=rendered_fields,
    )


def _record_to_param_check_row(record: EvaluationRecord) -> ParamCheckRow:
    row_dict = dict(record.display_fields)
    return ParamCheckRow(
        basis_code=record.basis_code,
        batch_label=record.batch_label,
        batch_index=record.batch_index,
        row_index=record.row_index,
        cert_index=record.cert_index,
        param_name=record.param_name,
        point_key=record.point_key,
        match_value=record.match_value,
        point_value=record.point_value,
        status=record.status,
        reason=record.reason,
        kb_code=row_dict.get("KB编号", "无"),
        kb_item=row_dict.get("KB条目", "N/A"),
        range_text=row_dict.get("范围", "N/A"),
        cert_error=row_dict.get("证书误差", "N/A"),
        limit_text=row_dict.get("允许误差", "N/A"),
        cert_u=row_dict.get("证书U", "N/A"),
        kb_u=row_dict.get("KB_U", "N/A"),
        raw_row=row_dict,
        review_reason_type=record.review_reason_type,
        evaluation_record=record,
    )


def _row_evaluation_record(row: ParamCheckRow) -> Optional[EvaluationRecord]:
    return getattr(row, "evaluation_record", None)


def _row_review_reason_type(row: ParamCheckRow) -> str:
    record = _row_evaluation_record(row)
    if record is not None and record.review_reason_type:
        return record.review_reason_type
    return row.review_reason_type or _classify_review_reason(row.reason)


def _row_anomaly_flags(row: ParamCheckRow) -> Tuple[str, ...]:
    record = _row_evaluation_record(row)
    if record is not None:
        return record.anomaly_flags
    return ()


def _row_to_markdown_line(display_index: int, row: ParamCheckRow) -> str:
    values = [
        str(display_index),
        row.raw_row.get("点位", "N/A"),
        row.raw_row.get("测量点", "unknown"),
        row.raw_row.get("测试条件", "N/A"),
        row.raw_row.get("KB编号", "无"),
        row.raw_row.get("KB条目", "N/A"),
        row.raw_row.get("证书匹配项", "N/A"),
        row.raw_row.get("范围", "N/A"),
        row.raw_row.get("证书误差", "N/A"),
        row.raw_row.get("允许误差", "N/A"),
        row.raw_row.get("证书U", "N/A"),
        row.raw_row.get("KB_U", "N/A"),
        row.raw_row.get("判定", row.status),
        row.raw_row.get("说明", row.reason),
    ]
    escaped = [_escape_markdown_table_cell(value) for value in values]
    return "| " + " | ".join(escaped) + " |"


def _render_param_rows_table(rows: List[ParamCheckRow]) -> List[str]:
    lines = [
        "| " + " | ".join(PARAM_RESULT_TABLE_HEADER) + " |",
        "| " + " | ".join(["---"] * len(PARAM_RESULT_TABLE_HEADER)) + " |",
    ]
    for idx, row in enumerate(rows, 1):
        lines.append(_row_to_markdown_line(idx, row))
    return lines


REVIEW_REASON_LABELS = {
    "kb_coverage_gap": "KB覆盖缺口",
    "source_field_gap": "源字段缺口",
    "semantic_ambiguity": "语义/选择歧义",
    "other_review": "其他待核验",
}


def _normalize_review_reason_text(reason: str) -> str:
    text = _coerce_text(reason)
    if not text:
        return ""
    text = text.replace("<br>", " | ")
    return re.sub(r"^`[^`]+`\s*", "", text).strip()


def _classify_review_reason(reason: str) -> str:
    text = _normalize_review_reason_text(reason).lower()
    if not text:
        return "other_review"
    if any(
        token in text
        for token in (
            "kb无对应参数",
            "kb未覆盖",
            "same basis missing kb subtype",
            "no candidates for basis code",
        )
    ):
        return "kb_coverage_gap"
    if "missing required fields" in text:
        return "source_field_gap"
    if "source anomaly" in text or "parser/source anomaly" in text:
        return "source_field_gap"
    if any(
        token in text
        for token in (
            "unknown semantic",
            "axis extraction ambiguous",
            "unit family mismatch",
            "same basis but no compatible candidate",
            "fallback period_range candidate for period_accuracy",
            "candidate uncertainty not directly comparable",
            "fallback cross target uncertainty comparison blocked",
            "period_accuracy fallback to period_range candidate",
        )
    ):
        return "semantic_ambiguity"
    return "other_review"


def _resolve_review_reason_type(status: str, reason: str) -> str:
    if _coerce_text(status).upper() != "REVIEW":
        return ""
    return _classify_review_reason(reason)


def _summarize_structured_rows(rows: List[ParamCheckRow]) -> Dict[str, int]:
    summary = {
        "pass": 0,
        "fail": 0,
        "review": 0,
        "error": 0,
        "total": len(rows),
        "kb_missing_review": 0,
        "field_gap_review": 0,
        "semantic_review": 0,
        "other_review": 0,
        "real_fail": 0,
    }
    for row in rows:
        status = _coerce_text(row.status).upper()
        note = row.reason or ""
        if status == "PASS":
            summary["pass"] += 1
        elif status == "FAIL":
            summary["fail"] += 1
            summary["real_fail"] += 1
        elif status == "ERROR":
            summary["error"] += 1
        else:
            summary["review"] += 1
            reason_type = _row_review_reason_type(row)
            if reason_type == "kb_coverage_gap":
                summary["kb_missing_review"] += 1
            elif reason_type == "source_field_gap":
                summary["field_gap_review"] += 1
            elif reason_type == "semantic_ambiguity":
                summary["semantic_review"] += 1
            else:
                summary["other_review"] += 1
    return summary


def _render_summary_lines(
    summary: Dict[str, int],
    total_expected: int,
    *,
    title: str = "## 📊 最终核验统计",
) -> List[str]:
    lines = [
        title,
        f"- **通过(PASS)**: {summary['pass']} 个测量点",
        f"- **失败(FAIL)**: {summary['fail']} 个测量点",
    ]
    if summary["review"] > 0:
        lines.append(f"- **需人工复核(REVIEW)**: {summary['review']} 个测量点")
    if summary["error"] > 0:
        lines.append(f"- **错误(ERROR)**: {summary['error']} 个测量点")
    lines.append(f"- **总数**: {summary['total']} 个测量点")
    lines.append(f"- **KB未覆盖型待人工核验**: {summary['kb_missing_review']} 个测量点")
    lines.append(f"- **源字段缺口型待人工核验**: {summary['field_gap_review']} 个测量点")
    lines.append(f"- **语义/选择歧义型待人工核验**: {summary['semantic_review']} 个测量点")
    lines.append(f"- **其他待人工核验**: {summary['other_review']} 个测量点")
    lines.append(f"- **真实核验失败**: {summary['real_fail']} 个测量点")
    pending = max(total_expected - summary["total"], 0)
    if pending > 0:
        lines.append("")
        lines.append(f"- **未完成**: {pending} 个测量点")
    if summary["total"] > 0:
        lines.append("")
        lines.append(f"- **通过率**: {(summary['pass'] / summary['total']) * 100:.1f}%")
    return lines


def _render_basis_audit_section(
    *,
    criterion: str,
    instrument_name: str,
    total_params: int,
    total_measurement_points: int,
    rows: List[ParamCheckRow],
) -> List[str]:
    lines = [
        f"## 依据: {criterion}",
        "",
        "### 核验范围",
        f"- 仪器: {instrument_name}",
        f"- 依据: {criterion}",
        f"- 参数量: {total_params} 个",
        f"- 总测量点数: {total_measurement_points} 个",
        "",
    ]

    grouped: Dict[str, List[ParamCheckRow]] = {}
    for row in sorted(rows, key=lambda item: (item.batch_index, item.cert_index, item.row_index)):
        grouped.setdefault(row.batch_label, []).append(row)

    for batch_label, batch_rows in grouped.items():
        lines.append(f"### 参数：{batch_label}")
        lines.extend(_render_param_rows_table(batch_rows))
        lines.append("")

    lines.append("---")
    lines.extend(
        _render_summary_lines(
            _summarize_structured_rows(rows),
            total_measurement_points,
            title="## 📊 依据核验统计",
        )
    )
    return lines


def _render_basis_preview_section(criterion: str, batch_markdowns: Dict[int, str]) -> List[str]:
    lines = [f"## 依据: {criterion}", "", "### Batch 详细报告"]
    for idx in sorted(batch_markdowns):
        lines.append(f"#### [批次] Batch {idx}")
        lines.append(batch_markdowns[idx])
        lines.append("\n---\n")
    return lines


def _build_error_rows_for_params(
    params: List[Dict[str, Any]],
    *,
    basis_code: str,
    reason: str,
    batch_label: str = "Batch 0",
    batch_index: int = 0,
) -> List[ParamCheckRow]:
    rows: List[ParamCheckRow] = []
    for row_index, param in enumerate(params, 1):
        param_name = _coerce_text(param.get("param_name"), "unknown") or "unknown"
        point_value = _extract_param_point_value(param) or _coerce_text(param.get("点位"), "N/A") or "N/A"
        condition_text = _extract_param_condition_text(param) or "N/A"
        match_value = _extract_param_measure_value(param)
        cert_u = _extract_param_cert_u(param) or "N/A"
        cert_error = _extract_param_error_value(param) or "N/A"
        limit_text = _extract_param_limit_value(param) or "N/A"
        row_reason = _format_explanation_block([f"`待人工核验` {reason}"])
        row_dict = _build_table_row_dict(
            point_value=point_value,
            param_name=param_name,
            condition_text=condition_text,
            kb_code="无",
            kb_item="N/A",
            match_value=_coerce_text(match_value, "N/A") or "N/A",
            range_text="N/A",
            cert_error=cert_error,
            limit_text=limit_text,
            cert_u=cert_u,
            kb_u="N/A",
            status="ERROR",
            reason=row_reason,
        )
        point_key = _build_point_key(
            param=param,
            param_name=param_name,
            match_value=row_dict["证书匹配项"],
            point_value=point_value,
            measure_value=match_value,
        )
        record = _build_evaluation_record(
            basis_code=basis_code,
            batch_label=batch_label,
            batch_index=batch_index,
            row_index=row_index,
            cert_index=int(param.get("__cert_index", row_index) or row_index),
            param_name=param_name,
            point_key=point_key,
            match_value=row_dict["证书匹配项"],
            point_value=point_value,
            status="ERROR",
            reason=row_reason,
            display_fields=row_dict,
        )
        rows.append(_record_to_param_check_row(record))
    return rows


def _build_review_rows_for_params(
    params: List[Dict[str, Any]],
    *,
    basis_code: str,
    reason: str,
    batch_label: str = "Batch 0",
    batch_index: int = 0,
) -> List[ParamCheckRow]:
    rows: List[ParamCheckRow] = []
    for row_index, param in enumerate(params, 1):
        param_name = _coerce_text(param.get("param_name"), "unknown") or "unknown"
        point_value = _extract_param_point_value(param) or _coerce_text(param.get("点位"), "N/A") or "N/A"
        condition_text = _extract_param_condition_text(param) or "N/A"
        match_value = _extract_param_measure_value(param)
        cert_u = _extract_param_cert_u(param) or "N/A"
        cert_error = _extract_param_error_value(param) or "N/A"
        limit_text = _extract_param_limit_value(param) or "N/A"
        row_reason = _format_explanation_block([f"`待人工核验` {reason}"])
        row_dict = _build_table_row_dict(
            point_value=point_value,
            param_name=param_name,
            condition_text=condition_text,
            kb_code="无",
            kb_item="N/A",
            match_value=_coerce_text(match_value, "N/A") or "N/A",
            range_text="N/A",
            cert_error=cert_error,
            limit_text=limit_text,
            cert_u=cert_u,
            kb_u="N/A",
            status="REVIEW",
            reason=row_reason,
        )
        point_key = _build_point_key(
            param=param,
            param_name=param_name,
            match_value=row_dict["证书匹配项"],
            point_value=point_value,
            measure_value=match_value,
        )
        record = _build_evaluation_record(
            basis_code=basis_code,
            batch_label=batch_label,
            batch_index=batch_index,
            row_index=row_index,
            cert_index=int(param.get("__cert_index", row_index) or row_index),
            param_name=param_name,
            point_key=point_key,
            match_value=row_dict["证书匹配项"],
            point_value=point_value,
            status="REVIEW",
            reason=row_reason,
            anomaly_flags=("kb_missing",),
            display_fields=row_dict,
        )
        rows.append(_record_to_param_check_row(record))
    return rows


def _build_merged_reason(rows: List[ParamCheckRow], final_status: str, final_rationale: str) -> str:
    basis_states = ", ".join(f"{row.basis_code}:{row.status}" for row in rows)
    lines = [f"`归并结论` {final_rationale}", f"`依据状态` {basis_states}"]

    if final_status == "REVIEW":
        review_notes: List[str] = []
        review_types: Dict[str, int] = {}

        for row in rows:
            if _coerce_text(row.status).upper() != "REVIEW":
                continue
            reason_text = _simplify_review_reason_text(row.reason)
            if not reason_text:
                continue
            reason_type = _row_review_reason_type(row)
            review_types[reason_type] = review_types.get(reason_type, 0) + 1
            review_notes.append(f"{row.basis_code}:{reason_text}")

        if review_types:
            type_summary = "；".join(
                f"{REVIEW_REASON_LABELS.get(reason_type, reason_type)}:{count}"
                for reason_type, count in sorted(review_types.items(), key=lambda item: item[0])
            )
            lines.append(f"`REVIEW分类` {type_summary}")

        if review_notes:
            # 只在 REVIEW 场景展开原始原因，便于人工复核时直接定位根因。
            lines.append("`REVIEW原因` " + "；".join(review_notes))

    return _format_explanation_block(lines)


def _select_representative_row(rows: List[ParamCheckRow], final_status: str) -> ParamCheckRow:
    preferred = [row for row in rows if row.status == final_status]
    return preferred[0] if preferred else rows[0]


def _merge_param_rows(rows: List[ParamCheckRow]) -> List[ParamCheckRow]:
    grouped: Dict[str, List[ParamCheckRow]] = {}
    for row in rows:
        grouped.setdefault(row.point_key, []).append(row)

    merged_rows: List[ParamCheckRow] = []
    for point_key, point_rows in grouped.items():
        ordered_rows = sorted(point_rows, key=lambda item: (item.cert_index, item.basis_code, item.batch_index, item.row_index))
        statuses = {row.status for row in ordered_rows}

        if "PASS" in statuses:
            final_status = "PASS"
            final_rationale = "至少一个依据判定为 PASS，因此最终按 PASS 归并"
        elif "REVIEW" in statuses:
            final_status = "REVIEW"
            final_rationale = "没有 PASS，但存在 REVIEW，因此最终按 REVIEW 归并"
        elif statuses == {"FAIL"}:
            final_status = "FAIL"
            final_rationale = "所有命中的依据均为 FAIL，因此最终按 FAIL 归并"
        elif statuses == {"ERROR"}:
            final_status = "ERROR"
            final_rationale = "所有命中的依据均为 ERROR，因此最终按 ERROR 归并"
        else:
            final_status = "REVIEW"
            final_rationale = "依据结果存在混合异常，无法证明全 FAIL 或明确 PASS，按 REVIEW 兜底"

        representative = _select_representative_row(ordered_rows, final_status)
        merged_reason = _build_merged_reason(ordered_rows, final_status, final_rationale)
        merged_row_dict = dict(representative.raw_row)
        merged_row_dict["判定"] = final_status
        merged_row_dict["说明"] = merged_reason
        merged_review_reason_type = ""
        if final_status == "REVIEW":
            review_types = {
                _row_review_reason_type(row)
                for row in ordered_rows
                if _coerce_text(row.status).upper() == "REVIEW"
            }
            review_types.discard("")
            if len(review_types) == 1:
                merged_review_reason_type = next(iter(review_types))
            elif len(review_types) > 1:
                merged_review_reason_type = "other_review"
        representative_record = _row_evaluation_record(representative)
        anomaly_flags = sorted(
            {
                flag
                for row in ordered_rows
                for flag in _row_anomaly_flags(row)
            }
        )
        merged_record = _build_evaluation_record(
            basis_code="MERGED",
            batch_label=representative.param_name,
            batch_index=representative.batch_index,
            row_index=representative.row_index,
            cert_index=representative.cert_index,
            param_name=representative.param_name,
            point_key=point_key,
            match_value=representative.match_value,
            point_value=representative.point_value,
            status=final_status,
            reason=merged_reason,
            semantic_target=getattr(representative_record, "semantic_target", ""),
            semantic_subtype=getattr(representative_record, "semantic_subtype", ""),
            axis_family=getattr(representative_record, "axis_family", ""),
            axis_value=getattr(representative_record, "axis_value", ""),
            selected_candidate_id=getattr(representative_record, "selected_candidate_id", ""),
            candidate_target=getattr(representative_record, "candidate_target", ""),
            candidate_primary_quantity=getattr(representative_record, "candidate_primary_quantity", ""),
            selected_target_relation=getattr(representative_record, "selected_target_relation", ""),
            anomaly_flags=anomaly_flags,
            planner_summary=getattr(representative_record, "planner_summary", {}),
            semantic_auditor_summary=getattr(representative_record, "semantic_auditor_summary", {}),
            display_fields=merged_row_dict,
            review_reason_type=merged_review_reason_type,
        )
        merged_rows.append(_record_to_param_check_row(merged_record))

    return sorted(merged_rows, key=lambda item: (item.cert_index, item.param_name, item.point_key))


def _render_merged_summary_section(
    *,
    criteria_list: List[str],
    instrument_name: str,
    total_params: int,
    total_measurement_points: int,
    merged_rows: List[ParamCheckRow],
) -> List[str]:
    lines = [
        "# 【主结果】多依据参数核验结果汇总",
        "> 这部分是跨依据归并后的最终参数结论；下方的审计与批次明细仅用于追溯和复核。",
        "## 核验范围",
        f"- 仪器: {instrument_name}",
        f"- 依据: {', '.join(criteria_list) if criteria_list else 'N/A'}",
        f"- 参数量: {total_params} 个",
        f"- 总测量点数: {total_measurement_points} 个",
        "",
    ]

    grouped: Dict[str, List[ParamCheckRow]] = {}
    for row in merged_rows:
        grouped.setdefault(row.param_name, []).append(row)

    for param_name, param_rows in grouped.items():
        lines.append(f"### 参数：{param_name}")
        lines.extend(_render_param_rows_table(param_rows))
        lines.append("")

    lines.append("---")
    lines.extend(_render_summary_lines(_summarize_structured_rows(merged_rows), total_measurement_points))
    return lines


def _build_param_check_version_stamp() -> str:
    """构建参数核验运行时版本戳，包含主入口和关键依赖模块。"""
    paths = _runtime_dependency_paths()
    latest_mtime = max((path.stat().st_mtime for path in paths), default=time.time())
    digest = hashlib.sha1()
    for path in sorted(paths):
        digest.update(str(path).encode("utf-8"))
        digest.update(path.read_bytes())
    mtime = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(latest_mtime))
    return f"langchain_app/checks/parameter bundle | files={len(paths)} | latest_mtime={mtime} | sha1={digest.hexdigest()[:10]}"


def collect_certificate_params(cert_root: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    兼容两种证书参数结构：
    1) 新版（行式）：依据参数_中间数据 = [{项目名称, 数据明细{...}}, ...]
    2) 旧版（列式）：参数名作为键，值是列表/对象
    """
    all_params = []
    try:
        row_based = cert_root.get("依据参数_中间数据")
        if row_based is None:
            row_based = cert_root.get("properties", {}).get("依据参数_中间数据")
        if isinstance(row_based, list):
            for row in row_based:
                if not isinstance(row, dict):
                    continue
                project_name = _coerce_text(row.get("项目名称") or row.get("测量值") or row.get("param_name"))
                param_name = project_name.strip()
                detail = row.get("数据明细", {}) or {}
                if not param_name or not isinstance(detail, dict) or not detail:
                    continue
                point = {
                    "param_name": param_name,
                    "项目名称": project_name,
                    "schema_version": row.get("schema_version"),
                    "__normalized_fields": row.get("__normalized_fields", {}) if isinstance(row.get("__normalized_fields"), dict) else {},
                    "__parameter_contract": row.get("__parameter_contract", {}) if isinstance(row.get("__parameter_contract"), dict) else {},
                    "__parser_meta": row.get("__parser_meta", {}) if isinstance(row.get("__parser_meta"), dict) else {},
                }
                point.update(detail)
                all_params.append(point)
            if all_params:
                return all_params
    except Exception:
        pass
    try:
        props = cert_root["properties"]["证书列表"]["items"]["properties"]
    except KeyError:
        props = cert_root
    param_names = []
    for k in props.keys():
        if k.startswith("依据参数_") and "点位" not in k and "数据明细" not in k:
            param_names.append(k)
    if not param_names:
        for k in props.keys():
            if k.startswith("依据参数_") and "点位" in k:
                base = k.replace("点位", "").rstrip("_")
                if base not in param_names:
                    param_names.append(base)
    if not param_names:
        return []
    max_len = 0
    for base in param_names:
        key = f"{base}_点位"
        if key in props:
            val = props.get(key, [])
            if isinstance(val, list):
                max_len = max(max_len, len(val))
    if max_len == 0:
        max_len = 1
    for i in range(max_len):
        point = {}
        for base in param_names:
            short_name = base.replace("依据参数_", "")
            val = None
            for suffix in ["", "_点位", "_值", "_误差", "_不确定度"]:
                key = f"{base}{suffix}"
                if key in props:
                    arr = props.get(key, [])
                    if isinstance(arr, list) and i < len(arr):
                        val = arr[i]
                        break
                    elif arr:
                        val = arr
                        break
            if val is not None:
                point[short_name] = val
            point["param_name"] = short_name
        if point:
            all_params.append(point)
    return all_params


def _unique_param_names(params: List[Dict]) -> List[str]:
    """获取唯一参数名列表"""
    seen = set()
    names = []
    for p in params:
        n = p.get("param_name", "unknown")
        if n not in seen:
            seen.add(n)
            names.append(n)
    return names


def _collect_param_tables(batch_contents: List[str], batch_expected_params: Dict[int, List[str]]) -> Dict[str, List[str]]:
    """收集参数表格"""
    param_to_table = {}
    for content in batch_contents:
        if not content or "|" not in content:
            continue
        lines = content.splitlines()
        current_param = None
        current_table = []
        in_table = False
        for line in lines:
            if line.startswith("### 参数："):
                if current_param and current_table:
                    if current_param not in param_to_table:
                        param_to_table[current_param] = []
                    param_to_table[current_param].extend(current_table)
                current_param = line.replace("### 参数：", "").strip()
                current_table = []
                continue
            if line.startswith("|"):
                if not in_table:
                    in_table = True
                current_table.append(line)
            elif in_table:
                in_table = False
        if current_param and current_table:
            if current_param not in param_to_table:
                param_to_table[current_param] = []
                param_to_table[current_param].extend(current_table)
    return param_to_table


def _extract_detail_table_lines(batch_md: str) -> List[str]:
    """从单个批次报告中提取参数明细表格行。

    当前 batch 报告的结构是:
    - 章节标题: ``## 参数核验详情``
    - 紧接着一张 Markdown 表
    - 后面可能还有空行或其他内容

    这个 helper 只提取该详情表，避免把其他汇总表或说明段落算进统计。
    """
    if not batch_md:
        return []

    lines = batch_md.splitlines()
    start_idx = None
    for idx, line in enumerate(lines):
        if "## 参数核验详情" in line:
            start_idx = idx + 1
            break

    if start_idx is None:
        return []

    table_lines: List[str] = []
    in_table = False
    for line in lines[start_idx:]:
        stripped = line.strip()
        if stripped.startswith("|"):
            in_table = True
            table_lines.append(line)
            continue
        if in_table:
            break

    return table_lines


def _summarize_table_statuses(table_lines: List[str]) -> Dict[str, int]:
    """统计表格状态"""
    result = {
        "pass": 0,
        "fail": 0,
        "total": 0,
        "kb_missing_fail": 0,
        "kb_missing_review": 0,
        "field_gap_review": 0,
        "semantic_review": 0,
        "other_review": 0,
        "real_fail": 0,
        "review": 0,
    }
    if not table_lines:
        return result
    in_table = False
    idx_judge = None
    idx_note = None
    header_cols = []

    def split_row(line: str) -> List[str]:
        raw = line.strip()
        if raw.startswith("|"):
            raw = raw[1:]
        if raw.endswith("|"):
            raw = raw[:-1]
        return [c.strip() for c in raw.split("|")]

    for line in table_lines:
        if line.strip().startswith("|") and "判定" in line:
            in_table = True
            header_cols = split_row(line)

            def find_idx(name: str):
                try:
                    return header_cols.index(name)
                except ValueError:
                    return None

            idx_judge = find_idx("判定")
            idx_note = find_idx("说明")
            continue
        if in_table and re.match(r"^\s*\|\s*-{2,}", line):
            continue
        if in_table and line.strip().startswith("|") and idx_judge is not None:
            cols = split_row(line)
            if len(cols) <= idx_judge:
                continue
            judge = cols[idx_judge].strip().upper()
            note = cols[idx_note].strip() if (idx_note is not None and idx_note < len(cols)) else ""
            result["total"] += 1
            if "PASS" in judge:
                result["pass"] += 1
            elif "FAIL" in judge:
                reason_type = _classify_review_reason(note)
                if reason_type == "kb_coverage_gap":
                    result["review"] += 1
                    result["kb_missing_fail"] += 1
                    result["kb_missing_review"] += 1
                else:
                    result["fail"] += 1
                    result["real_fail"] += 1
            elif "REVIEW" in judge:
                result["review"] += 1
                reason_type = _classify_review_reason(note)
                if reason_type == "kb_coverage_gap":
                    result["kb_missing_review"] += 1
                elif reason_type == "source_field_gap":
                    result["field_gap_review"] += 1
                elif reason_type == "semantic_ambiguity":
                    result["semantic_review"] += 1
                else:
                    result["other_review"] += 1
            continue
        if in_table and not line.strip().startswith("|"):
            in_table = False
    return result


def run_agentic_batch(
    llm_client: Optional[LLMClient],
    llm_client_error: Optional[Dict[str, str]],
    batch_params: List[Dict],
    kb_items: List[Dict],
    instrument: str,
    criterion: str,
    cfg: Any,
    batch_index: int,
    semantic_auditor_budget: Optional[LLMAuditorBudget] = None,
) -> BatchExecutionResult:
    """
    运行单个批次的 Agentic 核验
    """
    client = llm_client
    report = VerificationReport()
    report.set_header(
        source_name=criterion,
        model=getattr(cfg, "model", ""),
        temperature=getattr(cfg, "temperature", 0.0),
        topk=getattr(cfg, "topk", 3),
    )

    report.add_section("## 参数核验详情")
    report.add_section("")
    report.add_section("| " + " | ".join(PARAM_RESULT_TABLE_HEADER) + " |")
    report.add_section("| " + " | ".join(["---"] * len(PARAM_RESULT_TABLE_HEADER)) + " |")

    rows: List[ParamCheckRow] = []
    planner_traces: List[Dict[str, Any]] = []

    for idx, param in enumerate(batch_params, 1):
        param_name = param.get("param_name", "unknown")
        point_text = str(param)
        point_value = _extract_param_point_value(param) or _coerce_text(param.get("点位"), "N/A") or "N/A"
        condition_text = _extract_param_condition_text(param) or "N/A"
        measure_val = _extract_param_measure_value(param)
        reference_val = _extract_param_reference_value(param)
        error_val = _extract_param_error_value(param)
        cert_u = _extract_param_cert_u(param)
        # 语义层不再依赖自由文本抢 token，结构化数值优先。
        selection_context = " ".join(
            part
            for part in [
                f"点位:{point_value}" if point_value and point_value != "N/A" else "",
                f"测量值:{measure_val}" if measure_val else "",
                f"标准值:{reference_val}" if reference_val else "",
                f"误差:{error_val}" if error_val else "",
                point_text,
            ]
            if part
        ).strip()
        reference_point_hz = _extract_frequency_hz_from_text(selection_context) if _is_reference_frequency_param(param_name, selection_context, cert_u) else None
        range_result: Dict[str, Any] = {}
        error_result: Dict[str, Any] = {}
        u_result: Dict[str, Any] = {}
        anomaly_flags: List[str] = []

        # 选择依据
        selection_result = None
        try:
            selection_result = select_basis_with_audit(
                param_name=param_name,
                point_text=selection_context,
                cert_u=cert_u,
                kb_entries=kb_items,
                basis_code=criterion,
                section_label=param_name,
                measure_value=measure_val,
                reference_value=reference_val,
                error_value=error_val,
                point_value=point_value if point_value != "N/A" else "",
                parameter_contract=_get_parameter_contract(param),
                parser_meta=_get_parser_meta(param),
            )
            selected_candidate = selection_result.selected_candidate
            selected_kb = selection_result.selected[0] if selection_result.selected else None
        except Exception:
            selected_candidate = None
            selected_kb = None
            selection_result = None

        normalized_fields = _normalized_fields_for_llm(param)
        parser_meta = _get_parser_meta(param)
        planner_execution = _run_parameter_planner(
            llm_client=client,
            llm_client_error=llm_client_error,
            cfg=cfg,
            criterion=criterion,
            batch_index=batch_index,
            param=param,
            param_name=param_name,
            selection_result=selection_result,
            kb_items=kb_items,
            point_blob=point_text,
            selection_context=selection_context,
            normalized_fields=normalized_fields,
            parser_meta=parser_meta,
            measure_val=measure_val,
            reference_val=reference_val,
            error_val=error_val,
            point_value=point_value,
        )
        selection_result = planner_execution.selection_result
        selected_candidate = planner_execution.selected_candidate
        selected_kb = planner_execution.selected_kb
        active_selection_context = planner_execution.selection_context or selection_context
        planner_note = planner_execution.note
        if planner_execution.trace:
            planner_traces.append(planner_execution.trace)

        if selected_candidate and reference_point_hz is not None:
            if not _candidate_matches_frequency_point(active_selection_context, selected_candidate.source or {}):
                selected_candidate = None
                selected_kb = None
        elif selected_kb and reference_point_hz is not None:
            if not _candidate_matches_frequency_point(active_selection_context, selected_kb.source or {}):
                selected_kb = None

        allow_fallback = not extract_basis_code(criterion)
        if selected_kb is None and allow_fallback:
            fallback_entry = _fallback_select_kb_entry(
                param_name=param_name,
                measure_val=measure_val,
                error_val=error_val,
                cert_u=cert_u,
                kb_items=kb_items,
            )
            if fallback_entry and (reference_point_hz is None or _candidate_matches_frequency_point(selection_context, fallback_entry)):
                selected_kb = KbCapability(
                    measured=str(fallback_entry.get("measured", "") or ""),
                    capability_target="fallback",
                    primary_quantity="unknown",
                    result_quantity="unknown",
                    condition_axis=None,
                    uncertainty_kind="UNKNOWN",
                    source=fallback_entry,
                )
                selected_candidate = None

        input_sensitivity_override = _resolve_input_sensitivity_business_override(
            param_name=param_name,
            selection_result=selection_result,
            measure_val=measure_val or condition_text or point_text,
            cert_u=cert_u,
            error_val=error_val,
            limit_val=_extract_param_limit_value(param),
        )

        if input_sensitivity_override is not None:
            override_status, override_reason = input_sensitivity_override
            notes = []
            cert_point = getattr(selection_result, "cert_point", None) if selection_result is not None else None
            if cert_point is not None:
                notes.append(f"`semantic_target` {getattr(cert_point, 'semantic_target', 'unknown') or 'unknown'}")
                notes.append(f"`axis_family` {getattr(cert_point, 'axis_family', 'N/A') or 'N/A'}")
                notes.append(
                    "`axis_value` "
                    + _format_normalized_axis_value(
                        getattr(cert_point, "axis_value", None),
                        getattr(cert_point, "axis_family", None),
                    )
                )
            notes.append(f"`业务规则` {override_reason}")
            if planner_note:
                notes.append(planner_note)
            row_dict = _build_table_row_dict(
                point_value=point_value,
                param_name=param_name,
                condition_text=condition_text,
                kb_code="无",
                kb_item="N/A",
                match_value=_coerce_text(measure_val or condition_text, "N/A") or "N/A",
                range_text="N/A",
                cert_error=_coerce_text(error_val, "N/A") or "N/A",
                limit_text=_extract_param_limit_value(param) or "N/A",
                cert_u=cert_u or "N/A",
                kb_u="N/A",
                status=override_status,
                reason=_format_explanation_block(notes),
            )
        elif selected_kb:
            evaluation = _evaluate_selected_kb_results(
                selection_result=selection_result,
                selected_candidate=selected_candidate,
                selected_kb=selected_kb,
                param=param,
                measure_val=measure_val,
                reference_val=reference_val,
                error_val=error_val,
                cert_u=cert_u,
            )
            kb_source = evaluation["kb_source"]
            kb_range = evaluation["kb_range"]
            kb_u = evaluation["kb_u"]
            kb_code = evaluation["kb_code"]
            kb_measured = evaluation["kb_measured"]
            display_limit = evaluation["display_limit"]
            range_probe_value = evaluation["range_probe_value"]
            uncertainty_probe_value = evaluation["uncertainty_probe_value"]
            uncertainty_gate = evaluation["uncertainty_gate"]
            source_anomaly = evaluation["source_anomaly"]
            semantic_ambiguity = evaluation["semantic_ambiguity"]
            range_result = evaluation["range_result"]
            error_result = evaluation["error_result"]
            u_result = evaluation["u_result"]

            semantic_auditor_execution = _run_parameter_semantic_auditor(
                llm_client=client,
                llm_client_error=llm_client_error,
                cfg=cfg,
                criterion=criterion,
                batch_index=batch_index,
                param=param,
                param_name=param_name,
                selection_result=selection_result,
                parser_meta=parser_meta,
                normalized_fields=normalized_fields,
                point_blob=point_text,
                selection_context=active_selection_context,
                selected_kb=selected_kb,
                kb_items=kb_items,
                measure_val=measure_val,
                reference_val=reference_val,
                error_val=error_val,
                point_value=point_value,
                range_result=range_result,
                error_result=error_result,
                u_result=u_result,
                source_anomaly=source_anomaly,
                semantic_ambiguity=semantic_ambiguity,
                budget=semantic_auditor_budget,
            )
            selection_result = semantic_auditor_execution.selection_result
            if semantic_auditor_execution.applied:
                selected_candidate = semantic_auditor_execution.selected_candidate
                selected_kb = semantic_auditor_execution.selected_kb
                evaluation = _evaluate_selected_kb_results(
                    selection_result=selection_result,
                    selected_candidate=selected_candidate,
                    selected_kb=selected_kb,
                    param=param,
                    measure_val=measure_val,
                    reference_val=reference_val,
                    error_val=error_val,
                    cert_u=cert_u,
                )
                kb_source = evaluation["kb_source"]
                kb_range = evaluation["kb_range"]
                kb_u = evaluation["kb_u"]
                kb_code = evaluation["kb_code"]
                kb_measured = evaluation["kb_measured"]
                display_limit = evaluation["display_limit"]
                range_probe_value = evaluation["range_probe_value"]
                uncertainty_probe_value = evaluation["uncertainty_probe_value"]
                uncertainty_gate = evaluation["uncertainty_gate"]
                source_anomaly = evaluation["source_anomaly"]
                semantic_ambiguity = evaluation["semantic_ambiguity"]
                range_result = evaluation["range_result"]
                error_result = evaluation["error_result"]
                u_result = evaluation["u_result"]
            semantic_auditor_note = semantic_auditor_execution.note
            if semantic_auditor_execution.trace:
                planner_traces.append(semantic_auditor_execution.trace)

            # 综合判定
            status = _resolve_selected_kb_status(
                range_result,
                error_result,
                u_result,
                source_anomaly,
                semantic_ambiguity,
            )
            selected_target_relation = _coerce_text(
                getattr(getattr(selection_result, "audit", None), "selected_target_relation", "")
            )
            if source_anomaly.get("detected"):
                anomaly_flags.append("source_anomaly")
            if semantic_ambiguity.get("detected"):
                anomaly_flags.append("reference_probe_ambiguity")
            if not _coerce_text(_extract_param_limit_value(param)):
                anomaly_flags.append("missing_limit")
            if selected_target_relation == "fallback_cross_target":
                anomaly_flags.append("fallback_cross_target")

            notes = [
                _summarize_source_anomaly(source_anomaly),
                _summarize_semantic_ambiguity(semantic_ambiguity),
                _summarize_check_result("范围", range_result),
                _summarize_check_result("误差", error_result),
                _summarize_check_result("不确定度", u_result),
            ]

            match_value = _resolve_match_display_value(selected_kb, measure_val, range_probe_value) or "N/A"
            explanation = _format_reason_summary(notes)
            row_dict = _build_table_row_dict(
                point_value=point_value,
                param_name=param_name,
                condition_text=condition_text,
                kb_code=kb_code,
                kb_item=kb_measured,
                match_value=match_value,
                range_text=kb_range,
                cert_error=_coerce_text(error_val, "N/A") or "N/A",
                limit_text=display_limit,
                cert_u=cert_u or "N/A",
                kb_u=kb_u,
                status=status,
                reason=explanation,
            )
        else:
            review_reason = "KB无对应参数，需人工核验"
            semantic_auditor_execution = _run_parameter_semantic_auditor(
                llm_client=client,
                llm_client_error=llm_client_error,
                cfg=cfg,
                criterion=criterion,
                batch_index=batch_index,
                param=param,
                param_name=param_name,
                selection_result=selection_result,
                parser_meta=parser_meta,
                normalized_fields=normalized_fields,
                point_blob=point_text,
                selection_context=active_selection_context,
                selected_kb=selected_kb,
                kb_items=kb_items,
                measure_val=measure_val,
                reference_val=reference_val,
                error_val=error_val,
                point_value=point_value,
                range_result=None,
                error_result=None,
                u_result=None,
                source_anomaly=None,
                semantic_ambiguity=None,
                budget=semantic_auditor_budget,
            )
            selection_result = semantic_auditor_execution.selection_result
            semantic_auditor_note = semantic_auditor_execution.note
            if semantic_auditor_execution.trace:
                planner_traces.append(semantic_auditor_execution.trace)
            try:
                audit = selection_result.audit
                cert_point = selection_result.cert_point if selection_result is not None else None
                reason_parts = []
                if audit.rationale:
                    reason_parts.append(_simplify_review_reason_text(audit.rationale))
                elif cert_point is not None and getattr(cert_point, "normalization_notes", None):
                    reason_parts.append("参数归一化后仍无法稳定匹配，需人工核验")
                if reason_parts:
                    review_reason = _format_reason_summary(reason_parts)
            except Exception:
                pass
            anomaly_flags.append("kb_missing")
            row_dict = _build_table_row_dict(
                point_value=point_value,
                param_name=param_name,
                condition_text=condition_text,
                kb_code="无",
                kb_item="N/A",
                match_value=_coerce_text(measure_val, "N/A") or "N/A",
                range_text="N/A",
                cert_error=_coerce_text(error_val, "N/A") or "N/A",
                limit_text=_extract_param_limit_value(param) or "N/A",
                cert_u=cert_u or "N/A",
                kb_u="N/A",
                status="REVIEW",
                reason=_format_reason_summary([review_reason]),
            )

        planner_summary = dict(getattr(getattr(selection_result, "audit", None), "planner_summary", {}) or {})
        if planner_summary:
            row_dict.update(
                {
                    "planner_mode": _coerce_text(planner_summary.get("planner_mode"), "shadow") or "shadow",
                    "planner_action": _coerce_text(planner_summary.get("planner_action"), "abstain") or "abstain",
                    "planner_semantic_target": _coerce_text(planner_summary.get("planner_semantic_target"), ""),
                    "planner_candidate_ids": list(planner_summary.get("planner_candidate_ids") or []),
                    "planner_confidence": planner_summary.get("planner_confidence"),
                    "planner_reason": _coerce_text(planner_summary.get("planner_reason"), ""),
                    "planner_takeover_score": planner_summary.get("planner_takeover_score"),
                    "planner_takeover_threshold": planner_summary.get("planner_takeover_threshold"),
                    "planner_parser_risk": _coerce_text(planner_summary.get("planner_parser_risk"), ""),
                    "planner_takeover_basis": _coerce_text(
                        planner_summary.get("planner_takeover_basis"),
                        "deterministic_retained",
                    ),
                }
            )

        semantic_auditor_summary = dict(getattr(getattr(selection_result, "audit", None), "semantic_auditor_summary", {}) or {})
        if semantic_auditor_summary:
            row_dict.update(
                {
                    "semantic_auditor_mode": _coerce_text(semantic_auditor_summary.get("semantic_auditor_mode"), "shadow") or "shadow",
                    "semantic_auditor_triggered": True,
                    "semantic_auditor_reason": _coerce_text(semantic_auditor_summary.get("semantic_auditor_reason"), ""),
                    "semantic_auditor_confidence": semantic_auditor_summary.get("semantic_auditor_confidence"),
                    "semantic_auditor_suggested_target": _coerce_text(semantic_auditor_summary.get("semantic_auditor_suggested_target"), ""),
                    "semantic_auditor_issue_type": _coerce_text(semantic_auditor_summary.get("semantic_auditor_issue_type"), ""),
                    "semantic_auditor_takeover_basis": _coerce_text(semantic_auditor_summary.get("semantic_auditor_takeover_basis"), "shadow_retained") or "shadow_retained",
                    "semantic_auditor_replay_selected_candidate_id": _coerce_text(semantic_auditor_summary.get("semantic_auditor_replay_selected_candidate_id"), ""),
                    "semantic_auditor_replay_rationale": _coerce_text(semantic_auditor_summary.get("semantic_auditor_replay_rationale"), ""),
                }
            )

        cert_point = getattr(selection_result, "cert_point", None) if selection_result is not None else None
        point_key = _build_point_key(
            param=param,
            param_name=param_name,
            match_value=row_dict["证书匹配项"],
            point_value=point_value,
            measure_value=measure_val,
        )
        evaluation_record = _build_evaluation_record(
            basis_code=criterion,
            batch_label=f"Batch {batch_index}",
            batch_index=batch_index,
            row_index=idx,
            cert_index=int(param.get("__cert_index", idx) or idx),
            param_name=param_name,
            point_key=point_key,
            match_value=row_dict["证书匹配项"],
            point_value=point_value,
            status=row_dict["判定"],
            reason=row_dict["说明"],
            semantic_target=_coerce_text(getattr(cert_point, "semantic_target", "")),
            semantic_subtype=_coerce_text(getattr(cert_point, "semantic_subtype", "")),
            axis_family=_coerce_text(getattr(cert_point, "axis_family", "")),
            axis_value=(
                _format_normalized_axis_value(
                    getattr(cert_point, "axis_value", None),
                    getattr(cert_point, "axis_family", None),
                )
                if cert_point is not None
                else ""
            ),
            selected_candidate_id=_coerce_text(getattr(selected_candidate, "candidate_id", "")),
            candidate_target=_coerce_text(
                getattr(selected_candidate, "capability_target", "")
                or getattr(selected_kb, "capability_target", "")
            ),
            candidate_primary_quantity=_coerce_text(
                getattr(selected_candidate, "primary_quantity", "")
                or getattr(selected_kb, "primary_quantity", "")
            ),
            selected_target_relation=_coerce_text(
                getattr(getattr(selection_result, "audit", None), "selected_target_relation", "")
            ),
            range_result=range_result,
            error_result=error_result,
            u_result=u_result,
            anomaly_flags=anomaly_flags,
            planner_summary=planner_summary,
            semantic_auditor_summary=semantic_auditor_summary,
            display_fields=row_dict,
        )
        rows.append(_record_to_param_check_row(evaluation_record))
        report.add_section(_row_to_markdown_line(idx, rows[-1]))

    return BatchExecutionResult(markdown=report.render(), rows=rows, planner_traces=planner_traces)


def check_parameters(
    json_file: str,
    cfg: Optional[AppConfig] = None,
    stop_event=None,
    embedder_obj=None,
    llm_client: Optional[LLMClient] = None,
) -> str:
    """
    参数与不确定度核验主入口（与原始函数兼容）

    Args:
        json_file: JSON 文件路径
        cfg: 配置对象
        stop_event: 停止事件
        embedder_obj: 嵌入模型对象

    Returns:
        核验报告（Markdown 格式）
    """
    _refresh_runtime_dependency_bindings()
    cfg = coerce_app_config(cfg)

    # 初始刹车检查
    if stop_event and stop_event.is_set():
        print("[ParamCheck] 任务在初始化阶段被终止")
        return "[警告] 核验任务已由用户在初始化阶段取消。"

    # 读取 JSON
    with open(json_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    try:
        root = data["properties"]["证书列表"]["items"]["properties"]
    except KeyError:
        root = data

    instrument_name = root.get("INSTRUMENT_NAME") or root.get("仪器名称") or "N/A"
    criteria_list = root.get("校准依据", []) or ["N/A"]
    if isinstance(criteria_list, str):
        criteria_list = [criteria_list]
    elif not isinstance(criteria_list, list):
        criteria_list = [str(criteria_list)]
    all_cert_params = collect_certificate_params(data)
    for cert_index, param in enumerate(all_cert_params, 1):
        if isinstance(param, dict):
            param["__cert_index"] = cert_index

    print(f"[证书] {json_file}")
    print(f"[参数量] {len(all_cert_params)}")
    print(f"[配置] TopK={cfg.topk}, MaxWorkers={cfg.max_workers}")

    # 初始化资源
    client = llm_client
    if client is None:
        try:
            client = LLMClient(config=cfg)
            llm_client_error: Optional[Dict[str, str]] = None
        except Exception as exc:
            details = describe_llm_exception(exc, default_stage="client_init")
            client = None
            llm_client_error = {
                "error_stage": details["error_stage"],
                "error_code": details["error_code"],
                "error_message": f"{details['error_type']}({details['error_message']})",
            }
            logger.warning(
                "LLM client init failed stage=%s code=%s",
                details["error_stage"],
                details["error_code"],
            )
    else:
        llm_client_error = None

    param_groups: Dict[str, List[Dict[str, Any]]] = {}
    for param in all_cert_params:
        param_name = param.get("param_name", "unknown")
        param_groups.setdefault(param_name, []).append(param)

    batches: List[List[Dict[str, Any]]] = []
    batch_param_names_map: Dict[int, List[str]] = {}
    current_batch: List[Dict[str, Any]] = []
    for param_name, points in param_groups.items():
        if current_batch and len(current_batch) + len(points) > cfg.batch_size:
            batches.append(current_batch)
            batch_param_names_map[len(batches)] = _unique_param_names(current_batch)
            current_batch = []
        current_batch.extend(points)
    if current_batch:
        batches.append(current_batch)
        batch_param_names_map[len(batches)] = _unique_param_names(current_batch)

    total_params = len(param_groups)
    total_measurement_points = len(all_cert_params)

    report_lines = [
        "# CNAS 智能核验报告 (LangGraph Edition)",
        f"- 证书编号: {root.get('证书编号', 'N/A')}",
        f"- 仪器: {instrument_name}",
        f"- 时间: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 参数核验版本: {_build_param_check_version_stamp()}",
        ""
    ]

    document_review_reason = _resolve_document_parameter_review_reason(data, all_cert_params)
    if document_review_reason:
        report_lines.insert(
            len(report_lines) - 1,
            f"- 参数核验策略: 已降级为人工核验（{document_review_reason}）",
        )

    basis_preview_sections: List[str] = []
    basis_audit_sections: List[str] = []
    all_basis_rows: List[ParamCheckRow] = []
    all_planner_traces: List[Dict[str, Any]] = []
    semantic_auditor_budget = LLMAuditorBudget(
        max_calls=parameter_semantic_auditor_max_calls(cfg)
    )

    def _append_audit_section(section_text: str) -> None:
        basis_audit_sections.append(section_text)

    if document_review_reason:
        for criterion in criteria_list:
            criterion_rows = _build_review_rows_for_params(
                all_cert_params,
                basis_code=criterion,
                reason=document_review_reason,
            )
            basis_preview_sections.append(
                "\n".join(
                    _render_basis_preview_section(
                        criterion,
                        {
                            0: (
                                "### [人工核验] 参数自动核验已跳过\n"
                                f"- 证书依据: {criterion}\n"
                                f"- 原因: {document_review_reason}\n"
                                "- 处理建议: 请人工复核该文档的参数表后再决定是否重新触发自动核验。"
                            )
                        },
                    )
                )
            )
            _append_audit_section(
                "\n".join(
                    _render_basis_audit_section(
                        criterion=criterion,
                        instrument_name=instrument_name,
                        total_params=total_params,
                        total_measurement_points=total_measurement_points,
                        rows=criterion_rows,
                    )
                )
            )
            all_basis_rows.extend(criterion_rows)

        merged_rows = _merge_param_rows(all_basis_rows)
        if report_lines and report_lines[-1] != "":
            report_lines.append("")
        report_lines.extend(
            _render_merged_summary_section(
                criteria_list=criteria_list,
                instrument_name=instrument_name,
                total_params=total_params,
                total_measurement_points=total_measurement_points,
                merged_rows=merged_rows,
            )
        )

        if basis_audit_sections:
            report_lines.append("")
            report_lines.append("---")
            report_lines.append("")
            report_lines.append("## 依据级明细")
            report_lines.append("")
            for index, section in enumerate(basis_audit_sections, 1):
                if index > 1:
                    report_lines.append("---")
                    report_lines.append("")
                report_lines.append(section)
                report_lines.append("")

        if basis_preview_sections:
            report_lines.append("")
            report_lines.append("---")
            report_lines.append("")
            report_lines.append("# [预览] 各依据 Batch 详细报告")
            report_lines.append("")
            for index, section in enumerate(basis_preview_sections, 1):
                if index > 1:
                    report_lines.append("---")
                    report_lines.append("")
                report_lines.append(section)
                report_lines.append("")

        return "\n".join(report_lines)

    # 按依据循环
    for criterion in criteria_list:
        # 循环间刹车检查
        if stop_event and stop_event.is_set():
            return "[警告] 核验任务已由用户手动终止。"

        # 检索知识库
        global LAST_QUERY_ERROR
        LAST_QUERY_ERROR = None
        results_map: Dict[int, str] = {}
        criterion_rows: List[ParamCheckRow] = []

        try:
            kb_raw_items = search_calibration_data(
                query=criterion,
                cfg=cfg,
                topk=cfg.topk,
                instrument_name=instrument_name,
                embedder_obj=embedder_obj,
            )
        except Exception as e:
            LAST_QUERY_ERROR = str(e)
            kb_raw_items = []

        kb_items = [
            parse_kb_entry(
                item.get("page_content") or item.get("文档内容", ""),
                item.get("metadata", {}),
            )
            for item in kb_raw_items
        ]

        if LAST_QUERY_ERROR:
            reason = (
                "知识库访问失败，无法判定该依据下的参数结果；"
                f"索引诊断信息: {LAST_QUERY_ERROR}"
            )
            criterion_rows.extend(
                _build_error_rows_for_params(all_cert_params, basis_code=criterion, reason=reason)
            )
            results_map[0] = (
                "### 核验终止（知识库访问失败）\n"
                f"- 证书依据: {criterion}\n"
                "- 结果: 参数核验所需的向量库无法正常访问，当前不是“无匹配数据”，而是“索引读取失败”。\n"
                f"- 诊断信息: {LAST_QUERY_ERROR}\n"
                f"- 处理建议: 请检查/重建 `{cfg.cnas_db_dir}` 下的向量库索引后再重试。"
            )
            _append_audit_section(
                "\n".join(
                    _render_basis_audit_section(
                        criterion=criterion,
                        instrument_name=instrument_name,
                        total_params=total_params,
                        total_measurement_points=total_measurement_points,
                        rows=criterion_rows,
                    )
                )
            )
            basis_preview_sections.append("\n".join(_render_basis_preview_section(criterion, results_map)))
            all_basis_rows.extend(criterion_rows)
            continue

        # 依据一致性检查
        basis_code = extract_basis_code(criterion)
        basis_code_norm = norm_code(basis_code) if basis_code else None

        if basis_code_norm:
            def _entry_basis_candidates(item: Dict[str, Any]) -> List[str]:
                return [
                    str(item.get("file_code", "") or ""),
                    str(item.get("FILE_CODE", "") or ""),
                    str(item.get("standard_name", "") or ""),
                    str(item.get("FILE_NAME", "") or ""),
                    str(item.get("渚濇嵁鍚嶇О", "") or ""),
                    str(item.get("鏍″噯渚濇嵁", "") or ""),
                ]

            kb_items_same_basis = [
                it for it in kb_items
                if any(norm_code(candidate) == basis_code_norm for candidate in _entry_basis_candidates(it))
            ]

            if not kb_items_same_basis:
                for it in kb_items:
                    std_name = it.get("standard_name", "") or it.get("FILE_NAME", "") or it.get("渚濇嵁鍚嶇О", "") or it.get("鏍″噯渚濇嵁", "")
                    m2 = re.search(r"\b(JJ[GF]|GJB)\s*(\d+)(?:\s*-\s*\d{4})?\b", std_name, re.IGNORECASE)
                    if m2:
                        picked = f"{m2.group(1).upper()} {m2.group(2)}"
                        if norm_code(picked) == basis_code_norm:
                            kb_items_same_basis.append(it)

            if not kb_items_same_basis:
                reason = (
                    f"知识库中找不到与规程 {basis_code} 一致的条目，"
                    "因此该依据下全部参数按 ERROR 记录"
                )
                criterion_rows.extend(
                    _build_error_rows_for_params(all_cert_params, basis_code=criterion, reason=reason)
                )
                results_map[0] = (
                    "### [错误] 核验终止（依据一致性失败）\n"
                    f"- 证书依据: {criterion}\n"
                    f"- 提取规程代号: {basis_code}\n"
                    f"- 结果: 知识库中找不到与该规程一致的条目，因此跳过核验并返回 ERROR。\n"
                    f"- 处理建议: 请补充/导入 {basis_code} 对应的 KB 条目后再核验。"
                )
                _append_audit_section(
                    "\n".join(
                        _render_basis_audit_section(
                            criterion=criterion,
                            instrument_name=instrument_name,
                            total_params=total_params,
                            total_measurement_points=total_measurement_points,
                            rows=criterion_rows,
                        )
                    )
                )
                basis_preview_sections.append("\n".join(_render_basis_preview_section(criterion, results_map)))
                all_basis_rows.extend(criterion_rows)
                continue

            kb_items = kb_items_same_basis
        else:
            reason = "无法从依据中解析 JJG/JJF 规程代号，因此该依据下全部参数按 ERROR 记录"
            criterion_rows.extend(
                _build_error_rows_for_params(all_cert_params, basis_code=criterion, reason=reason)
            )
            results_map[0] = (
                "### [错误] 核验终止（依据代号无法解析）\n"
                f"- 证书依据: {criterion}\n"
                "- 结果: 无法从依据中解析 JJG/JJF 规程代号，系统不允许跨规程自动核验，因此返回 ERROR。"
            )
            _append_audit_section(
                "\n".join(
                    _render_basis_audit_section(
                        criterion=criterion,
                        instrument_name=instrument_name,
                        total_params=total_params,
                        total_measurement_points=total_measurement_points,
                        rows=criterion_rows,
                    )
                )
            )
            basis_preview_sections.append("\n".join(_render_basis_preview_section(criterion, results_map)))
            all_basis_rows.extend(criterion_rows)
            continue

        # 打印检索结果预览
        if kb_items:
            print("\n" + "=" * 60)
            preview_count = min(len(kb_items), 10)
            print(f"[预览] [Preview] 检索到的知识库内容（预览 {preview_count} 条，实际核验使用全部 {len(kb_items)} 条）:")
            print(f"   依据: {criterion}")
            print("-" * 60)
            for i, item in enumerate(kb_items[:preview_count], 1):
                std = item.get('file_code', 'N/A')
                measured = item.get('measured', 'N/A')
                rng = item.get('measure_range_text', '-')
                if len(rng) > 50:
                    rng = rng[:47] + "..."
                print(f"  {i:02d}. [{std}] {measured} | 范围: {rng}")
            if len(kb_items) > preview_count:
                print(f"  ... 其余 {len(kb_items) - preview_count} 条未在控制台展开，但已纳入后续核验。")
            print("=" * 60 + "\n")
        else:
            print(f"\n[警告] [Warning] 未检索到关于 '{criterion}' 的知识库条目！\n")

        total_batches = len(batches)
        if total_batches == 0:
            results_map[0] = "> 无可核验参数"
            _append_audit_section(
                "\n".join(
                    _render_basis_audit_section(
                        criterion=criterion,
                        instrument_name=instrument_name,
                        total_params=total_params,
                        total_measurement_points=total_measurement_points,
                        rows=criterion_rows,
                    )
                )
            )
            basis_preview_sections.append("\n".join(_render_basis_preview_section(criterion, results_map)))
            continue

        # 动态调整线程池大小
        max_w = cfg.max_workers
        if max_w > 5:
            max_w = min(max_w, 5)
            print(f"[警告] 自动优化线程数：从 {cfg.max_workers} 减少到 5，避免API限流")

        print(f"[启动] 启动并发处理: 共 {total_batches} 个批次，线程数: {max_w}")
        print(f"📊 参数分组: {list(param_groups.keys())}")

        batch_start_time = [time.time() for _ in range(total_batches + 1)]
        batch_rows_map: Dict[int, List[ParamCheckRow]] = {}
        with ThreadPoolExecutor(max_workers=max_w) as executor:
            future_to_context: Dict[Any, Tuple[int, List[Dict[str, Any]]]] = {}

            for idx, batch in enumerate(batches):
                batch_start_time[idx + 1] = time.time()
                if stop_event and stop_event.is_set():
                    break

                future = executor.submit(
                    run_agentic_batch,
                    client,
                    llm_client_error,
                    batch,
                    kb_items,
                    instrument_name,
                    criterion,
                    cfg,
                    idx + 1,
                    semantic_auditor_budget,
                )
                future_to_context[future] = (idx + 1, batch)

            try:
                for future in as_completed(future_to_context):
                    if stop_event and stop_event.is_set():
                        print("[ParamCheck] 接到终止指令，正在强制清理线程池...")
                        executor.shutdown(wait=False, cancel_futures=True)
                        return "[警告] 核验任务已由用户手动终止 (并发阶段)。"

                    idx, batch = future_to_context[future]
                    try:
                        start_time = batch_start_time[idx]
                        batch_result = future.result(timeout=600)
                        duration = time.time() - start_time

                        content = batch_result.markdown
                        content = enforce_kb_missing_fail(content)
                        content = enforce_uncertainty_by_tool(content)
                        content = enforce_batch_summary_from_table(
                            content,
                            expected_param_names=batch_param_names_map.get(idx, []),
                        )

                        results_map[idx] = content
                        batch_rows_map[idx] = batch_result.rows
                        if batch_result.planner_traces:
                            all_planner_traces.extend(batch_result.planner_traces)
                        print(f"   [完成] Batch {idx}/{total_batches} 完成 ({duration:.1f}s)")
                    except Exception as e:
                        error_msg = f"> 🚨 Batch {idx} 失败：{e}"
                        print(error_msg)
                        results_map[idx] = error_msg
                        batch_rows_map[idx] = _build_error_rows_for_params(
                            batch,
                            basis_code=criterion,
                            reason=f"Batch {idx} 失败: {e}",
                            batch_label=f"Batch {idx}",
                            batch_index=idx,
                        )

            except Exception as e:
                print(f"[错误] 线程池异常: {e}")

        # 再次检查，防止组装报告时浪费时间
        if stop_event and stop_event.is_set():
            return "[警告] 任务已终止"

        for i in range(1, total_batches + 1):
            if i not in results_map:
                results_map[i] = "> 任务被取消或执行异常"
            if i not in batch_rows_map:
                batch_rows_map[i] = _build_error_rows_for_params(
                    batches[i - 1],
                    basis_code=criterion,
                    reason=f"Batch {i} 未返回结果",
                    batch_label=f"Batch {i}",
                    batch_index=i,
                )
            criterion_rows.extend(batch_rows_map[i])

        _append_audit_section(
            "\n".join(
                _render_basis_audit_section(
                    criterion=criterion,
                    instrument_name=instrument_name,
                    total_params=total_params,
                    total_measurement_points=total_measurement_points,
                    rows=criterion_rows,
                )
            )
        )
        basis_preview_sections.append("\n".join(_render_basis_preview_section(criterion, results_map)))
        all_basis_rows.extend(criterion_rows)

    merged_rows = _merge_param_rows(all_basis_rows)
    if report_lines and report_lines[-1] != "":
        report_lines.append("")
    report_lines.extend(
        _render_merged_summary_section(
            criteria_list=criteria_list,
            instrument_name=instrument_name,
            total_params=total_params,
            total_measurement_points=total_measurement_points,
            merged_rows=merged_rows,
        )
    )

    if basis_audit_sections:
        report_lines.append("")
        report_lines.append("---")
        report_lines.append("")
        report_lines.append("## 依据级明细")
        report_lines.append("")
        for index, section in enumerate(basis_audit_sections, 1):
            if index > 1:
                report_lines.append("---")
                report_lines.append("")
            report_lines.append(section)
            report_lines.append("")

    if basis_preview_sections:
        report_lines.append("")
        report_lines.append("---")
        report_lines.append("")
        report_lines.append("# [预览] 各依据 Batch 详细报告")
        report_lines.append("")
        for index, section in enumerate(basis_preview_sections, 1):
            if index > 1:
                report_lines.append("---")
                report_lines.append("")
                report_lines.append(section)
                report_lines.append("")

    try:
        _write_planner_trace_sidecar(json_file=json_file, cfg=cfg, traces=all_planner_traces)
    except Exception as exc:
        print(f"[Planner] sidecar trace write failed: {exc}")

    return "\n".join(report_lines)


# ==================== 兼容旧接口 ====================

def parameter_check_wrapper(json_path: str, config):
    """
    兼容性函数，用于直接调用参数与不确定度核验

    Args:
        json_path: JSON 文件路径
        config: 配置对象（原始 AppConfig）

    Returns:
        核验报告
    """
    return check_parameters(json_path, config)


# 为了保持与原始函数名的兼容
def run_llm_mode(
    json_file: str,
    cfg,
    stop_event=None,
    embedder_obj=None,
    llm_client: Optional[LLMClient] = None,
) -> str:
    """
    与原始 param_check.py 中 run_llm_mode 函数兼容的包装函数
    """
    return check_parameters(json_file, cfg, stop_event, embedder_obj, llm_client=llm_client)
