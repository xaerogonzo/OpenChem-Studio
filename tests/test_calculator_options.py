"""The shared options pass.

ChemAxon puts the same handful of controls on nearly every plugin. These
tests check both that the options exist and that they actually DO
something -- an inert option is worse than a missing one, because it looks
like a working control.
"""

from __future__ import annotations

import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.bootstrap import build_service_container
from openchem.chem.calculator_options import (
    apply_microspecies,
    decimals,
    fmt,
    microspecies_note,
)
from openchem.chem.elemental_analysis import compute_elemental_analysis
from openchem.chem.huckel import compute_huckel_analysis, solve_huckel
from openchem.chem.topology_analysis import compute_topology_analysis
from openchem.domain.calculator import RegistryExecution


def _embed(smiles: str) -> Chem.Mol:
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    AllChem.EmbedMolecule(mol, randomSeed=1)
    AllChem.MMFFOptimizeMolecule(mol)
    return mol


# --- The shared helpers -------------------------------------------------


def test_decimal_places_is_clamped_to_something_formattable():
    assert decimals({"decimal_places": -3}) == 0
    assert decimals({"decimal_places": 99}) == 8
    assert decimals({"decimal_places": "nonsense"}) == 2
    assert decimals(None) == 2


def test_fmt_honours_the_requested_width():
    assert fmt(3.14159, {"decimal_places": 0}) == "3"
    assert fmt(3.14159, {"decimal_places": 4}) == "3.1416"


def test_microspecies_is_opt_in():
    acid = Chem.MolFromSmiles("CC(=O)O")
    assert apply_microspecies(acid, {}) is acid
    assert apply_microspecies(acid, None) is acid


def test_microspecies_changes_the_structure_when_asked():
    acid = Chem.MolFromSmiles("CC(=O)O")
    at_high_ph = apply_microspecies(acid, {"major_microspecies": True, "pH": 12.0})
    assert Chem.GetFormalCharge(at_high_ph) == -1


def test_a_changed_structure_is_always_announced():
    """Silently computing on a different structure than the one on screen
    is the kind of thing that costs someone an afternoon."""
    assert microspecies_note({}) == []
    note = microspecies_note({"major_microspecies": True, "pH": 12.0})
    assert note and "pH 12" in note[0]


# --- The options actually do something ---------------------------------


def test_decimal_places_changes_elemental_analysis_output():
    one = compute_elemental_analysis(Chem.MolFromSmiles("CCO"), "m", {"decimal_places": 1})
    four = compute_elemental_analysis(Chem.MolFromSmiles("CCO"), "m", {"decimal_places": 4})
    assert one.matched[-1] != four.matched[-1]


def test_decimal_places_changes_topology_output():
    one = compute_topology_analysis(Chem.MolFromSmiles("c1ccccc1"), "m", {"decimal_places": 1})
    four = compute_topology_analysis(Chem.MolFromSmiles("c1ccccc1"), "m", {"decimal_places": 4})
    randic_one = next(line for line in one.matched if "Randic" in line)
    randic_four = next(line for line in four.matched if "Randic" in line)
    assert randic_one == "Randic index: 3.0"
    assert randic_four == "Randic index: 3.0000"


def test_elemental_analysis_on_the_microspecies_reports_the_ion():
    result = compute_elemental_analysis(
        Chem.MolFromSmiles("CC(=O)O"), "m", {"major_microspecies": True, "pH": 12.0}
    )
    assert "-" in result.matched[0]  # the anion's formula
    assert any("pH 12" in line for line in result.matched)


# --- Huckel: the aromatic-ion bug this pass fixed ----------------------


@pytest.mark.parametrize(
    "smiles,label",
    [
        ("c1ccccc1", "benzene"),
        ("[cH-]1cccc1", "cyclopentadienyl anion"),
        ("[cH+]1cccccc1", "tropylium cation"),
    ],
)
def test_the_textbook_aromatic_ions_all_have_six_pi_electrons(smiles, label):
    """Before the formal-charge term, cyclopentadienyl came out with 5 and
    tropylium with 7 -- neither showing the closed six-electron shell that
    makes them aromatic, on exactly the species someone would use to check
    a Huckel implementation."""
    result = solve_huckel(Chem.MolFromSmiles(smiles))
    assert sum(result.occupations) == 6, label


def test_the_pi_electron_count_can_be_overridden():
    default = solve_huckel(Chem.MolFromSmiles("c1ccccc1"))
    forced = solve_huckel(Chem.MolFromSmiles("c1ccccc1"), pi_electrons=4)
    assert sum(default.occupations) == 6
    assert sum(forced.occupations) == 4


