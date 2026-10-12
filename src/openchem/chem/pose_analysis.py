from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Iterable

from rdkit import Chem

# Heavy-atom-to-heavy-atom distance heuristic for a "polar contact" --
# deliberately NOT a true donor-H...acceptor angle check: the receptor has
# no experimental hydrogen positions (they'd have to be added
# geometrically, same as receptor prep already does for docking itself),
# so an angle computed from placed-not-observed hydrogens would look more
# precise than it actually is. This is the same simplification common
# quick-analysis tools (e.g. PyMOL's default polar contacts) use -- a
# heavy-atom distance cutoff, no angle, symmetric on both sides (doesn't
# try to distinguish donor from acceptor).
HBOND_DISTANCE_CUTOFF = 3.5  # Angstrom
CLASH_TOLERANCE = 0.4  # Angstrom subtracted from summed van der Waals radii

# The remaining interaction cutoffs, in Angstrom. They live HERE rather
# than in `interaction_analysis` because that module already imports from
# this one -- the dependency runs one way and putting them the other way
# round is an import cycle. The physics is identical whether the two atoms
# are in one molecule or two, so both callers share these values.
SALT_BRIDGE_CUTOFF = 4.0  # charged-group centre separation
PI_STACKING_CUTOFF = 5.5  # aromatic ring centroid separation
CATION_PI_CUTOFF = 6.0  # cation to aromatic centroid
HYDROPHOBIC_CUTOFF = 4.5  # apolar carbon to apolar carbon
# A BOND TO A METAL HAS ITS OWN LENGTH, AND THE LENGTH DEPENDS ON THE METAL AND THE DONOR. This was one 2.8 A cutoff for
# every metal and every donor, which Harding accepted as the loosest bond (Ca...O up to 2.80 A, Mg...O up to 2.45)
# [source:harding1999] and which is right for none of them: a zinc to histidine nitrogen bond is 2.03 A, not 2.8, and a
# potassium to oxygen "bond" is 2.8 A and runs to about 3.6.
#
#: The distance, in angstrom, a bond from each metal to each kind of donor is expected to have, by DONOR ELEMENT. Where a
#: metal has several kinds of oxygen the entry is the longest of water, monodentate carboxylate and main-chain carbonyl, so
#: that a window built on it takes in all of them. Sources, which are the entries' only authority:
#:
#: * Zn, Fe, Co, Mn, Cu: Harding 2006 Table 4, the current table (it supersedes Harding 2001's Table 1) [source:harding2006];
#:   N is histidine and S is cysteine.
#: * Mg, Ca: Harding 2006 for oxygen. Their N and S entries (Mg 2.05 and 2.23, Ca 2.38 and 2.56) are Harding 2001's
#:   ESTIMATES, which he marks as such for want of data [source:harding2001]; 2006 has none.
#: * Na, K: Harding 2006 for oxygen (K 2.82 is the longest of 2.81, 2.82 and 2.74). N and S (Na 2.38 and 2.56, K 2.80 and
#:   2.98) are Harding 2002's estimates [source:harding2002]. The 2013 corrigendum corrects a sentence of that paper in which
#:   the sodium and potassium distances were interchanged; the tables were right [source:harding2013].
#: * Ni: Harding has no nickel. Zheng et al.'s CSD means (water 2.08, N 2.09, S 2.46, taking the larger where two values are
#:   given) [source:zheng2017]; they are survey means, not Harding's recommended targets.
#:
#: Fluorine has no table of its own: it takes the metal's oxygen entry. A fluoride ion (a fluorine bonded to neither carbon
#: nor boron) does so for every metal; a fluorine bonded to carbon or boron, donor key "CF", only for the metals in
#: `_ORGANIC_FLUORINE_DONOR_METALS` (see there).
METAL_DONOR_TARGETS: dict[str, dict[str, float]] = {
    "ZN": {"O": 2.09, "N": 2.03, "S": 2.31},
    "FE": {"O": 2.09, "N": 2.16, "S": 2.30},
    "CO": {"O": 2.09, "N": 2.14, "S": 2.25},
    "MN": {"O": 2.19, "N": 2.21, "S": 2.35},
    "CU": {"O": 2.13, "N": 2.02, "S": 2.15},
    "MG": {"O": 2.26, "N": 2.05, "S": 2.23},
    "CA": {"O": 2.39, "N": 2.38, "S": 2.56},
    "NA": {"O": 2.41, "N": 2.38, "S": 2.56},
    "K": {"O": 2.82, "N": 2.80, "S": 2.98},
    "NI": {"O": 2.08, "N": 2.09, "S": 2.46},
}

#: How far past the target a donor still counts as bonded, in angstrom. Harding's primary coordination sphere is the target
#: plus 0.5 [source:harding2001].
METAL_BOND_MARGIN = 0.5

#: The same, for sodium and potassium: the target plus 0.75, because their interactions are "predominantly electrostatic"
#: and a longer distance is not unusual [source:harding2002].
METAL_BOND_MARGIN_NA_K = 0.75

#: The same margin below the target, never below `METAL_DONOR_MIN_DISTANCE`. Harding says outright that for sodium and
#: potassium a distance 0.5 shorter than the target is not acceptable [source:harding2002]; for the other metals the same
#: 0.5 is applied by convention, and the floor of 1.8 (the shortest distance in his survey) is what actually binds.
METAL_BOND_MARGIN_BELOW = 0.5

#: Sodium and potassium contacts run on past the primary sphere (Harding's secondary sphere is the target plus 0.95,
#: [source:harding2002]; his CSD histograms have substantial numbers of K...O distances out to 3.8 A, and Na...O to 3.4).
#: A donor there is not reported as a bond, but it is a normal contact of an ion and not a steric clash, so it is left out of
#: the clash test. For the other metals, a donor beyond the primary sphere stays an ordinary contact.
METAL_CONTACT_MARGIN_NA_K = 0.95

#: Which donor entry a donor key reads: fluorine, whether a fluoride ion ("F") or one on carbon or boron ("CF"), reads oxygen's.
_DONOR_TABLE_ELEMENT = {"N": "N", "O": "O", "F": "O", "CF": "O", "S": "S"}

#: THE METALS A CARBON-BOUND (OR BORON-BOUND) FLUORINE COUNTS AS A DONOR TO. Organic fluorine is a real but weak donor to sodium,
#: potassium and calcium and is not shown to be one for any other metal. A fluoride ion is not covered by this: it is a donor
#: to every metal, and `metal_donor_symbol` tells the two apart by what the fluorine is bonded to.
#:
#: * Sodium, potassium, calcium: Plenio's survey of crystal structures finds attractive contacts to them, with sodium to
#:   fluorine at 2.30-2.67 A (the distribution of 79 contacts peaks at 2.50-2.70) and the acceptance limits he derives
#:   (Na 2.49-3.07, K 2.98-3.47, Ca 2.53-3.13 A) bracketing the oxygen windows used here (Na to 3.16, K to 3.57, Ca to
#:   2.89) [source:plenio1997]; Murray-Rust et al. find sodium to fluorine at 2.47 and potassium to fluorine at 2.80
#:   [source:murrayrust1983]. The interaction is weaker than the oxygen one (about 64 % of Li...O, by DFT) [source:plenio2004].
#: * Calcium is also seen directly in the PDB: one entry puts a fluorinated nucleotide's fluorine 2.57-2.83 A from three calciums
#:   that each already hold six oxygens (7ZLU); `benchmarks/fluorine_pdb_survey/`.
#: * Magnesium: none. Every Mg...F(C) distance measured is 3.2 A or more: 3.20-3.49 A in the crystal structures of magnesium
#:   fluoroaryls, computed from the coordinates of their supporting information [source:bakewell2016], and 3.29, 3.53 and 3.89 A
#:   in the 388 PDB entries with a fluorinated ligand and a magnesium (survey above); the window it would have had, the oxygen
#:   one, ends at 2.76 A. Plenio mentions magnesium only as a chelate proposed for a reaction [source:plenio1997].
#: * Zinc, iron, cobalt, manganese, copper, nickel: none. Plenio finds convincing evidence in the first transition series
#:   only for titanium and vanadium in unusual organometallic complexes; the cobalt contact (2.65 A) is intramolecular and
#:   its authors attributed it to torsion, the zinc contacts (2.53-2.73 A) are all in crowded aryl-CF3 or C6F5 organometallics,
#:   and there is nothing for iron, manganese, copper or nickel [source:plenio1997]. The only transition-metal fluoroalkane
#:   carboxylates found in 1983 were copper(II) fluoroacetates, whose sixth site quinoline or urea fills [source:murrayrust1983].
#:   The PDB survey agrees: no fluorine is nearer than 3.48 A to a zinc (559 entries), 3.35 to an iron or 3.69 to a manganese; the
#:   exception is copper, six pairs in two tyrosinase-inhibitor entries at 1.88-2.61 A, but those ligands fit their density poorly
#:   (real-space correlation 0.69-0.79 against 0.99 for the copper ions), the authors describe a substrate-mimic placement and not
#:   coordination [source:ferro2018] [source:ielo2019], and the measured copper(II)...F(CF3) contacts are 2.71-3.11 A
#:   [source:maverick2002], 0.8 A longer than that: copper stays out.
#:   A fluorine on carbon near one of these metals is therefore an ordinary contact, judged by the clash test, and not a bond.
_ORGANIC_FLUORINE_DONOR_METALS = frozenset({"NA", "K", "CA"})


