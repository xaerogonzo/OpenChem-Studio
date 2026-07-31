from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from openchem.domain.common import ScientificResult
from openchem.domain.scientific_result import NMRSpectrumResult, PerAtomDataset

# Diverging: negative -> red, zero -> near-white, positive -> blue. Matches
# the ask this exists for ("show which atoms increase LogP vs decrease
# it") -- sign carries real chemical meaning for contribution-style
# per-atom data (LogP contributions, partial charges).
_DIVERGING_PALETTE: list[tuple[float, str]] = [(0.0, "#d32f2f"), (0.5, "#f5f5f5"), (1.0, "#1976d2")]
# Sequential: low -> light, high -> dark. Nothing in this app produces a
# magnitude-only (all-same-sign) per-atom property yet, but the branch
# stays ready for one (e.g. a future electrostatic-potential-magnitude
# layer) without a data-shape change.
_SEQUENTIAL_PALETTE: list[tuple[float, str]] = [(0.0, "#fff3e0"), (1.0, "#e65100")]


def _interpolate_hex(color_a: str, color_b: str, fraction: float) -> str:
    a = tuple(int(color_a[i : i + 2], 16) for i in (1, 3, 5))
    b = tuple(int(color_b[i : i + 2], 16) for i in (1, 3, 5))
    mixed = tuple(round(a[i] + (b[i] - a[i]) * fraction) for i in range(3))
    return "#{:02x}{:02x}{:02x}".format(*mixed)


@dataclass(frozen=True, kw_only=True)
class ColorScale:
    """Maps a numeric value to a hex color via linear interpolation between
    ordered `(fraction, hex)` control points, `fraction` measured over
    `domain_min`..`domain_max`. Carried on the layer, not hardcoded in any
    viewer widget, so a future property isn't stuck reusing an earlier
    one's palette choice.
    """

    palette: list[tuple[float, str]]
    domain_min: float
    domain_max: float

    def color_for(self, value: float) -> str:
        if self.domain_max == self.domain_min:
            fraction = 0.5
        else:
            fraction = (value - self.domain_min) / (self.domain_max - self.domain_min)
        fraction = max(0.0, min(1.0, fraction))
        for (f0, c0), (f1, c1) in zip(self.palette, self.palette[1:]):
            if f0 <= fraction <= f1:
                local = 0.0 if f1 == f0 else (fraction - f0) / (f1 - f0)
                return _interpolate_hex(c0, c1, local)
        return self.palette[-1][1]


@dataclass(frozen=True, kw_only=True)
class VisualizationLayer:
    """Renderer-independent per-ATOM visualization data.
    `ViewerBackend.apply_visualization(s)` consumes this without knowing
    which scientific property (or which provider — descriptor, docking, a
    future quantum result) produced it.

    Kept as the atom-target layer rather than renamed to `AtomColorLayer`
    when residue targeting arrived (Phase 23): it has many existing
    callers and tests, and `ResidueColorLayer` below is a sibling rather
    than a subtype anyway — the two carry genuinely different key spaces
    (atom index vs residue identifier) with no shared field worth
    hoisting into a base beyond `name`, which does not justify the churn.
    """

    name: str
    atom_colors: dict[int, str]  # atom index -> resolved hex color
    color_scale: ColorScale | None = None  # for a legend; optional
    atom_labels: dict[int, str] | None = None  # atom index -> formatted value text (Phase 18)


@dataclass(frozen=True, kw_only=True)
class ResidueColorLayer:
    """Renderer-independent per-RESIDUE visualization data (Phase 23) —
    colours whole residues of a macromolecule rather than individual atoms.

    Keyed by the residue identifier `pose_analysis` already emits for every
    docking contact: name concatenated with number, e.g. `"TYR652"` (see
    `analyze_pose`'s `receptor_residue`). That existing, real data is what
    justifies this layer type — it is not a speculative generalization;
    `build_interaction_layers` below turns it into exactly these.
    """

    name: str
    residue_colors: dict[str, str]  # "TYR652" -> resolved hex color
    color_scale: ColorScale | None = None
    residue_labels: dict[str, str] | None = None


