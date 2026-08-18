from __future__ import annotations

from openchem.domain.common import Provenance
from openchem.domain.scientific_result import AlertResult, NMRSpectrumResult, PerAtomDataset
from openchem.ui.visualization import ColorScale, build_atom_color_layer, build_visualization_layer


def test_color_scale_interpolates_between_stops():
    scale = ColorScale(palette=[(0.0, "#ff0000"), (1.0, "#0000ff")], domain_min=0.0, domain_max=10.0)

    assert scale.color_for(0.0) == "#ff0000"
    assert scale.color_for(10.0) == "#0000ff"
    midpoint = scale.color_for(5.0)
    # Halfway between pure red and pure blue.
    assert midpoint == "#800080"


def test_color_scale_clamps_out_of_domain_values():
    scale = ColorScale(palette=[(0.0, "#ff0000"), (1.0, "#0000ff")], domain_min=0.0, domain_max=10.0)

    assert scale.color_for(-5.0) == "#ff0000"
    assert scale.color_for(50.0) == "#0000ff"


def test_color_scale_handles_zero_width_domain():
    scale = ColorScale(palette=[(0.0, "#ff0000"), (1.0, "#0000ff")], domain_min=5.0, domain_max=5.0)

    # Must not divide by zero -- falls back to the scale's midpoint color.
    assert scale.color_for(5.0) == "#800080"


def test_build_atom_color_layer_uses_diverging_scale_for_signed_data():
    dataset = PerAtomDataset(
        property_id="crippen_logp_contrib",
        name="LogP Contribution",
        units="",
        method="rdkit",
        molecule_uuid="mol-1",
        values={0: -0.5, 1: 0.5, 2: 0.0},
    )

    layer = build_atom_color_layer(dataset)

    assert layer.name == "LogP Contribution"
    assert set(layer.atom_colors) == {0, 1, 2}
    assert layer.color_scale is not None
    # Negative value should land toward the red end, positive toward blue.
    assert layer.atom_colors[0] != layer.atom_colors[1]
    assert layer.atom_colors[2] == layer.color_scale.color_for(0.0)


def test_build_atom_color_layer_uses_sequential_scale_for_magnitude_only_data():
    dataset = PerAtomDataset(
        property_id="fake_magnitude",
        name="Fake Magnitude",
        units="",
        method="rdkit",
        molecule_uuid="mol-1",
        values={0: 1.0, 1: 2.0, 2: 3.0},
    )

    layer = build_atom_color_layer(dataset)

    assert layer.color_scale.domain_min == 1.0
    assert layer.color_scale.domain_max == 3.0


def test_build_atom_color_layer_empty_values_produces_empty_layer():
    dataset = PerAtomDataset(
        property_id="empty", name="Empty", units="", method="rdkit", molecule_uuid="mol-1", values={}
    )

    layer = build_atom_color_layer(dataset)

    assert layer.atom_colors == {}


def test_build_atom_color_layer_default_has_no_labels():
    dataset = PerAtomDataset(
        property_id="crippen_logp_contrib", name="LogP Contribution", units="", method="rdkit",
        molecule_uuid="mol-1", values={0: -0.5, 1: 0.5},
    )

    layer = build_atom_color_layer(dataset)

    assert layer.atom_labels is None


def test_build_atom_color_layer_include_labels_formats_each_value():
    dataset = PerAtomDataset(
        property_id="crippen_logp_contrib", name="LogP Contribution", units="", method="rdkit",
        molecule_uuid="mol-1", values={0: -0.5, 1: 0.523},
    )

    layer = build_atom_color_layer(dataset, include_labels=True)

    assert layer.atom_labels == {0: "-0.50", 1: "+0.52"}


def test_build_visualization_layer_dispatches_to_the_per_atom_dataset_adapter():
    dataset = PerAtomDataset(
        property_id="crippen_logp_contrib", name="LogP Contribution", units="", method="rdkit",
        molecule_uuid="mol-1", values={0: -0.5, 1: 0.5},
    )

    layer = build_visualization_layer(dataset, include_labels=True)

    assert layer is not None
    assert layer.atom_labels == {0: "-0.50", 1: "+0.50"}


def test_build_visualization_layer_dispatches_to_the_same_adapter_for_nmr_spectrum_result():
    """Phase 22: NMRSpectrumResult reuses build_atom_color_layer as-is --
    it only touches .values/.name, structurally identical to what
    PerAtomDataset already provides."""
    spectrum = NMRSpectrumResult(
        spectrum_type="nmr_empirical", name="NMR Shift", units="ppm", method="smarts_lookup",
        molecule_uuid="mol-1", values={0: 25.0, 1: 190.0},
    )

    layer = build_visualization_layer(spectrum, include_labels=True)

    assert layer is not None
    assert layer.atom_colors.keys() == {0, 1}


