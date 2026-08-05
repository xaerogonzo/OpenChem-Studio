"""Run the ORCA frequency jobs `score.py` scores.

    python benchmarks/ir/generate.py <output directory> [--orca PATH]

WHY THIS EXISTS. `score.py` takes a directory of finished ORCA `.out` files
and was written against a scratch directory produced by hand. That is fine
for a developer who has just run the jobs and wrong for anything unattended:
the benchmark could be SCORED automatically but not RUN automatically, so
the self-hosted job had nothing to score. This is the missing half.

It is deliberately separate from `score.py` rather than folded into it.
Generating is minutes of ORCA per molecule and needs the executable;
scoring is instant and needs nothing. Keeping them apart means a developer
who already has the outputs can re-score without re-running, which is the
common case when the parser or the reference values change.

GEOMETRIES ARE OPTIMISED HERE, not taken from RDKit. `opt_freq` optimises
first and computes frequencies at the RESULT, and this project has already
been caught once by using the submitted geometry where the optimised one was
meant -- classifying linear water's modes against a bent input labelled both
O-H stretches "bend".
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "src"))

#: The molecules `reference.json` carries fundamentals for, plus the two that
#: are run and parsed but deliberately NOT scored on frequency (their
#: assignments are not one-to-one with a sorted list). Those two still earn
#: their place: benzene is the D6h symmetry check on the intensity column,
#: and acetone is the methyl-torsion case for mode classification.
MOLECULES: dict[str, str] = {
    "water": "O",
    "co2": "O=C=O",
    "methane": "C",
    "acetone": "CC(C)=O",
    "benzene": "c1ccccc1",
}

#: B3LYP/def2-SVP is what every number in benchmarks/ir/README.md was
#: measured at, and the fitted 0.9666 scaling factor is specific to it.
#: Changing this invalidates that factor rather than improving it.
METHOD_BASIS = "B3LYP def2-SVP"


def _orca_path(explicit: str | None) -> str:
    """The ORCA executable, from the flag or from the app's own settings.

    Reading `Settings` means a machine where the application already works
    needs no extra configuration for the benchmark -- one place to be wrong
    instead of two.
    """
    if explicit:
        return explicit
    try:
        from openchem.app.settings import Settings
        from openchem.events.base import EventBus

        configured = str(Settings(EventBus()).get("orca/executable_path", "") or "")
        if configured and Path(configured).is_file():
            return configured
    except Exception:  # noqa: BLE001 - fall through to the error below
        pass
    raise SystemExit(
        "No ORCA executable. Pass --orca PATH, or configure it in the "
        "application (Tools > External Tools) so this can read it."
    )


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out_dir", type=Path, help="where to write the ORCA jobs")
    parser.add_argument("--orca", default="", help="path to orca.exe")
    args = parser.parse_args(argv)

    orca = _orca_path(args.orca)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    from rdkit import Chem, RDLogger
    from rdkit.Chem import AllChem

    from openchem.chem.orca_engine import OrcaQuantumEngineProvider

    RDLogger.DisableLog("rdApp.*")
    provider = OrcaQuantumEngineProvider()

    failures: list[str] = []
    for name, smiles in MOLECULES.items():
        out = args.out_dir / f"{name}.out"
        if out.is_file() and "TERMINATED NORMALLY" in out.read_text(
            encoding="utf-8", errors="replace"
        ):
            print(f"{name}: already present, skipping")
            continue

        mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
        # A FIXED SEED, so re-running produces the same starting geometry.
        # ORCA optimises from here, and a converged optimum should not depend
        # on the seed -- but a benchmark that cannot be reproduced exactly is
        # a benchmark whose disagreements cannot be diagnosed.
        AllChem.EmbedMolecule(mol, randomSeed=0xF00D)
        AllChem.MMFFOptimizeMolecule(mol)

        inp = args.out_dir / f"{name}.inp"
        inp.write_text(
            provider.build_input(mol, 0, 1, METHOD_BASIS, "opt_freq"), encoding="utf-8"
        )

        print(f"{name}: running opt_freq ...", flush=True)
        result = subprocess.run(
            [orca, inp.name],
            cwd=args.out_dir,
            capture_output=True,
            text=True,
        )
        out.write_text(result.stdout, encoding="utf-8")

        if "TERMINATED NORMALLY" not in result.stdout:
            failures.append(name)
            print(f"{name}: DID NOT TERMINATE NORMALLY", file=sys.stderr)
            print(result.stdout[-800:], file=sys.stderr)
        else:
            print(f"{name}: done")

    if failures:
        print(f"\n{len(failures)} job(s) failed: {', '.join(failures)}", file=sys.stderr)
        return 1
    print(f"\nAll {len(MOLECULES)} jobs in {args.out_dir}. Now run:")
    print(f"  python benchmarks/ir/score.py {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
