"""Name ordinary molecules and read each name back, the instrument round 8 found its best defects with.

    python tools/naming_probe.py "CC(=O)C(=O)C" "COC(=O)OC" "C=CC(N)=O"
    python tools/naming_probe.py --failures "CON(C)C(C)=O"      # also print every plan that FAILED to execute
    python tools/naming_probe.py --file molecules.txt           # one SMILES per line, '#' comments

**WHY IT EXISTS.** The naming corpora measure the engine on what they contain. Six of round 8's limitations-pass fixes (acrylamide as
`prop-2-eneamide`, the Weinreb amide as an 'azinite' ester, biacetyl as `3-oxobutan-2-one`, dimethyl carbonate as `dimethoxyoxomethane`, ...)
were in NO corpus row and were found by naming a battery of ordinary compounds whose names one knows. This makes that a one-line command:
the SMILES is canonicalised first (the app names the RDKit canonical spelling, and the engine's output depends on atom order), named, and
read back through OPSIN with the app's own verdict (`MATCH`, `TAUTOMER`, `MISMATCH`, `PARSER_FAILED`, ...). A name that reads back is NOT thereby right,
so the point is to READ the names.

`--failures` prints, for every substitutive plan the engine tried, the message of a plan that failed to execute. A top-ranked plan that fails
execution is SILENT: the engine falls to the next plan and names the molecule differently ('atoms [0] unclaimed', 'owned by no node'), which is how
an amide beside an acid was once ranked below the amide. Needs a JRE for the read-back (JAVA_HOME and `java` on PATH).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


def _name_with_failures(smiles: str):
    """The engine's name, and the messages of every plan whose execution returned an error tree."""
    from openchem.vendor.iupac_namer import engine, name_smiles

    failures: list[str] = []
    original = engine.SubstitutivePath.execute

    def spy(self, plan, *args, **kwargs):
        out = original(self, plan, *args, **kwargs)
        if type(out).__name__ == "ErrorTree":
            failures.append(f"parent={plan.named_parent.name!r} pcg={plan.pcg_type}: {getattr(out, 'message', '')[:200]}")
        return out

    engine.SubstitutivePath.execute = spy
    try:
        return name_smiles(smiles), failures
    finally:
        engine.SubstitutivePath.execute = original


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("smiles", nargs="*")
    parser.add_argument("--file", type=Path, help="one SMILES per line; blank lines and '#' comments are skipped")
    parser.add_argument("--failures", action="store_true", help="also print plans that failed to execute")
    parser.add_argument("--no-readback", action="store_true", help="skip OPSIN (no JRE)")
    args = parser.parse_args()

    from rdkit import Chem, RDLogger

    RDLogger.DisableLog("rdApp.*")
    items = list(args.smiles)
    if args.file:
        items += [line.strip() for line in args.file.read_text(encoding="utf-8").splitlines() if line.strip() and not line.lstrip().startswith("#")]
    if not items:
        parser.error("no molecules given")

    providers = None
    if not args.no_readback:
        from openchem.chem import naming_providers as providers  # the app's own verdicts

    for smiles in items:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            print(f"{'INVALID':10} {smiles}")
            continue
        canonical = Chem.MolToSmiles(mol)
        if args.failures:
            name, failures = _name_with_failures(canonical)
        else:
            from openchem.vendor.iupac_namer import name_smiles

            name, failures = name_smiles(canonical), []
        verdict = ""
        if providers is not None:
            verdict = providers.verify_name_round_trip(name, mol).name
        print(f"{verdict:10} {canonical:44} -> {name}")
        for failure in failures:
            print(f"{'':10}   failed plan: {failure}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
