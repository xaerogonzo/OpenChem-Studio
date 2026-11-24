"""Mixed ordinary-vs-Quantum history compare is an allowlist, not a name match."""

from __future__ import annotations

import math

import pytest
from rdkit import Chem
from rdkit.Chem import AllChem, rdMolTransforms

from openchem.chem.submitted_structure import submitted_structure_identity
from openchem.domain.common import Provenance
from openchem.domain.descriptor import DescriptorValue
from openchem.domain.history_compare import (
    MIXED_QUANTITIES,
    MIXED_UNAPPROVED,
    QUANTUM_FAMILY_EMPTY,
    QUANTUM_INPUT_MISMATCH,
    MixedHistoryMatch,
    MixedQuantity,
    history_compare_choice_map,
    history_compare_label,
    match_mixed_history,
    mixed_history_comparable,
    named_row_from_mixed_match,
    other_history_entries,
    property_executions_comparable,
    quantum_family_rows,
    quantum_runs_comparable,
)
from openchem.domain.property_execution import ExecutionStatus, PropertyExecution
from openchem.domain.quantum_chemistry_run import QuantumChemistryRun, RunStatus, new_run_id
from openchem.domain.report import Fact, FactCategory, ReportResult
from openchem.domain.result_store import ResultIdentity, StoredResult
from openchem.domain.structure_issue import Basis


def _geometry_molblock(smiles: str, *, dx: float = 0.0, carbon_isotope: int | None = None) -> str:
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    if carbon_isotope is not None:
        mol.GetAtomWithIdx(0).SetIsotope(carbon_isotope)
    AllChem.EmbedMolecule(mol, randomSeed=1)
    if dx:
        conf = mol.GetConformer()
        for index in range(mol.GetNumAtoms()):
            point = conf.GetAtomPosition(index)
            conf.SetAtomPosition(index, (point.x + dx, point.y, point.z))
    return Chem.MolToMolBlock(mol)


_ETHANOL_A = _geometry_molblock("CCO")
_ETHANOL_B = _geometry_molblock("CCO", dx=0.75)


def _ethanol_oh_conformers() -> tuple[str, str]:
    """Anti and gauche C-C-O-H, same constitution, different coordinates."""
    mol = Chem.AddHs(Chem.MolFromSmiles("CCO"))
    AllChem.EmbedMolecule(mol, randomSeed=1)
    oxygen = next(atom.GetIdx() for atom in mol.GetAtoms() if atom.GetSymbol() == "O")
    carbons = [atom.GetIdx() for atom in mol.GetAtoms() if atom.GetSymbol() == "C"]
    hydrogen = next(
        neighbor.GetIdx()
        for neighbor in mol.GetAtomWithIdx(oxygen).GetNeighbors()
        if neighbor.GetSymbol() == "H"
    )
    carbon_at_oxygen = next(
        neighbor.GetIdx()
        for neighbor in mol.GetAtomWithIdx(oxygen).GetNeighbors()
        if neighbor.GetSymbol() == "C"
    )
    carbon_other = next(index for index in carbons if index != carbon_at_oxygen)
    conf = mol.GetConformer()
    rdMolTransforms.SetDihedralDeg(conf, carbon_other, carbon_at_oxygen, oxygen, hydrogen, 180.0)
    anti = Chem.MolToMolBlock(mol)
    rdMolTransforms.SetDihedralDeg(conf, carbon_other, carbon_at_oxygen, oxygen, hydrogen, 60.0)
    gauche = Chem.MolToMolBlock(mol)
    return anti, gauche


_METHANOL = _geometry_molblock("CO")
_BUTAN_2_OL_R = Chem.MolToMolBlock(Chem.MolFromSmiles("C[C@H](O)CC"))
_BUTAN_2_OL_S = Chem.MolToMolBlock(Chem.MolFromSmiles("C[C@@H](O)CC"))
_ETHANOL_13C = _geometry_molblock("CCO", carbon_isotope=13)


def _quantity(**overrides) -> MixedQuantity:
    values = dict(
        quantity_id="toy_homo",
        label="HOMO energy",
        units="eV",
        ordinary_producers=frozenset({"toy"}),
        ordinary_result_ids=frozenset({"toy_gap"}),
        ordinary_value_ids=frozenset({"toy.homo"}),
        quantum_descriptor_ids=frozenset({"orca.homo_energy"}),
        quantum_calc_types=frozenset({"sp"}),
        allow_cross_molecule=False,
    )
    values.update(overrides)
    return MixedQuantity(**values)


def _descriptor(
    descriptor_id="toy.homo", value=-0.3, units="eV", name="E(HOMO)", provider=None, provenance=None
) -> DescriptorValue:
    if provider is None:
        provider = descriptor_id.split(".", 1)[0] if "." in descriptor_id else "toy"
    return DescriptorValue(
        descriptor_id=descriptor_id,
        name=name,
        units=units,
        category="electronic",
        provider=provider,
        molecule_uuid="m1",
        value=value,
        provenance=provenance,
    )


def _stored(result, *, result_id="toy_gap", producer="toy", molecule="m1") -> StoredResult:
    return StoredResult(
        identity=ResultIdentity(
            molecule_uuid=molecule,
            result_id=result_id,
            calculation_input="geometry",
            input_fingerprint="fp",
            producer=producer,
        ),
        result=result,
    )


def _execution(
    *,
    producer="toy",
    molecule="m1",
    calculation_input="geometry",
    outputs=None,
    execution_id="exec-1",
) -> PropertyExecution:
    return PropertyExecution(
        execution_id=execution_id,
        molecule_uuid=molecule,
        producer=producer,
        method_model="huckel",
        parameters_key="k",
        calculation_input=calculation_input,
        input_fingerprint="fp",
        status=ExecutionStatus.COMPLETED,
        outputs=list(outputs or [_stored(_descriptor())]),
    )


