#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LangGraph 条件路由函数
"""

from langchain_app.graph.state import VerificationState


def check_should_stop(
    state: VerificationState,
) -> str:
    """
    检查是否需要提前终止流程

    完整性核验后调用，根据结果决定下一步执行路径

    Args:
        state: 当前状态

    Returns:
        str: 下一步节点名称
    """
    if state.should_stop:
        return "assemble_report"

    return "parse_json"


def after_parse_json(
    state: VerificationState,
) -> str:
    """
    JSON解析后路由

    Args:
        state: 当前状态

    Returns:
        str: 下一步节点名称
    """
    if state.should_stop or state.json_path is None:
        return "assemble_report"

    return "integrity_check"


def after_integrity_check(
    state: VerificationState,
) -> str:
    """
    完整性核验后路由

    Args:
        state: 当前状态

    Returns:
        str: 下一步节点名称
    """
    if state.should_stop or state.integrity_result is None:
        return "assemble_report"

    return "environment_check"


def after_environment_check(
    state: VerificationState,
) -> str:
    """
    环境条件核验后路由

    Args:
        state: 当前状态

    Returns:
        str: 下一步节点名称
    """
    if state.should_stop or state.environment_result is None:
        return "assemble_report"

    return "location_check"


def after_location_check(
    state: VerificationState,
) -> str:
    """
    校准地点核验后路由

    Args:
        state: 当前状态

    Returns:
        str: 下一步节点名称
    """
    if state.should_stop or state.location_result is None:
        return "assemble_report"

    return "cycle_check"


def after_cycle_check(
    state: VerificationState,
) -> str:
    """
    校准周期核验后路由

    Args:
        state: 当前状态

    Returns:
        str: 下一步节点名称
    """
    if state.should_stop or state.cycle_result is None:
        return "assemble_report"

    return "parameter_check"


def after_parameter_check(
    state: VerificationState,
) -> str:
    """
    参数与不确定度核验后路由

    Args:
        state: 当前状态

    Returns:
        str: 下一步节点名称
    """
    return "assemble_report"
