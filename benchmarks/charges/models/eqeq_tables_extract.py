"""TRIAGE 2.9: build EQeq's parameter table from the two sources its SI cites, POSITIONALLY.

    uvx --with pymupdf python eqeq_tables_extract.py <Moore1970.pdf> <andersen1999.pdf> <out.csv>

**This is a RECONSTRUCTION, not Wilmer's `ionizationData.dat`,** which is not in the ACS package.
Every row says where it came from, and check 2.9 carries that caveat into every result it produces.

- **Ionisation potentials:** Moore 1970 (NSRDS-NBS 34) Table I, which extracts in reading order as
  Z, element, then the successive potentials in eV. Integers are Z and decimals are potentials, so
  the parse needs no column geometry.
- **Electron affinities:** Andersen, Haugen & Hotop 1999 Table 3, "Summary of recommended atomic
  electron affinities". That one DOES need column geometry: its EA(eV) column sits at x = 310-360
  and its value is often split across two tokens ("1.232" + "712~15!" is 1.232712(15)).

Three OCR traps in these two scans, each of which silently lost or corrupted a row until it was
found, and each handled below:
- **Moore prints oxygen's symbol as the digit "0"**, so a symbol regex drops the row entirely. The
  atomic number is authoritative here: the element comes from Z, and the printed token is only
  checked against it.
- **This typesetting renders a minus sign as "2"** ("cm21" is cm^-1, "Pm2" is Pm^-). Nitrogen's
  affinity prints as "20.07", meaning -0.07 eV. A sign read literally would make nitrogen bind an
  electron it does not bind.
- **A value can be split across three fragments** ("0.754" + "203" + "75~3!" is 0.75420375), and a
  column can sit a little outside any fixed window.

**An element with no bound negative ion prints "<0" rather than a number** (magnesium and zinc among
them). Those rows are written with an empty EA and the printed text kept, so the decision about what
to do with them belongs to the check, not to this extractor.
"""

from __future__ import annotations

import csv
import io
import pathlib
import re
import sys

import pymupdf

#: Moore prints up to ten stages; the deepest charge centre check 2.9 uses is V(+4), needing I5.
MAX_STAGES = 10
ELEMENT = re.compile(r"^[A-Z][a-z]?$")
NUMBER = re.compile(r"^\d+\.\d+$")
INTEGER = re.compile(r"^\d{1,3}$")
#: Andersen's EA(eV) column, and the uncertainty suffix its OCR leaves attached ("0.675" "84~12!").
EA_WINDOW = (240.0, 430.0)
UNCERTAINTY = re.compile(r"[~(].*$")
#: The conversion Andersen's own Table 3 page prints: 1 eV = 8065.544 77(32) cm-1.
CM_PER_EV = 8065.54477


def symbol_for(z: int) -> str:
    """The element of an atomic number, from RDKit's own table rather than a hand-typed list."""
    from rdkit import Chem

    return Chem.GetPeriodicTable().GetElementSymbol(z)


def ionisation_potentials(path: pathlib.Path) -> dict[int, tuple[str, list[float]]]:
    """Moore Table I: {Z: (element, [I1, I2, ...])}, in the order the table prints them.

    Keyed on Z, with the symbol taken from the atomic number: Moore's scan prints oxygen as "0"."""
    document = pymupdf.open(path)
    tokens: list[str] = []
    for page in document:
        text = page.get_text()
        if "Ionization potentials" not in text:
            continue
        tokens.extend(token for token in text.split() if token)
    out: dict[int, tuple[str, list[float]]] = {}
    index = 0
    while index < len(tokens) - 1:
        token, following = tokens[index], tokens[index + 1]
        if INTEGER.match(token) and (ELEMENT.match(following) or following == "0"):
            z = int(token)
            if not 1 <= z <= 103:
                index += 1
                continue
            values: list[float] = []
            index += 2
            while index < len(tokens) and NUMBER.match(tokens[index]) and len(values) < MAX_STAGES:
                values.append(float(tokens[index]))
                index += 1
            if values and z not in out:
                out[z] = (symbol_for(z), values)
            continue
        index += 1
    return out


