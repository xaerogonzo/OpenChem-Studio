"""A refusal has a KIND, and the kind is what a person can act on.

Found in a live session on 1,3-dinitro-1,3-diazetidine: Detonation read
"Not applicable" -- a permanent, neutral statement that the method does not
cover the molecule -- when the truth was that the method covers it and wants
two numbers. Three different situations (a limit, a missing input, a missing
installation) were one word, so the launcher could not tell a person which of
them they were in. `domain.refusal_kinds` is the vocabulary; these tests pin
what it means and that it survives the trip from a calculator to the chip.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QThreadPool
from rdkit import Chem

from openchem.chem import energetics as E
from openchem.chem.descriptor_providers import CALCULATOR_DEFINITIONS
from openchem.chem.engine import ChemistryEngine
from openchem.domain import calculator as calculator_module
from openchem.domain import refusal_kinds as K
from openchem.domain.calculator import (
    CalculationRefusal,
    CalculationRequest,
    CalculatorDefinition,
    RegistryExecution,
)
from openchem.domain.common import CacheState
from openchem.domain.molecule import MoleculeModel
from openchem.domain.refusal_kinds import (
    InputProblem,
    MissingInput,
    RefusalKind,
    missing_inputs_of,
    refusal_kind_of,
    refusal_kind_of_result,
    refusal_parameters,
)
from openchem.domain.result_status import (
    FAILED,
    INAPPLICABLE,
    NEEDS_INPUT,
    NEEDS_SETUP,
    status_of,
)
from openchem.events.base import EventBus
from openchem.events.events import ResultRecorded
from openchem.services.calculator_registry import CalculatorRegistry
from openchem.services.descriptor_service import DescriptorService

TATB = "Nc1c(N)c([N+](=O)[O-])c(N)c([N+](=O)[O-])c1[N+](=O)[O-]"
TATB_ENTHALPY = -37.05
NITROGLYCERIN = "C(C(CO[N+](=O)[O-])O[N+](=O)[O-])O[N+](=O)[O-]"


# --- the table ------------------------------------------------------------


def test_the_scope_layer_codes_still_import_from_where_every_module_takes_them():
    """The constants MOVED here, and every calculator module still imports
    them from `domain.calculator` -- so the move must be invisible."""
    for name in (
        "MULTICOMPONENT_UNSUPPORTED", "METAL_CONTAINING_UNSUPPORTED", "NO_ORGANIC_COMPONENT",
        "ELEMENT_OUTSIDE_PARAMETER_SET", "INPUT_REQUIRED", "SIDECAR_NOT_CONFIGURED",
    ):
        assert getattr(calculator_module, name) is getattr(K, name), name


def test_a_code_nobody_classified_is_not_a_limit():
    """**THE FAIL-CLOSED HALF.** A new refusal code that reaches the launcher
    unclassified must read as something to look at, never as a permanent,
    ignorable "the method does not apply"."""
    assert refusal_kind_of("A_CODE_NOBODY_CLASSIFIED") is None
    assert refusal_kind_of("") is None
    assert refusal_kind_of(None) is None


def test_the_three_kinds_are_the_three_things_a_person_can_act_on():
    assert refusal_kind_of(K.MULTICOMPONENT_UNSUPPORTED) is RefusalKind.LIMIT
    assert refusal_kind_of(K.INPUT_REQUIRED) is RefusalKind.NEEDS_INPUT
    assert refusal_kind_of(K.NO_LOADING_DENSITY) is RefusalKind.NEEDS_INPUT
    assert refusal_kind_of(K.SIDECAR_NOT_CONFIGURED) is RefusalKind.NEEDS_SETUP


def test_a_fault_is_the_absence_of_a_kind_not_a_fourth_member():
    """There is deliberately no FAULT kind: "not one of the three named
    things" is what makes a refusal a fault."""
    assert {kind.name for kind in RefusalKind} == {"LIMIT", "NEEDS_INPUT", "NEEDS_SETUP"}


# --- CalculationRefusal resolves a kind, and never defaults to LIMIT --------


