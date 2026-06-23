#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Certificate field normalization.

Collapses synonym fields at the parser exit into a single canonical key.
Originals preserved under __raw_fields. Downstream checks read canonical
keys only; no per-call fallback chains.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ALIAS_MAP: Dict[str, List[str]] = {
    "仪器名称": ["仪器名称", "INSTRUMENT_NAME", "instrument_name"],
    "型号规格": ["型号规格", "型号", "规格型号", "规格"],
    "制造商": ["制造商", "制造厂", "厂家", "manufacturer"],
    "序列号": ["序列号", "机身号", "出厂编号", "serial_no", "SERIAL_NO"],
    "管理号": ["管理号", "资产编号", "asset_number"],
    "委托单位": ["委托单位", "委托单位名称", "客户名称", "client"],
    "委托方地址": ["委托方地址", "委托单位地址", "客户地址"],
    "温度": ["温度", "环境温度"],
    "相对湿度": ["相对湿度", "湿度", "环境湿度"],
    "温度_内页": ["温度_内页", "温度_内"],
    "相对湿度_内页": ["相对湿度_内页", "湿度_内页"],
    "校准地点": ["校准地点", "校准地址", "地点", "实验室地点"],
    "校准日期": ["校准日期", "测试日期"],
    "接收日期": ["接收日期", "送样日期"],
    "签发日期": ["签发日期", "签发时间", "出具日期"],
    "CNAS": ["CNAS", "是否CNAS", "CNAS标志"],
    "证书编号": ["证书编号", "Certificate No", "certificate_no"],
    "建议校准周期": ["建议校准周期", "校准周期", "推荐校准周期"],
    "校准依据": ["校准依据", "依据"],
}

_ALIAS_TO_CANONICAL: Dict[str, str] = {}
for _canonical, _aliases in ALIAS_MAP.items():
    for _alias in _aliases:
        _ALIAS_TO_CANONICAL[_alias] = _canonical

RAW_FIELDS_KEY = "__raw_fields"


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, (list, dict)):
        return len(value) == 0
    return False


def normalize_certificate_props(props: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(props, dict):
        return props

    out: Dict[str, Any] = {}
    raw_fields: Dict[str, Dict[str, Any]] = {}

    canonical_to_hits: Dict[str, List[Tuple[str, Any]]] = {}
    untouched: Dict[str, Any] = {}
    for key, value in props.items():
        if key == RAW_FIELDS_KEY:
            if isinstance(value, dict):
                for k, v in value.items():
                    if isinstance(v, dict):
                        raw_fields.setdefault(k, {}).update(v)
            continue
        canonical = _ALIAS_TO_CANONICAL.get(key)
        if canonical is None:
            untouched[key] = value
            continue
        canonical_to_hits.setdefault(canonical, []).append((key, value))

    for canonical, aliases in ALIAS_MAP.items():
        hits = canonical_to_hits.get(canonical)
        if not hits:
            continue
        priority = {alias: idx for idx, alias in enumerate(aliases)}
        hits.sort(key=lambda kv: priority.get(kv[0], len(aliases)))
        chosen_value: Any = None
        for _, value in hits:
            if not _is_empty(value):
                chosen_value = value
                break
        if chosen_value is None:
            chosen_value = hits[0][1]
        out[canonical] = chosen_value
        raw_fields.setdefault(canonical, {})
        for raw_key, raw_value in hits:
            raw_fields[canonical][raw_key] = raw_value

    for key, value in untouched.items():
        out[key] = value

    if raw_fields:
        out[RAW_FIELDS_KEY] = raw_fields

    return out


def apply_normalization_to_data(raw_data: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(raw_data, dict):
        return raw_data
    try:
        props_container = raw_data["properties"]["证书列表"]["items"]
        props = props_container.get("properties")
    except (KeyError, AttributeError, TypeError):
        return raw_data
    if not isinstance(props, dict):
        return raw_data
    props_container["properties"] = normalize_certificate_props(props)
    return raw_data


def normalize_certificate_json_file(json_path: Path) -> bool:
    json_path = Path(json_path)
    text = json_path.read_text(encoding="utf-8")
    data = json.loads(text)
    apply_normalization_to_data(data)
    new_text = json.dumps(data, ensure_ascii=False, indent=2)
    if new_text == text:
        return False
    json_path.write_text(new_text, encoding="utf-8")
    return True


def load_and_normalize_certificate_json(json_path) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    with open(json_path, "r", encoding="utf-8") as f:
        raw_data = json.load(f)
    apply_normalization_to_data(raw_data)
    try:
        props = raw_data["properties"]["证书列表"]["items"]["properties"]
    except KeyError:
        props = raw_data if isinstance(raw_data, dict) else {}
    if not isinstance(props, dict):
        props = {}
    return raw_data, props


def canonical_key_of(alias: str) -> Optional[str]:
    return _ALIAS_TO_CANONICAL.get(alias)
