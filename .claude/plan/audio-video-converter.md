# 音频/视频转 Markdown 功能实施计划（Phase 1）

## 1. 目标与边界

- 目标：在保持现有 `ConverterRegistry` 模式不变的前提下，为 any2md 增加音频/视频转 Markdown 能力。
- 范围：只实现第一期最小链路，本地文件 -> 上传到可访问 URL -> 调用 AUC `submit/query` -> 输出 Markdown。
- 非目标：不在第一期实现说话人增强渲染、复杂 utterance 排版、异步任务队列、断点续传、批量并发调度。

## 2. 架构决策

- 保持转换器签名为 `Callable[[Path], str]`。
- 采用单一 `AudioVideoConverter`，内部组合 4 个子模块：
  - `MediaPreprocessor`：识别文件类型、视频抽音轨、必要时转码。
  - `Uploader`：把本地媒体上传为可被 AUC 访问的 URL。
  - `AucClient`：负责配置加载、任务提交、轮询、结果解析。
  - `AucMarkdownRenderer`：把识别结果渲染为 Markdown。
- 默认注册由 `build_default_registry()` 完成，与图片转换器一致，运行时按环境变量决定是否可用。
- 临时文件统一使用 `TemporaryDirectory`，并通过 `try/finally` 做清理。
- 第一期开启最保守参数：
  - `enable_itn=true`
  - `enable_punc=true`
  - `enable_ddc=true`
  - `show_utterances=false`
  - `enable_speaker_info=false`

## 3. 模块设计

### 3.1 AudioVideoConverter

**职责**：作为 Registry 注册的转换器入口，协调子模块完成转换流程。

**接口**：
```python
class AudioVideoConverter:
    def __init__(
        self,
        preprocessor: MediaPreprocessor,
        uploader: Uploader,
        client: AucClient,
        renderer: AucMarkdownRenderer,
    ):
        ...

    def __call__(self, path: Path) -> str:
        # 1. 预处理（视频抽音轨、格式转换）
        # 2. 上传获取 URL
        # 3. 调用 AUC submit/query
        # 4. 渲染 Markdown
        ...
```

### 3.2 MediaPreprocessor

**职责**：识别文件类型、视频抽音轨、必要时转码。

**接口**：
```python
@dataclass
class PreparedMedia:
    source_path: Path
    working_path: Path
    media_kind: str  # "audio" | "video"
    audio_format: str  # "mp3" | "wav" | "m4a" ...
    sample_rate: int | None
    channels: int | None

class MediaPreprocessor:
    def prepare(self, path: Path) -> PreparedMedia:
        # 检测文件类型
        # 视频：ffmpeg 抽音轨到临时文件
        # 音频：直接使用或转码
        ...
```

**实现要点**：
- 使用 `mimetypes` 或后缀判断文件类型
- 视频统一抽成单声道 16kHz WAV：`ffmpeg -i input.mp4 -vn -ar 16000 -ac 1 output.wav`
- 音频若已是支持格式，直接使用；否则转码

### 3.3 Uploader

**职责**：把本地媒体上传为可被 AUC 访问的 URL。

**接口**（Protocol）：
```python
@dataclass
class UploadedMedia:
    url: str
    content_type: str

class Uploader(Protocol):
    def upload(self, path: Path, media: PreparedMedia) -> UploadedMedia:
        ...
```

**第一期实现**：
- 提供一个简单的 HTTP 上传实现（如上传到临时对象存储）
- 或提供 Mock 实现用于测试
- 配置通过环境变量：`ANY2MD_UPLOAD_ENDPOINT`、`ANY2MD_UPLOAD_TOKEN`

### 3.4 AucClient

**职责**：负责配置加载、任务提交、轮询、结果解析。

