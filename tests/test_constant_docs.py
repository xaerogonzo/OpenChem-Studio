"""The ratchet that catches a `#:` doc comment orphaned from its constant.

The defect it exists for is on record in `chem/energetics.py`: a new constant
was inserted between a `#:` block and the constant that block was written for,
so the comment silently documented the newcomer and `ENTHALPY_NOT_SUPPLIED`
was left with none. CLAUDE.md called that unautomatable -- "Nothing catches
that; it needs a reader" -- and the claim was repeated into a plan before
anybody measured it.

**IT IS A RATCHET, NOT A MIGRATION.** `tooltip_migration_debt.json` recorded a
backlog burned down to zero, because every control in it genuinely owed the
user an explanation. This does not: `_TOKEN = "x"` wants no doc comment, and a
guard demanding one gets `#: The token.` in reply -- the degenerate string the
tooltip work spent a phase refusing. So the recorded set may only SHRINK and
nobody is expected to empty it. What must not happen is a constant FALLING
INTO it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_TOOLS = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

from constant_docs import (  # noqa: E402
    DEBT_PATH,
    Constant,
    constants_in,
    undocumented,
    uses_the_convention,
    walk,
)

#: What the walk found when this guard was written. A floor, not a target.
#:
#: `>=` rather than `==` so ordinary work does not redden the suite -- but a
#: floor at all, because a walk that collapses to zero would make every
#: assertion below vacuously true while the tree rotted. The printed count is
#: what catches drift that stays above the floor, which is the pair
#: `test_no_signal_is_connected_to_a_self_capturing_lambda` already uses.
MINIMUM_CONSTANTS_WALKED = 800


def _recorded() -> set[str]:
    return set(json.loads(DEBT_PATH.read_text(encoding="utf-8"))["constants"])


# -- the invariant --------------------------------------------------------


def test_no_constant_has_fallen_out_of_documentation() -> None:
    """THE RATCHET. A constant undocumented today and not recorded is either
    newly written without a `#:`, or -- the case this exists for -- one whose
    doc comment was taken by something inserted above it.

    Fix it by documenting the constant, not by re-recording the set. If it
    genuinely wants no documentation, regenerate with
    `python tools/constant_docs.py --record` and say so in the commit.
    """
    fallen = sorted(c.key for c in undocumented() if c.key not in _recorded())
    assert not fallen, (
        f"{len(fallen)} constant(s) lost their `#:` documentation:\n  "
        + "\n  ".join(fallen)
    )


def test_the_recorded_set_is_not_empty_and_the_walk_still_finds_things() -> None:
    """**ASSERTS ITS OWN SETUP.** A walk returning nothing satisfies the
    ratchet above perfectly, because an empty set has nothing outside the
    record. This is what makes that guard mean something."""
    every = walk()
    print(f"checked {len(every)} module-level constants")
    assert len(every) >= MINIMUM_CONSTANTS_WALKED, len(every)
    assert _recorded(), "the debt fixture is empty; the ratchet checks nothing"


def test_every_recorded_constant_names_a_real_file() -> None:
    """A fixture may only shrink, so stale entries are allowed -- but an entry
    naming a file that no longer exists means the record has drifted far
    enough to be worth regenerating."""
    root = Path(__file__).resolve().parent.parent
    missing = sorted(
        {key.split("::")[0] for key in _recorded() if not (root / key.split("::")[0]).is_file()}
    )
    assert not missing, missing


# -- the defect it was written for ---------------------------------------


ORPHANED = '''
#: How far a stated set of fractions may sum from 1.
TOLERANCE = 1e-3

#: A REAL enthalpy of zero is legitimate, so it cannot double as "unset".
#: CHNO explosives run roughly -200 to +200 kcal/mol, so this is outside
#: anything real by a wide margin.
ENTHALPY_NOT_SUPPLIED = -1000.0
'''

ORPHANING = '''
#: How far a stated set of fractions may sum from 1.
TOLERANCE = 1e-3

#: A REAL enthalpy of zero is legitimate, so it cannot double as "unset".
#: CHNO explosives run roughly -200 to +200 kcal/mol, so this is outside
#: anything real by a wide margin.
NEW_TOLERANCE = 1e-3
ENTHALPY_NOT_SUPPLIED = -1000.0
'''


def test_the_orphaning_that_motivated_this_is_detected(tmp_path: Path) -> None:
    """The exact edit, before and after. A constant inserted between a block
    and its target takes the documentation, and the constant it was written
    for arrives in the undocumented set -- which is what the ratchet sees."""
    before = {c.name: c.documented for c in constants_in(tmp_path / "m.py", ORPHANED)}
    assert before == {"TOLERANCE": True, "ENTHALPY_NOT_SUPPLIED": True}

    after = {c.name: c.documented for c in constants_in(tmp_path / "m.py", ORPHANING)}
    assert after["NEW_TOLERANCE"] is True, "the newcomer takes the comment"
    assert after["ENTHALPY_NOT_SUPPLIED"] is False, "and its target is left with none"


# -- scope, and the narrow halves ----------------------------------------


def test_a_file_that_documents_nothing_is_not_in_the_population(tmp_path: Path) -> None:
    """**THE NARROW HALF OF THE SCOPE RULE.** Without it this becomes "every
    constant in the project must be documented" -- a far larger claim than
    anybody agreed to, and one that would be answered with degenerate
    comments."""
    plain = constants_in(tmp_path / "m.py", "A = 1\nB = 2\n")
    assert [c.name for c in plain] == ["A", "B"]
    assert not uses_the_convention(plain)


def test_a_file_that_documents_one_constant_IS_in_the_population(tmp_path: Path) -> None:
    """The other half. A file using the convention is held to it, which is
    the whole mechanism."""
    mixed = constants_in(tmp_path / "m.py", "#: why\nA = 1\nB = 2\n")
    assert uses_the_convention(mixed)
    assert [(c.name, c.documented) for c in mixed] == [("A", True), ("B", False)]


def test_a_trailing_docstring_counts_as_documentation(tmp_path: Path) -> None:
    """Sphinx honours both forms and so must this, or the one constant in
    this project using the second is a false positive on correct code."""
    found = constants_in(tmp_path / "m.py", '#: why\nA = 1\n\nB = 2\n"""Also documented."""\n')
    assert [(c.name, c.documented) for c in found] == [("A", True), ("B", True)]


def test_a_tuple_assignment_counts_every_name(tmp_path: Path) -> None:
    """`chem/decay_svg.py` really declares `CELL_W, CELL_H` this way, and a
    walk that skipped tuples would silently shrink its own population --
    which reads as a coverage win rather than as a fault."""
    found = constants_in(tmp_path / "m.py", "#: sizes\nCELL_W, CELL_H = 40, 30\n")
    assert [(c.name, c.documented) for c in found] == [("CELL_W", True), ("CELL_H", True)]


def test_lower_case_module_variables_are_not_constants(tmp_path: Path) -> None:
    """A module-level `logger` is not a constant and owes no `#:`. Without
    this the population would include every module global."""
    found = constants_in(tmp_path / "m.py", "#: why\nA = 1\nlogger = get()\n")
    assert [c.name for c in found] == ["A"]


def test_a_constant_inside_a_conditional_is_not_walked(tmp_path: Path) -> None:
    """`tree.body` only. This project has none, and the restriction keeps the
    walk from having to decide what a conditionally defined constant means."""
    source = "#: why\nA = 1\nif TYPE_CHECKING:\n    B = 2\n"
    assert [c.name for c in constants_in(tmp_path / "m.py", source)] == ["A"]


def test_the_key_names_the_constant_rather_than_a_line(tmp_path: Path) -> None:
    """A `file:line` moves under any edit; the constant survives one. Same
    reason the tooltip debt fixture recorded the CONTROL."""
    constant = Constant(path="src/x.py", name="A", line=12, documented=False)
    assert constant.key == "src/x.py::A"
