"""Guards for the solubility predictor.

Every numeric claim here was measured before it was asserted, and several
of these tests exist because a plausible-looking alternative was tried and
found wrong -- see the individual docstrings.
"""

from __future__ import annotations

import math

import pytest
from rdkit import Chem
from rdkit.Chem import Crippen, Descriptors

from openchem.chem.logd import (
    assign_site_polarity,
    ionization_factor,
    logd_henderson_hasselbalch,
)
from openchem.chem.pka_providers import PKaResolution, PKaStatus
from openchem.chem.solubility import (
    AQSOLDB,
    BCS_PH_HIGH,
    BCS_PH_LOW,
    ESOL,
    LOG_S,
    LOW_MODERATE_BOUNDARY_MG_PER_ML,
    MAX_PH_SOLUBILITY_ADJUSTMENT_LOG_UNITS,
    MG_PER_ML,
    MODERATE_HIGH_BOUNDARY_MG_PER_ML,
    MOL_PER_L,
    BcsOutcome,
    BcsReason,
    IonizationClass,
    SolubilityCategory,
    bcs_high_solubility_screen,
    classify_ionization,
    compute_solubility,
    compute_solubility_curve,
    dose_number,
    esol_logs,
    evaluate_solubility_window,
    intrinsic_category,
    logs_at_ph,
    logs_to_mg_per_ml,
    logs_to_mol_per_l,
    mg_per_ml_to_logs,
    parse_manual_pkas,
    ph_adjustment,
    resolve_solvent,
)

ASPIRIN = "CC(=O)Oc1ccccc1C(=O)O"
IBUPROFEN = "CC(C)Cc1ccc(cc1)C(C)C(=O)O"
PROPRANOLOL = "CC(C)NCC(O)COc1cccc2ccccc12"
CAFFEINE = "Cn1cnc2c1c(=O)n(C)c(=O)n2C"
GLYCINE = "NCC(=O)O"
ASPIRIN_SODIUM = "[Na+].CC(=O)Oc1ccccc1C(=O)[O-]"
DICLOFENAC = "OC(=O)Cc1ccccc1Nc1c(Cl)cccc1Cl"

#: Literature pKa, so a test's own setup does not depend on the sidecar.
ASPIRIN_PKA = 3.49
PROPRANOLOL_PKA = 9.42
DICLOFENAC_PKA = 4.15


def mol(smiles: str) -> Chem.Mol:
    return Chem.MolFromSmiles(smiles)


def found(*values: float, source: str = "manual") -> PKaResolution:
    return PKaResolution(status=PKaStatus.FOUND, values=tuple(values), source=source)


# --- the shared ionization factor -------------------------------------


def test_logd_and_solubility_move_the_same_factor_in_opposite_directions():
    """**AN IMPLEMENTATION INVARIANT, NOT A THERMODYNAMIC IDENTITY.**

    `logD + logS == logP + baseline` holds here because both calculators
    call the SAME `ionization_factor` and apply it with opposite sign. It
    says the two share one implementation and cannot drift apart. It says
    nothing about real octanol/water or real solubility, and must not be
    quoted as though it did -- a molecule's true logD and true solubility
    are not constrained to sum to anything.

    Run uncapped, because the cap deliberately breaks the symmetry.
    """
    logp, baseline = 2.5, -3.0
    pkas, is_acid = [4.9], [True]
    for ph in (0.0, 3.0, 4.9, 7.4, 11.0, 14.0):
        logd = logd_henderson_hasselbalch(logp, ph, pkas, is_acid)
        logs = logs_at_ph(baseline, ph, pkas, is_acid, limit=None)
        assert logd + logs == pytest.approx(logp + baseline, abs=1e-12)


def test_a_pka_without_its_acid_base_flag_raises_rather_than_being_dropped():
    """`zip` would silently drop the unpaired site, leaving a sum that is
    one term short and looks entirely reasonable."""
    with pytest.raises(ValueError, match="2 pKa values against 1"):
        ionization_factor(7.0, [4.8, 9.4], [True])


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), 999.0, -999.0])
def test_an_impossible_pka_is_refused(bad):
    with pytest.raises(ValueError):
        ionization_factor(7.0, [bad], [True])