def _run(
    *,
    molecule="m1",
    calc_type="sp",
    calculation_input="geometry",
    descriptors=None,
    run_id=None,
    extras=None,
    provider="orca",
    method_basis="B3LYP def2-SVP",
    input_fingerprint="fp",
    charge=0,
    multiplicity=1,
    solvent="",
    input_molblock="",
) -> QuantumChemistryRun:
    results = {"descriptors": list(descriptors or [_descriptor("orca.homo_energy", -0.4, name="E(HOMO)")])}
    if extras:
        results.update(extras)
    return QuantumChemistryRun(
        run_id=run_id or new_run_id(),
        molecule_uuid=molecule,
        calc_type=calc_type,
        method_basis=method_basis,
        charge=charge,
        multiplicity=multiplicity,
        calculation_input=calculation_input,
        input_fingerprint=input_fingerprint,
        input_molblock=input_molblock,
        solvent=solvent,
        provider=provider,
        status=RunStatus.COMPLETED,
        completed_at=1.0,
        results=results,
        output_status={},
    )


@pytest.fixture
def allow(monkeypatch):
    import openchem.domain.history_compare as module

    quantity = _quantity()
    monkeypatch.setattr(module, "MIXED_QUANTITIES", (quantity,))
    return quantity


def test_mixed_quantities_ships_empty():
    assert MIXED_QUANTITIES == ()


def test_empty_allowlist_refuses_every_mixed_pair():
    execution = _execution()
    run = _run()
    assert match_mixed_history(execution, run) == MIXED_UNAPPROVED
    assert mixed_history_comparable(execution, run) == MIXED_UNAPPROVED


def test_identical_display_names_do_not_authorize_comparison():
    execution = _execution()
    run = _run()
    assert "E(HOMO)" in (execution.outputs[0].result.name,)
    assert run.results["descriptors"][0].name == "E(HOMO)"
    assert match_mixed_history(execution, run) == MIXED_UNAPPROVED


def test_matching_producer_alone_does_not_authorize(allow, monkeypatch):
    import openchem.domain.history_compare as module

    monkeypatch.setattr(
        module,
        "MIXED_QUANTITIES",
        (_quantity(ordinary_result_ids=frozenset({"other_id"})),),
    )
    assert match_mixed_history(_execution(), _run()) == MIXED_UNAPPROVED


def test_patched_allowlist_returns_the_match(allow):
    execution = _execution()
    run = _run()
    outcome = match_mixed_history(execution, run)
    assert isinstance(outcome, MixedHistoryMatch)
    assert outcome.quantity is allow
    assert outcome.ordinary_value == pytest.approx(-0.3)
    assert outcome.quantum_value == pytest.approx(-0.4)
    assert outcome.units == "eV"
    assert outcome.quantity.label == "HOMO energy"
    assert mixed_history_comparable(execution, run) == ""


def test_exact_value_selectors_are_required(allow, monkeypatch):
    import openchem.domain.history_compare as module

    monkeypatch.setattr(
        module,
        "MIXED_QUANTITIES",
        (_quantity(ordinary_value_ids=frozenset({"not.this"})),),
    )
    assert match_mixed_history(_execution(), _run()) == MIXED_UNAPPROVED


def test_ambiguous_ordinary_match_refuses(allow):
    extra = _stored(_descriptor(value=-0.1), result_id="toy_gap")
    execution = _execution(outputs=[_stored(_descriptor()), extra])
    assert match_mixed_history(execution, _run()) == MIXED_UNAPPROVED


def test_missing_or_non_numeric_refuses(allow):
    execution = _execution(outputs=[_stored(_descriptor(value="n/a"))])
    assert match_mixed_history(execution, _run()) == MIXED_UNAPPROVED


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_non_finite_refuses(allow, value):
    execution = _execution(outputs=[_stored(_descriptor(value=value))])
    assert match_mixed_history(execution, _run()) == MIXED_UNAPPROVED


def test_units_must_match_the_declared_quantity(allow):
    execution = _execution(outputs=[_stored(_descriptor(units="beta"))])
    assert match_mixed_history(execution, _run()) == MIXED_UNAPPROVED


def test_unsupported_quantum_calc_type_refuses(allow):
    assert match_mixed_history(_execution(), _run(calc_type="opt")) == MIXED_UNAPPROVED


def test_drawing_versus_geometry_refuses_even_with_a_patched_entry(allow):
    execution = _execution(calculation_input="drawing")
    run = _run(calculation_input="geometry")
    message = match_mixed_history(execution, run)
    assert "drawing" in message.lower() or "3D" in message or "input" in message.lower()
    assert not isinstance(message, MixedHistoryMatch)


def test_cross_molecule_refuses_unless_the_entry_permits(allow, monkeypatch):
    import openchem.domain.history_compare as module

    execution = _execution(molecule="m1")
    run = _run(molecule="m2")
    assert match_mixed_history(execution, run) == "Those runs belong to different molecules."
    monkeypatch.setattr(
        module,
        "MIXED_QUANTITIES",
        (_quantity(allow_cross_molecule=True),),
    )
    outcome = match_mixed_history(execution, run)
    assert isinstance(outcome, MixedHistoryMatch)


