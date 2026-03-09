# any2md — 项目说明

[![English](https://img.shields.io/badge/Docs-English-2d7ff9)](PROJECT_BRIEF.en.md)
[![简体中文](https://img.shields.io/badge/文档-简体中文-e85d75)](PROJECT_BRIEF.md)

## 项目目标

将多种格式的文档转换为 Markdown，便于阅读、归档，以及后续接入
LLM 或 RAG 流程。

## 支持的格式

| 格式 | 处理方式 |
| --- | --- |
| `.pdf` | 使用 `pymupdf4llm` 提取结构化文本和标题 |
| `.epub` | 使用 `ebooklib` 解析章节 HTML，再由 `markdownify` 转为 Markdown |
| `.html` / `.htm` | 直接读取 HTML，再由 `markdownify` 转为 Markdown |
| `.txt` | 自动识别 UTF-8 / UTF-16 BOM，必要时回退到 GB18030 |
| `.docx` | 使用 `mammoth` 转为 HTML，再交给 `markdownify` |
| `.jpg` / `.jpeg` / `.png` | 使用兼容 OpenAI 的视觉聊天模型做 OCR，并输出 Markdown |
| 以 `.mp3` / `.wav` / `.m4a` / `.aac` / `.flac` / `.ogg` 结尾的直接音频 URL | 使用字节跳动 AUC API 做音频转录 |

## 当前能力

- [x] 根据文件后缀自动选择转换器
- [x] 支持单文件转换
- [x] 支持批量文件与目录转换
- [x] 支持通过 `--output` 自定义输出路径
- [x] 支持通过 `--recursive` 递归扫描目录
- [x] 支持通过 `--t2s` 执行繁体转简体
- [x] 支持通过 `--dry-run` 只做规划、不写文件
- [x] 支持通过 `--force` 覆盖已有输出
- [x] 支持 `skipped`、`failed`、`converted`、`planned` 状态统计
- [x] 支持通过兼容 OpenAI 的视觉模型进行图片 OCR
- [x] 支持通过字节跳动 AUC API 进行音频转录
- [x] 支持在 CLI 中直接传入音频 URL
- [x] 支持清理常见 OCR 包装文本并规范基础 Markdown 结构
- [x] 支持将结构稳定的 OCR 对齐文本块整理为 Markdown 表格

## 输出与退出码规则

- 单文件模式未指定 `--output` 时，输出到 `output/<源文件主名>.md`
- 单文件模式中，`--output` 可以指向文件路径；如果目标是已有目录，
  或路径以 `/` 或 `\\` 结尾，则输出到该目录下的 `<主名>.md`
- 批量模式默认输出到 `output/` 目录，并保留输入目录的相对结构
- 除非显式传入 `--force`，否则不会覆盖已有输出文件
- `--dry-run` 会执行发现、跳过统计、输出规划、冲突检查和覆盖检查，
  但不会真正写入文件
- 退出码：
  - `0`：没有失败项，且至少有一个条目被成功转换或完成规划
  - `1`：没有有效的转换或规划结果，例如全部被跳过或全部失败
  - `2`：部分失败

## 依赖

```text
pymupdf4llm>=0.3.4
pymupdf-layout>=1.27.1
ebooklib>=0.20
markdownify>=1.2.2
mammoth>=1.8.0
opencc-python-reimplemented>=0.1.7
```

## 用法示例

```bash
# 转换单个文件
uv run python main.py input.pdf

# 对图片执行 OCR
uv run python main.py image.png

# 直接转录音频 URL
uv run python main.py https://example.com/audio.mp3

# 只做规划，不写文件
uv run python main.py input.pdf --dry-run

# EPUB 转 Markdown，并执行繁体转简体
uv run python main.py input.epub --t2s

# 自定义输出文件
uv run python main.py note.txt --output result.md

# 批量转换目录
uv run python main.py docs/ --output output/ --recursive

# 覆盖已有输出
uv run python main.py note.txt --output result.md --force
```

## OCR 与音频说明

- 图片 OCR 默认使用兼容 OpenAI 的 Chat Completions 视觉模型
- 当模型能保留结构时，OCR 输出目标是 Markdown，而不是纯文本
- 音频转录使用字节跳动 AUC API
- 直接传入的音频 URL 会跳过上传，直接处理
- 本地音频文件已不再支持
- 后处理会清理常见包装语、规范标题和列表标记，并压缩多余空行
- 当 OCR 结果中存在由制表符或重复空格分隔的稳定对齐列时，
  会尝试将其整理为 Markdown 表格
- 表格转换策略偏保守，尽量避免破坏普通段落或列表内容

## 当前边界

- OCR 质量仍然依赖图片清晰度、版式复杂度以及上游视觉模型能力
- 音频转录依赖 AUC 服务可用性，以及所提供音频 URL 的可访问性
- 表格重建基于启发式规则，不规则布局仍可能需要手工调整
- 运行日志、单文件状态和汇总信息写入 `stderr`；`stdout` 预留给未来的内容输出功能
