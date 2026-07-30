from __future__ import annotations

from dataclasses import dataclass

from openchem.domain.scientific_result import PerAtomDataset

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
    """Renderer-independent visualization data. `ViewerBackend.apply_visualization`
    consumes this without knowing which scientific property (or which
    provider — descriptor, docking, a future quantum result) produced it.
    Only an atom-color-map variant exists today; layer composability
    (multiple simultaneous layers, reordering, opacity) and non-atom
    targets (residue/chain/surface coloring) are deliberately not built
    yet — callers hold `list[VisualizationLayer]` even though only one is
    ever active, so that lifts without a data-shape rewrite.
    """

    name: str
    atom_colors: dict[int, str]  # atom index -> resolved hex color
    color_scale: ColorScale | None = None  # for a legend; optional


def build_atom_color_layer(dataset: PerAtomDataset) -> VisualizationLayer:
    """Extracts a `VisualizationLayer` from a `PerAtomDataset` — diverging
    red/blue for signed data (contribution-style values, where the sign
    itself is meaningful), sequential for magnitude-only data."""
    values = dataset.values
    if not values:
        return VisualizationLayer(name=dataset.name, atom_colors={})

    has_negative = any(v < 0 for v in values.values())
    has_positive = any(v > 0 for v in values.values())
    if has_negative and has_positive:
        magnitude = max(abs(v) for v in values.values()) or 1.0
        scale = ColorScale(palette=_DIVERGING_PALETTE, domain_min=-magnitude, domain_max=magnitude)
    else:
        scale = ColorScale(
            palette=_SEQUENTIAL_PALETTE, domain_min=min(values.values()), domain_max=max(values.values())
        )

    atom_colors = {idx: scale.color_for(v) for idx, v in values.items()}
    return VisualizationLayer(name=dataset.name, atom_colors=atom_colors, color_scale=scale)
