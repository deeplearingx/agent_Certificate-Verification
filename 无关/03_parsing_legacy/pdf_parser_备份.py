import pdfplumber
import json
import re
import os
import time
from copy import deepcopy
from pathlib import Path
from openai import OpenAI
from concurrent.futures import ThreadPoolExecutor, as_completed

# ========== 配置 ==========
BASE_DIR = Path(r"D:\workspace\ai大模型开发课\文档核验\work_pdf\local_pdf")
OUT_DIR = Path(r"D:\workspace\ai大模型开发课\文档核验\work_pdf\local_json")
PDF_FILENAME = "1GA25003260-0015.pdf"
PDF_PATH = str(BASE_DIR / PDF_FILENAME)
OUT_PATH = str(OUT_DIR / PDF_FILENAME)

if not os.path.exists(OUT_DIR):
    os.makedirs(OUT_DIR)

if not os.path.exists(PDF_PATH):
    print(f"❌ 错误：找不到文件 {PDF_PATH}")
    # exit(1)

OUTPUT_JSON = str(Path(OUT_PATH).with_suffix(".json"))
FAILED_LOG_JSON = str(Path(OUT_PATH).stem + "_failed_pages.json")  # 记录彻底失败的页码

API_KEY = ""
API_BASE = "https://api.deepseek.com/v1"
MAX_WORKERS = 5

client = OpenAI(api_key=API_KEY, base_url=API_BASE)


# ========== 1. 按页提取 PDF 文本 ==========
def extract_text_by_page(pdf_path):
    pages_data = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                text = page.extract_text(x_tolerance=1, y_tolerance=3)
                if text:
                    pages_data.append((i + 1, text))
    except Exception as e:
        print(f"❌ 读取PDF失败: {e}")
        return []
    return pages_data


# ========== 2. 构造提示词 (保持不变) ==========
def build_prompt(page_text, page_num):
    return f"""
你是一名计量校准文档解析专家。这是 PDF 的第 {page_num} 页。
请提取该页中的**基本信息**和**校准结果表格数据**。

请严格输出 JSON 结构，格式如下：

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
          "接收日期": "...",
          "校准日期": "...",
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
          "温度_内页": "...",
          "相对湿度_内页": "...",
          "依据参数_中间数据": [
              {{
                "项目名称": "例如：8 方波上升时间",
                "数据明细": {{
                  "功能": "此处填第一列内容 (如 Rise Time)",
                  “实际表头Key(如频率/量程)": "...",
                  "标称值": "...",
                  "标准值": "...",
                  "误差": "...",
                  "允许误差": "...",
                  "结论": "..."
                }}
              }}
          ]
        }}
      }}
    }}
  }}
}}

**重要解析规则：**

1. **排除项**：**跳过“本次检定所使用的主要测量标准”表格**。

2. **【核心】项目名称唯一性**：
   - 提取 "项目名称" 时，**必须包含前面的章节编号**（如有）。
   - **错误示例**："射频信号载波频率" (会导致不同章节的数据混淆)。
   - **正确示例**："3.1 射频信号载波频率" 或 "5.1 射频信号载波频率"。
   - 如果没有编号，则使用完整的标题名称。

3. **通用首列处理规则**：
   - 表格的第一列通常是“测试点描述”、“参数名”或“功能”。
   - **请将第一列的文本内容统一填入 '功能' (Function) 字段中**。
   - **严禁**将第一列的文本直接作为 JSON 的 Key。

4. **动态表头与空值过滤**：
   - **Key 获取**：严格照抄表格顶部的实际表头（包含括号内的英文/单位）作为 Key。
   - **空值剔除**：如果某一行在某一列（如“标称值”）完全为空或无数据，**请不要在 JSON 对象中生成该 Key**，不要输出空字符串 ""。


5. 多值拆行规则：
   - 如果一行中并排出现了多个测量点（例如：同一行写了 50%, 20%, 80%），**必须拆分为多行数据**。
   - 【严禁嵌套】：'数据明细' 字段必须是对象(Object/Dict)，**绝对不能是数组(List/Array)**。
   - 如果一个项目有多个数据点，请生成多个包含相同 '项目名称' 的独立对象。
...
6. **数值对齐**：
   - 请确保提取的数值与其对应的表头列名垂直对齐。

7. **【关键】数值单位强制绑定规则**：
   - **目标**：所有“标称值”、“标准值”、“误差”、“允许误差”、“U”等字段的值，**必须带有单位**（除非该物理量本身无单位）。
   - **场景 A (单位在数值旁)**：如果原文是 "10.00 V"，直接提取 "10.00 V"。
   - **场景 B (单位在表头)**：如果表头写着 "Standard Value (MHz)"，而表格里只写 "10.000"，**你必须手动将单位拼接上去**，输出 "10.000 MHz"。
   - **场景 C (单位在首列)**：如果第一列写了 "Range: 10 V"，后续列只有数字，请根据上下文补全单位。
   - **禁止**输出裸数字（如 "10.000"），除非原文完全找不到任何单位暗示。
   - **百分号**：如果原文是 %，必须保留（如 "-0.03 %"）。
   
8. **环境温度与湿度**：
  -温度与湿度可能会出先在两个地方。
  -第一次出现时，直接填入温度、相对湿度的字段中。
  -第二次出现时，分别填入温度_内页、相对湿度_内页的字段中。
【第 {page_num} 页文本】
---------------------
{page_text}
---------------------
"""


