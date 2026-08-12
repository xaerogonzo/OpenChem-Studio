"""Phase 29: naming.

Network-dependent tests are marked and skipped by default -- the suite
must stay runnable offline. The parsing logic they would exercise is
covered separately with recorded payloads, including the two failure modes
that return HTTP 200 and look like success.
"""

from __future__ import annotations

import json
import os
import urllib.error
from unittest.mock import patch

import pytest
from rdkit import Chem

from openchem.chem import naming_providers
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
    """404 is the one HTTP status with its own message, so it needs its own
    test.

    **THIS WAS A LIVE NETWORK CALL WEARING A MOCK'S CLOTHES.** It patched
    `urllib.request.urlopen`, which `_pubchem` does not call -- it calls
    `open_url`, and `openchem.net` binds `urlopen` at import time, so the
    global patch never intercepts anything. Measured:

        patch("urllib.request.urlopen")   NOT intercepted, real call went out
        patch(module attribute open_url)  intercepted

    So this asked the real PubChem for "notarealcompound" and passed only
    because the real PubChem answers 404. CI caught it the day PubChem was
    busy and answered 503 instead:

        Expected regex: 'no record matching'
        Actual message: 'PubChem returned HTTP 503.'

    The sibling below already documented this trap; it was fixed there and
    left here.
    """
    error = urllib.error.HTTPError("url", 404, "Not Found", {}, None)
    with patch("openchem.chem.naming_providers.open_url", side_effect=error):
        with pytest.raises(NamingError, match="no record matching"):
            pubchem_structure_for_name("notarealcompound")


def test_an_unreachable_network_is_reported_as_such():
    # Patched at the seam the module actually calls. Patching
    # `urllib.request.urlopen` used to work by accident and no longer
    # does -- `openchem.net` binds the name at import time, so a global
    # patch would silently let this hit the real PubChem servers.
    with patch(
        "openchem.chem.naming_providers.open_url",
        side_effect=urllib.error.URLError("offline"),
    ):
        with pytest.raises(NamingError, match="Could not reach PubChem"):
            pubchem_name_for_structure(Chem.MolFromSmiles(ASPIRIN))


def test_an_empty_name_is_rejected_before_a_request_is_made():
    """Patched at the seam the module calls, or the "before" in the name
    means nothing -- a global `urllib.request.urlopen` patch is never
    reached, so the tripwire could not have fired however late the
    rejection happened."""
    with patch(
        "openchem.chem.naming_providers.open_url",
        side_effect=AssertionError("should not be called"),
    ):
        with pytest.raises(NamingError, match="Enter a name"):
            pubchem_structure_for_name("   ")


# --- Round-trip verification -------------------------------------------


def test_round_trip_is_unverified_when_no_parser_is_available():
    """UNVERIFIED (could not check) is deliberately distinct from MISMATCH
    (checked and failed) -- claiming a failed check would be a false
    negative."""
    from openchem.chem.naming_providers import RoundTrip

    with patch("openchem.chem.naming_providers.opsin_available", return_value=False):
        assert verify_name_round_trip("anything", Chem.MolFromSmiles(ASPIRIN)) is (
            RoundTrip.UNVERIFIED
        )


def test_round_trip_is_true_when_the_name_parses_back_to_the_same_structure():
    from openchem.chem.naming_providers import StructureResult

    with patch("openchem.chem.naming_providers.opsin_available", return_value=True), patch(
        "openchem.chem.naming_providers.opsin_structure_for_name",
        return_value=StructureResult(smiles=ASPIRIN, source="OPSIN", kind=PARSED),
    ):
        from openchem.chem.naming_providers import RoundTrip

        assert verify_name_round_trip(
            "2-acetyloxybenzoic acid", Chem.MolFromSmiles(ASPIRIN)
        ) is RoundTrip.MATCH


def test_round_trip_is_false_when_the_name_parses_to_something_else():
    """The check that catches a fluent, confident, wrong STOUT name."""
    from openchem.chem.naming_providers import StructureResult

    with patch("openchem.chem.naming_providers.opsin_available", return_value=True), patch(
        "openchem.chem.naming_providers.opsin_structure_for_name",
        return_value=StructureResult(smiles="CCO", source="OPSIN", kind=PARSED),
    ):
        from openchem.chem.naming_providers import RoundTrip

        assert verify_name_round_trip("ethanol", Chem.MolFromSmiles(ASPIRIN)) is (
            RoundTrip.MISMATCH
        )


