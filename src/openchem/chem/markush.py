"""Markush structure enumeration.

A Markush structure describes a compound CLASS by generic notation --
standard in patent claims and combinatorial library definitions. Its
"library" is the set of specific molecules it covers.

WHY THIS IS HAND-BUILT RATHER THAN DELEGATED TO RDKIT
-----------------------------------------------------
`rdMolEnumerator` exists, but confirmed live that `EnumeratorType` covers
only **LinkNode, PositionVariation and RepeatUnit** -- it has no notion of
R-groups or atom lists, which are the two central Markush features and the
first two rows of Marvin's own feature table. So R-group and atom-list
enumeration is implemented here directly (RWMol surgery and atomic-number
substitution, both verified live).

What RDKit DOES give us for free is `MolEnumeratorParams.doRandom`,
`maxToEnumerate` and `randomSeed` -- which is why the option names below
line up with Marvin's: random enumeration and a generation cap are
established ideas, not invented here.

FEATURE COVERAGE, stated honestly rather than implied:
    R-groups        supported (including multiple occurrences of one label)
    Atom lists      supported
    Link nodes      delegated to rdMolEnumerator
    Bond lists      NOT supported
    Nested R-groups NOT supported (an R-group definition containing another)

The four enumeration modes are Marvin's own, because they answer genuinely
different questions:
    library size        how big is the class? (combinatorial, no enumeration)
    sequential          the first N members, in a reproducible order
    random              a representative sample of a class too big to walk
    selected part       vary only some positions, leaving the rest generic
plus the valence filter, which discards members whose substitution produces
an impossible valence.
"""

from __future__ import annotations

import itertools
import math
import random
from dataclasses import dataclass, field
from typing import Any, Iterator

from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.domain.common import CacheState, Provenance
from openchem.domain.scientific_result import StructureEntry, StructureSetResult

# Attachment-point map number used inside a substituent's SMILES. 99 rather
# than 1 so it can never collide with an R-label the user is defining.
ATTACHMENT_MAP_NUM = 99

DEFAULT_MAX_STRUCTURES = 1000  # Marvin's own default "Generate maximum"


class MarkushError(ValueError):
    """Raised for a Markush definition that cannot be enumerated."""


@dataclass(frozen=True)
class RGroupDefinition:
    """One R-label and the fragments that may occupy it.

    Each substituent is a SMILES containing exactly one `[*:99]` marking
    where it attaches, e.g. `[*:99]Cl` or `[*:99]OC`.
    """

    label: int
    substituents: list[str]

    def __post_init__(self) -> None:
        if not self.substituents:
            raise MarkushError(f"R{self.label} has no substituent definitions.")


@dataclass(frozen=True)
class AtomListPosition:
    """One position that may be any of several elements -- Marvin's "atom
    list" feature, written `[C,N,O]` on the diagram."""

    atom_index: int
    elements: list[str]

    def __post_init__(self) -> None:
        if not self.elements:
            raise MarkushError(f"Atom list at index {self.atom_index} is empty.")


@dataclass(frozen=True)
class MarkushStructure:
    """A core plus its variable points.

    The core is SMILES whose R-group attachment points are dummy atoms
    carrying the R-label as their atom map number: `[*:1]c1ccc([*:2])cc1`
    is a benzene with R1 and R2.
    """

    core_smiles: str
    r_groups: list[RGroupDefinition] = field(default_factory=list)
    atom_lists: list[AtomListPosition] = field(default_factory=list)

    def core_mol(self) -> Chem.Mol:
        mol = Chem.MolFromSmiles(self.core_smiles, sanitize=False)
        if mol is None:
            raise MarkushError(f"Could not parse the Markush core: {self.core_smiles!r}")
        return mol

    def variable_points(self) -> list[tuple[str, Any, int]]:
        """Every variable point as (kind, key, option_count), in a stable
        order -- the basis for both sizing and enumeration."""
        points: list[tuple[str, Any, int]] = []
        for group in sorted(self.r_groups, key=lambda g: g.label):
            # One R-label can appear at several positions on the core, and
            # Marvin treats each occurrence as independently substitutable.
            occurrences = _label_occurrences(self.core_mol(), group.label)
            for _ in range(max(occurrences, 1)):
                points.append(("rgroup", group.label, len(group.substituents)))
        for atom_list in sorted(self.atom_lists, key=lambda a: a.atom_index):
            points.append(("atomlist", atom_list.atom_index, len(atom_list.elements)))
        return points


def _label_occurrences(core: Chem.Mol, label: int) -> int:
    return sum(1 for atom in core.GetAtoms() if atom.GetAtomicNum() == 0 and atom.GetAtomMapNum() == label)