def test_an_unclassified_refusal_is_a_fault_even_without_saying_so():
    """It used to be a permanent limit, because `inapplicable` defaulted to
    True -- so a code nobody had classified read as "does not apply"."""
    refusal = CalculationRefusal("SOME_NEW_CODE", "summary", "detail")
    assert refusal.kind is None
    assert refusal.inapplicable is False


def test_an_explicit_kind_wins_over_the_table_and_the_flag():
    refusal = CalculationRefusal(
        "SOME_NEW_CODE", "s", "d", kind=RefusalKind.NEEDS_INPUT, inapplicable=True,
        missing_inputs=(MissingInput("density", "g/cm3"),),
    )
    assert refusal.kind is RefusalKind.NEEDS_INPUT
    assert refusal.inapplicable is False, "a NEEDS_INPUT refusal is not a limit of the method"
    assert refusal.missing_inputs == (MissingInput("density", "g/cm3"),)


def test_the_table_supplies_a_kind_when_the_producer_declares_none():
    assert CalculationRefusal(K.INPUT_REQUIRED, "s", "d").kind is RefusalKind.NEEDS_INPUT
    limit = CalculationRefusal(K.MULTICOMPONENT_UNSUPPORTED, "s", "d")
    assert limit.kind is RefusalKind.LIMIT and limit.inapplicable is True


def test_the_legacy_flag_still_means_a_limit_when_the_code_is_unknown():
    """The producers that pass `inapplicable=True` today (the scope layer,
    Jensen, MMFF) are unmoved."""
    assert CalculationRefusal("X", "s", "d", inapplicable=True).kind is RefusalKind.LIMIT
    assert CalculationRefusal("X", "s", "d", inapplicable=False).kind is None


def test_a_kind_derived_only_from_the_legacy_flag_says_so():
    """It still reads as a limit; what changes is that it is NOT counted as
    classified, so the census can list the code."""
    assert CalculationRefusal("X", "s", "d", inapplicable=True).classified is False
    assert CalculationRefusal("X", "s", "d").classified is False
    assert CalculationRefusal(K.INPUT_REQUIRED, "s", "d").classified is True, "found in the table"
    assert CalculationRefusal("X", "s", "d", kind=RefusalKind.LIMIT).classified is True, "declared"
    parameters = refusal_parameters("X", RefusalKind.LIMIT, classified=False)
    assert parameters["refusal_classified"] is False
    assert "refusal_classified" not in refusal_parameters("X", RefusalKind.LIMIT)


# --- what travels on the result ---------------------------------------------


def test_the_carrier_is_plain_json_because_provenance_is_persisted():
    import json

    parameters = refusal_parameters(
        K.NO_LOADING_DENSITY, RefusalKind.NEEDS_INPUT,
        (MissingInput("loading_density_g_cm3", "g/cm3"),
         MissingInput("enthalpy_of_formation_kcal_mol", "kcal/mol", InputProblem.INVALID)),
    )
    assert json.loads(json.dumps(parameters)) == parameters
    assert parameters["refusal"] == K.NO_LOADING_DENSITY
    assert parameters["refusal_kind"] == "needs_input"


def test_a_missing_input_survives_its_own_round_trip():
    item = MissingInput("enthalpy_of_formation_kcal_mol", "kcal/mol", InputProblem.OUT_OF_DOMAIN)
    assert MissingInput.from_dict(item.to_dict()) == item


class _Carrier:
    """A result-shaped object: only `provenance.parameters` is read."""

    def __init__(self, parameters):
        self.provenance = type("P", (), {"parameters": parameters})()


def test_a_corrupt_kind_is_not_trusted_as_anything():
    assert refusal_kind_of_result(_Carrier({"refusal_kind": "needs_input"})) is RefusalKind.NEEDS_INPUT
    assert refusal_kind_of_result(_Carrier({"refusal_kind": "a_kind_from_the_future"})) is None
    assert refusal_kind_of_result(_Carrier({})) is None
    assert refusal_kind_of_result(object()) is None


