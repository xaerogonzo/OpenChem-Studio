"""Stage 2 of the smina spike: is smina's number the number the harness thinks it is?

    set OPENCHEM_SMINA=<env>\\Library\\bin\\smina.exe
    uv run --no-sync python benchmarks/docking/smina_oracles.py --probe
    uv run --no-sync python benchmarks/docking/smina_oracles.py

## What this spike is for, and what it is not

smina ([source:koes2013]) is the only obtainable candidate that is BOTH a
docking engine and a rescorer, so it is the arm that shows whether
`VinaEngine` / `PoseRescorer` are abstractions or Vina-shaped holes. **It is
NOT an independent second opinion**: it is a fork of AutoDock Vina 1.1.2 (its
own `--version` says so), and Vinardo -- also Vina-family -- is already a
ranking null. Nothing measured here reopens the family-independence question.

Before any adapter is written, these oracles establish what smina's numbers
ARE on files this application prepares, so an adapter cannot quietly make
smina "fit" by translating away a difference nobody measured.

## PRE-REGISTRATION -- committed before the first comparison was run

Everything in this section was fixed, and committed, before this script
produced a single smina-versus-Vina number. `--probe` runs first and is
exempt: it docks with smina and scores smina's OWN poses, to capture output
FORMATS (Stage 1's gate: a binary that starts and docks one ligand). It never
scores a Vina pose, so it cannot inform a verdict below.

### The case

5C1M (mu-opioid) from the local receptor cache, box from its own deposited
ligand VF1, prepared ONCE through `VinaDockingProvider._convert_receptor_to_pdbqt`
with `seed_spread.py`'s preparation (waters and cofactors stripped, VF1
stripped, pH 7.4). Ligand: fentanyl, component 7V7 (from 8EF5), embedded with
`seed_spread.embed`'s fixed seed and converted through
`_convert_ligand_to_pdbqt` at the same pH. This is the pose set
`chem/rescoring.py`'s docstring characterised against Vina 1.2.7.

**Both programs read the IDENTICAL receptor and pose files.** Receptor
preparation is not reproducible here (three preparations, three sha256s), so
a comparison across two preparations would measure preparation.

The pose set: Vina 1.2.7, exhaustiveness 25, seed 11, 9 modes, each pose
written BARE (no MODEL/ENDMDL) exactly as `_rescore_best` writes it.

### Tolerances

    SCORE_TOL_KCAL  = 0.01   Vina prints three decimals, and this project's
                             reconstruction of Vina's `unbound` term had a
                             worst residual of 0.005 (chem/rescoring.py)
    COORD_TOL_A     = 0.001  PDBQT prints coordinates to three decimals
    REFINE_DEST_TOL_A = 0.02 heavy-atom RMSD between two engines' REFINED
                             poses. Vina's refinement moves this ligand
                             0.079 A (domain/docking.py), so two
                             implementations of ONE operation must agree on
                             the destination to a quarter of that

### Verdicts, exactly one per comparison

    AGREE                 every pose within SCORE_TOL_KCAL
    EXPLAINED_DIVERGENCE  NOT within tolerance, AND all three hold:
                          deterministic (3 repeat calls identical),
                          consistent in sign across the pose set, and
                          removed -- to within tolerance -- by a NAMED
                          configuration from the diagnostic arms below
    UNEXPLAINED           anything else

### smina configurations

smina's help text names two defaults that differ from Vina's behaviour, so
four configurations are run on every score-only comparison:

    DEFAULTS   no extra flags
    NO_ADDH    --addH 0          smina "automatically add[s] hydrogens in
                                 ligands (on by default)"; this pipeline has
                                 already protonated the ligand at a DECLARED
                                 pH, so adding more would change the molecule
    FLEX_H     --flex_hydrogens  hidden option: "Enable torsions effecting
                                 only hydrogens (e.g. OH groups) ... provides
                                 compatibility with Vina"
    COMPAT     --addH 0 --flex_hydrogens

**The VERDICT is taken on COMPAT**, chosen now for the reasons in the two
rows above: it is smina run on this application's already-prepared inputs
under its own documented Vina-compatibility switch. DEFAULTS, NO_ADDH and
FLEX_H are DIAGNOSTICS -- they are what can name the cause of a divergence,
and a DEFAULTS-vs-COMPAT difference is itself a seam finding (an adapter
would have to pass flags to get the Vina-shaped answer).

### The oracles

    a  smina `default` vs Vina 1.2.7 `vina`, --score_only, all poses
    b  smina `vinardo` vs Vina 1.2.7 `vinardo`, --score_only, all poses.
       smina is Vinardo's REFERENCE implementation ([source:quiroga2016]
       section 2.2), so this checks Vina 1.2.7's later re-implementation --
       including Table 3's radii, which Vina's CLI does not expose -- against
       the paper's own code. A reference-implementation check, not an
       independent one
    c  raw smina docking output and score-only / minimise stdout, kept as
       fixtures under `smina_fixtures/` for the adapter's parsers
    d  within-engine reproducibility: same seed, same inputs, same options,
       docked twice (exhaustiveness 8), for smina AND for Vina as the
       control. REPRODUCIBLE = same pose count and order, every score within
       SCORE_TOL_KCAL, every heavy atom within COORD_TOL_A. Byte identity is
       recorded as an observation, never as the contract. This says nothing
       about cross-engine agreement
    e  smina --minimize vs Vina --local_only on Vina's top pose, both scored
       under `vina`/`default`: whether each accepts the pose, heavy-atom RMSD
       from the input, final score, runtime. Verdict SAME_OPERATION iff both
       accept, the two refined poses are within REFINE_DEST_TOL_A of each
       other AND the scores AGREE; otherwise ENGINE_SPECIFIC_PROTOCOL.
       smina's own `--local_only` ("you probably want to use --minimize") is
       run as a diagnostic. Differing flag names decide nothing
    f  wall clock per dock at exhaustiveness 25, seeds 11/22/33, each engine.
       A cost line only -- one run is not a duration

### Gate for Stages 3-4

(a) is AGREE or EXPLAINED_DIVERGENCE, and (d) is REPRODUCIBLE for smina.
Otherwise the spike's write-up is a refusal carrying this evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _config import smina_executable, vina_executable  # noqa: E402
from openbabel import pybel  # noqa: E402
from openchem import paths  # noqa: E402
from openchem.chem.binding_site import box_from_ligand  # noqa: E402
from openchem.chem.docking_providers import VinaDockingProvider  # noqa: E402
from openchem.chem.receptor_library import find  # noqa: E402
from openchem.chem.vina_engine import ExecutableVinaEngine  # noqa: E402
from seed_spread import component_smiles, embed  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
FIXTURES = HERE / "smina_fixtures"
SUMMARY = HERE / "smina_oracles.json"

RECEPTOR = "5C1M"
LIGAND_CODE = "7V7"
PREP = {"strip_waters": True, "strip_cofactors": True}
PH = 7.4
NUM_POSES = 9

SCORE_TOL_KCAL = 0.01
COORD_TOL_A = 0.001
REFINE_DEST_TOL_A = 0.02

POSE_SET_EXHAUSTIVENESS = 25
POSE_SET_SEED = 11
REPRO_EXHAUSTIVENESS = 8
REPRO_SEED = 11
TIMING_EXHAUSTIVENESS = 25
TIMING_SEEDS = (11, 22, 33)
REPEATS = 3

CONFIGURATIONS = {
    "DEFAULTS": (),
    "NO_ADDH": ("--addH", "0"),
    "FLEX_H": ("--flex_hydrogens",),
    "COMPAT": ("--addH", "0", "--flex_hydrogens"),
}
VERDICT_CONFIGURATION = "COMPAT"


def sha16(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def box_args(box) -> list[str]:
    cx, cy, cz = box.center
    sx, sy, sz = box.size
    return [
        "--center_x", str(cx), "--center_y", str(cy), "--center_z", str(cz),
        "--size_x", str(sx), "--size_y", str(sy), "--size_z", str(sz),
    ]


def run(argv: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(argv, capture_output=True, text=True)


def prepare(scratch: pathlib.Path):
    """The receptor, the ligand and the box, each built ONCE."""
    entry = find(RECEPTOR)
    structure = (paths.data_root() / "receptors" / f"{RECEPTOR}.pdb").read_text(encoding="utf-8")
    site = box_from_ligand(structure, "pdb", entry.ligand_code)
    provider = VinaDockingProvider(engine=ExecutableVinaEngine(vina_executable()))
    receptor = scratch / "receptor.pdbqt"
    provider._convert_receptor_to_pdbqt(
        pybel, structure, "pdb", receptor,
        {**PREP, "strip_ligand_codes": (entry.ligand_code,)}, PH,
    )
    ligand = scratch / "ligand.pdbqt"
    provider._convert_ligand_to_pdbqt(pybel, embed(component_smiles(LIGAND_CODE)), ligand, PH)
    return receptor, ligand, site.box


_MODEL_RE = re.compile(r"^MODEL\s+\d+\s*\n(.*?)^ENDMDL", re.MULTILINE | re.DOTALL)


def models(text: str) -> list[str]:
    """Pose blocks, BARE -- neither engine accepts a MODEL-wrapped single
    ligand, which is `_rescore_best`'s own finding."""
    return [m.group(1) for m in _MODEL_RE.finditer(text)]