##处理内页和封页两次出现温度、湿度
def pick_env_fields(final_metadata_props: dict, props: dict):
    """
    处理温湿度出现两次的情况：
    - 第一次出现：写入 温度 / 相对湿度
    - 第二次出现：写入 温度_内页 / 相对湿度_内页

    LLM 可能输出字段名：环境温度/相对湿度，或 温度/相对湿度，统一从候选里拿值。
    """
    # 候选 key（兼容不同命名）
    temp_val = props.get("温度") or props.get("环境温度")
    rh_val = props.get("相对湿度") or props.get("湿度")

    if temp_val:
        if final_metadata_props.get("温度") is None:
            final_metadata_props["温度"] = temp_val
        elif final_metadata_props.get("温度_内页") is None:
            final_metadata_props["温度_内页"] = temp_val

    if rh_val:
        if final_metadata_props.get("相对湿度") is None:
            final_metadata_props["相对湿度"] = rh_val
        elif final_metadata_props.get("相对湿度_内页") is None:
            final_metadata_props["相对湿度_内页"] = rh_val

def merge_metadata_in_order(page_meta_map: dict):
    """
    按页码顺序合并元数据，确保“第一次/第二次出现”的语义稳定。
    """
    #先给温度、湿度等值赋空，方便后续处理
    final_metadata_props = {
        "温度": None,
        "相对湿度": None,
        "温度_内页": None,
        "相对湿度_内页": None,
    }

    for p_num in sorted(page_meta_map.keys()):
        props = page_meta_map[p_num]
        if not isinstance(props, dict) or not props:
            continue

        # ✅ 先处理温湿度双出现（不能交给通用 merge）
        pick_env_fields(final_metadata_props, props)

        # ✅ 再合并其他字段：首次出现优先
        for key, value in props.items():
            if key == "依据参数_中间数据":
                continue

            # 避免温湿度被普通逻辑覆盖/重复写
            if key in ("温度", "环境温度", "相对湿度", "湿度", "温度_内页", "相对湿度_内页"):
                continue

            if value is None or value == "null":
                continue

            if key not in final_metadata_props or not final_metadata_props.get(key):
                final_metadata_props[key] = value

    return final_metadata_props

# ========== 修改后的 call_llm ==========
def call_llm(prompt):
    # 1. 在线程内部初始化 Client，避免全局锁竞争
    local_client = OpenAI(api_key=API_KEY, base_url=API_BASE)

    try:
        # 2. 增加 timeout 参数 (单位秒)，例如 60秒或 120秒
        # 这样即使服务器卡死，也会在60秒后报错重试，而不是无限等待
        response = local_client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=8192,
            response_format={"type": "json_object"},
            timeout=60  # <--- 【关键修改】设置超时时间
        )
        content = response.choices[0].message.content

        # ... (后续 JSON 解析逻辑保持不变)
        start_idx = content.find('{')
        if start_idx == -1: return None
        json_str = content[start_idx:]

        # ... (JSON修复逻辑保持不变) ...
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass

        quote_count = json_str.count('"') - json_str.count('\\"')
        if quote_count % 2 != 0: json_str += '"'
        stack = []
        for char in json_str:
            if char == '{':
                stack.append('}')
            elif char == '[':
                stack.append(']')
            elif char == '}' or char == ']':
                if stack and stack[-1] == char: stack.pop()
        while stack: json_str += stack.pop()

        try:
            return json.loads(json_str)
        except:
            return None
    except Exception as e:
        print(f"❌ API请求错误: {e}")
        return None


# ========== 4. 容错提取 ==========
def extract_valid_properties(data):
    if not data: return {}


    # ✅ 先按你期望的标准结构直接拿
    try:
        props = data["properties"]["证书列表"]["items"]["properties"]
        if isinstance(props, dict) and props:
            return props
    except Exception:
        pass

    # 兜底：再递归找
    target_keys = ["依据参数_中间数据", "INSTRUMENT_NAME", "证书编号", "校准依据"]

    def recursive_search(obj):
        if isinstance(obj, dict):
            for k in obj.keys():
                if k in target_keys: return obj
            for v in obj.values():
                res = recursive_search(v)
                if res: return res
        elif isinstance(obj, list):
            for item in obj:
                res = recursive_search(item)
                if res: return res
        return None

    found = recursive_search(data)
    if not found and isinstance(data, dict): return data
    return found if found else {}


