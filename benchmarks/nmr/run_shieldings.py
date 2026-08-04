"""Run ORCA NMR over a benchmark set, once, and keep the results.

WHY THIS EXISTS SEPARATELY FROM THE SCORER. Quantum chemistry is the only
expensive step in this benchmark -- minutes per molecule, hours per set --
and every design question downstream ("would strategy C have chosen
better?") is arithmetic over the same shieldings. Separating the two means
a new strategy costs seconds to evaluate rather than another full run.

TWO CACHES, deliberately different in kind:

  * RAW ORCA OUTPUT -- hundreds of KB each, kept in the data directory,
    NOT in git. Useful for re-parsing if a regex changes; too big to
    version.
  * PARSED SHIELDINGS -- a few KB of JSON per method, committed. This is
    the reusable artifact: anyone can re-run the whole design comparison
    from it without ORCA installed at all.

GEOMETRIES ARE CACHED TOO, as molblocks. A conformer search is stochastic,
so re-deriving the structure later would silently compare shieldings
computed on different geometries. It also pins the atom ordering that
every literature shift mapping is keyed to.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from rdkit import Chem
from rdkit.Chem import AllChem

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from openchem.chem.nmr_scaling import REFERENCE_COMPOUNDS  # noqa: E402
from openchem.chem.orca_engine import OrcaQuantumEngineProvider  # noqa: E402

ORCA = Path(r"D:\ORCA\orca.exe")
HERE = Path(__file__).resolve().parent
#: Committed: small, diffable, and enough to redo every design comparison.
SHIELDINGS = HERE / "shieldings"
GEOMETRIES = HERE / "geometries"
#: Not committed: the full ORCA logs.
RAW = Path(r"D:\Random Programs\OpenChemStudio_Data\nmr_bench_raw")

_provider = OrcaQuantumEngineProvider()


def slug(method_basis: str) -> str:
    return method_basis.replace(" ", "_").replace("/", "-")


@dataclass(frozen=True)
class Job:
    name: str
    smiles: str


def geometry(job: Job) -> Chem.Mol:
    """The molecule's 3D structure, generated once and reused forever.

    `useRandomCoords` is on because the default start fails outright on
    caged systems -- quinine's quinuclidine is the case that forced it.
    """
    path = GEOMETRIES / f"{job.name}.mol"
    if path.exists():
        return Chem.MolFromMolBlock(path.read_text(encoding="utf-8"), removeHs=False)

    mol = Chem.AddHs(Chem.MolFromSmiles(job.smiles))
    params = AllChem.ETKDGv3()
    params.randomSeed = 0xF00D
    params.useRandomCoords = True
    params.maxIterations = 2000
    if AllChem.EmbedMolecule(mol, params) != 0:
        raise RuntimeError(f"could not embed {job.name}")
    AllChem.MMFFOptimizeMolecule(mol, maxIters=5000)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(Chem.MolToMolBlock(mol), encoding="utf-8")
    return mol


def raw_output(job: Job, mol: Chem.Mol, method_basis: str) -> str:
    path = RAW / slug(method_basis) / f"{job.name}.out"
    if path.exists():
        return path.read_text(encoding="utf-8", errors="replace")
    text = _provider.build_input(mol, 0, 1, method_basis, "nmr")
    # The scratch directory is named after the molecule, and ORCA truncates
    # its input path at the first space -- "Maleic anhydride" died in
    # startup with "Cannot open input file ...nmr_d50_Maleic". Same trap as
    # ORCA needing a space-free install path.
    safe = "".join(c if c.isalnum() else "_" for c in job.name)
    with tempfile.TemporaryDirectory(prefix=f"nmr_{safe}_") as scratch:
        inp = Path(scratch) / "job.inp"
        inp.write_text(text, encoding="utf-8")
        done = subprocess.run(
            [str(ORCA), str(inp)], capture_output=True, text=True, cwd=scratch, timeout=28800
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(done.stdout, encoding="utf-8")
    return done.stdout


def run(jobs: list[Job], method_basis: str) -> dict:
    """Shieldings for every job, running only what is not already cached."""
    out_path = SHIELDINGS / f"{slug(method_basis)}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    store = json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() else {}

    for job in jobs:
        if job.name in store:
            print(f"  {job.name}: cached", flush=True)
            continue
        mol = geometry(job)
        try:
            result = _provider.parse_spectrum_output(
                raw_output(job, mol, method_basis), mol, "b", "nmr"
            )
        except Exception as exc:  # noqa: BLE001
            # One molecule that will not converge must not abort a batch of
            # fifty; the failure is recorded and the rest continue.
            print(f"  {job.name}: FAILED ({type(exc).__name__})", flush=True)
            store[job.name] = {"failed": True, "error": str(exc)[:200]}
            out_path.write_text(json.dumps(store, indent=1, sort_keys=True), encoding="utf-8")
            continue
        if result is None or not result.values:
            # Recorded rather than skipped silently: a molecule that will
            # not converge is a real fact about the benchmark set.
            store[job.name] = {"failed": True}
            print(f"  {job.name}: FAILED", flush=True)
        else:
            store[job.name] = {
                "shieldings": {str(i): round(v, 4) for i, v in result.values.items()},
                "elements": {str(i): e for i, e in result.elements.items()},
                "orca_version": (result.provenance.parameters or {}).get("orca_version", "unknown"),
            }
            print(f"  {job.name}: {len(result.values)} nuclei", flush=True)
        out_path.write_text(json.dumps(store, indent=1, sort_keys=True), encoding="utf-8")
    return store


def reference_jobs() -> list[Job]:
    """The 11 calibration standards from `chem/nmr_scaling.py`.

    Named identically to `ReferenceCompound.name` so `reference_points`
    can consume the results without a second mapping.
    """
    return [Job(name=c.name.replace(" ", "_"), smiles=c.smiles) for c in REFERENCE_COMPOUNDS]


if __name__ == "__main__":
    method = sys.argv[1] if len(sys.argv) > 1 else "B3LYP def2-SVP"
    flags = set(sys.argv[2:])
    sys.path.insert(0, str(HERE))
    extra: list[Job] = []
    if "--literature" in flags:
        from literature_shifts import SPECTRA  # noqa: E402

        extra += [Job(name=s.name, smiles=s.smiles) for s in SPECTRA.values()]
    if "--delta50" in flags:
        import delta50  # noqa: E402

        # Prefixed so a DELTA50 compound can never collide with a reference
        # standard of the same name -- Benzene and Cyclohexane are both.
        extra += [Job(name=f"d50_{c.name}", smiles=c.smiles) for c in delta50.load()]
    print(f"=== {method}", flush=True)
    run(reference_jobs() + extra, method)
