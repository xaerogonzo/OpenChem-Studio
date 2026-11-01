"""Which ORCA calculators the assistant can ask a person to start, and what each one is (`docs/AI_CALCULATION_BRIDGE.md`, section 17).

**A CALCULATOR IS STARTABLE HERE ONLY IF A CARD CAN STATE ALL OF IT.** `orca.sp` is one job whose settings are the three the Quantum Chemistry panel's Run button reads (calculation type, method and
basis, charge and multiplicity), so a card can state them all and the person approving it is approving exactly what the button would have started (`chem/quantum_run_request.prepare_run` applies
the button's own rules to it). Proton affinity is the second kind, a FIXED PROTOCOL: it has no setting to choose (the benchmarked method is the only one), it runs on the drawing and not on a stored
conformer, and what a card has to say is the base, how many ORCA jobs that is and whether the benchmark measured it (`prepare_proton_affinity`). Bond dissociation is a fixed protocol too, and the one choice it has, which bonds, is a default a card states (the dialog's own: the first six bond classes) and a person who wants
others starts it from the panel. The tautomer distribution is the third kind: the three settings of an ordinary job, run on the drawing, with the job count its enumeration gives (`prepare_tautomers`) stated on the card. The experimental Fukui
calculation stays where it was, hidden by default. A model is told of those as "run from its own panel".

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
    "orca.bond_dissociation_enthalpy": "bond_dissociation",
    "orca.tautomer_distribution": "tautomer_distribution",
})

#: The startable calculators that are a fixed protocol: no setting to choose (bond dissociation's one choice, which bonds, is stated on the card), run on the DRAWING (every structure is embedded fresh) and needing no stored conformer.
FIXED_PROTOCOL = frozenset({"orca.proton_affinity", "orca.bond_dissociation_enthalpy"})

#: The startable calculators that run on the DRAWING and need no stored conformer: the fixed protocols, and the tautomer distribution, which has the three settings of an ordinary job but
#: embeds every candidate fresh and whose job count is what its enumeration gives, stated on the card.
RUNS_ON_DRAWING = FIXED_PROTOCOL | {"orca.tautomer_distribution"}


def calc_type_of(calculator_id: str) -> str | None:
    """The calculation type code of a calculator a person can approve for the assistant, or None for any other."""
    return STARTABLE.get(calculator_id)
