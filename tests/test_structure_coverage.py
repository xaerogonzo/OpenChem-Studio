"""Whether the structure on screen is something a calculator takes, said before it is run.

Design: `docs/STRUCTURE_COVERAGE_DESIGN.md`. **THE CLAIM IS ONLY AS GOOD AS ITS AGREEMENT WITH THE REFUSAL**, so
most of this file is one question asked many ways: over a panel of structures, does the hook say what the real
calculator then does? A hook that kept a rule of its own would pass its own unit tests and drift.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QCoreApplication
from rdkit import Chem

from openchem.app.settings import STRUCTURE_COVERAGE, Settings
from openchem.bootstrap import build_service_container
from openchem.chem import bond_dissociation, coverage_hooks, energetics, hansen, proton_affinity
from openchem.chem.engine import ChemistryEngine
from openchem.domain.calculator import CalculationRefusal, CalculatorDefinition, CalculatorScope, RegistryExecution
from openchem.domain.calculator import Aggregation, ComponentSelection, MethodDomain
from openchem.domain.common import CacheState
from openchem.domain.molecule import MoleculeModel
from openchem.domain.project import ProjectModel
from openchem.domain.structure_coverage import Coverage, CoverageKind, as_coverage, tooltip_sentence
from openchem.events.base import EventBus
from openchem.events.events import MoleculeSelected, RecalculationDue
from openchem.services.calculator_registry import CalculatorRegistry
from openchem.ui.panels.property_panel import PropertyPanel
from tests.conftest import dispose

#: Structures chosen for SHAPE, as the census panel is: an ordinary molecule, the classes each hook refuses, a
#: salt, a metal, a polyoxyethylene chain, a ring tertiary amine, a nitro compound, a 12-heavy-atom chain.
PANEL = {
    "ethanol": "CCO",
    "benzene": "c1ccccc1",
    "nitrobenzene": "O=[N+]([O-])c1ccccc1",
    "thioethanol": "CCS",
    "n_methylpyrrolidine": "C1CN(C)CC1",
    "sodium_acetate": "CC(=O)[O-].[Na+]",
    "peg_dodecyl": "CCCCCCCCCCCCOCCOCCOCCOCCOCCOCCO",
    "triethylene_glycol": "OCCOCCOCCO",
    "pyridinium": "c1cc[nH+]cc1",
    "radical": "[CH3]",
    "ferrocene_like": "[Fe+2].c1cc[cH-]c1.c1cc[cH-]c1",
    "twelve_heavy_chain": "CCCCCCCCCCCC",
}


def _mol(smiles: str) -> Chem.Mol:
    mol = Chem.MolFromSmiles(smiles)
    assert mol is not None, smiles
    return mol


def _ran_and_refused(registry: CalculatorRegistry, calculator_id: str, smiles: str) -> bool | None:
    """True if the real calculator declined this structure as a limit, False if it ran, None if it faulted."""
    mol = _mol(smiles)
    try:
        result = registry.compute(calculator_id, mol, "u", {})
    except CalculationRefusal as refusal:
        return refusal.inapplicable
    if getattr(result, "cache_state", None) is CacheState.FAILED:
        return True if getattr(result, "inapplicable", False) else None
    return False


@pytest.fixture(scope="module")
def container():
    return build_service_container()


@pytest.fixture(scope="module")
def registry(container):
    return container.calculator_registry


# --- the value ------------------------------------------------------------------------------


def test_a_refusal_or_a_caveat_needs_its_sentence():
    with pytest.raises(ValueError):
        Coverage.refuses("  ")
    with pytest.raises(ValueError):
        Coverage.caveat("")
    assert Coverage.covered().reason == ""


def test_a_plain_string_is_the_old_refusal_and_everything_else_is_no_claim():
    assert as_coverage("why not") == Coverage.refuses("why not")
    for nothing in ("", "   ", None, 0, object()):
        assert as_coverage(nothing) is None
    covered = Coverage.covered()
    assert as_coverage(covered) is covered


# --- the registry: no claim unless the code that refuses made it ----------------------------


def _registry_with(**extra) -> CalculatorRegistry:
    registry = CalculatorRegistry()
    registry.register(
        CalculatorDefinition(
            calculator_id="probe",
            display_name="Probe",
            category="topology",
            description="Probe.",
            execution=RegistryExecution(compute=lambda _mol, _uuid, _params: None),
            **extra,
        )
    )
    return registry


def test_a_hook_that_raises_makes_no_claim():
    def boom(_mol):
        raise RuntimeError("the hook broke")

    assert _registry_with(preflight=boom).coverage("probe", _mol("CCO")) is None


def test_a_hook_with_nothing_to_say_makes_no_claim_and_a_calculator_without_one_the_same():
    assert _registry_with(preflight=lambda _mol: "").coverage("probe", _mol("CCO")) is None
    assert _registry_with(preflight=lambda _mol: None).coverage("probe", _mol("CCO")) is None
    assert _registry_with().coverage("probe", _mol("CCO")) is None
    assert _registry_with().coverage("not registered", _mol("CCO")) is None


def test_a_hook_is_handed_a_copy_so_it_cannot_change_what_the_next_one_sees():
    seen = []

    def vandal(mol):
        seen.append(mol)
        mol.RemoveAllConformers()
        Chem.Kekulize(mol, clearAromaticFlags=True)
        return Coverage.covered()

    mol = _mol("c1ccccc1")
    _registry_with(preflight=vandal).coverage("probe", mol)
    assert seen[0] is not mol
    assert all(a.GetIsAromatic() for a in mol.GetAtoms())


def test_the_scope_refuses_a_salt_for_every_pure_substance_calculator_with_no_hook(registry):
    """The free source: `components.select` is the call a run makes, so its refusal is the claim."""
    salt = _mol("CC(=O)[O-].[Na+]")
    scoped = [
        d for d in (registry.definitions())
        if d.scope is not None and d.scope.selection is ComponentSelection.REFUSE_MULTICOMPONENT
    ]
    assert scoped, "the registry declares pure-substance scopes"
    for definition in scoped:
        coverage = registry.coverage(definition.calculator_id, salt)
        assert coverage is not None and coverage.kind is CoverageKind.REFUSES, definition.calculator_id
        assert definition.display_name in coverage.reason, definition.calculator_id


def test_a_scope_that_lets_the_structure_through_never_claims_covered():
    scope = CalculatorScope(ComponentSelection.REFUSE_MULTICOMPONENT, Aggregation.COLLECTION, MethodDomain.ORGANIC)
    registry = _registry_with(scope=scope)
    assert registry.coverage("probe", _mol("CCO")) is None
    assert registry.coverage("probe", _mol("[Na+].[Cl-]")).kind is CoverageKind.REFUSES


def test_a_shared_pass_gives_each_calculator_the_sentence_a_direct_run_would(container, registry):
    """The pass shares the scope step between calculators; the reworded refusal must equal the one raised for each."""
    ids = [d.calculator_id for d in registry.definitions() if d.scope is not None]
    for smiles in ("CC(=O)[O-].[Na+]", "[Fe+2].c1cc[cH-]c1.c1cc[cH-]c1", "[Na+].[Cl-]", "CCO"):
        model = MoleculeModel(display_name="m")
        container.chemistry_engine.set_structure_from_smiles(model, smiles)
        passed = container.descriptor_service.coverage_pass(model, ids)
        for calculator_id in ids:
            alone = container.descriptor_service.coverage(model, calculator_id)
            assert passed.get(calculator_id) == alone, (smiles, calculator_id)


# --- the agreement: the hook says what the calculator then does -----------------------------

#: calculator id -> the structure names on which it must ANSWER (it is allowed to be silent on a structure
#: only when the real calculator faults, which is not a limit).
HOOKED = ("griffin_hlb", "oxygen_balance", "joback_properties", "hansen_solubility")


@pytest.mark.parametrize("calculator_id", HOOKED)
@pytest.mark.parametrize("name", sorted(PANEL))
def test_the_hook_refuses_exactly_what_the_calculator_then_refuses(registry, calculator_id, name):
    coverage = registry.coverage(calculator_id, _mol(PANEL[name]))
    refused = _ran_and_refused(registry, calculator_id, PANEL[name])
    if refused is None:
        return  # the calculator faulted: a bug, not a limit, and not this test's to judge
    assert coverage is not None, (calculator_id, name)
    assert (coverage.kind is CoverageKind.REFUSES) == refused, (calculator_id, name, coverage)


def test_every_scope_refusal_is_one_the_real_run_makes(registry):
    """For EVERY registered calculator, over the panel: when the row says "certain to refuse", the calculator then refuses it.

    The scope refusals come from the call a run makes first, so this should be a tautology; it exists because the
    registry's `coverage` reaches that call through a shared pass and a copy, and a tautology that is no longer one
    is the failure worth a test.
    """
    checked = 0
    for definition in registry.definitions():
        if not isinstance(definition.execution, RegistryExecution) or definition.scope is None:
            continue
        for name, smiles in PANEL.items():
            coverage = registry.coverage(definition.calculator_id, _mol(smiles))
            if coverage is None or coverage.kind is not CoverageKind.REFUSES:
                continue
            checked += 1
            refused = _ran_and_refused(registry, definition.calculator_id, smiles)
            assert refused is not False, (definition.calculator_id, name, coverage.reason[:80])
    assert checked > 50, f"only {checked} refusals were compared, so the panel or the scopes changed under this test"


@pytest.mark.parametrize("name", sorted(PANEL))
def test_the_proton_affinity_and_bde_hooks_are_the_scope_check_and_warnings_the_window_runs(name):
    """A refusal where `check_scope` raises, a limit where `scope_warnings` has something to say, covered otherwise."""
    mol = _mol(PANEL[name])
    for hook, module in (
        (coverage_hooks.proton_affinity_coverage, proton_affinity),
        (coverage_hooks.bond_dissociation_coverage, bond_dissociation),
    ):
        base = Chem.AddHs(mol)
        try:
            module.check_scope(base)
            expected = CoverageKind.CAVEAT if module.scope_warnings(base) else CoverageKind.COVERED
        except proton_affinity.OutOfScope:
            expected = CoverageKind.REFUSES
        assert hook(mol).kind is expected, (hook.__name__, name)


def test_a_base_outside_what_was_measured_is_a_limit_not_a_refusal_and_quotes_the_warning():
    surfactant = _mol(PANEL["peg_dodecyl"])
    for hook, module in (
        (coverage_hooks.proton_affinity_coverage, proton_affinity),
        (coverage_hooks.bond_dissociation_coverage, bond_dissociation),
    ):
        coverage = hook(surfactant)
        assert coverage.kind is CoverageKind.CAVEAT
        for warning in module.scope_warnings(Chem.AddHs(surfactant)):
            assert warning in coverage.reason


def test_a_hook_with_a_rule_of_its_own_is_caught_by_the_agreement_check(registry):
    """MUTATION CONTROL: the check above must fail for a hook that disagrees, or it proves nothing."""

    def second_rule(mol):
        return Coverage.covered()  # claims everything is fine, whatever the real calculator does

    liar = _registry_with(preflight=second_rule)
    assert liar.coverage("probe", _mol(PANEL["peg_dodecyl"])).kind is CoverageKind.COVERED
    real = registry.coverage("griffin_hlb", _mol(PANEL["ethanol"]))
    assert real.kind is CoverageKind.REFUSES, "ethanol has no polyoxyethylene, so the real hook disagrees with the liar"


def test_loosening_the_calculators_own_rule_loosens_the_indicator(monkeypatch):
    """Alex's policy: refuse less, and the row follows with no edit to the hook."""
    thioethanol = _mol(PANEL["thioethanol"])
    assert coverage_hooks.oxygen_balance_coverage(thioethanol).kind is CoverageKind.REFUSES
    monkeypatch.setattr(energetics, "CHNO", energetics.CHNO | {"S"})
    assert coverage_hooks.oxygen_balance_coverage(thioethanol).kind is CoverageKind.COVERED