def test_report_fact_matches_help_id_not_label(allow, monkeypatch):
    import openchem.domain.history_compare as module

    monkeypatch.setattr(
        module,
        "MIXED_QUANTITIES",
        (_quantity(ordinary_value_ids=frozenset({"fact.homo"})),),
    )
    fact = Fact(
        category=FactCategory.ELECTRONIC,
        label="E(HOMO)",
        value=-0.25,
        display_value="-0.25",
        source="toy",
        basis=Basis.DETERMINISTIC,
        units="eV",
        help_id="fact.homo",
    )
    report = ReportResult(
        report_id="toy_gap",
        name="Toy gap",
        molecule_uuid="m1",
        facts=(fact,),
    )
    execution = _execution(outputs=[_stored(report)])
    outcome = match_mixed_history(execution, _run())
    assert isinstance(outcome, MixedHistoryMatch)
    assert outcome.ordinary_value == pytest.approx(-0.25)


def test_named_row_reverses_delta_with_orientation(allow):
    match = match_mixed_history(_execution(), _run())
    assert isinstance(match, MixedHistoryMatch)
    ordinary_left = named_row_from_mixed_match(match, ordinary_on_left=True)
    quantum_left = named_row_from_mixed_match(match, ordinary_on_left=False)
    assert ordinary_left.delta == pytest.approx(-0.1)
    assert quantum_left.delta == pytest.approx(0.1)
    assert ordinary_left.label == "HOMO energy"


def test_pool_includes_both_kinds_and_excludes_the_selection():
    execution = _execution(execution_id="keep")
    other = _execution(execution_id="other")
    run = _run()
    pool = other_history_entries([execution, other], [run], execution)
    ids = {
        getattr(item, "execution_id", None) or getattr(item, "run_id", None)
        for item in pool
    }
    assert "keep" not in ids
    assert "other" in ids
    assert run.run_id in ids


def test_quantum_descriptor_id_not_display_name(allow, monkeypatch):
    import openchem.domain.history_compare as module

    monkeypatch.setattr(
        module,
        "MIXED_QUANTITIES",
        (_quantity(quantum_descriptor_ids=frozenset({"orca.homo_energy"})),),
    )
    run = _run(descriptors=[_descriptor("other.homo", -0.4, name="E(HOMO)")])
    assert match_mixed_history(_execution(), run) == MIXED_UNAPPROVED


def test_choice_map_prefixes_kind_and_keeps_records():
    execution = _execution()
    run = _run()
    choices = history_compare_choice_map([execution, run])
    assert any(label.startswith("Property ·") for label in choices)
    assert any(label.startswith("Quantum ·") for label in choices)
    assert history_compare_label(execution).startswith("Property ·")
    assert history_compare_label(run).startswith("Quantum ·")
    assert list(choices.values()) == [execution, run]


def test_same_kind_helpers_are_unchanged():
    left = _execution(execution_id="a")
    right = _execution(
        execution_id="b",
        producer="other",
        outputs=[_stored(_descriptor(), result_id="other_id", producer="other")],
    )
    assert "different quantities" in property_executions_comparable(left, right)
    from dataclasses import replace

    orca = _run()
    other = replace(orca, calc_type="opt", run_id=new_run_id())
    assert "different calculation types" in quantum_runs_comparable(orca, other)


def _scf(provider: str, value: float, **run_kwargs) -> QuantumChemistryRun:
    run_kwargs.setdefault("input_molblock", _ETHANOL_A)
    return _run(
        provider=provider,
        descriptors=[_descriptor(f"{provider}.scf_energy", value, units="Hartree", name="SCF Energy")],
        **run_kwargs,
    )


def test_orca_psi4_same_b3lyp_sp_is_comparable():
    orca = _scf("orca", -76.4)
    psi4 = _scf("psi4", -76.3)
    assert quantum_runs_comparable(orca, psi4) == ""
    rows = quantum_family_rows(orca, psi4)
    assert [row.label for row in rows] == ["SCF energy"]
    assert rows[0].delta == pytest.approx(0.1)


def test_quantum_input_type_mismatch_refuses():
    geometry = _scf("orca", -76.4, calculation_input="geometry")
    drawing = _scf("orca", -76.3, calculation_input="drawing")
    ensemble = _scf("orca", -76.2, calculation_input="ensemble")
    assert quantum_runs_comparable(geometry, drawing) == QUANTUM_INPUT_MISMATCH
    assert quantum_runs_comparable(geometry, ensemble) == QUANTUM_INPUT_MISMATCH
    assert quantum_runs_comparable(geometry, _scf("psi4", -76.1, calculation_input="geometry")) == ""


def test_display_name_does_not_make_a_family_row():
    left = _run(descriptors=[_descriptor("orca.other", -0.4, name="E(HOMO)", units="eV")])
    right = _run(descriptors=[_descriptor("orca.other", -0.5, name="E(HOMO)", units="eV")])
    assert quantum_family_rows(left, right) == []


def test_homo_matches_suffix_not_display_name():
    left = _run(descriptors=[_descriptor("orca.homo_energy", -0.4, name="Highest occupied")])
    right = _run(descriptors=[_descriptor("orca.homo_energy", -0.5, name="E(HOMO)")])
    rows = quantum_family_rows(left, right)
    assert [row.label for row in rows] == ["HOMO energy"]
    assert rows[0].delta == pytest.approx(-0.1)


def test_family_units_must_match_declaration():
    left = _scf("orca", -76.4)
    right = _run(
        provider="psi4",
        descriptors=[_descriptor("psi4.scf_energy", -76.3, units="eV", name="SCF Energy")],
    )
    assert quantum_family_rows(left, right) == []


def test_mismatched_descriptor_provider_skips():
    left = _scf("orca", -76.4)
    right = _run(
        provider="psi4",
        descriptors=[_descriptor("psi4.scf_energy", -76.3, units="Hartree", provider="orca")],
    )
    assert quantum_family_rows(left, right) == []


