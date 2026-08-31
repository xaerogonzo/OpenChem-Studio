"""The dominant ionization state, and why it used to be a coin flip.

`protonate_at_ph` took `variants[0]` from Dimorphite-DL. That list is an
ENUMERATION of microspecies, not a ranking, and its order comes from a set
iteration -- so it inherited `PYTHONHASHSEED`. Measured on
isobutyrylfentanyl at pH 7.4, eight separate processes returned THREE
different net charges for one molecule, and logD moved 1.68 to 4.38.

These guards are in two halves, and the second is the load-bearing one:
the correction must fire where Dimorphite is wrong AND must not fire
anywhere else. "Never protonate anything" satisfies every amide test in
this file and destroys the feature.
"""

from __future__ import annotations

import pytest
from rdkit import Chem

from openchem.chem.pka_providers import dominant_microspecies, protonate_at_ph


def _charge(smiles: str, ph: float = 7.4) -> int:
    return dominant_microspecies(Chem.MolFromSmiles(smiles), ph).formal_charge


# --- the corpus -------------------------------------------------------------
#
# Sixteen drug-like molecules whose charge state at pH 7.4 is not in doubt.
# Five of them were WRONG before this change and every one of those five is
# the same class: a tertiary amide, which Dimorphite matches with its plain
# `[C:1]-[NX3+0:2]` amine rule (pKa 8.16) because its `*Amide` rule requires
# an N-H that a tertiary amide does not have.

_CORPUS = [
    # (name, smiles, charge at pH 7.4, was wrong before this change)
    ("caffeine", "Cn1c(=O)c2c(ncn2C)n(C)c1=O", 0, False),
    ("acetanilide", "CC(=O)Nc1ccccc1", 0, False),
    ("diazepam", "CN1c2ccc(Cl)cc2C(=NCC1=O)c1ccccc1", 0, False),
    ("carbamazepine", "NC(=O)N1c2ccccc2C=Cc2ccccc21", 0, False),
    ("DMF", "CN(C)C=O", 0, True),
    ("DEET", "CCN(CC)C(=O)c1cccc(C)c1", 0, True),
    ("N,N-dimethylacetamide", "CC(=O)N(C)C", 0, True),
    ("N-methylpyrrolidone", "CN1CCCC1=O", 0, True),
    ("atropine", "CN1C2CCC1CC(C2)OC(=O)C(CO)c1ccccc1", 1, False),
    ("lidocaine", "CCN(CC)CC(=O)Nc1c(C)cccc1C", 1, False),
    ("nicotine", "CN1CCC[C@H]1c1cccnc1", 1, False),
    ("propranolol", "CC(C)NCC(O)COc1cccc2ccccc12", 1, False),
    ("fentanyl", "CCC(=O)N(c1ccccc1)C1CCN(CCc2ccccc2)CC1", 1, True),
    ("isobutyrylfentanyl", "CC(C)C(=O)N(c1ccccc1)C1CCN(CCc2ccccc2)CC1", 1, True),
    ("aspirin", "CC(=O)Oc1ccccc1C(=O)O", -1, False),
    ("ibuprofen", "CC(C)Cc1ccc(cc1)C(C)C(=O)O", -1, False),
]


@pytest.mark.parametrize(
    "name, smiles, expected", [(n, s, c) for n, s, c, _ in _CORPUS], ids=[n for n, *_ in _CORPUS]
)
def test_the_dominant_state_matches_the_literature_charge(name, smiles, expected):
    assert _charge(smiles) == expected


def test_the_corpus_still_contains_the_cases_that_were_wrong():
    """ASSERTS ITS OWN SETUP, so this file cannot go vacuous.

    Eleven of the sixteen were already right before the fix, so a corpus
    that quietly lost the other five would keep passing while testing
    nothing -- the "green suite, smaller universe" failure this project
    records repeatedly. The five are named because they are the evidence.
    """
    regressions = {name for name, _s, _c, was_wrong in _CORPUS if was_wrong}
    assert regressions == {
        "DMF",
        "DEET",
        "N,N-dimethylacetamide",
        "N-methylpyrrolidone",
        "fentanyl",
        "isobutyrylfentanyl",
    }


# --- determinism ------------------------------------------------------------


def test_the_answer_does_not_depend_on_the_librarys_ordering(monkeypatch):
    """THE ORIGINAL BUG, reproduced without needing two processes.

    The real defect only shows across processes, because the hash seed is
    fixed within one. Feeding the same states in two different orders is
    the same question asked in a way a test can actually put.
    """
    import dimorphite_dl

    states = [
        "CC(C)C(=O)[NH+](c1ccccc1)C1CC[NH+](CCc2ccccc2)CC1",
        "CC(C)C(=O)N(c1ccccc1)C1CC[NH+](CCc2ccccc2)CC1",
        "CC(C)C(=O)N(c1ccccc1)C1CCN(CCc2ccccc2)CC1",
    ]
    seen = []
    for order in (states, list(reversed(states)), [states[1], states[2], states[0]]):
        monkeypatch.setattr(
            dimorphite_dl, "protonate_smiles", lambda *a, _o=order, **k: list(_o)
        )
        mol = Chem.MolFromSmiles("CC(C)C(=O)N(c1ccccc1)C1CCN(CCc2ccccc2)CC1")
        seen.append(Chem.MolToSmiles(dominant_microspecies(mol, 7.4).mol))
    assert len(set(seen)) == 1, f"the answer followed the library's ordering: {seen}"


