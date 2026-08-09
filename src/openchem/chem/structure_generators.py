"""Generators that turn one structure into a SET of structures.

Stereoisomers, tautomers and resonance forms. Each returns a
`StructureSetResult` rendered by the shared structure grid.

A NOTE ON RESONANCE, confirmed live and load-bearing for both the code and
the UI:

1. `ResonanceMolSupplier` with DEFAULT flags returns **zero** forms for
   diazomethane -- which is the example in Marvin's own documentation.
   `ALLOW_CHARGE_SEPARATION` is required to get any, and adding
   `ALLOW_INCOMPLETE_OCTETS|UNCONSTRAINED_CATIONS|UNCONSTRAINED_ANIONS`
   takes it from 2 forms to 6. So the flag set is a user-facing option,
   not a hardcoded default.
2. Resonance forms COLLAPSE under canonical SMILES -- acetate's two forms
   both serialize to `CC(=O)[O-]`. They are genuinely different molecules
   with different bond orders; only the canonical normalization hides it.
   Nothing here may deduplicate on canonical SMILES, or half the results
   silently disappear.
"""

from __future__ import annotations

from typing import Any

from rdkit import Chem
from rdkit.Chem import AllChem
from rdkit.Chem.EnumerateStereoisomers import EnumerateStereoisomers, StereoEnumerationOptions
from rdkit.Chem.MolStandardize import rdMolStandardize

from openchem.domain.common import CacheState, Provenance
from openchem.domain.scientific_result import StructureEntry, StructureSetResult

# Marvin offers "major contributors" versus everything. These two flag sets
# are that distinction, with the exact behaviour confirmed on diazomethane.
RESONANCE_FLAG_SETS: dict[str, int] = {
    "Major contributors": Chem.ALLOW_CHARGE_SEPARATION,
    "All forms (charge-separated, incomplete octets)": (
        Chem.ALLOW_CHARGE_SEPARATION
        | Chem.ALLOW_INCOMPLETE_OCTETS
        | Chem.UNCONSTRAINED_CATIONS
        | Chem.UNCONSTRAINED_ANIONS
    ),
}

DEFAULT_MAX_STRUCTURES = 200


def _entry(mol: Chem.Mol, label: str, **extra: Any) -> StructureEntry:
    """Serializes to a molblock with 2D coordinates, which is what the grid
    depiction needs -- a molblock with no coordinates renders as a pile.

    IT ONLY COMPUTES THEM WHEN THERE ARE NONE, so whatever coordinates the
    caller's molecule carries propagate straight into the depiction. That
    is one of three reasons the generators in this module declare
    `CalculationInput.DRAWING` and must not be given a 3D conformer to be
    helpful -- the other two are worse, and are recorded on
    `enumerate_stereoisomers` and `enumerate_tautomers`.
    `tests/test_calculation_input.py` guards all three."""
    prepared = Chem.Mol(mol)
    if prepared.GetNumConformers() == 0:
        AllChem.Compute2DCoords(prepared)
    return StructureEntry(molblock=Chem.MolToMolBlock(prepared, kekulize=False), label=label, **extra)


def enumerate_stereoisomers(
    mol: Chem.Mol,
    molecule_uuid: str,
    max_isomers: int = DEFAULT_MAX_STRUCTURES,
    only_unassigned: bool = True,
) -> StructureSetResult:
    """Every stereoisomer of `mol`.

    `only_unassigned=True` (the default, and RDKit's) keeps any stereo the
    user actually drew and varies only the centres left unspecified --
    which is almost always what someone asking "what are the stereoisomers"
    of a partly-defined structure means.

    THIS MUST BE GIVEN THE DRAWING, NEVER A 3D CONFORMER. A conformer
    carries stereo PERCEIVED FROM ITS COORDINATES, so every centre is
    assigned and `only_unassigned` finds nothing left to vary. Measured on
    alanine with its stereocentre unspecified: the drawing enumerates 2
    isomers, a conformer of it enumerates 1 -- whichever configuration the
    embedder happened to produce. That is not a lower-quality answer, it
    is the feature silently not working, and only the drawing can answer
    the question that was asked.
    """
    options = StereoEnumerationOptions(maxIsomers=max_isomers, onlyUnassigned=only_unassigned)
    isomers = list(EnumerateStereoisomers(mol, options=options))
    entries = [
        _entry(isomer, Chem.MolToSmiles(isomer), metadata={"smiles": Chem.MolToSmiles(isomer)})
        for isomer in isomers
    ]
    return StructureSetResult(
        set_id="stereoisomers",
        name=f"Stereoisomers ({len(entries)})",
        method="rdkit",
        molecule_uuid=molecule_uuid,
        entries=entries,
        truncated=len(entries) >= max_isomers,
        provenance=Provenance(
            created_by="core", method="rdkit", parameters={"only_unassigned": only_unassigned}
        ),
    )


