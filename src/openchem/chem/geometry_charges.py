"""Geometry-dependent partial charges on the stored conformer.

The registered calculator in front of `chem/charge_equilibration.py`. That
module is pure arithmetic on element symbols and coordinates; this one reads
an RDKit conformer, refuses what it cannot compute honestly, and says what
the numbers are.

**ONLY METHODS WHOSE CURRENT SHIPPING VALIDATION SCOPE IS SATISFIED ARE
OFFERED.** Bultinck 2002 part I EEM passed its pre-registered gate.
Rappé–Goddard QEq did NOT pass its original gate (O4/O5, which stay failed);
it is offered under the narrower scope of amendment A8 of
`benchmarks/charges/rappe_goddard/preregistration.md`: lambda = 1/2, the
experimental hydrogen set only, refusing non-convergence and any solution
with an active charge bound, and noting silicon as a source discrepancy.
Each method is its own stored code, so the two never share a result.

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
from openchem.chem.protonation_geometry import (
    PROTONATION_SELECTION_POLICY_VERSION,
    REFUSE_AMBIGUOUS_H_IDENTITY,
    REFUSE_H_PLACEMENT,
    REFUSE_NOT_IONISATION_ONLY,
    REFUSE_PROTONATION_FAILED,
    protonate_conformer,
)
from openchem.domain.common import ATOM_BASIS, EXPLICIT_H, HEAVY_ATOMS, TOTAL, CacheState, Provenance, declare_total
from openchem.domain.scientific_result import PerAtomDataset

#: The dataset id, and the calculator id it is registered under.
PROPERTY_ID = "geometry_partial_charge"
#: The pH calculator's OWN dataset id. **The panel keys results by property_id, not by calculator
#: id**, so sharing one id made the pH result overwrite the as-drawn result instead of appearing
#: beside it -- found by driving the app, with every unit test green.
PROPERTY_ID_AT_PH = "geometry_partial_charge_at_ph"

#: The stored method codes. Each names its parameter set and reading, not just
#: the model, so another parameterisation is another code, never a reinterpretation.
EEM_BULTINCK2002_PART1 = "eem_bultinck2002_part1"
#: Rappé–Goddard 1991 QEq, lambda = 1/2 (eq 17'), experimental hydrogen set:
#: the one QEq reading amendment A8 ships.
QEQ_RG1991_LAMBDA_HALF_H_EXPERIMENTAL = "qeq_rg1991_lambda_half_h_experimental"
#: Ionescu et al. 2013's E-typing Mulliken model at 6-31G*, gas phase -- one of the two of its 24
#: parameterisations that ship (`benchmarks/charges/models/ionescu_src_preregistration.md` §10).
EEM_IONESCU2013_E_MPA_631GS_GAS = "eem_ionescu2013_e_mpa_631gs_gas"
#: The same at 6-31G**. See `EEM_IONESCU2013_E_MPA_631GS_GAS`.
EEM_IONESCU2013_E_MPA_631GSS_GAS = "eem_ionescu2013_e_mpa_631gss_gas"
#: Each Ionescu code's scheme name in the paper and in `data/eem_ionescu2013.json`.
IONESCU_SCHEMES = {
    EEM_IONESCU2013_E_MPA_631GS_GAS: "E-MPA/6-31G*/gas",
    EEM_IONESCU2013_E_MPA_631GSS_GAS: "E-MPA/6-31G**/gas",
}
#: Every method offered, in combo order; EEM first and the default. Anything else raises.
#: **Ionescu's models are appended, never inserted**, so the default and every existing result's
#: identity stay what they were.
GEOMETRY_CHARGE_METHODS = (
    EEM_BULTINCK2002_PART1, QEQ_RG1991_LAMBDA_HALF_H_EXPERIMENTAL,
    EEM_IONESCU2013_E_MPA_631GS_GAS, EEM_IONESCU2013_E_MPA_631GSS_GAS,
)
#: What each stored code is called on screen.
GEOMETRY_CHARGE_METHOD_LABELS = {
    EEM_BULTINCK2002_PART1: "EEM, Bultinck 2002",
    QEQ_RG1991_LAMBDA_HALF_H_EXPERIMENTAL: "QEq, Rappé–Goddard 1991",
    EEM_IONESCU2013_E_MPA_631GS_GAS: "EEM, Ionescu 2013, Mulliken 6-31G*",
    EEM_IONESCU2013_E_MPA_631GSS_GAS: "EEM, Ionescu 2013, Mulliken 6-31G**",
}
#: The short name each refusal message speaks of.
_METHOD_SHORT = {
    EEM_BULTINCK2002_PART1: "EEM",
    QEQ_RG1991_LAMBDA_HALF_H_EXPERIMENTAL: "QEq",
    EEM_IONESCU2013_E_MPA_631GS_GAS: "Ionescu EEM",
    EEM_IONESCU2013_E_MPA_631GSS_GAS: "Ionescu EEM",
}

#: A stable identifier for how an Ionescu result was validated, persisted with every result and
#: resolved to wording by the help layer -- the same reasoning as stable method codes: an English
#: sentence stored per result would drift from the one the help shows.
IONESCU_SCOPE_ID = "ionescu2013_protein_fragment_validation_v1"
#: What `IONESCU_SCOPE_ID` means, for the help layer and the user guide.
IONESCU_VALIDATION_SCOPE = (
    "Ionescu et al. 2013's EEM, as the paper parameterised it, reproduced exactly on the protein "
    "fragments it was fitted and tested on (36 of 36 model-by-dataset rows). This application ships 2 "
    "of its 24 parameterisations: the E-typing Mulliken gas-phase models, the only two whose behaviour "
    "on other molecules was measured. On molecules unlike proteins it is an extrapolation, and it can "
    "be wrong in sign and by more than 1.5 e without any refusal firing; molecules with a sulfur bonded "
    "to oxygen are refused because every one measured was. For any molecule containing an element whose "
    "effective hardness is negative in the model, the charges are the model's unique stationary point "
    "and not an energy minimum."
)

#: A8's validation scope, verbatim. Recorded beside a QEq result as how the
#: method was validated; it is not part of what was computed.
QEQ_VALIDATION_SCOPE = (
    "This calculator implements the Rappé–Goddard 1991 QEq formulation using the λ = ½ "
    "interpretation (eq 17′) and the experimental hydrogen parameter set. It reproduces the "
    "validated benchmark subset recorded in amendment A8. The published LiH value is not a "
    "self-consistent solution of the implemented equations, and such cases are refused. The "
    "published 1991 SiH₄ value is inconsistent with the later Rappé-group implementation and is "
    "treated as a source discrepancy, not as an oracle. Results whose final solution requires an "
    "active charge bound are refused pending the O9 study."
)
#: The silicon source discrepancy (A7, A8): a limitation note, not a numerical warning.
QEQ_SILICON_NOTE = (
    "Does not reproduce the published 1991 SiH₄ hydrogen charge; Rappé-group calculations "
    "(Ramachandran et al. 1996) support the sign returned here."
)

#: No 3D conformer: the resolver handed over the drawing, or a flat one.
REFUSE_NO_3D_GEOMETRY = "REFUSE_NO_3D_GEOMETRY"
#: Hydrogens implied by H counts rather than present as atoms with positions.
REFUSE_IMPLICIT_HYDROGENS = "REFUSE_IMPLICIT_HYDROGENS"
#: Hydrogen atoms present, but without finite coordinates.
REFUSE_MISSING_H_COORDINATES = "REFUSE_MISSING_H_COORDINATES"
#: QEq only: the converged final solution has an atom fixed at a charge bound.
#: The paper's bound procedure is unresolved (O9), so that domain is refused.
REFUSE_BOUND_ACTIVE = "REFUSE_BOUND_ACTIVE"
#: Ionescu only: a sulfur bonded to oxygen. Every such molecule measured -- the sulfonamides, dimethyl
#: sulfone, and the sulfoxides -- came back wrong by 0.84 to 1.75 e, several with the sign flipped, at
#: magnitudes no charge bound catches (preregistration §9-R, and sulfuric acid in §8-R).
REFUSE_OXIDISED_SULFUR = "REFUSE_OXIDISED_SULFUR"

#: What each refusal says, with {method} the method's short name. Stable,
#: because help and the user guide quote them.
REFUSAL_MESSAGES = {
    REFUSE_NO_3D_GEOMETRY: (
        "{method} needs 3D coordinates, and this molecule has no 3D conformer. "
        "Generate conformers first (Structure ▸ Generate Conformers...)."
    ),
    REFUSE_IMPLICIT_HYDROGENS: (
        "{method} needs every hydrogen as an atom with a 3D position; this conformer "
        "implies hydrogens it does not contain, and the calculator will not invent them."
    ),
    REFUSE_MISSING_H_COORDINATES: (
        "{method} requires explicit hydrogen coordinates for this stored conformer. "
        "Some hydrogen atoms have no valid position, and the calculator will not invent them."
    ),
    REFUSE_BOUND_ACTIVE: (
        "QEq's converged solution needs {atoms} held at a charge bound. How the paper's bound "
        "procedure should behave there is unresolved, so no charges are returned for this molecule."
    ),
    REFUSE_AMBIGUOUS_H_IDENTITY: (
        "At this pH a proton leaves an atom carrying several hydrogens that are not equivalent, "
        "so which of them goes is not determined by the structure. Charges are not computed rather "
        "than computed on an arbitrary choice."
    ),
    REFUSE_NOT_IONISATION_ONLY: (
        "The dominant state at this pH differs from the drawing by more than protons on its own "
        "atoms, so it is not an ionisation of this structure."
    ),
    REFUSE_H_PLACEMENT: (
        "MMFF94 could not place the hydrogens this pH adds, so no geometry was produced for them "
        "and no charges are returned."
    ),
    REFUSE_PROTONATION_FAILED: (
        "The dominant ionization state at this pH could not be determined for this structure."
    ),
    REFUSE_OXIDISED_SULFUR: (
        "This molecule has a sulfur bonded to oxygen ({atoms}). Ionescu's model was wrong on every such "
        "molecule it was checked against -- sulfonamides, sulfones and sulfoxides, by up to 1.75 e and "
        "sometimes in sign -- so no charges are returned rather than numbers that look plausible."
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
    REFUSE_BOUND_ACTIVE: "Charge bound reached",
    REFUSE_AMBIGUOUS_H_IDENTITY: "Which hydrogen is ambiguous",
    REFUSE_NOT_IONISATION_ONLY: "Not an ionisation",
    REFUSE_H_PLACEMENT: "Hydrogen placement failed",
    REFUSE_PROTONATION_FAILED: "Protonation state unavailable",
    REFUSE_OXIDISED_SULFUR: "Sulfur bonded to oxygen",
    ce.REFUSE_CHARGE_BOUND_EXCEEDED: "Runaway charge",
}

#: Sigma q must equal the net charge to this. A necessary check, never evidence
#: the distribution is right: a wholly wrong one can still sum correctly.
_CONSERVATION_TOLERANCE = 1e-8

#: The structure as the conformer holds it. The default, and the mode the plain 3D calculator uses.
AS_DRAWN_MODE = "as_drawn"
#: The dominant ionization state at a pH, carried onto that conformer (`geometry_partial_charge_at_ph`).
AT_PH_MODE = "at_ph"
#: Every mode `compute_geometry_charges` accepts; anything else is a ValueError, never a default.
PROTONATION_MODES = (AS_DRAWN_MODE, AT_PH_MODE)
#: What the user reads for each mode; never stored.
PROTONATION_MODE_LABELS = {AS_DRAWN_MODE: "As drawn", AT_PH_MODE: "Dominant state at a pH"}

#: What "at a pH" means, written into every result computed that way.
AT_PH = (
    "The dominant ionization state at the given pH, carried onto the stored conformer: every heavy "
    "atom and every retained hydrogen keeps its coordinates exactly, and only hydrogens this "
    "calculation adds are placed (MMFF94, with every other atom fixed). Ionization states only, "
    "never tautomers."
)

#: What "as drawn" means, written into every result's provenance.
AS_DRAWN = (
    "The stored conformer's atoms, explicit hydrogens and coordinates, with its net "
    "formal charge. Per-atom formal charges are not kept: the net charge is "
    "redistributed, so only the sum equals it. No protonation is applied."
)


def _refusal(
    code: str, name: str, method: str, places: int, molecule_uuid: str,
    message: str | None = None, diagnostics: dict | None = None, property_id: str = PROPERTY_ID,
) -> PerAtomDataset:
    parameters = {"refusal": code, "decimal_places": places, **(diagnostics or {})}
    return PerAtomDataset(
        property_id=property_id,
        name=name,
        units="e",
        method=method,
        molecule_uuid=molecule_uuid,
        cache_state=CacheState.FAILED,
        inapplicable=True,
        error=message or REFUSAL_MESSAGES[code].format(method=_METHOD_SHORT[method]),
        error_summary=_SHORT.get(code, "Not computed"),
        provenance=Provenance(created_by="core", method=method, parameters=parameters),
    )


def compute_geometry_charges_at_ph(mol: Chem.Mol, molecule_uuid: str, parameters: dict[str, Any] | None = None) -> PerAtomDataset:
    """`compute_geometry_charges` on the dominant ionization state at a pH.

    Its own calculator id, so the plain 3D calculator's stored results keep the identity they were
    saved under; the mode is not a user-facing parameter here, it is what this calculator IS.
    """
    return compute_geometry_charges(mol, molecule_uuid, {**(parameters or {}), "protonation": AT_PH_MODE})


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
    mode = str(parameters.get("protonation", AS_DRAWN_MODE))
    property_id = PROPERTY_ID_AT_PH if mode == AT_PH_MODE else PROPERTY_ID
    if mode not in PROTONATION_MODES:
        raise ValueError(f"Unknown protonation mode {mode!r}; expected one of {PROTONATION_MODES}")
    ph = float(parameters.get("pH", 7.4))
    label = GEOMETRY_CHARGE_METHOD_LABELS[method]
    name = f"Partial Charge ({label}, 3D){' incl. H' if include_hydrogens else ''}"
    if mode == AT_PH_MODE:  # the pH is part of what was computed, so it is part of what it is called
        name = f"Partial Charge ({label}, 3D, pH {ph:g}){' incl. H' if include_hydrogens else ''}"

    def refuse(code: str, message: str | None = None, diagnostics: dict | None = None) -> PerAtomDataset:
        return _refusal(code, name, method, places, molecule_uuid, message, diagnostics, property_id)

    try:
        conformer = _require_conformer(mol)
    except NoConformerError:
        return refuse(REFUSE_NO_3D_GEOMETRY)
    if any(atom.GetTotalNumHs() > 0 for atom in mol.GetAtoms()):
        return refuse(REFUSE_IMPLICIT_HYDROGENS)

    # The state change comes FIRST, because everything below reads coordinates and the net charge,
    # and at a pH both belong to the protonated structure rather than the drawn one.
    species, protonation = AS_DRAWN, {"protonation": AS_DRAWN_MODE}
    if mode == AT_PH_MODE:
        state = protonate_conformer(mol, ph)
        if state.refusal:
            return refuse(state.refusal, state.message)
        mol = state.mol
        conformer = mol.GetConformer()
        species = AT_PH
        protonation = {
            "protonation": AT_PH_MODE,
            "pH": ph,
            "state_id": state.state_id,
            "state_changed": state.changed,
            "site_changes": [
                {"atom": c.heavy_atom, "removed_hydrogen": c.removed_hydrogen,
                 "delta_h": c.delta_h, "delta_formal_charge": c.delta_charge}
                for c in state.site_changes
            ],
            "source_heavy_map": [list(pair) for pair in state.source_heavy_map],
            "placed_hydrogens": list(state.placed_hydrogens),
            "recorded_hydrogen_choices": [list(pair) for pair in state.recorded_choices],
            "selection_policy_version": PROTONATION_SELECTION_POLICY_VERSION,
            "tautomers": "not enumerated (ropp2019: Dimorphite-DL computes ionization states only)",
        }
    positions = np.array(conformer.GetPositions(), dtype=float)
    elements = [atom.GetSymbol() for atom in mol.GetAtoms()]
    finite = np.all(np.isfinite(positions), axis=1)
    if not np.all(finite):
        if any(not finite[i] and elements[i] == "H" for i in range(len(elements))):
            return refuse(REFUSE_MISSING_H_COORDINATES)
        return refuse(REFUSE_NO_3D_GEOMETRY)

    net_charge = float(Chem.GetFormalCharge(mol))
    if method == QEQ_RG1991_LAMBDA_HALF_H_EXPERIMENTAL:
        result = ce.qeq_charges(elements, positions, net_charge, hydrogen="experimental", readings=ce.ADOPTED)
        if result.status == ce.REFUSE_NOT_CONVERGED:
            return refuse(result.status, result.message, {
                "iterations": result.iterations,
                "final_metrics": dict(result.final_metrics),
                "trace_class": result.trace_class,
                "ever_clamped": result.ever_clamped,
            })
        if result.status != "converged":
            return refuse(result.status, result.message)
        if result.final_active_atoms:
            # The refusal is decided on the FINAL active set alone (A8): a
            # trajectory that touched a bound and left it is a valid result.
            active = [
                {"atom": result.solver_to_source[i], "element": elements[i], "bound": bound, "final_charge": float(result.charges[i])}
                for i, bound in sorted(result.final_active_atoms.items())
            ]
            atoms = ", ".join(f"{a['element']}{a['atom']}" for a in active)
            return refuse(REFUSE_BOUND_ACTIVE, REFUSAL_MESSAGES[REFUSE_BOUND_ACTIVE].format(atoms=atoms), {
                "final_active_atoms": active,
                "iterations": result.iterations,
                "ever_clamped": result.ever_clamped,
            })
    elif method in IONESCU_SCHEMES:
        # Refused BEFORE any solve, from the bonds, because this is a failure no charge magnitude
        # reveals: the wrong answers came back at ordinary sizes (preregistration §9-R).
        oxidised = sorted(
            atom.GetIdx() for atom in mol.GetAtoms()
            if atom.GetSymbol() == "S" and any(n.GetSymbol() == "O" for n in atom.GetNeighbors())
        )
        if oxidised:
            atoms = ", ".join(f"S{i}" for i in oxidised)
            return refuse(REFUSE_OXIDISED_SULFUR, REFUSAL_MESSAGES[REFUSE_OXIDISED_SULFUR].format(atoms=atoms),
                          {"oxidised_sulfur_atoms": oxidised})
        result = ce.ionescu_charges(elements, positions, IONESCU_SCHEMES[method], net_charge)
        if result.status != "converged":
            return refuse(result.status, result.message)
    else:
        result = ce.eem_charges(elements, positions, net_charge)
        if result.status != "converged":
            return refuse(result.status, result.message)

    own = {result.solver_to_source[k]: float(result.charges[k]) for k in range(len(elements))}
    every_atom = sum(own.values())
    if abs(every_atom - net_charge) > _CONSERVATION_TOLERANCE:
        raise ValueError(f"{_METHOD_SHORT[method]} charges sum to {every_atom:+.10f} on a conformer of net charge {net_charge:+.0f}")

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

    if method == QEQ_RG1991_LAMBDA_HALF_H_EXPERIMENTAL:
        computed = {
            "parameter_set": "rappe_1991_table_I",
            "hydrogen_parameter_set": "experimental",
            "zeta_parameterization": "rappe_1991_eq17_prime_lambda_half",
            "lambda": 0.5,
            "zeta_h_in_pairs": ce.ADOPTED.zeta_h_in_pairs,
            "hydrogen_self_term": ce.ADOPTED.hydrogen_self_term,
            "integral_model": "ns_slater_exact",
            "source": "rappe1991 (J. Phys. Chem. 1991, 95, 3358; doi:10.1021/j100161a070)",
            "hartree_ev": ce.HARTREE_EV,
            "bohr_angstrom": ce.QEQ_BOHR_ANGSTROM,
            "iterations": result.iterations,
            "final_metrics": dict(result.final_metrics),
            "bound_passes_max": result.bound_passes_max,
            "ever_clamped": result.ever_clamped,
            "validation": {"amendment": "A8", "scope": QEQ_VALIDATION_SCOPE},
        }
        if "Si" in elements:
            computed["source_discrepancy"] = QEQ_SILICON_NOTE
    elif method in IONESCU_SCHEMES:
        scheme = IONESCU_SCHEMES[method]
        model = ce.ionescu_parameters()[scheme]
        computed = {
            "parameter_set": f"ionescu_2013_table_S1_{scheme}",
            "scheme": scheme,
            "source": "ionescu2013 (J. Chem. Inf. Model. 2013, 53, 2548; doi:10.1021/ci400448n)",
            "equation_convention": "ionescu2013_eqs_3_4_kappa_over_r_angstrom",
            "kappa": model["kappa"],
            "units": "the paper's own; not eV, and not established here",
            "parameter_checksum": ce.payload_checksum(model),
            "equalized_electronegativity_paper_units": result.equalized_electronegativity_paper_units,
            # Exact, not estimated: preregistration §4 checked it on 1644 solves.
            "stationary_point": ce.ionescu_stationary_point(elements, scheme),
            # No detector can say "this is a protein fragment" (§10.4 option A is deferred), so every
            # computed result is labelled an extrapolation rather than claiming a domain it cannot test.
            "applicability": "extrapolation",
            "charge_bound": ce.IONESCU_CHARGE_BOUND,
            "validation": {"preregistration": "benchmarks/charges/models/ionescu_src_preregistration.md",
                           "scope_id": IONESCU_SCOPE_ID},
        }
    else:
        computed = {
            "parameter_set": "bultinck_2002_part_I_table_1",
            "source": "bultinck2002a (J. Phys. Chem. A 2002, 106, 7887; doi:10.1021/jp0205463)",
            "equation_convention": ce.EEM_EQUATION_CONVENTION,
            "kappa": "1 hartree bohr",
            "hartree_ev": ce.HARTREE_EV,
            "bohr_angstrom": ce.EEM_BOHR_ANGSTROM,
            "equalized_electronegativity_ev": result.equalized_electronegativity_ev,
        }
    return PerAtomDataset(
        property_id=property_id,
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
                **computed,
                "species": species,
                **protonation,
                "net_charge": net_charge,
                "include_hydrogens": include_hydrogens,
                "hydrogen_aggregation": "folded" if include_hydrogens else "separate",
                "solver_to_source": list(result.solver_to_source),
                "decimal_places": places,
                **({"not_applied": "protonation at a pH"} if mode == AS_DRAWN_MODE else {}),
                ATOM_BASIS: basis,
                TOTAL: declare_total(every_atom, "Net calculated charge", units="e", basis=basis),
            },
        ),
    )
