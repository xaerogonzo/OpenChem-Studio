"""What does the rescore column actually do?

Two arms, and the first thing to say is what is NOT here.

**RANKING POWER IS NOT MEASURED, AND THAT IS A DATA FINDING RATHER THAN A
DECISION.** The roadmap's Route 2 acceptance criterion is rank correlation
against MEASURED affinities on a set whose overlap with the rescorer's
training data has been checked. Measured 2026-09-03, every route to such a
set is closed from here:

    http://www.pdbbind.org.cn/casf.php            no connection
    http://www.pdbbind.org.cn/download/CASF-2016.tar.gz
                                                  no connection -- and this
                                                  is the plain `wget` URL
                                                  published evaluations use,
                                                  so it was open once
    http://www.pdbbind-cn.org/casf.asp            403
    http://www.pdbbind-plus.org.cn/...            200, but a JavaScript app
                                                  behind an account; the flat
                                                  download paths are gone
    https://bindingmoad.org/                      200, and the domain now
                                                  serves a commercial
                                                  antibody catalogue -- the
                                                  database is gone
    RCSB's own `rcsb_binding_affinity`            present but sparse and
                                                  assay-heterogeneous: 0
                                                  records for 1HSG, 3EML and
                                                  2RH1, and 104 for 4EY7
                                                  spanning Kd 8 nM to IC50
                                                  7120 nM for ONE ligand

A 4000-fold spread across assays is not a ranking oracle, and a benchmark
built on one would produce a number nobody should believe. So ranking power
stays open, and `docs/ROADMAP.md` carries the gap rather than this script
carrying a proxy for it.

**WHAT IS MEASURED HERE IS DOCKING POWER, WHICH HAS FREE GROUND TRUTH.**
Every receptor in the curated library is deposited WITH its own ligand, so
the crystal pose is known without downloading anything. That is CASF's
docking-power protocol: score a set of generated poses and ask whether the
best-scored one is the right one. It is a real question about the rescore --
[source:quiroga2016] claims Vinardo improves docking -- and it is emphatically
NOT the ranking gap, which is what the roadmap measured and what Route 2
exists to close.

Arm 2 needs no oracle at all: how much does the rescore REORDER the poses?
That is what the shipped UI's refusal to re-rank rests on, so it is worth a
number rather than an anecdote.

    uv run --no-sync python benchmarks/docking/rescore_power.py
    uv run --no-sync python benchmarks/docking/rescore_power.py --targets 5C1M 4EY7

Real Vina, roughly 40 s per target at exhaustiveness 8 plus one extra Vina
call per pose for the rescore.

## The smina arms -- PRE-REGISTERED 2026-09-12, before any of them ran

    uv run --no-sync python benchmarks/docking/rescore_power.py                      # A0
    uv run --no-sync python benchmarks/docking/rescore_power.py --engine vina  --rescorer smina:default        # A1
    uv run --no-sync python benchmarks/docking/rescore_power.py --engine smina --rescorer smina:dkoes_scoring  # A2 + A3

Stage 4 of the smina spike (`smina_oracles.py`, `_smina.py`). It asks whether
smina changes DOCKING POWER on these 8 deposited-pose targets. The deposited
ligand is a reference POSE; it is not ground truth for any scoring function.
smina is a Vina fork, so none of this is an independent second opinion.

    arm  search                        score the pick is made on
    A0   Vina 1.2.7 (vina)             NATIVE Vina 1.2.7 vina, plus Vina 1.2.7
                                       vinardo as the rescore -- THE UNCHANGED
                                       SHIPPED PATH, which must reproduce the
                                       recorded Vina 6/8 before any smina row
                                       is believed
    A1   Vina 1.2.7 (vina)             RESCORE smina 2020.12.10 default, as_docked
    A2   smina 2020.12.10 (default)    NATIVE smina 2020.12.10 default
    A3   smina 2020.12.10 (default)    RESCORE smina 2020.12.10 dkoes_scoring, as_docked

A2 and A3 are one run: the search picks are A2, the rescore picks A3.

**A1-A3 cannot run through the shipped provider**, and that is a recorded
seam (ledger seam 4): `_attach_rescores` builds `VinaPoseRescorer` around the
provider's own engine, and the receptor PDBQT is gone when `dock()` returns.
So `--engine` takes the DIRECT path -- the provider's own preparation
methods, the engine, then the rescorer on the same files. Its native picks
come from a different code path and a fresh receptor preparation, so A1's
Vina picks are NOT A0 and are not held to 6/8.

**Leakage, assigned before running** (`Leakage` below; no fourth value):

    Vina 1.2.7 vina / vinardo      TRAINING_PROVENANCE_UNRESOLVED (as before)
    smina default                  TRAINING_PROVENANCE_UNRESOLVED -- it is
                                   Vina's function, PDBbind 2007 (oracle a
                                   agrees with Vina 1.2.7 to 0.004 kcal/mol)
    smina dkoes_scoring            TRAINING_PROVENANCE_UNRESOLVED. The SOURCES
                                   DISAGREE on its training set: koes2013 says
                                   it was trained on CSAR-NRC HiQ 2010 (343
                                   structures from Binding MOAD) and that CSAR
                                   2012 was an independent test set "not
                                   available when the scoring function was
                                   created"; quiroga2016 names HiQ 2010 AND
                                   CSAR 2012. CSAR 2012's five test targets
                                   (koes2013 Table 4: cdk2, chk1, erk2, lpxc,
                                   urokinase) include none of these 8 at the
                                   TARGET level; HiQ 2010's code list is not
                                   obtainable (Binding MOAD is gone), so the
                                   code-level question is open. Whether smina's
                                   built-in dkoes_scoring IS koes2013's
                                   published function is also unverified

Handling, fixed now: no target is dropped after results are seen; a
KNOWN_OVERLAP target, were one found, is kept, flagged, and the arm reported
with and without it; UNRESOLVED is printed on the arm and never called clean.
**n = 8 is descriptive**: a one-target difference is not claimed as one.

### AMENDMENT -- written after the exhaustiveness-8 runs, before any at 25

**The registration above named "the recorded Vina 6/8" and did not name the
exhaustiveness it was recorded at.** `benchmarks/docking/README.md` measured
it at **25**; every arm was then run at this script's default of **8**. A0
at 8 matched the recorded COUNTS (6/8, 6/8, ceiling 8/8) while its per-target
rows differ from the README's -- so it was a coincidence of counts, not a
reproduction, and the first write-up said otherwise.

The exhaustiveness-8 arms are KEPT: all four ran under one protocol, so they
are comparable with each other. The arms are re-run at `--exhaustiveness 25`
with nothing else changed, and A0 at 25 is the reproduction. Its criterion is
the registered one (Vina 6/8, Vinardo 6/8, ceiling 8/8); each target's picks
are ALSO compared with the README's rows and reported as a diagnostic, since
receptor preparation is not reproducible and a row may legitimately move.
"""

