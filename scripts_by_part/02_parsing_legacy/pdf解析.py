import pdfplumber
import json
import re
from copy import deepcopy
from pathlib import Path
from openai import OpenAI

# ========== 配置 ==========
PDF_PATH = "2GB25009792-0001.pdf"
# 根据输入 PDF 自动生成输出 JSON 文件名
OUTPUT_JSON = str(Path(PDF_PATH).with_suffix(".json"))

API_KEY = ""  # ⚠️ 替换成你自己的
API_BASE = "https://api.deepseek.com/v1"

client = OpenAI(api_key=API_KEY, base_url=API_BASE)

CHUNK_SIZE = 8000


# ========== 提取 PDF 文本 ==========
def extract_pdf_text(pdf_path):
    text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                text += t + "\n"
    return text


# ========== 构造提示词 ==========
def build_prompt(chunk_text, chunk_id):
    return f"""
你是一名计量校准文档解析专家。请阅读以下 CNAS 校准证书文本（第 {chunk_id} 段），
并严格输出 JSON 结构，格式如下（仅输出 JSON）：

{{
  "properties": {{
    "证书列表": {{
      "items": {{
        "properties": {{
          "INSTRUMENT_NAME": "...",
          "型号": "...",
          "制造厂": "...",
          "委托单位名称": "...",
          "客户地址": "...",
          "管理号": "...",
          "机身号": "...",
          "证书编号": "...",
          "校准人": "...",
          "核验人": "...",
          "签发人": "...",
          "校准依据": ["..."],
          "温度": "...",
          "相对湿度": "...",
          "签发日期": "...",
          "有效日期": "...",
          "证书类型": "...",
          "证书状态": "...",
          "认可实验室": "...",
          "证书结论": "...",
          "是否CNAS": "...",
          "U_ATTR": "...",
          "专业": "...",
          "专业室": "...",
          "打印要求": ["..."],
          "客户要求": [],
          "校准地点": [],
          "建议校准周期": "...",
          "依据参数": {{
            "测量参数": [
              {{
                "...": {{
                  "量程": "...",
                  "标准值": "...",
                  "指示值": "...",
                  "误差": "...",
                  "允许误差": "...",
                  "结论": "...",
                  "U(k=2)": "..."
                }}
              }}
            ]
          }}
        }}
      }}
    }}
  }}
}}

要求：
1. 仅返回 JSON。
2. 单位 (V, A, Ω, MHz) 必须保留。
3. 数值表达式如 “50×100” 请计算后写结果（保留单位）。
4. 该段中未出现的字段写 null。

【第 {chunk_id} 段文本】
-------------------
{chunk_text}
-------------------
"""


# ========== 调用大模型（新版 SDK） ==========
def call_llm(prompt):
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=4096,
        )
        content = response.choices[0].message.content
        match = re.search(r"\{[\s\S]+\}", content)
        return json.loads(match.group(0)) if match else None
    except Exception as e:
        print(f"❌ LLM 调用失败：{e}")
        return None


# ========== JSON 验证与补齐 ==========
def validate_and_fix_json(data):
    required_keys = [
        "INSTRUMENT_NAME", "型号", "制造厂", "委托单位名称", "客户地址", "管理号", "机身号",
        "证书编号", "校准人", "核验人", "签发人", "校准依据", "温度", "相对湿度",
        "签发日期", "有效日期", "证书类型", "证书状态", "认可实验室", "证书结论",
        "是否CNAS", "U_ATTR", "专业", "专业室", "打印要求", "客户要求", "建议校准周期", "依据参数"
    ]

    try:
        props = data["properties"]["证书列表"]["items"]["properties"]
    except KeyError:
        print("⚠️ JSON 结构异常，已尝试修复。")
        data = {
            "properties": {"证书列表": {"items": {"properties": {}}}}
        }
        props = data["properties"]["证书列表"]["items"]["properties"]

    for key in required_keys:
        if key not in props:
            props[key] = None

    if props.get("校准依据") and isinstance(props["校准依据"], str):
        props["校准依据"] = [props["校准依据"]]
    if not props.get("依据参数"):
        props["依据参数"] = {"测量参数": []}

    return data


# ========== 主程序 ==========
def main():
    print("📘 正在读取 PDF...")
    pdf_text = extract_pdf_text(PDF_PATH)
    print(f"✅ 提取完成，文本长度：{len(pdf_text)} 字符")

    chunks = [pdf_text[i:i + CHUNK_SIZE] for i in range(0, len(pdf_text), CHUNK_SIZE)]
    print(f"✂️ 自动分为 {len(chunks)} 段。")

    merged_data = None

    for i, chunk in enumerate(chunks, 1):
        print(f"\n💬 调用模型解析第 {i}/{len(chunks)} 段...")
        prompt = build_prompt(chunk, i)
        data = call_llm(prompt)

        if not data:
            print(f"⚠️ 第 {i} 段返回空，跳过。")
            continue

        data = validate_and_fix_json(data)

        if merged_data is None:
            merged_data = deepcopy(data)
        else:
            try:
                new_params = data["properties"]["证书列表"]["items"]["properties"]["依据参数"]["测量参数"]
                merged_params = merged_data["properties"]["证书列表"]["items"]["properties"]["依据参数"]["测量参数"]
                merged_params.extend(new_params)
            except Exception as e:
                print(f"⚠️ 合并第 {i} 段失败: {e}")

    if not merged_data:
        print("❌ 所有分段均解析失败。")
        return

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(merged_data, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 解析完成！结果已保存到：{OUTPUT_JSON}")


if __name__ == "__main__":
    main()

