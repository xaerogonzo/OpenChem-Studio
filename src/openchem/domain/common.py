from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


#: `Provenance.parameters["scale"]` value by which a producer declares that
#: its per-atom values are CATEGORY IDS, not magnitudes -- which ring system
#: an atom belongs to, which functional group claims it.
#:
#: Carried in provenance rather than as a new field on `PerAtomDataset` or a
#: new result type, because the panels are typed to
#: `PerAtomDataset | SpectrumResult` and a third kind would have to be
#: taught to every one of them.
#:
#: It lives HERE rather than beside its first consumer in `ui/visualization`
#: because it is not a rendering hint: consumers in different layers have to
#: agree on it or they disagree about what the numbers are. The batch table
#: is the second such consumer, and summing category ids into a column total
#: is the same "Overall: 15" trap the Calculator Inspector already had to
#: close.
CATEGORICAL_SCALE = "categorical"


#: `Provenance.parameters["total"]` key, by which a producer declares whether
#: its per-atom values HAVE a molecular total -- and if so, what it is.
#:
#: THE POINT IS THAT NOBODY MAY DERIVE ONE. The Calculator Inspector used to
#: answer "what is this molecule's overall value" with `sum(values)`, which is
#: three different mistakes at once. Measured on aspirin: Crippen LogP
#: contributions summed to 0.1511 against a real LogP of 1.3101 (the hydrogens
#: are implicit and so have no atom to sit on), Gasteiger charges summed to
#: -0.6555 for a neutral molecule, and eccentricity summed to 65, which is not
#: a quantity at all. Four other calculators summed correctly and said only
#: "Overall: 220.7" without naming what it was.
#:
#: A list of numbers does not say whether adding it up means anything. The
#: PRODUCER knows -- so the producer declares, and a consumer that finds no
#: declaration shows no total. Same instinct as `CalculatorDefinition.
#: applies_to`, whose default is likewise the answer that cannot be wrong.
#:
#: DECLARING AND DECLINING ARE BOTH EXPLICIT STATES:
#:
#:     {"declared": True,  "value": 1.3101, "label": "LogP (Crippen)",
#:      "units": "", "basis": HEAVY_ATOMS}
#:     {"declared": False, "reason": "Eccentricity is a per-atom graph
#:      distance; no molecular sum is defined."}
#:
#: An ABSENT key is neither, and `tests/test_declared_totals.py` fails on it
#: naming the calculator -- which is what stops the next per-atom calculator
#: silently reacquiring the bug. Requiring a reason on the `False` form is the
#: same move as the assembly gate's `catches_composition_order: false`: it
#: turns "nobody got round to this" into "somebody decided this".
#:
#: A CATEGORICAL DATASET NEEDS NO `TOTAL`, and that is a recognised existing
#: declaration rather than an exemption that can rot. `CATEGORICAL_SCALE` is
#: already the producer saying "these values are category ids, not
#: magnitudes" -- see its own docstring above, which names the identical
#: "Overall: 15" trap. Requiring a second key to repeat it would put the same
#: statement in two places, which is how two sources of truth start
#: disagreeing. The five categorical datasets (ring systems, locants,
#: functional groups, stereocentres, oxidation states) are therefore
#: untouched, and the audit accepts either declaration.
TOTAL = "total"

#: `Provenance.parameters["atom_basis"]` -- WHICH ATOMS the values are keyed
#: to, so a view knows what to draw them on.
#:
#: DELIBERATELY ORTHOGONAL TO `TOTAL`, and the two must not be collapsed. This
#: says what the values are attached to; it says nothing about whether summing
#: them means anything. A dataset can cover every atom explicitly and still
#: have no meaningful total -- orbital electronegativity is exactly that, being
#: an intensive per-atom property whose sum (134.8 eV for aspirin) is
#: arithmetic rather than chemistry.
ATOM_BASIS = "atom_basis"

#: The closed vocabulary for `ATOM_BASIS`. Closed for the reason `applies_to`
#: is closed: a free string admits `heavy_atoms`/`heavy-atoms`/`heavy atom`,
#: and a typo would route a dataset to no branch at all while looking fine.
HEAVY_ATOMS = "heavy_atoms"  # implicit hydrogens, as drawn in the editor
EXPLICIT_H = "explicit_h"  # every hydrogen carries its own value
PI_SYSTEM = "pi_system"  # only the conjugated atoms (Huckel)

ATOM_BASES = frozenset({HEAVY_ATOMS, EXPLICIT_H, PI_SYSTEM})