def _metal_donor_target(metal: str, donor: str) -> float | None:
    targets = METAL_DONOR_TARGETS.get(metal.upper())
    element = _DONOR_TABLE_ELEMENT.get(donor.upper())
    if donor.upper() == "CF" and metal.upper() not in _ORGANIC_FLUORINE_DONOR_METALS:
        return None
    return None if targets is None or element is None else targets[element]


def metal_bond_window(metal: str, donor: str) -> tuple[float, float] | None:
    """`(shortest, longest)` distance, in angstrom, at which `donor` (N, O, F, CF or S; see `metal_donor_symbol`) is bonded to
    `metal`; None if either is not one this table covers, or for "CF" and a metal outside `_ORGANIC_FLUORINE_DONOR_METALS`. The longest is the target plus 0.5 (0.75 for sodium and potassium), the shortest the
    target less 0.5 but never below `METAL_DONOR_MIN_DISTANCE`."""
    target = _metal_donor_target(metal, donor)
    if target is None:
        return None
    above = METAL_BOND_MARGIN_NA_K if metal.upper() in _IONIC_METALS else METAL_BOND_MARGIN
    return (max(METAL_DONOR_MIN_DISTANCE, target - METAL_BOND_MARGIN_BELOW), target + above)


def metal_donor_symbol(atom: Chem.Atom) -> str:
    """The donor key `metal_bond_window` reads for `atom`: its element, except "CF" for a fluorine bonded to carbon or boron
    (`is_weak_acceptor_fluorine`), which is a donor to far fewer metals than a fluoride ion is."""
    return "CF" if is_weak_acceptor_fluorine(atom) else atom.GetSymbol().upper()


def is_metal_bond(metal: str, donor: str, distance: float) -> bool:
    """Whether a `donor` at `distance` from `metal` is bonded to it: inside `metal_bond_window`."""
    window = metal_bond_window(metal, donor)
    return window is not None and window[0] <= distance <= window[1]


def is_metal_contact(metal: str, donor: str, distance: float) -> bool:
    """Whether the pair is a bond, or (sodium and potassium only) a normal contact of the ion beyond the primary sphere;
    either way it is not a steric clash."""
    window = metal_bond_window(metal, donor)
    if window is None:
        return False
    longest = window[1]
    if metal.upper() in _IONIC_METALS:
        longest = _metal_donor_target(metal, donor) + METAL_CONTACT_MARGIN_NA_K
    return window[0] <= distance <= longest


#: The two metals whose interactions are mostly electrostatic and so get the wider margins.
_IONIC_METALS = frozenset({"NA", "K"})

_METALS = {"ZN", "MG", "CA", "FE", "MN", "CU", "NA", "K", "CO", "NI"}
_POLAR_ELEMENTS = {"N", "O", "F"}


#: The elements a fluorine can be bonded to and still hardly ever accept a hydrogen bond: carbon, and boron.
_WEAK_ACCEPTOR_FLUORINE_PARTNERS = frozenset({"C", "B"})


def is_weak_acceptor_fluorine(atom: Chem.Atom) -> bool:
    """Whether `atom` is a fluorine bonded to carbon (C-F) or boron (B-F), as opposed to a fluoride ion or a fluorine on
    any other element. THESE HARDLY EVER ACCEPT A HYDROGEN BOND: Dunitz and Taylor found 37 of 5,947 C-F bonds (0.6%) in a
    short contact with an O-H or N-H, against 42% of carbonyl oxygens and 32% of aromatic nitrogens, and only two of the 37
    unequivocal, one of them a fluorine with anionic character [source:dunitz1997]; Murray-Rust et al. found C-F...O
    contacts with a minimum near 2.85 A and no preferred direction, which they read as van der Waals contact
    [source:murrayrust1983]; and even ammonium tetrafluoroborate, the obvious candidate for B-F...H-N bonding, shows no short
    N-H...F contact [source:dunitz2004]. Fluorine on phosphorus, sulfur or silicon, and the fluoride ion, are not covered
    by any of that and keep counting. The fluorine is still a polar atom everywhere else (a hydrophobic carbon's neighbour,
    a metal donor to the hard cations)."""
    return atom.GetSymbol().upper() == "F" and any(
        n.GetSymbol().upper() in _WEAK_ACCEPTOR_FLUORINE_PARTNERS for n in atom.GetNeighbors()
    )

# A BOND TO A METAL IS NOT A CONTACT. Everything below is what the clash test
# needs to know to leave one out, and `_contact_interactions` reports the same
# pairs as `metal_coordination`, so the two cannot disagree about which atoms
# are bonded.
#
#: Which atoms can donate to a metal. The detector has always taken N, O, F
#: and S; the clash test takes exactly the same set (`_METAL_DONOR_ELEMENTS`),
#: because a pair reported as coordination and also as a clash is the defect.
#: Whether a given metal and donor are actually bonded is `metal_bond_window`'s
#: question (a fluorine on carbon or boron is a donor only to `_ORGANIC_FLUORINE_DONOR_METALS`).
_METAL_DONOR_ELEMENTS = _POLAR_ELEMENTS | {"S"}

#: The shortest distance still treated as a bond. Below it the two atoms
#: overlap and the pair stays in the clash test. 1.8 A sits just under the
#: shortest metal--N/O/S distance in Harding's CSD survey of Ca, Mg, Mn, Fe, Cu
#: and Zn (1.81 A, Cu--phenolate outliers; Mn 1.83 and Fe 1.84 are the shortest
#: regular ones) [source:harding1999]. One value for all donors is deliberately
#: loose for sulfur, whose own shortest bond there is 2.18 A (Fe--thiolate).
METAL_DONOR_MIN_DISTANCE = 1.8  # Angstrom

#: How far from a coordinating donor a ligand atom still counts as part of the
#: bond's own geometry rather than a contact with the metal. 2 means the
#: donor's neighbours (M--D--X, about 3.0-3.4 A away, fixed by the 126-131
#: degree M--N--C angle [source:harding1999] Table 6) and their neighbours,
#: which is where a six-membered chelate ring puts its far atom. It is the
#: convention `interaction_analysis.MIN_SEPARATION` already uses for clashes
#: inside one molecule (bond-path separation < 4, with the metal bonded to the
#: donor).
_BONDED_NEIGHBOUR_DEPTH = 2

