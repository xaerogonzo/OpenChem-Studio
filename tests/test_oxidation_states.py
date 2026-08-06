"""Oxidation states, and the cases where the rule declines to answer.

Every number below was MEASURED from a real run before it was asserted.
The rule was verified on eight cases and then found to break on a ninth
(magnetite), and further measurement found three more failure classes and
four near-misses. All of them are here, because the near-misses are what
stop the refusals being written too widely -- a rule that refused every
metal-carbon bond would throw away methyllithium, and one that refused
every metal-metal bond would throw away calomel.
"""

from __future__ import annotations

import pytest
from rdkit import Chem

from openchem.chem.oxidation_states import (
    assign,
    compute_oxidation_states,
    electronegativity_table,
    format_state,
)


def mol_for(smiles: str):
    mol = Chem.MolFromSmiles(smiles, sanitize=False)
    assert mol is not None, smiles
    mol.UpdatePropertyCache(strict=False)
    return mol


def states_by_element(smiles: str) -> dict[str, list[int]]:
    mol = mol_for(smiles)
    result = assign(mol)
    assert not result.refused, f"unexpectedly refused: {result.reason}"
    found: dict[str, list[int]] = {}
    for index, state in sorted(result.states.items()):
        found.setdefault(mol.GetAtomWithIdx(index).GetSymbol(), []).append(state)
    return found


# --- the rule, where it works -----------------------------------------------


@pytest.mark.parametrize(
    "label, smiles, expected",
    [
        ("methane", "C", {"C": [-4]}),
        ("ethane", "CC", {"C": [-3, -3]}),
        ("ethanol", "CCO", {"C": [-3, -1], "O": [-2]}),
        ("carbon dioxide", "O=C=O", {"O": [-2, -2], "C": [4]}),
        ("water", "O", {"O": [-2]}),
        ("ammonia", "N", {"N": [-3]}),
        ("sulfuric acid", "OS(=O)(=O)O", {"O": [-2, -2, -2, -2], "S": [6]}),
        ("nitrate", "[O-][N+](=O)[O-]", {"O": [-2, -2, -2], "N": [5]}),
        ("sodium chloride", "[Na+].[Cl-]", {"Na": [1], "Cl": [-1]}),
    ],
)
def test_the_partition_rule_on_classical_compounds(label, smiles, expected):
    assert states_by_element(smiles) == expected, label


def test_hydrogen_peroxide_oxygens_are_minus_one():
    """The case that proves homonuclear bonds are split rather than
    counted. Water's oxygen is -2; peroxide's is -1, and the whole
    difference is the O-O bond contributing nothing to either atom."""
    assert states_by_element("OO") == {"O": [-1, -1]}


def test_permanganate_manganese_is_plus_seven():
    assert states_by_element("[O-][Mn](=O)(=O)=O")["Mn"] == [7]


@pytest.mark.parametrize(
    "label, smiles, expected_iron",
    [
        ("iron(II) oxide", "O=[Fe]", [2]),
        ("iron(III) oxide", "O=[Fe]O[Fe]=O", [3, 3]),
    ],
)
def test_the_iron_oxides_the_editor_flags_are_assigned_normally(label, smiles, expected_iron):
    """The user-facing point of the whole module. The drawing canvas puts a
    valence warning on these; here they are ordinary, and they get the
    numbers the names carry."""
    assert states_by_element(smiles)["Fe"] == expected_iron, label


# --- the near-misses: correct, and therefore must NOT be refused ------------
#
# These are the more valuable half of the table. Each one is a case a
# broader refusal rule would have swallowed, and every one of them is right.


def test_calomel_keeps_its_answer_despite_a_metal_metal_bond():
    """Hg2Cl2 is mercury(I): a real Hg-Hg bond, and +1 on each mercury is
    the correct answer. A rule refusing every metal-metal bond would throw
    it away, which is why the cluster test needs TWO metal neighbours."""
    assert states_by_element("Cl[Hg][Hg]Cl") == {"Cl": [-1, -1], "Hg": [1, 1]}


