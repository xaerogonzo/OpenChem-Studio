"""The rail replaces a tab bar that could not fit its own labels.

Measured before any of this was written: twelve tabified panels give Qt
one `QTabBar` wanting **1992 px in about 920**, so every label elided to
two or three characters. Three grouped labels need 324.
"""

from __future__ import annotations

from PySide6.QtWidgets import QPushButton

from openchem.ui.widgets.panel_rail import GROUP_LABELS, PanelRail

import conftest


def _dispose(widget) -> None:
    conftest.dispose(widget)


def _rail(qapp) -> PanelRail:
    from openchem.ui.widgets.panel_rail import builtin_order_of

    rail = PanelRail()
    for panel_id, title, group in (
        ("Properties", "Properties", "analyze"),
        ("Atom_Inspector", "Atom Inspector", "analyze"),
        ("Quantum_Chemistry", "Quantum Chemistry", "compute"),
        ("Docking", "Docking", "compute"),
        ("Batch", "Batch", "extend"),
    ):
        rail.register(panel_id, title, group, builtin_order_of(panel_id))
    return rail


def test_a_group_shows_only_its_own_panels(qapp):
    rail = _rail(qapp)
    rail._select_group("analyze")
    assert rail.visible_panel_ids() == ["Properties", "Atom_Inspector"]
    rail._select_group("compute")
    assert rail.visible_panel_ids() == ["Docking", "Quantum_Chemistry"]
    _dispose(rail)


def test_names_are_never_truncated_because_they_are_rows_not_tabs(qapp):
    """The whole point. A row in a list is as wide as the list; a tab has
    to share one bar with every sibling, which is what elided them."""
    rail = _rail(qapp)
    rail._select_group("compute")
    labels = [rail._list.item(i).text() for i in range(rail._list.count())]
    assert "Quantum Chemistry" in labels, labels
    assert not any(label.endswith("...") for label in labels), labels
    _dispose(rail)


def test_choosing_a_panel_emits_its_id(qapp):
    rail = _rail(qapp)
    seen: list[str] = []
    rail.panel_chosen.connect(seen.append)
    rail._select_group("analyze")
    rail._on_item_chosen(rail._list.item(1))
    assert seen == ["Atom_Inspector"]
    _dispose(rail)


def test_an_unknown_group_falls_back_rather_than_vanishing(qapp):
    """A plugin declaring a group this build has never heard of must still
    be reachable -- a panel nobody can open is worse than a misfiled one."""
    rail = PanelRail()
    rail.register("Weird_Plugin", "Weird Plugin", "not-a-real-group")
    rail._select_group("extend")
    assert rail.visible_panel_ids() == ["Weird_Plugin"]
    _dispose(rail)


def test_a_favourite_is_pinned_above_every_group(qapp):
    rail = _rail(qapp)
    rail.set_favourites(["Batch"])
    rail._select_group("analyze")
    # Batch is in "compare", but pinned it shows here too -- that is what
    # pinning is for: the panel you use constantly should not need you to
    # remember which group somebody filed it under.
    assert rail.visible_panel_ids()[0] == "Batch"
    assert "Properties" in rail.visible_panel_ids()
    _dispose(rail)


def test_a_pinned_panel_is_not_listed_twice_in_its_own_group(qapp):
    rail = _rail(qapp)
    rail.set_favourites(["Properties"])
    rail._select_group("analyze")
    assert rail.visible_panel_ids().count("Properties") == 1
    _dispose(rail)


def test_toggling_a_favourite_reports_it_for_persisting(qapp):
    rail = _rail(qapp)
    seen: list[tuple[str, bool]] = []
    rail.favourite_toggled.connect(lambda pid, on: seen.append((pid, on)))
    rail.toggle_favourite("Docking")
    rail.toggle_favourite("Docking")
    assert seen == [("Docking", True), ("Docking", False)]
    assert rail.favourites() == []
    _dispose(rail)


def test_selecting_a_panel_switches_to_its_group_without_re_emitting(qapp):
    """Used when something OTHER than a click changed the front panel --
    a plugin revealing itself, or a restored layout. It must not loop back
    into the caller that just told it."""
    rail = _rail(qapp)
    seen: list[str] = []
    rail.panel_chosen.connect(seen.append)
    rail._select_group("analyze")

    rail.select_panel("Docking")

    assert rail.current_group() == "compute"
    assert seen == []
    _dispose(rail)


def test_registering_the_same_panel_twice_does_not_duplicate_it(qapp):
    """A plugin that reloads re-registers its panel."""
    rail = _rail(qapp)
    rail.register("Docking", "Docking", "compute")
    rail._select_group("compute")
    assert rail.visible_panel_ids().count("Docking") == 1
    _dispose(rail)


