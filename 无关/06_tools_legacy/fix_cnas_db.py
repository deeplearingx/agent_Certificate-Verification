#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修复或重建 CNAS 向量数据库的脚本。
如果 ChromaDB 索引损坏，将备份旧数据并重新构建新索引。
"""

import os
import sys
import json
import re
import shutil
import time
from pathlib import Path
from collections import Counter

# 设置控制台编码
try:
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
except:
    pass

# 添加项目根目录到系统路径
sys.path.append(str(Path(__file__).parent.resolve()))

from kb.chroma_client import create_persistent_client, try_repair_collection
from config.settings import get_app_config


def _find_default_source_text() -> Path:
    base = Path(__file__).parent / "CNAS解析" / "output"
    candidates = sorted(base.glob("*时间频率*.txt"))
    if candidates:
        return candidates[0]
    candidates = sorted(base.glob("*.txt"))
    if candidates:
        return candidates[0]
    raise FileNotFoundError(f"未找到 CNAS 原始文本文件: {base}")


def _extract_range_text(line: str) -> str:
    for prefix in ("测量范围是“", '测量范围是"'):
        if prefix in line:
            tail = line.split(prefix, 1)[1]
            for suffix in ("”", '"'):
                if suffix in tail:
                    return tail.split(suffix, 1)[0].strip()
    return ""


def _extract_measured_text(line: str) -> str:
    pattern = re.compile(r"对于被测量[“\"](?P<meas>.+?)[”\"]")
    match = pattern.search(line)
    return match.group("meas").strip() if match else ""


def _old_parser_prefix(range_text: str) -> str:
    if not range_text:
        return ""
    for separator in ("，", ",", "；", ";", "。"):
        pos = range_text.find(separator)
        if pos != -1:
            return range_text[:pos].strip()
    return range_text.strip()


def audit_cnas_source(source_file: str | None = None, output_file: str | None = None, sample_size: int = 40) -> bool:
    """
    扫描原始 CNAS 文本，检查是否存在会被旧解析器截断的范围字段。
    """
    try:
        source_path = Path(source_file).expanduser().resolve() if source_file else _find_default_source_text().resolve()
    except Exception as exc:
        print(f"[ERROR] 找不到原始 CNAS 文本: {exc}")
        return False

    if not source_path.exists():
        print(f"[ERROR] 原始文本不存在: {source_path}")
        return False

    text = source_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    rows = []

    for idx, line in enumerate(lines, 1):
        if "对于被测量" not in line or "测量范围是" not in line:
            continue
        measured = _extract_measured_text(line)
        range_text = _extract_range_text(line)
        if not measured or not range_text:
            continue

        old_prefix = _old_parser_prefix(range_text)
        risk = old_prefix != range_text
        if not risk:
            continue

        separators = [sep for sep in ("，", ",", "；", ";", "。") if sep in range_text]
        rows.append({
            "line_no": idx,
            "measured": measured,
            "range_text": range_text,
            "old_prefix": old_prefix,
            "separators": separators,
            "raw_line": line,
        })

    if not rows:
        print(f"[AUDIT] 未发现疑似截断风险的条目。来源: {source_path}")
        return True

    counter = Counter()
    for row in rows:
        for sep in row["separators"]:
            counter[sep] += 1

    print("[AUDIT] CNAS 范围字段截断审计")
    print("=" * 60)
    print(f"[SRC]  {source_path}")
    print(f"[STAT] 可疑条目: {len(rows)}")
    print("[STAT] 分隔符命中:")
    for sep, count in counter.most_common():
        printable = sep.encode("unicode_escape").decode()
        print(f"  - {printable}: {count}")

    print("\n[SAMPLE] 前 {0} 条可疑样本:".format(min(sample_size, len(rows))))
    for row in rows[:sample_size]:
        print(
            f"- L{row['line_no']}: {row['measured']} | {row['range_text']} | old_prefix={row['old_prefix']}"
        )

    payload = {
        "source_file": str(source_path),
        "total_suspicious": len(rows),
        "separator_counts": dict(counter),
        "samples": rows[:sample_size],
    }

    if output_file:
        out_path = Path(output_file).expanduser().resolve()
    else:
        out_path = Path(__file__).parent / "audit_reports" / "cnas_range_audit.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[OK] 审计结果已保存: {out_path}")
    return True

def main():
    print("CNAS 向量数据库修复工具")
    print("=" * 50)

    # 获取配置
    config = get_app_config()
    cnas_db_dir = config.cnas_db_dir
    collection_name = config.cnas_collection

    print(f"\n[DIR] 数据库路径: {cnas_db_dir}")
    print(f"[TAG]  集合名称: {collection_name}")

    # 检查数据库是否存在
    db_path = Path(cnas_db_dir)
    if not db_path.exists():
        print("\n[ERROR] 数据库目录不存在！")
        return False

    print("\n[TEST] 第一步：检查数据库状态...")

    # 尝试修复集合
    if try_repair_collection(cnas_db_dir, collection_name):
        print("\n[OK] 数据库状态良好！")
    else:
        print("\n[WARN]  数据库需要重建...")

    # 检查数据库是否包含数据
    try:
        client = create_persistent_client(cnas_db_dir)
        collection = client.get_collection(collection_name)
        count = collection.count()

        if count == 0:
            print("\n[NEW] 数据库是空的，需要重新构建！")
        else:
            print(f"\n[STATS] 数据库包含 {count} 个文档")

            # 验证查询功能
            print("\n[SEARCH] 测试简单查询...")
            from sentence_transformers import SentenceTransformer
            try:
                embedder = SentenceTransformer(config.embed_model_path)
                test_emb = embedder.encode(["测试查询"]).tolist()
                results = collection.query(
                    query_embeddings=test_emb,
                    n_results=3
                )
                print(f"[OK] 查询成功，返回 {len(results['documents'][0])} 个结果")

                if len(results['documents'][0]) > 0:
                    print(f"[DOC] 第一个文档: {results['documents'][0][0][:100]}...")

            except Exception as e:
                print(f"[ERROR] 查询测试失败: {e}")
                return False

    except Exception as e:
        print(f"[ERROR] 数据库访问错误: {e}")
        return False

    print("\n" + "=" * 50)
    print("[OK] 修复过程完成！")
    return True

def rebuild_cnas_db():
    """
    调用 CNSA数据库搭建.py 来重新构建 CNAS 向量数据库
    """
    print("\n[REBUILD] 开始重新构建 CNAS 向量数据库...")

    try:
        # 检查 CNSA数据库搭建.py 是否存在
        builder_file = Path(__file__).parent / "CNSA数据库搭建.py"
        if not builder_file.exists():
            print("[ERROR] 找不到 CNSA数据库搭建.py 文件")
            return False

        # 执行 CNSA数据库搭建.py 脚本来重新构建数据库
        import subprocess
        result = subprocess.run([
            sys.executable,
            str(builder_file),
        ], capture_output=True, text=True, encoding="utf-8")

        if result.returncode == 0:
            print("[OK] 数据库构建成功")
            if result.stdout:
                print("[LOG] 输出信息:")
                print(result.stdout)
            return True
        else:
            print(f"[ERROR] 数据库构建失败 (退出码: {result.returncode})")
            if result.stderr:
                print("[ERROR] 错误信息:")
                print(result.stderr)
            return False

    except Exception as e:
        print(f"[ERROR] 执行失败: {e}")
        return False


if __name__ == "__main__":
    # 解析命令行参数
    import argparse
    parser = argparse.ArgumentParser(description="CNAS 向量数据库修复工具")
    parser.add_argument("--rebuild", action="store_true", help="强制重新构建数据库")
    parser.add_argument("--audit", action="store_true", help="审计原始 CNAS 文本中的范围截断风险")
    parser.add_argument("--source", type=str, default=None, help="指定原始 CNAS 文本路径")
    parser.add_argument("--output", type=str, default=None, help="审计结果输出路径")
    parser.add_argument("--sample-size", type=int, default=40, help="审计报告样本条数")
    args = parser.parse_args()

    if args.audit:
        success = audit_cnas_source(args.source, args.output, args.sample_size)
    elif args.rebuild:
        success = rebuild_cnas_db()
    else:
        success = main()

    sys.exit(0 if success else 1)
