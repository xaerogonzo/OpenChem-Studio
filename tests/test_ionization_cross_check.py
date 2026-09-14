"""Where pkasolver and Dimorphite-DL land differently -- surfaced, not reconciled.

The two protonation models behind this application are separate: pkasolver
(numeric pKa, behind logD and solubility) and Dimorphite-DL (the dominant
species, behind the pH-dependent charges and every "major microspecies"
option). Measured on O1OCN1 at pH 7.4: pkasolver's basic pKa on the nitrogen
is 3.20, so it predicts the nitrogen neutral; Dimorphite protonates it. Neither
is known to be right.

The cross-check compares, SITE BY SITE, what pkasolver's prediction ENCODES --
its own protonated and deprotonated microstates, read from the sidecar -- with
Dimorphite's species at the same atom. It is a model comparison and a
declaration beside a result: no number moves because of it, which the last
tests here hold as a hard regression.
"""

from __future__ import annotations

import os

import pytest
from rdkit import Chem

from openchem.chem import pka_providers
from openchem.chem.pka_providers import (
    AGREES,
    DISAGREES,
    NOT_COMPARED,
    PkaPrediction,
    cross_check_lines,
    dominant_microspecies,
    ionization_model_cross_check,
)


def _species(smiles: str, ph: float) -> Chem.Mol:
    return dominant_microspecies(Chem.MolFromSmiles(smiles), ph).mol


def _only(check):
    assert len(check.sites) == 1, check.sites
    return check.sites[0]


# --- the four directions, each against the state the prediction ENCODES ---------

ACETIC = "CC(=O)O"  # 0 C, 1 C, 2 =O, 3 -OH
METHYLAMINE = "CN"  # 0 C, 1 N


def _acid_site(atom: int = 3) -> PkaPrediction:
    return PkaPrediction(atom_index=atom, value=4.76, stddev=0.27,
                         protonated_site=(1, 0), deprotonated_site=(0, -1))


def _base_site() -> PkaPrediction:
    return PkaPrediction(atom_index=1, value=10.6, protonated_site=(3, 1), deprotonated_site=(2, 0))


def test_an_acid_like_site_above_its_pka_is_predicted_deprotonated():
    site = _only(ionization_model_cross_check(_species(ACETIC, 7.4), [_acid_site()], 7.4))
    assert (site.verdict, site.pkasolver_state, site.pkasolver_label) == (AGREES, (0, -1), "deprotonated")


def test_an_acid_like_site_below_its_pka_is_predicted_protonated():
    site = _only(ionization_model_cross_check(_species(ACETIC, 2.0), [_acid_site()], 2.0))
    assert (site.verdict, site.pkasolver_state, site.pkasolver_label) == (AGREES, (1, 0), "protonated")


def test_a_base_like_site_below_its_pka_is_predicted_protonated():
    site = _only(ionization_model_cross_check(_species(METHYLAMINE, 7.4), [_base_site()], 7.4))
    assert (site.verdict, site.pkasolver_state, site.pkasolver_label) == (AGREES, (3, 1), "protonated")


def test_a_base_like_site_above_its_pka_is_predicted_deprotonated_meaning_its_encoded_state():
    """"Neutral" here is the model's own deprotonated microstate for the
    site, (2 H, 0) -- not "formal charge zero" read off anything."""
    site = _only(ionization_model_cross_check(_species(METHYLAMINE, 12.0), [_base_site()], 12.0))
    assert (site.verdict, site.pkasolver_state, site.pkasolver_label) == (AGREES, (2, 0), "deprotonated")


# --- the reported case, and what a disagreement carries -----------------------------


def test_the_reported_ring_disagrees_on_the_nitrogen_and_says_how_far_from_the_pka():
    """The values are the live sidecar's own, measured 2026-09-14."""
    species = _species("O1OCN1", 7.4)
    prediction = PkaPrediction(atom_index=3, value=3.1999, stddev=0.6439,
                               protonated_site=(2, 1), deprotonated_site=(1, 0))
    check = ionization_model_cross_check(species, [prediction], 7.4)
    site = _only(check)
    assert site.verdict == DISAGREES
    assert (site.atom_index, site.element) == (3, "N")
    assert (site.pkasolver_label, site.dimorphite_label) == ("deprotonated", "protonated")
    assert site.distance == pytest.approx(4.2001)

    (line,) = cross_check_lines(check, 7.4)
    assert line.startswith("Ionization-model cross-check at pH 7.4: pkasolver predicts atom 4 (N) deprotonated")
    assert "Dimorphite-DL selects it protonated" in line
    assert "4.20 from this pH" in line
    assert "charge of the molecule" not in line and "net" not in line


