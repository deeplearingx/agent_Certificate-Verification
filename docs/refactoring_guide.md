# 参数核验模块重构指南

## 概述

本次重构将原来 5400 行的大文件 `param_check.py` 拆分为多个模块化组件，便于功能的增添和删除。

## 目录结构

```
document-verification-master/
├── core/                          # 核心模块
│   ├── __init__.py               # 模块入口
│   ├── config.py                  # 配置管理
│   ├── number_parser.py           # 数值解析
│   ├── unit_converter.py         # 单位转换
│   ├── risk_verifier.py           # 范围验证
│   ├── error_verifier.py          # 误差验证
│   ├── uncertainty_verifier.py    # 不确定度验证
│   ├── table_processor.py         # 表格处理
│   ├── report_generator.py        # 报告生成
│   └── semantic_basis_selector.py # 语义选择
├── docs/                          # 文档
│   └── refactoring_guide.md       # 本指南
├── memory/                        # 知识库
│   └── param_check.md             # 旧代码分析
├── param_check.py                 # 原文件（保留）
└── param_check_refactored.py      # 重构后的使用入口
```

## 快速开始

### 使用重构版本

```python
from core.config import Config
from core.number_parser import NumberParser
from core.table_processor import TableProcessor
from core.report_generator import ReportGenerator

# 数值解析
value, unit = NumberParser.parse_extracted_token("10.5 mV")

# 表格处理
tables = TableProcessor.collect_param_tables(batch_contents)

# 报告生成
report = ReportGenerator()
summary = report.generate_final_statistics(tables)
```

### 保持向后兼容

重构后的 `param_check_refactored.py` 保留了所有原有的函数接口，可以直接替换使用：

```python
# 旧代码
from param_check import parse_value_with_unit, verify_range_logic

# 新代码（完全兼容）
from param_check_refactored import parse_value_with_unit, verify_range_logic
```

## 核心模块说明

### 1. Config - 配置管理

**功能**: 统一管理所有配置

```python
from core.config import Config

# 访问配置
print(Config.TOPK)           # 默认 Top-K
print(Config.OUTPUT_DIR)     # 输出目录

# 版本戳
version = Config.build_version_stamp(__file__)
```

**增添配置**: 在 `core/config.py` 中添加新的配置项即可。

### 2. NumberParser - 数值解析

**功能**: 统一的数值和单位解析

```python
from core.number_parser import NumberParser

# 解析带单位的数值
val, typ = NumberParser.parse_value_with_unit("10.5 mV")

# 解析 Unicode 科学计数法
val = NumberParser.parse_unicode_sci_number("6.6×10⁻⁹")

# 提取数值 Token
token = NumberParser.extract_value_token("测量值: 10.5 mV, 标准: 9.8 mV")

# 单位标准化
unit = NumberParser.normalize_unit_text("uv")  # "uV"
```

**增添新的数值格式**: 在 `parse_value_with_unit()` 中添加新的解析逻辑。

### 3. UnitConverter - 单位转换

**功能**: 统一的工程单位换算

```python
from core.unit_converter import UnitConverter

# 单位转换 (dBm -> Vpp)
result = UnitConverter.unit_convert_tool("-130 dBm")
print(json.loads(result)["converted_vpp"])  # 转换后的值

# 判断单位类型
if UnitConverter.is_power_unit("dBm"):
    print("这是功率单位")

if UnitConverter.is_voltage_unit("mV"):
    print("这是电压单位")
```

**增添新的单位转换**: 在 `unit_convert_tool()` 中添加新的转换逻辑。

### 4. RangeVerifier - 范围验证

**功能**: 统一的范围和边界解析

```python
from core.risk_verifier import RangeVerifier

# 解析单边限制
op, thr = RangeVerifier.parse_single_sided_limit("<= 10.5 mV")

# 解析区间范围
lower, upper = RangeVerifier.parse_range_limit("1 ns ~ 10 s")

# 解析对称容差
kind, *args = RangeVerifier.parse_symmetric_limit("±0.1")
if kind == "limit":
    limit = args[0]
elif kind == "range":
    lower, upper = args

# 范围验证
result = RangeVerifier.verify_range_logic("10.5 mV", "1 ~ 20 mV")
```

**增添新的范围格式**: 在对应的解析函数中添加新的正则模式。

### 5. TableProcessor - 表格处理

**功能**: 统一的 Markdown 表格操作

```python
from core.table_processor import TableProcessor

# 收集参数表格
param_to_table = TableProcessor.collect_param_tables(batch_contents)

# 合并表格行
merged = TableProcessor.merge_table_lines(existing, new)

# 标准化参数名称
normalized = TableProcessor.normalize_param_name_for_merge("频率范围 (1)")

# 统计表格状态
summary = TableProcessor.summarize_table_statuses(table_lines)
print(summary["pass"], summary["fail"], summary["total"])
```

**增添新的表格操作**: 在 `TableProcessor` 类中添加新的静态方法。

### 6. ReportGenerator - 报告生成

**功能**: 统一的报告生成逻辑

```python
from core.report_generator import ReportGenerator

generator = ReportGenerator()

# 构建 KB 预览表格
table = ReportGenerator.build_kb_table(kb_entries, top_k=10)

# 从表格生成总结
summary_lines = generator.build_summary_lines_from_table(table_lines)

# 强制生成批次总结
processed = generator.enforce_batch_summary_from_table(md_content)

# 生成最终统计
stats = generator.generate_final_statistics(param_to_table)
```

