"""Run the preregistered tautomer validation through the application's own path.

**WHY IT EXISTS.** `chem/data/tautomer_validation_v2.json` (the default; `--criteria`
selects another) froze, before any number existed, what the tautomer-distribution model
must reproduce to be allowed to show a population percentage. This is the experiment: it
runs every system in that file and writes the artifact
`chem.tautomer_validation.build_artifact` defines. The criteria-v1 file records revision
3 and cannot be re-run by revision-4 code; `--run` refuses it.

**NO VALIDATION-ONLY CHEMISTRY.** Each system goes through the same steps the
Quantum Chemistry panel's "Tautomers..." button takes: the structure through
`ChemistryEngine`, `generate_tautomer_candidates` (enumeration, stereo
enumeration, dedupe, embedding), the real `QuantumChemistryService
.request_tautomer_distribution` with real ORCA, and `build_outcome`. The only thing
added is a provider subclass that records each job's exact input text hash; it
changes nothing it is given.

    python tools/tautomer_validation.py --list
    python tools/tautomer_validation.py --check-mapping        # RDKit only, no ORCA; also the job count
    python tools/tautomer_validation.py --run --out DIR [--systems cytosine ...] [--resume]
    python tools/tautomer_validation.py --make-record ARTIFACT  # the compact record the service consults

`--run` prints how many ORCA optimizations it is about to make, per system and in total,
BEFORE the first one starts, and refuses if the model the criteria file declares is not the
one this code would execute. The artifact stores every job's optimized geometry and its
conformer-pool provenance (the recipe that made the start geometry, how many conformers the
pool held, which force field scored it, which were selected), so a failure can be diagnosed
from the artifact alone.

`--run` refuses a dirty working tree (the artifact names a commit) unless
`--allow-dirty` says it is a trial. A system's finished measurements are written to
`DIR/<system>.run.json` as soon as it ends, so a long run loses nothing to a crash,
and `--resume` reuses them only when the commit, model and reference bundle match.

Real ORCA is required for `--run`; the model under test and the expected ORCA
version come from the criteria file, never from this script or the user's settings.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

#: The panel's own default executable location on this machine is read from the
#: environment first; the criteria file declares which ORCA VERSION is acceptable.
DEFAULT_ORCA = r"D:\ORCA\orca.exe"
#: Longest a single system may take before the run gives up on it.
DEFAULT_SYSTEM_TIMEOUT_MINUTES = 240


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()


def source_commit(allow_dirty: bool) -> str:
    commit = _git("rev-parse", "HEAD")
    if _git("status", "--porcelain"):
        if not allow_dirty:
            raise SystemExit("the working tree is dirty: the artifact would name a commit it was not run on")
        commit += "-dirty"
    return commit


def _isolated_environment() -> Path:
    """Settings in a throwaway INI file and a throwaway data root: the run must
    not read or write the person's registry or project data."""
    from PySide6.QtCore import QSettings

    import openchem.app.settings as settings_module
    from openchem import paths as app_paths

    scratch = Path(tempfile.mkdtemp(prefix="openchem-validation-"))
    ini = scratch / "qsettings.ini"
    settings_module.QSettings = lambda *_a, **_k: QSettings(str(ini), QSettings.Format.IniFormat)
    os.environ[app_paths.DATA_ROOT_ENV_VAR] = str(scratch / "data-root")
    (scratch / "data-root").mkdir()
    return scratch


def _recording_provider():
    """The real ORCA provider, remembering a SHA-256 of every input it builds and the
    optimized geometry ORCA's output carried back (empty when the output had none).

    The service discards that geometry after reading the energy; Phase O's artifact therefore
    could not say WHICH minimum a job had reached, which left its failure's cause unverifiable.
    Recording it changes nothing the service is given or returns."""
    from openchem.chem.orca_engine import OrcaQuantumEngineProvider

    class RecordingProvider(OrcaQuantumEngineProvider):
        def __init__(self) -> None:
            super().__init__()
            self.input_hashes: list[str] = []
            self.optimized_molblocks: list[str] = []

        def build_input(self, mol, charge, multiplicity, method_basis, calc_type):  # noqa: ANN001
            text = super().build_input(mol, charge, multiplicity, method_basis, calc_type)
            self.input_hashes.append(hashlib.sha256(text.encode("utf-8")).hexdigest())
            return text

        def parse_output(self, output_text, mol, molecule_uuid, calc_type):  # noqa: ANN001
            try:
                descriptors, conformer = super().parse_output(output_text, mol, molecule_uuid, calc_type)
            except Exception:
                self.optimized_molblocks.append("")
                raise
            self.optimized_molblocks.append(conformer.molblock if conformer is not None else "")
            return descriptors, conformer

    return RecordingProvider()


