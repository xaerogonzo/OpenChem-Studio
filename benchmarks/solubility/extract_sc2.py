"""Step 1b (optional): the Solubility Challenge 2 "tight" set, from the paper.

    uv run --no-sync python benchmarks/solubility/extract_sc2.py <llinas2020.pdf>

Table 1 of Llinas, Oprisiu & Avdeef 2020 (doi 10.1021/acs.jcim.0c00701):
100 druglike compounds with interlaboratory-mean intrinsic solubility, a
PER-COMPOUND standard deviation, the number of literature sources behind
each value, a melting point, a logP, and the General Solubility Equation's
own prediction.

**WHY THIS SET IS WORTH THE EXTRACTION.** It brings two things the first
evaluation set cannot:

  * a NOISE FLOOR. Interlab SD averages 0.17 log unit here, so nothing can
    be scored below that and a difference smaller than it is not a
    difference.
  * a PUBLISHED BASELINE. The GSE column lets the scorer reproduce the
    number the paper reports (RMSE 1.1), which is how a reader tells "our
    model is mediocre" from "this endpoint is hard".

**THE EXTRACTION VALIDATES ITSELF AGAINST THE PAPER, AND REFUSES TO WRITE
ANYTHING THAT DISAGREES.** Table 1 closes with a Min/Max/Mean row; this
recomputes all four columns plus the GSE RMSE against it. That is not
ceremony. The first attempt ran straight past the end of Table 1 into
Table 2 -- the "contentious" set, whose interlab SD is 0.62 -- and
produced a perfectly plausible 129-row table silently mixing two data
qualities. The summary row is the only thing that caught it.

Two more defects the validation forced out:

  * the paper states 100 compounds and the first clean pass found 99,
    because `bromazepam`'s row is split across a page break;
  * a melting point carrying a footnote marker reads as `193b`, which a
    plain numeric match rejects.

Needs the PDF, which is not in this repository, and network access to
resolve compound NAMES -- the table carries no structures.
"""

from __future__ import annotations

import csv
import json
import re
import statistics
import sys
import time
from pathlib import Path

OUT = Path(__file__).resolve().parent / "data"

#: The paper's own closing row for Table 1, and the GSE RMSE it states.
#: These ARE the extraction's acceptance test.
PAPER_SUMMARY = {
    "logS0": (-6.8, -1.2, -4.0),
    "sd": (0.11, 0.22, 0.17),
    "mp": (33.0, 350.0, 191.0),
    "logp": (-2.0, 6.3, 2.6),
}
PAPER_GSE_RMSE = 1.1
PAPER_ROW_COUNT = 100

_NUM = re.compile(r"^(-?\d+(?:\.\d+)?)[a-z]?$")  # a trailing letter is a footnote
_HEAD = {"compound", "log S0", "SD", "n", "mp (oC)", "log P", "GSE -log S"}
_NOISE = re.compile(
    r"Journal of Chemical|pubs\.acs\.org|^Article$|dx\.doi\.org|J\. Chem\. Inf\.|^[A-Z]$"
)


def _number(line: str) -> float | None:
    match = _NUM.match(line)
    return float(match.group(1)) if match else None


def parse_table_one(pdf_path: Path) -> list[dict]:
    import pymupdf

    document = pymupdf.open(pdf_path)
    text = "\n".join(page.get_text() for page in document)
    text = text.replace("−", "-").replace("–", "-")

    start = text.index("Table 1. Intrinsic Solubility")
    # The Min/Max/Mean row closes Table 1. Stopping anywhere later walks
    # into Table 2 and its 0.62-SD measurements.
    end = text.index("\nMin\n", start)
    lines = [line.strip() for line in text[start:end].splitlines() if line.strip()]

    rows: list[dict] = []
    pending: dict | None = None
    index = 0
    while index < len(lines):
        line = lines[index]
        if _number(line) is not None:
            if pending is not None:
                while (
                    index < len(lines)
                    and len(pending["nums"]) < 6
                    and _number(lines[index]) is not None
                ):
                    pending["nums"].append(_number(lines[index]))
                    index += 1
                if len(pending["nums"]) == 6:
                    rows.append(pending)
                    pending = None
                continue
            index += 1
            continue
        if line.startswith("Table 1") or line in _HEAD or _NOISE.search(line) or len(line) > 60:
            index += 1
            continue
        nums: list[float] = []
        scan = index + 1
        while scan < len(lines) and len(nums) < 6 and _number(lines[scan]) is not None:
            nums.append(_number(lines[scan]))
            scan += 1
        record = {"name": line, "nums": nums}
        if len(nums) == 6:
            rows.append(record)
            index = scan
        elif nums:
            pending = record  # split across a page break
            index = scan
        else:
            index += 1

    return [
        {
            "name": r["name"],
            "measured_logs": r["nums"][0],
            "sd": r["nums"][1],
            "sources": int(r["nums"][2]),
            "melting_point_c": r["nums"][3],
            "logp": r["nums"][4],
            "gse_logs": r["nums"][5],
        }
        for r in rows
    ]


