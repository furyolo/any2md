from __future__ import annotations

import re


def apply_postprocess(
    markdown: str,
    *,
    t2s: bool = False,
    ocr_cleanup: bool = False,
) -> str:
    result = markdown
    if ocr_cleanup:
        result = clean_ocr_markdown(result)

    if not t2s:
        return result

    import opencc

    return opencc.OpenCC("t2s").convert(result)


def clean_ocr_markdown(markdown: str) -> str:
    result = markdown.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not result:
        return result

    lines = [_rstrip_line(line) for line in result.split("\n")]
    lines = _trim_explanatory_edges(lines)
    lines = [_normalize_markdown_line(line) for line in lines]
    lines = _convert_aligned_table_blocks(lines)

    result = "\n".join(lines).strip()
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result


def _trim_explanatory_edges(lines: list[str]) -> list[str]:
    trimmed = list(lines)
    while trimmed and _is_explanatory_line(trimmed[0]):
        trimmed.pop(0)
    while trimmed and _is_explanatory_line(trimmed[-1]):
        trimmed.pop()
    return trimmed


def _is_explanatory_line(line: str) -> bool:
    normalized = line.strip()
    if not normalized:
        return False

    patterns = (
        r"^(以下|下面)(是|为)?(图片|图像|截图)?(内容)?(的)?(ocr)?(识别|提取|整理|转换)?结果[：:]?$",
        r"^(ocr|OCR)(识别)?结果[：:]?$",
        r"^(以下|下面)(为)?整理后的Markdown[：:]?$",
        r"^(here is|here's) the (ocr|markdown).*$",
        r"^(extracted|recognized) (text|markdown)[：:]?$",
        r"^(如需|如果需要).*$",
        r"^(以上|上述)(就是|为)?(识别|提取|整理).*$",
    )
    return any(re.fullmatch(pattern, normalized) for pattern in patterns)


def _normalize_markdown_line(line: str) -> str:
    stripped = line.strip()
    if not stripped:
        return ""

    normalized = stripped
    normalized = re.sub(r"^(#{1,6})([^\s#])", r"\1 \2", normalized)
    normalized = re.sub(r"^([*+-])([^\s*+-])", r"\1 \2", normalized)
    normalized = re.sub(r"^(\d+\.)([^\s])", r"\1 \2", normalized)
    return normalized


def _convert_aligned_table_blocks(lines: list[str]) -> list[str]:
    converted: list[str] = []
    block: list[str] = []

    def flush() -> None:
        nonlocal block
        if not block:
            return
        converted.extend(_convert_table_block_if_needed(block))
        block = []

    for line in lines:
        if line.strip():
            block.append(line)
            continue
        flush()
        converted.append("")

    flush()
    return converted


def _convert_table_block_if_needed(block: list[str]) -> list[str]:
    rows = [_split_aligned_cells(line) for line in block]
    if any(row is None for row in rows):
        return block

    typed_rows = [row for row in rows if row is not None]
    if len(typed_rows) < 2:
        return block

    column_count = len(typed_rows[0])
    if column_count < 2 or any(len(row) != column_count for row in typed_rows):
        return block

    if any(_looks_like_non_table_line(line) for line in block):
        return block

    if len(typed_rows) >= 2 and _is_separator_row(typed_rows[1]):
        typed_rows = [typed_rows[0], *typed_rows[2:]]
    if len(typed_rows) < 2:
        return block

    separator = "| " + " | ".join("---" for _ in range(column_count)) + " |"
    markdown_rows = [_join_markdown_row(row) for row in typed_rows]
    return [markdown_rows[0], separator, *markdown_rows[1:]]


def _split_aligned_cells(line: str) -> list[str] | None:
    stripped = line.strip()
    if not stripped or "|" in stripped:
        return None

    if not re.search(r"(?:\t+|\s{2,})", line):
        return None

    cells = [cell.strip() for cell in re.split(r"\t+|\s{2,}", stripped) if cell.strip()]
    if len(cells) < 2:
        return None
    return cells


def _looks_like_non_table_line(line: str) -> bool:
    stripped = line.strip()
    patterns = (
        r"^#{1,6}\s+",
        r"^([*+-]|\d+\.)\s+",
        r"^>\s+",
        r"^```",
    )
    return any(re.match(pattern, stripped) for pattern in patterns)


def _is_separator_row(row: list[str]) -> bool:
    return all(re.fullmatch(r"[:\-—–_=.]{2,}", cell) for cell in row)


def _join_markdown_row(row: list[str]) -> str:
    escaped = [cell.replace("|", r"\|") for cell in row]
    return "| " + " | ".join(escaped) + " |"


def _rstrip_line(line: str) -> str:
    return line.rstrip()
