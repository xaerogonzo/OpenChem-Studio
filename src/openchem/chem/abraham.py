"""Solubility in a solvent other than water, by lookup rather than prediction.

Abraham's solvation equation, in the form his own solubility work uses:

    log Ss = log Sw + c + e*E + s*S + a*A + b*B + v*V

`log Sw` is the aqueous solubility this application already predicts,
`(c, e, s, a, b, v)` are the SOLVENT's coefficients, and `(E, S, A, B, V)`
are the SOLUTE's descriptors.

**BOTH SIDES ARE LOOKED UP, AND NEITHER IS PREDICTED. THAT IS THE DESIGN.**
The obvious route was the Platts group-contribution scheme -- estimate
E, S, A and B from structure, roughly 480 coefficients and 132
hand-written SMARTS patterns to transcribe, each one a place a silent
error can live, and 0.7-1.0 log units of its own error on top of ESOL's.
Looking up an EXPERIMENTAL descriptor costs neither. The price is
coverage: 2193 compounds, and anything else is refused by name.

That trade is the same one `chem/nmr_signals.py` already makes with
`RESIDUAL_SOLVENT_PEAKS` -- published values, exact in a way nothing
predicted can be, for the subset somebody measured.

**A MISCIBLE SOLVENT IS NOT EXCLUDED, and believing otherwise cost a
round of this work.** Ethanol and water are miscible, so no two-phase
partition coefficient exists for them, and the UFZ LSER database omits
ethanol for exactly that reason. Abraham's coefficients are derived from
SOLUBILITY RATIOS rather than a measured partition, so neat ethanol is in
the table and the equation above is valid for it.

DATA, both CC BY 4.0 and both fetched by `tools/build_abraham_tables.py`:

    solvents   Bradley, Abraham & Acree, BMC Chemistry 2015,
               doi 10.1186/s13065-015-0085-4, Table 1 -- 91 MEASURED
               solvents. The paper also PREDICTS coefficients for 293 and
               says of those "not as gospel"; those are not shipped.
    solutes    Bradley, Acree & Lang, figshare 2014,
               doi 10.6084/m9.figshare.1176994 -- experimental descriptors
               with the literature source on every row.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from rdkit import Chem
from rdkit.Chem import inchi

_DATA = Path(__file__).resolve().parent / "data"

#: Above this, the descriptor disagreement alone swamps the answer. A
#: prediction whose uncertainty exceeds a factor of ten is not one.
MAX_PROPAGATED_UNCERTAINTY_LOG = 1.0


@dataclass(frozen=True)
class SolventCoefficients:
    """One solvent's row of the Abraham equation."""

    name: str
    c: float
    e: float
    s: float
    a: float
    b: float
    v: float

    def shift(self, solute: SoluteDescriptors) -> float:
        """`log Ss - log Sw` for this solute in this solvent."""
        return (
            self.c
            + self.e * solute.e
            + self.s * solute.s
            + self.a * solute.a
            + self.b * solute.b
            + self.v * solute.v
        )

    def worst_case_uncertainty(self, solute: SoluteDescriptors) -> float:
        """How far the shift could move on the descriptors' own disagreement.

        `sum(|coefficient| * spread)` PER DESCRIPTOR. Still an upper bound,
        since it assumes every disagreement aligns in the same direction,
        but a real one.

        **THE FIRST VERSION WAS USELESSLY CONSERVATIVE.** It multiplied the
        single widest spread by the SUM of all five coefficient
        magnitudes -- assuming every descriptor was wrong by the worst
        amount at once -- and refused aspirin, caffeine and ibuprofen,
        three of the first four drugs tried. A bound that rejects the
        ordinary case is not a safety feature.

        Exactly zero for the compounds with one measurement.
        """
        return sum(
            abs(getattr(self, key)) * value for key, value in solute.spread.items()
        )


@dataclass(frozen=True)
class SoluteDescriptors:
    """One compound's measured Abraham descriptors."""

    inchikey: str
    name: str
    e: float
    s: float
    a: float
    b: float
    v: float
    #: How many literature rows were merged. More than one means a median
    #: was taken; see `spread`.
    measurements: int
    #: Per-descriptor disagreement between those rows, keyed "e".."v".
    #: Empty when every row agreed, which is the common case.
    spread: dict


@lru_cache(maxsize=1)
def _solvent_table() -> dict[str, SolventCoefficients]:
    payload = json.loads((_DATA / "abraham_solvents.json").read_text(encoding="utf-8"))
    return {
        name.lower(): SolventCoefficients(name=name, **values)
        for name, values in payload["solvents"].items()
    }


@lru_cache(maxsize=1)
def _solute_table() -> dict[str, dict]:
    payload = json.loads((_DATA / "abraham_solutes.json").read_text(encoding="utf-8"))
    return payload["solutes"]


def solvent_names() -> list[str]:
    """Every solvent with MEASURED coefficients, in the source's own naming."""
    return sorted(entry.name for entry in _solvent_table().values())


def solvent_coefficients(name: str) -> SolventCoefficients | None:
    return _solvent_table().get(name.strip().lower())


def solute_descriptors(mol: Chem.Mol) -> SoluteDescriptors | None:
    """This molecule's measured descriptors, or `None` if nobody measured it.

    Keyed on InChIKey rather than SMILES, so a match is on constitution
    and stereochemistry and not on how the source happened to write the
    string.
    """
    try:
        key = inchi.MolToInchiKey(mol)
    except Exception:  # noqa: BLE001 - an unconvertible structure simply has no entry
        return None
    entry = _solute_table().get(key)
    if entry is None:
        return None
    return SoluteDescriptors(
        inchikey=key,
        name=entry["name"],
        e=entry["e"],
        s=entry["s"],
        a=entry["a"],
        b=entry["b"],
        v=entry["v"],
        measurements=entry["n"],
        spread=entry.get("spread", {}),
    )


@dataclass(frozen=True)
class SolventShift:
    """What moving from water to this solvent does to the solubility."""

    solvent: SolventCoefficients
    solute: SoluteDescriptors
    log_shift: float
    uncertainty: float

    @property
    def usable(self) -> bool:
        return self.uncertainty <= MAX_PROPAGATED_UNCERTAINTY_LOG


def solvent_shift(mol: Chem.Mol, solvent_name: str) -> SolventShift | str:
    """The `log Ss - log Sw` term, or a sentence saying why there is none.

    Returns the REASON as a string rather than None, because every way
    this fails is something the reader can act on -- pick another solvent,
    draw a compound that has been measured, or accept that the two
    literature values disagree too much to average.
    """
    coefficients = solvent_coefficients(solvent_name)
    if coefficients is None:
        return (
            f"No measured Abraham coefficients for {solvent_name!r}. "
            f"{len(_solvent_table())} solvents are available."
        )
    solute = solute_descriptors(mol)
    if solute is None:
        return (
            "This compound has no measured Abraham descriptors. Solubility outside water is a "
            f"lookup over {len(_solute_table())} compounds, not a prediction from structure, so "
            "a molecule nobody has measured gets no answer rather than a guess."
        )
    shift = SolventShift(
        solvent=coefficients,
        solute=solute,
        log_shift=coefficients.shift(solute),
        uncertainty=coefficients.worst_case_uncertainty(solute),
    )
    if not shift.usable:
        return (
            f"{solute.name}'s descriptors come from {solute.measurements} literature sources "
            f"that disagree enough to leave +/-{shift.uncertainty:.1f} log units in "
            f"{coefficients.name}. Too wide to report as a solubility."
        )
    return shift