from __future__ import annotations

import argparse
import math
import pathlib
import tempfile
from enum import Enum

from _config import smina_executable, vina_executable
from _stats import spearman
from openbabel import pybel
from openchem.chem.binding_site import box_from_ligand
from openchem.chem.docking_providers import DEFAULT_PREPARATION_PH, VinaDockingProvider
from openchem.chem.receptor_library import find
from openchem.chem.rescoring import VinaPoseRescorer
from openchem.chem.vina_engine import ExecutableVinaEngine, parse_vina_output_pdbqt
from openchem.domain.docking import AS_DOCKED, pose_score_of
from openchem.net import open_url
from openchem.plugins.interfaces import RescoreRequest
from openchem.services.progress import ProgressHandle
from openchem.services.receptor_library_service import fetch_structure
from rdkit import Chem
from rdkit.Chem import AllChem

PREP = {"strip_waters": True, "strip_cofactors": True}

#: The same spread `redock.py` uses, for the same reason: two GPCRs, an
#: enzyme with a textbook answer, a nuclear receptor, the hERG channel, and
#: the mu-opioid pair the ranking work was reported against. Not one SMILES
#: is typed -- every ligand is the receptor's own deposited component,
#: fetched by chemical-component code.
TARGETS = ["1HSG", "4DKL", "3EML", "2RH1", "1ERE", "4EY7", "8EF5", "5C1M"]

