from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from openchem.chem.scalar_field import ScalarField, symmetric_range, to_dx
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

#: Qualitative: for per-atom data whose values are CATEGORY IDs, not
#: magnitudes -- which ring system an atom belongs to, later which
#: functional group claims it. Interpolating between categories is
#: meaningless, so these are picked to be distinguishable from each other
#: rather than to form a ramp, and are indexed rather than blended.
#:
#: Chosen for distinguishability under the common colour-vision
#: deficiencies (Okabe-Ito, which is designed for exactly that) rather than
#: by eye. Grey is deliberately absent: it reads as "no data" against the
#: uncoloured atoms these sit beside.
_QUALITATIVE_PALETTE: list[str] = [
    "#0072b2",  # blue
    "#e69f00",  # orange
    "#009e73",  # green
    "#cc79a7",  # reddish purple
    "#56b4e9",  # sky blue
    "#d55e00",  # vermillion
    "#f0e442",  # yellow
]

#: `Provenance.parameters["scale"]` value that routes a `PerAtomDataset`
#: down the categorical path.
#:
#: Carried in provenance rather than as a new field on `PerAtomDataset` or
#: a new result type, because the panels are typed to
#: `PerAtomDataset | SpectrumResult` and a third kind would have to be
#: taught to every one of them. `_label_decimals` below sets the precedent
#: in as many words: provenance parameters are "already the free-form place
#: this codebase puts exactly this kind of presentation metadata".
CATEGORICAL_SCALE = "categorical"


def _hex_to_rgb_fraction(color: str) -> tuple[float, float, float]:
    return tuple(int(color[i : i + 2], 16) / 255.0 for i in (1, 3, 5))


