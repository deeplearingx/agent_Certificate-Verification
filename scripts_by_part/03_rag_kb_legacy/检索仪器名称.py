import re
from typing import Any, Dict, List, Optional, Tuple
import chromadb
from sentence_transformers import SentenceTransformer


# ===================== 配置 =====================
DB_DIR = r"./vector_db/cnas_calibration"
COLLECTION = "calibration_data"
EMBED_MODEL_PATH = r"D:\workspace\ai_learning\pythonProject\models\BAAI\bge-m3"


# ===================== 规程代号解析/归一化 =====================
def extract_basis_code(text: str) -> Optional[str]:
    """
    从任意文本中提取规程代号，兼容：
    - JJG 959 / JJG959 / JJG 959-2010
    - JJG(军工) 172 / JJG（电子）306001
    - JJF xxxx / GJB xxxx
    返回标准形态：'JJG 959'
    """
    if not text:
        return None
    s = str(text)
    m = re.search(
        r"\b(JJ[GF]|GJB)\s*(?:[\(（][^)\）]*[\)）])?\s*(\d+)(?:\s*-\s*\d{4})?\b",
        s,
        flags=re.IGNORECASE,
    )
    if not m:
        return None
    return f"{m.group(1).upper()} {m.group(2)}"


def norm_code(code: str) -> str:
    """'JJG 959' -> 'JJG959'；用于严格相等判断"""
    code = (code or "").strip()
    m = re.search(r"\b(JJ[GF]|GJB)\s*(\d+)", code, flags=re.IGNORECASE)
    if m:
        return f"{m.group(1).upper()}{m.group(2)}"
    return re.sub(r"\s+", "", code).upper()


# ===================== 字段提取 =====================
def extract_instrument_name(doc: str, meta: Dict[str, Any]) -> str:
    meta = meta or {}
    name = meta.get("仪器名称") or meta.get("INSTRUMENT_NAME")
    if name and str(name).strip():
        return str(name).strip()

    m = re.search(r"仪器名称[：:]\s*(.+?)(?:[。；;\n]|$)", doc or "")
    return m.group(1).strip() if m else "N/A"


def extract_file_code(doc: str, meta: Dict[str, Any]) -> str:
    """
    从一条 KB 记录中提取规程代号（用于 strict filter）。
    优先从 meta 的多个字段找，因为你库里字段很丰富。
    """
    meta = meta or {}

    for k in ["校准依据", "raw_block", "_node_content", "ref_doc_id", "document_id", "doc_id"]:
        v = meta.get(k)
        b = extract_basis_code(v) if v else None
        if b:
            return b

    b2 = extract_basis_code(doc or "")
    return b2 if b2 else "未知规程"


def has_star_mark(name: str) -> bool:
    """判断仪器名称是否带星号（半角* / 全角＊）"""
    return ("*" in (name or "")) or ("＊" in (name or ""))


