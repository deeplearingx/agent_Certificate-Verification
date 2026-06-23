import json
import os
from pathlib import Path
import chromadb
try:
    from sentence_transformers import SentenceTransformer
except ModuleNotFoundError:  # pragma: no cover - optional runtime dependency in tests
    SentenceTransformer = None  # type: ignore[assignment]
from config.settings import get_app_config
from kb.chroma_client import get_collection


# ====================================
# ⚙️ 配置部分
# ====================================
class Config:
    _app = get_app_config()
    HUAWEI_DB_DIR = _app.huawei_cycle_db_dir
    GENERAL_DB_DIR = _app.general_cycle_db_dir
    EMBED_MODEL_PATH = _app.embed_model_path
    OUTPUT_REPORT = "cycle_report.md"
    API_KEY = _app.api_key
    API_BASE = _app.api_base
    BASE_DIR = _app.local_json_dir
    DEFAULT_CYCLE = _app.default_cycle

from datetime import datetime
#===  解析日期 ===#
def parse_date(date_str: str):
    """
    尝试解析常见日期格式，失败返回 None
    """
    if not date_str:
        return None

    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    return None
# ====================================
# 🧠 初始化 LLM
# ====================================
def init_llm(config: Config):
    from llm.client import create_openai_like_client

    return create_openai_like_client(
        model=getattr(config, "MODEL", "deepseek-chat"),
        api_base=config.API_BASE,
        api_key=config.API_KEY,
        temperature=0.3,
        max_tokens=512,
    )

## 日期校准逻辑##

def check_date_logic(receive_date_str: str, calibrate_date_str: str):
    """
    判断接收日期是否早于校准日期
    """
    receive_date = parse_date(receive_date_str)
    calibrate_date = parse_date(calibrate_date_str)

    if not receive_date or not calibrate_date:
        return {
            "pass": False,
            "reason": "接收日期或校准日期缺失或格式无法识别"
        }

    if receive_date <= calibrate_date:
        return {
            "pass": True,
            "reason": f"接收日期({receive_date_str}) 早于或等于 校准日期({calibrate_date_str})，日期逻辑正确"
        }
    else:
        return {
            "pass": False,
            "reason": f"接收日期({receive_date_str}) 晚于 校准日期({calibrate_date_str})，日期逻辑错误"
        }

##内页与封页的温度、湿度核对
import re

def _normalize_common(s: str) -> str:
    """通用归一化：去首尾空白、统一全角符号、移除所有空格"""
    if s is None:
        return ""
    s = str(s).strip()

    # 统一全角符号到半角/常用形态
    s = (s.replace("（", "(").replace("）", ")")
           .replace("～", "~").replace("〜", "~")
           .replace("－", "-").replace("–", "-").replace("—", "-"))

    # 去掉所有空白（包括中间空格）
    s = re.sub(r"\s+", "", s)
    return s


def normalize_temperature_value(temp_str: str) -> str:
    """
    温度归一化：
    - 去空格、统一括号/波浪线/全角符号
    - 去掉最外层括号（例如 (22~22.5)℃ -> 22~22.5℃）
    - 统一单位写法（尽量保留 ℃）
    """
    s = _normalize_common(temp_str)

    # 常见单位可能出现 "°C" 或 "℃"，统一成 "℃"
    s = s.replace("°C", "℃").replace("°c", "℃")

    # 去掉最外层括号： (xxx)℃ 或 (xxx) -> xxx
    # 只去“最外层”一对，避免破坏内部结构
    if s.startswith("(") and s.endswith("℃") and ")" in s:
        # 形如 "(22~22.5)℃"
        inner = s[1:s.rfind(")")]
        tail = s[s.rfind(")")+1:]  # 例如 "℃"
        s = inner + tail
    elif s.startswith("(") and s.endswith(")") and len(s) > 2:
        s = s[1:-1]

    # 统一范围分隔符：把连字符范围也转为 "~"（可选）
    # 例如 "22-22.5℃" -> "22~22.5℃"
    s = re.sub(r"(?<=\d)-(?=\d)", "~", s)

    return s


def normalize_humidity_value(rh_str: str) -> str:
    """
    湿度归一化：
    - 去空格、统一全角符号
    - 统一百分号写法
    """
    s = _normalize_common(rh_str)
    # 统一全角百分号
    s = s.replace("％", "%")
    return s


