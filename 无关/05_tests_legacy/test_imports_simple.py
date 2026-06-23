#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试 langchain_app/checks 模块的基本导入功能
不通过 checks/__init__.py 来避免依赖问题
使用 Windows 兼容的字符
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

print("=" * 60)
print("Testing langchain_app/checks module imports")
print("=" * 60)

print("\n1. Testing parameter module submodules...")
try:
    # 测试 parser 模块
    parser_mod = __import__('langchain_app.checks.parameter.parser', fromlist=['*'])
    print("   OK: parameter.parser imported")

    # 测试 validator 模块
    validator_mod = __import__('langchain_app.checks.parameter.validator', fromlist=['*'])
    print("   OK: parameter.validator imported")

    # 测试 semantic 模块
    semantic_mod = __import__('langchain_app.checks.parameter.semantic', fromlist=['*'])
    print("   OK: parameter.semantic imported")

    # 测试 reporter 模块
    reporter_mod = __import__('langchain_app.checks.parameter.reporter', fromlist=['*'])
    print("   OK: parameter.reporter imported")

    # 测试 retrieval 模块
    retrieval_mod = __import__('langchain_app.checks.parameter.retrieval', fromlist=['*'])
    print("   OK: parameter.retrieval imported")

    # 测试 parameter 主模块
    parameter_mod = __import__('langchain_app.checks.parameter.parameter', fromlist=['*'])
    print("   OK: parameter.parameter imported")

    print("\n2. Testing parameter module functions...")
    print("   Testing parser functions:")
    val, unit, orig = parser_mod.parse_value_with_unit("10.5 V")
    print("      parse_value_with_unit('10.5 V'): value=%s, unit=%s, orig=%s" % (val, unit, orig))

    code = parser_mod.norm_code("JJG 237-2010")
    print("      norm_code('JJG 237-2010'): %s" % code)

    basis = parser_mod.extract_basis_code("依据 JJF 1234-2020 进行校准")
    print("      extract_basis_code: %s" % basis)

    print("\n   Testing semantic functions:")
    semantics = semantic_mod.infer_param_semantics("电压", "10.0 V", "0.1 V")
    print("      infer_param_semantics: task_intent=%s, unit_family=%s" % (semantics.task_intent, semantics.unit_family))

    print("\n   Testing validator functions:")
    range_result = validator_mod.verify_range_logic("10.5 V", "0~20 V")
    print("      verify_range_logic: %s..." % range_result[:100])

    error_result = validator_mod.verify_error_logic("0.5", "1.0")
    print("      verify_error_logic: %s..." % error_result[:100])

    uncertainty_result = validator_mod.verify_uncertainty_logic("10.0", "0.5", "0.8")
    print("      verify_uncertainty_logic: %s..." % uncertainty_result[:100])

    print("\n   Testing reporter functions:")
    test_entries = [
        {"参数名称": "电压", "测量值": "10.5", "单位": "V", "范围": "0~20 V", "误差": "0.5", "不确定度": "0.2", "status": "PASS"},
    ]
    table = reporter_mod.build_param_table(test_entries)
    print("      build_param_table: generated %d lines" % len(table.splitlines()))

    print("\nOK: All parameter module submodules test passed!")

except Exception as e:
    print("   ERROR: Parameter module test failed: %s" % e)
    import traceback
    traceback.print_exc()

print("\n3. Testing other individual modules...")
modules_to_test = [
    ("integrity", "check_certificate_integrity"),
    ("environment", "check_environment"),
    ("location", "check_location"),
    ("cycle", "check_cycle_reasonableness"),
]

for module_name, func_name in modules_to_test:
    try:
        module = __import__('langchain_app.checks.' + module_name, fromlist=[func_name])
        func = getattr(module, func_name)
        print("   OK: %s.%s imported successfully" % (module_name, func_name))
    except Exception as e:
        print("   WARNING: %s.%s import has issue: %s" % (module_name, func_name, e))
        print("      Note: This may be due to missing LangChain dependencies")

print("\n" + "=" * 60)
print("Imports test complete!")
print("=" * 60)