def test_a_monoprotic_acid_is_half_ionized_at_its_pka():
    assert ionization_factor(4.9, [4.9], [True]) == pytest.approx(1.0)


def test_a_monoprotic_base_is_half_ionized_at_its_pka():
    assert ionization_factor(9.4, [9.4], [False]) == pytest.approx(1.0)


def test_a_neutral_molecule_has_no_ionization_at_all():
    assert ionization_factor(7.4, [], []) == 0.0


# --- monotonicity, uncapped and capped --------------------------------


def _uncapped(ph, pkas, is_acid):
    return math.log10(1.0 + ionization_factor(ph, pkas, is_acid))


def test_an_uncapped_acid_profile_rises_monotonically_with_ph():
    values = [_uncapped(p / 10, [4.9], [True]) for p in range(0, 141)]
    assert all(b > a for a, b in zip(values, values[1:]))


def test_an_uncapped_base_profile_falls_monotonically_with_ph():
    values = [_uncapped(p / 10, [9.4], [False]) for p in range(0, 141)]
    assert all(b < a for a, b in zip(values, values[1:]))


def test_a_capped_profile_rises_then_stays_flat_and_never_falls():
    """The cap must not introduce a kink that goes the wrong way -- a
    non-monotone profile would break the endpoint reasoning the ICH
    window evaluation rests on."""
    values = [ph_adjustment(p / 10, [4.9], [True]).applied for p in range(0, 141)]
    assert all(b >= a - 1e-12 for a, b in zip(values, values[1:]))
    assert max(values) == pytest.approx(MAX_PH_SOLUBILITY_ADJUSTMENT_LOG_UNITS)
    assert values[0] < MAX_PH_SOLUBILITY_ADJUSTMENT_LOG_UNITS  # it really does rise first


def test_the_cap_is_continuous_at_the_boundary():
    """Approach the limit from below and the values must meet it, not jump
    to it. A discontinuity would draw as a step in the chart.

    The crossing is NOT `pKa + limit`, which was the first guess and is
    wrong by 0.0044: the adjustment is `log10(1 + 10^(pH - pKa))`, so it
    reaches 2.0 when the term is 99, at `pKa + log10(10^2 - 1)`.
    """
    pkas, is_acid = [4.9], [True]
    crossing = 4.9 + math.log10(10**MAX_PH_SOLUBILITY_ADJUSTMENT_LOG_UNITS - 1)
    below = ph_adjustment(crossing - 1e-6, pkas, is_acid)
    above = ph_adjustment(crossing + 1e-6, pkas, is_acid)
    assert below.applied == pytest.approx(above.applied, abs=1e-5)
    assert not below.limited and above.limited


# --- the cap, on a case where it genuinely bites -----------------------


def test_the_cap_engages_far_beyond_its_boundary_not_marginally():
    """**THE FIXTURE HAS TO GENUINELY EXCEED THE CAP.** A molecule whose
    uncapped rise is 2.1 would let a test pass with the cap removed, to
    within any sane tolerance. Aspirin at pH 12 asks for +8.51, so
    deleting the cap moves the answer by six and a half log units.
    """
    adjustment = ph_adjustment(12.0, [ASPIRIN_PKA], [True])
    assert adjustment.uncapped > 8.0
    assert adjustment.limited
    assert adjustment.applied == MAX_PH_SOLUBILITY_ADJUSTMENT_LOG_UNITS


def test_without_the_cap_aspirin_reaches_a_physically_absurd_solubility():
    """The measurement that justifies the cap existing at all: 4.7e10
    mg/mL is 47 tonnes per litre."""
    baseline = esol_logs(mol(ASPIRIN))
    uncapped = logs_at_ph(baseline, 14.0, [ASPIRIN_PKA], [True], limit=None)
    mw = Descriptors.MolWt(mol(ASPIRIN))
    assert logs_to_mg_per_ml(uncapped, mw) > 1e9


