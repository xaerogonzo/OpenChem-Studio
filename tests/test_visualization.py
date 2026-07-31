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
