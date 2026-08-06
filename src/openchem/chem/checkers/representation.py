"""How a structure is written down, as distinct from whether it is possible.

Nothing here is an error. Every one of these is something a chemist does on
purpose somewhere -- a salt is two fragments, a deuterated standard carries
an isotope, a nitroxide carries a radical, a Markush scaffold carries query
atoms. They are reported because they change what downstream tools will do
with the structure, not because they are wrong.
"""

from __future__ import annotations

from typing import Any

from openchem.chem.structure_check import (
    PARSED_MOLECULE,
    SANITIZED_MOLECULE,
    Basis,
    Category,
    CheckContext,
    CheckerDefinition,
    Severity,
    StructureIssue,
)
from openchem.domain.common import Provenance

_RDKIT = Provenance(created_by="core", method="RDKit")


def _check_fragments(context: CheckContext) -> list[StructureIssue]:
    from rdkit import Chem

    fragments = Chem.GetMolFrags(context.mol, asMols=False, sanitizeFrags=False)
    if len(fragments) < 2:
        return []
    sizes = sorted((len(f) for f in fragments), reverse=True)
    return [
        StructureIssue(
            checker_id="disconnected_fragments",
            category=Category.REPRESENTATION,
            severity=Severity.WARNING,
            basis=Basis.DETERMINISTIC,
            message=(
                f"{len(fragments)} disconnected fragments ({', '.join(str(s) for s in sizes)} atoms). "
                "Salts and solvates look like this; so does a bond somebody meant to draw and did not."
            ),
            atom_indices=tuple(sorted(i for f in fragments[1:] for i in f)),
            fix_id="keep_largest_fragment",
        )
    ]


def _check_charge(context: CheckContext) -> list[StructureIssue]:
    from rdkit import Chem

    total = Chem.GetFormalCharge(context.mol)
    if total == 0:
        return []
    charged = tuple(a.GetIdx() for a in context.mol.GetAtoms() if a.GetFormalCharge() != 0)
    return [
        StructureIssue(
            checker_id="molecule_charge",
            category=Category.REPRESENTATION,
            severity=Severity.WARNING,
            basis=Basis.DETERMINISTIC,
            message=(
                f"Net charge {total:+d}. Deliberate for an ion; otherwise a missing "
                "counter-ion or a charge left behind by an edit."
            ),
            atom_indices=charged,
        )
    ]


def _check_explicit_hydrogens(context: CheckContext) -> list[StructureIssue]:
    explicit = tuple(a.GetIdx() for a in context.mol.GetAtoms() if a.GetAtomicNum() == 1)
    if not explicit:
        return []
    return [
        StructureIssue(
            checker_id="explicit_hydrogen",
            category=Category.REPRESENTATION,
            severity=Severity.INFO,
            basis=Basis.DETERMINISTIC,
            message=(
                f"{len(explicit)} hydrogens are drawn explicitly. They will be matched "
                "literally by substructure search, which is usually not what is wanted."
            ),
            atom_indices=explicit,
            fix_id="remove_explicit_hydrogens",
        )
    ]


def _check_isotopes(context: CheckContext) -> list[StructureIssue]:
    labelled = tuple(a.GetIdx() for a in context.mol.GetAtoms() if a.GetIsotope())
    if not labelled:
        return []
    symbols = ", ".join(
        f"{a.GetIsotope()}{a.GetSymbol()}" for a in context.mol.GetAtoms() if a.GetIsotope()
    )
    return [
        StructureIssue(
            checker_id="isotope",
            category=Category.REPRESENTATION,
            severity=Severity.INFO,
            basis=Basis.DETERMINISTIC,
            message=f"Isotopically labelled: {symbols}. Mass and formula reflect the label.",
            atom_indices=labelled,
        )
    ]


def _check_radicals(context: CheckContext) -> list[StructureIssue]:
    radicals = tuple(a.GetIdx() for a in context.mol.GetAtoms() if a.GetNumRadicalElectrons())
    if not radicals:
        return []
    return [
        StructureIssue(
            checker_id="radical",
            category=Category.REPRESENTATION,
            severity=Severity.INFO,
            basis=Basis.DETERMINISTIC,
            message=(
                f"{len(radicals)} atoms carry unpaired electrons. Real for a nitroxide or a "
                "persistent radical; otherwise usually a hydrogen count that was not intended."
            ),
            atom_indices=radicals,
        )
    ]


def _check_query_atoms(context: CheckContext) -> list[StructureIssue]:
    dummies = tuple(a.GetIdx() for a in context.mol.GetAtoms() if a.GetAtomicNum() == 0)
    if not dummies:
        return []
    return [
        StructureIssue(
            checker_id="query_atom",
            category=Category.REPRESENTATION,
            severity=Severity.INFO,
            basis=Basis.DETERMINISTIC,
            message=(
                f"{len(dummies)} query or R-group atoms. This is a template rather than a "
                "single compound, so property calculations will not be meaningful."
            ),
            atom_indices=dummies,
        )
    ]


def _check_unknown_stereo(context: CheckContext) -> list[StructureIssue]:
    """Stereocentres the drawing leaves undefined.

    A WARNING rather than INFO because it changes what the structure *is*:
    an undefined centre means the drawing describes a mixture, and every
    downstream identifier (InChI, canonical SMILES, an InChIKey pasted into
    a database) will describe that mixture rather than the compound the
    author probably had in mind.
    """
    from rdkit import Chem

    unspecified = Chem.FindMolChiralCenters(
        context.mol, includeUnassigned=True, useLegacyImplementation=False
    )
    undefined = tuple(idx for idx, label in unspecified if label == "?")
    if not undefined:
        return []
    return [
        StructureIssue(
            checker_id="unknown_stereo",
            category=Category.REPRESENTATION,
            severity=Severity.WARNING,
            basis=Basis.DETERMINISTIC,
            message=(
                f"{len(undefined)} stereocentres have no configuration. The structure "
                "describes a mixture, and its InChI and canonical SMILES will say so."
            ),
            atom_indices=undefined,
        )
    ]


_CHECKERS = (
    ("disconnected_fragments", "Disconnected fragments", _check_fragments, PARSED_MOLECULE),
    ("molecule_charge", "Net charge", _check_charge, PARSED_MOLECULE),
    ("explicit_hydrogen", "Explicit hydrogens", _check_explicit_hydrogens, PARSED_MOLECULE),
    ("isotope", "Isotopes", _check_isotopes, PARSED_MOLECULE),
    ("radical", "Radicals", _check_radicals, PARSED_MOLECULE),
    ("query_atom", "Query atoms", _check_query_atoms, PARSED_MOLECULE),
    ("unknown_stereo", "Undefined stereocentres", _check_unknown_stereo, SANITIZED_MOLECULE),
)


def register(registry: Any) -> None:
    for checker_id, display_name, run, requirement in _CHECKERS:
        registry.register(
            CheckerDefinition(
                checker_id=checker_id,
                display_name=display_name,
                category=Category.REPRESENTATION,
                run=run,
                requires=frozenset({requirement}),
                provenance=_RDKIT,
            )
        )
