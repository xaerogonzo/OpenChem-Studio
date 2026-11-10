"""Polarizability and orbital electronegativity.

POLARIZABILITY uses an additive atomic scheme, summing per-element contributions
in cubic angstroms.

    **THE TABLE WAS REPLACED ON 2026-11-05.** The values used before were labelled Jensen et al. 2002 and had no recorded source (`docs/LITERATURE_LOG.md`: ten papers searched, none
    contains them; Jensen's paper is a dipole-interaction model for H, B, C, N, O, F and Cl). They were matched to another program's screenshot, which is not a basis. Nine elements (H, C, N,
    O, F, S, Cl, Br, I) are now FITTED by this project, by weighted least squares on the relative error, to the experimental polarizabilities of 425 solvents in Bosque and Sales (J. Chem. Inf.
    Comput. Sci. 42, 1154, 2002), using that paper's own working set (fit) and prediction set (judged), as fixed in `benchmarks/polarizability/PREREGISTRATION.md` before fitting;
    results in `benchmarks/polarizability/RESULT.md`. Prediction-set mean absolute error 2.1 % (the old table: 7.8 %, biased +7 %); 4.3 % against 88 compounds of Kang and Jhon 1982, a
    non-gating second set (old table: 9.8 %).

    **SECOND REFIT, SAME DAY (`PREREGISTRATION_2.md`).** The CRC Handbook's table of molecular polarizabilities showed that table 14 % low on molecules of six atoms or fewer. The table was refitted
    to the Bosque set plus 264 molecules of that table, with one constant added per molecule (chosen by cross-validation among four variants), and ships because it met the registered criteria on
    a holdout: 7.7 % mean absolute error on held-out CRC molecules against the first table's 8.4 %, six atoms or fewer 9 % low against 16 % low, Bosque prediction set unchanged at 2.1 %. Phosphorus
    and silicon are now fitted too, to eight and six molecules, so they are marked as less certain. **Boron and selenium are NOT fitted** (two molecules and one): they keep their old numbers, which
    have no source, and every result that includes one says so. The result carries method id `additive_refit`; results stored under `jensen` came from the old table.

    LIMIT: a purely atom-additive scheme has no hybridization dependence, so it cannot distinguish an sp3 carbon from an aromatic one. Fitted mostly to aliphatic
    solvents, it is within about 2 to 4 % on the sets above, and saturated hydrocarbons (Kang's twelve, from methane to dodecane) come out 2.5 % off on average.

    MILLER's method is NOT offered. The vendor lists it as their second
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

import json
from dataclasses import replace
from functools import lru_cache
from pathlib import Path
from typing import Any

from rdkit import Chem
from rdkit.Chem import rdPartialCharges

from openchem.chem.calculator_options import atom_basis_of, decimals
from openchem.domain.calculator import ELEMENT_OUTSIDE_PARAMETER_SET, CalculationRefusal
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
from openchem.chem.report_adapter import report_from_fields
from openchem.domain.scientific_result import PerAtomDataset

def _load_additive_table() -> tuple[dict[str, float], frozenset[str], dict]:
    """The additive table, from `data/polarizability_refit.json`: values fitted by this project to experiment (nine elements), and four that were never fitted."""
    payload = json.loads((Path(__file__).resolve().parent / "data" / "polarizability_refit.json").read_text(encoding="utf-8"))
    table = {e: row["value"] for e, row in payload["fitted"].items()}
    table.update({e: row["value"] for e, row in payload["unsourced"].items()})
    return table, frozenset(payload["unsourced"]), payload


def _weak_elements() -> frozenset[str]:
    """Elements fitted, but to fewer than ten molecules: their value is less certain than the rest."""
    return frozenset(e for e, row in _ADDITIVE_PAYLOAD["fitted"].items() if row["weakly_determined"])


# Atomic polarizabilities, cubic angstroms. Fitted 2026-11-05 to 425 experimental solvent polarizabilities (module docstring; benchmarks/polarizability/).
#: The refitted atomic polarizabilities, the elements whose value has no source, and the parsed file they came from (`data/polarizability_refit.json`).
ADDITIVE_POLARIZABILITY, UNSOURCED_ADDITIVE_ELEMENTS, _ADDITIVE_PAYLOAD = _load_additive_table()
#: The id this method's results carry. It was "jensen" until the table was replaced on 2026-11-05; results stored under that id came from the old table.
ADDITIVE_METHOD_ID = "additive_refit"
#: One constant added once per molecule (`PREREGISTRATION_2.md`): it absorbs that small molecules are more polarizable per atom than a sum over atoms fitted on larger ones says.
ADDITIVE_CONSTANT = float(_ADDITIVE_PAYLOAD["constant"]["value"])
#: Elements fitted to few molecules, whose polarizability a result flags as less certain.
WEAK_ADDITIVE_ELEMENTS = _weak_elements()

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


_PI_DATA_PATH = Path(__file__).resolve().parent / "data" / "pi_orbital_electronegativity.json"

#: The two components of orbital electronegativity, as a CLOSED vocabulary.
#: A free string would let a typo select a different quantity silently --
#: the same reason `applies_to` is closed while `category` is not.
ORBITAL_COMPONENTS: dict[str, str] = {
    "Sigma (PEOE)": "sigma",
    "Pi (SD-POE)": "pi",
}

_DEFAULT_ORBITAL_COMPONENT = "Sigma (PEOE)"

_ORBITAL_NAME = {
    "sigma": "Orbital Electronegativity (sigma)",
    "pi": "Orbital Electronegativity (pi)",
}

_ORBITAL_METHOD = {"sigma": "gasteiger_marsili", "pi": "marsili_sd_poe"}

_ORBITAL_NOTE = {
    "sigma": (
        "chi = a + b*q + c*q^2 at the converged PEOE charge. Absolute values are "
        "parameter-set dependent; the ordering between atoms is the meaningful part."
    ),
    "pi": (
        "chi_pi = a + b*q + c*q^2 on Marsili & Gasteiger's Table I, at the converged "
        "PEOE SIGMA charge -- their starting POE values, NOT iterated to pi "
        "self-consistency. Covers the conjugated atoms only. Absolute values are "
        "parameter-set dependent; the ordering between atoms is the meaningful part, "
        "and it is NOT the sigma ordering -- a sigma-negative atom is screened and "
        "comes out lower, which is the effect these parameters exist to carry."
    ),
}


def _orbital_component(parameters: dict[str, Any]) -> str:
    """The provenance method id for the chosen component label.

    An unrecognised label falls back to SIGMA rather than raising, for the
    reason `_polarizability_method` records: a project stored by a future
    version must not make an older one unopenable. The RECORDED component
    is what stops that fallback being silent -- these are two different
    quantities on two different parameter sets, so a fallback nobody can
    see would change what a stored number MEANS.
    """
    label = str(parameters.get("component", _DEFAULT_ORBITAL_COMPONENT))
    return ORBITAL_COMPONENTS.get(label, ORBITAL_COMPONENTS[_DEFAULT_ORBITAL_COMPONENT])


@lru_cache(maxsize=1)
def pi_parameter_table() -> dict[str, dict[str, Any]]:
    """Marsili & Gasteiger 1980 Table I [source:marsili1980], by row key."""
    return json.loads(_PI_DATA_PATH.read_text(encoding="utf-8"))["orbitals"]


def _pi_role(atom: Chem.Atom) -> str | None:
    """Which of Table I's two kinds of orbital this atom contributes.

    `pz` is an atom putting ONE electron into a pi bond; `pair` is one
    donating a LONE PAIR into conjugation. The paper keys its rows that
    way ("N-sp2 (pz)" against "N-sp3 (electron pair)") and the two rows
    for one element are far apart -- nitrogen is 7.95 against 4.54 -- so
    picking the wrong one is not a rounding difference.

    The aromatic heteroatoms are the only place this needs a rule rather
    than a bond order: a pyridine nitrogen contributes one electron and a
    pyrrole nitrogen contributes two, and they differ by their connection
    count, not by anything RDKit exposes directly. Furan's oxygen and
    thiophene's sulfur are always two-electron donors.
    """
    symbol = atom.GetSymbol()
    if atom.GetIsAromatic():
        if symbol == "C":
            return "pz"
        if symbol == "N":
            return "pair" if atom.GetDegree() + atom.GetTotalNumHs() >= 3 else "pz"
        if symbol in ("O", "S"):
            return "pair"
        return None
    if any(bond.GetBondTypeAsDouble() > 1.0 for bond in atom.GetBonds()):
        return "pz" if symbol in ("C", "N", "O", "S") else None
    if symbol == "C":
        return None
    if any(
        neighbour.GetIsAromatic()
        or any(b.GetBondTypeAsDouble() > 1.0 for b in neighbour.GetBonds())
        for neighbour in atom.GetNeighbors()
    ):
        return "pair"
    return None


def _pi_chi_parameters(atom: Chem.Atom) -> tuple[float, float, float] | None:
    role = _pi_role(atom)
    if role is None:
        return None
    for row in pi_parameter_table().values():
        if row["element"] == atom.GetSymbol() and row["role"] == role:
            return (row["a"], row["b"], row["c"])
    return None


def pi_orbital_electronegativities(mol: Chem.Mol) -> dict[int, float]:
    """chi_pi at each conjugated atom's SIGMA charge, in eV.

    Marsili & Gasteiger's eq (7), `chi_pi = a + b*q + c*q^2`, evaluated at
    the converged PEOE sigma charge -- what [source:marsili1980] calls the
    STARTING POE values: "After the sigma level computation the sigma
    charges of the atoms involved in a pi level calculation are inserted
    into their specific POE parabolas (7) and from them the starting POE
    values are obtained."

    **IT IS THE STARTING VALUE AND NOT A CONVERGED ONE**, which is the
    whole limitation and is stated in the calculator's contract too. The
    paper's pi-charge iteration is not implemented here (see
    docs/VALIDATION.md for the three reconstructions that were measured
    and not shipped), so nothing below reflects pi charge redistribution.

    That is still the quantity that decides the DIRECTION of conjugation,
    which is the paper's own central point: with neutral-state values "no
    transfer from the heteroatom to the double bond would be possible",
    and inserting the sigma charge is what makes the lone pair's POE fall
    below the vicinal carbon's so a +M effect can be predicted at all.

    An atom outside the pi system is ABSENT rather than zero. Zero is a
    value on this scale and every real one here is positive, so reporting
    it for an atom that has no pi orbital would be a number with no
    referent.
    """
    working = Chem.Mol(mol)
    rdPartialCharges.ComputeGasteigerCharges(working)
    values: dict[int, float] = {}
    for atom in working.GetAtoms():
        coefficients = _pi_chi_parameters(atom)
        if coefficients is None or not atom.HasProp("_GasteigerCharge"):
            continue
        charge = atom.GetDoubleProp("_GasteigerCharge")
        if charge != charge:  # NaN, for atoms Gasteiger cannot type
            continue
        a, b, c = coefficients
        values[atom.GetIdx()] = a + b * charge + c * charge * charge
    return values


def _maybe_microspecies(mol: Chem.Mol, parameters: dict[str, Any]) -> Chem.Mol:
    """The reference editor offers "take major microspecies at pH" on both plugins, and
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
        contribution = ADDITIVE_POLARIZABILITY.get(atom.GetSymbol())
        if contribution is None:
            return None
        values[atom.GetIdx()] = contribution
    # The per-molecule constant is shared out equally so the atoms still sum to the molecule's value; it is not a property of any one atom.
    share = ADDITIVE_CONSTANT / len(values) if values else 0.0
    return {i: v + share for i, v in values.items()}