# Surface representations 3Dmol's vendored bundle actually supports --
# confirmed live that `$3Dmol.SurfaceType` is {VDW:1, MS:2, SAS:3, SES:4}
# (SES is real here even though Marvin doesn't offer it).
#
# `SurfaceLayer.representation` is deliberately a plain `str` rather than
# an Enum constrained to these four: electrostatic-potential, electron-
# density, molecular-orbital and spin-density surfaces are all real future
# additions that would come from volumetric data rather than a 3Dmol
# SurfaceType, and a closed enum would have to be widened for each. Same
# precedent as `CalculatorDefinition.category` (Phase 18), a plain string
# so a new value needs no code change.
SURFACE_REPRESENTATIONS = ["vdw", "sas", "ms", "ses"]
SURFACE_REPRESENTATION_LABELS = {
    "vdw": "van der Waals",
    "sas": "Solvent Accessible",
    "ms": "Molecular Surface",
    "ses": "Solvent Excluded",
}


@dataclass(frozen=True, kw_only=True)
class SurfaceLayer:
    """Renderer-independent molecular-SURFACE visualization data.

    A sibling of `VisualizationLayer`/`ResidueColorLayer` rather than a
    variant of either: a surface's identity is its representation and
    opacity, which neither of the others has, and its optional per-atom
    colours are a way of *painting* it rather than what it is. The sibling
    pattern is the one Phase 23 established for residues.

    `atom_colors` is optional -- a plain uncoloured surface (just shape) is
    a legitimate and common use. When present, surface vertices take the
    colour of the nearest atom, which is how a per-atom property such as
    partial charge gets mapped onto the surface the way Marvin shows it.
    """

    name: str
    representation: str = "vdw"
    opacity: float = 0.75
    atom_colors: dict[int, str] | None = None
    color_scale: ColorScale | None = None


# Any layer a `ViewerBackend` may be handed. A backend is expected to
# render the target kinds it can and ignore the rest -- 3Dmol.js has no
# residue concept for a small-molecule conformer, and a macromolecule
# viewer has no per-atom scientific data feeding it, so "ignore what you
# can't render" is the honest contract rather than requiring every backend
# to implement every target.
AnyVisualizationLayer = VisualizationLayer | ResidueColorLayer | SurfaceLayer


def build_surface_layer(
    dataset: PerAtomDataset, representation: str = "vdw", opacity: float = 0.75
) -> SurfaceLayer:
    """Paints a per-atom property onto a molecular surface, reusing
    `build_atom_color_layer`'s colour choices so the surface and the
    sticks underneath agree rather than each picking a palette."""
    atom_layer = build_atom_color_layer(dataset)
    return SurfaceLayer(
        name=dataset.name,
        representation=representation,
        opacity=opacity,
        atom_colors=atom_layer.atom_colors or None,
        color_scale=atom_layer.color_scale,
    )


_DEFAULT_LABEL_DECIMALS = 2


def _label_decimals(dataset: PerAtomDataset) -> int:
    """Display precision, carried by the DATA rather than passed in.

    The `decimal_places` option lives on the calculator's request, which
    the Calculator Inspector never sees -- it only receives the finished
    result. Rather than thread a parameter through every view, calculators
    record the requested precision in `Provenance.parameters`, which is
    already the free-form place this codebase puts exactly this kind of
    presentation metadata.
    """
    provenance = dataset.provenance
    if provenance is None:
        return _DEFAULT_LABEL_DECIMALS
    try:
        return max(0, min(8, int(provenance.parameters.get("decimal_places", _DEFAULT_LABEL_DECIMALS))))
    except (TypeError, ValueError):
        return _DEFAULT_LABEL_DECIMALS


