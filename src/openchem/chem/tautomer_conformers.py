"""The conformer pool behind one stereo class of one tautomer (model revision 4).

**WHY THIS EXISTS.** Model revision 3 optimized ONE embedded start geometry per
stereo class. For acetylacetone that start put the enol's O-H 4.76 A from the
carbonyl, the optimizer stayed in that non-hydrogen-bonded minimum, and the enol
came out 14.7 kcal/mol too high (measured, PBE0/def2-TZVP). A tautomer's energy is
the lowest of what was searched, so what is searched has to include its rotamers.

**THE RECIPE, EVERY PART OF IT IN THE MODEL POLICY.** ETKDGv3 embeds `embeds`
conformers from a seed that is NEVER 0; every conformer is minimized with MMFF94
(UFF where MMFF has no parameters, a rule and not a surprise); conformers that did
not converge are dropped, never ranked; the rest are reduced to the DISTINCT set by
the project's own `conformer_providers.distinct_conformers` (heavy atoms plus polar
hydrogens, symmetry-aware, with the energy veto) so the notion of "the same
conformer" is the one that module measured; then the lowest `topk` (or, in
`full_orca`, every one up to `cap`) go to ORCA.

**IDENTITY FIRST, PRESENTATION SECOND.** A conformer's identity is its RECIPE
(stereo class, seed, the embedding's own ordinal before any sorting, the effective
embedding policy, the RDKit release). It is the deterministic tie-break and the
lookup key. The index shown to a user is assigned AFTER selection and is never
identity: a rank-based identity would be circular (the rank is what the tie-break
decides) and would move whenever another conformer entered the pool.

**SELECTION IS NOT TRUNCATION.** Choosing `topk` of M distinct conformers is the
declared model, so it never makes a tautomer incomplete. Only `full_orca` with more
distinct conformers than `cap` truncates, and then the lowest `cap` are kept and
`truncated` says so.

**TWO MEASURED TRAPS** (RDKit 2025.09.6): `randomSeed=0` makes `EmbedMultipleConfs`
return N IDENTICAL conformers, so the seed is offset and never 0; and an unrelaxed
ETKDG geometry is not a minimum, hence the force-field step before anything is
compared.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass

from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.chem.conformer_providers import distinct_conformers
from openchem.chem.tautomer_ranking import RDKIT_VERSION

#: One embedded start geometry per stereo class: what revision 3 computed.
SEARCH_SINGLE = "single"
#: MMFF-prefiltered distinct conformers; the `topk` lowest are optimized.
SEARCH_TOPK = "mmff_topk"
#: Every retained conformer of the sampled, pruned pool, up to a cap. NOT
#: exhaustive conformational enumeration.
SEARCH_FULL = "full_orca"

#: Which force field scored the pool.
PREFILTER_MMFF = "mmff94"
#: UFF, the stated fallback where MMFF94 has no parameters for the structure.
PREFILTER_UFF = "uff"

#: Energies closer than this (kcal/mol) are tied for ordering, then broken by the
#: conformer's recipe fingerprint: a hard cut on a float would let two runs that
#: differ in the last digit order two identical conformers differently.
_TIE_DIGITS = 3


@dataclass(frozen=True)
class PoolMember:
    """One conformer that survived the pool, with its identity."""

    recipe_fingerprint: str
    #: Hydrogen-explicit, exactly one conformer.
    mol: Chem.Mol
    #: kcal/mol from `ConformerPool.prefilter`'s force field. Never compared
    #: across pools and never an ORCA quantity.
    prefilter_energy: float
    #: The embedding's own conformer id, BEFORE any sorting.
    raw_ordinal: int


@dataclass(frozen=True)
class ConformerPool:
    """What the search did for one stereo class, and what it selected."""

    #: Lowest prefilter energy first. The position is the presentation index.
    selected: tuple[PoolMember, ...]
    #: Every distinct conformer that survived the prune, selected or not.
    retained_recipes: tuple[str, ...]
    seed: int
    attempted: int
    produced: int
    prefilter_ok: int
    prefilter_failed: int
    prefilter: str
    #: `full_orca` only: more distinct conformers than the cap.
    truncated: bool

    @property
    def distinct(self) -> int:
        return len(self.retained_recipes)

    @property
    def selected_recipes(self) -> tuple[str, ...]:
        return tuple(m.recipe_fingerprint for m in self.selected)


def recipe_fingerprint(
    stereo_fingerprint: str, seed: int, raw_ordinal: int, embed_policy: str
) -> str:
    """A conformer's identity, from how it was made and never from coordinates or
    rank. The RDKit release is part of it: ETKDG, the force fields and their
    ordering are implementation-defined."""
    text = "|".join([stereo_fingerprint, str(seed), str(raw_ordinal), embed_policy, RDKIT_VERSION])
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def etkdg_signature() -> str:
    """The EFFECTIVE embedding parameters, not just the name `ETKDGv3`. Part of
    the model policy, so a changed default is a changed model."""
    p = AllChem.ETKDGv3()
    names = (
        "useExpTorsionAnglePrefs", "useBasicKnowledge", "useRandomCoords", "enforceChirality",
        "ETversion", "pruneRmsThresh", "useSmallRingTorsions", "useMacrocycleTorsions",
    )
    return ";".join(f"{n}={getattr(p, n, '?')}" for n in names)


def _optimize(mol: Chem.Mol, max_iters: int) -> tuple[str, dict[int, float]]:
    """Minimize every conformer of `mol`: `(force field used, {conformer id:
    kcal/mol})` for the ones that converged. MMFF94 where it has parameters, else
    UFF. A conformer that did not converge, or has a non-finite energy, is simply
    absent: it is never ranked."""
    ids = [c.GetId() for c in mol.GetConformers()]
    if AllChem.MMFFHasAllMoleculeParams(mol):
        used, result = PREFILTER_MMFF, AllChem.MMFFOptimizeMoleculeConfs(mol, maxIters=max_iters, numThreads=1)
    else:
        used, result = PREFILTER_UFF, AllChem.UFFOptimizeMoleculeConfs(mol, maxIters=max_iters, numThreads=1)
    energies = {
        cid: float(energy)
        for cid, (flag, energy) in zip(ids, result, strict=True)
        if flag == 0 and math.isfinite(energy)
    }
    return used, energies


def build_pool(
    isomer: Chem.Mol,
    *,
    stereo_fingerprint: str,
    seed: int,
    search: str,
    embeds: int,
    topk: int,
    cap: int,
    rms_threshold: float,
    energy_window: float,
    max_iters: int,
    embed_policy: str,
) -> ConformerPool:
    """The conformer pool of one stereo class (`isomer`, no explicit hydrogens).

    `seed` must be at least 1 (see the module docstring). An empty `selected`
    means no usable conformer: the caller drops the class and counts it, exactly
    as it does an embedding failure.
    """
    if seed < 1:
        raise ValueError("a pool seed of 0 returns identical conformers; use a seed of at least 1")
    if search not in (SEARCH_TOPK, SEARCH_FULL):
        raise ValueError(f"not a pool search: {search!r}")
    mol = Chem.AddHs(Chem.Mol(isomer))
    params = AllChem.ETKDGv3()
    params.randomSeed = seed
    params.numThreads = 1
    ids = list(AllChem.EmbedMultipleConfs(mol, embeds, params))
    if not ids:
        params.useRandomCoords = True
        ids = list(AllChem.EmbedMultipleConfs(mol, embeds, params))
    produced = len(ids)
    if not ids:
        return ConformerPool((), (), seed, embeds, 0, 0, 0, PREFILTER_MMFF, False)

    prefilter, energies = _optimize(mol, max_iters)
    members: list[PoolMember] = []
    for cid in ids:
        if cid not in energies:
            continue
        single = Chem.Mol(mol, confId=cid)
        members.append(
            PoolMember(
                recipe_fingerprint(stereo_fingerprint, seed, cid, embed_policy), single, energies[cid], cid
            )
        )
    members.sort(key=lambda m: (round(m.prefilter_energy, _TIE_DIGITS), m.recipe_fingerprint))
    by_mol = {id(m.mol): m for m in members}
    distinct = distinct_conformers(
        [(m.mol, m.prefilter_energy) for m in members],
        rms_threshold=rms_threshold,
        energy_window=energy_window,
    )
    retained = [by_mol[id(mol_)] for mol_, _energy in distinct]
    limit = topk if search == SEARCH_TOPK else cap
    return ConformerPool(
        selected=tuple(retained[:limit]),
        retained_recipes=tuple(m.recipe_fingerprint for m in retained),
        seed=seed,
        attempted=embeds,
        produced=produced,
        prefilter_ok=len(members),
        prefilter_failed=produced - len(members),
        prefilter=prefilter,
        truncated=search == SEARCH_FULL and len(retained) > cap,
    )
