"""The per-atom comparison, and the atom correspondence underneath it.

The correspondence tests carry most of the weight here. A wrong mapping
does not fail loudly -- it produces confident numbers for a difference
between two atoms that are not the same site, and nothing downstream can
tell. So the assertions check WHICH atoms were paired, not merely that
some were.
"""

from __future__ import annotations

import pytest
from rdkit import Chem

from openchem.chem.comparison import atom_correspondence, build_comparison, deltas_against
from openchem.domain.common import CacheState, Provenance
from openchem.domain.comparison import ComparisonDataset, EntryKind
from openchem.domain.scientific_result import PerAtomDataset

ASPIRIN = "CC(=O)Oc1ccccc1C(=O)O"
SALICYLIC = "OC(=O)c1ccccc1O"


def mol(smiles: str):
    return Chem.AddHs(Chem.MolFromSmiles(smiles))


def dataset(uuid: str, values: dict[int, float], **kwargs) -> PerAtomDataset:
    return PerAtomDataset(
        property_id="gasteiger_charge",
        name="Partial Charge",
        units="e",
        method="rdkit",
        molecule_uuid=uuid,
        values=values,
        **kwargs,
    )


# --------------------------------------------------------------------------
# The correspondence


def test_corresponding_atoms_are_the_same_element():
    """A mapping that pairs a carbon with an oxygen is silently wrong."""
    left, right = mol(ASPIRIN), mol(SALICYLIC)
    mapping = atom_correspondence(left, right)

    assert mapping, "aspirin and salicylic acid share a substructure"
    for reference_index, other_index in mapping.items():
        assert (
            left.GetAtomWithIdx(reference_index).GetSymbol()
            == right.GetAtomWithIdx(other_index).GetSymbol()
        )


def test_an_aromatic_ring_does_not_map_onto_a_sugar_chain():
    """The bug this file exists to prevent.

    RDKit's DEFAULT bond comparison treats aromatic and single bonds as
    interchangeable, so benzene's ring opens and maps onto glucose's carbon
    chain: 12 of 12 atoms, every element agreeing, entirely meaningless.
    Element equality cannot catch it -- only the count can.
    """
    benzene, glucose = mol("c1ccccc1"), mol("OCC1OC(O)C(O)C(O)C1O")
    mapping = atom_correspondence(benzene, glucose)

    assert len(mapping) < 6, (
        f"benzene mapped {len(mapping)} atoms onto glucose; the aromatic ring "
        "is being matched against an sp3 chain"
    )


@pytest.mark.parametrize(
    "label,left,right,minimum",
    [
        # Two rings differing only by one nitrogen -- ring-based strictness
        # refuses this pair, which is why it is not used.
        ("pyridine/benzene", "c1ccncc1", "c1ccccc1", 9),
        # A tautomer pair a chemist genuinely compares. `ringMatchesRingOnly`
        # cuts this from 22 atoms to 5.
        ("glucose ring/open", "OCC1OC(O)C(O)C(O)C1O", "OCC(O)C(O)C(O)C(O)C=O", 20),
        ("caffeine/theophylline", "Cn1cnc2c1c(=O)n(C)c(=O)n2C", "Cn1c(=O)c2[nH]cnc2n(C)c1=O", 18),
    ],
)
def test_real_pairs_keep_most_of_their_shared_structure(label, left, right, minimum):
    """Strictness must not be bought by refusing legitimate comparisons."""
    mapping = atom_correspondence(mol(left), mol(right))
    assert len(mapping) >= minimum, f"{label} mapped only {len(mapping)} atoms"


def test_hydrogens_are_carried_through():
    """`chem/alignment.py` drops them because O3A refuses them as
    constraints. A per-atom property comparison has no such excuse, and
    hydrogens carry some of the most interesting differences."""
    ethanol, propanol = mol("CCO"), mol("CCCO")
    mapping = atom_correspondence(ethanol, propanol)

    hydrogens = [i for i in mapping if ethanol.GetAtomWithIdx(i).GetAtomicNum() == 1]
    assert hydrogens, "no hydrogens survived the correspondence"


def test_the_same_molecule_maps_onto_itself_completely():
    """Comparing two conformers or two methods on ONE structure is a real
    use, and a correspondence that dropped atoms there would narrow the
    comparison without saying so."""
    ethanol = mol("CCO")
    mapping = atom_correspondence(ethanol, mol("CCO"))
    assert mapping == {index: index for index in range(ethanol.GetNumAtoms())}


