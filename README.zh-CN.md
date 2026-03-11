# any2md

[![English](https://img.shields.io/badge/Docs-English-2d7ff9)](README.md)
[![简体中文](https://img.shields.io/badge/文档-简体中文-e85d75)](README.zh-CN.md)

[![版本](https://img.shields.io/badge/版本-0.3.0-2ea44f)](pyproject.toml)
[![Python](https://img.shields.io/badge/python-3.10+-3776AB?logo=python&logoColor=white)](pyproject.toml)
[![接口](https://img.shields.io/badge/接口-CLI-5c6ac4)](main.py)

一个用于在命令行中将常见文档格式转换为 Markdown 的轻量工具。

[![Project Brief EN](https://img.shields.io/badge/Project_Brief-English-2d7ff9)](PROJECT_BRIEF.en.md)
[![项目说明](https://img.shields.io/badge/项目说明-简体中文-e85d75)](PROJECT_BRIEF.md)
[![更新记录](https://img.shields.io/badge/更新记录-latest-blue)](CHANGELOG.md)

## 功能亮点

- 支持将 `.pdf`、`.epub`、`.html`、`.txt`、`.docx`、常见图片格式、音频文件和视频文件转换为 Markdown。
- 支持单文件转换、目录批量转换和递归扫描。
- 支持用 `--dry-run` 先规划，用 `--force` 控制覆盖已有输出。
- 对输出文件增加文件锁，避免多个进程同时写入同一路径。
- 本地 Qwen3-ASR 长音频分片转录支持断点续传，中断后重新执行相同命令即可继续。
- 批量任务重复执行时，会自动跳过已完成输出，便于失败后续跑剩余文件。
- 批量模式会在输出目录写入 `.any2md-manifest.json`，记录输入哈希、状态、失败原因和最近执行时间。
- 可配合 `--resume-failed-only` 只重试 manifest 中上次失败的条目。
- 可用 `--manifest-list` / `--manifest-status` 直接查看批量任务清单和失败项。
- 可用 `--manifest-prune` 清理 manifest 中已失效的输出记录。
- 支持用 `--t2s` 在提取完成后执行繁体转简体。
- 图片 OCR 使用兼容 OpenAI 的视觉聊天模型，输出 Markdown，并清理常见 OCR 包装文本。
- 音频转录默认使用本地 Qwen3-ASR-1.7B，可通过 `--audio-backend auc` 选择字节跳动 AUC 支持。

## 快速开始

### 安装

```bash
uv sync
```

### 配置 OCR 和音频转录

先复制示例环境变量文件：

```bash
cp .env.example .env
```

然后在 `.env` 中配置：

**图片 OCR：**

```env
ANY2MD_LLM_API_BASE=https://api.openai.com/v1
ANY2MD_LLM_API_KEY=sk-your-api-key
ANY2MD_LLM_MODEL=gpt-4.1-mini
```

支持 OpenAI 和 Anthropic API，系统会自动检测 API 类型：
- OpenAI 示例：`ANY2MD_LLM_API_BASE=https://api.openai.com/v1`，`ANY2MD_LLM_MODEL=gpt-4o-mini`
- Anthropic 示例：`ANY2MD_LLM_API_BASE=https://api.anthropic.com/v1`，`ANY2MD_LLM_MODEL=claude-3-5-sonnet-20241022`
- 如果使用第三方代理且自动检测失败，可手动指定：`ANY2MD_LLM_API_TYPE=anthropic`（可选值：`openai` 或 `anthropic`）

**音频转录：**

```env
ANY2MD_AUC_APP_ID=your-app-id
ANY2MD_AUC_ACCESS_KEY=your-access-key
ANY2MD_AUC_RESOURCE_ID=volc.seedasr.auc
```

**本地 Qwen3-ASR-1.7B 音频转录：**

```env
ANY2MD_QWEN_AUDIO_RUNTIME=qwen-asr
ANY2MD_QWEN_AUDIO_MODEL=Qwen/Qwen3-ASR-1.7B
ANY2MD_QWEN_AUDIO_LANGUAGE=auto
ANY2MD_QWEN_AUDIO_TIMEOUT=3600
ANY2MD_QWEN_AUDIO_DEVICE_MAP=cpu
ANY2MD_QWEN_AUDIO_DTYPE=float32
```

说明：

- `ANY2MD_LLM_API_BASE` 既可以填写兼容 OpenAI 的服务根地址，也支持直接填写完整的 `/chat/completions` 地址。
- `ANY2MD_LLM_API_KEY` 是对应服务的 API Key。
- `ANY2MD_LLM_MODEL` 需要是支持图片输入的视觉模型。
- `ANY2MD_AUC_APP_ID` 和 `ANY2MD_AUC_ACCESS_KEY` 是字节跳动 AUC API 凭证。
- `ANY2MD_QWEN_AUDIO_EXECUTABLE` 和 `ANY2MD_QWEN_AUDIO_MODEL` 用于配置本地 Qwen3-ASR 运行时。
- `ANY2MD_QWEN_AUDIO_RUNTIME=qwen-asr` 是当前默认推荐方案，`ANY2MD_QWEN_AUDIO_MODEL` 可直接填写官方模型 ID，首次运行会自动下载。
- 如果你想强制在 CPU 上运行，可使用 `ANY2MD_QWEN_AUDIO_DEVICE_MAP=cpu` 与 `ANY2MD_QWEN_AUDIO_DTYPE=float32`。
- `ANY2MD_QWEN_AUDIO_COMMAND_TEMPLATE` 是可选项，仅在你使用 `chatllm.cpp` 或 `llama.cpp` 等实验性运行时时需要。
- `chatllm.cpp` 与 `llama.cpp` 对 `Qwen3-ASR` 的支持仍受上游版本影响，当前更稳妥的本地方案是官方 `qwen-asr`。
- 在处理图片或音频时，CLI 会自动从当前工作目录加载 `.env`。

### 基本用法

```bash
uv run python main.py input.pdf
uv run python main.py image.png
uv run python main.py https://example.com/audio.mp3
uv run python main.py local-audio.mp3
uv run python main.py "C:/Users/foogl/Music/demo.mp3"
uv run any2md input.docx --output output/
uv run python main.py docs/ --output output/ --recursive
```

### 异步与并发控制

默认情况下，any2md 在转换多个文件时使用异步处理以获得更好的性能：

```bash
# 默认：异步模式，5个并发转换
uv run python main.py docs/ --output output/ --recursive

# 控制并发数量
uv run python main.py docs/ --output output/ --recursive --max-concurrent 10

# 强制使用同步模式（逐个处理文件）
uv run python main.py docs/ --output output/ --recursive --sync
```

- `--max-concurrent N`：设置最大并发文件转换数（默认：5）
- `--sync`：强制使用同步模式而非异步处理

异步模式显著提升批量转换性能，特别是在处理涉及网络请求的文件（OCR、音频转录）时。

### 音频输入规则

> 默认情况下，any2md 使用本地 Qwen3-ASR 进行离线转录，同时支持本地文件和直接 URL。AUC 模式需要显式指定 `--audio-backend auc`，且仅支持远程 URL。

- **默认（Qwen3-ASR）**：支持本地音频文件（如 `demo.mp3`、`record.wav`）和直接 `http://` 或 `https://` 音频 URL。
- **AUC 模式**：需要 `--audio-backend auc`，仅支持直接远程音频 URL。
- 支持的音频后缀：`.mp3`、`.wav`、`.m4a`、`.aac`、`.flac`、`.ogg`。

### 默认：本地 Qwen3-ASR 后端

本地 Qwen3-ASR 是默认的音频转录后端，无需额外参数：

```bash
uv run python main.py demo.mp3
uv run python main.py demo.wav --output output/demo.md
uv run python main.py demo.flac --qwen-runtime qwen-asr
uv run python main.py "https://example.com/audio.mp3"
```

- 默认启用本地音频转录，同时支持本地音频文件和直接 URL。
- `--qwen-runtime qwen-asr` 是当前默认推荐方案，兼容官方 `Qwen/Qwen3-ASR-1.7B` 模型 ID 或本地预训练模型目录。
- `--qwen-runtime chatllm.cpp` 适合搭配 chatllm.cpp 自有模型格式（如 `.bin`），不适合直接加载 `.gguf`。
- `--qwen-runtime llama.cpp` 只有在上游版本已支持 `qwen3-asr` 架构时才可用；如需自定义命令，再提供 `--qwen-command-template` 或 `ANY2MD_QWEN_AUDIO_COMMAND_TEMPLATE`。
- 本地后端也兼容直接音频 URL；CLI 会先临时下载音频，再交给本地模型处理。

如果你希望明确指定模型来源，可以这样写：

```bash
uv run python main.py demo.mp3 --qwen-model Qwen/Qwen3-ASR-1.7B
uv run python main.py demo.mp3 --qwen-model "D:/Coding/models/Qwen3-ASR-1.7B"
```

如果你希望明确指定设备：

```bash
# CPU（默认）
uv run python main.py demo.mp3

# GPU（需要支持 CUDA 的 torch）
set ANY2MD_QWEN_AUDIO_DEVICE_MAP=cuda && uv run python main.py demo.mp3
```

### AUC 后端（可选）

要使用字节跳动 AUC 进行远程音频转录，需显式指定 `--audio-backend auc`：

```bash
uv run python main.py "https://example.com/audio.mp3" --audio-backend auc
```

- AUC 模式仅支持直接远程音频 URL（不支持本地文件）。
- 需要在 `.env` 中配置 AUC 凭证（见配置部分）。

### 长音频交互方式（仅限 AUC 模式）

对于较长音频，使用 AUC 后端时可以先提交任务，再稍后查询：

```bash
uv run python main.py "https://example.com/audio.mp3" --audio-backend auc --no-wait
uv run python main.py --auc-status <task-id>
uv run python main.py --auc-status <task-id> --output output/audio.md
```

- `--no-wait` 提交单个远程音频 URL 后立即返回任务 ID（仅限 AUC 模式）。
- `--auc-status <task-id>` 从本地任务缓存查询之前提交的任务（仅限 AUC 模式）。
- 当任务在等待窗口后仍在处理时，CLI 会报告仍在处理中，而不是视为硬失败。
- `--no-wait` 会提交单个远程音频 URL，并立即返回任务 ID。
- `--auc-status <task-id>` 会从本地任务缓存中读取任务并查询当前状态。
- 当任务在等待窗口内尚未完成时，CLI 会提示“仍在处理中”，而不是直接判定为失败。

## 特性说明

- 通过统一注册表按文件后缀自动选择对应转换器。
- 批量转换时，会在输出目录下保留输入文件的相对目录结构。
- `--dry-run` 会先执行规划、冲突检查和覆盖检查，再决定是否写入。
- 输出阶段会对目标文件加锁；若目标正被其他 `any2md` 进程占用，会直接报错而不是相互覆盖。
- 本地 Qwen3-ASR 分片转录会在输出旁写入续传状态文件；异常中断后再次执行相同命令会从已完成切片继续。
- 批量模式下再次执行同一批输入时，已存在且无续传状态的输出会被视为已完成并自动跳过。
- `.any2md-manifest.json` 会按输出文件维度记录 `input_hash`、`status`、`last_error`、`last_run_at`，输入变化时会自动重新转换。
- 繁体转简体是按需加载的可选后处理能力。
- 图片处理默认使用 LLM OCR，同时保留可扩展的 OCR 接口。
- OCR 清洗会规范标题、列表，并将结构稳定的对齐文本块整理为 Markdown 表格。
- 音频转录默认使用本地 Qwen3-ASR，可通过 `--audio-backend auc` 选择字节跳动 AUC 支持。

## 支持的格式

- `.pdf`
- `.epub`
- `.html` / `.htm`
- `.txt`（自动识别 UTF-8 / UTF-16 BOM，必要时回退 GB18030）
- `.docx`
- `.jpg` / `.jpeg` / `.png`（需要在 `.env` 中配置 OCR）
- 以 `.mp3`、`.wav`、`.m4a`、`.aac`、`.flac`、`.ogg` 结尾的直接音频 URL（默认使用本地 Qwen3-ASR，或通过 `--audio-backend auc` 使用 AUC）
- 本地 `.mp3`、`.wav`、`.m4a`、`.aac`、`.flac`、`.ogg` 文件（默认通过本地 Qwen3-ASR 支持）

## 用法示例

```bash
uv run python main.py input.pdf
uv run python main.py image.png
uv run python main.py https://example.com/audio.mp3
uv run python main.py input.pdf --dry-run
uv run python main.py input.epub --t2s
uv run python main.py note.txt --output result.md
uv run python main.py docs/ --output output/ --recursive
uv run python main.py note.txt --output result.md --force
uv run python main.py docs/ --output output/ --resume-failed-only
uv run python main.py --manifest-list output/
uv run python main.py --manifest-list output/ --manifest-status failed
uv run python main.py --manifest-prune output/
uv run any2md input.docx --output output/
```

## 输出规则

- 单文件且未指定 `--output`：写入 `output/<源文件主名>.md`。
- 单文件且 `--output` 指向文件路径：写入该文件。
- 单文件且 `--output` 指向已有目录，或路径以 `/` 或 `\\` 结尾：在该目录内写入 `<主名>.md`。
- 批量模式默认输出到 `output/` 目录。
- 批量模式下，`--output` 会被视为输出目录，除非该路径已存在且是普通文件。
- 批量模式会保留从输入目录扫描到的文件的相对目录结构。
- 除非显式传入 `--force`，否则不会覆盖已存在的输出文件。
- 如果检测到对应的续传状态文件，则允许继续未完成的分片转录，而不会把它误判成普通覆盖冲突。
- 批量模式下，如果目标文件已存在且无续传状态，则默认跳过该文件；单文件模式仍需使用 `--force` 才会覆盖。
- 如果 manifest 记录显示输入内容已变化，批量模式会自动重新转换并覆盖旧输出，无需额外传入 `--force`。
- `--resume-failed-only` 仅在批量模式下有意义：它会跳过上次已成功或未记录失败的条目，只重试 manifest 中状态为 `failed` 的文件。
- `--manifest-list <目录>` 会读取该输出目录下的 `.any2md-manifest.json` 并列出所有条目。
- `--manifest-status <状态>` 需要配合 `--manifest-list` 使用，可筛选 `converted`、`failed`、`pending`、`skipped`。
- `--manifest-prune <目录>` 会删除 `.any2md-manifest.json` 中那些对应输出文件已经不存在的条目。
- `--dry-run` 会执行文件发现、跳过统计、输出规划、冲突检查和覆盖检查，但不会真正写入文件。

## 退出码

- `0`：没有失败项，且至少有一个条目成功转换或完成规划。
- `1`：没有产生有效的转换或规划结果，例如全部被跳过或全部失败。
- `2`：部分失败，至少有一个条目成功转换或完成规划，同时至少有一个条目失败。

## 已知限制

- 图片 OCR 支持 OpenAI 和 Anthropic 兼容的视觉模型，系统会根据 URL 或模型名称自动检测 API 类型。
- 本地音频文件默认支持（Qwen3-ASR 模式）。
- 使用 AUC 模式（`--audio-backend auc`）时，音频文件必须能通过直接 URL 访问。
- 提取质量依赖源文档质量以及上游解析库能力。
- 运行日志和状态汇总写入 `stderr`，不会写入 `stdout`。
- 不支持的文件会被跳过，而不是强制尝试转换。

## 说明

- `--t2s` 会按需加载 OpenCC，并在提取完成后执行繁体转简体。
- 图片转换支持 OpenAI 和 Anthropic 兼容的视觉模型进行 OCR，系统会自动检测 API 类型并使用相应的端点格式（OpenAI: `/v1/chat/completions`，Anthropic: `/v1/messages`）。
- 音频转换默认使用本地 Qwen3-ASR，可通过 `--audio-backend auc` 选择字节跳动 AUC 支持。
- 视频文件会自动提取音轨后，使用选定的音频后端进行转录。
- 无论是不支持的文件直接传入，还是在目录扫描中发现，都会被标记为跳过。
- 运行日志、单文件状态和汇总信息会输出到 `stderr`；`stdout` 预留给未来的内容输出能力。

## 测试

```bash
uv run python -m unittest discover -s tests
```
