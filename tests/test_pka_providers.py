from __future__ import annotations

import pytest
from rdkit import Chem

from openchem.chem.pka_providers import compute_pka, pka_predictor_available, protonate_at_ph


def test_acetic_acid_is_neutral_at_low_ph():
    mol = Chem.MolFromSmiles("CC(=O)O")
    protonated = protonate_at_ph(mol, 2.0)
    assert Chem.MolToSmiles(protonated) == Chem.CanonSmiles("CC(=O)O")


def test_acetic_acid_is_deprotonated_at_physiological_ph():
    """Acetic acid's real pKa is ~4.76 -- deprotonated well above that,
    confirmed live against the actual Dimorphite-DL install."""
    mol = Chem.MolFromSmiles("CC(=O)O")
    protonated = protonate_at_ph(mol, 7.4)
    assert Chem.MolToSmiles(protonated) == Chem.CanonSmiles("CC(=O)[O-]")


def test_acetic_acid_stays_deprotonated_at_high_ph():
    mol = Chem.MolFromSmiles("CC(=O)O")
    protonated = protonate_at_ph(mol, 12.0)
    assert Chem.MolToSmiles(protonated) == Chem.CanonSmiles("CC(=O)[O-]")


def test_pka_predictor_unavailable_when_nothing_configured():
    """pkasolver runs out of process from its own environment (Phase 23):
    it needs numpy<2 while this app runs numpy 2.x, so it is configured as
    an external tool rather than imported. No configured path means no
    numeric pKa -- honestly reported, not a hardcoded stub."""
    assert pka_predictor_available(None) is False
    assert pka_predictor_available("") is False


def test_pka_predictor_unavailable_for_a_nonexistent_interpreter(tmp_path):
    assert pka_predictor_available(str(tmp_path / "does-not-exist.exe")) is False


def test_pka_predictor_available_for_a_real_file(tmp_path):
    fake = tmp_path / "python.exe"
    fake.write_text("")
    assert pka_predictor_available(str(fake)) is True


def test_compute_pka_returns_none_when_nothing_is_configured():
    """None means "not installed" -- distinct from an empty list, which
    would mean "ran, found no ionizable centre"."""
    mol = Chem.MolFromSmiles("CC(=O)O")
    assert compute_pka(mol, None) is None


def test_compute_pka_raises_when_a_configured_interpreter_fails(tmp_path):
    """A configured-but-broken environment must report a real error rather
    than degrade into the same silent state as "not configured"."""
    fake = tmp_path / "python.exe"
    fake.write_text("")  # exists, but is not a runnable interpreter
    mol = Chem.MolFromSmiles("CC(=O)O")

    with pytest.raises(RuntimeError):
        compute_pka(mol, str(fake))


def test_runner_output_parser_extracts_json_after_dependency_banners():
    """pkasolver's dependencies print citation/progress banners to stdout,
    so the JSON payload is the last brace-line, not the whole stream."""
    from openchem.chem.pka_providers import _parse_runner_output

    stdout = 'Dimorphite-DL citation banner\nloading models...\n{"pkas": [{"pka": 4.82, "atom_idx": 12}]}\n'
    payload = _parse_runner_output(stdout, "", 0)

    assert payload["pkas"][0]["pka"] == 4.82


def test_runner_output_parser_raises_on_a_structured_error():
    from openchem.chem.pka_providers import _parse_runner_output

    with pytest.raises(RuntimeError, match="boom"):
        _parse_runner_output('{"error": "boom"}', "", 1)


def test_runner_output_parser_raises_when_there_is_no_payload():
    from openchem.chem.pka_providers import _parse_runner_output

    with pytest.raises(RuntimeError, match="no usable output"):
        _parse_runner_output("just banners, no json\n", "traceback here", 1)


def test_describe_pka_status_reports_not_configured():
    from openchem.chem.pka_providers import describe_pka_status

    assert "Not configured" in describe_pka_status("")
