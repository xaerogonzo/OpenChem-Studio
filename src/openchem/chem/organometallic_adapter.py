"""The one place that knows how the vendored organometallic code works.

`vendor/iupac_namer/perception/organometallic.py` is 5,020 lines of real
perception -- metallocenes, cyclopentadienide rings, carbonyls, nitrosyls
-- written to produce a NAME and then throw the perception away. This
surfaces it, the way `structure_annotation.py` surfaced the same engine's
ring and functional-group analysis.

**A vendored module is not an API.** Everything below reaches into
private, underscore-prefixed functions of a file this project does not
own. That is exactly why it happens HERE and nowhere else: when the
vendored namer changes, one file needs repairing rather than four, and
`substance.py`, `oxidation_states.py` and `bond_report.py` never learn
that the namer exists.

## What it can actually do, measured rather than assumed

    classify_metallocene                27 EXACT structures, by canonical
                                        SMILES. Gives a retained name.
                                        Returns None for methylferrocene.
    _classify_substituted_metallocene   GENERAL. Handled methylferrocene,
                                        returning the metal and both Cp
                                        rings with substituent prefixes.

The narrow one is a pin table; the general one is perception. Both are
used, in that order, because a pinned hit also yields the accepted name
and the general one does not.

Everything here **fails soft**. A namer that cannot classify something
must not take a calculator down with it, so every call is wrapped and a
failure means "nothing perceived" rather than an exception.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger("openchem.chem")


@dataclass(frozen=True)
class CpRing:
    """One cyclopentadienyl ring bound to a metal."""

    atom_indices: tuple[int, ...]
    #: "" for an unsubstituted ring, else the namer's own prefix
    #: ("methyl", "pentamethyl"...).
    substituent_prefix: str = ""

    @property
    def label(self) -> str:
        return f"{self.substituent_prefix}Cp" if self.substituent_prefix else "Cp"


@dataclass(frozen=True)
class Metallocene:
    """A sandwich complex, as the vendored perception sees it."""

    metal_symbol: str
    metal_index: int | None
    rings: tuple[CpRing, ...]
    #: The accepted name when this matched a pinned structure, else "".
    #: Absence is not a failure -- methylferrocene is perceived without
    #: being pinned -- so callers must not treat it as identity.
    retained_name: str = ""

    @property
    def is_pinned(self) -> bool:
        return bool(self.retained_name)


def _module():
    from openchem.vendor.iupac_namer.perception import organometallic

    return organometallic


def metallocene(mol) -> Metallocene | None:
    """Perceive a sandwich complex, or return None.

    Tries the pin table first because a hit there also yields the accepted
    name; falls back to the general classifier, which is what handles
    every substituted ring.
    """
    if mol is None:
        return None
    try:
        module = _module()
    except Exception:  # noqa: BLE001 - a missing vendor must not be fatal
        logger.debug("organometallic perception unavailable", exc_info=True)
        return None

    try:
        pinned = module.classify_metallocene(mol)
    except Exception:  # noqa: BLE001
        logger.debug("classify_metallocene failed", exc_info=True)
        pinned = None
    if pinned is not None:
        return Metallocene(
            metal_symbol=mol.GetAtomWithIdx(pinned.center_atom_idx).GetSymbol(),
            metal_index=pinned.center_atom_idx,
            rings=tuple(
                CpRing(tuple(sorted(ring))) for ring in pinned.ring_atom_sets
            ),
            retained_name=pinned.retained_name,
        )

    try:
        general = module._classify_substituted_metallocene(mol)
    except Exception:  # noqa: BLE001
        logger.debug("_classify_substituted_metallocene failed", exc_info=True)
        return None
    if not general:
        return None

    symbol, *rings = general
    metal_index = next(
        (a.GetIdx() for a in mol.GetAtoms() if a.GetSymbol() == symbol), None
    )
    return Metallocene(
        metal_symbol=symbol,
        metal_index=metal_index,
        rings=tuple(
            CpRing(tuple(sorted(ring.atom_idxs)), getattr(ring, "substituent_prefix", ""))
            for ring in rings
        ),
    )


def is_cyclopentadienide(mol, atom_indices) -> bool:
    """Whether these atoms are a Cp- ring, by the namer's own test."""
    try:
        return bool(_module()._is_cyclopentadienide_anion_fragment(mol, tuple(atom_indices)))
    except Exception:  # noqa: BLE001
        logger.debug("cyclopentadienide test failed", exc_info=True)
        return False


def is_carbonyl_ligand(mol, atom_indices) -> bool:
    """Whether these atoms are a CO ligand, by the namer's own test."""
    try:
        return bool(_module()._is_co_fragment(mol, tuple(atom_indices)))
    except Exception:  # noqa: BLE001
        logger.debug("carbonyl test failed", exc_info=True)
        return False
