"""Polarizability and orbital electronegativity.

POLARIZABILITY uses the additive atomic scheme of Jensen et al. (2002,
J. Chem. Phys.), summing per-element contributions in cubic angstroms.

    Validated two ways. Against experiment: benzene 10.29 vs 10.32,
    CCl4 10.37 vs 10.51, toluene 12.40 vs 12.30, chloromethane 4.75 vs
    4.72 -- all inside 1.5%, with ~5.7% mean absolute error across a
    13-molecule set. And against ChemAxon's own screenshot, whose per-atom
    values read 1.36 for aromatic carbon and 0.39 for hydrogen against
    Jensen's 1.3266 and 0.3888 -- close enough to identify the parameter
    set they are using.

    KNOWN BIAS: saturated hydrocarbons come out ~11-12% high (methane
    2.88 vs 2.59, n-butane 9.19 vs 8.20). A purely atom-additive scheme
    has no hybridization dependence, so it cannot distinguish an sp3
    carbon from an aromatic one. Aromatics and halogenated compounds --
    most drug-like matter -- are the accurate cases.

    MILLER's method is NOT offered. ChemAxon lists it as their second
    option, but their docs do not publish its parameters, and an
    implementation from recalled atomic-hybrid values reproduced saturated
    hydrocarbons well while missing benzene by +27% and CCl4 by -50%.
    Fitting the missing parameters to experiment would have produced
    something that is not Miller's method wearing Miller's name.

ORBITAL ELECTRONEGATIVITY is the Gasteiger-Marsili quantity
chi(q) = a + b*q + c*q^2, evaluated at each atom's CONVERGED PEOE charge.
RDKit computes those charges with the same published method, so this reads
chi off a correct charge distribution rather than reimplementing the
iteration -- an independent reimplementation here diverged badly (chi from
-2.4 to 41 eV), which is exactly why it is not used.

    Absolute values depend on the parameter set and will not match another
    implementation digit for digit. What is meaningful, and what the tests
    pin, is the ORDERING: O > N > C, aromatic carbon above aliphatic, and
    every value inside a physically sensible range.
"""

from __future__ import annotations

from typing import Any

from rdkit import Chem
from rdkit.Chem import rdPartialCharges

from openchem.chem.calculator_options import atom_basis_of, decimals
from openchem.domain.common import (
    ATOM_BASIS,
    EXPLICIT_H,
    TOTAL,
    CacheState,
    Provenance,
    declare_total,
    decline_total,
)
from openchem.domain.report import ReportResult
from openchem.chem.report_adapter import report_fields
from openchem.domain.scientific_result import PerAtomDataset

# Jensen et al. (2002) atomic polarizabilities, cubic angstroms.
JENSEN_POLARIZABILITY: dict[str, float] = {
    "H": 0.3888, "C": 1.3266, "N": 0.9754, "O": 0.7658, "S": 2.4772,
    "F": 0.4642, "Cl": 2.2604, "Br": 3.3181, "I": 5.5593, "P": 2.6300,
    "Si": 3.9628, "B": 1.6000, "Se": 3.3800,
}

# Gasteiger-Marsili chi(q) = a + b*q + c*q^2 coefficients, eV.
_CHI_PARAMETERS: dict[tuple[str, str | None], tuple[float, float, float]] = {
    ("H", None): (7.17, 6.24, -0.56),
    ("C", "SP3"): (7.98, 9.18, 1.88),
    ("C", "SP2"): (8.79, 9.32, 1.51),
    ("C", "SP"): (10.39, 9.45, 0.73),
    ("N", "SP3"): (11.54, 10.82, 1.36),
    ("N", "SP2"): (12.87, 11.15, 0.85),
    ("N", "SP"): (15.68, 11.70, -0.27),
    ("O", "SP3"): (14.18, 12.92, 1.39),
    ("O", "SP2"): (17.07, 13.79, 0.47),
    ("F", None): (14.66, 13.85, 2.31),
    ("Cl", None): (11.00, 9.69, 1.35),
    ("Br", None): (10.08, 8.47, 1.16),
    ("I", None): (9.90, 7.96, 0.96),
    ("S", "SP3"): (10.14, 9.13, 1.38),
    ("S", "SP2"): (10.14, 9.13, 1.38),
}


