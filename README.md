# LNP paper extraction

The first stage uses existing parsing libraries to turn papers and supplementary information (SI) into searchable document bundles with source anchors. This stage makes no LLM calls. Its output is parsed source material, not manually reviewed experimental data.

## Getting started

Requires Python 3.11 or later:

```bash
python -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/lnp-preprocess parse Paper/P001_Yu_2026_ELEVATE
```

By default, output is written to `processed/P001_Yu_2026_ELEVATE/document_bundle.json` and an `assets/` directory alongside it. Source papers and existing development datasets remain unchanged. Generated output and virtual environments are excluded from Git.

```bash
.venv/bin/lnp-preprocess query processed/P001_Yu_2026_ELEVATE/document_bundle.json list_documents
.venv/bin/lnp-preprocess query processed/P001_Yu_2026_ELEVATE/document_bundle.json search_document --args '{"query":"ALC-0314","limit":5}'
.venv/bin/python -m unittest discover -s tests -v
```

To run integration checks on all three papers:

```bash
.venv/bin/lnp-preprocess parse Paper/P001_Yu_2026_ELEVATE
.venv/bin/lnp-preprocess parse Paper/P002_Cheng_2020_SORT
.venv/bin/lnp-preprocess parse Paper/P003_Yu_2026_siRNA_Screening
.venv/bin/python scripts/check_paper_bundles.py
```

## Input and output contract

The input is a directory for one paper, directly containing `main.pdf`, SI files in `.pdf`, `.docx`, or `.xlsx` format, and an optional `metadata.md`. Subdirectories are not scanned recursively. Unsupported files are recorded in the issue list. The directory name becomes the `paper_id`.

The output JSON contains these main fields:

| Field | Contents |
|---|---|
| `documents` | File names, roles, SHA-256 hashes, and parsing status |
| `chunks` | Raw parsed text, conservatively cleaned text, order, and source anchors |
| `tables` | PDF table candidates, Word tables, and Excel worksheets with their cells |
| `figures` | Full-page PDF images and embedded Word images, distinguished by `kind` |
| `references` | Mentions such as “Fig. 1” and “Table S1”; target links are not yet inferred |
| `issues` | Pages with little text, parsing failures, missing formula caches, scope limitations, and other issues |
| `config` / `dependencies` | Chunking settings and parser library versions for reproducibility |

Source anchor conventions:

- **PDF:** Page numbers start at 1. Bounding boxes use PDF points with a top-left origin. Text blocks currently point to their parent page and include character offsets within the parsed page text. Precise paragraph bounding boxes and reliable two-column reading order are not provided.
- **Word:** `body_index` starts at 1. Paragraphs and tables follow document body order. Tables include row and column positions and the origin of merged cells. Body positions are used instead of fixed page numbers, which are not reliably available in Word. Embedded images are anchored to their containing body block.
- **Excel:** Anchors include worksheet names, row numbers, and cell coordinates. Original values, formulas, existing cached results, number formats, and merged ranges are preserved. Only nonempty cells are saved; formatted but empty trailing rows do not become data.
- Text exceeding `max_chunk_chars` is split further with offsets retained within the block. Sentence boundaries are not guaranteed. `raw_text` is the parsing library's output, not the original PDF bytes.
- IDs depend on source file contents, file names, positions, parser and library versions, and configuration. Repeated runs with identical inputs and environments produce identical IDs. IDs may change when source files or versions change.

`source_root` is a local path. After moving output to another machine, reparse the documents or update the source root. Source files are identified by SHA-256 hashes, but queries do not automatically recheck whether those files have changed.

## Tools for downstream agents

```python
from lnp_preprocess.tools import DocumentTools

tools = DocumentTools("processed/P001_Yu_2026_ELEVATE/document_bundle.json")
hits = tools.search_document("ALC-0314", limit=5)
anchor = hits["items"][0]["id"]
evidence = tools.get_chunks([anchor], neighbors=1)
source = tools.get_source_region(anchor)
```

| Tool | Purpose |
|---|---|
| `list_documents()` | List files, parsing status, and issues |
| `get_document_outline(document_id, offset, limit)` | Return an ordered chunk index, not a semantic section hierarchy |
| `get_full_text(document_id=None, offset=0, max_chars=20000)` | Read parsed text with anchors within a character budget |
| `get_chunks(chunk_ids, neighbors=0)` | Read selected chunks and neighboring chunks from the same file |
| `search_document(query, document_id=None, offset=0, limit=20)` | Perform case-insensitive literal search |
| `get_table(table_id, offset=0, limit=200)` | Read paginated cells and table provenance |
| `get_figure(figure_id)` | Return an image path and provenance; the caller must provide vision-model integration |
| `resolve_reference(label, document_id=None)` | Return reference mentions and their unresolved status for the map agent to link |
| `get_source_region(anchor_id)` | Locate the source file, page/body position/worksheet, and associated images |

Tools return ordinary JSON-compatible dictionaries and can be connected to model function calling. They are not tied to a specific agent SDK. Paginated responses include `truncated` and `next_offset`; callers must follow the cursor to retrieve the remaining content. The `get_full_text` budget counts text characters, not model tokens or the full JSON response length. If the budget cannot fit even one chunk, the tool raises an error rather than discarding trailing text.

## Current limitations and next stages

1. The current program prepares source material and anchors. PDF tables are detected using lines by default and remain unreviewed candidates, with possible false positives and omissions. Raster tables are preserved in page images. An Excel worksheet is not automatically treated as a single experimental table.
2. The next stage is a map agent that combines text chunks, tables, and images to link experiments, formulations, measurements, and evidence across files. Formulations must not be merged automatically based on similar names.
3. An extraction agent will use the map and tools to fill data fields. Values shown only in figures require dedicated visual extraction or digitization, with estimates explicitly identified.
4. Accuracy benchmarks require human review first. The existing `development_set` contains drafts awaiting review.

OCR, semantic PDF reading order, automatic caption-to-image matching, bar-chart digitization, complete parsing of Word text boxes/equations/headers/footers, and extraction of embedded Excel charts are not yet integrated. These limitations are exposed through `issues`; preserved images are not treated as extracted numerical results.

See [Tool selection](docs/tool-selection.md) and [Validation record](docs/validation.md) for selection rationale and integration results. These supporting documents are currently in Chinese.
