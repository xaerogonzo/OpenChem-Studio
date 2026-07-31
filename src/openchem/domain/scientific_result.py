from __future__ import annotations

from dataclasses import dataclass, field

from openchem.domain.common import ScientificResult


@dataclass(frozen=True, kw_only=True)
class AlertResult(ScientificResult):
    """A structural-alert catalog result (PAINS today) — which alert(s)
    matched, not a single scalar, so it doesn't fit `DescriptorValue`.
    `matched` empty means "checked, nothing flagged," distinct from not
    having run at all (`cache_state` covers that).
    """

    alert_id: str  # e.g. "pains", "brenk"
    name: str  # display name, e.g. "PAINS"
    molecule_uuid: str
    matched: list[str] = field(default_factory=list)
    # Default matches PAINS, this field's only caller before Phase 19 --
    # additive, backward-compatible. Lets PropertyPanel route an alert to
    # the right section via `alert.category` instead of a hardcoded
    # string (BRENK's toxicity-relevant alerts belong under "admet", not
    # "medicinal_chemistry").
    category: str = "medicinal_chemistry"


@dataclass(frozen=True, kw_only=True)
class PerAtomDataset(ScientificResult):
    """A per-atom scientific value (partial charge, LogP contribution,
    later an NMR shift) — one value per atom index, not a single scalar,
    so it doesn't fit `DescriptorValue`. Consumed by Phase 11's
    visualization layers, which extract a `VisualizationLayer` from this
    generically rather than knowing what property it came from.
    """

    property_id: str  # e.g. "gasteiger_charge", "crippen_logp_contrib"
    name: str  # display name, e.g. "Partial Charge (Gasteiger)"
    units: str
    method: str  # e.g. "rdkit"
    molecule_uuid: str
    values: dict[int, float] = field(default_factory=dict)  # atom index -> value


@dataclass(frozen=True, kw_only=True)
class SpectrumResult(ScientificResult):
    """A spectroscopic prediction result — NMR today (`spectrum_type` in
    `{"nmr_1h", "nmr_13c", ...}`), room for `"ir"`/`"ms"`/`"uv"`/`"raman"`
    later without a rename. Per-nucleus data lives in `values` (atom index
    -> predicted value); `elements` (atom index -> element symbol) is
    separate since not every atom in a molecule necessarily gets a peak
    (e.g. NMR only reports for certain nuclei).
    """

    spectrum_type: str
    name: str
    units: str
    method: str
    molecule_uuid: str
    values: dict[int, float] = field(default_factory=dict)
    elements: dict[int, str] = field(default_factory=dict)


@dataclass(frozen=True, kw_only=True)
class NMRSpectrumResult(SpectrumResult):
    """NMR-specific spectrum data (Phase 22). `ranges` only makes sense
    for NMR (the empirical SMARTS estimator's typical-range output, atom
    index -> (low, high) ppm) — kept off the shared `SpectrumResult` base
    so a future IR/MS/UV producer doesn't inherit an always-None field
    with no real use. Both the ORCA ab initio path (raw + TMS-calibrated)
    and the empirical estimator construct this; the ORCA path simply
    never populates `ranges`. `couplings` (atom-index-pair -> Hz) is
    populated only by the "nmr_coupling" calc_type's real ab initio
    spin-spin coupling data.
    """

    ranges: dict[int, tuple[float, float]] | None = None
    couplings: dict[tuple[int, int], float] | None = None


