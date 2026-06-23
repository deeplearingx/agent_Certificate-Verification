#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Instrument profile registry for parameter verification."""

from __future__ import annotations

from typing import Iterable, List, Optional

from .base import InstrumentProfile, ProfileMatch, match_reason
from .general import GENERIC_PROFILES
from .oscilloscope_function import OSCILLOSCOPE_FUNCTION_PROFILES
from .rf_microwave import RF_MICROWAVE_PROFILES
from .time_frequency import TIME_FREQUENCY_PROFILES


PROFILE_REGISTRY: tuple[InstrumentProfile, ...] = tuple(
    sorted(
        (
            *TIME_FREQUENCY_PROFILES,
            *RF_MICROWAVE_PROFILES,
            *OSCILLOSCOPE_FUNCTION_PROFILES,
            *GENERIC_PROFILES,
        ),
        key=lambda profile: profile.priority,
    )
)


def get_profile(profile_id: str) -> InstrumentProfile:
    for profile in PROFILE_REGISTRY:
        if profile.profile_id == profile_id:
            return profile
    raise KeyError(f"Unknown parameter instrument profile: {profile_id}")


def match_profiles(
    *,
    instrument_name: str = "",
    criterion: str = "",
    pdf_category: str = "",
    include_generic: bool = True,
) -> List[ProfileMatch]:
    matches: List[ProfileMatch] = []
    for profile in PROFILE_REGISTRY:
        if profile.profile_id == "generic.default":
            continue
        if profile.matches(
            instrument_name=instrument_name,
            criterion=criterion,
            pdf_category=pdf_category,
        ):
            matches.append(
                ProfileMatch(
                    profile=profile,
                    reason=match_reason(
                        profile,
                        instrument_name=instrument_name,
                        criterion=criterion,
                        pdf_category=pdf_category,
                    ),
                )
            )
    if include_generic and not matches:
        matches.append(ProfileMatch(profile=get_profile("generic.default"), reason="fallback"))
    return matches


def enabled_semantic_targets(profiles: Iterable[InstrumentProfile]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for profile in profiles:
        for target in profile.semantic_targets:
            if target in seen:
                continue
            seen.add(target)
            ordered.append(target)
    return tuple(ordered)


def best_profile(
    *,
    instrument_name: str = "",
    criterion: str = "",
    pdf_category: str = "",
) -> Optional[InstrumentProfile]:
    matches = match_profiles(
        instrument_name=instrument_name,
        criterion=criterion,
        pdf_category=pdf_category,
        include_generic=True,
    )
    return matches[0].profile if matches else None