# Which residues receptor preparation removes. They live HERE, with the
# cutoffs, for the same reason: `docking_providers` strips them before
# handing a receptor to Vina, and this module must reach the SAME verdict
# when deciding what a pose is allowed to interact with. Two copies of
# these sets would drift, and the symptom would be silent -- an
# interaction reported against an atom the docking never saw.
WATER_RESIDUE_NAMES = {"HOH", "WAT", "H2O", "DOD", "TIP", "TIP3", "TIP4"}

# Standard amino acids plus common alternate-protonation-state names some
# tools/force fields emit (histidine tautomers, cysteine states, etc.) --
# anything else non-water is a "cofactor" candidate. Deliberately
# protein-only (no nucleotide residues): a docking receptor prepared
# through this pipeline is a protein target.
STANDARD_RECEPTOR_RESIDUES = {
    "ALA", "ARG", "ASN", "ASP", "CYS", "GLN", "GLU", "GLY", "HIS", "ILE",
    "LEU", "LYS", "MET", "PHE", "PRO", "SER", "THR", "TRP", "TYR", "VAL",
    "HID", "HIE", "HIP", "HSD", "HSE", "HSP", "CYX", "CYM", "ASH", "GLH", "LYN",
}


def filter_pdb_altlocs(pdb_text: str) -> str:
    """Drop every alternate location except the first (blank or 'A').

    Confirmed live that Open Babel's PDB reader does NOT dedupe these: a
    two-altloc atom comes back as two full atoms at two positions, not one
    occupancy-weighted atom. Column 17 (0-indexed 16) is the format's
    fixed-width altLoc field; shorter lines and non-coordinate records
    pass through untouched.

    Lives here, next to the residue tables, for the reason they do -- both
    receptor preparation and pose analysis must reach the same view of the
    structure. 8ZYO is what this looks like when they do not: its
    astemizole is one 34-atom molecule modelled in two conformations, and
    an unfiltered read reports 68 atoms spread over both, which then
    doubles the size of any box or contact set derived from it.
    """
    kept = []
    for line in pdb_text.splitlines(keepends=True):
        if line.startswith(("ATOM", "HETATM")) and len(line) > 16 and line[16] not in (" ", "A"):
            continue
        kept.append(line)
    return "".join(kept)


#: An alternate location that IS the one to keep -- unset, unknown, or the
#: first labelled one. Shared by both format filters so "which copy wins"
#: is decided once.
_PRIMARY_ALTLOCS = frozenset({"", " ", ".", "?", "A"})


#: What separates two CIF values. The line terminators are in here for
#: the reason `_cif_token_spans` gives: a value can never contain one, and
#: leaving them out silently glues `\n` onto a row's last token.
_CIF_WHITESPACE = " \t\r\n"


def _cif_token_spans(line: str) -> list[tuple[int, int]]:
    """`(start, end)` of each value in one mmCIF data row.

    The tokeniser proper, which `_cif_tokens` reads through. Split out
    because `normalise_mmcif_element_symbols` has to REWRITE one value and
    leave every other byte of the row alone, and it can only do that if it
    knows where the value sits. A second tokeniser written for that would
    be the off-by-one this one exists to prevent.

    For a quoted value the span covers the CONTENT, not the quotes, so
    `tokens[i] == line[start:end]` holds either way.

    THE LINE TERMINATOR IS A DELIMITER, and that is not cosmetic. A CIF
    value cannot contain a raw newline, but a tokeniser that only split on
    space and tab folded one into the LAST token of a row -- so
    `type_symbol` in the final column read as `"NA\\n"` and matched no
    element. Every existing caller passes a line already stripped (or from
    `splitlines()`), which is why nothing had noticed; the normaliser must
    keep the terminator, because its spans index into the row it returns.
    A CRLF file reaches here intact too, since `structure_io` decodes bytes
    itself rather than going through universal newlines.
    """
    spans: list[tuple[int, int]] = []
    index = 0
    length = len(line)
    while index < length:
        while index < length and line[index] in _CIF_WHITESPACE:
            index += 1
        if index >= length:
            break
        quote = line[index] if line[index] in "'\"" else ""
        if quote:
            index += 1
            start = index
            # A quote closes only when followed by whitespace or end of
            # line -- that is what lets an apostrophe live inside a value.
            while index < length and not (
                line[index] == quote
                and (index + 1 >= length or line[index + 1] in _CIF_WHITESPACE)
            ):
                index += 1
            spans.append((start, index))
            index += 1
        else:
            start = index
            while index < length and line[index] not in _CIF_WHITESPACE:
                index += 1
            spans.append((start, index))
    return spans


def _cif_tokens(line: str) -> list[str]:
    """Split one mmCIF data row into values.

    Not a plain `.split()`: CIF values may be quoted, and nucleic-acid
    atom names genuinely need it -- `O5'` is written `"O5'"`. Splitting on
    whitespace alone would shift every later column by one on those rows,
    which is exactly the kind of silent off-by-one that puts an altloc
    check on the wrong field.
    """
    return [line[start:end] for start, end in _cif_token_spans(line)]


def filter_mmcif_altlocs(mmcif_text: str) -> str:
    """Drop every alternate location except the first, for mmCIF.

    The PDB filter is a fixed-column slice and cannot be reused here --
    mmCIF has no columns, only a `loop_` whose tag order the file itself
    declares. So the `_atom_site.label_alt_id` position is READ from that
    header rather than assumed, because the order is a convention and not
    a rule.

    Without this, an mmCIF receptor reached Vina with duplicated atoms:
    7B6W's ligand is one 59-atom molecule refined in two half-occupancy
    conformations, and Open Babel returns all 118. Docking against a
    receptor whose atoms appear twice at slightly different positions is
    wrong in a way nothing reports -- the steric term is simply counted
    twice wherever a side chain was modelled in two states.

    Anything that is not the atom_site loop passes through untouched, and
    a file whose loop declares no `label_alt_id` is returned unchanged.
    """
    lines = mmcif_text.splitlines(keepends=True)
    output: list[str] = []
    index = 0
    total = len(lines)

    while index < total:
        line = lines[index]
        if line.strip() != "loop_":
            output.append(line)
            index += 1
            continue

        # Collect this loop's tag lines to learn its shape.
        output.append(line)
        index += 1
        tags: list[str] = []
        while index < total and lines[index].lstrip().startswith("_"):
            tags.append(lines[index].strip())
            output.append(lines[index])
            index += 1

        if not all(tag.startswith("_atom_site.") for tag in tags) or not tags:
            continue  # some other loop; its rows are copied by the outer pass
        try:
            altloc_column = tags.index("_atom_site.label_alt_id")
        except ValueError:
            continue  # no alternate locations declared, nothing to filter

        while index < total:
            row = lines[index]
            stripped = row.strip()
            # The loop's rows end at a comment, another loop, a new
            # category, or a new data block.
            if not stripped or stripped.startswith(("#", "loop_", "_", "data_")):
                break
            tokens = _cif_tokens(stripped)
            if len(tokens) > altloc_column and tokens[altloc_column] not in _PRIMARY_ALTLOCS:
                index += 1
                continue
            output.append(row)
            index += 1

    return "".join(output)


def filter_altlocs(structure_text: str, source_format: str) -> str:
    """Drop alternate locations, whichever format the structure is in.

    One entry point so receptor preparation and pose analysis cannot end
    up handling different formats differently -- which is precisely how
    the PDB-only version came to be applied on one path and not the other.
    """
    if source_format == "pdb":
        return filter_pdb_altlocs(structure_text)
    if source_format in ("mmcif", "cif"):
        return filter_mmcif_altlocs(structure_text)
    return structure_text


@lru_cache(maxsize=1)
def _symbols_by_uppercase() -> dict[str, str]:
    """Every element symbol, indexed by its uppercase form.

    Built from `element_reference` rather than written out here, so it
    cannot fall behind the table the rest of the app answers element
    questions from -- and so a symbol this does not know is a symbol the
    app does not know, rather than a second opinion. Imported inside the
    function because that module reads a JSON data file, which is not
    work this module should do just to be imported.
    """
    from openchem.chem.element_reference import all_symbols

    return {symbol.upper(): symbol for symbol in all_symbols()}