def test_the_same_molecule_in_a_different_atom_order_is_permuted_not_identity():
    """The test above cannot catch this, and an index-equality fast path
    passes it while being wrong.

    These two SMILES are the same molecule with the atoms written in a
    different order -- what you get when one copy came from a molblock and
    the other from SMILES. Equal canonical SMILES and equal atom count are
    both TRUE here and neither constrains the ordering: index-against-index
    pairs an oxygen with a carbon.
    """
    written_one_way = mol("OC(=O)c1ccccc1O")
    written_another = mol("Oc1ccccc1C(=O)O")

    assert Chem.MolToSmiles(written_one_way) == Chem.MolToSmiles(written_another)
    assert written_one_way.GetNumAtoms() == written_another.GetNumAtoms()

    mapping = atom_correspondence(written_one_way, written_another)

    # Every mapped pair is the same element -- which index-equality is not.
    for reference_index, other_index in mapping.items():
        assert (
            written_one_way.GetAtomWithIdx(reference_index).GetSymbol()
            == written_another.GetAtomWithIdx(other_index).GetSymbol()
        )
    assert len(mapping) == written_one_way.GetNumAtoms(), "the whole molecule should map"
    assert any(i != j for i, j in mapping.items()), (
        "these two orderings genuinely differ, so an identity mapping means "
        "atom order was assumed rather than solved"
    )


def test_molecules_with_nothing_in_common_return_an_empty_mapping():
    mapping = atom_correspondence(mol("[Na+].[Cl-]"), mol("c1ccccc1"))
    assert mapping == {}


# --------------------------------------------------------------------------
# Building the dataset


def test_a_molecule_that_was_never_computed_is_present_and_absent():
    """Dropping it would show three molecules for a four-molecule
    comparison, and the reader could not tell a missing result from an
    unremarkable one."""
    comparison = build_comparison(
        {"a": dataset("a", {0: 0.1, 1: -0.2}), "b": None},
        {"a": "Aspirin", "b": "Salicylic acid"},
        calculator_id="gasteiger",
        calculator_name="Partial Charge",
        order=["a", "b"],
    )

    assert len(comparison.entries) == 2
    absent = comparison.entry_for("b")
    assert absent is not None
    assert absent.kind is EntryKind.ABSENT
    assert not absent
    assert absent.molecule_name == "Salicylic acid"
    assert comparison.present() == (comparison.entry_for("a"),)


def test_per_atom_values_survive_the_reduction():
    """The entire reason this exists alongside `BatchTable`, which keeps
    only the aggregate."""
    comparison = build_comparison(
        {"a": dataset("a", {0: 0.5, 1: -0.5, 2: 0.25})},
        {"a": "Ethanol"},
        calculator_id="gasteiger",
        calculator_name="Partial Charge",
    )

    entry = comparison.entry_for("a")
    assert entry is not None
    assert entry.kind is EntryKind.PER_ATOM
    assert entry.values == {0: 0.5, 1: -0.5, 2: 0.25}
    assert entry.scalar == pytest.approx((0.5 - 0.5 + 0.25) / 3)


@pytest.mark.parametrize(
    "aggregate,expected",
    [("mean", 0.0), ("sum", 0.0), ("min", -0.6), ("max", 0.4), ("max_abs", -0.6)],
)
def test_each_aggregate_is_the_one_it_names(aggregate, expected):
    """`max_abs` returning -0.6 rather than 0.6 is deliberate -- the extreme
    value, signed, not its magnitude."""
    comparison = build_comparison(
        {"a": dataset("a", {0: 0.4, 1: -0.6, 2: 0.2})},
        {"a": "X"},
        calculator_id="gasteiger",
        calculator_name="Partial Charge",
        aggregate=aggregate,
    )
    entry = comparison.entry_for("a")
    assert entry is not None
    assert entry.scalar == pytest.approx(expected)
    assert entry.aggregate == aggregate


def test_an_unknown_aggregate_falls_back_rather_than_raising():
    comparison = build_comparison(
        {"a": dataset("a", {0: 1.0, 1: 3.0})},
        {"a": "X"},
        calculator_id="c",
        calculator_name="C",
        aggregate="median",
    )
    entry = comparison.entry_for("a")
    assert entry is not None
    assert entry.scalar == pytest.approx(2.0)
    assert entry.aggregate == "mean"


def test_an_empty_result_explains_itself_instead_of_reading_as_zero():
    """Caffeine really does match zero functional groups. That is a
    finding, and a blank cell does not communicate it."""
    empty = dataset(
        "a",
        {},
        provenance=Provenance(
            created_by="t",
            method="m",
            parameters={"summary": "No functional groups matched."},
        ),
    )
    comparison = build_comparison(
        {"a": empty}, {"a": "Caffeine"}, calculator_id="fg", calculator_name="Groups"
    )

    entry = comparison.entry_for("a")
    assert entry is not None
    assert entry.kind is EntryKind.PER_ATOM
    assert entry.scalar is None
    assert "No functional groups matched." in entry.note


def test_a_failed_result_is_absent_and_carries_its_reason():
    failed = dataset("a", {}, cache_state=CacheState.FAILED, error="no conformer")
    comparison = build_comparison(
        {"a": failed}, {"a": "X"}, calculator_id="c", calculator_name="C"
    )

    entry = comparison.entry_for("a")
    assert entry is not None
    assert entry.kind is EntryKind.ABSENT
    assert "no conformer" in entry.note


