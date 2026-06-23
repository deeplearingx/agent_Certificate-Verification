#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简单测试 langchain_app/checks 包的导入
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

print("=" * 60)
print("简单测试 langchain_app/checks 包的导入")
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
    print("All functions imported successfully!")
except ImportError as e:
    print("Import error:", e)
    import traceback
    print("Traceback:", traceback.format_exc())

print("\n" + "=" * 60)
print("Checking if all modules are present...")
print("=" * 60)

import os
checks_dir = os.path.join(os.path.dirname(__file__), "langchain_app", "checks")
for filename in os.listdir(checks_dir):
    if filename.endswith(".py") and filename != "__init__.py":
        module_name = filename[:-3]
        print(f"- {module_name}.py exists")
