"""Name ordinary molecules and read each name back, the instrument round 8 found its best defects with.

    python tools/naming_probe.py "CC(=O)C(=O)C" "COC(=O)OC" "C=CC(N)=O"
    python tools/naming_probe.py --failures "CON(C)C(C)=O"      # also print every plan that FAILED to execute
    python tools/naming_probe.py --file molecules.txt           # one SMILES per line, '#' comments
    python tools/naming_probe.py --file molecules.txt --json out.json   # also one record per structure, for a battery runner

**WHY IT EXISTS.** The naming corpora measure the engine on what they contain. Six of round 8's limitations-pass fixes (acrylamide as
`prop-2-eneamide`, the Weinreb amide as an 'azinite' ester, biacetyl as `3-oxobutan-2-one`, dimethyl carbonate as `dimethoxyoxomethane`, ...)
were in NO corpus row and were found by naming a battery of ordinary compounds whose names one knows. This makes that a one-line command:
the SMILES is canonicalised first (the app names the RDKit canonical spelling, and the engine's output depends on atom order), named, and
read back through OPSIN with the app's own verdict (`MATCH`, `TAUTOMER`, `MISMATCH`, `PARSER_FAILED`, ...). A name that reads back is NOT thereby right,
so the point is to READ the names.

`--failures` prints, for every substitutive plan the engine tried, the message of a plan that failed to execute. A top-ranked plan that fails
execution is SILENT: the engine falls to the next plan and names the molecule differently ('atoms [0] unclaimed', 'owned by no node'), which is how
an amide beside an acid was once ranked below the amide. Needs a JRE for the read-back (JAVA_HOME and `java` on PATH).

**Every structure also gets a STATUS, from plan counters** (naming round 9): `clean` (named, no plan died), `fallback` (a plan died and the
engine still named it: the silent fall-back), `no_plan` (no plan was ever generated: a CANDIDATE failure) and `all_plans_failed` (plans were
generated and every one died in the builder: an EXECUTION failure). The last line summarises them; the fallback count is the number to watch.

**It refuses a structure that is in a frozen population** (exit status 3): it names anything it is handed, so a frozen row could be typed
in by hand while debugging something else. The check is a salted hash from the population's META file, never the frozen file.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


NAMING_ERROR = "NAMING ERROR"

#: What the engine did to name one structure, from the counters below. The first two are names; the last two are not, and they are DIFFERENT
#: defects: `no_plan` is a CANDIDATE failure (no plan was ever generated to execute), `all_plans_failed` is an EXECUTION failure (plans were
#: generated and every one died in the builder).
STATUSES = ("clean", "fallback", "no_plan", "all_plans_failed")


def probe_structure(smiles: str) -> dict:
    """Name one canonical SMILES and report how the engine got there.

    `attempted` counts every `SubstitutivePath.execute` call, which includes the recursive naming of substituents, so it is a measure of
    the engine's work and not of the number of top-level plans. `errored` counts those that returned an error tree. `fallback` is the
    case round 8 found most of its defects in: a top-ranked plan died, the engine silently took the next one, and STILL produced a name.
    """
    from openchem.vendor.iupac_namer import engine, name_smiles

    failures: list[str] = []
    attempted = 0
    original = engine.SubstitutivePath.execute

    def spy(self, plan, *args, **kwargs):
        nonlocal attempted
        attempted += 1
        out = original(self, plan, *args, **kwargs)
        if type(out).__name__ == "ErrorTree":
            failures.append(f"parent={plan.named_parent.name!r} pcg={plan.pcg_type}: {getattr(out, 'message', '')[:200]}")
        return out

    engine.SubstitutivePath.execute = spy
    try:
        name = name_smiles(smiles)
    finally:
        engine.SubstitutivePath.execute = original
    if not str(name).startswith(NAMING_ERROR):
        status = "clean" if not failures else "fallback"
    else:
        status = "no_plan" if attempted == 0 else "all_plans_failed"
    return {"smiles": smiles, "name": name, "attempted": attempted, "errored": len(failures), "failures": failures, "status": status}


def _name_with_failures(smiles: str):
    """The engine's name, and the messages of every plan whose execution returned an error tree."""
    record = probe_structure(smiles)
    return record["name"], record["failures"]


def summarise(records: list[dict]) -> str:
    """One line for a battery: how many structures, by status, and the plan counters. The silent-fallback rate is the number to watch."""
    by_status = {s: sum(1 for r in records if r["status"] == s) for s in STATUSES}
    return (
        f"{len(records)} structures: " + ", ".join(f"{s} {n}" for s, n in by_status.items())
        + f"; plans executed {sum(r['attempted'] for r in records)}, error trees {sum(r['errored'] for r in records)}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("smiles", nargs="*")
    parser.add_argument("--file", type=Path, help="one SMILES per line; blank lines and '#' comments are skipped")
    parser.add_argument("--failures", action="store_true", help="also print plans that failed to execute")
    parser.add_argument("--no-readback", action="store_true", help="skip OPSIN (no JRE)")
    parser.add_argument("--json", type=Path, help="also write one record per structure (name, verdict, plan counters, status) to this file")
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

    import naming_populations as populations

    records: list[dict] = []
    refused = 0
    for smiles in items:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            print(f"{'INVALID':10} {smiles}")
            continue
        canonical = Chem.MolToSmiles(mol)
        # A frozen population's rows are evaluation-only and this tool names anything it is handed, so it asks the registry first. The
        # question is answered from the meta file's hashes; no frozen file is opened and no row is printed back.
        frozen = populations.frozen_key_of(canonical)
        if frozen is not None:
            print(f"{'FROZEN':10} refused: this structure is in {frozen}, which is evaluation-only (tools/naming_populations.py)")
            refused += 1
            continue
        record = probe_structure(canonical)
        verdict = providers.verify_name_round_trip(record["name"], mol).name if providers is not None else ""
        record["verdict"] = verdict
        records.append(record)
        print(f"{verdict:10} {canonical:44} -> {record['name']}")
        if args.failures:
            for failure in record["failures"]:
                print(f"{'':10}   failed plan: {failure}")
    print(summarise(records))
    if args.json:
        args.json.write_text(json.dumps(records, indent=1), encoding="utf-8")
    return 3 if refused else 0


if __name__ == "__main__":
    raise SystemExit(main())