def _fragments(cells, low: float, high: float) -> list[tuple[float, float]]:
    """(x, value) for each number in the window, with split fragments rejoined and "2" read as minus.

    A value may arrive in three pieces ("0.754", "203", "75~3!"), and a leading "2" is this scan's
    minus sign. Both readings of a leading "2" are returned; the caller keeps whichever pairs up.
    """
    parts = [(x, UNCERTAINTY.sub("", w)) for x, w in cells if low <= x <= high]
    parts = [(x, w) for x, w in parts if re.match(r"^[\d.]+$", w)]
    joined, buffer, start, last = [], "", None, None
    for x, w in parts:
        if buffer and last is not None and (x - last) < 35 and not w.startswith("."):
            buffer += w
        else:
            if buffer:
                joined.append((start, buffer))
            buffer, start = w, x
        last = x
    if buffer:
        joined.append((start, buffer))
    out = []
    for x, text in joined:
        try:
            out.append((x, float(text)))
        except ValueError:
            continue
        if text.startswith("2") and len(text) > 1:  # "20.07" is -0.07, "2560" is -560, in this scan
            try:
                out.append((x, -float(text[1:])))
            except ValueError:
                pass
    return out


def electron_affinities(path: pathlib.Path) -> dict[int, tuple[str, float | None, str]]:
    """Andersen Table 3: {Z: (element, EA in eV or None, the printed text)}.

    **THE PARSE VALIDATES ITSELF**, because the table prints each affinity twice: once in cm-1 and
    once in eV, related by the conversion the same page states (1 eV = 8065.544 77 cm-1). A row is
    accepted only when the two agree to 1e-3 eV, which is what rejects an OCR fragment that landed
    in the wrong column and what decides whether a leading "2" was a minus sign.
    """
    document = pymupdf.open(path)
    out: dict[int, tuple[str, float | None, str]] = {}
    for page in document:
        if "recommended atomic electron af" not in page.get_text().replace("ﬁ", "fi"):
            continue
        rows: dict[int, list[tuple[float, str]]] = {}
        for x0, y0, x1, y1, word, *_ in page.get_text("words"):
            rows.setdefault(round((y0 + y1) / 2), []).append(((x0 + x1) / 2, word))
        for y in sorted(rows):
            cells = sorted(rows[y])
            words = [w for _, w in cells]
            if len(words) < 3 or not INTEGER.match(words[0]) or not ELEMENT.match(words[1]):
                continue
            z = int(words[0])
            if not 1 <= z <= 103 or z in out or symbol_for(z) != words[1]:
                continue
            if any(w.startswith(",") for x, w in cells if x > 240):  # the OCR of "<0"
                out[z] = (words[1], None, "<0")
                continue
            values = _fragments(cells, *EA_WINDOW)
            pairs = [(wavenumbers, electronvolts)
                     for xw, wavenumbers in values for xe, electronvolts in values
                     if xe > xw and abs(wavenumbers) > 100 and abs(electronvolts) < 10
                     and abs(wavenumbers / CM_PER_EV - electronvolts) < 1e-3]
            if pairs:
                wavenumbers, electronvolts = max(pairs, key=lambda pair: abs(pair[1]))
                out[z] = (words[1], electronvolts, f"{wavenumbers:g} cm-1 = {electronvolts:g} eV")
    return out


def main() -> None:
    potentials = ionisation_potentials(pathlib.Path(sys.argv[1]))
    affinities = electron_affinities(pathlib.Path(sys.argv[2]))
    rows = []
    for z in sorted(potentials):
        element, values = potentials[z]
        ea_element, ea, printed = affinities.get(z, ("", None, ""))
        if ea_element and ea_element != element:
            raise SystemExit(f"Z={z}: Moore says {element!r}, Andersen says {ea_element!r}")
        rows.append([z, element, "" if ea is None else f"{ea:.6f}", printed,
                     *[f"{value:g}" for value in values], *[""] * (MAX_STAGES - len(values))])
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["Z", "element", "electron_affinity_eV", "affinity_as_printed",
                     *[f"I{stage}" for stage in range(1, MAX_STAGES + 1)]])
    writer.writerows(rows)
    pathlib.Path(sys.argv[3]).write_text(
        "# EQeq's parameter table, RECONSTRUCTED for TRIAGE check 2.9 -- this is NOT Wilmer 2012's\n"
        "# ionizationData.dat, which is not in the ACS package. Ionisation potentials from Moore 1970\n"
        "# (NSRDS-NBS 34) Table I; electron affinities from Andersen, Haugen & Hotop 1999 Table 3.\n"
        "# An empty electron_affinity_eV means the source prints no bound value; the printed text is kept.\n"
        + buffer.getvalue(), encoding="utf-8", newline="\n")
    print(f"{len(rows)} elements; affinities for {sum(1 for r in rows if r[2])}")
    for z in (1, 6, 7, 8, 12, 23, 27, 28, 29, 30, 46):
        if z in potentials:
            element, values = potentials[z]
            ea = affinities.get(z, ("", None, ""))
            print(f"  Z={z:3} {element:2} EA {ea[2] or '-':>14} I {values[:5]}")


if __name__ == "__main__":
    main()