def test_a_result_naming_only_a_classified_code_reads_as_its_kind():
    """The producers that build their own result (`alignment`, `markush`, the
    pKa sidecar path) write only `{"refusal": INPUT_REQUIRED}`, and read as
    what they are without a line of change in any of them."""
    assert refusal_kind_of_result(_Carrier({"refusal": K.INPUT_REQUIRED})) is RefusalKind.NEEDS_INPUT
    assert refusal_kind_of_result(_Carrier({"refusal": K.SIDECAR_NOT_CONFIGURED})) is RefusalKind.NEEDS_SETUP
    assert refusal_kind_of_result(_Carrier({"refusal": "UNCLASSIFIED"})) is None
    # A successful Kamlet-Jacobs result records `"refusal": None`.
    assert refusal_kind_of_result(_Carrier({"refusal": None})) is None
    # A corrupt declared kind falls through to the code rather than being trusted.
    corrupt = _Carrier({"refusal_kind": "from_the_future", "refusal": K.INPUT_REQUIRED})
    assert refusal_kind_of_result(corrupt) is RefusalKind.NEEDS_INPUT


def test_a_malformed_missing_input_entry_is_skipped_not_fatal():
    carrier = _Carrier({"missing_inputs": [{"parameter": "a", "units": "u"}, {"units": "no parameter"}, "junk"]})
    assert missing_inputs_of(carrier) == (MissingInput("a", "u"),)
    assert missing_inputs_of(_Carrier({"missing_inputs": "not a list"})) == ()


# --- status_of --------------------------------------------------------------


class _Result:
    def __init__(self, *, kind=None, inapplicable=False, failed=True, missing=()):
        self.cache_state = CacheState.FAILED if failed else CacheState.COMPLETED
        self.inapplicable = inapplicable
        self.structure_version = 1
        parameters = refusal_parameters("C", kind, missing) if kind is not None else {}
        self.provenance = type("P", (), {"parameters": parameters})()


def test_a_needs_input_refusal_is_not_reported_as_a_fault_or_a_limit():
    """It travels as FAILED, exactly as a limit does -- and both of the
    statuses that would otherwise claim it are wrong."""
    result = _Result(kind=RefusalKind.NEEDS_INPUT)
    assert result.cache_state is CacheState.FAILED, "setup: a refusal travels as FAILED"
    assert status_of(result, structure_version=1) == NEEDS_INPUT
    assert status_of(result, structure_version=1) not in (FAILED, INAPPLICABLE)


def test_a_needs_setup_refusal_is_its_own_status():
    assert status_of(_Result(kind=RefusalKind.NEEDS_SETUP), structure_version=1) == NEEDS_SETUP


def test_a_declared_limit_is_inapplicable_even_without_the_legacy_flag():
    assert status_of(_Result(kind=RefusalKind.LIMIT), structure_version=1) == INAPPLICABLE


def test_a_plain_failure_with_no_kind_is_still_a_failure():
    """The narrow half: "anything FAILED needs input" satisfies the tests
    above and silently stops reporting real faults."""
    assert status_of(_Result(), structure_version=1) == FAILED


# --- Kamlet-Jacobs: the case that found this --------------------------------


def _detonation(smiles: str, **parameters) -> CalculationRefusal:
    mol = Chem.MolFromSmiles(smiles)
    with pytest.raises(CalculationRefusal) as raised:
        E.compute_detonation(mol, "uuid-1", parameters)
    return raised.value


def test_a_covered_molecule_with_no_inputs_needs_input_and_says_both():
    refusal = _detonation(TATB)
    assert refusal.kind is RefusalKind.NEEDS_INPUT
    assert refusal.inapplicable is False
    assert [item.parameter for item in refusal.missing_inputs] == [
        "loading_density_g_cm3", "enthalpy_of_formation_kcal_mol",
    ], "one dialog, not one round trip per missing value"
    assert [item.units for item in refusal.missing_inputs] == ["g/cm3", "kcal/mol"]
    assert "LOADING DENSITY" in refusal.detail and "enthalpy of formation" in refusal.detail
    assert refusal.summary == "Needs a loading density and a condensed-phase enthalpy of formation"


