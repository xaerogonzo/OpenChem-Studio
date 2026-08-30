"""Quark arithmetic, what it proves, and the boundary it must not cross.

**THIS FEATURE IS A DELIBERATE REVERSAL**, and half of this file exists to
hold the boundary that reversal was made on. `docs/ARCHITECTURE.md`
recorded a DECISION against building a particle editor because nothing
downstream consumes a particle; that is still true, the editor was built
anyway because it was wanted, and what keeps the entry honest is that the
leaf really is a leaf. See `test_the_particle_editor_is_a_leaf` and the
three guards under it.

The science half rests on one identity that cannot be argued with:

    Q = I3 + (B + S + C + B' + T) / 2

which holds per quark and is additive on both sides, so it is a checksum
on the six-row flavour table rather than a test of the composition logic.
That is exactly what a hand-entered table needs.
"""

from __future__ import annotations

import ast
from fractions import Fraction
from pathlib import Path

import pytest

from openchem.domain.particle import (
    PDG_STATES,
    QUARK_FLAVOUR_NUMBERS,
    Composition,
    Flavour,
    Quark,
    Verdict,
    classify,
    derive,
    identify,
)

import conftest

_SRC = Path(__file__).resolve().parent.parent / "src" / "openchem"


def _q(letter: str) -> Quark:
    return Quark(Flavour(letter))


def _qbar(letter: str) -> Quark:
    return Quark(Flavour(letter), anti=True)


def _content(spec: str) -> tuple[Quark, ...]:
    """`"u u d"` -> three quarks; `"u dbar"` -> a meson."""
    out = []
    for token in spec.split():
        if token.endswith("bar"):
            out.append(_qbar(token[:-3]))
        else:
            out.append(_q(token))
    return tuple(out)


# --- the flavour table ------------------------------------------------------


@pytest.mark.parametrize("flavour", list(Flavour), ids=lambda f: f.value)
def test_gell_mann_nishijima_holds_for_every_quark(flavour):
    """**THE CHECKSUM ON A HAND-ENTERED TABLE.**

    Six rows is small enough to type and exactly large enough for a sign
    to go unnoticed. This catches a wrong sign or a mistyped third in any
    flavour, and the signs it protects are the classic traps: the
    negatively-charged quarks carry NEGATIVE flavour numbers, so s has
    S = -1 and b has B' = -1 while c has C = +1 and t has T = +1.
    """
    numbers = QUARK_FLAVOUR_NUMBERS[flavour]
    hypercharge = (
        numbers.baryon_number
        + numbers.strangeness
        + numbers.charm
        + numbers.bottomness
        + numbers.topness
    )
    assert numbers.charge == numbers.isospin_3 + hypercharge / 2


def test_the_strange_quark_carries_MINUS_one_strangeness():
    """Asserted by name because it is the sign everybody gets wrong, and
    because the PDG's own section headers are what settled it here:
    "Lambda BARYONS (S = -1, I = 0)" sits above "Lambda0 = uds", and
    "Omega BARYONS (S = -3, I = 0)" above "Omega- = sss"."""
    assert QUARK_FLAVOUR_NUMBERS[Flavour.STRANGE].strangeness == -1
    assert QUARK_FLAVOUR_NUMBERS[Flavour.BOTTOM].bottomness == -1
    assert QUARK_FLAVOUR_NUMBERS[Flavour.CHARM].charm == +1
    assert QUARK_FLAVOUR_NUMBERS[Flavour.TOP].topness == +1


def test_charges_are_exact_thirds_and_not_floats():
    """A proton is 2/3 + 2/3 - 1/3, which in binary floating point is
    0.9999999999999999 -- so an equality test against +1 fails and a
    tolerance would be a tolerance on a number that is exactly an
    integer."""
    charge = derive(_content("u u d")).charge
    assert isinstance(charge, Fraction)
    assert charge == 1


def test_an_antiquark_negates_every_number_it_carries():
    for flavour in Flavour:
        quark = QUARK_FLAVOUR_NUMBERS[flavour]
        anti = Quark(flavour, anti=True).numbers
        assert anti.charge == -quark.charge
        assert anti.isospin_3 == -quark.isospin_3
        assert anti.strangeness == -quark.strangeness
        assert anti.baryon_number == -quark.baryon_number


# --- the shipped states -----------------------------------------------------


