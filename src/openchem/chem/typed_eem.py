"""Two further EEM models, typed by element and bond order: Jiroušková 2009 (B3LYP/6-31G* Merz-Kollman) and NEEMP 2016's Ccd2016 (B3LYP/6-311G NPA).

THE CLAIM, AND ONLY THIS CLAIM: these are the charges that the published model assigns to this structure. They are not Bultinck's (`charge_equilibration.eem_charges`)
and not each other's: each model has its own kappa and its own charge scheme, so Cl and S from one cannot be added to the C, H, N and O of another. What is
validated, what is refused and why is `benchmarks/charges/models/eem_second_models_preregistration.md`, written before this file.

THE SYSTEM, read from the papers and from NEEMP's solver (`src/eem.c`, `fill_EEM_matrix_packed`) and the same matrix `charge_equilibration.ionescu_system`
builds: unknowns (q_1 .. q_N, chi); B_i on the diagonal; kappa / r_ij off it with r in ANGSTROM (the solver reads SDF coordinates and divides by their
distance, with no conversion); a column of -1 for chi; a row of ones; right-hand side (-A_1 .. -A_N, Q). A and B are in the papers' units ("Pauling units").

AN ATOM'S TYPE is its element plus the HIGHEST bond order of any bond to it, 1, 2 or 3, in a Kekule structure (NEEMP's `io.c`: an SDF bond of type 4 makes a
molecule invalid there). This module takes the bonds as a list and never an RDKit molecule, so it cannot reorder or drop an atom: the caller (a later
integration, not here) kekulises and lists them. A type the model lacks is a REFUSAL naming the type and, when the other model has it, the other model.

A NITRO GROUP OR CARBOXYLATE has two oxygens that are the same atom chemically but get different types, O1 and O2, from whichever the drawing made double-bonded, so
the plain model gives them different charges and gives one structure written two ways two answers (`benchmarks/charges/models/eem_resonance_typing_design.md`). The
`resonance` argument chooses what is done about it, given the resonance forms the caller found (`chem/resonance_forms.py` finds them): `as_drawn` is the published
model on the drawing, with a warning on the atoms that depend on it; `averaged` gives each such atom the MEAN of the parameters of its types over the forms (after Gilson,
Gilson and Potter 2003), an extension the claim line states; `refuse` declines such a molecule. The solver stays pure: it averages the forms it is handed.

Pure numpy, like its neighbour: element symbols, coordinates in angstrom, bonds and a net charge in; charges out.
"""

from __future__ import annotations

import functools
import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from openchem.chem.charge_equilibration import (
    OVERLAP_ANGSTROM,
    REFUSE_NOT_CONVERGED,
    REFUSE_OVERLAPPING_ATOMS,
    _overlap,
)

#: Where the shipped parameters live; built by `tools/build_eem_second_models.py` from the committed fixtures.
PARAMETERS_PATH = Path(__file__).resolve().parent / "data" / "eem_second_models.json"

#: Model J: Jiroušková 2009, B3LYP/6-31G* Merz-Kollman.
JIROUSKOVA2009_B3LYP_MK = "jirouskova2009_b3lyp_mk"
#: Model N: NEEMP 2016, Ccd2016, B3LYP/6-311G NPA.
NEEMP2016_CCD_GEN_NPA = "neemp2016_ccd_gen_npa"
#: Both models, in the order the parameter file lists them.
MODELS = (JIROUSKOVA2009_B3LYP_MK, NEEMP2016_CCD_GEN_NPA)

#: Types a paper parameterises that this application does not accept: preregistration section 8. Zinc is Jiroušková's only metal, from 52 atoms, and a
#: metal's bonds do not fit a highest-bond-order typing.
OUT_OF_SCOPE_TYPES = {JIROUSKOVA2009_B3LYP_MK: frozenset({"Zn1"}), NEEMP2016_CCD_GEN_NPA: frozenset()}

