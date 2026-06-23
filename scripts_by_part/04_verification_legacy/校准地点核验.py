import os
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import chromadb
from sentence_transformers import SentenceTransformer
from llama_index.llms.openai_like import OpenAILike
from llama_index.core.base.llms.types import ChatMessage, MessageRole
from sympy import false


# ===================== 配置 =====================
class Config:
    BASE_DIR = Path(r"D:\workspace\ai大模型开发课\文档核验\work_pdf\local_json")
    CNAS_DB_DIR = r"./vector_db/cnas_calibration"
    CNAS_COLLECTION = "calibration_data"
    ADDR_DB_DIR = r"./vector_db/address"
    ADDR_COLLECTION = "calibration_address"
    EMBED_MODEL_PATH = r"D:\workspace\ai_learning\pythonProject\models\BAAI\bge-m3"

    # 距离阈值：越小越相似（需要你结合样本继续标定）
    MUST_MATCH_THRESHOLD = 0.45       # 不带*：必须命中地址库
    OPTIONAL_MATCH_THRESHOLD = 0.45   # 带*：命中地址库算PASS（否则走“库外具体地点”）

    # ========== LLM增强开关 ==========
    USE_LLM_LOCATION_CHECK = True
    LLM_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
    LLM_API_BASE = "https://api.deepseek.com/v1"
    LLM_MODEL = "deepseek-chat"
    LLM_TEMPERATURE = 0.0
    LLM_MAX_TOKENS = 256


# ===================== 初始化大模型 =====================
def init_llm(cfg: Config):
    return OpenAILike(
        model=cfg.LLM_MODEL,
        api_base=cfg.LLM_API_BASE,
        api_key=cfg.LLM_API_KEY,
        is_chat_model=True,
        temperature=cfg.LLM_TEMPERATURE,
        max_tokens=cfg.LLM_MAX_TOKENS,
    )


# ===================== 大模型审核具体地点 =====================
def llm_is_specific_location(llm, location_text: str) -> Dict[str, Any]:
    system_prompt = (
        "你是一名计量/校准质量核验专家。\n"
        "任务：判断给定的“校准地点描述”是否足够具体。\n\n"
        "判定为【足够具体】需要至少满足以下之一：\n"
        "1) 明确到房间/门牌/编号（如203室、A-203、Room 302、9栋204室）\n"
        "2) 明确到楼层/楼栋/座/号楼（如D3栋3楼、A座、9栋）\n"
        "3) 明确到特定功能场所/设施（如恒温恒湿实验室、屏蔽室、暗室、洁净室、计量室、校准室）\n"
        "4) 明确到车间/厂房/生产线/区域（如××车间、D区、厂房1号）\n\n"
        "注意：仅有城市/区县/道路/园区名但缺少以上细节，通常判定为不具体。\n"
        "输出必须是JSON，且只输出JSON，不要输出任何多余文字。"
    )

    user_prompt = (
        f"校准地点描述：{location_text}\n\n"
        "请输出JSON，格式严格为：\n"
        '{ "is_specific": true/false, "reason": "...", "signals": ["..."] }\n'
        "signals里放你识别到的具体性线索类别，例如：楼层/房间/实验室/车间/楼栋/区域/编号 等。"
    )

    try:
        resp = llm.chat([
            ChatMessage(role=MessageRole.SYSTEM, content=system_prompt),
            ChatMessage(role=MessageRole.USER, content=user_prompt),
        ])
        txt = (resp.message.content or "").strip()
        txt = re.sub(r"^```json\s*|\s*```$", "", txt, flags=re.IGNORECASE).strip()

        obj = json.loads(txt)
        if not isinstance(obj, dict) or "is_specific" not in obj:
            return {"is_specific": False, "reason": "LLM输出JSON结构异常", "signals": []}

        return {
            "is_specific": bool(obj.get("is_specific")),
            "reason": str(obj.get("reason", "")).strip(),
            "signals": obj.get("signals") if isinstance(obj.get("signals"), list) else [],
        }
    except Exception as e:
        return {"is_specific": False, "reason": f"LLM调用/解析失败: {e}", "signals": []}


