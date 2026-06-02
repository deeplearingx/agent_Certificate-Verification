import json
import re
import os
import requests
from pathlib import Path
from config.settings import get_app_config
# ========== 配置 ==========
class Config:
    _app = get_app_config()
    OUTPUT_DIR = str(_app.reports_dir)
    USE_LLM_VERIFICATION = _app.use_llm_verification
    DEEPSEEK_API_KEY = _app.api_key
    DEEPSEEK_API_BASE = _app.api_base
    BASE_DIR = _app.local_json_dir

# ========== 工具函数 ==========
def normalize(value, default="N/A"):
    """将 null、空字符串、空数组 或严重乱码视为缺失"""
    if value is None:
        return default
    if isinstance(value, str):
        v = value.strip()
        if not v or v == "/":
            return default
        return v
    if isinstance(value, list) and len(value) == 0:
        return default
    return str(value)


def generate_report_filename(file_path: str, output_dir: str | None = None):
    """根据【输入文件名】生成报告文件名"""
    file_stem = Path(file_path).stem
    safe = re.sub(r"[^\w\-]", "_", file_stem)
    base_output_dir = output_dir or Config.OUTPUT_DIR
    os.makedirs(base_output_dir, exist_ok=True)
    return os.path.join(base_output_dir, f"certificate_integrity_{safe}.md")


# ========== DeepSeek 调用模块 ==========
def verify_with_deepseek(fields: dict, cert_no: str, cfg=None) -> str:
    """
    调用 DeepSeek API 进行字段语义合理性核验。
    """
    # 强化 Prompt，明确环境条件的重要性
    system_prompt = (
        "你是一名资深计量校准核验专家。你的任务是对校准证书的关键信息字段进行逻辑核验。\n"
        "### 核心规则\n"
        "1. **完整性**：检查字段是否有乱码、空值或“N/A”。\n"
        "2. **一致性**：检查仪器名称、型号、制造商是否逻辑匹配（如 Keysight 33511B 是合理的）。\n"
        "3. **致命缺陷判定（环境条件）**：\n"
        "   - 根据 CNAS-CL01 要求，**温度**和**相对湿度**为必须要素。\n"
        "   - 如果这两个字段缺失、为“N/A”或没有单位，**必须**在建议栏标记“严重不符合：环境数据缺失，证书无效”，并判定结果为“异常”。\n\n"
        "请直接输出 Markdown 表格，包含列：| 字段名 | 内容 | 核验结果 | 建议 |"
    )

    user_prompt = f"证书编号：{cert_no}\n待核验字段如下：\n"
    for name, val in fields.items():
        user_prompt += f"- {name}：{val}\n"

    user_prompt += "\n请根据上述规则生成核验表格。"

    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.1,  # 降低温度以保证严谨性
        "max_tokens": 1024
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {getattr(cfg, 'API_KEY', None) or Config.DEEPSEEK_API_KEY}"
    }

    try:
        api_base = getattr(cfg, "API_BASE", None) or Config.DEEPSEEK_API_BASE
        resp = requests.post(f"{api_base}/chat/completions", json=payload, headers=headers, timeout=30)
        resp.raise_for_status()
        result = resp.json()
        return result["choices"][0]["message"]["content"]
    except Exception as e:
        return f"> ⚠️ DeepSeek 调用失败: {str(e)}"



