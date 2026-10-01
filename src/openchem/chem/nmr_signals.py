from __future__ import annotations

import math
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


def _couplings_for(spectrum: SpectrumResult, group: list[int], partners: set[int]) -> list[float]:
    """Real J values only -- the couplings ORCA's "NMR + Spin-Spin Coupling"
    calc type produced. Empty for every other source rather than estimated
    from typical-value tables.

    **Scoped to `partners`, never every value ORCA's full matrix reports
    touching a group member.** ORCA computes a coupling constant between
    essentially every pair of magnetically active nuclei it's asked for --
    confirmed live on isopropanol: its 6H methyl doublet's raw matrix
    entries included ~180 Hz one-bond C-H couplings (a completely
    different kind of information, irrelevant to a 1H multiplet pattern)
    and couplings to atoms several bonds away, alongside the real H-H
    values the "d" in the table actually describes. `partners` is
    `build_nmr_signals`'s own `_coupling_partners(mol, group[0], ...)` --
    the SAME geminal/vicinal set the structural multiplicity prediction
    already uses -- so a signal's reported J values describe exactly the
    splitting its own multiplicity letter claims, not a grab-bag. Empty
    `partners` (every element but H) returns nothing, by construction.

    `couplings` lives on the `NMRSpectrumResult` subclass, not the
    `SpectrumResult` base this module is written against (a future IR/MS
    producer has no use for it), hence `getattr` -- the same access this
    field already gets in `QuantumChemistryPanel._update_correlation_tabs`
    (which reads it for the 2D correlation cross-peaks instead, a
    different and legitimate use: HSQC/HMBC/COSY want every pairwise
    coupling, not one signal's own splitting partners).
    """
    if not partners:
        return []
    couplings = getattr(spectrum, "couplings", None) or {}
    own_group = set(group)
    values = {
        round(hz, 2)
        for (atom_a, atom_b), hz in couplings.items()
        if (atom_a in own_group) != (atom_b in own_group)
        and (atom_a in partners or atom_b in partners)
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

    signals = []
    for group in groups:
        # The SAME partner set for both multiplicity and real J, computed
        # once: `_coupling_partners` is what `_multiplicity_for` already
        # uses for its n+1 structural prediction (geminal + vicinal
        # protons only, for ONE representative atom of the group), and
        # `coupling_hz` below is scoped to exactly those atoms too --
        # never ORCA's FULL coupling matrix for the group, which also
        # reports one-bond heteronuclear couplings (confirmed live:
        # isopropanol's 6H methyl doublet picked up ~180 Hz C-H values
        # alongside the real H-H ones before this existed) and couplings
        # to atoms several bonds away that the structural prediction never
        # counted as a splitting partner either. Empty for every element
        # but H, matching the heteronuclear-decoupled-singlet convention
        # the multiplicity branch below already states explicitly.
        partners = set(_coupling_partners(mol, group[0], set(group))) if element == "H" else set()
        signals.append(
            NMRSignal(
                shift=sum(spectrum.values[index] for index in group) / len(group),
                atom_indices=list(group),
                integration=len(group),
                # Multiplicity is a 1H concept here: routine 13C (and other
                # heteronuclear) spectra are broadband proton-decoupled, so
                # every line is a singlet. Stated explicitly rather than
                # left to fall out of _multiplicity_for finding no
                # partners, which it would for the wrong reason (a heavy
                # atom has no single "parent").
                multiplicity=(
                    _multiplicity_for(mol, group, group_of_atom)
                    if element == "H"
                    else _MULTIPLICITY_BY_LINE_COUNT[1]
                ),
                coupling_hz=_couplings_for(spectrum, group, partners),
                element=element,
            )
        )
    return sorted(signals, key=lambda signal: signal.shift, reverse=True)


# Residual solvent 1H/13C shifts, ppm, from Gottlieb, Kotlyar & Nudelman
# (J. Org. Chem. 1997, 62, 7512) -- the reference table every lab uses.
# Published values, not predictions, so they are exact in a way nothing
# else on this screen is.
RESIDUAL_SOLVENT_PEAKS: dict[str, dict[str, float]] = {
    "CDCl3": {"H": 7.26, "C": 77.16},
    "DMSO-d6": {"H": 2.50, "C": 39.52},
    "D2O": {"H": 4.79},
    "Acetone-d6": {"H": 2.05, "C": 29.84},
    "CD3OD": {"H": 3.31, "C": 49.00},
    "C6D6": {"H": 7.16, "C": 128.06},
    "CD3CN": {"H": 1.94, "C": 1.32},
}

# The common spectrometer field strengths, in MHz for 1H. Frequency does
# not move a chemical shift -- that is the entire point of the ppm scale --
# but it does set how far apart a multiplet's lines fall in ppm, which is
# why the same compound looks resolved at 600 MHz and a blur at 60.
SPECTROMETER_FREQUENCIES_MHZ = (60.0, 100.0, 200.0, 300.0, 400.0, 500.0, 600.0, 800.0)
DEFAULT_FREQUENCY_MHZ = 400.0

# Gyromagnetic ratio relative to 1H: a "400 MHz" spectrometer observes
# carbon near 100 MHz, so a 13C multiplet's lines are ~4x further apart in
# ppm than a proton multiplet with the same J in Hz.
_RELATIVE_FREQUENCY = {"H": 1.0, "C": 0.2514, "F": 0.9407, "P": 0.4048, "N": 0.0721}


def _binomial_row(n: int) -> list[float]:
    row = [1.0]
    for k in range(n):
        row.append(row[-1] * (n - k) / (k + 1))
    return row


def multiplet_lines(
    signal: NMRSignal, frequency_mhz: float = DEFAULT_FREQUENCY_MHZ
) -> list[tuple[float, float]]:
    """(ppm, relative intensity) for each line of a first-order multiplet.

    A multiplet's lines sit J Hz apart, and Hz converts to ppm by dividing
    by the observation frequency -- so this needs a real spectrometer
    frequency and a real J, and returns a single line when either is
    missing rather than inventing a splitting.

    Intensities are the binomial row, which is the first-order
    approximation: it is exact when the coupled nuclei are equivalent and
    the shift difference is large compared with J, and progressively wrong
    ("roofing") as they approach each other. Second-order line shapes
    would need a full spin-Hamiltonian simulation, which this is not.
    """
    lines_expected = next(
        (count for count, letter in _MULTIPLICITY_BY_LINE_COUNT.items() if letter == signal.multiplicity),
        1,
    )
    if lines_expected <= 1 or not signal.coupling_hz or frequency_mhz <= 0:
        return [(signal.shift, 1.0)]

    observation_mhz = frequency_mhz * _RELATIVE_FREQUENCY.get(signal.element, 1.0)
    if observation_mhz <= 0:
        return [(signal.shift, 1.0)]

    # One J for the whole multiplet: an n+1 pattern by definition comes
    # from n EQUIVALENT partners sharing one coupling constant. A signal
    # with several distinct J values is reported as "m" upstream and takes
    # the single-line path above.
    spacing_ppm = signal.coupling_hz[0] / observation_mhz
    neighbours = lines_expected - 1
    intensities = _binomial_row(neighbours)
    total = sum(intensities)
    return [
        (signal.shift + (neighbours / 2.0 - index) * spacing_ppm, intensity / total)
        for index, intensity in enumerate(intensities)
    ]


# HWHM of the Lorentzian each multiplet line is convolved with in "smooth"
# display mode. Not a measured linewidth -- real ones vary with shimming and
# field -- just narrow enough that two signals more than a few tenths of a
# ppm apart stay resolved, matching how the predicted shifts are normally
# spaced.
DEFAULT_LORENTZIAN_HWHM_PPM = 0.012


def lorentzian_envelope(
    signals: list[NMRSignal],
    xs: list[float],
    frequency_mhz: float = DEFAULT_FREQUENCY_MHZ,
    hwhm_ppm: float = DEFAULT_LORENTZIAN_HWHM_PPM,
) -> list[float]:
    """Sum, at each point in `xs`, of a unit-area Lorentzian centred on every
    `multiplet_lines()` position, weighted so each signal's own lines
    together integrate (over all ppm, not just the sampled `xs`) to that
    signal's `integration` -- the same quantity stick mode turns into a
    relative peak height. Two signals of integration 1 and 3 therefore
    enclose area in a 1:3 ratio under this curve, exactly as their stick
    heights would be 1:3 of the tallest signal.

    `xs` only decides where the curve is SAMPLED for display; a signal whose
    tails fall outside `xs` still had its full weight placed on the curve,
    just not drawn there.
    """
    ys = [0.0] * len(xs)
    for signal in signals:
        for line_shift, intensity in multiplet_lines(signal, frequency_mhz):
            weight = signal.integration * intensity
            for index, x in enumerate(xs):
                dx = x - line_shift
                ys[index] += weight * hwhm_ppm / (math.pi * (dx * dx + hwhm_ppm * hwhm_ppm))
    return ys
