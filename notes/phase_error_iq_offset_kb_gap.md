# Phase Error / IQ Offset 的 KB 映射问题记录

## 结论

当前实现里，`Phase Error` 和 `IQ Offset` 已经能被解析出来，也能被归到 `modulation_quality` 语义，但旧逻辑里没有它们对应的专用 KB 条目。

它们当前在报告里落成 `REVIEW`，原因不是 parser 没读到，而是 selector / KB 映射层没有可稳定命中的具体条目，只能保守留人工复核。

## 现象

- 最新报告里，`EVM` 能稳定落到 KB 条目 `误差矢量幅度`。
- `Phase Error` 和 `IQ Offset` 在多批次里都保持 `REVIEW`。
- 报告说明里可以看到 `semantic_target = modulation_quality`，但 `KB编号 / KB条目` 仍然是 `无`。

## 旧实现的处理状态

- 旧实现已经有 `EVM`、`Phase Error`、`IQ Offset` 的字段提取正则。
- 旧实现已经把 `modulation_quality` 相关语义和 `EVM` 关联起来。
- 旧实现的 KB 规则表里，`modulation_quality` 只包含 `error_vector_magnitude / 误差矢量幅度 / evm`。
- 旧实现没有把 `phase_error`、`iq_offset` 放进 KB 规则表，也没有对应的专用 KB 条目。

## 为什么先不处理

- 直接把 `Phase Error` / `IQ Offset` 硬并到 `EVM`，会把单位和物理量差异抹平。
- 现在的 `REVIEW` 是保守且一致的结果，不是误判。
- 若要继续压低 `REVIEW`，需要先补 KB 条目或明确业务规则，而不是只改 selector。

## 需要与公司确认

- `Phase Error` 和 `IQ Offset` 是否需要独立 KB 条目，还是业务上允许与现有 `EVM` 家族做归并。
- 如果允许归并，归并后的判定依据是否仍可直接复用 `EVM`，还是需要单独的误差/不确定度口径。
- 如果不允许归并，这两类参数长期保留 `REVIEW` 是否可接受，还是必须推动补库。

## 相关文件

- `langchain_app/checks/parameter/rules.py`
- `langchain_app/checks/parameter/semantic.py`
- `langchain_app/checks/parameter/selector.py`
- `final_reports/Report_2GB25006175-0005A.md`

## 后续建议

1. 如果业务上接受保守判定，保持现状即可。
2. 如果必须消除这类 `REVIEW`，先补 `Phase Error` / `IQ Offset` 的 KB 条目。
3. 不建议把它们直接并入 `EVM`，除非业务方明确接受这种归并。
