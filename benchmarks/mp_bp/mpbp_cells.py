"""What a melting-point or boiling-point cell SAYS, as a closed grammar.

Pure text in, a typed reading out; no PDF, no RDKit. The extractors (`mpbp_lange.py`, `mpbp_crc.py`) turn a
cell into one string per printed line, with `^{...}` for a superscript, `_{...}` for a subscript, U+2212 for a
minus-sign glyph and U+FFFD for a glyph that could not be read. This module decides what that string means, and
**a cell that does not match a known pattern exactly is refused with the reason -- never guessed.** The cost of
that strictness is a smaller corpus; the cost of the alternative is a wrong temperature that looks like a
measurement, which is the failure the preregistration (`PREREGISTRATION.md` section 3 and section 7) exists to
prevent.

The grammar follows each table's own explanation of its notation, read before extraction and recorded as
Amendment 1 of the preregistration:

* **Lange 15th ed., Table 1.15** -- boiling point at atmospheric pressure (760 mmHg) unless a pressure is
  printed as a superscript (`82` over `15mm`); `subl 550` sublimes; melting point `250 d` is a melting point
  with decomposition, `d 250` decomposition at 250 and higher only.
* **CRC Handbook 97th ed., Physical Constants of Organic Compounds** -- bp is the normal boiling point at
  760 mmHg (101.325 kPa); a bp at reduced pressure is printed with a superscript pressure in mmHg; `sp` marks a
  sublimation point; `dec` or `exp` after a value means the temperature may not be a true boiling point; a bare
  `sub` says only that the solid sublimes appreciably; mp `dec` is decomposition at that temperature and `tp`
  a triple point (at its own pressure, not 101.325 kPa); a number in parentheses is a combined expanded
  uncertainty (about 95 %).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

MINUS = "−"
UNREADABLE = "�"
MMHG_TO_PA = 101_325.0 / 760.0

#: Why a cell could not be read. These are the `problem` values; an empty `problem` means it was read.
PROBLEMS = (
    "unreadable_glyph",   # a symbol that is not a minus sign (<, >, ~, a Greek letter, +/-)
    "multiple_lines",     # several printed lines that do not join into one cell (two forms, cross-references)
    "unrecognised",       # text outside the grammar
    "superscript",        # a superscript the grammar has no meaning for
    "bad_range",          # low above high
    "bad_pressure",       # a pressure that is not a number of mmHg
)

_NUM = r"[−-]?\d+(?:\.\d+)?"


@dataclass(frozen=True)
class Reading:
    """One cell, read.

    `event` is one of the `tools/validation_rows.py` `TRANSITION_TYPES` for a readable cell, and `"unreadable"`
    when `problem` is set. Temperatures are degrees Celsius exactly as printed (the conversion to kelvin is
    done where the row is built, and recorded there).
    """

    printed: str
    event: str
    value: float | None = None
    low: float | None = None
    high: float | None = None
    #: A printed pressure in mmHg; None when the cell prints none (the table's own convention then applies).
    pressure_mmhg: float | None = None
    pressure_printed: str = ""
    #: A combined expanded uncertainty printed in parentheses (CRC); recorded, never used to score.
    uncertainty: float | None = None
    #: The notation that decided the event, for the audit trail.
    notation: str = ""
    problem: str = ""

    @property
    def readable(self) -> bool:
        return not self.problem

    @property
    def has_temperature(self) -> bool:
        return self.value is not None or self.low is not None


def _num(text: str) -> float:
    return float(text.replace(MINUS, "-"))


def _refuse(printed: str, problem: str) -> Reading:
    return Reading(printed=printed, event="unreadable", problem=problem)


def _join(lines: list[str]) -> tuple[str, str]:
    """The cell as one string, and a problem if it cannot be one cell. A wrapped cell ("-23 to" / "-20") joins; several
    values (two polymorphs, a cross-reference line) are tried as one string too and refused by the grammar."""
    cleaned = [re.sub(r"\s+", " ", line).strip() for line in lines if line.strip()]
    return " ".join(cleaned), ("multiple_lines" if len(cleaned) > 1 else "")


def _temperature(text: str):
    """A bare temperature or an interval: (value, low, high), or None when `text` is neither."""
    # A number such as 02.9 has lost a digit (Lange's triethylborane prints -02.9 for -92.9): refuse it, never read it.
    if re.search(r"(?<![\d.])0\d", text):
        return None
    m = re.fullmatch(rf"({_NUM})", text)
    if m:
        return _num(m.group(1)), None, None
    m = re.fullmatch(rf"({_NUM}) ?(?:–|-|to) ?({_NUM})", text)
    if m:
        low, high = _num(m.group(1)), _num(m.group(2))
        return (low + high) / 2.0, low, high
    return None


def _build(printed, event, temp, notation, pressure=None, pressure_printed="", uncertainty=None) -> Reading:
    value, low, high = temp if temp else (None, None, None)
    if low is not None and low > high:
        return _refuse(printed, "bad_range")
    return Reading(
        printed=printed, event=event, value=value if low is None else None, low=low, high=high,
        pressure_mmhg=pressure, pressure_printed=pressure_printed, uncertainty=uncertainty, notation=notation,
    )


def _pressure(text: str):
    """`15mm` / `0.5mmHg` -> mmHg; anything else is not a pressure this grammar knows."""
    m = re.fullmatch(r"(\d+(?:\.\d+)?) ?(?:mm|mmHg|torr)", text.strip())
    return float(m.group(1)) if m else None


def read_lange(column: str, lines: list[str]) -> Reading | None:
    """A Lange `mp` or `bp` cell. None for an empty cell (the source is silent: there is nothing to refuse)."""
    if not any(line.strip() for line in lines):
        return None
    text, multi = _join(lines)
    printed = " / ".join(line.strip() for line in lines if line.strip())
    if UNREADABLE in text:
        return _refuse(printed, "unreadable_glyph")
    # Superscripts are pressures in a boiling-point cell; anywhere else they are not understood.
    sup = re.search(r"\^\{([^}]*)\}", text)
    pressure = None
    pressure_printed = ""
    if sup:
        if column != "bp":
            return _refuse(printed, "superscript")
        pressure = _pressure(sup.group(1))
        if pressure is None:
            return _refuse(printed, "bad_pressure")
        pressure_printed = sup.group(1)
        text = (text[:sup.start()] + text[sup.end():]).strip()
    if "_{" in text:
        return _refuse(printed, "unrecognised")

    def done(event, temp, notation):
        return _build(printed, event, temp, notation, pressure, pressure_printed)

    temp = _temperature(text)
    if temp:
        return done("melting" if column == "mp" else "boiling", temp, "plain")
    # decomposition and sublimation notation
    m = re.fullmatch(rf"({_NUM}) ?d(?:ec)?\.?", text) or re.fullmatch(rf"({_NUM}) sl d(?:ec)?\.?", text)
    if m:
        return done("melting_with_decomposition" if column == "mp" else "decomposition", _temperature(m.group(1)),
                    "value then d")
    m = re.fullmatch(rf"d(?:ec)?\.? ?({_NUM})", text)
    if m:
        return done("decomposition", _temperature(m.group(1)), "d then value")
    if text in {"d", "dec"}:
        return done("decomposition", None, "d alone")
    m = re.fullmatch(rf"subl\.? ?({_NUM})", text) or re.fullmatch(rf"({_NUM}) ?\(?subl\)?\.?", text)
    if m:
        return done("sublimation", _temperature(m.group(1)), "subl with value")
    if text in {"subl", "sublimes", "subl."}:
        return done("sublimation", None, "subl alone")
    if column == "bp" and text in {"explodes", "expl", "may explode"}:
        return done("decomposition", None, "explodes")
    return _refuse(printed, multi or "unrecognised")


def read_crc(column: str, lines: list[str]) -> Reading | None:
    """A CRC `mp` or `bp` cell. None for an empty cell.

    `250^{9}` is 250 at 9 mmHg (the table prints a reduced-pressure bp "with a superscript indicating the
    pressure in mmHg"); `277.5(0.8)` carries a combined expanded uncertainty; the suffixes are `dec`, `exp`,
    `sp` (a sublimation point), `sub` (the solid sublimes appreciably) and `tp` (a triple point).
    """
    if not any(line.strip() for line in lines):
        return None
    text, multi = _join(lines)
    printed = " / ".join(line.strip() for line in lines if line.strip())
    pressure = None
    pressure_printed = ""
    sup = re.search(r"\^\{([^}]*)\}", text)
    if sup:
        if column != "bp":
            return _refuse(printed, "superscript")
        if not re.fullmatch(r"\d+(?:\.\d+)?", sup.group(1).strip()):
            return _refuse(printed, "bad_pressure")
        pressure = float(sup.group(1))
        pressure_printed = sup.group(1).strip()
        text = (text[:sup.start()] + text[sup.end():]).strip()
    if "_{" in text:
        return _refuse(printed, "unrecognised")
    m = re.fullmatch(rf"({_NUM}(?: ?(?:–|-) ?{_NUM})?)(?:\((\d+(?:\.\d+)?)\))?(?: ?(dec|sp|exp|tp|sub))?", text)
    suffix_only = re.fullmatch(r"(dec|sp|exp|tp|sub)", text)
    if not m and not suffix_only:
        return _refuse(printed, multi or "unrecognised")
    suffix = m.group(3) if m else suffix_only.group(1)
    temp = _temperature(m.group(1)) if m else None
    if m and temp is None:
        return _refuse(printed, "unrecognised")
    uncertainty = float(m.group(2)) if m and m.group(2) else None
    if suffix is None:
        event, notation = ("melting" if column == "mp" else "boiling"), "plain"
    elif suffix in {"sp", "sub"}:
        event, notation = "sublimation", suffix
    elif suffix == "dec":
        event, notation = ("melting_with_decomposition" if column == "mp" else "decomposition"), "dec"
    elif suffix == "exp":
        event, notation = "decomposition", "exp"
    else:  # tp
        event, notation = "unknown", "tp"
    return _build(printed, event, temp, notation, pressure, pressure_printed, uncertainty)


def shape(text: str) -> str:
    """The cell with its numbers replaced, for tallying what the grammar did not recognise."""
    return re.sub(r"\d+(?:\.\d+)?", "#", text)
