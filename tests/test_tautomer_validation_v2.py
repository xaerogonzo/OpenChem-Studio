"""The criteria-v2 preregistration: frozen, closed, and honest about how v4 was designed.

No ORCA and no computed number here. What is pinned: the file's three content hashes, that its
tolerances are exactly v1's (never retuned), that its held-out rows ARE the frozen manifest, that
the model it declares is the model this code would run, and that v1 and its artifact are untouched.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from openchem.chem.tautomer_validation import (
    PARTITION_HELD_OUT,
    PARTITION_REGRESSION,
    SPEC_PATH,
    SPEC_PATH_V2,
    Gates,
    SystemRun,
    TautomerEnergy,
    ValidationSpecError,
    assert_no_computed,
    build_artifact,
    canonical_key,
    computed_kcal,
    evaluate_system,
    load_spec,
    model_mismatches,
    parse_spec,
    partition_summary,
    policy_of,
)
from openchem.chem.tautomer_distribution import HARTREE_TO_KCAL_PER_MOL

ROOT = Path(__file__).resolve().parent.parent
FROZEN_CRITERIA_HASH = "89ec9c055bdd3da040539cd05a74c853f61faf67210aa0e46c01b85b84574e8c"
FROZEN_BENCHMARK_SET_HASH = "c983b1898e84dff3de36ed6abb8741bf5fe0614701eeda6a0070b0194147f75c"
FROZEN_REFERENCE_BUNDLE_HASH = "f03d2e4f32122079da661a2e3f15621530e7ad47467771ef0d3ecde21a553a15"

#: Pinned in the spec AND here: the held-out manifest and the method-screen rule, as committed.
MANIFEST_SHA256 = "8a3932ca92480b6022b6c51a7b60a7fea47d3d921f61f2d51173efba7cb1c12d"
SCREEN_RULE_SHA256 = "8449dc1111403c908bd7a741a4d03afd6ec84d6e19f6aee7f83e97bfd7c72bc0"


def _lf_sha256(path: Path) -> str:
    """Line endings are normalized: a Windows checkout rewrites them, and the hash is of the content."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


@pytest.fixture(scope="module")
def spec():
    return load_spec(SPEC_PATH_V2)


@pytest.fixture
def raw():
    return json.loads(SPEC_PATH_V2.read_text(encoding="utf-8"))


def test_the_spec_loads_and_is_frozen(spec):
    assert spec.criteria_version == "tautomer-validation-criteria-v2"
    assert (spec.criteria_hash, spec.benchmark_set_hash, spec.reference_bundle_hash) == (
        FROZEN_CRITERIA_HASH, FROZEN_BENCHMARK_SET_HASH, FROZEN_REFERENCE_BUNDLE_HASH,
    )


def test_it_holds_no_computed_value(raw):
    assert_no_computed(raw)


def test_every_system_has_a_partition_and_the_held_out_ones_are_required(spec):
    partitions = {s.id: (s.partition, s.role) for s in spec.systems}
    assert {p for p, _ in partitions.values()} == {PARTITION_REGRESSION, PARTITION_HELD_OUT}
    assert [i for i, (p, r) in partitions.items() if p == PARTITION_HELD_OUT and r == "required"] == [
        "indazole", "hypoxanthine", "triazole_123", "triazole_124",
    ]
    assert sum(1 for p, r in partitions.values() if p == PARTITION_REGRESSION and r == "required") == 4


def test_the_tolerances_are_exactly_v1s_and_the_regression_rows_are_v1s_rows(raw):
    v1 = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    for key in ("reference_tie_kcal", "mae_tolerance_kcal", "max_error_tolerance_kcal", "ranking_rule",
                "quantitative_rule", "scope", "tied_pairs_in_quantitative_gate", "pooled_mae"):
        assert raw["gates"][key] == v1["gates"][key], key
    assert raw["quantity"] == v1["quantity"]
    carried = [{k: v for k, v in s.items() if k != "partition"} for s in raw["systems"]
               if s["partition"] == PARTITION_REGRESSION]
    assert carried == v1["systems"], "a carried-forward row must be v1's row, value for value"


def test_v1_and_its_artifact_are_untouched():
    artifact = json.loads(
        (ROOT / "benchmarks/tautomer_validation/tautomer_validation_artifact.json").read_text(encoding="utf-8")
    )
    v1 = load_spec(SPEC_PATH)
    identity = artifact["identity"]
    assert (v1.criteria_hash, v1.benchmark_set_hash, v1.reference_bundle_hash) == (
        identity["criteria_hash"], identity["benchmark_set_hash"], identity["reference_bundle_hash"],
    )
    assert artifact["validation_gate_outcome"] == "attempted_failed"