def test_only_what_is_still_missing_is_named():
    refusal = _detonation(TATB, loading_density_g_cm3=1.8)
    assert [item.parameter for item in refusal.missing_inputs] == ["enthalpy_of_formation_kcal_mol"]
    assert refusal.code == K.NO_ENTHALPY_OF_FORMATION
    refusal = _detonation(TATB, enthalpy_of_formation_kcal_mol=TATB_ENTHALPY)
    assert [item.parameter for item in refusal.missing_inputs] == ["loading_density_g_cm3"]
    assert refusal.code == K.NO_LOADING_DENSITY


def test_a_negative_density_is_invalid_not_missing():
    refusal = _detonation(TATB, loading_density_g_cm3=-1.0, enthalpy_of_formation_kcal_mol=TATB_ENTHALPY)
    assert refusal.missing_inputs == (
        MissingInput("loading_density_g_cm3", "g/cm3", InputProblem.INVALID),
    )


def test_the_permanent_refusal_is_reported_before_the_fixable_one():
    """**NITROGLYCERIN IS OVER-OXIDISED, AND NO INPUT CAN FIX THAT.** The
    check needs only the formula, so it comes first: asking a person for a
    density and an enthalpy for a compound the method cannot use would send
    them looking for two numbers for nothing."""
    refusal = _detonation(NITROGLYCERIN)
    assert refusal.kind is RefusalKind.LIMIT
    assert refusal.inapplicable is True
    assert refusal.code == E.DetonationRefusal.OUTSIDE_THE_ARBITRARY.name
    assert refusal.missing_inputs == ()
    assert "over-oxidised" in refusal.detail


def test_a_non_chno_compound_is_a_limit():
    refusal = _detonation("ClCCl", loading_density_g_cm3=1.5, enthalpy_of_formation_kcal_mol=0.0)
    assert refusal.kind is RefusalKind.LIMIT and refusal.code == "NOT_CHNO"


def test_every_named_input_is_a_real_parameter_of_the_calculator():
    """The names are what a settings dialog focuses, so one that drifts from
    `CalculatorParameter.name` would name a field that does not exist."""
    definition = next(d for d in CALCULATOR_DEFINITIONS if d.calculator_id == "detonation")
    declared = {p.name for p in definition.parameters}
    for name, _units in E.DETONATION_INPUTS.values():
        assert name in declared, name


def test_the_pure_layer_is_unmoved():
    """`detonation()` keeps returning its enum, which the formulation path
    and thirty tests read; only the CALCULATOR raises."""
    assert E.detonation(Chem.MolFromSmiles(TATB), None, TATB_ENTHALPY).refusal is (
        E.DetonationRefusal.NO_LOADING_DENSITY
    )


# --- through the real service: what the chip is handed ----------------------


def _run(qapp, calculator_id, smiles, parameters=None, *, registry=None):
    bus = EventBus()
    engine = ChemistryEngine()
    if registry is None:
        registry = CalculatorRegistry()
        for definition in CALCULATOR_DEFINITIONS:
            registry.register(definition)
    service = DescriptorService(bus, engine, calculator_registry=registry)
    model = MoleculeModel()
    engine.set_structure_from_smiles(model, smiles)
    published = []
    # What the service RECORDS, whatever the result's shape: a refusal reaches
    # the reader as a per-atom dataset, but a producer that builds its own
    # result publishes an alert or a report instead.
    bus.subscribe(ResultRecorded, lambda e: published.append(e.stored.result))
    service.run_calculator(
        model, CalculationRequest(calculator_id=calculator_id, molecule_uuid=model.uuid,
                                  parameters=parameters or {}),
    )
    QThreadPool.globalInstance().waitForDone(5000)
    for _ in range(50):
        qapp.processEvents()
    assert len(published) == 1
    return published[0]


def test_detonation_with_no_inputs_reaches_the_chip_as_needs_input(qapp):
    """The whole point, end to end: real calculator, real service, and the
    word `status_of` gives the launcher."""
    result = _run(qapp, "detonation", TATB)
    assert result.cache_state is CacheState.FAILED
    assert result.inapplicable is False
    assert status_of(result, structure_version=0) == NEEDS_INPUT
    assert [i.parameter for i in missing_inputs_of(result)] == [
        "loading_density_g_cm3", "enthalpy_of_formation_kcal_mol",
    ]


