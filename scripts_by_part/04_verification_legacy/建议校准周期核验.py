import json
import os
from pathlib import Path
import chromadb
from sentence_transformers import SentenceTransformer
from llama_index.llms.openai_like import OpenAILike
from llama_index.core.base.llms.types import ChatMessage, MessageRole


# ====================================
# ⚙️ 配置部分
# ====================================
class Config:
    HUAWEI_DB_DIR = "./vector_db/huawei_cycle"  # 华为周期向量数据库路径
    GENERAL_DB_DIR = "./vector_db/general_cycle"  # 通用周期向量数据库路径
    EMBED_MODEL_PATH = r"D:\workspace\ai_learning\pythonProject\models\BAAI\bge-m3"
    OUTPUT_REPORT = "cycle_report.md"
    API_KEY = ""
    API_BASE = "https://api.deepseek.com/v1"
    BASE_DIR = Path(r"D:\workspace\ai大模型开发课\文档核验\work_pdf\local_json")
    # 新增：默认周期设置
    DEFAULT_CYCLE = "12个月"


# ====================================
# 🧠 初始化 LLM
# ====================================
def init_llm(config: Config):
    llm = OpenAILike(
        model="deepseek-chat",
        api_base=config.API_BASE,
        api_key=config.API_KEY,
        is_chat_model=True,
        temperature=0.3,
        max_tokens=512,
    )
    return llm


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
def check_cycle_reasonableness(json_file, config: Config):
    print(f"📂 正在加载证书：{json_file}")

    with open(json_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    props = data["properties"]["证书列表"]["items"]["properties"]

    client_name = props.get("委托单位名称", "") or props.get("客户名称", "未知客户")
    instrument_name = props.get("INSTRUMENT_NAME", "")
    model_name = props.get("型号", "")
    criterion_list = props.get("校准依据", [])
    report_cycle = props.get("建议校准周期", "")

    print(f"🔹 证书信息：客户={client_name}, 仪器={instrument_name}, 依据={criterion_list}, 周期={report_cycle}")

    embed_model = SentenceTransformer(config.EMBED_MODEL_PATH)
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
                client = chromadb.PersistentClient(path=config.HUAWEI_DB_DIR)
                collection = client.get_collection(name="huawei_cycle_data")
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
                client = chromadb.PersistentClient(path=config.GENERAL_DB_DIR)
                collection = client.get_collection(name="general_cycle_data")
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

    print("🔹 报告生成完成")
    return "\n".join(report_lines)


# ====================================
# 🚀 主执行函数
# ====================================
def main():
    # 请根据实际情况修改路径

    JSON_FILE = "2GB25009792-0001.json"

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
