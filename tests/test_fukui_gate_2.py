"""The second Fukui gate's arithmetic (`app/fukui_gate_2.py`, `benchmarks/fukui_gate_2/PREREGISTRATION.md`), tested with invented measurements.

The module is pure and decides the gate, so what is tested here is the DECISION: that the typed published tables obey their own checks (the column sums, the second printing), that the rules leave exactly the
numbers and statements the preregistration names, that the labels of every species are what the graph says, and that each verdict is reached by exactly the conditions written down and no others. Nothing
here runs ORCA, and every expected number is read off the published table or worked by hand.
"""

from __future__ import annotations

import dataclasses

import pytest
from rdkit import Chem

from openchem.app import fukui_gate as gate_1
from openchem.app import fukui_gate_2 as gate


# --- the typed published tables -----------------------------------------------------------------------------------------------


def test_the_preregistered_constants_are_the_first_gates_where_they_are_the_same_definition():
    assert gate.TOLERANCE == 0.02 == gate_1.TOLERANCE
    assert gate.FLOOR_LIMIT == 0.005 == gate_1.FLOOR_LIMIT
    assert gate.MAX_ATTEMPTS == 3 and gate.ORCA_VERSION == "6.1.1"
    assert gate.SUM_TOLERANCE == 0.002 and gate.SECOND_PRINTING_TOLERANCE == 0.0005
    assert gate.DIHEDRAL_LIMIT_DEGREES == 30.0


def test_fifteen_species_are_decided_and_six_are_reported_and_two_set_the_floors():
    assert sorted(gate.SPECIES) == sorted([
        "HCN", "N2O", "anilinium", "phenol", "aniline", "fluorobenzene", "benzaldehyde", "styrene", "nitrobenzene", "pyrrole", "furan", "thiophene", "acrolein", "SCN-", "NO2-",
    ])
    assert sorted(gate.REPORTED_SPECIES) == ["CO", "H2CO", "enolate", "maleic anhydride", "maleimide", "phenolate"]
    assert sorted(gate.FLOOR_SPECIES) == ["formate", "pyridine"]
    assert not set(gate.SPECIES) & set(gate.REPORTED_SPECIES) and not set(gate.SPECIES) & set(gate.FLOOR_SPECIES)


def test_the_decided_set_is_forty_seven_numbers_and_the_names_are_those_of_the_preregistration():
    decided = gate.decided_entries()
    assert gate.count_numbers(decided) == 47
    per_molecule: dict[str, int] = {}
    for entry in decided:
        per_molecule[entry.molecule] = per_molecule.get(entry.molecule, 0) + len(entry.values)
    assert per_molecule == {
        "HCN": 3, "N2O": 3, "SCN-": 3, "NO2-": 2, "anilinium": 3, "phenol": 5, "aniline": 3, "fluorobenzene": 3, "benzaldehyde": 5, "styrene": 5,
        "nitrobenzene": 3, "pyrrole": 2, "furan": 2, "thiophene": 2, "acrolein": 3,
    }


def test_what_is_kept_out_of_the_decision_is_kept_out():
    decided = {entry.molecule for entry in gate.decided_entries()}
    assert not decided & {"CO", "H2CO", "enolate", "phenolate", "maleic anhydride", "maleimide"}
    assert {entry.attack for entry in gate.decided_entries() if entry.molecule == "acrolein"} == {"f+"}
    assert {entry.attack for entry in gate.decided_entries() if entry.molecule != "acrolein"} == {"f-"}


def test_every_decided_number_is_at_the_level_of_its_species():
    for entry in gate.decided_entries():
        assert entry.level == gate.SPECIES[entry.molecule].level
    assert {gate.SPECIES[name].level for name in ("SCN-", "NO2-")} == {gate.LEVEL_6_31PGS}
    assert {species.level for name, species in gate.SPECIES.items() if name not in ("SCN-", "NO2-")} == {gate.LEVEL_6_31GS}


# --- Rule A: the sum rule ------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "molecule,attack,expected",
    [("HCN", "f-", 1.000), ("N2O", "f-", 1.000), ("CO", "f-", 1.001), ("H2CO", "f-", 1.000), ("H2CO", "f+", 0.999), ("SCN-", "f-", 1.000), ("NO2-", "f-", 1.000)],
)
def test_each_complete_column_sums_to_one_to_within_its_rounding(molecule, attack, expected):
    """Worked by hand from Table 4 and Table 6: HCN 0.109 + 0.389 + 0.502; NO2- 0.310 + 2 * 0.345; H2CO f- 0.433 + 0.229 + 2 * 0.169; H2CO f+ 0.308 + 0.397 + 2 * 0.147."""
    assert gate.column_sum(molecule, attack) == pytest.approx(expected, abs=1e-9)
    assert abs(gate.column_sum(molecule, attack) - 1.0) <= gate.SUM_TOLERANCE


def test_no_complete_column_fails_the_sum_rule():
    assert gate.failing_columns() == ()


def test_a_partial_column_cannot_be_summed():
    with pytest.raises(ValueError, match="omits atoms"):
        gate.column_sum("phenol", "f-")


def test_a_misprint_in_a_complete_column_is_found_and_the_whole_column_is_dropped(monkeypatch):
    """The sum rule is what checks the transcription of a column: change one number by 0.01 and the column is reported, and its numbers leave the decision."""
    broken = {**gate.DEPROFT, "HCN": {"f-": {"H": (0.109,), "C": (0.399,), "N": (0.502,)}}}
    monkeypatch.setattr(gate, "DEPROFT", broken)
    assert gate.failing_columns() == (("HCN", "f-", 1.01),)
    assert not [entry for entry in gate.decided_entries() if entry.molecule == "HCN"]
    assert gate.count_numbers(gate.decided_entries()) == 44


def test_a_misprint_inside_the_tolerance_is_not_one(monkeypatch):
    """The rule's width is the rounding of the printed values: CO's published column is 0.001 high and is not dropped."""
    broken = {**gate.DEPROFT, "HCN": {"f-": {"H": (0.109,), "C": (0.390,), "N": (0.502,)}}}
    monkeypatch.setattr(gate, "DEPROFT", broken)
    assert gate.failing_columns() == ()


