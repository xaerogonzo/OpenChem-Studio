"""Phase 29: naming.

Network-dependent tests are marked and skipped by default -- the suite
must stay runnable offline. The parsing logic they would exercise is
covered separately with recorded payloads, including the two failure modes
that return HTTP 200 and look like success.
"""

from __future__ import annotations

import json
import urllib.error
from unittest.mock import patch

import pytest
from rdkit import Chem

from openchem.chem.naming_providers import (
    EXACT,
    PARSED,
    PREDICTED,
    NameResult,
    NamingError,
    _first_property_record,
    compute_iupac_name,
    describe_opsin_status,
    opsin_available,
    pubchem_name_for_structure,
    pubchem_structure_for_name,
    verify_name_round_trip,
)
from openchem.chem.stout_providers import (
    _parse_runner_output,
    describe_stout_status,
    stout_available,
)
from openchem.domain.common import CacheState

ASPIRIN = "CC(=O)Oc1ccccc1C(=O)O"


# --- The failure modes that look like success ---------------------------


def test_cid_zero_is_treated_as_not_found():
    """CONFIRMED LIVE: a structure PubChem does not know comes back as
    HTTP 200 with {"CID": 0} and no properties. Without this check an
    unknown structure reads as a successful lookup returning no name."""
    payload = {"PropertyTable": {"Properties": [{"CID": 0}]}}

    with pytest.raises(NamingError, match="no record for this structure"):
        _first_property_record(payload)


def test_a_real_record_passes_through():
    record = _first_property_record(
        {"PropertyTable": {"Properties": [{"CID": 2244, "IUPACName": "2-acetyloxybenzoic acid"}]}}
    )
    assert record["IUPACName"] == "2-acetyloxybenzoic acid"


def test_an_empty_property_table_is_an_error_not_an_empty_name():
    with pytest.raises(NamingError):
        _first_property_record({"PropertyTable": {"Properties": []}})


def test_a_record_without_a_name_field_is_reported_not_returned_blank():
    """PubChem can hold a structure with no IUPAC name assigned. Returning
    an empty string would look like a successful naming."""
    payload = {"PropertyTable": {"Properties": [{"CID": 1234}]}}
    with patch("openchem.chem.naming_providers._pubchem", return_value=payload):
        with pytest.raises(NamingError, match="no IUPAC name"):
            pubchem_name_for_structure(Chem.MolFromSmiles(ASPIRIN))


def test_a_null_smiles_is_reported_not_returned_blank():
    """CanonicalSMILES and IsomericSMILES still resolve but return null;
    the live property is SMILES. A null would otherwise surface as a
    successful lookup with an empty structure."""
    payload = {"PropertyTable": {"Properties": [{"CID": 2244, "SMILES": None}]}}
    with patch("openchem.chem.naming_providers._pubchem", return_value=payload):
        with pytest.raises(NamingError, match="no structure"):
            pubchem_structure_for_name("aspirin")


# --- Network error handling --------------------------------------------


def test_a_404_becomes_a_readable_not_found():
    error = urllib.error.HTTPError("url", 404, "Not Found", {}, None)
    with patch("urllib.request.urlopen", side_effect=error):
        with pytest.raises(NamingError, match="no record matching"):
            pubchem_structure_for_name("notarealcompound")


def test_an_unreachable_network_is_reported_as_such():
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("offline")):
        with pytest.raises(NamingError, match="Could not reach PubChem"):
            pubchem_name_for_structure(Chem.MolFromSmiles(ASPIRIN))


def test_an_empty_name_is_rejected_before_a_request_is_made():
    with patch("urllib.request.urlopen", side_effect=AssertionError("should not be called")):
        with pytest.raises(NamingError, match="Enter a name"):
            pubchem_structure_for_name("   ")


# --- Round-trip verification -------------------------------------------


def test_round_trip_returns_none_when_no_parser_is_available():
    """None (could not check) is deliberately distinct from False (checked
    and failed) -- claiming a failed check would be a false negative."""
    with patch("openchem.chem.naming_providers.opsin_available", return_value=False):
        assert verify_name_round_trip("anything", Chem.MolFromSmiles(ASPIRIN)) is None


def test_round_trip_is_true_when_the_name_parses_back_to_the_same_structure():
    from openchem.chem.naming_providers import StructureResult

    with patch("openchem.chem.naming_providers.opsin_available", return_value=True), patch(
        "openchem.chem.naming_providers.opsin_structure_for_name",
        return_value=StructureResult(smiles=ASPIRIN, source="OPSIN", kind=PARSED),
    ):
        assert verify_name_round_trip("2-acetyloxybenzoic acid", Chem.MolFromSmiles(ASPIRIN)) is True