# --- units -------------------------------------------------------------


def test_a_mole_per_litre_of_aspirin_is_180_mg_per_ml():
    """**THE ANTI-1000x GUARD.** One mol/L of a 180.16 g/mol compound is
    180.16 g/L, and a g/L IS a mg/mL. A review of the plan proposed
    dividing by 1000 here; that would make this 0.18, and would drop
    aspirin from ChemAxon's published High to Low.
    """
    assert logs_to_mg_per_ml(0.0, 180.16) == pytest.approx(180.16)
    assert logs_to_mol_per_l(0.0) == pytest.approx(1.0)


@pytest.mark.parametrize("logs", [-8.0, -5.5, -2.0, 0.0, 1.5])
def test_the_unit_conversion_round_trips_across_magnitudes(logs):
    """Both ends of the scale, because a scale-factor error is invisible at
    exactly one magnitude if the fixture happens to sit there."""
    mw = 180.16
    assert mg_per_ml_to_logs(logs_to_mg_per_ml(logs, mw), mw) == pytest.approx(logs, abs=1e-12)


def test_a_conversion_with_no_molecular_weight_refuses():
    with pytest.raises(ValueError):
        logs_to_mg_per_ml(-2.0, 0.0)


# --- categories --------------------------------------------------------


def test_the_category_boundaries_fall_exactly_where_chemaxon_documents():
    """Both published numbers, at the value itself rather than near it."""
    assert intrinsic_category(LOW_MODERATE_BOUNDARY_MG_PER_ML - 1e-9) is SolubilityCategory.LOW
    assert intrinsic_category(LOW_MODERATE_BOUNDARY_MG_PER_ML) is SolubilityCategory.MODERATE
    assert intrinsic_category(MODERATE_HIGH_BOUNDARY_MG_PER_ML) is SolubilityCategory.MODERATE
    assert intrinsic_category(MODERATE_HIGH_BOUNDARY_MG_PER_ML + 1e-9) is SolubilityCategory.HIGH


def test_aspirin_lands_in_the_category_chemaxon_publishes_for_it():
    """Their own worked example: -1.81 logS is 2.79 mg/mL, reported High.
    Ours is a different baseline (-2.09) and must still be High, which is
    what says the threshold is being read on the right scale."""
    mw = Descriptors.MolWt(mol(ASPIRIN))
    assert logs_to_mg_per_ml(-1.81, mw) == pytest.approx(2.79, abs=0.01)
    assert intrinsic_category(logs_to_mg_per_ml(-1.81, mw)) is SolubilityCategory.HIGH
    assert intrinsic_category(logs_to_mg_per_ml(esol_logs(mol(ASPIRIN)), mw)) is SolubilityCategory.HIGH


def test_the_category_reads_the_baseline_not_the_ph_adjusted_value():
    """**THE ONE-WORD REGRESSION.** Writing `category(logs_at_ph(...))`
    produces a UI that looks entirely reasonable and a classification that
    changes when the user moves the pH control.

    **DICLOFENAC, AND THE FIXTURE CHOICE IS THE TEST.** Ibuprofen was the
    obvious pick and is degenerate: its ESOL baseline is 0.06002 mg/mL,
    which is 0.00002 above the Moderate/High boundary, so it reads High on
    BOTH sides and the mutation is invisible. Diclofenac is 0.0019 mg/mL
    baseline (Low) against 0.19 at pH 7.4 (High) -- two full bands apart,
    with neither value near a threshold.
    """
    target = mol(DICLOFENAC)
    mw = Descriptors.MolWt(target)
    baseline = esol_logs(target)
    at_ph = logs_at_ph(baseline, 7.4, [DICLOFENAC_PKA], [True])

    assert intrinsic_category(logs_to_mg_per_ml(baseline, mw)) is SolubilityCategory.LOW
    assert intrinsic_category(logs_to_mg_per_ml(at_ph, mw)) is SolubilityCategory.HIGH

    report = compute_solubility(target, "u", {"pka_values": str(DICLOFENAC_PKA), "pH": 7.4})
    stated = next(f for f in report.facts if f.label == "Solubility category")
    assert stated.display_value == SolubilityCategory.LOW.value


