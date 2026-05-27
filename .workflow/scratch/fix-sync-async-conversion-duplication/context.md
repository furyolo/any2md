# 快速分析

任务：修复 `src/any2md/app.py` 中同步 `run()` 与异步 `run_async()` 的转换规划重复。

已确认：
- `run()` 已有较完整规划逻辑：输出路径解析、输出冲突、`--resume-failed-only`、manifest 哈希判断、已存在输出跳过、输入变更重转。
- `run_async()` 另有一套简化逻辑：重复解析输出、重复处理 dry-run / resume；缺少同步路径中的输出冲突检测和 manifest 输入变更重转判断。
- 测试覆盖同步路径较多，异步路径此前只有基础并发测试。

实施边界：
- 不改 CLI 参数与用户可见输出格式。
- 不改 converter 注册方式。
- 抽出共享规划和 manifest 更新辅助方法，让同步/异步复用。
- 给异步路径补充与同步路径一致的关键行为测试。

执行结果：
- 新增 `ConversionPlan`，由 `_plan_jobs()` 统一输出路径、冲突、跳过、重转规划。
- 新增 `_update_manifest_from_result()`，同步/异步复用 manifest 更新逻辑。
- `run_async()` 只保留异步并发执行差异，规划和跳过判断改为复用同步路径。
- 新增异步测试：输出冲突、输入变更重转、`--resume-failed-only`。

验证：
- `python -m py_compile src/any2md/app.py tests/test_async.py` 通过。
- `uv run python -m unittest tests.test_app tests.test_async` 通过，27 tests OK。
- `uv run python -m unittest tests.test_app tests.test_async tests.test_cli` 中 `tests.test_cli` 存在既有失败，集中在 CLI 默认音频后端与旧测试期望不一致，本任务未修改 CLI 行为。
