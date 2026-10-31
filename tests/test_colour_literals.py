"""Every hex colour in the application's own UI code is one of three things, and a new one has to say which.

`tests/test_theme.py` guards HOW a stylesheet is set. This guards WHAT colours the code carries: a literal
that is text on a panel must have a dark value (`theme._DARK_FOR_LIGHT`), or already read on a dark surface
(4.5:1, WCAG 1.4.3), or be listed below with the reason it is neither. The list is the written-down result
of the 2026-10-31 sweep (`docs/APPEARANCE_DESIGN.md`, "The colour sweep"): 26 literals that look low-contrast
on a dark surface and are not a defect, each with why. It only shrinks; an entry nothing uses any more fails.

It reads the source text, so it sees a literal wherever it is written: a stylesheet, a painter constant, a
palette, an HTML fragment. It does not know how a literal is USED, which is why the reasons name the route
(`theme.ink` at the draw site, a data colour, a surface) and the review that put it here.
"""

from __future__ import annotations

import re
from pathlib import Path

from openchem.ui import theme

_ROOT = Path(__file__).resolve().parent.parent
#: The dark field a line edit or a table paints on: the lighter of the two dark surfaces, so passing here passes on both.
_DARK_FIELD = "#2d2d2d"
_LITERAL = re.compile(r"#[0-9a-fA-F]{6}(?![0-9a-zA-Z])|#[0-9a-fA-F]{3}(?![0-9a-zA-Z])")

_SURFACE = "a dark surface the application paints, not ink on one"
_INK = "painted, and routed through `theme.ink` at the draw site, which lifts it only as far as it must"
_DATA = "a colour that carries the data (a series, a category, a contact kind), never recoloured to fit a theme"
_NMR = "an NMR trace palette entry, painted through `theme.ink` (`nmr_spectrum_widget`)"
_CELL = "ink chosen against the fill of the data cell it sits on, not against the window"

#: literal (lower case, six digits) -> why it is not a defect. Keep each reason specific.
REVIEWED_LOW_CONTRAST: dict[str, str] = {
    "#2d2d2d": _SURFACE + " (the field colour `theme` measures against)",
    "#1f1f1f": _SURFACE + " (the 2D editor page's background)",
    "#1e1e1e": _SURFACE + " (a web page's background before its first frame)",
    "#111111": _CELL,
    "#000000": _CELL + "; and the editor's own black ink value, which the dark rule turns light",
    "#4a4a4a": _INK + " (the atom diagram's ring label)",
    "#7a7a7a": _INK + " (the atom diagram's ring)",
    "#8a5a00": _INK + " (the periodic table's qualified half-life)",
    "#e8546b": _INK + " (a nucleus and a trajectory marker, filled)",
    "#888888": _INK + " (the checker's disabled state, the alignment grey, a tautomer swatch)",
    "#4c566a": _NMR,
    "#b2182b": _NMR,
    "#aa3377": _NMR,
    "#8b5a2b": _NMR,
    "#117733": _NMR,
    "#6b6b00": _NMR,
    "#cc6677": _NMR,
    "#5d4037": _DATA + " (metal coordination in the 3D viewer's residue layers)",
    "#7b1fa2": _DATA + " (salt bridges in the 3D viewer's residue layers)",
    "#d32f2f": _DATA + " (clashes; the diverging heat-map's low end)",
    "#1976d2": _DATA + " (hydrogen bonds; the diverging heat-map's high end)",
    "#00897b": _DATA + " (aromatic contacts in the 3D viewer's residue layers)",
    "#e65100": _DATA + " (the sequential heat-map's high end)",
    "#009e73": _DATA + " (Okabe-Ito green: the checker's clean state, a series colour); 4.0:1 on the field, 4.9:1 on the base",
    "#cc79a7": _DATA + " (Okabe-Ito reddish purple); 4.5:1 on the field",
    "#ef6c00": "a status chip's caution text on the panel base (5.4:1; 4.5:1 on the field); a hue kept apart from the severity orange",
}


def _normal(literal: str) -> str:
    return theme._normal(literal)


def _literals() -> dict[str, list[str]]:
    """Every literal in the UI's own Python (and the plugins'), with where it is written."""
    found: dict[str, list[str]] = {}
    for base in (_ROOT / "src" / "openchem" / "ui", _ROOT / "plugins"):
        for path in sorted(base.rglob("*.py")):
            for number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if line.lstrip().startswith("#"):
                    continue
                for literal in _LITERAL.findall(line):
                    found.setdefault(_normal(literal), []).append(f"{path.relative_to(_ROOT).as_posix()}:{number}")
    return found


def test_the_scan_finds_the_literals_it_guards():
    """An empty scan passes everything; the UI carries well over a hundred of these."""
    assert sum(len(places) for places in _literals().values()) >= 100


def test_every_colour_literal_is_mapped_readable_or_reviewed():
    mapped = theme.dark_values()
    unreviewed = {}
    for literal, places in _literals().items():
        if literal in mapped or literal in REVIEWED_LOW_CONTRAST:
            continue
        if theme.contrast(literal, _DARK_FIELD) >= theme.MIN_CONTRAST:
            continue
        unreviewed[literal] = places[:3]
    assert not unreviewed, (
        "a colour that does not read on a dark surface (below 4.5:1) and has no dark value, in:\n"
        + "\n".join(f"  {literal} {where}" for literal, where in unreviewed.items())
        + "\nGive it a dark value in `theme._DARK_FOR_LIGHT` (text), route it through `theme.ink` (painted), or add it to"
        " REVIEWED_LOW_CONTRAST in this file with the reason it is neither."
    )


def test_no_reviewed_entry_outlives_its_literal():
    """The list only shrinks: a literal nothing writes any more, or that has since been mapped, is removed here."""
    present = _literals()
    mapped = theme.dark_values()
    stale = [
        literal
        for literal in REVIEWED_LOW_CONTRAST
        if literal not in present or literal in mapped
    ]
    assert not stale, f"remove from REVIEWED_LOW_CONTRAST: {stale}"


def test_every_reason_is_a_sentence_and_the_keys_are_normal():
    for literal, reason in REVIEWED_LOW_CONTRAST.items():
        assert re.fullmatch(r"#[0-9a-f]{6}", literal), literal
        assert len(reason) > 25, f"{literal}: say why"
