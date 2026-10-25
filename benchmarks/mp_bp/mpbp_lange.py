"""Lange's Handbook of Chemistry (15th ed.), Section 1, Table 1.15: raw entries read off the PDF's geometry.

**Why geometry and not text.** The PDF's text layer lists every cell of a row in reading order and drops the
empty ones, so "172-175" alone in a row cannot say whether it is a melting point or a boiling point. The
columns are recovered from where each span sits instead. Measured on all 122 upright pages that print a
header: every column starts at the same x on every page (`BANDS`), and an entry's id always starts at x = 58.

**Why glyphs are rendered.** The sign of a temperature is a symbol-font character the text layer does not
carry (`'\\x01'` in a font called Universal-Greek). The first page read showed it: acetaldehyde's melting
point is -123.5 and the text layer says `123`. A negative value read as positive is a silent error, so each
such glyph is drawn at 500 dpi and classified by its ink: a bar at least four times as long as it is thick is
a minus sign; anything else (a `<`, a Greek letter, a plus-or-minus) is returned as unreadable and the cell
is refused, never guessed. `classify_ink` is pure and tested on hand-made bitmaps.

**What this module does not do.** It reads cells and names as printed. Deciding what an event was, resolving a
name to a structure and checking identity are `mpbp_cells.py` and `mpbp_identity.py`; this file needs
`pymupdf` (not a project dependency: `uvx --with pymupdf python -I ...`) and is imported lazily by the builder.
The Lange file is copyrighted and is read from the local library, never committed.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

SOURCE_ID = "lange15"
EDITION = "Dean (ed.), Lange's Handbook of Chemistry, 15th ed., McGraw-Hill, 1999 (Section 1, Table 1.15)"

#: The columns of Table 1.15 as x-intervals (points) on an upright page. Measured, not assumed: the header word of
#: each column starts at the same x on all 122 upright pages that print one (No. 61, Name 111, Formula 203/277,
#: Beilstein 316, Density 357, Refractive 393, Melting 439, Boiling 483, Flash 526, Solubility 569) and the data
#: start about five points left of the header word.
BANDS = (
    ("id", 50.0, 80.0),
    ("name", 80.0, 160.0),
    ("formula", 160.0, 272.0),
    ("weight", 272.0, 308.0),
    ("beilstein", 308.0, 352.0),
    ("density", 352.0, 390.0),
    ("refractive", 390.0, 430.0),
    ("mp", 430.0, 474.0),
    ("bp", 474.0, 517.0),
    ("flash", 517.0, 556.0),
    ("solubility", 556.0, 1e9),
)

#: Where an entry's id starts on an upright page.
ID_COLUMN = 58.0

_ID = re.compile(r"^[a-z]\d+[a-z]?$")
#: A cross-reference line of the synonym blocks printed on the page ("Alaninol, a264, a265"). Dropped whole: it is
#: not an entry, and read as one it lends its pointers to the entry above it.
_CROSS_REFERENCE = re.compile(r"^.+, [a-z]\d+[a-z]?(?:, ?[a-z]\d+[a-z]?)*$")
_SMALL = 5.5  # points: sub- and superscripts are set at 4.3
_FONT_SYMBOL = ("Greek", "MathematicalPi", "Symbol", "ProgressivePi")

#: Table 1.15 starts on this zero-based PDF page and ends on `LAST_PAGE`; Table 1.14 (the empirical formula
#: index that is the only place a formula is printed for EVERY entry) is the pages before it.
FIRST_PAGE = 75
LAST_PAGE = 342
INDEX_PAGES = range(50, 75)


@dataclass
class RawEntry:
    """One Table 1.15 entry as printed, before anything is decided about it."""

    entry_id: str
    pdf_page: int          # zero-based
    name_lines: list[str] = field(default_factory=list)
    weight: str = ""
    #: One string per printed line of the cell, with `^{}` for a superscript, `_{}` for a subscript, U+2212 for a
    #: minus glyph and U+FFFD for a glyph that could not be read.
    mp_lines: list[str] = field(default_factory=list)
    bp_lines: list[str] = field(default_factory=list)
    unreadable_glyphs: int = 0
    notes: list[str] = field(default_factory=list)


def classify_ink(bitmap: list[list[int]]) -> str:
    """What a rendered glyph is: `"minus"` for a bar, `"blank"` for no ink, else `"other"`.

    A minus is a single bar: the ink's bounding box is at least four times longer than it is thick in one
    direction (the page may be set sideways) and at most six pixels thick at 500 dpi. A plus, a plus-or-minus,
    a `<`, `>`, a tilde or a Greek letter is none of those and is `"other"` -- the caller refuses the cell.
    """
    rows = [i for i, r in enumerate(bitmap) if any(r)]
    if not rows:
        return "blank"
    cols = [j for j in range(len(bitmap[0])) if any(r[j] for r in bitmap)]
    height = rows[-1] - rows[0] + 1
    width = cols[-1] - cols[0] + 1
    long_side, short_side = max(height, width), min(height, width)
    if short_side <= 6 and long_side >= 4 * short_side:
        # A bar must be solid: a dashed or wavy line is not a minus sign.
        inked = sum(bitmap[i][j] for i in rows for j in cols)
        if inked >= 0.8 * height * width:
            return "minus"
    return "other"


def _glyph_kind(page, bbox, rotation_matrix) -> str:
    import pymupdf

    rect = pymupdf.Rect(bbox) * rotation_matrix
    pix = page.get_pixmap(clip=rect, dpi=500, colorspace=pymupdf.csGRAY)
    w, h, s = pix.width, pix.height, pix.samples
    return classify_ink([[1 if s[y * w + x] < 140 else 0 for x in range(w)] for y in range(h)])


def _is_symbol(font: str, text: str) -> bool:
    return any(k in font for k in _FONT_SYMBOL) or (len(text) == 1 and ord(text) < 32)


def _band(col: float) -> str | None:
    for name, lo, hi in BANDS:
        if lo <= col < hi:
            return name
    return None


def _page_spans(page):
    """Spans of a page as (col, row, size, font, text, bbox), in a frame where columns run left to right.

    Upright pages (`rotation` 0, lines direction (1, 0)) are read as they are. The 24 pages set sideways
    (lines direction (0, -1)) run upward, so a span's reading start is the BOTTOM of its box; the column is
    measured from the page's own id spans, which always start at `ID_COLUMN`.
    """
    spans = []
    sideways = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            d = tuple(round(v) for v in line["dir"])
            if _CROSS_REFERENCE.match("".join(s["text"] for s in line["spans"]).strip()):
                continue
            for s in line["spans"]:
                spans.append((d, s))
    out = []
    mode = None
    for d, s in spans:
        text = s["text"].strip()
        if _ID.match(text):
            mode = d
            if d == (0, -1):
                sideways.append(round(s["bbox"][3], 0))
    if mode == (1, 0):
        for d, s in spans:
            if d != (1, 0):
                continue
            x0, y0, _x1, y1 = s["bbox"]
            out.append((x0, y0, s["size"], s["font"], s["text"], s["bbox"]))
    elif mode == (0, -1) and sideways:
        origin = Counter(sideways).most_common(1)[0][0] + ID_COLUMN
        for d, s in spans:
            if d != (0, -1):
                continue
            x0, y0, _x1, y1 = s["bbox"]
            out.append((origin - y1, x0, s["size"], s["font"], s["text"], s["bbox"]))
    return out, mode


def _cell_lines(items, base_rows, page, rotation_matrix, counters) -> list[str]:
    """One string per printed line of a cell. `items` are the cell's spans (col, row, size, font, text, bbox)."""
    by_line: dict[float, list] = defaultdict(list)
    for item in items:
        col, row, size, font, text, bbox = item
        if size >= _SMALL:
            base = min(base_rows, key=lambda b: abs(b - row))
            by_line[base].append((col, "n", item))
        else:
            # A small span belongs to the nearest base line at or above it; a superscript sits at about +0.8
            # points from that line's top, a subscript at about +4.3.
            above = [b for b in base_rows if -0.6 <= row - b < 6.5]
            if not above:
                continue
            base = max(above)
            by_line[base].append((col, "sup" if row - base < 2.5 else "sub", item))
    lines = []
    for base in sorted(by_line):
        parts = []
        for col, kind, (c, r, size, font, text, bbox) in sorted(by_line[base], key=lambda t: t[0]):
            if _is_symbol(font, text):
                glyph = _glyph_kind(page, bbox, rotation_matrix)
                if glyph == "minus":
                    piece = "−"
                elif glyph == "blank":
                    continue
                else:
                    piece = "�"
                    counters["unreadable"] += 1
            else:
                piece = text
            parts.append({"n": piece, "sup": "^{" + piece + "}", "sub": "_{" + piece + "}"}[kind])
        line = "".join(parts).strip()
        # A line that is only an entry id is debris from a cross-reference block, never part of a cell.
        if line and not _ID.match(line):
            lines.append(line)
    return lines