def normalise_mmcif_element_symbols(mmcif_text: str) -> str:
    """Case-normalise `_atom_site.type_symbol`, for Open Babel's benefit.

    **Open Babel's mmCIF reader looks up `type_symbol` case-sensitively,
    and the PDB archive writes two-letter symbols in UPPERCASE.** So every
    such atom arrives with atomic number 0 -- element unknown -- while the
    same deposit in PDB format reads correctly. Measured on Open Babel
    3.1.0, one atom per minimal mmCIF, varying nothing but the symbol:

        CL CA NA ZN FE MG MN CU BR SE NI CO   ->  0     (12 of 12)
        Cl Ca Na Zn Fe Mg Mn Cu Br Se Ni Co   ->  correct
        C N O S P F                           ->  correct either way

    It is not eight elements or twelve: it is EVERY two-letter symbol, and
    one-letter symbols are unaffected because case cannot differ.

    THIS IS NOT REWRITING THE DEPOSIT. The uppercase file is correct
    mmCIF -- `type_symbol` is case-insensitive in the format, and Mol*
    reads it perfectly. Only the copy handed to Open Babel is normalised,
    which is why this lives here beside `filter_altlocs` and NOT in
    `chem/structure_io.py`: that text becomes
    `MacromoleculeModel.structure_text`, which is what the viewer renders
    and what a saved project stores, and altering a correct deposit on
    disk to work around one consumer's lookup is a different and worse
    change. There is no Open Babel read option for this -- the mmCIF
    format offers only `s`, `p`, `b` and `w`, none about element typing.

    CONSERVATIVE BY CONSTRUCTION: a value is rewritten only when it is
    **not** an element symbol as written and **is** one after
    normalisation. So `C`, `W` and `Cl` pass through untouched, and so do
    `?`, `.` and anything unrecognised -- a symbol this cannot name is
    left for Open Babel to reject rather than guessed at.

    The substitution is length-preserving (case never changes a string's
    length), so the row's column alignment survives byte for byte.
    """
    lookup = _symbols_by_uppercase()
    lines = mmcif_text.splitlines(keepends=True)
    output: list[str] = []
    index = 0
    total = len(lines)

    while index < total:
        line = lines[index]
        if line.strip() != "loop_":
            output.append(line)
            index += 1
            continue

        output.append(line)
        index += 1
        tags: list[str] = []
        while index < total and lines[index].lstrip().startswith("_"):
            tags.append(lines[index].strip())
            output.append(lines[index])
            index += 1

        try:
            # The EXACT tag is what identifies the loop -- there is no
            # separate "is this atom_site" test, deliberately. mmCIF has
            # other categories with a `type_symbol` column
            # (`_chem_comp_atom.type_symbol` is the component dictionary's),
            # and a suffix match would rewrite those too. Coordinates are
            # the only thing Open Babel types atoms from, so they are the
            # only thing this touches.
            symbol_column = tags.index("_atom_site.type_symbol")
        except ValueError:
            continue  # some other loop, or no element column in this one

        while index < total:
            row = lines[index]
            stripped = row.strip()
            if not stripped or stripped.startswith(("#", "loop_", "_", "data_")):
                break
            spans = _cif_token_spans(row)
            if len(spans) > symbol_column:
                start, end = spans[symbol_column]
                written = row[start:end]
                canonical = lookup.get(written.upper())
                if canonical is not None and canonical != written:
                    row = row[:start] + canonical + row[end:]
            output.append(row)
            index += 1

    return "".join(output)


def normalise_element_symbols(structure_text: str, source_format: str) -> str:
    """Make element symbols legible to Open Babel, whichever format.

    One entry point, for the reason `filter_altlocs` has one: receptor
    preparation and pose analysis must reach the same view of a structure,
    and a normalisation applied on one path only is the divergence this
    module keeps being bitten by. PDB needs nothing -- its reader already
    matches case-insensitively, measured on the same twelve symbols.
    """
    if source_format in ("mmcif", "cif"):
        return normalise_mmcif_element_symbols(structure_text)
    return structure_text


def is_symmetry_generated(residue) -> bool:
    """Whether this atom is a crystallographic copy Open Babel invented.

    Open Babel expands the unit cell when it cannot recognise a space
    group -- it says so ("Unknown space group error... Converting to P 1
    cell using available symmetry transformations") and then returns the
    symmetry mates as real atoms. Measured against the deposited files:
    7M93 came back at 2.00x its own `_atom_site` row count and 6WGT at
    8.00x, and the receptor actually handed to Vina for 6WGT held 73,707
    atoms for an 8,100-atom deposit. That is not a crash, it is a
    silently wrong receptor -- eight overlapping copies of the protein.

    The generated copies carry NO residue record, which is what makes
    them identifiable, and the arithmetic confirms the identification is
    exact rather than approximate: dropping them leaves 5,812 atoms for
    7M93 and 8,100 for 6WGT, each equal to that file's own row count to
    the atom. Structures Open Babel handles correctly have none, so this
    costs them nothing -- 8ZYO triggers the same warning and has zero.

    The check is `residue.OBResidue is None`, NOT `residue is None`,
    because pybel wraps the null pointer in a perfectly truthy `Residue`
    object. That is why the existing `residue is not None` guard let
    these through and `residue.name` then raised `AttributeError:
    'NoneType' object has no attribute 'GetName'`, which is how this was
    found at all.

    There is no Open Babel read option to prevent the expansion -- its
    mmCIF reader offers only `s`, `p`, `b` and `w` -- and stripping the
    `_cell` records from the text to stop it SEGFAULTS the parser.
    Filtering after the fact is what is left, and it is exact.

    ## WHY IT CANNOT RECOGNISE THE SPACE GROUP: ITS DATABASE IS MISSING

    Established 2026-08-29, and the sentence above stood for months
    without it -- "cannot recognise a space group" was the observation,
    never the cause. **The cause is that `space-groups.txt` is
    unreachable on Windows.** `openbabel/__init__.py` sets
    `BABEL_DATADIR` to `share/openbabel/<version>/`, which in the Windows
    wheel holds one file (`splash.png`); the real tables are in
    `bin/data/`. The Linux wheel puts them where the variable points, so
    **this is a Windows-wheel packaging defect and not a platform
    difference in Open Babel.**

    Measured on a fixture with a REAL group, `P 21 21 21` and its four
    operations, four deposited atoms:

        BABEL_DATADIR as the wheel sets it   16 atoms, 12 invented
        BABEL_DATADIR at bin/data             4 atoms,  0 invented

    Which is this whole function's subject: with the database present
    Open Babel resolves the group and duplicates nothing. The recorded
    ratios follow from the operation counts -- 6WGT's 8.00x is a group
    with eight, 7M93's 2.00x one with two.

    **THE FILTER IS KEPT ANYWAY, AND NOT ONLY OUT OF CAUTION.** The
    receptor this application hands Vina is byte-identical either way --
    measured through `_convert_receptor_to_pdbqt`, same SHA-256, because
    every invented atom is dropped here. So repairing the variable would
    change what Open Babel does on the shipping platform and change
    nothing observable, while turning this exact, measured filter into a
    no-op. It also has to survive a wheel that fixes itself, and a
    deposit whose group genuinely is unknown.

    **AND THE OBVIOUS REPAIR CANNOT SHIP:** pointing `BABEL_DATADIR` at
    `bin/data` fails on Linux, where that directory does not exist.
    """
    if residue is None:
        return True
    return getattr(residue, "OBResidue", None) is None


def is_excluded_chain(chain: str, keep_chains) -> bool:
    """Whether receptor preparation would drop this chain.

    An empty or absent `keep_chains` means keep everything, so the option
    is off by default and every existing caller is unaffected.

    Comparison is EXACT, deliberately not case-folded. mmCIF
    `label_asym_id` is case-sensitive and multi-character, and files
    genuinely do carry both `A` and `a` as separate chains; folding case
    to be forgiving would silently merge two different chains, which is
    the same class of error as the residue key that once merged a
    homotetramer's subunits.
    """
    if not keep_chains:
        return False
    return (chain or "").strip() not in {str(c).strip() for c in keep_chains}


