"""Regenerate the real-ORCA fixtures of the Fukui v2 tests: `python benchmarks/fukui_gate_2/make_fixtures.py [output directory]`.

Each fixture is VERBATIM extracts of a real ORCA 6.1.1 run of the input the application's own `build_input` writes (`OrcaQuantumEngineProvider`, calc type
`fukui`), the way `tests/fixtures/orca/water_fukui.out` is: the version banner, each job's echo of its charge, multiplicity and electron count, the guess it
started from, its <S**2> lines, its Hirshfeld block and its energy line, in the order ORCA printed them; the first job also keeps its Mulliken and Loewdin
blocks so that a parse reading the wrong block would be caught. Every other line (SCF iterations, about 100 KB a job) is dropped. A job that did not finish
keeps what it printed before it stopped and no more.

The three cases (what each exists to test):

    methoxide_fukui_fminus.out           CH3O-, B3LYP 6-31+G*: an ANION, so two states and f- only, and a basis with diffuse functions, so the anionic N state
                                         has two extra starts (HCore, Hueckel) after the default ones: four jobs. All four converge to one solution.
    acetone_fukui_diffuse_hf.out         acetone at its HF/6-311+G** optimized geometry, HF 6-311+G**: the neutral's N+1 state has more than one SCF solution,
                                         and the HCore start is 1.0 eV below ORCA's default one (the case `benchmarks/fukui_gate/artifacts/anion_guess_probe_diffuse.json`
                                         found): five jobs, the lowest solution replaces the default.
    methoxide_fukui_failed_start.out     the first case with its LAST job given two SCF iterations: it cannot converge, ORCA ends the run with exit code 115, and the
                                         three jobs before it are intact.

The geometry of the methoxide cases is RDKit ETKDG (seed 7) then MMFF, which is a probe of the calculation and not of a geometry; acetone's is read from
the ORCA optimization of `benchmarks/fukui_gate/grid_sweep.py`, typed below.
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

#: (fixture name, smiles, charge, method/basis, explicit coordinates or None, tweak of the input or None)
CASES = (
    ("methoxide_fukui_fminus", "C[O-]", -1, "B3LYP 6-31+G*", None, None),
    ("acetone_fukui_diffuse_hf", "CC(C)=O", 0, "HF 6-311+G**", ACETONE_HF_A, None),
    ("methoxide_fukui_failed_start", "C[O-]", -1, "B3LYP 6-31+G*", None, "fail_last_job"),
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


def fail_last_job(text: str) -> str:
    """Give the last job two SCF iterations: ORCA cannot converge it and ends the whole run there."""
    head, last = text.rsplit("$new_job", 1)
    lines = last.splitlines()
    scf = next(index for index, line in enumerate(lines) if line.strip() == "%scf")
    lines.insert(scf + 1, "  MaxIter 2")
    return head + "$new_job" + "\n".join(lines) + "\n"


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
    for name, smiles, charge, method_basis, coordinates, tweak in CASES:
        mol = molecule(smiles, coordinates)
        text = provider.build_input(mol, charge, 1, method_basis, "fukui")
        if tweak == "fail_last_job":
            text = fail_last_job(text)
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
