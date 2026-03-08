"""Python AST summarizer using tree-sitter."""

from __future__ import annotations

from pathlib import Path
from typing import Generator

from utils.logger import logger

# Maximum characters of raw content to include as fallback
_FALLBACK_TRUNCATE = 4000


class ASTSummarizer:
    """
    Generates compact textual summaries of source files.

    Phase 1 supports Python only. Unsupported extensions fall back to
    returning the first _FALLBACK_TRUNCATE characters of raw content.
    """

    def __init__(self) -> None:
        self._python_parser = self._load_python_parser()

    # ── Public API ──────────────────────────────────────────────────────────

    def summarize(self, path: Path) -> str:
        """
        Return a compact summary of *path*.

        For Python files: extracts module docstring, classes, functions,
        and imports. For everything else: returns truncated raw content.
        """
        ext = path.suffix.lower()
        if ext == ".py" and self._python_parser is not None:
            try:
                return self._summarize_python(path)
            except Exception as e:
                logger.warning("AST summarization failed for %s: %s — using fallback", path, e)

        return self._fallback_summary(path)

    # ── Python AST ──────────────────────────────────────────────────────────

    def _load_python_parser(self):
        """Load tree-sitter Python parser.  Returns None on failure."""
        try:
            from tree_sitter import Language, Parser
            import tree_sitter_python as tspython

            PY_LANGUAGE = Language(tspython.language())
            parser = Parser(PY_LANGUAGE)
            return parser
        except Exception as e:
            logger.warning("tree-sitter Python parser unavailable: %s", e)
            return None

    def _summarize_python(self, path: Path) -> str:
        """Build a structured summary from a Python file's AST."""
        source = path.read_bytes()
        tree = self._python_parser.parse(source)
        root = tree.root_node
        src_text = source.decode("utf-8", errors="replace")

        lines: list[str] = []
        lines.append(f"# {path.name}")

        # Module-level docstring
        for child in root.children:
            if child.type == "expression_statement":
                for grandchild in child.children:
                    if grandchild.type in ("string", "concatenated_string"):
                        docstring = _node_text(src_text, grandchild)
                        lines.append(f"\n## Module docstring\n{_clean_docstring(docstring)}")
                break

        # Imports
        imports = []
        for node in _walk(root):
            if node.type in ("import_statement", "import_from_statement"):
                imports.append(_node_text(src_text, node).strip())
        if imports:
            lines.append("\n## Imports")
            lines.extend(f"  {imp}" for imp in imports[:20])  # cap at 20
            if len(imports) > 20:
                lines.append(f"  ... ({len(imports) - 20} more)")

        # Classes
        for node in _walk(root):
            if node.type == "class_definition":
                class_name = _child_text(src_text, node, "identifier")
                bases = _bases(src_text, node)
                lines.append(f"\n## class {class_name}({bases})")

                # Class docstring
                body = _child_by_type(node, "block")
                if body:
                    for stmt in body.children:
                        if stmt.type == "expression_statement":
                            for expr in stmt.children:
                                if expr.type in ("string", "concatenated_string"):
                                    lines.append(f"  \"\"\"{_clean_docstring(_node_text(src_text, expr))}\"\"\"")
                            break

                # Methods
                if body:
                    for method in body.children:
                        if method.type == "function_definition":
                            sig = _function_signature(src_text, method)
                            doc = _function_docstring(src_text, method)
                            lines.append(f"  def {sig}")
                            if doc:
                                lines.append(f"    \"\"\"{doc}\"\"\"")

        # Top-level functions (not inside classes)
        for node in root.children:
            if node.type == "function_definition":
                sig = _function_signature(src_text, node)
                doc = _function_docstring(src_text, node)
                lines.append(f"\n## def {sig}")
                if doc:
                    lines.append(f"  \"\"\"{doc}\"\"\"")

        return "\n".join(lines)

    # ── Fallback ─────────────────────────────────────────────────────────────

    def _fallback_summary(self, path: Path) -> str:
        """Return truncated raw content with a header."""
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return f"[Could not read {path.name}]"

        header = f"# {path.name} (raw, truncated)\n\n"
        if len(content) <= _FALLBACK_TRUNCATE:
            return header + content
        return header + content[:_FALLBACK_TRUNCATE] + f"\n\n... (truncated, {len(content)} chars total)"


# ── AST helpers ───────────────────────────────────────────────────────────────

def _node_text(src: str, node) -> str:
    return src[node.start_byte:node.end_byte]


def _child_text(src: str, node, child_type: str) -> str:
    for child in node.children:
        if child.type == child_type:
            return _node_text(src, child)
    return "?"


def _child_by_type(node, child_type: str):
    for child in node.children:
        if child.type == child_type:
            return child
    return None


def _walk(node) -> Generator:
    """Breadth-first walk of AST nodes."""
    yield node
    for child in node.children:
        yield from _walk(child)


def _bases(src: str, class_node) -> str:
    """Extract base class names as comma-separated string."""
    arg_list = _child_by_type(class_node, "argument_list")
    if arg_list is None:
        return ""
    parts = [
        _node_text(src, c)
        for c in arg_list.children
        if c.type not in ("(", ")", ",")
    ]
    return ", ".join(parts)


def _function_signature(src: str, func_node) -> str:
    """Return 'func_name(params) -> return_type' string."""
    name = _child_text(src, func_node, "identifier")
    params_node = _child_by_type(func_node, "parameters")
    params = _node_text(src, params_node) if params_node else "()"
    ret_node = _child_by_type(func_node, "type")
    ret = f" -> {_node_text(src, ret_node)}" if ret_node else ""
    return f"{name}{params}{ret}"


def _function_docstring(src: str, func_node) -> str | None:
    """Extract the first docstring from a function body, if present."""
    body = _child_by_type(func_node, "block")
    if body is None:
        return None
    for stmt in body.children:
        if stmt.type == "expression_statement":
            for expr in stmt.children:
                if expr.type in ("string", "concatenated_string"):
                    return _clean_docstring(_node_text(src, expr))
        break
    return None


def _clean_docstring(raw: str) -> str:
    """Strip quotes and leading/trailing whitespace from a docstring token."""
    for q in ('"""', "'''", '"', "'"):
        if raw.startswith(q) and raw.endswith(q):
            inner = raw[len(q): -len(q)]
            # Return first line only for brevity
            return inner.strip().splitlines()[0].strip() if inner.strip() else ""
    return raw.strip()
