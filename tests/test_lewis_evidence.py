"""Evidence from stored quantum-chemistry runs reaching the Lewis lines (`docs/RECIPES_DESIGN.md` section 4).

No Qt and no ORCA. The numbers are typed in, the way `tests/test_lewis_adduct.py` types the documented ones; what is
tested is where each number goes, what is refused at the door, and that the registered calculator has no such door.
The recipe path through real stored runs, and the gate on real ORCA, come after this.
"""

from __future__ import annotations

import inspect
import re

import pytest
from rdkit import Chem

from openchem.chem.lewis_adduct import compute_lewis_adduct, lewis_report
from openchem.domain.lewis import (
    EVIDENCE_CALC_TYPES,
    EVIDENCE_DESCRIPTORS,
    EvidenceValue,
    MoleculeEvidence,
    PairEvidence,
)
from openchem.domain.recipe_run import BindingState, Evidence

METHOD = "B3LYP def2-SVP"


def _evidence(kind: str, value: float, molecule: str, **kw) -> Evidence:
    base = dict(
        molecule_uuid=molecule, run_id=f"{molecule}-{kind}", descriptor_id=EVIDENCE_DESCRIPTORS[kind], value=value,
        unit="eV", calc_type=EVIDENCE_CALC_TYPES[kind], method_basis=METHOD, charge=0, multiplicity=1,
        input_fingerprint="ab" * 32,
    )
    base.update(kw)
    return Evidence(**base)


def _bound(kind: str, value: float, molecule: str, **kw) -> EvidenceValue:
    return EvidenceValue(value, BindingState.BOUND, evidence=_evidence(kind, value, molecule, **kw))


def _gap(state: BindingState, reason: str = "nothing yet") -> EvidenceValue:
    return EvidenceValue(state=state, reason=reason)


def _molecule(label: str, uuid: str, homo, lumo, hardness, **kw) -> MoleculeEvidence:
    def item(kind, value):
        return value if isinstance(value, EvidenceValue) else _bound(kind, value, uuid, **kw)

    return MoleculeEvidence(label, item("homo", homo), item("lumo", lumo), item("hardness", hardness))


def _line(report, label: str) -> list[float | None]:
    """The value(s) a line printed, in order, one per orientation; None for 'not available'."""
    found = []
    for text in report.matched:
        match = re.match(rf"\s*{re.escape(label)}: (?:(-?\d+\.\d+) eV|not available)", text)
        if match:
            found.append(float(match.group(1)) if match.group(1) else None)
    return found


def _mol(smiles: str):
    mol = Chem.MolFromSmiles(smiles)
    assert mol is not None, smiles
    return mol


GAP, HSAB = "Frontier orbital gap", "HSAB hardness match"


# --- an evidence value is a number with its provenance, or a reason -----------------------------------------


def test_a_bound_value_carries_the_run_it_was_copied_from():
    with pytest.raises(ValueError, match="carries a number and the evidence"):
        EvidenceValue(1.0, BindingState.BOUND)
    with pytest.raises(ValueError, match="carries a number and the evidence"):
        EvidenceValue(None, BindingState.BOUND, evidence=_evidence("homo", 1.0, "m"))


def test_a_number_in_another_unit_is_refused_not_converted():
    with pytest.raises(ValueError, match="never converted"):
        EvidenceValue(-0.37, BindingState.BOUND, evidence=_evidence("homo", -0.37, "m", unit="hartree"))


def test_the_number_and_its_evidence_must_agree():
    with pytest.raises(ValueError, match="disagree"):
        EvidenceValue(1.0, BindingState.BOUND, evidence=_evidence("homo", 2.0, "m"))


@pytest.mark.parametrize("state", [s for s in BindingState if s is not BindingState.BOUND])
def test_a_gap_has_no_number_and_says_why(state):
    assert EvidenceValue(state=state, reason="why").value is None
    with pytest.raises(ValueError, match="says why in words"):
        EvidenceValue(state=state)
    with pytest.raises(ValueError, match="says why in words"):
        EvidenceValue(state=state, reason="  ")
    with pytest.raises(ValueError, match="has no number"):
        EvidenceValue(1.0, state, reason="why")
    with pytest.raises(ValueError, match="has no number"):
        EvidenceValue(state=state, reason="why", evidence=_evidence("homo", 1.0, "m"))


