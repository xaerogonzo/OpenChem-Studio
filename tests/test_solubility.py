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
    ionization_log_factor,
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
    MISCIBILITY_CEILING_MG_PER_ML,
    SALT_LIMIT_LOG_UNITS_ACID,
    SALT_LIMIT_COUNTER_ION_MOLAR,
    SALT_LIMIT_LOG_UNITS_BASE,
    MG_PER_ML,
    MODERATE_HIGH_BOUNDARY_MG_PER_ML,
    MOL_PER_L,
    AdjustmentLimit,
    BcsOutcome,
    BcsReason,
    IonizationClass,
    LimitKind,
    SolubilityCategory,
    adjustment_limit,
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
    mcgowan_volume,
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
    call the SAME `ionization_log_factor` and apply it with opposite sign. It
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
        ionization_log_factor(7.0, [4.8, 9.4], [True])


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), 999.0, -999.0])
def test_an_impossible_pka_is_refused(bad):
    with pytest.raises(ValueError):
        ionization_log_factor(7.0, [bad], [True])


def test_a_monoprotic_acid_is_half_ionized_at_its_pka():
    """Half ionized doubles the dissolved total, so the LOG factor is
    log10(2), not 1. The function returns the log."""
    assert ionization_log_factor(4.9, [4.9], [True]) == pytest.approx(math.log10(2.0))


def test_a_monoprotic_base_is_half_ionized_at_its_pka():
    assert ionization_log_factor(9.4, [9.4], [False]) == pytest.approx(math.log10(2.0))


def test_a_neutral_molecule_has_no_ionization_at_all():
    assert ionization_log_factor(7.4, [], []) == 0.0


def test_sites_compose_multiplicatively_not_additively():
    """**THE MULTI-SITE CORRECTION, AS AN ASSERTION.**

    Two ionizable sites multiply the dissolved total, so their LOGS add.
    The wrong form -- `log10(1 + sum of terms)` -- never reaches the
    doubly-ionized scaling, because getting there needs both protons off
    and the sum has no term for it.

    Measured at pH 8 on a 3.0/4.5 diacid, the right and wrong forms differ
    by 3.49 log units.
    """
    pkas, flags = [3.0, 4.5], [True, True]
    ours = ionization_log_factor(8.0, pkas, flags)

    product = math.log10((1 + 10 ** (8.0 - 3.0)) * (1 + 10 ** (8.0 - 4.5)))
    assert ours == pytest.approx(product, abs=1e-12)

    wrong = math.log10(1 + 10 ** (8.0 - 3.0) + 10 ** (8.0 - 4.5))
    assert ours - wrong == pytest.approx(3.49, abs=0.01)


def test_the_microscopic_and_macroscopic_forms_differ_and_we_use_the_right_one():
    """**A SUBTLETY WORTH PINNING RATHER THAN ROUNDING AWAY.**

    Avdeef 2007 Table 1 (doi 10.1016/j.addr.2007.05.008) gives a diprotic
    acid as `1 + 10^(pH-pKa1) + 10^(2pH-pKa1-pKa2)`. The independent-site
    product expands to that PLUS a `10^(pH-pKa2)` term, so the two are
    close but not equal -- 4.3e-6 apart at pH 8 on a 3.0/4.5 diacid.

    They are not meant to be equal. Avdeef's constants are MACROSCOPIC
    (successive dissociations, where the singly-ionized species already
    lumps both microstates); ours are per-SITE. `ph_curves` records that
    pkasolver "predicts per-site values, which are closer to microscopic
    constants", so the product is the form matching our inputs.

    The distinction is tiny here and structural everywhere: a first guess
    would have been to widen the tolerance until the two agreed, which
    would have buried the reason they do not.
    """
    pkas, flags = [3.0, 4.5], [True, True]
    ours = ionization_log_factor(8.0, pkas, flags)
    macroscopic = math.log10(1 + 10 ** (8.0 - 3.0) + 10 ** (2 * 8.0 - 3.0 - 4.5))

    assert ours != macroscopic
    assert abs(ours - macroscopic) < 1e-5
    # Same leading behaviour: both reach the doubly-ionized 10^(2pH) scaling,
    # which is the whole thing the summed form misses.
    assert ours == pytest.approx(macroscopic, rel=1e-6)