def test_tightening_the_rule_tightens_it_too(monkeypatch):
    ethanol = _mol(PANEL["ethanol"])
    assert coverage_hooks.oxygen_balance_coverage(ethanol).kind is CoverageKind.COVERED
    monkeypatch.setattr(energetics, "CHNO", frozenset({"C", "H", "N"}))
    assert coverage_hooks.oxygen_balance_coverage(ethanol).kind is CoverageKind.REFUSES


def test_hansen_says_with_limits_when_a_parameter_will_be_missing(monkeypatch):
    """The second answer: the molecule is accepted and compute_hansen would report a gap."""
    benzene = _mol(PANEL["benzene"])
    assert coverage_hooks.hansen_coverage(benzene).kind is CoverageKind.COVERED
    real = hansen.parameter_value
    monkeypatch.setattr(
        hansen, "parameter_value",
        lambda f, which: hansen.ParameterValue(None, hansen.ParameterBasis.UNAVAILABLE, "x") if which == "hb" else real(f, which),
    )
    coverage = coverage_hooks.hansen_coverage(benzene)
    assert coverage.kind is CoverageKind.CAVEAT and "hydrogen" in coverage.reason.lower()


def test_hansen_says_with_limits_below_three_carbons_with_the_sentence_its_numbers_carry():
    """Ethanol is computed and labelled outside the stated domain, not refused: the row says so and quotes the label."""
    ethanol = _mol(PANEL["ethanol"])
    coverage = coverage_hooks.hansen_coverage(ethanol)
    assert coverage.kind is CoverageKind.CAVEAT
    assert coverage.reason == hansen.OUTSIDE_DOMAIN_NOTE.format(n=2)
    assert coverage_hooks.hansen_coverage(_mol("CCCO")).kind is CoverageKind.COVERED


