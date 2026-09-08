from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "src" / "openchem"
FORBIDDEN = {"rdkit", "openbabel"}
#: `domain/` is the layer every other one is allowed to import, so it may
#: depend on neither a chemistry toolkit NOR a GUI framework. That half
#: was documented all over the package and guarded by nothing -- a
#: `QColor` on a domain dataclass would have gone unnoticed, and a
#: presentation annotation is exactly the kind of type that attracts one.
FORBIDDEN_IN_DOMAIN = FORBIDDEN | {"PySide6"}


def _imported_top_level_modules(path: Path) -> set[str]:
    return _imported_top_level_modules_from_source(
        path.read_text(encoding="utf-8"), filename=str(path)
    )


def _imported_top_level_modules_from_source(source: str, filename: str = "<test>") -> set[str]:
    tree = ast.parse(source, filename=filename)
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module.split(".")[0])
    return modules


def _offenders(layer: str, forbidden: set[str]) -> list[tuple[str, set[str]]]:
    found = []
    for path in (SRC / layer).rglob("*.py"):
        hit = _imported_top_level_modules(path) & forbidden
        if hit:
            found.append((str(path.relative_to(SRC)), hit))
    return found


@pytest.mark.parametrize("layer", ["app", "ui"])
def test_layer_never_imports_chemistry_engines_directly(layer: str) -> None:
    offenders = _offenders(layer, FORBIDDEN)
    assert not offenders, f"UI/app files must not import RDKit/Open Babel directly: {offenders}"


def test_the_domain_layer_imports_neither_a_toolkit_nor_a_gui() -> None:
    """The rule every module under `domain/` already follows in prose.

    `RegistryExecution` types its callable's first argument as `Any` and
    says why: "domain/ stays free of RDKit/Qt imports (same layering rule
    every other module in this package follows)". Nothing checked the Qt
    half until a chart annotation -- a presentation-shaped domain type --
    made a `QColor` an easy thing to reach for.
    """
    offenders = _offenders("domain", FORBIDDEN_IN_DOMAIN)
    assert not offenders, f"domain/ must not import RDKit, Open Babel or Qt: {offenders}"


def test_the_domain_guard_would_catch_a_qt_import() -> None:
    """Asserts the guard above can say NO, rather than passing because
    `PySide6` never made it into the forbidden set."""
    assert "PySide6" in FORBIDDEN_IN_DOMAIN
    assert _imported_top_level_modules_from_source(
        "from PySide6.QtGui import QColor"
    ) & FORBIDDEN_IN_DOMAIN == {"PySide6"}