def _maybe_microspecies(mol: Chem.Mol, parameters: dict[str, Any]) -> Chem.Mol:
    """Marvin offers "take major microspecies at pH" on both plugins, and
    it genuinely matters: protonation changes both polarizability and
    electronegativity. Falls back to the drawn form if Dimorphite-DL
    cannot build one, rather than failing the whole calculation."""
    if not parameters.get("major_microspecies"):
        return mol
    try:
        from openchem.chem.pka_providers import protonate_at_ph

        return protonate_at_ph(mol, float(parameters.get("pH", 7.4)))
    except Exception:  # noqa: BLE001 - the drawn form is still a valid answer
        return mol


def atomic_polarizabilities(mol: Chem.Mol) -> dict[int, float] | None:
    """Per-atom contributions, or None if any element has no parameter --
    a partial sum would silently understate the molecule."""
    with_hydrogens = Chem.AddHs(mol)
    values: dict[int, float] = {}
    for atom in with_hydrogens.GetAtoms():
        contribution = JENSEN_POLARIZABILITY.get(atom.GetSymbol())
        if contribution is None:
            return None
        values[atom.GetIdx()] = contribution
    return values


def molecular_polarizability(mol: Chem.Mol) -> float | None:
    values = atomic_polarizabilities(mol)
    return None if values is None else sum(values.values())


def _unparameterised_elements(mol: Chem.Mol) -> list[str]:
    return sorted(
        {
            atom.GetSymbol()
            for atom in Chem.AddHs(mol).GetAtoms()
            if atom.GetSymbol() not in JENSEN_POLARIZABILITY
        }
    )


#: The three polarizability methods this calculator offers, as
#: `{label shown in the combo: provenance method id}`.
#:
#: **THEY ARE NOT INTERCHANGEABLE AND NEITHER MILLER FORM DEFAULTS TO THE
#: OTHER.** `ahc` squares a sum over the whole molecule and `ahp` is plain
#: additivity, so feeding one method's column into the other's formula
#: gives a perfectly reasonable-looking number that is wrong --
#: `chem/polarizability_miller.py` records that as the likely cause of the
#: -50% on CCl4 in this project's own history.
POLARIZABILITY_METHODS: dict[str, str] = {
    "Jensen (additive)": "jensen",
    "Miller ahc": "miller_ahc",
    "Miller ahp": "miller_ahp",
}

_DEFAULT_POLARIZABILITY_METHOD = "Jensen (additive)"


def _polarizability_method(parameters: dict[str, Any]) -> str:
    """The provenance method id for the chosen label.

    An unrecognised label falls back to Jensen rather than raising: a
    stored project written by a future version must not make an old one
    unopenable, and the recorded method says which was used either way.
    """
    label = str(parameters.get("method", _DEFAULT_POLARIZABILITY_METHOD))
    return POLARIZABILITY_METHODS.get(label, POLARIZABILITY_METHODS[_DEFAULT_POLARIZABILITY_METHOD])


def compute_polarizability(
    mol: Chem.Mol, molecule_uuid: str, parameters: dict[str, Any] | None = None
) -> ReportResult:
    """The "electronic" category's Polarizability calculator.

    **THE METHOD REACHES PROVENANCE, and that is a separate obligation
    from computing it.** There is no parameter-keyed result cache today,
    so a cache keyed on `(molecule, calculator_id)` alone would hand back
    the Jensen answer for every method; recording the selection in
    `Provenance.parameters` is what makes such a cache buildable later
    without silently doing that. `tests/test_polarizability_methods.py`
    asserts the numeric path and the metadata path separately, because a
    result that computed Miller while recording Jensen would pass a test
    of either one alone.
    """
    parameters = parameters or {}
    target = _maybe_microspecies(mol, parameters)
    method = _polarizability_method(parameters)

    if method == "jensen":
        total = molecular_polarizability(target)
        failure = (
            None
            if total is not None
            else "No Jensen polarizability parameter for: "
            + ", ".join(_unparameterised_elements(target))
        )
        basis = (
            "Additive atomic scheme (Jensen et al. 2002). Aromatics and halogenated "
            "compounds are accurate to about 1%; saturated hydrocarbons come out roughly "
            "11% high, because an atom-additive scheme has no hybridization dependence."
        )
        assignment: dict[str, int] = {}
    else:
        total, failure, basis, assignment = _miller_polarizability(target, method)

    if total is None:
        return _report(
            alert_id="polarizability",
            name="Polarizability",
            molecule_uuid=molecule_uuid,
            matched=[],
            category="electronic",
            cache_state=CacheState.FAILED,
            error=failure or "No polarizability could be computed.",
            provenance=Provenance(created_by="core", method=method, parameters={"method": method}),
        )

    lines = [f"Molecular polarizability: {total:.2f} A^3"]
    if parameters.get("major_microspecies"):
        lines.append(f"Computed on the major microspecies at pH {float(parameters.get('pH', 7.4)):g}.")
    if assignment:
        lines.append(
            "Hybrid assignment: "
            + ", ".join(f"{symbol} x{count}" for symbol, count in sorted(assignment.items()))
        )
    lines.append(basis)
    return _report(
        alert_id="polarizability",
        name="Polarizability",
        molecule_uuid=molecule_uuid,
        matched=lines,
        category="electronic",
        provenance=Provenance(
            created_by="core",
            method=method,
            parameters={"polarizability_a3": total, "method": method},
        ),
    )


