"""Score computed harmonic frequencies against experimental fundamentals.

Two questions, and the second is the one usually skipped:

  1. Are the peaks in the right PLACES?  Harmonic frequencies run
     systematically high, so this fits a single scaling factor and reports
     the error before and after. A factor that does not actually reduce the
     error is not worth applying.

  2. Are they the right HEIGHTS?  Frequency agreement does not imply
     intensity agreement, and a spectrum with every peak in the right place
     at the wrong height is still the wrong spectrum. Scored separately, by
     rank correlation, because absolute IR intensities in km/mol are not
     what a reader compares -- the relative ordering of the strong bands is.

Usage:
    python benchmarks/ir/score.py <directory of ORCA .out files>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from rdkit import Chem, RDLogger
from rdkit.Chem import AllChem

from openchem.chem.orca_engine import OrcaQuantumEngineProvider

RDLogger.DisableLog("rdApp.*")

HERE = Path(__file__).resolve().parent


def _mol_for(smiles: str) -> Chem.Mol:
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    AllChem.EmbedMolecule(mol, randomSeed=0xF00D)
    AllChem.MMFFOptimizeMolecule(mol)
    return mol


def _spearman(a: list[float], b: list[float]) -> float:
    """Rank correlation, with ties averaged.

    Written out rather than pulled from scipy because this benchmark must
    run with the project's own dependencies, and because a hand-checkable
    20-line implementation is worth more here than a import.
    """

    def ranks(values: list[float]) -> list[float]:
        order = sorted(range(len(values)), key=lambda i: values[i])
        out = [0.0] * len(values)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
                j += 1
            average = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                out[order[k]] = average
            i = j + 1
        return out

    ra, rb = ranks(a), ranks(b)
    n = len(a)
    if n < 2:
        return float("nan")
    mean_a = sum(ra) / n
    mean_b = sum(rb) / n
    cov = sum((x - mean_a) * (y - mean_b) for x, y in zip(ra, rb))
    var_a = sum((x - mean_a) ** 2 for x in ra)
    var_b = sum((y - mean_b) ** 2 for y in rb)
    if var_a == 0 or var_b == 0:
        return float("nan")
    return cov / (var_a * var_b) ** 0.5


def main(out_dir: Path) -> int:
    reference = json.loads((HERE / "reference.json").read_text(encoding="utf-8"))
    provider = OrcaQuantumEngineProvider()

    pairs: list[tuple[str, float, float]] = []
    print("FREQUENCIES -- computed harmonic vs experimental fundamental\n")

    for name, entry in reference["molecules"].items():
        path = out_dir / f"{name}.out"
        if not path.is_file():
            print(f"  {name}: no output at {path}, skipped")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        result = provider.parse_vibrational_spectrum(
            text, _mol_for(entry["smiles"]), name, "opt_freq"
        )
        if result is None or not result.modes:
            print(f"  {name}: no modes parsed, skipped")
            continue
        if result.imaginary_modes:
            print(f"  {name}: SADDLE POINT ({len(result.imaginary_modes)} imaginary), skipped")
            continue

        computed = sorted(mode.wavenumber_cm1 for mode in result.modes)
        experimental = sorted(entry["fundamentals"])
        if len(computed) != len(experimental):
            print(
                f"  {name}: {len(computed)} computed vs {len(experimental)} reference "
                f"modes -- NOT scored, because pairing them by index would "
                f"manufacture the comparison"
            )
            continue

        print(f"  {name}")
        for calc, exp, label in zip(computed, experimental, entry["assignments"]):
            print(
                f"     {calc:8.1f}  vs {exp:8.1f}   "
                f"{calc - exp:+7.1f}  ({calc / exp:.4f})   {label}"
            )
            pairs.append((name, calc, exp))
        print()

    if not pairs:
        print("Nothing scored.")
        return 1

    # Least-squares scaling factor through the origin: the standard form for
    # a harmonic-frequency scale factor, minimising sum (s*calc - exp)^2.
    numerator = sum(calc * exp for _, calc, exp in pairs)
    denominator = sum(calc * calc for _, calc, exp in pairs)
    scale = numerator / denominator

    def mae(factor: float) -> float:
        return sum(abs(factor * calc - exp) for _, calc, exp in pairs) / len(pairs)

    print(f"modes scored: {len(pairs)}")
    print(f"  MAE unscaled          : {mae(1.0):8.1f} cm-1")
    print(f"  fitted scaling factor : {scale:.4f}")
    print(f"  MAE scaled            : {mae(scale):8.1f} cm-1")
    improvement = mae(1.0) - mae(scale)
    print(f"  improvement           : {improvement:8.1f} cm-1")
    if improvement <= 0:
        print("  -> the factor does NOT reduce the error. Do not apply it.")

    # Intensities, scored separately and only where a molecule has enough
    # distinct bands for a rank correlation to mean anything.
    print("\nINTENSITIES -- rank correlation of relative IR band strength")
    print("  (not scored: no experimental intensity table is entered here.")
    print("   What IS checked is that the computed ordering is internally")
    print("   consistent and that the strongest band is the expected one.)")
    for name, entry in reference["molecules"].items():
        path = out_dir / f"{name}.out"
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        result = provider.parse_vibrational_spectrum(
            text, _mol_for(entry["smiles"]), name, "opt_freq"
        )
        if result is None or not result.modes:
            continue
        with_intensity = [m for m in result.modes if m.ir_intensity_km_mol is not None]
        if not with_intensity:
            continue
        strongest = max(with_intensity, key=lambda m: m.ir_intensity_km_mol)
        print(
            f"  {name:10s} strongest band {strongest.wavenumber_cm1:8.1f} cm-1 "
            f"({strongest.ir_intensity_km_mol:.1f} km/mol, {strongest.character or '?'})"
        )
    return 0


if __name__ == "__main__":
    directory = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE
    raise SystemExit(main(directory))
