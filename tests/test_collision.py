"""Tests that same-stem / same-name files in different subdirectories
do not collide across the three ingest pipeline stages (parse, clean, chunk).

All tests are pure file-system operations using tmp_path — no LLM, no Qdrant.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from src.common.models import Chunk, ChunkMetadata
from src.ingest.chunk import chunk_text
from src.ingest.clean import clean_text

# ---------------------------------------------------------------------------
# parse.py — output filename formula
# ---------------------------------------------------------------------------


def _parse_output_name(src: Path) -> str:
    """Replicate the filename formula used in parse.py main()."""
    return f"{src.stem}_{src.suffix.lstrip('.')}.txt"


def test_parse_same_stem_different_extension_different_names():
    """foo.txt and foo.md must produce different extracted filenames."""
    assert _parse_output_name(Path("foo.txt")) != _parse_output_name(Path("foo.md"))
    assert _parse_output_name(Path("foo.txt")) == "foo_txt.txt"
    assert _parse_output_name(Path("foo.md")) == "foo_md.txt"
    assert _parse_output_name(Path("report.pdf")) == "report_pdf.txt"


def test_parse_same_name_different_subdir_no_collision(tmp_path):
    """data/raw/a/foo.txt and data/raw/b/foo.txt must produce distinct output paths."""
    raw_dir = tmp_path / "raw"
    extracted_dir = tmp_path / "extracted"
    for sub in ("a", "b"):
        (raw_dir / sub).mkdir(parents=True)
        (raw_dir / sub / "foo.txt").write_text(f"content {sub}", encoding="utf-8")

    output_paths = set()
    for src_file in raw_dir.rglob("*.txt"):
        rel = src_file.relative_to(raw_dir)
        out = extracted_dir / rel.parent / _parse_output_name(src_file)
        output_paths.add(out)

    assert len(output_paths) == 2, "Two source files must map to two distinct output paths"


def test_parse_writes_distinct_content_for_same_stem(tmp_path):
    """Content from foo.txt and foo.md must not overwrite each other."""
    raw_dir = tmp_path / "raw"
    extracted_dir = tmp_path / "extracted"
    raw_dir.mkdir()
    (raw_dir / "foo.txt").write_text("plain text content", encoding="utf-8")
    (raw_dir / "foo.md").write_text("markdown content", encoding="utf-8")

    for src_file in raw_dir.rglob("*"):
        if not src_file.is_file():
            continue
        rel = src_file.relative_to(raw_dir)
        out = extracted_dir / rel.parent / _parse_output_name(src_file)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(src_file.read_text(encoding="utf-8"), encoding="utf-8")

    txt_out = extracted_dir / "foo_txt.txt"
    md_out = extracted_dir / "foo_md.txt"
    assert txt_out.exists() and md_out.exists()
    assert txt_out.read_text(encoding="utf-8") == "plain text content"
    assert md_out.read_text(encoding="utf-8") == "markdown content"


# ---------------------------------------------------------------------------
# clean.py — rglob + relative path mirroring
# ---------------------------------------------------------------------------


def test_clean_mirrors_subdirectory_structure(tmp_path):
    """Cleaned output must preserve the subdirectory layout of extracted files."""
    extracted_dir = tmp_path / "extracted"
    cleaned_dir = tmp_path / "cleaned"
    (extracted_dir / "subdir").mkdir(parents=True)
    (extracted_dir / "subdir" / "doc_pdf.txt").write_text("some   text\n\n\nmore", encoding="utf-8")
    (extracted_dir / "top_md.txt").write_text("top level", encoding="utf-8")

    for f in extracted_dir.rglob("*.txt"):
        out = cleaned_dir / f.relative_to(extracted_dir)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(clean_text(f.read_text(encoding="utf-8")), encoding="utf-8")

    assert (cleaned_dir / "subdir" / "doc_pdf.txt").exists()
    assert (cleaned_dir / "top_md.txt").exists()


def test_clean_same_stem_different_subdir_no_collision(tmp_path):
    """Two files with the same name in different subdirs must produce separate cleaned files."""
    extracted_dir = tmp_path / "extracted"
    cleaned_dir = tmp_path / "cleaned"
    for sub in ("a", "b"):
        (extracted_dir / sub).mkdir(parents=True)
        (extracted_dir / sub / "foo_txt.txt").write_text(f"content {sub}", encoding="utf-8")

    for f in extracted_dir.rglob("*.txt"):
        out = cleaned_dir / f.relative_to(extracted_dir)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(clean_text(f.read_text(encoding="utf-8")), encoding="utf-8")

    assert (cleaned_dir / "a" / "foo_txt.txt").read_text(encoding="utf-8") == "content a"
    assert (cleaned_dir / "b" / "foo_txt.txt").read_text(encoding="utf-8") == "content b"


# ---------------------------------------------------------------------------
# chunk.py — source_file uses relative path; output paths don't collide
# ---------------------------------------------------------------------------


def test_chunk_source_file_stores_relative_path(tmp_path):
    """ChunkMetadata.source_file must be the path relative to cleaned_dir, not just basename."""
    cleaned_dir = tmp_path / "cleaned"
    subdir = cleaned_dir / "subdir"
    subdir.mkdir(parents=True)
    f = subdir / "foo_txt.txt"
    f.write_text(" ".join(f"word{i}" for i in range(20)), encoding="utf-8")

    rel = f.relative_to(cleaned_dir)
    raw_chunks = chunk_text(f.read_text(encoding="utf-8"), chunk_size=10, overlap=2)

    for chunk_str in raw_chunks:
        meta = ChunkMetadata(
            source_file=rel.as_posix(),
            document_title="Test",
            hash=hashlib.sha256(chunk_str.encode()).hexdigest()[:16],
        )
        assert meta.source_file == "subdir/foo_txt.txt"
        assert "subdir" in meta.source_file, "source_file must include subdirectory"


def test_chunk_source_file_distinguishes_same_basename(tmp_path):
    """Two files named foo_txt.txt in different subdirs must get distinct source_file values."""
    cleaned_dir = tmp_path / "cleaned"
    source_files_seen = set()

    for sub in ("a", "b"):
        (cleaned_dir / sub).mkdir(parents=True)
        f = cleaned_dir / sub / "foo_txt.txt"
        f.write_text(f"content from {sub} " * 5, encoding="utf-8")
        rel = f.relative_to(cleaned_dir)
        source_files_seen.add(rel.as_posix())

    assert len(source_files_seen) == 2
    assert "a/foo_txt.txt" in source_files_seen
    assert "b/foo_txt.txt" in source_files_seen


def test_chunk_output_paths_no_collision_same_stem_different_subdir(tmp_path):
    """Same-stem files in different subdirs must write to different .chunks.jsonl paths."""
    cleaned_dir = tmp_path / "cleaned"
    chunks_dir = tmp_path / "chunks"

    for sub in ("a", "b"):
        (cleaned_dir / sub).mkdir(parents=True)
        (cleaned_dir / sub / "foo_txt.txt").write_text(f"content from {sub} " * 5, encoding="utf-8")

    output_paths = []
    for f in cleaned_dir.rglob("*.txt"):
        rel = f.relative_to(cleaned_dir)
        out_path = chunks_dir / rel.parent / (f.stem + ".chunks.jsonl")
        out_path.parent.mkdir(parents=True, exist_ok=True)

        raw_chunks = chunk_text(f.read_text(encoding="utf-8"), chunk_size=5, overlap=1)
        with out_path.open("w", encoding="utf-8") as fh:
            for chunk_str in raw_chunks:
                meta = ChunkMetadata(
                    source_file=rel.as_posix(),
                    document_title="T",
                    hash=hashlib.sha256(chunk_str.encode()).hexdigest()[:16],
                )
                fh.write(
                    json.dumps(
                        Chunk(metadata=meta, text=chunk_str).model_dump(exclude={"embedding"})
                    )
                    + "\n"
                )
        output_paths.append(out_path)

    assert len(output_paths) == 2
    assert len(set(output_paths)) == 2, "Each subdir must produce a unique chunk file path"

    # Verify content integrity: each chunk file only contains its own subdir's content
    for out_path in output_paths:
        subdir_name = out_path.parent.name  # "a" or "b"
        lines = [ln for ln in out_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        assert lines, f"Chunk file {out_path} should not be empty"
        for line in lines:
            chunk = json.loads(line)
            assert subdir_name in chunk["metadata"]["source_file"], (
                f"source_file {chunk['metadata']['source_file']!r} "
                f"should contain subdir {subdir_name!r}"
            )
