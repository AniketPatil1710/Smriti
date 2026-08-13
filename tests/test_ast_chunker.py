"""AST-aware chunking must align chunks to function/class boundaries and
degrade cleanly on anything it can't parse."""

from src.ingestion.ast_chunker import chunk_python_ast


def test_top_level_function_is_its_own_chunk():
    src = "import os\n\n\ndef greet(name):\n    return f'hi {name}'\n"
    pieces = chunk_python_ast(src, chunk_size=200)

    func_pieces = [p for p in pieces if "def greet" in p[0]]
    assert len(func_pieces) == 1
    text, start, end = func_pieces[0]
    assert text == "def greet(name):\n    return f'hi {name}'"
    assert start == 4
    assert end == 5


def test_small_class_stays_one_chunk():
    src = "class Widget:\n    def method(self):\n        return 1\n"
    pieces = chunk_python_ast(src, chunk_size=200)

    assert len(pieces) == 1
    assert pieces[0][0] == src.rstrip("\n")


def test_large_class_splits_into_header_and_one_chunk_per_method():
    methods = "\n\n".join(f"    def method_{i}(self):\n        return {i}" for i in range(6))
    src = f'class BigWidget:\n    """a big class"""\n\n{methods}\n'
    pieces = chunk_python_ast(src, chunk_size=50)

    assert pieces[0][0].startswith("class BigWidget:")
    method_pieces = pieces[1:]
    assert len(method_pieces) == 6
    for i, (text, _, _) in enumerate(method_pieces):
        assert text.startswith(f"def method_{i}(self):")


def test_decorated_function_keeps_its_decorator_in_the_chunk():
    src = "@staticmethod\ndef helper():\n    return 1\n"
    pieces = chunk_python_ast(src, chunk_size=200)

    assert len(pieces) == 1
    assert pieces[0][0].startswith("@staticmethod")


def test_chunks_reconstruct_original_source_by_line_number():
    src = "\n".join(
        [
            "import os",
            "",
            "def a():",
            "    return 1",
            "",
            "def b():",
            "    return 2",
        ]
    )
    lines = src.split("\n")
    for text, start, end in chunk_python_ast(src, chunk_size=200):
        reconstructed = "\n".join(lines[start - 1 : end])
        assert text == reconstructed


def test_unparseable_source_returns_none():
    assert chunk_python_ast("def broken(:\n    return\n", chunk_size=200) is None


def test_empty_source_returns_none():
    assert chunk_python_ast("", chunk_size=200) is None
