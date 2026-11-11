"""Fragments of a drawing, identified by graph, for salt Mode B.

Does not call chem.substance._components: that key is (formula, charge).

Mode B ``analyze_drawing`` rules:

1. Split with ``Chem.GetMolFrags(mol, asMols=True, sanitizeFrags=False)``.
2. Key each fragment with ``fragment_key``. On ``IdentityRefusal``, return
   ``code="identity_refused"`` and that reason.
3. ``charge == 0`` fragments go to ``extras`` (formula via
   ``rdMolDescriptors.CalcMolFormula`` after sanitize of a copy). Do not label
   them coformer/hydrate.
4. Nonzero-charge fragments group by ``identity`` (not formula). ``drawn_count``
   is the group size.
5. Distinct ionic identities: if ``>= 2`` cations and ``>= 2`` anions →
   ``ambiguous_pairing``, ``theoretical=None``, do not call ``balance_two``.
6. Else if distinct ionic identities ``> 2`` → ``unsupported_multicomponent``,
   ``theoretical=None``.
7. Else if distinct ionic identities ``== 0``: if one fragment and that
   fragment has both a positive and a negative atom charge → ``zwitterion``;
   else ``not_a_salt``.
8. Else if exactly one cation identity and one anion identity:
   ``drawn_total_charge = sum(c.drawn_count * c.charge for c in ions)``. Call
   ``balance_two`` for ``theoretical``. If ``drawn_total_charge == 0`` then
   ``code="charge_neutral"`` and ``charge_valid=True``; else ``code="unbalanced"``
   and ``charge_valid=False``. **Never change ``drawn_count``.**
9. One ionic identity only → ``unbalanced`` when any ion is present without a
   counter-ion of opposite sign; ``theoretical=None``.
"""

from __future__ import annotations

from dataclasses import dataclass

from rdkit import Chem
from rdkit.Chem import rdMolDescriptors

from openchem.domain.salt_stoichiometry import (
    ChargedSpecies,
    TwoIonBalance,
    balance_two,
)


@dataclass(frozen=True)
class IdentityRefusal:
    code: str
    reason: str


@dataclass(frozen=True)
class SaltComponent:
    identity: str
    charge: int
    drawn_count: int
    formula: str


@dataclass(frozen=True)
class ModeBResult:
    code: str
    reason: str
    ions: tuple[SaltComponent, ...]
    extras: tuple[SaltComponent, ...]
    drawn_total_charge: int
    charge_valid: bool
    theoretical: TwoIonBalance | None


def fragment_formal_charge(mol: Chem.Mol) -> int:
    return sum(atom.GetFormalCharge() for atom in mol.GetAtoms())


def fragment_key(mol: Chem.Mol) -> str | IdentityRefusal:
    copy = Chem.Mol(mol)
    for atom in copy.GetAtoms():
        atom.SetAtomMapNum(0)
    try:
        Chem.SanitizeMol(copy)
    except (ValueError, RuntimeError):
        return IdentityRefusal(
            code="unsanitizable",
            reason="The fragment could not be sanitized, so it has no identity key.",
        )
    smiles = Chem.MolToSmiles(copy, isomericSmiles=True)
    charge = fragment_formal_charge(copy)
    parsed = Chem.MolFromSmiles(smiles)
    if parsed is None:
        return IdentityRefusal(
            code="unsanitizable",
            reason="The canonical SMILES of the fragment could not be read back.",
        )
    if fragment_formal_charge(parsed) != charge:
        return IdentityRefusal(
            code="charge_mismatch",
            reason=(
                f"The graph key {smiles!r} has charge "
                f"{fragment_formal_charge(parsed):+d}, not {charge:+d}."
            ),
        )
    return smiles


def _formula(mol: Chem.Mol) -> str:
    copy = Chem.Mol(mol)
    try:
        Chem.SanitizeMol(copy)
    except (ValueError, RuntimeError):
        return ""
    return rdMolDescriptors.CalcMolFormula(copy)


def analyze_drawing(mol: Chem.Mol) -> ModeBResult:
    if mol is None or mol.GetNumAtoms() == 0:
        return ModeBResult(
            code="not_a_salt",
            reason="empty structure",
            ions=(),
            extras=(),
            drawn_total_charge=0,
            charge_valid=False,
            theoretical=None,
        )
    frags = Chem.GetMolFrags(mol, asMols=True, sanitizeFrags=False)
    extras_acc: dict[str, SaltComponent] = {}
    ion_acc: dict[str, SaltComponent] = {}
    for frag in frags:
        key = fragment_key(frag)
        if isinstance(key, IdentityRefusal):
            return ModeBResult(
                code="identity_refused",
                reason=key.reason,
                ions=(),
                extras=(),
                drawn_total_charge=0,
                charge_valid=False,
                theoretical=None,
            )
        charge = fragment_formal_charge(frag)
        formula = _formula(frag)
        bucket = extras_acc if charge == 0 else ion_acc
        existing = bucket.get(key)
        if existing is None:
            bucket[key] = SaltComponent(key, charge, 1, formula)
        else:
            bucket[key] = SaltComponent(key, charge, existing.drawn_count + 1, formula)
    ions = tuple(ion_acc.values())
    extras = tuple(extras_acc.values())
    drawn_total = sum(c.drawn_count * c.charge for c in ions)
    cations = [c for c in ions if c.charge > 0]
    anions = [c for c in ions if c.charge < 0]

    def _result(
        code: str, reason: str, theoretical: TwoIonBalance | None, valid: bool
    ) -> ModeBResult:
        return ModeBResult(code, reason, ions, extras, drawn_total, valid, theoretical)

    if len(cations) >= 2 and len(anions) >= 2:
        return _result(
            "ambiguous_pairing",
            "Several cation and anion species; the drawing does not say which pair.",
            None,
            False,
        )
    if len(ions) > 2:
        return _result(
            "unsupported_multicomponent",
            "More than two distinct ionic species; v1 does not balance those.",
            None,
            False,
        )
    if len(cations) == 1 and len(anions) == 1:
        theoretical = balance_two(
            ChargedSpecies(cations[0].identity, cations[0].charge),
            ChargedSpecies(anions[0].identity, anions[0].charge),
        )
        ratio = theoretical if isinstance(theoretical, TwoIonBalance) else None
        if drawn_total == 0:
            return _result(
                "charge_neutral",
                "Drawn charges cancel. The theoretical ratio is a separate fact.",
                ratio,
                True,
            )
        return _result(
            "unbalanced",
            "Drawn charges do not cancel. The theoretical ratio is diagnostic only.",
            ratio,
            False,
        )
    if ions:
        return _result(
            "unbalanced",
            "No opposite-charge partner in the drawing.",
            None,
            False,
        )
    if len(frags) == 1:
        atom_charges = [atom.GetFormalCharge() for atom in mol.GetAtoms()]
        if any(c > 0 for c in atom_charges) and any(c < 0 for c in atom_charges):
            return _result(
                "zwitterion",
                "One connected molecule with internal charges, not a salt pair.",
                None,
                False,
            )
    return _result(
        "not_a_salt",
        "No charged components.",
        None,
        False,
    )