# ===================== 通用检索主函数 =====================
def search_instruments_by_basis_code(
    basis_or_criterion: str,
    topk: int = 50,
    use_where_document: bool = True,
    where_variants: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    通用入口：输入规程号或依据文本（如 'JJG 959' 或 'JJG 959-2010 xxx规程'），输出匹配的仪器名列表，并标注是否带*。

    核心策略：
    1) 解析规程代号 basis（如 'JJG 959'）
    2) （强烈推荐）where_document 做“文本硬过滤”：只让包含该规程号的记录进入候选集
    3) 在候选集上做向量相似度排序
    4) strict filter：再次用 norm_code(file_code)==norm_code(basis) 兜底

    返回结构：
    {
      "basis": "JJG 959",
      "basis_norm": "JJG959",
      "hits_total": 3,            # 过滤后候选命中数（去重前）
      "instruments": [
         {"instrument_name": "*光时域反射计", "has_star": True, "file_code": "JJG 959", "distance": 0.12, "kb_basis_text": "..."},
         ...
      ]
    }
    """
    basis = extract_basis_code(basis_or_criterion)
    if not basis:
        raise ValueError(f"无法从输入中解析规程代号：{basis_or_criterion}")

    basis_norm = norm_code(basis)

    client = chromadb.PersistentClient(path=DB_DIR)
    coll = client.get_collection(COLLECTION)
    embedder = SentenceTransformer(EMBED_MODEL_PATH)

    # 让 query 更像“人话”：basis + 原始输入（如果你只给了JJG 959，这里也不会变差）
    query_text = f"{basis} {basis_or_criterion}".strip()
    q_emb = embedder.encode([query_text]).tolist()

    # where_document：优先用最贴近库里写法的变体（默认就是 'JJG 959'）
    if where_variants is None:
        where_variants = [
            basis,                 # "JJG 959"  ←你库里就是这种
            basis_norm,            # "JJG959"   ←防止某些文档无空格
            basis.replace(" ", ""),# "JJG959"
        ]

    # 先尝试 where_document 硬过滤；如果某次变体能命中，就用它
    last_res = None
    used_where = None

    if use_where_document:
        for w in where_variants:
            try:
                res = coll.query(
                    query_embeddings=q_emb,
                    n_results=topk,
                    include=["documents", "metadatas", "distances"],
                    where_document={"$contains": w},
                )
                docs = res.get("documents", [[]])[0] if res.get("documents") else []
                if docs:  # 命中就停
                    last_res = res
                    used_where = w
                    break
            except Exception:
                # 某些 Chroma 版本/配置可能不支持 where_document，直接跳出走 fallback
                last_res = None
                used_where = None
                break

    # fallback：不使用 where_document（纯向量召回）
    if last_res is None:
        res = coll.query(
            query_embeddings=q_emb,
            n_results=topk,
            include=["documents", "metadatas", "distances"],
        )
        last_res = res

    docs = last_res.get("documents", [[]])[0] if last_res.get("documents") else []
    metas = last_res.get("metadatas", [[]])[0] if last_res.get("metadatas") else []
    dists = last_res.get("distances", [[]])[0] if last_res.get("distances") else []

    # strict filter + 结构化输出
    raw_hits: List[Dict[str, Any]] = []
    for doc, meta, dist in zip(docs, metas, dists):
        fc = extract_file_code(doc, meta)
        if norm_code(fc) != basis_norm:
            continue
        inst = extract_instrument_name(doc, meta)
        raw_hits.append({
            "instrument_name": inst,
            "has_star": has_star_mark(inst),
            "file_code": fc,
            "distance": dist,
            "kb_basis_text": (meta or {}).get("校准依据"),
        })

    # 去重：同名保留最小 distance
    best: Dict[str, Dict[str, Any]] = {}
    for h in raw_hits:
        k = h["instrument_name"]
        if k not in best:
            best[k] = h
        else:
            old = best[k]
            if old["distance"] is None:
                best[k] = h
            elif h["distance"] is not None and h["distance"] < old["distance"]:
                best[k] = h

    instruments = list(best.values())
    instruments.sort(key=lambda x: (x["distance"] is None, x["distance"]))

    return {
        "basis": basis,
        "basis_norm": basis_norm,
        "used_where_contains": used_where,   # 记录到底用了哪个 contains 变体（方便排错）
        "hits_total": len(raw_hits),
        "instruments": instruments,
    }


# ===================== 示例 =====================
if __name__ == "__main__":
    for q in ["JJG 237-2010 数字式秒表检定规程", "JJG 959"]:
        out = search_instruments_by_basis_code(q, topk=50, use_where_document=True)
        print("\n输入:", q)
        print("basis:", out["basis"], "basis_norm:", out["basis_norm"], "used_where:", out["used_where_contains"])
        print("命中(去重前):", out["hits_total"], "仪器数(去重后):", len(out["instruments"]))
        for i, r in enumerate(out["instruments"], 1):
            dist = r["distance"]
            dist_str = f"{dist:.4f}" if isinstance(dist, (int, float)) else "N/A"
            print(f"  {i:02d}. {r['instrument_name']} | has_star={r['has_star']} | {r['file_code']} | dist={dist_str}")
            print("      校准依据:", r.get("kb_basis_text"))
