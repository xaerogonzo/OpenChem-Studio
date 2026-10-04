"""What the validation record authorizes: a percentage, only for the exact model and criteria it was made under.

The record (`chem/data/tautomer_validation_record_v2.json`) is derived from the committed artifact and
consulted by the service when a tautomer distribution finishes. Everything here is about the matching:
a record that is almost right must authorize nothing.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest
from rdkit import Chem

from openchem import paths as app_paths
from openchem.chem.tautomer_distribution import (
    MODEL_POLICY_FULL,
    MODEL_POLICY_TOPK,
    VALIDATION_RANKING_ONLY,
    VALIDATION_UNVALIDATED,
    VALIDATION_VALIDATED,
    ModelPolicy,
    generate_tautomer_candidates,
    model_version,
)
from openchem.chem.tautomer_validation import (
    RECORD_PATH_V2,
    SPEC_PATH_V2,
    artifact_sha256,
    load_records,
    load_spec,
    parse_spec,
    record_from_artifact,
    validation_branch_for,
)
from openchem.domain.calculator import DRAWING
from openchem.events.events import TautomerDistributionResultReady

sys.path.insert(0, str(Path(__file__).parent))
from test_tautomer_distribution_service import (  # noqa: E402
    _FAKE_DRAWING_FINGERPRINT,
    CYCLOHEXANONE,
    _make_service,
    _PerCandidateProvider,
)
from test_quantum_chemistry_service import _wait_until  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
#: The model the passed run validated, spelled out so the test does not call the builder it is checking.
VALIDATED_METHOD = "M062X def2-TZVP"


@pytest.fixture(scope="module")
def record():
    return json.loads(RECORD_PATH_V2.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def spec():
    return load_spec(SPEC_PATH_V2)


@pytest.fixture(autouse=True)
def _scratch_under_tmp_path(tmp_path, monkeypatch):
    root = tmp_path / "data-root"
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv(app_paths.DATA_ROOT_ENV_VAR, str(root))


def _version(method=VALIDATED_METHOD, policy=MODEL_POLICY_TOPK):
    return model_version(method, "ETKDGv3", 298.15, policy)


# --- the record is derived, never edited -------------------------------------------------------


def test_the_record_is_exactly_what_the_committed_artifact_derives(record):
    artifact_path = ROOT / record["artifact"]["path"]
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert artifact_sha256(artifact_path) == record["artifact"]["sha256"]
    assert record == record_from_artifact(artifact, record["artifact"]["path"], record["artifact"]["sha256"])


def test_the_record_is_of_the_model_and_criteria_this_code_has(record, spec):
    assert record["model_version"] == _version()
    assert (record["validation_criteria_version"], record["criteria_hash"]) == (
        spec.criteria_version, spec.criteria_hash,
    )
    assert record["reference_bundle_hash"] == spec.reference_bundle_hash
    assert record["validation_execution_status"] == "complete" and record["validation_gate_outcome"] == "passed"
    assert record["partial_run"] is False


# --- the matching ------------------------------------------------------------------------------


def test_the_validated_model_earns_validated_when_its_result_is_complete():
    assert validation_branch_for(_version(), True) == VALIDATION_VALIDATED


def test_an_incomplete_result_of_the_validated_model_shows_energies_never_a_percentage():
    assert validation_branch_for(_version(), False) == VALIDATION_RANKING_ONLY


@pytest.mark.parametrize(
    "version",
    [
        _version("HF STO-3G"),  # another method
        _version("PBE0 def2-TZVP"),
        _version(policy=MODEL_POLICY_FULL),  # full-ORCA conformers: a different model
        _version(policy=ModelPolicy(conformer_topk=4)),
        _version(policy=ModelPolicy(conformer_embeds=51)),
        _version(policy=ModelPolicy(conformer_prefilter_max_iters=2001)),
        _version(policy=ModelPolicy(stereo_cap=9)),
        _version().replace("tautomer-boltzmann-v5", "tautomer-boltzmann-v6"),  # another revision
        _version().replace("T=298.15K", "T=300K"),
        _version().replace("rdkit-", "rdkit-1999."),  # another RDKit release
    ],
)
def test_a_changed_model_is_unvalidated_whatever_the_record_says(version):
    assert version != _version()
    assert validation_branch_for(version, True) == VALIDATION_UNVALIDATED


def test_a_record_does_not_authorize_after_the_criteria_change():
    raw = json.loads(SPEC_PATH_V2.read_text(encoding="utf-8"))
    corrected = copy.deepcopy(raw)
    corrected["systems"][6]["tautomers"][1]["reference_kcal"] = 4.57
    corrected["systems"][6]["tautomers"][1]["variants"][0]["reference_kcal"] = 4.57
    assert validation_branch_for(_version(), True, spec=parse_spec(corrected)) == VALIDATION_UNVALIDATED
    retoleranced = copy.deepcopy(raw)
    retoleranced["gates"]["mae_tolerance_kcal"] = 1.5
    assert validation_branch_for(_version(), True, spec=parse_spec(retoleranced)) == VALIDATION_UNVALIDATED
    renamed = copy.deepcopy(raw)
    renamed["validation_criteria_version"] = "tautomer-validation-criteria-v3"
    assert validation_branch_for(_version(), True, spec=parse_spec(renamed)) == VALIDATION_UNVALIDATED


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ({"validation_gate_outcome": "attempted_failed"}, VALIDATION_UNVALIDATED),
        ({"validation_gate_outcome": "not_evaluable"}, VALIDATION_UNVALIDATED),
        ({"validation_gate_outcome": "ranking_only"}, VALIDATION_RANKING_ONLY),
        ({"validation_execution_status": "incomplete"}, VALIDATION_UNVALIDATED),
        ({"partial_run": True}, VALIDATION_UNVALIDATED),
        ({"record_schema": 2}, VALIDATION_UNVALIDATED),
    ],
)
def test_only_a_complete_whole_run_that_decided_so_authorizes(record, change, expected):
    assert validation_branch_for(_version(), True, records=[{**record, **change}]) == expected


def test_no_record_means_unvalidated_and_an_unreadable_one_is_skipped_not_fatal(tmp_path):
    assert validation_branch_for(_version(), True, records=[]) == VALIDATION_UNVALIDATED
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    assert load_records([broken, tmp_path / "missing.json"]) == ()


def test_the_frozen_build_ships_both_files():
    """A data file that works from a checkout and is missing from the installer is this project's
    established failure mode, and here it would be invisible: every result would just read unvalidated."""
    spec_text = (ROOT / "packaging" / "openchem.spec").read_text(encoding="utf-8")
    assert "tautomer_validation_v2.json" in spec_text
    assert "tautomer_validation_record_v2.json" in spec_text


# --- through the service -----------------------------------------------------------------------


def _run(qapp, *, method, policy, fail_at=None):
    candidates, _ = generate_tautomer_candidates(Chem.MolFromSmiles(CYCLOHEXANONE), policy=policy)
    energies = [-100.0 + 0.001 * i for i in range(len(candidates))]
    provider = _PerCandidateProvider(energies=energies, fail_to_parse_at={fail_at} if fail_at is not None else None)
    service, bus = _make_service(provider)
    results = []
    bus.subscribe(TautomerDistributionResultReady, results.append)
    service.request_tautomer_distribution(
        candidates=candidates,
        molecule_uuid="mol-validated",
        charge=0,
        multiplicity=1,
        method_basis=method,
        calculation_input=DRAWING,
        input_fingerprint=_FAKE_DRAWING_FINGERPRINT,
        provider_id="fake",
        policy=policy,
    )
    assert _wait_until(qapp, lambda: results)
    return results[0].result


def test_the_service_stamps_validated_and_a_percentage_for_the_validated_model(qapp):
    result = _run(qapp, method=VALIDATED_METHOD, policy=MODEL_POLICY_TOPK)
    params = result.provenance.parameters
    assert params["validation_branch"] == VALIDATION_VALIDATED and params["complete"] is True
    assert params["model_version"] == _version()
    populations = [e.score for e in result.entries if e.score is not None]
    assert populations and sum(populations) == pytest.approx(1.0)


def test_the_service_withholds_the_percentage_for_any_other_model(qapp):
    for method, policy in (("HF STO-3G", MODEL_POLICY_TOPK), (VALIDATED_METHOD, MODEL_POLICY_FULL)):
        result = _run(qapp, method=method, policy=policy)
        assert result.provenance.parameters["validation_branch"] == VALIDATION_UNVALIDATED
        assert all(e.score is None for e in result.entries)
        assert any(e.metadata.get("population_unvalidated") is not None for e in result.entries)


def test_one_failed_job_keeps_the_validated_model_from_showing_a_percentage(qapp):
    result = _run(qapp, method=VALIDATED_METHOD, policy=MODEL_POLICY_TOPK, fail_at=0)
    params = result.provenance.parameters
    assert params["complete"] is False and params["validation_branch"] == VALIDATION_RANKING_ONLY
    assert all(e.score is None for e in result.entries)
