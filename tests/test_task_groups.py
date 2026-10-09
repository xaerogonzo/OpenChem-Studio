"""Task groups: the browse layer above calculator categories.

What is guarded, and why each is a real failure rather than a tidy-up:

* a group label is a `QToolButton`-adjacent heading, so `&` (eaten as a
  mnemonic) and length (elided past 21 characters) are measured limits;
* every category the application can produce is FILED somewhere deliberate --
  a new one must not slip into the fallback group unnoticed;
* the browse key is TOTAL and decided by the visible heading, not the id;
* Properties and Results order sections with the same key;
* Find changes visibility only.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from openchem.domain import calculator_taxonomy as taxonomy
from openchem.domain.calculator import CalculatorDefinition, RegistryExecution
from openchem.domain.calculator_taxonomy import (
    CATEGORY_LABELS,
    CATEGORY_TASK_GROUP,
    FALLBACK_TASK_GROUP,
    TASK_GROUPS,
    assign_plugin_category_group,
    calculator_browse_sort_key,
    category_browse_key,
    reset_plugin_category_groups,
    task_group_of,
)
from openchem.services.calculator_registry import CalculatorRegistry


@pytest.fixture(autouse=True)
def _clean_plugin_groups():
    reset_plugin_category_groups()
    yield
    reset_plugin_category_groups()


def _definition(calculator_id, category, name=None, task_group=None):
    return CalculatorDefinition(
        calculator_id=calculator_id,
        display_name=name or calculator_id.replace("_", " ").title(),
        category=category,
        description="test calculator",
        execution=RegistryExecution(compute=lambda mol, uuid, params: None),
        task_group=task_group,
    )


# --- the vocabulary -----------------------------------------------------------


def test_every_group_label_fits_the_heading_it_is_drawn_in():
    for group, label in TASK_GROUPS.items():
        assert "&" not in label, f"{group!r}: a QToolButton eats '&' as a mnemonic"
        assert len(label) <= 21, f"{group!r}: {len(label)} characters, the measured ceiling is 21"


def test_the_fallback_group_exists_and_is_last():
    assert FALLBACK_TASK_GROUP in TASK_GROUPS
    assert list(TASK_GROUPS)[-1] == FALLBACK_TASK_GROUP


def test_the_mapping_only_names_real_groups_and_never_the_fallback():
    for category, group in CATEGORY_TASK_GROUP.items():
        assert group in TASK_GROUPS, f"{category!r} -> unknown group {group!r}"
        assert group != FALLBACK_TASK_GROUP, f"{category!r} is deliberately filed under 'other'?"


def _every_category_the_application_can_produce() -> set[str]:
    from openchem.bootstrap import build_service_container
    from openchem.chem.descriptor_providers import _DESCRIPTOR_SPECS, _SHAPE_DESCRIPTOR_SPECS

    categories = set(build_service_container().calculator_registry.categories())
    categories |= {spec[3] for spec in _DESCRIPTOR_SPECS if spec[3]}
    if _SHAPE_DESCRIPTOR_SPECS:
        categories.add("shape")
    categories |= set(CATEGORY_LABELS)
    return categories


def test_every_category_the_application_produces_is_filed_on_purpose():
    unfiled = sorted(c for c in _every_category_the_application_can_produce() if c not in CATEGORY_TASK_GROUP)
    assert not unfiled, (
        f"these categories fall to 'Other calculators' by accident: {unfiled}. "
        "Add them to CATEGORY_TASK_GROUP (and CATEGORY_LABELS if they need a heading)."
    )


# --- the sort key -------------------------------------------------------------


def test_a_group_leads_and_the_visible_heading_decides_inside_it():
    # Same group (solubility): by LABEL, "Lipophilicity" < "pKa" < "Solubility",
    # which is not the id order and not CATEGORY_ORDER.
    ordered = sorted(["solubility", "pka", "lipophilicity"], key=category_browse_key)
    assert ordered == ["lipophilicity", "pka", "solubility"]
    # A later group never precedes an earlier one whatever the labels say.
    assert sorted(["solubility", "identity"], key=category_browse_key) == ["identity", "solubility"]


def test_labels_are_compared_casefolded():
    # "pKa" would sort after "Solubility" under a case-sensitive comparison.
    assert category_browse_key("pka")[1] == "pka"
    assert category_browse_key("pka") < category_browse_key("solubility")


def test_the_calculator_key_is_total_even_for_equal_looking_names():
    a = _definition("b_id", "identity", name="Same Name")
    b = _definition("a_id", "identity", name="same name")
    assert calculator_browse_sort_key(a) != calculator_browse_sort_key(b)
    assert sorted([a, b], key=calculator_browse_sort_key)[0].calculator_id == "a_id"


def test_calculators_sort_a_to_z_inside_a_category():
    names = ["Zeta", "alpha", "Beta"]
    defs = [_definition(f"c{i}", "charge", name=n) for i, n in enumerate(names)]
    ordered = [d.display_name for d in sorted(defs, key=calculator_browse_sort_key)]
    assert ordered == ["alpha", "Beta", "Zeta"]


def test_an_unfiled_category_lands_in_other_and_orders_after_every_filed_one():
    assert task_group_of("my_tools") == FALLBACK_TASK_GROUP
    assert category_browse_key("my_tools") > category_browse_key("thermophysical")
    a, b = category_browse_key("zzz_plugin"), category_browse_key("aaa_plugin")
    assert b < a and b[0] == a[0]


# --- the plugin contract ------------------------------------------------------


def test_a_plugin_may_join_an_existing_group_for_a_category_nobody_files():
    registry = CalculatorRegistry()
    registry.register(_definition("my_calc", "my_tools", task_group="charge"))
    assert task_group_of("my_tools") == "charge"


@pytest.mark.parametrize("group", [None, "", "no_such_group", "other"])
def test_an_absent_or_unknown_plugin_group_falls_back_and_never_raises(group):
    registry = CalculatorRegistry()
    registry.register(_definition("my_calc", "my_tools", task_group=group))
    assert task_group_of("my_tools") == FALLBACK_TASK_GROUP


def test_a_plugin_cannot_move_a_category_the_application_already_files():
    assert assign_plugin_category_group("charge", "topology") is False
    assert task_group_of("charge") == "charge"


def test_a_plugins_registration_order_does_not_change_the_display_order():
    first, second = CalculatorRegistry(), CalculatorRegistry()
    for registry, order in ((first, ("a_cat", "b_cat")), (second, ("b_cat", "a_cat"))):
        reset_plugin_category_groups()
        for category in order:
            registry.register(_definition(f"{category}_calc", category))
    assert sorted(["b_cat", "a_cat"], key=category_browse_key) == ["a_cat", "b_cat"]


def test_the_taxonomy_still_imports_no_qt():
    import inspect

    source = inspect.getsource(taxonomy)
    assert "PySide6" not in source


# --- Properties --------------------------------------------------------------


def _panel(qapp, definitions):
    from openchem.chem.engine import ChemistryEngine
    from openchem.events.base import EventBus
    from openchem.ui.panels.property_panel import PropertyPanel

    registry = CalculatorRegistry()
    for definition in definitions:
        registry.register(definition)

    class _Service:
        def run_calculator(self, *args, **kwargs):  # pragma: no cover - never run here
            raise AssertionError

    return PropertyPanel(EventBus(), registry, _Service(), ChemistryEngine())


def _layout_order(panel) -> list[str]:
    """Section categories and group headers in layout order."""
    by_widget = {id(section): category for category, section in panel._sections.items()}
    headers = {id(header): f"#{group}" for group, header in panel._group_headers.items()}
    out = []
    layout = panel._sections_layout
    for index in range(layout.count()):
        widget = layout.itemAt(index).widget()
        if widget is None:
            continue
        out.append(by_widget.get(id(widget)) or headers.get(id(widget)))
    return out


def test_properties_shows_group_headers_then_sections_in_browse_order(qapp):
    panel = _panel(
        qapp,
        [
            _definition("a", "solubility"),
            _definition("b", "identity"),
            _definition("c", "charge"),
            _definition("d", "pka"),
        ],
    )
    assert _layout_order(panel) == [
        "#identity", "identity",
        "#charge", "charge",
        "#solubility", "pka", "solubility",
    ]


def test_properties_buttons_are_a_to_z_inside_a_section(qapp):
    panel = _panel(
        qapp,
        [
            _definition("z1", "charge", name="Zeta"),
            _definition("a1", "charge", name="alpha"),
            _definition("m1", "charge", name="Mid"),
        ],
    )
    rows_by_widget = {id(row): cid for cid, row in panel._calculator_rows.items()}
    layout = panel._sections["charge"]._calculators_layout
    ids = [rows_by_widget[id(layout.itemAt(i).widget())] for i in range(layout.count())]
    assert ids == ["a1", "m1", "z1"]


def test_a_group_header_shows_only_while_one_of_its_sections_does(qapp):
    panel = _panel(qapp, [_definition("a", "identity"), _definition("b", "charge")])
    panel._find_box.setText("nothing-matches-this")
    assert panel._group_headers["identity"].isHidden()
    assert panel._group_headers["charge"].isHidden()
    panel._find_box.setText("")
    assert not panel._group_headers["identity"].isHidden()


# --- Find ---------------------------------------------------------------------


def _find_panel(qapp):
    defs = [
        _definition("alpha_calc", "charge", name="Alpha Charge"),
        _definition("beta_calc", "charge", name="Beta Thing"),
        _definition("gamma_calc", "solubility", name="Gamma"),
    ]
    defs[1] = CalculatorDefinition(
        calculator_id="beta_calc",
        display_name="Beta Thing",
        category="charge",
        description="measures a dipole",
        execution=RegistryExecution(compute=lambda mol, uuid, params: None),
        tags=["polarity"],
    )
    return _panel(qapp, defs)


def _visible_rows(panel) -> set[str]:
    return {cid for cid, row in panel._calculator_rows.items() if not row.isHidden()}


def test_find_matches_name_tags_description_and_heading_ignoring_case(qapp):
    panel = _find_panel(qapp)
    for text, expected in [
        ("ALPHA", {"alpha_calc"}),
        ("polarity", {"beta_calc"}),
        ("dipole", {"beta_calc"}),
        ("solubility", {"gamma_calc"}),
        ("charge", {"alpha_calc", "beta_calc"}),
    ]:
        panel._find_box.setText(text)
        assert _visible_rows(panel) == expected, text


def test_a_whitespace_query_is_no_filter_and_no_match_says_so(qapp):
    panel = _find_panel(qapp)
    panel._find_box.setText("   ")
    assert _visible_rows(panel) == {"alpha_calc", "beta_calc", "gamma_calc"}
    assert panel._find_empty.isHidden()
    panel._find_box.setText("zzzz")
    assert _visible_rows(panel) == set()
    assert not panel._find_empty.isHidden()


def test_find_opens_matching_sections_and_restores_the_expansion_on_clear(qapp):
    panel = _find_panel(qapp)
    panel._sections["charge"].set_expanded(False)
    panel._sections["solubility"].set_expanded(False)
    panel._find_box.setText("g")  # matches Gamma, and 'charge' via the heading
    first = panel._find_snapshot
    panel._find_box.setText("gamma")  # a second query must not replace the snapshot
    assert panel._find_snapshot is first
    assert panel._sections["solubility"].is_expanded()
    panel._find_box.setText("")
    assert not panel._sections["charge"].is_expanded()
    assert not panel._sections["solubility"].is_expanded()
    assert panel._find_snapshot is None


def test_find_never_touches_ticks_or_what_a_calculator_is_offered_as(qapp):
    panel = _find_panel(qapp)
    panel._calculator_ticks["alpha_calc"].setChecked(True)
    panel._find_box.setText("gamma")
    assert panel._calculator_ticks["alpha_calc"].isChecked()
    assert panel._selected_calculator_ids() == ["alpha_calc"]
    panel._find_box.setText("")
    assert panel._selected_calculator_ids() == ["alpha_calc"]
