"""Which term leads the layout score: crossings, or clearance?

`chem/lewis_layout.LayoutScore` compares two numbers lexicographically
rather than summing them, following `lewis_svg._lone_pair_slots` -- but
which of the two LEADS is a choice, and choosing it on the same molecules
used to claim the chooser works would be tuning and evaluating on one
dataset.

So: two candidate orderings, a corpus split BEFORE either is scored, the
ordering fixed on the design half, and the frozen ordering evaluated on
the held-out half. The same discipline as the solubility base-bias study,
at a much smaller scale.

    uv run --no-sync python benchmarks/lewis_layout/choose.py

## Declared before running

CANDIDATES        A = (-crossings, crowding)   crossings lead
                  B = (crowding, -crossings)   clearance leads

CRITERION         An ordering is better if, over its half of the corpus,
                  it is NOT WORSE than today's shipped layout
                  (Compute2DCoords alone) on either metric more often,
                  with total crossings removed as the tie-break.

                  "Not worse" rather than "better" because the point of
                  the chooser is that it cannot lose, not that it always
                  wins: on ten of the corpus the two engines agree and
                  there is nothing to choose.

SPLIT             Alphabetical by name, alternating. Deterministic, fixed
                  here, and independent of anything measured.

WHAT WOULD FALSIFY THE WHOLE DESIGN
                  If either ordering is WORSE than Compute2DCoords alone
                  on the holdout, the chooser is not worth having and the
                  honest outcome is to keep the single engine.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from rdkit import Chem
from rdkit.Chem import AllChem, rdCoordGen

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from openchem.chem.lewis_layout import count_crossings, crowding  # noqa: E402

#: Drug-like and textbook structures, spanning 3 to 74 atoms with
#: hydrogens. Chosen for size and ring variety, before anything was
#: measured.
CORPUS: dict[str, str] = {
    "acetaminophen": "CC(=O)Nc1ccc(O)cc1",
    "acetate": "CC(=O)[O-]",
    "adamantane": "C1C2CC3CC1CC(C2)C3",
    "adenine": "Nc1ncnc2[nH]cnc12",
    "alanine": "C[C@@H](N)C(=O)O",
    "aspirin": "CC(=O)Oc1ccccc1C(=O)O",
    "benzene": "c1ccccc1",
    "biphenyl": "c1ccc(-c2ccccc2)cc1",
    "caffeine": "Cn1cnc2c1c(=O)n(C)c(=O)n2C",
    "camphor": "CC1(C)C2CCC1(C)C(=O)C2",
    "cholesterol": "CC(C)CCC[C@@H](C)[C@H]1CC[C@H]2[C@@H]3CC=C4C[C@@H](O)CC[C@]4(C)[C@H]3CC[C@]12C",
    "cubane": "C1C2C3C4C1C5C2C3C45",
    "cyclohexane": "C1CCCCC1",
    "diazepam": "CN1c2ccc(Cl)cc2C(=Nc3ccccc3)Cc1=O",
    "ethanol": "CCO",
    "furan": "c1ccoc1",
    "glucose": "OC[C@H]1OC(O)[C@H](O)[C@@H](O)[C@@H]1O",
    "glycine": "NCC(=O)O",
    "ibuprofen": "CC(C)Cc1ccc(cc1)[C@@H](C)C(O)=O",
    "imidazole": "c1cnc[nH]1",
    "indole": "c1ccc2[nH]ccc2c1",
    "lactose": "OC[C@H]1O[C@@H](O[C@H]2[C@H](O)[C@@H](O)C(O)O[C@@H]2CO)[C@H](O)[C@@H](O)[C@H]1O",
    "menthol": "CC(C)[C@@H]1CC[C@@H](C)C[C@H]1O",
    "methane": "C",
    "morphine": "CN1CC[C@]23c4c5ccc(O)c4O[C@H]2[C@@H](O)C=C[C@H]3[C@H]1C5",
    "naphthalene": "c1ccc2ccccc2c1",
    "nicotine": "CN1CCC[C@H]1c1cccnc1",
    "norbornane": "C1CC2CCC1C2",
    "paracetamol_dimer": "CC(=O)Nc1ccc(Oc2ccc(NC(C)=O)cc2)cc1",
    "penicillin_g": "CC1([C@@H](N2[C@H](S1)[C@@H](C2=O)NC(=O)Cc3ccccc3)C(=O)O)C",
    "phenol": "Oc1ccccc1",
    "pyridine": "c1ccncc1",
    "pyrrole": "c1cc[nH]c1",
    "quinine": "COc1ccc2nccc([C@@H](O)[C@H]3C[C@@H]4CCN3C[C@@H]4C=C)c2c1",
    "salicylic_acid": "OC(=O)c1ccccc1O",
    "strychnine": "O=C1C[C@H]2OCC=C3CN4CC[C@@]56[C@H]4C[C@H]3[C@H]2[C@H]6N1c1ccccc15",
    "sucrose": "OC[C@H]1O[C@@](CO)(O[C@H]2O[C@H](CO)[C@@H](O)[C@H](O)[C@H]2O)[C@@H](O)[C@@H]1O",
    "testosterone": "C[C@]12CC[C@H]3[C@@H](CCC4=CC(=O)CC[C@]34C)[C@@H]1CC[C@@H]2O",
    "thiophene": "c1ccsc1",
    "toluene": "Cc1ccccc1",
    "urea": "NC(=O)N",
    "water": "O",
}


def measure(mol) -> tuple[int, float]:
    conformer = mol.GetConformer()
    positions = {
        i: tuple(conformer.GetAtomPosition(i))[:2] for i in range(mol.GetNumAtoms())
    }
    bonds = [(b.GetBeginAtomIdx(), b.GetEndAtomIdx()) for b in mol.GetBonds()]
    return count_crossings(positions, bonds), crowding(positions, bonds)


def arms(smiles: str) -> dict[str, tuple[int, float]]:
    base = Chem.AddHs(Chem.MolFromSmiles(smiles))
    rdkit_arm = Chem.Mol(base)
    AllChem.Compute2DCoords(rdkit_arm)
    coordgen_arm = Chem.Mol(base)
    rdCoordGen.AddCoords(coordgen_arm)
    return {"rdkit": measure(rdkit_arm), "coordgen": measure(coordgen_arm)}


def pick(measurements: dict[str, tuple[int, float]], ordering: str) -> str:
    def key(name: str):
        crossings, clearance = measurements[name]
        return (-crossings, clearance) if ordering == "A" else (clearance, -crossings)

    # Ties keep "rdkit", the shipped engine -- a chooser that flipped on a
    # tie would churn layouts for no measured reason.
    return max(("rdkit", "coordgen"), key=lambda name: (key(name), name == "rdkit"))


def evaluate(names: list[str], ordering: str) -> dict:
    not_worse = 0
    crossings_removed = 0
    strictly_better = 0
    for name in names:
        measurements = arms(CORPUS[name])
        chosen = pick(measurements, ordering)
        base_crossings, base_clearance = measurements["rdkit"]
        got_crossings, got_clearance = measurements[chosen]
        if got_crossings <= base_crossings and got_clearance >= base_clearance:
            not_worse += 1
        if got_crossings < base_crossings or got_clearance > base_clearance:
            strictly_better += 1
        crossings_removed += base_crossings - got_crossings
    return {
        "n": len(names),
        "not_worse": not_worse,
        "strictly_better": strictly_better,
        "crossings_removed": crossings_removed,
    }


def main() -> None:
    names = sorted(CORPUS)
    design = names[0::2]
    holdout = names[1::2]
    print(f"design  ({len(design)}): {', '.join(design)}")
    print(f"holdout ({len(holdout)}): {', '.join(holdout)}")
    print()

    print("=== DESIGN: choosing the field ordering ===")
    design_results = {o: evaluate(design, o) for o in ("A", "B")}
    for ordering, result in design_results.items():
        print(f"  {ordering}: {result}")

    chosen = max(
        ("A", "B"),
        key=lambda o: (
            design_results[o]["not_worse"],
            design_results[o]["crossings_removed"],
        ),
    )
    print(f"\n  CHOSEN AND NOW FROZEN: ordering {chosen}")

    print("\n=== HOLDOUT: evaluating the frozen ordering ===")
    holdout_result = evaluate(holdout, chosen)
    print(f"  {chosen}: {holdout_result}")

    # The status quo is the control: keeping one engine is "not worse"
    # by definition and never strictly better, so the chooser has to
    # clear a bar that is trivially met on one axis and impossible on
    # the other.
    print(f"  keeping one engine would be: not_worse={len(holdout)}"
          f" of {len(holdout)}, strictly_better=0")

    verdict = (
        "SHIP"
        if holdout_result["not_worse"] == holdout_result["n"]
        and holdout_result["strictly_better"] > 0
        else "DO NOT SHIP -- keep the single engine"
    )
    print(f"\n  VERDICT: {verdict}")

    Path(__file__).with_name("result.json").write_text(
        json.dumps(
            {
                "design": design,
                "holdout": holdout,
                "design_results": design_results,
                "chosen_ordering": chosen,
                "holdout_result": holdout_result,
                "verdict": verdict,
            },
            indent=1,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
