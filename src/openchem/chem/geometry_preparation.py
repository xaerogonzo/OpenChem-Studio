"""Optimising a copy of a geometry, and choosing the lowest-energy of several.

ChemAxon's Geometrical Descriptors plugin has three controls that change WHICH geometry its
numbers are measured on: optimise before the MMFF94 energy, optimise before the projections,
and "calculate for the lowest energy conformer". This is that, built on what OpenChem already
has -- the conformer provider's embedding, its force-field selection and its four optimisation
levels -- rather than a second optimiser that could disagree with it.

**EVERYTHING HERE WORKS ON A COPY.** The molecule the person is looking at, and the conformers
stored on it, are never moved. A calculator that quietly relaxed the stored geometry would turn
"measure this conformer" into "measure what this conformer relaxes to" while the screen kept
showing the old one.

**"LOWEST" IS A CLAIM ABOUT A SEARCH, NOT ABOUT THE MOLECULE.** It is the lowest energy among
the candidates tried, under one force field, from one seeded random search. It is not the
global minimum, and the result says how many candidates there were and how many settled.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from rdkit import Chem

from openchem.chem.conformer_providers import (
    DEFAULT_SEARCH_SEED,
    OPTIMISATION_LEVELS,
    GenerationOptions,
    RDKitConformerProvider,
)

#: The stored codes of the optimisation limit, in order, and the level of
#: `conformer_providers.OPTIMISATION_LEVELS` each names. Codes, not the labels: a label is
#: wording and the stored value is part of a result's identity.
LIMIT_LEVELS: dict[str, str] = {
    "loose": "Loose",
    "normal": "Normal",
    "strict": "Strict",
    "very_strict": "Very strict",
}
#: The optimisation limit a result is computed at unless another is chosen.
DEFAULT_LIMIT = "normal"


def level_name(limit: str) -> str:
    """The optimisation level a stored limit code names; an unknown code is the default."""
    return LIMIT_LEVELS.get(limit, LIMIT_LEVELS[DEFAULT_LIMIT])


def geometry_fingerprint(mol: Chem.Mol) -> str:
    """A short hash of the coordinates and atoms, to say WHICH geometry a number was measured on."""
    try:
        text = Chem.MolToMolBlock(mol)
    except Exception:  # noqa: BLE001 - a fingerprint that cannot be made is recorded as absent
        return ""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class Optimised:
    """A relaxed copy, and how the relaxation went."""

    mol: Chem.Mol
    #: Energy at the relaxed geometry in kcal/mol, or None when no force field had parameters.
    energy: float | None
    converged: bool
    #: `MMFF94`, `UFF`, or "" when neither could be set up.
    force_field: str
    limit: str


def _with_hydrogens(mol: Chem.Mol) -> Chem.Mol:
    """`mol` with explicit hydrogens, keeping its coordinates (a no-op on a conformer)."""
    if any(atom.GetAtomicNum() == 1 for atom in mol.GetAtoms()) or not mol.GetNumConformers():
        return Chem.Mol(mol)
    return Chem.AddHs(mol, addCoords=True)


def optimised_copy(mol: Chem.Mol, limit: str = DEFAULT_LIMIT) -> Optimised:
    """A relaxed copy of `mol`: MMFF94 where it has parameters, UFF otherwise.

    The same minimiser, tolerances and force-field choice the conformer search uses, at the
    level `limit` names. A geometry that did not settle is returned with `converged` False
    rather than discarded: here it is a measurement input the caller reports on, not a
    conformer being offered.
    """
    if not mol.GetNumConformers():
        raise ValueError("There is no geometry to optimise.")
    working = _with_hydrogens(mol)
    provider = RDKitConformerProvider()
    mmff = has_mmff_parameters(working)
    energy, converged = provider.optimise(working, level_name(limit))
    if energy is None:
        return Optimised(mol=working, energy=None, converged=False, force_field="", limit=limit)
    return Optimised(
        mol=working, energy=float(energy), converged=bool(converged),
        force_field="MMFF94" if mmff else "UFF", limit=limit,
    )


def has_mmff_parameters(mol: Chem.Mol) -> bool:
    """Whether RDKit has MMFF94 parameters for every atom of `mol`.

    Placed after its first use only because the module reads top-down by purpose; it is a plain function."""
    from rdkit.Chem import AllChem

    try:
        return AllChem.MMFFGetMoleculeProperties(mol) is not None
    except (ValueError, RuntimeError):
        return False


@dataclass(frozen=True)
class LowestConformer:
    """The result of a seeded search, and what it can and cannot claim."""

    mol: Chem.Mol
    #: The winner's force-field energy in kcal/mol, in the force field the search used.
    energy: float
    #: How many geometries were considered, including the one supplied if it was a candidate.
    candidates: int
    #: How many of them settled in the optimiser and so were ranked.
    ranked: int
    #: How many of the candidates were generated here (the rest is the supplied geometry).
    generated: int
    #: The spread of the ranked energies, lowest to highest, kcal/mol: a search that found one
    #: shape and a search that found fifteen look alike without it.
    energy_range: tuple[float, float]
    #: Whether the winner is the geometry that was supplied rather than a generated one.
    supplied_won: bool
    force_field: str
    seed: int
    limit: str


def lowest_energy_conformer(
    mol: Chem.Mol, count: int, limit: str = DEFAULT_LIMIT, include_supplied: bool = True
) -> LowestConformer | None:
    """The lowest-energy of `count` freshly generated conformers (and the one supplied).

    Generated by the application's own seeded ETKDG search, so a repeat run returns the same
    answer. The supplied geometry is a candidate when it is a real 3D conformer: otherwise
    "always" could return something HIGHER than the conformer the person already has, which
    reads as the search being worse than doing nothing. Every candidate is relaxed at the same
    limit, so the energies compare. None when nothing could be generated.
    """
    provider = RDKitConformerProvider(random_seed=DEFAULT_SEARCH_SEED)
    options = GenerationOptions(optimisation=level_name(limit))
    base = Chem.Mol(mol)
    base.RemoveAllConformers()
    batch = provider.generate_conformer_batch(base, max(1, int(count)), True, None, options)

    pool: list[tuple[Chem.Mol, float, bool]] = [
        (candidate, float(energy), False) for candidate, energy in batch.results if energy is not None
    ]
    attempted = batch.attempted
    supplied_counted = False
    if include_supplied and mol.GetNumConformers() and mol.GetConformer().Is3D():
        relaxed = optimised_copy(mol, limit)
        supplied_counted = True
        if relaxed.energy is not None and relaxed.converged:
            pool.append((relaxed.mol, relaxed.energy, True))
    if not pool:
        return None
    winner, energy, supplied = min(pool, key=lambda item: item[1])
    energies = [item[1] for item in pool]
    force_field = "MMFF94" if has_mmff_parameters(winner) else "UFF"
    return LowestConformer(
        mol=winner,
        energy=energy,
        candidates=attempted + (1 if supplied_counted else 0),
        ranked=len(pool),
        generated=attempted,
        energy_range=(min(energies), max(energies)),
        supplied_won=supplied,
        force_field=force_field,
        seed=DEFAULT_SEARCH_SEED,
        limit=limit,
    )
