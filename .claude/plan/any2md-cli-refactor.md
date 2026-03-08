## 📋 实施计划：any2md CLI 重构

### 任务类型
- [x] 后端 / CLI
- [ ] 前端
- [ ] 全栈

### 技术方案
基于现有 [demo.py:9-49](demo.py#L9-L49) 的可工作原型，重构为一个最小但可维护的 CLI 工具：

- 保留现有 PDF / EPUB 转换逻辑与 `--t2s` 行为。
- 采用“后缀注册表 + 应用服务层 + CLI 入口”的分层结构，避免继续把参数解析、转换、写文件、错误处理耦合在一个脚本中。
- CLI 优先使用标准库 `argparse`，遵循 KISS / YAGNI，避免在当前单命令场景引入 `click` / `typer` 额外复杂度。
- 批量模式先做串行处理和失败隔离，不在第一版引入并发。
- 新格式优先级：`.html/.htm`、`.txt`、`.docx`；图片 OCR 只做可插拔边界，不在首版绑定具体引擎。
- 输出路径规则明确区分“单文件输出到文件”和“批量输出到目录”，提前检测冲突，避免覆盖。

### 现状结论
- 核心可用逻辑仅在 [demo.py:9-49](demo.py#L9-L49)。
- 真实入口尚未建立，[main.py:1-6](main.py#L1-L6) 仍是占位实现。
- 依赖已具备 PDF / EPUB / HTML→Markdown / OpenCC 基础能力，见 [pyproject.toml:1-17](pyproject.toml#L1-L17)。
- 需求来源与目标范围见 [projectBrif.md:1-48](projectBrif.md#L1-L48)。
- 当前 README 为空，[README.md](README.md)，且仓库内暂无项目级测试目录。

### 实施步骤
1. **建立包结构与真实入口**
   - 新增 `src/any2md/` 包结构或等价包结构。
   - 将 [main.py:1-6](main.py#L1-L6) 替换/改造为真实 CLI 入口。
   - 在 [pyproject.toml:1-17](pyproject.toml#L1-L17) 中补充脚本入口定义。
   - 预期产物：可通过统一入口运行 CLI，而不是直接依赖 demo 脚本。

2. **迁移现有 PDF / EPUB 核心逻辑**
   - 把 [demo.py:9-10](demo.py#L9-L10) 和 [demo.py:13-23](demo.py#L13-L23) 拆到独立 converter 模块。
   - 保持转换语义不变，不做额外美化或内容清洗。
   - 预期产物：`pdf` / `epub` converter 可被独立调用。

3. **抽象后缀注册表与统一单文件转换流程**
   - 从 [demo.py:26-29](demo.py#L26-L29) 升级为可维护注册表。
   - 将 [demo.py:32-42](demo.py#L32-L42) 拆分为：选择 converter → 执行转换 → 可选 postprocess → 输出写入。
   - 预期产物：统一的 `convert_one()` / `get_converter()` 风格接口。

4. **抽离 `--t2s` 后处理层**
   - 保留 [demo.py:38-40](demo.py#L38-L40) 的懒加载行为。
   - 让 `t2s` 成为全格式统一后处理，而不是绑定某个 converter。
   - 预期产物：`postprocess.py` 或等价模块。

5. **设计并实现输出路径解析规则**
   - 单文件：默认保持兼容，继续输出到 `output.md`。
   - 单文件 + `-o/--output`：允许目标为文件路径；若为目录，则输出 `<stem>.md`。
   - 批量：`--output` 必须表达目录语义；若未指定，则默认输出到 `output/` 目录下的同名 `.md`。
   - 在实际执行前检测输出冲突。
   - 预期产物：独立 `paths` / `pathing` 模块。

6. **实现批量输入与失败隔离**
   - 支持多个输入文件；必要时可扩展目录输入。
   - 逐文件执行，单文件异常不影响整个批次。
   - 最终打印摘要：总数、成功数、失败数。
   - 使用退出码表达“全部成功 / 部分失败 / 参数错误”。
   - 预期产物：`convert_many()` 和统一结果模型。

7. **增加近期待支持格式**
   - `.html/.htm`：读取 HTML 后直接 `markdownify`。
   - `.txt`：直接读取文本并输出 Markdown 文本。
   - `.docx`：推荐使用 `mammoth` 先转 HTML，再复用 `markdownify`。
   - 预期产物：新增 converter 模块与注册表映射。

8. **为图片 OCR 建立可插拔边界**
   - 定义 `OcrEngine` / `OcrProvider` 协议。
   - 图片 converter 在未配置 OCR 引擎时返回清晰错误，而不是直接耦合具体实现。
   - 暂不在本阶段落定 Tesseract / PaddleOCR / 云 OCR。
   - 预期产物：稳定扩展点，降低未来变更范围。

9. **补齐测试骨架与回归保障**
   - 新增项目级 `tests/`。
   - 覆盖注册表、CLI 参数、输出路径映射、失败隔离、`t2s` 后处理。
   - 对 PDF / EPUB 优先做 mock 或最小 fixture 回归测试。
   - 预期产物：最小但完整的测试护栏。

10. **完善 README 与使用说明**
   - 补齐 CLI 用法、支持格式、输出规则、OCR 未决边界说明。
   - 明确单文件与批量模式差异。
   - 预期产物：可发布的基础文档。

### 建议目录草案
```text
src/any2md/
  __init__.py
  cli.py
  app.py
  registry.py
  postprocess.py
  paths.py
  converters/
    pdf.py
    epub.py
    html.py
    text.py
    docx.py
    image.py
  ocr.py

tests/
  test_cli.py
  test_registry.py
  test_paths.py
  test_batch.py
  test_postprocess.py
  test_converters.py
```

### 关键伪代码
```python
Converter = Callable[[Path, ConversionContext], str]

REGISTRY = {
    ".pdf": convert_pdf,
    ".epub": convert_epub,
    ".html": convert_html,
    ".htm": convert_html,
    ".txt": convert_text,
    ".docx": convert_docx,
}


def convert_one(input_path: Path, ctx: ConversionContext, t2s: bool) -> str:
    converter = get_converter(input_path)
    markdown_text = converter(input_path, ctx)
    if t2s:
        markdown_text = to_simplified_chinese(markdown_text)
    return markdown_text


def convert_many(inputs: list[Path], output_arg: Path | None, t2s: bool, ctx: ConversionContext):
    planned_outputs = [resolve_output_path(path, output_arg, is_batch=len(inputs) > 1) for path in inputs]
    ensure_no_output_collisions(planned_outputs)

    results = []
    for input_path, output_path in zip(inputs, planned_outputs):
        try:
            markdown_text = convert_one(input_path, ctx, t2s)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(markdown_text, encoding="utf-8")
            results.append((input_path, output_path, True, None))
        except Exception as exc:
            results.append((input_path, None, False, str(exc)))
    return results
```

### 关键文件
| 文件 | 操作 | 说明 |
|------|------|------|
| [demo.py:9-49](demo.py#L9-L49) | 拆分/迁移 | 现有核心逻辑来源 |
| [main.py:1-6](main.py#L1-L6) | 替换/改造 | 真实 CLI 入口 |
| [pyproject.toml:1-17](pyproject.toml#L1-L17) | 修改 | 补充脚本入口、依赖与测试配置 |
| [projectBrif.md:1-48](projectBrif.md#L1-L48) | 参考 | 需求边界与验收依据 |
| [README.md](README.md) | 补充 | 用法与行为说明 |
| `src/any2md/*` | 新增 | 模块化实现 |
| `tests/*` | 新增 | 回归与行为验证 |

### 风险与缓解
| 风险 | 缓解措施 |
|------|----------|
| 批量模式下输出覆盖冲突 | 默认输出到 `output/` 目录并预先解析全部输出路径检测重复 |
| `docx` 解析实现复杂度过高 | 优先用 `mammoth -> html -> markdownify`，避免手写结构重建 |
| OCR 依赖过重或跨平台复杂 | 先做接口边界，不在首版绑定具体 OCR 引擎 |
| 重构导致 PDF / EPUB 行为漂移 | 先迁移后验证，保留原逻辑语义，添加最小回归测试 |
| Python 3.13 依赖兼容性风险 | 在实施阶段重新核对新增依赖兼容性，必要时评估版本策略 |
| README 为空导致使用成本高 | 在交付前补齐 CLI 合同和示例 |

### 方案取舍结论
- **Codex 强信号**：优先 `argparse`、注册表驱动、串行批处理、最小新增依赖。
- **Gemini 强信号**：CLI 语义必须直观，单文件/批量输出规则要清晰，OCR 应做插件边界。
- **综合结论**：采用“最小架构升级”而非过度平台化，先稳定核心转换与 CLI 合同，再扩展格式支持。

### SESSION_ID（供 /ccg:execute 使用）
- CODEX_SESSION: 019cccde-5da5-7e00-8d68-4e48439aeb3a
- CODEX_ARCHITECT_SESSION: 019ccce5-04f5-7d00-8960-5d8112515444
- GEMINI_SESSION: 4f9a4b45-8502-4aeb-8e99-5459f02959b3
- GEMINI_ARCHITECT_SESSION: unavailable (timeout / quota issue during architect phase)