def _structure(engine, smiles: str):
    """The molecule as the panel holds it: a drawing, never a bare SMILES mol."""
    from openchem.domain.molecule import MoleculeModel

    model = MoleculeModel()
    engine.set_structure_from_smiles(model, smiles)
    return model, engine.mol_from_molblock(model.molblock)


def _policy_for(spec):
    """The conformer policy the criteria file declares. A v1 file declares none (it is the
    revision-3 record), so the listing commands use revision 3's single-geometry policy for it
    and `--run` refuses it outright."""
    from openchem.chem.tautomer_distribution import MODEL_POLICY_SINGLE
    from openchem.chem.tautomer_validation import policy_of

    return policy_of(spec) if "conformer_search" in spec.model_under_test else MODEL_POLICY_SINGLE


def check_mapping(spec) -> int:
    """Every reference tautomer must be one the application enumerates; reported
    with what else it enumerates, and how many ORCA optimizations the system needs
    under the declared policy. RDKit only."""
    from openchem.chem.engine import ChemistryEngine
    from openchem.chem.tautomer_distribution import generate_tautomer_candidates
    from openchem.chem.tautomer_validation import (
        MappingError,
        canonical_key,
        map_reference_tautomers,
        unreferenced_tautomers,
    )

    engine = ChemistryEngine()
    policy = _policy_for(spec)
    bad = 0
    total = 0
    for system in spec.systems:
        _model, mol = _structure(engine, system.input_smiles)
        candidates, failures = generate_tautomer_candidates(mol, stereo_cap=policy.stereo_cap, policy=policy)
        keys = {c.tautomer_fingerprint: canonical_key(c.mol) for c in candidates}
        total += len(candidates)
        try:
            mapping = map_reference_tautomers(system, keys)
            note = ", ".join(f"{ref}<-{len(group)}" for ref, group in mapping.items())
        except MappingError as exc:
            bad += 1
            note = f"MAPPING ERROR {exc}"
        partition = f"/{system.partition}" if system.partition else ""
        print(
            f"{system.id} [{system.role}{partition}]: {len(candidates)} jobs, {len(keys)} tautomers, "
            f"{failures} embedding failure(s); {note}; unlisted {unreferenced_tautomers(system, keys)}"
        )
    print(f"total: {total} ORCA optimizations under {policy.conformer_search}")
    return 1 if bad else 0


def _serialize_run(run) -> dict[str, Any]:
    return dataclasses.asdict(run)


def _deserialize_run(data: dict[str, Any]):
    from openchem.chem.tautomer_validation import SystemRun, TautomerEnergy

    return SystemRun(
        system_id=data["system_id"],
        mapping_error=data["mapping_error"],
        energies={k: TautomerEnergy(**v) for k, v in data["energies"].items()},
        unreferenced=list(data["unreferenced"]),
        jobs=list(data["jobs"]),
    )


