"""A partial "nothing found" must not read as a complete one.

Found in a live session on a nitramine: one feature pattern (`fg:hydrazine`)
matched a charge state it does not declare, `detect_features` raised, and every
functional-group alert for the molecule went with it -- five identical
tracebacks while every panel looked fine. The vocabulary defect is fixed
(`test_structural_features`); THIS is about the class of failure. The
application now detects tolerantly -- one bad instance costs one instance --
and the price of tolerance is that the result must say what it skipped.

To reproduce the class without depending on that particular defect staying
unfixed, the pre-fix `fg:hydrazine` pattern is put back for the duration of a
test. It is a real pattern that really does match a nitramine, not a stub.
"""

from __future__ import annotations

import pytest
from rdkit import Chem

from openchem.chem import structure_annotation
from openchem.chem import structural_features as sf
from openchem.chem.descriptor_providers import compute_fragment_group_alert
from openchem.chem.structure_annotation import canonical_features, compute_functional_groups
from openchem.domain.completeness import (
    COMPLETENESS_KEY,
    Completeness,
    completeness_of,
    completeness_parameters,
    is_partial,
)
from openchem.domain.common import CacheState, Provenance
from openchem.domain.report import ReportResult

NITRAMINE = "O=[N+]([O-])N1CN([N+](=O)[O-])C1"

#: `fg:hydrazine` as it was before the nitro exclusion: two X3 non-aromatic,
#: non-acyl nitrogens joined by a single bond -- which is a nitramine's N-N.
_PRE_FIX_HYDRAZINE = "[NX3;!a;!$([#7][#6]=[O,S,#7]):1]-[NX3;!a;!$([#7][#6]=[O,S,#7]):1]"


def _mol(smiles: str) -> Chem.Mol:
    mol = Chem.MolFromSmiles(smiles)
    assert mol is not None
    return mol


@pytest.fixture
def broken_hydrazine(monkeypatch):
    """The pre-fix pattern, and a feature cache that cannot leak it.

    `canonical_features` is cached per molblock, so a result computed under the
    patched vocabulary would otherwise be served to every later test that
    draws the same nitramine.
    """
    structure_annotation._canonical_features_cached.cache_clear()
    monkeypatch.setitem(sf.SPECS, "fg:hydrazine", sf.FeatureSpec("fg:hydrazine", (_PRE_FIX_HYDRAZINE,)))
    yield
    monkeypatch.undo()
    structure_annotation._canonical_features_cached.cache_clear()


# --- the record ---------------------------------------------------------------


def test_partial_is_derived_from_what_was_skipped_so_the_two_cannot_disagree():
    assert Completeness(evaluated=12).partial is False
    assert Completeness(evaluated=12, skipped=("fg:hydrazine at atoms [1, 2]",), reason="x").partial is True


def test_a_completeness_survives_its_own_round_trip():
    record = Completeness(evaluated=3, skipped=("a", "b"), reason="because")
    assert Completeness.from_dict(record.to_dict()) == record


def test_no_record_is_no_claim_and_is_not_partial():
    """None is "no claim", which is not "complete" -- but it is not a reason to
    warn either."""
    report = ReportResult(molecule_uuid="u", report_id="r", name="R", facts=())
    assert completeness_of(report) is None
    assert is_partial(report) is False


def test_a_partial_record_is_read_back_off_the_provenance():
    record = Completeness(evaluated=5, skipped=("fg:x at atoms [0]",), reason="r")
    report = ReportResult(
        molecule_uuid="u", report_id="r", name="R", facts=(),
        provenance=Provenance(created_by="core", method="m", parameters=completeness_parameters(record)),
    )
    assert completeness_of(report) == record and is_partial(report)


def test_a_damaged_record_is_no_claim_rather_than_an_exception():
    for bad in ("junk", 3, {"evaluated": "not a number"}, None):
        report = ReportResult(
            molecule_uuid="u", report_id="r", name="R", facts=(),
            provenance=Provenance(created_by="core", method="m", parameters={COMPLETENESS_KEY: bad}),
        )
        assert completeness_of(report) is None


# --- the detector -------------------------------------------------------------


def test_the_strict_detector_still_raises_on_the_pre_fix_pattern(broken_hydrazine):
    """Strict is what the vocabulary's own tests and the census use, so a
    pattern defect stays loud where it can be fixed."""
    with pytest.raises(sf.UndeclaredChargeState):
        sf.detect_features(_mol(NITRAMINE))


