"""The DREIDING force field, implemented from the primary source.

Mayo, Olafson & Goddard, J. Phys. Chem. 1990, 94, 8897-8909.

Kept apart from `chem/geometry_analysis.py` because it is a force field
rather than a descriptor: the parameters, the typer and the energy terms
each have their own reasons to change, and the validation that matters is
against the paper's own published numbers rather than against any of
this project's other chemistry.
"""

from openchem.chem.dreiding.energy import (
    UNSUPPORTED_TERMS,
    EnergyBreakdown,
    dreiding_energy,
)
from openchem.chem.dreiding.typer import UntypedAtomError, assign_types, atom_type

__all__ = [
    "UNSUPPORTED_TERMS",
    "EnergyBreakdown",
    "UntypedAtomError",
    "assign_types",
    "atom_type",
    "dreiding_energy",
]
