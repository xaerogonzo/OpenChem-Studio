"""Regenerate the real-ORCA fixtures of the Fukui tests: `python benchmarks/fukui_gate_2/make_fixtures.py [output directory [case name ...]]`.

Each fixture is VERBATIM extracts of a real ORCA 6.1.1 run of the input the application's own `build_input` writes (`OrcaQuantumEngineProvider`, calc type
`fukui`), the way `tests/fixtures/orca/water_fukui.out` is: the version banner, each job's echo of its charge, multiplicity and electron count, the guess it
started from, its <S**2> lines, its Hirshfeld block and its energy line, in the order ORCA printed them; the first job also keeps its Mulliken and Loewdin
blocks so that a parse reading the wrong block would be caught. Every other line (SCF iterations, about 100 KB a job) is dropped. A job that did not finish
keeps what it printed before it stopped and no more.

The cases (what each exists to test):

    acetone_fukui_diffuse_hf.out         acetone at its HF/6-311+G** optimized geometry, HF 6-311+G**: the neutral's N+1 state has more than one SCF solution,
                                         and the HCore start is 1.0 eV below ORCA's default one (the case `benchmarks/fukui_gate/artifacts/anion_guess_probe_diffuse.json`
                                         found): five jobs, the lowest solution replaces the default.
    methoxide_fukui_anion.out            CH3O-, B3LYP 6-31+G*: an ANION at a basis with diffuse functions, so its own state has two extra starts (HCore, Hueckel), and
                                         its dianion comes LAST with two of its own: seven jobs (the order is `chem/fukui_plan.py`'s).
    cyanide_fukui_anion_no_diffuse.out   CN-, B3LYP 6-31G** at its optimized bond length: an anion without diffuse functions, three jobs and no extra start; the case the first
                                         gate decided on, whose stored f+ this reproduces to 2e-5.
    methoxide_fukui_failed_dianion.out   the methoxide case with its dianion's default job (the fifth) given two SCF iterations: it cannot converge, ORCA ends the run
                                         with exit code 115, the four jobs before it are intact, and the dianion's own extra starts never run.

Two fixtures were written by Fukui v2's builder, in which an anion had no dianion job, and are NOT regenerated here (the builder no longer reproduces their `.inp`;
they stay as real ORCA outputs of an anion run without a dianion, which the parser still reads as f- alone):

    methoxide_fukui_fminus.out           CH3O-, B3LYP 6-31+G*: four jobs (the anion, the neutral radical, and the anion again from HCore and from Hueckel).
    methoxide_fukui_failed_start.out     the same with its last job (Hueckel) given two SCF iterations.

The geometry of the methoxide cases is RDKit ETKDG (seed 7) then MMFF, which is a probe of the calculation and not of a geometry; acetone's is read from
the ORCA optimization of `benchmarks/fukui_gate/grid_sweep.py`, and cyanide's is its ORCA B3LYP/6-31G** optimized bond length, both typed below.
"""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

from rdkit import Chem
from rdkit.Chem import AllChem
from rdkit.Geometry import Point3D

from openchem.chem.orca_engine import OrcaQuantumEngineProvider

ORCA = r"D:\ORCA\orca.exe"

#: Acetone at its ORCA HF/6-311+G** optimized geometry (atom order: methyl C, carbonyl C, methyl C, O, then the six hydrogens, as the application embeds it).
ACETONE_HF_A = """C       -1.276505      0.018665     -0.224669
C       -0.034768     -0.000638      0.639125
C        1.293304     -0.018451     -0.085021
O       -0.099255     -0.001706      1.825699
H       -1.308332      0.941817     -0.797549
H       -1.256054     -0.802823     -0.935171
H       -2.159539     -0.052453      0.395195
H        2.103926      0.051091      0.627098
H        1.387007     -0.940286     -0.653192
H        1.350216      0.804784     -0.791516"""

#: Cyanide at its ORCA B3LYP/6-31G** optimized geometry: C-N 1.183918 A (`! B3LYP 6-31G** Opt` from a start of 1.17 A). RDKit's own embedding puts the two atoms 1.461 A
#: apart, which is no geometry of cyanide, and its f- comes out 0.063 away from the first gate's record of the same molecule; at this distance it agrees (the test says by how much).
CYANIDE_B3LYP = """C        0.000000      0.000000      0.000000
N        1.183918      0.000000      0.000000"""

#: (fixture name, smiles, charge, method/basis, explicit coordinates or None, the number of the job to give two SCF iterations or None)
CASES = (
    ("acetone_fukui_diffuse_hf", "CC(C)=O", 0, "HF 6-311+G**", ACETONE_HF_A, None),
    ("methoxide_fukui_anion", "C[O-]", -1, "B3LYP 6-31+G*", None, None),
    ("cyanide_fukui_anion_no_diffuse", "[C-]#N", -1, "B3LYP 6-31G**", CYANIDE_B3LYP, None),
    ("methoxide_fukui_failed_dianion", "C[O-]", -1, "B3LYP 6-31+G*", None, 5),
)

