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


# --- the drawn atom order survives ---------------------------------------------
#
# The SMILES round trip used to hand back Dimorphite's canonical order, and
# every per-atom consumer numbered its values by that. On O-O-C=N the pH 7.4
# Gasteiger charges put nitrogen's +0.00 on an oxygen.

#: Read through `_drawn`, which REVERSES each molecule's atom order. Measured:
#: written as SMILES, 11 of 15 drug-like molecules come back from the library
#: in their own order, so a SMILES corpus tests almost nothing -- while a
#: drawing is numbered in the order its atoms were placed, which is exactly
#: what the canonical round trip does not preserve. The setup guard below
#: asserts the reordering rather than assuming it.
_REORDERED = [
    "O1OC=N1",
    "O1OCN1",
    "CC(=O)O",
    "NCC(=O)O",
    "CC(=O)NC",
    "c1c[nH]cn1",
    "OC(=O)CCC(=O)O",
    "C/C=C/C(=O)O",
    "N[C@@H](Cc1ccccc1)C(=O)O",
    "CCC(=O)N(c1ccccc1)C1CCN(CCc2ccccc2)CC1",
]


def _adjacency(mol: Chem.Mol, index: int) -> set[int]:
    return {n.GetIdx() for n in mol.GetAtomWithIdx(index).GetNeighbors()}


def _drawn(smiles: str) -> Chem.Mol:
    mol = Chem.MolFromSmiles(smiles)
    return Chem.RenumberAtoms(mol, list(reversed(range(mol.GetNumAtoms()))))


def test_the_reordering_corpus_really_reorders():
    """ASSERTS ITS OWN SETUP: a corpus the library returns in drawn order
    would pass every index test below while testing nothing."""
    import dimorphite_dl

    reordered = 0
    for smiles in _REORDERED:
        mol = _drawn(smiles)
        raw = dimorphite_dl.protonate_smiles(
            Chem.MolToSmiles(mol), ph_min=7.4, ph_max=7.4, precision=0.0
        )
        parsed = Chem.MolFromSmiles(sorted(raw)[0])
        # Reordered means reading the library's index as the drawing's gets
        # an element OR a neighbour set wrong -- an element sequence alone
        # misses a swap between two atoms of the same element.
        if any(
            parsed.GetAtomWithIdx(i).GetAtomicNum() != mol.GetAtomWithIdx(i).GetAtomicNum()
            or _adjacency(parsed, i) != _adjacency(mol, i)
            for i in range(mol.GetNumAtoms())
        ):
            reordered += 1
    assert reordered == len(_REORDERED), f"only {reordered} of the corpus is actually reordered"


@pytest.mark.parametrize("ph", [1.0, 7.4, 12.0])
@pytest.mark.parametrize("smiles", _REORDERED)
def test_every_atom_keeps_its_drawn_index(smiles, ph):
    """Element and heavy-atom ADJACENCY, index for index -- not bond orders,
    which protonation legitimately changes (O-O-C=N comes back aromatic)."""
    mol = _drawn(smiles)
    species = dominant_microspecies(mol, ph).mol
    for index in range(mol.GetNumAtoms()):
        assert species.GetAtomWithIdx(index).GetAtomicNum() == mol.GetAtomWithIdx(index).GetAtomicNum()
        assert _adjacency(species, index) == _adjacency(mol, index), (smiles, ph, index)


@pytest.mark.parametrize("smiles", _REORDERED)
def test_renumbering_changes_nothing_but_the_numbering(smiles):
    """The same molecule Dimorphite chose, stereo included -- the fix is
    about identity and must not move a proton or a charge."""
    import dimorphite_dl

    from openchem.chem.pka_providers import restore_heavy_atom_order

    mol = _drawn(smiles)
    raw = dimorphite_dl.protonate_smiles(Chem.MolToSmiles(mol), ph_min=7.4, ph_max=7.4, precision=0.0)
    parsed = Chem.MolFromSmiles(sorted(raw)[0])
    assert Chem.MolToSmiles(restore_heavy_atom_order(mol, parsed)) == Chem.MolToSmiles(parsed)