def probe() -> int:
    """Stage 1's gate plus format capture. smina's OWN poses only."""
    smina = smina_executable()
    FIXTURES.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as scratch_dir:
        scratch = pathlib.Path(scratch_dir)
        receptor, ligand, box = prepare(scratch)
        print(f"receptor sha {sha16(receptor)}  ligand sha {sha16(ligand)}  box {box.center} {box.size}")

        out = scratch / "dock.pdbqt"
        argv = [smina, "-r", str(receptor), "-l", str(ligand), *box_args(box),
                "--num_modes", str(NUM_POSES), "--exhaustiveness", "8", "--seed", "11",
                "-o", str(out)]
        started = time.monotonic()
        docked = run(argv)
        print(f"dock exit {docked.returncode} in {time.monotonic() - started:.1f}s")
        (FIXTURES / "probe_dock_stdout.txt").write_text(docked.stdout + docked.stderr, encoding="utf-8")
        if docked.returncode != 0 or not out.exists():
            print(docked.stderr or docked.stdout)
            print("GATE FAILED: smina did not dock.")
            return 1
        text = out.read_text(encoding="utf-8")
        (FIXTURES / "probe_dock_out.pdbqt").write_text(text, encoding="utf-8")
        blocks = models(text)
        print(f"GATE: smina docked, {len(blocks)} MODEL blocks")
        if not blocks:
            return 1

        pose = scratch / "smina_pose0.pdbqt"
        pose.write_text(blocks[0], encoding="utf-8")
        for label, extra in (
            ("score_only", ["--score_only"]),
            ("minimize", ["--minimize", "-o", str(scratch / "min.pdbqt")]),
            ("local_only", ["--local_only", "-o", str(scratch / "local.pdbqt")]),
        ):
            done = run([smina, "-r", str(receptor), "-l", str(pose), *box_args(box), *extra])
            (FIXTURES / f"probe_{label}_stdout.txt").write_text(done.stdout + done.stderr, encoding="utf-8")
            print(f"{label}: exit {done.returncode}")
        for name in ("min.pdbqt", "local.pdbqt"):
            produced = scratch / name
            if produced.exists():
                (FIXTURES / f"probe_{name}").write_text(produced.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"wrote {FIXTURES}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--probe", action="store_true", help="Stage 1 gate and format capture only")
    args = parser.parse_args()
    if args.probe:
        return probe()
    raise SystemExit("The comparison run is written after the probe fixes the output formats.")


if __name__ == "__main__":
    raise SystemExit(main())
