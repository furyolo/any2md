# any2md

A small CLI for converting common document formats into Markdown.

## Installation

```bash
uv sync
```

## Supported formats

- `.pdf`
- `.epub`
- `.html` / `.htm`
- `.txt`
- `.docx`
- `.jpg` / `.jpeg` / `.png` (requires a configured OCR engine)

## Usage

```bash
uv run python main.py input.pdf
uv run python main.py input.pdf --dry-run
uv run python main.py input.epub --t2s
uv run python main.py note.txt --output result.md
uv run python main.py docs/ --output output/ --recursive
uv run python main.py note.txt --output result.md --force
uv run any2md input.docx --output output/
```

## Output rules

- Single file with no `--output`: writes to `<source-stem>.md` in the current working directory.
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

## Notes

- `--t2s` lazily loads OpenCC and applies Traditional-to-Simplified Chinese conversion after extraction.
- Image conversion only defines an OCR extension point in this version. No OCR engine is bundled by default.
- Unsupported files are reported as skipped whether they are passed directly or discovered during directory scanning.
- Operational logs, per-file statuses, and summaries are written to stderr. Stdout is reserved for future content output.

## Testing

```bash
uv run python -m unittest discover -s tests
```
