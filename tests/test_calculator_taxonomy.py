"""The calculator taxonomy has ONE owner, and it is not a UI panel.

`CATEGORY_ORDER`, `CATEGORY_LABELS` and the sort rule lived in
`ui/panels/property_panel.py` and were private to it. That was honest while
Properties was the only surface that grouped calculators. The Results reader
groups them too, and the obvious fix -- importing
`property_panel._CATEGORY_LABELS` -- would have left the application's
calculator taxonomy owned by the panel that is losing its presentation role.

These guards come in pairs. The wide half says the domain owns it; the narrow
half says the panel did not keep a copy, which is the failure this move exists
to prevent and the one a wide-only guard cannot see.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from openchem.domain.calculator_taxonomy import (
    CATEGORY_LABELS,
    CATEGORY_ORDER,
    category_label,
    category_sort_key,
)

SRC = Path(__file__).resolve().parent.parent / "src" / "openchem"


def test_the_panel_uses_the_domain_taxonomy_rather_than_a_copy():
    """IDENTITY, not equality -- a copied literal compares equal.

    The same move `test_the_two_sides_check_the_same_tolerance_because_it_is_one
    _constant` makes: asserting the two are `==` would pass against exactly the
    duplication being forbidden.
    """
    from openchem.ui.panels import property_panel

    assert property_panel._CATEGORY_LABELS is CATEGORY_LABELS
    assert property_panel._CATEGORY_ORDER is CATEGORY_ORDER
    assert property_panel._category_label is category_label


def test_no_ui_module_defines_a_second_category_label_table():
    """The narrow half. Nothing under `ui/` may assign a dict literal to a
    name that looks like a category-label map -- which is how the copy would
    come back, and it would pass every other guard in this file."""
    offenders: list[str] = []
    for path in (SRC / "ui").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Dict):
                continue
            for target in node.targets:
                name = getattr(target, "id", "")
                if "CATEGORY" in name.upper() and ("LABEL" in name.upper() or "ORDER" in name.upper()):
                    offenders.append(f"{path.relative_to(SRC)}::{name}")
    assert not offenders, (
        "a category table came back into ui/: " + ", ".join(offenders)
        + " -- it belongs in domain/calculator_taxonomy.py"
    )


def test_the_taxonomy_imports_nothing_from_qt_rdkit_or_ui():
    """It is a vocabulary. `tests/test_layering.py` holds this for the package
    generally; stated here too because this module is NEW in `domain/` and
    arrived from a Qt panel, which is exactly how such an import travels."""
    source = (SRC / "domain" / "calculator_taxonomy.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    forbidden = [m for m in imported if m.split(".")[0] in {"PySide6", "rdkit"}]
    forbidden += [m for m in imported if m.startswith("openchem.ui")]
    assert not forbidden, f"domain taxonomy imports {forbidden}"


def test_listed_categories_keep_the_order_the_panel_had():
    """The sort rule is EXTRACTED, not redesigned -- the Properties sections
    must not move. Listed categories in `CATEGORY_ORDER`'s order."""
    listed = sorted(CATEGORY_ORDER, key=category_sort_key)
    assert listed == list(CATEGORY_ORDER)


def test_unlisted_categories_are_appended_alphabetically():
    """And five categories this application SHIPS are unlisted --
    `thermophysical`, `energetic`, `nmr`, `docking`, `quantum_chemistry` -- so
    the alphabetical tail is the ordinary case here, not a plugin-only
    fallback. A sort that left them unordered would reshuffle five real
    sections on every rebuild."""
    unlisted = sorted(set(CATEGORY_LABELS) - set(CATEGORY_ORDER))
    assert unlisted, "fixture is degenerate: nothing is unlisted any more"
    ordered = sorted(CATEGORY_LABELS, key=category_sort_key)
    assert ordered[-len(unlisted):] == unlisted
    assert ordered[: len(CATEGORY_ORDER)] == list(CATEGORY_ORDER)


def test_a_plugin_category_sorts_deterministically_rather_than_by_arrival():
    """Two plugin categories with no registry order must still have a stable
    relative order, or the Results selector reshuffles as results land."""
    cats = ["zebra_tools", "my_tools", "admet"]
    assert sorted(cats, key=category_sort_key) == ["admet", "my_tools", "zebra_tools"]


@pytest.mark.parametrize(
    "category, expected",
    [
        ("admet", "ADMET / Regulatory"),
        # The acronym case, and how the whole fallback problem was noticed:
        # `category.title()` renders this as "Nmr".
        ("nmr", "NMR"),
        # A plugin category nobody here has named. The fallback is right for
        # this and cannot do acronyms, which is the stated limit.
        ("my_tools", "My Tools"),
        ("", "Other"),
    ],
)
def test_the_label_has_one_answer_and_one_fallback(category, expected):
    assert category_label(category) == expected
