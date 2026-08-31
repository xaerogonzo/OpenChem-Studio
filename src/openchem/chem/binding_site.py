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


#: Beyond this, a box centre is reported as being somewhere other than the
#: reference site. Derived rather than chosen: `MINIMUM_SIZE` is 16 A, so
#: half of it is the furthest a centre can move while the box still covers
#: the site's own middle. A box offset by more than that has stopped
#: containing what the reference ligand marked.
REFERENCE_SITE_TOLERANCE = MINIMUM_SIZE / 2.0


@dataclass(frozen=True)
class BoxPlacement:
    """Where a search box sits relative to what the structure says is there.

    Reported BEFORE a run, so somebody can see that a box is nowhere near
    the annotated site while there is still time not to run it. The failure
    this exists for produces no error at all: a box 55 A off site still
    clips protein, still returns nine poses, and still prints affinities to
    two decimal places.

    **THIS CLASSIFIES; IT DOES NOT DECIDE.** `far_from_reference_site` is
    evidence that a run did not sample the annotated site -- not a verdict
    that the user was wrong. Blind docking and allosteric sites are real
    uses, and a distant box is the intended experiment for both, which is
    why nothing here refuses anything.
    """

    #: Atoms of the SOURCE structure whose coordinates fall inside the box,
    #: as `pose_analysis.receptor_atoms_from_structure` reads it -- the
    #: module's own parser, so this cannot drift from `box_from_ligand`.
    #:
    #: **NOT the prepared-receptor count**, and the difference is the point.
    #: `docking_providers._require_atoms_in_box` deliberately counts the
    #: PREPARED PDBQT, after altloc filtering, chain exclusion, residue
    #: stripping and hydrogen addition, because it is the last check before
    #: Vina and must describe exactly what Vina receives. This one runs
    #: before any of that has happened, so it can warn while the user can
    #: still act. Two questions at two times; neither replaces the other,
    #: and the two numbers legitimately differ.
    atom_count: int

    #: The code that was consulted, whether or not it resolved.
    reference_site_code: str | None

    #: The reference site's own box, carried so that "why does it say
    #: 55 A?" is answerable without recomputing it.
    reference_site_box: DockingBox | None

    #: Why a supplied code did not resolve. See the class note below.
    reference_site_error: str | None

    #: CENTRE-TO-CENTRE Euclidean distance, in Angstrom, between the box
    #: being judged and the reference site's box. **Never a minimum
    #: distance between box volumes** -- two boxes can overlap and still
    #: report a large value here.
    site_distance_a: float | None

    #: `no_reference_site` covers BOTH "nothing to compare against" and "a
    #: code was given and could not be located", because neither yields a
    #: distance. `reference_site_error` is what tells them apart, and they
    #: need different words: one says nothing is wrong, the other says
    #: something is and names a likely cause.
    relationship: str

    def describe(self) -> str:
        if self.relationship == "no_reference_site":
            if self.reference_site_error is not None:
                return (
                    f"This receptor should have a {self.reference_site_code} site, but it "
                    f"could not be located: {self.reference_site_error} The search box holds "
                    f"{self.atom_count} receptor atoms."
                )
            return (
                "No annotated binding site for this receptor, so this box is user-defined. "
                f"It holds {self.atom_count} receptor atoms."
            )
        assert self.site_distance_a is not None
        if self.relationship == "at_reference_site":
            return (
                f"Search box is on the {self.reference_site_code} site "
                f"({self.site_distance_a:.1f} A from its centre) and holds "
                f"{self.atom_count} receptor atoms."
            )
        return (
            f"Search box is {self.site_distance_a:.1f} A from the "
            f"{self.reference_site_code} site and holds {self.atom_count} receptor atoms. "
            "Docking will run; use Derive from ligand to box the annotated site instead."
        )


def max_heavy_atom_extent(mol) -> float | None:
    """The largest distance between any two heavy atoms of a 3D conformer, in
    Angstrom, or None when the molecule carries no conformer.

    Heavy atoms only: hydrogens add roughly a bond length at each end and
    Vina's rigid PDBQT merges the nonpolar ones anyway, so counting them would
    inflate the number against a box that does not care about them.

    Separated from the predicate below because it needs RDKit and a real
    conformer, where the predicate is arithmetic over two numbers and can be
    tested on constructed values -- the same two-level split `ui/visual_check`
    uses, for the same reason: a predicate that reaches for a toolkit becomes a
    test about the machine.
    """
    if mol is None or mol.GetNumConformers() == 0:
        return None
    conformer = mol.GetConformer()
    positions = [
        conformer.GetAtomPosition(atom.GetIdx())
        for atom in mol.GetAtoms()
        if atom.GetAtomicNum() > 1
    ]
    if len(positions) < 2:
        return 0.0
    return max(
        ((a.x - b.x) ** 2 + (a.y - b.y) ** 2 + (a.z - b.z) ** 2) ** 0.5
        for i, a in enumerate(positions)
        for b in positions[i + 1 :]
    )


