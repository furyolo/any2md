# any2md — Project Brief

## 项目目标

将多种格式的文档文件转换为 Markdown 文本，便于后续 LLM / RAG 处理、归档与阅读。

## 当前已支持格式

| 格式 | 处理方式 |
| --- | --- |
| `.pdf` | `pymupdf4llm` 提取结构化文本与标题 |
| `.epub` | `ebooklib` 解析章节 HTML，`markdownify` 转 Markdown |
| `.html` / `.htm` | 读取 HTML 后直接 `markdownify` |
| `.txt` | 直接读取 UTF-8 文本 |
| `.docx` | `mammoth` 转 HTML 后再交给 `markdownify` |
| `.jpg` / `.jpeg` / `.png` | 预留 OCR 扩展点，未配置 OCR 引擎时返回清晰错误 |

## 当前功能

- [x] 根据文件后缀自动判断转换方式
- [x] 支持单文件转换
- [x] 支持批量文件 / 目录转换
- [x] 支持 `--output` 自定义输出路径
- [x] 支持 `--recursive` 递归扫描目录
- [x] 支持 `--t2s` 将繁体中文转换为简体中文
- [x] 支持 `--dry-run` 仅规划、不落盘
- [x] 支持 `--force` 覆盖已有输出
- [x] 支持 skipped / failed / converted / planned 状态统计

## 输出与退出码约定

- 单文件默认输出到当前工作目录下的 `<源文件主名>.md`
- 单文件 `--output` 可为文件路径；若目标是已存在目录或路径以 `/`、`\\` 结尾，则输出到该目录下的 `<stem>.md`
- 批量模式默认输出到 `output/` 目录，并保留相对目录结构
- 已有输出默认不覆盖，需显式传入 `--force`
- `--dry-run` 会执行发现、跳过统计、输出规划、冲突检测和覆盖检测，但不会写入文件
- 退出码：
  - `0`：无失败，且至少一个条目被 converted 或 planned
  - `1`：没有有效 converted / planned 结果，例如 all skipped 或 all failed
  - `2`：部分失败

## 依赖包

```text
pymupdf4llm>=0.3.4
pymupdf-layout>=1.27.1
ebooklib>=0.20
markdownify>=1.2.2
mammoth>=1.8.0
opencc-python-reimplemented>=0.1.7
```

## 运行方式

```bash
# 单文件转换
uv run python main.py input.pdf

# 仅规划，不写文件
uv run python main.py input.pdf --dry-run

# EPUB 转 Markdown，并执行繁转简
uv run python main.py input.epub --t2s

# 自定义输出文件
uv run python main.py note.txt --output result.md

# 批量转换目录
uv run python main.py docs/ --output output/ --recursive

# 覆盖已有输出
uv run python main.py note.txt --output result.md --force
```

## 当前边界

- 图片 OCR 仅提供扩展边界，本版本不内置 OCR 引擎
- 运行日志、逐文件状态与 summary 写入 stderr；stdout 保留给未来内容输出