**增添新的报告格式**: 在 `ReportGenerator` 类中添加新的方法。

## 功能增添指南

### 场景 1: 添加新的验证类型

假设要添加一个新的"示值误差"验证：

**步骤**:

1. 在 `core/` 下创建新文件 `core/error_verifier.py`（如果不存在）

2. 添加新的验证器类：

```python
class ErrorVerifier:
    @staticmethod
    def verify_error_logic(error_val, limit_val):
        """验证示值误差"""
        # 实现逻辑
        return json.dumps({
            "status": "PASS",
            "reason": "...",
            "calc_type": "error"
        }, ensure_ascii=False)
```

3. 在 `core/__init__.py` 中导出：

```python
from .error_verifier import ErrorVerifier
__all__.append('ErrorVerifier')
```

4. 在 `param_check_refactored.py` 中暴露：

```python
from core.error_verifier import ErrorVerifier
verify_error_logic = ErrorVerifier.verify_error_logic
```

### 场景 2: 添加新的表格列

假设要在报告表格中添加新的"备注"列：

**步骤**:

1. 在 `core/table_processor.py` 中添加：

```python
@staticmethod
def find_remark_column_index(cols: List[str]) -> Optional[int]:
    """查找备注列索引"""
    for idx, col in enumerate(cols):
        col_text = col.strip().lower()
        if "备注" in col_text or "remark" in col_text:
            return idx
    return None
```

2. 在 `summarize_table_statuses()` 中使用新方法。

### 场景 3: 添加新的不确定度类型

假设要添加一种新的"扩展不确定度"类型：

**步骤**:

1. 在 `core/number_parser.py` 的 `detect_uncertainty_info()` 中添加检测逻辑：

```python
# 检测扩展不确定度
m_extended = re.search(r"U\s*exp\s*=\s*([^，,。；;]+)", text, flags=re.IGNORECASE)
if m_extended:
    info["type"] = "U_EXTENDED"
    info["value"] = m_extended.group(1)
    return info
```

2. 在 `core/uncertainty_verifier.py` 中添加处理逻辑。

## 功能删除指南

### 场景 1: 删除不需要的验证器

假设不再需要"输入灵敏度"特殊处理：

**步骤**:

1. 找到相关代码（在 `core/risk_verifier.py` 中）
2. 删除或注释掉相关函数
3. 如果不再使用，清理相关测试用例

### 场景 2: 删除旧的兼容性代码

当确定所有代码都迁移到新结构后：

**步骤**:

1. 删除 `param_check_refactored.py` 中的旧函数转发
2. 更新调用方直接使用新的模块

## 迁移策略

### 阶段 1: 保持兼容（当前）

- 保留 `param_check.py` 不变
- 创建 `param_check_refactored.py` 提供相同接口
- 内部使用新的模块化结构

### 阶段 2: 逐步迁移

- 新代码直接导入 `core.*` 模块
- 旧代码逐步更新为使用新模块
- 保留兼容层作为过渡

### 阶段 3: 完全替换

- 删除 `param_check.py`
- 重命名 `param_check_refactored.py` 为 `param_check.py`
- 更新所有导入

## 最佳实践

### 1. 模块设计原则

- **单一职责**: 每个模块只做一件事
- **松耦合**: 模块间通过明确的接口通信
- **可测试**: 每个模块都可以独立测试

### 2. 添加新功能的检查清单

- [ ] 在适当的模块中添加代码
- [ ] 添加文档字符串
- [ ] 添加单元测试
- [ ] 更新 `__init__.py` 导出
- [ ] 在 `param_check_refactored.py` 中暴露（如需要）
- [ ] 更新文档

### 3. 代码风格

- 使用类型提示 (`->`, `:`, `Optional[]`)
- 编写文档字符串
- 保持函数简短（< 50 行）
- 使用静态方法进行无状态操作

## 常见问题

### Q: 原代码中的 `_extract_param_name` 函数有多个版本，应该用哪个？

**A**: 使用 `TableProcessor.extract_param_name()`，这是统一后的版本。

### Q: 如何添加新的配置项？

**A**: 在 `core/config.py` 的 `Config` 类中添加新的类变量。

### Q: 验证逻辑太复杂，能拆分吗？

**A**: 可以！每个验证器都是独立的模块，完全可以继续拆分。

### Q: 如何确保向后兼容？

**A**: 在 `param_check_refactored.py` 中保留原有的函数名，转发到新模块的实现。

## 示例: 完整的使用流程

```python
# 1. 导入模块
from core.config import Config
from core.number_parser import NumberParser
from core.table_processor import TableProcessor
from core.report_generator import ReportGenerator

# 2. 解析数值
measure_val = "10.5 mV ± 0.1 mV"
val, _ = NumberParser.parse_value_with_unit(measure_val)

# 3. 处理表格
tables = TableProcessor.collect_param_tables(batch_outputs)

# 4. 生成报告
generator = ReportGenerator()
stats = generator.generate_final_statistics(tables)

# 5. 输出结果
print(f"PASS: {stats['pass']}, FAIL: {stats['fail']}")
```

## 联系与支持

如有问题，请参考：
- `memory/param_check.md` - 原代码详细分析
- `core/*.py` - 各模块的实现代码