def test_the_koopmans_hardness_is_never_accepted():
    """Free from any job that has run, and it inverts ammonia against phosphine."""
    koopmans = EvidenceValue(
        8.0, BindingState.BOUND,
        evidence=_evidence("hardness", 8.0, "m", descriptor_id="orca.hardness", calc_type="sp"),
    )
    with pytest.raises(ValueError, match="Koopmans"):
        MoleculeEvidence("m", _bound("homo", -1.0, "m"), _bound("lumo", 1.0, "m"), koopmans)


@pytest.mark.parametrize(
    ("attribute", "descriptor_id", "calc_type"),
    [
        ("homo", "orca.lumo_energy", "sp"),
        ("lumo", "orca.homo_energy", "sp"),
        ("homo", "orca.homo_energy", "opt"),
        ("lumo", "orca.lumo_energy", "delta_scf"),
        ("hardness", "orca.dscf_hardness", "sp"),
    ],
    ids=["homo given the lumo", "lumo given the homo", "homo from an optimization", "lumo from a delta-SCF",
         "hardness from a single point"],
)
def test_each_number_must_be_the_descriptor_and_the_calculation_it_is_defined_by(attribute, descriptor_id, calc_type):
    kinds = {"homo": _bound("homo", -1.0, "m"), "lumo": _bound("lumo", 1.0, "m"), "hardness": _bound("hardness", 5.0, "m")}
    wrong = EvidenceValue(
        3.0, BindingState.BOUND, evidence=_evidence(attribute, 3.0, "m", descriptor_id=descriptor_id, calc_type=calc_type)
    )
    kinds[attribute] = wrong
    with pytest.raises(ValueError):
        MoleculeEvidence("m", **kinds)


def test_a_pair_never_subtracts_two_scales():
    a = _molecule("A", "a", -5.0, -1.0, 4.0)
    other_method = _molecule("B", "b", -6.0, -2.0, 5.0, method_basis="HF STO-3G")
    other_solvent = _molecule("B", "b", -6.0, -2.0, 5.0, solvent="water")
    for b in (other_method, other_solvent):
        with pytest.raises(ValueError, match="never subtracts two scales"):
            PairEvidence(a, b)


def test_each_pairing_a_line_uses_is_checked_in_both_orientations():
    base = dict(homo=-5.0, lumo=-1.0, hardness=4.0)
    other = {"method_basis": "HF STO-3G"}
    a = _molecule("A", "a", **base)
    # Only the second molecule's HOMO is at another level: the first-LUMO/second-HOMO pairing breaks.
    b_homo = MoleculeEvidence("B", _bound("homo", -6.0, "b", **other), _bound("lumo", -2.0, "b"), _bound("hardness", 5.0, "b"))
    with pytest.raises(ValueError, match="first LUMO with second HOMO"):
        PairEvidence(a, b_homo)
    # Only the second molecule's LUMO: the second-LUMO/first-HOMO pairing.
    b_lumo = MoleculeEvidence("B", _bound("homo", -6.0, "b"), _bound("lumo", -2.0, "b", **other), _bound("hardness", 5.0, "b"))
    with pytest.raises(ValueError, match="second LUMO with first HOMO"):
        PairEvidence(a, b_lumo)
    # Only the hardness.
    b_hard = MoleculeEvidence("B", _bound("homo", -6.0, "b"), _bound("lumo", -2.0, "b"), _bound("hardness", 5.0, "b", **other))
    with pytest.raises(ValueError, match="the two hardnesses"):
        PairEvidence(a, b_hard)


def test_a_gap_beside_a_number_is_not_a_scale_conflict():
    a = _molecule("A", "a", -5.0, -1.0, 4.0)
    b = _molecule("B", "b", -6.0, -2.0, _gap(BindingState.INCOMPATIBLE, "hardness is at another method"))
    PairEvidence(a, b)