**接口**：
```python
@dataclass
class AucSettings:
    app_id: str
    access_key: str
    resource_id: str = "volc.bigasr.auc"
    submit_url: str = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/submit"
    query_url: str = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/query"
    timeout: int = 30
    poll_interval: float = 1.0
    max_wait_seconds: int = 300

@dataclass
class AucTask:
    task_id: str
    logid: str

@dataclass
class AucTranscript:
    text: str
    utterances: list | None = None

class AucClient:
    def __init__(self, settings: AucSettings):
        ...

    def transcribe(self, uploaded: UploadedMedia, media: PreparedMedia) -> AucTranscript:
        # 1. submit 任务
        # 2. 轮询 query 直到完成
        # 3. 返回结果
        ...

    def _submit(self, uploaded: UploadedMedia, media: PreparedMedia) -> AucTask:
        ...

    def _poll(self, task: AucTask) -> AucTranscript:
        ...
```

**实现要点**：
- 从 `.env` 读取配置：`ANY2MD_AUC_APP_ID`、`ANY2MD_AUC_ACCESS_KEY`
- 请求头：`X-Api-App-Key`、`X-Api-Access-Key`、`X-Api-Resource-Id`、`X-Api-Request-Id`、`X-Api-Sequence`
- 状态码处理：
  - `20000000`：完成
  - `20000001`：处理中
  - `20000002`：排队中
  - `20000003`：静音音频（直接返回空文本）
  - `45000xxx`：参数错误
  - `55000031`：服务繁忙（退避重试）
- 轮询策略：每秒查询一次，最多等待 5 分钟

### 3.5 AucMarkdownRenderer

**职责**：把识别结果渲染为 Markdown。

**接口**：
```python
class AucMarkdownRenderer:
    def render(self, transcript: AucTranscript) -> str:
        # Phase 1: 只返回 transcript.text
        # Phase 2: 解析 utterances，添加时间戳和说话人
        ...
```

**第一期实现**：
- 直接返回 `transcript.text`
- 去除首尾空白

## 4. 文件结构规划

### 新增文件

```
src/any2md/converters/audio_video.py  # AudioVideoConverter 主类
src/any2md/auc/
    __init__.py
    settings.py      # AucSettings 配置加载
    client.py        # AucClient 实现
    renderer.py      # AucMarkdownRenderer 实现
    errors.py        # AUC 相关异常
src/any2md/media/
    __init__.py
    preprocessor.py  # MediaPreprocessor 实现
    uploader.py      # Uploader Protocol 和默认实现
    errors.py        # 媒体处理相关异常
tests/converters/test_audio_video.py
tests/auc/
    test_settings.py
    test_client.py
    test_renderer.py
tests/media/
    test_preprocessor.py
    test_uploader.py
```

### 修改文件

```
src/any2md/registry.py              # 注册音频/视频转换器
.env.example                        # 添加 AUC 配置示例
README.md                           # 更新支持格式列表
```

## 5. Step-by-Step 实施步骤

### Step 1: 创建基础模块结构

**文件**：`src/any2md/auc/__init__.py`、`src/any2md/media/__init__.py`

```python
# src/any2md/auc/__init__.py
from any2md.auc.client import AucClient
from any2md.auc.settings import AucSettings
from any2md.auc.renderer import AucMarkdownRenderer

__all__ = ["AucClient", "AucSettings", "AucMarkdownRenderer"]
```

### Step 2: 实现 AucSettings

**文件**：`src/any2md/auc/settings.py`

```python
from dataclasses import dataclass
import os

@dataclass
class AucSettings:
    app_id: str
    access_key: str
    resource_id: str = "volc.bigasr.auc"
    submit_url: str = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/submit"
    query_url: str = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/query"
    timeout: int = 30
    poll_interval: float = 1.0
    max_wait_seconds: int = 300

def load_auc_settings() -> AucSettings:
    app_id = os.getenv("ANY2MD_AUC_APP_ID")
    access_key = os.getenv("ANY2MD_AUC_ACCESS_KEY")

    if not app_id or not access_key:
        raise ValueError("AUC credentials not configured")

    return AucSettings(
        app_id=app_id,
        access_key=access_key,
        resource_id=os.getenv("ANY2MD_AUC_RESOURCE_ID", "volc.bigasr.auc"),
        submit_url=os.getenv("ANY2MD_AUC_SUBMIT_URL", AucSettings.submit_url),
        query_url=os.getenv("ANY2MD_AUC_QUERY_URL", AucSettings.query_url),
        timeout=int(os.getenv("ANY2MD_AUC_TIMEOUT", "30")),
        poll_interval=float(os.getenv("ANY2MD_AUC_POLL_INTERVAL", "1.0")),
        max_wait_seconds=int(os.getenv("ANY2MD_AUC_MAX_WAIT_SECONDS", "300")),
    )
```