def test_the_number_of_atoms_of_a_label_counts_in_a_sum():
    """NO2-'s oxygen is published once (0.345) and the molecule has two of them; formaldehyde's hydrogen likewise."""
    assert gate.column_sum("NO2-", "f-") == pytest.approx(0.310 + 2 * 0.345)
    assert gate.column_sum("H2CO", "f-") == pytest.approx(0.433 + 0.229 + 2 * 0.169)


# --- Rule B: the second printing ---------------------------------------------------------------------------------------------


def test_every_second_printed_number_equals_the_first_and_nothing_is_uncorroborated():
    assert gate.corroboration_failures() == ()
    for molecule, by_attack in gate.SABLON.items():
        for attack, by_label in by_attack.items():
            for label, second in by_label.items():
                assert sorted(second) == sorted(gate.DEPROFT[molecule][attack][label])


def test_the_second_printing_covers_ten_rings_and_acrolein_and_not_phenolate():
    assert sorted(gate.SABLON) == sorted(
        ["anilinium", "phenol", "aniline", "fluorobenzene", "benzaldehyde", "styrene", "nitrobenzene", "pyrrole", "furan", "thiophene", "acrolein"]
    )
    assert "phenolate" not in gate.SABLON


def test_a_number_the_second_printing_disagrees_with_leaves_the_decision(monkeypatch):
    second = {**gate.SABLON, "aniline": {"f-": {"ortho": (0.081,), "meta": (0.061,), "para": (0.131,)}}}
    monkeypatch.setattr(gate, "SABLON", second)
    assert [(m, a, label) for m, a, label, _f, _s in gate.corroboration_failures()] == [("aniline", "f-", "ortho")]
    assert gate.count_numbers(gate.decided_entries()) == 46
    assert not [entry for entry in gate.decided_entries() if entry.molecule == "aniline" and entry.label == "ortho"]


def test_a_number_with_no_second_printing_of_its_label_leaves_the_decision(monkeypatch):
    second = {**gate.SABLON, "furan": {"f-": {"2": (0.272,)}}}
    monkeypatch.setattr(gate, "SABLON", second)
    assert [(m, label, s) for m, _a, label, _f, s in gate.corroboration_failures()] == [("furan", "3", None)]
    assert gate.count_numbers(gate.decided_entries()) == 46


def test_a_pair_is_compared_as_a_pair_whatever_order_it_is_printed_in(monkeypatch):
    second = {**gate.SABLON, "phenol": {"f-": {"ortho": (0.091, 0.081), "meta": (0.073, 0.064), "para": (0.144,)}}}
    monkeypatch.setattr(gate, "SABLON", second)
    assert gate.corroboration_failures() == ()


def test_a_difference_of_one_thousandth_in_a_second_printing_is_a_disagreement(monkeypatch):
    second = {**gate.SABLON, "pyrrole": {"f-": {"2": (0.195,), "3": (0.068,)}}}
    monkeypatch.setattr(gate, "SABLON", second)
    assert [(m, label) for m, _a, label, _f, _s in gate.corroboration_failures()] == [("pyrrole", "2")]


# --- the typed tables against each other and against the first gate -----------------------------------------------------------------


def test_the_published_carbon_monoxide_and_formaldehyde_agree_with_the_first_gates_to_within_the_documented_gap():
    """Published against published, no ORCA: two groups' B3LYP values at neighbouring levels (6-31G* here, 6-31G** in the first gate) differ by at most 0.0023, which is the figure the
    preregistration quotes and is also a check on the transcription of both tables."""
    index = gate_1.OLAH_LEVELS.index(gate_1.DFT_B)
    differences = []
    for molecule, label_map in (("CO", {"C": "C", "O": "O"}), ("H2CO", {"C": "C", "O": "O"})):
        for attack in ("f-", "f+"):
            if attack not in gate.DEPROFT[molecule]:
                continue
            position = 1 if attack == "f+" else 2
            for label, element in label_map.items():
                first = gate_1.OLAH[molecule][element][position][index]
                differences.append(abs(first - gate.DEPROFT[molecule][attack][label][0]))
    assert len(differences) == 6
    assert max(differences) == pytest.approx(0.0023, abs=1e-9)


def test_the_experimental_column_is_typed_for_every_ring():
    assert sorted(gate.EXPERIMENTAL_SELECTIVITY) == sorted(
        ["anilinium", "phenolate", "phenol", "aniline", "fluorobenzene", "benzaldehyde", "styrene", "nitrobenzene", "pyrrole", "furan", "thiophene"]
    )


# --- the species: atoms and labels pinned by the graph ---------------------------------------------------------------------------


def _ring_labels(mol, symbols):
    labels = list(symbols)
    ring = next(r for r in mol.GetRingInfo().AtomRings() if len(r) == 6)
    ipso = next(i for i in ring if any(n.GetIdx() not in ring and n.GetSymbol() != "H" for n in mol.GetAtomWithIdx(i).GetNeighbors()))
    for i in ring:
        distance = 0 if i == ipso else len(Chem.GetShortestPath(mol, ipso, i)) - 1
        labels[i] = ("ipso", "ortho", "meta", "para")[distance]
    return labels