def test_frontier_and_hardness_of_one_molecule_may_come_from_different_inputs():
    """A stated caveat, not a block: the lines are independent evidence (RECIPES_DESIGN section 4)."""
    a = MoleculeEvidence(
        "A", _bound("homo", -5.0, "a", input_fingerprint="11" * 32), _bound("lumo", -1.0, "a", input_fingerprint="11" * 32),
        _bound("hardness", 4.0, "a", input_fingerprint="22" * 32),
    )
    PairEvidence(a, _molecule("B", "b", -6.0, -2.0, 5.0))


# --- where each number goes ---------------------------------------------------------------------------------

# A different value for every number, so that reading one molecule's number for the other's, or the HOMO for the
# LUMO, gives a DIFFERENT line and not merely a similar one. Written with a distinct decimal each.
FIRST = dict(homo=-1.1, lumo=-2.2, hardness=3.3)
SECOND = dict(homo=-10.4, lumo=20.5, hardness=30.6)


def _pair(first_smiles: str, second_smiles: str, role: str = "auto"):
    evidence = PairEvidence(_molecule("First", "u1", **FIRST), _molecule("Second", "u2", **SECOND))
    return lewis_report(_mol(first_smiles), "u1", _mol(second_smiles), role, evidence=evidence)


def test_the_acids_lumo_and_the_bases_homo_make_the_gap_whichever_molecule_is_which():
    # First (borane) is the acid: gap = E_LUMO(first) - E_HOMO(second) = -2.2 - (-10.4) = 8.2
    as_acid = _pair("B", "[C-]#[O+]", "acid")
    assert _line(as_acid, GAP) == [pytest.approx(8.2)]
    # First (now carbon monoxide) is the base, the same evidence the other way round:
    # gap = E_LUMO(second) - E_HOMO(first) = 20.5 - (-1.1) = 21.6
    as_base = _pair("[C-]#[O+]", "B", "base")
    assert _line(as_base, GAP) == [pytest.approx(21.6)]


def test_the_hsab_line_is_the_difference_of_the_two_hardnesses_in_either_orientation():
    assert _line(_pair("B", "[C-]#[O+]", "acid"), HSAB) == [pytest.approx(27.3)]
    assert _line(_pair("[C-]#[O+]", "B", "base"), HSAB) == [pytest.approx(27.3)]


def test_every_wrong_reading_gives_a_different_gap():
    """What a mutant that mixes the numbers up would print. None of these may equal the right answer."""
    wrong = {
        "second's LUMO for first's": 20.5 - (-10.4),
        "first's HOMO for second's": -2.2 - (-1.1),
        "both from the same molecule": -2.2 - (-1.1),
        "HOMO for LUMO": -1.1 - (-10.4),
        "LUMO for HOMO": -2.2 - 20.5,
    }
    right = _line(_pair("B", "[C-]#[O+]", "acid"), GAP)[0]
    for name, value in wrong.items():
        assert value != pytest.approx(right), name


def test_the_same_evidence_serves_both_orientations_of_an_unresolved_pair():
    """Methanol and ammonia can each be either partner, so BOTH ways round are reported, from one evidence set."""
    report = _pair("CO", "N")
    assert _line(report, GAP) == [pytest.approx(8.2), pytest.approx(21.6)]
    assert _line(report, HSAB) == [pytest.approx(27.3), pytest.approx(27.3)]


def test_swapping_which_molecule_is_first_gives_the_same_lines_for_the_same_roles():
    """Slot order is not part of the answer. (first=A, second=B, auto) and (first=B, second=A, auto) agree."""
    a, b = _molecule("A", "ua", **FIRST), _molecule("B", "ub", **SECOND)
    one = lewis_report(_mol("B"), "ua", _mol("[C-]#[O+]"), "auto", evidence=PairEvidence(a, b))
    other = lewis_report(_mol("[C-]#[O+]"), "ub", _mol("B"), "auto", evidence=PairEvidence(b, a))
    assert _line(one, GAP) == _line(other, GAP) and _line(one, HSAB) == _line(other, HSAB)
    assert _line(one, GAP) == [pytest.approx(8.2)]


