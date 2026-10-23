# LNP paper extraction

当前实现第一阶段：复用现有解析库，将正文和 SI 整理为可查询、可回溯的材料包。它不调用 LLM，不将解析结果当作人工审核后的实验数据。

## 运行

Python 3.11+：

```bash
python -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/lnp-preprocess parse Paper/P001_Yu_2026_ELEVATE
```

默认输出 `processed/P001_Yu_2026_ELEVATE/document_bundle.json` 和 `assets/`。原论文、既有开发集不变。输出和虚拟环境不提交到 Git。

```bash
.venv/bin/lnp-preprocess query processed/P001_Yu_2026_ELEVATE/document_bundle.json list_documents
.venv/bin/lnp-preprocess query processed/P001_Yu_2026_ELEVATE/document_bundle.json search_document --args '{"query":"ALC-0314","limit":5}'
.venv/bin/python -m unittest discover -s tests -v
```

三篇实测材料验收：

```bash
.venv/bin/lnp-preprocess parse Paper/P001_Yu_2026_ELEVATE
.venv/bin/lnp-preprocess parse Paper/P002_Cheng_2020_SORT
.venv/bin/lnp-preprocess parse Paper/P003_Yu_2026_siRNA_Screening
.venv/bin/python scripts/check_paper_bundles.py
```

## 输入与输出约定

输入为一篇论文的目录，直接包含 `main.pdf`、SI 的 `.pdf/.docx/.xlsx` 和可选 `metadata.md`。当前不递归扫描子目录；不支持的文件写入问题清单。目录名是 `paper_id`。

输出 JSON 的主要字段：

| 字段 | 内容 |
|---|---|
| `documents` | 文件名、角色、SHA-256、解析状态 |
| `chunks` | 原始解析文字、保守清洗后的文字、顺序、来源锚点 |
| `tables` | PDF 候选表格、Word 表格、Excel 工作表及单元格 |
| `figures` | PDF 整页图片、Word 嵌入图片；`kind` 区分二者 |
| `references` | “Fig. 1 / Table S1”等引用提及；链接暂不推断 |
| `issues` | 低文本页、解析失败、缺公式缓存、解析范围限制等 |
| `config` / `dependencies` | 分块设置与解析库版本，便于复现 |

锚点约定：

- PDF：页码从 1 开始，bbox 为 PDF points、左上原点。文本块当前定位到父页面，并提供该页解析文本中的字符偏移；不声称精确段落 bbox 或已解决双栏阅读顺序。
- Word：`body_index` 从 1 开始，段落与表格按正文顺序排列；表格包含行列和合并单元格起点。Word 无可靠固定页码，使用正文位置；嵌入图片定位到所在正文块。
- Excel：工作表名、行号、单元格坐标；保留原值、公式及已有缓存、数字格式、合并范围。只保存非空单元格；格式化的空尾行不当作数据。
- 文本超过 `max_chunk_chars` 时继续切分并保留块内偏移；未保证句子边界。`raw_text` 是解析库输出，并非 PDF 原始字节。
- ID 依赖源文件内容、文件名、位置、解析器版本、库版本与配置。同一输入和环境重复运行 ID 不变；换版本或源文件后允许变化。

`source_root` 是本机路径；将产物迁移到其他机器后需重新解析或更新来源根目录。原文件以 SHA-256 标识，查询不会自动重新校验文件是否变更。

## 给后续 agent 的工具

```python
from lnp_preprocess.tools import DocumentTools

tools = DocumentTools("processed/P001_Yu_2026_ELEVATE/document_bundle.json")
hits = tools.search_document("ALC-0314", limit=5)
anchor = hits["items"][0]["id"]
evidence = tools.get_chunks([anchor], neighbors=1)
source = tools.get_source_region(anchor)
```

| 工具 | 用途 |
|---|---|
| `list_documents()` | 文件清单、解析状态和问题 |
| `get_document_outline(document_id, offset, limit)` | 分块顺序索引；不是语义章节树 |
| `get_full_text(document_id=None, offset=0, max_chars=20000)` | 按预算读取带锚点的全部解析文字 |
| `get_chunks(chunk_ids, neighbors=0)` | 读指定块及同文件邻近块 |
| `search_document(query, document_id=None, offset=0, limit=20)` | 不区分大小写的字面搜索 |
| `get_table(table_id, offset=0, limit=200)` | 分页读取单元格及表格来源 |
| `get_figure(figure_id)` | 读取图片路径及来源；调用方需接入视觉模型 |
| `resolve_reference(label, document_id=None)` | 返回引用提及和未解析状态，供 map agent 链接 |
| `get_source_region(anchor_id)` | 回到文件、页/正文位置/工作表及对应图片 |

工具返回普通 JSON-compatible 字典，可接任意模型的 function calling；当前没有绑定某个 agent SDK。分页结果提供 `truncated` 和 `next_offset`，调用方必须继续读取。`get_full_text` 预算仅计算文字字符，不等于模型 token 数或完整 JSON 的长度；预算连一个块都放不下时明确报错，不丢弃尾部文字。

## 当前边界与后续阶段

1. 当前程序准备材料并提供锚点。PDF 表格默认用线条检测，结果仅为候选，可能误检或漏检；图像表格保留在页面图片中。Excel 的一张工作表也不自动等同于一个实验表。
2. 接下来 map agent 结合全文块、表格和图片，建立实验、配方、测量结果及跨文件证据关系。不得按相似名称自动合并配方。
3. 提取 agent 按 map 调用工具补齐字段；图中数值需要专门的视觉提取/数字化步骤，保留估读状态。
4. 人工审核后才建立准确率基准。现有 `development_set` 是待审核草稿。

尚未接入 OCR、PDF 语义阅读顺序、图注与图片自动配对、柱状图数字化、Word 文本框/公式/页眉页脚的完整解析、Excel 内嵌图表提取。缺失能力通过 `issues` 暴露，不把图片冒充数值结果。

选型依据和实测结果见 [工具选型](docs/tool-selection.md) 与 [验收记录](docs/validation.md)。