def test_categorical_values_get_no_aggregate_and_say_why():
    """The mean of ring-system ids 1, 2 and 3 is 2.0 and describes
    nothing."""
    categorical = dataset(
        "a",
        {0: 1.0, 1: 2.0, 2: 3.0},
        provenance=Provenance(created_by="t", method="m", parameters={"scale": "categorical"}),
    )
    comparison = build_comparison(
        {"a": categorical}, {"a": "X"}, calculator_id="rings", calculator_name="Ring system"
    )

    assert comparison.categorical
    entry = comparison.entry_for("a")
    assert entry is not None
    assert entry.scalar is None
    assert entry.values == {0: 1.0, 1: 2.0, 2: 3.0}
    assert any("not measurements" in limitation for limitation in comparison.limitations)


def test_spread_is_a_range_not_a_single_difference():
    comparison = build_comparison(
        {"a": dataset("a", {0: 1.0}), "b": dataset("b", {0: 5.0}), "c": dataset("c", {0: 3.0})},
        {"a": "A", "b": "B", "c": "C"},
        calculator_id="c",
        calculator_name="C",
        order=["a", "b", "c"],
    )
    assert comparison.spread() == (1.0, 5.0)


def test_spread_of_nothing_is_none_not_zero():
    comparison = build_comparison(
        {"a": None}, {"a": "A"}, calculator_id="c", calculator_name="C"
    )
    assert comparison.spread() is None
    assert not comparison


# --------------------------------------------------------------------------
# Deltas


def test_deltas_pair_corresponding_atoms_not_equal_indices():
    """Aspirin's ring carbon and salicylic acid's are at different indices.
    Subtracting index-for-index is the failure this guards."""
    left, right = mol(ASPIRIN), mol(SALICYLIC)
    mapping = atom_correspondence(left, right)

    left_values = {index: float(index) for index in range(left.GetNumAtoms())}
    right_values = {index: float(index) * 10 for index in range(right.GetNumAtoms())}
    comparison = build_comparison(
        {"a": dataset("a", left_values), "b": dataset("b", right_values)},
        {"a": "Aspirin", "b": "Salicylic acid"},
        calculator_id="c",
        calculator_name="C",
        order=["a", "b"],
    )

    deltas = deltas_against(comparison, "a", "b", mapping, reference_mol=left)
    assert deltas
    for delta in deltas:
        assert delta.other_value == pytest.approx(delta.other_index * 10)
        assert delta.reference_value == pytest.approx(delta.reference_index)
        assert delta.delta == pytest.approx(delta.other_value - delta.reference_value)
        # The pairing came from the correspondence, not from index equality.
        assert mapping[delta.reference_index] == delta.other_index


def test_atoms_outside_the_correspondence_are_omitted_not_zeroed():
    """A zero would read as 'identical here', which is the opposite of
    'this atom exists in only one of them'."""
    comparison = build_comparison(
        {"a": dataset("a", {0: 1.0, 1: 2.0, 2: 3.0}), "b": dataset("b", {0: 1.0, 1: 2.0})},
        {"a": "A", "b": "B"},
        calculator_id="c",
        calculator_name="C",
        order=["a", "b"],
    )

    deltas = deltas_against(comparison, "a", "b", {0: 0, 1: 1, 2: 99})
    assert [d.reference_index for d in deltas] == [0, 1]


def test_deltas_refuse_a_categorical_dataset():
    """Functional-group id 7 minus id 3 is 4, which is a number and means
    nothing at all."""
    categorical = dataset(
        "a",
        {0: 3.0},
        provenance=Provenance(created_by="t", method="m", parameters={"scale": "categorical"}),
    )
    other = dataset("b", {0: 7.0})
    comparison = build_comparison(
        {"a": categorical, "b": other},
        {"a": "A", "b": "B"},
        calculator_id="fg",
        calculator_name="Groups",
        order=["a", "b"],
    )

    assert deltas_against(comparison, "a", "b", {0: 0}) == []


def test_deltas_against_an_absent_molecule_are_empty():
    comparison = build_comparison(
        {"a": dataset("a", {0: 1.0}), "b": None},
        {"a": "A", "b": "B"},
        calculator_id="c",
        calculator_name="C",
        order=["a", "b"],
    )
    assert deltas_against(comparison, "a", "b", {0: 0}) == []


def test_the_delta_carries_both_indices_so_the_atom_can_be_pointed_at():
    left = mol("CCO")
    comparison = build_comparison(
        {"a": dataset("a", {0: 1.0}), "b": dataset("b", {5: 4.0})},
        {"a": "A", "b": "B"},
        calculator_id="c",
        calculator_name="C",
        order=["a", "b"],
    )

    (delta,) = deltas_against(comparison, "a", "b", {0: 5}, reference_mol=left)
    assert delta.reference_index == 0
    assert delta.other_index == 5
    assert delta.delta == pytest.approx(3.0)
    assert delta.element == "C"


def test_a_comparison_is_a_scientific_result():
    """So `result_clipboard` and the provenance conventions apply to it
    like every other result kind."""
    comparison = build_comparison(
        {"a": dataset("a", {0: 1.0})}, {"a": "A"}, calculator_id="c", calculator_name="C"
    )
    assert isinstance(comparison, ComparisonDataset)
    assert comparison.provenance is not None
    assert comparison.provenance.parameters["aggregate"] == "mean"
