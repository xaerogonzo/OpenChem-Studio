from __future__ import annotations

from rdkit import Chem

from openchem.chem.conformer_providers import RDKitConformerProvider
from openchem.domain.scientific_result import NMRSpectrumResult

# TMS (tetramethylsilane, Si(CH3)4) -- the standard 1H/13C NMR chemical
# shift reference compound. Its 12 equivalent H and 4 equivalent C atoms
# (real Td-symmetry equivalence, not an approximation) let one reference
# calculation cover both nuclei this app's NMR path reports.
_TMS_SMILES = "C[Si](C)(C)C"

_SPECTRUM_TYPE_BY_ELEMENT = {"H": "nmr_1h", "C": "nmr_13c"}


def tms_molecule() -> Chem.Mol:
    """Builds a real, embedded-and-optimized TMS structure via the exact
    same `RDKitConformerProvider` path every real molecule already goes
    through before an ORCA job -- not a shortcut/simplified geometry.
    """
    mol = Chem.MolFromSmiles(_TMS_SMILES)
    conformers = RDKitConformerProvider().generate_conformers(mol, num_conformers=1, optimize=True)
    if not conformers:
        raise RuntimeError("Failed to embed a TMS reference conformer")
    return conformers[0][0]


def average_reference_shielding(raw: NMRSpectrumResult) -> dict[str, float]:
    """Averages TMS's per-element isotropic shielding across its
    chemically-equivalent nuclei (12 H, 4 C) for a more robust reference
    value than picking one arbitrary atom -- real molecular symmetry, not
    a simplification.
    """
    totals: dict[str, float] = {}
    counts: dict[str, int] = {}
    for atom_index, shielding in raw.values.items():
        element = raw.elements.get(atom_index)
        if element is None:
            continue
        totals[element] = totals.get(element, 0.0) + shielding
        counts[element] = counts.get(element, 0) + 1
    return {element: totals[element] / counts[element] for element in totals}


def chemical_shift_from_reference(
    raw: NMRSpectrumResult, reference: dict[str, float]
) -> NMRSpectrumResult | None:
    """delta = reference[element] - raw_shielding -- the standard NMR
    referencing convention (higher shielding = more shielded = lower ppm).
    Only converts atoms whose element has a cached reference value (H/C
    today); returns None if nothing in `raw` has a covered element. A
    single combined result can mix elements (e.g. both H and C), matching
    the existing raw-shielding result's own precedent of one
    ScientificResult per ORCA job rather than splitting per element.
    """
    covered_values: dict[int, float] = {}
    covered_elements: dict[int, str] = {}
    for atom_index, element in raw.elements.items():
        if element not in reference or atom_index not in raw.values:
            continue
        covered_values[atom_index] = reference[element] - raw.values[atom_index]
        covered_elements[atom_index] = element

    if not covered_values:
        return None

    return NMRSpectrumResult(
        spectrum_type="nmr_calibrated",
        name="NMR Chemical Shift (referenced to TMS)",
        units="ppm (delta, referenced to TMS)",
        method=raw.method,
        molecule_uuid=raw.molecule_uuid,
        values=covered_values,
        elements=covered_elements,
        provenance=raw.provenance,
    )
