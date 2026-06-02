# param_check.py 代码结构分析

> 最后更新：2026-03-18
> 分析文件：`param_check.py`
> 用途：CNAS校准证书参数核验核心模块

---

## 📋 目录

- [1. 整体架构](#1-整体架构)
- [2. 配置模块](#2-配置模块)
- [3. 工具函数模块](#3-工具函数模块)
  - [3.1 数值解析工具](#31-数值解析工具)
  - [3.2 单位换算工具](#32-单位换算工具)
  - [3.3 范围解析工具](#33-范围解析工具)
- [4. 语义匹配模块](#4-语义匹配模块)
- [5. 数据库检索模块](#5-数据库检索模块)
- [6. 核验逻辑模块](#6-核验逻辑模块)
- [7. 后处理模块](#7-后处理模块)
- [8. 主流程模块](#8-主流程模块)
- [9. 扩展指南](#9-扩展指南)

---

## 1. 整体架构

### 依赖关系
```python
param_check.py
├── config.settings (配置管理)
├── llm.client (LLM客户端)
└── core.semantic_basis_selector (语义匹配核心)
    ├── FirstCandidateDecider
    ├── infer_param_semantics
    └── select_basis_with_audit
```

### 主要流程
```
证书JSON → 收集参数 → 检索KB → 语义匹配 → 范围/误差/不确定度核验 → 后处理 → 生成报告
```

---

## 2. 配置模块

### Config 类 (行 24-38)
```python
class Config:
    DB_DIR = _app.cnas_db_dir           # ChromaDB目录
    COLLECTION = _app.cnas_collection   # 集合名称
    EMBED_MODEL_PATH = ...              # 嵌入模型路径
    API_KEY = ...                       # DeepSeek API Key
    MODEL = ...                         # 模型名称
    TEMPERATURE = ...                   # 温度参数
    MAX_TOKENS = ...                    # 最大token数
    TOPK = ...                          # 检索Top-K
    BATCH_SIZE = ...                    # 批处理大小
    max_workers = ...                   # 并发数
```

### 版本戳 (行 44-49)
```python
def _build_param_check_version_stamp() -> str:
    """生成代码版本戳，用于追踪修改"""
    # 返回格式: "param_check.py | mtime=YYYY-MM-DD HH:MM:SS | sha1=xxxxxx"
```

---

## 3. 工具函数模块

### 3.1 数值解析工具

#### 科学计数法解析 (行 53-381)
```python
SUPERSCRIPT_MAP = {  # Unicode上标映射
    '⁰': '0', '¹': '1', '²': '2', ...
}

def parse_unicode_sci_number(s: str) -> Optional[float]:
    """
    解析Unicode科学计数法
    支持格式: 6.6×10⁻⁹, 3.2x10⁻⁶, 1.0*10⁻³, 6.6x10^-9
    """
    # 先尝试解析^格式，再解析Unicode上标格式
```

#### 数值+单位解析 (行 384-466)
```python
def parse_value_with_unit(val_str, base_val=None, keep_sign: bool = False):
    """
    数值解析与单位折算工具 (增强版)

    功能:
    - 支持Unicode科学计数法
    - 支持单位前缀换算 (k/M/G/m/u/μ/n/p)
    - 支持相对不确定度换算 (%, Urel)
    - keep_sign=True 保留正负号

    扩展点:
    [ ] 支持更多单位类型
    [ ] 自定义单位换算表
    """
```

### 3.2 单位换算工具

#### 单位标准化 (行 200-212)
```python
CANONICAL_UNIT_MAP = {
    "thz": "THz", "ghz": "GHz", "mhz": "MHz", ...
}

def _normalize_unit_text(unit: str) -> str:
    """单位文本标准化"""
```

#### 单位倍率获取 (行 214-231)
```python
EXACT_UNIT_MULTIPLIERS = {
    "THz": 1e12, "GHz": 1e9, ...
}

def _unit_multiplier_from_text(unit: str) -> float:
    """从单位文本获取倍率"""
```

#### 时间单位专用换算 (行 572-586)
```python
def convert_time_unit(value: float, from_unit: str, to_unit: str) -> float:
    """
    时间单位专用换算
    支持: ns, us/μs, ms, s

    扩展点:
    [ ] 支持更多时间单位
    """
```

### 3.3 范围解析工具

#### 单边限值解析 (行 490-512)
```python
def parse_single_sided_limit(limit_str: str):
    """
    解析单边限值
    格式: "<-75", "<= -75.0 dBc/Hz", ">0.1", ">= +3"

    返回: (op, threshold) 或 None
    """
```

#### 区间限值解析 (行 515-569)
```python
def parse_range_limit(limit_str: str):
    """
    解析区间限值
    格式: "-0.2~+0.1", "(-0.2, +0.1)", "-0.2 ～ 0.1"

    特点:
    - 接受任意顺序的范围，自动处理为 [min, max]
    - 支持前缀操作符: ">1 ms～"

    扩展点:
    [ ] 支持更多分隔符
    """
```

#### 对称容差解析 (行 589-634)
```python
def parse_symmetric_limit(limit_str: str):
    """
    解析对称容差
    格式: "±0.1", "+/-0.1", "±(a~b)"

    返回: ("range", a, b) 或 ("limit", val) 或 None
    """
```

---

## 4. 语义匹配模块

### 相关文件
- `core/semantic_basis_selector.py` - 语义匹配核心

### 语义预过滤 (行 1351-1395)
```python
def _apply_semantic_basis_prefilter(
    kb_items: List[Dict[str, Any]],
    batch_params: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    应用语义基础选择器预过滤

    流程:
    1. 提取参数名/测量点文本/证书U
    2. infer_param_semantics 推断语义
    3. select_basis_with_audit 选择匹配的KB条目

    扩展点:
    [ ] 自定义语义推断规则
    [ ] 自定义候选选择策略
    """
```

### 参数名提取 (行 1313-1318)
```python
def _extract_param_name_for_semantic_prefilter(param: Dict[str, Any]) -> str:
    """提取参数名用于语义预过滤"""
    # 优先级: param_name -> 项目名称 -> 测量值 -> name
```

---

## 5. 数据库检索模块

### ChromaDB 检索 (行 3920-4045)
```python
def query_kb_entries(
    query_text: str,
    basis_code: Optional[str] = None,
    topk: int = 5,
    max_retries: int = 3,
) -> List[Dict[str, Any]]:
    """
    检索CNAS知识库条目

    流程:
    1. 加载ChromaDB集合
    2. 生成嵌入向量
    3. 检索Top-K条目
    4. 按依据代码过滤（如果提供）

    扩展点:
    [ ] 支持多种向量数据库
    [ ] 自定义检索策略
    """
```

### KB条目解析 (行 3902-3918)
```python
def parse_kb_entry(doc: str, meta: Dict[str, Any]) -> Dict[str, Any]:
    """
    解析KB条目

    返回字段:
    - measured: 被测量
    - measure_range_text: 测量范围文本
    - u_text: 不确定度文本
    - file_code: 文件编号
    - 等等...

    扩展点:
    [ ] 支持更多KB格式
    """
```

---

## 6. 核验逻辑模块

### 范围核验 (行 1398-1499)
```python
def verify_range_logic(measure_val, range_str):
    """
    范围核验逻辑

    特点:
    - 保留测量值原始token/单位
    - 支持 ±limit / ±(a~b) 对称范围
    - 智能检测单位不匹配 (如 dBm vs mV)

    扩展点:
    [ ] 自定义范围核验规则
    [ ] 更多单位组合的智能处理
    """
```

### 不确定度核验 (TODO)
```python
def verify_uncertainty_logic(measure_val, cert_u, kb_u):
    """
    不确定度核验逻辑

    功能:
    - 绝对不确定度比较
    - 相对不确定度转换与比较
    - 自动单位换算

    扩展点:
    [ ] 自定义不确定度换算规则
    """
```

### 误差核验 (TODO)
```python
def verify_error_logic(error_val, limit_val):
    """
    误差核验逻辑

    扩展点:
    [ ] 自定义误差判定规则
    """
```

---

## 7. 后处理模块

### KB缺失强制FAIL (行 4048-4125)
```python
def enforce_kb_missing_fail(md: str) -> str:
    """
    兜底修正：若表格行 KB编号=无/N/A，则判定必须 FAIL

    适配列: 序号, 测量点, KB编号, 证书匹配项, 范围, 证书误差, 允许误差, 证书U, KB_U, 判定, 说明

    扩展点:
    [ ] 自定义强制失败规则
    """
```

### 点位补全 (行 4128-4211)
```python
def enforce_point_id(md: str) -> str:
    """
    后处理 Markdown 表格中的【点位】列

    逻辑:
    - 如果点位为空 / N/A
    - 且测量点中出现 CHx / ch x / CH x
    - 则强制将点位补为标准化后的 CHx

    扩展点:
    [ ] 支持更多点位格式
    """
```

### 工具判定强制执行 (行 4214-4451)
```python
def enforce_uncertainty_by_tool(md: str) -> str:
    """
    后处理：逐行复算范围/误差/不确定度，确保表格判定与工具结果一致

    规则:
    - 任一工具返回 FAIL → 强制置为 FAIL
    - 三类工具均无 FAIL 且存在有效判定 → 置为 PASS
    - KB缺失等原因是 FAIL 且无工具可覆盖 → 保留 FAIL

    扩展点:
    [ ] 自定义工具判定优先级
    [ ] 更多核验工具集成
    """
```

---

## 8. 主流程模块

### 参数收集 (行 4454-4550)
```python
def collect_certificate_params(cert_root: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    兼容两种证书参数结构

    1) 新版（行式）：依据参数_中间数据 = [{项目名称, 数据明细{...}}, ...]
    2) 旧版（列式）：依据参数 = {项目: {列名: [..] 或 单值}, ...}

    扩展点:
    [ ] 支持更多证书格式
    """
```

### 主核验流程 (行 4550+)
```python
def verify_certificate_params(...) -> str:
    """
    主核验流程入口

    流程:
    1. 收集证书参数
    2. 参数分批处理
    3. 并发检索KB
    4. 语义匹配与预过滤
    5. 调用Agent进行核验
    6. 应用后处理
    7. 生成Markdown报告

    扩展点:
    [ ] 自定义分批策略
    [ ] 自定义报告格式
    """
```

---

## 9. 扩展指南

### 9.1 添加新的参数语义匹配

**位置**: `core/semantic_basis_selector.py`

```python
# 1. 在 infer_param_semantics 中添加新的判断分支
def infer_param_semantics(...):
    # ... 现有代码 ...

    # 新增：你的参数类型
    if _contains_any(text, ["你的关键词1", "你的关键词2"]):
        return ParamSemantic(
            task_intent="your_task_type",
            primary_quantity="your_quantity",
            unit_family="your_unit_family",
            ...
        )

# 2. 在 infer_kb_capability 中添加KB条目匹配
def infer_kb_capability(entry: Dict[str, Any]) -> KbCapability:
    # ... 现有代码 ...

    if measured_lower in {"你的参数名"}:
        return KbCapability(
            measured=measured,
            capability_target="your_target",
            ...
        )

# 3. 在 structured_prefilter 中添加匹配规则
# 在 wanted_targets 字典中添加
wanted_targets = {
    # ... 现有 ...
    ("your_task_type", "your_quantity"): {"your_target"},
}
```

### 9.2 添加新的单位换算

**位置**: `param_check.py` 第 59-144 行

```python
# 1. 在 EXACT_UNIT_MULTIPLIERS 中添加
EXACT_UNIT_MULTIPLIERS = {
    # ... 现有 ...
    "你的单位": 倍率,
}

# 2. 在 CANONICAL_UNIT_MAP 中添加单位标准化
CANONICAL_UNIT_MAP = {
    # ... 现有 ...
    "你的单位小写": "你的标准单位",
}

# 3. 在 VALUE_TOKEN_PATTERN 中添加单位匹配正则
VALUE_TOKEN_PATTERN = re.compile(
    r"([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s*"
    r"(...|你的单位|...)",  # 添加你的单位
    flags=re.IGNORECASE,
)
```

### 9.3 添加新的核验工具

**位置**: `param_check.py` 后处理模块之前

```python
def verify_your_custom_logic(param1, param2):
    """
    自定义核验工具

    返回 JSON 格式:
    {
        "status": "PASS|FAIL|REVIEW|ERROR",
        "reason": "说明文字",
        "calc_type": "your_type"
    }
    """
    # 实现你的逻辑
    return json.dumps({...})

# 然后在 enforce_uncertainty_by_tool 中集成
def enforce_uncertainty_by_tool(md: str) -> str:
    # ... 现有代码 ...

    # 添加调用你的工具
    if not is_missing_cell(your_param):
        try:
            your_res = verify_your_custom_logic(val1, val2)
            add_tool_note("你的工具判定", json.loads(your_res))
        except Exception as e:
            note_additions.append(f"你的工具判定:ERROR({str(e)})")
```

### 9.4 添加新的后处理规则

**位置**: `param_check.py` 第 4048 行之后

```python
def enforce_your_custom_rule(md: str) -> str:
    """
    自定义后处理规则

    流程:
    1. 逐行解析Markdown表格
    2. 应用你的规则
    3. 修改判定或说明列
    4. 返回修改后的Markdown
    """
    # 实现你的逻辑
    return modified_md

# 然后在主流程中调用
def verify_certificate_params(...):
    # ... 现有代码 ...
    md = enforce_kb_missing_fail(md)
    md = enforce_point_id(md)
    md = enforce_uncertainty_by_tool(md)
    md = enforce_your_custom_rule(md)  # 新增
```

### 9.5 修改记录

| 日期 | 修改人 | 修改内容 |
|------|--------|----------|
| 2026-03-18 | Claude | 初始创建文档，添加语义匹配扩展（电秒表功能输出时间间隔） |
| | | |

---

## 附录：关键文件索引

| 文件 | 用途 |
|------|------|
| `param_check.py` | 主核验模块 |
| `core/semantic_basis_selector.py` | 语义匹配核心 |
| `config/settings.py` | 配置管理 |
| `llm/client.py` | LLM客户端 |