def fix_llm_json_structure(data):
    """
    自动修复 LLM 返回的脏数据结构。
    核心功能：如果 '数据明细' 是列表，将其展平为多行独立的记录。
    例如：
    { "项目名称": "A", "数据明细": [{"val": 1}, {"val": 2}] }
    转换为：
    [ { "项目名称": "A", "数据明细": {"val": 1} }, { "项目名称": "A", "数据明细": {"val": 2} } ]
    """
    if not data:
        return data

    def recursive_fix(obj):
        if isinstance(obj, dict):
            # 🎯 核心修复逻辑
            if "依据参数_中间数据" in obj and isinstance(obj["依据参数_中间数据"], list):
                original_rows = obj["依据参数_中间数据"]
                fixed_rows = []
                was_fixed = False

                for row in original_rows:
                    if not isinstance(row, dict):
                        continue

                    details = row.get("数据明细")
                    p_name = row.get("项目名称", "未知项目")

                    # 如果数据明细是列表，说明发生了嵌套，需要展平
                    if isinstance(details, list):
                        was_fixed = True
                        for sub_detail in details:
                            # 复制父级属性（如项目名称），绑定单个明细
                            new_row = row.copy()
                            new_row["数据明细"] = sub_detail
                            fixed_rows.append(new_row)
                    else:
                        # 正常结构，直接保留
                        fixed_rows.append(row)

                # 替换原有的列表
                obj["依据参数_中间数据"] = fixed_rows
                if was_fixed:
                    print(f"🔧 [Auto-Fix] 已自动修复 {len(original_rows)} -> {len(fixed_rows)} 行数据结构嵌套问题。")

            # 继续递归遍历子节点
            for k, v in obj.items():
                recursive_fix(v)

        elif isinstance(obj, list):
            for item in obj:
                recursive_fix(item)

    # 为了安全，使用深拷贝或直接操作（这里直接操作即可，因为是临时数据）
    try:
        recursive_fix(data)
    except Exception as e:
        print(f"⚠️ [Fix Failed] 尝试修复数据结构时出错: {e}")

    return data

# ========== 5. 严格校验函数 (核心修改) ==========
def validate_is_clean_data(data):
    """
    严格校验数据质量。
    如果发现 '数据明细' 是列表 (List)，直接判定为脏数据，返回 False。
    """
    if not data:
        return False

    target_rows = []

    # 递归提取所有的数据行
    def find_rows(obj):
        if isinstance(obj, dict):
            if "依据参数_中间数据" in obj and isinstance(obj["依据参数_中间数据"], list):
                target_rows.extend(obj["依据参数_中间数据"])
            for v in obj.values():
                find_rows(v)
        elif isinstance(obj, list):
            for item in obj:
                find_rows(item)

    find_rows(data)

    if not target_rows:
        # 如果是空数据页，视作通过（或者根据业务需求视作失败）
        # 这里假设没有数据行也是合法的（可能是封面页）
        return True

    for row in target_rows:
        if not isinstance(row, dict): continue
        details = row.get("数据明细")

        # 🚨 宁缺毋滥核心：如果数据明细是 List，直接杀掉，要求重试
        if isinstance(details, list):
            # print(f"DEBUG: 发现脏数据结构 (List detected in details)")
            return False

        if not isinstance(details, dict):
            return False

    return True


def reorganize_data_simple(all_rows):
    """
    因为在入口处已经严格过滤了 List 类型的数据，
    这里不需要再做复杂的展平 (Flatten) 逻辑，直接对齐即可。
    包含：列对齐 + 空列清洗
    """
    grouped_data = {}
    project_headers_list = {}

    # 1. 收集表头
    for row in all_rows:
        p_name = row.get("项目名称", "其他参数")
        details = row.get("数据明细", {})  # 经过校验，这里一定是 Dict

        if p_name not in project_headers_list:
            project_headers_list[p_name] = []
        for k in details.keys():
            if k not in project_headers_list[p_name]:
                project_headers_list[p_name].append(k)

    # 2. 初始化结构
    for p_name, headers_list in project_headers_list.items():
        grouped_data[p_name] = {h: [] for h in headers_list}

    # 3. 填入数据
    for row in all_rows:
        p_name = row.get("项目名称", "其他参数")
        details = row.get("数据明细", {})

        if p_name in grouped_data:
            for header in grouped_data[p_name].keys():
                val = details.get(header, "")

                # 🛡️【防御性修改】防止 None 变成 "None" 字符串
                if val is None:
                    val = ""

                grouped_data[p_name][header].append(str(val))

    # 4. 清除空列 (Logic confirmed ✅)
    for p_name, columns in list(grouped_data.items()):
        for col_key, col_values in list(columns.items()):
            # 如果这一列的值全是空字符串，则删除该列
            if all(v.strip() == "" for v in col_values):
                # print(f"🧹 [Clean] 移除全空列: {p_name} -> {col_key}") # 可选：调试日志
                del grouped_data[p_name][col_key]

    return grouped_data


