"""Where `main_window.py` imports the menu icons from, pinned because the wrong place broke window construction."""

from __future__ import annotations

import ast
from pathlib import Path


def test_main_window_imports_the_icons_lazily_not_at_module_level():
    """A module-level import made `ShortcutRegistry.apply` raise "QAction already deleted" in every probe run (CI shard 3
    failed on it while the touched test files passed); the lazy import inside `_apply_menu_icons` was measured clean."""
    source = (Path(__file__).parent.parent / "src" / "openchem" / "app" / "main_window.py").read_text(encoding="utf-8")
    top_level = [
        node
        for node in ast.parse(source).body
        if isinstance(node, (ast.Import, ast.ImportFrom)) and "menu_icons" in ast.dump(node)
    ]
    assert top_level == []
    assert "_apply_menu_icons" in source