# --- ionization classification ----------------------------------------


def test_a_molecule_with_both_centres_is_an_ampholyte():
    assert classify_ionization(mol(GLYCINE), found(2.34, 9.60)) is IonizationClass.AMPHOLYTE


def test_an_acid_and_a_base_are_told_apart():
    assert classify_ionization(mol(IBUPROFEN), found(4.91)) is IonizationClass.ACID
    assert classify_ionization(mol(PROPRANOLOL), found(9.42)) is IonizationClass.BASE


def test_neutral_comes_from_the_structure_and_never_from_a_failed_prediction():
    """**THE DISTINCTION THAT MATTERS.** A molecule that HAS an ionizable
    centre but whose pKa could not be predicted must not be treated as
    neutral -- that would draw a confident flat line for a curve nobody
    computed. Aspirin is the case: real acid, no values.

    Caffeine goes the other way. It has no centre at all, so it is neutral
    whatever the predictor did or did not manage, and its classification
    rests on the structure rather than on an empty list.
    """
    acid_without_values = mol(ASPIRIN)
    for broken in (PKaStatus.FAILED, PKaStatus.UNAVAILABLE):
        verdict = classify_ionization(acid_without_values, PKaResolution(status=broken))
        assert verdict is IonizationClass.UNSUPPORTED

    no_centres = mol(CAFFEINE)
    for status in (PKaStatus.NO_IONIZABLE_CENTRES, PKaStatus.FAILED, PKaStatus.UNAVAILABLE):
        assert classify_ionization(no_centres, PKaResolution(status=status)) is IonizationClass.NEUTRAL


def test_an_ampholyte_is_recognised_without_any_pka_predictor():
    """Which regime a molecule is in is a fact about the molecule. Asking
    about pKa availability first got this wrong: glycine came back as "no
    pKa values available", and the ampholyte refusal -- the more
    informative answer, and the correct one -- was never reached."""
    assert (
        classify_ionization(mol(GLYCINE), PKaResolution(status=PKaStatus.UNAVAILABLE))
        is IonizationClass.AMPHOLYTE
    )


def test_a_salt_is_unsupported_however_good_its_pka_values_look():
    assert classify_ionization(mol(ASPIRIN_SODIUM), found(3.49)) is IonizationClass.UNSUPPORTED


# --- the ICH M9 window -------------------------------------------------


def test_the_window_minimum_sits_at_an_endpoint_for_an_acid_and_for_a_base():
    """Monotone by construction, so the extremum is at one end. This is why
    the screen evaluates two points instead of scanning a grid that could
    step straight over a minimum."""
    acid = evaluate_solubility_window(-3.5, [4.9], [True], IonizationClass.ACID)
    assert acid.minimum_ph == BCS_PH_LOW

    base = evaluate_solubility_window(-3.5, [5.0], [False], IonizationClass.BASE)
    assert base.minimum_ph == BCS_PH_HIGH


def test_an_ampholyte_may_not_reach_the_window_evaluation():
    """Its profile is not monotone, so the endpoint shortcut would be
    wrong. Refused loudly rather than answered wrongly."""
    with pytest.raises(ValueError, match="not monotone"):
        evaluate_solubility_window(-3.5, [2.3, 9.6], [True, False], IonizationClass.AMPHOLYTE)