def test_round_trip_is_STEREO_OMITTED_when_the_name_cannot_express_the_stereo():
    """THE CASE THIS TAXONOMY EXISTS FOR.

    Reported after a conformer defined two bridgehead stereocentres: the
    nomenclature engine derived the SAME name before and after, that name
    cannot express bridgehead stereo, and so the comparison -- and only
    the comparison -- changed its mind and withheld it.

    The name is right about the skeleton and silent about stereochemistry
    the structure carries. That is a third thing, not a failure.
    """
    from openchem.chem.naming_providers import RoundTrip, StructureResult

    # The name parses to the flat skeleton; the structure is resolved.
    with patch("openchem.chem.naming_providers.opsin_available", return_value=True), patch(
        "openchem.chem.naming_providers.opsin_structure_for_name",
        return_value=StructureResult(smiles="CC(N)C(=O)O", source="OPSIN", kind=PARSED),
    ):
        verdict = verify_name_round_trip("alanine", Chem.MolFromSmiles("C[C@@H](N)C(=O)O"))

    assert verdict is RoundTrip.STEREO_OMITTED


def test_a_name_that_only_omits_stereo_is_SHOWN_with_what_it_omits(monkeypatch):
    """Shown rather than withheld -- withholding it reads as the namer
    being broken, which is exactly how this was reported. The caveat is
    what keeps it honest."""
    monkeypatch.setattr(
        naming_providers,
        "verify_name_round_trip",
        lambda name, mol: naming_providers.RoundTrip.STEREO_OMITTED,
    )

    result = naming_providers.derived_name_for_structure(
        Chem.MolFromSmiles("C[C@@H](N)C(=O)O")
    )

    assert result.name
    assert "stereochemistry" in result.note.lower()


# --- Optional-capability reporting -------------------------------------


def test_opsin_status_names_what_is_missing():
    status = describe_opsin_status()
    assert opsin_available() or "Java" in status or "py2opsin" in status


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
    to turn off -- unpublished structures are a real concern.

    **THE TRIPWIRE WAS ON THE WRONG SEAM, so this guarded nothing.** It
    patched `urllib.request.urlopen`, which `openchem.net.open_url` does
    not consult (it binds `urlopen` at import time), so a regression that
    sent every structure to NCBI with `use_pubchem: False` would have left
    this test green while the requests went out for real. Of the three
    tests in this file that made that mistake it is the one that mattered
    most: the other two assert a message, this one asserts a promise about
    where a user's unpublished structure does NOT go.
    """
    with patch(
        "openchem.chem.naming_providers.open_url",
        side_effect=AssertionError("network must not be touched"),
    ):
        result = compute_iupac_name(Chem.MolFromSmiles(ASPIRIN), "mol-1", {"use_pubchem": False})

    # Used to be FAILED: with the network off and STOUT gone, nothing
    # could name anything. The vendored nomenclature engine is offline and
    # deterministic, so the honest answer now is a real name.
    assert result.cache_state == CacheState.COMPLETED
    assert any("Nomenclature engine" in line for line in result.matched)


def test_calculator_reports_why_each_source_produced_nothing():
    with patch(
        "openchem.chem.naming_providers.pubchem_name_for_structure",
        side_effect=NamingError("PubChem has no record for this structure."),
    ):
        result = compute_iupac_name(Chem.MolFromSmiles(ASPIRIN), "mol-1", {"use_pubchem": True})

    joined = "\n".join(result.matched)
    assert "no record" in joined  # says why, rather than staying silent
    # ...and a structure PubChem cannot find still gets a name, which is the
    # entire reason for carrying a nomenclature engine.
    assert "Nomenclature engine" in joined


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


# --- The path that still works now STOUT is gone --------------------------


@pytest.mark.skipif(
    not naming_providers.opsin_available(),
    reason="needs py2opsin and a JRE",
)
def test_pubchem_name_round_trips_back_through_opsin():
    """With STOUT's weights withdrawn upstream, this IS the naming
    feature: PubChem gives an exact name for a known compound, and OPSIN
    parses it back to prove the name really denotes that structure.

    Hits the network, hence the marker -- but it is the only assertion
    that covers the two providers actually agreeing, which is the whole
    claim being made to the user.
    """
    aspirin = Chem.MolFromSmiles("CC(=O)Oc1ccccc1C(=O)O")

    name = naming_providers.pubchem_name_for_structure(aspirin)
    assert name.kind == naming_providers.EXACT

    parsed = naming_providers.opsin_structure_for_name(name.name)
    assert parsed.kind == naming_providers.PARSED
    assert Chem.MolToSmiles(Chem.MolFromSmiles(parsed.smiles)) == Chem.MolToSmiles(aspirin)


@pytest.mark.skipif(
    not naming_providers.opsin_available(),
    reason="needs py2opsin and a JRE",
)
def test_opsin_runs_without_emitting_a_bogus_java_warning(recwarn):
    """py2opsin probes `java -version` at IMPORT and warns when it fails.
    A runtime this app installed is on neither PATH nor JAVA_HOME, so the
    warning fired even though every call worked -- alarming and untrue.
    """
    naming_providers.opsin_structure_for_name("benzene")

    java_warnings = [w for w in recwarn if "Java may not be installed" in str(w.message)]
    assert java_warnings == []


def test_path_is_restored_after_opsin_runs():
    """The Java injection is scoped to the call. Leaking it would change
    which `java` every OTHER subprocess in the app resolves."""
    before = os.environ.get("PATH", "")
    with naming_providers._java_on_path():
        pass
    assert os.environ.get("PATH", "") == before


# --- The vendored deterministic nomenclature engine -----------------------


def test_a_derived_name_round_trips_to_the_structure_it_came_from():
    """The gate. A rule engine cannot be fluently wrong the way a model
    can, but it can still be wrong, and OPSIN is a cheap independent
    check -- the engine's own author uses the same one."""
    mol = Chem.MolFromSmiles("CC(=O)Oc1ccccc1C(=O)O")

    result = naming_providers.derived_name_for_structure(mol)

    assert result.kind == naming_providers.DERIVED
    assert result.source == "Nomenclature engine"
    parsed = naming_providers.opsin_structure_for_name(result.name)
    assert Chem.MolToSmiles(Chem.MolFromSmiles(parsed.smiles)) == Chem.MolToSmiles(mol)


