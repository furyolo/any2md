# 异步日志实时输出 - 实施计划

## 需求概述

将批量文件转换的日志输出从同步改为异步实时输出，让用户能够看到实时进度。

## 当前问题

- 所有文件转换完成后才统一输出日志（在 cli.py:172-189 的 for 循环中）
- 用户无法看到实时进度

## 期望行为

- 每个文件转换完成时立即输出 "Converted ..." 日志
- 日志顺序可能与输入顺序不同（异步特性）
- 最终 Summary 仍然正确统计

## 实施方案

### 1. 修改 `app.py`

#### 1.1 添加类型定义
```python
from typing import Awaitable, Callable, Sequence

ProgressCallback = Callable[[ConversionResult], Awaitable[None]]
```

#### 1.2 修改 `run_async` 方法签名
添加 `progress_callback` 参数：
```python
async def run_async(
    self,
    inputs: Sequence[str],
    recursive: bool = False,
    output_path: str | None = None,
    t2s: bool = False,
    dry_run: bool = False,
    force: bool = False,
    resume_failed_only: bool = False,
    max_concurrent: int = 5,
    progress_callback: ProgressCallback | None = None,
) -> RunSummary:
```

#### 1.3 实现回调触发逻辑
- 在 `run_async` 开始时，对已发现的结果（discovered results）触发回调
- 在 dry-run 模式下，每个计划的结果触发回调
- 在 `asyncio.as_completed` 循环中，每个任务完成时立即触发回调

### 2. 修改 `cli.py`

#### 2.1 创建进度回调函数
```python
async def progress_callback(result: ConversionResult) -> None:
    if result.succeeded:
        detail = f" ({result.message})" if result.message else ""
        print(f"Converted {result.input_path} -> {result.output_path}{detail}", file=error_stream)
    elif result.planned:
        print(f"Planned {result.input_path} -> {result.output_path}", file=error_stream)
    elif result.pending:
        print(f"Processing {result.input_path}: {result.message}", file=error_stream)
        if result.task_id:
            print(f"Task ID: {result.task_id}", file=error_stream)
            print(f"Continue later with: uv run main.py --auc-status {result.task_id}", file=error_stream)
    elif result.skipped:
        print(f"Skipped {result.input_path}: {result.message}", file=error_stream)
    else:
        print(f"Failed {result.input_path}: {result.error}", file=error_stream)
```

#### 2.2 传入回调到 `run_async`
```python
summary = asyncio.run(
    service.run_async(
        inputs=args.inputs,
        recursive=args.recursive,
        output_path=args.output,
        t2s=args.t2s,
        dry_run=args.dry_run,
        force=args.force,
        resume_failed_only=args.resume_failed_only,
        max_concurrent=args.max_concurrent,
        progress_callback=progress_callback,
    )
)
```

#### 2.3 移除原有的结果遍历输出
删除 cli.py:172-189 的 for 循环，只保留 Summary 输出。

### 3. 边界情况处理

- **discovered_results**：在任务开始前就已经确定的结果（如不支持的格式），需要在开始时触发回调
- **dry-run 模式**：计划的输出也需要触发回调
- **异常处理**：确保回调中的异常不会中断主流程
- **线程安全**：print 是线程安全的，但需要确保 error_stream 的正确性

### 4. 验收标准

- ✅ 运行批量转换时，每个文件完成立即输出日志
- ✅ 日志顺序可能与输入顺序不同（快的文件先完成）
- ✅ 最终 Summary 仍然正确统计
- ✅ 不影响其他命令（--auc-status, --manifest-list等）

## Codex 实施结果

Codex 已经生成了完整的代码修改，包括：
1. 在 `app.py` 中添加 `ProgressCallback` 类型定义
2. 修改 `run_async` 方法，添加 `progress_callback` 参数
3. 使用 `asyncio.as_completed` 实现实时回调
4. 在 `cli.py` 中创建并传入回调函数
5. 添加了单元测试验证异步顺序

SESSION_ID: 019cdc45-f93d-72f3-a36e-cddd10bcd0e2