def _graph_labels(kind: str, smiles: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """What the molecule's atoms are, and what a published table calls them, by the rules of section 4 applied to the graph: independent of the typed tuples."""
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    symbols = [atom.GetSymbol() for atom in mol.GetAtoms()]
    labels = list(symbols)
    if kind == "benzene":
        labels = _ring_labels(mol, symbols)
    elif kind == "five":
        ring = next(r for r in mol.GetRingInfo().AtomRings() if len(r) == 5)
        hetero = next(i for i in ring if symbols[i] != "C")
        for i in ring:
            if i != hetero:
                labels[i] = "2" if len(Chem.GetShortestPath(mol, hetero, i)) == 2 else "3"
    elif kind == "acrolein":
        oxygen = symbols.index("O")
        carbons = [i for i, s in enumerate(symbols) if s == "C"]
        carbonyl = next(c for c in carbons if mol.GetBondBetweenAtoms(c, oxygen) is not None)
        alpha = next(c for c in carbons if c != carbonyl and mol.GetBondBetweenAtoms(c, carbonyl) is not None)
        labels[carbonyl], labels[alpha] = "carbonyl", "alpha"
        labels[next(c for c in carbons if c not in (carbonyl, alpha))] = "beta"
    elif kind == "n2o":
        for atom in mol.GetAtoms():
            if atom.GetSymbol() == "N":
                labels[atom.GetIdx()] = "Nt" if atom.GetFormalCharge() == -1 else "Nc"
    elif kind == "five-carbonyl":
        ring = next(r for r in mol.GetRingInfo().AtomRings() if len(r) == 5)
        for i in ring:
            if symbols[i] == "C":
                double_to_o = any(
                    n.GetSymbol() == "O" and mol.GetBondBetweenAtoms(i, n.GetIdx()).GetBondTypeAsDouble() == 2.0 for n in mol.GetAtomWithIdx(i).GetNeighbors()
                )
                labels[i] = "carbonyl" if double_to_o else "CH"
    elif kind == "enolate":
        oxygen = symbols.index("O")
        carbons = [i for i, s in enumerate(symbols) if s == "C"]
        bonded = next(c for c in carbons if mol.GetBondBetweenAtoms(c, oxygen) is not None)
        for c in carbons:
            labels[c] = "CHO" if c == bonded else "CH2"
    return tuple(symbols), tuple(labels)


_KINDS = {
    "HCN": "plain", "N2O": "n2o", "anilinium": "benzene", "phenol": "benzene", "aniline": "benzene", "fluorobenzene": "benzene", "benzaldehyde": "benzene", "styrene": "benzene",
    "nitrobenzene": "benzene", "pyrrole": "five", "furan": "five", "thiophene": "five", "acrolein": "acrolein", "SCN-": "plain", "NO2-": "plain", "CO": "plain", "H2CO": "plain",
    "maleic anhydride": "five-carbonyl", "maleimide": "five-carbonyl", "enolate": "enolate", "phenolate": "benzene", "pyridine": "plain", "formate": "plain",
}


@pytest.mark.parametrize("name", sorted(gate.ALL_SPECIES))
def test_the_typed_atoms_and_labels_are_what_the_graph_of_the_smiles_says(name):
    species = gate.ALL_SPECIES[name]
    atoms, labels = _graph_labels(_KINDS[name], species.smiles)
    assert species.atoms == atoms
    assert species.labels == labels
    assert len(species.atoms) == len(species.labels)


@pytest.mark.parametrize("name", sorted(gate.ALL_SPECIES))
def test_the_typed_charge_is_the_smiles_net_charge_and_the_molecule_is_a_closed_shell(name):
    species = gate.ALL_SPECIES[name]
    mol = Chem.AddHs(Chem.MolFromSmiles(species.smiles))
    assert sum(atom.GetFormalCharge() for atom in mol.GetAtoms()) == species.charge
    assert sum(atom.GetNumRadicalElectrons() for atom in mol.GetAtoms()) == 0
    electrons = sum(atom.GetAtomicNum() for atom in mol.GetAtoms()) - species.charge
    assert electrons % 2 == 0


def test_every_published_label_is_a_label_of_its_species_and_a_pair_has_two_atoms_to_go_to():
    for molecule, by_attack in gate.DEPROFT.items():
        species = gate.ALL_SPECIES[molecule]
        for attack, by_label in by_attack.items():
            for label, values in by_label.items():
                atoms = sum(1 for candidate in species.labels if candidate == label)
                assert atoms >= 1, (molecule, label)
                assert len(values) in (1, 2) and (len(values) == 1 or atoms == 2), (molecule, label)


def test_an_anion_computes_f_minus_alone_and_every_other_species_the_four():
    assert {name for name, species in gate.SPECIES.items() if species.functions == "f-"} == {"SCN-", "NO2-"}
    assert all(species.functions == "f+ f- f0 dual" for name, species in gate.SPECIES.items() if species.charge >= 0)
    assert {name: species.charge for name, species in gate.SPECIES.items() if species.charge} == {"anilinium": 1, "SCN-": -1, "NO2-": -1}


def test_the_method_strings_are_the_panels():
    assert gate.SPECIES["phenol"].method_basis == "B3LYP 6-31G*"
    assert gate.SPECIES["SCN-"].method_basis == "B3LYP 6-31+G*"
    assert gate.METHOD_BASIS[gate.LEVEL_DEFAULT] == "B3LYP def2-SVP"


def test_the_grid_and_function_strings_are_the_ones_the_engine_writes():
    from openchem.chem.orca_engine import OrcaQuantumEngineProvider

    assert gate.GRID == OrcaQuantumEngineProvider._FUKUI_GRID_NAME
    assert gate.FUNCTIONS_ANION == "f-" and gate.FUNCTIONS_FULL == "f+ f- f0 dual"


# --- Rule C: the site statements ---------------------------------------------------------------------------------------------------


def test_eleven_statements_are_decidable_and_four_are_listed():
    decidable = gate.decidable_site_statements()
    assert [(s.molecule, s.attack, s.expected) for s in decidable] == [
        ("HCN", "f-", "N"), ("SCN-", "f-", "S"), ("anilinium", "f-", "para"), ("phenol", "f-", "para"), ("aniline", "f-", "para"), ("fluorobenzene", "f-", "para"),
        ("styrene", "f-", "para"), ("pyrrole", "f-", "2"), ("furan", "f-", "2"), ("thiophene", "f-", "3"), ("acrolein", "f+", "beta"),
    ]
    listed = {(s.molecule, s.expected): margin for s, margin in gate.undecidable_site_statements()}
    assert set(listed) == {("N2O", "O"), ("NO2-", "O"), ("benzaldehyde", "para"), ("nitrobenzene", "meta")}
    assert listed[("N2O", "O")] == pytest.approx(0.029) and listed[("NO2-", "O")] == pytest.approx(0.035)
    assert listed[("benzaldehyde", "para")] == pytest.approx(0.027) and listed[("nitrobenzene", "meta")] == pytest.approx(0.008)


@pytest.mark.parametrize(
    "molecule,expected,margin",
    [("HCN", "N", 0.113), ("SCN-", "S", 0.327), ("anilinium", "para", 0.080), ("phenol", "para", 0.053), ("aniline", "para", 0.051), ("fluorobenzene", "para", 0.071),
     ("styrene", "para", 0.050), ("pyrrole", "2", 0.126), ("furan", "2", 0.165), ("thiophene", "3", 0.079), ("acrolein", "beta", 0.040)],
)
def test_the_margin_of_each_decided_statement_is_worked_from_the_published_values(molecule, expected, margin):
    """The expected label's largest published value less the next label's largest, by hand: HCN 0.502 - 0.389; SCN- 0.606 - 0.279; phenol para 0.144 - ortho 0.091; styrene 0.115 - 0.065."""
    statement = next(s for s in gate.SITE_STATEMENTS if s.molecule == molecule and s.expected == expected)
    assert gate.published_margin(statement) == pytest.approx(margin, abs=1e-9)


def test_acrolein_sits_exactly_on_the_bound_and_is_decidable_because_of_the_float_slack():
    statement = next(s for s in gate.SITE_STATEMENTS if s.molecule == "acrolein")
    assert gate.published_margin(statement) == pytest.approx(2 * gate.TOLERANCE, abs=1e-12)
    assert statement in gate.decidable_site_statements()


def test_a_wider_tolerance_removes_statements_a_narrower_one_keeps():
    narrower = {(s.molecule, s.expected) for s in gate.decidable_site_statements(0.01)}
    assert len(narrower) == 11 + 3  # at T = 0.01 the bound is 0.02: benzaldehyde (0.027), N2O (0.029) and NO2- (0.035) join, nitrobenzene (0.008) does not
    assert {("benzaldehyde", "para"), ("N2O", "O"), ("NO2-", "O")} <= narrower and ("nitrobenzene", "meta") not in narrower
    assert len(gate.decidable_site_statements(0.03)) < 11


def test_a_statement_the_published_table_contradicts_has_no_margin():
    wrong = gate.SiteStatement("phenol", "f-", "ortho", ("ortho", "meta", "para"))
    assert gate.published_margin(wrong) is None


def test_a_statement_about_a_ring_is_about_the_ring_carbons_and_not_the_substituent():
    """Phenol's oxygen is an atom of the run and its f- is large; the statement is about ortho, meta and para only."""
    run = _perfect_run("phenol")
    labels = run.labels()
    values = list(run.f_minus)
    oxygen = labels.index("O")
    values[oxygen] = 0.9
    statement = next(s for s in gate.SITE_STATEMENTS if s.molecule == "phenol")
    assert gate.site_found(dataclasses.replace(run, f_minus=tuple(values)), statement) == "para"


def test_the_found_site_is_the_label_of_the_atom_with_the_largest_value_in_scope():
    run = _perfect_run("furan")
    statement = next(s for s in gate.SITE_STATEMENTS if s.molecule == "furan")
    assert gate.site_found(run, statement) == "2"
    swapped = dataclasses.replace(run, f_minus=tuple(0.5 if label == "3" else value for label, value in zip(run.labels(), run.f_minus)))
    assert gate.site_found(swapped, statement) == "3"


# --- invented runs ------------------------------------------------------------------------------------------------------------------


def _assign(species: gate.GateSpecies, published: dict[str, tuple[float, ...]]) -> list[float]:
    """A full f column whose published labels carry their published values (a pair to its two atoms in atom order) and whose unlisted atoms share what is left, so it sums to 1."""
    values: list[float | None] = [None] * len(species.atoms)
    used: dict[str, int] = {}
    for index, label in enumerate(species.labels):
        if label in published:
            options = published[label]
            position = used.get(label, 0)
            used[label] = position + 1
            values[index] = options[position] if len(options) == 2 else options[0]
    free = [index for index, value in enumerate(values) if value is None]
    left = 1.0 - sum(value for value in values if value is not None)
    for index in free:
        values[index] = left / len(free) if free else 0.0
    return [float(value) for value in values]


def _perfect_run(name: str, **changes) -> gate.MeasuredRun:
    """A run that reproduces every published number of `name` exactly, with everything else valid."""
    species = gate.ALL_SPECIES[name]
    published = gate.DEPROFT.get(name, {})
    size = len(species.atoms)
    f_minus = _assign(species, published.get("f-", {})) if "f-" in published else [1.0 / size] * size
    if species.charge < 0:
        f_plus, f_zero, dual = [], [], []
    else:
        f_plus = _assign(species, published.get("f+", {})) if "f+" in published else [1.0 / size] * size
        f_zero = [(p + m) / 2 for p, m in zip(f_plus, f_minus)]
        dual = [p - m for p, m in zip(f_plus, f_minus)]
    run = gate.MeasuredRun(
        molecule=name, level=species.level, symbols=species.atoms, f_plus=tuple(f_plus), f_minus=tuple(f_minus), f_zero=tuple(f_zero), dual=tuple(dual),
        charge=species.charge, multiplicity=1, orca_version="6.1.1", method_basis=species.method_basis, grid=gate.GRID, functions=species.functions,
        reference_charge=species.charge, completed=True, on_optimized_geometry=True, calculation_commit="a" * 40, calculation_dirty=False,
        dihedral_degrees=180.0 if name == "acrolein" else None,
    )
    return dataclasses.replace(run, **changes) if changes else run


def _all_runs(**per_species) -> dict[tuple[str, str], gate.MeasuredRun]:
    runs = {}
    for name, species in gate.SPECIES.items():
        runs[(name, species.level)] = _perfect_run(name, **per_species.get(name, {}))
    return runs


def _judge(runs=None, **kwargs):
    arguments = {"tolerance": 0.02, "floor": 0.001, "orca_versions": {"6.1.1"}}
    arguments.update(kwargs)
    return gate.judge(runs if runs is not None else _all_runs(), **arguments)


def _reason(verdict, fragment):
    return any(fragment in reason for reason in verdict.reasons)


def test_a_run_that_reproduces_every_published_number_passes():
    verdict = _judge()
    assert verdict.outcome is gate.Outcome.PASS and verdict.reasons == ()
    assert len(verdict.rows) == 47 and all(row.within for row in verdict.rows) and all(row.decided for row in verdict.rows)
    assert len(verdict.site_rows) == 11 and all(row.reproduced for row in verdict.site_rows)
    assert max(abs(row.difference) for row in verdict.rows) == 0.0 or max(abs(row.difference) for row in verdict.rows) < 1e-12


def test_the_invented_runs_obey_the_runs_own_sum_rules():
    """The builder is the instrument of every test below, so it is checked: f- of every species sums to 1, f+ too where it exists, and the identities hold."""
    for name in gate.SPECIES:
        run = _perfect_run(name)
        assert sum(run.f_minus) == pytest.approx(1.0, abs=1e-12)
        if run.f_plus:
            assert sum(run.f_plus) == pytest.approx(1.0, abs=1e-12)
            assert all(abs(d - (p - m)) < 1e-12 for p, m, d in zip(run.f_plus, run.f_minus, run.dual))
        else:
            assert gate.SPECIES[name].charge < 0 and not run.f_zero and not run.dual


# --- NOT EVALUABLE ---------------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kwargs,fragment",
    [
        ({"tolerance": 0.03}, "the tolerance is 0.03"),
        ({"tolerance": None}, "the tolerance is None"),
        ({"floor": None}, "no noise floor"),
        ({"floor": 0.0051}, "noise floor 0.0051 is above 0.005"),
        ({"orca_versions": {"6.0.0"}}, "ORCA 6.0.0 is not the preregistered 6.1.1"),
        ({"orca_versions": set()}, "no recorded version"),
        ({"unfinished_runs": ["phenol at B3LYP/6-31G*"]}, "a run did not complete: phenol"),
    ],
)
def test_the_conditions_of_the_gate_itself_make_it_not_evaluable(kwargs, fragment):
    verdict = _judge(**kwargs)
    assert verdict.outcome is gate.Outcome.NOT_EVALUABLE and _reason(verdict, fragment)