def test_stereochemistry_survives_into_the_derived_name():
    """The single capability no ML model in the benchmark had. If this
    regresses, two enantiomers get the same name."""
    r_name = naming_providers.derived_name_for_structure(
        Chem.MolFromSmiles("C[C@H](O)C(=O)O")).name
    s_name = naming_providers.derived_name_for_structure(
        Chem.MolFromSmiles("C[C@@H](O)C(=O)O")).name

    assert r_name != s_name
    assert ("2S)" in r_name) or ("2R)" in r_name)


def test_it_names_a_structure_pubchem_has_never_seen():
    """The whole reason to carry a nomenclature engine at all -- PubChem
    covers the known world, this covers the rest."""
    novel = Chem.MolFromSmiles("O=C(Nc1ccc(-c2ccncc2)cc1)Nc1cccc(C(F)(F)F)c1")

    result = naming_providers.derived_name_for_structure(novel)

    assert "urea" in result.name
    parsed = naming_providers.opsin_structure_for_name(result.name)
    assert Chem.MolToSmiles(Chem.MolFromSmiles(parsed.smiles)) == Chem.MolToSmiles(novel)


def test_a_name_that_fails_the_round_trip_is_withheld(monkeypatch):
    """Withheld, not shown with a caveat. A wrong systematic name looks
    exactly as authoritative as a right one."""
    monkeypatch.setattr(
        naming_providers,
        "verify_name_round_trip",
        lambda name, mol: naming_providers.RoundTrip.MISMATCH,
    )

    with pytest.raises(naming_providers.NamingError, match="withheld"):
        naming_providers.derived_name_for_structure(Chem.MolFromSmiles("CCO"))


def test_the_calculator_reports_pubchem_and_the_engine_separately():
    """Never merged into one 'the name': a curated record and a derived
    name differ in authority, and one string would erase that."""
    result = naming_providers.compute_iupac_name(
        Chem.MolFromSmiles("CCO"), "uuid", {"use_pubchem": False})

    assert any("Nomenclature engine, derived" in line for line in result.matched)
    assert not any("STOUT" in line for line in result.matched), (
        "the STOUT notice is obsolete now the engine covers that job"
    )