def is_stripped_residue(
    residue_name: str,
    strip_waters: bool,
    strip_cofactors: bool,
    strip_ligand_codes: Iterable[str] = (),
) -> bool:
    """Whether receptor preparation would delete this residue.

    One predicate, two callers -- `docking_providers` deletes the atoms
    before docking, and `receptor_atoms_from_structure` skips them before
    analysis. Sharing the decision is the point.

    `strip_ligand_codes` NAMES SPECIFIC RESIDUES and is independent of
    `strip_cofactors`, which is the whole reason it exists rather than
    being folded into that flag.

    MEASURED, real Vina 1.2.7 against real 1HSG, everything identical
    except this option:

        indinavir, 1HSG's OWN co-crystallised ligand   -5.34  ->  -9.78
        benzene                                        -2.97  ->  -4.08
        wall clock                                     65.6s  ->  28.3s

    The receptor library derives every binding-site box from a
    co-crystallised ligand (`ReceptorEntry.ligand_code` ->
    `binding_site.box_from_ligand`) and, before this, left that ligand
    sitting in the pocket the box describes. Docking then searched an
    occupied site: 4.4 kcal/mol too weak on the native ligand, and SLOWER,
    because Vina was competing with it for space.

    Widening the `strip_cofactors` default was the wrong fix. That flag
    covers haem, catalytic zinc and the rest, which are genuinely part of
    a site and must stay by default. What has to go is the one ligand
    whose coordinates DEFINED the box -- so the caller names it.

    The damage was never a constant offset, which is why this matters more
    than the numbers above suggest: a small ligand fitting the leftover
    space is penalised less than a large one that does not, so the RANKING
    can invert -- and a ranking is the entire output of a virtual screen.
    """
    name = residue_name.strip().upper()
    if name in {str(code).strip().upper() for code in strip_ligand_codes if code}:
        return True
    if name in WATER_RESIDUE_NAMES:
        return strip_waters
    return strip_cofactors and name not in STANDARD_RECEPTOR_RESIDUES

# Van der Waals radii (Angstrom) for elements likely to appear in a
# docking receptor/ligand -- anything else falls back to
# _DEFAULT_VDW_RADIUS. These are Bondi's 1964 values with hydrogen at
# 1.10, Rowland and Taylor's value for CONTACT distances [source:rowland1996], as the CRC
# Handbook has them: this table decides whether two atoms are in
# contact, which is what that hydrogen is for. The surface and volume
# calculators use a different table on purpose (docs/VDW_RADII_ASSESSMENT.md).
# Zn, Mg and Na are Bondi's metal radii; Ca is Mantina's; the Fe value
# is not in either source and has not been traced -- and no published set
# supports it: Batsanov has iron at 2.05, Alvarez 2013 at 2.44
# [source:alvarez2013]. Treat the metal entries as placeholders for a
# NON-BONDED contact (Alvarez puts Zn 2.39, Mg 2.51, Na 2.50, Ca 2.62 -- all
# well above these, partly because Bondi's metal values are in places a
# cutoff, not a radius).
#
# They no longer decide anything about a metal's own ligands. A donor inside
# `metal_bond_window` of a metal, and the atoms next to it, are a bond and are
# skipped by the clash test (`_metal_bonded_pairs`), so these numbers only
# apply to ligand atoms further from the metal than that.
# They were deliberately NOT replaced with Alvarez's: that would move every
# non-bonded metal contact the application reports, on a radius whose
# meaning (a contact-peak edge, not a cutoff) differs from the +/-0.4 A
# tolerance used here, and nothing has measured what it would do.
_VDW_RADII = {
    "H": 1.10, "C": 1.70, "N": 1.55, "O": 1.52, "S": 1.80, "P": 1.80,
    "F": 1.47, "CL": 1.75, "BR": 1.85, "I": 1.98, "ZN": 1.39, "MG": 1.73,
    "CA": 2.31, "FE": 1.56, "NA": 2.27, "K": 2.75,
}
_DEFAULT_VDW_RADIUS = 1.70

Position = tuple[float, float, float]


@dataclass(slots=True)
class ReceptorAtom:
    element: str
    position: Position
    residue_name: str
    residue_number: int
    #: The PDB atom name (CA, CZ, NH1, OD2 ...), stripped. Needed for
    #: anything beyond a distance: a PHE ring centroid is CG/CD1/CD2/
    #: CE1/CE2/CZ, and averaging every carbon in the residue instead pulls
    #: the centre off the ring by including CA and CB. Empty when the
    #: source had no atom names, in which case the detectors that need
    #: them simply find nothing rather than guessing.
    atom_name: str = ""
    #: Chain identifier ("A", "B", ...). Needed to tell copies of the same
    #: component apart: a ligand present in six chains is very often
    #: numbered identically in all six, so residue number alone merges
    #: them into one object spread across the whole structure. Empty when
    #: the source has no chain labelling.
    chain: str = ""


def receptor_atoms_from_structure(
    structure_text: str,
    source_format: str,
    prep_options: dict[str, Any] | None = None,
) -> list[ReceptorAtom]:
    """Plain (position, element, residue) data for the receptor, via Open
    Babel -- already this codebase's receptor parser
    (chem/docking_providers.py), format-agnostic across PDB/mmCIF, unlike
    RDKit's own `MolFromPDBBlock` (PDB only -- the installed RDKit version
    has no mmCIF block reader, confirmed directly). Parse once per docking
    job and reuse across every pose, not once per pose.

    **`prep_options` must be the same options the docking used**, because
    otherwise the analysis describes a different receptor than the one the
    pose was produced against. Found live, docking naloxone into 4DKL with
    waters and cofactors stripped: the pose came back with 195 clashes and
    hydrogen bonds to `BF0601` and `HOH718` -- the co-crystallised
    morphinan and two waters, all three deleted before Vina ever ran. The
    numbers were not noise; they were confidently describing contacts with
    atoms that were not there. Defaults to no stripping so an unprepared
    receptor still parses whole.
    """
    from openbabel import pybel

    options = prep_options or {}
    strip_waters = bool(options.get("strip_waters", False))
    strip_cofactors = bool(options.get("strip_cofactors", False))
    keep_chains = options.get("keep_chains") or ()
    # Read here too, and not optional: if docking strips the box-defining
    # ligand and analysis does not, every pose is scored for contacts
    # against an atom the docking never saw. That divergence is exactly
    # what one shared predicate exists to prevent.
    strip_ligand_codes = tuple(options.get("strip_ligand_codes", ()) or ())

    # Unconditional, unlike the strips: receptor preparation ALWAYS drops
    # alternate locations, so matching it needs no option.
    structure_text = filter_altlocs(structure_text, source_format)
    # Likewise unconditional -- an uppercase two-letter symbol reads as
    # element 0 and is then skipped below, which silently deletes the
    # atom. See `normalise_mmcif_element_symbols`.
    structure_text = normalise_element_symbols(structure_text, source_format)

    table = Chem.GetPeriodicTable()
    mol = pybel.readstring(source_format, structure_text)
    atoms = []
    for atom in mol.atoms:
        if atom.atomicnum == 0:
            continue
        residue = atom.residue
        if is_symmetry_generated(residue):
            continue
        if residue is not None and is_stripped_residue(
            residue.name or "", strip_waters, strip_cofactors, strip_ligand_codes
        ):
            continue
        # Open Babel keeps the PDB atom name on the residue, not the atom
        # -- confirmed live: `residue.OBResidue.GetAtomID(atom.OBAtom)`
        # returns " CD1" (padded, hence the strip).
        atom_name = ""
        chain = ""
        if residue is not None:
            ob_residue = getattr(residue, "OBResidue", None)
            if ob_residue is not None:
                try:
                    atom_name = ob_residue.GetAtomID(atom.OBAtom).strip()
                except Exception:  # noqa: BLE001 - a nameless atom is still a usable atom
                    atom_name = ""
                try:
                    # Confirmed live: returns a plain str ("A", "B", ...).
                    chain = str(ob_residue.GetChain()).strip()
                except Exception:  # noqa: BLE001 - chainless sources are valid
                    chain = ""
        # Checked here rather than beside the residue strips because the
        # chain is only known once the residue has been read. Same
        # predicate the docking preparation uses -- see
        # `VinaDockingProvider._strip_unselected_chains`.
        if is_excluded_chain(chain, keep_chains):
            continue
        atoms.append(
            ReceptorAtom(
                element=table.GetElementSymbol(atom.atomicnum).upper(),
                position=atom.coords,
                residue_name=residue.name.strip() if residue else "",
                residue_number=_residue_number(residue),
                atom_name=atom_name,
                chain=chain,
            )
        )
    return atoms