def test_a_floor_exactly_at_the_limit_is_usable():
    assert _judge(floor=0.005).outcome is gate.Outcome.PASS


def test_a_missing_run_makes_it_not_evaluable_and_names_the_species():
    runs = _all_runs()
    del runs[("furan", gate.LEVEL_6_31GS)]
    verdict = _judge(runs)
    assert verdict.outcome is gate.Outcome.NOT_EVALUABLE and _reason(verdict, "no run for: furan at B3LYP/6-31G*")


def test_a_species_that_could_not_be_computed_is_not_missing_it_is_a_failure():
    runs = _all_runs()
    del runs[("furan", gate.LEVEL_6_31GS)]
    verdict = _judge(runs, not_computed={("furan", gate.LEVEL_6_31GS)})
    assert verdict.outcome is gate.Outcome.FAIL and _reason(verdict, "furan at B3LYP/6-31G*: ORCA did not complete")


@pytest.mark.parametrize(
    "species,changes,fragment",
    [
        ("phenol", {"charge": 1}, "ran at charge 1, not the species' 0"),
        ("anilinium", {"charge": 0}, "ran at charge 0, not the species' 1"),
        ("SCN-", {"charge": 0}, "ran at charge 0, not the species' -1"),
        ("phenol", {"multiplicity": 2}, "ran at multiplicity 2"),
        ("phenol", {"completed": False}, "phenol at B3LYP/6-31G* did not complete"),
        ("phenol", {"on_optimized_geometry": False}, "did not run on the ORCA-optimized geometry"),
        ("phenol", {"symbols": ("O", "C")}, "has atoms"),
        ("phenol", {"method_basis": "B3LYP def2-SVP"}, "used 'B3LYP def2-SVP', the species' method is 'B3LYP 6-31G*'"),
        ("SCN-", {"method_basis": "B3LYP 6-31G*"}, "the species' method is 'B3LYP 6-31+G*'"),
        ("phenol", {"grid": ""}, "not the calculation the gate tests"),
        ("phenol", {"grid": "default"}, "its grid is 'default'"),
        ("SCN-", {"functions": "f+ f- f0 dual"}, "it computed 'f+ f- f0 dual', the species' calculation computes 'f-'"),
        ("phenol", {"functions": "f-"}, "the species' calculation computes 'f+ f- f0 dual'"),
        ("phenol", {"reference_charge": -1}, "reference charge is -1, not the species' 0"),
        ("phenol", {"reference_charge": None}, "reference charge is None"),
        ("phenol", {"calculation_dirty": True}, "src/ differed from commit"),
    ],
)
def test_each_property_of_a_run_the_preregistration_lists_makes_it_not_evaluable(species, changes, fragment):
    verdict = _judge(_all_runs(**{species: changes}))
    assert verdict.outcome is gate.Outcome.NOT_EVALUABLE and _reason(verdict, fragment), verdict.reasons


