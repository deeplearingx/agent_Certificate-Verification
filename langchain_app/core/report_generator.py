#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Markdown report builder used by the LangGraph mainline.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List


@dataclass
class MarkdownReport:
    title: str
    metadata: List[str] = field(default_factory=list)
    sections: List[str] = field(default_factory=list)

    def add_section(self, content: str, prepend_divider: bool = False) -> None:
        if prepend_divider and self.sections:
            self.sections.append("\n---\n" + content)
        else:
            self.sections.append(content)

    def render(self) -> str:
        parts = [self.title]
        parts.extend(self.metadata)
        parts.append("---")
        parts.extend(self.sections)
        return "\n".join(parts)


def build_verification_report_header(
    *,
    source_name: str,
    verified_at: str,
    model: str,
    temperature: float,
    topk: int,
) -> MarkdownReport:
    """Build the shared top-level report header."""
    return MarkdownReport(
        title="# 全流程智能核验报告",
        metadata=[
            f"**源文件**: `{source_name}`",
            f"**核验时间**: `{verified_at}`",
            f"**核验模型**: `{model}` (Temp: {temperature}, TopK: {topk})",
        ],
    )


class VerificationReport:
    """
    Backward-compatible report builder used by the checks modules.
    """

    def __init__(self):
        self.sections: List[str] = []
        self.source_name = ""
        self.verified_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.model = ""
        self.temperature = 0.0
        self.topk = 3

    def set_header(self, source_name: str, model: str, temperature: float, topk: int):
        self.source_name = source_name
        self.verified_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.model = model
        self.temperature = temperature
        self.topk = topk

    def add_section(self, content: str, prepend_divider: bool = False):
        if prepend_divider and self.sections:
            self.sections.append("\n---\n")
        self.sections.append(content)

    def render(self) -> str:
        header = build_verification_report_header(
            source_name=self.source_name,
            verified_at=self.verified_at,
            model=self.model,
            temperature=self.temperature,
            topk=self.topk,
        )
        for section in self.sections:
            header.add_section(section)
        return header.render()
