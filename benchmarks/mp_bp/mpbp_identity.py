"""Does a printed name, formula and molecular weight describe the structure the name resolved to?

**An identity consistency check, not proof of identity** (`PREREGISTRATION.md` section 7, step 3). The printed
formula, parsed into element counts, must equal the resolved structure's; the printed molecular weight must
agree within `max(0.5 x 10^-d, 2e-4 x MW)` where `d` is the number of decimals the table printed. Constitutional
isomers share both, so a name that resolves to more than one structure that passes is `ambiguous` and is NOT
accepted because the checksum passed.

Pure apart from RDKit: the name -> structure step (OPSIN, through `openchem.chem.naming_providers`) is done by
the caller and handed in as `resolved`, so every rule here is testable without Java.
"""

from __future__ import annotations

import itertools
import re
from collections import Counter
from dataclasses import dataclass

from rdkit import Chem
from rdkit.Chem import Descriptors

STATUSES = ("ok", "unresolved", "ambiguous", "mismatch", "unchecked")

#: Ligatures and invisible characters the PDFs' text layers carry.
SOFT_HYPHEN = chr(0xAD)  # a break the printer inserted inside a word
ZERO_WIDTH_SPACE = chr(0x200B)
_TRANSLATE = {"ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl", ZERO_WIDTH_SPACE: "", "’": "'", "′": "'"}

#: A leading optical sign: (+)-, (-)-, (+/-)-, (±)-. The sign is a symbol-font glyph in Lange; it is read (minus) or
#: unreadable (U+FFFD) and in either case says nothing about the connectivity, so it is removed. A lone Greek-letter
#: locant (alpha, beta) is NOT removable: it distinguishes isomers, and its glyph is U+FFFD outside parentheses.
_OPTICAL = re.compile(r"^\((?:[+−\-±�]|\+/[−\-]|[−\-]/\+)\)-?")
_TRAILING_DESCRIPTOR = re.compile(r"^(?P<name>.+?),\s*(?P<desc>\([^()]*\))-?$")


def clean(text: str) -> str:
    for old, new in _TRANSLATE.items():
        text = text.replace(old, new)
    return re.sub(r"\s+", " ", text).strip()


def _spell(lines: list[str]) -> list[str]:
    """Every way the printed lines can join into one name.

    A line ending in a hyphen is either a hyphenation break (`benzalde-` `hyde`) or a real locant hyphen
    (`2-` `aminoethane...`), and the page does not say which; both are produced and the formula and weight
    decide. A soft hyphen is always a break. Any other line end is a space.
    """
    lines = [clean(l) for l in lines if clean(l)]
    if not lines:
        return []
    options: list[list[str]] = []
    for left in lines[:-1]:
        if left.endswith(SOFT_HYPHEN):
            options.append([left[:-1]])
        elif left.endswith("-"):
            options.append([left[:-1], left])
        else:
            options.append([left + " "])
    spellings = ["".join(combo) + lines[-1] for combo in itertools.islice(itertools.product(*options), 8)]
    return list(dict.fromkeys(spellings))


def name_spellings(name_lines: list[str], extra: list[list[str]] | None = None) -> tuple[list[str], str]:
    """Candidate spellings for OPSIN, and a reason if the name cannot be offered at all.

    A name with an unreadable glyph outside an optical-sign group (a Greek locant, say) is not offered: dropping
    the letter would name a different isomer.
    """
    spellings: list[str] = []
    for lines in [name_lines] + list(extra or []):
        for joined in _spell(lines):
            current = joined
            m = _TRAILING_DESCRIPTOR.match(current)
            if m:
                current = f"{m.group('desc')}-{m.group('name')}"
            current = _OPTICAL.sub("", current).strip()
            if "�" in current or "()" in current:
                return [], "lost_character_in_name"
            current = ascii_name(current)
            if current is None:
                return [], "name_has_characters_opsin_cannot_be_sent"
            if current and current not in spellings:
                spellings.append(current)
    return spellings, ""