def build_atom_color_layer(dataset: PerAtomDataset, include_labels: bool = False) -> VisualizationLayer:
    """Extracts a `VisualizationLayer` from a `PerAtomDataset` — diverging
    red/blue for signed data (contribution-style values, where the sign
    itself is meaningful), sequential for magnitude-only data.
    `include_labels=True` (Calculator Inspector, Phase 18) also formats
    each value into `atom_labels`; the default `False` keeps the existing
    3D-viewer "Color by" dropdown (a quick-glance tool) uncluttered."""
    values = dataset.values
    if not values:
        return VisualizationLayer(name=dataset.name, atom_colors={})

    has_negative = any(v < 0 for v in values.values())
    has_positive = any(v > 0 for v in values.values())
    signed = has_negative and has_positive
    if signed:
        magnitude = max(abs(v) for v in values.values()) or 1.0
        scale = ColorScale(palette=_DIVERGING_PALETTE, domain_min=-magnitude, domain_max=magnitude)
    else:
        scale = ColorScale(
            palette=_SEQUENTIAL_PALETTE, domain_min=min(values.values()), domain_max=max(values.values())
        )

    atom_colors = {idx: scale.color_for(v) for idx, v in values.items()}
    atom_labels = None
    if include_labels:
        places = _label_decimals(dataset)
        # An explicit "+" belongs on contribution-style data, where the
        # sign carries the meaning -- but reads as noise on a magnitude,
        # since a surface area or an eccentricity has no negative branch
        # to distinguish it from. Same condition that picks the palette.
        sign = "+" if signed else ""
        atom_labels = {idx: f"{v:{sign}.{places}f}" for idx, v in values.items()}
    return VisualizationLayer(name=dataset.name, atom_colors=atom_colors, color_scale=scale, atom_labels=atom_labels)


# Phase 18: ScientificResult -> VisualizationAdapter -> VisualizationLayer.
# NMRSpectrumResult (Phase 22) reuses build_atom_color_layer as-is -- it
# only touches .values/.name, which SpectrumResult already has in the
# same shape, no PerAtomDataset-specific field needed.
_VISUALIZATION_ADAPTERS: dict[type, Callable[..., VisualizationLayer]] = {
    PerAtomDataset: build_atom_color_layer,
    NMRSpectrumResult: build_atom_color_layer,
}


def build_visualization_layer(result: ScientificResult, include_labels: bool = False) -> VisualizationLayer | None:
    """Dispatches to the registered adapter for `type(result)`, or `None`
    if no adapter is registered for that result kind."""
    adapter = _VISUALIZATION_ADAPTERS.get(type(result))
    return adapter(result, include_labels=include_labels) if adapter else None


# Binding-site interaction colours. Distinct hues rather than a scale:
# H-bond and clash are categorically different findings, not two points on
# one continuum, so a diverging/sequential ColorScale would misrepresent
# them (and both layers carry `color_scale=None` for the same reason).
_HBOND_COLOR = "#1976d2"  # blue -- favourable polar contact
_CLASH_COLOR = "#d32f2f"  # red -- unfavourable steric overlap


def build_interaction_layers(pose_metadata: dict) -> list[ResidueColorLayer]:
    """Turns one docked pose's interaction analysis into residue layers --
    which receptor residues hydrogen-bond with the ligand, and which clash.

    Consumes `DockingPoseModel.metadata` exactly as `analyze_pose`
    (`chem/pose_analysis.py`) writes it: `{"hbonds": [...], "clashes":
    [...]}`, each entry carrying `receptor_residue` like `"TYR652"`. This
    is the real, already-computed data that residue targeting exists for.

    Returns only non-empty layers, and clashes last so that a residue
    which both H-bonds AND clashes ends up flagged with the problem rather
    than the favourable contact -- a backend compositing layers in order
    lets the later one win, and a steric clash is the finding a user needs
    to see.
    """
    layers: list[ResidueColorLayer] = []
    for key, name, color in (
        ("hbonds", "H-bonds", _HBOND_COLOR),
        ("clashes", "Steric clashes", _CLASH_COLOR),
    ):
        residues = {
            contact["receptor_residue"]
            for contact in pose_metadata.get(key, [])
            if contact.get("receptor_residue")
        }
        if not residues:
            continue
        layers.append(
            ResidueColorLayer(
                name=f"{name} ({len(residues)} residue{'s' if len(residues) != 1 else ''})",
                residue_colors={residue: color for residue in residues},
            )
        )
    return layers
