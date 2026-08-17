"""External test sets 1 and 2 from Avdeef 2020, for the base-bias power study.

    uv run --no-sync --with pymupdf python benchmarks/solubility/extract_avdeef_sets.py <avdeef2020.pdf>

Avdeef 2020 (ADMET & DMPK 8(1) 29-77, doi 10.5599/admet.766,
[source:avdeef2020]) carries five
appendix tables of intrinsic solubility. **ONLY TWO OF THEM ARE NEW TO
THIS PROJECT, and finding that out is the reason this script exists
rather than a bulk extractor:**

    A1   External Test Set 1 (Yalkowsky & Banerjee 1992)   21   NEW
    A2   External Test Set 2 (Hopfinger et al. 2009)       28   NEW
    A3   External Test Set 3 (interlab SD ~0.17)          100   = SC-2 TIGHT
    A4   External Test Set 4 (interlab SD ~0.62)           32   = SC-2 LOOSE
    A5   per-source listing behind test set 4             148   not a corpus

**A3 AND A4 ARE THE SOLUBILITY CHALLENGE 2 SETS UNDER DIFFERENT NAMES.**
Extracting them would double-count data `extract_sc2.py` already provides
and would INFLATE the apparent power of the very experiment this feeds --
the opposite of the point. This script refuses to emit them, by name, and
says why.

So the honest gain is **49 compounds**, not the 172 a naive row count over
these pages suggests. That number was wrong in the plan and is corrected
here rather than quietly.

**A1 CARRIES A HIGH LEAKAGE RISK AND IS EXTRACTED ANYWAY.** Yalkowsky &
Banerjee 1992 is a classic compilation of the kind ESOL was plausibly
fitted on, so much of it may vanish to de-leaking. Measuring that overlap
is itself informative -- "how much of this set is already in Delaney's
fit" is a fact worth having, and dropping the table unmeasured would be
assuming the answer.

WHAT IS TAKEN: name, log S0, SD, n. **The paper's own GSE / ABSOLV / RFR
predictions are never extracted**, so nothing downstream can score against
them by accident.

Needs the PDF (not in this repository) and network access to resolve
compound NAMES, which the tables give instead of structures.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path

OUT = Path(__file__).resolve().parent / "data"

#: Tables this script will emit, with the identity string that must appear
#: in the PDF for the extraction to be trusted at all.
WANTED = {
    "avdeef_a1": ("A1", "Yalkowsky", "External Test Set 1 (Yalkowsky & Banerjee, 1992)"),
    "avdeef_a2": ("A2", "Hopfinger", "External Test Set 2 (Hopfinger et al. 2009)"),
}

#: Refused on purpose, with the reason, so a future reader does not
#: "helpfully" add them.
DUPLICATES_OF_KNOWN = {
    "A3": "the SC-2 TIGHT set -- already extracted by extract_sc2.py",
    "A4": "the SC-2 LOOSE set -- the same data as llinas2020 Table 2",
    "A5": "a per-source listing behind test set 4, not an independent corpus",
}

#: Documented domains. A value outside these is an extraction fault, not a
#: surprising compound.
LOGS0_RANGE = (-12.0, 2.0)
SD_RANGE = (0.0, 3.0)

#: Read off the PDF by hand and asserted, so a layout change that silently
#: shifts a column is caught rather than absorbed.
SPOT_CHECKS = {
    "avdeef_a2": {"Acebutolol": (-2.56, 0.31, 3), "Amoxicillin": (-2.12, 0.07, 11)},
}

#: PDF spellings PubChem does not recognise, each with its reason. Kept
#: tiny and explicit: a name resolver that guesses is how a corpus quietly
#: acquires the wrong compound.
ALIASES = {
    # The table writes PCB congeners with the class first and the locants
    # trailing. PubChem knows the systematic name. Its presence is itself a
    # finding: test set 1 is a classic compilation containing industrial
    # chemistry, which is what Delaney's ESOL was fitted on.
    "PCB,2,2',4,5,5'-": "2,2',4,5,5'-pentachlorobiphenyl",
}

_NUMBER = re.compile(r"^-?\d+\.\d+$")


class ExtractionError(RuntimeError):
    """The extraction disagreed with the paper. Nothing is written."""


def _pages(pdf_path: Path) -> list[str]:
    import pymupdf

    return [page.get_text() for page in pymupdf.open(pdf_path)]


def _lines(pages: list[str]) -> list[str]:
    return [line.strip() for line in "\n".join(pages).split("\n")]


def _table_bounds(lines: list[str]) -> dict[str, tuple[int, int]]:
    """Where each appendix table starts and stops.

    A table ends where the NEXT one begins -- the failure mode this guards
    is exactly the one `extract_sc2.py` records: running past the end of a
    table into the next and producing a plausible, wrong corpus.
    """
    starts: list[tuple[str, int]] = []
    for index, line in enumerate(lines):
        match = re.match(r"Table\s+(A\d)\.", line)
        if match:
            starts.append((match.group(1), index))
    bounds: dict[str, tuple[int, int]] = {}
    for position, (tag, start) in enumerate(starts):
        end = starts[position + 1][1] if position + 1 < len(starts) else len(lines)
        # Continuations repeat the tag; keep the first start and the last end.
        if tag in bounds:
            bounds[tag] = (bounds[tag][0], end)
        else:
            bounds[tag] = (start, end)
    return bounds


def parse_table(lines: list[str], start: int, end: int) -> list[dict]:
    """Rows as (name, log S0, SD, n), ignoring every predicted column.

    The PDF lays one cell per line, so a row is a non-numeric name followed
    by two floats and an integer. Reading only those four means the column
    count after them can change without breaking this.
    """
    rows: list[dict] = []
    index = start
    while index < end - 3:
        name, value, sd, count = lines[index:index + 4]
        if (
            name
            and not _NUMBER.match(name)
            and _NUMBER.match(value or "")
            and _NUMBER.match(sd or "")
            and (count or "").isdigit()
        ):
            rows.append(
                {
                    "name": ALIASES.get(
                        name.strip(), name.replace("_", " ").strip()
                    ),
                    "measured_logs": float(value),
                    "sd": float(sd),
                    "sources": int(count),
                }
            )
            index += 4
            continue
        index += 1
    return rows


def validate(tag: str, key: str, rows: list[dict]) -> None:
    """Identity and domain checks. A plausible row count is not correctness."""
    if not rows:
        raise ExtractionError(f"{tag}: no rows parsed")

    by_name: dict[str, float] = {}
    for row in rows:
        low, high = LOGS0_RANGE
        if not low <= row["measured_logs"] <= high:
            raise ExtractionError(f"{tag}: {row['name']} logS0 {row['measured_logs']} out of range")
        if not SD_RANGE[0] <= row["sd"] <= SD_RANGE[1]:
            raise ExtractionError(f"{tag}: {row['name']} SD {row['sd']} out of range")
        if row["sources"] < 1:
            raise ExtractionError(f"{tag}: {row['name']} claims {row['sources']} sources")
        previous = by_name.get(row["name"])
        if previous is not None and abs(previous - row["measured_logs"]) > 1e-9:
            raise ExtractionError(
                f"{tag}: {row['name']} appears twice with different values "
                f"({previous} vs {row['measured_logs']})"
            )
        by_name[row["name"]] = row["measured_logs"]

    for name, expected in SPOT_CHECKS.get(key, {}).items():
        found = next((r for r in rows if r["name"].lower() == name.lower()), None)
        if found is None:
            raise ExtractionError(f"{tag}: spot check {name!r} missing")
        actual = (found["measured_logs"], found["sd"], found["sources"])
        if actual != expected:
            raise ExtractionError(f"{tag}: spot check {name!r} is {actual}, expected {expected}")


def _fingerprint(rows: list[dict]) -> str:
    """Content hash over canonicalised rows, so a regenerated corpus that
    differs is detectable even though the source is a PDF."""
    payload = sorted(
        f"{r['name'].lower()}|{r['measured_logs']:.4f}|{r['sd']:.4f}|{r['sources']}" for r in rows
    )
    return hashlib.sha256("\n".join(payload).encode("utf-8")).hexdigest()[:16]


def main() -> int:
    if len(sys.argv) < 2:
        raise SystemExit("usage: extract_avdeef_sets.py <path to avdeef2020.pdf>")
    pdf_path = Path(sys.argv[1])
    if not pdf_path.is_file():
        raise SystemExit(f"No such file: {pdf_path}")

    lines = _lines(_pages(pdf_path))
    bounds = _table_bounds(lines)

    for tag, reason in DUPLICATES_OF_KNOWN.items():
        if tag in bounds:
            print(f"  refusing Table {tag}: {reason}")

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
    from extract_sc2 import resolve_structures  # noqa: E402 - sibling script

    OUT.mkdir(exist_ok=True)
    for key, (tag, identity_word, title) in WANTED.items():
        if tag not in bounds:
            raise SystemExit(f"Table {tag} not found in {pdf_path.name}")
        start, end = bounds[tag]
        header = " ".join(lines[start:start + 3])
        if identity_word.lower() not in header.lower():
            raise SystemExit(
                f"{tag} header does not mention {identity_word!r}: {header!r}. "
                "Refusing to extract a table whose identity is not confirmed."
            )

        rows = parse_table(lines, start, end)
        validate(tag, key, rows)

        resolved, unresolved = resolve_structures(rows, cache_name=f"{key}_smiles_cache.json")
        if unresolved:
            raise SystemExit(
                f"{tag}: {len(unresolved)} names unresolved: {unresolved}. "
                "Re-run to retry -- the rest is cached. A corpus whose membership "
                "depends on network luck is not a corpus."
            )

        corpus = OUT / f"{key}.csv"
        with corpus.open("w", encoding="utf-8", newline="") as handle:
            handle.write("name,smiles,measured_logs,sd,sources\n")
            for row in resolved:
                handle.write(
                    f"{row['name']},{row['smiles']},{row['measured_logs']},"
                    f"{row['sd']},{row['sources']}\n"
                )
        (OUT / f"{key}_manifest.json").write_text(
            json.dumps(
                {
                    "evaluation_source": f"Avdeef 2020 {tag}: {title}",
                    "source_version": "doi 10.5599/admet.766",
                    "target_type": "intrinsic",
                    "measured_unit": "logS (log mol/L)",
                    "temperature_c": 25,
                    "ph": None,
                    "solid_form": "unknown",
                    "rows": len(resolved),
                    "content_fingerprint": _fingerprint(resolved),
                    "resolver": "PubChem via openchem.chem.naming_providers",
                    "resolved_on": date.today().isoformat(),
                    "leakage_note": (
                        "Yalkowsky & Banerjee 1992 is a classic compilation ESOL was "
                        "plausibly fitted on; de-leak against Delaney before use."
                        if key == "avdeef_a1"
                        else "Independent of Delaney's fit as far as the source states."
                    ),
                },
                indent=1,
            ),
            encoding="utf-8",
        )
        print(f"  {tag}: {len(resolved)} compounds -> {corpus.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
