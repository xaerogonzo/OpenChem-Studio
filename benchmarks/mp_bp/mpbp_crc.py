"""CRC Handbook of Chemistry and Physics, 97th ed. (2016), "Physical Constants of Organic Compounds": raw entries.

Same approach as `mpbp_lange.py` -- columns recovered from where each span sits, never from reading order -- and
a much cleaner source: the text layer is mapped (the minus sign is a real character), every entry prints a
Hill formula and a CAS Registry Number, and the table says in its own words what its notation means (see
`mpbp_cells.py`). Measured on page 141: the columns start at x = 55 (No.), 77 (Name), 158 (Synonym), 240
(Mol. Form.), 291 (CAS RN), 327 (Mol. Wt.), 354 (Physical Form), 389 (mp), 427 (bp), 463 (den), 491 (nD) and
519 (Solubility), and a sub- or superscript is set at 4.2 points against 6.8.

An entry is a row that has BOTH a number in the first column and a molecular formula in the formula column; the
structure-diagram pages, which print only drawings and numbers, therefore yield nothing. Needs `pymupdf`; the
file is copyrighted and is read from the local library, never committed.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

SOURCE_ID = "crc97"
EDITION = "Haynes (ed.), CRC Handbook of Chemistry and Physics, 97th ed., CRC Press, 2016 (Physical Constants of Organic Compounds)"

#: Column bands as offsets from the entry-number column (x = 55 on the page measured). Relative, so a facing page
#: set a few points to one side reads the same.
BANDS = (
    ("no", -6.0, 18.0),
    ("name", 18.0, 100.0),
    ("synonym", 100.0, 182.0),
    ("formula", 182.0, 232.0),
    ("cas", 232.0, 267.0),
    ("weight", 267.0, 294.0),
    ("form", 294.0, 330.0),
    ("mp", 330.0, 368.0),
    ("bp", 368.0, 404.0),
    ("density", 404.0, 432.0),
    ("refractive", 432.0, 460.0),
    ("solubility", 460.0, 1e9),
)

FIRST_PAGE = 138
LAST_PAGE = 700
_SMALL = 5.5
_NUMBER = re.compile(r"^\d{1,5}[a-z]?$")
_CAS = re.compile(r"\b\d{2,7}-\d{2}-\d\b")


@dataclass
class RawEntry:
    entry_no: str
    pdf_page: int
    name_lines: list[str] = field(default_factory=list)
    synonym_lines: list[str] = field(default_factory=list)
    formula: str = ""
    cas: str = ""
    weight: str = ""
    form: str = ""
    mp_lines: list[str] = field(default_factory=list)
    bp_lines: list[str] = field(default_factory=list)


def _band(rel: float) -> str | None:
    for name, lo, hi in BANDS:
        if lo <= rel < hi:
            return name
    return None


def _lines(items, base_rows) -> list[str]:
    by_line: dict[float, list] = defaultdict(list)
    for x0, y0, size, text in items:
        if size >= _SMALL:
            base = min(base_rows, key=lambda b: abs(b - y0))
            by_line[base].append((x0, "n", text))
        else:
            above = [b for b in base_rows if -0.8 <= y0 - b < 6.0]
            if not above:
                continue
            base = max(above)
            by_line[base].append((x0, "sup" if y0 - base < 2.0 else "sub", text))
    out = []
    for base in sorted(by_line):
        parts = []
        for x0, kind, text in sorted(by_line[base], key=lambda t: t[0]):
            parts.append({"n": text, "sup": "^{" + text + "}", "sub": "_{" + text + "}"}[kind])
        line = "".join(parts).strip()
        if line:
            out.append(line)
    return out


def read_page(page, pdf_page: int) -> list[RawEntry]:
    spans = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            if tuple(round(v) for v in line["dir"]) != (1, 0):
                continue
            for s in line["spans"]:
                if s["text"].strip():
                    spans.append((s["bbox"][0], s["bbox"][1], s["size"], s["text"]))
    # The entry-number column is where digit-only spans start, most often: find it from rows that also hold a CAS number.
    cas_rows = [y for x, y, size, text in spans if size >= _SMALL and _CAS.fullmatch(text.strip())]
    candidates = [(round(x, 0), y) for x, y, size, text in spans if size >= _SMALL and _NUMBER.match(text.strip())
                  and any(abs(y - c) < 1.5 for c in cas_rows)]
    if not candidates:
        return []
    origin = defaultdict(int)
    for x, _y in candidates:
        origin[x] += 1
    no_x = max(origin, key=origin.get)
    numbered = sorted(
        (y, text.strip()) for x, y, size, text in spans
        if size >= _SMALL and abs(x - no_x) < 4.0 and _NUMBER.match(text.strip()) and any(abs(y - c) < 1.5 for c in cas_rows)
    )
    starts = [y for y, _ in numbered] + [1e9]
    entries = []
    for k, (y, number) in enumerate(numbered):
        lo, hi = y - 0.9, starts[k + 1] - 0.9
        mine = [s for s in spans if lo <= s[1] < hi]
        base_rows = sorted({round(s[1], 1) for s in mine if s[2] >= _SMALL})
        merged: list[float] = []
        for b in base_rows:
            if not merged or b - merged[-1] > 1.5:
                merged.append(b)
        by_band: dict[str, list] = defaultdict(list)
        for x0, y0, size, text in mine:
            band = _band(x0 - no_x)
            if band:
                by_band[band].append((x0, y0, size, text))
        entry = RawEntry(entry_no=number, pdf_page=pdf_page)
        entry.name_lines = _lines(by_band["name"], merged)
        entry.synonym_lines = _lines(by_band["synonym"], merged)
        entry.formula = " ".join(_lines(by_band["formula"], merged)).replace("_{", "").replace("}", "")
        entry.cas = " ".join(_lines(by_band["cas"], merged))
        entry.weight = " ".join(_lines(by_band["weight"], merged))
        entry.form = " ".join(_lines(by_band["form"], merged))
        entry.mp_lines = _lines(by_band["mp"], merged)
        entry.bp_lines = _lines(by_band["bp"], merged)
        entries.append(entry)
    return entries


def read_all(path) -> tuple[list[RawEntry], dict]:
    import pymupdf

    doc = pymupdf.open(path)
    entries: list[RawEntry] = []
    report = {"pages_read": 0, "pages_with_entries": 0}
    for p in range(FIRST_PAGE, min(LAST_PAGE, len(doc) - 1) + 1):
        report["pages_read"] += 1
        got = read_page(doc[p], p)
        if got:
            report["pages_with_entries"] += 1
            entries.extend(got)
    return entries, report
