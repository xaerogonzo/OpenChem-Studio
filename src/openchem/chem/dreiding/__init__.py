"""The DREIDING force field, implemented from the primary source.

Mayo, Olafson & Goddard, J. Phys. Chem. 1990, 94, 8897-8909.

**Validated against all eight of the paper's own rotational barriers**
(Table XI), worst deviation 0.008 kcal/mol -- see
`tests/test_dreiding_barriers.py`. Those are DREIDING's calculated
values rather than experiment, so reproducing them tests this
implementation with no ambiguity left over.

Kept apart from `chem/geometry_analysis.py` because it is a force field
rather than a descriptor: the parameters, the typer, the energy and its
gradient each have their own reasons to change.
"""

from openchem.chem.dreiding.energy import (
    UNSUPPORTED_TERMS,
    EnergyBreakdown,
    dreiding_energy,
)
from openchem.chem.dreiding.gradient import energy_and_gradient
from openchem.chem.dreiding.optimise import OptimisationResult, minimise, relaxed_scan
from openchem.chem.dreiding.typer import UntypedAtomError, assign_types, atom_type

__all__ = [
    "UNSUPPORTED_TERMS",
    "EnergyBreakdown",
    "OptimisationResult",
    "UntypedAtomError",
    "assign_types",
    "atom_type",
    "dreiding_energy",
    "energy_and_gradient",
    "minimise",
    "relaxed_scan",
]