def run_system(qapp, spec, system, orca: str, timeout_minutes: int):
    """One system, end to end, through the service. Returns a `SystemRun`."""
    from PySide6.QtCore import QCoreApplication

    from openchem.app.settings import Settings
    from openchem.chem.boltzmann import STANDARD_TEMPERATURE_K
    from openchem.chem.engine import ChemistryEngine
    from openchem.chem.tautomer_distribution import (
        build_outcome,
        generate_tautomer_candidates,
    )
    from openchem.chem.tautomer_validation import (
        MappingError,
        SystemRun,
        canonical_key,
        map_reference_tautomers,
        reference_tautomer_energies,
        unreferenced_tautomers,
    )
    from openchem.chem.calculation_input import input_fingerprint
    from openchem.domain.calculator import DRAWING
    from openchem.domain.common import CacheState
    from openchem.events.base import EventBus
    from openchem.events.events import QuantumChemistryJobStateChanged, TautomerDistributionResultReady
    from openchem.services.quantum_chemistry_service import QuantumChemistryService

    model_spec = spec.model_under_test
    if model_spec["embedding_base_seed"] != 0:
        raise SystemExit("the criteria declare a base seed other than the one the application uses")
    engine = ChemistryEngine()
    model, mol = _structure(engine, system.input_smiles)
    policy = _policy_for(spec)
    candidates, embedding_failures = generate_tautomer_candidates(
        mol, stereo_cap=policy.stereo_cap, policy=policy
    )
    keys = {c.tautomer_fingerprint: canonical_key(c.mol) for c in candidates}
    mapping_error = ""
    mapping: dict[str, tuple[str, ...]] = {}
    try:
        mapping = map_reference_tautomers(system, keys)
    except MappingError as exc:
        mapping_error = str(exc)
        print(f"  {mapping_error}")
        return SystemRun(system.id, mapping_error, {}, unreferenced_tautomers(system, keys), [])
    if embedding_failures:
        print(f"  {embedding_failures} candidate(s) failed to embed and are excluded (the tautomer will read incomplete)")

    bus = EventBus()
    settings = Settings(bus)
    settings.set("orca/executable_path", orca)
    provider = _recording_provider()
    service = QuantumChemistryService(bus, settings, providers={provider.provider_id: provider})
    arrived: list[TautomerDistributionResultReady] = []
    refused: list[str] = []
    bus.subscribe(TautomerDistributionResultReady, arrived.append)
    bus.subscribe(
        QuantumChemistryJobStateChanged,
        lambda e: refused.append(e.message) if e.state is CacheState.FAILED else None,
    )

    started = time.perf_counter()
    service.request_tautomer_distribution(
        candidates=candidates,
        molecule_uuid=model.uuid,
        charge=model_spec["charge"],
        multiplicity=model_spec["multiplicity"],
        method_basis=model_spec["method_basis"],
        calculation_input=DRAWING,
        input_fingerprint=input_fingerprint(engine, model, DRAWING),
        policy=policy,
    )
    run = service._tautomer_runs.get(model.uuid)  # the very object the service finishes with
    if run is None:
        raise SystemExit(f"the service started no run for {system.id}: {refused[-1:] or 'no reason given'}")
    deadline = started + timeout_minutes * 60
    last_report = 0
    while True:
        QCoreApplication.processEvents()
        if arrived:
            break
        time.sleep(0.05)
        if time.perf_counter() > deadline:
            raise SystemExit(f"{system.id}: not finished after {timeout_minutes} minutes")
        if refused and not service._tautomer_runs.get(model.uuid):
            raise SystemExit(f"{system.id}: the service refused or aborted: {refused[-1]}")
        if len(run.results) != last_report:
            last_report = len(run.results)
            print(f"  {system.id}: {last_report}/{len(candidates)} jobs done ({time.perf_counter() - started:.0f} s)")

    if len(provider.input_hashes) != len(run.results) or len(provider.optimized_molblocks) != len(run.results):
        # Both lists are appended once per job in completion order; a mismatch would attach an
        # input hash or a geometry to the wrong job, which is worse than recording none.
        raise SystemExit(
            f"{system.id}: {len(run.results)} results but {len(provider.input_hashes)} inputs and "
            f"{len(provider.optimized_molblocks)} outputs were recorded; the artifact would misattribute them"
        )
    outcome = build_outcome(run.results, temperature_k=STANDARD_TEMPERATURE_K)
    jobs = []
    for index, result in enumerate(run.results):
        jobs.append({
            "index": index,
            "fingerprint": result.fingerprint,
            "tautomer_fingerprint": result.tautomer_key,
            "stereo_index": result.stereo.index,
            "status": result.status.value,
            "absolute_energy_hartree": result.absolute_energy_hartree,
            "failure_reason_code": result.failure_reason_code,
            "failure_reason": result.failure_reason,
            "embedding_seed": result.embedding_seed,
            "start_geometry_sha256": hashlib.sha256(result.molblock.encode("utf-8")).hexdigest(),
            "start_geometry_molblock": result.molblock,
            "optimized_geometry_molblock": provider.optimized_molblocks[index],
            "input_sha256": provider.input_hashes[index],
            "stereo": dataclasses.asdict(result.stereo),
            "conformer": dataclasses.asdict(result.conformer),
            "tautomer_state": outcome.tautomer_states[result.tautomer_key].value,
            "calculation_source": "fresh_orca",
        })
    energies = reference_tautomer_energies(mapping, outcome)
    print(f"  {system.id}: done in {time.perf_counter() - started:.0f} s, {len(jobs)} jobs")
    return SystemRun(system.id, "", energies, unreferenced_tautomers(system, keys), jobs)


