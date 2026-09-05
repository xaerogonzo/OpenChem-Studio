"""Stage 1 of the Within-Assay Docking Ranking Benchmark: dock the corpus.

    uv run --no-sync python benchmarks/docking/rank_power.py --series 3HS4_CHEMBL...
    uv run --no-sync python benchmarks/docking/rank_power.py --all

Docks every ligand of a selected series into that target's catalogued
receptor, R times, and records each run. `rank_report.py` does the statistics;
nothing here computes a correlation, so a partial run is still evidence and
re-running the report costs seconds rather than hours.

**IT DOCKS THE FROZEN SELECTION AND NOTHING ELSE.** `chembl_corpus.py` writes
`docking_selection` into the manifest before any search runs, so a series
cannot be added or dropped after a rho has been seen.

## The receptor is prepared ONCE per series, and that is not an optimisation

`VinaDockingProvider.dock` re-prepares the receptor on every call, and
`chem/docking_providers._attach_rescores` records that receptor preparation is
**not reproducible**: three preparations of 5C1M gave three different sha256s,
80 of 3794 lines differing on polar-hydrogen rotamers. Per-call preparation is
harmless when one ligand is being docked and ruinous here, because two ligands
in the same series would be scored against two different receptor files -- a
difference in exactly the dimension this benchmark measures.

So this reaches the provider's private conversion methods, as `seed_spread.py`
already does, and prints the digest so a reader can see one file was used.

## The preparation differs from every other benchmark here, on purpose

    {"strip_waters": True, "strip_cofactors": False,
     "strip_ligand_codes": (entry.ligand_code,)}

`redock.py`, `rescore_power.py` and `seed_spread.py` all pass
`strip_cofactors: True`, and `pose_analysis.is_stripped_residue` resolves that
to "delete every non-standard residue" -- which would take **carbonic
anhydrase II's catalytic zinc**, the entire binding determinant for the
sulfonamide series that is 3HS4's whole reason for being in the corpus. That
function's own docstring says so: the flag "covers haem, catalytic zinc and
the rest, which are genuinely part of a site and must stay by default. What
has to go is the one ligand whose coordinates DEFINED the box."

Both halves are asserted before a search runs, because a blocked pocket or a
stripped cofactor compresses every score toward a constant and still yields a
perfectly plausible correlation.

## Seeds are derived per ligand, and that is a statistical requirement

`domain/affinity_range.py` makes it a precondition: two ligands sharing a
replicate seed make their values arrive as correlated pairs. `seed_spread.py`
shares one seed list across ligands, which is right for its question -- the
spread of ONE molecule -- and wrong for this one.

Derived by SHA-256, never `hash()`: `hash()` of a str is randomised per
process, so a "reproducible" protocol would depend on PYTHONHASHSEED. This
project shipped exactly that bug once, in `protonate_at_ph`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
import tempfile
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _config import vina_executable  # noqa: E402
from _stats import REPLICATE_HALVES  # noqa: E402
from openbabel import pybel  # noqa: E402
from openchem.chem.binding_site import (  # noqa: E402
    box_from_ligand,
    ligand_extent_exceeds_box,
    max_heavy_atom_extent,
)
from openchem.chem.docking_providers import VinaDockingProvider  # noqa: E402
from openchem.chem.receptor_library import find  # noqa: E402
from openchem.chem.rescoring import VinaPoseRescorer  # noqa: E402
from openchem.chem.vina_engine import ExecutableVinaEngine, parse_vina_output_pdbqt  # noqa: E402
from openchem.domain.docking import AS_DOCKED  # noqa: E402
from openchem.plugins.interfaces import RescoreRequest  # noqa: E402
from openchem.services.progress import ProgressHandle  # noqa: E402
from openchem.services.receptor_library_service import cached_structure  # noqa: E402
from rdkit import Chem  # noqa: E402
from rdkit.Chem import AllChem  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
DATA = HERE / "data"
RESULTS = HERE / "results"

#: [source:agarwal2022] measured 1/8/25/50/75/100 and found the mRMSD changes
#: little above 25. `rescore_power.py` uses 8 because it asks a pose question;
#: a RANKING measurement needs the search converged enough that a score
#: difference is not a search failure, so this is the shipped default.
EXHAUSTIVENESS = 25

#: Six, not five, so `_stats.REPLICATE_HALVES` splits evenly -- two aggregates
#: over different counts are not comparable. Also clears the derived minimum of
#: 4 in `domain/affinity_range.py`.
REPLICATES = len(REPLICATE_HALVES[0]) + len(REPLICATE_HALVES[1])

NUM_POSES = 9
PH = 7.4
RESCORE_WITH = "vinardo"

#: See the module docstring. Different from every other benchmark here.
PREP = {"strip_waters": True, "strip_cofactors": False}

#: Fixed, so the derived per-ligand seeds are reproducible from the record.
PROTOCOL_SEED = 4712


def derived_seed(protocol_seed: int, molecule_chembl_id: str, replicate: int) -> int:
    """A distinct, reproducible Vina seed per (ligand, replicate).

    SHA-256 rather than `hash()`, which is randomised per process and would
    make a recorded protocol depend on PYTHONHASHSEED -- a bug this project
    has already shipped once.

    PREFIX-STABLE in the replicate index: seed i never depends on the total
    count, so raising R from 6 to 10 keeps the first six runs identical and a
    longer sweep extends a sample rather than replacing it.
    """
    material = f"{protocol_seed}|{molecule_chembl_id}|{replicate}".encode()
    return int.from_bytes(hashlib.sha256(material).digest()[:4], "big") & 0x7FFFFFFF


def embed(smiles: str):
    """One conformer per ligand, one fixed embedding seed.

    The SAME molecule object feeds every replicate, so the only thing varying
    across a series' runs is Vina's own seed. Re-embedding per replicate would
    fold the embedder's randomness into a number reported as the search's.
    """
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    if AllChem.EmbedMolecule(mol, randomSeed=0xC0FFEE) != 0:
        raise RuntimeError("would not embed")
    AllChem.MMFFOptimizeMolecule(mol)
    return mol


def assert_pocket_is_clear(receptor_pdbqt: pathlib.Path, ligand_code: str) -> None:
    """The box-defining ligand is gone from the prepared receptor.

    **SILENT IF WRONG.** An occupied pocket compresses every score toward a
    constant and still produces a plausible rho -- measured at 4.4 kcal/mol on
    1HSG, and size-dependent, so it distorts the ranking rather than shifting
    it. Checked before any search rather than inferred from the results.
    """
    text = receptor_pdbqt.read_text(encoding="utf-8", errors="replace")
    hits = [line for line in text.splitlines() if line[17:20].strip().upper() == ligand_code.upper()]
    if hits:
        raise RuntimeError(
            f"{len(hits)} atoms of {ligand_code} survived preparation -- the search "
            "box is still occupied by the ligand that defined it"
        )


#: AutoDock types that are metals. PDBQT types, not element symbols -- "A" is
#: aromatic carbon and "NA" is a hydrogen-bond-accepting NITROGEN, not sodium,
#: which is why this is a set of the types Vina actually emits rather than a
#: periodic-table lookup.
METAL_AUTODOCK_TYPES = {"ZN", "MG", "MN", "FE", "CU", "CA", "NI", "CO"}


def metal_atom_count(receptor_pdbqt: pathlib.Path) -> int:
    """How many metal atoms reached Vina.

    Reported for every series and ASSERTED for the metalloenzymes, because
    `strip_cofactors: True` -- what every other docking benchmark here passes
    -- would silently remove the catalytic zinc that 3HS4's whole sulfonamide
    series binds through, and the run would look entirely normal.

    **A PDBQT IS NOT A PDB, and reading it as one made this return 0 on a
    receptor whose zinc was present.** The first version took `line[76:78]`,
    which is where the PDB format puts the element symbol. A PDBQT line is
    shorter and ends with the AUTODOCK TYPE instead:

        HETATM 2088 ZN    ZN A 301  -6.720 -1.684 15.288  1.00 4.85      ZN
        ATOM   2050 ZN   UNK A 116  -6.720 -1.684 15.288  0.00 0.00 +0.000 Zn

    so the column check silently found nothing and the assertion this function
    exists for could never have fired. Measured on the real 3HS4: the zinc IS
    retained, and the distinct trailing tokens across the file are exactly
    `A C HD N NA OA S Zn` -- the AutoDock type set.

    The last whitespace-separated token is therefore what is read, which is
    the format's own answer rather than an offset that happens to work.
    """
    count = 0
    for line in receptor_pdbqt.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.startswith(("ATOM", "HETATM")):
            continue
        tokens = line.split()
        if tokens and tokens[-1].upper() in METAL_AUTODOCK_TYPES:
            count += 1
    return count


def source_metal_count(structure_text: str, source_format: str) -> int:
    """Metals in the DEPOSITED structure, so the expectation is derived.

    A hardcoded list of "the metalloenzymes in this corpus" is the blocklist
    that rotted into 27 wrong entries in `inapplicable_calculators`. What the
    deposit contains answers the question directly, and a new target needs no
    code change to be covered.

    Read off the residue NAME rather than the element column, because that is
    the field both PDB and mmCIF spell the same way here and this only has to
    be right about whether a metal exists at all.
    """
    if source_format != "pdb":
        names = [
            line.split()[5].strip().upper()
            for line in structure_text.splitlines()
            if line.startswith(("ATOM", "HETATM")) and len(line.split()) > 5
        ]
    else:
        names = [
            line[17:20].strip().upper()
            for line in structure_text.splitlines()
            if line.startswith(("ATOM", "HETATM"))
        ]
    return sum(1 for name in names if name in METAL_AUTODOCK_TYPES)


def assert_metals_survived(structure_text: str, source_format: str, receptor_pdbqt: pathlib.Path) -> int:
    """A deposit with a metal must hand Vina a receptor with a metal.

    **THE CASE THIS BENCHMARK'S PREPARATION EXISTS FOR.** Every other docking
    benchmark here passes `strip_cofactors: True`, which
    `pose_analysis.is_stripped_residue` resolves to "delete every non-standard
    residue" -- taking carbonic anhydrase II's catalytic zinc, which is what
    its whole sulfonamide series binds through. The run would look entirely
    normal and the ranking would be measuring an artefact.

    Presence rather than an exact count: Open Babel legitimately drops
    symmetry copies and alternate locations, so equality would false-positive
    on correct preparation. The catastrophic case is "all of them", and that
    is what this catches.
    """
    prepared = metal_atom_count(receptor_pdbqt)
    if source_metal_count(structure_text, source_format) and not prepared:
        raise RuntimeError(
            "the deposit carries a metal and the prepared receptor carries none "
            "-- something stripped it, and a metalloenzyme's series would be "
            "measuring an artefact"
        )
    return prepared


def load_series(series_id: str) -> dict:
    path = DATA / "series" / f"{series_id}.json"
    if not path.is_file():
        raise SystemExit(f"No such series {series_id!r}. Run chembl_corpus.py first.")
    return json.loads(path.read_text(encoding="utf-8"))


def done_already(path: pathlib.Path) -> set[tuple[str, int]]:
    """The (molecule, replicate) pairs already on disk, so a run resumes.

    Read rather than assumed: a run that died part-way must not silently redo
    what it finished, and must not skip what it did not.
    """
    if not path.is_file():
        return set()
    seen: set[tuple[str, int]] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        seen.add((record["molecule_chembl_id"], record["replicate"]))
    return seen


def append(path: pathlib.Path, record: dict) -> None:
    """One line, opened and closed per record.

    `benchmarks/free_energy/hydration.py`'s discipline: a run that dies
    part-way must leave every completed result on disk, and a handle held open
    across a multi-hour run does not guarantee that.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")
        handle.flush()


