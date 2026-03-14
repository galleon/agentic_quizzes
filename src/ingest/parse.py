"""Parse source documents in data/raw/ into plain text under data/extracted/."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pymupdf  # PyMuPDF

from src.common.config import get_settings, project_root


def parse_pdf(pdf_path: Path) -> str:
    with pymupdf.open(str(pdf_path)) as doc:
        pages = []
        for i, page in enumerate(doc):
            text = page.get_text()
            if text.strip():
                pages.append(f"<!-- page {i + 1} -->\n{text}")
    return "\n\n".join(pages)


def parse_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


# Maps file extensions to their parser functions.
# Keep in sync with IngestConfig.supported_extensions in src/common/config.py.
_PARSERS = {
    ".pdf": parse_pdf,
    ".txt": parse_text,
    ".md": parse_text,
    ".html": parse_text,
}


def parse_file(path: Path) -> str:
    parser = _PARSERS.get(path.suffix.lower())
    if parser is None:
        print(f"  [skip] unsupported extension: {path.suffix}", file=sys.stderr)
        return ""
    return parser(path)


def main() -> None:
    cfg = get_settings()
    root = project_root()
    raw_dir = root / cfg.ingest.raw_dir
    out_dir = root / cfg.ingest.extracted_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    supported = set(cfg.ingest.supported_extensions)
    files = [p for p in raw_dir.rglob("*") if p.is_file() and p.suffix.lower() in supported]

    if not files:
        print(f"No supported files found in {raw_dir}. Nothing to parse.", file=sys.stderr)
        sys.exit(1)

    report_lines = [f"# Ingest Parse Report\n\nRun: {datetime.now().isoformat()}\n\n"]
    ok, skipped = 0, 0

    for src_file in files:
        print(f"Parsing: {src_file.name}")
        text = parse_file(src_file)
        if not text:
            skipped += 1
            report_lines.append(f"- SKIP `{src_file.name}` (empty or unsupported)\n")
            continue

        # Mirror relative path from raw_dir so same-name files in different
        # subdirectories don't overwrite each other.
        rel = src_file.relative_to(raw_dir)
        out_path = out_dir / rel.parent / f"{src_file.stem}_{src_file.suffix.lstrip('.')}.txt"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text, encoding="utf-8")
        ok += 1
        report_lines.append(f"- OK `{src_file.name}` → `{out_path.relative_to(root)}`\n")

    report_lines.append(f"\n**Total**: {ok} parsed, {skipped} skipped\n")
    reports_dir = root / cfg.quiz.reports_dir
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "parse_report.md").write_text("".join(report_lines), encoding="utf-8")
    print(f"Done. {ok} files extracted to {out_dir}")


if __name__ == "__main__":
    main()
