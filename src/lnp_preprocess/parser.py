"""Adapters around pdfplumber, python-docx and openpyxl.

Offsets and identifiers are evidence anchors, not inferred experiment identities.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime
from importlib.metadata import version
from pathlib import Path

import pdfplumber
from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from openpyxl import load_workbook

from . import __version__

SUPPORTED = {".pdf", ".docx", ".xlsx", ".md", ".txt"}
REFERENCE = re.compile(r"\b(?:Fig(?:ure)?s?\.?|Tables?)\s*S?\d+[a-z]?", re.I)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_value(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


class Builder:
    def __init__(self, paper_dir: Path, output_dir: Path, max_chars: int):
        if max_chars < 100:
            raise ValueError("max_chars must be >= 100")
        self.paper_dir, self.output_dir = paper_dir.resolve(), output_dir.resolve()
        if self.output_dir == self.paper_dir or self.output_dir in self.paper_dir.parents:
            raise ValueError("Output must not be the input directory or its ancestor")
        self.assets = self.output_dir / "assets"
        self.assets.mkdir(parents=True, exist_ok=True)
        self.max_chars = max_chars
        self.bundle = {
            "schema_version": "1.0", "parser_version": __version__,
            "paper_id": paper_dir.name,
            "source_root": str(self.paper_dir),
            "config": {"max_chunk_chars": max_chars, "pdf_render_resolution": 110},
            "dependencies": {name: version(name) for name in
                             ("pdfplumber", "pypdfium2", "python-docx", "openpyxl")},
            "documents": [], "chunks": [], "tables": [], "figures": [],
            "references": [], "issues": [],
        }

    def ident(self, doc, kind, locator):
        payload = [__version__, self.bundle["dependencies"], self.bundle["config"],
                   doc["id"], kind, locator]
        return kind + "_" + digest(json.dumps(payload, sort_keys=True).encode())[:20]

    def issue(self, doc, code, message, **locator):
        self.bundle["issues"].append({"document_id": doc["id"], "code": code,
                                      "message": message, "locator": locator})

    def chunk(self, doc, text, locator, kind="text", **extra):
        # Preserve exact input to the adapter; cleaned text is deliberately conservative.
        for offset in range(0, len(text), self.max_chars):
            raw = text[offset:offset + self.max_chars]
            loc = dict(locator, text_offset=offset, text_length=len(raw))
            item = {"id": self.ident(doc, "chunk", [kind, loc]),
                    "document_id": doc["id"], "kind": kind,
                    "order": len(self.bundle["chunks"]), "locator": loc,
                    "raw_text": raw, "text": raw.replace("\u00a0", " "), **extra}
            self.bundle["chunks"].append(item)
            for match in REFERENCE.finditer(raw):
                self.bundle["references"].append({
                    "source_chunk_id": item["id"], "label": match.group(),
                    "span": [match.start(), match.end()], "target_ids": [],
                    "status": "unresolved"})

    def table(self, doc, locator, cells, **extra):
        item = {"id": self.ident(doc, "table", locator), "document_id": doc["id"],
                "locator": locator, "cells": cells, **extra}
        self.bundle["tables"].append(item)
        return item

    def asset(self, doc, locator, content, suffix, kind):
        ident = self.ident(doc, "figure", [kind, locator])
        path = self.assets / (ident + suffix)
        path.write_bytes(content)
        item = {"id": ident, "document_id": doc["id"], "kind": kind,
                "locator": locator, "asset_path": str(path.relative_to(self.output_dir)),
                "label": None}
        self.bundle["figures"].append(item)
        return item

    def pdf(self, path, doc):
        self.issue(doc, "pdf_reading_order_unverified",
                   "Layout text preserves spacing; multi-column reading order and paragraph boundaries need review.")
        self.issue(doc, "pdf_visual_extraction_pending",
                   "Page images preserve charts and raster tables. No chart digitization, OCR or semantic figure detection is performed.")
        with pdfplumber.open(path) as pdf:
            doc["page_count"] = len(pdf.pages)
            for page in pdf.pages:
                loc = {"page": page.page_number, "bbox": list(page.bbox),
                       "coordinate_system": "pdf_points_top_left"}
                try:
                    rendered = page.to_image(resolution=110)
                    import io
                    stream = io.BytesIO()
                    rendered.original.save(stream, format="PNG")
                    self.asset(doc, loc, stream.getvalue(), ".png", "page_image")
                except Exception as exc:
                    self.issue(doc, "page_render_failed", str(exc), page=page.page_number)
                text = page.extract_text(layout=True) or ""
                if len(text.strip()) < 80:
                    self.issue(doc, "low_text_page", "OCR or visual inspection required.", page=page.page_number)
                # Split at layout blank lines; coordinates remain the parent page.
                offset = 0
                for part in re.split(r"(\n[ \t]*\n)", text):
                    if part.strip():
                        self.chunk(doc, part, dict(loc, page_text_offset=offset), "pdf_layout_block")
                    offset += len(part)
                try:
                    for index, table in enumerate(page.find_tables()):
                        rows = table.extract()
                        cells = [{"row": r + 1, "column": c + 1, "raw_value": value,
                                  "bbox": list(table.rows[r].cells[c]) if table.rows[r].cells[c] else None}
                                 for r, row in enumerate(rows) for c, value in enumerate(row)]
                        self.table(doc, dict(loc, bbox=list(table.bbox), table_index=index + 1),
                                   cells, status="candidate_unreviewed", row_count=len(rows),
                                   column_count=max(map(len, rows), default=0), method="pdfplumber_lines")
                except Exception as exc:
                    self.issue(doc, "pdf_table_detection_failed", str(exc), page=page.page_number)
                page.close()

    def docx(self, path, doc):
        document = Document(path)
        self.issue(doc, "docx_scope", "Main body text, tables and embedded images are parsed. Headers, footers, comments, text boxes and equations are not fully supported; Word page numbers are unavailable.")
        table_number = 0
        for body_index, block in enumerate(document.iter_inner_content(), 1):
            loc = {"body_index": body_index}
            if isinstance(block, Table):
                table_number += 1
                cells, origins = [], {}
                for r, row in enumerate(block.rows, 1):
                    for c, cell in enumerate(row.cells, 1 + row.grid_cols_before):
                        origin = origins.setdefault(cell._tc, [r, c])
                        cells.append({"row": r, "column": c, "raw_value": cell.text,
                                      "merged_origin": origin})
                table = self.table(doc, dict(loc, table_index=table_number), cells,
                                   status="parsed_unreviewed", row_count=len(block.rows),
                                   column_count=len(block.columns))
                self.chunk(doc, "\n".join(f"R{x['row']}C{x['column']}: {x['raw_value']}" for x in cells),
                           loc, "table_text", table_id=table["id"])
            else:
                self.chunk(doc, block.text, loc, "paragraph", style=block.style.name)
            # Includes drawings inside table cells; same body index anchors them.
            for image_index, blip in enumerate(block._element.iter(qn("a:blip")), 1):
                rel_id = blip.get(qn("r:embed"))
                if rel_id:
                    part = document.part.related_parts[rel_id]
                    self.asset(doc, dict(loc, image_index=image_index), part.blob,
                               Path(str(part.partname)).suffix, "embedded_image")
                else:
                    self.issue(doc, "external_image", "Linked image was not downloaded.", **loc)

    def xlsx(self, path, doc):
        formulas = load_workbook(path, data_only=False)
        cached = load_workbook(path, data_only=True)
        try:
            for sheet in formulas:
                cells, missing_cache = [], 0
                for row in sheet:
                    for cell in row:
                        if cell.value is None:
                            continue
                        formula = cell.value if cell.data_type == "f" else None
                        cache = cached[sheet.title][cell.coordinate].value if formula else None
                        if formula and cache is None:
                            missing_cache += 1
                        cells.append({"coordinate": cell.coordinate, "row": cell.row,
                                      "column": cell.column, "raw_value": json_value(cell.value),
                                      "formula": formula, "cached_value": json_value(cache),
                                      "data_type": cell.data_type, "number_format": cell.number_format})
                loc = {"sheet": sheet.title}
                table = self.table(doc, loc, cells, status="parsed_unreviewed",
                                   row_count=max((c["row"] for c in cells), default=0),
                                   column_count=max((c["column"] for c in cells), default=0),
                                   declared_dimensions=sheet.calculate_dimension(),
                                   merged_ranges=[str(r) for r in sheet.merged_cells.ranges],
                                   hidden=sheet.sheet_state != "visible")
                # One row per chunk, retaining cell coordinates and repeated/multirow headers.
                by_row = {}
                for cell in cells:
                    by_row.setdefault(cell["row"], []).append(cell)
                for row, values in by_row.items():
                    self.chunk(doc, " | ".join(f"{c['coordinate']}: {c['raw_value']}" for c in values),
                               dict(loc, row=row), "spreadsheet_row", table_id=table["id"])
                if missing_cache:
                    self.issue(doc, "formula_cache_missing", f"{missing_cache} formula cells lack cached results; no recalculation performed.", **loc)
                if sheet._images or sheet._charts:
                    self.issue(doc, "spreadsheet_visuals_pending", "Embedded Excel images/charts require separate extraction; original workbook preserved.", **loc)
        finally:
            formulas.close()
            cached.close()

    def run(self):
        files = sorted(p for p in self.paper_dir.iterdir() if p.is_file())
        if not any(p.suffix.lower() in SUPPORTED for p in files):
            raise ValueError("No supported documents in input directory")
        for path in files:
            sha = digest(path.read_bytes())
            doc = {"id": "doc_" + digest((path.name + sha).encode())[:20],
                   "filename": path.name, "sha256": sha, "format": path.suffix.lower()[1:],
                   "role": "main" if path.stem.lower() == "main" else
                           "metadata" if path.suffix.lower() in {".md", ".txt"} else "supplement",
                   "status": "parsed"}
            self.bundle["documents"].append(doc)
            try:
                suffix = path.suffix.lower()
                if suffix == ".pdf":
                    self.pdf(path, doc)
                elif suffix == ".docx":
                    self.docx(path, doc)
                elif suffix == ".xlsx":
                    self.xlsx(path, doc)
                elif suffix in {".txt", ".md"}:
                    self.chunk(doc, path.read_text(encoding="utf-8"), {}, "metadata_text")
                else:
                    doc["status"] = "unsupported"
                    self.issue(doc, "unsupported_file", "No adapter for this file format")
            except Exception as exc:
                doc["status"] = "failed"
                self.issue(doc, "document_parse_failed", f"{type(exc).__name__}: {exc}")
        output = self.output_dir / "document_bundle.json"
        output.write_text(json.dumps(self.bundle, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        return self.bundle


def parse_paper(paper_dir, output_dir, max_chars=4000):
    return Builder(Path(paper_dir), Path(output_dir), max_chars).run()
