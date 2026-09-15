"""Round 3 Track 2, experiment E2 B: dipoles from each charge model (preregistration.md).

    uv run --no-sync python benchmarks/charges/consumers/dipole_benchmark.py --freeze
    uv run --no-sync python benchmarks/charges/consumers/dipole_benchmark.py

An APPLICATION BENCHMARK: gasteiger1985 Table I's experimental dipoles against
each model on OpenChem conformers frozen once. Never a reproduction of the
paper, which prints no geometries. The mean absolute error does not choose any
default; it is reported, and each dipole result states it for its own model.
"""

from __future__ import annotations

import csv
import hashlib
import io
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from rdkit import Chem  # noqa: E402

from openchem.chem.charge_evaluation import CHARGE_MODELS, CHARGE_MODEL_LABELS  # noqa: E402
from openchem.chem.conformer_providers import GenerationOptions, RDKitConformerProvider, search_conformers  # noqa: E402
from openchem.chem.dipole import ChargesRefused, dipole_vector  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "charges"
TABLE = FIXTURES / "gasteiger1985_dipoles.csv"
CONFORMERS = FIXTURES / "gasteiger1985_conformers.csv"
OUTPUT = pathlib.Path(__file__).resolve().parent / "dipole_benchmark.csv"
SEED = 20260915
#: This project's earlier PEOE measurement on UNFROZEN conformers (docs/VALIDATION.md): a reference, not an oracle.
EARLIER_GASTEIGER_MAE = 0.794


def _read(path: pathlib.Path) -> list[dict]:
    return list(csv.DictReader(line for line in path.read_text(encoding="utf-8").splitlines() if not line.startswith("#")))


def freeze() -> None:
    rows = []
    for entry in _read(TABLE):
        mol = Chem.MolFromSmiles(entry["smiles"])
        outcome = search_conformers(RDKitConformerProvider(random_seed=SEED), mol, True, GenerationOptions())
        conformer, energy = min(outcome.pool, key=lambda pair: pair[1])
        rows.append([entry["molecule_printed"], entry["smiles"], f"{energy:.6f}", Chem.MolToMolBlock(conformer)])
    buffer = io.StringIO()
    csv.writer(buffer, lineterminator="\n").writerows([["molecule_printed", "smiles", "mmff_energy", "molblock"], *rows])
    CONFORMERS.write_text(f"# Frozen by dipole_benchmark.py --freeze: RDKitConformerProvider(random_seed={SEED}), default search, "
                          "lowest MMFF94 energy, explicit hydrogens.\n" + buffer.getvalue(), encoding="utf-8", newline="\n")
    print(CONFORMERS, hashlib.sha256(CONFORMERS.read_bytes()).hexdigest())


def run() -> dict:
    table = {e["molecule_printed"]: e for e in _read(TABLE)}
    rows, summary = [], {}
    for model in CHARGE_MODELS:
        errors, refused = [], []
        for entry in _read(CONFORMERS):
            mol = Chem.MolFromMolBlock(entry["molblock"], removeHs=False)
            experimental = float(table[entry["molecule_printed"]]["mu_exp_debye"])
            try:
                _vector, magnitude, _neutral = dipole_vector(mol, model)
            except ChargesRefused as exc:
                refused.append(entry["molecule_printed"])
                rows.append([model, entry["molecule_printed"], experimental, "", "", exc.evaluation.refusal])
                continue
            errors.append(abs(magnitude - experimental))
            rows.append([model, entry["molecule_printed"], experimental, f"{magnitude:.4f}", f"{magnitude - experimental:+.4f}", ""])
        summary[model] = {"n": len(errors), "refused": refused, "mae": sum(errors) / len(errors) if errors else float("nan")}
    buffer = io.StringIO()
    csv.writer(buffer, lineterminator="\n").writerows([["charge_model", "molecule", "mu_exp", "mu_model", "error", "refusal"], *rows])
    OUTPUT.write_text("# preregistration.md E2 B: an application benchmark, not a reproduction of gasteiger1985.\n" + buffer.getvalue(),
                      encoding="utf-8", newline="\n")
    for model, s in summary.items():
        print(f"{CHARGE_MODEL_LABELS[model]:28} MAE {s['mae']:.3f} D over n={s['n']} of 15; refused {s['refused']}")
    print(f"earlier Gasteiger reference (unfrozen conformers): {EARLIER_GASTEIGER_MAE} D; paper's own PEPE: 0.164 D (not compared)")
    return summary


if __name__ == "__main__":
    freeze() if "--freeze" in sys.argv else run()