def test_the_documented_pair_reproduces_and_the_disagreement_stays():
    """RECIPES_DESIGN section 10, the numbers it gates on, typed in: frontier gap 8.13 / 10.90 eV and |d eta|
    1.63 / 0.89 eV for BH3 and BF3 with CO. The lines DISAGREE on carbon monoxide, on purpose."""
    co = _molecule("CO", "co", -10.17, 99.0, 8.40)
    borane = _molecule("BH3", "bh3", -99.0, -2.04, 6.77)
    trifluoride = _molecule("BF3", "bf3", -99.0, 0.73, 9.29)
    bh3 = lewis_report(_mol("B"), "bh3", _mol("[C-]#[O+]"), "acid", evidence=PairEvidence(borane, co))
    bf3 = lewis_report(_mol("FB(F)F"), "bf3", _mol("[C-]#[O+]"), "acid", evidence=PairEvidence(trifluoride, co))
    assert _line(bh3, GAP) == [pytest.approx(8.13)] and _line(bf3, GAP) == [pytest.approx(10.90)]
    assert _line(bh3, HSAB) == [pytest.approx(1.63)] and _line(bf3, HSAB) == [pytest.approx(0.89)]
    assert _line(bh3, GAP)[0] < _line(bf3, GAP)[0], "the frontier gap prefers borane"
    assert _line(bf3, HSAB)[0] < _line(bh3, HSAB)[0], "the HSAB line prefers BF3: the disagreement must reproduce"


def test_evidence_decides_no_orientation():
    """There is no rule 3: contrived hardness that would favour the other way round changes nothing about WHO is
    the acid, which comes from the structures (`resolve_roles`)."""
    favours_reverse = PairEvidence(
        _molecule("BH3", "u1", homo=-50.0, lumo=50.0, hardness=1.0), _molecule("CO", "u2", homo=50.0, lumo=-50.0, hardness=1.0)
    )
    report = lewis_report(_mol("B"), "u1", _mol("[C-]#[O+]"), "auto", evidence=favours_reverse)
    text = "\n".join(report.matched)
    assert "Acid: B\n" in text and "Base: [C-]#[O+]" in text
    assert "from the structures" in text


# --- gaps ---------------------------------------------------------------------------------------------------


def test_a_missing_hardness_loses_the_hsab_line_and_keeps_the_frontier_line():
    evidence = PairEvidence(
        _molecule("First", "u1", -1.1, -2.2, _gap(BindingState.MISSING, "First has no delta-SCF run at B3LYP def2-SVP")),
        _molecule("Second", "u2", **SECOND),
    )
    report = lewis_report(_mol("B"), "u1", _mol("[C-]#[O+]"), "acid", evidence=evidence)
    assert _line(report, GAP) == [pytest.approx(8.2)]
    assert _line(report, HSAB) == [None]


@pytest.mark.parametrize("state", [s for s in BindingState if s is not BindingState.BOUND])
def test_a_gap_in_any_state_reaches_predict_as_not_available_never_as_a_number(state):
    evidence = PairEvidence(
        _molecule("First", "u1", _gap(state, "no usable run"), -2.2, 3.3), _molecule("Second", "u2", **SECOND)
    )
    report = lewis_report(_mol("[C-]#[O+]"), "u1", _mol("B"), "base", evidence=evidence)
    # first is the base here, so its HOMO is the missing input of the frontier line; hardness is intact.
    assert _line(report, GAP) == [None]
    assert _line(report, HSAB) == [pytest.approx(27.3)]


def test_every_gap_is_a_fact_with_its_state_and_its_reason():
    reason = "First has two earlier geometries; choose one by run id (r1, r2)"
    evidence = PairEvidence(
        _molecule("First", "u1", _gap(BindingState.AMBIGUOUS, reason), -2.2, 3.3), _molecule("Second", "u2", **SECOND)
    )
    report = lewis_report(_mol("B"), "u1", _mol("[C-]#[O+]"), "acid", evidence=evidence)
    [fact] = [f for f in report.facts if f.label == "First: E(HOMO)"]
    assert "ambiguous" in fact.display_value and fact.limitations == (reason,) and fact.value is None


