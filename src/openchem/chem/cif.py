"""A CIF reader for small molecules and minerals.

`chem/binarycif.py` is protein-oriented: it reads mmCIF's macromolecular
categories and neither crystal symmetry nor site occupancy, which are the
two things a mineral file is mostly made of. This is a separate reader
rather than an extension of that one, for the same reason `domain/crystal`
does not inherit from the molecule model -- the overlap is "both are
text with loops in", and sharing on that basis would couple a protein
pipeline to a mineral one forever.

## What it handles

    data_ blocks              the first one, or a named one
    loop_                     with any number of tags
    'quoted' and "values"     including embedded spaces
    ; text fields ;           multi-line values
    5.6393(2)                 a value with its standard uncertainty
    ? and .                   the CIF spellings of "unknown" and "n/a"
    _atom_site_type_symbol    'Na+', 'O2-' -> element Na, O

## What it deliberately does not

Anisotropic displacement parameters, disorder groups, restraints,
publication metadata. **They are recorded in `Crystal.unhandled` rather
than dropped**, because a structure with disorder is still worth showing
and silently ignoring the fields is how a tool starts implying it
understood more than it did.

## Standard uncertainty is discarded, not parsed into a value

`5.6393(2)` means 5.6393 with an uncertainty of 2 in the last digit. The
number is taken and the uncertainty is dropped. Keeping it would mean
propagating it through every derived quantity to be worth anything, and a
half-propagated uncertainty is worse than none -- the same call this
project made about confidence percentages.
"""

from __future__ import annotations

import re

from openchem.domain.crystal import (
    Crystal,
    Lattice,
    Site,
    SymmetryOperation,
    parse_symmetry_operation,
)

#: CIF's two spellings of "no value": unknown, and not applicable.
_NULLS = {"?", "."}

#: Tags the reader understands. Anything else outside these prefixes is
#: reported in `Crystal.unhandled`.
_KNOWN_PREFIXES = (
    "_cell_",
    "_symmetry_",
    "_space_group_",
    "_atom_site_label",
    "_atom_site_type_symbol",
    "_atom_site_fract_",
    "_atom_site_occupancy",
    "_atom_site_symmetry_multiplicity",
    "_atom_site_wyckoff",
    "_chemical_",
)

_UNCERTAINTY = re.compile(r"\(\d+\)\s*$")
_ELEMENT = re.compile(r"^([A-Z][a-z]?)")
#: The charge suffix of a type symbol: `Na+`, `O2-`, `Fe2+`.
#: Digits BEFORE the sign, which is the CIF convention and the
#: opposite of how SMILES writes it.
_CHARGE = re.compile(r"^[A-Z][a-z]?(\d*)([+-])$")


class CifError(ValueError):
    """The file could not be read as a CIF."""


def parse_number(text: str) -> float | None:
    """`'5.6393(2)'` -> 5.6393, `'?'` -> None.

    The standard uncertainty is stripped rather than parsed; see the
    module docstring.
    """
    if text is None:
        return None
    cleaned = text.strip().strip("'\"")
    if not cleaned or cleaned in _NULLS:
        return None
    cleaned = _UNCERTAINTY.sub("", cleaned).strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def charge_of(symbol: str) -> int | None:
    """`'Na+'` -> `1`, `'O2-'` -> `-2`, `'Na'` -> `None`.

    **None is "the file did not say", never "neutral".** A deposition
    that states no oxidation state has not claimed the atom is neutral,
    and treating the two alike is how a lattice energy gets computed for
    a structure nothing said was ionic.

    Deliberately NOT read from the site label: `Na1` means the first
    sodium site, and reading its `1` as a charge would invent one for
    every mineral file in existence.
    """
    cleaned = (symbol or "").strip().strip("'\"")
    match = _CHARGE.match(cleaned)
    if match is None:
        return None
    magnitude = int(match.group(1)) if match.group(1) else 1
    return magnitude if match.group(2) == "+" else -magnitude