def test_duplicate_family_descriptors_skip_even_if_one_is_nan():
    left = _run(
        descriptors=[
            _descriptor("orca.homo_energy", -0.4),
            _descriptor("orca.homo_energy", math.nan),
        ]
    )
    right = _run(descriptors=[_descriptor("orca.homo_energy", -0.5)])
    assert quantum_family_rows(left, right) == []


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_non_finite_family_value_skips(value):
    left = _run(descriptors=[_descriptor("orca.homo_energy", value)])
    right = _run(descriptors=[_descriptor("orca.homo_energy", -0.5)])
    assert quantum_family_rows(left, right) == []


@pytest.mark.parametrize("calc_type", ["opt", "opt_freq"])
def test_homo_and_lumo_are_family_rows_on_opt_and_opt_freq(calc_type):
    left = _run(
        calc_type=calc_type,
        descriptors=[
            _descriptor("orca.homo_energy", -0.4),
            _descriptor("orca.lumo_energy", 0.2),
        ],
    )
    right = _run(
        calc_type=calc_type,
        descriptors=[
            _descriptor("orca.homo_energy", -0.5),
            _descriptor("orca.lumo_energy", 0.1),
        ],
    )
    assert quantum_runs_comparable(left, right) == ""
    labels = [row.label for row in quantum_family_rows(left, right)]
    assert labels == ["HOMO energy", "LUMO energy"]


def test_homo_allows_different_method_and_fingerprint():
    left = _run(
        calc_type="opt",
        method_basis="B3LYP def2-SVP",
        input_fingerprint="a",
        descriptors=[_descriptor("orca.homo_energy", -0.4)],
    )
    right = _run(
        calc_type="opt",
        method_basis="PBE0 def2-SVP",
        input_fingerprint="b",
        descriptors=[_descriptor("orca.homo_energy", -0.5)],
    )
    labels = [row.label for row in quantum_family_rows(left, right)]
    assert labels == ["HOMO energy"]


def test_missing_homo_on_one_side_skips_that_row():
    left = _run(calc_type="opt", descriptors=[_descriptor("orca.homo_energy", -0.4)])
    right = _run(calc_type="opt", descriptors=[_descriptor("orca.scf_energy", -76.3, units="Hartree")])
    assert "HOMO energy" not in [row.label for row in quantum_family_rows(left, right)]


def test_xtb_opt_freq_does_not_gain_homo_from_orca():
    orca = _run(
        calc_type="opt_freq",
        input_molblock=_ETHANOL_A,
        descriptors=[
            _descriptor("orca.scf_energy", -76.4, units="Hartree"),
            _descriptor("orca.homo_energy", -0.4),
        ],
    )
    xtb = _run(
        provider="xtb",
        calc_type="opt_freq",
        input_molblock=_ETHANOL_A,
        descriptors=[_descriptor("xtb.scf_energy", -76.3, units="Hartree")],
    )
    labels = [row.label for row in quantum_family_rows(orca, xtb)]
    assert "HOMO energy" not in labels
    assert labels == ["SCF energy"]


def test_homo_is_not_a_family_row_for_nmr():
    left = _run(calc_type="nmr", descriptors=[_descriptor("orca.homo_energy", -0.4)])
    right = _run(calc_type="nmr", descriptors=[_descriptor("orca.homo_energy", -0.5)])
    assert quantum_family_rows(left, right) == []


def _thermo(provider: str, enthalpy: float, gibbs: float, *, scf=None, **run_kwargs):
    run_kwargs.setdefault("input_molblock", _ETHANOL_A)
    descriptors = [
        _descriptor(f"{provider}.enthalpy", enthalpy, units="Hartree", name="Enthalpy"),
        _descriptor(f"{provider}.gibbs_free_energy", gibbs, units="Hartree", name="Gibbs"),
    ]
    if scf is not None:
        descriptors.insert(0, _descriptor(f"{provider}.scf_energy", scf, units="Hartree", name="SCF Energy"))
    return _run(provider=provider, calc_type="opt_freq", descriptors=descriptors, **run_kwargs)


@pytest.mark.parametrize("provider", ["orca", "xtb"])
def test_matching_opt_freq_tabulates_enthalpy_gibbs_and_scf(provider):
    left = _thermo(provider, -76.2, -76.1, scf=-76.4)
    right = _thermo(provider, -76.0, -75.9, scf=-76.3)
    labels = [row.label for row in quantum_family_rows(left, right)]
    assert labels == ["SCF energy", "Enthalpy", "Gibbs free energy"]


def test_missing_thermo_on_one_side_skips_only_that_quantity():
    left = _thermo("orca", -76.2, -76.1, scf=-76.4)
    right = _run(
        calc_type="opt_freq",
        input_molblock=_ETHANOL_A,
        descriptors=[
            _descriptor("orca.scf_energy", -76.3, units="Hartree"),
            _descriptor("orca.enthalpy", -76.0, units="Hartree"),
        ],
    )
    labels = [row.label for row in quantum_family_rows(left, right)]
    assert labels == ["SCF energy", "Enthalpy"]
    assert "Gibbs free energy" not in labels


@pytest.mark.parametrize(
    "kwargs",
    [
        {"method_basis": "PBE0 def2-SVP"},
        {"charge": 1},
        {"multiplicity": 3},
        {"solvent": "water"},
        {"input_fingerprint": "other"},
        {"molecule": "m2"},
    ],
)
def test_thermo_skipped_when_model_or_state_or_fingerprint_differs(kwargs):
    base = _thermo("orca", -76.2, -76.1, scf=-76.4)
    other = _thermo("orca", -76.0, -75.9, scf=-76.3, **kwargs)
    labels = [row.label for row in quantum_family_rows(base, other)]
    assert "Enthalpy" not in labels
    assert "Gibbs free energy" not in labels
    if kwargs == {"input_fingerprint": "other"}:
        assert labels == ["SCF energy"]


