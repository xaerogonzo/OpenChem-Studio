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

#: The three molecules of the Fukui v3 fixtures at their ORCA B3LYP/6-31G* optimized geometries (`! B3LYP 6-31G* Opt` from an RDKit ETKDG seed-7 + MMFF embedding, the recipe of
#: `cation_states_probe.py`), in the orientation ORCA left them in. Atom order is the one the application embeds (the heavy atoms in SMILES order, then the hydrogens).
HCN_B3LYP = """C       -0.028892      0.000975      0.000000
N        1.127654     -0.037938     -0.000000
H       -1.098762      0.036963     -0.000000"""

BENZENE_B3LYP = """C        1.279487      0.560508     -0.034170
C        1.123435     -0.827423     -0.074694
C       -0.156035     -1.387923     -0.040522
C       -1.279487     -0.560508      0.034171
C       -1.123435      0.827422      0.074695
C        0.156035      1.387923      0.040522
H        2.275079      0.996607     -0.060734
H        1.997617     -1.471281     -0.132830
H       -0.277431     -2.467925     -0.072072
H       -2.275079     -0.996608      0.060733
H       -1.997618      1.471280      0.132831
H        0.277430      2.467925      0.072070"""

BENZALDEHYDE_B3LYP = """O        2.871096     -1.433418     -0.112420
C        2.314946     -0.359057     -0.239995
C        0.858628     -0.137733     -0.088207
C        0.327127      1.147804     -0.257971
C       -1.043579      1.364044     -0.116397
C       -1.884775      0.292581      0.195403
C       -1.358450     -0.994352      0.365932
C        0.008722     -1.210606      0.224988
H        2.898135      0.556363     -0.488987
H        0.991602      1.974995     -0.500779
H       -1.455488      2.360937     -0.247765
H       -2.953317      0.458815      0.306313
H       -2.018655     -1.822877      0.608318
H        0.444007     -2.197495      0.351567"""

#: Water at its textbook geometry (O-H 0.9572 A, H-O-H 104.52 degrees), the geometry of `water_fukui.out`.
WATER_TEXTBOOK = """O        0.000000      0.000000      0.117300
H        0.000000      0.757350     -0.468070
H        0.000000     -0.757350     -0.468070"""

#: (fixture name, smiles, charge, method/basis, explicit coordinates or None, the number of the job to give two SCF iterations or None, whether the input carries the
#: hole starts of the cation search). The first four are the fixtures of Fukui v2 and the anion's f+, written WITHOUT the search (their `.inp` files are that plan);
#: the others are written with it.
CASES = (
    ("acetone_fukui_diffuse_hf", "CC(C)=O", 0, "HF 6-311+G**", ACETONE_HF_A, None, False),
    ("methoxide_fukui_anion", "C[O-]", -1, "B3LYP 6-31+G*", None, None, False),
    ("cyanide_fukui_anion_no_diffuse", "[C-]#N", -1, "B3LYP 6-31G**", CYANIDE_B3LYP, None, False),
    ("methoxide_fukui_failed_dianion", "C[O-]", -1, "B3LYP 6-31+G*", None, 5, False),
    ("hcn_fukui_cation_search", "C#N", 0, "B3LYP 6-31G*", HCN_B3LYP, None, True),
    ("hcn_fukui_cation_search_failed_hole", "C#N", 0, "B3LYP 6-31G*", HCN_B3LYP, 5, True),
    ("benzaldehyde_fukui_cation_search", "O=Cc1ccccc1", 0, "B3LYP 6-31G*", BENZALDEHYDE_B3LYP, None, True),
    ("benzene_fukui_cation_search", "c1ccccc1", 0, "B3LYP 6-31G*", BENZENE_B3LYP, None, True),
    ("water_fukui_cation_search", "O", 0, "B3LYP 6-31G*", WATER_TEXTBOOK, None, True),
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


def input_echo(lines: list[str]) -> list[str]:
    """ORCA's echo of the whole compound input (the `INPUT FILE` block, from its dashed title to `****END OF INPUT****`), which is how a hole start is told from a default one."""
    begin = next(index for index, line in enumerate(lines) if line.strip() == "INPUT FILE") - 1
    end = next(index for index in range(begin, len(lines)) if "****END OF INPUT****" in lines[index])
    return lines[begin:end + 1] + [""]


def orbital_table(job: list[str]) -> list[str]:
    """The ORBITAL ENERGIES table of a job (its dashed title, the rows, up to the blank line that ends them): the occupied orbitals' energies are what the search's
    'first orbital that was not tried' reads."""
    for index, line in enumerate(job):
        if line.strip() == "ORBITAL ENERGIES":
            end = next(i for i in range(index + 3, len(job)) if not job[i].strip() or job[i].startswith("*"))
            return job[index - 1:end] + [""]
    return []


def extract(output: str) -> str:
    """The verbatim lines the parsers read (see the module docstring), from a full ORCA output."""
    lines = output.splitlines()
    kept = [next(line for line in lines if "Program Version" in line), ""]
    kept.extend(input_echo(lines))
    echoes = [index for index, line in enumerate(lines) if JOB_ECHO.match(line)]
    for number, begin in enumerate(echoes):
        end = echoes[number + 1] if number + 1 < len(echoes) else len(lines)
        job = lines[begin:end]
        kept.extend(job[:3])
        if number == 0:
            kept.extend(block(job, "MULLIKEN ATOMIC CHARGES", 1) + block(job, "LOEWDIN ATOMIC CHARGES", 1))
            kept.extend(orbital_table(job))
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
    only = set(sys.argv[2:])
    for name, smiles, charge, method_basis, coordinates, failing_job, search in CASES:
        if only and name not in only:
            continue
        provider = OrcaQuantumEngineProvider(cation_search=lambda search=search: search)
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