def run_series(series_id: str, provider, engine, rescorer, exhaustiveness: int, replicates: int) -> None:
    series = load_series(series_id)
    entry = find(series["pdb_id"])
    if entry is None:
        raise SystemExit(f"{series['pdb_id']} is not in the receptor library")

    cached = cached_structure(series["pdb_id"])
    if cached is None:
        raise SystemExit(
            f"{series['pdb_id']} is not in the receptor cache. Populate it through "
            "File > Receptor Library -- a measurement that depends on RCSB being up "
            "is not a measurement."
        )
    structure_text, source_format = cached
    site = box_from_ligand(structure_text, source_format, entry.ligand_code)

    out_path = RESULTS / f"{series_id}.jsonl"
    already = done_already(out_path)

    with tempfile.TemporaryDirectory() as scratch:
        scratch_dir = pathlib.Path(scratch)
        receptor_pdbqt = scratch_dir / "receptor.pdbqt"
        started = time.monotonic()
        prep = {**PREP, "strip_ligand_codes": (entry.ligand_code,)}
        provider._convert_receptor_to_pdbqt(
            pybel, structure_text, source_format, receptor_pdbqt, prep, PH
        )
        prep_seconds = time.monotonic() - started
        digest = hashlib.sha256(receptor_pdbqt.read_bytes()).hexdigest()[:16]

        # SETUP ASSERTIONS, BEFORE ANY SEARCH.
        assert_pocket_is_clear(receptor_pdbqt, entry.ligand_code)
        metals = assert_metals_survived(structure_text, source_format, receptor_pdbqt)
        print(
            f"\n[{series_id}] {series['pdb_id']} {series['chembl_target_id']} "
            f"({series['target_organism']}) n={series['n_ligands']} "
            f"span={series['span_pchembl']:.2f}"
        )
        print(
            f"  receptor sha {digest}  prep {prep_seconds:.1f}s  metals {metals}  "
            f"box {tuple(round(v, 2) for v in site.box.center)}"
        )
        print(f"  assay {series['assay_chembl_id']}: {series['assay_description'][:90]}")

        seeds_used: list[int] = []
        for ligand in series["ligands"]:
            molecule_id = ligand["molecule_chembl_id"]
            try:
                mol = embed(ligand["canonical_smiles"])
            except Exception as exc:  # noqa: BLE001 - one bad ligand must not end the series
                print(f"  {molecule_id:16s} SKIPPED -- {exc}")
                continue

            extent = max_heavy_atom_extent(mol)
            overflows = ligand_extent_exceeds_box(extent, site.box)

            ligand_pdbqt = scratch_dir / f"{molecule_id}.pdbqt"
            provider._convert_ligand_to_pdbqt(pybel, mol, ligand_pdbqt, PH)

            for replicate in range(replicates):
                if (molecule_id, replicate) in already:
                    continue
                seed = derived_seed(PROTOCOL_SEED, molecule_id, replicate)
                seeds_used.append(seed)
                run_started = time.monotonic()
                output = engine.dock(
                    receptor_pdbqt, ligand_pdbqt, site.box, NUM_POSES,
                    exhaustiveness, seed, ProgressHandle(),
                )
                poses = parse_vina_output_pdbqt(output)
                best = min((p.binding_affinity_kcal_mol for p in poses), default=None)

                rescore = None
                if poses:
                    rescore = _rescore_best(
                        rescorer, scratch_dir, receptor_pdbqt, poses, site,
                        structure_text, source_format, prep,
                    )

                append(out_path, {
                    "series_id": series_id,
                    "schema_version": series["schema_version"],
                    "molecule_chembl_id": molecule_id,
                    "replicate": replicate,
                    "seed": seed,
                    "protocol_seed": PROTOCOL_SEED,
                    "exhaustiveness": exhaustiveness,
                    "num_poses": NUM_POSES,
                    "scoring_function": "vina",
                    "rescore_with": RESCORE_WITH,
                    "vina_best": best,
                    "rescore_best": rescore,
                    "pose_count": len(poses),
                    "receptor_sha": digest,
                    "ligand_extent_a": extent,
                    "ligand_exceeds_box": overflows,
                    "pchembl_value": ligand["pchembl_value"],
                    "seconds": round(time.monotonic() - run_started, 2),
                })
            flag = "  BOX" if overflows else ""
            print(f"  {molecule_id:16s} pChEMBL {ligand['pchembl_value']:.2f}  done{flag}")

        # A DUPLICATE SEED WOULD MAKE TWO LIGANDS' VALUES ARRIVE AS CORRELATED
        # PAIRS, which voids the statistics rather than merely biasing them.
        assert len(set(seeds_used)) == len(seeds_used), "derived seeds collided within a series"


