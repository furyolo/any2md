# any2md — Project Brief

[![English](https://img.shields.io/badge/Docs-English-2d7ff9)](PROJECT_BRIEF.en.md)
[![简体中文](https://img.shields.io/badge/文档-简体中文-e85d75)](PROJECT_BRIEF.md)

## Project Goal

Convert documents in multiple formats into Markdown so the output is easier
to read, archive, and feed into downstream LLM or RAG workflows.

## Supported Formats

| Format | Processing approach |
| --- | --- |
| `.pdf` | `pymupdf4llm` extracts structured text and headings |
| `.epub` | `ebooklib` parses chapter HTML, then `markdownify` converts it to Markdown |
| `.html` / `.htm` | Reads HTML and converts it directly with `markdownify` |
| `.txt` | Reads UTF-8 text directly |
| `.docx` | `mammoth` converts to HTML, then `markdownify` converts it to Markdown |
| `.jpg` / `.jpeg` / `.png` | Uses an OpenAI-compatible vision chat model for OCR and outputs Markdown |

## Current Capabilities

- [x] Selects converters automatically by file extension
- [x] Supports single-file conversion
- [x] Supports batch file and directory conversion
- [x] Supports custom output paths through `--output`
- [x] Supports recursive directory scanning through `--recursive`
- [x] Supports `--t2s` for Traditional-to-Simplified Chinese conversion
- [x] Supports `--dry-run` for planning without writing files
- [x] Supports `--force` to overwrite existing output
- [x] Reports `skipped`, `failed`, `converted`, and `planned` statuses
- [x] Supports image OCR through an OpenAI-compatible vision model
- [x] Cleans common OCR wrapper text and normalizes basic Markdown structure
- [x] Converts stable aligned OCR text blocks into Markdown tables

## Output and Exit-Code Rules

- Single-file mode without `--output` writes to `output/<source-stem>.md`
- In single-file mode, `--output` may point to a file path; if the target is
  an existing directory or ends with `/` or `\\`, the output is written as
  `<stem>.md` inside that directory
- Batch mode defaults to the `output/` directory and preserves relative input
  directory structure
- Existing output files are not overwritten unless `--force` is explicitly set
- `--dry-run` performs discovery, skip accounting, output planning, collision
  checks, and overwrite checks without writing files
- Exit codes:
  - `0`: no failures, and at least one item is converted or planned
  - `1`: no useful converted or planned result, for example when everything is
    skipped or everything fails
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

# Convert an image with OCR
uv run python main.py image.png

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

## OCR Notes

- Image OCR uses an OpenAI-compatible Chat Completions endpoint with a
  vision-capable model
- OCR output is expected to be Markdown rather than plain text whenever the
  model can preserve structure
- The post-processing step removes common wrapper phrases, normalizes headings
  and list markers, and collapses excessive blank lines
- When OCR output contains stable aligned columns separated by tabs or repeated
  spaces, those blocks may be converted into Markdown tables
- Table conversion is intentionally conservative to avoid damaging ordinary
  paragraphs or list content

## Current Boundaries

- OCR quality still depends heavily on image quality, layout complexity, and
  the capabilities of the upstream vision model
- Table reconstruction is heuristic-based, so irregular layouts may still need
  manual cleanup
- Runtime logs, per-file statuses, and summary output go to `stderr`; `stdout`
  is reserved for future content output features

