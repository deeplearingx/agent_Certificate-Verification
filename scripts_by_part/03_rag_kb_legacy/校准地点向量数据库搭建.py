import os
import re
import hashlib
from pathlib import Path
from typing import Dict, Any, List

import pandas as pd
import chromadb
from sentence_transformers import SentenceTransformer


# ===================== 配置 =====================
EXCEL_PATH = "./data/校准地点.xlsx"
##pd.read_excel(..., sheet_name=None) 的含义是：读取所有 Sheet
SHEET_NAME = "Sheet1" # None = 第一个 Sheet
DB_DIR = r"./vector_db/address"
COLLECTION_NAME = "calibration_address"
EMBED_MODEL_PATH = "./models"

BATCH_SIZE = 256


# ===================== 工具函数 =====================
def norm_space(s: str) -> str:
    """规范空白字符"""
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s


def make_doc(row: Dict[str, Any]) -> str:
    """
    构造 document（用于向量检索）
    ⚠️ document = 语义检索用，尽量“像一句话”
    """
    seq = str(row.get("序号", "")).strip()
    addr = norm_space(row.get("校准地址", ""))
    dept = norm_space(row.get("专业室", ""))

    return f"校准地点 {addr}，专业室 {dept}，序号 {seq}"


def make_id(row: Dict[str, Any]) -> str:
    """
    构造稳定唯一 ID
    使用 序号 + 地址 + 专业室 的 hash
    """
    raw = (
        str(row.get("序号", "")).strip()
        + "|"
        + norm_space(row.get("校准地址", ""))
        + "|"
        + norm_space(row.get("专业室", ""))
    )
    h = hashlib.md5(raw.encode("utf-8")).hexdigest()[:16]
    return f"addr_{h}"


def ensure_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    校验并清洗 DataFrame 列
    """
    if not isinstance(df, pd.DataFrame):
        raise TypeError(f"ensure_columns 期望 DataFrame，但收到 {type(df)}")

    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]

    required = ["序号", "校准地址", "专业室"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Excel 缺少必要列 {missing}，当前列={list(df.columns)}")

    # 去掉全空行
    df = df.dropna(how="all")

    # 统一字符串列
    for col in required:
        df[col] = df[col].astype(str).map(norm_space)

    # 校准地址为空的直接丢弃（无检索意义）
    df = df[df["校准地址"] != ""]

    return df


# ===================== 主流程：建库 =====================
def build_chroma_from_excel(
    excel_path: str,
    db_dir: str,
    collection_name: str,
    embed_model_path: str,
    sheet_name=None,
    batch_size: int = 256,
):
    excel_path = str(excel_path)
    if not os.path.exists(excel_path):
        raise FileNotFoundError(f"❌ 找不到 Excel 文件: {excel_path}")

    print(f"📄 读取 Excel: {excel_path}")
    df = pd.read_excel(excel_path, sheet_name=sheet_name, engine="openpyxl")
    df = ensure_columns(df)
    print(f"✅ 清洗完成，共 {len(df)} 行")

    # 初始化 embedding 模型
    print(f"🧠 加载向量模型: {embed_model_path}")
    embedder = SentenceTransformer(embed_model_path)

    # 初始化 ChromaDB
    print(f"🗂️ 连接 ChromaDB: {db_dir}")
    client = chromadb.PersistentClient(path=db_dir)

    # 获取 / 创建集合
    try:
        coll = client.get_collection(collection_name)
        print(f"ℹ️ 使用已存在集合: {collection_name}")
    except Exception:
        coll = client.create_collection(
            name=collection_name,
            metadata={"description": "校准地点 / 专业室 向量检索库"}
        )
        print(f"✅ 创建集合: {collection_name}")

    rows = df.to_dict(orient="records")
    total = len(rows)

    print(f"🚀 开始入库，总记录数 {total}，batch_size={batch_size}")

    for start in range(0, total, batch_size):
        chunk = rows[start:start + batch_size]

        ids: List[str] = []
        docs: List[str] = []
        metas: List[Dict[str, Any]] = []

        for r in chunk:
            ids.append(make_id(r))
            docs.append(make_doc(r))
            metas.append({
                "序号": str(r.get("序号", "")).strip(),
                "校准地址": norm_space(r.get("校准地址", "")),
                "专业室": norm_space(r.get("专业室", "")),
                "source": Path(excel_path).name,
            })

        embeddings = embedder.encode(docs, show_progress_bar=False).tolist()

        coll.upsert(
            ids=ids,
            documents=docs,
            metadatas=metas,
            embeddings=embeddings,
        )

        print(f"   ✅ 已写入 {min(start + batch_size, total)}/{total}")

    print("\n🎉 入库完成")
    print("📦 集合总记录数:", coll.count())


# ===================== 入口 =====================
if __name__ == "__main__":
    build_chroma_from_excel(
        excel_path=EXCEL_PATH,
        db_dir=DB_DIR,
        collection_name=COLLECTION_NAME,
        embed_model_path=EMBED_MODEL_PATH,
        sheet_name=SHEET_NAME,
        batch_size=BATCH_SIZE,
    )