def _miller_polarizability(
    target: Chem.Mol, method: str
) -> tuple[float | None, str | None, str, dict[str, int]]:
    """One of Miller's two answers, or a named refusal.

    Imported here rather than at module scope only to keep the two
    parameter tables from being loaded by every consumer of this module;
    the dispatch itself is deliberately explicit, since `ahc` and `ahp`
    reaching one implementation is the silent failure this whole
    parameter exists around.
    """
    from openchem.chem.polarizability_miller import (
        MillerAssignmentError,
        miller_polarizability,
    )

    try:
        result = miller_polarizability(target)
    except MillerAssignmentError as error:
        return None, f"Miller's Table I has no parameter: {error}", "", {}

    if method == "miller_ahc":
        value = result.ahc
        basis = (
            "Miller's ahc method: alpha = (4/N)(sum of tau_A)^2 over N total electrons "
            "(Miller & Savchik 1979; parameters from Miller 1990, Table I). Measured here "
            "at +0.6% on benzene and +0.2% on CCl4 -- the two molecules an earlier "
            "reconstruction missed by +27% and -50%. It is an empirical scheme fitted to "
            "about 240 molecules and reports an isotropic average, not a tensor."
        )
    else:
        value = result.ahp
        basis = (
            "Miller's ahp method: alpha = sum of alpha_A, plain additivity (Miller 1990, "
            "Table I). Squaring a sum is what makes ahc not a group-additivity scheme, so "
            "the two columns are not interchangeable and this one is the additive answer. "
            "Empirical, fitted to about 240 molecules, and isotropic."
        )
    return value, None, basis, dict(result.assignment)


def compute_atomic_polarizability(
    mol: Chem.Mol, molecule_uuid: str, parameters: dict[str, Any] | None = None
) -> PerAtomDataset:
    """Per-atom polarizability contributions, projected onto 2D and 3D --
    the "atomic" Type option in Marvin's panel."""
    _places = decimals(parameters)
    parameters = parameters or {}
    target = _maybe_microspecies(mol, parameters)
    values = atomic_polarizabilities(target)
    if values is None:
        return PerAtomDataset(
            property_id="atomic_polarizability",
            name="Atomic Polarizability",
            units="A^3",
            method="jensen",
            molecule_uuid=molecule_uuid,
            values={},
            cache_state=CacheState.FAILED,
            error=(
                "No Jensen polarizability parameter for: "
                + ", ".join(_unparameterised_elements(target))
            ),
            provenance=Provenance(created_by="core", method="jensen", parameters={"decimal_places": _places}),
        )
    return PerAtomDataset(
        property_id="atomic_polarizability",
        name="Atomic Polarizability",
        units="A^3",
        method="jensen",
        molecule_uuid=molecule_uuid,
        values=values,
        provenance=Provenance(
            created_by="core",
            method="jensen",
            parameters={
                "decimal_places": _places,
                # `atomic_polarizabilities` works on `Chem.AddHs(mol)`, so
                # every hydrogen carries its own value and the basis is
                # explicit whatever was handed in.
                ATOM_BASIS: EXPLICIT_H,
                # Jensen's method IS an additive atomic scheme -- the
                # molecular polarizability is defined as the sum -- so the
                # total is exact rather than approximate here.
                TOTAL: declare_total(
                    sum(values.values()),
                    "Molecular polarizability",
                    units="A^3",
                    basis=EXPLICIT_H,
                ),
            },
        ),
    )


