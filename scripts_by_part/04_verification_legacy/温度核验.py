import json
import re
import os
from pathlib import Path
import chromadb
from sentence_transformers import SentenceTransformer
from llama_index.llms.openai_like import OpenAILike
from llama_index.core.base.llms.types import ChatMessage, MessageRole

# ========== 配置 ==========
class Config:
    TEMP_DB_DIR = "./vector_db/temperature"  # 向量数据库路径
    EMBED_MODEL_PATH = r"D:\workspace\ai_learning\pythonProject\models\BAAI\bge-m3"

    API_KEY = ""  # 替换为你的 DeepSeek Key
    API_BASE = "https://api.deepseek.com/v1"
    OUTPUT_DIR = "./reports"  # 报告输出路径
# ========== 工具函数 ==========
def extract_numbers_from_str(s: str):
    """提取字符串中的数值（支持范围如 20～25）"""
    if not s:
        return []
    s = s.replace("～", " ").replace("~", " ").replace("至", " ")
    matches = re.findall(r"-?\d+\.?\d*", s)
    return [float(x) for x in matches] if matches else []

# ========== LLM 初始化 ==========
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

# ========== 调用 LLM 核验 ==========
def verify_with_llm(llm, criterion, current_temp, current_hum, db_entries):
    system_prompt = (
        "你是一名实验室质量核验专家，根据温度、湿度和温差判断环境条件是否符合校准要求。\n"
        "请严格按照下表输出：\n"
        "| 项目 | 要求 | 实际 | 判定 | 说明 |\n"
        "| --- | --- | --- | --- | --- |\n"
        "只输出表格，不要额外文本。"
    )

    db_text = ""
    for i, rec in enumerate(db_entries, 1):
        db_text += (
            f"\n[{i}] 仪器 {rec['INSTRUMENT_NAME']}，依据编号 {rec['FILE_CODE']}，"
            f"依据名称 {rec['FILE_NAME']}，温度要求 {rec['温度要求']}，"
            f"湿度要求 {rec['相对湿度要求']}，温差 {rec['最大温度变化范围']}"
        )

    user_prompt = (
        f"校准依据：{criterion}\n"
        f"当前温度：{current_temp} ℃\n"
        f"当前湿度：{current_hum} %\n"
        f"向量数据库检索的前5条相关要求：{db_text}\n"
        f"请判断当前温度、湿度和温差是否符合要求，并在表格中说明理由。"
    )

    messages = [
        ChatMessage(role=MessageRole.SYSTEM, content=system_prompt),
        ChatMessage(role=MessageRole.USER, content=user_prompt),
    ]

    response = llm.chat(messages=messages)
    return response.message.content.strip()


# ========== 核验逻辑（修改版） ==========
def check_environment(json_file, config: Config):
    with open(json_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    props = data["properties"]["证书列表"]["items"]["properties"]

    temp_text = props.get("温度", "")
    humidity_text = props.get("相对湿度", "")
    criteria_list = props.get("校准依据", [])

    current_temp = extract_numbers_from_str(temp_text)
    current_temp = current_temp[0] if current_temp else None
    current_hum = extract_numbers_from_str(humidity_text)
    current_hum = current_hum[0] if current_hum else None

    print(f"🧠 正在加载语义模型：{config.EMBED_MODEL_PATH}")
    embed_model = SentenceTransformer(config.EMBED_MODEL_PATH)

    client = chromadb.PersistentClient(path=config.TEMP_DB_DIR)
    collection = client.get_collection(name="temperature_data")

    llm = init_llm(config)
    report_lines = ["# 第二步：环境条件核验"]

    for criterion in criteria_list:
        code_match = re.match(r"([A-Z]{2,}\s*\d{3,4}-\d{4})", criterion)
        if not code_match:
            report_lines.append(f"⚠️ 未识别的依据格式：{criterion}")
            continue
        code = code_match.group(1).strip()

        # 使用完整关键词查询语义向量（包含广州实验室）
        query_text = f"{criterion} 广州实验室"
        query_emb = embed_model.encode([query_text]).tolist()
        result = collection.query(query_embeddings=query_emb, n_results=10)

        matched_docs = result["documents"][0]
        matched_metas = result["metadatas"][0]

        db_entries = []
        for doc, meta in zip(matched_docs, matched_metas):
            db_entries.append({
                "INSTRUMENT_NAME": meta.get("仪器名称", ""),
                "FILE_CODE": meta.get("FILE_CODE", ""),
                "FILE_NAME": meta.get("FILE_NAME", ""),
                "温度要求": meta.get("温度要求", ""),
                "相对湿度要求": meta.get("相对湿度要求", ""),
                "最大温度变化范围": meta.get("最大温度变化范围", ""),
                "认可组织": meta.get("认可组织", ""),
            })

        # 只保留广州实验室的记录
        db_entries = [rec for rec in db_entries if rec["认可组织"] == "广州实验室"]

        if not db_entries:
            report_lines.append(f"❌ {code} 在广州实验室没有匹配记录")
            continue

        # 输出向量数据库检索结果
        report_lines.append(f"## 依据 {code} 向量数据库检索结果：")
        report_lines.append("| 仪器名称 | 文件编号 | 文件名称 | 温度要求 | 湿度要求 | 最大温差 | 认可组织 |")
        report_lines.append("| --- | --- | --- | --- | --- | --- | --- |")
        for rec in db_entries:
            report_lines.append(
                f"| {rec['INSTRUMENT_NAME']} | {rec['FILE_CODE']} | {rec['FILE_NAME']} | "
                f"{rec['温度要求']} | {rec['相对湿度要求']} | {rec['最大温度变化范围']} | {rec['认可组织']} |"
            )

        # 调用 LLM 判断
        llm_result = verify_with_llm(llm, criterion, current_temp, current_hum, db_entries)
        report_lines.append(f"\n## 依据 {code} 核验结果：\n{llm_result}\n")

    return "\n".join(report_lines)

# ========== 主执行函数 ==========
def main():
    json_file = "2GB25009792-0001.json"  # 输入 JSON 文件
    cfg = Config()

    print(f"📂 正在加载证书：{json_file}")
    env_report = check_environment(json_file, cfg)
    print("\n" + env_report)

    file_stem = Path(json_file).stem

    # 2. 定义输出目录 (./reports)
    output_dir = "./reports"  # 或者使用 Config.OUTPUT_DIR
    os.makedirs(output_dir, exist_ok=True)

    # 3. 拼接最终路径: ./reports/temperature_report_xxxxx.md
    report_path = os.path.join(output_dir, f"temperature_report_{file_stem}.md")

    # 4. 写入文件
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(env_report)

    # 5. 打印结果 (使用 resolve/abspath 获取绝对路径)
    print(f"\n📝 核验报告已生成：{Path(report_path).resolve()}")

    # ---------------------------------------------------------
    # 修改结束
    # ---------------------------------------------------------


if __name__ == "__main__":
    main()

