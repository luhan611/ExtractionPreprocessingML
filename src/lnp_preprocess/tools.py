"""Read-only, JSON-compatible tools for the subsequent map/extraction agents."""
from __future__ import annotations

import json
from pathlib import Path


class DocumentTools:
    def __init__(self, bundle_path):
        self.path = Path(bundle_path).resolve()
        self.bundle = json.loads(self.path.read_text(encoding="utf-8"))
        self.documents = {x["id"]: x for x in self.bundle["documents"]}
        self.chunks = {x["id"]: x for x in self.bundle["chunks"]}
        self.tables = {x["id"]: x for x in self.bundle["tables"]}
        self.figures = {x["id"]: x for x in self.bundle["figures"]}

    @staticmethod
    def _page(items, offset=0, limit=20):
        if offset < 0 or limit < 1:
            raise ValueError("offset must be >= 0 and limit >= 1")
        selected = items[offset:offset + limit]
        end = offset + len(selected)
        return {"items": selected, "total": len(items), "offset": offset,
                "truncated": end < len(items), "next_offset": end if end < len(items) else None}

    def _document_chunks(self, document_id=None):
        if document_id is not None and document_id not in self.documents:
            raise KeyError(document_id)
        return [x for x in self.bundle["chunks"] if document_id is None or x["document_id"] == document_id]

    def list_documents(self):
        return {"documents": self.bundle["documents"], "issues": self.bundle["issues"]}

    def get_document_outline(self, document_id, offset=0, limit=100):
        # Structural index, not an LLM-generated section hierarchy.
        items = [{k: x[k] for k in ("id", "kind", "order", "locator")}
                 | {"preview": x["text"][:120]} for x in self._document_chunks(document_id)]
        return self._page(items, offset, limit)

    def get_chunks(self, chunk_ids, neighbors=0):
        if neighbors < 0:
            raise ValueError("neighbors must be >= 0")
        selected = set()
        for ident in chunk_ids:
            item = self.chunks[ident]
            siblings = self._document_chunks(item["document_id"])
            index = next(i for i, x in enumerate(siblings) if x["id"] == ident)
            selected.update(x["id"] for x in siblings[max(0, index-neighbors):index+neighbors+1])
        return {"items": [x for x in self.bundle["chunks"] if x["id"] in selected],
                "truncated": False}

    def get_full_text(self, document_id=None, offset=0, max_chars=20000):
        """Cursor is a chunk index; returned blocks always retain source IDs.

        Stops before budget; raises if budget cannot fit even one complete chunk.
        This prevents losing the tail of a chunk at the next cursor.
        """
        if offset < 0 or max_chars < 1:
            raise ValueError("Invalid offset or character budget")
        chunks = self._document_chunks(document_id)
        items, size = [], 0
        for chunk in chunks[offset:]:
            if size + len(chunk["text"]) > max_chars:
                if not items:
                    raise ValueError(f"max_chars must be >= {len(chunk['text'])} to fit next chunk")
                break
            items.append(chunk)
            size += len(chunk["text"])
        end = offset + len(items)
        return {"items": items, "text_characters": size, "total_chunks": len(chunks),
                "total_text_characters": sum(len(x["text"]) for x in chunks),
                "offset": offset, "truncated": end < len(chunks),
                "next_offset": end if end < len(chunks) else None,
                "scope": "parsed text only; see issues and figures for visual evidence"}

    def search_document(self, query, document_id=None, offset=0, limit=20):
        if not query.strip():
            raise ValueError("query must not be empty")
        matches = [x for x in self._document_chunks(document_id) if query.casefold() in x["text"].casefold()]
        return self._page(matches, offset, limit)

    def get_table(self, table_id, offset=0, limit=200):
        table = self.tables[table_id]
        return {k: v for k, v in table.items() if k != "cells"} | {"cell_page": self._page(table["cells"], offset, limit)}

    def get_figure(self, figure_id):
        figure = self.figures[figure_id]
        return figure | {"absolute_asset_path": str(self.path.parent / figure["asset_path"])}

    def resolve_reference(self, label, document_id=None):
        if document_id is not None and document_id not in self.documents:
            raise KeyError(document_id)
        refs = [x for x in self.bundle["references"] if x["label"].casefold() == label.casefold()
                and (document_id is None or self.chunks[x["source_chunk_id"]]["document_id"] == document_id)]
        return {"label": label, "mentions": refs, "status": "unresolved",
                "reason": "Numbered figure/table linkage is reserved for the map agent; no guessed targets."}

    def get_source_region(self, anchor_id):
        item = next((index[anchor_id] for index in (self.chunks, self.tables, self.figures)
                     if anchor_id in index), None)
        if item is None:
            raise KeyError(anchor_id)
        doc = self.documents[item["document_id"]]
        locator = item["locator"]
        assets = [x for x in self.bundle["figures"] if x["document_id"] == doc["id"]
                  and (("page" in locator and x["locator"].get("page") == locator["page"])
                       or ("body_index" in locator and x["locator"].get("body_index") == locator["body_index"]))]
        return {"document": doc, "locator": locator,
                "source_path": str(Path(self.bundle["source_root"]) / doc["filename"]),
                "assets": assets, "region_precision": "page" if "page" in locator else
                "cell_or_sheet" if "sheet" in locator else "body_block"}
