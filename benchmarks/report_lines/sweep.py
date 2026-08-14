"""Every result line the app really produces, and what each parser does to it.

Built because a string parser cannot be reviewed by reading its
producers. Two of them judge free-text `matched` lines written all over
`chem/`:

    chem/report_adapter._MEASUREMENT      presentation -- label + display
    chem/result_reduction.parse_reported_numbers   numeric batch columns

and the population they judge is spread across 49 calculators, so
"which lines does this affect" is not answerable by grep. It is
answerable by running them.

**OBSERVATIONAL. It runs production and reports on it.** The line
population is captured by instrumenting `report_adapter._split` itself
rather than by re-deriving which calculators emit what -- so a producer
added tomorrow is included with no change here. Nothing is simulated and
no parser is reimplemented: `--candidate` swaps only the VALUE group of
the shipped pattern, and the numeric arm calls the real
`parse_reported_numbers`.

WHY IT EARNS ITS KEEP. Fixing the `"Dipole Z: +0.16 Debye"` sign bug, the
first candidate pattern -- a proper number plus a `(?=\\s|$)` boundary, to
stop a comma-separated value list mis-splitting -- looked obviously
correct and REGRESSED 31 real lines: `"C: 23.79%"` and `"Percent buried
volume: 13.30%"` attach their unit with no space. Reading the producers
would not have found that. One sweep did.

WHAT IT DOES NOT REACH. Only `bootstrap.CALCULATOR_DEFINITIONS`, which is
every in-process calculator. The discovery-only `ServiceExecution`
entries in `bootstrap._EXTERNAL_CALCULATOR_DEFINITIONS` (Docking, Quantum
Chemistry) are owned by their own panels and their lines never appear
here -- so a parser change touching those has no coverage from this
script and needs its own evidence.

Usage:
    python sweep.py                       # the population, and each parser's verdict
    python sweep.py --refused             # only what each parser turns away
    python sweep.py --candidate '[-+]?\\d+(?:[.,]\\d+)*'    # diff a value pattern
    python sweep.py --candidate '...' --quiet   # just the two totals

**A pattern STARTING with `-` needs the `=` form** -- `--candidate='-?\\d...'`
-- or argparse reads it as an option and exits 2 before the sweep runs.
Which is easy to misread as the sweep failing.

Exit status is 1 when a candidate refuses anything the shipped pattern
accepts, so `--quiet` is usable as a check. It is NOT a pass/fail verdict:
a newly refused line can be exactly the intent (the boundary candidate
above refuses 36, of which 5 ARE its purpose and 31 are the regression).
Read the two directions; the exit code only tells you to look.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from rdkit import Chem, RDLogger
from rdkit.Chem import AllChem

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from openchem.bootstrap import CALCULATOR_DEFINITIONS  # noqa: E402
from openchem.chem import report_adapter  # noqa: E402
from openchem.chem.result_reduction import parse_reported_numbers  # noqa: E402

RDLogger.DisableLog("rdApp.*")

HERE = Path(__file__).resolve().parent

#: The embedding seed is pinned so the population is reproducible. It has
#: to be: several calculators report geometry-derived numbers, so an
#: unpinned run changes the DIGITS in a third of these lines and a diff
#: against a previous sweep becomes unreadable. It does not change which
#: line SHAPES appear, which is what the parsers are judged on.
SEED = 0xF00D


def _molecules() -> list[tuple[str, Chem.Mol]]:
    """The corpus, embedded, with every SMILES checked as it is read.

    **A SMILES THAT DOES NOT PARSE SILENTLY REMOVES COVERAGE**, and this
    project has already had one benchmark tell a different story because
    a from-memory structure failed to build and nothing said so. Refused
    loudly rather than skipped.
    """
    corpus = json.loads((HERE / "molecules.json").read_text(encoding="utf-8"))
    built: list[tuple[str, Chem.Mol]] = []
    for entry in corpus["molecules"]:
        mol = Chem.MolFromSmiles(entry["smiles"])
        if mol is None:
            raise SystemExit(
                f"{entry['name']}: SMILES does not parse ({entry['smiles']!r}). "
                "Fix it rather than dropping it -- see this entry's 'why'."
            )
        mol = Chem.AddHs(mol)
        params = AllChem.ETKDGv3()
        params.randomSeed = SEED
        if AllChem.EmbedMolecule(mol, params) != 0:
            AllChem.EmbedMolecule(mol, useRandomCoords=True, randomSeed=SEED)
        AllChem.MMFFOptimizeMolecule(mol)
        built.append((entry["name"], mol))
    return built


def collect_lines() -> list[str]:
    """Every distinct line that reaches `_split`, by instrumenting it.

    Patching the module global works because `facts_from_alert` looks
    `_split` up by name at call time. The real function is still called,
    so this observes rather than replaces.
    """
    seen: list[str] = []
    real = report_adapter._split

    def spy(line, source, category):
        seen.append(line)
        return real(line, source, category)

    report_adapter._split = spy
    try:
        for name, mol in _molecules():
            for definition in CALCULATOR_DEFINITIONS:
                compute = getattr(definition.execution, "compute", None)
                if compute is None:  # ServiceExecution: discovery-only
                    continue
                try:
                    compute(mol, f"uuid-{name}", {})
                except Exception:
                    # A calculator that refuses this molecule contributes no
                    # lines, which is a fact about that calculator and not a
                    # failure of the sweep. Its OTHER molecules still count.
                    continue
    finally:
        report_adapter._split = real
    return sorted(set(seen))


def _with_value(pattern: str) -> re.Pattern[str]:
    """The shipped measurement pattern with its value group replaced.

    Swapping only the value keeps the label bound and the units tail
    identical, so a diff attributes the change to the thing being tuned.
    """
    return re.compile(
        rf"^(?P<label>[^:]{{1,60}}):\s+(?P<value>{pattern})\s*(?P<units>[^\s].*)?$"
    )


def _parsed(rx: re.Pattern[str], line: str):
    match = rx.match(line.strip())
    if match is None:
        return None
    units = (match.group("units") or "").strip()
    value = match.group("value")
    return match.group("label").strip(), value, (value + " " + units).strip(), units


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--candidate",
        help="a replacement for the VALUE group of report_adapter._MEASUREMENT; "
             "prints the lines whose parse changes, in both directions",
    )
    parser.add_argument("--refused", action="store_true",
                        help="list what each parser turns away")
    parser.add_argument("--quiet", action="store_true",
                        help="totals only, for a fast pass/fail read")
    args = parser.parse_args()

    lines = collect_lines()
    shipped = report_adapter._MEASUREMENT

    print(f"distinct lines reaching _split : {len(lines)}")
    print(f"refused by report_adapter      : {sum(1 for ln in lines if not shipped.match(ln.strip()))}")
    numeric = {label for label, _v, _u in parse_reported_numbers(lines)}
    print(f"accepted by result_reduction   : {len(numeric)} numeric columns")

    if args.refused:
        print("\n--- report_adapter refuses (line stays whole, labelled by its source) ---")
        for ln in lines:
            if not shipped.match(ln.strip()):
                print(f"  {ln[:150]}")
        print("\n--- result_reduction refuses (no numeric batch column) ---")
        kept = {label for label, _v, _u in parse_reported_numbers(lines)}
        for ln in lines:
            head = ln.split(":")[0].strip()
            if head not in kept:
                print(f"  {ln[:150]}")

    if not args.candidate:
        return 0

    candidate = _with_value(args.candidate)
    gained, lost, altered = [], [], []
    for ln in lines:
        before, after = _parsed(shipped, ln), _parsed(candidate, ln)
        if before == after:
            continue
        (gained if before is None else lost if after is None else altered).append(
            (ln, before, after)
        )

    print(f"\ncandidate value pattern: {args.candidate}")
    print(f"  newly ACCEPTED : {len(gained)}")
    print(f"  newly REFUSED  : {len(lost)}   <- each one needs a justification")
    print(f"  parse ALTERED  : {len(altered)}")
    if args.quiet:
        return 1 if lost else 0

    for title, rows in (
        ("NEWLY REFUSED -- the regressions", lost),
        ("NEWLY ACCEPTED -- the fix", gained),
        ("ALTERED -- same line, different split", altered),
    ):
        if not rows:
            continue
        print(f"\n=== {title} ===")
        for ln, before, after in rows:
            print(f"  line : {ln[:140]}")
            print(f"    old: {before if before is None else (before[0], before[1], before[3])}")
            print(f"    new: {after if after is None else (after[0], after[1], after[3])}")
    return 1 if lost else 0


if __name__ == "__main__":
    raise SystemExit(main())
