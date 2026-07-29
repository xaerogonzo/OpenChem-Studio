from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "src" / "openchem"
FORBIDDEN = {"rdkit", "openbabel"}


def _imported_top_level_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module.split(".")[0])
    return modules


@pytest.mark.parametrize("layer", ["app", "ui"])
def test_layer_never_imports_chemistry_engines_directly(layer: str) -> None:
    offenders = []
    for path in (SRC / layer).rglob("*.py"):
        hit = _imported_top_level_modules(path) & FORBIDDEN
        if hit:
            offenders.append((str(path.relative_to(SRC)), hit))
    assert not offenders, f"UI/app files must not import RDKit/Open Babel directly: {offenders}"