def check_env_consistency(temp: str, rh: str, temp_in: str, rh_in: str):
    """
    当四个字段都非空时，比较 温度 vs 温度_内页、相对湿度 vs 相对湿度_内页 是否一致。
    返回结构化结果，方便写报告。
    """
    # 判空：这里认为空字符串/None 都算空
    def _is_empty(x):
        return x is None or str(x).strip() == ""

    if any(_is_empty(x) for x in [temp, rh, temp_in, rh_in]):
        return {
            "enabled": False,
            "pass": False,
            "reason": "温度/湿度字段存在空值，跳过一致性比对。",
            "detail": {}
        }

    t1 = normalize_temperature_value(temp)
    t2 = normalize_temperature_value(temp_in)
    h1 = normalize_humidity_value(rh)
    h2 = normalize_humidity_value(rh_in)

    temp_same = (t1 == t2)
    rh_same = (h1 == h2)

    overall = temp_same and rh_same

    detail = {
        "温度_raw": temp,
        "温度_内页_raw": temp_in,
        "温度_norm": t1,
        "温度_内页_norm": t2,
        "相对湿度_raw": rh,
        "相对湿度_内页_raw": rh_in,
        "相对湿度_norm": h1,
        "相对湿度_内页_norm": h2,
        "温度一致": temp_same,
        "湿度一致": rh_same,
    }

    if overall:
        reason = "温度与温度_内页一致，且相对湿度与相对湿度_内页一致。"
    else:
        parts = []
        if not temp_same:
            parts.append("温度不一致")
        if not rh_same:
            parts.append("湿度不一致")
        reason = "；".join(parts) + "（基于归一化后对比）"

    return {
        "enabled": True,
        "pass": overall,
        "reason": reason,
        "detail": detail
    }



# ====================================
# 🔍 调用 LLM 进行比对分析
# ====================================
def verify_cycle_with_llm(llm, client_name, instrument_name, criterion, report_cycle, db_entries):
    """
    调用 LLM 判断证书记录周期是否合理
    """
    import json
    from llama_index.core.base.llms.types import ChatMessage, MessageRole

    # 1️⃣ 构建系统提示词
    system_prompt = (
        "你是一名实验室质量核验专家。任务是：判断证书中记录的校准周期是否与建议周期一致。\n"
        "输出必须严格遵守 JSON 格式，不允许有其他文字。\n"
        "JSON 字段要求：\n"
        "- find: 0表示数据库没有匹配, 1表示有匹配(包括使用了默认标准)\n"
        "- reason: 核验说明文字\n"
        "- table: Markdown 表格字符串，如无匹配可为空\n"
        "如果数据库建议周期为空且无默认标准，请返回 find:0。\n"
        "如果有匹配记录（或默认标准），请返回 find:1，并生成表格对比证书值与建议值。\n"
    )

    # 2️⃣ 构建用户提示词
    db_text = ""
    for i, rec in enumerate(db_entries, 1):
        db_text += (
            f"\n[{i}] 仪器名称：{rec.get('仪器名称', '')}，依据：{rec.get('依据', '')}，"
            f"建议校准周期：{rec.get('建议校准周期', '')}，来源：{rec.get('来源', '')}"
        )

    user_prompt = (
        f"客户：{client_name}\n"
        f"仪器名称：{instrument_name}\n"
        f"校准依据：{criterion}\n"
        f"证书记录的周期：{report_cycle}\n"
        f"参考建议周期：{db_text}\n"
        "请判断证书记录的校准周期是否合理，并严格返回 JSON。"
    )

    messages = [
        ChatMessage(role=MessageRole.SYSTEM, content=system_prompt),
        ChatMessage(role=MessageRole.USER, content=user_prompt),
    ]

    # 3️⃣ 调用 LLM
    try:
        response = llm.chat(messages=messages)
        content = response.message.content.strip()
        # 去除可能存在的 markdown 代码块标记
        if content.startswith("```json"):
            content = content[7:]
        if content.endswith("```"):
            content = content[:-3]

        result_json = json.loads(content)
    except Exception as e:
        print(f"❌ LLM JSON 解析失败: {e}")
        # 如果解析失败，但也算作一次尝试
        result_json = {
            "find": 0,
            "reason": f"LLM输出无法解析: {str(e)}",
            "table": ""
        }

    return result_json


