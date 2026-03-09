# any2md

[![English](https://img.shields.io/badge/Docs-English-2d7ff9)](README.md)
[![简体中文](https://img.shields.io/badge/文档-简体中文-e85d75)](README.zh-CN.md)

[![版本](https://img.shields.io/badge/版本-0.2.0-2ea44f)](pyproject.toml)
[![Python](https://img.shields.io/badge/python-3.10+-3776AB?logo=python&logoColor=white)](pyproject.toml)
[![接口](https://img.shields.io/badge/接口-CLI-5c6ac4)](main.py)

一个用于将常见文档格式转换为 Markdown 的轻量级命令行工具。

[![Project Brief EN](https://img.shields.io/badge/Project_Brief-English-2d7ff9)](PROJECT_BRIEF.en.md)
[![项目说明](https://img.shields.io/badge/项目说明-简体中文-e85d75)](PROJECT_BRIEF.md)

## 功能亮点

- 支持 `.pdf`、`.epub`、`.html`、`.txt`、`.docx` 和常见图片格式转换。
- 支持单文件转换、目录批量转换和递归扫描。
- 支持用 `--dry-run` 先规划、用 `--force` 控制覆盖已有输出。
- 支持用 `--t2s` 在提取完成后执行繁体转简体。
- 图片 OCR 已支持通过兼容 OpenAI Chat Completions 的视觉模型输出 Markdown，并清理常见包裹文本。

## 快速开始

### 安装

```bash
uv sync
```

### 配置 OCR

先复制示例环境变量文件：

```bash
cp .env.example .env
```

然后在 `.env` 中配置：

```env
ANY2MD_LLM_API_BASE=https://api.openai.com/v1
ANY2MD_LLM_API_KEY=sk-your-api-key
ANY2MD_LLM_MODEL=gpt-4.1-mini
```

说明：

- `ANY2MD_LLM_API_BASE` 支持填写兼容 OpenAI 的服务根地址，也支持直接填写完整的 `/chat/completions` 地址。
- `ANY2MD_LLM_API_KEY` 为对应服务密钥。
- `ANY2MD_LLM_MODEL` 为可处理图片输入的视觉模型。
- 程序在处理图片时会自动读取当前工作目录下的 `.env`。

### 基本用法

```bash
uv run python main.py input.pdf
uv run python main.py image.png
uv run any2md input.docx --output output/
uv run python main.py docs/ --output output/ --recursive
```

## 功能特性

- 通过统一注册表按文件后缀自动选择对应转换器。
- 批量转换时会在输出目录下保留输入文件的相对目录结构。
- `--dry-run` 会先做规划、冲突检查和覆盖检查，再决定是否写入。
- 繁体转简体是按需加载的可选后处理能力。
- 图片处理默认走 LLM OCR，可通过环境变量切换模型与服务地址。
- OCR 清洗会规范常见标题、列表，并将规则对齐的文本块整理为 Markdown 表格。

## 支持的格式

- `.pdf`
- `.epub`
- `.html` / `.htm`
- `.txt`（自动识别 UTF-8 / UTF-16 BOM，必要时回退 GB18030）
- `.docx`
- `.jpg` / `.jpeg` / `.png`（需要在 `.env` 中配置 LLM OCR）

## 用法

```bash
uv run python main.py input.pdf
uv run python main.py image.png
uv run python main.py input.pdf --dry-run
uv run python main.py input.epub --t2s
uv run python main.py note.txt --output result.md
uv run python main.py docs/ --output output/ --recursive
uv run python main.py note.txt --output result.md --force
uv run any2md input.docx --output output/
```

## 输出规则

- 单文件且未指定 `--output`：写入 `output/<源文件名>.md`。
- 单文件且 `--output` 指向文件路径：写入该文件。
- 单文件且 `--output` 指向已有目录，或路径以 `/` 或 `\\` 结尾：在该目录内写入 `<文件名>.md`。
- 批量模式默认输出到 `output/` 目录。
- 批量模式下，`--output` 会被视为输出目录，除非该路径已存在且是普通文件。
- 批量模式会保留从输入目录扫描到的文件的相对目录结构。
- 除非显式传入 `--force`，否则不会覆盖已存在的输出文件。
- `--dry-run` 会执行发现文件、跳过项统计、输出路径规划、冲突检查和覆盖检查，但不会实际写入文件。

## 退出码

- `0`：没有失败项，且至少有一个条目成功转换或完成规划。
- `1`：没有产生有效的转换或规划结果，例如所有条目都被跳过或全部失败。
- `2`：部分失败，至少有一个条目成功转换或完成规划，且至少有一个条目失败。

## 路线图

- 补充更清晰的 OCR 后端接入示例和配置说明。
- 为更复杂的真实文档增加回归测试样例。
- 继续改进打包与发布体验，降低分发和使用门槛。
- 在确有价值的前提下扩展更多格式适配器和后处理钩子。

## 已知限制

- 当前版本默认使用兼容 OpenAI Chat Completions 的视觉模型进行 OCR。
- 提取质量依赖源文档质量以及上游解析库的能力。
- 运行日志和状态汇总输出到 `stderr`，不会写入 `stdout`。
- 不支持的文件会被跳过，而不是强制尝试转换。

## 说明

- `--t2s` 会按需加载 OpenCC，并在提取完成后执行繁体转简体。
- 当前版本的图片转换默认使用兼容 OpenAI Chat Completions 的视觉模型进行 OCR，并自动清理常见的说明性包裹文本、将规则对齐的文本块整理为 Markdown 表格。
- 不支持的文件无论是直接传入还是在目录扫描中发现，都会被标记为已跳过。
- 运行日志、单文件状态和汇总信息会写入 stderr，stdout 预留给未来的内容输出能力。

## 测试

```bash
uv run python -m unittest discover -s tests
```