def test_the_ring_from_the_report_puts_each_charge_on_its_own_atom():
    """THE REPORTED CASE. Charges computed on the species, read back by the
    drawing's index, must be the charges of the drawing's atoms: nitrogen's
    value on the nitrogen, not on an oxygen."""
    from openchem.chem.descriptor_providers import compute_gasteiger_charge_at_ph

    mol = Chem.MolFromSmiles("O1OC=N1")
    dataset = compute_gasteiger_charge_at_ph(mol, "u", {"pH": 7.4})
    by_element = {
        mol.GetAtomWithIdx(i).GetSymbol() + str(i): round(v, 4) for i, v in dataset.values.items()
    }
    # Measured on the renumbered species. Before the fix the pH 7.4 values
    # were {0: +0.2762, 1: +0.0027, 2: -0.164, 3: -0.2513}: the carbon's and
    # nitrogen's charges sitting on the two oxygens.
    assert by_element["O0"] < 0 and by_element["O1"] < 0, by_element
    assert by_element["C2"] > 0.2, by_element


def test_the_registered_calculator_keys_charges_to_the_drawn_atoms():
    """THROUGH THE REGISTRY, not the function: a direct-import test once
    passed while the registration bound to a different callable. A drawing
    in placement order, so the library genuinely reorders it."""
    from openchem.bootstrap import build_service_container
    from openchem.chem.descriptor_providers import compute_gasteiger_charges

    registry = build_service_container().calculator_registry
    mol = _drawn("CC(=O)NC")  # an amide: Dimorphite leaves it neutral at 7.4
    result = registry.compute("gasteiger_charge_at_ph", mol, "uuid", {"pH": 7.4})
    assert result.values == pytest.approx(compute_gasteiger_charges(Chem.Mol(mol))), (
        "on a molecule whose dominant species IS the drawing, the pH charges "
        "must equal the drawing's own charges index for index"
    )


def test_the_drawings_own_hydrogen_atoms_keep_their_indices():
    mol = Chem.AddHs(Chem.MolFromSmiles("CC(=O)O"))
    species = dominant_microspecies(mol, 1.0).mol
    assert [a.GetSymbol() for a in species.GetAtoms()] == [a.GetSymbol() for a in mol.GetAtoms()]
    for index in range(mol.GetNumAtoms()):
        assert _adjacency(species, index) == _adjacency(mol, index)


def test_a_drawn_hydrogen_the_species_removes_is_refused_not_dropped():
    """Deleting the atom would renumber everything after it -- the very bug
    being fixed -- so an index with no answer is a refusal."""
    from openchem.chem.engine import InvalidStructureError

    with pytest.raises(InvalidStructureError, match="drawn with a hydrogen"):
        dominant_microspecies(Chem.AddHs(Chem.MolFromSmiles("CC(=O)O")), 7.4)


def test_the_proton_goes_to_the_atom_the_drawing_says_held_it(monkeypatch):
    """With bond orders erased an acid's two oxygens are interchangeable; the
    DRAWING breaks the tie. The -OH, not the =O, becomes O-."""
    import dimorphite_dl

    monkeypatch.setattr(dimorphite_dl, "protonate_smiles", lambda *a, **k: ["[O-]C(C)=O"])
    mol = Chem.MolFromSmiles("CC(=O)O")  # 0 C, 1 C, 2 =O, 3 -OH
    species = dominant_microspecies(mol, 7.4).mol
    assert species.GetAtomWithIdx(3).GetFormalCharge() == -1
    assert species.GetAtomWithIdx(2).GetFormalCharge() == 0


def test_a_genuinely_ambiguous_correspondence_refuses(monkeypatch):
    """One of two EQUIVALENT amines protonated: nothing says which drawn
    nitrogen carries it, so choosing would be invention."""
    import dimorphite_dl

    from openchem.chem.engine import InvalidStructureError

    monkeypatch.setattr(dimorphite_dl, "protonate_smiles", lambda *a, **k: ["NCC[NH3+]"])
    with pytest.raises(InvalidStructureError, match="Symmetry-equivalent"):
        dominant_microspecies(Chem.MolFromSmiles("NCCN"), 7.4)


