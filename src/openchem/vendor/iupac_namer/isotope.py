"""
iupac_namer/isotope.py

Isotope-label perception and emission (Stage 6 R1-D).

IUPAC 2013 Blue Book — "Isotopically Modified Compounds" — defines two
equivalent notations for isotopic labels.  This module supports the IUPAC
bracketed-element style (the audit canonical):

    (²H)methanol              — one deuterium on methanol
    (²H₄)methanol             — four deuteria (perdeuteromethanol)
    (¹³C)methane              — single ¹³C
    (1-¹³C)ethan-1-ol         — locanted label at C1 of ethanol
    (1-¹⁵N)-1H-indole         — locanted on N1 of 1H-indole
    (1R)-(1-²H)ethan-1-ol     — combined stereo + isotope

Labels are collected per (locant, element, mass_number) and grouped so that
three deuteria on the same carbon produce a single bracket with count=3.

The module exposes two entry points:

1.  ``collect_isotope_labels(mol, atom_to_locant, fg_anchor_map=None)`` —
    walks the molecule and returns a tuple of :class:`IsotopeLabel` ready
    to be stashed on a :class:`SubstitutiveTree`.
2.  ``render_isotope_labels(labels)`` — formats a label tuple to the
    assembly-ready string ``"(²H)-"`` / ``"(²H₄)"`` / ``"(1-¹³C)-"`` etc.

The module does not touch the mol and does not mutate state — all
functions are pure.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Iterable, Mapping

from openchem.vendor.iupac_namer.types import IsotopeLabel, Locant


# ---------------------------------------------------------------------------
# Unicode superscript/subscript digit translation
# ---------------------------------------------------------------------------
#
# IUPAC isotope labels cite the mass number in superscript and the atom
# count in subscript.  Unicode has a dedicated code-point for every digit
# (U+2070, U+00B9, U+00B2, U+00B3, U+2074..U+2079 for superscript;
# U+2080..U+2089 for subscript) so we can emit "¹³C", "²H₄", "¹⁴C", "¹⁵N"
# directly.

_SUPERSCRIPT_DIGITS: dict[str, str] = {
    "0": "\u2070",
    "1": "\u00b9",
    "2": "\u00b2",
    "3": "\u00b3",
    "4": "\u2074",
    "5": "\u2075",
    "6": "\u2076",
    "7": "\u2077",
    "8": "\u2078",
    "9": "\u2079",
}

_SUBSCRIPT_DIGITS: dict[str, str] = {
    "0": "\u2080",
    "1": "\u2081",
    "2": "\u2082",
    "3": "\u2083",
    "4": "\u2084",
    "5": "\u2085",
    "6": "\u2086",
    "7": "\u2087",
    "8": "\u2088",
    "9": "\u2089",
}


def _superscript(n: int) -> str:
    """Return *n* rendered in Unicode superscript digits."""
    return "".join(_SUPERSCRIPT_DIGITS[d] for d in str(n))


def _subscript(n: int) -> str:
    """Return *n* rendered in Unicode subscript digits."""
    return "".join(_SUBSCRIPT_DIGITS[d] for d in str(n))


# ---------------------------------------------------------------------------
# collect_isotope_labels
# ---------------------------------------------------------------------------


def collect_isotope_labels(
    mol: object,
    atom_to_locant: Mapping[int, Locant],
    fg_anchor_map: Mapping[int, Locant] | None = None,
    unnumbered_ok: frozenset | None = None,
    suffix_ok: frozenset | None = None,
    alkoxy_ok: frozenset | None = None,
) -> tuple[IsotopeLabel, ...]:
    """Extract IUPAC isotope labels from *mol* for the given parent.

    For each atom with ``GetIsotope() > 0``:

    * Element ``"H"`` → the label targets the atom's single heavy neighbour,
      not the hydrogen itself (deuterium and tritium are *hydrogen isotopes
      on the parent position*).  If the neighbour lacks a locant (e.g. the
      H is attached to an off-parent atom), the label is dropped.
    * Any other element → the label targets the atom itself.  If the atom
      is not in ``atom_to_locant`` (not a parent backbone atom) the label
      is dropped.

    The optional ``fg_anchor_map`` extends the set of label-addressable
    atoms to include suffix-FG atoms that are structurally owned by the
    parent (e.g. the oxygen of an "-ol" alcohol, the nitrogens of an
    "-amine").  Each FG atom maps to the locant of its anchor so that
    ``(²H₄)methanol`` captures both the methyl-CD3 and the hydroxyl-OD
    deuteriums under locant 1.

    Labels are grouped by ``(locant, element, mass_number)`` and ``count``
    equals the number of isotope-bearing atoms in that bucket.

    ``unnumbered_ok`` names atoms of a parent whose RETAINED name numbers nothing there (`aniline`'s nitrogen, `phenol`'s oxygen, `benzonitrile`'s two
    atoms) and which are the only atom of their element among such atoms: a nuclide on one is cited with no locant, `(15N)aniline`, `(18O)phenol`
    (P-82.6.1.2: "Locants are omitted when there is only one atom of a given element"; the locant of the anchor carbon this used to give, `(1-18O)phenol`,
    is one OPSIN cannot read). ``suffix_ok`` names the heteroatoms of a systematic parent's suffix group that are the only atom of their element in it:
    their label is marked ``at_suffix`` so assembly can cite it before the suffix word. Hydrogen isotopes keep the heteroatom locant they always had.

    ``alkoxy_ok`` names the ester oxygen that the carve turned into the acid component's hydroxyl (D-197): its label is cited with the element as its locant,
    `(O-18O)acetate`, `prop-2-en-1-(O-18O)oate`, which OPSIN reads as the alkoxy oxygen where the carbonyl oxygen's `(18O)acetate` and `-1-(18O)oate` are the other one.

    The returned tuple is sorted by ``(locant-as-string, mass_number,
    element)`` for deterministic output.
    """
    # bucket: (locant, element, mass, at_suffix) -> count
    buckets: dict[tuple[Locant | None, str, int, bool], int] = defaultdict(int)

    for atom in mol.GetAtoms():                      # type: ignore[attr-defined]
        iso = atom.GetIsotope()
        if iso == 0:
            continue
        element = atom.GetSymbol()
        if element == "H":
            # Attach the label to the heavy neighbour (CAS/IUPAC convention:
            # D/T label sits on the *heavy* position, not the H index).
            neighbours = list(atom.GetNeighbors())
            if len(neighbours) != 1:
                # Unbound or multiply-bonded H (rare) — can't locate the
                # parent position, skip silently.
                continue
            target_idx = neighbours[0].GetIdx()
        else:
            target_idx = atom.GetIdx()

        # Primary lookup: parent-backbone locant.  Fall-back: suffix-FG
        # anchor locant (e.g. the O of methanol maps back to C1).
        locant = atom_to_locant.get(target_idx)
        if locant is None and fg_anchor_map is not None:
            locant = fg_anchor_map.get(target_idx)
            # Heteroatom-locant rule (P-82.2.3.1.1 / Blue Book isotope ref):
            # a D/T (or other isotope) sitting directly on a suffix-FG
            # heteroatom — the -OH oxygen, -SH sulfur, -NH nitrogen — is
            # cited with the italic element-symbol locant ("O-2H", "S-2H",
            # "N-2H"), NOT the numeric locant of the anchor carbon.  The
            # fg_anchor_map maps those heteroatoms onto their anchor's
            # numeric locant for backbone purposes; override that here when
            # the labelled position is itself the heteroatom (i.e. an
            # isotopic H whose sole heavy neighbour is the FG heteroatom).
            if locant is not None:
                target_atom = mol.GetAtomWithIdx(target_idx)  # type: ignore[attr-defined]
                target_sym = target_atom.GetSymbol()
                if (element == "H"
                        and target_sym != "C"
                        and target_idx not in atom_to_locant):
                    locant = Locant.hetero(target_sym)
        at_suffix = False
        if element != "H" and alkoxy_ok and target_idx in alkoxy_ok:
            locant = Locant.hetero(element)
            at_suffix = True
        elif element != "H" and unnumbered_ok and target_idx in unnumbered_ok:
            locant = None                       # a retained name numbers nothing here: the nuclide is cited bare
        elif element != "H" and suffix_ok and target_idx in suffix_ok and locant is not None:
            at_suffix = True
        # If the target atom has no addressable locant on this parent and the retained name does not own it,
        # drop the label rather than emitting a guess (the nuclide guard in `engine._check_nuclides_named` then refuses the name).
        elif locant is None:
            continue

        key = (locant, element, iso, at_suffix)
        buckets[key] += 1

    def _sort_key(item: tuple[tuple[Locant | None, str, int, bool], int]) -> tuple[str, int, str]:
        # ``sorted(buckets.items(), key=_sort_key)`` hands us a
        # ``((locant, element, mass), count)`` item — pull the key tuple out.
        loc, elem, mass, _suffix = item[0]
        loc_str = "" if loc is None else str(loc)
        # Pad numeric locants for natural order: "10" > "2"
        try:
            loc_sort = (0, int(loc_str)) if loc_str.isdigit() else (1, loc_str)
        except ValueError:
            loc_sort = (1, loc_str)
        return (f"{loc_sort[0]}:{loc_sort[1]!s:>10}", mass, elem)

    return tuple(
        IsotopeLabel(locant=loc, element=elem, mass_number=mass, count=count, at_suffix=at_suffix)
        for (loc, elem, mass, at_suffix), count in sorted(buckets.items(), key=_sort_key)
    )


# ---------------------------------------------------------------------------
# render_isotope_labels
# ---------------------------------------------------------------------------


def render_isotope_label(label: IsotopeLabel) -> str:
    """Render a single IsotopeLabel as its inner bracket text.

    Stage 16 R16-B switched the renderer from unicode super/subscripts
    (``²H``, ``¹³C``, ``²H₄``) to ASCII (``2H``, ``13C``, ``2H4``)
    because OPSIN's parser does not accept unicode digits in isotope
    labels — names like ``(1-¹³C)methane`` and ``(²H₄)methanol`` were
    OPSIN-unparseable, so isotopologue inputs (``[13CH4]``,
    ``[2H][2H][2H][2H]C``, etc.) couldn't round-trip even though the
    engine produced a structurally-correct name.

    For count > 1 with an explicit locant, OPSIN expects a VERBOSE
    locant list (``(1,1,1,1-2H4)methane``) rather than a count subscript
    on a single locant (``(1-2H4)methane`` — rejected by OPSIN).  The
    whole-molecule form ``(2H4)methane`` (no locants, count subscript
    on element) is accepted.  We therefore preserve the locant list
    when one is present and the count > 1.

    Examples:
        IsotopeLabel(None, "H", 2, 1)  -> "2H"
        IsotopeLabel(None, "H", 2, 4)  -> "2H4"
        IsotopeLabel("1",  "C", 13, 1) -> "1-13C"
        IsotopeLabel("2",  "C", 13, 1) -> "2-13C"
        IsotopeLabel(None, "N", 15, 1) -> "15N"
        IsotopeLabel("1",  "H", 2, 4)  -> "1,1,1,1-2H4"
    """
    mass = str(label.mass_number)
    count_str = str(label.count) if label.count > 1 else ""
    body = f"{mass}{label.element}{count_str}"
    if label.locant is None:
        return body
    if label.count == 1:
        return f"{label.locant}-{body}"
    # count > 1 with an explicit locant: OPSIN requires the locant
    # repeated for each isotope atom.  All atoms share the same locant
    # because perception bucketed them together — emit the locant list.
    locant_list = ",".join([str(label.locant)] * label.count)
    return f"{locant_list}-{body}"


def render_isotope_labels(labels: Iterable[IsotopeLabel]) -> str:
    """Render a sequence of IsotopeLabel as the IUPAC bracket prefix.

    Multiple labels are combined inside a single pair of parentheses,
    comma-separated.  Returns the empty string when no labels are
    supplied (so the caller can unconditionally concatenate).

    Examples:
        ()                                       -> ""
        (IsotopeLabel(None,"H",2,4),)            -> "(²H₄)"
        (IsotopeLabel("1","C",13,1),)            -> "(1-¹³C)"
        (IsotopeLabel("1","H",2,1),
         IsotopeLabel("2","C",13,1),)            -> "(1-²H,2-¹³C)"
    """
    labels = tuple(labels)
    if not labels:
        return ""
    body = ",".join(render_isotope_label(lbl) for lbl in labels)
    return f"({body})"


# ---------------------------------------------------------------------------
# isotopic_prefix
# ---------------------------------------------------------------------------


_LEADING_ISOTOPE_BRACKET = re.compile(r"^\(((?:[0-9A-Za-z,']+-)?\d+[A-Z][a-z]?\d*(?:,(?:[0-9A-Za-z,']+-)?\d+[A-Z][a-z]?\d*)*)\)")


def isotopic_prefix(prefix: str, atom: object) -> str:
    """A one-atom substituent prefix with its atom's nuclide: ``bromo`` on ``[81Br]`` is ``(81Br)bromo``.

    P-82.2.1 (BlueBookV2.pdf p. 853) cites the nuclide in enclosing marks before the name of the group it modifies: ``2-(35Cl)chloro-3-(2H3)methyl
    (1-2H1)pentane``, ``N-[7-(131I)iodo-9H-fluoren-2-yl]acetamide``. A prefix that is ONE atom has no locant to give ("Locants are omitted when
    there is only one atom of a given element", P-82.6.1.2, p. 860), so the label is the bare nuclide symbol and there is nothing to number.

    `collect_isotope_labels` cannot do this: it labels the atoms of the PARENT, and a halogen or any other one-atom prefix is never a parent atom, so
    its label was dropped there ("drop the label rather than emit a guess") and the name read back as the unlabelled compound. Returning the
    prefix unchanged for a natural-abundance atom keeps every existing name exactly as it was.

    The atom's hydrogens are part of what the prefix names (`hydroxy` is O-H, `amino` N-H2), so an isotopic hydrogen on it is cited here too, with the
    atom's symbol as its locant, the way the parent's `(O-2H)methanol` does it: `3-[(O-2H)hydroxy]propanoic acid`, which OPSIN reads and
    `3-[(2H)hydroxy]propanoic acid` it does not. A deuterium here used to be dropped, and the prefix read back as the plain hydroxy compound.
    """
    labels = []
    mass = atom.GetIsotope()  # type: ignore[attr-defined]
    if mass:
        labels.append(IsotopeLabel(locant=None, element=atom.GetSymbol(), mass_number=mass, count=1))  # type: ignore[attr-defined]
    hydrogens: dict[int, int] = {}
    for neighbour in atom.GetNeighbors():  # type: ignore[attr-defined]
        if neighbour.GetAtomicNum() == 1 and neighbour.GetIsotope():
            hydrogens[neighbour.GetIsotope()] = hydrogens.get(neighbour.GetIsotope(), 0) + 1
    for hydrogen_mass, count in sorted(hydrogens.items()):
        labels.append(IsotopeLabel(locant=Locant.hetero(atom.GetSymbol()), element="H", mass_number=hydrogen_mass, count=count))  # type: ignore[attr-defined]
    if not labels:
        return prefix
    own = render_isotope_labels(labels)
    # A prefix that already starts with a nuclide bracket (`(1-13C)methoxy`) takes this one into the SAME bracket, `(1-13C,18O)methoxy`: OPSIN reads that
    # and reads neither `(18O)(1-13C)methoxy` nor `(1-13C)(18O)methoxy`, and the book's own multi-label form is one bracket (`(1-2H,2-13C)`).
    leading = _LEADING_ISOTOPE_BRACKET.match(prefix)
    if leading is not None:
        return "(" + leading.group(1) + "," + own[1:-1] + ")" + prefix[leading.end():]
    return own + prefix


__all__ = [
    "collect_isotope_labels",
    "isotopic_prefix",
    "render_isotope_label",
    "render_isotope_labels",
]