def validate(rows: list[dict]) -> list[str]:
    """Every disagreement with the paper, or an empty list."""
    problems = []
    if len(rows) != PAPER_ROW_COUNT:
        problems.append(f"{len(rows)} compounds, paper states {PAPER_ROW_COUNT}")
    fields = {"logS0": "measured_logs", "sd": "sd", "mp": "melting_point_c", "logp": "logp"}
    tolerances = {"logS0": 0.06, "sd": 0.006, "mp": 1.0, "logp": 0.06}
    for key, field in fields.items():
        values = [r[field] for r in rows]
        got = (min(values), max(values), statistics.fmean(values))
        for label, mine, theirs in zip(("min", "max", "mean"), got, PAPER_SUMMARY[key]):
            if abs(mine - theirs) > tolerances[key]:
                problems.append(f"{key} {label} {mine:.2f} against the paper's {theirs}")
    rmse = (sum((r["gse_logs"] - r["measured_logs"]) ** 2 for r in rows) / len(rows)) ** 0.5
    if abs(rmse - PAPER_GSE_RMSE) > 0.06:
        problems.append(f"GSE RMSE {rmse:.2f} against the paper's {PAPER_GSE_RMSE}")
    return problems


def resolve_structures(rows: list[dict]) -> tuple[list[dict], list[str]]:
    """PubChem, because the table gives names and no structures.

    **CACHED AND RETRIED, because the naive version is not reproducible.**
    Two consecutive runs resolved 100 and then 97 of the same names --
    diazoxide, diclofenac and nortriptyline dropped out on the second,
    which is rate limiting rather than anything about those compounds. A
    corpus whose membership depends on network luck is not a corpus, and
    the failure is silent unless somebody compares row counts.

    The cache also makes a re-run free, which matters because every other
    step here is deterministic and this one was the reason to avoid
    re-running at all.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
    from openchem.chem.naming_providers import NamingError, pubchem_structure_for_name

    cache_path = OUT / "sc2_smiles_cache.json"
    cache: dict[str, str] = {}
    if cache_path.is_file():
        cache = json.loads(cache_path.read_text(encoding="utf-8"))

    def candidates(name: str) -> list[str]:
        # The table inverts substituent prefixes: "DOPA, L-" is L-DOPA and
        # "barbital,buta-" is butabarbital. Plain name first.
        out = [name]
        if "," in name:
            head, tail = (part.strip() for part in name.split(",", 1))
            out += [tail + head, tail.rstrip("-") + head, tail.rstrip("-") + "-" + head]
        return out

    def lookup(name: str) -> str | None:
        for attempt in range(3):
            for query in candidates(name):
                try:
                    return pubchem_structure_for_name(query).smiles
                except NamingError as exc:
                    # "no record" is a real answer about that spelling;
                    # anything else is the network and deserves a retry.
                    if "no record" not in str(exc).lower():
                        break
            time.sleep(1.0 + attempt)
        return None

    resolved, unresolved = [], []
    for row in rows:
        name = row["name"]
        smiles = cache.get(name) or lookup(name)
        if smiles:
            cache[name] = smiles
            resolved.append({**row, "smiles": smiles})
        else:
            unresolved.append(name)

    OUT.mkdir(exist_ok=True)
    cache_path.write_text(json.dumps(cache, indent=1, sort_keys=True), encoding="utf-8")
    return resolved, unresolved


def main() -> int:
    if len(sys.argv) < 2:
        raise SystemExit("usage: extract_sc2.py <path to llinas2020.pdf>")
    pdf = Path(sys.argv[1])
    if not pdf.is_file():
        raise SystemExit(f"No such file: {pdf}")

    rows = parse_table_one(pdf)
    problems = validate(rows)
    if problems:
        # Refuse rather than write a corpus that disagrees with its source.
        raise SystemExit(
            "Extraction does not reproduce the paper's own summary row:\n"
            + "\n".join(f"  - {p}" for p in problems)
        )
    print(f"parsed and validated {len(rows)} compounds against the paper's summary row")

    rows, unresolved = resolve_structures(rows)
    if unresolved:
        raise SystemExit(
            f"{len(unresolved)} of {PAPER_ROW_COUNT} names did not resolve: {unresolved}. "
            "Refusing to write a short corpus -- re-run to retry, the rest is cached."
        )

    OUT.mkdir(exist_ok=True)
    fields = [
        "name", "smiles", "measured_logs", "sd", "sources",
        "melting_point_c", "logp", "gse_logs",
    ]
    with (OUT / "sc2_tight.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows({k: r[k] for k in fields} for r in rows)

    (OUT / "sc2_manifest.json").write_text(
        json.dumps(
            {
                "evaluation_source": "Solubility Challenge 2, Test Set 1 (Llinas, Oprisiu & Avdeef 2020)",
                "source_version": "doi 10.1021/acs.jcim.0c00701, Table 1",
                "measured_unit": "logS (log mol/L)",
                "target_type": "intrinsic",
                "temperature_c": 25,
                "ph": None,
                "solid_form": "unknown",
                "rows": len(rows),
                "interlab_sd_log": 0.17,
                "published_baseline": {"name": "GSE", "rmse": PAPER_GSE_RMSE},
                "models_trained_on_this": [],
            },
            indent=1,
        ),
        encoding="utf-8",
    )
    print(f"wrote {OUT / 'sc2_tight.csv'} ({len(rows)} compounds with structures)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
