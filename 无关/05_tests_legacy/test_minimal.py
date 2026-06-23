#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
最小测试 - 验证重构是否成功
"""

import json

def main():
    print("=" * 60)
    print("Param Check Refactoring - Minimal Test")
    print("=" * 60)

    # Test 1: Import modules
    try:
        from core import (
            Config, NumberParser, UnitConverter,
            RangeVerifier, ErrorVerifier, UncertaintyVerifier,
            KBFilters, TableProcessor, ReportGenerator
        )
        print("[OK] All modules imported successfully")
    except Exception as e:
        print(f"[FAIL] Import failed: {e}")
        return 1

    # Test 2: Parse value with unit
    try:
        value, unit, _ = NumberParser.parse_value_with_unit("10.5 kHz")
        if abs(value - 10.5) < 1e-9 and unit == "kHz":
            print(f"[OK] Parse '10.5 kHz' -> {value} {unit}")
        else:
            print(f"[FAIL] Parse '10.5 kHz' failed")
    except Exception as e:
        print(f"[FAIL] Parse test failed: {e}")

    # Test 3: Verify range
    try:
        result = RangeVerifier.verify_range_logic("10.5 V", "0~20 V")
        result_json = json.loads(result)
        if result_json["status"] == "PASS":
            print(f"[OK] Range verify: {result_json['reason']}")
        else:
            print(f"[FAIL] Range verify failed")
    except Exception as e:
        print(f"[FAIL] Range verify test failed: {e}")

    # Test 4: Verify error
    try:
        result = ErrorVerifier.verify_error_logic("0.1 mV", "0.5 mV")
        result_json = json.loads(result)
        if result_json["status"] == "PASS":
            print(f"[OK] Error verify: {result_json['reason']}")
        else:
            print(f"[FAIL] Error verify failed")
    except Exception as e:
        print(f"[FAIL] Error verify test failed: {e}")

    # Test 5: Verify uncertainty
    try:
        result = UncertaintyVerifier.verify_uncertainty_logic("10.5 V", "0.1", "0.2")
        result_json = json.loads(result)
        if result_json["status"] == "PASS":
            print(f"[OK] Uncertainty verify: {result_json['reason']}")
        else:
            print(f"[FAIL] Uncertainty verify failed")
    except Exception as e:
        print(f"[FAIL] Uncertainty verify test failed: {e}")

    # Test 6: Frequency parsing
    try:
        freq = KBFilters.parse_frequency_to_hz("100 kHz")
        if abs(freq - 100000.0) < 1e-9:
            print(f"[OK] Frequency parse: 100 kHz -> {freq} Hz")
        else:
            print(f"[FAIL] Frequency parse failed: {freq}")
    except Exception as e:
        print(f"[FAIL] Frequency parse test failed: {e}")

    # Test 7: Backward compatibility
    try:
        from core import parse_value_with_unit, verify_range_logic

        value, unit, _ = parse_value_with_unit("10.5 kHz")
        if abs(value - 10.5) < 1e-9 and unit == "kHz":
            print("[OK] Backward compatible parse_value_with_unit works")
        else:
            print("[FAIL] Backward compatible parse_value_with_unit failed")

        result = verify_range_logic("10.5 V", "0~20 V")
        result_json = json.loads(result)
        if result_json["status"] == "PASS":
            print("[OK] Backward compatible verify_range_logic works")
        else:
            print("[FAIL] Backward compatible verify_range_logic failed")
    except Exception as e:
        print(f"[FAIL] Backward compatibility test failed: {e}")

    print("\n" + "=" * 60)
    print("Minimal test completed!")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    exit(main())