def test_a_carboxylate_site_mapped_onto_the_other_oxygen_is_not_a_false_disagreement():
    """`map_site_atom` takes an arbitrary match where the skeleton is
    symmetric, and a carboxyl's two oxygens are. Atom for atom, landing on the
    =O would read as a disagreement that is really a coin toss."""
    check = ionization_model_cross_check(_species(ACETIC, 7.4), [_acid_site(atom=2)], 7.4)
    assert _only(check).verdict == AGREES


def test_a_real_carboxyl_disagreement_is_still_caught_on_either_oxygen():
    """The narrow half: 'any equivalent atom' must not become 'always agree'."""
    neutral = Chem.MolFromSmiles(ACETIC)  # a species left neutral at 7.4
    for atom in (2, 3):
        assert _only(ionization_model_cross_check(neutral, [_acid_site(atom)], 7.4)).verdict == DISAGREES


def test_a_polyprotic_molecule_is_compared_site_by_site_with_no_net_charge():
    species = _species("NCC(=O)O", 7.4)  # 0 N ... 4 O
    predictions = [
        PkaPrediction(atom_index=4, value=3.83, protonated_site=(1, 0), deprotonated_site=(0, -1)),
        PkaPrediction(atom_index=0, value=9.81, protonated_site=(3, 1), deprotonated_site=(2, 0)),
    ]
    check = ionization_model_cross_check(species, predictions, 7.4)
    assert [(s.atom_index, s.verdict) for s in check.sites] == [(4, AGREES), (0, AGREES)]
    assert cross_check_lines(check, 7.4) == ()


# --- what is NOT compared, and says why ----------------------------------------------


def test_exactly_at_the_pka_is_not_compared_and_still_reports_the_distance():
    site = _only(ionization_model_cross_check(_species(ACETIC, 4.76), [_acid_site()], 4.76))
    assert site.verdict == NOT_COMPARED
    assert site.reason == "exactly at the model's transition point"
    assert site.distance == 0.0


def test_no_pkasolver_is_not_configured_rather_than_agreement():
    check = ionization_model_cross_check(_species(ACETIC, 7.4), None, 7.4)
    assert (check.status, check.sites) == ("not configured", ())


def test_a_payload_from_before_the_microstates_is_not_compared():
    old = PkaPrediction(atom_index=3, value=4.76)
    site = _only(ionization_model_cross_check(_species(ACETIC, 7.4), [old], 7.4))
    assert (site.verdict, site.reason) == (NOT_COMPARED, "the pKa runner sent no microstates for this site")


def test_an_unmapped_site_is_not_compared():
    unmapped = PkaPrediction(atom_index=None, value=4.76, protonated_site=(1, 0), deprotonated_site=(0, -1))
    site = _only(ionization_model_cross_check(_species(ACETIC, 7.4), [unmapped], 7.4))
    assert site.verdict == NOT_COMPARED and "could not be placed" in site.reason


# --- the payload the runner sends ------------------------------------------------------


def test_the_runners_microstates_become_the_encoded_site_states(monkeypatch, tmp_path):
    import json
    import subprocess

    interpreter = tmp_path / "python.exe"
    interpreter.write_text("")

    def tag(smiles):
        mol = Chem.MolFromSmiles(smiles)
        for atom in mol.GetAtoms():
            atom.SetAtomMapNum(atom.GetIdx() + 1)
        return Chem.MolToSmiles(mol)

    payload = {
        "pkas": [{
            "pka": 3.2, "atom_idx": 1, "stddev": 0.64,
            "site_smiles": tag("C1[NH2+]OO1"),
            "protonated_smiles": tag("C1[NH2+]OO1"),
            "deprotonated_smiles": tag("C1NOO1"),
        }],
        "pkasolver_version": "0+untagged.1.ga6ec86e",
    }
    monkeypatch.setattr(
        pka_providers.subprocess, "run",
        lambda argv, **_k: subprocess.CompletedProcess(argv, 0, stdout=json.dumps(payload), stderr=""),
    )
    (prediction,) = pka_providers.compute_pka(Chem.MolFromSmiles("O1OCN1"), str(interpreter))
    assert Chem.MolFromSmiles("O1OCN1").GetAtomWithIdx(prediction.atom_index).GetSymbol() == "N"
    assert (prediction.protonated_site, prediction.deprotonated_site) == ((2, 1), (1, 0))
    assert prediction.model_version == "0+untagged.1.ga6ec86e"


