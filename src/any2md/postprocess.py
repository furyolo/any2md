def apply_postprocess(markdown: str, *, t2s: bool = False) -> str:
    if not t2s:
        return markdown

    import opencc

    return opencc.OpenCC("t2s").convert(markdown)