# ===================== 规程代号解析/归一化 =====================
def extract_basis_code(text: str) -> Optional[str]:
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
    code = (code or "").strip()
    m = re.search(r"\b(JJ[GF]|GJB)\s*(\d+)", code, flags=re.IGNORECASE)
    if m:
        return f"{m.group(1).upper()}{m.group(2)}"
    return re.sub(r"\s+", "", code).upper()


# ===================== CNAS库：字段提取 =====================
def extract_instrument_name(doc: str, meta: Dict[str, Any]) -> str:
    meta = meta or {}
    name = meta.get("仪器名称") or meta.get("INSTRUMENT_NAME")
    if name and str(name).strip():
        return str(name).strip()
    m = re.search(r"仪器名称[：:]\s*(.+?)(?:[。；;\n]|$)", doc or "")
    return m.group(1).strip() if m else "N/A"


def extract_file_code(doc: str, meta: Dict[str, Any]) -> str:
    meta = meta or {}
    for k in ["校准依据", "raw_block", "_node_content", "ref_doc_id", "document_id", "doc_id"]:
        v = meta.get(k)
        b = extract_basis_code(v) if v else None
        if b:
            return b
    b2 = extract_basis_code(doc or "")
    return b2 if b2 else "未知规程"


def has_star_mark(name: str) -> bool:
    return ("*" in (name or "")) or ("＊" in (name or ""))


# ===================== 1) CNAS库检索：按规程找“仪器是否带*” =====================
def search_instruments_by_basis_code(
    cfg: Config,
    basis_or_criterion: str,
    embedder: SentenceTransformer,
    topk: int = 50,
    use_where_document: bool = True,
    where_variants: Optional[List[str]] = None,
) -> Dict[str, Any]:
    basis = extract_basis_code(basis_or_criterion)
    if not basis:
        raise ValueError(f"无法从输入中解析规程代号：{basis_or_criterion}")
    basis_norm = norm_code(basis)

    client = chromadb.PersistentClient(path=cfg.CNAS_DB_DIR)
    coll = client.get_collection(cfg.CNAS_COLLECTION)

    query_text = f"{basis} {basis_or_criterion}".strip()
    q_emb = embedder.encode([query_text]).tolist()

    if where_variants is None:
        where_variants = [basis, basis_norm, basis.replace(" ", "")]

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
                if docs:
                    last_res = res
                    used_where = w
                    break
            except Exception:
                last_res = None
                used_where = None
                break

    if last_res is None:
        last_res = coll.query(
            query_embeddings=q_emb,
            n_results=topk,
            include=["documents", "metadatas", "distances"],
        )

    docs =  last_res.get("documents", [[]])[0] if last_res.get("documents") else []
    metas = last_res.get("metadatas", [[]])[0] if last_res.get("metadatas") else []
    dists = last_res.get("distances", [[]])[0] if last_res.get("distances") else []

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

    # 去重：同名取最小 distance
    best: Dict[str, Dict[str, Any]] = {}
    for h in raw_hits:
        k = h["instrument_name"]
        if k not in best:
            best[k] = h
        else:
            if h["distance"] is not None and (best[k]["distance"] is None or h["distance"] < best[k]["distance"]):
                best[k] = h

    instruments = list(best.values())
    instruments.sort(key=lambda x: (x["distance"] is None, x["distance"]))

    return {
        "basis": basis,
        "basis_norm": basis_norm,
        "used_where_contains": used_where,
        "hits_total": len(raw_hits),
        "instruments": instruments,
    }


# ===================== 2) 地址库检索（vector_db/address） =====================
def search_address_in_db(
    cfg: Config,
    embedder: SentenceTransformer,
    query_text: str,
    topk: int = 5,
) -> List[Dict[str, Any]]:
    client = chromadb.PersistentClient(path=cfg.ADDR_DB_DIR)
    coll = client.get_collection(cfg.ADDR_COLLECTION)

    q_emb = embedder.encode([query_text]).tolist()
    res = coll.query(
        query_embeddings=q_emb,
        n_results=topk,
        include=["documents", "metadatas", "distances"],
    )

    docs = res.get("documents", [[]])[0] if res.get("documents") else []
    metas = res.get("metadatas", [[]])[0] if res.get("metadatas") else []
    dists = res.get("distances", [[]])[0] if res.get("distances") else []

    out = []
    for doc, meta, dist in zip(docs, metas, dists):
        meta = meta or {}
        out.append({
            "校准地址": meta.get("校准地址", ""),
            "专业室": meta.get("专业室", ""),
            "序号": meta.get("序号", ""),
            "distance": dist,
            "doc": doc,
        })
    return out