def test_an_unreadable_structure_is_a_fault_not_a_limit_and_makes_no_claim():
    assert coverage_hooks.griffin_hlb_coverage(None) is None
    assert coverage_hooks.oxygen_balance_coverage(None) is None
    assert coverage_hooks.hansen_coverage(None) is None


def test_a_geometric_index_says_nothing_about_a_drawing():
    """HOMA and Bird need a 3D structure; before one exists that is another state, not a coverage claim."""
    drawing = _mol("c1ccccc1")
    assert coverage_hooks.homa_coverage(drawing) is None
    assert coverage_hooks.bird_coverage(drawing) is None


def test_a_geometric_index_refuses_a_structure_with_no_ring_once_it_has_a_conformer():
    from rdkit.Chem import AllChem

    mol = Chem.AddHs(_mol("CCO"))
    AllChem.EmbedMolecule(mol, randomSeed=7)
    assert coverage_hooks.homa_coverage(mol).kind is CoverageKind.REFUSES
    benzene = Chem.AddHs(_mol("c1ccccc1"))
    AllChem.EmbedMolecule(benzene, randomSeed=7)
    assert coverage_hooks.homa_coverage(benzene).kind is CoverageKind.COVERED


# --- the panel ------------------------------------------------------------------------------


@pytest.fixture
def panel(qapp, container):
    # Its own bus: the container's is shared by the module, and a disposed panel's handlers would still be on it.
    bus = EventBus()
    settings = Settings(bus)
    widget = PropertyPanel(
        bus,
        container.calculator_registry,
        container.descriptor_service,
        container.chemistry_engine,
        settings=settings,
    )
    molecules = {}
    for name in ("ethanol", "peg_dodecyl", "sodium_acetate"):
        model = MoleculeModel(display_name=name)
        container.chemistry_engine.set_structure_from_smiles(model, PANEL[name])
        molecules[name] = model
    widget.set_project(ProjectModel(molecules=list(molecules.values())))
    yield widget, bus, settings, molecules
    dispose(widget)


