"""Run the ORCA TD-DFT jobs `score.py` scores.

    python benchmarks/uvvis/generate.py <output directory> [--orca PATH]

WHY THIS EXISTS. ROADMAP.md records UV-Vis as measured and deliberately NOT
shipped, and names the untried lead in the same breath: "A functional better
suited to charge-transfer and pi->pi* states (a range-separated hybrid such as
wB97X-D) is the more promising lead than any basis change, and has not been
tried." This runs it.

TWO JOBS PER MOLECULE, NOT ONE. `! ... Opt` together with a `%tddft` block
does not mean "optimise, then compute the spectrum" -- it requests an
EXCITED-STATE geometry optimisation, which needs the third functional
derivative of B88 and which this ORCA build refuses outright. The ground-state
optimisation and the TD-DFT single point have to be separate jobs.

ONE GEOMETRY, SHARED BY EVERY ARM. The optimisation runs once per molecule at
B3LYP/def2-SVP and every arm's TD-DFT single point uses that same geometry.
Two reasons, and the first is the one that matters: the recorded def2-SVP vs
def2-SVPD comparison this is being compared against was itself taken "on the
same optimised geometries", so re-optimising per functional would change two
things at once and make the new numbers incomparable with the old. The second
is that for valence excitations the geometry difference between these
functionals is a second-order effect on the excitation energy.

THE B3LYP ARM IS A CONTROL, NOT A CANDIDATE. It exists to reproduce the
figures already in ROADMAP.md (formaldehyde 4.078 eV, benzene's 1E1u at
7.918 eV carrying f = 0.9607). If it does not reproduce them, the harness is
wrong and no conclusion about wB97X-D is worth anything -- a control that
cannot fail is not a control.

`nroots 15`, NEVER 8. The recorded 8-root run reported benzene's strongest
band as missing when it was simply outside the requested roots, and produced
entirely plausible numbers while doing it. `score.py` refuses to score a
transition it cannot locate rather than taking the nearest one.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "src"))

#: The molecules `reference.json` carries experimental transitions for.
#: Three are the ones ROADMAP.md already has recorded numbers for; pyridine is
#: the fourth so the aromatic verdict does not rest on benzene alone, and it is
#: a heteroaromatic rather than another substituted benzene so the added case
#: is a genuinely different electronic environment (it carries both an n->pi*
#: from the nitrogen lone pair and the benzene-like pi->pi* manifold).
MOLECULES: dict[str, str] = {
    "formaldehyde": "C=O",
    "acetone": "CC(C)=O",
    "benzene": "c1ccccc1",
    "pyridine": "c1ccncc1",
}

#: Geometry optimisation, run once per molecule. See the module docstring for
#: why every arm shares it.
GEOMETRY_METHOD_BASIS = "B3LYP def2-SVP"

#: The TD-DFT arms. `b3lyp-svp` is the control that must reproduce ROADMAP's
#: recorded figures; the two wB97X-D3 arms are the experiment.
#:
#: "wB97X-D3" is this ORCA build's spelling -- confirmed live, the run
#: terminated normally and ORCA-CIS/TD-DFT finished without error.
ARMS: dict[str, str] = {
    "b3lyp-svp": "B3LYP def2-SVP",
    "wb97xd-svp": "wB97X-D3 def2-SVP",
    "wb97xd-svpd": "wB97X-D3 def2-SVPD",
}

NROOTS = 15


def _orca_path(explicit: str | None) -> str:
    """The ORCA executable, from the flag or from the app's own settings.

    Lifted deliberately from `benchmarks/ir/generate.py`: a machine where the
    application already works needs no extra configuration for the benchmark,
    which is one place to be wrong instead of two.

    **THE PATH IS NORMALISED TO NATIVE SEPARATORS, AND THAT IS LOAD-BEARING.**
    ORCA derives the directory of its own helper binaries (`orca_startup` and
    friends) from the path it was invoked with, and a FORWARD-SLASH path
    defeats that on Windows -- it aborts in `Startup` with "aborting the run",
    naming `orca_startup` and nothing else. Measured, same input file, same
    working directory, same parent process, only the separator varying:

        subprocess.run(["D:/ORCA/orca.exe",  "x.inp"])  ->  Startup failure
        subprocess.run([r"D:\\ORCA\\orca.exe", "x.inp"])  ->  TERMINATED NORMALLY

    It is the same mechanism as the already-known "ORCA must not be installed
    under a path containing spaces", and it reads identically -- like a broken
    input file rather than a broken invocation. Note a single-point job can
    survive it while an `Opt` of the same molecule does not, so a working
    probe does not clear the path.
    """
    if explicit:
        return str(Path(explicit))
    try:
        from openchem.app.settings import Settings
        from openchem.events.base import EventBus

        configured = str(Settings(EventBus()).get("orca/executable_path", "") or "")
        if configured and Path(configured).is_file():
            return str(Path(configured))
    except Exception:  # noqa: BLE001 - fall through to the error below
        pass
    raise SystemExit(
        "No ORCA executable. Pass --orca PATH, or configure it in the "
        "application (Tools > External Tools) so this can read it."
    )


def _finished(out: Path) -> bool:
    return out.is_file() and "TERMINATED NORMALLY" in out.read_text(
        encoding="utf-8", errors="replace"
    )


def _run(orca: str, inp: Path, out: Path, label: str) -> bool:
    print(f"{label}: running ...", flush=True)
    result = subprocess.run(
        [orca, inp.name], cwd=inp.parent, capture_output=True, text=True
    )
    out.write_text(result.stdout, encoding="utf-8")
    if "TERMINATED NORMALLY" not in result.stdout:
        print(f"{label}: DID NOT TERMINATE NORMALLY", file=sys.stderr)
        print(result.stdout[-800:], file=sys.stderr)
        return False
    print(f"{label}: done")
    return True


def _optimised_geometry(out_dir: Path, name: str) -> list[str]:
    """The coordinate lines ORCA wrote for the optimised structure.

    ORCA emits `<basename>.xyz` at the end of an `Opt`, which is the
    optimised geometry and is far less fragile to read than scraping the
    final coordinate block out of the log.
    """
    xyz = out_dir / f"{name}_opt.xyz"
    if not xyz.is_file():
        raise SystemExit(f"{name}: no optimised geometry at {xyz}")
    lines = xyz.read_text(encoding="utf-8").splitlines()
    # An xyz file is: count, comment, then one line per atom.
    return [line for line in lines[2:] if line.strip()]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out_dir", type=Path, help="where to write the ORCA jobs")
    parser.add_argument("--orca", default="", help="path to orca.exe")
    parser.add_argument("--only", default="", help="one molecule name, for a quick check")
    parser.add_argument("--arm", default="", help="one arm name, for a quick check")
    args = parser.parse_args(argv)

    orca = _orca_path(args.orca)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    from rdkit import Chem, RDLogger
    from rdkit.Chem import AllChem

    from openchem.chem.orca_engine import OrcaQuantumEngineProvider

    RDLogger.DisableLog("rdApp.*")
    provider = OrcaQuantumEngineProvider()

    molecules = {k: v for k, v in MOLECULES.items() if not args.only or k == args.only}
    arms = {k: v for k, v in ARMS.items() if not args.arm or k == args.arm}
    if not molecules:
        raise SystemExit(f"--only {args.only!r} matches no molecule in {list(MOLECULES)}")
    if not arms:
        raise SystemExit(f"--arm {args.arm!r} matches no arm in {list(ARMS)}")

    failures: list[str] = []
    for name, smiles in molecules.items():
        opt_out = args.out_dir / f"{name}_opt.out"
        if _finished(opt_out):
            print(f"{name}_opt: already present, skipping")
        else:
            mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
            # A FIXED SEED, so re-running produces the same starting geometry.
            # ORCA optimises from here and a converged optimum should not
            # depend on it -- but a benchmark that cannot be reproduced
            # exactly is one whose disagreements cannot be diagnosed.
            AllChem.EmbedMolecule(mol, randomSeed=0xF00D)
            AllChem.MMFFOptimizeMolecule(mol)
            inp = args.out_dir / f"{name}_opt.inp"
            inp.write_text(
                provider.build_input(mol, 0, 1, GEOMETRY_METHOD_BASIS, "opt"),
                encoding="utf-8",
            )
            if not _run(orca, inp, opt_out, f"{name}_opt"):
                failures.append(f"{name}_opt")
                continue

        coordinates = _optimised_geometry(args.out_dir, name)

        for arm, method_basis in arms.items():
            td_out = args.out_dir / f"{name}_{arm}_td.out"
            if _finished(td_out):
                print(f"{name}_{arm}: already present, skipping")
                continue
            inp = args.out_dir / f"{name}_{arm}_td.inp"
            inp.write_text(
                "\n".join(
                    [
                        f"! {method_basis} TightSCF",
                        "%tddft",
                        f"  nroots {NROOTS}",
                        "end",
                        "* xyz 0 1",
                        *coordinates,
                        "*",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            if not _run(orca, inp, td_out, f"{name}_{arm}"):
                failures.append(f"{name}_{arm}")

    if failures:
        print(f"\n{len(failures)} job(s) failed: {', '.join(failures)}", file=sys.stderr)
        return 1
    print(f"\nAll jobs in {args.out_dir}. Now run:")
    print(f"  python benchmarks/uvvis/score.py {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
