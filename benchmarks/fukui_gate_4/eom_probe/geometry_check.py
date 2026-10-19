"""Diagnostic after the outcome (not a plan record; run once, result in artifacts/their_geometry/pyridine.txt): our EOM-IP-CCSD/cc-pVTZ pipeline on pyridine at the geometry of Ranasinghe 2019's CGB set (their SI file 43_Pyridine.xyz, dummy X atoms dropped)."""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eom_probe"))
sys.path.insert(0, str(ROOT))
import eom_parse  # noqa: E402
import run_gate as rg  # noqa: E402

xyz = Path(r"D:/Xaero Stuff/Documents/Sci Downloads/ranasinghe2019_si/Geomatries/CBG/43_Pyridine.xyz").read_text().splitlines()[2:]
atoms = [(l.split()[0], np.array([float(v) for v in l.split()[1:4]])) for l in xyz if l.split() and l.split()[0] != "X"]
coords = rg.oriented(np.array([c for _, c in atoms]))
lines = [f"{s:<3}{x:>14.6f}{y:>14.6f}{z:>14.6f}" for (s, _), (x, y, z) in zip(atoms, coords)]
text = "\n".join(["! IP-EOM-CCSD cc-pVTZ TightSCF", "%maxcore 3000", "%pal nprocs 8 end", "%mdci", "  DoEOM true", "  NRoots 8", "  FollowCIS true", "end",
                  "%output", "  Print[P_ReducedOrbPopMO_L] 1", "end", "* xyz 0 1", *lines, "*", ""])
work = Path(__file__).resolve().parent / "artifacts" / "their_geometry"
work.mkdir(exist_ok=True)
(work / "job.inp").write_text(text)
done = subprocess.run([rg.ORCA, "job.inp"], capture_output=True, text=True, cwd=work)
(work / "job.out").write_text(done.stdout)
roots = eom_parse.classified_roots(done.stdout)
e0 = roots[0]["energy_ev"]
for r in roots[:5]:
    print(round(r["energy_ev"], 3), round(r["energy_ev"] - e0, 3), r["kind"])
