"""Frozen CNNaffinity ranking power vs Vina (`PREREGISTRATION_CNN_AFFINITY.md`).

    uv run --no-sync python benchmarks/docking/run_cnn_affinity_test.py list
    uv run --no-sync python benchmarks/docking/run_cnn_affinity_test.py gates

`list` and `gates` start no catalog CNNaffinity. `rescore` / `report` ran
after freeze `e52f01ae`; the catalog result is HARMFUL
(`RESULT_CNN_AFFINITY.md`).
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import cnn_affinity_core as core  # noqa: E402


def cmd_list(_args: argparse.Namespace) -> None:
    deciding = core.deciding_pdbs()
    overlap = core.overlap_pdbs()
    plan = {
        "n_ranking_series": core.n_series(sorted(core.RANKING_PDBS)),
        "n_deciding_series": core.n_series(deciding),
        "n_overlap_series": core.n_series(overlap),
        "deciding_pdbs": list(deciding),
        "overlap_pdbs": list(overlap),
        "score_only": core.SCORE_ONLY,
        "cnn_scoring": core.CNN_SCORING,
        "cnn_ensemble": list(core.CNN_ENSEMBLE),
        "cnn_higher_is_better": core.CNN_AFFINITY_HIGHER_IS_BETTER,
        "crossdocked_sha256": core.CROSSDOCKED_SET_IDS_SHA256,
    }
    print(json.dumps(plan, indent=2))
    print(
        f"{plan['n_deciding_series']} deciding series on {len(deciding)} PDBs; "
        f"{plan['n_overlap_series']} overlap series reported apart",
        flush=True,
    )


def cmd_gates(_args: argparse.Namespace) -> None:
    import run_gnina_test as pose_run

    ver = pose_run.wsl(f"{pose_run.GNINA_WSL} --version", timeout=120)
    help_p = pose_run.wsl(f"{pose_run.GNINA_WSL} --help", timeout=180)
    gpu = pose_run.wsl("nvidia-smi -L", timeout=60)
    version_text = (ver.stdout or "") + (ver.stderr or "")
    help_text = (help_p.stdout or "") + (help_p.stderr or "")
    gpu_text = gpu.stdout or ""
    report = {
        "version_pinned": pose_core_version(version_text),
        "ensemble_named": core.help_names_default_ensemble(help_text),
        "gpu_ok": "4060" in gpu_text,
        "binary_ok": pose_run.GNINA_WIN.is_file()
        and pose_run.GNINA_WIN.stat().st_size == core.GNINA_ASSET_BYTES,
        "score_only": core.SCORE_ONLY,
        "sign_predeclared": core.cnn_sign_is_predeclared(True),
    }
    print(json.dumps(report, indent=2))
    if not all(
        [
            report["version_pinned"],
            report["ensemble_named"],
            report["gpu_ok"],
            report["binary_ok"],
            report["score_only"] is True,
            report["sign_predeclared"],
        ]
    ):
        raise SystemExit("gates failed")


def pose_core_version(text: str) -> bool:
    return core.VERSION_NEEDLE in text and core.COMMIT_NEEDLE in text


OUT_DEFAULT = "benchmarks/docking/artifacts_cnn_affinity"
_CNN_VAR = re.compile(r"CNNvariance:\s*([-0-9]*\.?[0-9]+)", re.I)


def _wsl_path(path: pathlib.Path) -> str:
    resolved = path.resolve()
    drive = resolved.drive.rstrip(":").lower()
    return "/mnt/" + drive + resolved.as_posix()[len(resolved.drive) :]


def _hundredths(value: float) -> float:
    return round(float(value), 2)


def _done(path: pathlib.Path) -> set[tuple[str, str]]:
    seen: set[tuple[str, str]] = set()
    if not path.is_file():
        return seen
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        seen.add((row["series_id"], row["molecule_id"]))
    return seen


def _append(path: pathlib.Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")
        handle.flush()


def _write_receptor_pdb(text: str, fmt: str, dest: pathlib.Path) -> None:
    if fmt.lower() in {"pdb", "ent"}:
        dest.write_text(text, encoding="utf-8")
        return
    from openbabel import pybel

    mol = pybel.readstring(fmt, text)
    mol.write("pdb", str(dest), overwrite=True)


def _pose_sdf(pdbqt_text: str, dest: pathlib.Path) -> None:
    from openbabel import pybel

    mol = pybel.readstring("pdbqt", pdbqt_text)
    mol.write("sdf", str(dest), overwrite=True)


def cmd_rescore(args: argparse.Namespace) -> None:
    import gnina_core as pose_core
    import rank_power as rp
    import run_gnina_test as pose_run
    from _config import vina_executable
    from openchem.chem.docking_providers import VinaDockingProvider
    from openchem.chem.vina_engine import ExecutableVinaEngine, parse_vina_output_pdbqt
    from openchem.services.progress import ProgressHandle
    from openchem.services.receptor_library_service import cached_structure
    from openbabel import pybel
    from openchem.chem.receptor_library import find
    from openchem.chem.binding_site import box_from_ligand

    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    jsonl = out / "results.jsonl"
    seen = _done(jsonl)
    manifest = json.loads((rp.DATA / "manifest.json").read_text(encoding="utf-8"))
    selection = list(manifest.get("docking_selection") or [])
    engine = ExecutableVinaEngine(vina_executable())
    provider = VinaDockingProvider(engine=engine)

    for series_id in selection:
        series = rp.load_series(series_id)
        pdb_id = series["pdb_id"]
        runs_path = rp.RESULTS / f"{series_id}.jsonl"
        if not runs_path.is_file():
            print(series_id, "missing ranking jsonl", flush=True)
            continue
        runs = [json.loads(line) for line in runs_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        by_mol: dict[str, list[dict]] = {}
        for run in runs:
            if run.get("vina_best") is None:
                continue
            by_mol.setdefault(run["molecule_chembl_id"], []).append(run)

        entry = find(pdb_id)
        cached = cached_structure(pdb_id)
        if entry is None or cached is None:
            print(series_id, "no receptor cache", flush=True)
            continue
        structure_text, source_format = cached
        site = box_from_ligand(structure_text, source_format, entry.ligand_code)
        series_dir = out / "work" / series_id
        series_dir.mkdir(parents=True, exist_ok=True)
        receptor_pdb = series_dir / "receptor.pdb"
        receptor_pdbqt = series_dir / "receptor.pdbqt"
        prep = {**rp.PREP, "strip_ligand_codes": (entry.ligand_code,)}
        if not receptor_pdbqt.is_file():
            _write_receptor_pdb(structure_text, source_format, receptor_pdb)
            provider._convert_receptor_to_pdbqt(
                pybel, structure_text, source_format, receptor_pdbqt, prep, rp.PH
            )
            rp.assert_pocket_is_clear(receptor_pdbqt, entry.ligand_code)
            rp.assert_metals_survived(structure_text, source_format, receptor_pdbqt)

        for ligand in series["ligands"]:
            molecule_id = ligand["molecule_chembl_id"]
            if (series_id, molecule_id) in seen:
                continue
            mol_runs = by_mol.get(molecule_id) or []
            record = {
                "series_id": series_id,
                "pdb": pdb_id,
                "molecule_id": molecule_id,
                "pchembl": ligand["pchembl_value"],
                "replicate": None,
                "seed": None,
                "vina": None,
                "vina_reproduced": None,
                "match": False,
                "cnn_affinity": None,
                "cnn_score": None,
                "cnn_variance": None,
            }
            try:
                pairs = [(int(r["replicate"]), float(r["vina_best"])) for r in mol_runs]
                replicate = core.representative_replicate(pairs)
            except (ValueError, KeyError, TypeError):
                _append(jsonl, record)
                print(series_id, molecule_id, "no representative", flush=True)
                continue
            chosen = next(r for r in mol_runs if int(r["replicate"]) == replicate)
            record["replicate"] = replicate
            record["seed"] = int(chosen["seed"])
            record["vina"] = float(chosen["vina_best"])
            try:
                mol = rp.embed(ligand["canonical_smiles"])
                ligand_pdbqt = series_dir / f"{molecule_id}.pdbqt"
                provider._convert_ligand_to_pdbqt(pybel, mol, ligand_pdbqt, rp.PH)
                output = engine.dock(
                    receptor_pdbqt,
                    ligand_pdbqt,
                    site.box,
                    rp.NUM_POSES,
                    rp.EXHAUSTIVENESS,
                    int(chosen["seed"]),
                    ProgressHandle(),
                )
                poses = parse_vina_output_pdbqt(output)
            except Exception as exc:  # noqa: BLE001 - one ligand must not end the series
                record["error"] = str(exc)
                _append(jsonl, record)
                print(series_id, molecule_id, "dock failed", flush=True)
                continue
            if not poses:
                _append(jsonl, record)
                print(series_id, molecule_id, "no poses", flush=True)
                continue
            best = min(poses, key=lambda p: p.binding_affinity_kcal_mol)
            record["vina_reproduced"] = best.binding_affinity_kcal_mol
            record["match"] = _hundredths(best.binding_affinity_kcal_mol) == _hundredths(
                float(chosen["vina_best"])
            )
            if not record["match"]:
                _append(jsonl, record)
                print(series_id, molecule_id, "vina mismatch", flush=True)
                continue
            work = series_dir / molecule_id
            work.mkdir(parents=True, exist_ok=True)
            pose_sdf = work / "pose.sdf"
            _pose_sdf(best.pdbqt_text, pose_sdf)
            rec_pdb = receptor_pdb if receptor_pdb.is_file() else receptor_pdb
            wsl_work = _wsl_path(work)
            wsl_rec = _wsl_path(rec_pdb)
            log = work / "gnina.out"
            pose_run.wsl(
                f"{pose_run.GNINA_WSL} -r {wsl_rec} -l {wsl_work}/pose.sdf "
                f"--score_only --cnn_scoring {core.CNN_SCORING} --device 0 "
                f"> {wsl_work}/gnina.out 2>&1",
                timeout=600,
            )
            text = log.read_text(encoding="utf-8", errors="replace") if log.is_file() else ""
            scores, affs = pose_core.parse_cnn_scores(text)
            variances = [float(m.group(1)) for m in _CNN_VAR.finditer(text)]
            if affs:
                record["cnn_affinity"] = affs[0]
            if scores:
                record["cnn_score"] = scores[0]
            if variances:
                record["cnn_variance"] = variances[0]
            _append(jsonl, record)
            print(series_id, molecule_id, "ok", record["cnn_affinity"], flush=True)


def cmd_report(args: argparse.Namespace) -> None:
    out = pathlib.Path(args.out)
    rows = [
        json.loads(line)
        for line in (out / "results.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    by_series: dict[str, list[dict]] = {}
    for row in rows:
        by_series.setdefault(row["series_id"], []).append(row)

    deciding_deltas: list[float] = []
    overlap_deltas: list[float] = []
    by_pdb: dict[str, list[float]] = {pdb: [] for pdb in core.deciding_pdbs()}
    dropped = 0
    for series_id, ligands in sorted(by_series.items()):
        pdb = ligands[0]["pdb"]
        vina = [float(r["vina"]) for r in ligands if r.get("vina") is not None]
        cnn = [
            float(r["cnn_affinity"]) if r.get("cnn_affinity") is not None else None
            for r in ligands
            if r.get("vina") is not None
        ]
        pchembl = [float(r["pchembl"]) for r in ligands if r.get("vina") is not None]
        # Pairing is inside paired_delta_rho (drops None cnn).
        if len(vina) != len(cnn):
            continue
        delta = core.paired_delta_rho(vina, cnn, pchembl)
        if delta is None:
            if pdb in core.RANKING_PDBS and pdb not in core.TRAINING_OVERLAP:
                dropped += 1
            continue
        if pdb in core.TRAINING_OVERLAP:
            overlap_deltas.append(delta)
        else:
            deciding_deltas.append(delta)
            by_pdb.setdefault(pdb, []).append(delta)

    n_deciding = core.n_series(core.deciding_pdbs())
    series_iv = core.bootstrap_interval(deciding_deltas)
    clustered = core.clustered_interval({k: v for k, v in by_pdb.items() if v})
    v = core.verdict(series_iv, dropped=dropped, n_deciding=n_deciding)
    eligible = core.integration_eligible(v, clustered)
    summary = {
        "deciding_n": len(deciding_deltas),
        "overlap_n": len(overlap_deltas),
        "dropped": dropped,
        "median_delta": core.median_of(deciding_deltas) if deciding_deltas else None,
        "series_interval": list(series_iv) if series_iv else None,
        "clustered_interval": list(clustered) if clustered else None,
        "verdict": v,
        "integration_eligible": eligible,
    }
    print(json.dumps(summary, indent=2))
    print(f"VERDICT (deciding series): {v}", flush=True)
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="stage", required=True)
    sub.add_parser("list")
    sub.add_parser("gates")
    rescore = sub.add_parser("rescore")
    rescore.add_argument("--out", default=OUT_DEFAULT)
    report = sub.add_parser("report")
    report.add_argument("--out", default=OUT_DEFAULT)
    args = parser.parse_args()
    {
        "list": cmd_list,
        "gates": cmd_gates,
        "rescore": cmd_rescore,
        "report": cmd_report,
    }[args.stage](args)


if __name__ == "__main__":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    main()