### Step 3: 实现 AucClient

**文件**：`src/any2md/auc/client.py`

```python
import time
import uuid
import requests
from dataclasses import dataclass
from any2md.auc.settings import AucSettings

@dataclass
class AucTask:
    task_id: str
    logid: str

@dataclass
class AucTranscript:
    text: str
    utterances: list | None = None

class AucClient:
    def __init__(self, settings: AucSettings):
        self._settings = settings

    def transcribe(self, audio_url: str, audio_format: str) -> AucTranscript:
        task = self._submit(audio_url, audio_format)
        return self._poll(task)

    def _submit(self, audio_url: str, audio_format: str) -> AucTask:
        task_id = str(uuid.uuid4())
        headers = {
            "X-Api-App-Key": self._settings.app_id,
            "X-Api-Access-Key": self._settings.access_key,
            "X-Api-Resource-Id": self._settings.resource_id,
            "X-Api-Request-Id": task_id,
            "X-Api-Sequence": "-1",
        }
        payload = {
            "user": {"uid": "any2md"},
            "audio": {"url": audio_url},
            "request": {
                "model_name": "bigmodel",
                "enable_itn": True,
                "enable_punc": True,
                "enable_ddc": True,
            },
        }

        response = requests.post(
            self._settings.submit_url,
            json=payload,
            headers=headers,
            timeout=self._settings.timeout,
        )

        status_code = response.headers.get("X-Api-Status-Code")
        if status_code != "20000000":
            raise RuntimeError(f"AUC submit failed: {status_code}")

        logid = response.headers.get("X-Tt-Logid", "")
        return AucTask(task_id=task_id, logid=logid)

    def _poll(self, task: AucTask) -> AucTranscript:
        start_time = time.time()

        while True:
            if time.time() - start_time > self._settings.max_wait_seconds:
                raise TimeoutError("AUC transcription timeout")

            headers = {
                "X-Api-App-Key": self._settings.app_id,
                "X-Api-Access-Key": self._settings.access_key,
                "X-Api-Resource-Id": self._settings.resource_id,
                "X-Api-Request-Id": task.task_id,
                "X-Tt-Logid": task.logid,
            }

            response = requests.post(
                self._settings.query_url,
                json={},
                headers=headers,
                timeout=self._settings.timeout,
            )

            status_code = response.headers.get("X-Api-Status-Code")

            if status_code == "20000000":
                result = response.json()
                return AucTranscript(text=result.get("result", {}).get("text", ""))
            elif status_code == "20000003":
                return AucTranscript(text="")
            elif status_code in ("20000001", "20000002"):
                time.sleep(self._settings.poll_interval)
            else:
                raise RuntimeError(f"AUC query failed: {status_code}")
```

### Step 4: 实现 MediaPreprocessor

**文件**：`src/any2md/media/preprocessor.py`

