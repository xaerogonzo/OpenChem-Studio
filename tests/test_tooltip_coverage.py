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
        assert reason in {"dialog_button", "internal", "not_interactive"}
        assert instance_path