#: Greek letters the CRC prints as themselves. `py2opsin` writes its input as cp1252, so a letter outside it would
#: crash the batch -- and a character silently turned into another would name a different molecule. Spelled out
#: they are ordinary OPSIN input; anything else non-ASCII is not sent.
_GREEK = {
    "α": "alpha", "β": "beta", "γ": "gamma", "δ": "delta", "ε": "epsilon",
    "ω": "omega", "μ": "mu", "σ": "sigma", "π": "pi", "λ": "lambda",
    "Δ": "Delta", "–": "-", "—": "-", "−": "-",
}


def ascii_name(text: str) -> str | None:
    """`text` with Greek letters and dashes spelled out, or None if any other non-ASCII character remains."""
    for char, word in _GREEK.items():
        text = text.replace(char, word)
    return text if text.isascii() else None


_TOKEN = re.compile(r"([A-Z][a-z]?)(\d*)")


def parse_formula(text: str) -> Counter | None:
    """A plain Hill formula as element counts, or None for anything else (hydrate dots, charges, brackets)."""
    text = clean(text).replace(" ", "")
    if not text or not re.fullmatch(r"(?:[A-Z][a-z]?\d*)+", text):
        return None
    counts: Counter = Counter()
    for symbol, number in _TOKEN.findall(text):
        counts[symbol] += int(number) if number else 1
    return counts


def structure_formula(mol: Chem.Mol) -> Counter:
    counts: Counter = Counter()
    for atom in Chem.AddHs(mol).GetAtoms():
        counts[atom.GetSymbol()] += 1
    return counts


def weight_tolerance(printed: str) -> tuple[float, float] | None:
    """(weight, tolerance) from the weight as printed, or None if it is not a number."""
    printed = clean(printed)
    m = re.fullmatch(r"(\d+)(?:\.(\d+))?", printed)
    if not m:
        return None
    weight = float(printed)
    decimals = len(m.group(2) or "")
    return weight, max(0.5 * 10 ** (-decimals), 2e-4 * weight)


@dataclass(frozen=True)
class Identity:
    status: str          # one of STATUSES
    smiles: str = ""     # the accepted structure, when status == "ok"
    reason: str = ""
    spellings_resolved: int = 0
    spellings_passing: int = 0


def check(resolved: list[tuple[str, str | None]], printed_formula: str | None, printed_weight: str) -> Identity:
    """Decide identity from the spellings tried (`(spelling, smiles or None)` in the order tried).

    `printed_formula` None means the table printed none for this entry (Lange's formula index lacks about 9 %):
    that is `unchecked`, not a pass.
    """
    if printed_formula is None:
        return Identity("unchecked", reason="no printed formula for this entry")
    formula = parse_formula(printed_formula)
    if formula is None:
        return Identity("unchecked", reason=f"printed formula {printed_formula!r} is not a plain formula")
    weight = weight_tolerance(printed_weight)
    if weight is None:
        return Identity("unchecked", reason=f"printed weight {printed_weight!r} is not a number")
    if not any(smiles for _, smiles in resolved):
        return Identity("unresolved", reason="no spelling of the name resolved to a structure")
    passing: list[str] = []
    failures: list[str] = []
    for spelling, smiles in resolved:
        if not smiles:
            continue
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            failures.append(f"{spelling!r}: unreadable structure")
            continue
        if structure_formula(mol) != formula:
            failures.append(f"{spelling!r}: formula differs")
        elif abs(Descriptors.MolWt(mol) - weight[0]) > weight[1]:
            failures.append(f"{spelling!r}: weight differs")
        else:
            passing.append(smiles)
    resolved_count = sum(1 for _, s in resolved if s)
    if not passing:
        return Identity("mismatch", reason="; ".join(failures[:3]), spellings_resolved=resolved_count)
    blocks = {Chem.MolToInchiKey(Chem.MolFromSmiles(s)).split("-", 1)[0] for s in passing}
    if len(blocks) > 1:
        return Identity("ambiguous", reason="spellings give different structures that all fit the formula and weight",
                        spellings_resolved=resolved_count, spellings_passing=len(passing))
    return Identity("ok", smiles=passing[0], spellings_resolved=resolved_count, spellings_passing=len(passing))