def test_different_geometry_opt_freq_keeps_scf_and_skips_thermo():
    left = _thermo(
        "orca",
        -76.2,
        -76.1,
        scf=-76.4,
        input_fingerprint="geom-a",
        input_molblock=_ETHANOL_A,
    )
    right = _thermo(
        "orca",
        -76.0,
        -75.9,
        scf=-76.3,
        input_fingerprint="geom-b",
        input_molblock=_ETHANOL_B,
    )
    labels = [row.label for row in quantum_family_rows(left, right)]
    assert labels == ["SCF energy"]


def test_duplicate_enthalpy_descriptors_skip_that_row():
    left = _run(
        calc_type="opt_freq",
        descriptors=[
            _descriptor("orca.enthalpy", -76.2, units="Hartree"),
            _descriptor("orca.enthalpy", -76.25, units="Hartree"),
            _descriptor("orca.gibbs_free_energy", -76.1, units="Hartree"),
        ],
    )
    right = _thermo("orca", -76.0, -75.9)
    labels = [row.label for row in quantum_family_rows(left, right)]
    assert "Enthalpy" not in labels
    assert labels == ["Gibbs free energy"]


def test_enthalpy_wrong_units_or_provider_skips():
    left = _thermo("orca", -76.2, -76.1)
    wrong_units = _run(
        calc_type="opt_freq",
        descriptors=[
            _descriptor("orca.enthalpy", -76.0, units="eV"),
            _descriptor("orca.gibbs_free_energy", -75.9, units="Hartree"),
        ],
    )
    wrong_provider = _run(
        calc_type="opt_freq",
        descriptors=[
            _descriptor("orca.enthalpy", -76.0, units="Hartree", provider="xtb"),
            _descriptor("orca.gibbs_free_energy", -75.9, units="Hartree"),
        ],
    )
    assert "Enthalpy" not in [row.label for row in quantum_family_rows(left, wrong_units)]
    assert "Enthalpy" not in [row.label for row in quantum_family_rows(left, wrong_provider)]


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_non_finite_enthalpy_skips_that_row(value):
    left = _run(
        calc_type="opt_freq",
        descriptors=[
            _descriptor("orca.enthalpy", value, units="Hartree"),
            _descriptor("orca.gibbs_free_energy", -76.1, units="Hartree"),
        ],
    )
    right = _thermo("orca", -76.0, -75.9)
    labels = [row.label for row in quantum_family_rows(left, right)]
    assert "Enthalpy" not in labels
    assert "Gibbs free energy" in labels


def _origin(independent=True) -> Provenance:
    return Provenance(created_by="core", method="test", parameters={"origin_independent": independent})


def _family_dipole(provider: str, value: float, *, origin=True, **run_kwargs):
    run_kwargs.setdefault("input_molblock", _ETHANOL_A)
    run_kwargs.setdefault("input_fingerprint", "fp")
    descriptors = run_kwargs.pop("descriptors", None)
    if descriptors is None:
        descriptors = [
            _descriptor(f"{provider}.scf_energy", -76.4, units="Hartree", name="SCF Energy"),
            _descriptor(
                f"{provider}.dipole_moment",
                value,
                units="Debye",
                name="Dipole",
                provenance=_origin(origin),
            ),
        ]
    return _run(provider=provider, descriptors=descriptors, **run_kwargs)


def test_neutral_qc_dipoles_are_a_family_row():
    left = _family_dipole("orca", 1.5)
    right = _family_dipole("psi4", 1.8)
    labels = [row.label for row in quantum_family_rows(left, right)]
    assert labels == ["SCF energy", "Dipole"]
    assert quantum_family_rows(left, right)[1].delta == pytest.approx(0.3)


def test_dipole_family_omits_ions_and_malformed_origin_flags():
    good = _family_dipole("orca", 1.5)
    ion = _family_dipole("orca", 1.6, origin=False)
    assert "Dipole" not in [row.label for row in quantum_family_rows(good, ion)]
    assert "SCF energy" in [row.label for row in quantum_family_rows(good, ion)]

    missing = _family_dipole("orca", 1.7)
    missing.results["descriptors"][1].provenance = None
    assert "Dipole" not in [row.label for row in quantum_family_rows(good, missing)]

    malformed = _family_dipole("orca", 1.8)
    malformed.results["descriptors"][1].provenance.parameters["origin_independent"] = 1
    assert "Dipole" not in [row.label for row in quantum_family_rows(good, malformed)]

    charged_run = _family_dipole("orca", 1.9, charge=1)
    assert "Dipole" not in [row.label for row in quantum_family_rows(good, charged_run)]

    no_key = _family_dipole("orca", 1.7)
    no_key.results["descriptors"][1].provenance.parameters.pop("origin_independent")
    assert "Dipole" not in [row.label for row in quantum_family_rows(good, no_key)]


def test_missing_dipole_omits_only_that_family_row():
    both = _family_dipole("orca", 1.5)
    scf_only = _scf("orca", -76.3, input_molblock=_ETHANOL_A)
    labels = [row.label for row in quantum_family_rows(both, scf_only)]
    assert labels == ["SCF energy"]


