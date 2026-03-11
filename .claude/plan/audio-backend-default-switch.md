# 音频转录后端默认值切换实施计划

## 1. 需求概述

**目标**：将音频/视频转录的默认后端从 AUC (ByteDance API) 切换为本地 Qwen3-ASR，AUC 模式改为可选，通过命令行参数显式启用。

**当前状态**：
- 默认后端：`--audio-backend auc`（第52 行）
- 可选后端：`--audio-backend qwen-local`
- 两种后端都已完全实现并可用

**目标状态**：
- 默认后端：`--audio-backend qwen-local`
- 可选后端：`--audio-backend auc`（需显式指定）

---

## 2. 详细实施计划

### 2.1 文件修改清单

#### A. `src/any2md/cli.py` - 参数定义与验证

**位置 1**：第 49-54 行 - 参数定义
```python
parser.add_argument(
    "--audio-backend",
    choices=["auc", "qwen-local"],
    default="auc",  # ← 改为 "qwen-local"
    help="Choose the audio transcription backend.",
)
```

**修改内容**：
- `default="auc"` → `default="qwen-local"`
- 更新 `help` 文本，说明新的默认行为

**位置 2**：第 228-325 行 - 参数验证逻辑

需要更新三处验证条件，因为它们检查 `args.audio_backend != "auc"`：

1. **第 240行**（`_validate_args` 中`--auc-status` 验证）
   - 当前：`or args.audio_backend != "auc"`
   - 逻辑：`--auc-status` 只能与 AUC 后端一起使用
   - **无需修改**（逻辑仍然正确）

2. **第 265 行**（`--manifest-list` 验证）
   - 当前：`or args.audio_backend != "auc"`
   - 逻辑：`--manifest-list` 不能与任何音频后端选项混用
   - **无需修改**（逻辑仍然正确）

3. **第 294 行**（`--manifest-prune` 验证）
   - 当前：`or args.audio_backend != "auc"`
   - 逻辑：`--manifest-prune` 不能与任何音频后端选项混用
   - **无需修改**（逻辑仍然正确）

4. **第 319-320 行**（`--no-wait` 验证）
   ```python
   if args.no_wait:
       if args.audio_backend != "auc":
           parser.error("--no-wait is only available with --audio-backend auc")
   ```
   - **无需修改**（逻辑正确，`--no-wait` 确实只支持 AUC）

**位置 3**：第 136行 - 主函数中的后端检测
```python
allow_local_audio_inputs = args.audio_backend == "qwen-local"
```
- **无需修改**（逻辑已正确）

**位置 4**：第 327-356 行 - `_build_audio_converter()` 函数
```python
def _build_audio_converter(args, error_stream):
    if args.audio_backend == "qwen-local":
        # ... qwen-local 逻辑
        return (QwenAsrAudioConverter(...), True)

    return (AudioConverter(...), False)  # AUC 后端
```
- **无需修改**（逻辑已正确处理两种情况）

#### B. `README.md` - 文档更新

**位置 1**：第 122-129 行 - 音频输入规则部分

当前文本：
```markdown
### Audio input rules

> AUC mode supports direct remote audio URLs; local mode supports both local files and direct URLs.
```

**修改内容**：
- 更新说明，反映 Qwen3-ASR 现在是默认后端
- 说明如何使用 AUC 模式（需显式指定 `--audio-backend auc`）

**位置 2**：第 130-146 行 - 本地 Qwen3-ASR 后端部分

当前标题：`### Local Qwen3-ASR backend`

**修改内容**：
- 改为 `### Default: Local Qwen3-ASR backend`
- 更新示例，移除 `--audio-backend qwen-local`（因为现在是默认值）
- 添加说明：不需要指定后端参数即可使用本地转录

**位置 3**：第 165-177 行 - 长音频工作流部分

当前文本提到 `--no-wait` 和 `--auc-status`

**修改内容**：
- 添加说明：这些选项仅适用于 AUC 模式
- 更新示例，显示如何显式启用 AUC 模式

**位置 4**：第 253-260 行 - 已知限制部分

当前：
```markdown
- In AUC mode, audio files must be accessible via direct URL.
- Local audio file paths are supported when `--audio-backend qwen-local` is selected.
```