# ========== 7. 单页处理函数 (3次重试，不过则丢弃) ==========
def process_single_page(page_data):
    page_num, page_text = page_data
    print(f"🚀 [Start] 开始解析第 {page_num} 页...")

    if len(page_text) < 50:
        print(f"⚠️ [Skip] 第 {page_num} 页内容过少，跳过。")
        return page_num, None

    prompt = build_prompt(page_text, page_num)

    max_retries = 3

    for attempt in range(1, max_retries + 1):
        data = call_llm(prompt)

        if data:
            # 🔥【新增】在校验前，先尝试自动修复结构
            data = fix_llm_json_structure(data)

            # 🔥 严格校验：经过修复后，如果还是脏数据，才当作失败
            if validate_is_clean_data(data):
                print(f"✅ [Done] 第 {page_num} 页解析成功 (第 {attempt} 次尝试)")
                return page_num, data
            else:
                print(
                    f"⚠️ [Dirty Data] 第 {page_num} 页数据结构仍不合规，拒绝接收。正在重试 {attempt}/{max_retries}...")
        else:
            print(f"⚠️ [Error] 第 {page_num} 页 API 调用失败，正在重试 {attempt}/{max_retries}...")

    # 💀 三次都失败
    print(f"❌ [Drop] 第 {page_num} 页多次重试仍无法生成合规数据，该页将被**丢弃**。")
    return page_num, None


# ========== 主程序 ==========
def main():
    start_time = time.time()
    print(f"📘 正在读取 PDF: {PDF_PATH}")
    pages = extract_text_by_page(PDF_PATH)

    if not pages:
        print("❌ 未提取到文本。")
        return

    print(f"📄 共读取到 {len(pages)} 页，准备并发解析 (线程数: {MAX_WORKERS})...")

    # ✅ 改动1：先把每页的 props 收集起来，最后按页码合并
    page_meta_map = {}       # {page_num: props}
    page_results_map = {}    # {page_num: rows}
    failed_pages = []        # 记录哪些页码彻底丢弃了

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_page = {executor.submit(process_single_page, page): page[0] for page in pages}

        for future in as_completed(future_to_page):
            page_num, data = future.result()

            # 如果是 None，说明该页质量不行，直接丢弃
            if data is None:
                failed_pages.append(page_num)
                continue

            props = extract_valid_properties(data)
            if not props:
                continue

            # ✅ 改动2：这里不再立即 merge 到 final_metadata_props
            #         只保存每页的 props，后面按页码顺序统一合并
            page_meta_map[page_num] = props

            # 收集表格行
            rows = props.get("依据参数_中间数据", [])
            if rows:
                page_results_map[page_num] = rows

    # 按页码顺序合并表格行
    sorted_page_nums = sorted(page_results_map.keys())
    all_extracted_rows = []
    for p_num in sorted_page_nums:
        all_extracted_rows.extend(page_results_map[p_num])

    print(f"\n🔄 解析结束，耗时 {time.time() - start_time:.2f} 秒。")

    # 报告丢弃情况
    if failed_pages:
        print(f"❌ 警告：以下页码因无法生成合规数据已被丢弃，请人工核查: {sorted(failed_pages)}")
        with open(FAILED_LOG_JSON, "w") as f:
            json.dump({"failed_pages": sorted(failed_pages)}, f)

    print("🔄 正在重组数据...")

    # ✅ 改动3：按页码顺序合并元数据（温湿度“双出现”在这里稳定解决）
    final_metadata_props = merge_metadata_in_order(page_meta_map)

    # 使用纯净版重组函数
    pivoted_params = reorganize_data_simple(all_extracted_rows)
    final_metadata_props["依据参数"] = pivoted_params

    final_json = {
        "properties": {
            "证书列表": {
                "items": {
                    "properties": final_metadata_props
                }
            }
        }
    }

    # ✅ 建议：把内页字段也补齐，方便下游知道有没有抽到
    required_keys = [
        "INSTRUMENT_NAME", "证书编号", "校准依据",
        "温度", "相对湿度", "签发日期",
        "温度_内页", "相对湿度_内页"
    ]
    for k in required_keys:
        if k not in final_metadata_props:
            final_metadata_props[k] = None

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(final_json, f, ensure_ascii=False, indent=2)

    print(f"✅ 全部完成！结果已保存到：{OUTPUT_JSON}")


if __name__ == "__main__":
    main()