# ===================== 3) regex：库外地点“足够具体”判定 =====================
def is_specific_location(text: str) -> bool:
    if not text:
        return False
    s = str(text).strip()

    room_pat = r"(\broom\s*\d+\b)|(\d+\s*室)|(\d+\s*房)|(\d+\s*号房)|(\d+\s*楼\s*\d+\s*室)|(\d+\s*栋\s*\d+\s*室)|([A-Za-z]\s*\d{2,4})|(\d+-\d+)"
    if re.search(room_pat, s, flags=re.IGNORECASE):
        return True

    building_pat = r"(实验楼|办公楼|楼宇|大楼|园区|厂房|A座|B座|C座|D座|[A-Z]座|\d+栋|\d+号楼|\d+楼)"
    if re.search(building_pat, s):
        return True

    facility_pat = r"(恒温恒湿|屏蔽室|暗室|洁净室|计量室|校准室|检测室|标准室|无尘室|温湿度|振动|电磁兼容|车间|生产线|厂区|工位)"
    if re.search(facility_pat, s):
        return True

    return False


# ===================== 4) 校准地点核验（按*号分流） =====================
def verify_calibration_location(
    cfg: Config,
    embedder: SentenceTransformer,
    location_text: str,
    has_star: bool,
    topk: int = 5,
) -> Dict[str, Any]:
    loc = (location_text or "").strip()
    if not loc:
        return {
            "status": "FAIL",
            "reason": "校准地点字段为空/缺失",
            "has_star": has_star,
            "matched_db": False,
            "contains_hit": False,
            "contains_addr": None,
            "best_dist": None,
            "threshold": None,
            "specificity_source": None,
            "specificity_detail": None,
            "db_hits": [],
        }

    hits = search_address_in_db(cfg, embedder, loc, topk=topk)
    best = hits[0] if hits else None
    best_dist = best["distance"] if best else None

    # 子串命中（更接近“是否一样”的解释）
    contains_hit = False
    contains_addr = None
    for h in hits:
        addr = (h.get("校准地址") or "").strip()
        if addr and (addr in loc or loc in addr):
            contains_hit = True
            contains_addr = addr
            break

    def matched_db(strict: bool) -> Tuple[bool, float]:
        thr = cfg.MUST_MATCH_THRESHOLD if strict else cfg.OPTIONAL_MATCH_THRESHOLD
        if contains_hit:
            return True, thr
        if best_dist is None:
            return False, thr
        return (best_dist <= thr), thr

    # ---------- 带* ----------
    if has_star:
        ok, thr = matched_db(strict=False)
        if ok:
            return {
                "status": "PASS",
                "reason": f"仪器带*：地点命中地址库（best_dist={best_dist}) 或包含库内地址",
                "has_star": True,
                "matched_db": True,
                "contains_hit": contains_hit,
                "contains_addr": contains_addr,
                "best_dist": best_dist,
                "threshold": thr,
                "specificity_source": "db",
                "specificity_detail": None,
                "db_hits": hits,
            }

        if cfg.USE_LLM_LOCATION_CHECK:
            llm = init_llm(cfg)
            llm_judge = llm_is_specific_location(llm, loc)
            if llm_judge["is_specific"]:
                return {
                    "status": "PASS",
                    "reason": "仪器带*：地点未命中地址库，但LLM判定地点描述足够具体",
                    "has_star": True,
                    "matched_db": False,
                    "contains_hit": contains_hit,
                    "contains_addr": contains_addr,
                    "best_dist": best_dist,
                    "threshold": thr,
                    "specificity_source": "llm",
                    "specificity_detail": llm_judge,
                    "db_hits": hits,
                }
            else:
                return {
                    "status": "FAIL",
                    "reason": "仪器带*：地点未命中地址库，且LLM判定描述不够具体（需具体到楼栋/楼层/房间/设施/车间等）",
                    "has_star": True,
                    "matched_db": False,
                    "contains_hit": contains_hit,
                    "contains_addr": contains_addr,
                    "best_dist": best_dist,
                    "threshold": thr,
                    "specificity_source": "llm",
                    "specificity_detail": llm_judge,
                    "db_hits": hits,
                }

        # 不用LLM，走regex
        if is_specific_location(loc):
            return {
                "status": "PASS",
                "reason": "仪器带*：地点未命中地址库，但代码识别到地点描述足够具体",
                "has_star": True,
                "matched_db": False,
                "contains_hit": contains_hit,
                "contains_addr": contains_addr,
                "best_dist": best_dist,
                "threshold": thr,
                "specificity_source": "regex",
                "specificity_detail": None,
                "db_hits": hits,
            }

        return {
            "status": "FAIL",
            "reason": "仪器带*：地点未命中地址库，且代码未识别到楼栋/楼层/房间/设施/车间等",
            "has_star": True,
            "matched_db": False,
            "contains_hit": contains_hit,
            "contains_addr": contains_addr,
            "best_dist": best_dist,
            "threshold": thr,
            "specificity_source": "regex",
            "specificity_detail": None,
            "db_hits": hits,
        }

    # ---------- 不带* ----------
    ok, thr = matched_db(strict=True)
    if ok:
        return {
            "status": "PASS",
            "reason": f"仪器不带*：地点命中地址库（best_dist={best_dist}) 或包含库内地址",
            "has_star": False,
            "matched_db": True,
            "contains_hit": contains_hit,
            "contains_addr": contains_addr,
            "best_dist": best_dist,
            "threshold": thr,
            "specificity_source": "db",
            "specificity_detail": None,
            "db_hits": hits,
        }

    return {
        "status": "FAIL",
        "reason": "仪器不带*：地点必须来自地址库，但当前地点未匹配到库内校准地址",
        "has_star": False,
        "matched_db": False,
        "contains_hit": contains_hit,
        "contains_addr": contains_addr,
        "best_dist": best_dist,
        "threshold": thr,
        "specificity_source": "db",
        "specificity_detail": None,
        "db_hits": hits,
    }