# --- the real sidecar, when there is one to ask ------------------------------------------


@pytest.mark.skipif(
    not os.environ.get("OPENCHEM_PKASOLVER_PYTHON"),
    reason="set OPENCHEM_PKASOLVER_PYTHON to a pkasolver environment's interpreter",
)
def test_the_real_sidecar_disagrees_with_dimorphite_on_the_reported_ring():
    interpreter = os.environ["OPENCHEM_PKASOLVER_PYTHON"]
    drawing = Chem.MolFromSmiles("O1OCN1")
    predictions = pka_providers.compute_pka(drawing, interpreter)
    check = ionization_model_cross_check(dominant_microspecies(drawing, 7.4).mol, predictions, 7.4)
    assert [(s.element, s.verdict) for s in check.sites] == [("N", DISAGREES)]
    assert check.model_version != "unknown"


# --- no number changes: the cross-check is a declaration, not a computation -----------------


def _disagreeing_pkasolver(monkeypatch):
    """The SAME fake on both arms, so logD takes the same branch each time."""
    monkeypatch.setattr(pka_providers, "pka_predictor_available", lambda _path: True)
    monkeypatch.setattr(
        pka_providers, "compute_pka",
        lambda _mol, _path: [PkaPrediction(atom_index=3, value=3.2, stddev=0.64,
                                           protonated_site=(2, 1), deprotonated_site=(1, 0))],
    )


def test_logd_changes_no_number_when_the_cross_check_speaks(monkeypatch):
    from openchem.chem import descriptor_providers
    from openchem.chem.descriptor_providers import compute_logd
    from openchem.chem.pka_providers import IonizationCrossCheck

    _disagreeing_pkasolver(monkeypatch)
    mol = Chem.MolFromSmiles("O1OCN1")
    spoken = compute_logd(mol, "u", {"pH": 7.4}, "x")
    assert any(line.startswith("Ionization-model cross-check") for line in spoken.limitations), (
        "setup: the cross-check said nothing, so this compares nothing"
    )

    monkeypatch.setattr(
        descriptor_providers, "ionization_cross_check_for",
        lambda *_a, **_k: IonizationCrossCheck(status="pkasolver"),
    )
    silent = compute_logd(mol, "u", {"pH": 7.4}, "x")

    assert [(f.label, f.value, f.display_value) for f in spoken.facts] == [
        (f.label, f.value, f.display_value) for f in silent.facts
    ]
    assert spoken.charts == silent.charts
    assert [line for line in spoken.limitations if not line.startswith("Ionization-model")] == list(
        silent.limitations
    )


def test_logd_through_the_registry_declares_the_disagreement(monkeypatch):
    """THROUGH THE REGISTRY: a direct-import test once passed while the
    registration bound to a different callable."""
    from openchem.chem.descriptor_providers import CALCULATOR_DEFINITIONS
    from openchem.services.calculator_registry import CalculatorRegistry

    _disagreeing_pkasolver(monkeypatch)
    registry = CalculatorRegistry()
    for definition in CALCULATOR_DEFINITIONS:
        if definition.calculator_id == "logd":
            registry.register(definition)
    result = registry.compute("logd", Chem.MolFromSmiles("O1OCN1"), "u", {"pH": 7.4})
    assert any("pkasolver predicts atom 4 (N) deprotonated" in line for line in result.limitations)
    assert result.provenance.parameters["ionization_cross_check"] == "pkasolver"
    assert result.provenance.parameters["ionization_cross_check_sites"][0]["verdict"] == DISAGREES


def test_the_charges_change_no_number_when_the_cross_check_speaks(monkeypatch):
    from openchem.chem import descriptor_providers
    from openchem.chem.descriptor_providers import compute_gasteiger_charge_at_ph
    from openchem.chem.pka_providers import IonizationCrossCheck

    _disagreeing_pkasolver(monkeypatch)
    mol = Chem.MolFromSmiles("O1OCN1")
    spoken = compute_gasteiger_charge_at_ph(mol, "u", {"pH": 7.4}, "x")
    assert "Ionization-model cross-check" in spoken.provenance.parameters["summary"], (
        "setup: the cross-check said nothing, so this compares nothing"
    )

    monkeypatch.setattr(
        descriptor_providers, "_cross_check_species",
        lambda *_a, **_k: IonizationCrossCheck(status="pkasolver"),
    )
    silent = compute_gasteiger_charge_at_ph(mol, "u", {"pH": 7.4}, "x")

    assert spoken.values == silent.values
    moved = {
        key for key in set(spoken.provenance.parameters) | set(silent.provenance.parameters)
        if spoken.provenance.parameters.get(key) != silent.provenance.parameters.get(key)
    }
    assert moved <= {"summary", "ionization_cross_check_sites"}, moved