def element_of(symbol: str, fallback_label: str = "") -> str:
    """`'Na+'` -> `'Na'`, `'O2-'` -> `'O'`, `'Fe2+'` -> `'Fe'`.

    Falls back to the site LABEL when there is no type symbol, since
    mineral files often carry only `Na1`, `O3`. Taking the leading letters
    is what both conventions have in common.
    """
    for candidate in (symbol, fallback_label):
        cleaned = (candidate or "").strip().strip("'\"")
        match = _ELEMENT.match(cleaned)
        if match:
            return match.group(1)
    return ""


def _tokenise(line: str) -> list[str]:
    """Split a CIF data line, respecting quotes.

    `shlex` is not used: it treats a lone apostrophe inside a word as an
    opening quote, and mineral files contain names like `'Ca-rich'` beside
    bare words with apostrophes in them.
    """
    tokens: list[str] = []
    index = 0
    while index < len(line):
        character = line[index]
        if character.isspace():
            index += 1
            continue
        if character in "'\"":
            closing = line.find(character, index + 1)
            if closing == -1:
                tokens.append(line[index + 1 :])
                break
            tokens.append(line[index + 1 : closing])
            index = closing + 1
            continue
        end = index
        while end < len(line) and not line[end].isspace():
            end += 1
        tokens.append(line[index:end])
        index = end
    return tokens


