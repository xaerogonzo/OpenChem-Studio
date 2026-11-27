"""PREREGISTRATION: ESOL on stable radicals (OS4, the last item: `solubility` on radicals).

Written and committed BEFORE ESOL was run on these molecules. The reference is the first measured aqueous solubility of nitroxide radicals held here: Zhou, Liu, Qin, Chen, Xu, Cao and Li, 'Fundamental properties of
TEMPO-based catholytes for aqueous redox flow batteries', RSC Advances 10, 21839-21844 (2020), doi:10.1039/d0ra03424j (`zhou2020.pdf`), Table 1, 'Solubility in pure water (M)', journal page 21841 (PDF page 3): UV-vis
after 48 h equilibration of excess solid, at 'room temperature' (no number given), five 4-substituted TEMPO radicals from one laboratory. Plain TEMPO is not in the paper.

QUESTION. Is the baseline of the application's `solubility` calculator (ESOL, `chem.solubility.esol_logs`, an input of the closed-shell formula with no spin term) within its own usual error on these five stable radicals?

RULE. measured logS = log10(M). error = ESOL logS minus measured logS, in log units. A radical EXCEEDS when |error| is more than ESOL's own published error on this project's two independent sets, its SC-2 RMSE of 1.26
(`chem/solubility.py` docstring: 'all n=73 MAE 0.90 RMSE 1.26', Delaney's fitting set subtracted by InChIKey). Verdict over the five:
    0 exceed       CONSISTENT: within ESOL's usual error on this panel (a statement about five radicals from one laboratory, not a validation)
    1 exceeds      MIXED: reported, with its error and sign
    2 or more      NOT CONSISTENT: the warning states the measured errors and their sign
The mean signed error is reported in every case. AqSolDB is not run (its sidecar is not set up on the machine that runs this).

CAVEATS written down before the run: 4-amino-TEMPO is a base and 4-carboxy-TEMPO an acid, so their 'pure water' solutions are partly ionised and ESOL (a neutral-species formula) is asked about the neutral; the temperature is
'room temperature'; the three weakly polar derivatives are the cleaner test.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

#: ESOL's own RMSE on the project's second independent set (`chem/solubility.py` docstring): the size of error that is usual for the model.
ESOL_USUAL_ERROR = 1.26

CONSISTENT, MIXED, NOT_CONSISTENT = "CONSISTENT", "MIXED", "NOT CONSISTENT"


@dataclass(frozen=True)
class Radical:
    name: str
    smiles: str
    #: Solubility in pure water, mol/L, Zhou et al. 2020 Table 1.
    molar: float


#: The five radicals of Zhou et al. 2020 Table 1 with a pure-water value.
PANEL = (
    Radical("4-hydroxy-TEMPO", "CC1(C)CC(O)CC(C)(C)N1[O]", 2.11),
    Radical("4-oxo-TEMPO", "CC1(C)CC(=O)CC(C)(C)N1[O]", 1.22),
    Radical("4-amino-TEMPO", "CC1(C)CC(N)CC(C)(C)N1[O]", 5.79),
    Radical("4-cyano-TEMPO", "CC1(C)CC(C#N)CC(C)(C)N1[O]", 2.6e-2),
    Radical("4-carboxy-TEMPO", "CC1(C)CC(C(=O)O)CC(C)(C)N1[O]", 2.1e-2),
)


def measured_logs(radical: Radical) -> float:
    return math.log10(radical.molar)


def errors(predicted: dict[str, float]) -> dict[str, float]:
    """ESOL minus measured, log units, by radical name. A radical with no prediction is absent."""
    return {r.name: predicted[r.name] - measured_logs(r) for r in PANEL if r.name in predicted}


def verdict(error_by_name: dict[str, float]) -> tuple[str, int, float | None]:
    """(verdict, how many exceed `ESOL_USUAL_ERROR`, mean signed error). INCONCLUSIVE-shaped input (fewer than the five, or a non-finite error) gives `("INCONCLUSIVE", 0, None)`."""
    if len(error_by_name) != len(PANEL) or any(not math.isfinite(e) for e in error_by_name.values()):
        return "INCONCLUSIVE", 0, None
    exceeding = sum(1 for e in error_by_name.values() if abs(e) > ESOL_USUAL_ERROR)
    mean = sum(error_by_name.values()) / len(error_by_name)
    return (CONSISTENT if exceeding == 0 else MIXED if exceeding == 1 else NOT_CONSISTENT), exceeding, mean
