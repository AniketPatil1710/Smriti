"""Canonical-language docs filtering must not silently drop content on repos without that convention."""

from pathlib import Path

from src.ingestion.file_walker import walk_repo


def _write(root: Path, rel_path: str, content: str = "hello") -> None:
    path = root / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def test_only_canonical_language_docs_indexed_when_docs_en_exists(tmp_path):
    _write(tmp_path, "docs/en/tutorial.md")
    _write(tmp_path, "docs/ja/tutorial.md")
    _write(tmp_path, "docs/de/tutorial.md")
    _write(tmp_path, "src/main.py")

    files = {f.relative_path for f in walk_repo(tmp_path)}

    assert "docs/en/tutorial.md" in files
    assert "docs/ja/tutorial.md" not in files
    assert "docs/de/tutorial.md" not in files
    assert "src/main.py" in files


def test_all_docs_indexed_when_no_canonical_docs_dir(tmp_path):
    _write(tmp_path, "docs/tutorial.md")
    _write(tmp_path, "docs/guide.md")

    files = {f.relative_path for f in walk_repo(tmp_path)}

    assert "docs/tutorial.md" in files
    assert "docs/guide.md" in files


def test_non_docs_files_unaffected_by_docs_en_convention(tmp_path):
    _write(tmp_path, "docs/en/tutorial.md")
    _write(tmp_path, "fastapi/routing.py")
    _write(tmp_path, "tests/test_routing.py")

    files = {f.relative_path for f in walk_repo(tmp_path)}

    assert "fastapi/routing.py" in files
    assert "tests/test_routing.py" in files