```python
import subprocess
import mimetypes
from pathlib import Path
from dataclasses import dataclass
from tempfile import TemporaryDirectory

@dataclass
class PreparedMedia:
    source_path: Path
    working_path: Path
    media_kind: str
    audio_format: str
    temp_dir: TemporaryDirectory | None = None

class MediaPreprocessor:
    AUDIO_SUFFIXES = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}
    VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".avi", ".webm"}

    def prepare(self, path: Path) -> PreparedMedia:
        suffix = path.suffix.lower()

        if suffix in self.AUDIO_SUFFIXES:
            return PreparedMedia(
                source_path=path,
                working_path=path,
                media_kind="audio",
                audio_format=suffix[1:],
            )
        elif suffix in self.VIDEO_SUFFIXES:
            return self._extract_audio(path)
        else:
            raise ValueError(f"Unsupported media format: {suffix}")

    def _extract_audio(self, video_path: Path) -> PreparedMedia:
        temp_dir = TemporaryDirectory()
        output_path = Path(temp_dir.name) / "audio.wav"

        cmd = [
            "ffmpeg",
            "-i", str(video_path),
            "-vn",
            "-ar", "16000",
            "-ac", "1",
            str(output_path),
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            temp_dir.cleanup()
            raise RuntimeError(f"ffmpeg failed: {result.stderr}")

        return PreparedMedia(
            source_path=video_path,
            working_path=output_path,
            media_kind="video",
            audio_format="wav",
            temp_dir=temp_dir,
        )
```

### Step 5: 实现 Uploader Protocol

**文件**：`src/any2md/media/uploader.py`

```python
from pathlib import Path
from dataclasses import dataclass
from typing import Protocol

@dataclass
class UploadedMedia:
    url: str
    content_type: str

class Uploader(Protocol):
    def upload(self, path: Path) -> UploadedMedia:
        ...

class MockUploader:
    """用于测试的 Mock 实现"""
    def upload(self, path: Path) -> UploadedMedia:
        return UploadedMedia(
            url=f"https://example.com/{path.name}",
            content_type="audio/wav",
        )
```

### Step 6: 实现 AucMarkdownRenderer

**文件**：`src/any2md/auc/renderer.py`

```python
from any2md.auc.client import AucTranscript

class AucMarkdownRenderer:
    def render(self, transcript: AucTranscript) -> str:
        return transcript.text.strip()
```

### Step 7: 实现 AudioVideoConverter

**文件**：`src/any2md/converters/audio_video.py`

```python
from pathlib import Path
from any2md.media.preprocessor import MediaPreprocessor
from any2md.media.uploader import Uploader
from any2md.auc.client import AucClient
from any2md.auc.renderer import AucMarkdownRenderer

class AudioVideoConverter:
    def __init__(
        self,
        preprocessor: MediaPreprocessor,
        uploader: Uploader,
        client: AucClient,
        renderer: AucMarkdownRenderer,
    ):
        self._preprocessor = preprocessor
        self._uploader = uploader
        self._client = client
        self._renderer = renderer

    def __call__(self, path: Path) -> str:
        prepared = None
        try:
            # 1. 预处理
            prepared = self._preprocessor.prepare(path)

            # 2. 上传
            uploaded = self._uploader.upload(prepared.working_path)

            # 3. 转录
            transcript = self._client.transcribe(
                audio_url=uploaded.url,
                audio_format=prepared.audio_format,
            )

            # 4. 渲染
            return self._renderer.render(transcript)
        finally:
            if prepared and prepared.temp_dir:
                prepared.temp_dir.cleanup()
```

### Step 8: 注册转换器

**文件**：`src/any2md/registry.py`

```python
# 在 build_default_registry 函数中添加
from any2md.converters.audio_video import AudioVideoConverter
from any2md.media.preprocessor import MediaPreprocessor
from any2md.media.uploader import MockUploader
from any2md.auc.client import AucClient
from any2md.auc.settings import load_auc_settings
from any2md.auc.renderer import AucMarkdownRenderer

def build_default_registry(ocr_engine: OcrEngine | None = None) -> ConverterRegistry:
    registry = ConverterRegistry()
    registry.register([".pdf"], pdf_to_markdown)
    registry.register([".epub"], epub_to_markdown)
    registry.register([".html", ".htm"], html_to_markdown)
    registry.register([".txt"], text_to_markdown)
    registry.register([".docx"], docx_to_markdown)
    registry.register([".jpg", ".jpeg", ".png"], ImageConverter(ocr_engine or build_default_ocr_engine()))

    # 音频/视频转换器
    try:
        settings = load_auc_settings()
        audio_video_converter = AudioVideoConverter(
            preprocessor=MediaPreprocessor(),
            uploader=MockUploader(),  # TODO: 替换为真实上传器
            client=AucClient(settings),
            renderer=AucMarkdownRenderer(),
        )
        registry.register(
            [".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"],
            audio_video_converter,
        )
        registry.register(
            [".mp4", ".mov", ".mkv", ".avi", ".webm"],
            audio_video_converter,
        )
    except ValueError:
        # AUC 未配置，跳过注册
        pass

    return registry
```

