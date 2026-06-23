#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Parameter retrieval helpers.

This module bypasses the langchain_chroma query path and reads the persisted
Chroma collection directly. The local index can be read in batches with the
native chromadb client on this machine.
"""

from __future__ import annotations

import os
import re
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import chromadb

from langchain_app.utils import get_app_config, AppConfig
from langchain_app.retrieval.types import (
    Diagnostic,
    DiagnosticCode,
    RetrievalResponse,
    response_from_legacy_dicts,
)
from .parser_domain import _filter_kb_entries_multidimensional
from .rules import PLACEHOLDER_INSTRUMENT_NAMES


def get_config(cfg: Optional[AppConfig] = None):
    return cfg or get_app_config()


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", "", (text or "").lower())


def _normalize_match_text(text: str) -> str:
    text = _normalize_text(text)
    return re.sub(r"[`~!@#$%^&*()_+\-={}[\]|\\:;\"'<>,.?/·*【】（）「」『』、，。！？]", "", text)


def _extract_criterion_norm(text: str) -> str:
    m = re.search(r"\b(JJ[GF]|GJB)\s*(\d+)(?:\s*-\s*\d{4})?\b", text or "", re.IGNORECASE)
    if not m:
        return ""
    return f"{m.group(1).upper()}{m.group(2)}"


def _entry_basis_candidates(doc_text: str, metadata: Dict[str, Any]) -> List[str]:
    candidates = [
        metadata.get("file_code", ""),
        metadata.get("依据编号", ""),
        metadata.get("standard_name", ""),
        metadata.get("校准依据", ""),
        metadata.get("依据名称", ""),
    ]
    if doc_text:
        candidates.append(doc_text)
    return [str(item or "") for item in candidates]


def _matches_criterion_norm(doc_text: str, metadata: Dict[str, Any], criterion_norm: str) -> bool:
    if not criterion_norm:
        return False
    for candidate in _entry_basis_candidates(doc_text, metadata):
        match = _extract_criterion_norm(candidate)
        if match and match == criterion_norm:
            return True
    return False


def _matches_instrument_filter(entry: Dict[str, Any], instrument_filter: str) -> bool:
    if not instrument_filter:
        return True
    name_norm = _normalize_match_text(instrument_filter)
    if not name_norm:
        return True
    candidates = [entry.get("INSTRUMENT_NAME", ""), entry.get("仪器名称", ""), entry.get("浠櫒鍚嶇О", "")]
    candidate_norms = [_normalize_match_text(str(cand)) for cand in candidates if cand]
    return any(
        name_norm in cand_norm or cand_norm in name_norm
        for cand_norm in candidate_norms
        if cand_norm
    )


def _is_placeholder_instrument_name(name: Any) -> bool:
    text = _normalize_text(str(name or ""))
    text = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", text)
    if not text:
        return True
    return text in PLACEHOLDER_INSTRUMENT_NAMES or text in {"modeltype", "serialnumber", "assetnumber"}


def _lexical_score(query: str, doc_text: str, metadata: Dict[str, Any]) -> float:
    query_norm = _normalize_text(query)
    if not query_norm:
        return 0.0

    parts = [doc_text or ""]
    for value in metadata.values():
        if value is not None:
            parts.append(str(value))
    doc_norm = _normalize_text(" ".join(parts))

    score = 0.0
    if query_norm in doc_norm:
        score += 10.0

    query_tokens = set(re.findall(r"[a-z0-9\u4e00-\u9fff]+", query_norm))
    doc_tokens = set(re.findall(r"[a-z0-9\u4e00-\u9fff]+", doc_norm))
    score += float(len(query_tokens & doc_tokens))
    return score


def _load_raw_records(cfg: AppConfig) -> List[tuple[str, Dict[str, Any]]]:
    db_path = Path(cfg.cnas_db_dir).resolve()
    try:
        db_path = Path(os.path.relpath(str(db_path), start=str(Path.cwd())))
    except Exception:
        pass

    client = chromadb.PersistentClient(
        path=str(db_path),
        settings=chromadb.config.Settings(anonymized_telemetry=False),
    )
    collection = client.get_collection(str(cfg.cnas_collection))

    try:
        data = collection.peek(limit=10000)
    except Exception as exc:
        raise RuntimeError(f"cnas collection peek failed: {exc}") from exc

    rows = []
    documents = data.get("documents") or []
    metadatas = data.get("metadatas") or []
    for doc_text, metadata in zip(documents, metadatas):
        rows.append((str(doc_text or ""), dict(metadata or {})))
    return rows


def _infer_measured_label(doc_text: str, metadata: Dict[str, Any]) -> str:
    text = str(doc_text or "")
    lowered = text.lower()
    meta_blob = " ".join(
        str(metadata.get(key) or "")
        for key in (
            "???",
            "????",
            "??????",
            "measure_range_segments_json",
            "measure_range_segments_text",
            "??",
            "??",
            "????",
            "error_limit_text",
        )
        if metadata.get(key) not in (None, "")
    ).lower()

    if (
        "period measurement and sensitivity" in lowered
        or "period measurement range and input sensitivity" in lowered
        or "period_measurement_range_and_input_sensitivity" in meta_blob
        or "??????????" in text
        or "????????????" in text
        or "????????" in text
        or "10 ?s" in meta_blob
        or "50 ns" in meta_blob
        or "40 ps" in meta_blob
    ):
        return "period_measurement_range_and_input_sensitivity"
    if (
        "frequency measurement and sensitivity" in lowered
        or "frequency measurement range and input sensitivity" in lowered
        or "frequency_measurement_range_and_input_sensitivity" in meta_blob
        or "??????????" in text
        or "????????????" in text
        or "????????" in text
        or "100 kHz" in meta_blob
        or "20 mhz" in meta_blob
        or "50 ghz" in meta_blob
    ):
        return "frequency_measurement_range_and_input_sensitivity"
    if "period measurement" in lowered or "????" in text:
        return "period"
    if "frequency measurement" in lowered or "????" in text:
        return "frequency"
    if "relative frequency deviation" in lowered or "??" in text:
        return "crystal"

    for key in ("被测量", "measured", "项目名称", "???", "??", "??", "??"):
        value = metadata.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _first_present(metadata: Dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = metadata.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _uncertainty_text_from_raw(raw_u: Any, doc_text: str) -> str:
    uncertainty = ensure_uncertainty(raw_u, doc_text)
    if isinstance(uncertainty, dict):
        return str(
            uncertainty.get("value_display")
            or uncertainty.get("value")
            or uncertainty.get("raw")
            or ""
        ).strip()
    return str(raw_u or "").strip()


def search_calibration_data(
    query_text: str = "",
    cfg: Optional[AppConfig] = None,
    topk: int = 20,
    instrument_name: Optional[str] = None,
    embedder_obj=None,
    **kwargs,
) -> List[Dict[str, Any]]:
    """Return the top-matching CNAS records as dictionaries."""
    if not query_text:
        query_text = str(kwargs.get("query", "")).strip()

    cfg = get_config(cfg)
    records = _load_raw_records(cfg)
    criterion_norm = _extract_criterion_norm(query_text)
    instrument_filter = str(instrument_name or "").strip()
    if _is_placeholder_instrument_name(instrument_filter):
        instrument_filter = ""

    scored: List[tuple[float, Dict[str, Any], bool]] = []
    for doc_text, metadata in records:
        raw_u = (
            metadata.get("u_text")
            or metadata.get("kb_u")
            or metadata.get("不确定度")
            or metadata.get("uncertainty")
            or metadata.get("error_limit_text", "")
        )
        uncertainty = ensure_uncertainty(raw_u, doc_text)
        entry = {
            "page_content": doc_text,
            "文档内容": doc_text,
            "measured": _infer_measured_label(doc_text, metadata),
            "measure_range_text": _first_present(metadata, "测量范围", "范围", "measure_range_text"),
            "u_text": _uncertainty_text_from_raw(raw_u, doc_text),
            "uncertainty": uncertainty,
            "仪器名称": _first_present(metadata, "仪器名称", "instrument_name"),
            "依据编号": _first_present(metadata, "依据编号", "file_code"),
            "依据名称": _first_present(metadata, "依据名称", "standard_name", "校准依据"),
            "FILE_CODE": _first_present(metadata, "file_code", "依据编号"),
            "INSTRUMENT_NAME": _first_present(metadata, "仪器名称", "instrument_name"),
            "FILE_NAME": _first_present(metadata, "standard_name", "依据名称", "校准依据"),
            "校准依据": _first_present(metadata, "校准依据", "standard_name", "依据名称"),
            "范围": _first_present(metadata, "测量范围", "范围", "measure_range_text"),
            "频率": _first_present(metadata, "频率"),
            "metadata": metadata,
            "error_limit_text": metadata.get("error_limit_text", "") or _extract_error_limit_text(doc_text, metadata),
        }
        score = _lexical_score(query_text, doc_text, metadata)
        basis_hit = _matches_criterion_norm(doc_text, metadata, criterion_norm)
        if basis_hit or score > 0:
            scored.append((score, entry, basis_hit))

    if not scored:
        return []

    # 阶段1：先按规程号命中收敛候选集；若无法解析/命中则回退到语义检索结果。
    if criterion_norm:
        basis_pool = [(score, entry) for score, entry, basis_hit in scored if basis_hit]
    else:
        basis_pool = []
    # 规则：一旦识别出规程号并命中候选，必须返回“同规程号全量条目”。
    # 仪器名仅用于优先排序，不用于裁剪掉同规程条目。
    if basis_pool:
        if instrument_filter:
            matched = [(score, entry) for score, entry in basis_pool if _matches_instrument_filter(entry, instrument_filter)]
            unmatched = [(score, entry) for score, entry in basis_pool if not _matches_instrument_filter(entry, instrument_filter)]
            matched.sort(key=lambda item: item[0], reverse=True)
            unmatched.sort(key=lambda item: item[0], reverse=True)
            final_pool = matched + unmatched
        else:
            final_pool = sorted(basis_pool, key=lambda item: item[0], reverse=True)
        return [entry for _, entry in final_pool]

    # 无规程号可用时，按原策略：可被仪器名过滤并截断 topk。
    working_pool = [(score, entry) for score, entry, _ in scored]
    if instrument_filter:
        working_pool = [
            (score, entry)
            for score, entry in working_pool
            if _matches_instrument_filter(entry, instrument_filter)
        ]
    working_pool.sort(key=lambda item: item[0], reverse=True)
    return [entry for _, entry in working_pool[:topk]]


def search_calibration_response(
    query_text: str = "",
    cfg: Optional[AppConfig] = None,
    topk: int = 20,
    instrument_name: Optional[str] = None,
    embedder_obj=None,
    **kwargs,
) -> RetrievalResponse:
    """Canonical entry point returning RetrievalResponse with diagnostic codes.

    Wraps the legacy search_calibration_data() so new call sites can branch on
    diagnostic.code rather than guessing from len(items).
    """
    cfg = get_config(cfg)
    db_dir = str(getattr(cfg, "cnas_db_dir", "") or "")
    collection = str(getattr(cfg, "cnas_collection", "") or "")
    criterion_norm = _extract_criterion_norm(query_text or str(kwargs.get("query", "")))

    if db_dir and not Path(db_dir).exists():
        return RetrievalResponse(
            query=query_text,
            hits=[],
            diagnostic=Diagnostic(
                code=DiagnosticCode.DB_MISSING,
                message=f"vector_db path missing: {db_dir}",
            ),
            db_dir=db_dir,
            collection=collection,
            topk=topk,
        )

    try:
        items = search_calibration_data(
            query_text=query_text,
            cfg=cfg,
            topk=topk,
            instrument_name=instrument_name,
            embedder_obj=embedder_obj,
            **kwargs,
        )
    except Exception as exc:
        message = str(exc)
        if "collection" in message.lower() and "exist" in message.lower():
            code = DiagnosticCode.COLLECTION_MISSING
        else:
            code = DiagnosticCode.UNEXPECTED_ERROR
        return RetrievalResponse(
            query=query_text,
            hits=[],
            diagnostic=Diagnostic(code=code, message=message),
            db_dir=db_dir,
            collection=collection,
            topk=topk,
        )

    if not items:
        if criterion_norm:
            diagnostic = Diagnostic(
                code=DiagnosticCode.NO_SAME_BASIS,
                message=f"no entry matches basis {criterion_norm}",
            )
        else:
            diagnostic = Diagnostic(
                code=DiagnosticCode.LOW_SIMILARITY,
                message="no hits returned",
            )
        return RetrievalResponse(
            query=query_text,
            hits=[],
            diagnostic=diagnostic,
            db_dir=db_dir,
            collection=collection,
            topk=topk,
        )

    return response_from_legacy_dicts(
        query=query_text,
        items=items,
        db_dir=db_dir,
        collection=collection,
        topk=topk,
    )


def _extract_text_from_source(source: Dict[str, Any], keys: List[str]) -> str:
    if not isinstance(source, dict):
        return ""
    for key in keys:
        value = source.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _extract_error_limit_text(doc: str, meta: Dict[str, Any]) -> str:
    candidates = [
        _extract_text_from_source(
            meta,
            [
                "error_limit_text",
                "limit_text",
                "允许误差",
                "允许范围",
                "限值",
                "最大允许误差",
                "误差限值",
                "容差",
                "允差",
                "limit",
                "Limit",
            ],
        ),
        _extract_text_from_source(
            meta.get("meta") or meta.get("metadata") or {},
            [
                "error_limit_text",
                "limit_text",
                "允许误差",
                "允许范围",
                "限值",
                "最大允许误差",
                "误差限值",
                "容差",
                "允差",
                "limit",
                "Limit",
            ],
        ),
    ]
    for candidate in candidates:
        if candidate:
            return candidate

    patterns = [
        r"(?:最大允许误差|允许误差|误差限值|限值|容差|允差|limit)[：:]\s*([^。\n;；]+)",
        r"(?:允许误差|误差|偏差)[：:]\s*([^。\n;；]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, doc, re.IGNORECASE)
        if match:
            candidate = match.group(1).strip()
            if candidate and candidate.lower() not in {"n/a", "na", "none", "无", "未知"}:
                return candidate

    for line in doc.splitlines():
        line_text = str(line).strip()
        if not line_text:
            continue
        lowered = line_text.lower()
        if any(token in lowered for token in ("允许误差", "误差限值", "最大允许误差", "限值", "容差", "允差", "limit", "偏差")):
            match = re.search(r"[：:]\s*([^。\n;；]+)", line_text)
            if match:
                candidate = match.group(1).strip()
                if candidate and candidate.lower() not in {"n/a", "na", "none", "无", "未知"}:
                    return candidate
            if re.search(r"[≤≥<>]=?\s*[-+]?\d", line_text):
                return line_text
    return "N/A"


def filter_kb_entries(
    kb_entries: List[Dict[str, Any]],
    batch_params: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    return _filter_kb_entries_multidimensional(kb_entries, batch_params)


def _parse_measure_range_segments(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]

    text = str(value).strip()
    if not text:
        return []

    if text.startswith("["):
        try:
            loaded = json.loads(text)
            if isinstance(loaded, list):
                return [str(item).strip() for item in loaded if str(item).strip()]
        except Exception:
            pass

    parts = [part.strip() for part in re.split(r"[；;]", text) if part.strip()]
    if len(parts) > 1:
        return parts
    return [text]


def parse_kb_entry(doc: str, meta: Dict[str, Any]) -> Dict[str, Any]:
    meta = ensure_dict(meta)

    instrument_name = (
        meta.get("仪器名称")
        or meta.get("instrument_name")
        or pick_first(doc, r"仪器名称[：:]\s*(.+?)(?:[。；\n]|$)")
        or "N/A"
    )

    standard_name = (
        meta.get("standard_name")
        or meta.get("校准依据")
        or pick_first(doc, r"校准依据[：:]\s*(.+?)(?:[。；\n]|$)")
        or "N/A"
    )

    file_code = meta.get("file_code") or meta.get("依据编号") or None
    if not file_code:
        m = re.search(r"\b(JJ[GF]|GJB)\s*(\d+)", standard_name, re.IGNORECASE)
        if m:
            file_code = f"{m.group(1).upper()} {m.group(2)}"
    if not file_code:
        file_code = standard_name if standard_name != "N/A" else "未知规程"

    measured = (
        meta.get("被测量")
        or meta.get("measured")
        or pick_first(doc, r"被测量[：:]\s*(.+?)(?:[。；\n]|$)")
        or "N/A"
    )

    measure_range_text = (
        meta.get("测量范围")
        or meta.get("measure_range_text")
        or pick_first(doc, r"测量范围[：:]\s*(.+?)(?:[。；\n]|$)")
        or "-"
    )
    measure_range_segments = _parse_measure_range_segments(
        meta.get("measure_range_segments_json")
        or meta.get("measure_range_segments")
        or pick_first(doc, r"测量范围分段[：:]\s*(.+?)(?:[。；\n]|$)")
    )

    raw_u = meta.get("不确定度") or meta.get("uncertainty")
    uncertainty = ensure_uncertainty(raw_u, doc)
    error_limit_text = _extract_error_limit_text(doc, meta)

    return {
        "instrument_name": instrument_name,
        "standard_name": standard_name,
        "file_code": file_code,
        "measured": measured,
        "measure_range_text": measure_range_text,
        "measure_range_segments": measure_range_segments,
        "measure_range_segments_text": "；".join(measure_range_segments),
        "error_limit_text": error_limit_text,
        "uncertainty": uncertainty,
        "raw": doc,
        "meta": meta,
    }


def ensure_dict(obj: Any) -> Dict[str, Any]:
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    return {}


def pick_first(text: str, pattern: str) -> Optional[str]:
    if not text or not pattern:
        return None
    match = re.search(pattern, text)
    if match:
        return match.group(1).strip()
    return None


def ensure_uncertainty(u_info: Any, doc: str) -> Dict[str, Any]:
    if isinstance(u_info, dict):
        return u_info
    if not u_info or u_info == "N/A":
        return {"type": "N/A", "value": "N/A"}

    u_str = str(u_info)
    if any(sep in u_str for sep in ("~", "～")):
        if re.search(r"U\s*rel\s*=", u_str, re.IGNORECASE) or re.search(r"Urel\s*=", u_str, re.IGNORECASE) or "%" in u_str:
            return {"type": "Urel", "value": u_str, "value_display": u_str, "raw": u_str}
        return {"type": "U", "value": u_str, "value_display": u_str, "raw": u_str}

    match = re.search(r"([\d.]+)\s*(%|Urel|U|urel)", u_str, re.IGNORECASE)
    if match:
        value = match.group(1)
        u_type = match.group(2).lower()
        if "%" in u_type:
            return {"type": "rel", "value": f"{value}%", "value_display": f"{value}%", "raw": u_str}
        if "urel" in u_type or "rel" in u_type:
            return {"type": "urel", "value": value, "value_display": value, "raw": u_str}
        return {"type": "U", "value": value, "value_display": value, "raw": u_str}

    u_from_doc = pick_first(doc, r"不确定度[：:]\s*([\d.]+)\s*(%|U)")
    if u_from_doc:
        return {"type": "U" if "U" in u_from_doc else "rel", "value": u_from_doc, "value_display": u_from_doc, "raw": u_str}

    return {"type": "N/A", "value": str(u_info), "value_display": str(u_info), "raw": u_str}


def select_best_kb_entries(
    kb_entries: List[Dict[str, Any]],
    criterion: str,
) -> List[Dict[str, Any]]:
    if not kb_entries:
        return []

    m = re.search(r"\b(JJ[GF]|GJB)\s*(\d+)(?:\s*-\s*\d{4})?\b", criterion or "", re.IGNORECASE)
    if not m:
        return kb_entries[:10]

    criterion_norm = f"{m.group(1).upper()}{m.group(2)}"
    matched = []
    for entry in kb_entries:
        file_code = str(entry.get("file_code", "") or entry.get("依据编号", "")).strip()
        file_norm = re.sub(r"\s+", "", file_code).upper()
        if file_norm == criterion_norm:
            matched.append(entry)
    return matched[:10] if matched else kb_entries[:10]