#: Poses per run. More than `redock.py`'s 5, because this arm is about
#: CHOOSING among poses and a wider set gives the two functions more to
#: disagree about.
NUM_POSES = 9

#: Centroid displacement, in Angstrom, at or below which a pose counts as
#: having found the site. `redock.py`'s own "same pocket" threshold, reused
#: rather than re-chosen -- and it is a CENTROID displacement, not a
#: symmetry-corrected RMSD, because this has no atom correspondence to the
#: deposited ligand. That makes it a coarser test than CASF's 2 A RMSD
#: criterion and it must not be reported as though it were the same thing.
SAME_POCKET_A = 3.0


class Leakage(Enum):
    """Three-valued, because "we could not establish it" is not "there is
    none". Same shape as the sources registry's
    citation/citation_and_claim/unverified, and as `ArmStatus` in
    `benchmarks/solubility/nonaqueous.py`."""

    KNOWN_OVERLAP = "codes intersect a training or selection set"
    NO_IDENTIFIED_OVERLAP = "no intersection at the code level"
    TRAINING_PROVENANCE_UNRESOLVED = "the training set could not be obtained"


#: **UNRESOLVED, AND SAYING SO IS THE POINT.**
#:
#: [source:quiroga2016] section 3.1 names Vinardo's selection set precisely:
#: 122 of the 195 PDBbind Core 2013 structures, evaluated further on
#: Iridium-HT, CSAR 2012 and Astex-diverse. Vina was trained on PDBbind 2007.
#: Both are checkable IN PRINCIPLE by intersecting PDB codes -- and neither
#: list is obtainable from here, because they live behind the same PDBbind
#: registration that closed CASF-2016.
#:
#: So the overlap between this script's eight targets and either set is
#: UNKNOWN. It is not asserted absent. The paper does report its biggest
#: docking improvements on the sets NOT used in development, which is
#: evidence against over-training and is the authors' own claim rather than
#: a measurement of ours.
LEAKAGE = Leakage.TRAINING_PROVENANCE_UNRESOLVED

#: Per scoring function, for the smina arms. See the module docstring's
#: pre-registration for the reason behind each; all three are unresolved.
ARM_LEAKAGE = {
    "vina:vina": Leakage.TRAINING_PROVENANCE_UNRESOLVED,
    "vina:vinardo": Leakage.TRAINING_PROVENANCE_UNRESOLVED,
    "smina:default": Leakage.TRAINING_PROVENANCE_UNRESOLVED,
    "smina:dkoes_scoring": Leakage.TRAINING_PROVENANCE_UNRESOLVED,
}


def build_engine(name: str):
    if name == "vina":
        return ExecutableVinaEngine(vina_executable())
    from _smina import SminaEngine

    return SminaEngine(smina_executable())


def build_rescorer(qualified: str):
    """An ENGINE-QUALIFIED rescorer id -- 'vina:vinardo', 'smina:default'.
    A bare 'vinardo' names two quantities 1.5-2.1 kcal/mol apart (ledger
    seam 5), so the harness refuses to take one."""
    engine_name, _, function = qualified.partition(":")
    if engine_name == "vina" and function in ("vina", "vinardo"):
        return VinaPoseRescorer(function, engine=build_engine("vina"))
    if engine_name == "smina":
        from _smina import SminaPoseRescorer

        return SminaPoseRescorer(function, build_engine("smina"))
    raise SystemExit(f"--rescorer must be engine-qualified (vina:vinardo, smina:<function>); got {qualified!r}")


