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

from openchem.ui.widgets.help_tooltip import HelpTooltip, HelpTooltipError
from openchem.ui.widgets.tooltip_inventory import (
    iter_documentable_controls,
    iter_exclusions,
)

import conftest

#: The legacy raw `setToolTip` calls present when the contract landed.
#:
#: A SET, NOT A COUNT: a bare number cannot tell "still 248" from "one
#: removed and a different one added", so a frozen count would let churn
#: through while looking stable. Keyed on `instance_path` -- the control --
#: rather than on a source location, because `file:line` moves under the
#: migration and the tooltip STRING is the very thing the migration
#: rewrites, while the control it lands on survives both.

#: Surfaces that reached zero, and may not go back.
#:
#: THE MIRROR OF `_DEBT`, and it exists because a surviving mutation said
#: it had to: removing a contract from a finished control is invisible to
#: every other guard here. `missing` cannot be a failure while 84 controls
#: still are, so "this surface is DONE" has to be recorded to be defended.
#: The debt set may only shrink; this one may only grow.


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


def test_a_line_edits_clear_button_is_qt_s_own(qapp):
    """The same hole a third time, and it escapes the prefix rule TWICE.

    `setClearButtonEnabled(True)` makes Qt build two things inside a
    `QLineEdit`, and neither carries the `qt_` object-name prefix that
    `_is_qt_internal` derives its answer from:

        the button   QToolButton with NO object name at all
        the action   QAction named `_q_qlineeditclearaction`, Qt's OTHER
                     reserved prefix, parented to the line edit itself

    So both arrived in the inventory as controls owing the user an
    explanation, which is how the help window and the receptor library
    each reported twice the controls they have.

    NOT TAKEN FROM THE WINDOW, because it cannot show this: all 13 of the
    real window's line edits are plain ones, and the only two clear
    buttons in the application are in dialogs. Built here for the same
    reason `test_an_explicitly_set_action_tooltip_still_counts_as_debt`
    is built here.

    THE SETUP IS ASSERTED. A Qt that stopped creating either child would
    leave nothing to exclude, and a test that only checked "neither is
    documentable" would pass while covering nothing.
    """
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import QLineEdit, QToolButton, QWidget

    host = QWidget()
    edit = QLineEdit(host)
    edit.setClearButtonEnabled(True)
    try:
        assert edit.findChildren(QToolButton), (
            "Qt built no clear button, so there is nothing here to exclude"
        )
        assert [a for a in edit.findChildren(QAction)], (
            "Qt built no clear action, so half this guard is testing nothing"
        )

        documentable = {c.instance_path for c in iter_documentable_controls(host)}
        excluded = {path: reason for reason, path in
                    [(e.reason, e.instance_path) for e in iter_exclusions(host)]}

        button = next(p for p in excluded if p.endswith("QToolButton"))
        action = next(p for p in excluded if p.endswith("_q_qlineeditclearaction"))
        assert excluded[button] == "internal"
        assert excluded[action] == "internal"
        assert button not in documentable and action not in documentable, (
            "Qt's own clear button is being asked for a help contract"
        )
        # And the narrow half at the smallest scale the rule has: the line
        # edit that OWNS the clear button is still a control itself.
        assert any(p.endswith("QLineEdit") for p in documentable), (
            "the line edit itself was excluded along with its clear button"
        )
    finally:
        conftest.dispose(host)