@pytest.mark.parametrize(
    "label, smiles, metal, expected",
    [
        ("methyllithium", "C[Li]", "Li", [1]),
        ("methylmagnesium bromide", "C[Mg]Br", "Mg", [2]),
    ],
)
def test_main_group_organometallics_keep_their_answers(label, smiles, metal, expected):
    """A polar main-group metal-carbon bond is exactly what the partition
    rule was built for. Only TRANSITION metals bonded to carbon are
    refused, and this is the pair that draws that line."""
    assert states_by_element(smiles)[metal] == expected, label


def test_iron_three_oxide_is_not_mistaken_for_mixed_valence():
    """Two irons, same state. The mixed-valence rule must compare the
    states rather than count the atoms."""
    result = assign(mol_for("O=[Fe]O[Fe]=O"))

    assert not result.refused


def test_a_molecule_whose_carbons_differ_is_not_refused():
    """Ethanol's carbons are -3 and -1. Carbon takes several states in
    almost every organic molecule, so scoping the mixed-valence rule to
    metals is not a detail -- without it this would refuse most of organic
    chemistry."""
    result = assign(mol_for("CCO"))

    assert not result.refused


# --- the refusals -----------------------------------------------------------


def test_magnetite_is_refused_rather_than_given_an_iron_four():
    """The case the whole design is built around.

    Fe3O4 is one Fe(II) and two Fe(III). This rule reports +3, +4, +3 --
    inventing an oxidation state iron does not have here, missing the mixed
    valence, and putting the wrong number on whichever iron the SMILES
    happened to write in the middle.
    """
    result = assign(mol_for("O=[Fe]O[Fe](O[Fe]=O)=O"))

    assert result.refused
    assert result.states == {}
    assert "mixed-valence" in result.reason
    assert "+3, +4" in result.reason
    assert len(result.atom_indices) == 3  # the three irons, for highlighting


@pytest.mark.parametrize(
    "label, smiles, metal",
    [
        ("chromium hexacarbonyl", "O=C[Cr](C=O)(C=O)(C=O)(C=O)C=O", "Cr"),
        ("iron pentacarbonyl", "O=C[Fe](C=O)(C=O)(C=O)C=O", "Fe"),
        ("ferrocene, drawn sigma-bonded", "C1=CC=C[CH]1[Fe][CH]1C=CC=C1", "Fe"),
    ],
)
def test_transition_metal_organometallics_are_refused(label, smiles, metal):
    """Measured, not assumed: this rule gives Cr(CO)6 a chromium of +6 and
    Fe(CO)5 an iron of +5. Both are zero-valent complexes. The rule counts
    the metal-carbon electrons as carbon's and never sees the back-donation
    going the other way."""
    result = assign(mol_for(smiles))

    assert result.refused, label
    assert "bonded directly to carbon" in result.reason


def test_diborane_is_refused_for_its_bridging_hydrogens():
    """Electron-deficient bonding. The rule hands each bridging hydrogen a
    full pair from both borons at once: measured, B(+4) and a bridging
    H(-2), against the real B(+3)."""
    result = assign(mol_for("[H]B1([H])[H]B([H])([H])[H]1"))

    assert result.refused
    assert "three-centre two-electron" in result.reason


def test_a_metal_cluster_is_refused():
    result = assign(mol_for("[Fe]1[Fe][Fe]1"))

    assert result.refused
    assert "cluster" in result.reason


def test_an_element_with_no_tabulated_electronegativity_is_refused():
    """Absent means refused, never a guessed or borrowed value."""
    result = assign(mol_for("[He]"))

    assert result.refused
    assert "He" in result.reason


def test_query_atoms_are_refused():
    result = assign(mol_for("*CC"))

    assert result.refused
    assert "no element" in result.reason


def test_ferrocene_as_an_ion_pair_is_assigned_and_that_is_deliberate():
    """The same compound, drawn two ways, gets two different answers -- and
    both are right about what was drawn.

    A bare Fe(2+) beside two cyclopentadienide anions IS a classical ionic
    description, and an isolated ion's oxidation state is its charge by
    definition. Drawn with iron bonded into the rings it is eta-5
    coordination, which this rule cannot describe, and is refused. That
    the answer depends on the drawing is a property of the formalism, and
    saying so is better than pretending otherwise.
    """
    result = assign(mol_for("[cH-]1cccc1.[cH-]1cccc1.[Fe+2]"))

    assert not result.refused
    iron = next(
        index
        for index in result.states
        if mol_for("[cH-]1cccc1.[cH-]1cccc1.[Fe+2]").GetAtomWithIdx(index).GetSymbol() == "Fe"
    )
    assert result.states[iron] == 2


