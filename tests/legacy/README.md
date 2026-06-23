# Legacy Tests

本目录保留旧版根目录脚本测试，默认不参与 `pytest`。

这些测试依赖已经归档的旧模块名，例如：

- `param_check.py`
- `run_batch_verification.py`
- 旧 `config/`、`core/` 包

迁移原则：

1. 如果测试覆盖的逻辑已经迁入 `langchain_app/`，优先改成新导入路径并移回 `tests/`。
2. 如果测试依赖旧版内部函数或旧批处理入口，先保留在本目录作为行为参考。
3. 不为了让旧测试通过而把旧模块重新放回根目录。