def test_one_site_is_where_the_sum_and_the_product_agree():
    """Which is why the bug hid: every monoprotic answer is identical
    under both forms, and monoprotic is the overwhelmingly common case."""
    for pka, acidic in ((4.9, True), (9.4, False)):
        for ph in (0.0, 4.0, 7.4, 11.0, 14.0):
            summed = math.log10(1.0 + 10.0 ** min((ph - pka) if acidic else (pka - ph), 12.0))
            assert ionization_log_factor(ph, [pka], [acidic]) == pytest.approx(summed, abs=1e-12)


# --- monotonicity, uncapped and capped --------------------------------


def _uncapped(ph, pkas, is_acid):
    return ionization_log_factor(ph, pkas, is_acid)


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
    limit = SALT_LIMIT_LOG_UNITS_ACID
    values = [ph_adjustment(p / 10, [4.9], [True], limit).applied for p in range(0, 141)]
    assert all(b >= a - 1e-12 for a, b in zip(values, values[1:]))
    assert max(values) == pytest.approx(limit)
    assert values[0] < limit  # it really does rise first


def test_the_cap_is_continuous_at_the_boundary():
    """Approach the limit from below and the values must meet it, not jump
    to it. A discontinuity would draw as a step in the chart.

    The crossing is NOT `pKa + limit`, which was the first guess and is
    wrong by 0.0044: the adjustment is `log10(1 + 10^(pH - pKa))`, so it
    reaches 2.0 when the term is 99, at `pKa + log10(10^2 - 1)`.
    """
    pkas, is_acid = [4.9], [True]
    limit = SALT_LIMIT_LOG_UNITS_ACID
    crossing = 4.9 + math.log10(10**limit - 1)
    below = ph_adjustment(crossing - 1e-6, pkas, is_acid, limit)
    above = ph_adjustment(crossing + 1e-6, pkas, is_acid, limit)
    assert below.applied == pytest.approx(above.applied, abs=1e-5)
    assert not below.limited and above.limited


# --- the cap, on a case where it genuinely bites -----------------------


def test_the_cap_engages_far_beyond_its_boundary_not_marginally():
    """**THE FIXTURE HAS TO GENUINELY EXCEED THE CAP.** A molecule whose
    uncapped rise is 2.1 would let a test pass with the cap removed, to
    within any sane tolerance. Aspirin at pH 12 asks for +8.51, so
    deleting the cap moves the answer by six and a half log units.
    """
    adjustment = ph_adjustment(12.0, [ASPIRIN_PKA], [True], SALT_LIMIT_LOG_UNITS_ACID)
    assert adjustment.uncapped > 8.0
    assert adjustment.limited
    assert adjustment.applied == SALT_LIMIT_LOG_UNITS_ACID


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


def test_the_cited_salt_limit_un_saturates_propranolol_s_window():
    """**THE FIX MOVED THE VERY SYMPTOM THAT MOTIVATED THE BOUNDED SCREEN.**

    Propranolol's pKa 9.4 asks for +8.20 at pH 1.2 and +2.60 at pH 6.8.
    Under the old symmetric +2 that saturated the ENTIRE ICH window and
    the displayed spread was exactly zero -- which is what an arbitrary
    constant blanking a whole compound class looked like.

    Avdeef's base limit is 3.0, and 2.60 fits under it. So the window is
    no longer saturated at its minimum and the curve carries real pH
    information again. Both halves are asserted, because the improvement
    is the point and a reader will otherwise assume the old note still
    holds.
    """
    old = evaluate_solubility_window(
        -3.57, [PROPRANOLOL_PKA], [False], IonizationClass.BASE, limit=2.0
    )
    assert old.fully_limited, "the historical +2 really did saturate the window"

    now = evaluate_solubility_window(
        -3.57, [PROPRANOLOL_PKA], [False], IonizationClass.BASE,
        limit=SALT_LIMIT_LOG_UNITS_BASE,
    )
    assert not now.fully_limited
    assert now.logs_low != pytest.approx(now.logs_high)