def _residue_number(residue) -> int:
    """The residue number the STRUCTURE FILE gives, not Open Babel's index.

    `residue.idx` is an internal 0-based counter, so a PDB's LYS 128 came
    back as 1. That was wrong everywhere it surfaced, and worst where it
    is invisible: `ui/visualization.py` builds labels like "TYR652" from
    this, and `resources/molstar/*.html` matches them against Mol*'s
    `auth_seq_id` -- the file's own numbering. Feeding an index into an
    auth_seq_id comparison meant the binding-site colouring highlighted
    whatever residue happened to sit at that index, or nothing at all.

    `GetNum()` is the file's number. Confirmed live: a PDB with residues
    57 and 128 reports idx 0/1 and GetNum 57/128.
    """
    if residue is None:
        return 0
    ob_residue = getattr(residue, "OBResidue", None)
    if ob_residue is not None:
        try:
            return int(ob_residue.GetNum())
        except Exception:  # noqa: BLE001 - fall back rather than fail a whole job
            pass
    return int(getattr(residue, "idx", 0))


def _ligand_heavy_atoms(
    pose_molblock: str,
) -> tuple[Chem.Mol | None, list[tuple[int, str, Position]]]:
    """The pose and its heavy atoms as `(atom index, symbol, position)`.

    The index is the atom's place in the MOLECULE (hydrogens included), not
    in the returned list, because the bond graph that decides which atoms
    sit next to a coordinating donor is indexed the first way.
    """
    mol = Chem.MolFromMolBlock(pose_molblock, sanitize=False, removeHs=False)
    if mol is None or mol.GetNumConformers() == 0:
        return None, []
    conformer = mol.GetConformer()
    atoms = []
    for atom in mol.GetAtoms():
        symbol = atom.GetSymbol().upper()
        if symbol == "H":
            continue
        pos = conformer.GetAtomPosition(atom.GetIdx())
        atoms.append((atom.GetIdx(), symbol, (pos.x, pos.y, pos.z)))
    return mol, atoms


def _metal_bonded_pairs(
    mol: Chem.Mol | None,
    ligand_atoms: list[tuple[int, str, Position]],
    receptor_atoms: list[ReceptorAtom],
) -> set[tuple[int, int]]:
    """`(ligand atom index, receptor atom index)` pairs that are a bond to a
    metal, and so not a steric contact.

    Three kinds of pair, all keyed the same way:

    * a ligand donor (N, O, F, S) inside `metal_bond_window` of a RECEPTOR metal, which is per metal and per donor
      (and, for sodium and potassium, extended to their normal contacts by `is_metal_contact`);
    * every ligand atom within `_BONDED_NEIGHBOUR_DEPTH` bonds of such a donor,
      against THAT metal only. Their distance to the metal is fixed by the
      bond's geometry (the M--N--C angle is 126-131 degrees, which puts an
      imidazole carbon 3.0-3.4 A from the metal whatever the metal is), so
      measuring it against a van der Waals sum finds a "clash" in every
      coordinated pose, and the larger and more correct the metal's radius,
      the more of them. Atoms further out keep the ordinary test;
    * a LIGAND metal and a RECEPTOR donor in the same window. Only
      the pair itself: the receptor arrives as coordinates with no bonds, so
      there is no neighbourhood to walk.

    Computed once per pose. The bond graph is only built when a coordinating
    pair actually exists, which is almost never.
    """
    bonded: set[tuple[int, int]] = set()
    receptor_metals = [i for i, a in enumerate(receptor_atoms) if a.element in _METALS]
    ligand_metals = [(i, s, p) for i, s, p in ligand_atoms if s in _METALS]
    if not receptor_metals and not ligand_metals:
        return bonded

    path_lengths = None
    for receptor_index in receptor_metals:
        metal = receptor_atoms[receptor_index]
        for ligand_index, symbol, position in ligand_atoms:
            if symbol not in _METAL_DONOR_ELEMENTS:
                continue
            distance = math.dist(position, metal.position)
            donor = metal_donor_symbol(mol.GetAtomWithIdx(ligand_index)) if symbol == "F" and mol is not None else symbol
            if is_metal_bond(metal.element, donor, distance):
                bonded.add((ligand_index, receptor_index))
                if path_lengths is None:
                    path_lengths = Chem.GetDistanceMatrix(mol)
                for other_index, _symbol, _position in ligand_atoms:
                    if path_lengths[ligand_index][other_index] <= _BONDED_NEIGHBOUR_DEPTH:
                        bonded.add((other_index, receptor_index))
            elif is_metal_contact(metal.element, donor, distance):
                # an ion's normal contact beyond its primary sphere: not a bond, not a clash, and no neighbourhood
                bonded.add((ligand_index, receptor_index))

    for ligand_index, metal_symbol, metal_position in ligand_metals:
        for receptor_index, atom in enumerate(receptor_atoms):
            if atom.element in _METAL_DONOR_ELEMENTS and is_metal_contact(
                metal_symbol, atom.element, math.dist(metal_position, atom.position)
            ):
                bonded.add((ligand_index, receptor_index))
    return bonded


def _vdw_radius(element: str) -> float:
    return _VDW_RADII.get(element, _DEFAULT_VDW_RADIUS)



# --- Receptor feature perception ----------------------------------------
#
# Everything below identifies groups by RESIDUE AND ATOM NAME rather than
# by bond perception. That is deliberate and not a shortcut: the receptor
# arrives as coordinates from a PDB/mmCIF file with no reliable bond
# orders, and standard residues have standard atom names, which is exactly
# what the PDB naming convention is for. Anything non-standard -- a ligand
# in the receptor file, a modified residue -- simply contributes no
# features rather than being guessed at.
#
# Cutoffs are IMPORTED from `interaction_analysis`, not restated. The
# physics does not change between two atoms in one molecule and two atoms
# in different ones, and a second copy is how the two would drift apart.

#: Aromatic side-chain rings, by the atoms whose centroid IS the ring.
#: Tryptophan has two fused rings; the six-membered one is used, which is
#: the convention for pi-stacking geometry.
_AROMATIC_RINGS: dict[str, tuple[str, ...]] = {
    "PHE": ("CG", "CD1", "CD2", "CE1", "CE2", "CZ"),
    "TYR": ("CG", "CD1", "CD2", "CE1", "CE2", "CZ"),
    "TRP": ("CD2", "CE2", "CE3", "CZ2", "CZ3", "CH2"),
    "HIS": ("CG", "ND1", "CD2", "CE1", "NE2"),
}

#: Charged side-chain groups. HIS is included as a cation because it is
#: protonated at physiological pH often enough to matter, but it is the
#: least certain of these -- its pKa sits right at 6, so whether a given
#: histidine is charged depends on its environment, which coordinates
#: cannot tell us.
_CATION_GROUPS: dict[str, tuple[str, ...]] = {
    "ARG": ("NE", "NH1", "NH2"),
    "LYS": ("NZ",),
    "HIS": ("ND1", "NE2"),
}
_ANION_GROUPS: dict[str, tuple[str, ...]] = {
    "ASP": ("OD1", "OD2"),
    "GLU": ("OE1", "OE2"),
}

