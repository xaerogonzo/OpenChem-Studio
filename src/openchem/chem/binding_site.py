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
each ligand's own SMILES fetched from RCSB rather than transcribed:

    PDB   ligand  affinity   centroid shift from the crystal pose
    1HSG  MK1     -10.5       0.18 A    indinavir / HIV-1 protease
    2RH1  CAU     -10.1       0.35 A    carazolol / beta-2 adrenergic
    1ERE  EST     -10.8       0.49 A    estradiol / estrogen receptor
    8ZYO  XB7     -12.3       0.53 A    astemizole / hERG
    4DKL  BF0      -8.4       0.71 A    beta-FNA / mu-opioid
    4EY7  E20     -11.1       0.73 A    donepezil / acetylcholinesterase
    3EML  ZMA      -8.9       3.90 A    ZM241385 / adenosine A2A

Six of seven inside 0.75 A is the pocket being found essentially exactly.
The A2A outlier is worth naming rather than averaging away: ZM241385 is
long and roughly linear, and a pose flipped end-for-end in the same
pocket displaces the centroid by several Angstrom while scoring well.
That is a limit of Vina's pose ranking, not of the box -- the box put it
in the right place, and something has to choose among what is found there.

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
    atoms = [
        atom
        for atom in receptor_atoms_from_structure(structure_text, source_format)
        if atom.residue_name.strip().upper() == code
    ]
    if not atoms:
        raise BindingSiteError(
            f"No residue {code!r} in this structure — it may be a different "
            "deposit revision, or the ligand may be part of the polymer "
            "rather than a separate component."
        )

    atoms = _single_copy(atoms)
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
    )


def _single_copy(atoms: list) -> list:
    """One copy of the ligand, when the structure holds several.

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
    definition than a complete one, with the (chain, number) key breaking
    ties so the same structure always yields the same box.
    """
    copies: dict[tuple[str, int], list] = {}
    for atom in atoms:
        copies.setdefault((atom.chain, atom.residue_number), []).append(atom)
    if len(copies) <= 1:
        return atoms
    key = max(copies, key=lambda k: (len(copies[k]), k[0], -k[1]))
    return copies[key]


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
