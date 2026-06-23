# import re
# from typing import List, Dict, Any
# import chromadb
# from sentence_transformers import SentenceTransformer
#
#
# # ---------------------------
# # 解析 KB 文本段落
# # ---------------------------
# def pick_first(text: str, *patterns: str):
#     if not text:
#         return None
#     for p in patterns:
#         m = re.search(p, text, flags=re.IGNORECASE)
#         if m:
#             return m.group(1).strip()
#     return None
#
#
# def detect_uncertainty_info(text: str) -> Dict[str, Any]:
#     info = {"type": None, "value": None, "raw": None}
#     if not text:
#         return info
#
#     m_abs = re.search(r"\bU\s*=\s*([-\d\.]+)", text, flags=re.IGNORECASE)
#     m_rel = re.search(r"\bU\s*rel\s*=\s*([\d\.]+)\s*%", text, flags=re.IGNORECASE)
#
#     if m_abs:
#         return {"type": "U", "value": float(m_abs.group(1)), "raw": m_abs.group(0)}
#     if m_rel:
#         return {"type": "Urel", "value": float(m_rel.group(1)) / 100.0, "raw": m_rel.group(0)}
#
#     return info
#
#
# def parse_kb_entry(doc: str, meta: Dict[str, Any]) -> Dict[str, Any]:
#     instr_name = meta.get("仪器名称") or pick_first(doc, r"仪器名称[:：]\s*([^\n，。]+)")
#     standard = meta.get("校准依据") or pick_first(doc, r"(JJF[0-9\-]+|JJG[0-9\-]+)")
#     meas = meta.get("被测量")
#     rng = meta.get("测量范围")
#     uncert = meta.get("不确定度")
#
#     uncertainty = detect_uncertainty_info(doc)
#
#     return {
#         "仪器名称": instr_name,
#
#         "校准依据": standard,
#         "被测量": meas,
#         "测量范围": rng,
#         "不确定度": uncert,
#
#     }
#
#
# # ---------------------------
# # ⭐ 主函数：依据检索
# # ---------------------------
# def query_by_instrument_and_basis(
#     chroma_dir: str,
#     collection: str,
#     embed_model_path: str,
#     instrument_name: str,
#     criterion: str,
#     topk: int = 10,
# ) -> List[Dict[str, Any]]:
#     """
#     根据“仪器名称 + 依据编号”检索 Chroma 向量数据库，返回解析后的 KB 条目。
#     """
#
#     print("\n=== 【开始依据检索】 ===")
#     print(f"仪器名称: {instrument_name}")
#     print(f"依据输入: {criterion}")
#
#     # 提取依据编号（如 JJF1059-2012）
#     m = re.search(r"(JJF\s*\d{3,5}[-–－]?\d{0,4}|JJG\s*\d{3,5}[-–－]?\d{0,4})",
#                   criterion, flags=re.IGNORECASE)
#
#     basis_code = m.group(1).strip().replace(" ", "") if m else ""
#     print(f"➡️ 提取依据编号: {basis_code}")
#
#     query_text = f"{instrument_name} {basis_code}".strip()
#     print(f"➡️ 检索文本: {query_text}")
#
#     # --- 加载模型与集合 ---
#     embedder = SentenceTransformer(embed_model_path)
#     client = chromadb.PersistentClient(path=chroma_dir)
#     coll = client.get_collection(collection)
#
#     # --- 向量化查询 ---
#     q_emb = embedder.encode([query_text]).tolist()
#
#     # --- 执行检索 ---
#     res = coll.query(query_embeddings=q_emb, n_results=topk)
#
#     docs = res.get("documents", [[]])[0]
#     metas = res.get("metadatas", [[]])[0]
#
#     print(f"检索结果数量: {len(docs)}")
#
#     # --- 解析 KB 文本 ---
#     entries = []
#     for d, m in zip(docs, metas):
#         entries.append(parse_kb_entry(d, m))
#
#     return entries
#
#
# # ---------------------------
# # 🔧 示例调用
# # ---------------------------
# if __name__ == "__main__":
#     results = query_by_instrument_and_basis(
#         chroma_dir="./vector_db/cnas_calibration",
#         collection="calibration_data",
#         embed_model_path=r"D:\workspace\ai_learning\pythonProject\models\BAAI\bge-m3",
#         instrument_name="函数发生器",
#         criterion="JJG 840-2015 函数发生器检定规程",
#         topk=5
#     )
#
#     print("\n=== 检索结果（结构化） ===")
#     for i, e in enumerate(results, 1):
#         print(f"\n--- #{i} ---")
#         print(e)