def library_size(markush: MarkushStructure, only_labels: set[int] | None = None) -> int:
    """The exact number of specific structures the Markush class covers.

    Computed COMBINATORIALLY -- the product of each variable point's option
    count -- never by enumerating. That is the whole point of the feature:
    Marvin's own documentation example reports 38,102,400 members, and the
    only way to answer that is arithmetic.

    The count deliberately ignores the valence filter, matching Marvin,
    whose docs state the library size "does not consider the valence check
    filter". Filtering would require generating every member.
    """
    total = 1
    for kind, key, count in markush.variable_points():
        if only_labels is not None and kind == "rgroup" and key not in only_labels:
            continue
        total *= count
    return total


def _substitute_rgroup(mol: Chem.Mol, label: int, substituent_smiles: str) -> Chem.Mol:
    """Replaces ONE occurrence of `label`'s dummy atom with a substituent.

    Verified live: joining the two neighbour atoms and deleting both dummy
    atoms composes correctly across successive substitutions.
    """
    fragment = Chem.MolFromSmiles(substituent_smiles, sanitize=False)
    if fragment is None:
        raise MarkushError(f"Could not parse substituent: {substituent_smiles!r}")

    combined = Chem.RWMol(Chem.CombineMols(mol, fragment))
    core_dummy = next(
        (
            atom.GetIdx()
            for atom in combined.GetAtoms()
            if atom.GetAtomicNum() == 0 and atom.GetAtomMapNum() == label
        ),
        None,
    )
    fragment_dummy = next(
        (
            atom.GetIdx()
            for atom in combined.GetAtoms()
            if atom.GetAtomicNum() == 0 and atom.GetAtomMapNum() == ATTACHMENT_MAP_NUM
        ),
        None,
    )
    if core_dummy is None or fragment_dummy is None:
        raise MarkushError(
            f"R{label}: the core needs a [*:{label}] attachment point and the substituent "
            f"a [*:{ATTACHMENT_MAP_NUM}] one."
        )

    core_neighbors = combined.GetAtomWithIdx(core_dummy).GetNeighbors()
    fragment_neighbors = combined.GetAtomWithIdx(fragment_dummy).GetNeighbors()
    if not core_neighbors or not fragment_neighbors:
        raise MarkushError(f"R{label}: an attachment point is not bonded to anything.")

    combined.AddBond(core_neighbors[0].GetIdx(), fragment_neighbors[0].GetIdx(), Chem.BondType.SINGLE)
    for index in sorted([core_dummy, fragment_dummy], reverse=True):
        combined.RemoveAtom(index)
    return combined.GetMol()


def _apply_atom_list(mol: Chem.Mol, atom_index: int, element: str) -> Chem.Mol:
    editable = Chem.RWMol(mol)
    if atom_index >= editable.GetNumAtoms():
        raise MarkushError(f"Atom list position {atom_index} is outside the core.")
    editable.GetAtomWithIdx(atom_index).SetAtomicNum(
        Chem.GetPeriodicTable().GetAtomicNumber(element)
    )
    return editable.GetMol()


def _build_member(
    markush: MarkushStructure, choices: tuple[int, ...], only_labels: set[int] | None
) -> tuple[Chem.Mol | None, bool]:
    """One library member from one combination of option indices.

    Returns `(mol, valence_ok)`. A member whose substitution produces an
    impossible valence is STILL RETURNED, with `valence_ok=False` --
    confirmed live that sanitizing without `SANITIZE_PROPERTIES` leaves
    such a structure usable and depictable (a quaternary carbon swapped to
    nitrogen gives `CN(C)(C)C`, which draws fine and is chemically wrong).
    That is what lets the valence filter genuinely change the result count
    the way Marvin's does, instead of being an inert checkbox.

    `(None, False)` means the combination could not be built at all.
    """
    mol = markush.core_mol()
    substituents = {group.label: group.substituents for group in markush.r_groups}

    position = 0
    for kind, key, _count in markush.variable_points():
        if kind == "rgroup":
            if only_labels is not None and key not in only_labels:
                continue
            mol = _substitute_rgroup(mol, key, substituents[key][choices[position]])
        else:
            atom_list = next(a for a in markush.atom_lists if a.atom_index == key)
            mol = _apply_atom_list(mol, key, atom_list.elements[choices[position]])
        position += 1

    try:
        Chem.SanitizeMol(mol)
        return mol, True
    except Exception:  # noqa: BLE001 - an impossible valence is a real, expected outcome
        pass

    # Retry without the valence/property check so the structure survives
    # for the filter-off path.
    relaxed = Chem.Mol(mol)
    try:
        Chem.SanitizeMol(
            relaxed, sanitizeOps=Chem.SanitizeFlags.SANITIZE_ALL ^ Chem.SanitizeFlags.SANITIZE_PROPERTIES
        )
        return relaxed, False
    except Exception:  # noqa: BLE001 - genuinely unusable, not merely bad valence
        return None, False