def _select(bus, model):
    bus.publish(MoleculeSelected(molecule_uuid=model.uuid))
    QCoreApplication.processEvents()


def _chip_text(widget, calculator_id):
    return widget._calculator_status[calculator_id].text()


def test_the_chip_says_can_run_with_limits_or_not_applicable_before_any_run(panel):
    widget, bus, _settings, molecules = panel
    _select(bus, molecules["peg_dodecyl"])
    assert _chip_text(widget, "griffin_hlb") == "Can run"
    assert "inside what the method covers" in widget._calculator_status["griffin_hlb"].toolTip()
    _select(bus, molecules["ethanol"])
    assert _chip_text(widget, "griffin_hlb").endswith("Not applicable")
    assert "polyoxyethylene" in widget._calculator_status["griffin_hlb"].toolTip()
    assert _chip_text(widget, "oxygen_balance") == "Can run"


def test_a_row_with_no_hook_still_says_not_run(panel):
    widget, bus, _settings, molecules = panel
    _select(bus, molecules["ethanol"])
    no_hook = [i for i, d in ((i, widget._calculator_registry.get(i)) for i in widget._calculator_status)
               if d.preflight is None]
    assert no_hook
    for calculator_id in no_hook:
        assert _chip_text(widget, calculator_id) == "Not run", calculator_id


