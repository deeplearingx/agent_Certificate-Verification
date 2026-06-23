#!/usr/bin/env python
# -*- coding: utf-8 -*-

import json
import sys
import os
sys.path.insert(0, os.path.abspath('.'))

from md_parser_no_llm import parse_md_to_json

def test_parse():
    md_file = "local_md/1GA25016225-0002.md"
    output_json = "local_json/test_1GA25016225-0002.json"

    print(f"正在解析: {md_file}")

    try:
        parse_result = parse_md_to_json(md_file)

        print("解析成功!")
        print()
        print("生成的JSON结构:")
        print(json.dumps(parse_result, indent=4, ensure_ascii=False))

        # 保存到临时文件用于验证
        with open(output_json, 'w', encoding='utf-8') as f:
            json.dump(parse_result, f, indent=4, ensure_ascii=False)

        print()
        print(f"JSON文件已保存到: {output_json}")

        # 检查是否包含校准地点字段
        if parse_result.get('properties'):
            props = parse_result['properties']['证书列表']['items']['properties']

            print()
            print("--- 解析结果检查 ---")
            print(f"委托单位: {props.get('委托单位')}")
            print(f"湿度: {props.get('湿度')}")
            print(f"校准地点: {props.get('校准地点')}")
            print(f"相对湿度: {props.get('相对湿度')}")
            print()

            if props.get('校准地点'):
                print("✅ 校准地点字段提取成功!")
                print(f"   值: {props['校准地点']}")
            else:
                print("❌ 校准地点字段提取失败!")

            if props.get('湿度') and props['湿度'] != 'N/A':
                print("✅ 湿度字段提取成功!")
                print(f"   值: {props['湿度']}")

            if props.get('委托单位') and props['委托单位'] != 'N/A':
                print("✅ 委托单位字段提取成功!")
                print(f"   值: {props['委托单位']}")

    except Exception as e:
        print(f"解析失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_parse()
