"""POST-GATE PROBE (not the gate, changes nothing shipped): is the shortfall of CO2's anion Hirshfeld charge sum an integration-grid effect?

Standalone ORCA, fresh directories. CO2 is linear, C=O 1.16 A (the application's own run uses an ORCA-optimized geometry; this probes the grid and
does not reproduce the application's number, though the default-grid sums land within 0.002 of the application's: -0.927 at B3LYP and -0.977 at HF).
The anion is the N+1 state (charge -1, doublet), the case the application refused at 6-311+G** (B3LYP -0.927, HF -0.977).
"""
import re
import subprocess
import tempfile
from pathlib import Path

HERE = Path(tempfile.mkdtemp(prefix="fukui_grid_probe_"))
ORCA = r"D:\ORCA\orca.exe"
GEOM = "C 0 0 0\nO 0 0 1.16\nO 0 0 -1.16"
ROW = re.compile(r"^\s*\d+\s+([A-Z][a-z]?)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s*$", re.M)
FINER = "%method\n  IntAcc 6.0\nend\n"
FINEST = "%method\n  AngularGrid 7\n  IntAcc 6.0\nend\n"


def run(name: str, keywords: str, charge: int, mult: int, blocks: str = "") -> tuple[float, float | None]:
    work = HERE / name
    work.mkdir(exist_ok=True)
    (work / "job.inp").write_text(f"! {keywords}\n{blocks}%output\n  Print[P_Hirshfeld] 1\nend\n* xyz {charge} {mult}\n{GEOM}\n*\n")
    out = subprocess.run([ORCA, str(work / "job.inp")], capture_output=True, text=True, cwd=work).stdout
    (work / "job.out").write_text(out)
    block = out[out.rfind("HIRSHFELD ANALYSIS"):]
    charges = [float(m.group(2)) for m in ROW.finditer(block.split("TOTAL")[0])]
    energy = re.findall(r"FINAL SINGLE POINT ENERGY\s+(-?\d+\.\d+)", out)
    return sum(charges), float(energy[-1]) if energy else None


for label, keywords, blocks in (
    ("B3LYP default", "B3LYP 6-311+G**", ""),
    ("B3LYP DefGrid3", "B3LYP 6-311+G** DefGrid3", ""),
    ("B3LYP IntAcc 6.0", "B3LYP 6-311+G**", FINER),
    ("B3LYP AngularGrid 7 IntAcc 6.0", "B3LYP 6-311+G**", FINEST),
    ("HF default", "HF 6-311+G**", ""),
    ("HF DefGrid3", "HF 6-311+G** DefGrid3", ""),
    ("HF IntAcc 6.0", "HF 6-311+G**", FINER),
    ("HF AngularGrid 7 IntAcc 6.0", "HF 6-311+G**", FINEST),
):
    total, energy = run(re.sub(r"\W+", "_", label), keywords, -1, 2, blocks)
    print(f"{label:32s} charges sum to {total:+.4f}  (state charge -1, short by {total + 1:+.4f})  E = {energy}", flush=True)