def declare_total(
    value: float, label: str, units: str = "", basis: str = HEAVY_ATOMS, **extra: Any
) -> dict[str, Any]:
    """A producer's "yes, and here it is"."""
    return {"declared": True, "value": value, "label": label, "units": units, "basis": basis, **extra}


def decline_total(reason: str) -> dict[str, Any]:
    """A producer's "no, and here is why". The reason is required: it is what
    a later reader sees instead of wondering whether this was an oversight."""
    return {"declared": False, "reason": reason}


def valid_total_declaration(declaration: Any) -> bool:
    """Whether `declaration` is a WELL-FORMED total declaration.

    STRUCTURAL ONLY, and that limit is the design rather than laziness. This
    checks that a value is numeric and a label is non-empty; it does NOT check
    that "A^2" is the right unit for a surface area, because that is a
    chemistry claim and answering it here would rebuild in the domain layer
    the very "the UI decides what the numbers mean" engine this key exists to
    remove. Generic machinery validates the SHAPE of scientific metadata;
    domain tests validate its TRUTH.

    The distinction is tested directly: a producer declaring
    `label="LogP (Crippen)", value=sum(values)` -- a plausible lie -- MUST
    pass here and MUST fail the Crippen chemistry guard. If this function
    catches it, semantics have leaked back into the wrong layer.

    `units` may legitimately be "": LogP, a pi-electron count and the Wiener
    index are all dimensionless. The contract is that units were STATED, not
    that every quantity has a physical dimension.
    """
    if not isinstance(declaration, dict) or "declared" not in declaration:
        return False
    if declaration["declared"] is False:
        return bool(str(declaration.get("reason", "")).strip())
    if declaration["declared"] is not True:
        return False
    value = declaration.get("value")
    # bool is an int subclass, and a True total is a producer bug rather than
    # a zero-magnitude one -- so it is refused rather than read as 1.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    if not str(declaration.get("label", "")).strip():
        return False
    if not isinstance(declaration.get("units", None), str):
        return False
    return declaration.get("basis") in ATOM_BASES


class CacheState(str, Enum):
    """Lifecycle of an asynchronously computed value (a descriptor, a batch
    of conformers, or any future long-running provider result).

    Modeled explicitly, rather than just holding a value, so slow providers
    (docking, ORCA, AI, conformer search) share one async contract instead
    of each inventing its own.
    """

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class Provenance:
    """What produced a scientific result, with what parameters, when —
    first used on Phase 6+ domain models (starting with `DockingResultModel`)
    so every generated result can answer "what produced this," later
    retrofitted (Phase 9.5) onto `ConformerModel`/`DescriptorValue` as an
    additive optional field alongside their own pre-existing `.method`/
    `.timestamp`/`.provider` fields, not a replacement for them.
    """

    created_by: str  # plugin_id, or "core"
    method: str  # e.g. "vina-python", "vina-executable"
    parameters: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "created_by": self.created_by,
            "method": self.method,
            "parameters": self.parameters,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Provenance:
        return cls(
            created_by=data["created_by"],
            method=data["method"],
            parameters=dict(data.get("parameters", {})),
            timestamp=data.get("timestamp", 0.0),
        )


@dataclass(frozen=True, kw_only=True)
class ScientificResult:
    """Shared shape for a computed scientific output that isn't a bare
    scalar. `DescriptorValue` (one number per descriptor) predates this and
    keeps its own directly-defined `provenance`/`timestamp`/`cache_state`
    fields rather than being retrofitted to compose this — no behavior
    change for existing callers, it's simply the same shape by convention.
    New result kinds that don't fit a single scalar (per-atom datasets,
    categorical alerts, spectra — see `PerAtomDataset`, `AlertResult`,
    `SpectrumResult`) build on this instead of each inventing their own
    provenance/timestamp/status shape independently.

    `kw_only=True` so subclasses can add their own required fields (a
    dataclass can't otherwise mix required subclass fields after
    already-defaulted base fields — every field here has a default so
    plain positional inheritance would force subclasses to default
    everything too, including fields that should stay required).
    """

    provenance: Provenance | None = None
    timestamp: float = field(default_factory=time.time)
    cache_state: CacheState = CacheState.COMPLETED
    # Same convention DescriptorValue's own `error` field already
    # established -- a human-readable reason when `cache_state` is
    # FAILED (e.g. "pkasolver not installed"), added here (Phase 18)
    # rather than on individual subclasses so every result kind can
    # report a failure reason uniformly.
    error: str | None = None