# ========== 核验证书完整性主函数 ==========
def check_certificate_integrity(json_file: str, cfg=None):
    # 1. 读取 JSON
    with open(json_file, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    # 2. 路径提取 (增加容错)
    try:
        props = raw_data["properties"]["证书列表"]["items"]["properties"]
    except KeyError:
        print("⚠️ JSON 结构解析失败，尝试直接读取根目录...")
        props = raw_data

    # ================= 新增 CNAS 阻断逻辑 =================
    is_cnas = normalize(props.get("是否CNAS"))

    # 检查逻辑：如果为空、N/A 或不是 "是"，则终止
    if is_cnas not in ["是", "Yes", "TRUE"]:
        print(f"🛑 检测到非 CNAS 证书 (标记为: {is_cnas})，终止核验。")

        # 生成简短的终止报告
        report_lines = [
            "# 🛑 核验终止报告",
            f"**证书文件**：{os.path.basename(json_file)}",
            f"**证书编号**：{normalize(props.get('证书编号'))}",
            "",
            "## ⛔ 严重不符合",
            f"> **原因**：该证书未标记为 CNAS 认可证书（'是否CNAS' 字段值为 '{is_cnas}'）。",
            "> **结论**：超出核验范围，系统拒绝处理。",
        ]

        # 保存并返回
        report_path = generate_report_filename(json_file, getattr(cfg, "OUTPUT_DIR", None))
        with open(report_path, "w", encoding="utf-8") as f:
            f.write("\n".join(report_lines))
        return "\n".join(report_lines)
    # ======================================================

    # 3. 提取并规范化字段 (只有通过 CNAS 检查才继续执行)
    instrument_name = normalize(props.get("INSTRUMENT_NAME") or props.get("仪器名称"))
    model_name = normalize(props.get("型号") or props.get("型号规格"))
    manufacturer = normalize(props.get("制造厂") or props.get("制造商"))
    serial_no = normalize(props.get("机身号") or props.get("序列号"))
    manage_no = normalize(props.get("管理号"))
    client_name = normalize(props.get("委托单位名称") or props.get("委托单位") or props.get("客户名称"))
    cert_no = normalize(props.get("证书编号"), default="unknown")

    # 环境数据
    temp_raw = normalize(props.get("温度"))
    hum_raw = normalize(props.get("相对湿度") or props.get("湿度"))

    report_cycle = normalize(props.get("建议校准周期"))
    criteria_list = props.get("校准依据") or []

    # 4. 构造报告 (后续逻辑保持不变)
    report_lines = [
        "# 🧾 校准证书完整性核验报告",
        f"**证书文件**：{os.path.basename(json_file)}",
        f"**是否CNAS**：✅ {is_cnas}",  # 在报告里确认一下
        "",
        "## 一、被测仪器信息",
        f"- 仪器名称：{instrument_name}",
        f"- 型号规格：{model_name}",
        f"- 制造商：{manufacturer}",
        f"- 机身号：{serial_no}",
        f"- 管理号：{manage_no}",
        f"- 委托单位名称：{client_name}",
        f"- 建议校准周期：{report_cycle}",
        f"- 温度：{temp_raw}",
        f"- 相对湿度：{hum_raw}",
        "",
        "## 二、字段完整性检测 (本地规则)",
    ]

    # 定义待查字典
    fields_to_check = {
        "仪器名称": instrument_name,
        "型号规格": model_name,
        "制造商": manufacturer,
        "机身号": serial_no,
        "管理号": manage_no,
        "委托单位名称": client_name,
        "温度": temp_raw,
        "相对湿度": hum_raw,
    }

    missing_count = 0
    for key, val in fields_to_check.items():
        # 【修正】这里增加了 key 的显示，之前的代码只显示 val
        if val in ["N/A", ""]:
            report_lines.append(f"❌ **{key}**：缺少，已填充为“N/A”")
            missing_count += 1
        else:
            report_lines.append(f"✅ **{key}**：完整 ({val})")

    # 校准依据检测
    report_lines.append("")
    report_lines.append("## 三、校准依据格式检查")
    if not criteria_list:
        report_lines.append("❌ 缺少【校准依据】")
    else:
        for c in criteria_list:
            if re.match(r"[A-Z]{2,}\s*\d{3,4}(-\d{4})?", c):
                report_lines.append(f"✅ 格式正确：{c}")
            else:
                report_lines.append(f"⚠️ 格式存疑：{c}")

    # 5. DeepSeek 核验增强
    use_llm_verification = getattr(cfg, "USE_LLM_VERIFICATION", Config.USE_LLM_VERIFICATION)
    if use_llm_verification:
        report_lines.append("")
        report_lines.append("## 四、DeepSeek 智能核验结果")
        print("🤖 正在调用 DeepSeek 进行深度分析...")

        # 将上面准备好的字典传给 LLM
        llm_feedback = verify_with_deepseek(fields_to_check, cert_no, cfg=cfg)
        report_lines.append(llm_feedback)

    # 综合结论
    report_lines.append("")
    report_lines.append("## 五、综合结论")
    if temp_raw == "N/A" or hum_raw == "N/A":
        report_lines.append("> 🛑 **不推荐通过**：缺少必要的环境条件（温度/湿度），证书无效。")
    elif missing_count > 0:
        report_lines.append("> ⚠️ **建议补充**：存在缺失的非关键字段（如管理号）。")
    else:
        report_lines.append("> ✅ **通过**：关键信息完整。")

    # 6. 保存报告
    report_path = generate_report_filename(json_file, getattr(cfg, "OUTPUT_DIR", None))
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))

    print(f"📝 核验报告已生成：{report_path}")
    return "\n".join(report_lines)


# ========== 主程序 ==========
def main():
    JSON_FILE = "1GA25005017-0001.json"
    cfg = Config()
    JSON_PATH = str(cfg.BASE_DIR / JSON_FILE)
    print(JSON_PATH)
    if not os.path.exists(JSON_PATH):
        print(f"❌ 找不到文件：{JSON_FILE}")
        return

    print(f"📂 正在加载证书：{JSON_FILE}")
    report = check_certificate_integrity(JSON_PATH)
    print("\n" + report)


if __name__ == "__main__":
    main()
