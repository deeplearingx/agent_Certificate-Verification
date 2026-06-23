#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DEPRECATED: 旧桥接层 - 已不再使用

此模块提供旧项目架构的兼容层，但新代码应该直接使用 langchain_app.checks.* 模块。

WARNING: 此模块将在未来版本中删除。
"""

import warnings

warnings.warn(
    "checks.adapters is deprecated and will be removed in a future version. "
    "Please use langchain_app.checks.* modules directly.",
    DeprecationWarning,
    stacklevel=2
)

from checks.base import CheckExecution, CheckRunner

import cycle_check
import env_check
import info_check
import location_check
import param_check


class InfoCheckRunner(CheckRunner):
    name = "integrity"

    def run(self, *, json_path: str, runtime_cfg, stop_event=None, embedder=None) -> CheckExecution:
        report = info_check.check_certificate_integrity(json_path, cfg=runtime_cfg)
        should_stop = "核验终止报告" in report or "系统拒绝处理" in report
        return CheckExecution(name=self.name, report=report, success=True, should_stop=should_stop)


class EnvironmentCheckRunner(CheckRunner):
    name = "environment"

    def run(self, *, json_path: str, runtime_cfg, stop_event=None, embedder=None) -> CheckExecution:
        report = env_check.check_environment(json_path, runtime_cfg)
        return CheckExecution(name=self.name, report=report)


class LocationCheckRunner(CheckRunner):
    name = "location"

    def run(self, *, json_path: str, runtime_cfg, stop_event=None, embedder=None) -> CheckExecution:
        report = location_check.check_location(
            json_file=json_path,
            cfg=runtime_cfg,
            embedder_obj=embedder,
            stop_event=stop_event,
        )
        return CheckExecution(name=self.name, report=report)


class CycleCheckRunner(CheckRunner):
    name = "cycle"

    def run(self, *, json_path: str, runtime_cfg, stop_event=None, embedder=None) -> CheckExecution:
        try:
            report = cycle_check.check_cycle_reasonableness(json_path, runtime_cfg, stop_event=stop_event)
        except TypeError:
            report = cycle_check.check_cycle_reasonableness(json_path, runtime_cfg)
        return CheckExecution(name=self.name, report=report)


class ParameterCheckRunner(CheckRunner):
    name = "parameter"

    def run(self, *, json_path: str, runtime_cfg, stop_event=None, embedder=None) -> CheckExecution:
        report = param_check.run_llm_mode(
            json_path,
            runtime_cfg,
            stop_event=stop_event,
            embedder_obj=embedder,
        )
        return CheckExecution(name=self.name, report=report)