def test_round_trip_is_false_when_the_name_parses_to_something_else():
    """The check that catches a fluent, confident, wrong STOUT name."""
    from openchem.chem.naming_providers import StructureResult

    with patch("openchem.chem.naming_providers.opsin_available", return_value=True), patch(
        "openchem.chem.naming_providers.opsin_structure_for_name",
        return_value=StructureResult(smiles="CCO", source="OPSIN", kind=PARSED),
    ):
        assert verify_name_round_trip("ethanol", Chem.MolFromSmiles(ASPIRIN)) is False


# --- Optional-capability reporting -------------------------------------


def test_opsin_status_names_what_is_missing():
    status = describe_opsin_status()
    assert opsin_available() or "Java" in status or "py2opsin" in status


def test_stout_is_unavailable_without_a_configured_interpreter():
    assert not stout_available("")
    assert not stout_available(None)
    assert "not configured" in describe_stout_status("").lower()


def test_stout_runner_output_is_taken_from_the_last_brace_line():
    """TensorFlow prints banners and progress bars to stdout on import, so
    the JSON payload is never the only thing there."""
    stdout = (
        "2024-01-01 oneDNN custom operations are on...\n"
        "{\"not\": \"the payload\"}\n"
        "1/1 [==============================] - 0s\n"
        '{"name": "ethanol"}\n'
    )
    assert _parse_runner_output(stdout, "", 0) == {"name": "ethanol"}


def test_stout_runner_with_no_json_raises_with_the_tail():
    with pytest.raises(RuntimeError, match="no usable output"):
        _parse_runner_output("traceback nonsense\n", "boom", 1)


# --- The calculator -----------------------------------------------------


def test_calculator_labels_each_source_with_its_kind():
    with patch(
        "openchem.chem.naming_providers.pubchem_name_for_structure",
        return_value=NameResult(name="2-acetyloxybenzoic acid", source="PubChem", kind=EXACT),
    ):
        result = compute_iupac_name(Chem.MolFromSmiles(ASPIRIN), "mol-1", {"use_pubchem": True})

    joined = "\n".join(result.matched)
    assert "2-acetyloxybenzoic acid" in joined
    assert "PubChem" in joined and EXACT in joined


def test_calculator_can_be_run_without_touching_the_network():
    """PubChem lookup sends the structure to NCBI, so it must be possible
    to turn off -- unpublished structures are a real concern."""
    with patch(
        "urllib.request.urlopen", side_effect=AssertionError("network must not be touched")
    ):
        result = compute_iupac_name(Chem.MolFromSmiles(ASPIRIN), "mol-1", {"use_pubchem": False})

    assert result.cache_state == CacheState.FAILED
    assert any("STOUT" in line for line in result.matched)


def test_calculator_reports_why_each_source_produced_nothing():
    with patch(
        "openchem.chem.naming_providers.pubchem_name_for_structure",
        side_effect=NamingError("PubChem has no record for this structure."),
    ):
        result = compute_iupac_name(Chem.MolFromSmiles(ASPIRIN), "mol-1", {"use_pubchem": True})

    joined = "\n".join(result.matched)
    assert "no record" in joined
    assert "STOUT" in joined  # says it isn't configured rather than staying silent


def test_a_predicted_name_is_flagged_as_predicted():
    with patch(
        "openchem.chem.naming_providers.pubchem_name_for_structure",
        side_effect=NamingError("nope"),
    ), patch("openchem.chem.naming_providers.stout_is_configured", return_value=True), patch(
        "openchem.chem.naming_providers.stout_name_for_structure",
        return_value=NameResult(name="made up name", source="STOUT", kind=PREDICTED),
    ):
        result = compute_iupac_name(Chem.MolFromSmiles(ASPIRIN), "mol-1", {"use_pubchem": True})

    assert any(PREDICTED in line for line in result.matched)


def test_naming_results_carry_no_numeric_confidence():
    """No engine here reports a calibrated confidence, and inventing one
    would be the fabricated precision this project has refused elsewhere."""
    assert not hasattr(NameResult(name="x", source="y", kind=EXACT), "confidence")


# --- Live network (opt-in) ----------------------------------------------


@pytest.mark.skip(reason="hits the network; run manually with --no-skip equivalents")
def test_live_pubchem_round_trip():  # pragma: no cover - manual
    original = Chem.MolFromSmiles(ASPIRIN)
    name = pubchem_name_for_structure(original)
    back = Chem.MolFromSmiles(pubchem_structure_for_name(name.name).smiles)
    assert Chem.MolToSmiles(back) == Chem.MolToSmiles(original)


def test_naming_result_lines_stay_ascii():
    """These land in AlertResult.matched, which reaches logs and console
    streams as well as Qt. A Windows cp1252 stream raises
    UnicodeEncodeError on an em-dash -- hit three times this session."""
    with patch(
        "openchem.chem.naming_providers.pubchem_name_for_structure",
        side_effect=NamingError("no record"),
    ):
        result = compute_iupac_name(Chem.MolFromSmiles(ASPIRIN), "mol-1", {"use_pubchem": True})

    for line in result.matched:
        line.encode("cp1252")