def test_the_dominant_state_is_requested_rather_than_the_enumeration():
    """`precision=0.0` collapses Dimorphite's window to the pKa itself.

    Asserted on the source: with the default precision the library returns
    several states and which one arrives first is a set iteration. The
    sorting above makes that harmless, but requesting the enumeration at
    all and then picking one is answering a different question from the
    one being asked.
    """
    from pathlib import Path

    body = (
        Path(__file__).parent.parent
        / "src" / "openchem" / "chem" / "pka_providers.py"
    ).read_text(encoding="utf-8")
    call = body[body.index("dimorphite_dl.protonate_smiles(") :][:200]
    assert "precision=0.0" in call, (
        "the dominant-state request is gone, so this is enumerating "
        "microspecies again and choosing one"
    )


# --- the correction, both halves ---------------------------------------------


def test_a_tertiary_amide_nitrogen_is_not_protonated():
    result = dominant_microspecies(Chem.MolFromSmiles("CN(C)C=O"), 7.4)
    assert result.formal_charge == 0
    assert result.corrected_atoms, "the correction did not fire on a tertiary amide"


def test_a_basic_amine_is_STILL_protonated():
    """THE LOAD-BEARING HALF. "Never protonate anything" passes every amide
    guard in this file and silently deletes the feature."""
    result = dominant_microspecies(Chem.MolFromSmiles("CN1CCCCC1"), 7.4)
    assert result.formal_charge == 1
    assert result.corrected_atoms == ()


def test_the_correction_does_not_fire_where_dimorphite_is_already_right():
    """Acetanilide has an N-H, so Dimorphite's own `*Amide` rule catches it
    and there is nothing to override. A correction that fired here would be
    reaching past the defect it was written for."""
    result = dominant_microspecies(Chem.MolFromSmiles("CC(=O)Nc1ccccc1"), 7.4)
    assert result.corrected_atoms == ()


def test_the_correction_only_ever_removes_a_proton(monkeypatch):
    """It may lower a charge and must never raise one.

    Overriding a library's chemistry is a claim, and this is the bound on
    it: whatever Dimorphite does that is not this specific error stands.
    """
    import dimorphite_dl

    for smiles in [s for _n, s, _c, _w in _CORPUS]:
        mol = Chem.MolFromSmiles(smiles)
        monkeypatch.undo()
        after = dominant_microspecies(mol, 7.4)
        raw = dimorphite_dl.protonate_smiles(
            Chem.MolToSmiles(mol), ph_min=7.4, ph_max=7.4, precision=0.0
        )
        before = Chem.GetFormalCharge(Chem.MolFromSmiles(sorted(raw)[0]))
        assert after.formal_charge <= before, (
            f"{smiles}: the correction ADDED charge, {before} -> {after.formal_charge}"
        )


def test_the_thin_wrapper_agrees_with_the_detailed_form():
    """Six production consumers call `protonate_at_ph`; only the charge
    calculator wants the detail. They must not drift."""
    mol = Chem.MolFromSmiles("CN(C)C=O")
    assert Chem.MolToSmiles(protonate_at_ph(mol, 7.4)) == Chem.MolToSmiles(
        dominant_microspecies(mol, 7.4).mol
    )


# --- the producer says which species it charged ------------------------------


def _note(smiles: str) -> str:
    from openchem.chem.descriptor_providers import compute_gasteiger_charge_at_ph

    dataset = compute_gasteiger_charge_at_ph(
        Chem.MolFromSmiles(smiles), "u", {"include_hydrogens": True}
    )
    return dataset.provenance.parameters.get("summary") or ""


def test_the_producer_says_so_when_the_species_it_charged_is_not_the_one_drawn():
    note = _note("CC(C)C(=O)N(c1ccccc1)C1CCN(CCc2ccccc2)CC1")
    assert "+1" in note and "microspecies" in note, note


def test_it_says_NOTHING_when_the_drawn_structure_is_what_was_charged():
    """THE NARROW HALF. "Always declare" satisfies the guard above and puts
    a line on every neutral result -- noise given a voice, which is the
    tolerance discipline `_balance_text` already applies to a balance of
    1e-16."""
    assert _note("c1ccccc1") == ""


def test_an_overridden_amide_is_named_in_the_note():
    """The correction is reported, not applied silently: a charge
    distribution that quietly disagrees with the library that produced it
    is the kind of number this project exists to remove."""
    note = _note("CC(C)C(=O)N(c1ccccc1)C1CCN(CCc2ccccc2)CC1")
    assert "amide-like nitrogen" in note, note
    assert "amide-like nitrogen" not in _note("CN1CCCCC1"), (
        "a plain amine reported an amide correction that never happened"
    )


# --- a refusal is declared, not sniffed --------------------------------------


def test_joback_declares_its_refusal_as_a_limit_of_the_method():
    """The reported "calculator failure" -- a ring tertiary amine, which
    Joback's 1987 table genuinely has no group for."""
    from openchem.chem.joback import compute_joback

    result = compute_joback(
        Chem.MolFromSmiles("CC(C)C(=O)N(c1ccccc1)C1CCN(CCc2ccccc2)CC1"), "u", {}
    )
    assert result.cache_state.value == "failed"
    assert result.inapplicable, (
        "Joback's refusal is still declared as a fault, so it renders with "
        "the same red X as a crash"
    )


def test_a_calculator_that_simply_works_declares_no_inapplicability():
    """The narrow half again: 'everything is inapplicable' passes the guard
    above."""
    from openchem.chem.joback import compute_joback

    result = compute_joback(Chem.MolFromSmiles("CCO"), "u", {})
    assert result.cache_state.value != "failed"
    assert not result.inapplicable