def test_an_anion_run_that_holds_an_f_plus_is_not_the_calculation_the_gate_tests():
    run = _perfect_run("phenol")
    verdict = _judge(_all_runs(**{"SCN-": {"f_plus": run.f_plus[:3] or (0.3, 0.3, 0.4), "f_zero": (0.3, 0.3, 0.4), "dual": (0.0, 0.0, 0.0)}}))
    assert verdict.outcome is gate.Outcome.NOT_EVALUABLE and _reason(verdict, "holds f+, f0 or the dual descriptor, which v2 does not compute")


def test_runs_made_from_two_commits_are_not_one_calculation():
    verdict = _judge(_all_runs(phenol={"calculation_commit": "b" * 40}))
    assert verdict.outcome is gate.Outcome.NOT_EVALUABLE and _reason(verdict, "2 different commits")


def test_a_run_whose_f_values_do_not_sum_to_one_is_not_evaluable_whatever_it_compares_as():
    run = _perfect_run("phenol")
    bent = tuple(value + (0.01 if index == 0 else 0.0) for index, value in enumerate(run.f_minus))
    verdict = _judge(_all_runs(phenol={"f_minus": bent}))
    assert verdict.outcome is gate.Outcome.NOT_EVALUABLE and _reason(verdict, "phenol at B3LYP/6-31G*: f- sums to 1.0100")


def test_an_anions_f_minus_is_checked_against_one_and_its_missing_f_plus_is_not_a_sum_failure():
    assert _judge().outcome is gate.Outcome.PASS
    run = _perfect_run("SCN-")
    bent = tuple(value + (0.01 if index == 0 else 0.0) for index, value in enumerate(run.f_minus))
    verdict = _judge(_all_runs(**{"SCN-": {"f_minus": bent}}))
    assert verdict.outcome is gate.Outcome.NOT_EVALUABLE and _reason(verdict, "SCN- at B3LYP/6-31+G*: f- sums to 1.0100")
    assert not _reason(verdict, "f+ sums")


def test_the_dual_descriptor_and_f0_must_be_what_they_are_defined_as():
    run = _perfect_run("phenol")
    verdict = _judge(_all_runs(phenol={"dual": tuple(d + 1e-6 for d in run.dual)}))
    assert verdict.outcome is gate.Outcome.NOT_EVALUABLE and _reason(verdict, "the dual descriptor is not f+ - f-")
    verdict = _judge(_all_runs(phenol={"f_zero": tuple(z + 1e-6 for z in run.f_zero)}))
    assert verdict.outcome is gate.Outcome.NOT_EVALUABLE and _reason(verdict, "f0 is not the mean of f+ and f-")


