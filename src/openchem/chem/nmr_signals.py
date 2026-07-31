from __future__ import annotations

from dataclasses import dataclass, field

from rdkit import Chem

from openchem.domain.scientific_result import SpectrumResult

# n+1 rule: n equivalent coupling partners split a signal into n+1 lines.
# Abbreviations are Marvin's own (singlet through septet); anything beyond a
# septet, or any signal coupling to more than one distinct partner group, is
# reported as "m" -- see _multiplicity_for's docstring for why that isn't a
# cop-out but the only honest first-order answer.
_MULTIPLICITY_BY_LINE_COUNT = {1: "s", 2: "d", 3: "t", 4: "q", 5: "quint", 6: "sx", 7: "sp"}
_COMPLEX_MULTIPLET = "m"


@dataclass(frozen=True, kw_only=True)
class NMRSignal:
    """One line of the signal list a chemist actually reads, as opposed to
    the raw per-nucleus values an `NMRSpectrumResult` carries: symmetry-
    equivalent nuclei collapsed into a single peak with an integration.

    `atom_indices` is what makes the spectrum interactive -- it is the
    complete set of atoms contributing to this peak, so a peak click can
    highlight them and a 3D atom click can find its owning signal. Indices
    are into whichever mol was passed to `build_nmr_signals`, which must be
    the same numbering the source `NMRSpectrumResult` used (see
    `align_mol_to_spectrum`).
    """

    shift: float  # ppm, the group's mean value
    atom_indices: list[int]
    integration: int  # nuclei contributing; == len(atom_indices)
    multiplicity: str  # "s"|"d"|"t"|"q"|"quint"|"sx"|"sp"|"m"
    coupling_hz: list[float] = field(default_factory=list)
    element: str = "H"


def align_mol_to_spectrum(mol: Chem.Mol, spectrum: SpectrumResult) -> Chem.Mol:
    """Returns a mol whose atom indices line up with `spectrum.values`.

    The empirical estimator runs on `Chem.AddHs(mol)` while its caller holds
    the editor molblock (implicit hydrogens), so proton shifts are keyed to
    indices that don't exist in the caller's own mol; an ORCA result, built
    from a real conformer, already has explicit hydrogens and needs no such
    fixup. Tested by index range rather than by "does this molblock have H
    atoms" because the index range is the invariant that actually has to
    hold -- `AddHs` appends and never reorders, so heavy-atom indices are
    identical either way.
    """
    if not spectrum.values or max(spectrum.values) < mol.GetNumAtoms():
        return mol
    return Chem.AddHs(mol)


def _heavy_parent(mol: Chem.Mol, hydrogen_index: int) -> Chem.Atom | None:
    """The one heavy atom a hydrogen hangs off. `None` for anything with a
    different neighbour count (a bare proton, or a caller passing a heavy
    atom index) rather than silently picking neighbour zero."""
    neighbors = mol.GetAtomWithIdx(hydrogen_index).GetNeighbors()
    return neighbors[0] if len(neighbors) == 1 else None


def depiction_atoms(mol: Chem.Mol, signal: NMRSignal) -> list[int]:
    """The atoms a 2D depiction should label/highlight for `signal`.

    A proton's shift is drawn on the heavy atom bearing it -- where every
    published assignment puts it, and the only place it can go: the 2D
    depiction is drawn from the editor molblock, whose hydrogens are
    implicit and therefore have no atom index to attach a label to. Heavy
    atom indices are shared between that molblock and the `AddHs` mol the
    shifts are keyed to, since `AddHs` appends without reordering.
    """
    atoms: list[int] = []
    for index in signal.atom_indices:
        if index >= mol.GetNumAtoms():
            continue
        atom = mol.GetAtomWithIdx(index)
        if atom.GetAtomicNum() != 1:
            atoms.append(index)
            continue
        parent = _heavy_parent(mol, index)
        if parent is not None and parent.GetIdx() not in atoms:
            atoms.append(parent.GetIdx())
    return atoms


def _stereo_keys(mol: Chem.Mol) -> set[tuple[str, int]]:
    return {(str(element.type), element.centeredOn) for element in Chem.FindPotentialStereo(mol)}