**修改内容**：
- 改为：`Local audio file paths are supported by default (Qwen3-ASR mode).`
- 添加：`When using AUC mode (--audio-backend auc), audio files must be accessible via direct URL.`

**位置 5**：第 262-270 行 - 注释部分

当前：
```markdown
- Audio conversion supports both ByteDance AUC and the local Qwen3-ASR backend.
- Local audio files are supported when `--audio-backend qwen-local` is selected.
```

**修改内容**：
- 改为：`Audio conversion uses local Qwen3-ASR by default, with optional ByteDance AUC support.`
- 移除重复的本地文件支持说明

#### C. `README.zh-CN.md` - 中文文档更新

对应英文文档的所有修改，应用到中文版本。

---

## 3. 参数设计方案

### 3.1 命令行参数变更

**参数名**：`--audio-backend`

**可选值**：
- `qwen-local`（新默认值）
- `auc`（需显式指定）

**使用示例**：

```bash
# 默认使用 Qwen3-ASR（无需指定参数）
any2md demo.mp3 --output output/

# 显式指定 Qwen3-ASR（与默认行为相同）
any2md demo.mp3 --audio-backend qwen-local --output output/

# 使用 AUC 模式（需显式指定）
any2md "https://example.com/audio.mp3" --audio-backend auc --output output/

# AUC 模式 + 不等待完成
any2md "https://example.com/audio.mp3" --audio-backend auc --no-wait
```

### 3.2 参数验证规则（无需修改）

现有验证规则已正确处理新的默认值：

1. `--no-wait` 仅在 `--audio-backend auc` 时允许 ✓
2. `--auc-status` 仅在 `--audio-backend auc` 时允许 ✓
3. `--manifest-list` 和 `--manifest-prune` 不允许任何音频后端选项 ✓
4. Qwen 相关参数（`--qwen-*`）仅在 `--audio-backend qwen-local` 时有效 ✓

---

## 4. 向后兼容性处理

### 4.1 兼容性分析

**现有脚本的影响**：

1. **未指定 `--audio-backend` 的脚本**
   - 旧行为：使用 AUC
   - 新行为：使用 Qwen3-ASR
   - **影响**：需要更新脚本或显式指定 `--audio-backend auc`

2. **显式指定 `--audio-backend qwen-local` 的脚本**
   - 旧行为：使用 Qwen3-ASR
   - 新行为：使用 Qwen3-ASR
   - **影响**：无（完全兼容）

3. **显式指定 `--audio-backend auc` 的脚本**
   - 旧行为：使用 AUC
   - 新行为：使用 AUC
   - **影响**：无（完全兼容）

### 4.2 迁移建议

**对用户的建议**：

1. **如果依赖 AUC 模式**：
   - 在现有脚本中添加 `--audio-backend auc`
   - 示例：`any2md audio.mp3 --audio-backend auc --output output/`

2. **如果已使用 Qwen3-ASR**：
   - 无需修改（可选择移除 `--audio-backend qwen-local` 参数）

3. **新用户**：
   - 默认获得本地转录能力，无需额外配置

### 4.3 版本号更新

建议在 `pyproject.toml` 中更新版本号：
- 当前：`0.3.0`
- 建议：`0.4.0`（主要功能变更）

---

## 5. 潜在风险点与注意事项

### 5.1 风险点

| 风险 | 影响范围 | 缓解措施 |
|------|--------|--------|
| 现有 AUC 脚本失效 | 依赖 AUC 的用户 | 在 CHANGELOG 中明确说明，提供迁移指南 |
| 环境配置不完整 | Qwen3-ASR 依赖 | 确保 `qwen-asr` 在 `pyproject.toml` 中（已有） |
| 验证逻辑遗漏 | 参数组合错误 | 现有验证规则已完整，无需修改 |
| 文档不一致 | 用户困惑 | 同时更新英文和中文文档 |

### 5.2 注意事项

1. **验证逻辑检查**
   - 三处 `args.audio_backend != "auc"` 的检查逻辑仍然正确
   - 这些检查用于确保 `--auc-status` 和 `--no-wait` 只在 AUC 模式下使用
   - 新的默认值不会影响这些检查的有效性

2. **环境变量**
   - Qwen3-ASR 相关环境变量已在 `.env.example` 中定义
   - AUC 相关环境变量仍然可用（用户显式启用 AUC 时）