def dock_direct(text, source_format, site, mol, engine, rescorer, exhaustiveness, seed):
    """The DIRECT path for the smina arms: the shipped provider's own
    preparation methods, then the engine, then the rescorer on the SAME
    receptor and pose files. Returns (pose, PoseScore) pairs."""
    preparer = VinaDockingProvider(engine=ExecutableVinaEngine(vina_executable()))
    with tempfile.TemporaryDirectory() as scratch_dir:
        scratch = pathlib.Path(scratch_dir)
        receptor, ligand = scratch / "receptor.pdbqt", scratch / "ligand.pdbqt"
        preparer._convert_receptor_to_pdbqt(pybel, text, source_format, receptor, PREP, DEFAULT_PREPARATION_PH)
        preparer._require_receptor_in_box(receptor, site.box)
        preparer._convert_ligand_to_pdbqt(pybel, mol, ligand, DEFAULT_PREPARATION_PH)
        raw = parse_vina_output_pdbqt(
            engine.dock(receptor, ligand, site.box, NUM_POSES, exhaustiveness, seed, ProgressHandle())
        )
        poses = [preparer._raw_pose_to_model(pybel, r) for r in raw]
        paths = []
        for index, r in enumerate(raw):
            path = scratch / f"pose_{index}.pdbqt"
            path.write_text(r.pdbqt_text, encoding="utf-8")  # BARE -- see _rescore_best
            paths.append(path)
        scores = rescorer.rescore(
            RescoreRequest(
                receptor_pdbqt=receptor, pose_pdbqt_paths=tuple(paths), box=site.box,
                receptor_structure_text=text, receptor_source_format=source_format,
                receptor_prep_options=dict(PREP), pose_molblocks=tuple(p.pose_molblock for p in poses),
            ),
            AS_DOCKED,
        )
    return list(zip(poses, scores))


def component_smiles(comp_id: str) -> str | None:
    """The deposited component's own SMILES, from RCSB. Nothing here is
    typed from memory -- this project has already recorded a benchmark whose
    story changed when two remembered SMILES were replaced by the corpus's
    own."""
    url = f"https://data.rcsb.org/rest/v1/core/chemcomp/{comp_id}"
    try:
        with open_url(url, timeout=30) as response:
            import json

            data = json.load(response)
    except Exception:  # noqa: BLE001 - a target that cannot be fetched is skipped
        return None
    for entry in data.get("pdbx_chem_comp_descriptor", []) or []:
        if entry.get("type") == "SMILES_CANONICAL":
            return entry.get("descriptor")
    for entry in data.get("pdbx_chem_comp_descriptor", []) or []:
        if entry.get("type") == "SMILES":
            return entry.get("descriptor")
    return None


def centroid(points) -> tuple[float, float, float]:
    n = len(points)
    return (
        sum(p[0] for p in points) / n,
        sum(p[1] for p in points) / n,
        sum(p[2] for p in points) / n,
    )


def pose_centroid(molblock: str) -> tuple[float, float, float] | None:
    mol = Chem.MolFromMolBlock(molblock, sanitize=False)
    if mol is None or mol.GetNumConformers() == 0:
        return None
    conf = mol.GetConformer()
    heavy = [
        (conf.GetAtomPosition(a.GetIdx()).x,
         conf.GetAtomPosition(a.GetIdx()).y,
         conf.GetAtomPosition(a.GetIdx()).z)
        for a in mol.GetAtoms()
        if a.GetSymbol() != "H"
    ]
    return centroid(heavy) if heavy else None


