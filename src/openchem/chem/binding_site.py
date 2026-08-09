"""Turn a co-crystallised ligand into a docking search box.

This is the step that makes a catalogue entry usable. A PDB id tells you
which protein; it does not tell you where on it to search, and a box in
the wrong place produces poses that score and mean nothing. The ligand
that was crystallised with the receptor answers that directly: it marks a
site that is real, occupied and druggable, which is why boxing the
reference ligand is the standard way to set up a redocking run.

The parsing is `pose_analysis.receptor_atoms_from_structure`, reused
rather than rewritten -- it already reads PDB and mmCIF through Open
Babel, and it already exposes `residue_name`, which is exactly the
chemical component id (`BF0`, `DZP`, `AZM`) a catalogue entry records.

MEASURED, NOT ASSUMED. Boxes are only as good as the poses they produce,
so this was checked by redocking: take the ligand that was crystallised
with the receptor, discard its coordinates, dock it back through the
derived box with real Vina, and see how far the result lands from where
crystallography put it. Run against the real installed Vina 1.2.7, with
each ligand's own SMILES fetched from RCSB rather than transcribed.

Re-measured as an A/B when `_single_copy` changed, three whole runs of
`benchmarks/docking/redock.py` -- one before, two after -- because the
change moves which COPY of a ligand gets boxed and a single run cannot
tell an improvement from Vina's own scatter:

    PDB   ligand  before   after      after
    1HSG  MK1     0.17 A   0.17 A   0.16 A   indinavir / HIV-1 protease
    2RH1  CAU     0.39 A   0.33 A   0.33 A   carazolol / beta-2 adrenergic
    1ERE  EST     0.50 A   0.46 A   0.48 A   estradiol / estrogen receptor
    8ZYO  XB7     0.56 A   0.55 A   0.52 A   astemizole / hERG
    4DKL  BF0     0.83 A   0.70 A   0.71 A   beta-FNA / mu-opioid
    4EY7  E20     0.69 A   0.37 A   0.39 A   donepezil / acetylcholinesterase
    3EML  ZMA     2.59 A   2.54 A   2.48 A   ZM241385 / adenosine A2A

All seven land in the same pocket in every arm. **The run-to-run scatter
is about 0.03 A**, which is what makes 4EY7 readable: 0.69 -> 0.37 is
twenty times the noise, and 4EY7 is one of the entries whose box moved to
a more buried copy. Everything else is unchanged or better by a margin
too small to claim. The seed is NOT pinned here -- `VinaDockingProvider`
passes `seed=None`, as the shipped app does -- so this measures the app's
real behaviour and the noise floor is measured rather than removed.

A2A is worth naming rather than averaging away: ZM241385 is long and
roughly linear, and a pose flipped end-for-end in the same pocket
displaces the centroid by several Angstrom while scoring well. That is a
limit of Vina's pose ranking, not of the box. **Its previously recorded
3.90 A does not reproduce** -- the before arm above, on unchanged code,
gives 2.59 A. Treat that old figure as one draw from a wide
distribution, not as a regression this change repaired.

`benchmarks/docking/redock.py` reruns the whole table.
"""

from __future__ import annotations

from dataclasses import dataclass

from openchem.chem.pose_analysis import (
    WATER_RESIDUE_NAMES,
    is_stripped_residue,
    receptor_atoms_from_structure,
)
from openchem.domain.docking import DockingBox

#: Added to each side of the ligand's own extent. A docked molecule needs
#: room to be bigger than the reference and to rotate within the site; a
#: box clipped to the reference's exact envelope can only reproduce it.
#: 4 A is the low end of common practice (4-5 A either side).
DEFAULT_PADDING = 4.0

#: No axis goes below this. A small reference ligand -- GABA is three
#: heavy atoms across -- would otherwise produce a box too tight for
#: anything drug-sized to enter, which is the failure this floor exists
#: for and the reason the GABA-A orthosteric entry is usable at all.
MINIMUM_SIZE = 16.0