3. **测试覆盖**
   - 需要测试默认行为（不指定 `--audio-backend`）
   - 需要测试显式指定两种后端的情况
   - 需要测试参数验证规则

4. **CHANGELOG 更新**
   - 明确说明这是破坏性变更
   - 提供迁移指南
   - 解释为什么做出这个改变

---

## 6. 文档更新清单

### 6.1 需要更新的文件

- [ ] `src/any2md/cli.py` - 第 52 行：改变默认值
- [ ] `README.md` - 多处更新（见 2.1 节 B 部分）
- [ ] `README.zh-CN.md` - 对应中文更新
- [ ] `CHANGELOG.md` - 添加版本记录和迁移指南
- [ ] `.env.example` - 确认 Qwen3-ASR 配置已包含（可能已有）

### 6.2 文档更新要点

1. **快速开始部分**
   - 强调本地 Qwen3-ASR 是默认后端
   - 移除 `--audio-backend qwen-local` 从基础示例

2. **音频输入规则部分**
   - 更新为：本地文件现在默认支持
   - AUC 模式需显式启用

3. **长音频工作流部分**
   - 添加说明：`--no-wait` 和 `--auc-status` 仅适用于 AUC 模式
   - 更新示例：`--audio-backend auc --no-wait`

4. **已知限制部分**
   - 调整措辞，反映新的默认行为

5. **CHANGELOG**
   - 版本：0.4.0
   - 类型：Breaking Change
   - 说明：默认音频后端从 AUC 改为 Qwen3-ASR
   - 迁移指南：如何在现有脚本中启用 AUC

---

## 7. 测试验证要点

### 7.1 功能测试

```bash
# 测试 1：默认行为（应使用 Qwen3-ASR）
any2md demo.mp3 --output output/

# 测试 2：显式指定 Qwen3-ASR
any2md demo.mp3 --audio-backend qwen-local --output output/

# 测试 3：显式指定 AUC
any2md "https://example.com/audio.mp3" --audio-backend auc --output output/

# 测试 4：AUC + --no-wait
any2md "https://example.com/audio.mp3" --audio-backend auc --no-wait

# 测试 5：验证 --no-wait 不能与 qwen-local 一起使用
any2md demo.mp3 --audio-backend qwen-local --no-wait  # 应报错

# 测试 6：验证 --auc-status 不能与 qwen-local 一起使用
any2md --auc-status task-id --audio-backend qwen-local  # 应报错
```

### 7.2 参数验证测试

- [ ] `--no-wait` 仅在 AUC 模式下允许
- [ ] `--auc-status` 仅在 AUC 模式下允许
- [ ] `--qwen-*` 参数仅在 Qwen3-ASR 模式下有效
- [ ] `--manifest-list` 和 `--manifest-prune` 不允许任何音频后端选项

### 7.3 回归测试

- [ ] 现有 Qwen3-ASR 脚本仍然工作
- [ ] 现有 AUC 脚本在添加 `--audio-backend auc` 后仍然工作
- [ ] 其他转换器（PDF、图像等）不受影响

---

## 8. 实施步骤

### 第 1 步：代码修改
1. 修改 `src/any2md/cli.py` 第 52 行：`default="qwen-local"`
2. 更新 help 文本说明默认行为
3. 验证参数验证逻辑无需修改

### 第 2 步：文档更新
1. 更新 `README.md`
2. 更新 `README.zh-CN.md`
3. 更新 `CHANGELOG.md`

### 第 3 步：测试
1. 运行单元测试
2. 手动测试各种参数组合
3. 验证错误消息清晰

### 第 4 步：发布
1. 更新版本号为 0.4.0
2. 提交 PR 并进行代码审查
3. 合并到 main 分支
4. 发布新版本

---

## 9. 总结

这个变更是一个**破坏性变更**（Breaking Change），但影响范围有限：

- **受影响用户**：仅限于未显式指定 `--audio-backend` 且依赖 AUC 的用户
- **迁移成本**：低（仅需添加一个参数）
- **收益**：
  - 降低新用户的使用门槛（无需配置 AUC API）
  - 提供更好的隐私性（本地处理）
  - 减少网络依赖

**代码修改最小化**：仅需修改 1-2 行代码（`default="qwen-local"` + help 文本），其余都是文档更新。