# `spearman` MOVED to `_stats.py` when the ranking benchmark needed the same
# function. Two implementations of one statistic is how two benchmarks come to
# disagree about a number, and this one is already verified against five
# hand-worked cases -- including one where the author's remembered expectation
# was the thing that was wrong. Its verification docstring travelled with it.


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--targets", nargs="*", default=None)
    parser.add_argument("--rescore-with", default="vinardo")
    parser.add_argument("--exhaustiveness", type=int, default=8)
    parser.add_argument("--seed", type=int, default=4712)
    parser.add_argument("--engine", choices=("vina", "smina"), default=None,
                        help="take the DIRECT path with this search engine (smina arms A1-A3)")
    parser.add_argument("--rescorer", default=None,
                        help="engine-qualified rescorer for the direct path, e.g. smina:default")
    args = parser.parse_args()

    targets = [t.upper() for t in (args.targets or TARGETS)]
    provider = VinaDockingProvider(engine=ExecutableVinaEngine(vina_executable()))
    direct = args.engine is not None
    if direct and not args.rescorer:
        raise SystemExit("--engine needs --rescorer: the direct path always rescores")
    engine = build_engine(args.engine) if direct else None
    rescorer = build_rescorer(args.rescorer) if direct else None
    search_label = "vina:vina" if not direct or args.engine == "vina" else "smina:default"
    rescore_label = args.rescorer if direct else f"vina:{args.rescore_with}"

    print(__doc__.split("\n\n")[0])
    if direct:
        print(f"\nDIRECT PATH  search {engine.version()} ({search_label}, NATIVE score)")
        print(f"             rescore {rescore_label}, as_docked")
        print(f"LEAKAGE: search {ARM_LEAKAGE[search_label].name}; rescore {ARM_LEAKAGE[rescore_label].name}")
    else:
        print(f"\nLEAKAGE: {LEAKAGE.name} -- {LEAKAGE.value}")
    print(f"rescoring with {rescore_label}, exhaustiveness {args.exhaustiveness}, "
          f"seed {args.seed}, {NUM_POSES} poses\n")

    search_column = "search picks" if direct else "vina picks"
    header = (f"{'PDB':<6}{'lig':<5}{'poses':>6}{'best possible':>15}"
              f"{search_column:>12}{'rescore picks':>15}{'rho':>7}")
    print(header)
    print("-" * len(header))

    rows = []
    for pdb_id in targets:
        entry = find(pdb_id)
        text, source_format = fetch_structure(pdb_id)
        site = box_from_ligand(text, source_format, entry.ligand_code)

        smiles = component_smiles(entry.ligand_code)
        if not smiles:
            print(f"{pdb_id:<6}{entry.ligand_code:<5} no SMILES from RCSB - skipped")
            continue
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            print(f"{pdb_id:<6}{entry.ligand_code:<5} SMILES did not parse - skipped")
            continue
        mol = Chem.AddHs(mol)
        if AllChem.EmbedMolecule(mol, randomSeed=0xC0FFEE) != 0:
            print(f"{pdb_id:<6}{entry.ligand_code:<5} would not embed - skipped")
            continue
        AllChem.MMFFOptimizeMolecule(mol)

        try:
            if direct:
                pairs = dock_direct(text, source_format, site, mol, engine, rescorer,
                                    args.exhaustiveness, args.seed)
            else:
                poses = provider.dock(
                    receptor_structure_text=text,
                    receptor_source_format=source_format,
                    ligand_mol=mol,
                    box=site.box,
                    num_poses=NUM_POSES,
                    progress=ProgressHandle(),
                    receptor_prep_options=PREP,
                    search_options={
                        "exhaustiveness": args.exhaustiveness,
                        "seed": args.seed,
                        # The SHIPPED path, not a direct call to the rescorer:
                        # this exercises the same `search_options` key the panel
                        # sends, so the benchmark measures what a user gets.
                        "rescore_with": args.rescore_with,
                    },
                )
                pairs = [(pose, pose_score_of(pose)) for pose in poses]
        except Exception as exc:  # noqa: BLE001
            print(f"{pdb_id:<6}{entry.ligand_code:<5} docking failed: {str(exc)[:40]}")
            continue

        crystal = centroid(site.ligand_positions)
        shifts, vina_scores, rescores = [], [], []
        for pose, score in pairs:
            middle = pose_centroid(pose.pose_molblock)
            if middle is None or score is None or not score.succeeded:
                continue
            shifts.append(math.dist(middle, crystal))
            vina_scores.append(pose.binding_affinity_kcal_mol)
            rescores.append(score.value)

        if len(shifts) < 2:
            print(f"{pdb_id:<6}{entry.ligand_code:<5} fewer than two scored poses - skipped")
            continue

        # The pose each function RANKS FIRST -- lower (more negative) is
        # better for both, which is the only thing the two scales share.
        vina_pick = shifts[min(range(len(shifts)), key=lambda i: vina_scores[i])]
        rescore_pick = shifts[min(range(len(shifts)), key=lambda i: rescores[i])]
        # THE CEILING, and it is what separates two different failures: a
        # search that never found the site, and a search that found it while
        # the score picked something else. Without it a bad row is
        # unattributable.
        best_possible = min(shifts)
        rho = spearman(vina_scores, rescores)

        rows.append((pdb_id, best_possible, vina_pick, rescore_pick, rho))
        print(f"{pdb_id:<6}{entry.ligand_code:<5}{len(shifts):>6}"
              f"{best_possible:>13.2f} A{vina_pick:>10.2f} A{rescore_pick:>13.2f} A"
              f"{'  n/a' if rho is None else f'{rho:>7.2f}'}")

    if not rows:
        print("\nNo target produced a scored pose set.")
        return 1

    print("\n=== docking power: does the top-scored pose find the site? ===")
    # Fully qualified on the direct path, where "vina" could be smina's search.
    labels = (f"{search_label} NATIVE", f"{rescore_label} RESCORE") if direct else ("vina", "rescore")
    for label, index in ((labels[0], 2), (labels[1], 3)):
        hits = sum(1 for r in rows if r[index] <= SAME_POCKET_A)
        mean = sum(r[index] for r in rows) / len(rows)
        print(f"  {label:<10} {hits}/{len(rows)} within {SAME_POCKET_A} A"
              f"   mean displacement {mean:.2f} A")
    ceiling = sum(1 for r in rows if r[1] <= SAME_POCKET_A)
    print(f"  {'ceiling':<10} {ceiling}/{len(rows)} -- the search FOUND a pose that close, "
          f"whether or not either score picked it")

    print("\n=== how much does the rescore reorder the poses? ===")
    rhos = [r[4] for r in rows if r[4] is not None]
    if rhos:
        print(f"  Spearman(vina, rescore) over poses within a run:")
        print(f"    mean {sum(rhos)/len(rhos):+.2f}   min {min(rhos):+.2f}   max {max(rhos):+.2f}")
        print(f"    disagreeing outright (rho < 0): {sum(1 for r in rhos if r < 0)}/{len(rhos)}")
    print("\n  A rho well below 1 is why the panel does not re-rank on the second")
    print("  column. It says the two functions order the SAME poses differently; it")
    print("  says nothing about which ordering is better, which is the ranking")
    print("  question this script cannot answer.")

    print("\n=== how much would this run detect? ===")
    print(f"  n = {len(rows)} targets. A {len(rows)}-target set cannot distinguish two")
    print("  functions that differ by less than roughly one target, so equal counts")
    print("  here are NOT evidence that the two are equivalent -- only that no")
    print("  difference large enough to see at this n showed up. Widen the target")
    print("  list before reading anything into a small gap.")

    print(f"\n=== scope ===")
    print("  MEASURED: docking power -- pose selection, against the deposited ligand.")
    print("  NOT MEASURED: ranking power -- one ligand against another, which needs")
    print("  measured affinities. See this module's docstring for the six routes")
    print(f"  tried and what each returned. Leakage: {LEAKAGE.name}.")
    print("  Centroid displacement, NOT symmetry-corrected RMSD: coarser than CASF's")
    print("  2 A criterion and not comparable to a published docking-power figure.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
