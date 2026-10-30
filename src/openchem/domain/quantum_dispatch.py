"""Which ORCA calculators the assistant can ask a person to start, and what each one is (`docs/AI_CALCULATION_BRIDGE.md`, section 17).

**A CALCULATOR IS STARTABLE HERE ONLY IF ONE ORCA JOB IS ALL IT IS.** `orca.sp` is one job whose settings are the three the Quantum Chemistry panel's Run button reads (calculation type, method and
basis, charge and multiplicity), so a card can state them all and the person approving it is approving exactly what the button would have started (`chem/quantum_run_request.prepare_run` applies
the button's own rules to it). The others stay where they were: proton affinity and bond dissociation each ask a question of their own in a dialog (which site, which bond), the tautomer runs
enumerate their own jobs, and the experimental Fukui calculation is hidden by default. A model is told of those as "run from its own panel".

Pure: no Qt, no RDKit.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

#: Calculator id -> the ORCA calculation type code the Quantum Chemistry panel's `RunChoice.calc_type` carries. The ids are registered in `bootstrap.py` as `orca.<code>`.
STARTABLE: Mapping[str, str] = MappingProxyType({
    "orca.sp": "sp",
    "orca.opt": "opt",
    "orca.opt_freq": "opt_freq",
    "orca.nmr": "nmr",
    "orca.nmr_coupling": "nmr_coupling",
    "orca.delta_scf": "delta_scf",
    "orca.led": "led",
})


def calc_type_of(calculator_id: str) -> str | None:
    """The calculation type code of a calculator a person can approve for the assistant, or None for any other."""
    return STARTABLE.get(calculator_id)