def test_the_held_out_rows_are_the_frozen_manifest(spec, raw):
    manifest_path = ROOT / raw["preregistration"]["selection_manifest"]["path"]
    assert _lf_sha256(manifest_path) == MANIFEST_SHA256 == raw["preregistration"]["selection_manifest"]["sha256"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    held_out = [s for s in spec.systems if s.partition == PARTITION_HELD_OUT]
    assert [s.id for s in held_out] == [m["id"] for m in manifest["systems"]]
    for system, entry in zip(held_out, manifest["systems"], strict=True):
        from_manifest = {canonical_key(t["smiles"]): t["reference_kcal_mol"] for t in entry["reference_tautomers"]}
        from_spec = {canonical_key(t.smiles): t.reference_kcal for t in system.tautomers}
        assert from_spec == from_manifest, system.id
        assert system.source["key"] == entry["reference_source"]["key"]
        assert system.reference["method"] == entry["reference_method"]


def test_the_method_screen_record_is_committed_and_its_rule_is_unchanged(raw):
    screen = raw["preregistration"]["method_screen"]
    assert _lf_sha256(ROOT / screen["rule_path"]) == SCREEN_RULE_SHA256 == screen["rule_sha256"]
    directory = ROOT / screen["record_directory"]
    for name in ("run_opt.py", "run_sp.py", "analyze.py", "screen_energies.json", "screen_results.txt"):
        assert (directory / name).is_file(), name
    assert screen["chosen_method_basis"] == raw["model_under_test"]["method_basis"]


def test_the_declared_model_is_the_model_this_code_would_run(spec):
    assert model_mismatches(spec) == []
    assert policy_of(spec).conformer_search == "mmff_topk"
    assert spec.model_under_test["method_basis"] == "M062X def2-TZVP"


def test_a_declared_model_that_drifted_from_the_code_is_reported(raw):
    drifted = copy.deepcopy(raw)
    drifted["model_under_test"]["model_version"] += "x"
    assert any("model_version" in p for p in model_mismatches(parse_spec(drifted)))
    drifted = copy.deepcopy(raw)
    drifted["model_under_test"]["rdkit_version"] = "1999.01.1"
    assert any("rdkit_version" in p for p in model_mismatches(parse_spec(drifted)))


def test_the_disclosure_states_what_a_reader_must_know(raw):
    text = " ".join(raw["preregistration"]["design_disclosure"]).lower()
    for needle in ("seen data", "not independent evidence", SCREEN_RULE_SHA256, "9d6a533d",
                   "full-orca-conformer mode is a different scientific model", "not retuned"):
        assert needle.lower() in text, needle


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda r: r["systems"][0].pop("partition"), "partition"),
        (lambda r: r["systems"][0].__setitem__("partition", "validation"), "partition"),
        (lambda r: r["preregistration"].__setitem__("design_disclosure", []), "design_disclosure"),
        (lambda r: r["preregistration"].pop("selection_manifest"), "selection_manifest"),
        (lambda r: r["model_under_test"].pop("model_version"), "model_version"),
        (lambda r: [x.__setitem__("role", "optional") for x in r["systems"] if x["partition"] == "held_out"], "held_out"),
        (lambda r: r["systems"][0].__setitem__("surprise", 1), "unknown"),
        (lambda r: r["systems"][6]["reference"]["protocol"].__setitem__("solvent", "water"), "quantity"),
    ],
)
def test_the_v2_schema_is_closed_and_demanding(raw, mutate, message):
    broken = copy.deepcopy(raw)
    mutate(broken)
    with pytest.raises(ValidationSpecError, match=message):
        parse_spec(broken)


def test_partition_and_source_are_part_of_the_hashes(raw, spec):
    moved = copy.deepcopy(raw)
    moved["systems"][0]["partition"] = PARTITION_HELD_OUT
    assert parse_spec(moved).benchmark_set_hash != spec.benchmark_set_hash
    retabled = copy.deepcopy(raw)
    retabled["systems"][6]["source"]["locator"] += " (row 2)"
    changed = parse_spec(retabled)
    assert changed.reference_bundle_hash != spec.reference_bundle_hash
    assert changed.benchmark_set_hash == spec.benchmark_set_hash  # same set, a different bundle


