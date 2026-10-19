"""Turns a list of stock SMILES into the file AiZynthFinder reads as a stock: one InChI key per line, the key the PLANNER computes (its own `Molecule.inchi_key`), so a molecule is "in stock" for exactly the reason the planner will use. Run by the PLANNER's Python.

    <planner python> make_stock.py stock_n1.txt stock_n1_inchikeys.txt

Why: AiZynthFinder's text stock holds InChI keys, not SMILES (`aizynthfinder/context/stock/queries.py`), and PaRoutes ships SMILES. A SMILES the planner cannot parse is reported and left out, never silently dropped.
"""
from __future__ import annotations

import sys
import warnings

warnings.simplefilter("ignore")


def main(source: str, destination: str) -> int:
    from aizynthfinder.chem import Molecule

    keys, failed = [], []
    with open(source, encoding="utf-8") as handle:
        for line in handle:
            smiles = line.strip()
            if not smiles:
                continue
            try:
                keys.append(Molecule(smiles=smiles).inchi_key)
            except Exception:  # noqa: BLE001 - reported below
                failed.append(smiles)
    with open(destination, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(keys) + "\n")
    print(f"{len(keys)} keys written ({len(set(keys))} distinct); {len(failed)} SMILES the planner could not read", file=sys.stderr)
    for smiles in failed[:10]:
        print("  unreadable:", smiles, file=sys.stderr)
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1], sys.argv[2]))
