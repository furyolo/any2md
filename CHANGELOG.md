# Changelog / 更新记录

This file records notable project changes.
本文件用于记录项目的重要变更。

## [Unreleased] / 未发布

- No changes yet.
- 暂无变更。

## [0.4.0] - 2026-03-11

### ⚠️ Breaking Changes / 破坏性变更

- **Changed default audio backend from AUC to local Qwen3-ASR.**
- **将默认音频后端从 AUC 改为本地 Qwen3-ASR。**

  - Audio and video files now use local Qwen3-ASR transcription by default without requiring `--audio-backend qwen-local`.
  - 音频和视频文件现在默认使用本地 Qwen3-ASR 转录，无需指定 `--audio-backend qwen-local`。

  - To use AUC mode, explicitly specify `--audio-backend auc`.
  - 要使用 AUC 模式，需显式指定 `--audio-backend auc`。

  - Local audio files are now supported by default.
  - 本地音频文件现在默认支持。

### Migration Guide / 迁移指南

**If you rely on AUC mode:**

- Add `--audio-backend auc` to your existing commands.
- Example: `any2md "https://example.com/audio.mp3" --audio-backend auc`

**如果你依赖 AUC 模式：**

- 在现有命令中添加 `--audio-backend auc`。
- 示例：`any2md "https://example.com/audio.mp3" --audio-backend auc`

**If you already use Qwen3-ASR:**

- No changes needed. You can optionally remove `--audio-backend qwen-local` from your commands.

**如果你已经使用 Qwen3-ASR：**

- 无需修改。可选择移除命令中的 `--audio-backend qwen-local`。

### Changed / 变更

- Updated CLI parameter `--audio-backend` default value from `"auc"` to `"qwen-local"`.
- 更新了 CLI 参数 `--audio-backend` 的默认值，从 `"auc"` 改为 `"qwen-local"`。

- Updated help text to reflect the new default behavior.
- 更新了帮助文本以反映新的默认行为。

### Documentation / 文档

- Updated `README.md` to reflect local Qwen3-ASR as the default backend.
- 更新了 `README.md`，反映本地 Qwen3-ASR 为默认后端。

- Updated `README.zh-CN.md` with corresponding Chinese documentation changes.
- 更新了 `README.zh-CN.md`，对应中文文档变更。

- Clarified that `--no-wait` and `--auc-status` are AUC-only options.
- 明确说明 `--no-wait` 和 `--auc-status` 仅适用于 AUC 模式。

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