def test_symmetry_that_cannot_matter_does_not_refuse():
    """The narrow half: both amines protonated, or a phenyl ring flipped, is
    symmetric but unambiguous -- every candidate puts the same thing at
    every index. "Refuse whenever there is symmetry" passes the guard above
    and refuses fentanyl."""
    assert dominant_microspecies(Chem.MolFromSmiles("NCCN"), 7.4).formal_charge == 2
    assert dominant_microspecies(
        Chem.MolFromSmiles("CCC(=O)N(c1ccccc1)C1CCN(CCc2ccccc2)CC1"), 7.4
    ).formal_charge == 1


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


# --- the caller's atom maps -----------------------------------------------------
#
# Measured 2026-09-14: a drawing carrying map numbers reached Dimorphite with
# them written into its SMILES. A mapped imidazole came back with NO state at
# pH 7.4 where the unmapped one gives the anion, and every output atom lost its
# map.


def _mapped(smiles: str) -> Chem.Mol:
    mol = Chem.MolFromSmiles(smiles)
    for atom in mol.GetAtoms():
        atom.SetAtomMapNum(atom.GetIdx() + 1)
    return mol


def _unmapped_smiles(mol: Chem.Mol) -> str:
    copy = Chem.Mol(mol)
    for atom in copy.GetAtoms():
        atom.SetAtomMapNum(0)
    return Chem.MolToSmiles(copy)


@pytest.mark.parametrize("smiles", ["c1c[nH]cn1", "CCC(=O)O", "Oc1ccc(cc1)[N+](=O)[O-]"])
def test_a_drawing_with_atom_maps_gets_the_same_species_as_one_without(smiles):
    plain = dominant_microspecies(Chem.MolFromSmiles(smiles), 7.4)
    mapped = dominant_microspecies(_mapped(smiles), 7.4)
    assert _unmapped_smiles(mapped.mol) == _unmapped_smiles(plain.mol)
    assert mapped.formal_charge == plain.formal_charge


def test_the_callers_maps_come_back_on_their_own_atoms():
    mol = _mapped("CCC(=O)O")
    species = dominant_microspecies(mol, 7.4).mol
    assert [a.GetAtomMapNum() for a in species.GetAtoms()] == [a.GetAtomMapNum() for a in mol.GetAtoms()]
    assert species.GetAtomWithIdx(4).GetFormalCharge() == -1, "setup: the acid was not deprotonated"


def test_an_unmapped_drawing_stays_unmapped():
    """The narrow half: 'number every atom' passes the guard above."""
    species = dominant_microspecies(Chem.MolFromSmiles("CCC(=O)O"), 7.4).mol
    assert all(a.GetAtomMapNum() == 0 for a in species.GetAtoms())


def test_the_pka_runner_is_handed_no_caller_maps(monkeypatch, tmp_path):
    """The runner uses map numbers itself, to carry pkasolver's indices back;
    a caller's map 1 on atom 5 must not reach it."""
    import json
    import subprocess

    from openchem.chem import pka_providers

    interpreter = tmp_path / "python.exe"
    interpreter.write_text("")
    seen = []

    def fake_run(argv, **_kwargs):
        seen.append(argv[-1])
        return subprocess.CompletedProcess(argv, 0, stdout=json.dumps({"pkas": []}), stderr="")

    monkeypatch.setattr(pka_providers.subprocess, "run", fake_run)
    mol = Chem.MolFromSmiles("CCC(=O)O")
    mol.GetAtomWithIdx(4).SetAtomMapNum(1)
    assert pka_providers.compute_pka(mol, str(interpreter)) == []
    assert seen and ":" not in seen[0], f"a map number reached the runner: {seen[0]!r}"
