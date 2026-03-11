# Team Plan: async-upgrade

## 概述
将 any2md 从同步架构升级为异步架构，支持并发处理多个文件，提升批量转换性能。

## Codex 分析摘要
**技术可行性：**
- 使用 asyncio（Python 3.10+ 原生支持）
- httpx 已支持异步客户端（AsyncClient）
- 需要添加 aiofiles 用于异步文件 I/O
- subprocess 可用 asyncio.create_subprocess_exec 替代

**关键改造点：**
1. `src/any2md/auc/client.py` - AucClient 改为异步 HTTP 请求
2. `src/any2md/app.py` - ConversionService 批量处理改为并发
3. `src/any2md/ocr.py` - OCR API 调用改为异步
4. `src/any2md/converters/audio.py` - 音频处理改为异步子进程

**风险评估：**
- 破坏性变更：需要保持 CLI 接口向后兼容
- 测试策略：逐模块迁移，保留同步版本作为回退
- 依赖兼容性：所有依赖库均支持异步

## Gemini 分析摘要
**CLI 用户体验：**
- CLI 入口（main）保持同步，使用 `asyncio.run()` 包装异步逻辑
- 添加 `--max-concurrent N` 参数控制并发数（默认 5）
- 保持现有参数接口不变，用户无感知升级

**组件拆分策略：**
- 保持同步：CLI 参数解析、日志输出、manifest 文件读写
- 改为异步：HTTP 请求、文件转换、批量处理循环

**交互设计：**
- 实时进度显示：使用 tqdm 异步模式
- 错误处理：异步任务失败不影响其他任务
- 优雅退出：Ctrl+C 取消所有待处理任务

## 技术方案

### 架构设计
```
CLI 入口 (同步)
  └─> asyncio.run()
       └─> ConversionService.run_async()
            ├─> asyncio.gather() 并发处理
            │    ├─> convert_single_async() [Task 1]
            │    ├─> convert_single_async() [Task 2]
            │    └─> convert_single_async() [Task N]
            └─> 收集结果 + 生成摘要
```

### 关键技术决策
1. **并发控制**：使用 `asyncio.Semaphore(max_concurrent)` 限制并发数
2. **向后兼容**：保留同步 API，CLI 内部调用异步版本
3. **依赖添加**：`aiofiles>=24.1.0`
4. **错误隔离**：每个文件转换独立异步任务，互不影响

## 子任务列表

### Task 1: 添加异步依赖和基础设施
- **类型**: 后端
- **文件范围**: 
  - `pyproject.toml` - 添加 aiofiles 依赖
  - `src/any2md/async_utils.py` (新建) - 异步工具函数
- **依赖**: 无
- **实施步骤**:
  1. 在 pyproject.toml 添加 `aiofiles>=24.1.0`
  2. 创建 async_utils.py，实现 Semaphore 包装器
  3. 实现异步文件读写辅助函数
- **验收标准**: 依赖安装成功，async_utils.py 可导入

### Task 2: AUC 客户端异步化
- **类型**: 后端
- **文件范围**:
  - `src/any2md/auc/client.py` - AucClient 类
- **依赖**: Task 1
- **实施步骤**:
  1. 添加 `AucAsyncClient` 类
  2. 将 `httpx.post()` 改为 `httpx.AsyncClient().post()`
  3. 所有方法改为 `async def`
  4. 保留原 `AucClient` 作为同步兼容层
- **验收标准**: 
  - `AucAsyncClient.transcribe()` 可异步调用
  - 原 `AucClient` 仍可正常工作

### Task 3: OCR 模块异步化
- **类型**: 后端
- **文件范围**:
  - `src/any2md/ocr.py` - OCR API 调用
- **依赖**: Task 1
- **实施步骤**:
  1. 添加 `ocr_image_async()` 函数
  2. 使用 `httpx.AsyncClient` 替代同步请求
  3. 保留原 `ocr_image()` 函数
- **验收标准**: `ocr_image_async()` 可并发调用多张图片

