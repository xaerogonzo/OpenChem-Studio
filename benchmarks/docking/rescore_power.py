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
"""

from __future__ import annotations

import argparse
import math
from enum import Enum

from _config import vina_executable
from openchem.chem.binding_site import box_from_ligand
from openchem.chem.docking_providers import VinaDockingProvider
from openchem.chem.receptor_library import find
from openchem.chem.vina_engine import ExecutableVinaEngine
from openchem.domain.docking import pose_score_of
from openchem.net import open_url
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


def spearman(a: list[float], b: list[float]) -> float | None:
    """Rank correlation, written out rather than imported: scipy is not a
    dependency of this project and adding one for a benchmark would be a
    dependency nobody reviewed.

    **VERIFIED BEFORE ITS NUMBERS WERE WRITTEN DOWN**, because a hand-rolled
    statistic with a tie-handling bug produces plausible figures and this
    one's output goes straight into a README:

        [1,2,3,4,5] vs [10,20,30,40,50]   +1.0
        [1,2,3,4,5] vs [50,40,30,20,10]   -1.0
        [1,2,3]     vs [7,7,7]            None -- zero variance, not 0.0
        [1,2,3,4,5] vs [2,1,4,3,5]        +0.8, by 1 - 6*sum(d^2)/(n(n^2-1))
                                          with d = [-1,+1,-1,+1,0]
        [1,2,3,4]   vs [1,2,2,4]          +0.948683..., midranks 1/2.5/2.5/4

    The fourth case is worth keeping for a reason that is about the CHECKER
    rather than the code: it was first written with an expected 0.6, pulled
    from memory, and the function was briefly suspected before the identity
    was worked through by hand. An expectation invented to test a function
    is not an oracle.

    Zero variance returns None rather than 0.0 -- "the ranks do not vary" is
    not "the ranks are uncorrelated", and a benchmark that averaged the
    second into a mean would be reporting a value it never measured.
    """
    n = len(a)
    if n < 2:
        return None

    def ranks(values: list[float]) -> list[float]:
        order = sorted(range(n), key=lambda i: values[i])
        out = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and values[order[j + 1]] == values[order[i]]:
                j += 1
            shared = (i + j) / 2 + 1
            for k in range(i, j + 1):
                out[order[k]] = shared
            i = j + 1
        return out

    ra, rb = ranks(a), ranks(b)
    mean_a, mean_b = sum(ra) / n, sum(rb) / n
    num = sum((x - mean_a) * (y - mean_b) for x, y in zip(ra, rb))
    den = math.sqrt(sum((x - mean_a) ** 2 for x in ra) * sum((y - mean_b) ** 2 for y in rb))
    return None if den == 0 else num / den


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--targets", nargs="*", default=None)
    parser.add_argument("--rescore-with", default="vinardo")
    parser.add_argument("--exhaustiveness", type=int, default=8)
    parser.add_argument("--seed", type=int, default=4712)
    args = parser.parse_args()

    targets = [t.upper() for t in (args.targets or TARGETS)]
    provider = VinaDockingProvider(engine=ExecutableVinaEngine(vina_executable()))

    print(__doc__.split("\n\n")[0])
    print(f"\nLEAKAGE: {LEAKAGE.name} -- {LEAKAGE.value}")
    print(f"rescoring with {args.rescore_with}, exhaustiveness {args.exhaustiveness}, "
          f"seed {args.seed}, {NUM_POSES} poses\n")

    header = (f"{'PDB':<6}{'lig':<5}{'poses':>6}{'best possible':>15}"
              f"{'vina picks':>12}{'rescore picks':>15}{'rho':>7}")
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
        except Exception as exc:  # noqa: BLE001
            print(f"{pdb_id:<6}{entry.ligand_code:<5} docking failed: {str(exc)[:40]}")
            continue

        crystal = centroid(site.ligand_positions)
        shifts, vina_scores, rescores = [], [], []
        for pose in poses:
            middle = pose_centroid(pose.pose_molblock)
            score = pose_score_of(pose)
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
    for label, index in (("vina", 2), ("rescore", 3)):
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
