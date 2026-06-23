#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Instrument profile models for parameter verification."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Dict, Iterable, List, Tuple


def normalize_text(value: str | None) -> str:
    return re.sub(r"\s+", "", str(value or "").strip().lower())


def contains_any(text: str | None, aliases: Iterable[str]) -> bool:
    normalized = normalize_text(text)
    if not normalized:
        return False
    return any(normalize_text(alias) in normalized for alias in aliases if normalize_text(alias))


@dataclass(frozen=True)
class InstrumentProfile:
    """Rules enabled for one instrument family or calibration criterion family.

    Profiles intentionally stay declarative. The current parameter pipeline can
    use them to route semantic targets and special policies without moving core
    range/error/U verification logic into many small modules too early.
    """

    profile_id: str
    display_name: str
    family: str
    instrument_aliases: Tuple[str, ...] = ()
    criterion_aliases: Tuple[str, ...] = ()
    pdf_category_aliases: Tuple[str, ...] = ()
    semantic_targets: Tuple[str, ...] = ()
    special_policies: Dict[str, str] = field(default_factory=dict)
    parser_notes: Tuple[str, ...] = ()
    verification_notes: Tuple[str, ...] = ()
    priority: int = 100

    def matches(
        self,
        *,
        instrument_name: str = "",
        criterion: str = "",
        pdf_category: str = "",
    ) -> bool:
        return (
            contains_any(instrument_name, self.instrument_aliases)
            or contains_any(criterion, self.criterion_aliases)
            or contains_any(pdf_category, self.pdf_category_aliases)
        )


@dataclass(frozen=True)
class ProfileMatch:
    profile: InstrumentProfile
    reason: str


def match_reason(
    profile: InstrumentProfile,
    *,
    instrument_name: str = "",
    criterion: str = "",
    pdf_category: str = "",
) -> str:
    if contains_any(instrument_name, profile.instrument_aliases):
        return "instrument_alias"
    if contains_any(criterion, profile.criterion_aliases):
        return "criterion_alias"
    if contains_any(pdf_category, profile.pdf_category_aliases):
        return "pdf_category_alias"
    return "fallback"

