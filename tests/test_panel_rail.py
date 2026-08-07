"""The rail replaces a tab bar that could not fit its own labels.

Measured before any of this was written: twelve tabified panels give Qt
one `QTabBar` wanting **1992 px in about 920**, so every label elided to
two or three characters. Three grouped labels need 324.
"""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QToolButton

from openchem.ui.widgets.panel_rail import GROUP_LABELS, PanelRail


def _dispose(widget) -> None:
    widget.setParent(None)
    widget.deleteLater()
    QCoreApplication.sendPostedEvents(widget, QEvent.Type.DeferredDelete)


def _rail(qapp) -> PanelRail:
    rail = PanelRail()
    rail.register("Properties", "Properties", "analysis")
    rail.register("Atom_Inspector", "Atom Inspector", "analysis")
    rail.register("Quantum_Chemistry", "Quantum Chemistry", "compute")
    rail.register("Docking", "Docking", "compute")
    rail.register("Batch", "Batch", "compare")
    return rail


def test_a_group_shows_only_its_own_panels(qapp):
    rail = _rail(qapp)
    rail._select_group("analysis")
    assert rail.visible_panel_ids() == ["Properties", "Atom_Inspector"]
    rail._select_group("compute")
    assert rail.visible_panel_ids() == ["Quantum_Chemistry", "Docking"]
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
    rail._select_group("analysis")
    rail._on_item_chosen(rail._list.item(1))
    assert seen == ["Atom_Inspector"]
    _dispose(rail)


def test_an_unknown_group_falls_back_rather_than_vanishing(qapp):
    """A plugin declaring a group this build has never heard of must still
    be reachable -- a panel nobody can open is worse than a misfiled one."""
    rail = PanelRail()
    rail.register("Weird_Plugin", "Weird Plugin", "not-a-real-group")
    rail._select_group("extensions")
    assert rail.visible_panel_ids() == ["Weird_Plugin"]
    _dispose(rail)


def test_a_favourite_is_pinned_above_every_group(qapp):
    rail = _rail(qapp)
    rail.set_favourites(["Batch"])
    rail._select_group("analysis")
    # Batch is in "compare", but pinned it shows here too -- that is what
    # pinning is for: the panel you use constantly should not need you to
    # remember which group somebody filed it under.
    assert rail.visible_panel_ids()[0] == "Batch"
    assert "Properties" in rail.visible_panel_ids()
    _dispose(rail)


def test_a_pinned_panel_is_not_listed_twice_in_its_own_group(qapp):
    rail = _rail(qapp)
    rail.set_favourites(["Properties"])
    rail._select_group("analysis")
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
    rail._select_group("analysis")

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
    buttons = rail._buttons.findChildren(QToolButton)
    assert len(buttons) == len(GROUP_LABELS)
    for button in buttons:
        assert button.text() in GROUP_LABELS.values()
        assert not button.icon().isNull(), f"{button.text()} has no icon"
    _dispose(rail)


def test_the_group_icons_actually_draw(qapp):
    """Drawn with primitives rather than shipped, so "it drew nothing" is
    a real possibility -- an icon that is blank at rail size is worse than
    no icon, because the button becomes a mystery."""
    from openchem.ui.widgets.panel_rail import _group_icon

    blank = _group_icon("analysis").pixmap(22, 22).toImage()
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

    assert rail._buttons.width() < 60, (
        f"the icon column is {rail._buttons.width()}px -- it is icons, not labels"
    )
    assert rail.sizeHint().width() < 300, rail.sizeHint().width()
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
    rail._select_group("analysis")
    assert rail._heading.text() == "Analysis"
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
        if b.property("openchem_group") == "analysis"
    )

    # "analysis" is already the group showing, so the FIRST click on it is
    # the second-click-collapses gesture.
    assert rail.current_group() == "analysis"
    assert rail.is_list_visible()
    wide = rail.sizeHint().width()

    button.click()
    assert not rail.is_list_visible()
    assert rail.sizeHint().width() < wide - 150, "collapsing gave back almost nothing"
    # Still the current group, and the button still says so -- Qt unchecks
    # a checked button in an exclusive group on click, which would
    # otherwise leave the rail claiming no group at all.
    assert rail.current_group() == "analysis"
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
