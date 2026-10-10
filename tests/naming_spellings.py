"""Reproducible random spellings of one structure, for the tests that assert an atom-order-free result.

**Not `Chem.MolToSmiles(mol, doRandom=True)`.** Measured 2026-10-10 on RDKit 2025.09.6 (the project venv): `doRandom=True` IGNORES
`rdBase.SeedRandomNumberGenerator`. Calling the seed and then writing three spellings, twice, gave different strings each time. A test
built on it samples fresh spellings on every run, so a failure cannot be re-run from its SEED, and an atom-order defect that shows in a
minority of spellings is caught by chance only.

A seeded `random.Random` shuffles the atom numbering instead, and `MolToSmiles(..., canonical=False)` writes the atoms in that order: a
random root and a random branch order, deterministically. Same algorithm as `spellings` in `tools/naming_variants.py` (kept separate: that
module lives on a branch of its own, and `tests/` must not import from `tools/`).

Stereo is preserved by `RenumberAtoms`, but a spelling is still only evidence if it IS the structure, so `checked_spellings` compares
InChIKeys. (`doRandom=True` on a molecule straight out of `EnumerateStereoisomers` once wrote a different stereoisomer and a run "found"
instability that was the probe's; the check stays even though this writer does not do that.)
"""
from __future__ import annotations

import random

from rdkit import Chem


def _as_mol(structure: str | Chem.Mol) -> Chem.Mol:
    mol = Chem.MolFromSmiles(structure) if isinstance(structure, str) else structure
    assert mol is not None, f"not a structure: {structure!r}"
    return mol


def _one(mol: Chem.Mol, rng: random.Random) -> str:
    order = list(range(mol.GetNumAtoms()))
    rng.shuffle(order)
    return Chem.MolToSmiles(Chem.RenumberAtoms(mol, order), canonical=False)


def random_spellings(structure: str | Chem.Mol, count: int, seed: int) -> list[str]:
    """`count` spellings of one structure, each written from a random permutation of its atoms; the same `seed` gives the same list."""
    mol = _as_mol(structure)
    rng = random.Random(seed)
    return [_one(mol, rng) for _ in range(count)]


def checked_spellings(smiles: str, count: int, seed: int, *, distinct: bool = False) -> list[str]:
    """`[smiles]` followed by `count` random spellings, each asserted (by InChIKey) to BE that structure.

    With `distinct=True` the list is instead grown until it holds `count` DIFFERENT strings in all, `smiles` included, which is what
    a test over a large molecule with few degrees of freedom needs; it gives up after `50 * count` draws rather than loop forever.
    """
    mol = _as_mol(smiles)
    key = Chem.MolToInchiKey(mol)
    rng = random.Random(seed)
    out = [smiles]

    def take() -> str:
        spelling = _one(mol, rng)
        assert Chem.MolToInchiKey(Chem.MolFromSmiles(spelling)) == key, spelling
        return spelling

    if distinct:
        draws = 0
        while len(out) < count:
            draws += 1
            assert draws <= 50 * count, f"only {len(out)} distinct spellings of {smiles} in {draws - 1} draws"
            spelling = take()
            if spelling not in out:
                out.append(spelling)
    else:
        out.extend(take() for _ in range(count))
    return out