def test_the_application_hands_the_charge_calculator_its_pkasolver(monkeypatch, tmp_path):
    """THE BINDING, not the function: the interpreter reaches the charges only
    through `_CALCULATOR_INTERPRETER_SETTING`, so this goes through the real
    container and the setting a user configures."""
    from openchem.app.settings import Settings
    from openchem.bootstrap import build_service_container
    from openchem.events.base import EventBus

    interpreter = tmp_path / "python.exe"
    interpreter.write_text("")
    Settings(EventBus()).set(pka_providers.PKASOLVER_PYTHON_SETTING, str(interpreter))
    seen = []

    def fake_compute_pka(mol, path, **_kwargs):
        seen.append(path)
        return [PkaPrediction(atom_index=3, value=3.2, protonated_site=(2, 1), deprotonated_site=(1, 0))]

    monkeypatch.setattr(pka_providers, "compute_pka", fake_compute_pka)
    registry = build_service_container().calculator_registry
    result = registry.compute("gasteiger_charge_at_ph", Chem.MolFromSmiles("O1OCN1"), "u", {"pH": 7.4})

    assert seen == [str(interpreter)]
    assert "pkasolver predicts atom 4 (N) deprotonated" in result.provenance.parameters["summary"]


def test_a_kept_pkasolver_answer_is_mapped_onto_each_callers_own_atoms(monkeypatch, tmp_path):
    """The cache keeps the RAW answer: the same molecule drawn in another atom
    order must get its own indices, not the first caller's."""
    import json
    import subprocess

    pka_providers.clear_pka_cache()
    interpreter = tmp_path / "python.exe"
    interpreter.write_text("")

    def tag(smiles):
        mol = Chem.MolFromSmiles(smiles)
        for atom in mol.GetAtoms():
            atom.SetAtomMapNum(atom.GetIdx() + 1)
        return Chem.MolToSmiles(mol)

    payload = {"pkas": [{"pka": 4.76, "atom_idx": 3, "site_smiles": tag("CC(=O)[O-]"),
                         "protonated_smiles": tag("CC(=O)O"), "deprotonated_smiles": tag("CC(=O)[O-]")}]}
    calls = []

    def fake_run(argv, **_kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(pka_providers.subprocess, "run", fake_run)
    forwards = Chem.MolFromSmiles("CC(=O)O")
    backwards = Chem.RenumberAtoms(forwards, [3, 2, 1, 0])

    (first,) = pka_providers.compute_pka(forwards, str(interpreter))
    (second,) = pka_providers.compute_pka(backwards, str(interpreter))

    assert len(calls) == 1, "the second drawing of the same molecule ran pkasolver again"
    assert forwards.GetAtomWithIdx(first.atom_index).GetSymbol() == "O"
    assert backwards.GetAtomWithIdx(second.atom_index).GetSymbol() == "O"
    assert first.atom_index != second.atom_index, "setup: the two drawings number the oxygen alike"


def test_a_failure_is_never_kept(monkeypatch, tmp_path):
    import subprocess

    pka_providers.clear_pka_cache()
    interpreter = tmp_path / "python.exe"
    interpreter.write_text("")
    outcomes = iter([
        subprocess.CompletedProcess([], 1, stdout='{"error": "boom"}', stderr=""),
        subprocess.CompletedProcess([], 0, stdout='{"pkas": []}', stderr=""),
    ])
    monkeypatch.setattr(pka_providers.subprocess, "run", lambda argv, **_k: next(outcomes))

    with pytest.raises(RuntimeError, match="boom"):
        pka_providers.compute_pka(Chem.MolFromSmiles("CCO"), str(interpreter))
    assert pka_providers.compute_pka(Chem.MolFromSmiles("CCO"), str(interpreter)) == []


def test_a_check_that_must_really_run_bypasses_the_kept_answer(monkeypatch, tmp_path):
    import subprocess

    pka_providers.clear_pka_cache()
    interpreter = tmp_path / "python.exe"
    interpreter.write_text("")
    calls = []

    def fake_run(argv, **_kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout='{"pkas": []}', stderr="")

    monkeypatch.setattr(pka_providers.subprocess, "run", fake_run)
    mol = Chem.MolFromSmiles("CCO")
    pka_providers.compute_pka(mol, str(interpreter))
    pka_providers.compute_pka(mol, str(interpreter), use_cache=False)
    assert len(calls) == 2
