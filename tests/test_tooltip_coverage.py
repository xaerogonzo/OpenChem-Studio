"""Every interactive control owes the user an explanation, and the
explanation has to be a declared contract rather than a loose string.

ITERATES OVER WHAT THE WINDOW ACTUALLY BUILDS, never over a list kept
beside it -- the direction `tests/test_empty_states.py` established, and
the reason two panels once shipped with no help topic while two guards
walked the map instead of the docks.

THE GUARD CHECKS STRUCTURE AND NEVER PROSE. It cannot tell a good tooltip
from a bad one and does not try: the software guarantees the metadata
relationships, a human or an agent writes the wording. In particular there
is no LLM grading here and there must never be -- asking a model whether a
tooltip "explains the widget" makes the oracle stochastic, and a test that
can disagree with itself between runs is worse than no test.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from openchem.ui.widgets.help_tooltip import HelpTooltipError
from openchem.ui.widgets.tooltip_inventory import (
    iter_documentable_controls,
    iter_exclusions,
)

#: The legacy raw `setToolTip` calls present when the contract landed.
#:
#: A SET, NOT A COUNT: a bare number cannot tell "still 248" from "one
#: removed and a different one added", so a frozen count would let churn
#: through while looking stable. Keyed on `instance_path` -- the control --
#: rather than on a source location, because `file:line` moves under the
#: migration and the tooltip STRING is the very thing the migration
#: rewrites, while the control it lands on survives both.
_DEBT = Path(__file__).parent / "fixtures" / "tooltip_migration_debt.json"

#: Surfaces that reached zero, and may not go back.
#:
#: THE MIRROR OF `_DEBT`, and it exists because a surviving mutation said
#: it had to: removing a contract from a finished control is invisible to
#: every other guard here. `missing` cannot be a failure while 84 controls
#: still are, so "this surface is DONE" has to be recorded to be defended.
#: The debt set may only shrink; this one may only grow.
_COMPLETED = Path(__file__).parent / "fixtures" / "tooltip_completed_surfaces.json"


@dataclass(frozen=True)
class _Fact:
    """What a test needs to know about one control, with NO Qt handle.

    **The handles are dropped on purpose.** Holding 372 live Qt references
    -- widgets, `QAction`s, and `QTableWidgetItem`s, which are not even
    `QObject`s -- across a module-scoped fixture releases them all at once
    into the teardown `gc.collect()`, which is precisely the moment this
    suite has a documented history of dying in (`conftest.py`'s retainer
    and the account in CLAUDE.md). Nothing here needs a live widget: every
    assertion is about metadata, so the metadata is what the fixture keeps.
    """

    kind: str
    status: str
    instance_path: str
    widget_class: str
    object_name: str
    help_tooltip: object | None


@pytest.fixture(scope="module")
def controls(qapp, tmp_path_factory):
    """One MainWindow, walked once, reduced to plain facts.

    Module-scoped because building the window is expensive and every test
    here asks the same question of it. The window itself is NOT disposed:
    `conftest` retains MainWindows for the session deliberately, since
    collecting one corrupts the heap -- about fifteen full suite runs went
    into establishing that.
    """
    from openchem.app.main_window import MainWindow
    from openchem.app.session import SessionManager
    from openchem.app.settings import Settings
    from openchem.bootstrap import build_service_container

    tmp_path = tmp_path_factory.mktemp("tooltips")
    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(tmp_path / "no_plugins"))
    settings.set("plugins/user_directory", str(tmp_path / "no_user_plugins"))
    window = MainWindow(services, settings, SessionManager())

    facts = [
        _Fact(
            kind=c.kind,
            status=c.status,
            instance_path=c.instance_path,
            widget_class=c.widget_class,
            object_name=c.object_name,
            # A frozen dataclass of plain strings -- carries no Qt object.
            help_tooltip=c.help_tooltip,
        )
        for c in iter_documentable_controls(window)
    ]
    exclusions = [
        (e.reason, e.instance_path) for e in iter_exclusions(window)
    ]
    return facts, exclusions


def test_the_walk_finds_all_three_surfaces(controls):
    """Assert the universe is not silently empty on a surface.

    `QAction` is the one this exists for. It was missing from an early
    draft of the design, and `app/main_window.py` alone has 57 action
    sites -- so a widgets-and-headers walk would have declared the entire
    menu bar documented while covering none of it. A lazily built menu
    yields an empty list that looks exactly like full coverage, which is
    why the count is asserted rather than assumed.
    """
    found, _ = controls
    kinds = {kind: [c for c in found if c.kind == kind] for kind in ("widget", "action", "header")}

    assert len(kinds["widget"]) > 100, "the panels build far more than this"
    assert len(kinds["action"]) > 30, "the menu bar's actions are not being discovered"
    assert len(kinds["header"]) > 10, "no item-view headers found"


def test_every_contract_that_exists_is_structurally_valid(controls):
    found, _ = controls
    for control in found:
        if control.help_tooltip is None:
            continue
        try:
            control.help_tooltip.validate()
        except HelpTooltipError as exc:
            pytest.fail(f"{control.instance_path}: {exc}")


def test_one_help_id_means_exactly_one_thing(controls):
    """Uniqueness is over semantic DEFINITIONS, not runtime instances.

    Any number of controls may share a `help_id` when they mean the same
    thing -- ten generated parameter rows are one concept rendered ten
    times, and `instance_path` tells the renderings apart. What must not
    happen is one id carrying two different contracts, which would make
    every reference to it ambiguous.
    """
    found, _ = controls
    contracts: dict[str, object] = {}
    for control in found:
        tooltip = control.help_tooltip
        if tooltip is None:
            continue
        existing = contracts.setdefault(tooltip.help_id, tooltip)
        assert existing == tooltip, (
            f"help_id {tooltip.help_id!r} carries two different contracts "
            f"(at {control.instance_path})"
        )


def test_one_concept_is_not_split_across_many_help_ids(controls):
    """The mirror of the test above, and the one that was missing.

    `test_one_help_id_means_exactly_one_thing` stops two concepts sharing an
    id. Nothing stopped the reverse -- one concept given sixty ids -- and a
    mutation proved it: renaming the batch tick boxes to
    `properties.batch_selection_<calculator_id>` passed the whole file. Each
    id then had exactly one contract, so the existing guard was satisfied
    while the meaning had been shredded into sixty.

    IDENTICAL TEXT IS THE STRUCTURAL SIGNAL, and it needs no prose
    judgement: if two contracts say byte-identical things to the user, then
    either they are one concept wearing two ids, or one of them is wrong.
    Both are worth failing on.

    This is what keeps the sixty batch tick boxes sharing
    `properties.batch_selection` -- one concept rendered sixty times, with
    `instance_path` telling the renderings apart.
    """
    found, _ = controls
    by_text: dict[str, set[str]] = {}
    for control in found:
        tooltip = control.help_tooltip
        if tooltip is None:
            continue
        by_text.setdefault(tooltip.text, set()).add(tooltip.help_id)

    split = {text: ids for text, ids in by_text.items() if len(ids) > 1}
    assert not split, (
        "one concept is split across several help_ids -- they should share one:\n"
        + "\n".join(f"  {sorted(ids)} all say {text[:60]!r}..." for text, ids in split.items())
    )


def test_a_claimed_help_anchor_resolves(controls):
    """Resolved through `openchem.help`, which already owns topic discovery.

    Not re-parsed here: `tests/test_help.py` and `tools/list_tooltips.py`
    ask the same module, so there is one implementation of "what anchors
    exist" rather than three that can drift.
    """
    from openchem import help as help_docs

    found, _ = controls
    known = {topic.key for topic in help_docs.topics()}
    for control in found:
        anchor = control.help_tooltip.help_anchor if control.help_tooltip else None
        if anchor is None:
            continue
        assert anchor in known, (
            f"{control.instance_path} claims help anchor {anchor!r}, which no document defines"
        )


def test_a_claimed_source_key_is_in_the_registry(controls):
    """A UI claim citing a source must cite one that exists.

    The motivating case: a Vina scoring error was nearly shipped in a
    tooltip quoted from memory. It happened to be right, which is luck
    rather than method -- an unsourced number in a tooltip acquires the
    application's authority.
    """
    import tomllib

    found, _ = controls
    registry = Path(__file__).parent.parent / "docs" / "sources.toml"
    keys = {entry["key"] for entry in tomllib.loads(registry.read_text(encoding="utf-8"))["source"]}
    for control in found:
        key = control.help_tooltip.source_key if control.help_tooltip else None
        if key is None:
            continue
        assert key in keys, f"{control.instance_path} cites unknown source {key!r}"


#: Rejected outright. A FLOOR, NOT A QUALITY ORACLE -- and what is
#: deliberately excluded matters as much as what is here: no label-overlap
#: detection, no noun/verb heuristics, no word-count rules, no
#: "must contain units" regexes, no LLM grading. Every one of those turns a
#: useful structural check into a brittle pseudo-language-model that is
#: satisfied by nonsense like "Maximum poses. Higher values."
_DEGENERATE = frozenset({
    "options", "settings", "choose a value", "select a value",
    "input", "value", "details", "help",
})

#: Tiers 2 and 3 must say more than a label restated. Conservative on
#: purpose: long enough to exclude "Poses." and short enough not to become
#: a writing-style rule.
_MINIMUM_LENGTH = {2: 40, 3: 80}


def _normalised(text: str) -> str:
    return " ".join(text.casefold().split()).rstrip(".")


def test_no_contract_is_a_placeholder(controls):
    found, _ = controls
    for control in found:
        tooltip = control.help_tooltip
        if tooltip is None:
            continue
        normalised = _normalised(tooltip.text)
        assert normalised not in _DEGENERATE, (
            f"{control.instance_path} ({tooltip.help_id}) has placeholder text {tooltip.text!r}"
        )
        floor = _MINIMUM_LENGTH.get(tooltip.tier)
        if floor is not None:
            assert len(normalised) >= floor, (
                f"{tooltip.help_id} is tier {tooltip.tier} but only {len(normalised)} characters: "
                f"{tooltip.text!r}"
            )


def test_the_migration_debt_never_grows(controls):
    """Raw `setToolTip` with no contract is recorded debt, not a failure --
    for now.

    THE STAGING IS THE POINT. 248 controls carried a legacy tooltip when
    this landed, so a guard that failed on "tooltip without contract" would
    have made this commit red and forbidden the incremental migration it
    exists to enable. So: the recorded set may SHRINK freely and may not
    grow. A new bare `setToolTip` fails here immediately while the existing
    debt is burned down, and the day the set is empty this test and the
    fixture go with it.
    """
    found, _ = controls
    recorded = set(json.loads(_DEBT.read_text(encoding="utf-8"))["instance_paths"])
    current = {c.instance_path for c in found if c.status == "legacy_tooltip"}

    added = current - recorded
    assert not added, (
        f"{len(added)} control(s) gained a raw setToolTip with no help contract. "
        f"Use apply_help_tooltip instead: {sorted(added)[:5]}"
    )


def test_the_cli_and_this_guard_share_one_discovery_layer():
    """`tools/list_tooltips.py` must not grow its own idea of the universe.

    Checked structurally rather than by comparing two counts, because two
    counts agreeing today says nothing about tomorrow: what matters is that
    the tool calls `iter_documentable_controls` and defines no traversal of
    its own. A second walker is the failure this whole module exists to
    prevent -- the same class as `is_stripped_residue`, `filter_altlocs`
    and the two privately written display gates.
    """
    import ast

    source = (Path(__file__).parent.parent / "tools" / "list_tooltips.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)

    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and (node.module or "").endswith("tooltip_inventory")
        for alias in node.names
    }
    assert "iter_documentable_controls" in imported, (
        "the CLI must consume the shared discovery layer"
    )

    called = {
        node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
    }
    assert not {"findChildren", "children"} & called, (
        "the CLI is walking the widget tree itself -- discovery has forked"
    )


def test_every_exclusion_records_why(controls):
    """"Why isn't this button covered?" must have a deterministic answer.

    Exclusions are derived -- a control inside a `QDialogButtonBox`, or one
    Qt built inside a composite, or one Qt named with its own `qt_` prefix
    -- never a list of widget names, which is what rotted
    `inapplicable_calculators` into 27 wrong entries.
    """
    _, exclusions = controls
    assert exclusions, "nothing was excluded, which means the reasons are untested"
    for reason, instance_path in exclusions:
        assert reason in {
            "dialog_button",
            "internal",
            "not_interactive",
            # A menu TITLE: its explanation is the menu it opens, and every
            # entry under it still owes a contract of its own.
            "opens_a_menu",
        }
        assert instance_path


def test_a_tab_bars_scroll_buttons_are_qt_s_own(controls):
    """`_is_qt_internal` reads the widget's OWN name, and a `QTabBar` breaks
    its own convention for the two buttons it builds.

    Qt reserves the `qt_` object-name prefix for its internal scaffolding,
    and the tab bar itself honours it (`qt_tabwidget_tabbar`). The two
    overflow buttons it creates underneath do NOT -- they are named
    `ScrollLeftButton` and `ScrollRightButton` -- so the prefix rule
    excluded the parent and admitted the children, and three tab widgets
    put six Qt scroll arrows into the inventory as controls owing the user
    an explanation.

    THE SETUP IS ASSERTED. If the application ever stops building a
    `QTabWidget`, or Qt stops creating these buttons, there is nothing to
    exclude and a test that merely checked "none are documentable" would
    pass while covering nothing.
    """
    found, exclusions = controls

    excluded_scroll = [
        (reason, path)
        for reason, path in exclusions
        if path.rsplit("/", 1)[-1] in {"ScrollLeftButton", "ScrollRightButton"}
    ]
    assert excluded_scroll, (
        "no tab-bar scroll button was excluded -- either the window builds no "
        "QTabWidget any more, or Qt stopped creating them, and this guard is "
        "no longer testing anything"
    )
    assert all(reason == "internal" for reason, _ in excluded_scroll)

    documentable = {
        c.instance_path
        for c in found
        if c.instance_path.rsplit("/", 1)[-1]
        in {"ScrollLeftButton", "ScrollRightButton"}
    }
    assert not documentable, (
        f"{len(documentable)} Qt tab-bar scroll button(s) are being asked for a "
        f"help contract: {sorted(documentable)[:3]}"
    )


def test_the_composite_rule_does_not_swallow_the_panels(controls):
    """The narrow rule, guarded against the tempting broad one.

    "Anything under a `qt_`-named ancestor is Qt's own" is the principled
    -sounding generalisation of the test above, and it is catastrophic:
    every panel in this application lives inside a `QScrollArea`, whose
    viewport is named `qt_scrollarea_viewport`. Measured when the tab-bar
    rule was written, that version excluded **200 of 243 widgets** -- and
    it would have registered as a large jump in coverage rather than as a
    fault.

    So the claim is not merely "the scroll buttons are gone", it is "and
    the panels are still here". A control inside a scroll-area viewport
    must remain documentable.
    """
    found, _ = controls
    inside_a_viewport = [
        c for c in found if "qt_scrollarea_viewport" in c.instance_path
    ]
    assert len(inside_a_viewport) > 100, (
        f"only {len(inside_a_viewport)} controls inside a scroll area are "
        "documentable -- an exclusion is swallowing the panels themselves"
    )
def test_a_menu_actions_synthesised_tooltip_is_not_help(controls):
    """`QAction.toolTip()` NEVER RETURNS EMPTY, and the queue believed it.

    With no tooltip ever set, Qt answers `toolTip()` with the action's own
    `text()` minus the `&` accelerators and the `...`. So a plain
    "does it have a non-empty tooltip" test reports every menu action as
    carrying help, and what it carries is the label the user just read.

    Measured when the menu-bar batch was picked up: all 83 actions were
    classified `legacy_tooltip` and NOT ONE held a human-written string.
    That overstated the migration debt by 83 and hid 83 controls from
    `--missing`, which is the queue the migration is worked from.

    THE SETUP IS ASSERTED. If Qt ever stops synthesising, or the window
    stops building a menu bar, there is nothing to misclassify and a test
    that only checked "no action is legacy" would pass while covering
    nothing.
    """
    from PySide6.QtGui import QAction

    probe = QAction("&Open Project...")
    assert probe.toolTip() == "Open Project", (
        f"Qt no longer synthesises a QAction tooltip from its text "
        f"(got {probe.toolTip()!r}) -- this guard is testing nothing"
    )

    found, _ = controls
    actions = [c for c in found if c.widget_class == "QAction"]
    assert actions, "the window built no QAction, so nothing here is tested"

    echoed = [c for c in actions if c.status == "legacy_tooltip"]
    assert not echoed, (
        f"{len(echoed)} menu action(s) counted as documented on the strength of "
        f"a tooltip Qt wrote from their own label: "
        f"{sorted(c.instance_path for c in echoed)[:5]}"
    )


def test_an_explicitly_set_action_tooltip_still_counts_as_debt():
    """The control, and the half that makes the rule narrow.

    "A QAction is never legacy_tooltip" would satisfy the test above and be
    wrong: an action somebody wrote a real tooltip for is exactly the debt
    the fixture exists to burn down, and silently dropping it would make
    the migration look finished early.

    Asserted on the predicate rather than through the window, because no
    action in the application carries an explicit tooltip today -- so the
    end-to-end route cannot tell a narrow rule from a blanket one, and a
    branch nothing can enter is a question about where to assert.
    """
    from PySide6.QtGui import QAction

    from openchem.ui.widgets.tooltip_inventory import _status

    synthesised = QAction("&Open Project...")
    assert _status(synthesised) == "missing"

    explicit = QAction("&Open Project...")
    explicit.setToolTip("Opens a saved .ocsproj and replaces the current session.")
    assert _status(explicit) == "legacy_tooltip", (
        "a hand-written action tooltip must still count as migration debt"
    )

    # And the degenerate case both ways: a tooltip set to exactly what Qt
    # would have synthesised reads as absent, which is the right answer --
    # restating the label is not an explanation.
    restates_label = QAction("&Open Project...")
    restates_label.setToolTip("Open Project")
    assert _status(restates_label) == "missing"
def test_a_menu_title_is_explained_by_its_menu(controls):
    """`QMenu.menuAction()` is a `QAction` and lands in the same walk.

    So `&File`, `Copy Structure As` and `2D Structure Display` all arrived
    asking for a contract, and there is nothing honest to write on one: a
    title's meaning is the list of entries under it, each of which carries
    its own. Thirteen contracts reading "Opens the File menu" is the
    restate-the-label degeneracy `test_no_contract_is_a_placeholder`
    refuses one layer down.

    THE SETUP IS ASSERTED -- a window that stops building menus would make
    a bare "no title is documentable" check pass while covering nothing.
    """
    _, exclusions = controls
    titles = [path for reason, path in exclusions if reason == "opens_a_menu"]
    assert len(titles) >= 5, (
        f"only {len(titles)} menu title(s) were excluded -- the window may no "
        "longer build a menu bar, and this guard would then test nothing"
    )
    # The menu bar's own top-level titles are the unmistakable ones.
    assert any(path.endswith("&File") for path in titles), titles[:8]


def test_menu_entries_are_not_exempted_along_with_their_titles(controls):
    """The narrow half, and the one worth mutating.

    "A QAction under a menu needs no contract" would satisfy the test above
    and would silently exempt the entire menu bar -- 71 real commands --
    while reading as a large jump in coverage. The exemption is for the
    action that OPENS a menu and for nothing inside one.

    Checked on entries whose contracts are the point of the batch: a
    command that does something must still be in the universe.
    """
    found, _ = controls
    actions = {c.instance_path.rsplit("/", 1)[-1] for c in found if c.kind == "action"}
    for entry in ("New Project", "Exit", "Paste Structure", "SMILES"):
        assert entry in actions, (
            f"{entry!r} is a menu COMMAND and has fallen out of the documentable "
            "universe -- the menu-title exemption is too broad"
        )


def test_the_menu_title_exemption_is_derived_from_qt(controls):
    """Derived, not a list of menu names.

    A name list is the rot `inapplicable_calculators` is this repository's
    standing warning about. Asserted on the predicate: an action carrying a
    menu is exempt and an otherwise identical one is not, so the rule
    cannot be satisfied by a hard-coded set of titles.
    """
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import QMenu

    from openchem.ui.widgets.tooltip_inventory import _action_opens_a_menu

    plain = QAction("Copy Structure As")
    assert not _action_opens_a_menu(plain)

    menu = QMenu("Copy Structure As")
    assert _action_opens_a_menu(menu.menuAction())
def test_a_menu_entrys_contract_is_actually_shown(qapp, tmp_path_factory):
    """A rendering that never renders does not honour the contract.

    `QMenu.toolTipsVisible()` is FALSE by default, so a `QAction` can carry
    a perfectly good tooltip that Qt simply never draws. Measured on the
    real window when the menu contracts landed: all seven top-level menus
    answered False, which would have left 71 freshly written contracts
    documented, queryable, passing every coverage guard -- and invisible.

    Its own window rather than the shared `controls` fixture, because this
    asks about the QMenus rather than about the walked controls, and the
    fixture deliberately drops every Qt handle.
    """
    from PySide6.QtWidgets import QMenu

    from openchem.app.main_window import MainWindow
    from openchem.app.session import SessionManager
    from openchem.app.settings import Settings
    from openchem.bootstrap import build_service_container

    tmp_path = tmp_path_factory.mktemp("menu_tooltips")
    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(tmp_path / "no_plugins"))
    settings.set("plugins/user_directory", str(tmp_path / "no_user_plugins"))
    window = MainWindow(services, settings, SessionManager())

    menus = window.menuBar().findChildren(QMenu)
    assert len(menus) >= 5, (
        f"the window built {len(menus)} menu(s) -- too few for this guard to be "
        "testing anything"
    )
    hidden = [m.title() for m in menus if not m.toolTipsVisible()]
    assert not hidden, (
        f"{len(hidden)} menu(s) will not show their entries' tooltips, so the "
        f"contracts on them cannot reach a user: {hidden}"
    )
def test_a_finished_surface_does_not_regress(controls):
    """A contract removed from a completed surface must fail here.

    The coverage guard cannot fail on `missing` -- that is the whole
    staged-migration design, and 84 controls are still missing. So
    deleting `apply_help_tooltip` from a documented control simply moves
    it back into the backlog and nothing notices. A mutation removing the
    contract from File > New Project survived every other test in this
    file.

    What is recorded is the SURFACE rather than the control, so a new
    menu entry or a new control on a finished panel is held to the
    standard the rest of that surface already meets -- which is the
    property a list of individual controls would not have.
    """
    found, _ = controls
    completed = json.loads(_COMPLETED.read_text(encoding="utf-8"))

    for kind in completed["by_kind"]:
        undocumented = [
            c.instance_path for c in found if c.kind == kind and c.status != "tooltip"
        ]
        assert not undocumented, (
            f"the {kind!r} surface was complete and {len(undocumented)} control(s) "
            f"have lost their contract: {sorted(undocumented)[:5]}"
        )

    for fragment in completed["by_instance_path_fragment"]:
        on_surface = [c for c in found if fragment in c.instance_path]
        assert on_surface, (
            f"{fragment!r} matches no control at all -- the surface was renamed "
            "and this guard is testing nothing"
        )
        undocumented = [c.instance_path for c in on_surface if c.status != "tooltip"]
        assert not undocumented, (
            f"{fragment} was complete and {len(undocumented)} control(s) have lost "
            f"their contract: {sorted(undocumented)[:5]}"
        )