def test_a_strong_base_saturates_the_displayed_curve_but_not_the_verdict():
    """**MEASURED, AND IT IS THE ORDINARY CASE FOR BASIC DRUGS.**
    Propranolol's pKa 9.4 asks for +8.20 at pH 1.2 and +2.60 at pH 6.8, so
    every point in the ICH window hits the safeguard and the DISPLAYED
    spread across it is exactly zero.

    That used to decide the screen, which meant an arbitrary constant
    blanked a whole compound class. The verdict is bounded now, so the
    saturation is still reported -- it is true, and the curve really is
    flat there -- while the outcome is decided by the sandwich instead.
    """
    window = evaluate_solubility_window(-3.57, [PROPRANOLOL_PKA], [False], IonizationClass.BASE)
    assert window.fully_limited
    assert window.logs_low == pytest.approx(window.logs_high)
    # The uncapped ceiling is far above the capped display value, which is
    # exactly why the bracket is wide for a base.
    assert window.uncapped_minimum_logs > window.minimum_logs + 0.5


def test_a_verdict_never_depends_on_the_adjustment_safeguard():
    """**THE FIX, AS AN ASSERTION.** Changing the safeguard must not change
    a BCS outcome: the screen reads the floor (the neutral species alone)
    and the ceiling (uncapped ionization), and the cap sits strictly
    between them. Run at three very different limits, including none.
    """
    outcomes = set()
    for limit in (0.5, MAX_PH_SOLUBILITY_ADJUSTMENT_LOG_UNITS, 6.0, None):
        window = evaluate_solubility_window(
            -3.57, [PROPRANOLOL_PKA], [False], IonizationClass.BASE, limit=limit
        )
        screen = bcs_high_solubility_screen(window, dose_mg=40.0, molecular_weight=259.3)
        outcomes.add((screen.outcome, screen.reason))
    assert len(outcomes) == 1


@pytest.mark.parametrize(
    ("smiles", "pka", "is_acid", "dose", "expected"),
    [
        (CAFFEINE, None, None, 100.0, BcsOutcome.PASS),
        (ASPIRIN, ASPIRIN_PKA, True, 500.0, BcsOutcome.FAIL),
        (IBUPROFEN, 4.91, True, 400.0, BcsOutcome.FAIL),
        (PROPRANOLOL, PROPRANOLOL_PKA, False, 40.0, BcsOutcome.UNDETERMINED),
    ],
)
def test_the_bounded_screen_reaches_a_sound_verdict_where_one_exists(
    smiles, pka, is_acid, dose, expected
):
    """Four of five measured compounds get a real answer; propranolol is
    the honest UNDETERMINED, because for a base the window minimum sits at
    pH 6.8 where ionization is doing all the work and whether the salt
    precipitates decides everything.

    **THE PARAMETRISATION IS THE TEST.** A single passing compound would
    not show that the two bounds license OPPOSITE verdicts.
    """
    target = mol(smiles)
    baseline = esol_logs(target)
    pkas = [] if pka is None else [pka]
    flags = [] if pka is None else [is_acid]
    ionization = (
        IonizationClass.NEUTRAL
        if pka is None
        else (IonizationClass.ACID if is_acid else IonizationClass.BASE)
    )
    window = evaluate_solubility_window(baseline, pkas, flags, ionization)
    screen = bcs_high_solubility_screen(window, dose, Descriptors.MolWt(target))

    assert screen.outcome is expected
    if expected is BcsOutcome.UNDETERMINED:
        assert screen.reason is BcsReason.BOUNDS_STRADDLE
        assert screen.dose_number_low <= 1.0 < screen.dose_number_high
    else:
        assert screen.reason is BcsReason.COMPUTABLE


