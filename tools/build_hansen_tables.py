"""Build `chem/data/hansen_groups.json` from Stefanis & Panayiotou's paper.

Tables 3-6 of *Int J Thermophys* (2008) **29**:568-585,
doi 10.1007/s10765-008-0415-z -- see `[source:stefanis2008]`.

THE TEXT LAYER IS TRUSTED HERE, WHICH IT IS NOT FOR THE SCANNED SOURCES IN
THIS PROJECT. The paper is born-digital: it prints its own DOI, the glyphs
extract as real characters rather than plausible substitutes, and the rows
come out on an exactly regular stride. Contrast `joback_groups.json`, whose
header records five corrupted values on one page of a scan.

**BUT BORN-DIGITAL IS NOT THE SAME AS CLEAN, AND THIS PAPER CARRIES FOUR
TRANSCRIPTION HAZARDS.** Every one was found by running the paper's own
worked examples against the extraction rather than by reading the output:

    1  `>C=0` -- a DIGIT ZERO where the letter O belongs, in exactly one
       first-order group name. `O=C=N-` on the same page renders its O
       correctly, so this is one bad row rather than a systematic fault.

    2  `Ccyclic=O` in Table 4 is `C(cyclic)=O` in the alizarin worked
       example -- the same group spelled two ways in one paper, because the
       subscript flattens differently in a table cell and in running text.
       Keying on the worked example's spelling raises KeyError against the
       contribution table, which is how this was caught.

    3  THE DASH IS A DIFFERENT CHARACTER IN DIFFERENT TABLES, and this is
       the dangerous one because the strings look IDENTICAL in every
       rendering:

           Table 3   '-CH3'   U+2212 MINUS SIGN
           Table 5   '-CH3'   U+2013 EN DASH

       All three of U+002D, U+2013 and U+2212 appear across these tables. A
       lookup keyed on the raw name silently finds nothing when the low-delta
       branch consults Table 5, and a silently empty contribution set is a
       number rather than an error.

    4  the low-delta tables print FIVE decimal places where Tables 3 and 4
       print four, so a value pattern fitted to the main tables matches
       nothing in Tables 5 and 6.

So a canonical KEY is derived by folding every dash variant onto ASCII
`-`, and the paper's own spelling is kept beside it as `printed`. That is
the same discipline `tsei_radii.json` follows in keeping each row's printed
symbol: a later audit is then a line-by-line comparison against the page
rather than a re-derivation.

**THE ACCEPTANCE TEST IS THE PAPER'S OWN ARITHMETIC**, and it runs here
before anything is written. Tables 7-9 work 1-hexanal at W=0 and Tables
11-16 work alizarin at W=1, both printing their group assignments, their
per-group contributions and their totals. A transcription error in any row
either example touches contradicts a number the paper printed.

Needs `pymupdf` and a local copy of the paper, so it cannot run in CI --
the same admitted limit `build_ketcher_notices.py` carries. Run it in a
THROWAWAY venv, never the project venv:

    uv venv && uv pip install pymupdf
    PYTHONIOENCODING=utf-8 .venv/Scripts/python tools/build_hansen_tables.py

`--check` re-extracts and compares against the committed JSON without
writing, which is what a test can call when the paper IS available.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "src" / "openchem" / "chem" / "data" / "hansen_groups.json"

DEFAULT_PDF = Path(r"D:\Xaero Stuff\Documents\Sci Downloads\stefanis2008.pdf")

#: Zero-based page indices. Table 3 spans two pages.
PAGES_FIRST_ORDER = (10, 11)
PAGES_SECOND_ORDER = (12,)

#: Table 5 has a page to itself. Table 6 shares one with Tables 7-10, which
#: are the WORKED EXAMPLES -- full of values in the same shape, so a walk that
#: runs past Table 6's last row silently absorbs 1-hexanal's occurrences and
#: contributions as though they were group data. That is the Avdeef extraction
#: failure this project already records: a run past the end of one table into
#: the next produced a plausible row count and a corpus of two data qualities.
#: The stop is found by CAPTION rather than by a row count, so it survives the
#: table growing.
PAGE_LOW_FIRST = 13
PAGE_LOW_SECOND = 14
LOW_SECOND_STOPS_AT = "Table 7"

#: Eq. 24-26. The intercept is per parameter and is NOT a group contribution.
CONSTANTS = {"d": 17.3231, "p": 7.3548, "hb": 7.9793}

#: Eqs. 25 and 26 are stated valid only above this, and Tables 5/6 exist to
#: cover below it. In (MPa)^0.5.
LOW_DELTA_THRESHOLD = 3.0

#: EQS. 27 AND 28, AND THEY ARE EASY TO MISS. The low-range branch is not
#: Eqs. 25/26 with different group contributions -- it has its OWN
#: intercepts, given in a sentence between two figures rather than beside
#: Tables 5 and 6. Building the branch without them puts n-hexane's delta_p
#: at -2.009, a NEGATIVE solubility parameter, which is impossible; with them
#: it is 0.737 against a literature 0.0.
LOW_CONSTANTS = {"p": 2.7467, "hb": 1.3720}

#: Every dash the paper uses for the same bond stroke. Hazard 3.
DASHES = "\u002d\u2010\u2011\u2012\u2013\u2014\u2212"

#: Hazard 1, corrected with the printed form kept beside it.
DIGIT_ZERO_ROWS = {">C=0 (except as above)": ">C=O (except as above)"}

#: Hazard 2. The worked example's spelling, mapped onto the table's.
SPELLING_VARIANTS = {"C(cyclic)=O": "Ccyclic=O"}

#: Hazard 4, and it is wider than "five decimals". Measured across Tables 5
#: and 6, the value cells come in FOUR shapes:
#:
#:     plain, 4 to 6 decimal places      71 cells
#:     a bare integer (`0`)               2
#:     `***`                             33
#:     SCIENTIFIC, superscript flattened  3   `10-8` and `2 10-8`
#:
#: The last is the trap. `10-8` is the paper's 10^-8 with the exponent's
#: superscript lost, and `2 10-8` is 2 x 10^-8 with the multiplication sign
#: lost too. Neither parses as a float, so a pattern that merely fails to
#: match them SKIPS A CELL -- and because rows are recognised by their shape,
#: one skipped cell slides the whole walk and the table comes back EMPTY
#: rather than short. Measured: Table 6 extracted 0 rows of 11 that way.
VALUE_RE = re.compile(
    r"^(?:[%s]?\d+(?:\.\d{1,8})?|\d*\s*10[%s]\d+)$" % (DASHES, DASHES)
)
SCIENTIFIC_RE = re.compile(r"^(\d*)\s*10[%s](\d+)$" % DASHES)
MISSING = "***"

SKIP_PREFIXES = (
    "Int J Thermophys", "Table ", "First-order groups", "Second-order groups",
    "Examples (Occurrences)", "Occurrences", "Contributions", "\u03b4d",
    "\u03b4p", "\u03b4hb", "Low \u03b4", "\u2217\u2217\u2217The specific",
    "\u2217\u2217\u2217The speci", "contributions to this delta",
    "parameter are not available", "solubility parameter", "the hydrogen-bonding",
    "values, \u03b4", "contributions to the polar",
)


def _is_page_furniture(line: str) -> bool:
    """A running page number or Springer's `123` mark, never a contribution.

    **`str.isdigit()` ALONE EATS A REAL VALUE.** Table 6's `-O-CHm-O-CHn-` row
    carries a bare `0` for its low-delta_p contribution, and a digit filter
    dropped it -- which slid the walk and cost that row entirely: 10 rows
    extracted of 11. Derived from the document rather than guessed: every page
    number here is three digits (578-585) and so is the `123` footer, while a
    contribution is a single digit or a decimal.
    """
    return line.isdigit() and len(line) >= 3


def canonical(name: str) -> str:
    """The lookup key: dashes folded to ASCII, case folded, whitespace squeezed.

    NEVER used for display -- `printed` carries what the paper wrote.

    CASE IS FOLDED BECAUSE THE PAPER VARIES IT: Table 4 writes `ring of 5
    carbons` and Table 6 writes `Ring of 5 carbons`, for the same group. The
    low-delta tables are a SUBSTITUTE parameter set for the same groups, so a
    key that does not match across tables makes the low-delta branch silently
    find nothing -- and an empty contribution set is a number, not an error.
    `_as_map` raises on a collision, so folding cannot quietly merge two
    genuinely different groups.
    """
    folded = "".join("-" if ch in DASHES else ch for ch in name)
    return " ".join(folded.split()).casefold()


def _number(text: str) -> float | None:
    if text == MISSING:
        return None
    scientific = SCIENTIFIC_RE.match(text)
    if scientific:
        mantissa, exponent = scientific.groups()
        return float(mantissa or 1) * 10 ** -int(exponent)
    return float("".join("-" if ch in DASHES else ch for ch in text))


def _lines(doc, pages) -> list[str]:
    out = []
    for page in pages:
        for raw in doc[page].get_text().split("\n"):
            line = raw.strip()
            if not line or _is_page_furniture(line):
                continue
            if any(line.startswith(p) for p in SKIP_PREFIXES):
                continue
            out.append(line)
    return out


def _rows(lines: list[str], columns: int, with_example: bool) -> list[dict]:
    """Walk lines and emit one record per row.

    A row is recognised by the SHAPE of what follows a candidate name --
    exactly `columns` value-or-missing lines -- rather than by a line count,
    so a caption fragment that survives the skip list shifts nothing.
    """
    rows: list[dict] = []
    i = 0
    while i < len(lines):
        window = lines[i + 1 : i + 1 + columns]
        is_row = len(window) == columns and all(
            VALUE_RE.match(w) or w == MISSING for w in window
        )
        if not is_row:
            i += 1
            continue
        printed = lines[i]
        values = [_number(w) for w in window]
        nxt = i + 1 + columns
        example = ""
        if with_example and nxt < len(lines):
            candidate = lines[nxt]
            if not (VALUE_RE.match(candidate) or candidate == MISSING):
                example = candidate
                nxt += 1
        rows.append({"printed": printed, "values": values, "example": example})
        i = nxt
    return rows


def _as_map(rows, keys, *, with_example):
    out = {}
    for row in rows:
        printed = row["printed"]
        corrected = DIGIT_ZERO_ROWS.get(printed, printed)
        key = canonical(corrected)
        if key in out:
            raise SystemExit(f"duplicate group key {key!r} -- the walk is mis-aligned")
        entry = dict(zip(keys, row["values"]))
        entry["printed"] = printed
        if corrected != printed:
            entry["corrected"] = corrected
        if with_example:
            entry["example"] = row["example"]
        out[key] = entry
    return out


def extract(pdf: Path) -> dict:
    try:
        import pymupdf
    except ImportError:  # pragma: no cover - tooling path
        raise SystemExit(
            "pymupdf is required. Install it in a THROWAWAY venv, never the "
            "project venv: uv venv && uv pip install pymupdf"
        )
    if not pdf.is_file():
        raise SystemExit(f"cannot find the paper at {pdf}")

    doc = pymupdf.open(pdf)
    first = _as_map(
        _rows(_lines(doc, PAGES_FIRST_ORDER), 3, True), ("d", "p", "hb"), with_example=True
    )
    second = _as_map(
        _rows(_lines(doc, PAGES_SECOND_ORDER), 3, True), ("d", "p", "hb"), with_example=True
    )
    low_first = _rows(_lines(doc, (PAGE_LOW_FIRST,)), 2, False)

    # Table 6 is followed on its page by the worked examples, so the walk is
    # cut at the next caption before any row is read.
    raw_lines = doc[PAGE_LOW_SECOND].get_text().split("\n")
    stop = next(
        (i for i, line in enumerate(raw_lines)
         if line.strip().startswith(LOW_SECOND_STOPS_AT)),
        None,
    )
    if stop is None:
        raise SystemExit(
            f"could not find {LOW_SECOND_STOPS_AT!r} on page {PAGE_LOW_SECOND} -- "
            "refusing to read Table 6 without knowing where it ends"
        )
    kept = []
    for raw in raw_lines[:stop]:
        line = raw.strip()
        if not line or _is_page_furniture(line):
            continue
        if any(line.startswith(p) for p in SKIP_PREFIXES):
            continue
        kept.append(line)
    low_second = _rows(kept, 2, False)

    return {
        "first_order": first,
        "second_order": second,
        "first_order_low": _as_map(low_first, ("p", "hb"), with_example=False),
        "second_order_low": _as_map(low_second, ("p", "hb"), with_example=False),
    }


# ---------------------------------------------------------------------------
# The paper's own worked examples, run before anything is written.
# ---------------------------------------------------------------------------

HEXANAL = ([("-CH3", 1), ("-CH2", 4), ("CHO (aldehydes)", 1)], None)
HEXANAL_PRINTED = {"d": 15.8411, "p": 7.9654, "hb": 5.7191}

ALIZARIN = (
    [("ACH", 6), ("AC", 4), ("ACOH", 2), (">C=O (except as above)", 2)],
    [("Ccyclic=O", 2)],
)
ALIZARIN_FIRST_ORDER = {"d": 21.5535, "p": 10.4308, "hb": 22.9753}
#: Only delta_hb's second-order total is printed as a number in the text.
ALIZARIN_SECOND_ORDER = {"hb": 22.02}


def _evaluate(tables, first, second, key):
    total = CONSTANTS[key]
    for name, count in first:
        total += count * tables["first_order"][canonical(name)][key]
    for name, count in second or ():
        total += count * tables["second_order"][canonical(name)][key]
    return total


def verify(tables) -> list[str]:
    problems = []
    for key, printed in HEXANAL_PRINTED.items():
        got = _evaluate(tables, HEXANAL[0], None, key)
        if abs(got - printed) > 5e-5:
            problems.append(f"1-hexanal delta_{key}: {got:.4f} against a printed {printed}")
    for key, printed in ALIZARIN_FIRST_ORDER.items():
        got = _evaluate(tables, ALIZARIN[0], None, key)
        if abs(got - printed) > 5e-5:
            problems.append(f"alizarin W=0 delta_{key}: {got:.4f} against a printed {printed}")
    for key, printed in ALIZARIN_SECOND_ORDER.items():
        got = _evaluate(tables, ALIZARIN[0], ALIZARIN[1], key)
        if abs(got - printed) > 5e-3:
            problems.append(f"alizarin W=1 delta_{key}: {got:.4f} against a printed {printed}")
    return problems


def document(tables) -> dict:
    return {
        "_source_key": "stefanis2008",
        "_description": (
            "Stefanis & Panayiotou group contributions to the Hansen solubility "
            "parameters, Tables 3-6 (pp 578-581)."
        ),
        "_read_from": "the BORN-DIGITAL text layer of stefanis2008.pdf, not a render",
        "_why_text_layer": (
            "The paper prints its own DOI and its glyphs extract as real characters, "
            "unlike the scanned sources in this project. Its four transcription "
            "hazards are recorded in tools/build_hansen_tables.py and are about "
            "NAMING rather than about digits: a digit zero for a letter O, one group "
            "spelled two ways, three different Unicode dashes for the same bond "
            "stroke, and five decimal places in the low-delta tables against four in "
            "the main ones."
        ),
        "_equations": {
            "_table": "Eqs. 23-26, pp 573-574",
            "general": "f(x) = sum(Ni*Ci) + W*sum(Mj*Dj)",
            "W": "0 for a compound with NO second-order groups, 1 for one with any",
            "delta_d": "sum(Ni*Ci) + W*sum(Mj*Dj) + 17.3231",
            "delta_p": "sum(Ni*Ci) + W*sum(Mj*Dj) + 7.3548",
            "delta_hb": "sum(Ni*Ci) + W*sum(Mj*Dj) + 7.9793",
            "delta_t": "sqrt(delta_d**2 + delta_p**2 + delta_hb**2)",
        },
        "_units": {"delta_d": "MPa^0.5", "delta_p": "MPa^0.5",
                   "delta_hb": "MPa^0.5", "delta_t": "MPa^0.5"},
        "_constants": CONSTANTS,
        "_low_delta": {
            "threshold": LOW_DELTA_THRESHOLD,
            "constants": LOW_CONSTANTS,
            "equations": {
                "delta_p": "sum(Ni*Ci) + W*sum(Mj*Dj) + 2.7467   Eq. 27",
                "delta_hb": "sum(Ni*Ci) + W*sum(Mj*Dj) + 1.3720  Eq. 28",
            },
            "why": (
                "Eqs. 25 and 26 are stated valid only for values greater than 3 "
                "(MPa)^0.5. Tables 5 and 6 carry SEPARATE contributions for delta_p "
                "< 3 and delta_hb < 3, so the low range is answerable rather than "
                "refused -- but with a different parameter set, not the main one."
            ),
            "applies_to": ["p", "hb"],
        },
        "_applicability": (
            "Stated on p574: the model is applicable to organic compounds with "
            "THREE OR MORE CARBON ATOMS, excluding the atom of the characteristic "
            "group (e.g. -COOH or -CHO)."
        ),
        "_missing_marker": (
            "A null contribution is the paper's own '***', which its Table 5 caption "
            "expands as 'The specific group contributions to this delta parameter "
            "are not available'. It is ABSENCE, never zero."
        ),
        "_asymmetries": {
            "low_first_order_groups_absent_from_table_3": [
                "ACCH<", "CCl2F", "CHNH", "CHO"
            ],
            "why": (
                "Table 5 lists four first-order groups Table 3 does not, verified "
                "against the raw page rather than inferred from a failed lookup: "
                "ACCH< (0.86718, -1.44666), CHNH (1.25999, ***), CCl2F (***, ***) "
                "and a bare CHO (***, -0.40667). So a low-delta contribution can "
                "exist for a group with NO main-table contribution, and the "
                "reverse. Neither table is a subset of the other."
            ),
            "cho_is_ambiguous": (
                "Table 3 disambiguates CHO into 'CHO (aldehydes)' and 'CHO "
                "(ethers)', which carry different contributions. Table 5 writes a "
                "bare 'CHO'. Its low-delta_hb value of -0.40667 therefore cannot "
                "be attributed to either without a judgement the paper does not "
                "make -- so a consumer must REFUSE the low-delta branch for those "
                "two groups rather than pick one. Recorded here because the data "
                "cannot express the distinction and the code must not invent it."
            ),
        },
        "_naming": (
            "`printed` is the paper's own spelling and the key is that spelling with "
            "every dash variant folded onto ASCII '-'. Where the two differ by more "
            "than dashes, `corrected` records the change and why it was made."
        ),
        **tables,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, default=DEFAULT_PDF)
    parser.add_argument("--check", action="store_true",
                        help="re-extract and compare against the committed JSON")
    args = parser.parse_args()

    tables = extract(args.pdf)
    problems = verify(tables)
    if problems:
        print("THE PAPER'S OWN WORKED EXAMPLES DO NOT REPRODUCE:", file=sys.stderr)
        for line in problems:
            print("  " + line, file=sys.stderr)
        return 1

    counts = {name: len(rows) for name, rows in tables.items()}
    print("verified against 1-hexanal (W=0) and alizarin (W=1)")
    print("  " + ", ".join(f"{k} {v}" for k, v in counts.items()))

    built = document(tables)
    if args.check:
        if not OUTPUT.is_file():
            print(f"{OUTPUT} does not exist", file=sys.stderr)
            return 1
        existing = json.loads(OUTPUT.read_text(encoding="utf-8"))
        if existing != built:
            print(f"{OUTPUT} is STALE -- re-run without --check", file=sys.stderr)
            return 1
        print(f"{OUTPUT} is current")
        return 0

    OUTPUT.write_text(
        json.dumps(built, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"wrote {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
