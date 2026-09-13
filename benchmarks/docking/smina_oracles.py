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

## POST-HOC, added after the registered results were committed (40c14f9)

**Oracle (b) came back UNEXPLAINED and STAYS UNEXPLAINED under the rule
above.** smina's Vinardo was 1.53-2.10 kcal/mol more negative on every pose,
and no configuration removed it. What follows is a diagnosis, written and
given its own acceptance rule BEFORE `--explain-b` was first run -- it is not
a re-labelling of the verdict.

The lead, from the two programs' own printouts: smina's built-in `vinardo`
prints `num_tors_div` with weight **0**, while Vina 1.2.7's
`--help_advanced` gives `--weight_vinardo_rot` a default of **0.05846** --
Vina's own N_rot weight reused. And [source:quiroga2016]'s Eq 1 defines the
binding energy as the sum of pair interactions alone, with no rotatable-bond
term anywhere in the paper.

**The intervention changes ONE variable:** Vina 1.2.7 `--scoring vinardo
--weight_vinardo_rot 0`, same receptor file, same poses. The diagnosis is
ACCEPTED iff every pose then lies within SCORE_TOL_KCAL of smina's `vinardo`
(COMPAT). Anything else leaves (b) without a cause.
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


# ---------------------------------------------------------------------------
# Parsers, written AFTER `--probe` fixed the formats and BEFORE any comparison.
#
# score-only prints `Affinity: -8.75406 (kcal/mol)`; --minimize and
# --local_only print `Affinity: -8.73664  -0.97922 (kcal/mol)` then
# `RMSD: 0.10268`. The FIRST number is the affinity in both.
#
# **A minimised output PDBQT carries TWO `minimizedAffinity` remarks** --
# the new value, then the INPUT's value passed through
# (smina_fixtures/probe_min.pdbqt). So the first match is the answer and the
# last is a lie, which is the same passthrough trap `parse_vina_score_output`
# records for Vina's --local_only. The stdout is what gets read.
# ---------------------------------------------------------------------------

_SMINA_AFFINITY_RE = re.compile(r"^Affinity:\s+(-?\d+(?:\.\d+)?)", re.MULTILINE)
_SMINA_RMSD_RE = re.compile(r"^RMSD:\s+(-?\d+(?:\.\d+)?)", re.MULTILINE)
_SMINA_MODEL_AFFINITY_RE = re.compile(r"^REMARK minimizedAffinity\s+(-?\d+(?:\.\d+)?)", re.MULTILINE)
_VINA_MODEL_AFFINITY_RE = re.compile(r"^REMARK VINA RESULT:\s+(-?\d+(?:\.\d+)?)", re.MULTILINE)
_NON_HEAVY_TYPES = {"H", "HD", "HS"}


def smina_affinity(stdout: str) -> float:
    match = _SMINA_AFFINITY_RE.search(stdout)
    if match is None:
        raise ValueError(f"smina printed no Affinity line:\n{stdout[-400:]}")
    return float(match.group(1))


def heavy_coordinates(block: str) -> list[tuple[str, tuple[float, float, float]]]:
    """(atom name, xyz) for every heavy atom, in file order."""
    atoms = []
    for line in block.splitlines():
        if not line.startswith(("ATOM", "HETATM")):
            continue
        if line.split()[-1] in _NON_HEAVY_TYPES:
            continue
        atoms.append((line[12:16].strip(), (float(line[30:38]), float(line[38:46]), float(line[46:54]))))
    return atoms


