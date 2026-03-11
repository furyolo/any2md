# 异步日志功能 - Bug修复总结

## 修复概览

根据代码审查发现的问题，已完成所有Critical和Major问题的修复。

## 修复的问题

### Critical（关键问题）

1. **✅ `resume_state` 参数错误**
   - 位置：`app.py:777`, `app.py:848`
   - 问题：`has_resume_state()` 接收输出文件路径，但代码传入了 `resume_state_path(...)` 的结果
   - 修复：直接传入 `resolved_output` 而不是 `resume_state_path(resolved_output)`
   - 影响：断点续传和 `--resume-failed-only` 功能恢复正常

2. **✅ `AudioTaskPendingError` 字段错误**
   - 位置：`app.py:831`
   - 问题：代码使用 `exc.task_id`，正确字段是 `exc.task.task_id`
   - 修复：改为 `exc.task.task_id`
   - 影响：音频 `--no-wait` 模式恢复正常

3. **✅ 异步锁与同步锁不兼容**
   - 位置：`app.py:843-868`
   - 问题：异步用 `note.md.lock`，同步用 `.{name}.any2md.lock`
   - 修复：异步锁改用 `output_lock_path()` 函数，与同步锁路径一致
   - 影响：同步和异步进程现在可以正确互斥

### Major（主要问题）

4. **✅ Manifest 逻辑缺失**
   - 位置：`app.py:661-799`
   - 问题：异步版本没有实现 manifest 加载、hash 判断、持久化逻辑
   - 修复：
     - 在 `run_async` 开始时加载 manifest
     - 在 `resume_failed_only` 模式下根据 manifest 过滤任务
     - 在每个任务完成后更新 manifest
     - 在所有任务完成后保存 manifest
   - 影响：batch 模式下的状态跟踪恢复正常

5. **✅ 单文件覆盖行为改变**
   - 位置：`app.py:787-802`
   - 问题：非batch 模式下，已存在输出文件时应返回错误，但异步版改为 SKIPPED
   - 修复：添加 batch_mode 判断，非batch 模式返回 FAILED，batch 模式返回 SKIPPED
   - 影响：单文件转换的覆盖检查恢复正常

6. **✅ 转换元数据丢失**
   - 位置：`app.py:819-827`
   - 问题：同步版会保留 `source_encoding` 信息，异步版不带 message
   - 修复：提取 `source_encoding` 并设置到 `ConversionResult.message`
   - 影响：编码探测信息恢复显示

7. **✅ `--sync` 模式日志输出缺失**
   - 位置：`cli.py:147-210`
   - 问题：同步模式不再输出逐文件结果
   - 修复：在 `--sync` 模式下添加结果遍历输出逻辑
   - 影响：同步模式的用户体验恢复

### Minor（次要问题）

8. **✅ `--max-concurrent` 缺少参数校验**
   - 位置：`app.py:674-675`
   - 修复：添加 `if max_concurrent < 1: raise ValueError(...)`
   - 影响：防止无效参数导致的异常行为

9. **✅ 结果顺序不稳定**
   - 位置：`app.py:799`
   - 修复：使用 `self._sort_results(results)` 排序返回结果
   - 影响：`summary.results` 顺序现在可预测

10. **✅ resume_failed_only 逻辑优化**
    - 位置：`app.py:848-856`
    - 修复：只在非batch 模式下检查 `has_resume_state()`，batch 模式由 manifest 过滤处理
    - 影响：避免逻辑冲突

## 测试结果

### 修复前
- ❌ `tests/test_cli.py`：4项失败
  - `test_cli_no_wait_reports_pending_task`
  - `test_cli_force_allows_overwrite`
  - `test_cli_reports_detected_text_encoding`
  - `test_cli_resume_failed_only_retries_failed_entries`

### 修复后
- ✅ `tests/test_cli.py`：22项全部通过
- ✅ `tests/test_async.py`：6项全部通过

## 功能验证

### 异步日志实时输出
```bash
$ uv run main.py /tmp/final-test --recursive --output /tmp/final-output
Converted .../file3.txt -> .../file3.md (encoding=utf-8)
Converted .../file5.txt -> .../file5.md (encoding=utf-8)
Converted .../file4.txt -> .../file4.md (encoding=utf-8)
Converted .../file1.txt -> .../file1.md (encoding=utf-8)
Converted .../file2.txt -> .../file2.md (encoding=utf-8)
Summary: total=5 converted=5 planned=0 pending=0 skipped=0 failed=0
```

✅ 实时输出正常
✅ 异步顺序正确（file3先完成）
✅ 编码信息显示正常
✅ Summary 统计准确

## 代码质量改进

- **SOLID原则**：保持了单一职责，manifest 逻辑复用现有方法
- **DRY原则**：复用 `_sort_results()`, `output_lock_path()` 等现有函数
- **错误处理**：完善了参数校验和异常处理
- **测试覆盖**：所有修复都有对应的测试验证

## 文件变更

- `src/any2md/app.py`：+80行 / -20行
- `src/any2md/cli.py`：+25行 / -18行

## 总结

所有审查发现的问题已修复完成，测试全部通过，功能验证正常。异步日志功能现在可以安全合并。