# --- the calculator ---------------------------------------------------------


def test_the_calculator_is_reachable_through_the_registry(qapp):
    """Through the registry, never by direct import.

    A direct-import test once passed while the registration was bound to a
    shadowed two-argument function, and every molecule raised TypeError in
    the app while the suite stayed green.
    """
    from openchem.bootstrap import build_service_container

    registry = build_service_container().calculator_registry
    definition = registry.get("oxidation_states")
    assert definition is not None

    parameters = {p.name: p.default for p in definition.parameters}
    result = registry.compute("oxidation_states", mol_for("O=[Fe]O[Fe]=O"), "uuid", parameters)

    assert result.provenance.parameters["summary"] == "Fe +3; O -2"


def test_a_refusal_is_an_empty_dataset_and_not_a_failed_one():
    """"This rule cannot describe magnetite" is a fact about the rule. A
    permanent red FAILED row would misfile it as something broken, the same
    call `ring_systems` makes for a molecule with no rings."""
    from openchem.domain.common import CacheState

    dataset = compute_oxidation_states(mol_for("O=[Fe]O[Fe](O[Fe]=O)=O"), "uuid")

    assert dataset.values == {}
    assert dataset.cache_state is CacheState.COMPLETED
    assert dataset.error is None
    assert "mixed-valence" in dataset.provenance.parameters["refusal"]


def test_the_states_are_marked_categorical_rather_than_a_magnitude():
    """Iron(+3) is not "one more" of anything than iron(+2). A continuous
    colour ramp across them would imply an ordering the formalism does not
    carry."""
    dataset = compute_oxidation_states(mol_for("O=[Fe]O[Fe]=O"), "uuid")

    assert dataset.provenance.parameters["scale"] == "categorical"


def test_explicit_hydrogens_are_left_off_the_labels_by_default():
    """They are nearly all -1, they outnumber the heavy atoms, and a label
    on every one buries the number anybody opened this for."""
    with_hs = mol_for("[H]O[H]")

    hidden = compute_oxidation_states(with_hs, "uuid", {"show_hydrogens": False})
    shown = compute_oxidation_states(with_hs, "uuid", {"show_hydrogens": True})

    assert len(hidden.values) == 1
    assert len(shown.values) == 3


def test_the_caveat_travels_with_the_result():
    """An oxidation state is a formalism. That belongs in provenance, where
    it is carried into every export and inspector view, not only in prose
    somebody may not read."""
    dataset = compute_oxidation_states(mol_for("CCO"), "uuid")

    assert "not a measurement" in dataset.provenance.parameters["caveat"]


# --- the data file ----------------------------------------------------------


def test_every_tabulated_element_has_a_value_and_a_category():
    table = electronegativity_table()

    assert len(table) > 80
    for symbol, entry in table.items():
        assert isinstance(entry["pauling"], (int, float)), symbol
        assert entry["category"], symbol


def test_the_noble_gases_without_an_accepted_value_are_absent():
    """Absent rather than zero. A zero would make helium the most
    electropositive element in the table and quietly poison every
    partition it took part in."""
    table = electronegativity_table()

    assert "He" not in table
    assert "Ne" not in table
    assert "Ar" not in table


def test_the_electronegativity_file_is_in_the_packaging_spec():
    """`chem/data` is shipped file by file, so a new data file has to be
    named in the spec or the frozen build raises FileNotFoundError the
    first time anybody asks for an oxidation state."""
    from pathlib import Path

    spec = Path(__file__).resolve().parent.parent / "packaging" / "openchem.spec"

    assert "electronegativity.json" in spec.read_text(encoding="utf-8")


def test_format_state_writes_zero_without_a_sign():
    assert format_state(0) == "0"
    assert format_state(3) == "+3"
    assert format_state(-2) == "-2"
