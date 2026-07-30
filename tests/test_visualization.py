from __future__ import annotations

from openchem.domain.common import Provenance
from openchem.domain.scientific_result import AlertResult, PerAtomDataset
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


def test_build_visualization_layer_returns_none_for_an_unregistered_result_type():
    alert = AlertResult(
        alert_id="pains", name="PAINS", molecule_uuid="mol-1", matched=[], provenance=Provenance(created_by="core", method="rdkit")
    )

    assert build_visualization_layer(alert) is None