JOB_ECHO = re.compile(r" Total Charge\s+Charge\s+\.\.\.\.\s+-?\d+")
HIRSHFELD_TITLE = "HIRSHFELD ANALYSIS"


def molecule(smiles: str, coordinates: str | None) -> Chem.Mol:
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    AllChem.EmbedMolecule(mol, randomSeed=7)
    if coordinates is None:
        AllChem.MMFFOptimizeMolecule(mol, maxIters=2000)
        return mol
    rows = [line.split() for line in coordinates.splitlines()]
    assert [row[0] for row in rows] == [atom.GetSymbol() for atom in mol.GetAtoms()], "atom order differs from the one the application embeds"
    conformer = mol.GetConformer()
    for index, row in enumerate(rows):
        conformer.SetAtomPosition(index, Point3D(*(float(value) for value in row[1:])))
    return mol


def fail_job(text: str, number: int) -> str:
    """Give job `number` (from 1) two SCF iterations: ORCA cannot converge it and ends the whole run there, so the jobs after it never run."""
    jobs = text.split("$new_job")
    lines = jobs[number - 1].splitlines()
    scf = next(index for index, line in enumerate(lines) if line.strip() == "%scf")
    lines.insert(scf + 1, "  MaxIter 2")
    jobs[number - 1] = "\n".join(lines) + "\n"
    return "$new_job".join(jobs)


def extract(output: str) -> str:
    """The verbatim lines the parsers read (see the module docstring), from a full ORCA output."""
    lines = output.splitlines()
    kept = [next(line for line in lines if "Program Version" in line), ""]
    echoes = [index for index, line in enumerate(lines) if JOB_ECHO.match(line)]
    for number, begin in enumerate(echoes):
        end = echoes[number + 1] if number + 1 < len(echoes) else len(lines)
        job = lines[begin:end]
        kept.extend(job[:3])
        if number == 0:
            kept.extend(block(job, "MULLIKEN ATOMIC CHARGES", 1) + block(job, "LOEWDIN ATOMIC CHARGES", 1))
        guess = [line for line in job if line.startswith("INITIAL GUESS:")]
        kept.extend(guess[:1])
        kept.extend(line for line in job if line.startswith(("Expectation value of <S**2>", "Ideal value S*(S+1)")))
        kept.extend(hirshfeld(job))
        kept.extend(line for line in job if line.startswith("FINAL SINGLE POINT ENERGY"))
        kept.append("")
    return "\n".join(kept).rstrip() + "\n"


def block(job: list[str], title: str, _unused: int) -> list[str]:
    """A charge block of the first job: the dashed title, its rows up to the blank line after `Sum of atomic charges`."""
    for index, line in enumerate(job):
        if line.strip() == title:
            begin = index - 1
            end = next(i for i in range(index, len(job)) if job[i].startswith("Sum of atomic charges") or not job[i].strip() and i > index + 2)
            return job[begin:end + 1] + [""]
    return []


def hirshfeld(job: list[str]) -> list[str]:
    for index, line in enumerate(job):
        if line.strip() == HIRSHFELD_TITLE:
            end = next(i for i in range(index, len(job)) if job[i].strip().startswith("TOTAL"))
            return [""] + job[index - 1:end + 1] + [""]
    return []


def main() -> None:
    destination = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "orca"
    destination.mkdir(parents=True, exist_ok=True)
    work_root = Path(tempfile.mkdtemp(prefix="fukui_v2_fixtures_"))
    provider = OrcaQuantumEngineProvider()
    only = set(sys.argv[2:])
    for name, smiles, charge, method_basis, coordinates, failing_job in CASES:
        if only and name not in only:
            continue
        mol = molecule(smiles, coordinates)
        text = provider.build_input(mol, charge, 1, method_basis, "fukui")
        if failing_job is not None:
            text = fail_job(text, failing_job)
        work = work_root / name
        work.mkdir()
        (work / "job.inp").write_text(text)
        proc = subprocess.run([ORCA, str(work / "job.inp")], capture_output=True, text=True, cwd=work)
        (work / "job.out").write_text(proc.stdout)
        (destination / f"{name}.inp").write_text(text)
        (destination / f"{name}.out").write_text(extract(proc.stdout))
        print(f"{name}: ORCA exit {proc.returncode}, {proc.stdout.count('JOB NUMBER')} jobs, full output kept at {work / 'job.out'}", flush=True)


if __name__ == "__main__":
    main()
