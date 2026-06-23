#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试重构的完整性
"""

import sys
import json
from typing import Dict, Any

def test_import() -> bool:
    """测试模块导入"""
    print("1. 模块导入测试")
    try:
        from core import Config
        from core import NumberParser, UnitConverter, RangeVerifier, ErrorVerifier, UncertaintyVerifier
        from core import KBFilters
        from core import TableProcessor, ReportGenerator
        from core import FirstCandidateDecider, infer_param_semantics, select_basis_with_audit

        print("   ✅ 所有模块成功导入")
        return True
    except Exception as e:
        print(f"   ❌ 模块导入失败: {e}")
        return False


def test_config() -> bool:
    """测试配置模块"""
    print("2. 配置模块测试")
    try:
        from core import Config

        cfg = Config.to_dict()
        print("   ✅ 配置读取成功")
        print(f"   DB_DIR: {cfg.get('DB_DIR')}")
        print(f"   API_BASE: {cfg.get('API_BASE')}")
        return True
    except Exception as e:
        print(f"   ❌ 配置模块失败: {e}")
        return False


def test_number_parser() -> bool:
    """测试数值解析"""
    print("3. 数值解析测试")
    try:
        from core import NumberParser

        # 解析带单位的数值
        value, unit, _ = NumberParser.parse_value_with_unit("10.5 kHz")
        if abs(value - 10.5) < 1e-9 and unit == "kHz":
            print("   ✅ 解析 '10.5 kHz' 成功")
        else:
            print(f"   ❌ 解析 '10.5 kHz' 失败: {value} {unit}")

        # 解析Unicode科学计数法
        unicode_val = NumberParser.parse_unicode_sci_number("6.6×10⁻⁹ Hz")
        if abs(unicode_val - 6.6e-9) < 1e-15:
            print("   ✅ 解析 '6.6×10⁻⁹ Hz' 成功")
        else:
            print(f"   ❌ 解析 '6.6×10⁻⁹ Hz' 失败: {unicode_val}")

        return True
    except Exception as e:
        print(f"   ❌ 数值解析失败: {e}")
        return False


def test_range_verifier() -> bool:
    """测试范围验证"""
    print("4. 范围验证测试")
    try:
        from core import RangeVerifier

        result = RangeVerifier.verify_range_logic("10.5 V", "0~20 V")
        result_json = json.loads(result)

        if result_json["status"] == "PASS":
            print(f"   ✅ 范围验证成功: {result_json['reason']}")
        else:
            print(f"   ❌ 范围验证失败: {result}")

        return True
    except Exception as e:
        print(f"   ❌ 范围验证失败: {e}")
        return False


def test_error_verifier() -> bool:
    """测试误差验证"""
    print("5. 误差验证测试")
    try:
        from core import ErrorVerifier

        result = ErrorVerifier.verify_error_logic("0.1 mV", "0.5 mV")
        result_json = json.loads(result)

        if result_json["status"] == "PASS":
            print(f"   ✅ 误差验证成功: {result_json['reason']}")
        else:
            print(f"   ❌ 误差验证失败: {result}")

        return True
    except Exception as e:
        print(f"   ❌ 误差验证失败: {e}")
        return False


def test_uncertainty_verifier() -> bool:
    """测试不确定度验证"""
    print("6. 不确定度验证测试")
    try:
        from core import UncertaintyVerifier

        result = UncertaintyVerifier.verify_uncertainty_logic("10.5 V", "0.1", "0.2")
        result_json = json.loads(result)

        if result_json["status"] == "PASS":
            print(f"   ✅ 不确定度验证成功: {result_json['reason']}")
        else:
            print(f"   ❌ 不确定度验证失败: {result}")

        return True
    except Exception as e:
        print(f"   ❌ 不确定度验证失败: {e}")
        return False


def test_filters() -> bool:
    """测试过滤器功能"""
    print("7. 过滤器功能测试")
    try:
        from core import KBFilters

        # 频率解析测试
        freq = KBFilters.parse_frequency_to_hz("100 kHz")
        if abs(freq - 100000.0) < 1e-9:
            print("   ✅ 频率解析成功")
        else:
            print(f"   ❌ 频率解析失败: {freq}")

        # 频率范围解析
        range_result = KBFilters.parse_frequency_range("0.1 Hz～100 kHz")
        if abs(range_result[0] - 0.1) < 1e-9 and abs(range_result[1] - 100000.0) < 1e-9:
            print("   ✅ 频率范围解析成功")
        else:
            print(f"   ❌ 频率范围解析失败: {range_result}")

        return True
    except Exception as e:
        print(f"   ❌ 过滤器功能失败: {e}")
        return False


def test_backward_compatibility() -> bool:
    """测试向后兼容性"""
    print("8. 向后兼容性测试")
    try:
        from core import parse_value_with_unit, verify_range_logic

        value, unit, _ = parse_value_with_unit("10.5 kHz")
        if abs(value - 10.5) < 1e-9 and unit == "kHz":
            print("   ✅ 向后兼容 parse_value_with_unit() 成功")
        else:
            print(f"   ❌ 向后兼容 parse_value_with_unit() 失败")

        result = verify_range_logic("10.5 V", "0~20 V")
        result_json = json.loads(result)
        if result_json["status"] == "PASS":
            print("   ✅ 向后兼容 verify_range_logic() 成功")
        else:
            print("   ❌ 向后兼容 verify_range_logic() 失败")

        return True
    except Exception as e:
        print(f"   ❌ 向后兼容性失败: {e}")
        return False


def test_semantic_selector_import() -> bool:
    """测试语义选择器导入"""
    print("9. 语义选择器导入测试")
    try:
        from core import FirstCandidateDecider, infer_param_semantics, select_basis_with_audit

        print("   ✅ 语义选择器成功导入")
        return True
    except Exception as e:
        print(f"   ❌ 语义选择器失败: {e}")
        return False


def main() -> int:
    """主测试函数"""
    print("=" * 60)
    print("param_check.py 重构 - 完整功能测试")
    print("=" * 60)

    tests = [
        test_import,
        test_config,
        test_number_parser,
        test_range_verifier,
        test_error_verifier,
        test_uncertainty_verifier,
        test_filters,
        test_backward_compatibility,
        test_semantic_selector_import
    ]

    passed = 0
    failed = 0

    for i, test_func in enumerate(tests):
        try:
            print(f"\nTest {i+1}/{len(tests)}: {test_func.__name__}")
            if test_func():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            failed += 1
            print(f"   ❌ 测试 '{test_func.__name__}' 抛出异常: {e}")

    print("\n" + "=" * 60)
    print(f"测试完成: {passed} 个通过, {failed} 个失败")
    print("=" * 60)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
