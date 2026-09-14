"""Geometry-dependent partial charges on the stored conformer.

The registered calculator in front of `chem/charge_equilibration.py`. That
module is pure arithmetic on element symbols and coordinates; this one reads
an RDKit conformer, refuses what it cannot compute honestly, and says what
the numbers are.

**ONLY METHODS PAST THEIR PRE-REGISTERED GATE ARE OFFERED.** Today that is
Bultinck 2002 part I EEM. Rappé–Goddard QEq is implemented and stopped at its
gate (`benchmarks/charges/rappe_goddard/README.md`: Table III's hydrogen
charges are not reproduced, and the paper's bound procedure misses the
constrained optimum), so it has no stored code here. `method` is still a
parameter so a method added later changes `parameters_key` rather than
silently sharing results.

**"AS DRAWN", DEFINED.** The stored conformer's own atoms, its own explicit
hydrogens and their coordinates, and its net formal charge. It does NOT mean
each atom keeps its formal charge: EEM distributes the net charge over the
whole molecule, so a nitro group's N+ and O- or a zwitterion's two centres
come back as partial charges that only SUM to the net. No protonation is
applied: no Dimorphite, no pKa.

**ATOM IDENTITY IS CARRIED, NOT INFERRED.** The solver sees the conformer's
atoms in the conformer's order and returns `solver_to_source`; every value is
written back through it. Keys are the conformer's atom indices, as for
`atom_sasa`, which agree with the drawing's because conformer generation
appends hydrogens. That last step is the shared OPEN item "GEOMETRY per-atom
datasets assume heavy atoms come first" in Known TODOs.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from rdkit import Chem

from openchem.chem import charge_equilibration as ce
from openchem.chem.calculator_options import decimals
from openchem.chem.geometry_analysis import NoConformerError, _require_conformer
from openchem.domain.common import ATOM_BASIS, EXPLICIT_H, HEAVY_ATOMS, TOTAL, CacheState, Provenance, declare_total
from openchem.domain.scientific_result import PerAtomDataset

#: The dataset id, and the calculator id it is registered under.
PROPERTY_ID = "geometry_partial_charge"

#: The one stored method code. It names the parameter set, not just the model,
#: so a second EEM parameterisation is a second code and never a reinterpretation.
EEM_BULTINCK2002_PART1 = "eem_bultinck2002_part1"
#: Every method offered, in combo order. Anything else raises.
GEOMETRY_CHARGE_METHODS = (EEM_BULTINCK2002_PART1,)
#: What each stored code is called on screen.
GEOMETRY_CHARGE_METHOD_LABELS = {EEM_BULTINCK2002_PART1: "EEM, Bultinck 2002"}

#: No 3D conformer: the resolver handed over the drawing, or a flat one.
REFUSE_NO_3D_GEOMETRY = "REFUSE_NO_3D_GEOMETRY"
#: Hydrogens implied by H counts rather than present as atoms with positions.
REFUSE_IMPLICIT_HYDROGENS = "REFUSE_IMPLICIT_HYDROGENS"
#: Hydrogen atoms present, but without finite coordinates.
REFUSE_MISSING_H_COORDINATES = "REFUSE_MISSING_H_COORDINATES"

#: What each refusal says. Stable, because help and the user guide quote them.
REFUSAL_MESSAGES = {
    REFUSE_NO_3D_GEOMETRY: (
        "EEM needs 3D coordinates, and this molecule has no 3D conformer. "
        "Generate conformers first (Structure ▸ Generate Conformers...)."
    ),
    REFUSE_IMPLICIT_HYDROGENS: (
        "EEM needs every hydrogen as an atom with a 3D position; this conformer "
        "implies hydrogens it does not contain, and the calculator will not invent them."
    ),
    REFUSE_MISSING_H_COORDINATES: (
        "EEM requires explicit hydrogen coordinates for this stored conformer. "
        "Some hydrogen atoms have no valid position, and the calculator will not invent them."
    ),
}
#: The table-cell form of each refusal; the full sentence is the error.
_SHORT = {
    REFUSE_NO_3D_GEOMETRY: "Needs a 3D conformer",
    REFUSE_IMPLICIT_HYDROGENS: "Hydrogens are not atoms",
    REFUSE_MISSING_H_COORDINATES: "Hydrogen positions missing",
    ce.REFUSE_ELEMENT_NOT_PARAMETERISED: "Element not parameterised",
    ce.REFUSE_OVERLAPPING_ATOMS: "Atoms overlap",
    ce.REFUSE_NOT_CONVERGED: "Did not converge",
}

#: Sigma q must equal the net charge to this. A necessary check, never evidence
#: the distribution is right: a wholly wrong one can still sum correctly.
_CONSERVATION_TOLERANCE = 1e-8

#: What "as drawn" means, written into every result's provenance.
AS_DRAWN = (
    "The stored conformer's atoms, explicit hydrogens and coordinates, with its net "
    "formal charge. Per-atom formal charges are not kept: the net charge is "
    "redistributed, so only the sum equals it. No protonation is applied."
)


def _refusal(code: str, name: str, method: str, places: int, molecule_uuid: str, message: str | None = None) -> PerAtomDataset:
    return PerAtomDataset(
        property_id=PROPERTY_ID,
        name=name,
        units="e",
        method=method,
        molecule_uuid=molecule_uuid,
        cache_state=CacheState.FAILED,
        inapplicable=True,
        error=message or REFUSAL_MESSAGES[code],
        error_summary=_SHORT.get(code, "Not computed"),
        provenance=Provenance(created_by="core", method=method, parameters={"refusal": code, "decimal_places": places}),
    )


def compute_geometry_charges(mol: Chem.Mol, molecule_uuid: str, parameters: dict[str, Any] | None = None) -> PerAtomDataset:
    """Partial charges from the conformer's own coordinates.

    `mol` is the ONE resolved snapshot the descriptor service hands every
    calculator: coordinates, atom order, the charges and the dataset all come
    from it, and nothing here reads the live molecule model.
    """
    parameters = parameters or {}
    places = decimals(parameters)
    method = str(parameters.get("method", EEM_BULTINCK2002_PART1))
    if method not in GEOMETRY_CHARGE_METHODS:
        raise ValueError(f"Unknown geometry charge method {method!r}; expected one of {GEOMETRY_CHARGE_METHODS}")
    include_hydrogens = bool(parameters.get("include_hydrogens", False))
    label = GEOMETRY_CHARGE_METHOD_LABELS[method]
    name = f"Partial Charge ({label}, 3D){' incl. H' if include_hydrogens else ''}"

    def refuse(code: str, message: str | None = None) -> PerAtomDataset:
        return _refusal(code, name, method, places, molecule_uuid, message)

    try:
        conformer = _require_conformer(mol)
    except NoConformerError:
        return refuse(REFUSE_NO_3D_GEOMETRY)
    if any(atom.GetTotalNumHs() > 0 for atom in mol.GetAtoms()):
        return refuse(REFUSE_IMPLICIT_HYDROGENS)
    positions = np.array(conformer.GetPositions(), dtype=float)
    elements = [atom.GetSymbol() for atom in mol.GetAtoms()]
    finite = np.all(np.isfinite(positions), axis=1)
    if not np.all(finite):
        if any(not finite[i] and elements[i] == "H" for i in range(len(elements))):
            return refuse(REFUSE_MISSING_H_COORDINATES)
        return refuse(REFUSE_NO_3D_GEOMETRY)

    net_charge = float(Chem.GetFormalCharge(mol))
    result = ce.eem_charges(elements, positions, net_charge)
    if result.status != "converged":
        return refuse(result.status, result.message)

    own = {result.solver_to_source[k]: float(result.charges[k]) for k in range(len(elements))}
    every_atom = sum(own.values())
    if abs(every_atom - net_charge) > _CONSERVATION_TOLERANCE:
        raise ValueError(f"EEM charges sum to {every_atom:+.10f} on a conformer of net charge {net_charge:+.0f}")

    if include_hydrogens:
        values: dict[int, float] = {}
        for atom in mol.GetAtoms():
            index = atom.GetIdx()
            heavy_neighbours = [n.GetIdx() for n in atom.GetNeighbors() if n.GetAtomicNum() != 1]
            if atom.GetAtomicNum() == 1 and heavy_neighbours:
                continue
            values[index] = own[index]
        for atom in mol.GetAtoms():
            if atom.GetAtomicNum() != 1:
                continue
            heavy_neighbours = [n.GetIdx() for n in atom.GetNeighbors() if n.GetAtomicNum() != 1]
            if heavy_neighbours:
                values[heavy_neighbours[0]] += own[atom.GetIdx()]
        basis = EXPLICIT_H if any(mol.GetAtomWithIdx(i).GetAtomicNum() == 1 for i in values) else HEAVY_ATOMS
        if abs(sum(values.values()) - net_charge) > _CONSERVATION_TOLERANCE:
            raise ValueError("Folding hydrogens onto their neighbours lost or doubled a charge")
    else:
        values = own
        basis = EXPLICIT_H if any(e == "H" for e in elements) else HEAVY_ATOMS

    return PerAtomDataset(
        property_id=PROPERTY_ID,
        name=name,
        units="e",
        method=method,
        molecule_uuid=molecule_uuid,
        values=values,
        provenance=Provenance(
            created_by="core",
            method=method,
            parameters={
                "method": method,
                "parameter_set": "bultinck_2002_part_I_table_1",
                "source": "bultinck2002a (J. Phys. Chem. A 2002, 106, 7887; doi:10.1021/jp0205463)",
                "equation_convention": ce.EEM_EQUATION_CONVENTION,
                "kappa": "1 hartree bohr",
                "hartree_ev": ce.HARTREE_EV,
                "bohr_angstrom": ce.EEM_BOHR_ANGSTROM,
                "species": AS_DRAWN,
                "net_charge": net_charge,
                "include_hydrogens": include_hydrogens,
                "hydrogen_aggregation": "folded" if include_hydrogens else "separate",
                "solver_to_source": list(result.solver_to_source),
                "equalized_electronegativity_ev": result.equalized_electronegativity_ev,
                "decimal_places": places,
                "not_applied": "protonation at a pH",
                ATOM_BASIS: basis,
                TOTAL: declare_total(every_atom, "Net calculated charge", units="e", basis=basis),
            },
        ),
    )