# ===================== 5) 按你提供的方式读取 JSON =====================
def read_json_props(json_file: str) -> Dict[str, Any]:
    with open(json_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["properties"]["证书列表"]["items"]["properties"]


def get_json_inputs_from_props(props: Dict[str, Any]) -> Tuple[str, List[str], str]:
    instrument_name = props.get("INSTRUMENT_NAME") or props.get("仪器名称") or "N/A"
    criteria_list = props.get("校准依据", []) or []
    location_text = (props.get("校准地点") or props.get("校准地址") or props.get("地点") or "")

    if isinstance(location_text, (list, dict)):
        location_text = json.dumps(location_text, ensure_ascii=False)

    return str(instrument_name), [str(x) for x in criteria_list], str(location_text)


# ===================== 报告渲染：CNAS 仪器明细表 =====================
def render_cnas_instrument_table(basis_details: List[Dict[str, Any]]) -> str:
    lines: List[str] = []
    lines.append("## CNAS 仪器检索明细（用于*号判定）")

    flat: List[Dict[str, Any]] = []
    for out in basis_details:
        basis = out.get("basis", "N/A")
        used_where = out.get("used_where_contains", None)
        for it in out.get("instruments", []) or []:
            x = dict(it)
            x["_basis"] = basis
            x["_used_where"] = used_where
            flat.append(x)

    if not flat:
        lines.append("> CNAS 仪器库未检索到与证书依据一致的仪器记录（instruments=0）。")
        lines.append("- *号最终判定：**False**（未检到仪器，默认False）")
        return "\n".join(lines)

    lines.append("| 序号 | 依据 | used_where | 仪器名称 | 是否带* | file_code | distance |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for i, it in enumerate(flat, 1):
        dist = it.get("distance")
        dist_str = f"{dist:.4f}" if isinstance(dist, (int, float)) else "N/A"
        lines.append(
            f"| {i} | {it.get('_basis','')} | {it.get('_used_where','')} | "
            f"{it.get('instrument_name','')} | {it.get('has_star', False)} | "
            f"{it.get('file_code','')} | {dist_str} |"
        )

    is_star = any(x.get("has_star") for x in flat)
    lines.append("")
    lines.append(f"- *号最终判定：**{is_star}**（只要任意命中仪器名含*即为True）")
    return "\n".join(lines)


# ===================== 6) 主核验函数 =====================
def check_location(json_file: str, cfg: Config) -> str:
    props = read_json_props(json_file)
    instrument_in_json, criteria_list, location_text = get_json_inputs_from_props(props)

    if not criteria_list:
        return "❌ JSON 中未找到 '校准依据'，无法进行*号判定。"

    print(f"🧠 正在加载语义模型：{cfg.EMBED_MODEL_PATH}")
    embedder = SentenceTransformer(cfg.EMBED_MODEL_PATH)

    basis_details: List[Dict[str, Any]] = []
    for criterion in criteria_list:
        out = search_instruments_by_basis_code(
            cfg=cfg,
            basis_or_criterion=criterion,
            embedder=embedder,
            topk=50,
            use_where_document=True,
        )
        basis_details.append(out)

    has_star = any(any(it["has_star"] for it in out["instruments"]) for out in basis_details)

    loc_res = verify_calibration_location(
        cfg=cfg,
        embedder=embedder,
        location_text=location_text,
        has_star=has_star,
        topk=5,
    )

    lines: List[str] = []
    lines.append("# 校准地点核验报告")
    lines.append(f"- JSON: {Path(json_file).name}")
    lines.append(f"- 仪器(证书): {instrument_in_json}")
    lines.append(f"- 校准地点(证书): {location_text}")
    lines.append(f"- 是否带*(来自CNAS库): {has_star}")
    lines.append("")

    lines.append(render_cnas_instrument_table(basis_details))
    lines.append("")

    lines.append("## 结论")
    lines.append(f"- 判定: **{loc_res['status']}**")
    lines.append(f"- 说明: {loc_res['reason']}")
    lines.append(f"- matched_db: {loc_res.get('matched_db')}")
    lines.append(f"- contains_hit: {loc_res.get('contains_hit')} | contains_addr: {loc_res.get('contains_addr')}")
    lines.append(f"- best_dist: {loc_res.get('best_dist')} | threshold: {loc_res.get('threshold')}")
    lines.append(f"- 具体性判定来源: {loc_res.get('specificity_source', 'N/A')}")
    if loc_res.get("specificity_source") == "llm":
        detail = loc_res.get("specificity_detail") or {}
        lines.append(
            f"- LLM判定: is_specific={detail.get('is_specific')} | signals={detail.get('signals')} | reason={detail.get('reason')}"
        )

    lines.append("")
    lines.append("## 地址库 Top 命中")
    lines.append("| Top | distance | 序号 | 专业室 | 校准地址 |")
    lines.append("| --- | --- | --- | --- | --- |")
    for i, h in enumerate(loc_res.get("db_hits", [])[:5], 1):
        dist = h.get("distance")
        dist_str = f"{dist:.4f}" if isinstance(dist, (int, float)) else "N/A"
        lines.append(f"| {i} | {dist_str} | {h.get('序号','')} | {h.get('专业室','')} | {h.get('校准地址','')} |")

    return "\n".join(lines)


# ===================== 主执行 =====================
def main():
    JSON_FILE = "1GA25001576-0015.json"
    cfg = Config()

    JSON_PATH = str(cfg.BASE_DIR / JSON_FILE)
    if not os.path.exists(JSON_PATH):
        print(f"❌ 文件不存在: {JSON_PATH}")
        return

    report = check_location(JSON_PATH, cfg)
    print("\n" + report)

    out_dir = Path("./reports")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"location_report_{Path(JSON_PATH).stem}.md"
    out_path.write_text(report, encoding="utf-8")
    print(f"\n📝 核验报告已生成：{out_path.resolve()}")


if __name__ == "__main__":
    main()