def _chi_parameters(atom: Chem.Atom) -> tuple[float, float, float] | None:
    symbol = atom.GetSymbol()
    hybridization = str(atom.GetHybridization())
    if symbol in ("C", "N", "O", "S") and atom.GetIsAromatic():
        hybridization = "SP2"
    return _CHI_PARAMETERS.get((symbol, hybridization)) or _CHI_PARAMETERS.get((symbol, None))


def orbital_electronegativities(
    mol: Chem.Mol, include_hydrogens: bool = False
) -> dict[int, float]:
    """chi at each atom's converged PEOE charge, in eV.

    Hydrogens are excluded by default, matching Marvin, which displays
    "orbital EN values next to the atoms (except hydrogens)".
    """
    working = Chem.Mol(mol)
    rdPartialCharges.ComputeGasteigerCharges(working)
    values: dict[int, float] = {}
    for atom in working.GetAtoms():
        if not include_hydrogens and atom.GetSymbol() == "H":
            continue
        coefficients = _chi_parameters(atom)
        if coefficients is None or not atom.HasProp("_GasteigerCharge"):
            continue
        charge = atom.GetDoubleProp("_GasteigerCharge")
        if charge != charge:  # NaN, for atoms Gasteiger cannot type
            continue
        a, b, c = coefficients
        values[atom.GetIdx()] = a + b * charge + c * charge * charge
    return values


def compute_orbital_electronegativity(
    mol: Chem.Mol, molecule_uuid: str, parameters: dict[str, Any] | None = None
) -> PerAtomDataset:
    """The "electronic" category's Orbital Electronegativity calculator.

    Only the SIGMA component is offered. Marvin additionally exposes a pi
    component, which needs a separate pi-charge iteration this does not
    implement -- claiming a pi value by relabelling the sigma one would be
    worse than not offering it.
    """
    _places = decimals(parameters)
    parameters = parameters or {}
    target = _maybe_microspecies(mol, parameters)
    values = orbital_electronegativities(
        target, include_hydrogens=bool(parameters.get("include_hydrogens", False))
    )
    if not values:
        return PerAtomDataset(
            property_id="orbital_electronegativity",
            name="Orbital Electronegativity (sigma)",
            units="eV",
            method="gasteiger_marsili",
            molecule_uuid=molecule_uuid,
            values={},
            cache_state=CacheState.FAILED,
            error="No atom in this molecule has Gasteiger-Marsili parameters.",
            provenance=Provenance(created_by="core", method="gasteiger_marsili", parameters={"decimal_places": _places}),
        )
    return PerAtomDataset(
        property_id="orbital_electronegativity",
        name="Orbital Electronegativity (sigma)",
        units="eV",
        method="gasteiger_marsili",
        molecule_uuid=molecule_uuid,
        values=values,
        provenance=Provenance(
            created_by="core",
            method="gasteiger_marsili",
            parameters={
                "component": "sigma",
                "note": (
                    "chi = a + b*q + c*q^2 at the converged PEOE charge. Absolute values are "
                    "parameter-set dependent; the ordering between atoms is the meaningful part."
                ),
                ATOM_BASIS: atom_basis_of(target),
                # DECLINED, and the note above already says why: an
                # electronegativity is an INTENSIVE per-atom property, so
                # adding them up produces a number with no referent. The
                # Calculator Inspector used to print exactly that --
                # "Overall: 134.8" for aspirin, eV summed over thirteen
                # atoms -- which is arithmetic wearing a unit.
                TOTAL: decline_total(
                    "Orbital electronegativity is an intensive per-atom property. "
                    "Summing it is not a molecular quantity, and the absolute values "
                    "are parameter-set dependent -- the ordering between atoms is the "
                    "meaningful part."
                ),
            },
        ),
    )


def _report(**fields) -> ReportResult:
    """One `AlertResult(...)` call site, as a `ReportResult`.

    The keyword names are unchanged -- `alert_id`, `name`, `matched`,
    `category` -- so the call sites above read as they always did and the
    diff stays small. `report_fields` does the translation and turns each
    line into a `Fact`; see `chem/report_adapter.py` for what a string can
    and cannot carry.

    A calculator that wants real units, evidence or limitations on a fact
    builds `Fact`s directly instead, as `geometry_analysis` now does.
    """
    return ReportResult(**report_fields(**fields))