def test_unregistering_removes_it_from_the_list_and_the_favourites(qapp):
    rail = _rail(qapp)
    rail.set_favourites(["Docking"])
    rail.unregister("Docking")
    rail._select_group("compute")
    assert "Docking" not in rail.visible_panel_ids()
    assert rail.favourites() == []
    _dispose(rail)


def test_every_group_has_a_button_and_a_readable_name(qapp):
    rail = _rail(qapp)
    buttons = rail._buttons.findChildren(QPushButton)
    assert len(buttons) == len(GROUP_LABELS)
    for button in buttons:
        assert button.text() in GROUP_LABELS.values(), "the name is beside the icon while the list is open"
        assert not button.icon().isNull(), f"{button.text()} has no icon"
    _dispose(rail)


def test_the_group_icons_actually_draw(qapp):
    """Drawn with primitives rather than shipped, so "it drew nothing" is
    a real possibility -- an icon that is blank at rail size is worse than
    no icon, because the button becomes a mystery."""
    from openchem.ui.widgets.panel_rail import _group_icon

    blank = _group_icon("analyze").pixmap(22, 22).toImage()
    seen = set()
    for group in GROUP_LABELS:
        image = _group_icon(group).pixmap(22, 22).toImage()
        opaque = sum(
            1
            for x in range(image.width())
            for y in range(image.height())
            if image.pixelColor(x, y).alpha() > 0
        )
        assert opaque > 10, f"the {group} icon drew almost nothing ({opaque} px)"
        seen.add(image.constBits().tobytes())
    assert len(seen) == len(GROUP_LABELS), "two groups drew the same icon"
    assert blank is not None


def test_the_rail_stays_narrow_enough_to_be_worth_it(qapp):
    """The rail replaced a tab bar that wanted 1992 px. It would be a poor
    trade to hand that width to the navigation instead.

    First attempt: 412 px, because each icon carried its group name
    underneath and "Extensions" set the column. Icons only, with the group
    name as the list's heading, brought it to 264.
    """
    rail = _rail(qapp)
    rail.show()
    qapp.processEvents()

    # Labels now sit beside the icons, ABOVE the list, so they cost no width:
    # the rail is as wide as its list, and folded it is icons alone.
    assert rail.sizeHint().width() < 300, rail.sizeHint().width()
    rail.set_list_visible(False)
    assert rail.sizeHint().width() < 80, f"folded rail is {rail.sizeHint().width()}px"
    _dispose(rail)


def test_the_longest_panel_name_still_fits(qapp):
    """The whole point of the phase. "Quantum Chemistry" is the longest
    name in the app and needs 204 px measured; the list allows 230.

    If a future panel needs more than this, RENAME THE PANEL -- widening
    the list is how a 1992 px tab bar happened in the first place.
    """
    rail = _rail(qapp)
    rail.show()
    qapp.processEvents()
    rail._select_group("compute")

    metrics = rail._list.fontMetrics()
    for row in range(rail._list.count()):
        text = rail._list.item(row).text()
        assert metrics.horizontalAdvance(text) <= rail._list.maximumWidth() - 20, (
            f'"{text}" does not fit the rail -- rename the panel rather '
            "than widening the rail"
        )
    _dispose(rail)


def test_the_heading_names_the_group_the_icons_no_longer_do(qapp):
    """Icon-only buttons are only honest if the name is somewhere."""
    rail = _rail(qapp)
    rail._select_group("compute")
    assert rail._heading.text() == "Compute"
    rail._select_group("analyze")
    assert rail._heading.text() == "Analyze"
    _dispose(rail)


def test_clicking_the_active_group_again_collapses_the_rail(qapp):
    """The name list costs 230 px of a column the panels need -- with it
    open the Quantum Chemistry form truncates its own controls. A second
    click on the group already showing hands that width back."""
    rail = _rail(qapp)
    rail.show()
    qapp.processEvents()
    button = next(
        b for b in rail._button_group.buttons()
        if b.property("openchem_group") == "analyze"
    )

    # "analyze" is already the group showing, so the FIRST click on it is
    # the second-click-collapses gesture.
    assert rail.current_group() == "analyze"
    assert rail.is_list_visible()
    wide = rail.sizeHint().width()

    button.click()
    assert not rail.is_list_visible()
    assert rail.sizeHint().width() < wide - 150, "collapsing gave back almost nothing"
    # Still the current group, and the button still says so -- Qt unchecks
    # a checked button in an exclusive group on click, which would
    # otherwise leave the rail claiming no group at all.
    assert rail.current_group() == "analyze"
    assert button.isChecked()

    button.click()
    assert rail.is_list_visible(), "a third click should open it again"
    _dispose(rail)