def test_dipole_family_needs_matching_model_and_identity():
    left = _family_dipole("orca", 1.5)
    other_method = _family_dipole("orca", 1.6, method_basis="HF STO-3G")
    other_mol = _family_dipole("orca", 1.6, input_molblock=_METHANOL, input_fingerprint="meoh")
    assert quantum_family_rows(left, other_method) == []
    assert "Dipole" not in [row.label for row in quantum_family_rows(left, other_mol)]


def test_dipole_family_allows_real_conformer_geometries():
    anti, gauche = _ethanol_oh_conformers()
    assert submitted_structure_identity(anti) == submitted_structure_identity(gauche)
    assert anti != gauche
    left = _family_dipole("orca", 1.5, input_molblock=anti, input_fingerprint="anti")
    right = _family_dipole("orca", 1.9, input_molblock=gauche, input_fingerprint="gauche")
    labels = [row.label for row in quantum_family_rows(left, right)]
    assert "Dipole" in labels


def test_orca_entropy_is_a_family_row_on_matching_opt_freq():
    left = _run(
        provider="orca",
        calc_type="opt_freq",
        input_molblock=_ETHANOL_A,
        descriptors=[
            _descriptor("orca.enthalpy", -76.2, units="Hartree"),
            _descriptor("orca.entropy_term", 0.02, units="Hartree"),
        ],
    )
    right = _run(
        provider="orca",
        calc_type="opt_freq",
        input_molblock=_ETHANOL_A,
        descriptors=[
            _descriptor("orca.enthalpy", -76.0, units="Hartree"),
            _descriptor("orca.entropy_term", 0.01, units="Hartree"),
        ],
    )
    labels = [row.label for row in quantum_family_rows(left, right)]
    assert labels == ["Enthalpy", "Entropy term"]
    other_geom = _run(
        provider="orca",
        calc_type="opt_freq",
        input_fingerprint="other",
        input_molblock=_ETHANOL_A,
        descriptors=[_descriptor("orca.entropy_term", 0.01, units="Hartree")],
    )
    assert quantum_family_rows(left, other_geom) == []


def test_xtb_zpe_is_a_family_row_on_matching_opt_freq():
    left = _run(
        provider="xtb",
        calc_type="opt_freq",
        method_basis="GFN2-xTB",
        input_molblock=_ETHANOL_A,
        descriptors=[_descriptor("xtb.zero_point_energy", 0.03, units="Hartree")],
    )
    right = _run(
        provider="xtb",
        calc_type="opt_freq",
        method_basis="GFN2-xTB",
        input_molblock=_ETHANOL_A,
        descriptors=[_descriptor("xtb.zero_point_energy", 0.04, units="Hartree")],
    )
    labels = [row.label for row in quantum_family_rows(left, right)]
    assert labels == ["Zero-point energy"]
    other_method = _run(
        provider="xtb",
        calc_type="opt_freq",
        method_basis="GFN1-xTB",
        input_molblock=_ETHANOL_A,
        descriptors=[_descriptor("xtb.zero_point_energy", 0.04, units="Hartree")],
    )
    assert quantum_family_rows(left, other_method) == []


def test_orca_versus_xtb_has_no_shared_entropy_or_zpe_row():
    orca = _run(
        provider="orca",
        calc_type="opt_freq",
        input_molblock=_ETHANOL_A,
        descriptors=[
            _descriptor("orca.entropy_term", 0.02, units="Hartree"),
            _descriptor("xtb.zero_point_energy", 0.03, units="Hartree"),
        ],
    )
    xtb = _run(
        provider="xtb",
        calc_type="opt_freq",
        method_basis="B3LYP def2-SVP",
        input_molblock=_ETHANOL_A,
        descriptors=[
            _descriptor("orca.entropy_term", 0.01, units="Hartree"),
            _descriptor("xtb.zero_point_energy", 0.04, units="Hartree"),
        ],
    )
    labels = [row.label for row in quantum_family_rows(orca, xtb)]
    assert "Entropy term" not in labels
    assert "Zero-point energy" not in labels


def test_missing_entropy_omits_only_that_quantity():
    left = _run(
        provider="orca",
        calc_type="opt_freq",
        input_molblock=_ETHANOL_A,
        descriptors=[
            _descriptor("orca.enthalpy", -76.2, units="Hartree"),
            _descriptor("orca.entropy_term", 0.02, units="Hartree"),
        ],
    )
    right = _run(
        provider="orca",
        calc_type="opt_freq",
        input_molblock=_ETHANOL_A,
        descriptors=[_descriptor("orca.enthalpy", -76.0, units="Hartree")],
    )
    assert [row.label for row in quantum_family_rows(left, right)] == ["Enthalpy"]


def test_scf_skipped_when_method_or_state_differs():
    base = _scf("orca", -76.4)
    assert quantum_family_rows(base, _scf("psi4", -76.3, method_basis="PBE0 def2-SVP")) == []
    assert quantum_family_rows(base, _scf("psi4", -76.3, charge=1)) == []
    assert quantum_family_rows(base, _scf("psi4", -76.3, multiplicity=3)) == []
    assert quantum_family_rows(base, _scf("psi4", -76.3, solvent="water")) == []


def test_scf_tabulates_different_conformer_geometries():
    left = _scf("orca", -76.4, input_fingerprint="geom-a", input_molblock=_ETHANOL_A)
    right = _scf("psi4", -76.3, input_fingerprint="geom-b", input_molblock=_ETHANOL_B)
    assert quantum_runs_comparable(left, right) == ""
    rows = quantum_family_rows(left, right)
    assert [row.label for row in rows] == ["SCF energy"]
    assert rows[0].delta == pytest.approx(0.1)