def _blocks(text: str) -> dict[str, tuple[dict[str, str], list[dict[str, list[str]]]]]:
    """Split into data blocks, each with its plain tags and its loops."""
    blocks: dict[str, tuple[dict[str, str], list[dict[str, list[str]]]]] = {}
    name = ""
    tags: dict[str, str] = {}
    loops: list[dict[str, list[str]]] = []

    lines = text.splitlines()
    index = 0
    while index < len(lines):
        raw = lines[index]
        stripped = raw.strip()

        if stripped.startswith("#") or not stripped:
            index += 1
            continue

        if stripped.lower().startswith("data_"):
            if name or tags or loops:
                blocks[name] = (tags, loops)
            name = stripped[5:]
            tags, loops = {}, []
            index += 1
            continue

        if stripped.lower() == "loop_":
            index += 1
            loop_tags: list[str] = []
            while index < len(lines) and lines[index].strip().startswith("_"):
                loop_tags.append(lines[index].strip().split()[0].lower())
                index += 1
            values: list[str] = []
            while index < len(lines):
                candidate = lines[index].strip()
                if (
                    not candidate
                    or candidate.startswith("_")
                    or candidate.lower() == "loop_"
                    or candidate.lower().startswith("data_")
                ):
                    break
                if candidate.startswith("#"):
                    index += 1
                    continue
                values.extend(_tokenise(candidate))
                index += 1
            if loop_tags:
                columns: dict[str, list[str]] = {tag: [] for tag in loop_tags}
                width = len(loop_tags)
                # A ragged tail means the file is malformed or the reader
                # mis-split a line; dropping it beats emitting sites with
                # coordinates borrowed from the next row.
                for row in range(len(values) // width):
                    for offset, tag in enumerate(loop_tags):
                        columns[tag].append(values[row * width + offset])
                loops.append(columns)
            continue

        if stripped.startswith("_"):
            parts = _tokenise(stripped)
            tag = parts[0].lower()
            if len(parts) > 1:
                tags[tag] = " ".join(parts[1:])
            else:
                # A value on following lines, possibly a ';' text field.
                index += 1
                collected: list[str] = []
                if index < len(lines) and lines[index].startswith(";"):
                    collected.append(lines[index][1:])
                    index += 1
                    while index < len(lines) and not lines[index].startswith(";"):
                        collected.append(lines[index])
                        index += 1
                    index += 1
                elif index < len(lines):
                    collected.extend(_tokenise(lines[index].strip()))
                    index += 1
                # **Newlines, not spaces.** A `;` field is a text block and
                # its line structure is meaningful -- leucopterin's
                # `_chemical_name_common` is a name on the first line
                # followed by a paragraph of explanation. Joining with
                # spaces destroyed that, and the whole paragraph became the
                # structure's name in the report. Found by running the app.
                tags[tag] = "\n".join(part.rstrip() for part in collected).strip()
                continue
            index += 1
            continue

        index += 1

    blocks[name] = (tags, loops)
    return blocks


def _lattice_from(tags: dict[str, str]) -> Lattice:
    lengths = [parse_number(tags.get(f"_cell_length_{axis}", "")) for axis in "abc"]
    if any(value is None or value <= 0 for value in lengths):
        raise CifError(
            "no usable unit cell: _cell_length_a/b/c are missing or non-positive. "
            "A file without a cell is not a crystal structure."
        )
    angles = [
        parse_number(tags.get(f"_cell_angle_{name}", "")) or 90.0
        for name in ("alpha", "beta", "gamma")
    ]
    return Lattice(*lengths, *angles)


def _operations_from(loops: list[dict[str, list[str]]]) -> tuple[SymmetryOperation, ...]:
    """Symmetry operations, under either of the two tag spellings.

    `_symmetry_equiv_pos_as_xyz` is the older form and
    `_space_group_symop_operation_xyz` the current one; files in the wild
    use both, and some carry both. Reading only one is a silent way to get
    an unexpanded structure.
    """
    for loop in loops:
        for tag in (
            "_space_group_symop_operation_xyz",
            "_symmetry_equiv_pos_as_xyz",
            "_space_group_symop_id",
            "_symmetry_equiv_pos_site_id",
        ):
            if tag in loop and not tag.endswith("_id"):
                return tuple(parse_symmetry_operation(text) for text in loop[tag])
    return None


def _operations_from_symbol(symbol: str, lattice: Lattice):
    """The operations a space-group symbol stands for, or why not.

    **This is the branch that used to return the identity and say
    nothing.** A CIF may legally name its space group and supply no
    `_symmetry_equiv_pos_as_xyz` loop, and answering that with `x,y,z`
    leaves the asymmetric unit unexpanded -- so atoms per cell,
    composition, density, volume per formula unit, every coordination
    shell and the lattice energy are all computed about a structure that
    was never built. None of them looks wrong.

    All six shipped COD fixtures carry a symop loop, so the corpus could
    not see this: a mutation deleting the fallback passed.

    The cell is passed through because it is what disambiguates the seven
    rhombohedral groups, whose hexagonal and rhombohedral settings differ
    by a factor of three in operation count. See `chem/space_groups`.
    """
    from openchem.chem.space_groups import Unresolved, describe, resolve

    resolved = resolve(symbol, lattice)
    if isinstance(resolved, Unresolved):
        return None, describe(resolved, symbol)
    return resolved.symmetry_operations(), ""


def _sites_from(loops: list[dict[str, list[str]]]) -> tuple[Site, ...]:
    for loop in loops:
        if "_atom_site_fract_x" not in loop:
            continue
        labels = loop.get("_atom_site_label", [])
        symbols = loop.get("_atom_site_type_symbol", [])
        occupancies = loop.get("_atom_site_occupancy", [])
        sites: list[Site] = []
        for index in range(len(loop["_atom_site_fract_x"])):
            position = tuple(
                parse_number(loop[f"_atom_site_fract_{axis}"][index]) or 0.0
                for axis in "xyz"
            )
            label = labels[index] if index < len(labels) else f"site{index + 1}"
            symbol = symbols[index] if index < len(symbols) else ""
            element = element_of(symbol, label)
            if not element:
                continue
            occupancy = (
                parse_number(occupancies[index]) if index < len(occupancies) else None
            )
            sites.append(
                Site(
                    label=label,
                    element=element,
                    position=position,
                    occupancy=1.0 if occupancy is None else occupancy,
                    # From the type symbol only -- see `charge_of` for why
                    # the site LABEL is not consulted.
                    charge=charge_of(symbols[index]) if index < len(symbols) else None,
                )
            )
        return tuple(sites)
    return ()


#: A name longer than this is prose, not a name. Chosen from the real
#: case: leucopterin's is "Leucopterin (variable hydrate)" at 29
#: characters, followed by 400 more of explanation.
_MAX_NAME = 80


def _short_name(text: str) -> str:
    """The first line of a name field, and nothing after it.

    `_chemical_name_common` is often a `;` block whose first line is the
    name and whose remainder is a paragraph about the refinement. Taking
    the lot put 400 characters of prose in the report's Structure row,
    which is where running the app found it.

    The remainder is not lost -- it stays in the file, and the fields the
    reader did not interpret are already listed in `Crystal.unhandled`.
    """
    lines = [line.strip() for line in (text or "").strip().splitlines()]
    first = next((line for line in lines if line), "")
    if len(first) <= _MAX_NAME:
        return first
    # A single run-on line: cut at a sentence end if there is one nearby,
    # so the result reads as a name rather than a truncation.
    stop = first.find(". ")
    if 0 < stop <= _MAX_NAME:
        return first[:stop].strip()
    return first[:_MAX_NAME].rstrip() + "..."


def read_cif(text: str, *, block: str = "") -> Crystal:
    """Read one data block into a `Crystal`.

    Takes the named block, or the first one that has a unit cell -- a
    published CIF often holds several structures, and picking blindly
    would silently return whichever happened to be first.
    """
    blocks = _blocks(text)
    if not blocks:
        raise CifError("no data_ block found; this does not look like a CIF")

    if block:
        if block not in blocks:
            raise CifError(f"no data block named {block!r}; found {sorted(blocks)}")
        candidates = [(block, blocks[block])]
    else:
        candidates = [
            item for item in blocks.items() if "_cell_length_a" in item[1][0]
        ] or list(blocks.items())

    name, (tags, loops) = candidates[0]
    lattice = _lattice_from(tags)
    sites = _sites_from(loops)
    if not sites:
        raise CifError(
            "the cell was read but no atom sites were: _atom_site_fract_x/y/z are "
            "missing. A structure with coordinates only in Cartesian is not handled."
        )

    unhandled = sorted(
        {
            tag
            for tag in tags
            if not tag.startswith(_KNOWN_PREFIXES)
        }
        | {
            tag
            for loop in loops
            for tag in loop
            if not tag.startswith(_KNOWN_PREFIXES)
        }
    )

    number = parse_number(tags.get("_symmetry_int_tables_number", "")) or parse_number(
        tags.get("_space_group_it_number", "")
    )
    z = parse_number(tags.get("_cell_formula_units_z", ""))

    space_group = (
        tags.get("_symmetry_space_group_name_h-m")
        or tags.get("_space_group_name_h-m_alt")
        or ""
    ).strip()

    # The loop is authoritative when it is there; the symbol is the
    # fallback; the identity is the LAST resort and is recorded as such.
    operations = _operations_from(loops)
    if operations is not None:
        symmetry_source, symmetry_note = "loop", ""
    else:
        operations, note = _operations_from_symbol(space_group, lattice)
        if operations is not None:
            symmetry_source, symmetry_note = "space_group", ""
        else:
            operations = (parse_symmetry_operation("x,y,z"),)
            symmetry_source = "unexpanded"
            symmetry_note = note or (
                "the file lists no symmetry operations and names no space group, "
                "so the asymmetric unit could not be expanded"
            )

    return Crystal(
        lattice=lattice,
        sites=sites,
        operations=operations,
        symmetry_source=symmetry_source,
        symmetry_note=symmetry_note,
        space_group=space_group,
        space_group_number=int(number) if number else None,
        formula_units_z=int(z) if z else None,
        name=_short_name(
            tags.get("_chemical_name_mineral")
            or tags.get("_chemical_name_common")
            or name
        ),
        source=tags.get("_chemical_formula_sum", "").strip(),
        unhandled=tuple(unhandled),
    )