def _perfect_runs(spec, *, wrong=()):
    """Every system's computed energies equal its reference (a synthetic run), except `wrong`,
    which get the gap reversed."""
    runs = []
    for system in spec.systems:
        energies = {}
        for tautomer in system.tautomers:
            gap = tautomer.reference_kcal
            if system.id in wrong:
                gap = -gap
            energies[tautomer.id] = TautomerEnergy(tautomer.id, -100.0 + gap / HARTREE_TO_KCAL_PER_MOL, "fp", True)
        runs.append(SystemRun(system.id, "", energies, [], []))
    return runs


def test_the_gate_is_reported_by_partition(spec):
    gates = Gates(1.0, 1.0, 2.0)
    absolute = {t.id: -100.0 + t.reference_kcal / HARTREE_TO_KCAL_PER_MOL for t in spec.system("indazole").tautomers}
    assert evaluate_system(spec.system("indazole"), absolute, gates).passed
    assert computed_kcal(absolute)  # the same arithmetic the gate uses

    kwargs = dict(model_version="m", model_policy="p", source_commit="c", orca_version="o", rdkit_version="r")
    clean = build_artifact(spec, _perfect_runs(spec), **kwargs)
    assert clean["validation_gate_outcome"] == "passed"
    assert {k: v["passed"] for k, v in clean["partitions"].items()} == {"regression": True, "held_out": True}

    # Repaired the known cases, failed unseen chemistry: the overall gate fails and says where.
    mixed = build_artifact(spec, _perfect_runs(spec, wrong=("indazole",)), **kwargs)
    assert mixed["validation_gate_outcome"] != "passed"
    assert mixed["partitions"]["regression"]["passed"] is True
    assert mixed["partitions"]["held_out"]["passed"] is False
    assert mixed["partitions"]["held_out"]["failed_systems"] == ["indazole"]
    by_id = {s["id"]: s for s in mixed["systems"]}
    assert by_id["indazole"]["partition"] == PARTITION_HELD_OUT and by_id["cytosine"]["partition"] == PARTITION_REGRESSION


def test_a_partition_with_an_unevaluated_required_system_is_not_called_passed(spec):
    summary = partition_summary(spec, [])
    assert all(block["passed"] is None for block in summary.values())


def _runner():
    path = ROOT / "tools" / "tautomer_validation.py"
    loaded = importlib.util.spec_from_file_location("tautomer_validation_runner", path)
    module = importlib.util.module_from_spec(loaded)
    loaded.loader.exec_module(module)
    return module


def test_the_runner_reports_by_partition_and_refuses_the_revision_3_file(tmp_path):
    runner = _runner()
    lines = runner.partition_report({"partitions": {
        "regression": {"passed": True, "failed_systems": [], "evaluated": ["a"], "required_systems": ["a"]},
        "held_out": {"passed": False, "failed_systems": ["b"], "evaluated": ["b"], "required_systems": ["b", "c"]},
    }})
    assert "regression: passed" in lines[0] and "held_out: FAILED (b); 1/2" in lines[1]
    with pytest.raises(SystemExit, match="revision-3 record"):
        runner.main(["--run", "--out", str(tmp_path), "--criteria", str(SPEC_PATH)])


def test_the_runner_counts_its_jobs_before_running(spec, capsys):
    runner = _runner()
    total = runner.print_job_counts([spec.system("indazole"), spec.system("triazole_124")], policy_of(spec))
    out = capsys.readouterr().out
    assert total == 4 and "indazole: 2 ORCA optimizations" in out and "total: 4" in out


def test_every_reference_tautomer_of_every_system_is_one_the_app_enumerates(spec):
    """The check that found the revision-4 defect: a reference tautomer the enumerator never
    produces cannot be evaluated, and the run would be wasted on a system it cannot see."""
    from openchem.chem.engine import ChemistryEngine
    from openchem.chem.tautomer_distribution import generate_tautomer_candidates
    from openchem.chem.tautomer_validation import map_reference_tautomers

    runner = _runner()
    engine = ChemistryEngine()
    policy = policy_of(spec)
    for system in spec.systems:
        _model, mol = runner._structure(engine, system.input_smiles)
        candidates, _ = generate_tautomer_candidates(mol, stereo_cap=policy.stereo_cap, policy=policy)
        keys = {c.tautomer_fingerprint: canonical_key(c.mol) for c in candidates}
        mapping = map_reference_tautomers(system, keys)  # raises on any miss
        assert all(mapping.values()), system.id
