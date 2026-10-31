"""Which ORCA calculators the assistant can ask a person to start, and what each one is (`docs/AI_CALCULATION_BRIDGE.md`, section 17).

**A CALCULATOR IS STARTABLE HERE ONLY IF A CARD CAN STATE ALL OF IT.** `orca.sp` is one job whose settings are the three the Quantum Chemistry panel's Run button reads (calculation type, method and
basis, charge and multiplicity), so a card can state them all and the person approving it is approving exactly what the button would have started (`chem/quantum_run_request.prepare_run` applies
the button's own rules to it). Proton affinity is the second kind, a FIXED PROTOCOL: it has no setting to choose (the benchmarked method is the only one), it runs on the drawing and not on a stored
conformer, and what a card has to say is the base, how many ORCA jobs that is and whether the benchmark measured it (`prepare_proton_affinity`). The others stay where they were: bond dissociation
asks which bonds in a dialog, the tautomer runs enumerate their own jobs, and the experimental Fukui calculation is hidden by default. A model is told of those as "run from its own panel".

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
    "orca.proton_affinity": "proton_affinity",
})

#: The startable calculators that are a fixed protocol: no setting to choose, run on the DRAWING (every structure is embedded fresh) and needing no stored conformer.
FIXED_PROTOCOL = frozenset({"orca.proton_affinity"})


def calc_type_of(calculator_id: str) -> str | None:
    """The calculation type code of a calculator a person can approve for the assistant, or None for any other."""
    return STARTABLE.get(calculator_id)