def test_the_ceiling_is_the_uncapped_profile_not_the_displayed_one():
    """**A MUTATION SURVIVED UNTIL THIS EXISTED**, and the reason is the
    fixture set rather than the code.

    The ceiling licenses the FAIL side: "even the most optimistic
    solubility misses the criterion". Build it from the displayed (capped)
    curve instead of the uncapped profile and it is no longer a ceiling --
    it understates solubility, so it can license a FAIL the evidence does
    not support.

    Nothing caught that. For an acid the window minimum sits at pH 1.2
    where the molecule is barely ionized, so capped and uncapped agree
    exactly; for propranolol at 40 mg both land on the same verdict. The
    two ceilings only disagree about the OUTCOME when the dose falls in
    the gap between them, which for propranolol is 1745-6989 mg. At 3000
    mg the honest answer is UNDETERMINED and the capped ceiling claims a
    sound FAIL.
    """
    window = evaluate_solubility_window(-3.57, [PROPRANOLOL_PKA], [False], IonizationClass.BASE)
    # The setup itself is asserted: without a real gap this proves nothing.
    assert window.uncapped_minimum_logs > window.minimum_logs + 0.5

    screen = bcs_high_solubility_screen(window, dose_mg=3000.0, molecular_weight=259.3)
    assert screen.outcome is BcsOutcome.UNDETERMINED
    assert screen.reason is BcsReason.BOUNDS_STRADDLE

    # And the ceiling really is the uncapped one, read directly.
    ceiling = logs_to_mg_per_ml(window.uncapped_minimum_logs, 259.3)
    assert screen.dose_number_low == pytest.approx(3000.0 / (ceiling * 250.0))


def test_the_two_bounds_really_do_bracket_the_capped_estimate():
    """The sandwich has to hold, or a verdict licensed by one side says
    nothing about the value shown to the user."""
    window = evaluate_solubility_window(-3.57, [PROPRANOLOL_PKA], [False], IonizationClass.BASE)
    assert window.baseline_logs <= window.minimum_logs <= window.uncapped_minimum_logs


def test_a_missing_dose_is_undetermined_and_says_which_reason():
    """The reasons must not collapse into one generic UNDETERMINED --
    'no dose given' is the user's to fix, 'saturated' is not."""
    window = evaluate_solubility_window(-2.0, [4.9], [True], IonizationClass.ACID)
    screen = bcs_high_solubility_screen(window, dose_mg=None, molecular_weight=180.16)
    assert screen.outcome is BcsOutcome.UNDETERMINED
    assert screen.reason is BcsReason.MISSING_DOSE


def test_dose_number_refuses_impossible_inputs_rather_than_dividing_by_zero():
    assert dose_number(0.0, 1.0) is None
    assert dose_number(-5.0, 1.0) is None
    assert dose_number(100.0, 0.0) is None
    assert dose_number(250.0, 1.0) == pytest.approx(1.0)


# --- manual pKa --------------------------------------------------------


def test_manual_pka_values_are_parsed_and_a_typo_is_refused():
    assert parse_manual_pkas("3.49, 9.4") == [3.49, 9.4]
    assert parse_manual_pkas("4.8; 9.1") == [4.8, 9.1]
    with pytest.raises(ValueError, match="not a number"):
        parse_manual_pkas("3.49, abc")


def test_a_manual_pka_overrides_the_prediction_and_changes_the_answer():
    """**THE FIXTURE MUST SIT WHERE THE CAP DOES NOT BIND**, or both pKa
    values give the identical capped answer and the test passes with the
    override ignored. At pH 4.0 aspirin's adjustment is well under the
    limit, so 3.49 and 6.00 really do differ.
    """
    target = mol(ASPIRIN)
    baseline = esol_logs(target)
    near = logs_at_ph(baseline, 4.0, [3.49], [True])
    far = logs_at_ph(baseline, 4.0, [6.00], [True])
    assert abs(near - far) > 0.4

    report = compute_solubility(target, "u", {"pka_values": "6.00", "pH": 4.0})
    stated = next(f for f in report.facts if f.label.startswith("Predicted solubility at pH"))
    assert float(stated.display_value) == pytest.approx(far, abs=0.01)
    assert report.provenance.parameters["pka_source"] == "manual"
    assert report.provenance.parameters["pka_input_text"] == "6.00"


# --- the calculators, end to end ---------------------------------------