def _substitute_hydrogen(mol: Chem.Mol, hydrogen_index: int) -> Chem.Mol | None:
    """The classic substitution test's first half: swap one hydrogen for a
    different atom (fluorine, monovalent so the valence stays satisfied) and
    let RDKit perceive the resulting stereochemistry."""
    editable = Chem.RWMol(mol)
    editable.GetAtomWithIdx(hydrogen_index).SetAtomicNum(9)
    substituted = editable.GetMol()
    try:
        Chem.SanitizeMol(substituted)
    except Exception:  # noqa: BLE001 - a substitution that won't sanitize is
        # simply not a usable probe; treat it as "can't tell" rather than
        # failing the whole spectrum.
        return None
    return substituted


def are_diastereotopic(mol: Chem.Mol, hydrogen_a: int, hydrogen_b: int) -> bool:
    """The substitution test, done properly: replace one of the two protons
    and ask what kind of stereochemistry that creates.

    Two shortcuts were tried first and both are wrong, which is why this
    does the full analysis:

    - `CanonicalRankAtoms(includeChirality=True)` still ranks ibuprofen's
      benzylic CH2 protons identically. Diastereotopicity is not a graph-
      symmetry property, so no canonical ranking will ever find it.
    - "substitute and compare canonical SMILES" reports *everything* as
      diastereotopic, including ethylbenzene's genuinely equivalent CH2,
      because RDKit faithfully records an arbitrary chiral tag even on a
      centre that isn't stereogenic.

    What actually distinguishes the two cases is what the substitution
    products are to each other:

    - No new stereo element -> the products are identical (homotopic).
    - A new tetrahedral centre and nothing else stereogenic in the molecule
      -> the two products are mirror images (enantiotopic, equivalent in an
      achiral solvent). This is ethylbenzene: substituting its CH2 does make
      that carbon stereogenic, which is exactly why "is it stereogenic?"
      alone is not a sufficient test.
    - A new tetrahedral centre *plus* another stereogenic element elsewhere
      -> the products are diastereomers. This is ibuprofen: the alpha
      stereocentre is what makes its benzylic protons inequivalent.
    - A new stereogenic double bond -> E and Z are diastereomers by
      definition, so no second element is needed (styrene's vinyl protons).
    """
    before = _stereo_keys(mol)
    substituted = _substitute_hydrogen(mol, hydrogen_a)
    if substituted is None:
        return False
    after = list(Chem.FindPotentialStereo(substituted))
    created = [e for e in after if (str(e.type), e.centeredOn) not in before]
    if not created:
        return False
    if any(str(element.type).startswith("Bond_") for element in created):
        return True
    return any((str(e.type), e.centeredOn) in before for e in after)


def _split_diastereotopic(mol: Chem.Mol, group: list[int]) -> list[list[int]]:
    """Splits a geminal proton pair into two signals when they are
    diastereotopic. Deliberately narrow: only a group that is exactly the
    two protons of one CH2 is considered.

    A group spanning several symmetry-equivalent CH2 groups (say a molecule
    with two equivalent diastereotopic methylenes) would also split in
    reality, but doing that correctly means deciding *which* proton of
    carbon 1 pairs with which proton of carbon 2 -- a correspondence the
    canonical ranking deliberately doesn't provide. Splitting them
    arbitrarily would put protons in the same signal on no real basis, so
    those stay grouped, which under-splits rather than mis-splits.
    """
    if len(group) != 2:
        return [group]
    parent_a = _heavy_parent(mol, group[0])
    parent_b = _heavy_parent(mol, group[1])
    if parent_a is None or parent_b is None or parent_a.GetIdx() != parent_b.GetIdx():
        return [group]
    if not are_diastereotopic(mol, group[0], group[1]):
        return [group]
    return [[group[0]], [group[1]]]


def _coupling_partners(mol: Chem.Mol, representative: int, own_group: set[int]) -> list[int]:
    """Protons that split `representative`: geminal (same heavy atom) and
    vicinal (an adjacent heavy atom), excluding its own equivalence group.

    Counted for ONE representative proton rather than pooled over the whole
    group: a para-disubstituted ring's two equivalent aromatic protons each
    couple to one ortho neighbour, but pooling both protons' partners would
    count two and report a triplet where a doublet is correct.
    """
    parent = _heavy_parent(mol, representative)
    if parent is None:
        return []
    partners: list[int] = []
    for heavy in [parent, *(n for n in parent.GetNeighbors() if n.GetAtomicNum() != 1)]:
        for neighbor in heavy.GetNeighbors():
            index = neighbor.GetIdx()
            if neighbor.GetAtomicNum() == 1 and index != representative and index not in own_group:
                partners.append(index)
    return partners


