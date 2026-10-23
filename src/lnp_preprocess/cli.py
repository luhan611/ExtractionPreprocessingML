import argparse
import json
from pathlib import Path

from .parser import parse_paper
from .tools import DocumentTools


def main():
    parser = argparse.ArgumentParser(description="Parse paper documents or query an existing bundle")
    sub = parser.add_subparsers(dest="command", required=True)
    parse = sub.add_parser("parse")
    parse.add_argument("paper_dir", type=Path)
    parse.add_argument("--output", type=Path)
    parse.add_argument("--max-chars", type=int, default=4000)
    query = sub.add_parser("query")
    query.add_argument("bundle", type=Path)
    query.add_argument("tool", choices=["list_documents", "get_document_outline", "get_full_text",
                                      "get_chunks", "search_document", "get_table", "get_figure",
                                      "resolve_reference", "get_source_region"])
    query.add_argument("--args", default="{}", help="JSON object of tool arguments")
    args = parser.parse_args()
    if args.command == "parse":
        output = args.output or Path("processed") / args.paper_dir.name
        bundle = parse_paper(args.paper_dir, output, args.max_chars)
        result = {"output": str(output / "document_bundle.json"),
                  "counts": {key: len(bundle[key]) for key in
                             ("documents", "chunks", "tables", "figures", "issues")},
                  "failed_documents": [d["filename"] for d in bundle["documents"] if d["status"] == "failed"]}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if result["failed_documents"]:
            raise SystemExit(1)
    else:
        result = getattr(DocumentTools(args.bundle), args.tool)(**json.loads(args.args))
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
