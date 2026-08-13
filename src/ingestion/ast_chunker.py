"""AST-aware chunking for Python via tree-sitter.

The character splitter in chunker.py is language-aware only at the level of
preferring to break on blank lines and block keywords — it has no concept of
"this line is inside function foo", so a long function body can still be torn
in half between two chunks, with neither half making sense alone. Parsing the
real syntax tree instead lets each top-level function or class become its own
chunk, on the actual boundary a reader (or embedding model) would use.

A class much bigger than chunk_size is further split into a header chunk
(signature, docstring, class-level statements) plus one chunk per method,
so a class with many methods doesn't collapse into one unfocused blob whose
embedding is diluted across everything it contains.

Returns None on anything that isn't valid, parseable Python — chunk_file
falls back to the character splitter in that case.
"""

import tree_sitter_python as tspython
from tree_sitter import Language, Node, Parser

from src.utils.logger import get_logger

logger = get_logger(__name__)

_LANGUAGE = Language(tspython.language())
_DEF_TYPES = {"function_definition", "class_definition"}


def chunk_python_ast(text: str, chunk_size: int) -> list[tuple[str, int, int]] | None:
    """(piece_text, start_line, end_line) tuples covering `text` in source order.

    A piece may exceed `chunk_size` (a function or a single statement can be
    arbitrarily long) — chunk_file is responsible for further subdividing
    any piece that's too big to embed as one chunk.
    """
    source = text.encode("utf-8")
    try:
        tree = Parser(_LANGUAGE).parse(source)
    except Exception as e:
        logger.warning(f"tree-sitter failed to parse Python source, falling back to character split: {e}")
        return None
    if tree.root_node.has_error:
        return None

    spans: list[tuple[int, int]] = []
    pending: list[Node] = []

    def flush_pending() -> None:
        if pending:
            spans.append((pending[0].start_byte, pending[-1].end_byte))
            pending.clear()

    for child in tree.root_node.named_children:
        target = child
        if child.type == "decorated_definition":
            target = next((gc for gc in child.named_children if gc.type in _DEF_TYPES), child)

        if target.type not in _DEF_TYPES:
            pending.append(child)
            if pending[-1].end_byte - pending[0].start_byte > chunk_size:
                flush_pending()
            continue

        flush_pending()
        if target.type == "class_definition" and (child.end_byte - child.start_byte) > chunk_size * 2:
            spans.extend(_split_class(child, target, chunk_size))
        else:
            spans.append((child.start_byte, child.end_byte))

    flush_pending()
    if not spans:
        return None

    return [_locate(source, start, end) for start, end in spans]


def _split_class(outer: Node, class_node: Node, chunk_size: int) -> list[tuple[int, int]]:
    """Header (everything before the first method) as one span, each method as its own."""
    body = next((c for c in class_node.children if c.type == "block"), None)
    methods = [c for c in body.named_children if c.type in ("function_definition", "decorated_definition")] if body else []

    if not methods:
        return [(outer.start_byte, outer.end_byte)]

    header_end = methods[0].start_byte
    spans = [(outer.start_byte, header_end)]
    spans.extend((m.start_byte, m.end_byte) for m in methods)
    return spans


def _locate(source: bytes, start_byte: int, end_byte: int) -> tuple[str, int, int]:
    piece = source[start_byte:end_byte].decode("utf-8")
    start_line = source[:start_byte].count(b"\n") + 1
    end_line = source[:end_byte].count(b"\n") + 1
    if source[end_byte - 1 : end_byte] == b"\n":
        end_line -= 1
    return piece, start_line, end_line
