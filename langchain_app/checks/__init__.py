#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
langchain_app/checks 包初始化文件

导出所有的检查模块，并提供统一的接口（惰性导入策略）
"""

# 轻量导出 - 避免在包初始化时导入所有检查模块
__all__ = [
    "check_certificate_integrity",
    "info_check_wrapper",
    "check_environment",
    "environment_check_wrapper",
    "check_location",
    "location_check_wrapper",
    "check_cycle_reasonableness",
    "cycle_check_wrapper",
    "check_parameters",
    "parameter_check_wrapper",
    "run_llm_mode",
]

# 惰性导入策略 - 避免在包初始化时触发全部导入链
def __getattr__(name):
    if name in ["check_certificate_integrity", "info_check_wrapper"]:
        from .integrity import check_certificate_integrity, info_check_wrapper
        if name == "check_certificate_integrity":
            return check_certificate_integrity
        return info_check_wrapper
    if name in ["check_environment", "environment_check_wrapper"]:
        from .environment import check_environment, environment_check_wrapper
        if name == "check_environment":
            return check_environment
        return environment_check_wrapper
    if name in ["check_location", "location_check_wrapper"]:
        from .location import check_location, location_check_wrapper
        if name == "check_location":
            return check_location
        return location_check_wrapper
    if name in ["check_cycle_reasonableness", "cycle_check_wrapper"]:
        from .cycle import check_cycle_reasonableness, cycle_check_wrapper
        if name == "check_cycle_reasonableness":
            return check_cycle_reasonableness
        return cycle_check_wrapper
    if name in ["check_parameters", "parameter_check_wrapper", "run_llm_mode"]:
        from .parameter import check_parameters, parameter_check_wrapper, run_llm_mode
        if name == "check_parameters":
            return check_parameters
        if name == "parameter_check_wrapper":
            return parameter_check_wrapper
        return run_llm_mode
    raise AttributeError(f"module 'langchain_app.checks' has no attribute '{name}'")