def enumerate_tautomers(
    mol: Chem.Mol, molecule_uuid: str, max_tautomers: int = DEFAULT_MAX_STRUCTURES
) -> StructureSetResult:
    """Every tautomer RDKit's standardizer can reach, with the canonical
    one flagged -- which is the one a database would store, so it is worth
    pointing at rather than leaving the user to guess.

    THIS MUST BE GIVEN THE DRAWING, NEVER A 3D CONFORMER, and here the
    failure is corruption rather than collapse. A conformer's EXPLICIT
    HYDROGENS send the enumerator into structures that are not tautomers
    of anything -- measured on alanine, 4 sensible forms from the drawing
    against 10 from a conformer of it, including `[H]O=C(O)...` and
    `[CH]([H])...`. More results, all worse, which is the shape of bug
    that gets shipped."""
    enumerator = rdMolStandardize.TautomerEnumerator()
    enumerator.SetMaxTautomers(max_tautomers)
    tautomers = list(enumerator.Enumerate(mol))
    canonical = Chem.MolToSmiles(enumerator.Canonicalize(mol))

    entries = []
    for tautomer in tautomers:
        smiles = Chem.MolToSmiles(tautomer)
        is_canonical = smiles == canonical
        entries.append(
            _entry(
                tautomer,
                f"{smiles} (canonical)" if is_canonical else smiles,
                metadata={"smiles": smiles, "canonical": is_canonical},
            )
        )
    return StructureSetResult(
        set_id="tautomers",
        name=f"Tautomers ({len(entries)})",
        method="rdkit",
        molecule_uuid=molecule_uuid,
        entries=entries,
        truncated=len(entries) >= max_tautomers,
        provenance=Provenance(created_by="core", method="rdkit"),
    )


def enumerate_resonance_forms(
    mol: Chem.Mol,
    molecule_uuid: str,
    flag_set: str = "Major contributors",
    max_forms: int = DEFAULT_MAX_STRUCTURES,
) -> StructureSetResult:
    """Resonance contributors.

    See the module docstring: the default RDKit flags return nothing useful
    (zero forms for diazomethane), and canonical SMILES collapses distinct
    forms, so entries are built from the mol objects and NOT deduplicated
    on SMILES.
    """
    flags = RESONANCE_FLAG_SETS.get(flag_set, Chem.ALLOW_CHARGE_SEPARATION)
    supplier = Chem.ResonanceMolSupplier(mol, flags)
    supplier.SetNumThreads(1)

    entries = []
    for index, form in enumerate(supplier):
        if form is None or index >= max_forms:
            break
        # Kekulized SMILES, because the canonical aromatic form is exactly
        # what hides the difference between contributors.
        try:
            kekulized = Chem.MolToSmiles(form, kekuleSmiles=True)
        except Exception:  # noqa: BLE001 - some forms can't kekulize; the structure is still valid
            kekulized = Chem.MolToSmiles(form)
        entries.append(_entry(form, f"Form {index + 1}", metadata={"smiles": kekulized}))

    return StructureSetResult(
        # Matches the registered calculator_id exactly -- PropertyPanel
        # pairs a result to the click that asked for it on this string.
        set_id="resonance_forms",
        name=f"Resonance forms ({len(entries)})",
        method="rdkit",
        molecule_uuid=molecule_uuid,
        entries=entries,
        truncated=len(entries) >= max_forms,
        provenance=Provenance(created_by="core", method="rdkit", parameters={"flags": flag_set}),
    )


def compute_stereoisomers(
    mol: Chem.Mol, molecule_uuid: str, parameters: dict[str, Any] | None = None
) -> StructureSetResult:
    parameters = parameters or {}
    return enumerate_stereoisomers(
        mol,
        molecule_uuid,
        max_isomers=int(parameters.get("max_structures", DEFAULT_MAX_STRUCTURES)),
        only_unassigned=bool(parameters.get("only_unassigned", True)),
    )


def compute_tautomers(
    mol: Chem.Mol, molecule_uuid: str, parameters: dict[str, Any] | None = None
) -> StructureSetResult:
    parameters = parameters or {}
    return enumerate_tautomers(
        mol, molecule_uuid, max_tautomers=int(parameters.get("max_structures", DEFAULT_MAX_STRUCTURES))
    )


def compute_resonance_forms(
    mol: Chem.Mol, molecule_uuid: str, parameters: dict[str, Any] | None = None
) -> StructureSetResult:
    parameters = parameters or {}
    return enumerate_resonance_forms(
        mol,
        molecule_uuid,
        flag_set=parameters.get("flag_set", "Major contributors"),
        max_forms=int(parameters.get("max_structures", DEFAULT_MAX_STRUCTURES)),
    )