def test_build_visualization_layer_returns_none_for_an_unregistered_result_type():
    alert = AlertResult(
        alert_id="pains", name="PAINS", molecule_uuid="mol-1", matched=[], provenance=Provenance(created_by="core", method="rdkit")
    )

    assert build_visualization_layer(alert) is None


# --- Phase 23: residue-target layers from real docking interaction data ------

# Verbatim shape of what analyze_pose (chem/pose_analysis.py) writes into
# DockingPoseModel.metadata -- residue coloring exists because THIS data
# already exists, not as a speculative generalization.
_POSE_METADATA = {
    "hbonds": [
        {"ligand_element": "O", "receptor_element": "N", "receptor_residue": "TYR652", "distance": 2.9},
        {"ligand_element": "N", "receptor_element": "O", "receptor_residue": "TYR652", "distance": 3.1},
        {"ligand_element": "O", "receptor_element": "N", "receptor_residue": "SER624", "distance": 2.8},
    ],
    "clashes": [
        {"ligand_element": "C", "receptor_element": "C", "receptor_residue": "PHE656", "distance": 2.9},
    ],
}


def test_interaction_layers_are_built_for_hbonds_and_clashes():
    from openchem.ui.visualization import build_interaction_layers

    layers = build_interaction_layers(_POSE_METADATA)

    assert [layer.name.split(" (")[0] for layer in layers] == ["H-bonds", "Steric clashes"]
    assert set(layers[0].residue_colors) == {"TYR652", "SER624"}
    assert set(layers[1].residue_colors) == {"PHE656"}


def test_multiple_contacts_to_one_residue_collapse_to_a_single_entry():
    """TYR652 appears in two separate H-bond contacts above -- it is one
    residue to colour, not two."""
    from openchem.ui.visualization import build_interaction_layers

    hbond_layer = build_interaction_layers(_POSE_METADATA)[0]

    assert len(hbond_layer.residue_colors) == 2
    assert "2 residues" in hbond_layer.name


def test_clashes_come_after_hbonds_so_a_problem_residue_wins():
    """Backends composite in order with later layers winning, so a residue
    that both H-bonds AND clashes must end up flagged as the clash -- that
    is the finding a user needs to see."""
    from openchem.ui.visualization import build_interaction_layers

    both = {
        "hbonds": [{"receptor_residue": "TYR652"}],
        "clashes": [{"receptor_residue": "TYR652"}],
    }
    layers = build_interaction_layers(both)

    assert layers[-1].name.startswith("Steric clashes")


def test_a_clean_pose_produces_no_layers():
    from openchem.ui.visualization import build_interaction_layers

    assert build_interaction_layers({"hbonds": [], "clashes": []}) == []
    assert build_interaction_layers({}) == []


def test_singular_residue_wording():
    from openchem.ui.visualization import build_interaction_layers

    layers = build_interaction_layers({"hbonds": [{"receptor_residue": "TYR652"}]})

    assert "1 residue)" in layers[0].name


def test_build_surface_layer_reuses_the_atom_layer_colors(qapp=None):
    """The surface and the sticks underneath must agree -- one colour
    decision feeding both, not two independent palette choices for the
    same property."""
    from openchem.ui.visualization import build_atom_color_layer, build_surface_layer

    dataset = PerAtomDataset(
        property_id="crippen_logp_contrib",
        name="LogP Contribution",
        units="",
        method="rdkit",
        molecule_uuid="mol-1",
        values={0: -0.4, 1: 0.0, 2: 0.4},
    )

    atom_layer = build_atom_color_layer(dataset)
    surface = build_surface_layer(dataset, representation="sas", opacity=0.6)

    assert surface.atom_colors == atom_layer.atom_colors
    assert surface.color_scale == atom_layer.color_scale
    assert surface.representation == "sas"
    assert surface.opacity == 0.6


def test_build_surface_layer_on_an_empty_dataset_has_no_colors():
    """None rather than an empty dict: viewer.html treats a null atomColors
    as 'plain uncoloured surface', which is the honest rendering of a
    property that produced no values."""
    from openchem.ui.visualization import build_surface_layer

    surface = build_surface_layer(
        PerAtomDataset(
            property_id="p", name="P", units="", method="rdkit", molecule_uuid="mol-1", values={}
        )
    )

    assert surface.atom_colors is None


def test_surface_representations_match_the_confirmed_3dmol_types():
    """Confirmed live: $3Dmol.SurfaceType is {VDW:1, MS:2, SAS:3, SES:4}.
    A representation not in that set would silently fall back to VDW in
    viewer.html rather than erroring."""
    from openchem.ui.visualization import SURFACE_REPRESENTATION_LABELS, SURFACE_REPRESENTATIONS

    assert SURFACE_REPRESENTATIONS == ["vdw", "sas", "ms", "ses"]
    assert set(SURFACE_REPRESENTATION_LABELS) == set(SURFACE_REPRESENTATIONS)