#: Side-chain carbons bonded to N or O, which are therefore NOT apolar
#: even though they are carbon. Listing the exceptions is shorter and
#: more legible than listing every apolar carbon, and the backbone
#: carbonyl carbon "C" is excluded for every residue.
_POLAR_CARBONS: dict[str, frozenset[str]] = {
    "ARG": frozenset({"CZ"}),
    "ASN": frozenset({"CG"}),
    "ASP": frozenset({"CG"}),
    "GLN": frozenset({"CD"}),
    "GLU": frozenset({"CD"}),
    "HIS": frozenset({"CG", "CD2", "CE1"}),
    "LYS": frozenset({"CE"}),
    "SER": frozenset({"CB"}),
    "THR": frozenset({"CB"}),
    "TRP": frozenset({"CD1", "CE2"}),
    "TYR": frozenset({"CZ"}),
}


@dataclass(frozen=True)
class _Group:
    """A named point on the receptor -- a ring centroid or a charge site."""

    residue: str
    position: Position
    #: Which subunit it belongs to. Kept beside `residue` rather than
    #: folded into it, because `residue` is the label that reaches Mol*
    #: and must stay `NAME` + `NUMBER`.
    chain: str = ""
    #: The element, for a metal (the bond window depends on which); empty for a ring or a charge site.
    element: str = ""


def _residues(
    receptor_atoms: list[ReceptorAtom],
) -> dict[tuple[str, str, int], list[ReceptorAtom]]:
    """Group atoms into residues, keyed by CHAIN, name and number.

    The chain is not optional. Without it every subunit of a multimer
    collapses into one "residue", and since `receptor_features` then
    indexes those atoms by atom name, the last chain read silently
    overwrites the rest -- three quarters of a homotetramer's aromatic
    rings and charge sites simply never existed as far as the interaction
    analysis was concerned.

    Measured on 8ZYO (hERG, four identical subunits): 34 aromatic rings
    found before, 136 after. Its four Tyr652 rings -- the residue every
    hERG structure-activity paper implicates in drug block -- sit 5-8 A
    apart around the pore, and only one of them was ever visible.
    """
    grouped: dict[tuple[str, str, int], list[ReceptorAtom]] = {}
    for atom in receptor_atoms:
        grouped.setdefault(
            (atom.chain, atom.residue_name, atom.residue_number), []
        ).append(atom)
    return grouped


def _centroid(positions: list[Position]) -> Position:
    count = len(positions)
    return (
        sum(p[0] for p in positions) / count,
        sum(p[1] for p in positions) / count,
        sum(p[2] for p in positions) / count,
    )


def receptor_features(receptor_atoms: list[ReceptorAtom]) -> dict[str, list[_Group]]:
    """Aromatic ring centroids, charge sites and metals on the receptor.

    Computed ONCE per docking job and reused across poses, like the atom
    list itself -- a receptor does not move between poses, and re-deriving
    this per pose was the mistake `receptor_atoms_from_structure` already
    warns about.

    A ring only counts when EVERY one of its atoms is present. A partially
    resolved side chain would otherwise produce a centroid computed from
    three atoms and reported as if it were the ring.
    """
    rings: list[_Group] = []
    cations: list[_Group] = []
    anions: list[_Group] = []
    metals: list[_Group] = []

    for (chain, name, number), atoms in _residues(receptor_atoms).items():
        label = f"{name}{number}"
        by_name = {atom.atom_name: atom for atom in atoms if atom.atom_name}

        wanted = _AROMATIC_RINGS.get(name)
        if wanted and all(atom_name in by_name for atom_name in wanted):
            rings.append(
                _Group(label, _centroid([by_name[a].position for a in wanted]), chain)
            )

        for table, sink in ((_CATION_GROUPS, cations), (_ANION_GROUPS, anions)):
            wanted = table.get(name)
            if wanted:
                present = [by_name[a].position for a in wanted if a in by_name]
                if present:
                    sink.append(_Group(label, _centroid(present), chain))

        for atom in atoms:
            if atom.element in _METALS:
                metals.append(_Group(label, atom.position, chain, atom.element))

    return {"rings": rings, "cations": cations, "anions": anions, "metals": metals}


def _is_apolar_receptor_carbon(atom: ReceptorAtom) -> bool:
    if atom.element != "C" or not atom.atom_name:
        return False
    if atom.atom_name == "C":  # the backbone carbonyl carbon
        return False
    return atom.atom_name not in _POLAR_CARBONS.get(atom.residue_name, frozenset())



def _formal_charge_sites(mol: Chem.Mol) -> tuple[list[int], list[int]]:
    """Atoms that are a real cation / anion site, not just a charge in the drawing.

    A formal charge is bookkeeping, and a neutral group is often DRAWN with a pair of them on neighbouring atoms: the
    nitro group (`[N+](=O)[O-]`), an N-oxide, a sulfoxide or sulfone written `[S+][O-]`, an azide, a diazo
    compound, an ylide. Reading each end as an ion reported nitrobenzene's nitro nitrogen as a cation 2.86 A from its
    own ring. The rule: atoms that carry a charge and are bonded to one another form a cluster, and a cluster's
    charges cancel as the drawing intends. A cluster that nets to zero contributes no site; one that does not
    (nitrate, `O=[N+]([O-])[O-]`, nets -1) contributes the atoms of the sign it nets to, and none of the other.
    A charge with no charged neighbour (an ammonium, a carboxylate O-) is a cluster of one and is kept.
    """
    charged = {a.GetIdx(): a.GetFormalCharge() for a in mol.GetAtoms() if a.GetFormalCharge()}
    positive: list[int] = []
    negative: list[int] = []
    seen: set[int] = set()
    for start in charged:
        if start in seen:
            continue
        cluster, frontier = [start], [start]
        seen.add(start)
        while frontier:
            for neighbor in mol.GetAtomWithIdx(frontier.pop()).GetNeighbors():
                index = neighbor.GetIdx()
                if index in charged and index not in seen:
                    seen.add(index)
                    cluster.append(index)
                    frontier.append(index)
        net = sum(charged[index] for index in cluster)
        if net > 0:
            positive += [index for index in cluster if charged[index] > 0]
        elif net < 0:
            negative += [index for index in cluster if charged[index] < 0]
    return sorted(positive), sorted(negative)


def _ligand_features(pose_molblock: str) -> dict[str, Any]:
    """Apolar carbons, aromatic ring centroids and charge sites on the pose.

    The pose is parsed WITHOUT sanitization first, because a docked pose
    is geometry rather than a curated structure and a strict parse would
    reject perfectly usable output. Sanitization is then attempted purely
    to get ring and aromaticity perception; when it fails, the ring-based
    interactions simply find nothing rather than the whole analysis
    failing -- distances and clashes still work on any parse.
    """
    mol = Chem.MolFromMolBlock(pose_molblock, sanitize=False, removeHs=False)
    if mol is None or mol.GetNumConformers() == 0:
        return {"apolar": [], "rings": [], "cations": [], "anions": [], "polar": [], "metals": []}
    conformer = mol.GetConformer()
    position = lambda index: tuple(conformer.GetAtomPosition(index))  # noqa: E731

    aromatic_ok = True
    try:
        Chem.SanitizeMol(mol)
    except Exception:  # noqa: BLE001 - geometry is still usable without perception
        aromatic_ok = False

    # A formal charge is bookkeeping, not an ion: a nitro group, N-oxide or
    # charge-separated sulfoxide is a neutral group drawn with two. The bond
    # graph is there even when sanitisation failed (the molblock carries the
    # bonds), so the cluster rule needs no perception.
    cation_sites, anion_sites = (set(sites) for sites in _formal_charge_sites(mol))

    apolar, cations, anions, polar, metals = [], [], [], [], []
    for atom in mol.GetAtoms():
        symbol = atom.GetSymbol().upper()
        if symbol == "H":
            continue
        index = atom.GetIdx()
        if symbol == "C":
            neighbours = {n.GetSymbol().upper() for n in atom.GetNeighbors()}
            if not (neighbours & _POLAR_ELEMENTS):
                apolar.append(position(index))
        if symbol in _METAL_DONOR_ELEMENTS:
            polar.append((symbol, position(index), metal_donor_symbol(atom)))
        elif symbol in _METALS:
            metals.append((symbol, position(index)))
        if index in cation_sites:
            cations.append(position(index))
        elif index in anion_sites:
            anions.append(position(index))

    rings = []
    if aromatic_ok:
        for ring in mol.GetRingInfo().AtomRings():
            if all(mol.GetAtomWithIdx(i).GetIsAromatic() for i in ring):
                rings.append(_centroid([position(i) for i in ring]))
    return {
        "apolar": apolar, "rings": rings, "cations": cations, "anions": anions,
        "polar": polar, "metals": metals,
    }