def test_a_strong_enough_base_still_saturates_and_the_verdict_survives_it():
    """Saturation has not been abolished, only pushed back. A base above
    about pKa 10 still fills the window -- and the verdict is unaffected,
    because the screen reads the bounds and never the limit."""
    window = evaluate_solubility_window(
        -3.57, [11.0], [False], IonizationClass.BASE, limit=SALT_LIMIT_LOG_UNITS_BASE
    )
    assert window.fully_limited
    assert window.logs_low == pytest.approx(window.logs_high)
    assert window.uncapped_minimum_logs > window.minimum_logs + 1.0


def test_a_verdict_never_depends_on_the_adjustment_safeguard():
    """**THE FIX, AS AN ASSERTION.** Changing the safeguard must not change
    a BCS outcome: the screen reads the floor (the neutral species alone)
    and the ceiling (uncapped ionization), and the cap sits strictly
    between them. Run at three very different limits, including none.
    """
    outcomes = set()
    for limit in (0.5, 2.0, 6.0, None):
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

    Nothing caught it. For an ACID the window minimum sits at pH 1.2 where
    the molecule is barely ionized, so capped and uncapped agree exactly.
    Propranolol was the original fixture and no longer works at all: under
    Avdeef's base limit of 3.0 its minimum is not capped, so there is no
    gap to disagree about. It takes a base strong enough that the limit
    still binds across the window -- pKa 11 here, which leaves a 1.20 log
    gap between the two candidate ceilings.

    **THE FIXTURE HAS BEEN WRONG TWICE NOW**, once for being too weak to
    show the gap and once for a limit change closing it. Both times the
    setup assertion below is what said so.
    """
    window = evaluate_solubility_window(
        -3.57, [11.0], [False], IonizationClass.BASE, limit=SALT_LIMIT_LOG_UNITS_BASE
    )
    # The setup itself is asserted: without a real gap this proves nothing.
    assert window.uncapped_minimum_logs > window.minimum_logs + 1.0

    screen = bcs_high_solubility_screen(window, dose_mg=100000.0, molecular_weight=259.3)
    assert screen.outcome is BcsOutcome.UNDETERMINED
    assert screen.reason is BcsReason.BOUNDS_STRADDLE

    # And the ceiling really is the uncapped one, read directly.
    ceiling = logs_to_mg_per_ml(window.uncapped_minimum_logs, 259.3)
    assert screen.dose_number_low == pytest.approx(100000.0 / (ceiling * 250.0))


def test_the_two_bounds_really_do_bracket_the_displayed_estimate():
    """The sandwich has to hold, or a verdict licensed by one side says
    nothing about the value shown to the user."""
    window = evaluate_solubility_window(
        -3.57, [PROPRANOLOL_PKA], [False], IonizationClass.BASE,
        limit=SALT_LIMIT_LOG_UNITS_BASE,
    )
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


# --- the two bounds on the profile ------------------------------------


def test_the_salt_limit_is_asymmetric_and_matches_avdeef():
    """Avdeef's "sdiff 3-4": FOUR orders for a weak acid (sodium salt),
    THREE for a weak base (chloride salt), in 0.15 M NaCl. Asymmetric
    because the two salts are not equally soluble -- which the symmetric
    +2 it replaced could not express."""
    assert SALT_LIMIT_LOG_UNITS_ACID == 4.0
    assert SALT_LIMIT_LOG_UNITS_BASE == 3.0
    assert SALT_LIMIT_LOG_UNITS_ACID != SALT_LIMIT_LOG_UNITS_BASE

    acid = adjustment_limit(IonizationClass.ACID, -6.0, 300.0)
    base = adjustment_limit(IonizationClass.BASE, -6.0, 300.0)
    assert acid.log_units == SALT_LIMIT_LOG_UNITS_ACID
    assert base.log_units == SALT_LIMIT_LOG_UNITS_BASE
    assert acid.kind is base.kind is LimitKind.SALT_PRECIPITATION


def test_avdeefs_own_worked_example_reproduces():
    """**THE CHECK THAT THE RULE WAS READ CORRECTLY.** Avdeef gives
    amiodarone an intrinsic solubility of 7.9e-9 M and an estimated Ksp of
    1.2e-6 M^2 "using the sdiff 3-4 approximation". A base takes three
    orders, and Ksp = Si x [counter-ion]:

        7.9e-9 x 10^3 x 0.15 = 1.19e-6

    Reproducing his number is what says the reading is right rather than
    merely plausible.
    """
    intrinsic_molar = 7.9e-9
    salt_solubility = intrinsic_molar * 10**SALT_LIMIT_LOG_UNITS_BASE
    ksp = salt_solubility * SALT_LIMIT_COUNTER_ION_MOLAR
    assert ksp == pytest.approx(1.2e-6, rel=0.02)


def test_a_soluble_acid_is_stopped_by_the_ceiling_not_the_salt_rule():
    """**THE MEASUREMENT THAT FORCED A SECOND BOUND.** Aspirin's uncapped
    rise at pH 7.4 is 3.91, which never reaches an acid's 4.0 -- so the
    salt rule alone leaves it at 11,925 mg/mL, twelve kilograms per litre.
    sdiff is stated for SPARINGLY-soluble drugs and is silent about a
    compound whose intrinsic solubility is already 1.5 mg/mL.
    """
    target = mol(ASPIRIN)
    mw = Descriptors.MolWt(target)
    baseline = esol_logs(target)

    salt_only = logs_to_mg_per_ml(baseline + SALT_LIMIT_LOG_UNITS_ACID, mw)
    assert salt_only > 1e4, "the salt rule alone really is not enough here"

    limit = adjustment_limit(IonizationClass.ACID, baseline, mw)
    assert limit.kind is LimitKind.PLAUSIBILITY_CEILING
    assert limit.log_units < SALT_LIMIT_LOG_UNITS_ACID
    assert logs_to_mg_per_ml(baseline + limit.log_units, mw) == pytest.approx(
        MISCIBILITY_CEILING_MG_PER_ML
    )


def test_a_sparingly_soluble_base_is_stopped_by_the_salt_rule():
    """The other side of the same coin, and the case sdiff was stated for.
    Propranolol at pH 1.2 lands at 70 mg/mL, against a real propranolol
    hydrochloride solubility of roughly 50 -- where the old symmetric +2
    gave 7."""
    target = mol(PROPRANOLOL)
    mw = Descriptors.MolWt(target)
    baseline = esol_logs(target)

    limit = adjustment_limit(IonizationClass.BASE, baseline, mw)
    assert limit.kind is LimitKind.SALT_PRECIPITATION
    assert limit.log_units == SALT_LIMIT_LOG_UNITS_BASE

    at_gastric_ph = logs_at_ph(baseline, 1.2, [PROPRANOLOL_PKA], [False], limit.log_units)
    assert logs_to_mg_per_ml(at_gastric_ph, mw) == pytest.approx(70.0, abs=5.0)
    # The old cap is what this replaced, and the difference is an order of
    # magnitude on a real drug.
    old = logs_at_ph(baseline, 1.2, [PROPRANOLOL_PKA], [False], 2.0)
    assert logs_to_mg_per_ml(old, mw) == pytest.approx(7.0, abs=1.0)


def test_the_two_bounds_are_reported_as_different_things():
    """A salt plateau and an arithmetic ceiling are not the same claim, and
    a fact derived from one must not read like the other."""
    soluble = compute_solubility(
        mol(ASPIRIN), "u", {"pka_values": str(ASPIRIN_PKA), "pH": 7.4, "compare_models": False}
    )
    sparing = compute_solubility(
        mol(PROPRANOLOL), "u",
        {"pka_values": str(PROPRANOLOL_PKA), "pH": 1.2, "compare_models": False},
    )
    assert soluble.provenance.parameters["adjustment_limit_kind"] == LimitKind.PLAUSIBILITY_CEILING.value
    assert sparing.provenance.parameters["adjustment_limit_kind"] == LimitKind.SALT_PRECIPITATION.value

    note = next(
        f for f in soluble.facts if f.label.startswith("Predicted solubility at pH")
    ).limitations
    assert note and "pure-compound ceiling" in note[0]


def test_a_neutral_molecule_has_no_salt_limit_to_reach():
    limit = adjustment_limit(IonizationClass.NEUTRAL, -0.53, 194.2)
    assert limit.kind is LimitKind.NONE
    assert limit.log_units == 0.0


def test_the_drawn_curve_honours_the_same_bound_its_facts_describe():
    """**A FACT AND A PICTURE DISAGREEING IS WORSE THAN EITHER BEING WRONG
    ALONE**, and that is exactly what shipped for one render.

    The limit was threaded into the facts and the ICH window but not into
    the profile the chart draws, so propranolol's stats block read
    "Adjustment limit +3.0 logS, reached at 26 of 57 sampled pH values"
    while the plotted curve climbed to 1.8e8 mg/mL. Every test passed; the
    y-axis showed it instantly.
    """
    curve = compute_solubility_curve(
        mol(PROPRANOLOL), "u",
        {"pka_values": str(PROPRANOLOL_PKA), "unit": MG_PER_ML, "compare_models": False},
    )
    stated = next(f for f in curve.facts if f.label.startswith("Adjustment limit"))
    assert "reached at" in stated.display_value

    baseline = esol_logs(mol(PROPRANOLOL))
    mw = Descriptors.MolWt(mol(PROPRANOLOL))
    ceiling = logs_to_mg_per_ml(baseline + float(stated.value), mw)

    drawn = next(iter(curve.series.values()))
    assert max(drawn) == pytest.approx(ceiling, rel=1e-9)


# --- the one Abraham descriptor that is exactly computable -------------


@pytest.mark.parametrize(
    ("smiles", "published"),
    [
        ("c1ccccc1", 0.7164),        # benzene
        ("Cc1ccccc1", 0.8573),       # toluene
        ("O", 0.1673),               # water
        ("CCO", 0.4491),             # ethanol
        ("CCCCCC", 0.9540),          # hexane
        ("ClC(Cl)Cl", 0.6167),       # chloroform
        ("CC(C)=O", 0.5470),         # acetone
        ("Oc1ccccc1", 0.7751),       # phenol
    ],
)
def test_the_mcgowan_volume_matches_published_values(smiles, published):
    """Exact to four decimals, because the definition is arithmetic on the
    formula and the bond count -- no geometry, no fitting, nothing anybody
    chose. This is what makes it the only Abraham solute descriptor the
    project can supply today."""
    assert mcgowan_volume(mol(smiles)) == pytest.approx(published, abs=5e-5)


def test_an_element_with_no_published_volume_is_refused():
    """The published set covers eleven elements. Guessing a twelfth would
    put an invented number into a descriptor whose whole appeal is that it
    contains none."""
    with pytest.raises(ValueError, match="No McGowan atomic volume"):
        mcgowan_volume(mol("[Se]"))


def test_the_textbook_excess_molar_refraction_relation_does_not_work_here():
    """**A MEASURED NEGATIVE, and it corrects this project's own
    documentation.**

    `docs/SOLVENT_SOLUBILITY_ASSESSMENT.md` claimed the Abraham descriptor
    E was "derivable from Crippen molar refractivity" via
    `MR/10 - 2.83195*Vx + 0.52553`. It is not. Hexane IS the alkane
    reference, so its E is 0.000 by definition, and that relation returns
    0.805 on Crippen's MR scale. Water returns 0.413 against 0.000.

    A refit of the same two inputs reaches about 0.12 RMSE on thirteen
    compounds -- fitted on them, so optimistic -- which is why the doc now
    says "needs a validated refit" rather than "derivable". Asserted here
    so the claim cannot drift back.
    """
    from rdkit.Chem import Crippen

    def textbook_e(smiles: str) -> float:
        target = mol(smiles)
        return Crippen.MolMR(target) / 10.0 - 2.83195 * mcgowan_volume(target) + 0.52553

    assert textbook_e("CCCCCC") > 0.5   # hexane, whose true E is 0.000
    assert textbook_e("O") > 0.2        # water, likewise 0.000