# --- Categorical per-atom data (ring systems, Thread 1) -----------------


def _categorical(values, **parameters):
    """A PerAtomDataset marked categorical the way compute_ring_systems
    marks one."""
    return PerAtomDataset(
        property_id="ring_systems",
        name="Ring Systems",
        units="",
        method="iupac-namer-perception",
        molecule_uuid="mol-1",
        values=values,
        provenance=Provenance(
            created_by="core",
            method="iupac-namer-perception",
            parameters={"scale": "categorical", **parameters},
        ),
    )


def test_categorical_data_gets_distinct_colours_not_an_interpolated_ramp():
    """Two ring systems are not 'one apart' in any meaningful sense, so
    they must be indexed into a qualitative palette rather than blended
    along a sequential one."""
    layer = build_atom_color_layer(_categorical({0: 1.0, 1: 1.0, 2: 2.0, 3: 2.0}))

    assert layer.atom_colors[0] == layer.atom_colors[1]
    assert layer.atom_colors[2] == layer.atom_colors[3]
    assert layer.atom_colors[0] != layer.atom_colors[2]


def test_a_categorical_layer_carries_no_colour_scale():
    """A ColorScale exists to draw a continuous legend, and there is no
    continuum here to draw. Leaving it set would render a gradient bar
    describing something the layer does not show."""
    assert build_atom_color_layer(_categorical({0: 1.0})).color_scale is None


def test_a_continuous_dataset_is_unaffected_by_the_categorical_branch():
    """The hint is opt-in: everything already shipping carries no `scale`
    parameter and must keep its diverging/sequential behaviour."""
    dataset = PerAtomDataset(
        property_id="gasteiger_charge",
        name="Partial Charge",
        units="e",
        method="rdkit",
        molecule_uuid="mol-1",
        values={0: -0.5, 1: 0.5},
    )
    assert build_atom_color_layer(dataset).color_scale is not None


def test_categorical_labels_prefer_the_per_atom_note():
    """'4a' is what the atom IS; '1.00' is an implementation detail of how
    it got its colour."""
    layer = build_atom_color_layer(
        _categorical({0: 1.0, 1: 1.0}, atom_notes={0: "4a"}),
        include_labels=True,
    )
    assert layer.atom_labels[0] == "4a"


def test_categorical_labels_fall_back_to_the_category_name():
    layer = build_atom_color_layer(
        _categorical({0: 1.0}, category_labels={1: "fused aromatic, 10 atoms"}),
        include_labels=True,
    )
    assert layer.atom_labels[0] == "fused aromatic, 10 atoms"


def test_the_qualitative_palette_cycles_rather_than_clamping():
    """A molecule with more ring systems than palette entries is rare but
    real. Cycling repeats a colour, which is a legible failure; clamping
    would paint every system past the last one identically with no hint
    that it had."""
    values = {i: float(i + 1) for i in range(20)}
    colours = build_atom_color_layer(_categorical(values)).atom_colors

    assert len(set(colours.values())) > 1
    assert colours[0] == colours[7]  # palette has 7 entries, so it wraps
def test_an_interaction_layer_carries_the_chain_it_was_measured_on():
    """Without it the selection matches the residue in EVERY chain.

    Measured on 6WGT, which carries three copies of the receptor: `GLN72`
    resolves to chains A, B and C, and 370 of that deposit's 388 residue
    keys appear in more than one chain. A pose computed against the boxed
    copy was therefore colouring all three -- and `analyze_pose` had been
    carrying `receptor_chain` beside `receptor_residue` the whole time,
    with this the consumer that threw it away.
    """
    from openchem.ui.visualization import build_interaction_layers

    layers = build_interaction_layers(
        {
            "hbonds": [
                {"receptor_residue": "TYR652", "receptor_chain": "B"},
                {"receptor_residue": "GLN72", "receptor_chain": "A"},
            ]
        }
    )

    assert len(layers) == 1
    assert sorted(layers[0].residue_colors) == ["A/GLN72", "B/TYR652"]


def test_a_contact_with_no_chain_still_colours_something():
    """Degrade to the old behaviour rather than losing the colouring.

    A single-chain receptor has nothing to qualify with, and a source
    without chain labelling cannot supply one. The bare key is still a
    valid selection and is still right for both, so the absence of a chain
    must not silently drop the residue.

    A chain that could not survive being written into a mol-script literal
    unquoted is treated the same way -- see `_SAFE_CHAIN`.
    """
    from openchem.ui.visualization import build_interaction_layers

    layers = build_interaction_layers(
        {
            "clashes": [
                {"receptor_residue": "PHE656"},
                {"receptor_residue": "ALA1", "receptor_chain": "   "},
                {"receptor_residue": "ASP2", "receptor_chain": "!!"},
            ]
        }
    )

    assert sorted(layers[0].residue_colors) == ["ALA1", "ASP2", "PHE656"]
