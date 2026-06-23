#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
直接测试 parameter 子模块，不通过 checks/__init__.py 来避免依赖问题
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

print("=" * 60)
print("Testing parameter module directly")
print("=" * 60)

parameter_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), "langchain_app", "checks", "parameter")

# 测试 parser.py
print("\n1. Testing parser module...")
parser_path = os.path.join(parameter_dir, "parser.py")
try:
    import importlib.util
    spec = importlib.util.spec_from_file_location("langchain_app.checks.parameter.parser", parser_path)
    parser_mod = importlib.util.module_from_spec(spec)
    sys.modules["langchain_app.checks.parameter.parser"] = parser_mod
    spec.loader.exec_module(parser_mod)
    print("   OK: parser module imported")

    # 测试 parser 函数
    print("   Testing parse_value_with_unit:")
    val, unit, orig = parser_mod.parse_value_with_unit("10.5 V")
    print("      parse_value_with_unit('10.5 V'): value=%s, unit=%s, orig=%s" % (val, unit, orig))

    print("   Testing norm_code:")
    code = parser_mod.norm_code("JJG 237-2010")
    print("      norm_code('JJG 237-2010'): %s" % code)

    print("   Testing extract_basis_code:")
    basis = parser_mod.extract_basis_code("依据 JJF 1234-2020 进行校准")
    print("      extract_basis_code: %s" % basis)

except Exception as e:
    print("   ERROR: Parser module test failed: %s" % e)
    import traceback
    print("   Traceback:\n%s" % traceback.format_exc())

# 测试 validator.py
print("\n2. Testing validator module...")
validator_path = os.path.join(parameter_dir, "validator.py")
try:
    import importlib.util
    spec = importlib.util.spec_from_file_location("langchain_app.checks.parameter.validator", validator_path)
    validator_mod = importlib.util.module_from_spec(spec)
    sys.modules["langchain_app.checks.parameter.validator"] = validator_mod
    spec.loader.exec_module(validator_mod)
    print("   OK: validator module imported")

    # 测试 validator 函数
    print("   Testing verify_range_logic:")
    range_result = validator_mod.verify_range_logic("10.5 V", "0~20 V")
    print("      verify_range_logic: %s..." % range_result[:100])

    print("   Testing verify_error_logic:")
    error_result = validator_mod.verify_error_logic("0.5", "1.0")
    print("      verify_error_logic: %s..." % error_result[:100])

    print("   Testing verify_uncertainty_logic:")
    u_result = validator_mod.verify_uncertainty_logic("10.0", "0.5", "0.8")
    print("      verify_uncertainty_logic: %s..." % u_result[:100])

except Exception as e:
    print("   ERROR: Validator module test failed: %s" % e)
    import traceback
    print("   Traceback:\n%s" % traceback.format_exc())

# 测试 semantic.py
print("\n3. Testing semantic module...")
semantic_path = os.path.join(parameter_dir, "semantic.py")
try:
    import importlib.util
    spec = importlib.util.spec_from_file_location("langchain_app.checks.parameter.semantic", semantic_path)
    semantic_mod = importlib.util.module_from_spec(spec)
    sys.modules["langchain_app.checks.parameter.semantic"] = semantic_mod
    spec.loader.exec_module(semantic_mod)
    print("   OK: semantic module imported")

    # 测试 semantic 函数
    print("   Testing infer_param_semantics:")
    semantics = semantic_mod.infer_param_semantics("电压", "10.0 V", "0.1 V")
    print("      infer_param_semantics: task_intent=%s, unit_family=%s" % (semantics.task_intent, semantics.unit_family))

    print("   Testing infer_uncertainty_kind:")
    kind = semantic_mod.infer_uncertainty_kind("0.5%")
    print("      infer_uncertainty_kind('0.5%'): %s" % kind)

except Exception as e:
    print("   ERROR: Semantic module test failed: %s" % e)
    import traceback
    print("   Traceback:\n%s" % traceback.format_exc())

# 测试 reporter.py
print("\n4. Testing reporter module...")
reporter_path = os.path.join(parameter_dir, "reporter.py")
try:
    import importlib.util
    spec = importlib.util.spec_from_file_location("langchain_app.checks.parameter.reporter", reporter_path)
    reporter_mod = importlib.util.module_from_spec(spec)
    sys.modules["langchain_app.checks.parameter.reporter"] = reporter_mod
    spec.loader.exec_module(reporter_mod)
    print("   OK: reporter module imported")

    # 测试 reporter 函数
    print("   Testing build_param_table:")
    test_entries = [
        {"参数名称": "电压", "测量值": "10.5", "单位": "V", "范围": "0~20 V", "误差": "0.5", "不确定度": "0.2", "status": "PASS"},
    ]
    table = reporter_mod.build_param_table(test_entries)
    print("      build_param_table: generated %d lines" % len(table.splitlines()))

except Exception as e:
    print("   ERROR: Reporter module test failed: %s" % e)
    import traceback
    print("   Traceback:\n%s" % traceback.format_exc())

# 测试 retrieval.py
print("\n5. Testing retrieval module...")
retrieval_path = os.path.join(parameter_dir, "retrieval.py")
try:
    import importlib.util
    spec = importlib.util.spec_from_file_location("langchain_app.checks.parameter.retrieval", retrieval_path)
    retrieval_mod = importlib.util.module_from_spec(spec)
    sys.modules["langchain_app.checks.parameter.retrieval"] = retrieval_mod
    spec.loader.exec_module(retrieval_mod)
    print("   OK: retrieval module imported")

except Exception as e:
    print("   ERROR: Retrieval module test failed: %s" % e)
    import traceback
    print("   Traceback:\n%s" % traceback.format_exc())

print("\n" + "=" * 60)
print("Test complete!")
print("=" * 60)