def analyze_pose(pose_molblock: str, receptor_atoms: list[ReceptorAtom]) -> dict[str, Any]:
    """Returns `{"hbonds": [...], "clashes": [...]}` for one docked pose
    against an already-parsed receptor atom list (see
    `receptor_atoms_from_structure`). Each entry is a plain dict (not a
    dataclass) since this lands directly in `DockingPoseModel.metadata`,
    an open `dict[str, Any]` meant for JSON-serializable data.
    """
    hbonds: list[dict[str, Any]] = []
    clashes: list[dict[str, Any]] = []

    ligand_mol, ligand_atoms = _ligand_heavy_atoms(pose_molblock)
    # A bond to a metal is not a contact: those pairs (and the donor's own
    # neighbours, whose distance to the metal the bond fixes) are left out of
    # the clash test and reported as `metal_coordination` instead.
    metal_bonded = _metal_bonded_pairs(ligand_mol, ligand_atoms, receptor_atoms)
    # A C-F or B-F fluorine is not a hydrogen-bond acceptor (see `is_weak_acceptor_fluorine`). The receptor's fluorine, which arrives as
    # coordinates with no bonds, is a fluoride ion or a cofactor's and is still counted: it cannot be told apart.
    weak_acceptor_fluorine = {
        index
        for index, element, _position in ligand_atoms
        if element == "F" and ligand_mol is not None and is_weak_acceptor_fluorine(ligand_mol.GetAtomWithIdx(index))
    }

    for ligand_index, ligand_element, ligand_position in ligand_atoms:
        ligand_radius = _vdw_radius(ligand_element)
        ligand_is_polar = ligand_element in _POLAR_ELEMENTS and ligand_index not in weak_acceptor_fluorine
        for receptor_index, receptor_atom in enumerate(receptor_atoms):
            distance = math.dist(ligand_position, receptor_atom.position)
            contact = {
                "ligand_element": ligand_element,
                "receptor_element": receptor_atom.element,
                "receptor_residue": f"{receptor_atom.residue_name}{receptor_atom.residue_number}",
                # Separate from the label ON PURPOSE. `receptor_residue` is
                # what `ui/visualization.py` turns into a Mol* selection
                # against `auth_seq_id`, so its format must not change --
                # but without the chain, every subunit of a symmetric
                # multimer collapses into one entry. hERG is a homotetramer
                # and a pore blocker touches Tyr652 in more than one
                # subunit; that was invisible until this was carried.
                "receptor_chain": receptor_atom.chain,
                "distance": round(distance, 2),
            }
            if (
                ligand_is_polar
                and receptor_atom.element in _POLAR_ELEMENTS
                and distance <= HBOND_DISTANCE_CUTOFF
            ):
                hbonds.append(contact)
            if (ligand_index, receptor_index) in metal_bonded:
                continue
            receptor_radius = _vdw_radius(receptor_atom.element)
            if distance < (ligand_radius + receptor_radius - CLASH_TOLERANCE):
                clashes.append(contact)

    found: dict[str, Any] = {"hbonds": hbonds, "clashes": clashes}
    found.update(_contact_interactions(pose_molblock, receptor_atoms))
    return found


def _contact_interactions(
    pose_molblock: str, receptor_atoms: list[ReceptorAtom]
) -> dict[str, list[dict[str, Any]]]:
    """The interaction types beyond hydrogen bonds and clashes.

    Split out rather than folded into `analyze_pose`'s loop because these
    work on GROUPS -- ring centroids, charged-group centres -- not on
    atom pairs, so they cannot share that loop's structure without
    contorting it.

    Every entry keeps the same `receptor_residue` key the existing two
    use, so `build_interaction_layers` can colour any of them without
    knowing which type it is holding.
    """
    ligand = _ligand_features(pose_molblock)
    receptor = receptor_features(receptor_atoms)

    def pairs(a_points, b_groups, cutoff, describe):
        out = []
        for a in a_points:
            for group in b_groups:
                distance = math.dist(a, group.position)
                if distance <= cutoff:
                    out.append({
                        "receptor_residue": group.residue,
                        "receptor_chain": group.chain,
                        "distance": round(distance, 2),
                        **describe,
                    })
        return out

    hydrophobic = []
    for point in ligand["apolar"]:
        for atom in receptor_atoms:
            if not _is_apolar_receptor_carbon(atom):
                continue
            distance = math.dist(point, atom.position)
            if distance <= HYDROPHOBIC_CUTOFF:
                hydrophobic.append({
                    "receptor_residue": f"{atom.residue_name}{atom.residue_number}",
                    "receptor_chain": atom.chain,
                    "distance": round(distance, 2),
                    "ligand_element": "C",
                    "receptor_element": "C",
                })

    # A salt bridge needs OPPOSITE charges, so each ligand sign pairs with
    # the receptor's other sign -- pairing like with like would report
    # electrostatic repulsion as a favourable contact.
    salt_bridges = (
        pairs(ligand["cations"], receptor["anions"], SALT_BRIDGE_CUTOFF, {"charge": "ligand +"})
        + pairs(ligand["anions"], receptor["cations"], SALT_BRIDGE_CUTOFF, {"charge": "ligand -"})
    )
    metal_coordination = []
    for element, point, donor in ligand["polar"]:
        for group in receptor["metals"]:
            distance = math.dist(point, group.position)
            if is_metal_bond(group.element, donor, distance):
                metal_coordination.append({
                    "receptor_residue": group.residue,
                    "receptor_chain": group.chain,
                    "distance": round(distance, 2),
                    "ligand_element": element,
                })
    # The other direction: a metal the LIGAND carries, bound by a receptor
    # N/O/S. `analyze_pose` leaves exactly these pairs out of the clash test
    # (`_metal_bonded_pairs`), so they must be reported here or the contact
    # would vanish from both lists. The entry names the metal in
    # `ligand_element` as it does for a ligand donor, and says which receptor
    # element donates.
    for element, point in ligand["metals"]:
        for atom in receptor_atoms:
            if atom.element not in _METAL_DONOR_ELEMENTS:
                continue
            distance = math.dist(point, atom.position)
            if is_metal_bond(element, atom.element, distance):
                metal_coordination.append({
                    "receptor_residue": f"{atom.residue_name}{atom.residue_number}",
                    "receptor_chain": atom.chain,
                    "distance": round(distance, 2),
                    "ligand_element": element,
                    "receptor_element": atom.element,
                })

    return {
        "hydrophobic": hydrophobic,
        "salt_bridges": salt_bridges,
        "pi_stacking": pairs(
            ligand["rings"], receptor["rings"], PI_STACKING_CUTOFF, {"geometry": "centroid"}
        ),
        # Both directions: a ligand cation over a receptor aromatic ring,
        # and a receptor cation (ARG/LYS/HIS) over a ligand ring. Reporting
        # only one would miss half of a symmetric interaction.
        "cation_pi": (
            pairs(ligand["cations"], receptor["rings"], CATION_PI_CUTOFF, {"cation": "ligand"})
            + pairs(ligand["rings"], receptor["cations"], CATION_PI_CUTOFF, {"cation": "receptor"})
        ),
        "metal_coordination": metal_coordination,
    }