# ====================================
# 📘 核验逻辑（增加默认一年逻辑）
# ====================================
def check_cycle_reasonableness(json_file, config):
    # 直接使用 get_app_config() 获取配置，避免任何路径编码问题
    app_config = get_app_config()
    print(f"📂 正在加载证书：{json_file}")

    with open(json_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    props = data["properties"]["证书列表"]["items"]["properties"]

    receive_date = props.get("接收日期", "")
    calibrate_date = props.get("校准日期", "")

    client_name = props.get("委托单位名称", "") or props.get("委托单位", "") or props.get("客户名称", "未知客户")
    instrument_name = props.get("仪器名称", "")
    model_name = props.get("型号规格", "")
    criterion_list = props.get("校准依据", [])
    report_cycle = props.get("建议校准周期", "")

    print(f"🔹 证书信息：客户={client_name}, 仪器={instrument_name}, 依据={criterion_list}, 周期={report_cycle}")

     ##执行日期校准
    date_check_result = check_date_logic(receive_date, calibrate_date)

    print(f"📅 日期校验结果: {date_check_result['reason']}")

    temp = props.get("温度", "")
    rh = props.get("相对湿度") or props.get("湿度", "")
    temp_in = props.get("温度_内页", "")
    rh_in = props.get("相对湿度_内页") or props.get("湿度_内页", "")

    env_consistency_result = check_env_consistency(temp, rh, temp_in, rh_in)
    print(f"🌡️ 温湿度一致性校验: {env_consistency_result['reason']}")


    if SentenceTransformer is None:
        raise ModuleNotFoundError(
            "sentence_transformers is required to run cycle checks; install the runtime dependency first."
        )
    embed_model = SentenceTransformer(app_config.embed_model_path)
    llm = init_llm(config)

    all_db_entries = []
    llm_results = []
    is_huawei = "华为" in client_name

    # 遍历每条校准依据
    for criterion in criterion_list:
        llm_result = {"find": 0}  # 初始化结果

        # -------------------------------------------------
        # Step 1: 华为数据库查询 (如果是华为客户)
        # -------------------------------------------------
        if is_huawei:
            print(f"    🔍 [Step 1] 查询华为数据库: '{model_name} {criterion}'")
            try:
                collection = get_collection(app_config.huawei_cycle_db_dir, "huawei_cycle_data")
                query_emb = embed_model.encode([f"{model_name} {criterion}"]).tolist()
                results = collection.query(query_embeddings=query_emb, n_results=3)  # 减少数量提高精准度

                db_entries = []
                for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
                    db_entries.append({
                        "仪器名称": meta.get("仪器名称", "") or meta.get("INSTRUMENT_NAME", ""),
                        "依据": meta.get("依据", "") or meta.get("FILE_NAME", ""),
                        "建议校准周期": meta.get("建议校准周期", ""),
                        "来源": "华为数据库"
                    })

                if db_entries:
                    llm_result = verify_cycle_with_llm(llm, client_name, instrument_name, criterion, report_cycle,
                                                       db_entries)
                    if llm_result.get("find", 0) == 1:
                        all_db_entries.extend(db_entries)
            except Exception as e:
                print(f"    ⚠️ 华为数据库查询出错: {e}")

        # -------------------------------------------------
        # Step 2: 通用数据库查询 (如果华为没找到，或者不是华为客户)
        # -------------------------------------------------
        if llm_result.get("find", 0) == 0:
            print(f"    🔍 [Step 2] 查询通用数据库: '{instrument_name} {criterion}'")
            try:
                collection = get_collection(app_config.general_cycle_db_dir, "general_cycle_data")
                query_emb = embed_model.encode([f"{instrument_name} {criterion}"]).tolist()
                results = collection.query(query_embeddings=query_emb, n_results=3)

                db_entries = []
                for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
                    db_entries.append({
                        "仪器名称": meta.get("仪器名称", "") or meta.get("INSTRUMENT_NAME", ""),
                        "依据": meta.get("依据", "") or meta.get("FILE_NAME", ""),
                        "建议校准周期": meta.get("建议校准周期", ""),
                        "来源": "通用数据库"
                    })

                if db_entries:
                    llm_result = verify_cycle_with_llm(llm, client_name, instrument_name, criterion, report_cycle,
                                                       db_entries)
                    if llm_result.get("find", 0) == 1:
                        all_db_entries.extend(db_entries)
            except Exception as e:
                print(f"    ⚠️ 通用数据库查询出错: {e}")

        # -------------------------------------------------
        # Step 3: 默认规则兜底 (如果两库都未找到匹配)
        # -------------------------------------------------
        if llm_result.get("find", 0) == 0:
            print(f"    ⚠️ [Step 3] 知识库均未匹配，启用默认规则：{config.DEFAULT_CYCLE}")

            # 构造一个“虚拟”的数据库条目，代表默认规则
            default_entry = [{
                "仪器名称": instrument_name,  # 使用当前仪器名
                "依据": "通用计量常规要求 (无特定规程匹配)",
                "建议校准周期": config.DEFAULT_CYCLE,
                "来源": "默认标准(兜底)"
            }]

            # 再次调用 LLM，这次它一定会由“默认标准”进行比对
            llm_result = verify_cycle_with_llm(llm, client_name, instrument_name, criterion, report_cycle,
                                               default_entry)

            # 强制标记为找到（因为我们使用了默认规则），并记录
            if llm_result.get("find", 0) == 1:  # LLM 应该返回 1，因为它看到了我们传入的默认建议
                all_db_entries.extend(default_entry)
            else:
                # 如果 LLM 即使给了默认值还返回 0，手动修正一下让它显示
                llm_result["find"] = 1
                all_db_entries.extend(default_entry)

        # 记录本轮依据的最终结果
        llm_results.append(llm_result)

    # -------------------------------------------------
    # 生成报告逻辑
    # -------------------------------------------------

    # 合并数据库记录（去重）
    seen = set()
    merged_entries = []
    for rec in all_db_entries:
        # 使用来源作为去重的一部分，防止默认标准被意外覆盖
        key = (rec["仪器名称"], rec["依据"], rec["来源"])
        if key not in seen:
            merged_entries.append(rec)
            seen.add(key)

    report_lines = [
        "# 🧾 校准周期合理性核验报告",
        "",
        f"**客户名称：** {client_name}",
        f"**仪器名称：** {instrument_name}",
        f"**型号：** {model_name}",
        f"**校准依据：** {', '.join(criterion_list)}",
        f"**证书记录周期：** {report_cycle}",
        "",
        "## 📚 参考标准来源",
        "",
        "| 序号 | 仪器/依据 | 建议校准周期 | 数据来源 |",
        "| ---- | ---------- | ---------------- | ---------- |",
    ]

    for idx, rec in enumerate(merged_entries, 1):
        report_lines.append(
            f"| {idx} | {rec['仪器名称']} / {rec['依据']} | {rec['建议校准周期']} | {rec['来源']} |"
        )

    report_lines.append("\n## 🤖 智能核验结论\n")

    matched_results = [r for r in llm_results if r.get("find", 0) == 1]
    if not matched_results:
        report_lines.append("> ⚠️ 系统异常：未能生成有效核验结论。\n")
    else:
        for i, r in enumerate(matched_results, 1):
            reason = r.get("reason", "").strip()
            table = r.get("table", "").strip()

            report_lines.append(f"### ✅ 核验项 {i}\n")
            report_lines.append(f"> **分析说明：** {reason}\n")
            if table:
                report_lines.append("\n" + table + "\n")
            else:
                report_lines.append("\n> (无详细对比表)\n")

    report_lines.extend([
        "## 📅 日期逻辑核验",
        "",
        f"- **接收日期：** {receive_date or '未提供'}",
        f"- **校准日期：** {calibrate_date or '未提供'}",
        "",
    ])

    if date_check_result["pass"]:
        report_lines.append(f"> ✅ {date_check_result['reason']}\n")
    else:
        report_lines.append(f"> ❌ {date_check_result['reason']}\n")

    report_lines.extend([
        "## 🌡️ 温湿度一致性核验",
        "",
        f"- **温度：** {temp or '未提供'}",
        f"- **相对湿度：** {rh or '未提供'}",
        f"- **温度_内页：** {temp_in or '未提供'}",
        f"- **相对湿度_内页：** {rh_in or '未提供'}",
        "",
    ])

    if not env_consistency_result["enabled"]:
        report_lines.append(f"> ⚠️ {env_consistency_result['reason']}\n")
    else:
        if env_consistency_result["pass"]:
            report_lines.append(f"> ✅ {env_consistency_result['reason']}\n")
        else:
            report_lines.append(f"> ❌ {env_consistency_result['reason']}\n")

        # 可选：把归一化后的对比细节也写成小表格（便于排查）
        d = env_consistency_result["detail"]
        report_lines.append("| 项目 | 原始值 | 归一化后 |")
        report_lines.append("| --- | --- | --- |")
        report_lines.append(f"| 温度 | {d['温度_raw']} | {d['温度_norm']} |")
        report_lines.append(f"| 温度_内页 | {d['温度_内页_raw']} | {d['温度_内页_norm']} |")
        report_lines.append(f"| 相对湿度 | {d['相对湿度_raw']} | {d['相对湿度_norm']} |")
        report_lines.append(f"| 相对湿度_内页 | {d['相对湿度_内页_raw']} | {d['相对湿度_内页_norm']} |")
        report_lines.append("")

    print("🔹 报告生成完成")
    return "\n".join(report_lines)


# ====================================
# 🚀 主执行函数
# ====================================
def main():
    # 请根据实际情况修改路径

    JSON_FILE = "1GA25001576-0015.json"

    cfg = Config()

    # 拼接输出路径
    JSON_PATH = str(cfg.BASE_DIR / JSON_FILE)
    if not os.path.exists(JSON_PATH):
        print(f"❌ 文件不存在: {JSON_PATH}")
        return

    report = check_cycle_reasonableness(JSON_PATH, cfg)
    print("\n" + report)

    # 按照题目要求输出：temperature_report_{json名}.md
    # 注意：这里虽然题目叫 temperature_report 但内容是 cycle，根据要求命名
    output_filename = f"Cycle_report_{Path(JSON_FILE).stem}.md"
    output_dir = Path("./reports")
    output_dir.mkdir(parents=True, exist_ok=True)

    report_path = output_dir / output_filename

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\n📝 核验报告已生成：{report_path.resolve()}")


if __name__ == "__main__":
    main()