def make_record(artifact_path: Path) -> int:
    """Writes `chem/data/tautomer_validation_record_v2.json` from a committed artifact. The record
    is DERIVED (a test rebuilds it from the artifact and refuses any difference), so this is the
    only way it is made; it is never edited by hand."""
    from openchem.chem.tautomer_validation import RECORD_PATH_V2, artifact_sha256, record_from_artifact

    artifact_path = artifact_path.resolve()
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    if artifact["validation_execution_status"] != "complete" or artifact.get("partial_run"):
        raise SystemExit("a record is made only from a COMPLETE, whole run")
    relative = artifact_path.relative_to(ROOT).as_posix()
    record = record_from_artifact(artifact, relative, artifact_sha256(artifact_path))
    RECORD_PATH_V2.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {RECORD_PATH_V2} ({record['validation_gate_outcome']}, {record['model_version'][:40]}...)")
    return 0


def print_job_counts(systems, policy) -> int:
    """How many ORCA optimizations the run will make, per system and in total, printed
    BEFORE the first one starts. RDKit only. A long run that surprises its operator with its
    own size has no way to be stopped in time, so the size is stated first."""
    from openchem.chem.engine import ChemistryEngine
    from openchem.chem.tautomer_distribution import generate_tautomer_candidates

    engine = ChemistryEngine()
    total = 0
    for system in systems:
        _model, mol = _structure(engine, system.input_smiles)
        candidates, failures = generate_tautomer_candidates(mol, stereo_cap=policy.stereo_cap, policy=policy)
        total += len(candidates)
        extra = f" (+{failures} that failed to embed)" if failures else ""
        print(f"  {system.id}: {len(candidates)} ORCA optimizations{extra}")
    print(f"  total: {total} ORCA optimizations under {policy.conformer_search}")
    return total


