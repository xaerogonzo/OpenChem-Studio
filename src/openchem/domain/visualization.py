"""Renderer-independent visualization data: what to draw, never how.

Four layer types and the colour scale they carry, moved out of
`ui/visualization.py` when `domain/report.py`'s chart channel needed to
declare a per-atom depiction.

**MOVED RATHER THAN COPIED, AND THAT IS THE WHOLE POINT.** The channel
needed "atom index -> colour and label" and `VisualizationLayer` had been
exactly that since Phase 11 -- so a `DepictionAnnotation` with its own
per-atom map would have been a second representation of one idea, which
this repository has paid for five times. The 3D viewer and a declared 2D
depiction now describe the same thing.

**NOTHING HERE IMPORTS A TOOLKIT OR A GUI**, which is what made the move
possible: every one of these is a frozen dataclass of primitives. The
BUILDERS stay behind in `ui/visualization.py` because they genuinely need
`chem.scalar_field` and `PerAtomDataset` -- the split is data here,
construction there.

`ui/visualization.py` re-exports all of it, so the twenty-two modules and
tests that name these types are untouched. That is what makes the move
behaviour-neutral by construction rather than by re-testing.

The same argument was already made once in this codebase, one type
earlier: `CATEGORICAL_SCALE` moved to `domain/common.py` when `chem/`
needed it, because `chem/` importing `ui/` would invert the layering and
the marker "was never a UI concept". Neither is a layer.
"""

from __future__ import annotations

from dataclasses import dataclass


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

    **A KEY MAY BE CHAIN-QUALIFIED**, as `"B/TYR652"`, and is whenever the
    contact knows its chain. Without it the selection matches the residue
    in EVERY chain: measured on 6WGT, `GLN72` resolves to chains A, B and
    C, and 370 of that deposit's 388 residue keys appear in more than one
    chain. A pose computed against chain B was colouring all three.

    The bare form is still valid and still correct for anything with one
    chain or no chain labelling, so a producer that cannot say which chain
    degrades to the old behaviour rather than losing the colouring.
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