### Task 4: 音频转换器异步化
- **类型**: 后端
- **文件范围**:
  - `src/any2md/converters/audio.py` - AudioConverter 类
- **依赖**: Task 2
- **实施步骤**:
  1. 添加 `AudioAsyncConverter` 类
  2. subprocess 调用改为 `asyncio.create_subprocess_exec()`
  3. AUC 客户端调用改为 `AucAsyncClient`
  4. 保留原 `AudioConverter` 类
- **验收标准**: 可并发处理多个音频文件

### Task 5: 图片转换器异步化
- **类型**: 后端
- **文件范围**:
  - `src/any2md/converters/image.py` - ImageConverter 类
- **依赖**: Task 3
- **实施步骤**:
  1. 添加 `ImageAsyncConverter` 类
  2. OCR 调用改为 `ocr_image_async()`
  3. 保留原 `ImageConverter` 类
- **验收标准**: 可并发处理多张图片

### Task 6: 核心服务异步化
- **类型**: 后端
- **文件范围**:
  - `src/any2md/app.py` - ConversionService 类
- **依赖**: Task 2, Task 3, Task 4, Task 5
- **实施步骤**:
  1. 添加 `ConversionService.run_async()` 方法
  2. 使用 `asyncio.gather()` 并发处理文件列表
  3. 添加 `asyncio.Semaphore` 控制并发数
  4. 实现 `_convert_single_async()` 方法
  5. 异步文件锁机制（使用 aiofiles）
  6. 保留原 `run()` 方法
- **验收标准**: 
  - 批量转换可并发执行
  - 并发数可控制
  - 错误隔离正常工作

### Task 7: CLI 集成异步支持
- **类型**: 前端
- **文件范围**:
  - `src/any2md/cli.py` - main() 函数
- **依赖**: Task 6
- **实施步骤**:
  1. 添加 `--max-concurrent` 参数（默认 5）
  2. 添加 `--sync` 参数（强制使用同步模式）
  3. 在 main() 中判断：默认调用 `asyncio.run(service.run_async())`
  4. 如果 `--sync`，调用原 `service.run()`
  5. 保持所有现有参数接口不变
- **验收标准**: 
  - CLI 接口向后兼容
  - `--max-concurrent` 参数生效
  - `--sync` 可回退到同步模式

### Task 8: 文档和测试更新
- **类型**: 前端
- **文件范围**:
  - `README.md` - 更新文档
  - `tests/` - 添加异步测试
- **依赖**: Task 7
- **实施步骤**:
  1. 更新 README.md，说明新增的 `--max-concurrent` 参数
  2. 添加异步转换的性能对比示例
  3. 创建 `tests/test_async.py` 测试异步功能
  4. 确保现有测试仍然通过
- **验收标准**: 
  - 文档完整
  - 异步测试覆盖核心功能

## 文件冲突检查
✅ 无冲突 - 所有任务操作不同文件，或在同一文件添加新类/函数（不修改现有代码）

## 并行分组
- **Layer 1 (并行)**: Task 1
- **Layer 2 (依赖 Layer 1)**: Task 2, Task 3 (并行)
- **Layer 3 (依赖 Layer 2)**: Task 4, Task 5 (并行)
- **Layer 4 (依赖 Layer 3)**: Task 6
- **Layer 5 (依赖 Layer 4)**: Task 7
- **Layer 6 (依赖 Layer 5)**: Task 8

## 实施策略
1. **渐进式迁移**：每个模块添加异步版本，保留同步版本
2. **向后兼容**：CLI 接口不变，用户可选择同步/异步模式
3. **性能优化**：默认并发数 5，可通过参数调整
4. **错误隔离**：单个文件失败不影响其他文件处理
5. **测试覆盖**：每个异步模块都有对应测试

## 预期收益
- **性能提升**：批量处理 100 个文件，预计耗时减少 60-80%
- **用户体验**：实时进度显示，响应更快
- **可扩展性**：为未来更多并发场景打下基础