@pytest.mark.parametrize("state", PDG_STATES, ids=lambda s: s.symbol)
def test_every_shipped_state_obeys_gell_mann_nishijima(state):
    assert state.derived.obeys_gell_mann_nishijima


@pytest.mark.parametrize(
    "symbol,charge,baryon,strangeness",
    [
        ("p", 1, 1, 0),
        ("n", 0, 1, 0),
        ("Lambda0", 0, 1, -1),
        ("Sigma+", 1, 1, -1),
        ("Sigma-", -1, 1, -1),
        ("Xi0", 0, 1, -2),
        ("Xi-", -1, 1, -2),
        ("Omega-", -1, 1, -3),
        ("pi+", 1, 0, 0),
        ("K+", 1, 0, 1),
        ("K-", -1, 0, -1),
    ],
)
def test_the_derived_numbers_are_the_ones_the_physics_says(
    symbol, charge, baryon, strangeness
):
    """**DERIVED, NEVER STORED.** No `ParticleState` carries a charge, so
    these come from summing the quark content the PDG prints beside the
    name. A table that stored its own charges could not be checked
    against anything, and this is the check."""
    state = next(s for s in PDG_STATES if s.symbol == symbol)
    numbers = state.derived
    assert numbers.charge == charge
    assert numbers.baryon_number == baryon
    assert numbers.strangeness == strangeness


def test_no_state_stores_a_quantum_number_it_could_derive():
    """The structural half of the rule above.

    If a row ever grew a `charge` field the test above would still pass
    while asserting nothing about the arithmetic -- it would be reading
    the stored value back. This is what stops that.
    """
    forbidden = {"charge", "baryon_number", "strangeness", "charm", "isospin_3"}
    fields = set(PDG_STATES[0].__dataclass_fields__)
    assert not (fields & forbidden), f"a state stores {sorted(fields & forbidden)}"
    # `isospin` (TOTAL) is stored deliberately -- it is precisely the one
    # that is NOT a sum over the content. See the Lambda/Sigma0 case.
    assert "isospin" in fields


def test_the_omega_minus_is_three_strange_quarks():
    omega = next(s for s in PDG_STATES if s.symbol == "Omega-")
    assert omega.content_symbol == "s s s"
    assert omega.derived.strangeness == -3
    assert omega.derived.charge == -1


# --- classification ---------------------------------------------------------


@pytest.mark.parametrize(
    "spec,expected",
    [
        ("u u d", Composition.BARYON),
        ("s s s", Composition.BARYON),
        ("ubar ubar dbar", Composition.ANTIBARYON),
        ("u dbar", Composition.MESON),
        ("u d", Composition.INVALID),
        ("u ubar d", Composition.INVALID),
        ("u", Composition.INVALID),
        ("u u d s", Composition.INVALID),
    ],
)
def test_a_composition_is_a_baryon_a_meson_or_neither(spec, expected):
    assert classify(_content(spec)) is expected


def test_an_exotic_hadron_is_refused_without_being_called_impossible():
    """Tetraquarks and pentaquarks are real. The refusal says "not a
    baryon or a meson" and names the scope, rather than implying the
    state does not exist."""
    result = identify(_content("u u d d sbar"))
    assert result.verdict is Verdict.INVALID
    assert "out of scope" in result.reason
    assert "not a particle" not in result.reason


# --- identification ---------------------------------------------------------


def test_a_proton_is_identified():
    result = identify(_content("u u d"))
    assert result.verdict is Verdict.IDENTIFIED
    assert result.state.name == "proton"
    assert result.state.mass_mev == pytest.approx(938.27208816)


def test_quark_order_does_not_change_the_answer():
    """`udu` is `uud`. Without this the editor would answer differently
    depending on which slot a user filled first."""
    assert identify(_content("u d u")).state.name == "proton"
    assert identify(_content("d u u")).state.name == "proton"


def test_uds_is_valid_and_NOT_identified_and_names_both_candidates():
    """**THE CASE THE WHOLE DESIGN IS BUILT AROUND, and the PDG supplies
    it.** Lambda and Sigma zero are both `uds` with identical charge,
    baryon number, strangeness and third isospin component. They differ in
    TOTAL isospin, which is not a sum over quark content -- so the derived
    numbers provably cannot choose, and choosing anyway would be the
    editor inventing an identity.
    """
    result = identify(_content("u d s"))
    assert result.verdict is Verdict.VALID_UNIDENTIFIED
    assert result.state is None
    assert {c.name for c in result.candidates} == {"Lambda", "Sigma zero"}
    assert "TOTAL isospin" in result.reason