def test_scf_skipped_when_same_uuid_has_different_constitution():
    left = _scf("orca", -76.4, input_fingerprint="ethanol", input_molblock=_ETHANOL_A)
    right = _scf("psi4", -76.3, input_fingerprint="methanol", input_molblock=_METHANOL)
    assert quantum_runs_comparable(left, right) == ""
    assert quantum_family_rows(left, right) == []


def test_scf_skipped_when_same_uuid_has_different_stereochemistry():
    left = _scf("orca", -76.4, input_fingerprint="r", input_molblock=_BUTAN_2_OL_R)
    right = _scf("psi4", -76.3, input_fingerprint="s", input_molblock=_BUTAN_2_OL_S)
    assert quantum_family_rows(left, right) == []


def test_scf_skipped_when_same_uuid_has_different_isotope():
    left = _scf("orca", -76.4, input_fingerprint="c12", input_molblock=_ETHANOL_A)
    right = _scf("psi4", -76.3, input_fingerprint="c13", input_molblock=_ETHANOL_13C)
    assert quantum_family_rows(left, right) == []


def test_submitted_structure_identity_keeps_isotopes_and_refuses_empty():
    assert submitted_structure_identity("") == ""
    assert submitted_structure_identity(_ETHANOL_A) == submitted_structure_identity(_ETHANOL_B)
    assert submitted_structure_identity(_ETHANOL_A) != submitted_structure_identity(_METHANOL)
    assert submitted_structure_identity(_ETHANOL_A) != submitted_structure_identity(_ETHANOL_13C)
    assert submitted_structure_identity(_BUTAN_2_OL_R) != submitted_structure_identity(_BUTAN_2_OL_S)


def test_scf_skipped_when_input_molblock_is_missing():
    left = _scf("orca", -76.4, input_fingerprint="a", input_molblock="")
    right = _scf("psi4", -76.3, input_fingerprint="b", input_molblock="")
    assert quantum_family_rows(left, right) == []


def test_scf_is_not_shown_across_molecules():
    left = _scf("orca", -76.4, molecule="m1")
    right = _scf("psi4", -76.3, molecule="m2")
    assert quantum_runs_comparable(left, right) == ""
    assert quantum_family_rows(left, right) == []


def test_psi4_sp_has_no_homo_row():
    orca = _run(
        input_molblock=_ETHANOL_A,
        descriptors=[
            _descriptor("orca.scf_energy", -76.4, units="Hartree"),
            _descriptor("orca.homo_energy", -0.4),
        ],
    )
    psi4 = _scf("psi4", -76.3)
    labels = [row.label for row in quantum_family_rows(orca, psi4)]
    assert labels == ["SCF energy"]


def _result_store(*records):
    from openchem.chem.engine import ChemistryEngine
    from openchem.domain.molecule import MoleculeModel
    from openchem.domain.project import ProjectModel
    from openchem.events.base import EventBus
    from openchem.services.result_store_service import ResultStoreService

    project = ProjectModel(name="p")
    project.molecules.extend(
        [
            MoleculeModel(uuid="m1", display_name="water"),
            MoleculeModel(uuid="m2", display_name="ethanol"),
        ]
    )
    service = ResultStoreService(EventBus(), ChemistryEngine())
    service.set_project(project)
    for record in records:
        if isinstance(record, PropertyExecution):
            service.property_executions.record(record)
        else:
            service.qc_runs.record(record)
    return service, project


class _CompareHost:
    def __init__(self, packed):
        from types import SimpleNamespace

        from openchem.app.main_window import MainWindow

        service, project = packed
        self._services = SimpleNamespace(result_store_service=service)
        self._session = SimpleNamespace(project=project)
        self.named = []
        self.atoms = []
        self._on_history_compare_requested = MainWindow._on_history_compare_requested.__get__(self)
        self._show_quantum_history_compare = MainWindow._show_quantum_history_compare.__get__(self)
        self._show_ordinary_history_compare = MainWindow._show_ordinary_history_compare.__get__(self)
        self._history_compare_column_label = MainWindow._history_compare_column_label.__get__(self)

    def _history_molecule_name(self, molecule_uuid: str) -> str:
        from openchem.app.main_window import MainWindow

        return MainWindow._history_molecule_name(self, molecule_uuid)

    def _show_named_history_compare(self, rows, left, right, empty_message=None) -> None:
        self.named.append((rows, left, right, empty_message))

    def _show_atom_history_compare(self, outcome, symbols, molecule_uuid) -> None:
        self.atoms.append((outcome, symbols, molecule_uuid))


def test_compare_request_refuses_mixed_without_opening_the_table(qapp, monkeypatch):
    from types import SimpleNamespace

    from PySide6.QtWidgets import QInputDialog, QMessageBox

    execution = _execution()
    run = _run()
    host = _CompareHost(_result_store(execution, run))
    messages = []

    def choose(_parent, _title, _label, items, *_args, **_kwargs):
        return next(item for item in items if item.startswith("Quantum ·")), True

    monkeypatch.setattr(QInputDialog, "getItem", staticmethod(choose))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *_a, **_k: messages.append(_a[2])))
    host._on_history_compare_requested(
        SimpleNamespace(history_kind="execution", history_id=execution.execution_id)
    )
    assert host.named == []
    assert messages == [MIXED_UNAPPROVED]


