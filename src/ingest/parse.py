"""Parse source documents in data/raw/ into plain text under data/extracted/."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from src.common.config import get_settings, project_root
from src.ingest.parse_docling import parse_pdf_docling


def parse_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


# Maps file extensions to their parser functions.
# Keep in sync with IngestConfig.supported_extensions in src/common/config.py.
_PARSERS: dict[str, object] = {
    ".pdf": parse_pdf_docling,
    ".txt": parse_text,
    ".md": parse_text,
    ".html": parse_text,
}


def parse_file(path: Path) -> str:
    """Parse a single file to text."""
    suffix = path.suffix.lower()
    parser = _PARSERS.get(suffix)
    if parser is None:
        print(f"  [skip] unsupported extension: {path.suffix}", file=sys.stderr)
        return ""
    return parser(path)  # type: ignore[operator]


def main() -> None:
    cfg = get_settings()
    root = project_root()
    raw_dir = root / cfg.ingest.raw_dir
    out_dir = root / cfg.ingest.extracted_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    # Intersect config extensions with _PARSERS: config controls which formats
    # are active (so users can narrow the set via settings.yaml), while _PARSERS
    # is the safety net ensuring we never attempt to parse an unsupported type.
    supported = set(cfg.ingest.supported_extensions) & set(_PARSERS.keys())
    files = sorted(
        (p for p in raw_dir.rglob("*") if p.is_file() and p.suffix.lower() in supported),
        key=lambda p: p.relative_to(raw_dir).as_posix(),
    )

    if not files:
        print(f"No supported files found in {raw_dir}. Nothing to parse.", file=sys.stderr)
        sys.exit(1)

    report_lines = [f"# Ingest Parse Report\n\nRun: {datetime.now().isoformat()}\n\n"]
    ok, skipped = 0, 0

    for src_file in files:
        print(f"Parsing: {src_file.relative_to(raw_dir)}")
        text = parse_file(src_file)
        if not text:
            skipped += 1
            report_lines.append(
                f"- SKIP `{src_file.relative_to(raw_dir).as_posix()}` (empty or unsupported)\n"
            )
            continue

        # Mirror relative path from raw_dir so same-name files in different
        # subdirectories don't overwrite each other.
        rel = src_file.relative_to(raw_dir)
        out_path = out_dir / rel.parent / f"{src_file.stem}_{src_file.suffix.lstrip('.')}.txt"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text, encoding="utf-8")
        ok += 1
        report_lines.append(
            f"- OK `{rel.as_posix()}` → `{out_path.relative_to(root).as_posix()}`\n"
        )

    report_lines.append(f"\n**Total**: {ok} parsed, {skipped} skipped\n")
    reports_dir = root / cfg.quiz.reports_dir
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "parse_report.md").write_text("".join(report_lines), encoding="utf-8")
    print(f"Done. {ok} files extracted to {out_dir}")


if __name__ == "__main__":
    main()
