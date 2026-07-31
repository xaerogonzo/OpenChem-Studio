"""Elemental composition of a molecule.

Validated against MarvinSketch's own Elemental Analysis output for
tyramine hydrochloride (the molecule in its documentation screenshot):
formula `C8H12ClNO`, exact mass 173.060742 (Marvin: 173.060741718), atom
count 23, and composition C 55.34 / H 6.97 / Cl 20.42 / N 8.07 / O 9.21 --
every percentage matching to the two decimals Marvin reports.

Average molecular mass comes out 173.643 against Marvin's 173.640. That is
a standard-atomic-weight table revision, not an error in either tool:
IUPAC revises these periodically and the two were built against different
editions. Not worth chasing, but worth knowing before someone reports it
as a bug.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from rdkit import Chem
from rdkit.Chem import Descriptors, rdMolDescriptors

from openchem.chem.calculator_options import (
    apply_microspecies,
    decimals,
    microspecies_note,
)
from openchem.domain.common import Provenance
from openchem.domain.scientific_result import AlertResult


def molecular_formula(mol: Chem.Mol) -> str:
    return rdMolDescriptors.CalcMolFormula(mol)


def isotope_formula(mol: Chem.Mol) -> str:
    """Formula listing explicitly-isotope-labelled atoms separately, e.g.
    `C6H5[2H]` for mono-deuterated benzene. Identical to the plain formula
    for a molecule with no isotope labels, which is the common case."""
    counts: Counter[str] = Counter()
    for atom in mol.GetAtoms():
        isotope = atom.GetIsotope()
        symbol = f"[{isotope}{atom.GetSymbol()}]" if isotope else atom.GetSymbol()
        counts[symbol] += 1
        # Implicit/explicit hydrogens attached to this atom carry no
        # isotope label of their own -- they are ordinary H.
        hydrogens = atom.GetTotalNumHs()
        if hydrogens:
            counts["H"] += hydrogens
    return "".join(
        f"{symbol}{count if count > 1 else ''}" for symbol, count in sorted(counts.items())
    )


def dot_disconnected_formula(mol: Chem.Mol) -> str:
    """Per-fragment formulas joined by dots, e.g. `C8H11NO.ClH` for a
    hydrochloride salt -- which is how a salt's composition is normally
    written, and what Marvin reports separately from the plain formula."""
    fragments = Chem.GetMolFrags(mol, asMols=True, sanitizeFrags=False)
    return ".".join(rdMolDescriptors.CalcMolFormula(fragment) for fragment in fragments)


def element_composition(mol: Chem.Mol) -> dict[str, float]:
    """Mass percentage (w/w %) per element.

    Requires explicit hydrogens to be correct -- a molecule with implicit
    H would report 0% hydrogen. `compute_elemental_analysis` adds them.
    """
    counts = Counter(atom.GetSymbol() for atom in mol.GetAtoms())
    table = Chem.GetPeriodicTable()
    masses = {element: count * table.GetAtomicWeight(element) for element, count in counts.items()}
    total = sum(masses.values())
    if total <= 0.0:
        return {}
    return {element: 100.0 * mass / total for element, mass in sorted(masses.items())}


def compute_elemental_analysis(
    mol: Chem.Mol, molecule_uuid: str, parameters: dict[str, Any] | None = None
) -> AlertResult:
    """The "identity" category's Elemental Analysis calculator.

    Reported as an `AlertResult` rather than a pile of separate scalars
    because it is one coherent readout a chemist reads together -- exactly
    how Marvin's own Elemental Analysis window presents it -- and because
    `AlertResult.matched` already renders as a labelled list in the
    Property Panel with no new result shape or view needed.
    """
    parameters = parameters or {}
    places = decimals(parameters)
    # Explicit hydrogens or the composition is wrong: RDKit keeps H
    # implicit by default, and an implicit H contributes no atom to count.
    mol_with_h = Chem.AddHs(apply_microspecies(mol, parameters))
    composition = element_composition(mol_with_h)
    plain = molecular_formula(mol_with_h)
    dotted = dot_disconnected_formula(mol_with_h)

    lines = [
        f"Formula: {plain}",
        f"Mass: {Descriptors.MolWt(mol_with_h):.{max(places, 3)}f}",
        f"Exact mass: {Descriptors.ExactMolWt(mol_with_h):.{max(places, 6)}f}",
        f"Atom count: {mol_with_h.GetNumAtoms()}",
    ]
    # Only shown when it actually says something new -- a single-fragment
    # molecule's dot-disconnected formula IS its formula, and repeating it
    # is noise.
    if dotted != plain:
        lines.append(f"Dot-disconnected formula: {dotted}")
    isotopes = isotope_formula(mol_with_h)
    if any(atom.GetIsotope() for atom in mol_with_h.GetAtoms()):
        lines.append(f"Isotope formula: {isotopes}")
    lines.extend(
        f"{element}: {percent:.{places}f}%" for element, percent in composition.items()
    )
    lines.extend(microspecies_note(parameters))

    return AlertResult(
        alert_id="elemental_analysis",
        name="Elemental Analysis",
        molecule_uuid=molecule_uuid,
        matched=lines,
        category="identity",
        provenance=Provenance(created_by="core", method="rdkit"),
    )
