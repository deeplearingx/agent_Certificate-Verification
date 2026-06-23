#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试 langchain_app/checks 包的导入
"""

print("=" * 60)
print("测试 langchain_app/checks 包的导入")
print("=" * 60)

try:
    from langchain_app.checks import (
        check_certificate_integrity,
        check_environment,
        check_location,
        check_cycle_reasonableness,
        info_check_wrapper,
        environment_check_wrapper,
        location_check_wrapper,
        cycle_check_wrapper,
    )
    print("✅ 所有函数导入成功！")
    print(f"   - check_certificate_integrity: {check_certificate_integrity}")
    print(f"   - check_environment: {check_environment}")
    print(f"   - check_location: {check_location}")
    print(f"   - check_cycle_reasonableness: {check_cycle_reasonableness}")
    print(f"   - info_check_wrapper: {info_check_wrapper}")
    print(f"   - environment_check_wrapper: {environment_check_wrapper}")
    print(f"   - location_check_wrapper: {location_check_wrapper}")
    print(f"   - cycle_check_wrapper: {cycle_check_wrapper}")
except ImportError as e:
    print(f"❌ 导入失败: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("测试单个模块的导入")
print("=" * 60)

modules_to_test = [
    ("integrity", "langchain_app.checks.integrity"),
    ("environment", "langchain_app.checks.environment"),
    ("location", "langchain_app.checks.location"),
    ("cycle", "langchain_app.checks.cycle"),
]

for name, module_path in modules_to_test:
    try:
        __import__(module_path)
        print(f"✅ {name} 模块导入成功")
    except ImportError as e:
        print(f"❌ {name} 模块导入失败: {e}")
        import traceback
        traceback.print_exc()

print("\n" + "=" * 60)
print("测试完成！")
print("=" * 60)