@pytest.mark.parametrize("dihedral,evaluable", [(180.0, True), (-179.0, True), (150.0, True), (-150.0, True), (149.9, False), (0.0, False), (30.0, False), (None, False)])
def test_acrolein_must_be_the_s_trans_molecule_the_source_published(dihedral, evaluable):
    verdict = _judge(_all_runs(acrolein={"dihedral_degrees": dihedral}))
    assert (verdict.outcome is not gate.Outcome.NOT_EVALUABLE) == evaluable
    if not evaluable:
        assert _reason(verdict, "O=C-C=C")


def test_every_reason_is_collected_and_none_hides_another():
    verdict = _judge(_all_runs(phenol={"grid": "x", "multiplicity": 2}), floor=0.5, tolerance=0.1)
    assert verdict.outcome is gate.Outcome.NOT_EVALUABLE
    for fragment in ("the tolerance is 0.1", "noise floor 0.5000", "ran at multiplicity 2", "its grid is 'x'"):
        assert _reason(verdict, fragment), fragment


def test_a_not_evaluable_gate_claims_neither_a_pass_nor_a_failure_even_if_a_number_is_far_off():
    run = _perfect_run("phenol")
    far = tuple(value + (0.5 if index == 0 else 0.0) for index, value in enumerate(run.f_minus))
    verdict = _judge(_all_runs(phenol={"f_minus": far}), floor=None)
    assert verdict.outcome is gate.Outcome.NOT_EVALUABLE and verdict.rows == ()


# --- PASS, PARTIAL, FAIL -----------------------------------------------------------------------------------------------------------------


def _consistent(run: gate.MeasuredRun, *, f_plus=None, f_minus=None) -> dict:
    """The changes that put new f+ and/or f- into `run` and keep f0 and the dual descriptor what they are defined as (an anion keeps none of the two)."""
    plus = run.f_plus if f_plus is None else tuple(f_plus)
    minus = run.f_minus if f_minus is None else tuple(f_minus)
    changes = {"f_plus": plus, "f_minus": minus}
    if plus:
        changes["f_zero"] = tuple((p + m) / 2 for p, m in zip(plus, minus))
        changes["dual"] = tuple(p - m for p, m in zip(plus, minus))
    return changes


def _bend(name: str, label: str, delta: float, attack: str = "f-", donor: str | None = None):
    """A perfect run of `name` with every atom of `label` moved by `delta` in `attack`, the weight taken from the atoms no published table lists (or, for a complete column, from the atoms of `donor`), so the
    column still sums to 1 and f0 and the dual descriptor are still what they are defined as."""
    run = _perfect_run(name)
    values = list(run.values(attack))
    labels = run.labels()
    moved = [index for index, candidate in enumerate(labels) if candidate == label]
    published = gate.DEPROFT[name][attack]
    donors = [index for index, candidate in enumerate(labels) if candidate == donor] if donor else [index for index, candidate in enumerate(labels) if candidate not in published]
    assert donors, "a complete column needs a donor label"
    for index in moved:
        values[index] += delta
    share = delta * len(moved) / len(donors)
    for index in donors:
        values[index] -= share
    return _consistent(run, f_plus=values if attack == "f+" else None, f_minus=values if attack == "f-" else None)


def test_a_neutral_number_exactly_at_the_tolerance_is_within_it_and_one_hundredth_over_is_a_failure():
    inside = _judge(_all_runs(phenol=_bend("phenol", "para", 0.02)))
    assert inside.outcome is gate.Outcome.PASS
    over = _judge(_all_runs(phenol=_bend("phenol", "para", 0.0201)))
    assert over.outcome is gate.Outcome.FAIL
    assert _reason(over, "phenol para f- at B3LYP/6-31G*: 0.1641 is +0.0201 from deproft2002's 0.1440")


def test_a_published_pair_is_matched_sorted_so_the_order_of_the_atoms_does_not_matter():
    """Phenol's published ortho pair is 0.081 and 0.091. A run whose two ortho carbons came out 0.090 and 0.080, in the order of the atoms that is the OTHER way round from the sorted pair, is 0.001 under
    each, and the signed differences say so."""
    run = _perfect_run("phenol")
    values = list(run.f_minus)
    ortho = [i for i, label in enumerate(run.labels()) if label == "ortho"]
    values[ortho[0]], values[ortho[1]] = 0.090, 0.080
    entries = [e for e in gate.decided_entries() if e.molecule == "phenol" and e.label == "ortho"]
    rows = gate.compare(entries, {("phenol", gate.LEVEL_6_31GS): dataclasses.replace(run, f_minus=tuple(values))}, 0.02)
    assert sorted((row.published, round(row.measured, 6), round(row.difference, 6)) for row in rows) == [(0.081, 0.080, -0.001), (0.091, 0.090, -0.001)]
    assert all(row.within for row in rows)


def test_a_published_pair_with_the_wrong_number_of_measured_atoms_is_not_compared():
    run = _perfect_run("phenol")
    odd = dataclasses.replace(run, symbols=run.symbols[:-1], f_plus=run.f_plus[:-1], f_minus=run.f_minus[:-1], f_zero=run.f_zero[:-1], dual=run.dual[:-1])
    entries = [e for e in gate.decided_entries() if e.molecule == "phenol"]
    assert gate.compare(entries, {("phenol", gate.LEVEL_6_31GS): odd}, 0.02) == []  # the atoms are not phenol's, so no label matches


def test_equivalent_atoms_that_came_apart_are_judged_by_the_worse_one():
    """NO2- has one published oxygen value and two oxygens; if one of them is 0.03 off the row says so."""
    run = _perfect_run("NO2-")
    values = list(run.f_minus)
    oxygens = [i for i, label in enumerate(run.labels()) if label == "O"]
    values[oxygens[1]] += 0.03
    values[run.labels().index("N")] -= 0.03
    rows = gate.compare([e for e in gate.decided_entries() if e.molecule == "NO2-" and e.label == "O"], {("NO2-", gate.LEVEL_6_31PGS): dataclasses.replace(run, f_minus=tuple(values))}, 0.02)
    assert len(rows) == 1 and rows[0].difference == pytest.approx(0.03) and rows[0].within is False