### Step 9: 更新配置示例

**文件**：`.env.example`

```env
# 现有配置...

# AUC 语音识别配置
ANY2MD_AUC_APP_ID=your-app-id
ANY2MD_AUC_ACCESS_KEY=your-access-key
ANY2MD_AUC_RESOURCE_ID=volc.bigasr.auc
```

### Step 10: 更新文档

**文件**：`README.md`

在 "Supported formats" 部分添加：

```markdown
- `.mp3` / `.wav` / `.m4a` / `.aac` / `.flac` / `.ogg` (requires AUC settings in `.env`)
- `.mp4` / `.mov` / `.mkv` / `.avi` / `.webm` (requires AUC settings and ffmpeg)
```

## 6. 测试策略

### 单元测试

**test_settings.py**：
- 测试从环境变量加载配置
- 测试缺失必需配置时抛出异常
- 测试默认值

**test_client.py**：
- Mock requests，测试 submit 请求构造
- Mock requests，测试 query 轮询逻辑
- 测试状态码处理（20000000/20000001/20000002/20000003）
- 测试超时处理

**test_preprocessor.py**：
- 测试音频文件直接返回
- Mock ffmpeg，测试视频抽音轨
- 测试不支持格式抛出异常

**test_renderer.py**：
- 测试纯文本渲染
- 测试空文本处理

**test_audio_video.py**：
- Mock 所有子模块，测试完整流程
- 测试临时文件清理

### 集成测试

**test_cli.py**（扩展现有测试）：
- 测试音频文件转换成功
- 测试视频文件转换成功
- 测试未配置 AUC 时跳过
- 测试 dry-run 模式

## 7. 错误处理策略

### 异常类型

**src/any2md/auc/errors.py**：
```python
class AucError(Exception):
    pass

class AucConfigError(AucError):
    pass

class AucSubmitError(AucError):
    pass

class AucQueryError(AucError):
    pass

class AucTimeoutError(AucError):
    pass
```

**src/any2md/media/errors.py**：
```python
class MediaError(Exception):
    pass

class UnsupportedMediaFormatError(MediaError):
    pass

class FfmpegError(MediaError):
    pass

class UploadError(MediaError):
    pass
```

### 重试逻辑

- AUC 服务繁忙（55000031）：指数退避重试，最多 3 次
- 网络超时：重试 1 次
- 其他错误：不重试，直接失败

### 日志输出

- INFO：任务提交、轮询状态、完成
- WARNING：服务繁忙、重试
- ERROR：ffmpeg 失败、上传失败、AUC 请求失败

## 8. Phase 1 完成判定

- `.mp3/.wav/.m4a` 可成功输出 Markdown
- `.mp4/.mov/.mkv` 可通过 `ffmpeg` 抽音后成功输出 Markdown
- 未配置 AUC 或上传器时，报错信息明确
- Registry 正确注册音频/视频后缀
- CLI 在成功、失败、dry-run 下保持现有语义不变
- 所有单元测试通过

## 9. 后续 Phase 规划

**Phase 2：增强识别结果**
- 开启 `show_utterances`、`enable_speaker_info`
- 解析 speaker/channel 信息
- Markdown 渲染为带时间戳的段落

**Phase 3：稳定性与运维**
- 增加退避重试、详细日志
- 补充集成测试和故障注入测试
- 评估引入 Flash 直传作为可选路径
