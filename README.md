# any2md

[![English](https://img.shields.io/badge/Docs-English-2d7ff9)](README.md)
[![简体中文](https://img.shields.io/badge/文档-简体中文-e85d75)](README.zh-CN.md)

[![Version](https://img.shields.io/badge/version-0.2.0-2ea44f)](pyproject.toml)
[![Python](https://img.shields.io/badge/python-3.10+-3776AB?logo=python&logoColor=white)](pyproject.toml)
[![Interface](https://img.shields.io/badge/interface-CLI-5c6ac4)](main.py)

Convert common document formats into Markdown from the command line.

[![Project Brief EN](https://img.shields.io/badge/Project_Brief-English-2d7ff9)](PROJECT_BRIEF.en.md)
[![项目说明](https://img.shields.io/badge/项目说明-简体中文-e85d75)](PROJECT_BRIEF.md)

## Highlights

- Convert `.pdf`, `.epub`, `.html`, `.txt`, `.docx`, and common image formats.
- Support single-file conversion, batch directory conversion, and recursive scanning.
- Use `--dry-run` for planning and `--force` for controlled overwrites.
- Use `--t2s` to convert Traditional Chinese text to Simplified Chinese after extraction.
- Use OpenAI-compatible vision chat models for image OCR, return Markdown, and clean common OCR wrapper text.

## Quick Start

### Installation

```bash
uv sync
```

### Configure OCR

Copy the example environment file first:

```bash
cp .env.example .env
```

Then set these values in `.env`:

```env
ANY2MD_LLM_API_BASE=https://api.openai.com/v1
ANY2MD_LLM_API_KEY=sk-your-api-key
ANY2MD_LLM_MODEL=gpt-4.1-mini
```

Notes:

- `ANY2MD_LLM_API_BASE` can be either an OpenAI-compatible base URL or a full `/chat/completions` endpoint.
- `ANY2MD_LLM_API_KEY` is the API key for that service.
- `ANY2MD_LLM_MODEL` must be a vision-capable model.
- The CLI loads `.env` from the current working directory when converting images.

### Basic usage

```bash
uv run python main.py input.pdf
uv run python main.py image.png
uv run any2md input.docx --output output/
uv run python main.py docs/ --output output/ --recursive
```

## Features

- Converter selection is based on file suffixes through a central registry.
- Batch conversion preserves relative directory layout under the output directory.
- Dry-run mode performs planning, collision checks, and overwrite checks before writing.
- Traditional-to-Simplified Chinese conversion is optional and loaded only when needed.
- Image handling uses LLM OCR by default while keeping the OCR interface extensible.
- OCR cleanup can normalize headings and lists, and convert aligned text blocks into Markdown tables.

## Supported formats

- `.pdf`
- `.epub`
- `.html` / `.htm`
- `.txt` (auto-detects UTF-8 / UTF-16 BOM, with GB18030 fallback)
- `.docx`
- `.jpg` / `.jpeg` / `.png` (requires LLM OCR settings in `.env`)

## Usage

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

## Output rules

- Single file with no `--output`: writes to `output/<source-stem>.md`.
- Single file with `--output` pointing to a file path: writes to that file.
- Single file with `--output` pointing to an existing directory, or a path ending with `/` or `\\`: writes `<stem>.md` inside that directory.
- Batch mode defaults to the `output/` directory.
- Batch mode treats `--output` as an output directory unless that path already exists as a regular file.
- Batch mode preserves the relative layout of files discovered from input directories.
- Existing output files are not overwritten unless `--force` is provided.
- `--dry-run` performs discovery, skip reporting, output planning, collision checks, and overwrite checks without writing any files.

## Exit codes

- `0`: no failures, and at least one item was converted or planned.
- `1`: no useful conversion or planning result was produced, for example all items were skipped or all items failed.
- `2`: partial failure, where at least one item converted or planned and at least one item failed.

## Roadmap

- Add clearer OCR backend integration examples and configuration guidance.
- Expand regression fixtures for more complex real-world documents.
- Improve packaging and release ergonomics for easier distribution.
- Explore more format adapters and post-processing hooks where they provide clear value.

## Known limitations

- This version uses an OpenAI-compatible vision chat model for OCR by default.
- Extraction quality depends on the source document quality and the upstream parsing libraries.
- Runtime logs and status summaries are written to `stderr`, not `stdout`.
- Unsupported files are skipped instead of being force-converted.

## Notes

- `--t2s` lazily loads OpenCC and applies Traditional-to-Simplified Chinese conversion after extraction.
- Image conversion uses an OpenAI-compatible vision chat model by default, strips common wrapper text from OCR output, and converts aligned text blocks into Markdown tables when the structure is stable enough.
- Unsupported files are reported as skipped whether they are passed directly or discovered during directory scanning.
- Operational logs, per-file statuses, and summaries are written to stderr. Stdout is reserved for future content output.

## Testing

```bash
uv run python -m unittest discover -s tests
```