def test_a_run_behind_a_number_is_named_with_its_method_charge_multiplicity_and_input():
    report = _pair("B", "[C-]#[O+]", "acid")
    [fact] = [f for f in report.facts if f.label == "First: E(HOMO)"]
    assert fact.value == pytest.approx(-1.1) and fact.units == "eV"
    joined = " | ".join(fact.evidence)
    assert "orca.homo_energy from run u1-homo" in joined
    assert f"sp, {METHOD}, charge 0, multiplicity 1" in joined
    assert "input " + "ab" * 6 in joined


def test_the_evidence_block_lists_both_molecules_and_all_six_numbers():
    labels = [f.label for f in _pair("B", "[C-]#[O+]", "acid").facts if f.source == "Stored quantum-chemistry run"]
    assert labels == [
        "First: E(HOMO)", "First: E(LUMO)", "First: Chemical hardness (delta-SCF)",
        "Second: E(HOMO)", "Second: E(LUMO)", "Second: Chemical hardness (delta-SCF)",
    ]


def test_an_unresolved_pair_names_its_evidence_too():
    """The both-orientations report is a different return path from the resolved one, and carries the same block."""
    report = _pair("CO", "N")
    assert "Role: not determined" in report.matched[0]
    labels = [f.label for f in report.facts if f.source == "Stored quantum-chemistry run"]
    assert len(labels) == 6 and labels[0] == "First: E(HOMO)" and labels[-1] == "Second: Chemical hardness (delta-SCF)"


def test_a_molecule_with_no_label_is_named_by_its_slot():
    evidence = PairEvidence(_molecule("", "u1", **FIRST), _molecule("", "u2", **SECOND))
    report = lewis_report(_mol("B"), "u1", _mol("[C-]#[O+]"), "acid", evidence=evidence)
    assert "first: E(HOMO)" in [f.label for f in report.facts]
    assert "second: E(LUMO)" in [f.label for f in report.facts]


def test_a_solvent_is_named_when_there_is_one():
    evidence = PairEvidence(
        _molecule("First", "u1", **FIRST, solvent="water"), _molecule("Second", "u2", **SECOND, solvent="water")
    )
    report = lewis_report(_mol("B"), "u1", _mol("[C-]#[O+]"), "acid", evidence=evidence)
    [fact] = [f for f in report.facts if f.label == "First: E(HOMO)"]
    assert any("solvent water" in e for e in fact.evidence)


# --- what does not change -------------------------------------------------------------------------------------


def test_the_role_text_the_assumptions_and_the_limitations_are_the_calculators_own():
    with_evidence = _pair("B", "[C-]#[O+]", "acid")
    without = compute_lewis_adduct(_mol("B"), "u1", {"partner_smiles": "[C-]#[O+]", "role": "acid"})

    def kept(report):
        return [t for t in report.matched if t.startswith(("Role:", "Assumption:", "Limitation:", "Acid:", "Base:"))]

    assert kept(with_evidence) == kept(without)


def test_there_is_still_no_combined_score():
    labels = " ".join(f.label.lower() for f in _pair("B", "[C-]#[O+]", "acid").facts)
    for word in ("score", "combined", "overall", "total", "rank"):
        assert word not in labels, word
    assert not hasattr(_pair("B", "[C-]#[O+]", "acid"), "score")


def test_the_registered_calculator_has_no_way_to_be_handed_evidence():
    """Six numeric parameters would be an unprovenanced channel into a result beside a published-looking enthalpy."""
    assert list(inspect.signature(compute_lewis_adduct).parameters) == ["mol", "molecule_uuid", "parameters"]
    report = compute_lewis_adduct(
        _mol("B"), "u1", {"partner_smiles": "[C-]#[O+]", "role": "acid", "acid_lumo_ev": -2.0, "base_homo_ev": -10.0}
    )
    assert _line(report, GAP) == [None], "a number smuggled in through the parameters must not become a line"


def test_without_evidence_the_report_has_no_evidence_facts():
    plain = compute_lewis_adduct(_mol("B"), "u1", {"partner_smiles": "[C-]#[O+]", "role": "acid"})
    assert not [f for f in plain.facts if f.source == "Stored quantum-chemistry run"]