#: The diverging palette as RGB fractions, which is what RDKit's contour
#: renderer takes. DERIVED from `_DIVERGING_PALETTE` rather than written
#: out again, so the 2D heat map, the 2D atom colours and the 3D surface
#: cannot drift into three nearly-identical reds.
DIVERGING_COLOUR_MAP: list[tuple[float, float, float]] = [
    _hex_to_rgb_fraction(color) for _stop, color in _DIVERGING_PALETTE
]


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

    `scalar_field_dx` is the OTHER way to paint one, and it is not a
    variation on `atom_colors`: nearest-atom colouring is a step function
    over the atoms, while a scalar field is defined everywhere in space
    and so varies BETWEEN them -- which is what an electrostatic potential
    map actually is. Carried as OpenDX text because that is what the
    viewer parses; `chem/scalar_field.py` produces it. When both are set
    the field wins, since it is the more specific request.
    """

    name: str
    representation: str = "vdw"
    opacity: float = 0.75
    atom_colors: dict[int, str] | None = None
    color_scale: ColorScale | None = None
    scalar_field_dx: str | None = None
    scalar_field_range: tuple[float, float] | None = None


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


def build_scalar_field_surface_layer(
    field: ScalarField,
    representation: str = "vdw",
    opacity: float = 0.75,
    percentile: float = 95.0,
) -> SurfaceLayer:
    """A surface coloured by a continuous field rather than by its atoms.

    The colour range comes from `symmetric_range`, not from the field's
    raw extremes: those sit at the grid points nearest the nuclei, which
    are both the largest values and the least meaningful ones, and
    scaling to them washes the whole surface out to white.

    `_DIVERGING_PALETTE` runs red at the low end to blue at the high one,
    which is the same direction as 3Dmol's `Gradient.RWB` -- so the legend
    this layer carries describes what the surface actually shows rather
    than being a second, independently-chosen scale beside it.
    """
    low, high = symmetric_range(field, percentile=percentile)
    return SurfaceLayer(
        name=field.name,
        representation=representation,
        opacity=opacity,
        color_scale=ColorScale(
            palette=_DIVERGING_PALETTE, domain_min=low, domain_max=high
        ),
        scalar_field_dx=to_dx(field),
        scalar_field_range=(low, high),
    )


_DEFAULT_LABEL_DECIMALS = 2


def is_categorical(result) -> bool:
    """Whether a result's per-atom values are category ids, not magnitudes.

    Public because consumers outside this module have to know: summing
    category ids produces a number ("Overall: 15" for a molecule's ring
    systems) that looks like a measurement and means nothing, which is the
    same misleading-total trap a summed spectrum would be.
    """
    return _provenance_parameter(result, "scale") == CATEGORICAL_SCALE


def summary_note(result) -> str:
    """A producer-supplied line for a result that has no meaningful total.

    Exists for the empty case. A categorical result with no values renders
    as an uncoloured molecule and a blank summary, which reads as broken
    rather than as "nothing matched" -- the same class of bug as the
    spectrum that showed "Overall: n/a". A producer that can explain its own
    emptiness puts the sentence here.
    """
    return str(_provenance_parameter(result, "summary", "") or "")


def _provenance_parameter(dataset: PerAtomDataset, key: str, default=None):
    """One provenance parameter, or `default`.

    Tolerant on purpose: most datasets carry no provenance at all, and a
    missing presentation hint must fall back to the ordinary numeric path
    rather than raise inside a render.
    """
    provenance = getattr(dataset, "provenance", None)
    if provenance is None:
        return default
    try:
        return provenance.parameters.get(key, default)
    except AttributeError:
        return default


def _build_categorical_layer(
    dataset: PerAtomDataset, include_labels: bool = False
) -> VisualizationLayer:
    """Colours atoms by CATEGORY MEMBERSHIP rather than by magnitude.

    The values are category ids -- ring system 1, ring system 2 -- so they
    are indexed into a qualitative palette, never interpolated. Two ring
    systems being "1 apart" says nothing about how similar they are, and a
    sequential ramp would quietly imply that it did.

    `color_scale` is deliberately left None. A `ColorScale` exists to draw a
    continuous legend, and there is no continuum here to draw; a view that
    wants a key should read the category names out of provenance.

    The palette CYCLES rather than clamping. A molecule with more ring
    systems than palette entries is rare but real (and cycling repeats a
    colour, which is a legible failure), whereas clamping would paint every
    system past the seventh the same colour with no hint that it had.
    """
    categories = {int(round(v)) for v in dataset.values.values()}
    ordered = sorted(categories)

    # A FIXED colour per category, when the producer supplies one. This is
    # not a nicety: positional assignment gives the first category present
    # the first palette entry, so a molecule with only S centres would
    # paint them the exact blue that R gets in a molecule that has both.
    # For ring systems, whose ids are arbitrary and local to one molecule,
    # positional is right; for a category with meaning that outlives the
    # molecule, it is a correctness bug.
    fixed = _provenance_parameter(dataset, "category_colors") or {}
    colour_for_category = {}
    for position, category in enumerate(ordered):
        override = fixed.get(category, fixed.get(str(category)))
        colour_for_category[category] = override or _QUALITATIVE_PALETTE[
            position % len(_QUALITATIVE_PALETTE)
        ]
    atom_colors = {
        idx: colour_for_category[int(round(v))] for idx, v in dataset.values.items()
    }

    atom_labels = None
    if include_labels:
        # Per-atom notes beat the raw category id: "4a" or "bridgehead" is
        # what the atom actually is, where "1.00" is an implementation
        # detail of how it got its colour.
        notes = _provenance_parameter(dataset, "atom_notes") or {}
        names = _provenance_parameter(dataset, "category_labels") or {}
        atom_labels = {}
        for idx, value in dataset.values.items():
            category = int(round(value))
            note = notes.get(idx) or notes.get(str(idx))
            atom_labels[idx] = str(
                note if note else names.get(category, names.get(str(category), category))
            )

    return VisualizationLayer(
        name=dataset.name,
        atom_colors=atom_colors,
        color_scale=None,
        atom_labels=atom_labels,
    )


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

    if _provenance_parameter(dataset, "scale") == CATEGORICAL_SCALE:
        return _build_categorical_layer(dataset, include_labels=include_labels)

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
_HYDROPHOBIC_COLOR = "#f9a825"  # amber -- apolar burial
_SALT_BRIDGE_COLOR = "#7b1fa2"  # purple -- charge pairing
_PI_COLOR = "#00897b"  # teal -- aromatic (stacking and cation-pi)
_METAL_COLOR = "#5d4037"  # brown -- metal coordination


def build_interaction_layers(pose_metadata: dict) -> list[ResidueColorLayer]:
    """Turns one docked pose's interaction analysis into residue layers --
    which receptor residues hydrogen-bond with the ligand, and which clash.

    Consumes `DockingPoseModel.metadata` exactly as `analyze_pose`
    (`chem/pose_analysis.py`) writes it -- one list per interaction type,
    each entry carrying `receptor_residue` like `"TYR652"`. This is the
    real, already-computed data that residue targeting exists for.

    ORDER IS THE WHOLE DESIGN HERE. A backend compositing layers in order
    lets the later one win, so the list runs from least to most urgent and
    CLASHES ARE LAST: a residue that both hydrogen-bonds and clashes ends
    up flagged with the problem, which is the finding a user needs. The
    favourable types are ordered by how specific they are -- hydrophobic
    burial is the most common and least informative, so it sits first and
    is overwritten by anything more particular.

    Unknown keys are ignored rather than coloured, so a future interaction
    type added to `analyze_pose` shows up here only once it has been given
    a colour and a place in this order deliberately.
    """
    layers: list[ResidueColorLayer] = []
    for key, name, color in (
        ("hydrophobic", "Hydrophobic contacts", _HYDROPHOBIC_COLOR),
        ("pi_stacking", "Pi-stacking", _PI_COLOR),
        ("cation_pi", "Cation-pi", _PI_COLOR),
        ("salt_bridges", "Salt bridges", _SALT_BRIDGE_COLOR),
        ("metal_coordination", "Metal coordination", _METAL_COLOR),
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