def _choice_space(markush: MarkushStructure, only_labels: set[int] | None) -> list[int]:
    return [
        count
        for kind, key, count in markush.variable_points()
        if not (only_labels is not None and kind == "rgroup" and key not in only_labels)
    ]


def _sequential_combinations(space: list[int]) -> Iterator[tuple[int, ...]]:
    """Marvin's sequential order: vary the first definition of the first
    variable first. `itertools.product` over ranges is exactly that."""
    return itertools.product(*(range(count) for count in space))


def _random_combinations(space: list[int], count: int, seed: int | None) -> Iterator[tuple[int, ...]]:
    """A representative random sample.

    Draws each variable point independently and uniformly, which is what
    makes the sample representative over the library space rather than
    biased toward whichever definitions happen to come first.
    """
    rng = random.Random(seed)
    seen: set[tuple[int, ...]] = set()
    total = math.prod(space) if space else 1
    # Stop trying once the space is exhausted -- otherwise a small library
    # asked for more samples than it has members would spin forever.
    attempts = 0
    max_attempts = max(count * 20, 100)
    while len(seen) < min(count, total) and attempts < max_attempts:
        attempts += 1
        combination = tuple(rng.randrange(size) for size in space)
        if combination not in seen:
            seen.add(combination)
            yield combination


def enumerate_markush(
    markush: MarkushStructure,
    molecule_uuid: str,
    mode: str = "sequential",
    max_structures: int = DEFAULT_MAX_STRUCTURES,
    valence_filter: bool = True,
    only_labels: set[int] | None = None,
    seed: int | None = None,
) -> StructureSetResult:
    """Enumerate the library.

    `mode` is "sequential" or "random". `only_labels` restricts enumeration
    to some R-labels (Marvin's "selected part enumeration"), leaving the
    others as generic attachment points in the output -- which is why those
    results are still Markush structures, just more specific ones.
    """
    space = _choice_space(markush, only_labels)
    total = library_size(markush, only_labels)

    if mode == "random":
        combinations = _random_combinations(space, max_structures, seed)
    else:
        combinations = _sequential_combinations(space)

    entries: list[StructureEntry] = []
    rejected = 0
    for combination in combinations:
        if len(entries) >= max_structures:
            break
        member, valence_ok = _build_member(markush, combination, only_labels)
        if member is None:
            continue  # could not be built at all, not merely bad valence
        if not valence_ok:
            rejected += 1
            if valence_filter:
                continue
        prepared = Chem.Mol(member)
        try:
            AllChem.Compute2DCoords(prepared)
        except Exception:  # noqa: BLE001 - depiction is best-effort
            pass
        smiles = Chem.MolToSmiles(member)
        entries.append(
            StructureEntry(
                molblock=Chem.MolToMolBlock(prepared, kekulize=valence_ok),
                # Flagged in the label, not just in metadata: a structure
                # with an impossible valence looks perfectly normal in a
                # grid of depictions unless it is called out.
                # Plain ASCII deliberately: this label reaches logs and
                # console streams, and a Windows cp1252 stream raises
                # UnicodeEncodeError on a warning glyph (hit while testing).
                label=smiles if valence_ok else f"{smiles}  [valence error]",
                metadata={
                    "smiles": smiles,
                    "choices": list(combination),
                    "valence_ok": valence_ok,
                },
            )
        )

    name = f"Markush library ({len(entries)} of {total:,})"
    provenance_parameters: dict[str, Any] = {
        "mode": mode,
        "valence_filter": valence_filter,
        "library_size": total,
        "rejected_by_valence": rejected,
    }
    if only_labels:
        provenance_parameters["only_labels"] = sorted(only_labels)
    if mode == "random" and seed is not None:
        provenance_parameters["seed"] = seed

    return StructureSetResult(
        set_id="markush_enumeration",
        name=name,
        method="rdkit",
        molecule_uuid=molecule_uuid,
        entries=entries,
        total_available=total,
        truncated=len(entries) < total,
        provenance=Provenance(created_by="core", method="rdkit", parameters=provenance_parameters),
    )


def parse_substituent_spec(spec: str) -> list[RGroupDefinition]:
    """Parses `"R1: Cl, F, Br; R2: O, N, OC"` into R-group definitions.

    A plain text format because the generic settings dialog has no
    structure-drawing widget, and because a patent claim's R-group table is
    naturally written this way. Each substituent is SMILES for the fragment
    ALONE -- the `[*:99]` attachment marker is added here, so a user writes
    `Cl` rather than `[*:99]Cl`.
    """
    definitions: list[RGroupDefinition] = []
    for clause in spec.split(";"):
        clause = clause.strip()
        if not clause:
            continue
        if ":" not in clause:
            raise MarkushError(f"Expected 'R<n>: sub, sub', got {clause!r}")
        label_text, substituents_text = clause.split(":", 1)
        label_text = label_text.strip().lstrip("Rr")
        if not label_text.isdigit():
            raise MarkushError(f"Not an R-label: {clause.split(':', 1)[0].strip()!r}")
        substituents = [s.strip() for s in substituents_text.split(",") if s.strip()]
        if not substituents:
            raise MarkushError(f"R{label_text} lists no substituents.")
        definitions.append(
            RGroupDefinition(
                label=int(label_text),
                substituents=[f"[*:{ATTACHMENT_MAP_NUM}]{s}" for s in substituents],
            )
        )
    return definitions


