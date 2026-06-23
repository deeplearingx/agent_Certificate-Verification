#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
演示如何使用新的模块化API编写简洁的CNAS参数核验代码
"""

import json
from typing import Any, Dict, List

from core import (
    NumberParser,
    RangeVerifier,
    ErrorVerifier,
    UncertaintyVerifier,
    ReportGenerator
)


def main():
    print("=" * 60)
    print("CNAS参数核验 - 使用新API示例")
    print("=" * 60)

    # ===================== 1. 基础功能演示 =====================
    print("\n1. 基础功能")
    print("-" * 40)

    # 解析带单位的数值
    value, unit, original = NumberParser.parse_value_with_unit("6.6×10⁻⁹ Hz")
    print(f"解析值: {original} → {value} {unit}")

    # 验证范围
    range_result = RangeVerifier.verify_range_logic("10.5 V", "0~20 V")
    print(f"范围验证: {json.loads(range_result)['reason']}")

    # 验证误差
    error_result = ErrorVerifier.verify_error_logic("0.1 mV", "0.5 mV")
    print(f"误差验证: {json.loads(error_result)['reason']}")

    # 验证不确定度
    unc_result = UncertaintyVerifier.verify_uncertainty_logic("10.5 V", "0.1", "0.2")
    print(f"不确定度验证: {json.loads(unc_result)['reason']}")

    # ===================== 2. 完整工作流程演示 =====================
    print("\n2. 完整工作流程")
    print("-" * 40)

    # 模拟数据
    parameters = [
        {
            "param_name": "输入电压",
            "measure_val": "10.5 V",
            "range_str": "0~20 V",
            "status": "PASS",
            "kb_code": "JJG 314",
            "note": "合格"
        },
        {
            "param_name": "输出电流",
            "measure_val": "5.2 mA",
            "range_str": "0~10 mA",
            "status": "PASS",
            "kb_code": "JJG 314",
            "note": "合格"
        },
        {
            "param_name": "频率",
            "measure_val": "6.6e-9 Hz",
            "range_str": "5~10 nHz",
            "status": "FAIL",
            "kb_code": "JJG 123",
            "note": "超出范围"
        }
    ]

    # 生成报告
    report = ReportGenerator.build_param_table(parameters)
    print("报告生成:\n")
    print(report)

    # ===================== 3. 错误处理演示 =====================
    print("\n3. 错误处理")
    print("-" * 40)

    try:
        invalid_result = RangeVerifier.verify_range_logic("invalid", "0~10")
        print(f"处理无效值: {invalid_result}")
    except Exception as e:
        print(f"Error: {e}")

    print("\n" + "=" * 60)
    print("演示完成！")
    print("使用新API的代码更简洁、更易维护")
    print("=" * 60)


if __name__ == "__main__":
    main()
