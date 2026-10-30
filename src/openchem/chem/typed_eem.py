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

Pure numpy, like its neighbour: element symbols, coordinates in angstrom, bonds and a net charge in; charges out.
"""

from __future__ import annotations

import functools
import json
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

JIROUSKOVA2009_B3LYP_MK = "jirouskova2009_b3lyp_mk"
NEEMP2016_CCD_GEN_NPA = "neemp2016_ccd_gen_npa"
MODELS = (JIROUSKOVA2009_B3LYP_MK, NEEMP2016_CCD_GEN_NPA)

#: Types a paper parameterises that this application does not accept: preregistration section 8. Zinc is Jiroušková's only metal, from 52 atoms, and a
#: metal's bonds do not fit a highest-bond-order typing.
OUT_OF_SCOPE_TYPES = {JIROUSKOVA2009_B3LYP_MK: frozenset({"Zn1"}), NEEMP2016_CCD_GEN_NPA: frozenset()}

#: An atom's type is not in the model (or the atom has no bond, or the model leaves the type out of scope). The message names the type.
REFUSE_TYPE_NOT_PARAMETERISED = "REFUSE_TYPE_NOT_PARAMETERISED"
#: The bond list is not a list of bonds between this structure's atoms with orders 1 to 3.
REFUSE_BAD_BONDS = "REFUSE_BAD_BONDS"


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


def typed_system(types: Sequence[str], coords_angstrom, model: str, net_charge: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
    """The (N+1)x(N+1) system for atoms of these (already accepted) types. See the module docstring for its form."""
    entry = parameters()[model]
    coords = np.asarray(coords_angstrom, dtype=float).reshape(-1, 3)
    count = len(types)
    distance = np.linalg.norm(coords[:, None, :] - coords[None, :, :], axis=-1)
    matrix = np.zeros((count + 1, count + 1))
    rhs = np.zeros(count + 1)
    for i, atom_type in enumerate(types):
        a, b = entry["types"][atom_type]
        matrix[i, i] = b
        rhs[i] = -a
        for j in range(count):
            if j != i:
                matrix[i, j] = entry["kappa"] / distance[i, j]
    matrix[:count, count] = -1.0
    matrix[count, :count] = 1.0
    rhs[count] = net_charge
    return matrix, rhs


def typed_charges(elements: Sequence[str], coords_angstrom, bonds: Sequence[tuple[int, int, int]], model: str, net_charge: float = 0.0) -> TypedEEMResult:
    """The charges `model` assigns, or a refusal. Refuses, in this order and each by name: a bad bond list, a type the model lacks (naming the other model
    when it has the type), two overlapping atoms, and a system it cannot solve."""
    if model not in MODELS:
        raise ValueError(f"unknown model {model!r}; the models are {', '.join(MODELS)}")
    coords = np.asarray(coords_angstrom, dtype=float).reshape(-1, 3)
    count = len(elements)
    if coords.shape[0] != count:
        raise ValueError("one coordinate row per element is required")
    try:
        types = atom_types(elements, bonds)
    except ValueError as exc:
        return TypedEEMResult(status=REFUSE_BAD_BONDS, message=str(exc))

    missing = _missing(model, types)
    if missing:
        entry = parameters()[model]
        others = [m for m in MODELS if m != model and not _missing(m, types)]
        alternative = others[0] if others else ""
        message = f"{entry['label']} has no parameters for the atom type{'s' if len(missing) > 1 else ''} {', '.join(missing)} (element and highest bond order)."
        if any(t.endswith("0") for t in missing):
            message += " An atom with no bond has order 0."
        if alternative:
            message += f" {parameters()[alternative]['label']} has {'them' if len(missing) > 1 else 'it'}; it is a different model, so no charge is taken from it here."
        return TypedEEMResult(status=REFUSE_TYPE_NOT_PARAMETERISED, atom_types=types, message=message, alternative=alternative)

    pair = _overlap(coords)
    if pair is not None:
        return TypedEEMResult(status=REFUSE_OVERLAPPING_ATOMS, atom_types=types, message=f"Atoms {pair[0]} and {pair[1]} are closer than {OVERLAP_ANGSTROM} A.")

    matrix, rhs = typed_system(types, coords, model, net_charge)
    try:
        solution = np.linalg.solve(matrix, rhs)
    except np.linalg.LinAlgError:
        return TypedEEMResult(status=REFUSE_NOT_CONVERGED, atom_types=types, message="The EEM system is singular for this structure.")
    if not np.all(np.isfinite(solution)):
        return TypedEEMResult(status=REFUSE_NOT_CONVERGED, atom_types=types, message="The EEM system gave a non-finite charge for this structure.")
    return TypedEEMResult(status="converged", charges=solution[:count], atom_types=types, equalized_electronegativity=float(solution[count]))