# ---------------------------------------------------------------------------
# THE THREE PATHS TO `MISMATCH`
#
# `verify_name_round_trip` reaches MISMATCH from three places and only one is
# evidence against the name -- OPSIN failing to parse, and RDKit failing to
# build OPSIN's SMILES, are both the CHECKER failing. Splitting them so a
# checker-failure showed the name with a caveat was designed and then not
# built: over the 181-molecule corpus, ZERO inputs reach either
# checker-failed path (benchmarks/naming/round_trip_paths.py re-measures it).
#
# These hold the three apart so a future change cannot silently collapse
# them. **Each asserts HOW FAR THE PIPELINE GOT, not merely that the verdict
# was MISMATCH** -- three tests all asserting MISMATCH would pass against an
# implementation that had merged the branches into one, which is the exact
# regression they exist to catch. The verdict enum is the only public
# signal, so the branch is identified by observable facts about the
# dependencies instead; no reason field was invented purely for a test.
#
# They use controlled dependency failures rather than real molecules on
# purpose. These ARE dependency-failure paths, and hunting an input that
# triggers each one is the fixture hunt this project has already abandoned
# once. The corpus scan is the real-world layer underneath them.
# ---------------------------------------------------------------------------


def _spy_opsin(monkeypatch, behaviour):
    """Replace OPSIN with a recording double. Returns the call log."""
    calls: list[dict] = []

    def fake(name: str):
        record: dict = {"name": name}
        calls.append(record)
        result = behaviour(name)
        record["returned"] = result.smiles
        return result

    monkeypatch.setattr(naming_providers, "opsin_available", lambda: True)
    monkeypatch.setattr(naming_providers, "opsin_structure_for_name", fake)
    return calls


def test_mismatch_path_one_opsin_could_not_parse_our_name(monkeypatch):
    """The CHECKER failed: OPSIN never returned a structure at all."""
    from openchem.chem.naming_providers import NamingError, RoundTrip

    calls: list[str] = []

    def fake(name: str):
        calls.append(name)
        raise NamingError("OPSIN could not parse it")

    monkeypatch.setattr(naming_providers, "opsin_available", lambda: True)
    monkeypatch.setattr(naming_providers, "opsin_structure_for_name", fake)

    verdict = verify_name_round_trip("some-name", Chem.MolFromSmiles("CCO"))

    assert verdict is RoundTrip.MISMATCH
    # The distinguishing fact: OPSIN was reached and produced NOTHING, so
    # nothing downstream ever had a structure to compare.
    assert calls == ["some-name"], "OPSIN was not consulted at all"


def test_mismatch_path_two_rdkit_could_not_build_opsins_smiles(monkeypatch):
    """The CHECKER failed one step later: OPSIN answered, RDKit refused."""
    from openchem.chem.naming_providers import RoundTrip, StructureResult

    unparseable = "this-is-not-smiles"
    # ASSERT THE SETUP. If a future RDKit starts accepting this string the
    # test would silently exercise path three instead, and still pass.
    assert Chem.MolFromSmiles(unparseable) is None, "the fixture is no longer unparseable"

    calls = _spy_opsin(
        monkeypatch,
        lambda name: StructureResult(smiles=unparseable, source="OPSIN", kind=PARSED),
    )

    verdict = verify_name_round_trip("some-name", Chem.MolFromSmiles("CCO"))

    assert verdict is RoundTrip.MISMATCH
    # The distinguishing fact: OPSIN DID return, and what it returned is
    # what RDKit could not build.
    assert len(calls) == 1 and calls[0]["returned"] == unparseable


def test_mismatch_path_three_the_skeletons_genuinely_differ(monkeypatch):
    """The only path that is evidence against the NAME.

    This is the one metformin takes, and the one withholding exists for.
    """
    from openchem.chem.naming_providers import RoundTrip, StructureResult

    original, other = "CCO", "c1ccccc1"
    calls = _spy_opsin(
        monkeypatch,
        lambda name: StructureResult(smiles=other, source="OPSIN", kind=PARSED),
    )

    verdict = verify_name_round_trip("some-name", Chem.MolFromSmiles(original))

    assert verdict is RoundTrip.MISMATCH
    # The distinguishing facts: OPSIN returned, RDKit BUILT it, and the two
    # skeletons really are different -- so nothing failed except the match.
    assert len(calls) == 1 and calls[0]["returned"] == other
    assert Chem.MolFromSmiles(other) is not None, "path three needs a buildable SMILES"
    assert naming_providers._skeleton(Chem.MolFromSmiles(other)) != naming_providers._skeleton(
        Chem.MolFromSmiles(original)
    ), "the fixture no longer differs in skeleton, so this is not path three"
