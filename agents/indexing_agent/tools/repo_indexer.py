"""
Build a lightweight repo index after GitOps clone:
- Python AST: modules → functions/classes (line ranges, docstrings)
- Call graph (intra-file): simple AST Call-name resolution
- JSON artifacts under `<repo>/.devops_orchestra_index/`
- Optional Chroma persistent store for symbol chunks (retrieval for test/analysis prompts)
"""
from __future__ import annotations

import ast
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from shared_modules.state.devops_state import DevOpsAgentState, StatusEnum
from shared_modules.utils.logger import logger

SKIP_DIR_NAMES = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    "dist",
    "build",
    "target",
    ".devops_orchestra_index",
    ".idea",
    ".vscode",
}

MAX_FILE_BYTES = 512_000
MAX_CHUNKS_CHROMA = 400
SNIPPET_LINES = 60


def _should_skip_path(path: Path) -> bool:
    parts = set(path.parts)
    return bool(parts & SKIP_DIR_NAMES)


def _read_text_limited(path: Path) -> Optional[str]:
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _extract_python_symbols(
    rel_path: str, source: str
) -> Tuple[List[Dict[str, Any]], Dict[str, List[str]]]:
    """Returns symbol records and call_graph caller -> callees (names only, same file)."""
    symbols: List[Dict[str, Any]] = []
    call_graph: Dict[str, List[str]] = {}

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return symbols, call_graph

    class Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.scope_stack: List[str] = []

        def _qual(self, name: str) -> str:
            if self.scope_stack:
                return f"{self.scope_stack[-1]}.{name}"
            return name

        def visit_ClassDef(self, node: ast.ClassDef) -> Any:
            self.scope_stack.append(node.name)
            self.generic_visit(node)
            self.scope_stack.pop()
            return node

        def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
            self._record_function(node, async_fn=False)
            return node

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:
            self._record_function(node, async_fn=True)
            return node

        def _record_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef, async_fn: bool) -> None:
            q = self._qual(node.name)
            doc = ast.get_docstring(node) or ""
            end_lineno = getattr(node, "end_lineno", node.lineno) or node.lineno
            symbols.append(
                {
                    "path": rel_path,
                    "kind": "async_function" if async_fn else "function",
                    "name": node.name,
                    "qualified": q,
                    "lineno": node.lineno,
                    "end_lineno": end_lineno,
                    "docstring": doc[:500],
                }
            )
            callees: Set[str] = set()

            class CallVisitor(ast.NodeVisitor):
                def visit_Call(self, c: ast.Call) -> Any:
                    if isinstance(c.func, ast.Name):
                        callees.add(c.func.id)
                    elif isinstance(c.func, ast.Attribute):
                        callees.add(c.func.attr)
                    self.generic_visit(c)
                    return c

            CallVisitor().visit(node)
            if callees:
                call_graph[q] = sorted(callees)

            self.scope_stack.append(node.name)
            self.generic_visit(node)
            self.scope_stack.pop()

    Visitor().visit(tree)

    # Top-level classes
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            doc = ast.get_docstring(node) or ""
            end_lineno = getattr(node, "end_lineno", node.lineno) or node.lineno
            symbols.append(
                {
                    "path": rel_path,
                    "kind": "class",
                    "name": node.name,
                    "qualified": node.name,
                    "lineno": node.lineno,
                    "end_lineno": end_lineno,
                    "docstring": doc[:500],
                }
            )

    return symbols, call_graph


def _snippet_for_symbol(source_lines: List[str], start: int, end: int, cap: int = SNIPPET_LINES) -> str:
    """1-based inclusive line range."""
    s = max(1, start) - 1
    e = min(len(source_lines), max(end, start))
    chunk = source_lines[s : s + cap]
    return "\n".join(chunk)


def _build_retrieval_context(
    repo_root: Path,
    symbols: List[Dict[str, Any]],
    changed_files: List[str],
) -> str:
    """Plain-text bundle for LLM prompts (changed files prioritized)."""
    changed_set = {c.replace("\\", "/") for c in changed_files}
    lines_out: List[str] = []
    lines_out.append("=== Repository index (Python symbols, prioritized by git diff) ===\n")

    prioritized = [s for s in symbols if s["path"] in changed_set]
    rest = [s for s in symbols if s["path"] not in changed_set]
    ordered = prioritized[:80] + rest[:40]

    for sym in ordered:
        rel = sym["path"]
        fp = repo_root / rel
        if not fp.is_file():
            continue
        src = _read_text_limited(fp)
        if not src:
            continue
        slines = src.splitlines()
        snip = _snippet_for_symbol(slines, sym["lineno"], sym.get("end_lineno") or sym["lineno"])
        tag = "CHANGED" if rel in changed_set else "other"
        lines_out.append(f"\n--- [{tag}] {sym['qualified']} ({rel}:{sym['lineno']}) ---\n")
        if sym.get("docstring"):
            lines_out.append(f"Docstring: {sym['docstring']}\n")
        lines_out.append(snip[:8000])
        if len(snip) > 8000:
            lines_out.append("\n... [truncated] ...\n")

    return "\n".join(lines_out)[:120_000]