def test_the_two_uds_states_really_do_agree_on_every_derived_number():
    """The setup assertion for the test above.

    If Lambda and Sigma zero differed in any additive number, the
    ambiguity would be an artefact of matching on content rather than a
    fact about the physics, and the reason string would be wrong.
    """
    lam = next(s for s in PDG_STATES if s.symbol == "Lambda0")
    sig = next(s for s in PDG_STATES if s.symbol == "Sigma0")
    assert lam.derived == sig.derived
    # ...and they are genuinely different particles.
    assert lam.isospin != sig.isospin
    assert lam.mass_mev != sig.mass_mev


def test_a_quark_with_its_own_antiquark_is_not_named():
    """**THE PDG'S OWN POSITION, NOT A LIMITATION HERE.** Its light
    unflavoured section is headed by the statement that pi0 is
    `(u ubar - d dbar)/sqrt(2)` and the I = 0 mesons are
    `c1(u ubar + d dbar) + c2(s sbar)`. Those are superpositions, so no
    single pair names one.
    """
    for spec in ("u ubar", "d dbar", "s sbar"):
        result = identify(_content(spec))
        assert result.verdict is Verdict.VALID_UNIDENTIFIED, spec
        assert result.candidates == ()
        assert "superposition" in result.reason or "mixture" in result.reason


def test_a_valid_state_this_table_does_not_carry_says_so_without_denying_it():
    """An antiproton is a real particle and is not in the shipped set. The
    reason must not read as "no such particle exists"."""
    result = identify(_content("ubar ubar dbar"))
    assert result.verdict is Verdict.VALID_UNIDENTIFIED
    assert result.composition is Composition.ANTIBARYON
    assert "not a claim that no such particle exists" in result.reason


def test_an_ambiguous_match_is_never_promoted_to_an_identity():
    """`Identification.state` answers only for a single candidate.

    Asserted on the property rather than through a composition, because
    the shipped table happens to contain no case where several rows share
    a content APART from Lambda/Sigma0 -- so an end-to-end test covers
    one instance of a rule that must hold for all of them.
    """
    ambiguous = identify(_content("u d s"))
    assert len(ambiguous.candidates) == 2
    assert ambiguous.state is None
    single = identify(_content("u u d"))
    assert len(single.candidates) == 1
    assert single.state is not None