#: An atom's type is not in the model (or the atom has no bond, or the model leaves the type out of scope). The message names the type.
REFUSE_TYPE_NOT_PARAMETERISED = "REFUSE_TYPE_NOT_PARAMETERISED"
#: The bond list is not a list of bonds between this structure's atoms with orders 1 to 3.
REFUSE_BAD_BONDS = "REFUSE_BAD_BONDS"
#: `resonance="refuse"` and some atom's type depends on how the structure is drawn.
REFUSE_RESONANCE_DEPENDENT = "REFUSE_RESONANCE_DEPENDENT"

#: What to do about an atom whose type depends on the drawing (the option of `eem_resonance_typing_design.md`). Stored as these codes, never as words.
RESONANCE_AVERAGED = "averaged"
#: Use the drawing as it is, with a warning on the atoms that depend on it.
RESONANCE_AS_DRAWN = "as_drawn"
#: Decline a molecule whose types depend on the drawing.
RESONANCE_REFUSE = "refuse"
#: Every accepted value of the `resonance` option.
RESONANCE_VALUES = (RESONANCE_AVERAGED, RESONANCE_AS_DRAWN, RESONANCE_REFUSE)

#: The claim line of an averaged result: what it is, and that it is not the published model.
AVERAGED_CLAIM = (
    "The charges this EEM model gives, with the parameters of atoms whose type depends on how the structure is drawn (the two oxygens of a nitro group or a carboxylate) "
    "averaged over the resonance forms, after Gilson, Gilson and Potter 2003. That averaging is an extension of the published model, not something its authors computed."
)


@dataclass
class TypedEEMResult:
    status: str
    charges: np.ndarray | None = None
    #: One type per atom, in the caller's order: "C2", "Cl1".
    atom_types: tuple[str, ...] = ()
    #: The equalised electronegativity chi, in the paper's units.
    equalized_electronegativity: float | None = None
    message: str = ""
    #: When the refusal is for a type the OTHER model has, that model's id; else "".
    alternative: str = ""
    #: The `resonance` code the result was computed with.
    resonance: str = RESONANCE_AS_DRAWN
    #: Atoms (the caller's indices) whose type differs between the resonance forms, or from the drawing's own; empty when the caller gave no forms.
    variable_atoms: tuple[int, ...] = ()
    #: How many resonance forms the parameters were averaged over (1 unless `averaged` and some atom varies).
    forms_used: int = 1
    #: The (A, B) each atom was solved with, in the caller's order: the table's own values, or their mean over the forms for a variable atom under `averaged`.
    parameters_used: tuple[tuple[float, float], ...] = ()
    #: Sentences a surface must show beside the charges (a caveat for `as_drawn`).
    warnings: tuple[str, ...] = ()
    #: What the charges are, when that is more than the model's own claim; "" for the plain published model.
    claim: str = ""


@functools.lru_cache(maxsize=1)
def parameters() -> dict:
    """The shipped models: {id: {label, scheme, kappa, types: {"C2": [A, B]}, ...}}."""
    return json.loads(PARAMETERS_PATH.read_text(encoding="utf-8"))["models"]


def highest_bond_orders(count: int, bonds: Sequence[tuple[int, int, int]]) -> list[int]:
    """The highest bond order of any bond to each atom (0 for an atom with no bond). Raises ValueError for a bond that is not between two different atoms of
    this structure or whose order is not 1, 2 or 3 (an aromatic order of 4 is the caller's to kekulise first)."""
    orders = [0] * count
    for i, j, order in bonds:
        if not (0 <= i < count and 0 <= j < count) or i == j:
            raise ValueError(f"bond ({i}, {j}) is not between two different atoms of a {count}-atom structure")
        if order not in (1, 2, 3):
            raise ValueError(f"bond ({i}, {j}) has order {order}; a Kekule structure has only 1, 2 and 3")
        orders[i] = max(orders[i], order)
        orders[j] = max(orders[j], order)
    return orders