def ligand_extent_exceeds_box(max_extent_a: float | None, box: DockingBox) -> bool:
    """Whether the ligand is longer than the box's SHORTEST side.

    **This is a conservative warning, not a fit test, and the difference is
    the whole reason for the wording.** A ligand longer than the shortest side
    can still dock -- it simply cannot lie along that axis, so whole
    orientations are excluded from the search. Actual fit is
    orientation-dependent and this predicate deliberately does not attempt it;
    calling it "does not fit" would claim more than the arithmetic supports.

    The PRINCIPLE is sourced: [source:feinstein2015] relates the optimal search
    space to the docked ligand's radius of gyration and shows sizing must
    follow the DOCKED ligand rather than only the reference one. The
    predicate is ours -- that paper defines an Rg-based optimum, not this
    comparison -- and saying otherwise would borrow its authority for a rule it
    never states.

    **THE CASE THAT PROMPTED THIS DOES NOT TRIP IT, and that is the finding
    rather than a disappointment.** The first measurement counted ALL atoms
    including hydrogens and put fentanyl at 16.1 A against a 16.00 A shortest
    side -- over, and apparently the explanation for a disappointing run. Vina's
    ligand PDBQT MERGES nonpolar hydrogens into their heavy atom, so that
    number described a molecule Vina never receives. Re-measured on the atoms
    actually written to the PDBQT, lowest-energy conformer, 5C1M's BU-72 box:

        atoms Vina receives        extent    vs 16.00 A shortest side
        BU-72 (the reference)   34  12.39 A  inside
        fentanyl                26  14.13 A  inside
        butyryl fentanyl        27  13.73 A  inside

    So that box was adequate for all three and the reported poses are not
    explained by it. `max_heavy_atom_extent` is used as the measure because it
    agrees with the PDBQT extent to 0.03 A on this set while needing no
    conversion -- the polar hydrogens that survive sit within a bond length of
    a heavy atom they cannot extend past.

    The guard stays because the failure mode is real -- a box is user-editable,
    and [source:feinstein2015] measures pose accuracy degrading when the search
    space is too small for the ligand -- but it is a guard against a box
    somebody makes too small, NOT the diagnosis of the run that motivated it.

    Nothing is resized. A box that quietly grew would change what was docked
    without saying so, which is the failure this whole module exists to make
    visible.
    """
    if max_extent_a is None:
        return False
    return max_extent_a > min(box.size)


def describe_box_placement(
    structure_text: str,
    source_format: str,
    box: DockingBox,
    ligand_code: str | None = None,
) -> BoxPlacement:
    """Judge `box` against what the structure says is in it.

    The motivating case, measured on 6WGT (5-HT2A with LSD) and pinned in
    `tests/test_binding_site.py`:

        box                          distance to 7LD   atoms inside
        derived from 7LD                      0.0 A            218
        the panel's old default (0,0,0)      55.1 A            139

    139 atoms is why the existing empty-box refusal could not catch this.
    That guard fires on ZERO atoms; a box in the wrong place still clips
    protein, so it passed cleanly and four ligands were docked 55 A from
    the orthosteric pocket.

    Parses the structure twice when a code is supplied -- once here, once
    inside `box_from_ligand`. Left that way deliberately rather than
    threading pre-parsed atoms through a function whose redocking
    validation is recorded in this module's docstring: ~150 ms at the point
    a multi-second docking run is starting is not worth destabilising it.
    """
    parsed = receptor_atoms_from_structure(structure_text, source_format)
    cx, cy, cz = box.center
    hx, hy, hz = (size / 2.0 for size in box.size)
    atom_count = sum(
        1
        for atom in parsed
        if abs(atom.position[0] - cx) <= hx
        and abs(atom.position[1] - cy) <= hy
        and abs(atom.position[2] - cz) <= hz
    )

    code = (ligand_code or "").strip().upper()
    if not code:
        return BoxPlacement(
            atom_count=atom_count,
            reference_site_code=None,
            reference_site_box=None,
            reference_site_error=None,
            site_distance_a=None,
            relationship="no_reference_site",
        )

    try:
        site = box_from_ligand(structure_text, source_format, code)
    except BindingSiteError as exc:
        # A code WAS supplied and did not resolve. Classified the same as
        # "no annotation" because there is still no distance to report --
        # but the error travels so the caller can say something different,
        # which it must: "there is no site" and "there should be a site and
        # it is missing" are opposite messages.
        return BoxPlacement(
            atom_count=atom_count,
            reference_site_code=code,
            reference_site_box=None,
            reference_site_error=str(exc),
            site_distance_a=None,
            relationship="no_reference_site",
        )

    sx, sy, sz = site.box.center
    distance = ((cx - sx) ** 2 + (cy - sy) ** 2 + (cz - sz) ** 2) ** 0.5
    return BoxPlacement(
        atom_count=atom_count,
        reference_site_code=code,
        reference_site_box=site.box,
        reference_site_error=None,
        site_distance_a=distance,
        relationship=(
            "at_reference_site"
            if distance <= REFERENCE_SITE_TOLERANCE
            else "far_from_reference_site"
        ),
    )
