"""POST-GATE DIAGNOSTIC (not the gate, cannot change its outcome): why is CO's f- at HF/6-31G** 0.0214 from the published 0.6931?

Hypothesis: the unrestricted cation (CO+, a doublet) is spin-contaminated in ORCA's UHF, and the source used single-annihilated UHF.
Measured here: <S**2> of the UHF cation, and the Hirshfeld f- from the UHF cation against the ROHF cation (no spin contamination).
Standalone ORCA in fresh directories (the application runs every job in a fresh scratch directory too).
"""
import re
import subprocess
from pathlib import Path

from rdkit import Chem
from rdkit.Chem import AllChem

HERE = Path(__file__).parent / "diag_co"
HERE.mkdir(exist_ok=True)
ORCA = r"D:\ORCA\orca.exe"


def run(name: str, text: str) -> str:
    work = HERE / name
    work.mkdir(exist_ok=True)
    (work / "job.inp").write_text(text)
    out = subprocess.run([ORCA, str(work / "job.inp")], capture_output=True, text=True, cwd=work).stdout
    (work / "job.out").write_text(out)
    return out


mol = Chem.AddHs(Chem.MolFromSmiles("[C-]#[O+]"))
AllChem.EmbedMolecule(mol, randomSeed=7)
conf = mol.GetConformer()
xyz = "\n".join(f"{a.GetSymbol():<3}{conf.GetAtomPosition(a.GetIdx()).x:>14.6f}{conf.GetAtomPosition(a.GetIdx()).y:>14.6f}{conf.GetAtomPosition(a.GetIdx()).z:>14.6f}" for a in mol.GetAtoms())
opt = run("opt", f"! HF 6-31G** Opt\n* xyz 0 1\n{xyz}\n*\n")
coords = re.search(r"CARTESIAN COORDINATES \(ANGSTROEM\)\r?\n-+\r?\n((?:\s*[A-Za-z]{1,2}(?:\s+-?\d+\.\d+){3}\r?\n)+)", opt[opt.rfind("FINAL ENERGY EVALUATION"):] if "FINAL ENERGY EVALUATION" in opt else opt)
geom = "\n".join(l.strip() for l in coords.group(1).strip().splitlines())
print("optimized geometry:\n" + geom)

HIRSH = re.compile(r"^\s*\d+\s+([A-Z][a-z]?)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s*$", re.M)


def hirshfeld(out: str):
    block = out[out.rfind("HIRSHFELD ANALYSIS"):]
    return [float(m.group(2)) for m in HIRSH.finditer(block.split("TOTAL")[0])]


def state(name: str, method: str, charge: int, mult: int):
    out = run(name, f"! {method} 6-31G**\n%output\n  Print[P_Hirshfeld] 1\nend\n* xyz {charge} {mult}\n{geom}\n*\n")
    s2 = re.search(r"Expectation value of <S\*\*2>\s*:\s*(-?\d+\.\d+)", out)
    return hirshfeld(out), (float(s2.group(1)) if s2 else None)


neutral, _ = state("n", "HF", 0, 1)
cation_u, s2 = state("cu", "HF", 1, 2)
cation_ro, _ = state("cr", "ROHF", 1, 2)
anion_u, s2_an = state("au", "HF", -1, 2)
anion_ro, _ = state("ar", "ROHF", -1, 2)
print(f"\nUHF cation <S^2> = {s2}   UHF anion <S^2> = {s2_an}   (a pure doublet is 0.75)")
for label, cat, an in (("UHF ", cation_u, anion_u), ("ROHF", cation_ro, anion_ro)):
    fm = [c - n for n, c in zip(neutral, cat)]
    fp = [n - a for n, a in zip(neutral, an)]
    print(f"{label}: f- C {fm[0]:.4f} O {fm[1]:.4f} | f+ C {fp[0]:.4f} O {fp[1]:.4f}")
print("published (Olah HF/6-31G**): f- C 0.6931 O 0.3069 | f+ C 0.6801 O 0.3198")
