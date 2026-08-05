from __future__ import annotations

import logging
from typing import Callable

from rdkit import Chem
from rdkit.Chem import AllChem, rdMolAlign

from openchem.plugins.interfaces import ConformerProvider

logger = logging.getLogger("openchem.chemistry")

#: RMSD (Å) below which two embeddings are treated as the same conformer.
#: Computed over the skeleton `comparison_skeleton` returns.
#:
#: 0.5 Å is RDKit's conventional `pruneRmsThresh` value, and it was
#: checked here rather than adopted on authority. Over 40 embeddings of
#: butane every pair came out either below 0.5 Å or at 0.66 Å -- two
#: clean clusters, anti and gauche, with nothing in between. So 0.5
#: separates them with margin, while 1.0 merges them into one and loses a
#: real conformer. Measured against this module, 10 requested:
#:
#:     threshold      0.25   0.50   1.00
#:     aziridine         1      1      1
#:     benzene           1      1      1
#:     butane            3      2      1     <- 1.0 is too coarse
#:     ethanol           3      2      1     <- and here
#:     ibuprofen        10      7      3     <- 0.25 keeps every embedding
#:
#: 0.25 is too fine at the other end: it returns all ten embeddings of
#: ibuprofen, which is the no-op this exists to avoid.
#:
#: Cost is negligible (≤1.6 ms for 10 conformers of ibuprofen), so the
#: N-squared comparison is not worth optimising at these counts.
DEFAULT_RMS_THRESHOLD = 0.5


#: Hydrogens on these keep their orientation for comparison; see
#: `distinct_conformers`. Carbon is the one deliberately absent.
_POLAR_H_NEIGHBOURS = frozenset({7, 8, 16})  # N, O, S


def comparison_skeleton(mol: Chem.Mol) -> Chem.Mol:
    """`mol` with its carbon-bound hydrogens removed, for RMSD comparison.

    Public because anything checking whether two conformers are the same
    has to use the SAME notion of sameness this module does. A test that
    compared survivors with plain `RemoveHs` reported them as duplicates
    while the pruner had correctly kept them apart on an O-H orientation.
    """
    editable = Chem.RWMol(mol)
    doomed = [
        atom.GetIdx()
        for atom in editable.GetAtoms()
        if atom.GetAtomicNum() == 1
        and atom.GetDegree() == 1
        and atom.GetNeighbors()[0].GetAtomicNum() not in _POLAR_H_NEIGHBOURS
    ]
    # Descending, because removing an atom renumbers every index above it.
    for index in sorted(doomed, reverse=True):
        editable.RemoveAtom(index)
    return editable.GetMol()


def distinct_conformers(
    results: list[tuple[Chem.Mol, float | None]],
    rms_threshold: float = DEFAULT_RMS_THRESHOLD,
) -> list[tuple[Chem.Mol, float | None]]:
    """Drop embeddings that are the same shape as one already kept.

    WHY THIS IS NOT OPTIONAL. Embedding is random, so asking for ten
    conformers of a molecule that HAS one produced ten copies of it, and
    the UI dutifully reported "Conformer 1/10" with every one identical.
    That is not a cosmetic issue: it invites Boltzmann-weighting a
    population that is really one state ten times over, and it makes a
    rigid molecule look conformationally rich.

    Measured before the fix, 10 requested with MMFF optimisation:
    aziridine 1 distinct, 2H-azirine 1, butane 2.

    HEAVY ATOMS PLUS POLAR HYDROGENS, and symmetry-aware via `GetBestRMS`.

    Hydrogens on carbon are dropped because a rotated methyl is not a
    different conformer but does move three atoms. Hydrogens on N, O and S
    are KEPT because their orientation is a real conformational degree of
    freedom -- it sets hydrogen bonding, and it changes the energy of the
    QM jobs these conformers are generated for.

    Dropping them all was tried first and is measurably worse. Ethanol's
    heavy atoms are C-C-O, which is three points and therefore rigid by
    construction, so heavy-atom-only RMSD reports ONE conformer for a
    molecule whose O-H rotamers are exactly what a conformer search is
    for. Measured over 12 embeddings:

        molecule          heavy-only   +polar H
        ethanol                    1          2
        ethylene glycol            2          3
        ibuprofen                  7          9
        aziridine                  1          1
        butane                     2          2
        benzene / water            1          1

    So the rigid cases -- including the one this fix exists for -- are
    unaffected, and the cases with a rotatable O-H stop being collapsed.

    Symmetry-awareness matters separately: the two ends of butane are
    interchangeable, and a naive atom-order RMSD calls the same shape
    different simply for having been numbered the other way round.

    Order is preserved, so a caller that has already sorted by energy
    keeps the lowest-energy member of each cluster.
    """
    kept: list[tuple[Chem.Mol, float | None]] = []
    kept_heavy: list[Chem.Mol] = []
    for mol, energy in results:
        try:
            heavy = comparison_skeleton(mol)
        except Exception:  # noqa: BLE001 - a shape we cannot compare is one we keep
            kept.append((mol, energy))
            continue
        duplicate = False
        for other in kept_heavy:
            try:
                if rdMolAlign.GetBestRMS(heavy, other) < rms_threshold:
                    duplicate = True
                    break
            except (RuntimeError, ValueError):
                # GetBestRMS raises when it cannot match the two graphs.
                # Keeping the conformer is the safe direction: showing one
                # too many is a far smaller error than silently discarding
                # a real minimum.
                continue
        if not duplicate:
            kept.append((mol, energy))
            kept_heavy.append(heavy)
    return kept


