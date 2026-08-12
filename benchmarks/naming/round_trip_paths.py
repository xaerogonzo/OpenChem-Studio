"""Which of `MISMATCH`'s three paths does the corpus actually reach?

    python benchmarks/naming/round_trip_paths.py

WHY THIS EXISTS. `verify_name_round_trip` returns `MISMATCH` from three
places and only one is evidence against the name -- OPSIN failing to parse
our name, and RDKit failing to build OPSIN's SMILES, are both the CHECKER
failing rather than the name being wrong. That distinction is real, and the
obvious response is to split the verdict so a checker-failure shows the name
with a caveat instead of withholding it.

**This is the measurement that said not to.** Run over the 181-molecule
naming corpus, 2026-08-12:

    180  match
      1  MISMATCH: REAL skeleton disagreement    metformin

Zero inputs reach either checker-failed path, so the split would have been a
branch shipped, documented, and never once run. The conflation is recorded
on `verify_name_round_trip` and the three paths are held apart by tests
using controlled dependency failures; the split stays cheap if a real case
ever appears. Re-run this before deciding it has.

The single `MISMATCH` is metformin, which ROADMAP.md already carries as a
known `gate_disagreement` -- canonical SMILES and InChIKey disagreeing over
a tautomer. That is exactly the case withholding exists for.

NEEDS JAVA. OPSIN is a Java library reached through py2opsin, and it needs
both `JAVA_HOME` and `java` on PATH -- they are different requirements and
CLAUDE.md records the measurement that separated them:

    export JAVA_HOME="/d/Random Programs/OpenChemStudio_Data/jre/jdk-21.0.12+8-jre"
    export PATH="$JAVA_HOME/bin:$PATH"

Takes about three minutes: py2opsin starts a JVM per call.

ONE READING TRAP, paid for once. OPSIN emits `APPEARS_AMBIGUOUS` as a
WARNING while still returning a parse. An ambiguity warning is not a parse
failure and must not be counted as one.
"""

from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "src"))

CORPUS = Path(__file__).resolve().parent / "corpus.json"


def main() -> int:
    from rdkit import Chem, RDLogger

    RDLogger.DisableLog("rdApp.*")

    from openchem.chem.naming_providers import (
        NamingError,
        RoundTrip,
        _skeleton,
        opsin_available,
        opsin_structure_for_name,
        verify_name_round_trip,
    )
    from openchem.vendor.iupac_namer import name_smiles

    if not opsin_available():
        print(
            "OPSIN is not available -- this scan cannot distinguish a "
            "checker failure from a real mismatch without it. Set JAVA_HOME "
            "and put java on PATH; see this file's docstring.",
            file=sys.stderr,
        )
        return 1

    rows = json.loads(CORPUS.read_text(encoding="utf-8"))
    tally: collections.Counter[str] = collections.Counter()
    examples: dict[str, list[str]] = collections.defaultdict(list)

    for row in rows:
        mol = Chem.MolFromSmiles(row["smiles"])
        if mol is None:
            tally["input SMILES did not parse"] += 1
            continue
        try:
            name = name_smiles(Chem.MolToSmiles(mol))
        except Exception:  # noqa: BLE001 - the engine raises widely on odd input
            tally["the namer raised"] += 1
            continue
        if not name:
            tally["the namer produced no name"] += 1
            continue

        verdict = verify_name_round_trip(str(name), mol)
        if verdict is not RoundTrip.MISMATCH:
            tally[verdict.value] += 1
            continue

        # Re-walk the same three branches to say WHICH one produced it.
        try:
            parsed = opsin_structure_for_name(str(name))
            candidate = Chem.MolFromSmiles(parsed.smiles)
            if candidate is None:
                key = "MISMATCH: RDKit could not build OPSIN's SMILES"
            elif _skeleton(candidate) != _skeleton(mol):
                key = "MISMATCH: REAL skeleton disagreement"
            else:
                key = "MISMATCH: skeletons agree -- unreachable, investigate"
        except NamingError:
            key = "MISMATCH: OPSIN could not parse our name"

        tally[key] += 1
        if len(examples[key]) < 3:
            examples[key].append(row.get("name") or row["smiles"])

    print(f"corpus size: {len(rows)}\n")
    for key, count in tally.most_common():
        print(f"  {count:4}  {key}")
        for example in examples.get(key, []):
            print(f"          e.g. {example}")

    checker_failures = sum(
        count
        for key, count in tally.items()
        if key.startswith("MISMATCH:") and "REAL skeleton" not in key
    )
    print(
        f"\nChecker-failed paths reached: {checker_failures}. "
        "While this is 0, splitting MISMATCH would add an unreachable branch."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