def _rescore_best(rescorer, scratch_dir, receptor_pdbqt, poses, site, structure_text, source_format, prep):
    """Vinardo on the SAME poses, through the SHIPPED rescorer.

    **The pose is written BARE**, with no `MODEL`/`ENDMDL` wrapper: Vina
    refuses a MODEL-wrapped single-pose ligand, which is exactly the wrapper
    `_raw_pose_to_model` adds for Open Babel. Two consumers of one pose,
    opposite requirements.

    Through `VinaPoseRescorer` rather than `engine.score_pose` so this exercises
    what the panel's own control reaches, including `PoseScore`'s error states.
    """
    paths = []
    for index, pose in enumerate(poses):
        path = scratch_dir / f"pose_{index}.pdbqt"
        path.write_text(pose.pdbqt_text, encoding="utf-8")
        paths.append(path)
    request = RescoreRequest(
        receptor_pdbqt=receptor_pdbqt,
        pose_pdbqt_paths=tuple(paths),
        box=site.box,
        receptor_structure_text=structure_text,
        receptor_source_format=source_format,
        receptor_prep_options=dict(prep),
        # EMPTY, AND SAID RATHER THAN QUIETLY OMITTED. `RescoreRequest` carries
        # molblocks so a rescorer from another family (DSX wants PDB + Mol2) is
        # not locked out, and `VinaPoseRescorer` reads only the PDBQT paths.
        # Building them here means an Open Babel conversion per pose per
        # replicate -- of order 5000 for one corpus -- for a field this
        # rescorer never opens. A non-AutoDock rescorer added later has to
        # fill this in, which is why it is a comment and not an oversight.
        pose_molblocks=(),
    )
    scores = rescorer.rescore(request, AS_DOCKED)
    values = [score.value for score in scores if score.value is not None]
    return min(values) if values else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--series", nargs="*", default=None)
    parser.add_argument("--all", action="store_true", help="every series in the frozen selection")
    parser.add_argument("--exhaustiveness", type=int, default=EXHAUSTIVENESS)
    parser.add_argument("--replicates", type=int, default=REPLICATES)
    args = parser.parse_args()

    manifest_path = DATA / "manifest.json"
    if not manifest_path.is_file():
        raise SystemExit("No corpus. Run chembl_corpus.py first.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    selection = manifest.get("docking_selection") or []

    wanted = args.series or (selection if args.all else None)
    if not wanted:
        print("Frozen docking selection:")
        for series_id in selection:
            print(f"  {series_id}")
        print("\nPass --all to run them, or --series <id> for one.")
        return 0

    outside = [s for s in wanted if s not in selection]
    if outside:
        # NOT REFUSED, but SAID. Running a series outside the frozen selection
        # is a legitimate exploration; letting it into the headline silently is
        # what the freeze exists to prevent, so `rank_report.py` reports only
        # the selection and this line is the warning.
        print(f"NOTE: outside the frozen selection, and excluded from the headline: {outside}")

    engine = ExecutableVinaEngine(vina_executable())
    provider = VinaDockingProvider(engine=engine)
    rescorer = VinaPoseRescorer(score_function=RESCORE_WITH, engine=engine)

    print(__doc__.split("\n\n")[0])
    print(
        f"\nsetup: exhaustiveness {args.exhaustiveness}, {args.replicates} replicates, "
        f"pH {PH}, protocol seed {PROTOCOL_SEED}"
    )
    print(f"setup: prep {PREP} plus the box-defining ligand per receptor")
    print(f"setup: rescoring the same poses with {RESCORE_WITH}")

    for series_id in wanted:
        run_series(series_id, provider, engine, rescorer, args.exhaustiveness, args.replicates)
    print(f"\nwrote {RESULTS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