# RDKitConformerProvider implements the same ConformerProvider ABC a future
# plugin would (openchem.plugins.interfaces.ConformerProvider) — ConformerService
# can't tell a built-in method from a plugin-supplied one.


class RDKitConformerProvider(ConformerProvider):
    """Embeds conformers one at a time (rather than RDKit's batch
    EmbedMultipleConfs) specifically so each iteration can report progress
    and honor cancellation via `on_progress`'s return value: returning
    `False` stops the loop before the next conformer starts (RDKit's own
    embed/optimize calls aren't preemptible mid-call, so this is
    best-effort, checked between conformers, not instant). A `None` return
    (the common case -- most callers' `on_progress` has no return
    statement) means "keep going," so this is fully backward compatible
    with callers that don't care about cancellation at all.
    """

    provider_id = "rdkit"

    def generate_conformers(
        self,
        mol: Chem.Mol,
        num_conformers: int,
        optimize: bool,
        on_progress: Callable[[int, int], bool | None] | None = None,
    ) -> list[tuple[Chem.Mol, float | None]]:
        results: list[tuple[Chem.Mol, float | None]] = []
        for i in range(num_conformers):
            conf_mol = self._embed_one(mol)
            energy = self._optimize_one(conf_mol) if conf_mol is not None and optimize else None
            if conf_mol is not None:
                results.append((conf_mol, energy))
            if on_progress is not None:
                should_continue = on_progress(i + 1, num_conformers)
                if should_continue is False:
                    break
        # Ascending by energy so conformer 1/N is the lowest-energy (most
        # relevant) one -- matches Marvin/standard conformer-tool convention.
        # A stable sort with unenergized (optimize=False) results all keyed
        # equal leaves embedding order untouched in that case.
        results.sort(key=lambda item: item[1] if item[1] is not None else float("inf"))
        # Duplicate embeddings are NOT pruned here. `ConformerService` does
        # it, so that a plugin-supplied provider gets the same treatment
        # without having to remember to, and so the count before and after
        # are both available where the user-facing message is built.
        # Sorting first means the survivor of each cluster is its
        # lowest-energy member rather than whichever came out of the loop
        # first.
        return results

    def _embed_one(self, mol: Chem.Mol) -> Chem.Mol | None:
        conf_mol = Chem.AddHs(Chem.Mol(mol))
        params = AllChem.ETKDGv3()
        conf_id = AllChem.EmbedMolecule(conf_mol, params)
        if conf_id < 0:
            # Retry once with random coordinates — some strained/unusual
            # structures fail ETKDG's distance-geometry pass otherwise.
            params.useRandomCoords = True
            conf_id = AllChem.EmbedMolecule(conf_mol, params)
        if conf_id < 0:
            logger.warning("Failed to embed a conformer for molecule")
            return None
        return conf_mol

    def _optimize_one(self, conf_mol: Chem.Mol) -> float | None:
        mmff_props = AllChem.MMFFGetMoleculeProperties(conf_mol)
        if mmff_props is not None:
            AllChem.MMFFOptimizeMolecule(conf_mol, confId=0)
            force_field = AllChem.MMFFGetMoleculeForceField(conf_mol, mmff_props, confId=0)
        else:
            # MMFF94 has no parameters for some elements/charges — UFF covers
            # a much broader range of the periodic table as a fallback.
            AllChem.UFFOptimizeMolecule(conf_mol, confId=0)
            force_field = AllChem.UFFGetMoleculeForceField(conf_mol, confId=0)
        return force_field.CalcEnergy() if force_field is not None else None
