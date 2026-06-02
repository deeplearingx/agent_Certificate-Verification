# JJF1984 频率/周期误差与 JJG349 KB 缺口记录

## 结论

当前这批报告里，`2GB24003522-0015`、`2GB25003297-0001` 和 `4GC24000017-0001` 的剩余非 `PASS`，主因已经不再是 parser 抽错或共享 probe 主链 bug。

目前剩下的是两类真实缺口：

- `JJF1984` 下，`频率误差(Frequency Error)` / `周期测量误差(Period Measurement Error)` 已能稳定解析成 `frequency_accuracy` / `period_accuracy`，但同规程 KB 中没有兼容 candidate。
- `JJG349-2014` 在当前 KB 中没有对应条目，因此该依据下整批参数只能记为 `ERROR`。

不建议把这类 `frequency_error / period_error` 直接作为通用规则硬映射到现有 `reference_oscillator` 家族。

## 现象

### 1. `2GB24003522-0015`

- 报告路径：
  `final_reports/Report_2GB24003522-0015.md`
- 当前结果：
  `0 PASS / 0 FAIL / 1 REVIEW`
- 剩余 `REVIEW` 行：
  `2. 频率误差(Frequency Error)`
- 报告里明确写出：
  - `semantic_target = frequency_accuracy`
  - `axis_family = frequency_band`
  - `待人工核验 = same basis but no compatible candidate`
  - 同规程候选仅有 `开机特性 / 相对频率偏差 / 日老化率 / 1 s频率稳定度 / 频率复现性`

### 2. `2GB25003297-0001`

- 报告路径：
  `final_reports/Report_2GB25003297-0001.md`
- 当前结果：
  `0 PASS / 0 FAIL / 1 REVIEW`
- 剩余 `REVIEW` 行与上面同类：
  `2. 频率误差(Frequency Error)`
- 现象与 `2GB24003522-0015` 一致，差别只在数值点位和 planner 明细。

### 3. `4GC24000017-0001`

- 报告路径：
  `final_reports/Report_4GC24000017-0001.md`
- 当前主结果：
  `23 PASS / 0 FAIL / 14 REVIEW`
- 已修复部分：
  - `2.1 开机特性`
  - `2.2 1s频率稳定度`
  - `2.3 相对频率偏差`
  这些现在都已是 `PASS`，说明此前 `reference_oscillator` 的 probe 基准 bug 已收住。
- 剩余 `REVIEW`：
  - `4 频率测量误差(Frequency Measurement Error)` 多条
  - `5 周期测量误差(Period Measurement Error)` 多条
  这两组同样都是：
  - `semantic_target = frequency_accuracy / period_accuracy`
  - `same basis but no compatible candidate`
  - 同规程候选仍落在 `JJF1984` 的 `reference_oscillator` 指标条目
- 同时该报告下 `JJG349-2014` 整条依据全部为 `ERROR`，原因是：
  `知识库中找不到与规程 JJG 349 一致的条目`

## 当前实现状态

### 已经正确的部分

- parser / contract 已能稳定把这类证书行建模为：
  - `frequency_accuracy`
  - `period_accuracy`
- `4GC24000017-0001` 中 `2.1/2.2/2.3` 的 `reference_oscillator` 指标行，probe 已修正为按指标值核验，不再拿 `10 MHz` 去撞 `1e-10` 量级范围。
- planner 已能看出这些行是 `frequency_accuracy / period_accuracy`，但拿不到可安全 takeover 的同规程候选。

### 仍然缺失的部分

- `JJF1984` 的同规程候选目前基本只有：
  - `开机特性`
  - `相对频率偏差`
  - `1 s频率稳定度`
  - `频率复现性`
  - `日老化率`
- 当前 selector 不会把：
  - `Frequency Error`
  - `Period Measurement Error`
  直接并入这些 `reference_oscillator` 指标家族。
- `JJG349` 当前没有入库条目，因此 basis 级核验只能返回 `ERROR`。

## 为什么先不直接做映射

- `frequency_error / period_error` 与 `reference_oscillator` 在业务语义上不是天然等价。
- 现在这些证书行本质上是“测量功能误差表”，而 `reference_oscillator` 是“晶振性能指标家族”。
- 若直接做共享自动映射，会把真正的 KB/能力建模缺口洗成“已匹配”。
- `planner` 即使给出建议，也不能替代同规程 candidate 的业务合法性。

## 需要后续对接验证的点

### 1. 业务口径确认

- `JJF1984` 下的 `频率误差(Frequency Error)`，是否允许等价视为某类晶振指标核验。
- `JJF1984` 下的 `周期测量误差(Period Measurement Error)`，是否本来就应有独立能力条目。
- 多依据场景中，`JJG349` 缺 KB 时，主结论是否允许只按 `JJF1984` 归并。

### 2. KB 数据对接

- 是否补充 `JJF1984` 下的：
  - `频率测量误差(Frequency Measurement Error)`
  - `周期测量误差(Period Measurement Error)`
- 是否补充 `JJG349-2014` 的对应 KB 条目。

### 3. 受限映射验证

- 如果业务确认可映射，也只能做“受限映射”验证：
  - 限于 `JJF1984`
  - 限于固定频点 `1/2/5/10 MHz`
  - 限于标准 `reference / error / limit / U` 结构
- 不建议直接作为全局默认规则上线。

## 对应报告

- `final_reports/Report_2GB24003522-0015.md`
- `final_reports/Report_2GB25003297-0001.md`
- `final_reports/Report_4GC24000017-0001.md`

## 对应代码链

- `langchain_app/checks/parameter/contracts.py`
  负责 subtype / probe role / comparison mode 定义
- `langchain_app/checks/parameter/semantic.py`
  负责证书参数与 KB 条目的家族语义建模
- `langchain_app/checks/parameter/selector.py`
  负责同规程候选过滤、target set 和 candidate 排序
- `langchain_app/checks/parameter/parameter.py`
  负责最终 range / error / uncertainty 核验与 verdict 汇总

## 后续建议

1. 先把它定义为明确的 KB / 能力建模缺口，不再继续怀疑 parser 或已修复的 probe 主链。
2. 优先和业务/KB 维护方确认：
   - 是补 `JJF1984` / `JJG349` 条目
   - 还是允许一小类 `Frequency Error @ fixed MHz point` 做受限映射
3. 在业务口径确认前，不建议把 `frequency_error / period_error` 直接并入 `reference_oscillator` 当共享默认规则。