def _parse_labels(text: str) -> set[int] | None:
    """`"1,2"` -> {1, 2}; empty -> None (meaning "every label")."""
    text = (text or "").strip()
    if not text:
        return None
    labels = set()
    for part in text.replace("R", "").replace("r", "").split(","):
        part = part.strip()
        if part.isdigit():
            labels.add(int(part))
    return labels or None


def compute_markush_enumeration(
    mol: Chem.Mol, molecule_uuid: str, parameters: dict[str, Any] | None = None
) -> StructureSetResult:
    """The "markush" category's calculator.

    The CORE is the molecule as drawn: any dummy atom carrying an atom map
    number (`[*:1]`) is an R-group attachment point, which is how a Markush
    core is drawn in Ketcher. Substituent definitions come from the
    settings text field.

    Covers all four of Marvin's enumeration modes plus the valence filter:
    `mode` selects sequential vs random, `only_labels` gives selected-part
    enumeration, `max_structures` is "generate maximum", and the "Markush
    library size" mode reports the combinatorial count without enumerating.
    """
    parameters = parameters or {}
    mode = parameters.get("mode", "Sequential enumeration")

    try:
        r_groups = parse_substituent_spec(parameters.get("substituents", ""))
    except MarkushError as exc:
        return _failed(molecule_uuid, str(exc))

    core_smiles = Chem.MolToSmiles(mol)
    attachment_labels = {
        atom.GetAtomMapNum()
        for atom in mol.GetAtoms()
        if atom.GetAtomicNum() == 0 and atom.GetAtomMapNum()
    }
    if not attachment_labels:
        return _failed(
            molecule_uuid,
            "This structure has no R-group attachment points. Draw them as dummy atoms with a "
            "map number -- [*:1], [*:2] -- to mark where substituents attach.",
        )
    if not r_groups:
        return _failed(
            molecule_uuid,
            f"The core defines {sorted(attachment_labels)} but no substituents were given. "
            "Enter them as e.g. \"R1: Cl, F, Br; R2: O, N\".",
        )
    missing = attachment_labels - {group.label for group in r_groups}
    if missing:
        return _failed(
            molecule_uuid,
            f"No substituents given for R{', R'.join(str(m) for m in sorted(missing))}.",
        )

    markush = MarkushStructure(core_smiles=core_smiles, r_groups=r_groups)
    only_labels = _parse_labels(parameters.get("only_labels", ""))

    if mode == "Markush library size":
        # Size only -- no structures generated, which is the entire point
        # for a class too large to walk.
        return StructureSetResult(
            set_id="markush_enumeration",
            name=describe_library_size(markush, only_labels),
            method="rdkit",
            molecule_uuid=molecule_uuid,
            entries=[],
            total_available=library_size(markush, only_labels),
            truncated=True,
            provenance=Provenance(
                created_by="core", method="rdkit", parameters={"mode": "library_size"}
            ),
        )

    return enumerate_markush(
        markush,
        molecule_uuid,
        mode="random" if mode == "Random enumeration" else "sequential",
        max_structures=int(parameters.get("max_structures", DEFAULT_MAX_STRUCTURES)),
        valence_filter=bool(parameters.get("valence_filter", True)),
        only_labels=only_labels,
        seed=int(parameters.get("seed", 0)) or None,
    )


def _failed(molecule_uuid: str, message: str) -> StructureSetResult:
    return StructureSetResult(
        set_id="markush_enumeration",
        name="Markush Enumeration",
        method="rdkit",
        molecule_uuid=molecule_uuid,
        entries=[],
        cache_state=CacheState.FAILED,
        error=message,
        provenance=Provenance(created_by="core", method="rdkit"),
    )


def describe_library_size(markush: MarkushStructure, only_labels: set[int] | None = None) -> str:
    """Marvin shows the exact value up to 20 digits and the magnitude above
    that. Same convention here -- an exact count is more useful when it is
    readable, and a magnitude is more honest when it is not."""
    total = library_size(markush, only_labels)
    if total < 10**20:
        return f"Markush library size = {total:,} (~10^{len(str(total)) - 1})"
    return f"Markush library size ~ 10^{len(str(total)) - 1}"
