# any2md

[![English](https://img.shields.io/badge/Docs-English-2d7ff9)](README.md)
[![简体中文](https://img.shields.io/badge/文档-简体中文-e85d75)](README.zh-CN.md)

[![Version](https://img.shields.io/badge/version-0.3.0-2ea44f)](pyproject.toml)
[![Python](https://img.shields.io/badge/python-3.10+-3776AB?logo=python&logoColor=white)](pyproject.toml)
[![Interface](https://img.shields.io/badge/interface-CLI-5c6ac4)](main.py)

Convert common document formats into Markdown from the command line.

[![Project Brief EN](https://img.shields.io/badge/Project_Brief-English-2d7ff9)](PROJECT_BRIEF.en.md)
[![项目说明](https://img.shields.io/badge/项目说明-简体中文-e85d75)](PROJECT_BRIEF.md)
[![Changelog](https://img.shields.io/badge/Changelog-latest-blue)](CHANGELOG.md)

## Highlights

- Convert `.pdf`, `.epub`, `.html`, `.txt`, `.docx`, common image formats, audio files, and video files.
- Support single-file conversion, batch directory conversion, and recursive scanning.
- Use `--dry-run` for planning and `--force` for controlled overwrites.
- Add file locking on outputs to prevent concurrent writes to the same path.
- Support checkpoint resume for chunked local Qwen3-ASR transcription by rerunning the same command.
- Re-running a batch automatically skips files that were already converted, so you can continue unfinished jobs.
- Batch mode writes `.any2md-manifest.json` in the output directory to track input hashes, statuses, failure reasons, and last run times.
- You can pair it with `--resume-failed-only` to retry only the entries that previously failed.
- You can use `--manifest-list` / `--manifest-status` to inspect batch manifests and failed items directly.
- You can use `--manifest-prune` to remove stale manifest entries whose outputs no longer exist.
- Use `--t2s` to convert Traditional Chinese text to Simplified Chinese after extraction.
- Use OpenAI-compatible vision chat models for image OCR, return Markdown, and clean common OCR wrapper text.
- Use ByteDance AUC API or local Qwen3-ASR-1.7B runtime for audio transcription.

## Quick Start

### Installation

```bash
uv sync
```

### Configure OCR and Audio Transcription

Copy the example environment file first:

```bash
cp .env.example .env
```

Then set these values in `.env`:

**For image OCR:**

```env
ANY2MD_LLM_API_BASE=https://api.openai.com/v1
ANY2MD_LLM_API_KEY=sk-your-api-key
ANY2MD_LLM_MODEL=gpt-4.1-mini
```

Supports both OpenAI and Anthropic APIs with automatic detection:
- OpenAI example: `ANY2MD_LLM_API_BASE=https://api.openai.com/v1`, `ANY2MD_LLM_MODEL=gpt-4o-mini`
- Anthropic example: `ANY2MD_LLM_API_BASE=https://api.anthropic.com/v1`, `ANY2MD_LLM_MODEL=claude-3-5-sonnet-20241022`
- For third-party proxies where auto-detection fails, manually specify: `ANY2MD_LLM_API_TYPE=anthropic` (options: `openai` or `anthropic`)

**For audio transcription:**

```env
ANY2MD_AUC_APP_ID=your-app-id
ANY2MD_AUC_ACCESS_KEY=your-access-key
ANY2MD_AUC_RESOURCE_ID=volc.seedasr.auc
```

**For local Qwen3-ASR-1.7B transcription:**

```env
ANY2MD_QWEN_AUDIO_RUNTIME=qwen-asr
ANY2MD_QWEN_AUDIO_MODEL=Qwen/Qwen3-ASR-1.7B
ANY2MD_QWEN_AUDIO_LANGUAGE=auto
ANY2MD_QWEN_AUDIO_TIMEOUT=3600
ANY2MD_QWEN_AUDIO_DEVICE_MAP=cpu
ANY2MD_QWEN_AUDIO_DTYPE=float32
```

Notes:

- `ANY2MD_LLM_API_BASE` can be either an OpenAI-compatible base URL or a full `/chat/completions` endpoint.
- `ANY2MD_LLM_API_KEY` is the API key for that service.
- `ANY2MD_LLM_MODEL` must be a vision-capable model.
- `ANY2MD_AUC_APP_ID` and `ANY2MD_AUC_ACCESS_KEY` are ByteDance AUC API credentials.
- `ANY2MD_QWEN_AUDIO_EXECUTABLE` and `ANY2MD_QWEN_AUDIO_MODEL` configure the local Qwen3-ASR runtime.
- `ANY2MD_QWEN_AUDIO_RUNTIME=qwen-asr` is the recommended default; `ANY2MD_QWEN_AUDIO_MODEL` can be an official model ID and will download on first use.
- If you want to stay on CPU, set `ANY2MD_QWEN_AUDIO_DEVICE_MAP=cpu` and `ANY2MD_QWEN_AUDIO_DTYPE=float32`.
- `ANY2MD_QWEN_AUDIO_COMMAND_TEMPLATE` is optional and only needed for experimental runtimes such as `chatllm.cpp` or `llama.cpp`.
- Support for `Qwen3-ASR` in `chatllm.cpp` / `llama.cpp` depends on upstream versions; the more reliable local path is the official `qwen-asr` runtime.
- The CLI loads `.env` from the current working directory when converting images or audio files.

### Basic usage

```bash
uv run python main.py input.pdf
uv run python main.py image.png
uv run python main.py https://example.com/audio.mp3
uv run python main.py local-audio.mp3 --audio-backend qwen-local
uv run python main.py "C:/Users/foogl/Music/demo.mp3" --audio-backend qwen-local
uv run any2md input.docx --output output/
uv run python main.py docs/ --output output/ --recursive
```

### Async and concurrency control

By default, any2md uses asynchronous processing for better performance when converting multiple files:

```bash
# Default: async mode with 5 concurrent conversions
uv run python main.py docs/ --output output/ --recursive

# Control concurrency level
uv run python main.py docs/ --output output/ --recursive --max-concurrent 10

# Force synchronous mode (process files one by one)
uv run python main.py docs/ --output output/ --recursive --sync
```

- `--max-concurrent N`: Set maximum concurrent file conversions (default: 5)
- `--sync`: Force synchronous mode instead of async processing

Async mode significantly improves performance for batch conversions, especially when processing files that involve network requests (OCR, audio transcription).

### Audio input rules

> By default, any2md uses local Qwen3-ASR for offline transcription and supports both local files and direct URLs. AUC mode requires explicit `--audio-backend auc` and only supports remote URLs.

- **Default (Qwen3-ASR)**: Supports local audio files (e.g., `demo.mp3`, `record.wav`) and direct `http://` or `https://` audio URLs.
- **AUC mode**: Requires `--audio-backend auc` and only supports direct remote audio URLs.
- Supported audio suffixes: `.mp3`, `.wav`, `.m4a`, `.aac`, `.flac`, `.ogg`.

### Default: Local Qwen3-ASR backend

Local Qwen3-ASR is the default audio transcription backend and requires no additional parameters:

```bash
uv run python main.py demo.mp3
uv run python main.py demo.wav --output output/demo.md
uv run python main.py demo.flac --qwen-runtime qwen-asr
uv run python main.py "https://example.com/audio.mp3"
```

- Local audio transcription is enabled by default and accepts both local audio files and direct URLs.
- `--qwen-runtime qwen-asr` is the recommended default and works with the official `Qwen/Qwen3-ASR-1.7B` model ID or a local pretrained model directory.
- `--qwen-runtime chatllm.cpp` works with chatllm.cpp-native model formats such as `.bin`, not with `.gguf`.
- `--qwen-runtime llama.cpp` only works when the upstream version already supports the `qwen3-asr` architecture; only provide `--qwen-command-template` or `ANY2MD_QWEN_AUDIO_COMMAND_TEMPLATE` if you need custom launch arguments.
- The local backend also accepts direct audio URLs and downloads them to a temporary file before transcription.

If you want to explicitly control the model source, you can also use:

```bash
uv run python main.py demo.mp3 --qwen-model Qwen/Qwen3-ASR-1.7B
uv run python main.py demo.mp3 --qwen-model "D:/Coding/models/Qwen3-ASR-1.7B"
```

If you want to explicitly control the device:

```bash
# CPU (default)
uv run python main.py demo.mp3

# GPU (requires CUDA-enabled torch)
set ANY2MD_QWEN_AUDIO_DEVICE_MAP=cuda && uv run python main.py demo.mp3
```

### AUC backend (optional)

To use ByteDance AUC for remote audio transcription, explicitly specify `--audio-backend auc`:

```bash
uv run python main.py "https://example.com/audio.mp3" --audio-backend auc
```

- AUC mode only supports direct remote audio URLs (not local files).
- Requires AUC credentials in `.env` (see Configuration section).

### Long audio workflow (AUC mode only)

For longer audio with AUC backend, you can submit first and check later:

```bash
uv run python main.py "https://example.com/audio.mp3" --audio-backend auc --no-wait
uv run python main.py --auc-status <task-id>
uv run python main.py --auc-status <task-id> --output output/audio.md
```

- `--no-wait` submits a single remote audio URL and returns a task ID immediately (AUC mode only).
- `--auc-status <task-id>` checks a previously submitted task from the local task cache (AUC mode only).
- When a task is still processing after the wait window, the CLI reports it as still processing instead of treating it as a hard failure.

## Features

- Converter selection is based on file suffixes through a central registry.
- Batch conversion preserves relative directory layout under the output directory.
- Dry-run mode performs planning, collision checks, and overwrite checks before writing.
- Output writes are protected by a file lock; if another `any2md` process is already writing the same target, the run fails with a detailed error.
- Chunked local Qwen3-ASR transcription stores resume metadata next to the output so interrupted runs can continue.
- In batch mode, existing outputs without a resume state are treated as already completed and skipped automatically.
- `.any2md-manifest.json` tracks `input_hash`, `status`, `last_error`, and `last_run_at` per output file, so changed inputs are re-converted automatically.
- Traditional-to-Simplified Chinese conversion is optional and loaded only when needed.
- Image handling uses LLM OCR by default while keeping the OCR interface extensible.
- OCR cleanup can normalize headings and lists, and convert aligned text blocks into Markdown tables.
- Audio transcription uses local Qwen3-ASR by default, with optional ByteDance AUC support via `--audio-backend auc`.

## Supported formats

- `.pdf`
- `.epub`
- `.html` / `.htm`
- `.txt` (auto-detects UTF-8 / UTF-16 BOM, with GB18030 fallback)
- `.docx`
- `.jpg` / `.jpeg` / `.png` (requires LLM OCR settings in `.env`)
- Direct audio URLs ending in `.mp3`, `.wav`, `.m4a`, `.aac`, `.flac`, or `.ogg` (local Qwen3-ASR by default, or AUC with `--audio-backend auc`)
- Local `.mp3`, `.wav`, `.m4a`, `.aac`, `.flac`, `.ogg` files (supported by default via local Qwen3-ASR)

## Usage

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

## Output rules

- Single file with no `--output`: writes to `output/<source-stem>.md`.
- Single file with `--output` pointing to a file path: writes to that file.
- Single file with `--output` pointing to an existing directory, or a path ending with `/` or `\`: writes `<stem>.md` inside that directory.
- Batch mode defaults to the `output/` directory.
- Batch mode treats `--output` as an output directory unless that path already exists as a regular file.
- Batch mode preserves the relative layout of files discovered from input directories.
- Existing output files are not overwritten unless `--force` is provided.
- If a matching resume state file exists, unfinished chunked transcription is resumed instead of being treated as a normal overwrite conflict.
- In batch mode, existing outputs without a resume state are skipped by default; single-file mode still requires `--force` to overwrite.
- If the manifest shows that an input has changed, batch mode automatically re-converts it and overwrites the stale output without requiring `--force`.
- `--resume-failed-only` is intended for batch mode: it skips entries that were previously successful or not recorded as failed, and only retries files whose manifest status is `failed`.
- `--manifest-list <dir>` reads `.any2md-manifest.json` from that output directory and prints all entries.
- `--manifest-status <status>` must be used with `--manifest-list` and filters by `converted`, `failed`, `pending`, or `skipped`.
- `--manifest-prune <dir>` removes entries from `.any2md-manifest.json` when their corresponding output files no longer exist.
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

- Image OCR supports OpenAI and Anthropic-compatible vision models, with automatic API type detection based on URL or model name.
- Local audio file paths are supported by default (Qwen3-ASR mode).
- When using AUC mode (`--audio-backend auc`), audio files must be accessible via direct URL.
- Extraction quality depends on the source document quality and the upstream parsing libraries.
- Runtime logs and status summaries are written to `stderr`, not `stdout`.
- Unsupported files are skipped instead of being force-converted.

## Notes

- `--t2s` lazily loads OpenCC and applies Traditional-to-Simplified Chinese conversion after extraction.
- Image conversion supports OpenAI and Anthropic-compatible vision models for OCR, with automatic API type detection and appropriate endpoint formatting (OpenAI: `/v1/chat/completions`, Anthropic: `/v1/messages`).
- Audio conversion uses local Qwen3-ASR by default, with optional ByteDance AUC support via `--audio-backend auc`.
- Video files are automatically processed by extracting audio tracks first, then transcribed using the selected audio backend.
- Unsupported files are reported as skipped whether they are passed directly or discovered during directory scanning.
- Operational logs, per-file statuses, and summaries are written to stderr. Stdout is reserved for future content output.

## Testing

```bash
uv run python -m unittest discover -s tests
```