def test_the_scope_refusal_reaches_a_row_that_has_no_hook(panel):
    widget, bus, _settings, molecules = panel
    _select(bus, molecules["sodium_acetate"])
    scoped_no_hook = [
        i for i in widget._calculator_status
        if widget._calculator_registry.get(i).preflight is None
        and widget._calculator_registry.get(i).scope is not None
        and widget._calculator_registry.get(i).scope.selection is ComponentSelection.REFUSE_MULTICOMPONENT
    ]
    for calculator_id in scoped_no_hook:
        assert _chip_text(widget, calculator_id).endswith("Not applicable"), calculator_id


def test_the_indicator_follows_an_edit(panel, container):
    widget, bus, _settings, molecules = panel
    model = molecules["ethanol"]
    _select(bus, model)
    assert _chip_text(widget, "griffin_hlb").endswith("Not applicable")
    container.chemistry_engine.set_structure_from_smiles(model, PANEL["triethylene_glycol"] + "CCCCCC")
    bus.publish(RecalculationDue(molecule_uuid=model.uuid))
    QCoreApplication.processEvents()
    assert _chip_text(widget, "griffin_hlb") == "Can run"


def test_a_service_row_gets_a_mark_and_a_sentence_and_loses_them_with_the_claim(panel):
    widget, bus, _settings, molecules = panel
    row = widget._service_rows["orca.proton_affinity"]
    base = "Proton Affinity and Gas Basicity > Quantum Chemistry panel"
    _select(bus, molecules["ethanol"])
    assert row._full_text == "✓ " + base
    assert "inside what the method covers" in row.toolTip()
    _select(bus, molecules["sodium_acetate"])
    assert row._full_text == "○ " + base
    assert "more than one component" in row.toolTip()
    # a row with no hook is exactly what it was
    plain = widget._service_rows["orca.nmr"]._full_text
    assert not plain[0] in "✓△○", plain


def test_switching_it_off_in_settings_removes_every_claim_and_back_on_restores_them(panel):
    widget, bus, settings, molecules = panel
    _select(bus, molecules["ethanol"])
    assert widget._coverage
    settings.set_preference(STRUCTURE_COVERAGE, False)
    QCoreApplication.processEvents()
    assert not widget._coverage
    assert _chip_text(widget, "griffin_hlb") == "Not run"
    assert "✓" not in widget._service_rows["orca.proton_affinity"]._full_text
    assert "inside what the method covers" not in widget._service_rows["orca.proton_affinity"].toolTip()
    settings.set_preference(STRUCTURE_COVERAGE, True)
    QCoreApplication.processEvents()
    assert _chip_text(widget, "griffin_hlb").endswith("Not applicable")


def test_off_means_the_pass_is_never_made(panel, monkeypatch):
    widget, bus, settings, molecules = panel
    settings.set_preference(STRUCTURE_COVERAGE, False)
    calls = []
    monkeypatch.setattr(widget._descriptor_service, "coverage_pass", lambda *a, **k: calls.append(a) or {})
    _select(bus, molecules["ethanol"])
    assert calls == []


def test_a_result_still_outranks_the_claim(panel):
    from openchem.domain.report import ReportResult

    widget, bus, _settings, molecules = panel
    model = molecules["ethanol"]
    _select(bus, model)
    from openchem.events.events import ReportComputed

    bus.publish(ReportComputed(report=ReportResult(
        report_id="griffin_hlb", name="HLB (Griffin)", category="surface", molecule_uuid=model.uuid,
    )))
    QCoreApplication.processEvents()
    assert _chip_text(widget, "griffin_hlb").endswith("Ready")


def test_the_tooltip_sentences_are_distinct_and_state_what_they_do_not_say():
    covered, caveat, refuses = (
        tooltip_sentence(Coverage.covered()),
        tooltip_sentence(Coverage.caveat("a gap.")),
        tooltip_sentence(Coverage.refuses("it cannot.")),
    )
    assert len({covered, caveat, refuses}) == 3
    assert "a gap." in caveat and "it cannot." in refuses
    assert "does not say a tool is set up" in covered and "does not say a tool is set up" in caveat