def test_the_tolerant_detector_skips_the_instance_and_names_it(broken_hydrazine):
    detection = sf.detect_features_tolerant(_mol(NITRAMINE))
    # TWO N-N bonds, so two instances -- each recorded once, although a
    # symmetric pattern matches every instance in both atom orders.
    assert [item.feature_id for item in detection.skipped] == ["fg:hydrazine", "fg:hydrazine"]
    assert len({item.atoms for item in detection.skipped}) == 2
    ids = {feature.feature_id for feature in detection.features}
    assert "fg:nitro" in ids, "everything that COULD be evaluated still was"
    assert detection.evaluated == len(detection.features) + 2


def test_the_tolerant_detector_equals_the_strict_one_when_nothing_is_skipped():
    """The narrow half: tolerance must not change a single answer for a
    molecule the strict detector can evaluate."""
    for smiles in (NITRAMINE, "CC(=O)Nc1ccc(O)cc1", "CCN(CC)CC", "OC(=O)c1ccccc1O"):
        mol = _mol(smiles)
        detection = sf.detect_features_tolerant(mol)
        assert detection.skipped == ()
        assert detection.features == sf.detect_features(mol)


# --- the results built from it ------------------------------------------------


def test_fragment_counts_says_it_is_partial_and_still_counts_the_rest(broken_hydrazine):
    result = compute_fragment_group_alert(_mol(NITRAMINE), "u")
    assert any(line.startswith("nitro (2)") for line in result.matched), "the count that could be made survives"
    record = completeness_of(result)
    assert record is not None and record.partial
    assert any("fg:hydrazine" in name for name in record.skipped)
    assert is_partial(result)


def test_fragment_counts_records_an_explicit_complete_claim_when_nothing_was_skipped():
    result = compute_fragment_group_alert(_mol(NITRAMINE), "u")
    record = completeness_of(result)
    assert record is not None, "complete is a claim, not the absence of one"
    assert record.partial is False and record.evaluated > 0
    assert not any("hydrazine" in line for line in result.matched)


def test_functional_groups_says_it_is_partial_too(broken_hydrazine):
    dataset = compute_functional_groups(_mol(NITRAMINE), "u")
    assert dataset.cache_state is CacheState.COMPLETED
    assert is_partial(dataset)


def test_the_skip_is_logged_once_per_structure_not_once_per_calculator(broken_hydrazine, caplog):
    """Two views read one cached detection, so one warning -- and it is a
    warning, not a traceback: the ledger names it, the log is not flooded."""
    import logging

    mol = _mol(NITRAMINE)
    with caplog.at_level(logging.WARNING, logger="openchem.chemistry"):
        compute_fragment_group_alert(mol, "u")
        compute_functional_groups(mol, "u")
        canonical_features(mol)
    warnings = [r for r in caplog.records if "skipped" in r.getMessage()]
    assert len(warnings) == 1
    assert warnings[0].exc_info is None
    assert "fg:hydrazine" in warnings[0].getMessage()


# --- the reader ---------------------------------------------------------------


def test_the_reader_warns_about_a_partial_result_before_it_is_read(broken_hydrazine):
    from openchem.ui.widgets.results_view import ResultsView

    result = compute_fragment_group_alert(_mol(NITRAMINE), "u")
    line = ResultsView._partial_line(None, result)
    assert line.startswith("Partial result: could not evaluate fg:hydrazine")
    assert "absence" in line


def test_the_reader_says_nothing_extra_for_a_complete_result():
    from openchem.ui.widgets.results_view import ResultsView

    assert ResultsView._partial_line(None, compute_fragment_group_alert(_mol(NITRAMINE), "u")) == ""


def test_the_reader_leads_a_refusal_with_its_kind():
    """"Not applicable" for a method that wants two numbers was the original
    defect, and it lived in this sentence as well as in the chip."""
    from openchem.chem.energetics import compute_detonation
    from openchem.domain.calculator import CalculationRefusal
    from openchem.domain.refusal_kinds import refusal_parameters
    from openchem.ui.widgets.results_view import ResultsView

    with pytest.raises(CalculationRefusal) as raised:
        compute_detonation(_mol("Nc1c(N)c([N+](=O)[O-])c(N)c([N+](=O)[O-])c1[N+](=O)[O-]"), "u", {})
    refusal = raised.value

    def report(kind):
        return ReportResult(
            molecule_uuid="u", report_id="detonation", name="D", facts=(),
            cache_state=CacheState.FAILED, error=refusal.detail, inapplicable=refusal.inapplicable,
            provenance=Provenance(
                created_by="core", method="m",
                parameters=refusal_parameters(refusal.code, kind, refusal.missing_inputs),
            ),
        )

    assert ResultsView._status_line(None, report(refusal.kind)).startswith("Needs input: ")
    from openchem.domain.refusal_kinds import RefusalKind

    assert ResultsView._status_line(None, report(RefusalKind.NEEDS_SETUP)).startswith("Needs setup: ")
    assert ResultsView._status_line(None, report(RefusalKind.LIMIT)).startswith("Not applicable: ")
