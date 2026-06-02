#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LangGraph 状态定义
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

from langchain_app.utils.config import AppConfig, coerce_app_config


class VerificationState(BaseModel):
    """
    文档核验流程的状态定义

    所有节点共享这个状态对象，包含完整的核验上下文和结果
    """

    # ==================== 文件路径 ====================
    source_pdf_path: Optional[str] = Field(default=None, description="原始PDF文件路径")
    md_path: Optional[str] = Field(default=None, description="Markdown解析结果路径")
    json_path: Optional[str] = Field(default=None, description="JSON解析结果路径")

    # ==================== 配置与运行时 ====================
    config: Optional[AppConfig] = Field(default=None, description="应用配置对象")
    runtime_cfg: Optional[Any] = Field(default=None, description="兼容保留的旧运行时配置")
    embedder: Optional[Any] = Field(default=None, description="嵌入模型对象")
    llm_client: Optional[Any] = Field(default=None, description="LLM客户端")
    hooks: Optional[Any] = Field(default=None, description="UI hooks")
    stop_event: Optional[Any] = Field(default=None, description="任务停止事件")

    # ==================== 核验结果 ====================
    integrity_result: Optional[str] = Field(default=None, description="完整性核验结果")
    environment_result: Optional[str] = Field(default=None, description="环境条件核验结果")
    location_result: Optional[str] = Field(default=None, description="校准地点核验结果")
    cycle_result: Optional[str] = Field(default=None, description="校准周期核验结果")
    parameter_result: Optional[str] = Field(default=None, description="参数与不确定度核验结果")

    # ==================== 报告与日志 ====================
    final_report: Optional[str] = Field(default=None, description="最终核验报告")
    report_sections: List[str] = Field(default_factory=list, description="按原主线顺序累积的报告分段")
    logs: List[str] = Field(default_factory=list, description="运行日志")
    warnings: List[str] = Field(default_factory=list, description="警告信息")
    errors: List[str] = Field(default_factory=list, description="错误信息")

    # ==================== 流程控制 ====================
    should_stop: bool = Field(default=False, description="是否应该提前终止流程")
    current_step: Optional[str] = Field(default=None, description="当前执行步骤")
    progress: float = Field(default=0.0, description="进度 (0.0-1.0)")

    # ==================== 工具方法 ====================

    def add_log(self, message: str):
        """添加日志"""
        self.logs.append(message)

    def add_warning(self, message: str):
        """添加警告"""
        self.warnings.append(message)

    def add_error(self, message: str):
        """添加错误"""
        self.errors.append(message)

    def add_report_section(self, content: str):
        """按原流水线顺序追加报告段落"""
        if content:
            normalized = content.strip()
            # 仅剥离完整报告头，避免误伤参数核验这类以标题开头的正常章节。
            if normalized.startswith("# 全流程智能核验报告") and "\n---\n" in normalized:
                normalized = normalized.split("\n---\n", 1)[1].lstrip("\n")
            self.report_sections.append(normalized)

    def set_progress(self, progress: float, step: Optional[str] = None):
        """设置进度"""
        self.progress = max(0.0, min(1.0, progress))
        if step:
            self.current_step = step

    def emit_status(self, message: str):
        if self.hooks and getattr(self.hooks, "emit_status", None):
            self.hooks.emit_status(message)

    def emit_progress(self, value: int):
        if self.hooks and getattr(self.hooks, "emit_progress", None):
            self.hooks.emit_progress(value)

    def emit_info(self, message: str):
        self.add_log(message)
        if self.hooks and getattr(self.hooks, "emit_info", None):
            self.hooks.emit_info(message)

    def emit_warning(self, message: str):
        self.add_warning(message)
        if self.hooks and getattr(self.hooks, "emit_warning", None):
            self.hooks.emit_warning(message)

    def emit_error(self, message: str):
        self.add_error(message)
        if self.hooks and getattr(self.hooks, "emit_error", None):
            self.hooks.emit_error(message)

    def emit_success(self, message: str):
        if self.hooks and getattr(self.hooks, "emit_success", None):
            self.hooks.emit_success(message)

    def get_all_results(self) -> Dict[str, Optional[str]]:
        """获取所有核验结果"""
        return {
            "integrity": self.integrity_result,
            "environment": self.environment_result,
            "location": self.location_result,
            "cycle": self.cycle_result,
            "parameter": self.parameter_result,
        }

    def has_errors(self) -> bool:
        """是否有错误"""
        return len(self.errors) > 0

    def has_warnings(self) -> bool:
        """是否有警告"""
        return len(self.warnings) > 0

    class Config:
        """Pydantic 配置"""
        arbitrary_types_allowed = True


# ==================== 状态初始值 ====================

def create_initial_state(
    pdf_path: str = None,
    json_path: str = None,
    config: Any = None,
    runtime_cfg: Any = None,
    embedder: Optional[Any] = None,
    llm_client: Optional[Any] = None,
    hooks: Optional[Any] = None,
    stop_event: Optional[Any] = None,
) -> VerificationState:
    """
    创建初始状态

    Args:
        pdf_path: PDF文件路径（可选）
        json_path: JSON文件路径（可选）
        config: 应用配置（可选）
        runtime_cfg: 兼容保留的旧运行时配置（可选）
        embedder: 嵌入模型（可选）
        llm_client: LLM客户端（可选）

    Returns:
        VerificationState: 初始状态对象
    """
    normalized_config: Optional[AppConfig] = None
    if config is not None or runtime_cfg is not None:
        normalized_config = coerce_app_config(config if config is not None else runtime_cfg)

    state = VerificationState(
        config=normalized_config,
        runtime_cfg=runtime_cfg,
        embedder=embedder,
        llm_client=llm_client,
        hooks=hooks,
        stop_event=stop_event,
        logs=[],
        progress=0.0,
        report_sections=[],
    )

    if pdf_path:
        state.source_pdf_path = str(pdf_path)
        state.logs.append(f"初始化核验流程: {pdf_path}")

    if json_path:
        state.json_path = str(json_path)

    return state
