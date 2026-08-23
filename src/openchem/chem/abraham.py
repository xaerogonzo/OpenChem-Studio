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
               solvents. The paper considers 293 in total and PREDICTS
               coefficients for all of them, saying of those "not as
               gospel"; the 202 predicted-only ones are not shipped, for
               two measured reasons in `_PREDICTED_COEFFICIENTS_NOTE`.
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

#: The paper's own out-of-bag (held-out) RMSE for the random forest that
#: PREDICTED coefficients for the solvents it did not measure -- its
#: Table 4. Kept as data because it is what decides that those solvents
#: cannot ship; see `_PREDICTED_COEFFICIENTS_NOTE`.
PREDICTED_COEFFICIENT_OOB_RMSE = {
    "e": 0.181, "s": 0.326, "a": 0.477, "b": 0.471, "v": 0.228,
}

_PREDICTED_COEFFICIENTS_NOTE = """\
Why the 202 predicted-only solvents are not shipped.

**ACETIC ACID IS NO LONGER ONE OF THEM.** It was the case that motivated
this note -- asked for by name, refused, and the numbers below are its
measurements. A MEASURED set has since been read from a second source
(Stovall 2015; see `solvent_sources` in the shipped table), so it ships
with an intercept and standard errors of its own. The reasoning below is
unchanged and still governs the other 117: what changed was the
literature available, not the standard applied to it.

**IT FAILS THE BOUND THIS MODULE ALREADY APPLIES**, so this is the
existing rule applied consistently rather than a fresh opinion.
Propagating the paper's own Table 4 out-of-bag RMSE through the same
`sum(|error| * descriptor)` used for measured-descriptor disagreement:

    aspirin 1.57   caffeine 2.04   ibuprofen 1.34   paracetamol 1.76

against a ceiling of 1.0 log. Caffeine's 2.04 is a factor of 110. Only
benzene passes, at 0.51, and a solvent that works for benzene and no drug
is not a solvent option. Two of the five coefficients are poor at the
source: OOB R-squared is 0.308 for `e` and 0.474 for `b`, against
in-sample values of 0.885 and 0.903 -- the classic overfit gap, which the
paper itself flags.

**AND THE PREDICTED TABLE IS THE WRONG PARAMETERISATION.** It gives only
the `c = 0` refit (`e0 s0 a0 b0 v0`), which is the paper's equation 3 for
log P and exists to make solvents comparable with each other. The
solubility equation is its equation 2 and needs the intercept: ethanol's
measured `c` is +0.222, and the predicted table has no column for it.
Using one form where the other belongs is precisely the units-and-meaning
confusion the solubility module exists to prevent.

Either reason alone is sufficient. Together they make this a refusal with
a measurement behind it, which is the only kind this project ships.\
"""


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
def _predicted_only() -> frozenset[str]:
    """Solvents the source PREDICTS and does not measure, by name only.

    Deliberately names with NO coefficients attached, so nothing
    downstream can quietly start using them. See
    `_PREDICTED_COEFFICIENTS_NOTE` for the two measurements that decided
    it. 118 of the 202 predicted-only solvents appear in the article's own
    table; the rest are in a supplementary spreadsheet and are not needed
    here, since the point is to explain a refusal rather than to enumerate.
    """
    payload = json.loads((_DATA / "abraham_solvents.json").read_text(encoding="utf-8"))
    return frozenset(payload.get("predicted_only", ()))


@lru_cache(maxsize=1)
def _solute_table() -> dict[str, dict]:
    payload = json.loads((_DATA / "abraham_solutes.json").read_text(encoding="utf-8"))
    return payload["solutes"]


def predicted_only_reason(solvent_name: str) -> str:
    """Why this solvent is refused, if the source PREDICTED it; else "".

    One function, two callers -- `resolve_solvent` refuses first and is
    the one a user actually reaches, `solvent_shift` refuses for callers
    that bypass it. Writing the sentence twice is how the two drift into
    disagreeing about the same refusal.
    """
    name = solvent_name.strip().lower()
    if name not in _predicted_only():
        return ""
    return (
        f"{name} has no MEASURED Abraham coefficients. The source predicts them, and its own "
        "held-out error propagates to 1.3-2.0 log units on ordinary drugs -- a factor of 20 to "
        "100 -- so they are not shipped. The predicted table also omits the intercept the "
        "solubility equation needs. Its authors say the predicted values should not be taken "
        '"as gospel".'
    )


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
        # A solvent the source PREDICTED gets the specific reason, because
        # "not in the table" reads as an oversight when the truth is that
        # the numbers exist and were measured to be too poor to use.
        specific = predicted_only_reason(solvent_name)
        if specific:
            return specific
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