def test_identification_matches_on_CONTENT_and_not_on_a_number_tuple():
    """"Known particle" must not become "search by quantum numbers and
    report whatever comes back".

    Asserted on the source, because the shipped table contains no pair
    whose derived numbers coincide while their contents differ -- so
    there is no composition that discriminates the two implementations
    end to end. This is the project's own "an unreachable branch is a
    question about where to assert" rule: the claim is about how the
    lookup is written, so the lookup is what is checked.
    """
    source = (_SRC / "domain" / "particle.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    function = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "identify"
    )
    called = {
        node.func.id
        for node in ast.walk(function)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "_same_content" in called, "identify no longer matches on quark content"


# --- the boundary the reversal was made on ----------------------------------


def test_the_particle_editor_is_a_leaf():
    """**`domain/particle.py` IMPORTS NOTHING FROM `openchem.chem`.**

    This is the guard `docs/ARCHITECTURE.md` points at. The DECISION
    against building this said every layer below the UI is built on atoms
    as the smallest unit and nothing consumes a particle; that is still
    true, and the reversal is honest only while the new module stays on
    its own side of the line.
    """
    tree = ast.parse((_SRC / "domain" / "particle.py").read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    offenders = {name for name in imported if name.startswith("openchem")}
    assert not offenders, f"domain/particle.py imports {sorted(offenders)}"


def test_no_particle_is_reachable_from_the_project():
    """A particle must not become a project document.

    `ProjectModel` is what gets serialised, so a field here is the one
    step that would put a baryon into a saved `.ocsproj` -- and from
    there into every consumer that iterates a project.
    """
    from openchem.domain.project import ProjectModel

    fields = set(ProjectModel.__dataclass_fields__)
    assert not any("particle" in name or "quark" in name for name in fields), fields


def test_a_particle_is_never_serialised_as_a_molecule_or_a_crystal():
    """The narrow half, and the load-bearing one.

    "No field on ProjectModel" is satisfied by smuggling a particle into
    `metadata`, or by giving `ParticleState` a `to_dict` that a molecule
    loader would accept. This asserts the type carries no serialisation
    at all, so there is nothing for a project writer to call.
    """
    from openchem.domain.particle import ParticleState

    for method in ("to_dict", "from_dict", "molblock", "smiles", "uuid"):
        assert not hasattr(ParticleState, method), (
            f"ParticleState grew {method!r}, which is the first step to a "
            "particle being written into a project file"
        )


def test_nothing_in_chem_imports_the_particle_model():
    """The other direction. The guard above stops particles reaching
    chemistry; this stops chemistry reaching particles, which is how a
    calculator would start trying to answer about a baryon."""
    offenders = []
    for path in sorted((_SRC / "chem").rglob("*.py")):
        if "vendor" in path.parts:
            continue
        if "domain.particle" in path.read_text(encoding="utf-8"):
            offenders.append(str(path.relative_to(_SRC)))
    assert not offenders, f"chem/ reaches the particle model: {offenders}"


# --- the dialog -------------------------------------------------------------


def _dispose(widget):

    conftest.dispose(widget)


def test_the_dialog_opens_on_a_proton(qapp):
    """**IT OPENED ON A DELTA++ AND EVERY TEST PASSED.**

    `QComboBox.findData` compares through `QVariant` and cannot match the
    Python tuple `(Flavour, bool)` the items carry, so it returned -1 and
    every slot stayed at index 0 -- `u u u`. Nothing noticed, because
    `content()` reads `currentData()` and was correct about the wrong
    selection; the suite was green and the screenshot was not.

    This asserts the CONTENT the dialog starts with rather than the combo
    indices, so it still holds if the picker is reordered.
    """
    from openchem.ui.dialogs.particle_dialog import ParticleDialog

    dialog = ParticleDialog()
    try:
        assert [q.symbol for q in dialog.content()] == ["u", "u", "d"]
        assert "proton" in dialog.verdict_text()
    finally:
        _dispose(dialog)


def test_a_lookup_that_should_always_succeed_raises_rather_than_going_quiet(qapp):
    """The narrow half: the reason the bug was invisible was a silent -1.

    Restoring `findData` would make `_select` a no-op again, which this
    catches only because the failure is now loud. Asserted on the helper,
    since no reachable UI path can ask for a flavour the picker lacks.
    """
    from openchem.ui.dialogs.particle_dialog import ParticleDialog

    dialog = ParticleDialog()
    try:
        with pytest.raises(ValueError, match="no combo entry"):
            dialog._select(0, "not a flavour", False)
    finally:
        _dispose(dialog)


def test_switching_to_meson_mode_drops_the_third_quark(qapp):
    from openchem.ui.dialogs.particle_dialog import ParticleDialog

    dialog = ParticleDialog()
    try:
        dialog._meson.setChecked(True)
        assert len(dialog.content()) == 2
        assert "pion plus" in dialog.verdict_text()
        # Disabled rather than hidden: a control that vanishes reads as a
        # bug, one that greys out says a meson has two constituents.
        assert not dialog._slots[2].isEnabled()
    finally:
        _dispose(dialog)


def test_the_derived_panel_is_populated_even_with_no_identification(qapp):
    """The arithmetic is the part that always works, so it must be on
    screen exactly when there is no name to show."""
    from openchem.ui.dialogs.particle_dialog import ParticleDialog

    dialog = ParticleDialog()
    try:
        dialog._select(0, Flavour.UP, False)
        dialog._select(1, Flavour.DOWN, False)
        dialog._select(2, Flavour.STRANGE, False)
        assert "not identified" in dialog.verdict_text()
        assert dialog.derived_text("charge") == "0"
        assert dialog.derived_text("strangeness") == "-1"
        assert dialog.derived_text("baryon") == "1"
        # Both candidates named, neither chosen.
        assert "Lambda" in dialog.measured_text()
        assert "Sigma zero" in dialog.measured_text()
    finally:
        _dispose(dialog)


def test_an_identified_state_shows_what_the_PDG_prints(qapp):
    from openchem.ui.dialogs.particle_dialog import ParticleDialog

    dialog = ParticleDialog()
    try:
        assert "938.272" in dialog.measured_text()
        assert "I(J^P) = 1/2(1/2+)" in dialog.measured_text()
        # The proton's mean life is a LIMIT, not a measurement.
        assert "no decay observed" in dialog.measured_text()
    finally:
        _dispose(dialog)