def test_clicking_a_different_group_reopens_a_collapsed_rail(qapp):
    rail = _rail(qapp)
    rail.set_list_visible(False)

    other = next(
        b for b in rail._button_group.buttons()
        if b.property("openchem_group") == "compute"
    )
    other.click()

    assert rail.is_list_visible()
    assert rail.current_group() == "compute"
    _dispose(rail)


def test_the_panel_menu_offers_beside_and_lock_and_reports_them(qapp):
    """A left click replaces; the menu is the way to ask for the other two things, and the rail only ASKS."""
    rail = _rail(qapp)
    beside: list[str] = []
    locks: list[str] = []
    rail.panel_chosen_alongside.connect(beside.append)
    rail.panel_lock_toggled.connect(locks.append)
    menu, actions = rail.build_panel_menu("Docking")

    actions["alongside"].trigger()
    actions["lock"].trigger()
    actions["pin"].trigger()

    assert beside == ["Docking"]
    assert locks == ["Docking"]
    assert rail.favourites() == ["Docking"]
    menu.deleteLater()
    _dispose(rail)


def test_a_locked_panel_shows_its_lock_and_the_menu_offers_the_release(qapp):
    rail = _rail(qapp)
    rail._select_group("compute")
    rail.set_locked_panels({"Docking"})

    labels = [rail._list.item(r).text() for r in range(rail._list.count())]
    assert any(label.startswith("\U0001F512") and "Docking" in label for label in labels)
    assert not any(label.startswith("\U0001F512") and "Docking" not in label for label in labels)
    _menu, actions = rail.build_panel_menu("Docking")
    assert actions["lock"].text().startswith("Unlock")
    _menu, other = rail.build_panel_menu("Alignment") if "Alignment" in rail.panel_ids() else rail.build_panel_menu("Docking")

    rail.set_locked_panels(set())
    assert not any(rail._list.item(r).text().startswith("\U0001F512") for r in range(rail._list.count()))
    _dispose(rail)


# --- the three-group rail ------------------------------------------------------


def test_there_are_three_groups_each_with_a_sentence():
    from openchem.ui.widgets.panel_rail import GROUP_DESCRIPTIONS

    assert list(GROUP_LABELS) == ["analyze", "compute", "extend"]
    assert set(GROUP_DESCRIPTIONS) == set(GROUP_LABELS)
    assert all(text.strip().endswith(".") for text in GROUP_DESCRIPTIONS.values())


def test_a_folded_rail_shows_icons_only_and_an_open_one_names_the_groups(qapp):
    rail = _rail(qapp)
    buttons = rail._button_group.buttons()
    assert [b.text() for b in buttons] == list(GROUP_LABELS.values())
    rail.set_list_visible(False)
    assert [b.text() for b in buttons] == ["", "", ""]
    assert all(not b.toolTip() == "" for b in buttons), "a folded icon still says what it is"
    rail.set_list_visible(True)
    assert [b.text() for b in buttons] == list(GROUP_LABELS.values())
    _dispose(rail)


def test_the_old_five_group_ids_are_filed_not_lost(qapp):
    rail = PanelRail()
    for old, new in (("analysis", "analyze"), ("compare", "extend"), ("assist", "extend"), ("extensions", "extend")):
        rail.register(f"P_{old}", old, old)
        assert rail._panels[f"P_{old}"][1] == new
    _dispose(rail)


def test_builtin_panels_list_in_their_declared_order_then_plugins_a_to_z(qapp):
    from openchem.ui.widgets.panel_rail import BUILTIN_PANELS, builtin_order_of

    rail = PanelRail()
    # Registered in a scrambled order, plugins loaded zeta-first.
    for panel_id, group in reversed(BUILTIN_PANELS):
        rail.register(panel_id, panel_id.replace("_", " "), group, builtin_order_of(panel_id))
    rail.register("Zeta_Plugin", "Zeta Plugin", "extend")
    rail.register("Alpha_Plugin", "Alpha Plugin", "extend")
    rail._select_group("extend")
    assert rail.visible_panel_ids() == ["Compare", "Alpha_Plugin", "Zeta_Plugin"]
    rail._select_group("analyze")
    assert rail.visible_panel_ids() == [p for p, g in BUILTIN_PANELS if g == "analyze"]
    _dispose(rail)


def test_the_primary_pair_leads_analyze_and_the_rest_run_a_to_z():
    from openchem.ui.widgets.panel_rail import BUILTIN_PANELS

    analyze = [p.replace("_", " ") for p, g in BUILTIN_PANELS if g == "analyze"]
    assert analyze[:2] == ["Properties", "Results"]
    assert analyze[2:] == sorted(analyze[2:], key=str.casefold)
    for group in ("compute",):
        titles = [p.replace("_", " ") for p, g in BUILTIN_PANELS if g == group]
        assert titles == sorted(titles, key=str.casefold), group