def _multiplicity_for(mol: Chem.Mol, group: list[int], group_of_atom: dict[int, int]) -> str:
    """First-order n+1 multiplicity.

    Coupling to more than one distinct group of protons is reported as "m",
    not as a single letter: a proton coupled to one partner with J1 and
    another with J2 gives a doublet of doublets, and calling that a
    "triplet" would assert a line pattern the molecule doesn't have. Real
    line-shape simulation (which is how Marvin arrives at letters like the
    "sx" it reports for ibuprofen's benzylic protons) needs the actual J
    values, which no predictor wired up here supplies.
    """
    own_group = set(group)
    partners = _coupling_partners(mol, group[0], own_group)
    if not partners:
        return _MULTIPLICITY_BY_LINE_COUNT[1]
    partner_groups = {group_of_atom.get(index, -1) for index in partners}
    if len(partner_groups) > 1:
        return _COMPLEX_MULTIPLET
    return _MULTIPLICITY_BY_LINE_COUNT.get(len(partners) + 1, _COMPLEX_MULTIPLET)


def _couplings_for(spectrum: SpectrumResult, group: list[int]) -> list[float]:
    """Real J values only -- the couplings ORCA's "NMR + Spin-Spin Coupling"
    calc type produced. Empty for every other source rather than estimated
    from typical-value tables.

    `couplings` lives on the `NMRSpectrumResult` subclass, not the
    `SpectrumResult` base this module is written against (a future IR/MS
    producer has no use for it), hence `getattr` -- the same access this
    field already gets in `QuantumChemistryPanel._update_correlation_tabs`.
    """
    couplings = getattr(spectrum, "couplings", None) or {}
    own_group = set(group)
    values = {
        round(hz, 2)
        for (atom_a, atom_b), hz in couplings.items()
        if (atom_a in own_group) != (atom_b in own_group)
    }
    return sorted(values, reverse=True)


def build_nmr_signals(
    mol: Chem.Mol, spectrum: SpectrumResult, element: str = "H"
) -> list[NMRSignal]:
    """Collapses `spectrum`'s per-nucleus values into a chemist-readable
    signal list for one element, ordered by descending shift (NMR
    convention).

    `mol` must use the same atom numbering as `spectrum` -- pass it through
    `align_mol_to_spectrum` first if it came from an editor molblock.

    Equivalence comes from `Chem.CanonicalRankAtoms(breakTies=False)`, which
    reproduces 8 of the 9 groups MarvinSketch reports for ibuprofen exactly;
    the 9th is the diastereotopic benzylic split `_split_diastereotopic`
    adds. Note that when a split does happen, both resulting signals carry
    the same shift unless the underlying predictor distinguishes them --
    the *inequivalence* is a structural fact this can establish, the two
    different shift values are a prediction it cannot invent.
    """
    if not spectrum.values:
        return []

    selected = [
        index
        for index in spectrum.values
        if spectrum.elements.get(index, "") == element and index < mol.GetNumAtoms()
    ]
    if not selected:
        return []

    ranks = list(Chem.CanonicalRankAtoms(mol, breakTies=False))
    by_rank: dict[int, list[int]] = {}
    for index in sorted(selected):
        by_rank.setdefault(ranks[index], []).append(index)

    groups: list[list[int]] = []
    for _rank, group in sorted(by_rank.items()):
        groups.extend(_split_diastereotopic(mol, group) if element == "H" else [group])

    # Assigned after splitting so a diastereotopic partner counts as a
    # distinct coupling partner (geminal coupling is real and observed).
    group_of_atom = {index: number for number, group in enumerate(groups) for index in group}

    signals = [
        NMRSignal(
            shift=sum(spectrum.values[index] for index in group) / len(group),
            atom_indices=list(group),
            integration=len(group),
            # Multiplicity is a 1H concept here: routine 13C (and other
            # heteronuclear) spectra are broadband proton-decoupled, so every
            # line is a singlet. Stated explicitly rather than left to fall
            # out of _multiplicity_for finding no partners, which it would
            # for the wrong reason (a heavy atom has no single "parent").
            multiplicity=(
                _multiplicity_for(mol, group, group_of_atom)
                if element == "H"
                else _MULTIPLICITY_BY_LINE_COUNT[1]
            ),
            coupling_hz=_couplings_for(spectrum, group),
            element=element,
        )
        for group in groups
    ]
    return sorted(signals, key=lambda signal: signal.shift, reverse=True)