def molecular_polarizability(mol: Chem.Mol) -> float | None:
    values = atomic_polarizabilities(mol)
    return None if values is None else sum(values.values())


def _outside_additive_table(target: Chem.Mol) -> CalculationRefusal:
    """An element with no entry in `ADDITIVE_POLARIZABILITY` is outside the
    method, which is a limit and not a fault. It used to come back as a bare
    failure on every sodium salt (round 5 sweep), painted like a crash. The
    covered set is READ from the table, so the sentence cannot drift from it."""
    missing = ", ".join(_unparameterised_elements(target))
    covered = ", ".join(ADDITIVE_POLARIZABILITY)
    return CalculationRefusal(
        ELEMENT_OUTSIDE_PARAMETER_SET,
        "Element outside the additive table",
        f"No additive polarizability parameter for: {missing}. The table covers {covered}.",
    )


def _elements_present(mol: Chem.Mol) -> set[str]:
    return {atom.GetSymbol() for atom in Chem.AddHs(mol).GetAtoms()}


def _unparameterised_elements(mol: Chem.Mol) -> list[str]:
    return sorted(
        {
            atom.GetSymbol()
            for atom in Chem.AddHs(mol).GetAtoms()
            if atom.GetSymbol() not in ADDITIVE_POLARIZABILITY
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
    "Atomic additive": ADDITIVE_METHOD_ID,
    "Miller ahc": "miller_ahc",
    "Miller ahp": "miller_ahp",
}

_DEFAULT_POLARIZABILITY_METHOD = "Atomic additive"
#: The label this method had before its citation was corrected (2026-11-05); a stored project may still hold it.
_LEGACY_POLARIZABILITY_LABELS = {"Jensen (additive)": "Atomic additive"}


def _polarizability_method(parameters: dict[str, Any]) -> str:
    """The provenance method id for the chosen label.

    An unrecognised label falls back to Jensen rather than raising: a
    stored project written by a future version must not make an old one
    unopenable, and the recorded method says which was used either way.
    """
    label = str(parameters.get("method", _DEFAULT_POLARIZABILITY_METHOD))
    label = _LEGACY_POLARIZABILITY_LABELS.get(label, label)
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

    if method == ADDITIVE_METHOD_ID:
        total = molecular_polarizability(target)
        if total is None:
            refusal = _outside_additive_table(target)
            return report_from_fields(
                alert_id="polarizability",
                name="Polarizability",
                molecule_uuid=molecule_uuid,
                matched=[],
                category="electronic",
                cache_state=CacheState.FAILED,
                error=refusal.detail,
                error_summary=refusal.summary,
                inapplicable=True,
                provenance=Provenance(created_by="core", method=method,
                                      parameters={"method": method, "refusal": refusal.code}),
            )
        failure = None
        basis = (
            "Additive atomic scheme plus one constant per molecule, fitted by this project to experimental polarizabilities of 425 solvents (Bosque and Sales 2002) "
            "and 264 further molecules (CRC Handbook). Typical error about 2% on solvents like the first and about 8% on the second, which is more varied; "
            "molecules of six atoms or fewer are still about 9% low on average (13% mean absolute), and it has no hybridization dependence, "
            "so fused aromatics (about 11% low) and strained, charged or unusual molecules can be further off."
        )
        weak = sorted(_elements_present(target) & WEAK_ADDITIVE_ELEMENTS)
        if weak:
            basis += f" Note: {', '.join(weak)} was fitted to fewer than ten molecules, so its value is less certain."
        unsourced = sorted(_elements_present(target) & UNSOURCED_ADDITIVE_ELEMENTS)
        if unsourced:
            basis += (
                f" WARNING: {', '.join(unsourced)} has a value that was never fitted to data and has no recorded source; "
                "treat the total as unvalidated."
            )
        assignment: dict[str, int] = {}
    else:
        total, failure, basis, assignment = _miller_polarizability(target, method)

    if total is None:
        return report_from_fields(
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
    report = report_from_fields(
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
    if method != ADDITIVE_METHOD_ID or parameters.get("major_microspecies"):
        return report
    # **THE DEFAULT ANSWER'S NUMBER IS TYPED, AND NO OTHER ONE IS.** The first line is a fact whose value was the text the line shows (`'10.29'`), which a derived score
    # must not rest on: it would move with a display setting. The producer holds the number, so it hands it over, and the line, the label, the units and the cell's text do not move
    # (`tests/test_polarizability_typed.py` holds them to a recording made before this change). Only Jensen's answer on the drawing is typed: Miller's two methods and the
    # microspecies option are different estimators or a different structure under the same id and label, and a score must not read one as the other.
    facts = tuple(
        replace(fact, value=float(total)) if fact.label == "Molecular polarizability" else fact for fact in report.facts
    )
    return replace(report, facts=facts)


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
    the "atomic" Type option in the reference editor's panel."""
    _places = decimals(parameters)
    parameters = parameters or {}
    target = _maybe_microspecies(mol, parameters)
    values = atomic_polarizabilities(target)
    if values is None:
        refusal = _outside_additive_table(target)
        return PerAtomDataset(
            property_id="atomic_polarizability",
            name="Atomic Polarizability",
            units="A^3",
            method=ADDITIVE_METHOD_ID,
            molecule_uuid=molecule_uuid,
            values={},
            cache_state=CacheState.FAILED,
            error=refusal.detail,
            error_summary=refusal.summary,
            inapplicable=True,
            provenance=Provenance(created_by="core", method=ADDITIVE_METHOD_ID,
                                  parameters={"decimal_places": _places, "refusal": refusal.code}),
        )
    return PerAtomDataset(
        property_id="atomic_polarizability",
        name="Atomic Polarizability",
        units="A^3",
        method=ADDITIVE_METHOD_ID,
        molecule_uuid=molecule_uuid,
        values=values,
        provenance=Provenance(
            created_by="core",
            method=ADDITIVE_METHOD_ID,
            parameters={
                "decimal_places": _places,
                **({"summary": "Unsourced element value (never fitted to data): " + ", ".join(sorted(_elements_present(target) & UNSOURCED_ADDITIVE_ELEMENTS))}
                   if _elements_present(target) & UNSOURCED_ADDITIVE_ELEMENTS else {}),
                # `atomic_polarizabilities` works on `Chem.AddHs(mol)`, so
                # every hydrogen carries its own value and the basis is
                # explicit whatever was handed in.
                ATOM_BASIS: EXPLICIT_H,
                # This method IS an additive atomic scheme -- the
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

    Hydrogens are excluded by default, matching the reference editor, which displays
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

    Two components, chosen by the `component` parameter.

    SIGMA is Gasteiger-Marsili PEOE [source:gasteiger1980] via RDKit, and
    is the default and the historical behaviour.

    PI is Marsili & Gasteiger's eq (7) [source:marsili1980] on their own
    Table I parameters, at the atom's converged sigma charge -- the paper's
    STARTING POE values. It is not iterated to pi self-consistency; see
    `pi_orbital_electronegativities` and docs/VALIDATION.md, which records
    the three pi-charge reconstructions that were measured and refused.

    THEY ARE DIFFERENT QUANTITIES ON DIFFERENT PARAMETER SETS, not one
    number relabelled -- nitrogen's two rows alone are 7.95 and 4.54 --
    which is what makes offering the pi one honest at all.
    """
    _places = decimals(parameters)
    parameters = parameters or {}
    component = _orbital_component(parameters)
    target = _maybe_microspecies(mol, parameters)
    if component == "pi":
        # `include_hydrogens` is not consulted: hydrogen has no pi orbital
        # and no row in Table I, so there is nothing for it to include.
        values = pi_orbital_electronegativities(target)
    else:
        values = orbital_electronegativities(
            target, include_hydrogens=bool(parameters.get("include_hydrogens", False))
        )
    if not values:
        return PerAtomDataset(
            property_id="orbital_electronegativity",
            name=_ORBITAL_NAME[component],
            units="eV",
            method=_ORBITAL_METHOD[component],
            molecule_uuid=molecule_uuid,
            values={},
            cache_state=CacheState.FAILED,
            error=(
                "This molecule has no conjugated pi system, so no atom has a "
                "pi-orbital electronegativity."
                if component == "pi"
                else "No atom in this molecule has Gasteiger-Marsili parameters."
            ),
            error_summary=("No pi system" if component == "pi" else "No parameters"),
            # A LIMIT OF THE METHOD, not a fault: nothing to fix in the drawing.
            inapplicable=True,
            provenance=Provenance(
                created_by="core",
                method=_ORBITAL_METHOD[component],
                parameters={
                    "decimal_places": _places, "component": component,
                    "refusal": "NO_PI_SYSTEM" if component == "pi" else ELEMENT_OUTSIDE_PARAMETER_SET,
                },
            ),
        )
    return PerAtomDataset(
        property_id="orbital_electronegativity",
        name=_ORBITAL_NAME[component],
        units="eV",
        method=_ORBITAL_METHOD[component],
        molecule_uuid=molecule_uuid,
        values=values,
        provenance=Provenance(
            created_by="core",
            method=_ORBITAL_METHOD[component],
            parameters={
                "component": component,
                "note": _ORBITAL_NOTE[component],
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
