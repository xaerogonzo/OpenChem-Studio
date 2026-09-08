"""`Fact.units` belongs to `value`, and composing it must stay sound.

`Fact.value_with_units` joins `display_value` and `units` for the eight
consumers that need a fact as one string. That join is only sound while
`display_value` is a bare rendering of the same number -- and two
producers broke it in two different ways, each invisible to the other's
tests:

    report_adapter (223 facts)  the unit in BOTH fields  -> "C: 60.00 % %"
    atom_report    (1)          the same, hand-written   -> "0.76 A A"
    crystal_report (72)         a SENTENCE with a units  -> "1.934 deg,
                                claim describing only       d = 21.0517 A,
                                its first quantity          mult 2, I = 0.4
                                                            degrees 2theta"

**THE POPULATION IS THE WHOLE POINT OF THIS FILE.** The first attempt to
measure this swept `CALCULATOR_DEFINITIONS` and reported ZERO violations,
because `crystal_report` is not a registered calculator -- it reaches the
user through the crystal path and `chem/powder_xrd.py` declares no
`USER_FACING_PROVIDER` at all. A sweep that cannot reach the offender
reports a clean result and reads exactly like a passing check. So this
walks every report BUILDER, and asserts its own population size for the
same reason `_do_visual_check` logs its painted-item count: "nothing
violates the rule" and "the walk found nothing to check" read identically
in an empty findings list.
"""

from __future__ import annotations

import re
from pathlib import Path

from rdkit import Chem

from openchem.chem.atom_report import build_atom_report
from openchem.chem.bond_report import build_bond_report
from openchem.chem.cif import read_cif
from openchem.chem.crystal_report import build_crystal_report
from openchem.chem.molecule_report import build_molecule_report
from openchem.domain.report import Basis, Fact, FactCategory

#: A bare rendering of a number, which is what a fact declaring `units`
#: promises its `display_value` is. Deliberately permissive about the
#: NUMBER -- signs, exponents, thousands separators and comma-joined value
#: lists all pass -- because what is being refused is a SENTENCE, not an
#: unusual numeric format.
_BARE_VALUE = re.compile(r"^[-+]?[\d.,eE+-]+$")

_CIF_FIXTURES = Path(__file__).parent / "fixtures" / "cif"


def _every_report():
    """Every report builder a bare context can run, with its name.

    Scoped the way `test_dialog_help_contracts.py` scopes its dialogs: a
    builder needing services or a computed result is out, because handing
    this a rich enough context makes it a slow integration test that fails
    for reasons having nothing to do with units.
    """
    mol = Chem.MolFromSmiles("CC(=O)Oc1ccccc1C(=O)O")
    yield "molecule_report", build_molecule_report(mol)
    yield "atom_report", build_atom_report(mol, 0)
    yield "bond_report", build_bond_report(mol, 0)
    for path in sorted(_CIF_FIXTURES.glob("*.cif")):
        yield f"crystal_report[{path.stem}]", build_crystal_report(
            read_cif(path.read_text(encoding="utf-8"))
        )


#: Built ONCE. A crystal report is 3.6-10.6 s on these fixtures -- the
#: coordination shells, not the powder pattern -- so walking them per test
#: put a minute onto the suite for three assertions over one population.
_CACHE: list[tuple[str, object]] = []


def _unit_bearing():
    if not _CACHE:
        _CACHE.extend(
            (tag, fact)
            for tag, report in _every_report()
            for fact in report.facts
            if (fact.units or "").strip()
        )
    return _CACHE


def violation(fact) -> str:
    """Why this fact's units cannot be composed, or "" if they can.

    **A PURE PREDICATE, SEPARATE FROM THE WALK, and the split is not
    stylistic.** The two halves of the rule are exercised by different
    things: the duplication half by a real producer, and the sentence half
    by nothing at all once `crystal_report` stopped claiming a unit for
    its powder lines. Measured as a mutation -- deleting the sentence rule
    left the population walk GREEN, because no shipped fact reaches it.

    So the walk proves the shipped producers comply, and this proves the
    rule can still say no. Which is the answer this project already gives
    for a branch its own data cannot reach: an unreachable branch is a
    question about where to assert, not dead code.
    """
    text = fact.display_value.strip()
    units = (fact.units or "").strip()
    if not units:
        return ""
    if text.endswith(units):
        return f"units in both fields -> {fact.value_with_units!r}"
    if not _BARE_VALUE.match(text):
        return f"display_value is not a bare value -> {fact.value_with_units!r}"
    return ""


def test_a_fact_declaring_units_has_a_bare_value_to_put_them_on():
    """Every shipped producer complies -- the population half of the rule."""
    offenders = [
        f"{tag} {fact.label!r}: {reason}"
        for tag, fact in _unit_bearing()
        if (reason := violation(fact))
    ]
    assert not offenders, "\n".join(offenders)


def test_the_rule_refuses_both_shapes_it_was_written_for():
    """The predicate half, on CONSTRUCTED facts, because the shipped ones
    no longer reach it.

    Both arms reproduce a defect that really happened:

        "0.76 A" / "A"          `atom_report`, hand-written, one fact
        a four-quantity line    `crystal_report`, 72 powder rows, where
        with a units claim      the unit described only the FIRST number
    """
    def probe(display, units):
        return Fact(
            category=FactCategory.STRUCTURE, label="probe", value=0.76,
            display_value=display, source="probe", basis=Basis.DETERMINISTIC,
            units=units,
        )

    assert "both fields" in violation(probe("0.76 A", "A"))
    assert "not a bare value" in violation(
        probe("1.934 deg, d = 21.0517 A, mult 2, I = 0.4", "degrees 2theta")
    )
    assert violation(probe("0.76", "A")) == "", "a bare value is the ordinary case"
    assert violation(probe("anything at all", "")) == "", (
        "a fact claiming no units is making no claim to check"
    )


def test_the_walk_really_reaches_the_crystal_report():
    """THE ASSERTION ON ITS OWN SETUP, and it is why this file exists.

    72 of the 73 violations lived in the crystal report, which no sweep
    over `CALCULATOR_DEFINITIONS` can reach. If this walk ever stops
    building it -- a fixture moved, a builder gaining a required argument
    -- the guard above goes green while checking a population that
    structurally cannot contain the case it was written for.
    """
    tags = {tag for tag, _ in _unit_bearing()}
    assert any(tag.startswith("crystal_report") for tag in tags), tags
    assert any(tag == "atom_report" for tag in tags), tags


def test_the_population_is_not_empty():
    """A rule nothing is held to is not a rule.

    Measured when this landed: **21** unit-bearing facts across these
    builders -- molecular weight and density, the cell's volume and
    dimensions, a covalent radius, a bond length. It was 93 before the
    powder lines stopped claiming "degrees 2theta", which is the fix
    working rather than coverage lost: those 72 rows still carry their
    angle in `value`, they just no longer claim a unit for a sentence.

    The floor is below 21 so ordinary drift does not redden it, and far
    above zero so a walk that collapses does.
    """
    found = _unit_bearing()
    assert len(found) >= 15, f"only {len(found)} unit-bearing facts were walked"