def atom_types(elements: Sequence[str], bonds: Sequence[tuple[int, int, int]]) -> tuple[str, ...]:
    """Each atom's type, element then highest bond order: ("C2", "H1", ...). An atom with no bond is "X0"."""
    return tuple(f"{element}{order}" for element, order in zip(elements, highest_bond_orders(len(elements), bonds), strict=True))


def _missing(model: str, types: Sequence[str]) -> list[str]:
    known = parameters()[model]["types"]
    excluded = OUT_OF_SCOPE_TYPES[model]
    return sorted({t for t in types if t not in known or t in excluded})


def typed_system(
    types: Sequence[str], coords_angstrom, model: str, net_charge: float = 0.0, parameters_override: Sequence[tuple[float, float]] | None = None
) -> tuple[np.ndarray, np.ndarray]:
    """The (N+1)x(N+1) system for atoms of these (already accepted) types. See the module docstring for its form. `parameters_override` gives each atom's (A, B) directly
    (for atoms whose parameters were averaged); without it they are the types' own."""
    entry = parameters()[model]
    coords = np.asarray(coords_angstrom, dtype=float).reshape(-1, 3)
    count = len(types)
    distance = np.linalg.norm(coords[:, None, :] - coords[None, :, :], axis=-1)
    matrix = np.zeros((count + 1, count + 1))
    rhs = np.zeros(count + 1)
    for i, atom_type in enumerate(types):
        a, b = parameters_override[i] if parameters_override is not None else entry["types"][atom_type]
        matrix[i, i] = b
        rhs[i] = -a
        for j in range(count):
            if j != i:
                matrix[i, j] = entry["kappa"] / distance[i, j]
    matrix[:count, count] = -1.0
    matrix[count, :count] = 1.0
    rhs[count] = net_charge
    return matrix, rhs


def _variable_atoms(drawn: Sequence[str], form_types: Sequence[Sequence[str]]) -> tuple[int, ...]:
    return tuple(i for i in range(len(drawn)) if len({drawn[i], *(ft[i] for ft in form_types)}) > 1)