import re
from typing import List, Dict, Any
import chromadb
from sentence_transformers import SentenceTransformer
import json

# ---------------------------
# 不确定度解析工具
# ---------------------------
def detect_uncertainty_info(text: str) -> str:
    if not text:
        return None
    m_abs = re.search(r"\bU\s*=\s*([-\d\.]+)", text, flags=re.IGNORECASE)
    m_rel = re.search(r"\bU\s*rel\s*=\s*([\d\.]+)\s*%", text, flags=re.IGNORECASE)
    if m_abs:
        return f"U={m_abs.group(1)}"
    if m_rel:
        return f"Urel={float(m_rel.group(1))/100:.4f}"
    return None

# ---------------------------
# 文本测量条目解析
# ---------------------------
def parse_measurements_from_text(text: str) -> List[Dict[str, Any]]:
    """
    支持格式：
    被测量：XXX 测量范围：YYY 不确定度：ZZZ
    """
    pattern = r"被测量[:：]\s*(.+?)\s*测量范围[:：]\s*(.+?)(?:\s*不确定度[:：]\s*(.+?))?(?:$|\n)"
    matches = re.findall(pattern, text)
    measurements = []
    for meas, rng, uncert_raw in matches:
        measurements.append({
            "被测量": meas.strip(),
            "测量范围": rng.strip(),
            "扩展不确定度": detect_uncertainty_info(uncert_raw)
        })
    return measurements

# ---------------------------
# 主检索函数
# ---------------------------
def query_all_measurements_by_basis(
    chroma_dir: str,
    collection: str,
    embed_model_path: str,
    instrument_name: str,
    criterion: str,
    topk: int = 50,
) -> Dict[str, Any]:
    # 初始化
    embedder = SentenceTransformer(embed_model_path)
    client = chromadb.PersistentClient(path=chroma_dir)
    coll = client.get_collection(collection)

    # 构建查询向量
    query_text = f"{instrument_name} {criterion}".strip()
    q_emb = embedder.encode([query_text]).tolist()

    # 执行向量检索
    res = coll.query(query_embeddings=q_emb, n_results=topk)
    docs = res.get("documents", [[]])[0]
    metas = res.get("metadatas", [[]])[0]

    print(f"检索到文档数量: {len(docs)}")

    # 过滤 JJG 840 并汇总测量条目
    all_measurements = []
    for d, m in zip(docs, metas):
        basis_in_doc = m.get("校准依据") or ""
        basis_code_match = re.search(r"(JJF[0-9\-]+|JJG\s*[0-9\-]+)", basis_in_doc, flags=re.IGNORECASE)
        basis_code = basis_code_match.group(1).replace(" ", "") if basis_code_match else ""
        if "JJG840" in basis_code.upper():
            measurements = parse_measurements_from_text(d)
            if measurements:
                all_measurements.extend(measurements)
            print(f"✅ 文档匹配: {basis_in_doc}")
        else:
            print(f"❌ 文档过滤: {basis_in_doc}")

    # 返回汇总结构
    result = {
        "仪器名称": instrument_name,
        "校准依据":criterion,
        "测量条目": all_measurements
    }
    return result

# ---------------------------
# 示例调用
# ---------------------------
if __name__ == "__main__":
    res = query_all_measurements_by_basis(
        chroma_dir="./vector_db/cnas_calibration",
        collection="calibration_data",
        embed_model_path=r"D:\workspace\ai_learning\pythonProject\models\BAAI\bge-m3",
        instrument_name="函数信号发生器",
        criterion="JJG 840 函数发生器检定规程",
        topk=50
    )

    print("\n=== 最终检索结果（结构化） ===")
    print(json.dumps(res, ensure_ascii=False, indent=2))