def test_a_neutral_site_that_is_missed_is_a_failure():
    run = _perfect_run("furan")
    verdict = _judge(_all_runs(furan={"f_minus": tuple(0.6 if label == "3" else value for label, value in zip(run.labels(), run.f_minus))}))
    assert verdict.outcome is gate.Outcome.NOT_EVALUABLE  # it no longer sums to one, and neither f0 nor the dual descriptor are what they are defined as
    shifted = list(run.f_minus)
    labels = run.labels()
    two = [i for i, label in enumerate(labels) if label == "2"]
    three = [i for i, label in enumerate(labels) if label == "3"]
    for i in two:
        shifted[i] -= 0.10
    for i in three:
        shifted[i] += 0.10
    verdict = _judge(_all_runs(furan=_consistent(run, f_minus=shifted)))
    assert verdict.outcome is gate.Outcome.FAIL
    assert _reason(verdict, "furan f- at B3LYP/6-31G*: the largest value is on 3, the documented site is 2")


def test_a_neutral_species_that_could_not_be_computed_fails_the_gate():
    runs = _all_runs()
    del runs[("acrolein", gate.LEVEL_6_31GS)]
    verdict = _judge(runs, not_computed={("acrolein", gate.LEVEL_6_31GS)})
    assert verdict.outcome is gate.Outcome.FAIL and _reason(verdict, "acrolein")


@pytest.mark.parametrize("name,label,delta,donor", [("anilinium", "para", 0.03, None), ("SCN-", "S", 0.03, "N"), ("NO2-", "N", 0.03, "O")])
def test_a_charged_species_that_misses_gives_partial_and_is_named(name, label, delta, donor):
    verdict = _judge(_all_runs(**{name: _bend(name, label, delta, donor=donor)}))
    assert verdict.outcome is gate.Outcome.PARTIAL, verdict.reasons
    assert verdict.anions_outside == (name,)
    assert any(r.within is False and not r.neutral for r in verdict.rows)


def test_a_charged_site_that_is_missed_gives_partial():
    run = _perfect_run("SCN-")
    labels = run.labels()
    values = list(run.f_minus)
    values[labels.index("S")] -= 0.4
    values[labels.index("N")] += 0.4
    verdict = _judge(_all_runs(**{"SCN-": {"f_minus": tuple(values)}}))
    assert verdict.outcome is gate.Outcome.PARTIAL and _reason(verdict, "SCN- f- at B3LYP/6-31+G*: the largest value is on N, the documented site is S")


def test_a_charged_species_that_could_not_be_computed_gives_partial():
    runs = _all_runs()
    del runs[("NO2-", gate.LEVEL_6_31PGS)]
    verdict = _judge(runs, not_computed={("NO2-", gate.LEVEL_6_31PGS)})
    assert verdict.outcome is gate.Outcome.PARTIAL and verdict.anions_outside == ("NO2-",)


def test_a_neutral_failure_wins_over_a_charged_one_and_both_are_listed():
    verdict = _judge(_all_runs(phenol=_bend("phenol", "para", 0.05), **{"SCN-": _bend("SCN-", "S", 0.05, donor="N")}))
    assert verdict.outcome is gate.Outcome.FAIL
    assert _reason(verdict, "phenol para f-") and _reason(verdict, "SCN- S f-")
    assert verdict.anions_outside == ("SCN-",)


def test_a_failure_in_the_cation_alone_does_not_fail_the_neutral_molecules():
    verdict = _judge(_all_runs(anilinium=_bend("anilinium", "ortho", 0.05)))
    assert verdict.outcome is gate.Outcome.PARTIAL and verdict.anions_outside == ("anilinium",)


# --- from the records the drive writes ---------------------------------------------------------------------------------------------


def _record(name: str, *, attempt: int = 1, completed: bool = True, **changes) -> dict:
    run = _perfect_run(name)
    record = {
        "species": name, "level": run.level, "attempt": attempt, "completed": completed, "symbols": list(run.symbols), "f_plus": list(run.f_plus),
        "f_minus": list(run.f_minus), "f_zero": list(run.f_zero), "dual": list(run.dual), "charge": run.charge, "multiplicity": 1, "orca_version": "6.1.1",
        "method_basis": run.method_basis, "grid": gate.GRID, "functions": run.functions, "reference_charge": run.charge, "on_optimized_geometry": True,
        "calculation_commit": "a" * 40, "calculation_dirty": False, "dihedral_degrees": run.dihedral_degrees,
    }
    record.update(changes)
    return record


def _records(**per_species) -> list[dict]:
    return [_record(name, **per_species.get(name, {})) for name in gate.SPECIES]


def test_records_judge_like_runs():
    verdict = gate.judge_records(_records(), floor=0.001)
    assert verdict.outcome is gate.Outcome.PASS and len(verdict.rows) == 47


def test_a_record_with_no_calculation_identity_is_not_evaluable_by_default():
    """The drive writes the commit and whether src/ differed; a record that lacks them (written by something else) cannot be trusted to be the calculation, so the defaults are the cautious ones."""
    records = _records()
    for record in records:
        del record["calculation_dirty"]
    verdict = gate.judge_records(records, floor=0.001)
    assert verdict.outcome is gate.Outcome.NOT_EVALUABLE and _reason(verdict, "src/ differed from commit")


def test_a_record_that_does_not_say_it_ran_on_the_optimized_geometry_did_not():
    records = _records()
    for record in records:
        del record["on_optimized_geometry"]
    assert gate.judge_records(records, floor=0.001).outcome is gate.Outcome.NOT_EVALUABLE


def test_an_anions_record_may_leave_out_f_plus_entirely():
    records = _records()
    scn = next(r for r in records if r["species"] == "SCN-")
    for key in ("f_plus", "f_zero", "dual"):
        del scn[key]
    assert gate.judge_records(records, floor=0.001).outcome is gate.Outcome.PASS


def test_three_failed_attempts_make_a_species_not_computed_and_two_leave_the_gate_unable_to_decide():
    records = [r for r in _records() if r["species"] != "furan"]
    failed = [_record("furan", attempt=n, completed=False) for n in (1, 2, 3)]
    assert gate.judge_records(records + failed, floor=0.001).outcome is gate.Outcome.FAIL
    assert gate.judge_records(records + failed[:2], floor=0.001).outcome is gate.Outcome.NOT_EVALUABLE