def partition_report(artifact: dict[str, Any]) -> list[str]:
    """The gate's result by partition, as the lines the runner prints. A regression pass is
    NOT independent evidence (v4 was shaped on those systems), so the held-out line is the one
    to read; the overall gate is still the criterion."""
    lines = []
    for partition, block in (artifact.get("partitions") or {}).items():
        verdict = {True: "passed", False: "FAILED", None: "not evaluable"}[block["passed"]]
        failed = f" ({', '.join(block['failed_systems'])})" if block["failed_systems"] else ""
        lines.append(f"  {partition}: {verdict}{failed}; {len(block['evaluated'])}/{len(block['required_systems'])} required systems evaluated")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--list", action="store_true")
    mode.add_argument("--check-mapping", action="store_true")
    mode.add_argument("--run", action="store_true")
    mode.add_argument("--make-record", type=Path, metavar="ARTIFACT",
                      help="write the compact validation record (chem/data) from a committed artifact")
    parser.add_argument("--out", type=Path, help="directory for the artifact and per-system files")
    parser.add_argument("--systems", nargs="*", help="only these system ids (a partial run cannot pass the gate)")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--allow-dirty", action="store_true")
    parser.add_argument(
        "--criteria", type=Path, default=None,
        help="an alternate criteria file (default: the criteria-v2 file), for exercising the runner with a "
        "cheap model. Its artifact carries ITS criteria hash, so it can never stand in for the preregistered run",
    )
    parser.add_argument("--orca", default=os.environ.get("OPENCHEM_VALIDATION_ORCA", DEFAULT_ORCA))
    parser.add_argument("--timeout-minutes", type=int, default=DEFAULT_SYSTEM_TIMEOUT_MINUTES)
    args = parser.parse_args(argv)

    from openchem.chem.tautomer_validation import SPEC_PATH_V2, load_spec, systems_summary

    spec = load_spec(args.criteria or SPEC_PATH_V2)
    if args.list:
        print("\n".join(systems_summary(spec.systems)))
        print(f"criteria {spec.criteria_hash}\nbenchmark set {spec.benchmark_set_hash}\nbundle {spec.reference_bundle_hash}")
        return 0
    if args.check_mapping:
        return check_mapping(spec)
    if args.make_record:
        return make_record(args.make_record)

    if args.out is None:
        parser.error("--run needs --out")
    if "conformer_search" not in spec.model_under_test:
        raise SystemExit(
            "this criteria file is the revision-3 record (it declares no conformer policy); revision-4 code "
            "cannot re-run it. Use the criteria-v2 file."
        )
    from openchem.chem.tautomer_validation import model_mismatches

    if problems := model_mismatches(spec):
        raise SystemExit(
            "the model the criteria file declares is not the one this code would run, so the run would "
            "validate something else:\n  " + "\n  ".join(problems)
        )
    commit = source_commit(args.allow_dirty)
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    _isolated_environment()
    from PySide6.QtWidgets import QApplication
    from rdkit import rdBase

    from openchem.chem.tautomer_distribution import model_version
    from openchem.chem.tautomer_validation import build_artifact
    from openchem.services.tool_download_service import verify_orca

    orca_version = verify_orca(args.orca)
    if spec.model_under_test["orca_version"] not in orca_version:
        raise SystemExit(f"ORCA reports {orca_version!r}; the criteria declare {spec.model_under_test['orca_version']}")
    qapp = QApplication.instance() or QApplication([])
    policy = _policy_for(spec)
    model_ver = model_version(
        spec.model_under_test["method_basis"], spec.model_under_test["embedding_algorithm"],
        spec.model_under_test["temperature_k"], policy,
    )
    args.out.mkdir(parents=True, exist_ok=True)
    wanted = [s for s in spec.systems if not args.systems or s.id in args.systems]
    unknown = sorted(set(args.systems or []) - {s.id for s in spec.systems})
    if unknown:
        raise SystemExit(f"no such system(s): {unknown}")
    print(f"model {model_ver}")
    print_job_counts(wanted, policy)
    runs = []
    for system in wanted:
        path = args.out / f"{system.id}.run.json"
        stamp = {"commit": commit, "model_version": model_ver, "reference_bundle_hash": spec.reference_bundle_hash}
        if args.resume and path.is_file():
            saved = json.loads(path.read_text(encoding="utf-8"))
            if saved["stamp"] == stamp:
                print(f"{system.id}: reusing {path.name}")
                runs.append(_deserialize_run(saved["run"]))
                continue
        print(f"{system.id} [{system.role}]")
        run = run_system(qapp, spec, system, args.orca, args.timeout_minutes)
        path.write_text(json.dumps({"stamp": stamp, "run": _serialize_run(run)}, indent=1) + "\n", encoding="utf-8")
        runs.append(run)

    artifact = build_artifact(
        spec, runs, model_version=model_ver, model_policy=policy.canonical(),
        source_commit=commit, orca_version=orca_version, rdkit_version=rdBase.rdkitVersion,
    )
    artifact["partial_run"] = len(wanted) != len(spec.systems)
    target = args.out / "tautomer_validation_artifact.json"
    target.write_text(json.dumps(artifact, indent=1) + "\n", encoding="utf-8")
    print(f"execution {artifact['validation_execution_status']}, outcome {artifact['validation_gate_outcome']}")
    for line in partition_report(artifact):
        print(line)
    print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
