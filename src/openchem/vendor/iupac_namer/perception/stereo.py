"""
iupac_namer/perception/stereo.py

StereoAnalysis subsystem — Subsystem 2 of the Perception layer.

Detects stereocenters in a molecule using RDKit's CIP implementation.

Two kinds of stereocenters are detected:
  1. Tetrahedral — chiral atoms with R/S descriptors (or unspecified chirality).
  2. Double-bond — E/Z stereochemistry on C=C and analogous bonds.

Results are computed once on construction and cached.  All public data is
immutable.

See ARCHITECTURE_PERCEPTION.md §Subsystem 2 for the full spec.
See ARCHITECTURE_DATA_STRUCTURES.md for the StereoCenter dataclass.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from openchem.vendor.iupac_namer.types import StereoCenter

if TYPE_CHECKING:
    from openchem.vendor.iupac_namer.perception.atoms import AtomAnalysis

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# StereoAnalysis
# ---------------------------------------------------------------------------


class StereoAnalysis:
    """Detect stereocenters in an RDKit molecule.

    Parameters
    ----------
    mol:
        An RDKit ``Mol`` object (after sanitisation).
    atom_analysis:
        The :class:`~iupac_namer.perception.atoms.AtomAnalysis` for this mol.
        Accepted for interface uniformity and future use; not heavily used
        internally since RDKit's own stereo perception operates on the mol.

    Notes
    -----
    RDKit's :func:`~rdkit.Chem.AssignStereochemistry` must be called before
    CIP codes are available on atoms and bonds.  We call it here with
    ``cleanIt=True, force=True`` to ensure a clean assignment from scratch.

    After the legacy pass we re-stamp CIP codes via
    :func:`~rdkit.Chem.rdCIPLabeler.AssignCIPLabels` (the modern labeller).
    The legacy implementation never emits the lowercase ``r`` / ``s``
    descriptors required by IUPAC P-91.2 for pseudoasymmetric centres
    (e.g. the C-3 of ribitol), and it can disagree with the modern labeller
    at borderline cases (sulfoxide S, certain meso isomers).  The modern
    labeller is authoritative — we let it overwrite the legacy ``_CIPCode``
    so downstream code sees the correct descriptors.
    """

    def __init__(self, mol: object, atom_analysis: "AtomAnalysis") -> None:
        self._mol = mol
        self._atoms = atom_analysis
        self._stereocenters: tuple[StereoCenter, ...] = self._analyze()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def stereocenters(self) -> tuple[StereoCenter, ...]:
        """All stereocenters detected in the molecule (immutable tuple)."""
        return self._stereocenters

    @property
    def has_stereo(self) -> bool:
        """True if the molecule contains at least one stereocenter."""
        return len(self._stereocenters) > 0

    def stereo_at_atom(self, atom_idx: int) -> StereoCenter | None:
        """Return the StereoCenter at the given atom index, or None.

        For double-bond stereocenters, the begin-atom index is used.
        """
        for sc in self._stereocenters:
            if sc.atom_idx == atom_idx:
                return sc
        return None

    @property
    def tetrahedral_centers(self) -> tuple[StereoCenter, ...]:
        """Only the tetrahedral stereocenters."""
        return tuple(sc for sc in self._stereocenters if sc.type == "tetrahedral")

    @property
    def double_bond_centers(self) -> tuple[StereoCenter, ...]:
        """Only the double-bond (E/Z) stereocenters."""
        return tuple(sc for sc in self._stereocenters if sc.type == "double_bond")

    # ------------------------------------------------------------------
    # Internal analysis
    # ------------------------------------------------------------------

    def _analyze(self) -> tuple[StereoCenter, ...]:
        """Compute all stereocenters; return an immutable tuple."""
        from rdkit import Chem

        # Assign CIP codes to atoms and bonds.
        # cleanIt=True — clear any existing stereo flags first.
        # force=True   — re-assign even if already assigned.
        Chem.AssignStereochemistry(self._mol, cleanIt=True, force=True)  # type: ignore[attr-defined]

        # Overwrite with the modern CIP labeller so pseudoasymmetric centres
        # get their lowercase ``r`` / ``s`` descriptors and meso isomers get
        # the correct R/S assignment.  The legacy ``AssignStereochemistry``
        # call above primes the chiral tags / bond stereo flags that
        # ``rdCIPLabeler`` reads, so we keep both invocations.
        try:
            from rdkit.Chem import rdCIPLabeler  # type: ignore[attr-defined]
            rdCIPLabeler.AssignCIPLabels(self._mol)
        except Exception:  # pragma: no cover — defensive only
            logger.debug("rdCIPLabeler.AssignCIPLabels unavailable; using legacy CIP codes")

        self._label_azolide_on_neutral_view()

        centers: list[StereoCenter] = []

        centers.extend(self._detect_tetrahedral())
        centers.extend(self._detect_double_bond())

        return tuple(centers)

    def _label_azolide_on_neutral_view(self) -> None:
        label_azolide_on_neutral_view(self._mol)  # type: ignore[arg-type]

    # ------------------------------------------------------------------
    # Tetrahedral detection
    # ------------------------------------------------------------------

    def _detect_tetrahedral(self) -> list[StereoCenter]:
        """Detect tetrahedral stereocenters (R/S)."""
        from rdkit import Chem

        results: list[StereoCenter] = []
        seen_idxs: set[int] = set()

        for atom in self._mol.GetAtoms():  # type: ignore[attr-defined]
            chiral_tag = atom.GetChiralTag()
            if chiral_tag == Chem.ChiralType.CHI_UNSPECIFIED:
                continue

            # Retrieve CIP code if assigned (may be absent if the center is
            # formally chiral but not CIP-deterministic, e.g. unspecified).
            props = atom.GetPropsAsDict()
            cip = props.get("_CIPCode", None)

            # Prefer the inherited parent CIP descriptor over the locally
            # recomputed one when both are present.  Per IUPAC P-92.1.4.3 the
            # free valence on a substituent is treated as a phantom atom of
            # the parent's identity, so internal CIP priorities should be
            # evaluated *as if* the substituent were still attached.  The
            # carving pass stamps _ParentCIPCode on every fragment atom that
            # had a CIP code in the parent.  Carving may flip a stereo
            # priority at internal centers whose neighbour-set priority
            # ordering depends on the parent-side branch beyond the cut
            # (e.g. bleomycin's β-OH carbon two atoms from the amide-N cut).
            inherited = props.get("_ParentCIPCode", None)
            if inherited is not None:
                cip = inherited

            sc = StereoCenter(
                atom_idx=atom.GetIdx(),
                type="tetrahedral",
                descriptor=cip,
                cip_priorities=None,  # Could be computed but not needed yet.
            )
            results.append(sc)
            seen_idxs.add(atom.GetIdx())
            logger.debug(
                "Tetrahedral stereocenter at atom %d: descriptor=%s",
                atom.GetIdx(),
                cip,
            )

        # Inherited stereocenters: when a substituent is carved from a parent
        # mol the attachment atom may lose its chiral tag because dummy→H
        # replacement leaves it with two equivalent H neighbours (e.g. an
        # α-C of an amino-acid residue carved through the amide N).  The
        # atom is still stereogenic in context — IUPAC P-91.5.4 requires the
        # parent-derived descriptor.  carve_substituent stashes the parent
        # CIP code as ``_ParentCIPCode``; emit a virtual StereoCenter for it
        # here when no native chirality is detected.
        for atom in self._mol.GetAtoms():  # type: ignore[attr-defined]
            if atom.GetIdx() in seen_idxs:
                continue
            if not atom.HasProp("_ParentCIPCode"):
                continue
            inherited = atom.GetProp("_ParentCIPCode")
            sc = StereoCenter(
                atom_idx=atom.GetIdx(),
                type="tetrahedral",
                descriptor=inherited,
                cip_priorities=None,
            )
            results.append(sc)
            logger.debug(
                "Inherited tetrahedral stereocenter at atom %d: descriptor=%s",
                atom.GetIdx(),
                inherited,
            )

        return results

    # ------------------------------------------------------------------
    # Double-bond (E/Z) detection
    # ------------------------------------------------------------------

    def _detect_double_bond(self) -> list[StereoCenter]:
        """Detect E/Z double-bond stereocenters."""
        from rdkit import Chem

        results: list[StereoCenter] = []

        for bond in self._mol.GetBonds():  # type: ignore[attr-defined]
            stereo = bond.GetStereo()
            props = bond.GetPropsAsDict()
            inherited = props.get("_ParentCIPCode", None)
            if stereo == Chem.BondStereo.STEREONONE and inherited is None:
                continue

            begin_idx = bond.GetBeginAtomIdx()

            # The inherited descriptor first, for the reason the tetrahedral
            # branch gives: carving replaces the cut side with H, which
            # reorders the two groups on a double-bond carbon whenever the cut
            # side was one of them -- every E/Z measured inside a substituent
            # came out inverted before this.  A bond that stops being
            # stereogenic once carved (-CH=CH-CH3 cut at the first CH leaves
            # CH2=) still carries its parent descriptor here, the way an
            # inherited tetrahedral centre does below.
            # Then the CIP code stored on the bond; then STEREOE / STEREOZ
            # flags, which are the pre-CIP geometric designators.
            ez: str | None = None
            if inherited is not None:
                ez = inherited
            elif "_CIPCode" in props:
                ez = props["_CIPCode"]
            elif stereo == Chem.BondStereo.STEREOE:
                ez = "E"
            elif stereo == Chem.BondStereo.STEREOZ:
                ez = "Z"
            else:
                # STEREOANY or an unusual value — leave descriptor as None.
                logger.debug(
                    "Double-bond stereocenter at bond %d--%d has unusual stereo flag %s",
                    begin_idx,
                    bond.GetEndAtomIdx(),
                    stereo,
                )

            sc = StereoCenter(
                atom_idx=begin_idx,
                type="double_bond",
                descriptor=ez,
                cip_priorities=None,
            )
            results.append(sc)
            logger.debug(
                "Double-bond stereocenter at bond %d--%d: descriptor=%s",
                begin_idx,
                bond.GetEndAtomIdx(),
                ez,
            )

        return results

    # ------------------------------------------------------------------
    # Dunder helpers
    # ------------------------------------------------------------------

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"StereoAnalysis("
            f"n_tetrahedral={len(self.tetrahedral_centers)}, "
            f"n_double_bond={len(self.double_bond_centers)})"
        )

    def __len__(self) -> int:
        return len(self._stereocenters)


def label_azolide_on_neutral_view(mol) -> None:
    """Give the CIP codes of a molecule with an aromatic `[n-]` the codes of its neutral `[nH]` view, in place (naming round 60).

    RDKit's labeller reads the deprotonated ring nitrogen with different duplicate atoms than the neutral azole, so a spiro centre beside a pyrazolide was `S` where the neutral
    compound is `R`, and OPSIN (which the names are checked against) agrees with the neutral view: `(4S)-...pyrazole-2-id` read back as the other enantiomer. The charge
    does not change the arrangement in space, only RDKit's reading of the ring."""
    from rdkit import Chem

    sites = [a.GetIdx() for a in mol.GetAtoms() if a.GetAtomicNum() == 7 and a.GetFormalCharge() == -1 and a.GetIsAromatic()]
    if not sites:
        return
    work = Chem.Mol(mol)
    for i in sites:
        atom = work.GetAtomWithIdx(i)
        atom.SetFormalCharge(0)
        atom.SetNumExplicitHs(1)
        atom.SetNoImplicit(True)
    try:
        Chem.SanitizeMol(work)
        Chem.AssignStereochemistry(work, cleanIt=True, force=True)  # type: ignore[attr-defined]
        from rdkit.Chem import rdCIPLabeler  # type: ignore[attr-defined]
        rdCIPLabeler.AssignCIPLabels(work)
    except Exception:  # noqa: BLE001 - keep the ion's own codes
        return
    for atom in work.GetAtoms():
        if atom.HasProp("_CIPCode"):
            mol.GetAtomWithIdx(atom.GetIdx()).SetProp("_CIPCode", atom.GetProp("_CIPCode"))
    for bond in work.GetBonds():
        if bond.HasProp("_CIPCode"):
            mol.GetBondWithIdx(bond.GetIdx()).SetProp("_CIPCode", bond.GetProp("_CIPCode"))