def typed_charges(
    elements: Sequence[str],
    coords_angstrom,
    bonds: Sequence[tuple[int, int, int]],
    model: str,
    net_charge: float = 0.0,
    *,
    resonance: str = RESONANCE_AS_DRAWN,
    bond_forms: Sequence[Sequence[tuple[int, int, int]]] | None = None,
) -> TypedEEMResult:
    """The charges `model` assigns, or a refusal. `bonds` is the drawing's own Kekule bond list; `bond_forms` is the resonance forms to consider (each a bond list over the same
    atoms; the caller selects them), or None for "none were looked for", in which case no atom is variable and all three `resonance` values give the drawing's answer.

    Refuses, in this order and each by name: a bad bond list, a molecule whose types depend on the drawing (only for `refuse`), a type the model lacks (naming the other model
    when it has the type), two overlapping atoms, and a system it cannot solve."""
    if model not in MODELS:
        raise ValueError(f"unknown model {model!r}; the models are {', '.join(MODELS)}")
    if resonance not in RESONANCE_VALUES:
        raise ValueError(f"unknown resonance option {resonance!r}; the values are {', '.join(RESONANCE_VALUES)}")
    coords = np.asarray(coords_angstrom, dtype=float).reshape(-1, 3)
    count = len(elements)
    if coords.shape[0] != count:
        raise ValueError("one coordinate row per element is required")
    forms = [list(f) for f in bond_forms] if bond_forms else []
    try:
        types = atom_types(elements, bonds)
        form_types = [atom_types(elements, f) for f in forms]
    except ValueError as exc:
        return TypedEEMResult(status=REFUSE_BAD_BONDS, message=str(exc), resonance=resonance)
    variable = _variable_atoms(types, form_types)

    if resonance == RESONANCE_REFUSE and variable:
        shown = ", ".join(f"atom {i} ({'/'.join(sorted({types[i], *(ft[i] for ft in form_types)}))})" for i in variable[:6]) + (" ..." if len(variable) > 6 else "")
        return TypedEEMResult(
            status=REFUSE_RESONANCE_DEPENDENT,
            atom_types=types,
            resonance=resonance,
            variable_atoms=variable,
            message=(
                f"The type of {shown} depends on how this structure is drawn (the two oxygens of a nitro group or a carboxylate are the same atom, but one is typed with a double "
                "bond and the other without). The resonance option can be set to 'averaged', which averages the parameters over the resonance forms, or 'as_drawn', which uses the drawing as it is and warns."
            ),
        )

    averaging = resonance == RESONANCE_AVERAGED and bool(variable) and bool(form_types)
    relevant = form_types if averaging else [types]
    needed = [t for ts in relevant for t in ts]
    missing = _missing(model, needed)
    if missing:
        entry = parameters()[model]
        others = [m for m in MODELS if m != model and not _missing(m, needed)]
        alternative = others[0] if others else ""
        message = f"{entry['label']} has no parameters for the atom type{'s' if len(missing) > 1 else ''} {', '.join(missing)} (element and highest bond order)."
        if any(t.endswith("0") for t in missing):
            message += " An atom with no bond has order 0."
        if alternative:
            message += f" {parameters()[alternative]['label']} has {'them' if len(missing) > 1 else 'it'}; it is a different model, so no charge is taken from it here."
        return TypedEEMResult(status=REFUSE_TYPE_NOT_PARAMETERISED, atom_types=types, message=message, alternative=alternative, resonance=resonance, variable_atoms=variable)

    pair = _overlap(coords)
    if pair is not None:
        return TypedEEMResult(status=REFUSE_OVERLAPPING_ATOMS, atom_types=types, message=f"Atoms {pair[0]} and {pair[1]} are closer than {OVERLAP_ANGSTROM} A.", resonance=resonance, variable_atoms=variable)

    table = parameters()[model]["types"]
    used: list[tuple[float, float]] = []
    for i in range(count):
        if averaging and i in variable:
            # math.fsum is exactly rounded whatever the order, so two atoms that see the same forms in a different order get bit-identical parameters (a plain mean does not)
            used.append((math.fsum(table[ft[i]][0] for ft in form_types) / len(form_types), math.fsum(table[ft[i]][1] for ft in form_types) / len(form_types)))
        else:
            a, b = table[types[i]]  # an atom that does not vary keeps its own type's numbers exactly, so a molecule with no variable atom is bit-identical under every value
            used.append((float(a), float(b)))

    matrix, rhs = typed_system(types, coords, model, net_charge, used)
    try:
        solution = np.linalg.solve(matrix, rhs)
    except np.linalg.LinAlgError:
        return TypedEEMResult(status=REFUSE_NOT_CONVERGED, atom_types=types, message="The EEM system is singular for this structure.", resonance=resonance, variable_atoms=variable)
    if not np.all(np.isfinite(solution)):
        return TypedEEMResult(status=REFUSE_NOT_CONVERGED, atom_types=types, message="The EEM system gave a non-finite charge for this structure.", resonance=resonance, variable_atoms=variable)

    warnings: tuple[str, ...] = ()
    if resonance == RESONANCE_AS_DRAWN and variable:
        shown = ", ".join(str(i) for i in variable[:8]) + (" ..." if len(variable) > 8 else "")
        warnings = (
            f"The charges on atoms {shown} depend on how this structure was drawn: the same structure written another way (which oxygen of a nitro group or carboxylate has the double bond) "
            "gives different charges on them, by up to about 0.1 e on the structures measured. Set the resonance option to 'averaged' for charges that do not depend on the drawing.",
        )
    return TypedEEMResult(
        status="converged",
        charges=solution[:count],
        atom_types=types,
        equalized_electronegativity=float(solution[count]),
        resonance=resonance,
        variable_atoms=variable,
        forms_used=len(form_types) if averaging else 1,
        parameters_used=tuple(used),
        warnings=warnings,
        claim=AVERAGED_CLAIM if averaging else "",
    )