def test_a_neutral_molecule_gets_a_flat_curve_rather_than_a_failure():
    """Caffeine's solubility genuinely does not vary with pH, and that is
    an answer. `compute_logd_curve` declines the same molecule because a
    flat logD line adds nothing to logP -- the difference between the two
    is exactly why pKa resolution hands back a status instead of deciding
    for both callers.
    """
    curve = compute_solubility_curve(mol(CAFFEINE), "u", {})
    assert not curve.error
    values = next(iter(curve.series.values()))
    assert max(values) - min(values) == 0.0
    assert "does not vary" in curve.name


def test_an_ampholyte_is_refused_with_the_reason_named():
    report = compute_solubility(mol(GLYCINE), "u", {})
    assert report.error
    assert "ampholyte" in report.error
    assert "zwitterion" in report.error.lower()


def test_a_salt_is_refused_and_told_to_draw_the_parent():
    report = compute_solubility(mol(ASPIRIN_SODIUM), "u", {})
    assert report.error
    assert "more than one component" in report.error


def test_an_unknown_solvent_is_refused_rather_than_silently_given_water():
    """A user who asked for ethanol and got water's number under ethanol's
    label has a wrong answer, not a degraded one."""
    with pytest.raises(KeyError):
        resolve_solvent("ethanol")
    report = compute_solubility(mol(ASPIRIN), "u", {"solvent": "ethanol"})
    assert report.error
    assert "ethanol" in report.error


def test_water_is_supported_and_is_the_default():
    assert resolve_solvent("water").key == "water"
    assert resolve_solvent(None).key == "water"


# --- the two plumbing invariants ---------------------------------------


def test_changing_the_display_unit_changes_no_modelled_quantity():
    """**A PURE PLUMBING TRAP.** The unit orders the report; it must never
    reach the chemistry. Same category, same underlying logS, three
    renderings."""
    target = mol(ASPIRIN)
    reports = {
        unit: compute_solubility(target, "u", {"unit": unit, "pka_values": "3.49"})
        for unit in (LOG_S, MG_PER_ML, MOL_PER_L)
    }
    categories = {
        next(f.display_value for f in r.facts if f.label == "Solubility category")
        for r in reports.values()
    }
    assert len(categories) == 1

    logs = {
        next(
            f.value for f in r.facts
            if f.label == "Predicted intrinsic solubility (log mol/L)"
        )
        for r in reports.values()
    }
    assert len(logs) == 1


def test_changing_the_reported_ph_leaves_the_baseline_and_pka_untouched():
    """Only the pH-adjusted value may move."""
    target = mol(ASPIRIN)
    first = compute_solubility(target, "u", {"pH": 2.0, "pka_values": "3.49"})
    second = compute_solubility(target, "u", {"pH": 9.0, "pka_values": "3.49"})

    def baseline(report):
        return next(
            f.value for f in report.facts
            if f.label == "Predicted intrinsic solubility (log mol/L)"
        )

    assert baseline(first) == baseline(second)
    assert first.provenance.parameters["pka_values"] == second.provenance.parameters["pka_values"]

    def at_ph(report):
        return next(f.value for f in report.facts if f.label.startswith("Predicted solubility at pH"))

    assert at_ph(first) != at_ph(second)


def test_provenance_records_the_model_status_not_merely_the_model():
    """A stored result must distinguish "AqSolDB was asked for and was not
    there" from "ESOL was chosen"."""
    report = compute_solubility(mol(ASPIRIN), "u", {"model": AQSOLDB}, admet_interpreter_path="")
    assert report.provenance.parameters["model"] == AQSOLDB
    assert report.provenance.parameters["model_status"] == "unavailable"
    assert report.error


def test_no_model_disagreement_is_reported_when_only_one_model_ran():
    """**NEVER MANUFACTURE A DELTA.** An unavailable sidecar is not a
    disagreement between two numbers; it is one number and nothing."""
    report = compute_solubility(mol(ASPIRIN), "u", {"model": ESOL}, admet_interpreter_path="")
    assert not any(f.label == "Model disagreement" for f in report.facts)


# --- the curve result --------------------------------------------------


