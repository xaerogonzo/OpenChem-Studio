"""Build a salt-composition preview from molecules. RDKit stays here.

The window never imports this module's toolkit; it is handed a ``SaltPreview``.
pKa is recorded as evidence and is never used to rank or to pick a ratio.
"""

from __future__ import annotations

from rdkit import Chem

from openchem.chem.salt_components import (
    IdentityRefusal,
    ModeBResult,
    analyze_drawing,
    fragment_formal_charge,
)
from openchem.chem.salt_ionization import select_by_net_charge, structures_at_net_charge
from openchem.chem.salt_mode_a import compose_from_ion_mols, compose_from_mols, species_from_mol
from openchem.chem.salt_mode_c import enumerate_pair
from openchem.domain.salt_evidence import assess_pka_compatible
from openchem.domain.salt_preview import (
    MODE_ANALYZE,
    MODE_ENUMERATE,
    MODE_IONS,
    MODE_NEUTRALS,
    SaltPreview,
    make_preview,
)
from openchem.domain.salt_stoichiometry import (
    KIND_METAL_HYDROXIDE,
    IonizationRefusal,
    ModeAComposition,
    ModeARefusal,
)

REACHED_BY = (
    "window: MainWindow.show_salt_composition evaluates through this module"
)


def _pka_line(*, already_charged: bool) -> str:
    claim = assess_pka_compatible(
        already_charged=already_charged,
        proposed_acid_step_id="",
        proposed_conjugate_acid_step_id="",
        acid=None,
        conjugate_acid=None,
    )
    if claim.delta is None:
        return f"pKa evidence: {claim.verdict} — {claim.reason}"
    return f"pKa evidence: {claim.verdict} (ΔpKa {claim.delta})"


def _refusal_preview(mode: str, code: str, reason: str) -> SaltPreview:
    return make_preview(mode, reason, (f"Refused ({code}).",), charge_valid=False)


def _from_identity(mode: str, refused: IdentityRefusal) -> SaltPreview:
    return _refusal_preview(mode, refused.code, refused.reason)


def _from_mode_a(
    mode: str,
    result: ModeAComposition | ModeARefusal | IdentityRefusal,
    *,
    already_charged: bool,
) -> SaltPreview:
    if isinstance(result, IdentityRefusal):
        return _from_identity(mode, result)
    if isinstance(result, ModeARefusal):
        return _refusal_preview(mode, result.code, result.reason)
    return make_preview(
        mode,
        f"Formula unit {result.cation_count} : {result.anion_count} (cation : anion).",
        (
            f"charge_valid: {result.charge_valid}",
            _pka_line(already_charged=already_charged),
        ),
        charge_valid=result.charge_valid,
    )


def _from_mode_b(result: ModeBResult) -> SaltPreview:
    lines = [
        f"code: {result.code}",
        f"drawn total charge: {result.drawn_total_charge:+d}",
        f"charge_valid: {result.charge_valid}",
    ]
    if result.theoretical is not None:
        lines.append(
            "theoretical ratio (not a correction of the drawing): "
            f"{result.theoretical.cation_count} : {result.theoretical.anion_count}"
        )
    if result.extras:
        lines.append(
            f"{len(result.extras)} uncharged fragment(s) set aside; they are not a hydrate field."
        )
    lines.append(_pka_line(already_charged=True))
    return make_preview(
        MODE_ANALYZE,
        result.reason,
        tuple(lines),
        charge_valid=result.charge_valid,
    )


def _ion_from_key(key: str) -> Chem.Mol | IdentityRefusal:
    mol = Chem.MolFromSmiles(key)
    if mol is None:
        return IdentityRefusal(
            code="unsanitizable",
            reason="The ionized structure could not be read back from its identity key.",
        )
    return mol


