# any2md — Project Brief

[![English](https://img.shields.io/badge/Docs-English-2d7ff9)](PROJECT_BRIEF.en.md)
[![简体中文](https://img.shields.io/badge/文档-简体中文-e85d75)](PROJECT_BRIEF.md)

## Project goal

Convert documents in multiple formats into Markdown text for downstream
LLM / RAG processing, archiving, and reading.

## Currently supported formats

| Format | Processing approach |
| --- | --- |
| `.pdf` | `pymupdf4llm` extracts structured text and headings |
| `.epub` | `ebooklib` parses chapter HTML, then `markdownify` converts it to Markdown |
| `.html` / `.htm` | Reads HTML and converts it directly with `markdownify` |
| `.txt` | Reads UTF-8 text directly |
| `.docx` | `mammoth` converts to HTML, then `markdownify` converts it to Markdown |
| `.jpg` / `.jpeg` / `.png` | Reserved OCR extension point; returns a clear error when no OCR engine is configured |

## Current features

- [x] Automatically selects the converter by file extension
- [x] Supports single-file conversion
- [x] Supports batch file / directory conversion
- [x] Supports custom output paths with `--output`
- [x] Supports recursive directory scanning with `--recursive`
- [x] Supports `--t2s` to convert Traditional Chinese to Simplified Chinese
- [x] Supports `--dry-run` for planning without writing files
- [x] Supports `--force` to overwrite existing output
- [x] Supports skipped / failed / converted / planned status reporting

## Output and exit-code rules

- For a single file with no `--output`, output is written to `output/<source-stem>.md`
- For a single file, `--output` may be a file path; if the target is an existing directory or ends with `/` or `\\`, output is written as `<stem>.md` inside that directory
- Batch mode defaults to the `output/` directory and preserves the relative directory structure
- Existing output is not overwritten unless `--force` is explicitly provided
- `--dry-run` performs discovery, skip accounting, output planning, collision checks, and overwrite checks without writing files
- Exit codes:
  - `0`: no failures, and at least one item is converted or planned
  - `1`: no useful converted / planned result, for example all skipped or all failed
  - `2`: partial failure

## Dependencies

```text
pymupdf4llm>=0.3.4
pymupdf-layout>=1.27.1
ebooklib>=0.20
markdownify>=1.2.2
mammoth>=1.8.0
opencc-python-reimplemented>=0.1.7
```

## Usage

```bash
# Convert a single file
uv run python main.py input.pdf

# Plan only, do not write files
uv run python main.py input.pdf --dry-run

# Convert EPUB to Markdown and apply Traditional-to-Simplified conversion
uv run python main.py input.epub --t2s

# Write to a custom output file
uv run python main.py note.txt --output result.md

# Convert a directory in batch mode
uv run python main.py docs/ --output output/ --recursive

# Overwrite existing output
uv run python main.py note.txt --output result.md --force
```

## Current boundaries

- Image OCR is only an extension point in this version; no OCR engine is bundled
- Runtime logs, per-file status, and summary output go to stderr; stdout is reserved for future content output