def read_page(page, pdf_page: int) -> tuple[list[RawEntry], dict]:
    """The entries of one page, and what could not be read (`{"orientation": ..., "ids": n}` when skipped)."""
    spans, mode = _page_spans(page)
    if mode is None:
        return [], {"skipped": "no entry ids in a supported orientation", "orientation": page.rotation}
    weight_rows = [row for col, row, size, font, text, bbox in spans if _band(col) == "weight" and text.strip()]
    ids = sorted(
        ((row, text.strip()) for col, row, size, font, text, bbox in spans
         if _ID.match(text.strip()) and abs(col - ID_COLUMN) < 4.0
         and any(abs(row - w) < 1.5 for w in weight_rows)),
        key=lambda t: t[0],
    )
    if not ids:
        return [], {"skipped": "no entry ids in the id column"}
    starts = [row for row, _ in ids] + [1e9]
    entries: list[RawEntry] = []
    counters = {"unreadable": 0}
    for k, (row, entry_id) in enumerate(ids):
        lo, hi = row - 0.9, starts[k + 1] - 0.9
        mine = [s for s in spans if lo <= s[1] < hi]
        base_rows = sorted({round(s[1], 1) for s in mine if s[2] >= _SMALL and not _is_symbol(s[3], s[4])})
        # Merge base rows that are the same line (rounding of the same row).
        merged: list[float] = []
        for b in base_rows:
            if not merged or b - merged[-1] > 1.5:
                merged.append(b)
        by_band: dict[str, list] = defaultdict(list)
        for s in mine:
            band = _band(s[0])
            if band:
                by_band[band].append(s)
        entry = RawEntry(entry_id=entry_id, pdf_page=pdf_page)
        name_lines = _cell_lines(by_band["name"], merged, page, page.rotation_matrix, counters)
        entry.name_lines = name_lines
        entry.weight = " ".join(_cell_lines(by_band["weight"], merged, page, page.rotation_matrix, counters))
        entry.mp_lines = _cell_lines(by_band["mp"], merged, page, page.rotation_matrix, counters)
        entry.bp_lines = _cell_lines(by_band["bp"], merged, page, page.rotation_matrix, counters)
        entry.unreadable_glyphs = counters["unreadable"]
        counters["unreadable"] = 0
        entries.append(entry)
    return entries, {"orientation": "sideways" if mode == (0, -1) else "upright", "ids": len(ids)}


