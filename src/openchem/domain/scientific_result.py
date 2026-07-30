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
