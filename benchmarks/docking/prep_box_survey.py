"""Redock every catalogued receptor and say WHAT KIND of miss each miss was.

    uv run --no-sync python benchmarks/docking/prep_box_survey.py --targets 1HSG 5C1M
    uv run --no-sync python benchmarks/docking/prep_box_survey.py            # all of them
    uv run --no-sync python benchmarks/docking/prep_box_survey.py --report   # tally only

`redock.py` asks one question of nine receptors: did the centroid land in the right
pocket. This asks it of the whole catalogue and splits the answer by cause, because the
question behind it is whether a "bad default pose" is a SETUP defect (no site, wrong box,
ligand not built, receptor prepared badly) or a SCORING one (right pocket, wrong or
mis-ranked pose). Only the first kind is something better preparation could fix.

Two arms, differing in ONE thing:

    app        the Docking panel's own defaults: waters stripped, cofactors kept, pH 7.4
    stripped   the same with cofactors stripped (what `redock.py` has always used)

BOTH arms also strip the residue that defined the box (`strip_ligand_codes`), exactly as
the panel does for a catalogue receptor (`box_defining_ligand_codes`). The first pilot left
it out of the "app" arm, so every ligand docked onto its own crystal copy and landed
"wrong pocket" with a positive score: a defect of the survey, not of the application.

Everything else is identical and the seed is pinned, so a receptor that changes class
between arms changed because of its cofactors and nothing else. The distance is an
assignment RMSD, a LOWER BOUND (see `prep_box_core.py`); the centroid shift is kept
beside it. Each pose also gets the four physical checks of `chem/pose_plausibility.py`.

Results are appended to `<out>/results.jsonl` one run at a time, so a stopped run resumes
where it stopped and a finished row is never repeated.
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import prep_box_core as core  # noqa: E402
from _config import vina_executable  # noqa: E402
from openchem.chem.binding_site import BindingSiteError, box_from_ligand  # noqa: E402
from openchem.chem.docking_providers import (  # noqa: E402
    DEFAULT_EXHAUSTIVENESS,
    VinaDockingProvider,
)
from openchem.chem.pose_analysis import receptor_atoms_from_structure  # noqa: E402
from openchem.chem.pose_plausibility import check_pose  # noqa: E402
from openchem.chem.receptor_library import RECEPTOR_LIBRARY, find  # noqa: E402
from openchem.net import open_url  # noqa: E402
from openchem.services.progress import ProgressHandle  # noqa: E402
from openchem.services.receptor_library_service import fetch_structure  # noqa: E402
from rdkit import Chem  # noqa: E402
from rdkit.Chem import AllChem  # noqa: E402

ARMS = {
    "app": {"strip_waters": True, "strip_cofactors": False},
    "stripped": {"strip_waters": True, "strip_cofactors": True},
}
#: Pinned, so two arms and a re-run draw the same search.
SEEDS = (20261029,)
NUM_POSES = 9


def component_smiles(comp_id: str) -> str | None:
    try:
        data = json.loads(
            open_url(f"https://data.rcsb.org/rest/v1/core/chemcomp/{comp_id}", timeout=45).read()
        )
    except Exception:  # noqa: BLE001
        return None
    for row in data.get("pdbx_chem_comp_descriptor", []) or []:
        if row.get("type") == "SMILES_CANONICAL":
            return row.get("descriptor")
    descriptor = data.get("rcsb_chem_comp_descriptor") or {}
    return descriptor.get("SMILES_stereo") or descriptor.get("SMILES")


def crystal_atoms(structure: str, fmt: str, code: str, positions) -> list[core.Atom]:
    """Elements for the chosen ligand copy, found by position (the box keeps only positions)."""
    wanted = {tuple(round(c, 3) for c in p) for p in positions}
    found = []
    for atom in receptor_atoms_from_structure(structure, fmt):
        if atom.residue_name.strip().upper() == code.upper():
            if tuple(round(c, 3) for c in atom.position) in wanted:
                found.append((atom.element.capitalize(), tuple(atom.position)))
    return found


def prep_options(arm: str, ligand_code: str) -> dict:
    """What the panel hands the provider for a catalogue receptor in this arm."""
    return {**ARMS[arm], "strip_ligand_codes": [ligand_code]}


def run_one(provider, pdb_id: str, arm: str, seed: int, exhaustiveness: int) -> dict:
    entry = find(pdb_id)
    row = {"pdb": pdb_id, "ligand": entry.ligand_code, "arm": arm, "seed": seed,
           "exhaustiveness": exhaustiveness}
    started = time.time()
    try:
        text, fmt = fetch_structure(pdb_id)
        site = box_from_ligand(text, fmt, entry.ligand_code)
    except BindingSiteError as exc:
        return {**row, "outcome": core.SETUP_NO_SITE, "detail": str(exc)[:120]}
    except Exception as exc:  # noqa: BLE001
        return {**row, "outcome": core.SETUP_NO_SITE, "detail": f"{type(exc).__name__}: {exc}"[:120]}
    row.update(box_size=[round(v, 1) for v in site.box.size], site_atoms=site.atom_count,
               size_clamped=site.size_was_clamped)

    smiles = component_smiles(entry.ligand_code)
    mol = Chem.MolFromSmiles(smiles) if smiles else None
    if mol is None:
        return {**row, "outcome": core.SETUP_LIGAND, "detail": "no usable SMILES from RCSB"}
    mol = Chem.AddHs(mol)
    if AllChem.EmbedMolecule(mol, randomSeed=0xC0FFEE) != 0:
        return {**row, "outcome": core.SETUP_LIGAND, "detail": "would not embed"}
    AllChem.MMFFOptimizeMolecule(mol)

    try:
        poses = provider.dock(
            receptor_structure_text=text, receptor_source_format=fmt, ligand_mol=mol,
            box=site.box, num_poses=NUM_POSES, progress=ProgressHandle(),
            receptor_prep_options=prep_options(arm, entry.ligand_code),
            search_options={"seed": seed, "exhaustiveness": exhaustiveness},
        )
    except Exception as exc:  # noqa: BLE001
        return {**row, "outcome": core.SETUP_DOCK, "detail": f"{type(exc).__name__}: {exc}"[:120]}

    crystal = crystal_atoms(text, fmt, entry.ligand_code, site.ligand_positions)
    ctr = core.centroid(crystal) if crystal else None
    receptor = receptor_atoms_from_structure(text, fmt, prep_options(arm, entry.ligand_code))
    measures, detail = [], []
    for pose in poses:
        docked = Chem.MolFromMolBlock(pose.pose_molblock, sanitize=False)
        conf = docked.GetConformer()
        atoms = [(a.GetSymbol(), tuple(conf.GetAtomPosition(a.GetIdx())))
                 for a in docked.GetAtoms() if a.GetSymbol() != "H"]
        shift = math.dist(core.centroid(atoms), ctr) if ctr else float("inf")
        rmsd = core.assignment_rmsd(atoms, crystal) if crystal else None
        measures.append(core.PoseMeasure(rmsd=rmsd, centroid_shift=shift))
        failed = check_pose(pose.pose_molblock, receptor, site.box)["failed"]
        detail.append({"affinity": round(pose.binding_affinity_kcal_mol, 2),
                       "rmsd": None if rmsd is None else round(rmsd, 2),
                       "shift": round(shift, 2), "failed_checks": failed})
    return {**row, "outcome": core.classify(measures), "poses": detail,
            "crystal_atoms": len(crystal), "seconds": round(time.time() - started)}


def report(results: pathlib.Path) -> None:
    rows = [json.loads(line) for line in results.read_text().splitlines() if line.strip()]
    for arm in ARMS:
        mine = [r for r in rows if r["arm"] == arm]
        if not mine:
            continue
        print(f"\n== arm {arm}: {len(mine)} runs ==")
        for name, count in core.tally([r["outcome"] for r in mine]).items():
            print(f"  {name:<40} {count:>3}")
    by: dict = {}
    for r in rows:
        by.setdefault((r["pdb"], r["seed"]), {})[r["arm"]] = r["outcome"]
    moved = [(k, v) for k, v in by.items() if len(v) == len(ARMS) and len(set(v.values())) > 1]
    print(f"\nreceptors whose class differs between the arms: {len(moved)}")
    for (pdb, _seed), v in moved:
        print(f"  {pdb}: " + " | ".join(f"{a}: {o}" for a, o in v.items()))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--targets", nargs="+", default=None)
    parser.add_argument("--arms", nargs="+", default=list(ARMS), choices=list(ARMS))
    parser.add_argument("--exhaustiveness", type=int, default=DEFAULT_EXHAUSTIVENESS)
    parser.add_argument("--out", default="bench-out/prep_box_survey")
    parser.add_argument("--report", action="store_true", help="tally the results so far and stop")
    args = parser.parse_args()
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    results = out / "results.jsonl"
    results.touch()
    if args.report:
        report(results)
        return
    done = {(r["pdb"], r["arm"], r["seed"], r["exhaustiveness"])
            for r in (json.loads(x) for x in results.read_text().splitlines() if x.strip())}
    targets = [t.upper() for t in args.targets] if args.targets else [e.pdb_id for e in RECEPTOR_LIBRARY]
    provider = VinaDockingProvider(executable_path_resolver=lambda: vina_executable())
    for pdb_id in targets:
        for arm in args.arms:
            for seed in SEEDS:
                if (pdb_id, arm, seed, args.exhaustiveness) in done:
                    continue
                row = run_one(provider, pdb_id, arm, seed, args.exhaustiveness)
                with results.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(row) + "\n")
                print(f"{pdb_id:<5} {arm:<9} {row['outcome']:<36} {row.get('seconds', '')}s", flush=True)
    report(results)


if __name__ == "__main__":
    main()
