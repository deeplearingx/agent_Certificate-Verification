#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
bge-m3 模型下载脚本 - 多种下载方式
"""

import os
import sys
from pathlib import Path


def download_method_1():
    """方法1: 使用 sentence_transformers 直接下载（最简单）"""
    print("=" * 60)
    print("方法1: 使用 sentence_transformers 下载")
    print("=" * 60)
    try:
        from sentence_transformers import SentenceTransformer
        print("正在下载/加载模型...")
        model = SentenceTransformer('BAAI/bge-m3')
        print(f"✓ 模型加载成功!")
        print(f"  模型保存在: {model.model_card_data.model_name_or_path}")
        return True
    except Exception as e:
        print(f"✗ 方法1失败: {e}")
        return False


def download_method_2():
    """方法2: 使用 transformers 下载"""
    print("\n" + "=" * 60)
    print("方法2: 使用 transformers 下载")
    print("=" * 60)
    try:
        from transformers import AutoModel, AutoTokenizer
        model_name = "BAAI/bge-m3"
        local_dir = Path("./models/BAAI/bge-m3")
        local_dir.mkdir(parents=True, exist_ok=True)

        print(f"正在下载模型到: {local_dir}")
        model = AutoModel.from_pretrained(model_name, cache_dir="./models")
        tokenizer = AutoTokenizer.from_pretrained(model_name, cache_dir="./models")

        model.save_pretrained(local_dir)
        tokenizer.save_pretrained(local_dir)
        print(f"✓ 模型已保存到: {local_dir}")
        return True
    except Exception as e:
        print(f"✗ 方法2失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def download_method_3():
    """方法3: 使用 huggingface_hub snapshot_download"""
    print("\n" + "=" * 60)
    print("方法3: 使用 huggingface_hub 快照下载")
    print("=" * 60)
    try:
        from huggingface_hub import snapshot_download
        local_dir = Path("./models/BAAI/bge-m3")

        print(f"正在下载模型到: {local_dir}")
        model_path = snapshot_download(
            repo_id="BAAI/bge-m3",
            local_dir=str(local_dir),
            local_dir_use_symlinks=False
        )
        print(f"✓ 模型已下载到: {model_path}")
        return True
    except Exception as e:
        print(f"✗ 方法3失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def check_model_exists():
    """检查模型是否已存在"""
    model_paths = [
        Path("./models/BAAI/bge-m3"),
        Path("./models") / "BAAI" / "bge-m3",
    ]

    # 检查 sentence-transformers 缓存
    try:
        from sentence_transformers import SentenceTransformer
        import transformers
        cache_dir = transformers.utils.hub.get_cache_dir()
        st_cache = Path.home() / ".cache" / "torch" / "sentence_transformers"
        model_paths.append(st_cache)
    except:
        pass

    for path in model_paths:
        if path.exists() and any(path.iterdir()):
            print(f"\n✓ 发现模型目录: {path}")
            return True
    return False


def main():
    print("bge-m3 模型下载工具")
    print("=" * 60)

    # 先检查是否已存在
    if check_model_exists():
        print("\n模型已存在，无需重新下载！")
        return

    # 尝试各种下载方法
    methods = [
        download_method_1,
        download_method_2,
        download_method_3,
    ]

    success = False
    for method in methods:
        if method():
            success = True
            break

    if success:
        print("\n" + "=" * 60)
        print("✓ 模型下载成功！")
        print("=" * 60)
    else:
        print("\n" + "=" * 60)
        print("✗ 所有方法都失败了")
        print("\n备用方案：")
        print("1. 手动从 ModelScope 下载: https://www.modelscope.cn/models/BAAI/bge-m3")
        print("2. 手动从 HuggingFace 下载: https://huggingface.co/BAAI/bge-m3")
        print("3. 修改 app.py 中的 EMBED_MODEL_PATH 指向已有模型")
        print("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    main()