def test_the_electron_count_is_clamped_to_what_the_orbitals_hold():
    result = solve_huckel(Chem.MolFromSmiles("c1ccccc1"), pi_electrons=999)
    assert sum(result.occupations) == 12  # two per orbital, six orbitals


def test_huckel_reports_the_electron_count_it_used():
    lines = compute_huckel_analysis(Chem.MolFromSmiles("[cH-]1cccc1"), "m").matched
    assert "6 pi electrons" in lines[0]


# --- Registry-wide ------------------------------------------------------


def test_every_numeric_text_calculator_offers_decimal_places():
    """The single most systematic gap found in the audit: ChemAxon puts
    this on nearly every panel and we had it on none."""
    registry = build_service_container().calculator_registry
    expected = {
        "elemental_analysis", "topology_analysis", "geometry_analysis",
        "surface_analysis", "interaction_analysis", "dipole_moment",
        "huckel_analysis", "cns_mpo",
    }
    for calculator_id in expected:
        definition = registry.get(calculator_id)
        names = {parameter.name for parameter in definition.parameters}
        assert "decimal_places" in names, calculator_id


def test_microspecies_options_always_travel_as_a_pair():
    """A pH with nothing to apply it to is meaningless."""
    registry = build_service_container().calculator_registry
    for category in registry.categories():
        for definition in registry.by_category(category):
            if not isinstance(definition.execution, RegistryExecution):
                continue
            names = {parameter.name for parameter in definition.parameters}
            if "major_microspecies" in names:
                assert "pH" in names, definition.calculator_id


def test_no_parameter_list_contains_duplicate_names():
    """A duplicate would make the settings dialog build two widgets under
    one key, and the second would silently win."""
    registry = build_service_container().calculator_registry
    for category in registry.categories():
        for definition in registry.by_category(category):
            names = [parameter.name for parameter in definition.parameters]
            assert len(names) == len(set(names)), definition.calculator_id


# --- Per-atom label precision (the second half of the options pass) ------


def test_per_atom_label_precision_comes_from_the_dataset():
    """The Calculator Inspector only ever sees a finished result, never the
    request -- so the precision travels in Provenance.parameters rather
    than being threaded through every view."""
    from openchem.chem.descriptor_providers import compute_crippen_logp_contrib_calculator
    from openchem.ui.visualization import build_atom_color_layer

    mol = Chem.MolFromSmiles("CCO")
    one = build_atom_color_layer(
        compute_crippen_logp_contrib_calculator(mol, "m", {"decimal_places": 1}), include_labels=True
    )
    four = build_atom_color_layer(
        compute_crippen_logp_contrib_calculator(mol, "m", {"decimal_places": 4}), include_labels=True
    )
    assert list(one.atom_labels.values()) != list(four.atom_labels.values())
    assert all(len(label.split(".")[1]) == 1 for label in one.atom_labels.values())
    assert all(len(label.split(".")[1]) == 4 for label in four.atom_labels.values())


def test_signed_data_keeps_its_plus_sign():
    """LogP contributions are signed and the sign carries the meaning."""
    from openchem.chem.descriptor_providers import compute_crippen_logp_contrib_calculator
    from openchem.ui.visualization import build_atom_color_layer

    layer = build_atom_color_layer(
        compute_crippen_logp_contrib_calculator(Chem.MolFromSmiles("CCO"), "m", {}),
        include_labels=True,
    )
    assert any(label.startswith("+") for label in layer.atom_labels.values())


def test_magnitude_only_data_gets_no_bogus_plus_sign():
    """An eccentricity or a surface area has no negative branch, so a "+"
    reads as noise rather than information."""
    from openchem.chem.topology_analysis import compute_eccentricity_dataset
    from openchem.ui.visualization import build_atom_color_layer

    layer = build_atom_color_layer(
        compute_eccentricity_dataset(Chem.MolFromSmiles("CCO"), "m", {}), include_labels=True
    )
    assert not any(label.startswith("+") for label in layer.atom_labels.values())


def test_a_dataset_without_provenance_still_labels_sensibly():
    from openchem.domain.scientific_result import PerAtomDataset
    from openchem.ui.visualization import build_atom_color_layer

    layer = build_atom_color_layer(
        PerAtomDataset(
            property_id="p", name="P", units="", method="m", molecule_uuid="m",
            values={0: 1.5, 1: 2.5},
        ),
        include_labels=True,
    )
    assert layer.atom_labels == {0: "1.50", 1: "2.50"}