def test_two_completed_attempts_of_one_job_are_a_conflict():
    verdict = gate.judge_records(_records() + [_record("furan", attempt=2)], floor=0.001)
    assert verdict.outcome is gate.Outcome.NOT_EVALUABLE and _reason(verdict, "furan at B3LYP/6-31G* has 2 completed attempts")


# --- the reported arm --------------------------------------------------------------------------------------------------------------


def test_the_reported_arm_holds_the_numbers_outside_the_decision_and_the_default_preset():
    entries = gate.reported_entries()
    outside = [e for e in entries if e.level != gate.LEVEL_DEFAULT]
    assert {e.molecule for e in outside} == {"CO", "H2CO", "maleic anhydride", "maleimide", "enolate", "phenolate"}
    assert gate.count_numbers(outside) == 2 + 6 + 4 + 3 + 3
    default = [e for e in entries if e.level == gate.LEVEL_DEFAULT]
    assert gate.count_numbers(default) == 47 - 5  # the 13 neutral and cation species' decided numbers; the anions are not run at def2-SVP
    assert not {e.molecule for e in default} & {"SCN-", "NO2-"}


def test_reported_rows_are_never_decided_and_a_verdict_never_reads_them():
    runs = {("CO", gate.LEVEL_6_31GS): _perfect_run("CO")}
    rows = gate.reported_rows(runs)
    assert rows and all(row["decided"] is False for row in rows)
    assert {row["molecule"] for row in rows} == {"CO"}


def test_the_undecided_statements_are_reported_with_the_experimental_class_where_there_is_one():
    runs = {(name, species.level): _perfect_run(name) for name, species in gate.SPECIES.items()}
    rows = gate.reported_site_rows(runs)
    assert sorted((row["molecule"], row["found"], row["experimental"]) for row in rows) == [
        ("N2O", "O", None), ("NO2-", "O", None), ("benzaldehyde", "para", "m > o >> p"), ("nitrobenzene", "meta", "m >> o > p"),
    ]
    assert all(row["decided"] is False for row in rows)


def test_the_share_within_a_tighter_bound_is_counted_and_decides_nothing():
    rows = _judge().rows
    assert gate.share_within(rows, 0.01) == (47, 47)
    verdict = _judge(_all_runs(phenol=_bend("phenol", "para", 0.015)))
    within, total = gate.share_within(verdict.rows, 0.01)
    assert total == 47 and within == 46 and verdict.outcome is gate.Outcome.PASS


# --- the noise floors --------------------------------------------------------------------------------------------------------------


def test_the_gate_uses_the_larger_of_the_two_routes_floors():
    neutral = gate.FloorResult("pyridine", same_input=0.0, whole_chain=0.0021)
    anion = gate.FloorResult("formate", same_input=0.0004, whole_chain=0.0009)
    assert neutral.floor == 0.0021 and anion.floor == 0.0009
    assert gate.combined_floor([neutral, anion]) == 0.0021
    with pytest.raises(ValueError):
        gate.combined_floor([])


def test_a_floor_is_the_largest_difference_of_any_atoms_f_between_two_runs_and_an_anions_has_f_minus_alone():
    a = _perfect_run("formate")
    b = dataclasses.replace(a, f_minus=tuple(value + (0.003 if index == 0 else 0.0) for index, value in enumerate(a.f_minus)))
    differences = gate.repeat_differences(a, b)
    assert set(differences) == {f"f_minus[{i}]" for i in range(len(a.f_minus))}
    assert gate.noise_floor(differences) == pytest.approx(0.003)


# --- acrolein's input check, from the optimized coordinates --------------------------------------------------------------------------


@pytest.mark.parametrize("d,magnitude", [((1, 1, 0), 0.0), ((1, -1, 0), 180.0), ((1, 0, 1), 90.0), ((1, 0, -1), 90.0), ((1, 1, 1), 45.0)])
def test_the_dihedral_of_four_points_is_cis_zero_trans_one_eighty_and_perpendicular_ninety(d, magnitude):
    """a above the b-c axis; d on the same side (cis), the opposite side (trans), perpendicular to it, or half way up: worked from the geometry, not the formula under test."""
    assert abs(gate.dihedral_degrees((0, 1, 0), (0, 0, 0), (1, 0, 0), d)) == pytest.approx(magnitude, abs=1e-9)


def test_the_dihedral_does_not_depend_on_the_scale_of_the_coordinates():
    assert abs(gate.dihedral_degrees((0, 3, 0), (0, 0, 0), (5, 0, 0), (5, -2, 0))) == pytest.approx(180.0)


def _acrolein_positions(beta):
    """Atoms in the order of acrolein's labels (beta, alpha, carbonyl, O, then four H): the carbonyl carbon at the origin, its oxygen up, the alpha carbon along x, and the beta carbon above or below."""
    positions = {"beta": beta, "alpha": (1.5, 0.0, 0.0), "carbonyl": (0.0, 0.0, 0.0), "O": (-0.6, 1.1, 0.0)}
    return [positions.get(label, (9.0, 9.0, 9.0)) for label in gate.SPECIES["acrolein"].labels]


def test_acrolein_is_s_trans_when_the_beta_carbon_is_on_the_other_side_of_the_alpha_carbon_from_the_oxygen():
    trans = gate.acrolein_dihedral(gate.SPECIES["acrolein"].labels, _acrolein_positions((2.2, -1.2, 0.0)))
    cis = gate.acrolein_dihedral(gate.SPECIES["acrolein"].labels, _acrolein_positions((2.2, 1.2, 0.0)))
    assert abs(abs(trans) - 180.0) < 1e-6 and abs(cis) < 1e-6


def test_the_dihedral_check_of_the_judge_accepts_the_s_trans_input_this_computes_and_refuses_the_s_cis_one():
    labels = gate.SPECIES["acrolein"].labels
    trans = gate.acrolein_dihedral(labels, _acrolein_positions((2.2, -1.2, 0.0)))
    cis = gate.acrolein_dihedral(labels, _acrolein_positions((2.2, 1.2, 0.0)))
    assert _judge(_all_runs(acrolein={"dihedral_degrees": trans})).outcome is gate.Outcome.PASS
    assert _judge(_all_runs(acrolein={"dihedral_degrees": cis})).outcome is gate.Outcome.NOT_EVALUABLE