#: And no axis above this. A box much larger than a binding site makes
#: Vina search volume it has no business searching -- slower, and the
#: extra volume is where spurious poses come from. Reached only by a
#: `ligand_code` that matches something disordered or repeated across the
#: structure, which is a signal worth surfacing rather than absorbing.
MAXIMUM_SIZE = 40.0


class BindingSiteError(Exception):
    """Raised when a ligand code names nothing in the structure."""


@dataclass(frozen=True)
class BindingSite:
    """A located binding site, plus what it was derived from.

    Carries `atom_count` and `extent` rather than only the box because
    they are how a user judges whether the box is sensible: 33 atoms
    spanning 12 A reads as a real drug-like ligand, while 3 atoms spanning
    2 A says the code matched an ion and the box is meaningless.

    `atom_count` counts ONE alternate location, in both formats. This
    paragraph previously recorded the opposite -- that mmCIF sources
    over-report because altlocs were filtered only for PDB, whose fixed
    columns make it a one-line slice -- and named 7B6W as the case: one
    59-atom ligand refined in two half-occupancy conformations, counted
    as 118. That limit is gone; `pose_analysis.filter_altlocs` handles
    mmCIF's loop layout too, reading the `label_alt_id` position from the
    header rather than assuming it. Re-measured on the same entry: 118
    raw `_atom_site` rows for T0B, every one carrying an altloc, and 59
    reported here.
    """

    ligand_code: str
    box: DockingBox
    atom_count: int
    extent: tuple[float, float, float]
    #: True when a floor or ceiling changed the size the ligand implied.
    size_was_clamped: bool = False
    #: Where the atoms of the copy that was boxed actually are.
    #:
    #: Carried so that WHICH COPY was chosen is an answer this returns
    #: rather than one a caller has to reproduce. `benchmarks/docking/`
    #: needs the crystal pose to measure a redocked one against, and it
    #: used to re-derive the copy by calling `_single_copy` again -- with
    #: different information, since it had no environment to judge burial
    #: from, so the benchmark could measure against a DIFFERENT copy than
    #: the one it had docked into. Same divergence class as
    #: `filter_altlocs` and `is_stripped_residue`, and silent in the same
    #: way: the shift would simply come out large and read as a bad box.
    ligand_positions: tuple[tuple[float, float, float], ...] = ()

    def describe(self) -> str:
        cx, cy, cz = self.box.center
        sx, sy, sz = self.box.size
        note = " (size clamped)" if self.size_was_clamped else ""
        return (
            f"{self.ligand_code}: {self.atom_count} atoms, "
            f"centre ({cx:.1f}, {cy:.1f}, {cz:.1f}), "
            f"box {sx:.0f}×{sy:.0f}×{sz:.0f} Å{note}"
        )


def box_from_ligand(
    structure_text: str,
    source_format: str,
    ligand_code: str,
    padding: float = DEFAULT_PADDING,
) -> BindingSite:
    """Locate `ligand_code` in the structure and box it.

    Raises `BindingSiteError` rather than returning an empty box when the
    code matches nothing: a silently-centred-on-origin box would dock into
    empty space and return poses that look like results.

    **Only ONE copy is boxed** when a structure holds several -- see
    `_single_copy`. A pentameric channel like 5-HT3A has the same ligand
    at five equivalent subunit interfaces, and boxing all five puts the
    centre on the pore axis, in the middle of the protein, where no site
    is. One real site beats the centroid of five.
    """
    code = ligand_code.strip().upper()
    parsed = receptor_atoms_from_structure(structure_text, source_format)
    atoms = [atom for atom in parsed if atom.residue_name.strip().upper() == code]
    if not atoms:
        raise BindingSiteError(
            f"No residue {code!r} in this structure — it may be a different "
            "deposit revision, or the ligand may be part of the polymer "
            "rather than a separate component."
        )

    # The rest of the structure, which `_single_copy` needs to tell a
    # buried copy from a surface one. Waters are excluded: a ligand's own
    # solvation shell says nothing about whether it is in a pocket, and
    # ordered waters are far more numerous around exposed sites.
    environment = [
        atom
        for atom in parsed
        if atom.residue_name.strip().upper() not in (code, *WATER_RESIDUE_NAMES)
    ]
    atoms = _single_copy(atoms, environment)
    xs = [a.position[0] for a in atoms]
    ys = [a.position[1] for a in atoms]
    zs = [a.position[2] for a in atoms]
    extent = (max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))
    center = (
        (max(xs) + min(xs)) / 2.0,
        (max(ys) + min(ys)) / 2.0,
        (max(zs) + min(zs)) / 2.0,
    )
    # Midpoint of the bounding box, not the mean of the atom positions.
    # The mean is pulled toward whichever end of the ligand carries more
    # atoms -- a long molecule with a bulky head ends up boxed off-centre,
    # with its tail against the wall.
    raw = tuple(span + 2.0 * padding for span in extent)
    size = tuple(min(max(value, MINIMUM_SIZE), MAXIMUM_SIZE) for value in raw)
    return BindingSite(
        ligand_code=code,
        box=DockingBox(center=center, size=size),  # type: ignore[arg-type]
        atom_count=len(atoms),
        extent=extent,
        size_was_clamped=any(abs(a - b) > 1e-9 for a, b in zip(raw, size, strict=True)),
        ligand_positions=tuple(tuple(a.position) for a in atoms),  # type: ignore[misc]
    )


