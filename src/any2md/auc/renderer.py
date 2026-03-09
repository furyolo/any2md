from __future__ import annotations

from any2md.auc.client import AucTranscript


class AucMarkdownRenderer:
    def render(self, transcript: AucTranscript) -> str:
        return transcript.text.strip()
