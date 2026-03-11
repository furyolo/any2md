# Team Research: 项目升级为原生异步

## 增强后的需求

**目标**：将 any2md 项目升级为原生异步架构

**范围**：
- 批量处理异步化：保持单文件转换同步，批量处理时并发执行多个转换任务
- 网络请求异步化：HTTP请求（AUC API、OCR API）改为异步
- 架构现代化：采用 Python asyncio 生态

**技术约束**：
- Python 3.10+
- 允许破坏性变更（可升级到 1.0.0）
- 相对性能提升即可，无具体量化指标
- 主要目标：提升批量处理性能、优化网络请求效率、架构现代化

**验收标准**：
- 批量处理时能并发执行多个文件转换
- 网络 I/O 不阻塞其他任务
- 功能完全正确
- 比当前同步版本更快

---

## 约束集

### 硬约束

#### [HC-1] httpx 已支持异步 — 来源：代码分析
- **描述**：项目已使用 httpx 库，该库原生支持 `httpx.AsyncClient`
- **影响**：无需引入新的 HTTP 库，直接升级为异步调用
- **位置**：
  - `src/any2md/auc/client.py` (第 55、111 行)
  - `src/any2md/converters/audio.py` (第 280 行)

#### [HC-2] urllib 不支持异步 — 来源：代码分析
- **描述**：`src/any2md/ocr.py` 使用 `urllib.request.urlopen` 进行 HTTP 调用
- **影响**：必须替换为 httpx.AsyncClient
- **位置**：`src/any2md/ocr.py` 第 11、145 行

#### [HC-3] subprocess 同步调用 — 来源：代码分析
- **描述**：本地 Qwen ASR 使用 `subprocess.run()` 调用外部进程
- **影响**：需改为 `asyncio.create_subprocess_exec()`
- **位置**：`src/any2md/converters/audio.py` 第 249 行

#### [HC-4] 文件锁使用系统级锁 — 来源：代码分析
- **描述**：`OutputFileLock` 使用 msvcrt/fcntl 实现跨进程文件锁
- **影响**：系统级锁是同步阻塞的，需要在异步环境中适配
- **位置**：`src/any2md/locking.py` 第 32、34 行
- **用户决策**：改为异步锁（使用 asyncio.Lock + aiofiles）

#### [HC-5] 批量处理顺序循环 — 来源：代码分析
- **描述**：`ConversionService.run()` 使用 `for job in jobs` 顺序处理
- **影响**：这是性能瓶颈，需改为 `asyncio.gather()` 并发执行
- **位置**：`src/any2md/app.py` 第 404-533 行

#### [HC-6] Manifest 写入非原子 — 来源：代码分析
- **描述**：`BatchManifest.save()` 使用临时文件 + replace 实现原子写入
- **影响**：在异步并发环境下，多个任务可能同时更新 manifest，需要加锁保护
- **位置**：`src/any2md/manifest.py` 第 56-64 行

#### [HC-7] AUC 轮询使用 time.sleep — 来源：代码分析
- **描述**：`AucClient._poll()` 使用 `time.sleep()` 阻塞等待
- **影响**：需改为 `asyncio.sleep()` 避免阻塞事件循环
- **位置**：`src/any2md/auc/client.py` 第 140 行

#### [HC-8] CLI 入口点是同步函数 — 来源：代码分析
- **描述**：`main()` 函数是同步的，返回 int 退出码
- **影响**：需要在 main() 内部使用 `asyncio.run()` 启动异步运行时
- **位置**：`src/any2md/cli.py` 第 100 行

---

### 软约束

#### [SC-1] 保持 CLI 接口不变 — 来源：用户需求
- **描述**：虽然允许破坏性变更，但 CLI 参数应尽量保持兼容
- **建议**：内部异步化，外部接口不变

#### [SC-2] 转换器接口统一 — 来源：代码分析
- **描述**：所有转换器遵循 `Converter = Callable[[ConverterInput], str]` 协议
- **影响**：需要将协议改为 `AsyncConverter = Callable[[ConverterInput], Awaitable[str]]`
- **位置**：`src/any2md/registry.py` 第 18 行

#### [SC-3] 错误处理保持一致 — 来源：代码分析
- **描述**：当前使用自定义异常类（Any2MDError 及其子类）
- **建议**：异步版本继续使用相同的异常体系

#### [SC-4] 测试覆盖率 — 来源：项目结构
- **描述**：项目有 `tests/` 目录，存在单元测试
- **影响**：异步化后需要更新测试，使用 `pytest-asyncio`

---

### 依赖关系

#### [DEP-1] ConversionService → ConverterRegistry → Converters
- **描述**：服务层依赖注册表，注册表依赖各个转换器
- **影响**：必须自底向上异步化（先转换器，再注册表，最后服务层）

#### [DEP-2] AucClient → httpx
- **描述**：AUC 客户端依赖 httpx 进行 HTTP 调用
- **影响**：需要将 `httpx.post()` 改为 `async with httpx.AsyncClient() as client: await client.post()`

#### [DEP-3] OcrEngine → urllib/httpx
- **描述**：OCR 引擎依赖 HTTP 库调用 LLM API
- **影响**：需要完全替换 urllib 为 httpx.AsyncClient

#### [DEP-4] LocalQwenAudioConverter → subprocess
- **描述**：本地 ASR 依赖 subprocess 调用外部程序
- **影响**：需要改为 `asyncio.create_subprocess_exec()`

#### [DEP-5] ConversionService → OutputFileLock
- **描述**：服务层在写入文件前获取文件锁
- **影响**：文件锁必须支持异步上下文管理器