#: How close a receptor atom must be to count as packed against a ligand
#: copy. 4.5 A is `pose_analysis.HYDROPHOBIC_CUTOFF` -- the distance this
#: app already calls a contact -- rather than a number invented here.
_BURIAL_CUTOFF = 4.5


def _single_copy(atoms: list, environment: list) -> list:
    """One copy of the ligand, when the structure holds several.

    `environment` is REQUIRED rather than defaulting to empty, and that is
    a deliberate barb. `benchmarks/docking/redock.py` used to call this a
    second time to recover the copy the box had been placed on; with no
    receptor to weigh burial against, a default would have let that call
    keep working while quietly answering a different question. A
    TypeError is the better outcome -- see `BindingSite.ligand_positions`,
    which is what that caller should use instead.

    **Copies are keyed by (chain, residue number), and the chain half is
    the part that matters.** Keying on residue number alone looks
    sufficient and is not: crystallographers routinely give every copy the
    SAME number and distinguish them only by chain. 1ERE holds six
    estradiols, all numbered 600, in chains A-F. Merging them produced a
    "ligand" of 120 atoms spanning the entire dimer, whose bounding-box
    centre sits in solvent between the copies -- a 40x40x40 box aimed at
    nothing, which still returns poses and scores. Six entries in the
    catalogue were doing this before the chain was carried through.

    The largest copy wins, since a partly-resolved one is a worse site
    definition than a complete one.

    **THE TIE-BREAK IS BURIAL, AND IT MUST NOT BE A LABEL.** Ties are the
    normal case, not the exotic one -- equivalent copies have equal atom
    counts by construction -- so the tie-break decides most multi-copy
    structures, and the labels are not comparable across formats. Open
    Babel hands us `label_asym_id` from mmCIF and the AUTHOR chain from
    PDB, and it reports no residue number at all from mmCIF (measured:
    3HS4's three acetazolamides come back as chains D/E/F numbered 0,
    against A/701, A/702, A/703 from the same deposit as PDB). Sorting on
    those picked a DIFFERENT PHYSICAL COPY depending only on which format
    RCSB happened to serve:

        3HS4  AZM  mmCIF boxed a copy 16.62 A from the catalytic zinc
                   PDB boxed the one 1.94 A from it
                   the two boxes are 17.96 A apart
        8EF5  7V7  36.08 A apart, and the formats order the two copies
                   in opposite directions (mmCIF H/N vs PDB R/M)

    **And one of those copies was simply wrong.** 3HS4 is carbonic
    anhydrase II: acetazolamide binds by coordinating the catalytic zinc,
    so of its three copies exactly one is the pharmacology and the other
    two are surface-bound crystallisation artefacts. Counting neighbours
    separates them cleanly, and picks the right one:

        copy       protein atoms within 4.5 A     nearest Zn
        A/701                              45        1.94 A   <- the site
        A/703                              34       16.62 A
        A/702                              22       17.31 A

    So this is not merely a determinism fix. A box is only as good as the
    copy it was placed on, and "most buried" is a statement about the
    structure rather than about how a depositor named its chains.

    Coordinates are the one thing the two formats agree on exactly --
    verified atom for atom to three decimals on both entries above -- so
    a geometric criterion is reproducible where a label is not. The final
    tie-break is the copy centroid, purely so that a genuine draw (two
    equally buried copies of equal size) still resolves the same way every
    time rather than on dict order.
    """
    copies: dict[tuple[str, int], list] = {}
    for atom in atoms:
        copies.setdefault((atom.chain, atom.residue_number), []).append(atom)
    if len(copies) <= 1:
        return atoms

    neighbours = _NeighbourGrid(environment or (), _BURIAL_CUTOFF)

    def rank(key: tuple[str, int]) -> tuple:
        copy = copies[key]
        centroid = tuple(
            sum(a.position[i] for a in copy) / len(copy) for i in range(3)
        )
        # Negated centroid so `max` takes the numerically smallest, which
        # is an arbitrary but fixed choice -- only its stability matters.
        return (len(copy), neighbours.count_near(copy), tuple(-v for v in centroid))

    return copies[max(copies, key=rank)]


