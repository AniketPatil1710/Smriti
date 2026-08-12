"""Line numbers must survive chunking — getting this wrong silently breaks citations."""

from pathlib import Path

from src.ingestion.chunker import chunk_file
from src.ingestion.file_walker import SourceFile

PY_SOURCE = "\n".join(
    [
        "# module docstring",
        "import os",
        "",
        *[f"def func_{i}():" f"\n    return {i}" for i in range(40)],
        "",
        "class Trailer:",
        "    def method(self):",
        "        return 'end'",
    ]
)


def _make_source_file(tmp_path: Path, text: str, name: str = "sample.py") -> SourceFile:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return SourceFile(path=path, relative_path=name, language="python")


def test_chunks_cover_the_file_in_order(tmp_path):
    sf = _make_source_file(tmp_path, PY_SOURCE)
    chunks = chunk_file(sf, repo="testrepo", chunk_size=200, chunk_overlap=40)

    assert len(chunks) > 1  # fixture must be long enough to actually split

    starts = [c.start_line for c in chunks]
    assert starts == sorted(starts)  # chunks appear in source order


def test_line_range_reconstructs_the_chunk_text(tmp_path):
    sf = _make_source_file(tmp_path, PY_SOURCE)
    chunks = chunk_file(sf, repo="testrepo", chunk_size=200, chunk_overlap=40)
    original_lines = PY_SOURCE.split("\n")

    for chunk in chunks:
        assert 1 <= chunk.start_line <= chunk.end_line <= len(original_lines)
        reconstructed = "\n".join(original_lines[chunk.start_line - 1 : chunk.end_line])
        assert chunk.text in reconstructed


def test_chunk_metadata_is_populated(tmp_path):
    sf = _make_source_file(tmp_path, PY_SOURCE)
    chunks = chunk_file(sf, repo="testrepo", chunk_size=200, chunk_overlap=40)

    for chunk in chunks:
        assert chunk.file_path == "sample.py"
        assert chunk.language == "python"
        assert chunk.repo == "testrepo"
        assert chunk.chunk_id.startswith(f"sample.py:{chunk.start_line}-{chunk.end_line}")


def test_chunk_ids_are_unique_even_on_one_long_line(tmp_path):
    # A single very long line (e.g. a base64 blob) can be split into several
    # chunks that all report the same start/end line — chunk_id must still
    # be unique since it's used as the Chroma document id (DuplicateIDError
    # otherwise). Regression test for a real collision found in fastapi's
    # docs_src/stream_data/tutorial002_py310.py.
    long_line = "x = " + "A" * 3000
    source = f"import base64\n\n{long_line}\n\ny = 1\n"
    sf = _make_source_file(tmp_path, source)
    chunks = chunk_file(sf, repo="testrepo", chunk_size=200, chunk_overlap=40)

    ids = [c.chunk_id for c in chunks]
    assert len(ids) == len(set(ids))
    assert sum(1 for c in chunks if c.start_line == 3 and c.end_line == 3) > 1


def test_single_short_file_is_one_chunk(tmp_path):
    sf = _make_source_file(tmp_path, "x = 1\n")
    chunks = chunk_file(sf, repo="testrepo")

    assert len(chunks) == 1
    assert chunks[0].start_line == 1
    assert chunks[0].text.strip() == "x = 1"


def test_empty_file_yields_no_chunks(tmp_path):
    sf = _make_source_file(tmp_path, "   \n\n  ")
    assert chunk_file(sf, repo="testrepo") == []


def test_undecodable_file_is_skipped_not_raised(tmp_path):
    path = tmp_path / "binaryish.py"
    path.write_bytes(b"\xff\xfe\x00\x01broken")
    sf = SourceFile(path=path, relative_path="binaryish.py", language="python")

    assert chunk_file(sf, repo="testrepo") == []