#### [DEP-6] ConversionService → BatchManifest
- **描述**：服务层在每次转换后更新 manifest
- **影响**：manifest 更新需要加锁保护（避免并发写入冲突）

---

### 风险

#### [RISK-1] 并发竞态条件 — 缓解：使用 asyncio.Lock 保护共享状态
- **描述**：多个任务并发写入 manifest 可能导致数据丢失
- **缓解策略**：在 ConversionService 中维护一个 asyncio.Lock，保护 manifest.update() 和 manifest.save()

#### [RISK-2] 文件锁语义变化 — 缓解：使用 aiofiles + asyncio.Lock
- **描述**：从跨进程锁改为进程内锁，可能影响多进程并发场景
- **缓解策略**：
  - 短期：使用 asyncio.Lock（仅保护单进程内并发）
  - 长期：如需跨进程保护，使用 `asyncio.to_thread()` 包装同步锁

#### [RISK-3] 子进程管道阻塞 — 缓解：使用 asyncio.create_subprocess_exec
- **描述**：subprocess 输出过大可能导致管道阻塞
- **缓解策略**：使用异步子进程，异步读取 stdout/stderr

#### [RISK-4] HTTP 连接池耗尽 — 缓解：限制并发数
- **描述**：无限制并发可能导致 HTTP 连接池耗尽或 API 限流
- **缓解策略**：使用 `asyncio.Semaphore` 限制并发数（用户决策：限制并发数）

#### [RISK-5] 内存占用增加 — 缓解：流式处理 + 并发限制
- **描述**：大量并发任务可能导致内存占用激增
- **缓解策略**：
  - 使用 Semaphore 限制并发数
  - 对大文件使用流式读写

#### [RISK-6] 测试复杂度增加 — 缓解：使用 pytest-asyncio
- **描述**：异步代码的测试需要特殊处理
- **缓解策略**：引入 pytest-asyncio，使用 `@pytest.mark.asyncio` 装饰器

---

## 用户决策记录

### Q1: 批量处理时的并发控制策略？
**回答**：限制并发数（推荐）
**约束**：[HC-9] 使用 asyncio.Semaphore 限制并发数，默认值建议为 10

### Q2: 文件锁（OutputFileLock）如何适配异步环境？
**回答**：改为异步锁
**约束**：[HC-10] 使用 asyncio.Lock + aiofiles 实现异步文件锁，放弃跨进程保护

### Q3: httpx.AsyncClient 的生命周期管理？
**回答**：服务级管理（推荐）
**约束**：[HC-11] 在 ConversionService 中持有 AsyncClient，在 run() 开始时创建，结束时关闭

### Q4: 批量异步处理时是否需要实时进度反馈？
**回答**：回调机制
**约束**：[SC-5] 提供可选的进度回调接口，允许用户自定义进度处理逻辑

---

## 成功判据

### [OK-1] 批量处理性能提升
- **验证方式**：对比同步版本和异步版本处理 100 个文件的总耗时
- **预期结果**：异步版本耗时显著低于同步版本（至少 30% 提升）

### [OK-2] 网络请求并发执行
- **验证方式**：使用网络抓包工具观察 HTTP 请求时序
- **预期结果**：多个 HTTP 请求并发发送，而非顺序发送

### [OK-3] 功能完全正确
- **验证方式**：运行现有测试套件，确保所有测试通过
- **预期结果**：异步版本的输出与同步版本完全一致

### [OK-4] 并发安全
- **验证方式**：并发处理输出到同一目录的多个文件，检查 manifest 完整性
- **预期结果**：无数据丢失，无文件冲突

### [OK-5] CLI 接口兼容
- **验证方式**：使用现有的 CLI 命令测试异步版本
- **预期结果**：所有命令正常工作，输出格式保持一致

---

## 技术实施路径

### Phase 1: 基础设施层异步化
1. 将 `httpx.post()` 改为 `httpx.AsyncClient`
2. 将 `urllib.urlopen()` 改为 `httpx.AsyncClient`
3. 将 `subprocess.run()` 改为 `asyncio.create_subprocess_exec()`
4. 实现异步文件锁（AsyncOutputFileLock）
5. 为 BatchManifest 添加并发保护

### Phase 2: 转换器层异步化
1. 定义 `AsyncConverter` 协议
2. 将所有转换器改为 async 函数
3. 更新 ConverterRegistry 支持异步转换器

### Phase 3: 服务层异步化
1. 将 `ConversionService.run()` 改为 async 方法
2. 使用 `asyncio.gather()` 并发执行转换任务
3. 添加 `asyncio.Semaphore` 限制并发数
4. 实现进度回调机制

### Phase 4: CLI 层适配
1. 在 `main()` 中使用 `asyncio.run()` 启动异步运行时
2. 保持 CLI 参数和输出格式不变

### Phase 5: 测试和优化
1. 更新测试套件，使用 pytest-asyncio
2. 性能基准测试
3. 并发安全测试
4. 文档更新

---

## 依赖变更

### 新增依赖
- `aiofiles` - 异步文件 I/O
- `pytest-asyncio` - 异步测试支持（开发依赖）

### 现有依赖升级
- `httpx` - 已支持异步，无需升级

### 移除依赖
- 无（urllib 是标准库，保留用于其他用途）

---

## 预估工作量

- **Phase 1**: 2-3 天（基础设施层）
- **Phase 2**: 2-3 天（转换器层）
- **Phase 3**: 3-4 天（服务层 + 并发控制）
- **Phase 4**: 1 天（CLI 适配）
- **Phase 5**: 2-3 天（测试和优化）

**总计**: 10-14 天

---

## 开放问题（已解决）

所有关键决策点已通过用户确认解决，无遗留开放问题。
