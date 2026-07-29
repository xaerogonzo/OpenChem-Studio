from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src" / "openchem" / "plugins"


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_plugin_manager_never_imports_main_window():
    modules = _imported_modules(SRC / "manager.py")
    assert not any("main_window" in m for m in modules), modules


def test_plugin_context_never_imports_main_window():
    modules = _imported_modules(SRC / "context.py")
    assert not any("main_window" in m for m in modules), modules