def test_mixed_compare_opens_one_named_row_in_both_orientations(qapp, allow, monkeypatch):
    from types import SimpleNamespace

    from PySide6.QtWidgets import QInputDialog

    execution = _execution()
    run = _run()
    host = _CompareHost(_result_store(execution, run))

    def choose_quantum(_parent, _title, _label, items, *_args, **_kwargs):
        return next(item for item in items if item.startswith("Quantum ·")), True

    def choose_property(_parent, _title, _label, items, *_args, **_kwargs):
        return next(item for item in items if item.startswith("Property ·")), True

    monkeypatch.setattr(QInputDialog, "getItem", staticmethod(choose_quantum))
    host._on_history_compare_requested(
        SimpleNamespace(history_kind="execution", history_id=execution.execution_id)
    )
    monkeypatch.setattr(QInputDialog, "getItem", staticmethod(choose_property))
    host._on_history_compare_requested(
        SimpleNamespace(history_kind="quantum", history_id=run.run_id)
    )
    assert len(host.named) == 2
    first_rows, first_left, first_right, _empty = host.named[0]
    second_rows, second_left, second_right, _ = host.named[1]
    assert first_rows[0].delta == pytest.approx(-0.1)
    assert second_rows[0].delta == pytest.approx(0.1)
    assert isinstance(first_left, PropertyExecution)
    assert isinstance(first_right, QuantumChemistryRun)
    assert isinstance(second_left, QuantumChemistryRun)
    assert isinstance(second_right, PropertyExecution)


def test_ordinary_compare_still_opens_named_table(qapp):
    left = _execution(execution_id="exec-a")
    right = _execution(execution_id="exec-b", outputs=[_stored(_descriptor(value=-0.5))])
    host = _CompareHost(_result_store(left, right))
    host._show_ordinary_history_compare(left, right)
    assert host.atoms == []
    assert len(host.named) == 1
    assert host.named[0][0][0].delta == pytest.approx(-0.2)


def test_quantum_named_compare_still_opens_named_table(qapp):
    left = _scf("orca", -76.4)
    right = _scf("psi4", -76.3)
    host = _CompareHost(_result_store(left, right))
    host._show_quantum_history_compare(left, right)
    assert host.atoms == []
    assert len(host.named) == 1
    rows, named_left, named_right, empty = host.named[0]
    assert [row.label for row in rows] == ["SCF energy"]
    assert empty is not None and "family quantity" in empty
    assert "orca" in host._history_compare_column_label(named_left, named_right)
    assert "psi4" in host._history_compare_column_label(named_right, named_left)


def test_opt_freq_named_compare_shows_thermo_rows(qapp):
    left = _thermo("orca", -76.2, -76.1, scf=-76.4)
    right = _thermo("orca", -76.0, -75.9, scf=-76.3)
    host = _CompareHost(_result_store(left, right))
    host._show_quantum_history_compare(left, right)
    assert host.atoms == []
    rows, _named_left, _named_right, empty = host.named[0]
    assert [row.label for row in rows] == ["SCF energy", "Enthalpy", "Gibbs free energy"]
    assert empty == QUANTUM_FAMILY_EMPTY


def test_quantum_empty_family_uses_the_family_sentence(qapp):
    left = _run(descriptors=[_descriptor("orca.other", 1.0, units="Hartree")])
    right = _run(descriptors=[_descriptor("orca.other", 2.0, units="Hartree")])
    host = _CompareHost(_result_store(left, right))
    host._show_quantum_history_compare(left, right)
    rows, _left, _right, empty = host.named[0]
    assert rows == []
    assert empty == QUANTUM_FAMILY_EMPTY


def test_quantum_nmr_opens_the_per_atom_dialog(qapp):
    from openchem.domain.scientific_result import NMRSpectrumResult

    spectrum_a = NMRSpectrumResult(
        spectrum_type="nmr_13c",
        name="NMR",
        units="ppm",
        method="orca",
        molecule_uuid="m1",
        values={0: 120.0},
        elements={0: "C"},
    )
    spectrum_b = NMRSpectrumResult(
        spectrum_type="nmr_13c",
        name="NMR",
        units="ppm",
        method="orca",
        molecule_uuid="m1",
        values={0: 118.0},
        elements={0: "C"},
    )
    from dataclasses import replace

    left = _run(calc_type="nmr", extras={"spectrum": spectrum_a})
    right = replace(
        _run(calc_type="nmr", extras={"spectrum": spectrum_b}),
        method_basis="PBE0 def2-SVP",
    )
    host = _CompareHost(_result_store(left, right))
    host._show_quantum_history_compare(left, right)
    assert host.named == []
    assert len(host.atoms) == 1
    assert host.atoms[0][2] == "m1"


def test_cross_molecule_column_labels_name_both_molecules(qapp, monkeypatch):
    from openchem.app.main_window import MainWindow

    execution = _execution(molecule="m1")
    run = _run(molecule="m2")
    host = _CompareHost(_result_store(execution, run))
    left = MainWindow._history_compare_column_label(host, execution, run)
    right = MainWindow._history_compare_column_label(host, run, execution)
    assert "water" in left
    assert "ethanol" in right
    assert "Property ·" in left
    assert "Quantum ·" in right


def test_named_dialog_shows_the_mixed_row(qapp, allow):
    from openchem.ui.dialogs.compare_results_dialog import NamedValueCompareDialog

    match = match_mixed_history(_execution(), _run())
    row = named_row_from_mixed_match(match, ordinary_on_left=True)
    dialog = NamedValueCompareDialog(
        [row],
        "Property · toy · huckel · exec-1",
        "Quantum · sp · orca · B3LYP def2-SVP · abcd1234",
        "water vs ethanol",
    )
    assert dialog._table.rowCount() == 1
    assert dialog._table.item(0, 0).text() == "HOMO energy"
    assert "Property ·" in dialog._table.horizontalHeaderItem(1).text()
    assert "Quantum ·" in dialog._table.horizontalHeaderItem(2).text()
    assert "water vs ethanol" in dialog.windowTitle()