_FORMULA_LINE = re.compile(r"^([A-Z][A-Za-z0-9]*): (.*)$")
_ID_LIST = re.compile(r"[a-z]\d+[a-z]?")


def read_formula_index(doc) -> dict[str, list[str]]:
    """Table 1.14: formula -> entry ids, from the empirical formula index. An entry id appears under one formula."""
    index: dict[str, list[str]] = {}
    current: str | None = None
    for p in INDEX_PAGES:
        text = doc[p].get_text()
        if "Empirical Formula Index" not in text[:400]:
            continue
        for raw in text.splitlines():
            line = raw.strip()
            m = _FORMULA_LINE.match(line)
            if m and _ID_LIST.search(m.group(2)):
                current = m.group(1)
                index.setdefault(current, []).extend(_ID_LIST.findall(m.group(2)))
            elif current and line and re.fullmatch(r"(?:[a-z]\d+[a-z]?(?:,\s*)?)+", line):
                index[current].extend(_ID_LIST.findall(line))
            else:
                if not re.match(r"^[A-Z][A-Za-z0-9]*:", line):
                    current = current if re.fullmatch(r"[a-z\d, ]*", line) else None
    return index


def formula_by_entry(index: dict[str, list[str]]) -> tuple[dict[str, str], dict[str, list[str]]]:
    """entry id -> formula, and the ids listed under more than one formula (a defect of the index or the parse)."""
    seen: dict[str, list[str]] = defaultdict(list)
    for formula, ids in index.items():
        for entry_id in ids:
            seen[entry_id].append(formula)
    unique = {i: fs[0] for i, fs in seen.items() if len(set(fs)) == 1}
    clash = {i: fs for i, fs in seen.items() if len(set(fs)) > 1}
    return unique, clash


def read_all(path) -> tuple[list[RawEntry], dict[str, str], dict]:
    """Every Table 1.15 entry, the formula of each entry id, and a report of what the reader skipped."""
    import pymupdf

    doc = pymupdf.open(path)
    entries: list[RawEntry] = []
    report: dict = {"pages": 0, "skipped_pages": [], "sideways_pages": 0, "clashing_formula_ids": {}}
    for p in range(FIRST_PAGE, LAST_PAGE + 1):
        got, info = read_page(doc[p], p)
        report["pages"] += 1
        if "skipped" in info:
            report["skipped_pages"].append({"pdf_page": p, **info})
            continue
        if info["orientation"] == "sideways":
            report["sideways_pages"] += 1
        entries.extend(got)
    formulas, clash = formula_by_entry(read_formula_index(doc))
    report["clashing_formula_ids"] = clash
    return entries, formulas, report
