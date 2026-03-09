# Changelog / 更新记录

This file records notable project changes.
本文件用于记录项目的重要变更。

## [Unreleased] / 未发布

- No changes yet.
- 暂无变更。

## [0.3.0] - 2026-03-09

### Changed / 变更

- Removed video transcription support and all related video format registrations.
- 移除了视频转录能力以及相关视频格式注册。

- Kept audio transcription support for `.mp3`, `.wav`, `.m4a`, `.aac`, `.flac`, and `.ogg`.
- 保留了 `.mp3`、`.wav`、`.m4a`、`.aac`、`.flac`、`.ogg` 的音频转录支持。

- Kept direct audio URL input from the CLI and removed local audio upload support.
- 保留了命令行直接传入音频 URL 的能力，并移除了本地音频上传支持。

### Documentation / 文档

- Updated `README.md`, `README.zh-CN.md`, `PROJECT_BRIEF.en.md`, `PROJECT_BRIEF.md`, and `.env.example` to reflect audio-only transcription.
- 已更新 `README.md`、`README.zh-CN.md`、`PROJECT_BRIEF.en.md`、`PROJECT_BRIEF.md` 和 `.env.example`，统一反映“仅支持音频转录”的现状。

- Normalized the Chinese README and project brief content into clean UTF-8 text.
- 已将中文 README 和项目说明整理为规范的 UTF-8 文本内容。
