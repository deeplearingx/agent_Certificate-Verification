# 参数核验 Profile 结构说明

本文说明参数核验后续如何按“通用规则 + 仪器/规程 profile”拆分。当前代码已新增 `langchain_app/checks/parameter/profiles/` 作为声明式 profile 层，第一步不改变现有核验行为，只明确后续扩展边界。

## 1. 为什么需要 Profile 层

当前参数核验核心集中在：

- `parameter.py`：主流程、批处理、报告拼接。
- `rules.py`：语义目标、别名、字段规则。
- `contracts.py`：解析行合同化。
- `semantic.py`：证书行和 KB 条目的语义识别。
- `selector.py`：候选 KB 选择。
- `validator.py`：范围、误差、不确定度判定。

这些模块已经有较完整的通用能力，但特殊仪器规则继续堆在 `rules.py` 或 `parameter.py` 会越来越难维护。Profile 层用于回答：

```text
这份证书属于哪类仪器/规程？
应该启用哪些 semantic target？
有哪些字段探针或判定策略要特殊处理？
哪些逻辑仍走通用 validator？
```

## 2. 第一版分类依据

当前根据 `pdf/` 目录中的证书分类，先建立以下 profile：

| Profile | PDF 类别/仪器 | 主要 semantic target | 特殊点 |
| --- | --- | --- | --- |
| `time_frequency.counter` | 通用计数器、频率计、微波频率计数器 | `frequency_accuracy`、`period_accuracy`、`period_range`、`count_accuracy`、`input_sensitivity`、`reference_oscillator` | 同一证书常混合频率、周期、计数、时基 |
| `time_frequency.time_interval` | 时间间隔测量仪、时间间隔发生器、脉冲计数器、脉冲分配放大器、时间检定仪 | `period_accuracy`、`period_range`、`count_accuracy`、`input_sensitivity` | 脉宽、周期、占空比、输出时间间隔字段探针不同 |
| `time_frequency.stopwatch_timer` | 秒表、时间继电器计时器、JJG 488 瞬时日差测量仪 | `period_accuracy`、`period_range`、`reference_oscillator` | 日差/月差/走时误差按 `limit_error`，输出时间间隔用专属 subtype |
| `time_frequency.frequency_standard` | 铷原子频率标准、石英晶体频率标准、石英晶体振荡器、频标比对器 | `reference_oscillator`、`frequency_accuracy`、`frequency_range` | 开机特性、频率稳定度、日老化率、复现性不能当普通频率误差 |
| `time_frequency.gnss` | GNSS 信号模拟器、信号转发器、采集回放仪 | `frequency_accuracy`、`power_accuracy`、`phase_noise`、`modulation_quality`、`spectral_purity`、`dynamic_range`、`cnr_consistency`、`position_consistency` | 载波频率、EVM、相位误差、IQ 偏置、伪距/位置一致性都是特殊规则 |
| `rf_microwave.signal_source` | 射频/微波信号源、频谱/网络分析相关仪器 | `power_accuracy`、`phase_noise`、`modulation_quality`、`spectral_purity`、`dynamic_range`、`vswr_accuracy`、`impedance_accuracy` | 功率、相位噪声、调制质量不能套普通频率/时间规则 |
| `scope_function.oscilloscope` | 示波器 | 当前先启用 `frequency_accuracy`、`period_accuracy`、`dynamic_range` | 幅度、垂直偏转、时基等目标尚待补 semantic target |
| `scope_function.function_generator` | 函数/任意波形发生器 | 当前先启用 `frequency_accuracy`、`period_accuracy`、`power_accuracy` | 幅度准确度、失真、波形参数后续单独建模 |
| `generic.default` | 未识别仪器 | 全部通用 semantic target | 只走通用规则，不做仪器专属修正 |

## 3. 代码结构

```text
langchain_app/checks/parameter/
  profiles/
    base.py                  # InstrumentProfile / ProfileMatch
    registry.py              # PROFILE_REGISTRY、match_profiles、best_profile
    general.py               # generic.default
    time_frequency.py        # 时间频率类 profile
    rf_microwave.py          # 射频/微波类 profile
    oscilloscope_function.py # 示波器/函数类 profile
```

Profile 是声明式配置，不直接执行判定。核心字段：

- `profile_id`：稳定 ID，例如 `time_frequency.gnss`。
- `instrument_aliases`：从 JSON `仪器名称` 匹配。
- `criterion_aliases`：从 `校准依据` 匹配。
- `pdf_category_aliases`：从 PDF 目录或批处理相对路径匹配。
- `semantic_targets`：该仪器族允许启用的语义目标。
- `special_policies`：特殊字段探针、比较模式或人工复核策略说明。
- `priority`：多个 profile 命中时的优先级，数字越小越优先。

## 4. 通用部分与特殊仪器差异

通用部分保留在现有模块：

- 数值解析：`parser_core.py`
- 参数合同：`contracts.py`
- 通用语义识别：`semantic.py`
- KB 候选选择：`selector.py`
- 范围/误差/U 判定：`validator.py`
- 报告渲染：`reporter.py`

特殊仪器 profile 只处理差异：

- 哪些 semantic target 可用。
- 某个参数行应该使用哪个 subtype。
- 某个字段应该作为测量值、条件轴、误差值还是 U 探针。
- 知识库缺项时应 REVIEW 还是 ERROR。
- 某类仪器是否需要额外人工复核说明。

不建议把完整 validator 复制到每个仪器目录。特殊 profile 应尽量只提供“路由和策略”，底层判定继续复用通用函数。

## 5. 后续接入步骤

第一阶段已经完成：

- 新增 profile 数据结构。
- 按当前 PDF 分类建立第一批 profile。
- 增加 profile registry 测试。

第二阶段建议接入：

1. 在 `collect_certificate_params` 或批处理入口提取 `instrument_name`、`criterion`、`pdf_category`。
2. 调用 `match_profiles(...)` 得到当前证书的 profile。
3. 把 profile ID 和启用的 semantic targets 写入参数核验 trace。
4. 在 `semantic.py` 和 `selector.py` 中只允许 profile 启用的 semantic target 参与候选排序。
5. 将 GNSS、秒表、频标等特殊字段探针逐步从通用规则迁到 profile policy。

第三阶段新增仪器：

1. 在 `profiles/` 新建或扩展对应文件。
2. 增加 `InstrumentProfile`。
3. 在 `registry.py` 注册。
4. 增加一份最小测试，确认能匹配仪器名/规程号，并启用预期 semantic targets。
5. 再补实际参数判定测试。