def test_detonation_on_an_over_oxidised_compound_reaches_the_chip_as_a_limit(qapp):
    result = _run(qapp, "detonation", NITROGLYCERIN)
    assert status_of(result, structure_version=0) == INAPPLICABLE


def _refusing_registry(refusal: CalculationRefusal) -> CalculatorRegistry:
    def compute(mol, molecule_uuid, params):
        raise refusal

    registry = CalculatorRegistry()
    registry.register(CalculatorDefinition(
        calculator_id="refuser", display_name="Refuser", category="test", description="",
        execution=RegistryExecution(compute=compute),
    ))
    return registry


def test_an_unconfigured_sidecar_reaches_the_chip_as_needs_setup(qapp):
    result = _run(
        qapp, "refuser", "CCO",
        registry=_refusing_registry(CalculationRefusal(K.SIDECAR_NOT_CONFIGURED, "No interpreter", "Configure it.")),
    )
    assert status_of(result, structure_version=0) == NEEDS_SETUP


def test_an_unclassified_refusal_reaches_the_chip_as_a_failure(qapp, caplog):
    """And says so in the log: at WARNING, so a driven run's ledger reports
    it rather than a code nobody classified passing as a quiet limit."""
    import logging

    with caplog.at_level(logging.WARNING, logger="openchem.chemistry"):
        result = _run(
            qapp, "refuser", "CCO",
            registry=_refusing_registry(CalculationRefusal("BRAND_NEW_CODE", "New", "A new code.")),
        )
    assert status_of(result, structure_version=0) == FAILED
    assert any("unclassified" in record.getMessage() for record in caplog.records)


def test_a_producer_that_builds_its_own_result_reads_as_needs_input(qapp):
    """Lewis Adduct with no partner molecule returns its own FAILED alert
    naming `INPUT_REQUIRED` -- no kind, and `inapplicable == False`, so it
    read as "Failed". It is the same situation as Kamlet-Jacobs's, and the
    table is what says so."""
    result = _run(qapp, "lewis_adduct", "CCO")
    assert result.cache_state is CacheState.FAILED and result.inapplicable is False
    assert result.provenance.parameters["refusal"] == K.INPUT_REQUIRED
    assert status_of(result, structure_version=0) == NEEDS_INPUT


def test_a_summarised_refusal_keeps_its_kind_for_the_panel(qapp):
    """**FOUND BY DRIVING THE APP, WITH EVERY TEST ABOVE GREEN.** The panel
    does not file the raw result: it files `summarise(result)`, a
    `ResultSummaryView`, and `status_of` reads a refusal's kind off
    `provenance.parameters`, which that view did not carry. Detonation was
    correctly refused as NEEDS_INPUT by the service and still read "Failed"
    in Properties -- `expect_results` in
    benchmarks/visual/energetic_nitramine_ledger.json is the check that
    caught it, and this is the same claim at unit level."""
    from openchem.ui.result_adapters import summarise

    result = _run(qapp, "detonation", TATB)
    summary = summarise(result, result_id="detonation", name="Detonation", category="energetic")
    assert status_of(summary, structure_version=0) == NEEDS_INPUT
    assert missing_inputs_of(summary) == missing_inputs_of(result) != ()


def test_a_refused_alert_keeps_its_refusal_when_it_becomes_a_report():
    """`report_from_alert` dropped `inapplicable` and `error_summary`, so a
    refused alert read as a fault with no short form."""
    from openchem.chem.report_adapter import report_from_alert
    from openchem.domain.scientific_result import AlertResult

    alert = AlertResult(
        alert_id="a", name="A", molecule_uuid="u", cache_state=CacheState.FAILED,
        error="the full sentence", error_summary="short", inapplicable=True,
    )
    report = report_from_alert(alert)
    assert report.inapplicable is True and report.error_summary == "short"
    assert status_of(report, structure_version=0) == INAPPLICABLE