def test_the_curve_carries_its_scalar_findings_as_facts():
    curve = compute_solubility_curve(mol(ASPIRIN), "u", {"pka_values": "3.49"})
    labels = {f.label for f in curve.facts}
    assert "Solubility category" in labels
    assert any(label.startswith("Predicted intrinsic solubility") for label in labels)


def test_the_existing_ph_curves_carry_no_facts():
    """`facts` was added for solubility. Migrating `isoelectric_point` and
    `logd_curve` off their name-string workaround is a separate decision,
    and this pins that it has not drifted in."""
    from openchem.chem.ph_curves import compute_isoelectric_point, compute_logd_curve

    for compute in (compute_isoelectric_point, compute_logd_curve):
        result = compute(mol(ASPIRIN), "u", {}, interpreter_path=None)
        assert result.facts == ()


def test_a_ph_curve_built_without_facts_still_works():
    """The field defaults empty, so every existing producer is untouched."""
    from openchem.domain.scientific_result import PhCurveResult

    curve = PhCurveResult(curve_id="x", name="x", method="m", molecule_uuid="u")
    assert curve.facts == ()


def test_copying_a_curve_exports_its_facts_as_well_as_its_table():
    """The facts are the half a reader quotes. A copy that dropped them
    would silently export less than the screen shows."""
    from openchem.ui.result_clipboard import result_to_text

    curve = compute_solubility_curve(mol(ASPIRIN), "u", {"pka_values": "3.49"})
    text = result_to_text(curve)
    assert "Solubility category" in text
    assert "pH\t" in text


def test_every_reported_string_survives_a_windows_console():
    """Result lines reach cp1252 streams, where a non-encodable character
    RAISES. This project has hit that three times with a tick mark."""
    from openchem.ui.result_clipboard import result_to_text

    for target, params in ((ASPIRIN, {"pka_values": "3.49"}), (PROPRANOLOL, {"pka_values": "9.42"})):
        for result in (
            compute_solubility(mol(target), "u", params),
            compute_solubility_curve(mol(target), "u", params),
        ):
            result_to_text(result).encode("cp1252")


# --- ESOL, and that it is now shared -----------------------------------


def test_esol_reproduces_the_values_it_was_verified_against():
    """Live-checked against the reference implementation when the
    descriptor was written; unchanged by the move into this module."""
    assert esol_logs(mol(ASPIRIN)) == pytest.approx(-2.09, abs=0.01)
    assert esol_logs(mol(CAFFEINE)) == pytest.approx(-0.53, abs=0.01)
    assert esol_logs(mol(IBUPROFEN)) == pytest.approx(-3.54, abs=0.01)


def test_the_descriptor_and_the_calculator_use_one_esol_implementation():
    """Two copies of a fitted regression is two chances to drift. The
    descriptor row and the calculator's baseline must be the same number,
    to the last bit."""
    from openchem.chem.descriptor_providers import RDKitDescriptorProvider

    target = mol(ASPIRIN)
    computed = RDKitDescriptorProvider().compute(target, "u")
    values = {v.descriptor_id: v.value for v in computed}
    assert values["esol_logs"] == esol_logs(target)


def test_the_esol_row_is_filed_under_solubility_not_admet():
    """A reclassification, not a new computation -- and easy to break. The
    row must move section while keeping its value, name and units."""
    from openchem.chem.descriptor_providers import _DESCRIPTOR_SPECS

    specs = {spec[0]: spec for spec in _DESCRIPTOR_SPECS}
    descriptor_id, name, units, category = specs["esol_logs"]
    assert category == "solubility"
    assert name == "Aqueous Solubility (ESOL, log mol/L)"
    assert units == ""


def test_the_site_polarity_convention_is_shared_with_logd():
    """logD and solubility must agree about which pKa is the acid, or the
    same molecule gets two different curves."""
    pkas, is_acid = assign_site_polarity(mol(IBUPROFEN), [4.91])
    assert pkas == [4.91]
    assert is_acid == [True]

    pkas, is_acid = assign_site_polarity(mol(PROPRANOLOL), [9.42])
    assert is_acid == [False]
