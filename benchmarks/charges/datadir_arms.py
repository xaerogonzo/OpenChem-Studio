"""Which data-directory setting lets Open Babel's charge models compute.

    uv run --no-sync python benchmarks/charges/datadir_arms.py

Five arms, each in a fresh process (see `openbabel_child.py`), on methanol
embedded by RDKit with a fixed seed. Prints the exit code, whether the model
computed, the charges, and the distinct Open Babel error lines.

Measured 2026-09-14 on Windows, openbabel-wheel 3.1.1.23 (module 3.1.0):

    arm                          EEM                  QEq
    plain (the wheel's setting)  file not opened, 0s  file not opened, SEGFAULT
    shell, Windows path          file not opened, 0s  file not opened, SEGFAULT
    Python after import, Windows computes             computes
    shell, POSIX path            file not opened, 0s  file not opened, SEGFAULT
    Python after import, POSIX   file not opened, 0s  file not opened, SEGFAULT

A value set in the shell is overwritten by the wheel's own `__init__`, which
sets `BABEL_DATADIR` after loading the library. The library reads the variable
when it opens a file, from the environment Python writes to, so setting it
after import works.
"""

import os
import pathlib
import subprocess
import sys
import tempfile

import openbabel
from rdkit import Chem
from rdkit.Chem import AllChem

HERE = pathlib.Path(__file__).parent


def main() -> None:
    molecule = Chem.AddHs(Chem.MolFromSmiles(sys.argv[1] if len(sys.argv) > 1 else "CO"))
    AllChem.EmbedMolecule(molecule, randomSeed=7)
    data = pathlib.Path(openbabel.__file__).parent / "bin" / "data"
    posix = "/" + str(data).replace(":\\", "/").replace("\\", "/")
    arms = {
        "plain (the wheel's setting)": ("plain", {}),
        "shell, Windows path": ("plain", {"BABEL_DATADIR": str(data)}),
        "Python after import, Windows path": ("python_after_import_win", {}),
        "shell, POSIX path": ("plain", {"BABEL_DATADIR": posix}),
        "Python after import, POSIX path": ("python_after_import_posix", {}),
    }
    with tempfile.TemporaryDirectory() as scratch:
        mol_path = pathlib.Path(scratch) / "input.mol"
        mol_path.write_text(Chem.MolToMolBlock(molecule))
        for method in ("eem", "qeq"):
            for label, (arm, extra) in arms.items():
                env = {k: v for k, v in os.environ.items() if k != "BABEL_DATADIR"}
                env.update(extra)
                run = subprocess.run(
                    [sys.executable, str(HERE / "openbabel_child.py"), arm, method, str(mol_path)],
                    env=env, capture_output=True, text=True, timeout=120,
                )
                result = next((line[7:] for line in run.stdout.splitlines() if line.startswith("RESULT ")), None)
                errors = sorted({line.strip() for line in run.stderr.splitlines() if line.strip() and "==" not in line})
                print(f"--- {method} / {label}: exit code {run.returncode}")
                print(f"    {result}")
                for error in errors[:6]:
                    print(f"    stderr: {error[:150]}")


if __name__ == "__main__":
    main()