def rmsd(a, b) -> float:
    # SETUP ASSERTION: an RMSD over two different atom orders is a number
    # about nothing, and would read as a small displacement.
    assert [name for name, _ in a] == [name for name, _ in b], "atom order differs; RMSD undefined"
    total = sum((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2 for (_, p), (_, q) in zip(a, b))
    return (total / len(a)) ** 0.5


def max_displacement(a, b) -> float:
    assert [name for name, _ in a] == [name for name, _ in b], "atom order differs"
    return max(max(abs(p[i] - q[i]) for i in range(3)) for (_, p), (_, q) in zip(a, b))


def score_verdict(vina: list[list[float]], by_config: dict[str, list[list[float]]]) -> dict:
    """Apply the pre-registered rule. `vina[i]` and `by_config[c][i]` are the
    REPEATS values for pose i."""

    def deltas(config):
        return [s[0] - v[0] for s, v in zip(by_config[config], vina)]

    def agrees(config):
        return all(abs(d) <= SCORE_TOL_KCAL for d in deltas(config))

    deterministic = all(len(set(v)) == 1 for v in vina) and all(
        len(set(s)) == 1 for rows in by_config.values() for s in rows
    )
    table = {
        config: {
            "max_abs_delta": round(max(abs(d) for d in deltas(config)), 5),
            "deltas": [round(d, 5) for d in deltas(config)],
            "agree": agrees(config),
        }
        for config in by_config
    }
    if agrees(VERDICT_CONFIGURATION):
        verdict, cause = "AGREE", None
    else:
        signs = {d > 0 for d in deltas(VERDICT_CONFIGURATION) if abs(d) > SCORE_TOL_KCAL}
        rescuers = [c for c in by_config if c != VERDICT_CONFIGURATION and agrees(c)]
        if deterministic and len(signs) == 1 and rescuers:
            verdict, cause = "EXPLAINED_DIVERGENCE", f"agrees under {rescuers}, not under {VERDICT_CONFIGURATION}"
        else:
            verdict, cause = "UNEXPLAINED", None
    return {"verdict": verdict, "cause": cause, "deterministic": deterministic, "by_configuration": table}


def dock_smina(smina, receptor, ligand, box, exhaustiveness, seed, out: pathlib.Path):
    started = time.monotonic()
    done = run([smina, "-r", str(receptor), "-l", str(ligand), *box_args(box),
                "--num_modes", str(NUM_POSES), "--exhaustiveness", str(exhaustiveness),
                "--seed", str(seed), "-o", str(out), *CONFIGURATIONS[VERDICT_CONFIGURATION]])
    elapsed = time.monotonic() - started
    if done.returncode != 0:
        raise RuntimeError(done.stderr or done.stdout)
    return out.read_text(encoding="utf-8"), elapsed


def dock_vina(vina, receptor, ligand, box, exhaustiveness, seed, out: pathlib.Path):
    started = time.monotonic()
    done = run([vina, "--receptor", str(receptor), "--ligand", str(ligand), *box_args(box),
                "--num_modes", str(NUM_POSES), "--exhaustiveness", str(exhaustiveness),
                "--seed", str(seed), "--out", str(out)])
    elapsed = time.monotonic() - started
    if done.returncode != 0:
        raise RuntimeError(done.stderr or done.stdout)
    return out.read_text(encoding="utf-8"), elapsed


def reproducibility(first: str, second: str, affinity_re) -> dict:
    a, b = models(first), models(second)
    same_count = len(a) == len(b)
    scores_a = [float(affinity_re.search(m).group(1)) for m in a]
    scores_b = [float(affinity_re.search(m).group(1)) for m in b]
    scores_agree = same_count and all(abs(x - y) <= SCORE_TOL_KCAL for x, y in zip(scores_a, scores_b))
    coords_agree = same_count and all(
        max_displacement(heavy_coordinates(x), heavy_coordinates(y)) <= COORD_TOL_A for x, y in zip(a, b)
    )
    return {
        "reproducible": bool(same_count and scores_agree and coords_agree),
        "pose_counts": [len(a), len(b)],
        "scores": [scores_a, scores_b],
        "byte_identical": first == second,
    }


def compare() -> int:
    smina, vina = smina_executable(), vina_executable()
    vina_engine = ExecutableVinaEngine(vina)
    raw = HERE / "results" / "smina_oracles_raw"
    raw.mkdir(parents=True, exist_ok=True)
    summary: dict = {
        "smina_version": run([smina, "--version"]).stdout.strip(),
        "vina_version": vina_engine.version(),
        "tolerances": {"score_kcal": SCORE_TOL_KCAL, "coord_a": COORD_TOL_A, "refine_dest_a": REFINE_DEST_TOL_A},
        "verdict_configuration": VERDICT_CONFIGURATION,
        "configurations": {k: list(v) for k, v in CONFIGURATIONS.items()},
    }

    with tempfile.TemporaryDirectory() as scratch_dir:
        scratch = pathlib.Path(scratch_dir)
        receptor, ligand, box = prepare(scratch)
        summary["receptor_sha16"], summary["ligand_sha16"] = sha16(receptor), sha16(ligand)
        summary["box"] = {"center": list(box.center), "size": list(box.size)}
        print(f"receptor sha {summary['receptor_sha16']}  ligand sha {summary['ligand_sha16']}")

        # The pose set, from Vina, written bare.
        vina_out, _ = dock_vina(vina, receptor, ligand, box, POSE_SET_EXHAUSTIVENESS, POSE_SET_SEED,
                                scratch / "vina_poses.pdbqt")
        pose_paths = []
        for index, block in enumerate(models(vina_out)):
            path = scratch / f"pose_{index}.pdbqt"
            path.write_text(block, encoding="utf-8")
            pose_paths.append(path)
        assert pose_paths, "Vina produced no poses; nothing to compare"
        summary["pose_sha16"] = [sha16(p) for p in pose_paths]
        print(f"pose set: {len(pose_paths)} Vina poses")

        # (a) and (b)
        for oracle, vina_function, smina_function in (("a", "vina", "default"), ("b", "vinardo", "vinardo")):
            vina_values = [
                [vina_engine.score_pose(receptor, p, box, vina_function) for _ in range(REPEATS)]
                for p in pose_paths
            ]
            by_config = {}
            for config, flags in CONFIGURATIONS.items():
                rows = []
                for index, p in enumerate(pose_paths):
                    values = []
                    for repeat in range(REPEATS):
                        done = run([smina, "-r", str(receptor), "-l", str(p), *box_args(box),
                                    "--score_only", "--scoring", smina_function, *flags])
                        if done.returncode != 0:
                            raise RuntimeError(done.stderr or done.stdout)
                        values.append(smina_affinity(done.stdout))
                        if repeat == 0:
                            (raw / f"{oracle}_{config}_pose{index}.txt").write_text(done.stdout, encoding="utf-8")
                    rows.append(values)
                by_config[config] = rows
            result = score_verdict(vina_values, by_config)
            result["vina"] = [v[0] for v in vina_values]
            result["smina"] = {c: [r[0] for r in rows] for c, rows in by_config.items()}
            summary[oracle] = result
            print(f"({oracle}) {smina_function} vs Vina {vina_function}: {result['verdict']}"
                  f"  max|d| {VERDICT_CONFIGURATION} {result['by_configuration'][VERDICT_CONFIGURATION]['max_abs_delta']}"
                  f"  deterministic {result['deterministic']}")
            for config, row in result["by_configuration"].items():
                print(f"    {config:9s} max|d| {row['max_abs_delta']:.5f}  {row['deltas']}")

        # (c) the fixtures the adapter's parsers are written against.
        FIXTURES.mkdir(exist_ok=True)
        done = run([smina, "-r", str(receptor), "-l", str(pose_paths[0]), *box_args(box),
                    "--score_only", *CONFIGURATIONS[VERDICT_CONFIGURATION]])
        (FIXTURES / "score_only_vina_pose0_compat_stdout.txt").write_text(done.stdout, encoding="utf-8")

        # (d) within-engine reproducibility
        repro = {}
        first, _ = dock_smina(smina, receptor, ligand, box, REPRO_EXHAUSTIVENESS, REPRO_SEED, scratch / "s1.pdbqt")
        second, _ = dock_smina(smina, receptor, ligand, box, REPRO_EXHAUSTIVENESS, REPRO_SEED, scratch / "s2.pdbqt")
        repro["smina"] = reproducibility(first, second, _SMINA_MODEL_AFFINITY_RE)
        (FIXTURES / "dock_compat_seed11_ex8.pdbqt").write_text(first, encoding="utf-8")
        first, _ = dock_vina(vina, receptor, ligand, box, REPRO_EXHAUSTIVENESS, REPRO_SEED, scratch / "v1.pdbqt")
        second, _ = dock_vina(vina, receptor, ligand, box, REPRO_EXHAUSTIVENESS, REPRO_SEED, scratch / "v2.pdbqt")
        repro["vina_control"] = reproducibility(first, second, _VINA_MODEL_AFFINITY_RE)
        summary["d"] = repro
        for engine, row in repro.items():
            print(f"(d) {engine}: reproducible {row['reproducible']}  byte-identical {row['byte_identical']}"
                  f"  poses {row['pose_counts']}")

        # (e) refinement, on Vina's top pose
        top = pose_paths[0]
        input_atoms = heavy_coordinates(top.read_text(encoding="utf-8"))
        refine: dict = {}
        vina_refined = scratch / "vina_refined.pdbqt"
        started = time.monotonic()
        done = run([vina, "--receptor", str(receptor), "--ligand", str(top), *box_args(box),
                    "--local_only", "--out", str(vina_refined)])
        refine["vina_local_only"] = {
            "accepted": done.returncode == 0 and vina_refined.exists(),
            "score": vina_engine.score_pose(receptor, top, box, "vina", refine=True) if done.returncode == 0 else None,
            "seconds": round(time.monotonic() - started, 3),
        }
        for label, flag in (("smina_minimize", "--minimize"), ("smina_local_only", "--local_only")):
            out = scratch / f"{label}.pdbqt"
            started = time.monotonic()
            done = run([smina, "-r", str(receptor), "-l", str(top), *box_args(box), flag,
                        "-o", str(out), *CONFIGURATIONS[VERDICT_CONFIGURATION]])
            refine[label] = {
                "accepted": done.returncode == 0 and out.exists(),
                "score": smina_affinity(done.stdout) if done.returncode == 0 else None,
                "smina_reported_rmsd": float(_SMINA_RMSD_RE.search(done.stdout).group(1))
                if done.returncode == 0 and _SMINA_RMSD_RE.search(done.stdout) else None,
                "seconds": round(time.monotonic() - started, 3),
            }
            (raw / f"e_{label}.txt").write_text(done.stdout + done.stderr, encoding="utf-8")
        refined_atoms = {}
        for label, path in (("vina_local_only", vina_refined),
                            ("smina_minimize", scratch / "smina_minimize.pdbqt"),
                            ("smina_local_only", scratch / "smina_local_only.pdbqt")):
            if refine[label]["accepted"]:
                blocks = models(path.read_text(encoding="utf-8")) or [path.read_text(encoding="utf-8")]
                refined_atoms[label] = heavy_coordinates(blocks[0])
                refine[label]["rmsd_from_input"] = round(rmsd(input_atoms, refined_atoms[label]), 4)
        if {"vina_local_only", "smina_minimize"} <= refined_atoms.keys():
            destination = rmsd(refined_atoms["vina_local_only"], refined_atoms["smina_minimize"])
            scores = (refine["vina_local_only"]["score"], refine["smina_minimize"]["score"])
            same = destination <= REFINE_DEST_TOL_A and abs(scores[0] - scores[1]) <= SCORE_TOL_KCAL
            refine["destination_rmsd_vina_vs_smina_minimize"] = round(destination, 4)
            refine["verdict"] = "SAME_OPERATION" if same else "ENGINE_SPECIFIC_PROTOCOL"
        else:
            refine["verdict"] = "ENGINE_SPECIFIC_PROTOCOL"
        summary["e"] = refine
        print(f"(e) {refine['verdict']}  " + json.dumps({k: v for k, v in refine.items() if k != 'verdict'}))

        # (f) cost
        timing = {"smina": [], "vina": []}
        for seed in TIMING_SEEDS:
            _, elapsed = dock_smina(smina, receptor, ligand, box, TIMING_EXHAUSTIVENESS, seed, scratch / f"ts{seed}.pdbqt")
            timing["smina"].append(round(elapsed, 1))
            _, elapsed = dock_vina(vina, receptor, ligand, box, TIMING_EXHAUSTIVENESS, seed, scratch / f"tv{seed}.pdbqt")
            timing["vina"].append(round(elapsed, 1))
        summary["f"] = timing
        print(f"(f) seconds per dock at exhaustiveness {TIMING_EXHAUSTIVENESS}: {timing}")

    gate = summary["a"]["verdict"] in {"AGREE", "EXPLAINED_DIVERGENCE"} and summary["d"]["smina"]["reproducible"]
    summary["gate_stages_3_4"] = gate
    SUMMARY.write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(f"\nGATE for Stages 3-4: {'PASS' if gate else 'FAIL'}\nwrote {SUMMARY}")
    return 0


def explain_b() -> int:
    """The post-hoc intervention in the module docstring. One variable."""
    from openchem.chem.vina_engine import parse_vina_score_output

    smina, vina = smina_executable(), vina_executable()
    rows = []
    with tempfile.TemporaryDirectory() as scratch_dir:
        scratch = pathlib.Path(scratch_dir)
        receptor, ligand, box = prepare(scratch)
        vina_out, _ = dock_vina(vina, receptor, ligand, box, POSE_SET_EXHAUSTIVENESS, POSE_SET_SEED,
                                scratch / "vina_poses.pdbqt")
        for index, block in enumerate(models(vina_out)):
            pose = scratch / f"pose_{index}.pdbqt"
            pose.write_text(block, encoding="utf-8")
            base = [vina, "--receptor", str(receptor), "--ligand", str(pose), *box_args(box),
                    "--score_only", "--scoring", "vinardo"]
            as_shipped = run(base)
            rot_zero = run([*base, "--weight_vinardo_rot", "0"])
            smina_row = run([smina, "-r", str(receptor), "-l", str(pose), *box_args(box),
                             "--score_only", "--scoring", "vinardo", *CONFIGURATIONS[VERDICT_CONFIGURATION]])
            for done in (as_shipped, rot_zero, smina_row):
                if done.returncode != 0:
                    raise RuntimeError(done.stderr or done.stdout)
            rows.append({
                "pose": index,
                "vina_vinardo": parse_vina_score_output(as_shipped.stdout),
                "vina_vinardo_rot0": parse_vina_score_output(rot_zero.stdout),
                "smina_vinardo": smina_affinity(smina_row.stdout),
            })
            if index == 0:
                (FIXTURES / "explain_b_vina_vinardo_pose0_stdout.txt").write_text(as_shipped.stdout, encoding="utf-8")
                (FIXTURES / "explain_b_vina_vinardo_rot0_pose0_stdout.txt").write_text(rot_zero.stdout, encoding="utf-8")

    print(f"{'pose':>4} {'Vina vinardo':>13} {'rot=0':>9} {'smina':>9} {'d shipped':>10} {'d rot=0':>9} {'ratio':>7}")
    for r in rows:
        r["delta_shipped"] = round(r["smina_vinardo"] - r["vina_vinardo"], 5)
        r["delta_rot0"] = round(r["smina_vinardo"] - r["vina_vinardo_rot0"], 5)
        r["ratio_rot0_over_shipped"] = round(r["vina_vinardo_rot0"] / r["vina_vinardo"], 4)
        print(f"{r['pose']:>4} {r['vina_vinardo']:>13.3f} {r['vina_vinardo_rot0']:>9.3f} {r['smina_vinardo']:>9.3f}"
              f" {r['delta_shipped']:>10.4f} {r['delta_rot0']:>9.4f} {r['ratio_rot0_over_shipped']:>7.4f}")
    accepted = all(abs(r["delta_rot0"]) <= SCORE_TOL_KCAL for r in rows)
    result = {"rule": "every pose within SCORE_TOL_KCAL of smina after --weight_vinardo_rot 0",
              "accepted": accepted, "max_abs_delta_rot0": max(abs(r["delta_rot0"]) for r in rows), "rows": rows}
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    summary["b_post_hoc_diagnosis"] = result
    SUMMARY.write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(f"\nDIAGNOSIS {'ACCEPTED' if accepted else 'NOT ACCEPTED'} "
          f"(max |d| after rot=0: {result['max_abs_delta_rot0']:.4f}); (b)'s registered verdict is unchanged")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--probe", action="store_true", help="Stage 1 gate and format capture only")
    parser.add_argument("--explain-b", action="store_true", help="the post-hoc one-variable diagnosis of (b)")
    args = parser.parse_args()
    if args.probe:
        return probe()
    return explain_b() if args.explain_b else compare()


if __name__ == "__main__":
    raise SystemExit(main())