@dataclass(frozen=True, kw_only=True)
class StructureEntry:
    """One generated structure inside a `StructureSetResult`.

    A dataclass rather than a bare tuple, and carrying `score`/`energy`
    from the start because two consumers need them on day one: conformers
    have energies, and resonance forms can carry a relative weight. Same
    call Phase 22 made when it replaced a raw tuple with `CrossPeak`.

    Not a `ScientificResult` itself -- it has no independent provenance or
    cache state, existing only as an entry in a set.
    """

    molblock: str
    label: str = ""
    score: float | None = None
    energy: float | None = None
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True, kw_only=True)
class TrajectoryResult(ScientificResult):
    """Frames of a structure evolving over time (Phase 30).

    Not "a list of conformers": molecular dynamics, normal-mode
    animations, reaction paths, NEB images and docking pose animations all
    share this shape, and docking poses are already representable from
    today's `DockingResultModel` -- so this has a consumer beyond the one
    that introduced it.

    Deliberately no `cell` field: nothing here models periodic systems and
    the MD is explicitly vacuum, so it would be an always-None field with
    no consumer -- the same speculative scaffolding this project has
    declined elsewhere.
    """

    trajectory_id: str
    name: str
    method: str
    molecule_uuid: str
    frames: list[str] = field(default_factory=list)  # molblocks, in time order
    times: list[float] = field(default_factory=list)  # fs
    energies: list[float] = field(default_factory=list)  # kcal/mol
    temperature: float | None = None  # K, initial
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True, kw_only=True)
class StructureSetResult(ScientificResult):
    """A set of generated structures (Phase 27).

    Four consumers from the start: stereoisomer enumeration, tautomer
    enumeration, resonance forms, and Markush library enumeration -- plus
    the conformer grid.

    `total_available` is separate from `len(entries)` on purpose. A Markush
    library can hold 10^8 members while only the first thousand are
    generated; a UI that showed only the generated count would badly
    misrepresent the structure's real scope. `None` means "all of them are
    here".
    """

    set_id: str
    name: str
    method: str
    molecule_uuid: str
    entries: list[StructureEntry] = field(default_factory=list)
    total_available: int | None = None
    truncated: bool = False


@dataclass(frozen=True, kw_only=True)
class PhCurveResult(ScientificResult):
    """A property sampled across a pH range (Phase 25a).

    One shape, four real consumers: pKa microspecies distribution, logD vs
    pH, the isoelectric-point charge curve, and H-bond donor/acceptor
    counts vs pH -- so this is a shared shape from day one rather than a
    generalization built ahead of need.

    `series` is a mapping of series name -> one value per entry in
    `ph_values`, which is what lets a single result carry several curves
    on one set of axes (a pKa distribution has one curve per microspecies;
    an isoelectric-point result has exactly one). Every list in `series`
    must be the same length as `ph_values` -- the widget zips them.
    """

    curve_id: str  # e.g. "pka_microspecies", "logd_vs_ph"
    name: str  # display name
    method: str
    molecule_uuid: str
    ph_values: list[float] = field(default_factory=list)
    series: dict[str, list[float]] = field(default_factory=dict)
    x_label: str = "pH"
    y_label: str = ""
    # Optional hard axis bounds, for quantities that are physically
    # bounded. Without them the widget pads the observed range by 8% to
    # keep curves off the frame, which is right for an unbounded quantity
    # like logD but produces "-8% to 108%" on a microspecies distribution
    # -- caught by rendering one and looking at it. A calculator that
    # knows its range says so; everything else keeps the padding.
    y_min: float | None = None
    y_max: float | None = None


@dataclass(frozen=True, kw_only=True)
class CrossPeak:
    """One correlated atom pair inside a `CorrelationResult` — a plain
    value object, not its own `ScientificResult` (it has no independent
    provenance/cache_state; it only exists as an entry in a
    CorrelationResult's `cross_peaks` list).
    """

    atom_a: int
    atom_b: int
    coupling_hz: float | None = None  # None for a connectivity-derived
    # pair with no real ab initio spin-spin coupling value (yet).


@dataclass(frozen=True, kw_only=True)
class CorrelationResult(ScientificResult):
    """A 2D NMR correlation result (HSQC/HMBC/COSY, Phase 22) — which atom
    pairs are expected to show a cross peak, derived either from molecular
    connectivity (`method="connectivity"`, always available, no ORCA
    capability needed) or real ab initio spin-spin coupling
    (`method="orca_j_coupling"`, when that calc_type has been run).
    """

    correlation_type: str  # "hsqc" | "hmbc" | "cosy"
    name: str
    method: str  # "connectivity" | "orca_j_coupling"
    molecule_uuid: str
    cross_peaks: list[CrossPeak] = field(default_factory=list)