def test_the_composite_rule_does_not_swallow_the_line_edits(controls):
    """The narrow half, and the one that fails if the rule is too broad.

    "A `QLineEdit` is Qt's own composite" is one word away from "a
    `QLineEdit` is not a control", which would silently drop every search
    box, filter and text field in the application -- and would register as
    a jump in coverage rather than as a fault, exactly as the broad
    `qt_`-ancestor rule would have.

    The claim is therefore not merely "the clear buttons are gone", it is
    "and the line edits themselves are still here". Measured on the real
    window, which is a smaller number than it first looks:

        13 QLineEdits in the window
        -7 inside a QDoubleSpinBox    already excluded before this rule,
        -3 inside a QSpinBox          by the composite rule as it stood
        -1 inside a QComboBox
        = 2 standing alone            `facts.search`, `batch.property_filter`

    Those two are the whole population the window can offer, so this
    asserts them BY NAME rather than by a threshold that would read as
    stronger than it is.
    """
    found, _ = controls
    line_edits = {c.instance_path: c for c in found if c.widget_class == "QLineEdit"}
    ids = {c.help_tooltip.help_id for c in line_edits.values() if c.help_tooltip}
    assert {"facts.search", "batch.property_filter"} <= ids, (
        f"the window's stand-alone line edits are no longer documentable "
        f"({sorted(ids)}) -- the composite rule is excluding the line edits "
        "themselves and not merely the clear buttons Qt builds inside them"
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


def test_every_control_carries_a_help_contract(controls):
    """THE MIGRATION IS OVER, and this is what replaced its scaffolding.

    Two fixtures used to stand where this assertion is.
    `tooltip_migration_debt.json` recorded the 248 controls carrying a raw
    `setToolTip` when the layer landed and was allowed only to SHRINK;
    `tooltip_completed_surfaces.json` was its mirror, naming the surfaces
    that had reached zero so a finished one could not quietly fall back
    into the backlog. Both existed because `missing` could not be a
    failure while 84 controls still were -- that staging is the only
    reason the layer could be added without a red commit.

    It is zero now, so the honest invariant is the simple one: every
    documentable control in this application declares what it means. That
    is strictly stronger than a list of finished surfaces, and it needs no
    fixture to keep in step with the code.

    SAFE TO STATE BLANKET BECAUSE THE WALK IS THE APPLICATION'S OWN. The
    `controls` fixture points both plugin directories at paths that do not
    exist, so no plugin-contributed panel is ever walked and a third-party
    panel cannot fail this. Checked from the built window rather than
    assumed -- had plugins loaded, the surface list would have had to stay.

    A NEW CONTROL IS NOW RED UNTIL IT IS DOCUMENTED, deliberately. That is
    the whole point of finishing: the standard the rest of the application
    already meets applies to whatever is added next.
    """
    found, _ = controls
    undocumented = sorted(c.instance_path for c in found if c.status != "tooltip")

    assert not undocumented, (
        f"{len(undocumented)} control(s) carry no help contract. Use "
        f"`apply_help_tooltip`, never a raw setToolTip, and see "
        f"`tools/list_tooltips.py --help-id <id> --context` for the brief: "
        f"{undocumented[:5]}"
    )


def test_a_weak_but_well_formed_contract_is_ACCEPTED(controls):
    """The boundary, asserted from the side nothing else guards.

    `test_no_contract_is_a_placeholder` sets a FLOOR: a contract may not
    be a degenerate string. Nothing asserted the complement, and without
    it the floor creeps upward one `assert "A" in text` at a time until
    the guard is grading prose -- which is the one thing this layer's
    design forbids, because a test that can disagree with itself between
    runs is worse than none.

    So: a tier-3 contract that is structurally impeccable and says almost
    nothing useful must PASS. The validator's job is the shape of the
    declaration; judging whether the words explain the control is a
    reviewer's, and a human wrote every one of the 219 ids here.

    Same move as `test_a_plausible_lie_passes_the_validator_and_fails_the_chemistry`
    makes for `valid_total_declaration`, one subsystem along.
    """
    weak = HelpTooltip(
        # Structurally impeccable at tier 3 and genuinely poor: it names a
        # quantity, gestures at units and adds a caveat, and tells a
        # reader nothing they could not have guessed from the label.
        text=(
            "The measured value this control reports, expressed in its own "
            "units, which should be interpreted with appropriate care in "
            "context."
        ),
        tier=3,
        help_id="example.deliberately_weak_contract",
        topic="example",
    )

    weak.validate()  # the structural contract: must not raise

    normalised = _normalised(weak.text)
    assert normalised not in _DEGENERATE
    assert len(normalised) >= _MINIMUM_LENGTH[weak.tier], (
        "the degenerate-string floor has grown into a prose grader: it now "
        "rejects a contract that is merely UNINFORMATIVE rather than "
        "malformed. Judging whether wording explains a control is a "
        "reviewer's job, and a stochastic oracle in the suite is the "
        "failure this whole layer is designed against."
    )