def build_repo_index(repo_path: str, state: DevOpsAgentState) -> None:
    """
    Populate `state.index` and write artifacts under `.devops_orchestra_index/`.
    Non-fatal: on failure sets status FAILED and logs; pipeline continues.
    """
    root = Path(repo_path)
    state.index = state.index.model_copy(update={"logs": []})
    state.index.status = StatusEnum.IN_PROGRESS

    if not root.is_dir():
        state.index.status = StatusEnum.FAILED
        state.index.logs.append(f"Not a directory: {repo_path}")
        return

    idx_dir = root / ".devops_orchestra_index"
    try:
        idx_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        state.index.status = StatusEnum.FAILED
        state.index.logs.append(f"Cannot create index dir: {e}")
        return

    state.index.index_root = str(idx_dir)
    all_symbols: List[Dict[str, Any]] = []
    merged_calls: Dict[str, List[str]] = {}
    py_files = 0

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIR_NAMES]
        for name in filenames:
            if not name.endswith(".py"):
                continue
            full = Path(dirpath) / name
            if _should_skip_path(full.relative_to(root)):
                continue
            rel = str(full.relative_to(root)).replace("\\", "/")
            text = _read_text_limited(full)
            if not text:
                continue
            py_files += 1
            syms, cg = _extract_python_symbols(rel, text)
            all_symbols.extend(syms)
            for k, v in cg.items():
                merged_calls.setdefault(k, [])
                merged_calls[k] = sorted(set(merged_calls[k]) | set(v))

    ast_map_path = idx_dir / "ast_map.json"
    call_graph_path = idx_dir / "call_graph.json"
    manifest_path = idx_dir / "manifest.json"

    try:
        ast_map_path.write_text(json.dumps(all_symbols, indent=2), encoding="utf-8")
        call_graph_path.write_text(json.dumps(merged_calls, indent=2), encoding="utf-8")
        manifest = {
            "repo_path": str(root),
            "python_files_scanned": py_files,
            "symbol_count": len(all_symbols),
            "changed_files": state.git_meta.changed_files,
        }
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    except OSError as e:
        state.index.status = StatusEnum.FAILED
        state.index.logs.append(f"Failed to write JSON artifacts: {e}")
        return

    state.index.ast_map_path = str(ast_map_path)
    state.index.call_graph_path = str(call_graph_path)
    state.index.symbol_count = len(all_symbols)
    state.index.file_count = py_files

    ctx_path = idx_dir / "retrieval_context.txt"
    try:
        ctx = _build_retrieval_context(root, all_symbols, state.git_meta.changed_files or [])
        ctx_path.write_text(ctx, encoding="utf-8")
        state.index.retrieval_context_path = str(ctx_path)
    except OSError as e:
        state.index.logs.append(f"retrieval_context write failed: {e}")

    # Optional Chroma
    chroma_dir = idx_dir / "chroma_db"
    chroma_ok = False
    try:
        import chromadb  # type: ignore
        from chromadb.config import Settings  # type: ignore

        client = chromadb.PersistentClient(
            path=str(chroma_dir),
            settings=Settings(anonymized_telemetry=False),
        )
        coll_name = f"repo_{re.sub(r'[^a-zA-Z0-9_-]+', '_', root.name)[:60]}"
        try:
            client.delete_collection(coll_name)
        except Exception:
            pass
        collection = client.create_collection(name=coll_name, metadata={"repo": root.name})

        docs: List[str] = []
        ids: List[str] = []
        metas: List[Dict[str, Any]] = []
        for i, sym in enumerate(all_symbols[:MAX_CHUNKS_CHROMA]):
            fp = root / sym["path"]
            text = _read_text_limited(fp)
            if not text:
                continue
            slines = text.splitlines()
            body = _snippet_for_symbol(slines, sym["lineno"], sym.get("end_lineno") or sym["lineno"], cap=40)
            chunk = f"{sym['qualified']}\n{sym.get('docstring') or ''}\n{body}"
            docs.append(chunk[:12_000])
            ids.append(f"sym_{i}")
            metas.append(
                {
                    "path": sym["path"],
                    "name": sym["name"],
                    "qualified": sym["qualified"],
                    "lineno": sym["lineno"],
                }
            )

        if docs:
            collection.add(ids=ids, documents=docs, metadatas=metas)
            state.index.vector_store_path = str(chroma_dir)
            state.index.embedding_backend = "chromadb"
            chroma_ok = True
            logger.info(f"[Indexing] Chroma collection {coll_name} with {len(docs)} chunks.")
    except ImportError:
        state.index.logs.append("chromadb not installed; skipped vector store.")
    except Exception as e:
        state.index.logs.append(f"Chroma indexing skipped: {e}")

    if not chroma_ok and not state.index.vector_store_path:
        state.index.embedding_backend = "none"

    # Expose compact context for downstream agents without re-reading huge files
    try:
        if ctx_path.is_file():
            state.llm_context_memory = ctx_path.read_text(encoding="utf-8", errors="replace")[:100_000]
    except OSError:
        pass

    state.index.status = StatusEnum.SUCCESS
    state.index.logs.append(
        f"Indexed {py_files} Python file(s), {len(all_symbols)} symbol(s); "
        f"chroma={'yes' if chroma_ok else 'no'}."
    )
    logger.info(f"[Indexing] Complete: {state.index.logs[-1]}")
