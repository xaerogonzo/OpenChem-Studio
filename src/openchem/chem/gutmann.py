"""Gutmann donor and acceptor numbers, read from the classical tables.

WHY THIS WAS DEFERRED, AND WHAT CHANGED. CLAUDE.md records the
assessment: the accessible source was
[source:gutmann_frontiers2022], which tabulates ionic liquids and deep
eutectic solvents rather than the classical molecular scale, and which
"reports its own acceptor-number model failing outright". That paper was
correctly rejected. What was missing was the original tables, and they
are here now -- Gutmann's own 1976 review ([source:gutmann1976]).

**TWO SCALES, AND CONFLATING THEM IS THE FAILURE TO AVOID.** They are
not two readings of one quantity:

    DN  donor number, kcal/mol, DILUTE in 1,2-dichloroethane
        DN = -dH for the donor's adduct with SbCl5
    AN  acceptor number, DIMENSIONLESS, from the 31P shift of Et3P=O
        on a two-point scale: hexane = 0, SbCl5/DCE = 100

A solvent can be high in both (water: DN 18.0, AN 54.8) or high in one
and nearly zero in the other (HMPA: DN 38.8, AN 10.6). Asking for "the
Gutmann number" of a solvent is not a well-formed question, so there is
no function here that answers it.

**AND BULK DONICITY IS A THIRD THING.** The paper's footnote a marks
values measured "in the associated liquid" rather than dilute, and six
amines plus hydrazine are reported ONLY that way. Water is reported both
ways and is the row that shows why they must not be merged: 18.0 dilute
against 33.0 bulk, a 15 kcal/mol gap. `donor_number` returns the dilute
value and `bulk_donicity` the other; neither silently substitutes for the
other.

RELATED TO THE SHIPPED DRAGO E/C TABLE, AND NOT A SECOND READING OF IT.
DN is defined as -dH against SbCl5, which `chem/lewis.py`'s parameters
can also predict, so the two scales are connected in principle. They are
NOT two implementations of one number -- different parameterisations,
different reference acids, different experimental bases -- so nothing
here is validated against that table, and a cross-scale comparison would
let a real transcription error hide behind a legitimate difference. The
acceptance oracle is the published values themselves.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_DATA = Path(__file__).resolve().parent / "data"


@dataclass(frozen=True)
class SolventDonicity:
    """What the 1976 tables record for one solvent.

    Every field is optional because the tables are not rectangular: most
    solvents carry a DN and no AN, some the reverse, seven carry only a
    bulk donicity, and 1,2-dichloroethane deliberately carries no DN at
    all because it is the medium the measurement is made in.
    """

    name: str
    donor_number: float | None = None
    bulk_donicity: float | None = None
    acceptor_number: float | None = None
    #: The 31P shift of Et3P=O the acceptor number is derived from, ppm.
    p31_shift: float | None = None
    #: True where the paper writes "~" rather than a value.
    approximate: bool = False
    #: The paper's own remark, where it has one.
    note: str = ""


@lru_cache(maxsize=1)
def _payload() -> dict:
    return json.loads((_DATA / "gutmann_solvents.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _table() -> dict[str, SolventDonicity]:
    payload = _payload()
    donors = payload["donor_numbers"]
    acceptors = payload["acceptor_numbers"]
    out: dict[str, SolventDonicity] = {}
    for name in sorted(set(donors) | set(acceptors)):
        donor = donors.get(name, {})
        acceptor = acceptors.get(name, {})
        out[name] = SolventDonicity(
            name=name,
            donor_number=donor.get("dn"),
            bulk_donicity=donor.get("bulk_dn"),
            acceptor_number=acceptor.get("an"),
            p31_shift=acceptor.get("p31_shift"),
            approximate=bool(donor.get("approximate")),
            note=donor.get("note") or acceptor.get("note") or "",
        )
    return out


def solvent_names() -> list[str]:
    """Every solvent either table records, in the paper's own naming."""
    return sorted(_table())


def donicity(solvent_name: str) -> SolventDonicity | None:
    """Both scales for one solvent, or None if it is in neither table.

    Returns the WHOLE record rather than a number, deliberately: a caller
    that wanted "the Gutmann number" has asked a question with two
    answers, and handing back one of them would pick for them.
    """
    return _table().get(solvent_name.strip().lower())


def scale_anchors() -> dict[str, float]:
    """The two points that define the acceptor scale.

    Exposed because AN is meaningless without them -- it is not a
    measured quantity in its own units but a position between hexane and
    SbCl5 -- and because a transcription slip in either would silently
    rescale the whole column.
    """
    acceptors = _payload()["acceptor_numbers"]
    return {
        "hexane": acceptors["hexane"]["an"],
        "antimony pentachloride in dichloroethane": acceptors[
            "antimony pentachloride in dichloroethane"
        ]["an"],
    }