def _unique_ion(mol: Chem.Mol, target_charge: int) -> Chem.Mol | IonizationRefusal | IdentityRefusal:
    chosen = select_by_net_charge(mol, target_charge)
    if isinstance(chosen, (IonizationRefusal, IdentityRefusal)):
        return chosen
    return _ion_from_key(chosen)


def _states(mol: Chem.Mol, want_positive: bool) -> list[Chem.Mol]:
    """User ion if already the right sign, plus N/O/P/S states at ±1 and ±2."""
    mols: list[Chem.Mol] = []
    charge = fragment_formal_charge(mol)
    if (want_positive and charge > 0) or ((not want_positive) and charge < 0):
        mols.append(mol)
    for step in (1, 2):
        target = step if want_positive else -step
        for key in structures_at_net_charge(mol, target):
            built = _ion_from_key(key)
            if isinstance(built, IdentityRefusal):
                continue
            mols.append(built)
    return mols


def compose(mode: str, first: Chem.Mol | None, second: Chem.Mol | None) -> SaltPreview:
    """One preview for the four window modes. Never ranks by pKa."""
    if first is None:
        return make_preview(mode, "Pick a molecule in the project.")
    if mode == MODE_ANALYZE:
        return _from_mode_b(analyze_drawing(first))
    if second is None:
        return make_preview(mode, "A pair needs two molecules.")
    if mode == MODE_NEUTRALS:
        for parent in (first, second):
            species = species_from_mol(parent)
            if isinstance(species, IdentityRefusal):
                return _from_identity(mode, species)
            if species.kind == KIND_METAL_HYDROXIDE:
                return _refusal_preview(
                    mode,
                    "hydroxide_neutralization",
                    (
                        "Metal-hydroxide neutralization is not two-neutral proton "
                        "transfer; v1 does not form water and a spectator cation."
                    ),
                )
        cation = _unique_ion(first, 1)
        if isinstance(cation, IdentityRefusal):
            return _from_identity(mode, cation)
        if isinstance(cation, IonizationRefusal):
            return _refusal_preview(mode, cation.code, cation.reason)
        anion = _unique_ion(second, -1)
        if isinstance(anion, IdentityRefusal):
            return _from_identity(mode, anion)
        if isinstance(anion, IonizationRefusal):
            return _refusal_preview(mode, anion.code, anion.reason)
        return _from_mode_a(
            mode,
            compose_from_mols(first, second, cation, anion),
            already_charged=False,
        )
    if mode == MODE_IONS:
        return _from_mode_a(
            mode,
            compose_from_ion_mols(first, second),
            already_charged=True,
        )
    if mode == MODE_ENUMERATE:
        cations = _states(first, True)
        anions = _states(second, False)
        if not cations or not anions:
            return make_preview(
                mode,
                "Enumeration needs a cation state of the first molecule and an anion state of the second.",
            )
        result = enumerate_pair(cations, anions)
        if isinstance(result, IdentityRefusal):
            return _from_identity(mode, result)
        if not result.hits:
            return make_preview(
                mode,
                "No charge-balanced pair in that set.",
                (f"generated {result.generated}, returned {result.returned}, omitted {result.omitted}.",)
                + result.notes,
                notes=result.notes,
            )
        first_hit = result.hits[0]
        lines = [
            f"{hit.cation_count} : {hit.anion_count}  {hit.cation_identity} / {hit.anion_identity}"
            f"{'  (charge_valid)' if hit.charge_valid else ''}"
            for hit in result.hits
        ]
        lines.append(
            f"generated {result.generated}, returned {result.returned}, omitted {result.omitted}."
        )
        lines.append(_pka_line(already_charged=True))
        lines.extend(result.notes)
        return make_preview(
            mode,
            f"{result.returned} composition(s). First: {first_hit.cation_count} : {first_hit.anion_count}.",
            tuple(lines),
            charge_valid=first_hit.charge_valid,
            notes=result.notes,
        )
    return make_preview(mode, f"Unknown mode {mode!r}.")