class _NeighbourGrid:
    """Counts environment atoms near a set of positions, in linear time.

    A plain double loop is O(copies x ligand x receptor) and a receptor
    can be 70,000 atoms, which turns placing a box into seconds of work
    for a question about a dozen atoms. Bucketing by a cutoff-sized cell
    means each ligand atom looks at the 27 cells around it and nothing
    else.
    """

    def __init__(self, environment, cutoff: float) -> None:
        self._cutoff = cutoff
        self._cutoff_squared = cutoff * cutoff
        self._cells: dict[tuple[int, int, int], list] = {}
        for atom in environment:
            self._cells.setdefault(self._cell(atom.position), []).append(atom.position)

    def _cell(self, position) -> tuple[int, int, int]:
        return tuple(int(v // self._cutoff) for v in position)  # type: ignore[return-value]

    def count_near(self, copy) -> int:
        """How many environment atoms lie within the cutoff of ANY atom of
        `copy` -- each counted once, however many contacts it makes, so a
        copy is not rewarded for being large twice over."""
        seen: set[tuple[float, float, float]] = set()
        for atom in copy:
            cx, cy, cz = self._cell(atom.position)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for dz in (-1, 0, 1):
                        for other in self._cells.get((cx + dx, cy + dy, cz + dz), ()):
                            if other in seen:
                                continue
                            if (
                                (other[0] - atom.position[0]) ** 2
                                + (other[1] - atom.position[1]) ** 2
                                + (other[2] - atom.position[2]) ** 2
                            ) <= self._cutoff_squared:
                                seen.add(other)
        return len(seen)


def ligand_codes_in(structure_text: str, source_format: str) -> list[str]:
    """Candidate ligand codes present, largest first.

    For structures the catalogue does not cover: a user with their own PDB
    still needs to know what is in it before they can box anything, and
    "list what is bound" is the question RCSB's own page answers slowly.

    Protein residues and waters are excluded via the same tables receptor
    preparation uses -- without that this returns ILE, LEU, PHE and every
    other amino acid, which is technically "the residue codes present" and
    useless as an answer to "what is bound". Largest first because a real
    ligand outweighs the ions and buffer components it shares a file with.
    """
    counts: dict[str, int] = {}
    for atom in receptor_atoms_from_structure(structure_text, source_format):
        name = atom.residue_name.strip().upper()
        # Not-protein AND not-water. `is_stripped_residue(name, True, True)`
        # alone answers "would prep remove this", which is True for water
        # as well -- and a structure's thousand waters would then bury
        # every real ligand at the top of the list.
        if not name or name in WATER_RESIDUE_NAMES:
            continue
        if is_stripped_residue(name, False, True):
            counts[name] = counts.get(name, 0) + 1
    return sorted(counts, key=lambda code: (-counts[code], code))
