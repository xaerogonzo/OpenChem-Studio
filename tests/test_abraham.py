"""Guards for solubility outside water.

The route is a LOOKUP on both sides -- measured solvent coefficients and
measured solute descriptors -- so most of what can go wrong is data
handling rather than arithmetic, and that is what these cover.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from rdkit import Chem

from openchem.chem import abraham
from openchem.chem.abraham import (
    MAX_PROPAGATED_UNCERTAINTY_LOG,
    SolventShift,
    solute_descriptors,
    solvent_coefficients,
    solvent_names,
    solvent_shift,
)
from openchem.chem.solubility import SOLVENTS, compute_solubility, compute_solubility_curve

_DATA = Path(__file__).resolve().parents[1] / "src" / "openchem" / "chem" / "data"

ASPIRIN = "CC(=O)Oc1ccccc1C(=O)O"
BENZENE = "c1ccccc1"


def mol(smiles: str) -> Chem.Mol:
    return Chem.MolFromSmiles(smiles)


# --- the shipped data --------------------------------------------------


def test_both_tables_carry_their_attribution():
    """CC BY 4.0 requires it, and a data file whose provenance lives only
    in a build script is one refactor from being unattributable."""
    for name, expected in (
        ("abraham_solvents.json", "10.1186/s13065-015-0085-4"),
        ("abraham_solutes.json", "10.6084/m9.figshare.1176994"),
    ):
        payload = json.loads((_DATA / name).read_text(encoding="utf-8"))
        assert expected in payload["attribution"]
        assert "CC BY 4.0" in payload["attribution"]


def test_the_missing_value_sentinel_never_reached_the_shipped_table():
    """**THE TRAP IN THE SOURCE DATA.** It uses -123 for "not measured",
    which `float()` reads as a perfectly ordinary number. 513 rows carry
    one, and a single leak would put a wildly negative descriptor into a
    prediction that still looked like a prediction.
    """
    payload = json.loads((_DATA / "abraham_solutes.json").read_text(encoding="utf-8"))
    for key, entry in payload["solutes"].items():
        for descriptor in ("e", "s", "a", "b", "v"):
            assert entry[descriptor] != -123, f"{key} carries the sentinel"


def test_only_measured_solvents_are_offered():
    """The paper also predicts coefficients for 202 further solvents and
    says of those "not as gospel". Only measured ones ship.

    **92, NOT 91, AND THE 92ND IS NOT BRADLEY'S.** Acetic acid comes from
    Stovall 2015, which measured it -- see the acetic-acid tests at the
    foot of this file. The count is asserted rather than bounded so that
    a predicted row cannot arrive unnoticed; adding another MEASURED
    solvent is expected to move it, with its own source entry.
    """
    assert len(solvent_names()) == 92
    for required in ("ethanol", "hexane", "methanol", "1-octanol", "toluene"):
        assert solvent_coefficients(required) is not None


def test_acetic_acid_is_present_now_and_the_refusal_is_history():
    """**THIS TEST ASSERTED THE OPPOSITE, AND WAS RIGHT AT THE TIME.**

    It read "acetic acid is absent and that is deliberate", because the
    only coefficients that existed were PREDICTED and the paper declines
    to stand behind them. What changed is not this project's standard but
    the literature available to it: Stovall 2015 measured them.

    Kept as a rename with a successor rather than deleted, because the
    reason it existed is the durable part -- a predicted row still must
    not ship, which the predicted-only tests below still assert.
    """
    assert solvent_coefficients("acetic acid") is not None


def test_a_predicted_only_solvent_is_refused_with_its_REAL_reason():
    """**"Not in the table" reads as an oversight**, and for acetic acid it
    would be false: the numbers exist, and the paper's own held-out error
    is what makes them unusable. Alex asked for acetic acid by name, so
    the refusal has to carry the measurement rather than a shrug.
    """
    from openchem.chem.abraham import predicted_only_reason

    # 1,3-dioxolane stands in for acetic acid, which was this test's
    # original subject and now SHIPS -- measured coefficients arrived
    # from a second source. The refusal it demonstrates is unchanged and
    # still applies to 117 named solvents.
    reason = predicted_only_reason("1,3-dioxolane")
    assert "held-out error" in reason
    assert "intercept" in reason

    # A solvent in neither table gets the ordinary message, not this one.
    assert predicted_only_reason("liquid ammonia") == ""


def test_the_predicted_only_reason_reaches_the_USER_not_just_the_helper():
    """**THE FIX WAS UNREACHABLE FOR THE ONE CASE IT EXISTS FOR.** It first
    lived only in `solvent_shift` -- but `resolve_solvent` refuses a
    solvent that is not in `SOLVENTS` several layers earlier, so acetic
    acid never reached it and the user still got "91 solvents are
    supported". Assert through the calculator, which is the path a person
    actually takes.
    """
    report = compute_solubility(
        mol(ASPIRIN), "u", {"solvent": "1,3-dioxolane", "compare_models": False}
    )
    assert report.error
    assert "held-out error" in report.error
    assert "solvents are supported" not in report.error


def test_no_predicted_coefficient_is_shipped_anywhere():
    """The names ship so a refusal can be specific; the NUMBERS must not,
    or something downstream will eventually start using them."""
    payload = json.loads((_DATA / "abraham_solvents.json").read_text(encoding="utf-8"))
    assert payload["predicted_only"], "the names are needed for the refusal"
    for name in payload["predicted_only"]:
        assert isinstance(name, str), "predicted_only must be bare names, never coefficients"
        assert name not in payload["solvents"], f"{name} is in both tables"


def test_a_miscible_solvent_is_present_which_is_the_whole_point():
    """**A ROUND OF THIS WORK WAS SPENT BELIEVING OTHERWISE.** Ethanol and
    water are miscible, so no two-phase partition coefficient exists and
    the UFZ LSER database omits ethanol entirely. Abraham's coefficients
    come from SOLUBILITY RATIOS instead, so neat ethanol is here.
    """
    assert solvent_coefficients("ethanol") is not None


# --- the lookup --------------------------------------------------------


def test_a_measured_compound_resolves_by_inchikey_not_by_smiles_spelling():
    """Two spellings of one structure must find the same row."""
    plain = solute_descriptors(mol("CC(=O)Oc1ccccc1C(=O)O"))
    rewritten = solute_descriptors(mol("O=C(C)Oc1ccccc1C(O)=O"))
    assert plain is not None
    assert rewritten is not None
    assert plain.inchikey == rewritten.inchikey


def test_an_unmeasured_compound_is_refused_by_name_rather_than_guessed():
    """Coverage is the price of not predicting the descriptors. A molecule
    nobody measured gets a sentence, not a number."""
    invented = mol("CCCCCCCCCCCCCCCCCCCCCCCCCCN1CCN(CC1)C(=O)c1ccc(OCCCCBr)cc1")
    assert solute_descriptors(invented) is None
    outcome = solvent_shift(invented, "ethanol")
    assert isinstance(outcome, str)
    assert "no measured Abraham descriptors" in outcome


def test_an_unknown_solvent_says_how_many_are_available():
    outcome = solvent_shift(mol(BENZENE), "liquid ammonia")
    assert isinstance(outcome, str)
    assert f"{len(solvent_names())} solvents" in outcome


# --- disagreement between literature sources ---------------------------


def test_a_compound_measured_once_carries_no_uncertainty():
    shift = solvent_shift(mol(BENZENE), "hexane")
    assert isinstance(shift, SolventShift)
    assert shift.uncertainty == 0.0
    assert shift.usable


def test_disagreeing_sources_propagate_into_the_answer_and_can_refuse_it():
    """**THE MEDIAN ALONE WOULD HAVE HIDDEN THIS.** 432 InChIKeys appear
    more than once and only 51 of those groups agree exactly; the worst
    single descriptor disagrees by 2.24. A solvent coefficient of -4.9
    turns a 0.3 disagreement into 1.5 log units, so the spread is carried
    and propagated rather than averaged away.

    Aspirin in toluene is the case: two sources, and the propagated width
    exceeds the bound, so it refuses rather than reporting a midpoint.
    """
    outcome = solvent_shift(mol(ASPIRIN), "toluene")
    assert isinstance(outcome, str)
    assert "disagree" in outcome

    usable = solvent_shift(mol(ASPIRIN), "ethanol")
    assert isinstance(usable, SolventShift)
    assert 0.0 < usable.uncertainty <= MAX_PROPAGATED_UNCERTAINTY_LOG


def test_the_uncertainty_is_per_descriptor_not_a_blanket_worst_case():
    """The first version multiplied the single widest spread by the SUM of
    all five coefficient magnitudes, which refused aspirin, caffeine and
    ibuprofen -- three of the first four drugs tried. A bound that rejects
    the ordinary case is not a safety feature.
    """
    shift = solvent_shift(mol(ASPIRIN), "ethanol")
    assert isinstance(shift, SolventShift)

    coefficients = solvent_coefficients("ethanol")
    blanket = max(shift.solute.spread.values()) * sum(
        abs(getattr(coefficients, key)) for key in "esabv"
    )
    assert shift.uncertainty < blanket


# --- how the calculators use it ----------------------------------------


def test_every_offered_solvent_can_actually_be_asked_for():
    """The offered set is built FROM the coefficient table, so the two
    cannot drift -- the failure `inapplicable_calculators` suffered once,
    where a hand-kept list rotted into 27 wrong entries."""
    assert set(SOLVENTS) == {"water"} | {name.lower() for name in solvent_names()}


def test_water_is_offered_first_despite_sorting_dead_last():
    """`sorted(SOLVENTS)` buries the default at position 91 of 91 -- water
    is the very last entry alphabetically. It is not merely the default: it
    is the solvent the pH curve, the BCS screen and the whole benchmark are
    about."""
    from openchem.chem.solubility import solvent_choices

    choices = solvent_choices()
    assert choices[0] == "water"
    assert choices[1:] == sorted(choices[1:])
    assert len(choices) == len(SOLVENTS)


def test_the_refusal_names_familiar_solvents_and_only_real_ones():
    """A refusal listing `1,9-decadiene` and `1-chlorobutane` -- the first
    two alphabetically after water -- answers "is my solvent here?" for
    nobody. The handful shown is filtered against the real table, so it can
    never advertise a solvent that would then be refused."""
    from openchem.chem.solubility import _FAMILIAR_SOLVENTS, resolve_solvent

    with pytest.raises(KeyError) as caught:
        resolve_solvent("liquid ammonia")
    message = str(caught.value)

    assert "ethanol" in message and "hexane" in message
    assert str(len(SOLVENTS)) in message
    for name in _FAMILIAR_SOLVENTS:
        assert name in SOLVENTS, f"{name} is advertised but not supported"


def test_a_non_aqueous_solvent_needs_no_pka():
    """Nothing downstream applies Henderson-Hasselbalch there. Requiring a
    pKa anyway refused aspirin in ethanol for want of a number the
    calculation never uses."""
    report = compute_solubility(
        mol(ASPIRIN), "u", {"solvent": "ethanol", "compare_models": False}
    )
    assert not report.error
    assert any(f.label.startswith("Predicted solubility in ethanol") for f in report.facts)


# --- three defects that only the RENDERED panel showed ------------------
#
# Every test above passed while all three were live. They were found by
# grabbing the FactView under QT_QPA_PLATFORM=windows and reading it.


def test_a_value_row_names_the_solvent_instead_of_saying_intrinsic():
    """**THE ROW CARRIED AN ETHANOL NUMBER IN AQUEOUS WORDING.**
    `baseline_logs` already includes the Abraham shift, so an unqualified
    "Predicted intrinsic solubility" row was reporting 52.81 mg/mL --
    aspirin in ethanol -- under a label every other part of the app uses
    for the aqueous value.
    """
    ethanolic = compute_solubility(
        mol(ASPIRIN), "u", {"solvent": "ethanol", "compare_models": False}
    )
    assert not any("intrinsic" in f.label for f in ethanolic.facts)

    aqueous = compute_solubility(
        mol(ASPIRIN), "u", {"solvent": "water", "pka_values": "3.49", "compare_models": False}
    )
    assert any("intrinsic" in f.label for f in aqueous.facts)


def test_the_aqueous_category_is_withheld_outside_water():
    """**ChemAxon's Low/Moderate/High ARE AQUEOUS THRESHOLDS.** They encode
    expectations about dissolution in the gut, so calling 52.81 mg/mL in
    ethanol "High" borrows an aqueous verdict's authority for a different
    question -- the same scoping mistake the BCS screen is guarded against
    one function away, missed here until the panel was rendered.

    Refused explicitly rather than omitted: a MISSING row reads as "not
    computed yet", where the point is that it does not apply.
    """
    report = compute_solubility(
        mol(ASPIRIN), "u", {"solvent": "ethanol", "compare_models": False}
    )
    category = next(f for f in report.facts if f.label == "Solubility category")
    assert "Not applicable" in category.display_value
    assert category.display_value not in {"Low", "Moderate", "High"}


def test_the_bcs_refusal_names_the_SOLVENT_and_not_the_species():
    """It borrowed `UNSUPPORTED_SPECIES` at first, whose text reads "this
    species is outside the model". That is false -- aspirin is perfectly
    well supported; ICH M9 is simply defined on aqueous media. A refusal
    naming the wrong cause sends the reader to fix the wrong thing.
    """
    report = compute_solubility(
        mol(ASPIRIN), "u",
        {"solvent": "ethanol", "dose_mg": 500.0, "compare_models": False},
    )
    bcs = next(f for f in report.facts if f.label.startswith("BCS"))
    assert "aqueous" in bcs.display_value
    assert "species" not in bcs.display_value


def test_outside_water_no_two_rows_report_the_same_quantity_twice():
    """**THE PANEL REPEATED ONE VALUE FOUR TIMES.** With no pH adjustment
    outside water, the "baseline" rows and the "at pH" row coincide
    exactly, so a fourth row was emitted carrying a number already on
    screen three times in three units. Invisible to every test here, which
    read labels rather than asking whether two rows said the same thing.
    """
    report = compute_solubility(
        mol(ASPIRIN), "u", {"solvent": "ethanol", "compare_models": False}
    )
    numeric = [f.display_value for f in report.facts if f.value is not None]
    assert len(numeric) == len(set(numeric)), f"a value is reported twice: {numeric}"


def test_a_non_aqueous_answer_is_never_labelled_with_a_ph():
    """pH is an aqueous concept. A pH-labelled row carrying an ethanol
    number would be an aqueous answer's clothes on a non-aqueous one."""
    report = compute_solubility(
        mol(ASPIRIN), "u", {"solvent": "ethanol", "compare_models": False}
    )
    assert not any("pH" in f.label for f in report.facts)


def test_varies_with_ph_answers_for_the_solvent_and_not_only_the_molecule():
    """**ASSERTED ON THE PREDICATE, BECAUSE ITS ONE CALLER CANNOT REACH
    IT.** `_ph_facts` returns for a non-aqueous solvent before it ever
    asks, so dropping the `is_water` term changes no rendered output and
    survived the whole file. The property's contract is "does pH move this
    analysis", and answering True for an ethanol solution is wrong on its
    own terms whether or not today's caller would notice.

    **BOTH ARMS MUST CARRY THE pKa, AND THE FIRST DRAFT DID NOT.** Without
    one, and with no pkasolver interpreter configured under test, aspirin
    classifies UNSUPPORTED in ethanol too -- so `varies_with_ph` was False
    for a reason that had nothing to do with the solvent and the fixture
    could not have discriminated. Its own setup assertion caught that.
    The pKa is inert outside water; it is here to make the classification
    ACID so that only the solvent half is left to decide.
    """
    from openchem.chem.solubility import IonizationClass, analyse_solubility

    aqueous = analyse_solubility(mol(ASPIRIN), {"solvent": "water", "pka_values": "3.49"})
    assert aqueous.ionization is IonizationClass.ACID
    assert aqueous.varies_with_ph

    ethanolic = analyse_solubility(mol(ASPIRIN), {"solvent": "ethanol", "pka_values": "3.49"})
    assert ethanolic.ionization is IonizationClass.ACID
    assert not ethanolic.varies_with_ph


def test_the_ph_curve_refuses_outright_outside_water():
    curve = compute_solubility_curve(mol(ASPIRIN), "u", {"solvent": "ethanol"})
    assert curve.error
    assert "pH is an aqueous concept" in curve.error


def test_the_bcs_screen_does_not_follow_the_solute_out_of_water():
    """ICH M9 is a criterion about aqueous media. Reporting it for a
    solubility in hexane would be a regulatory-shaped answer to a question
    the regulation does not ask."""
    report = compute_solubility(
        mol(ASPIRIN), "u",
        {"solvent": "ethanol", "dose_mg": 500.0, "compare_models": False},
    )
    bcs = next(f for f in report.facts if f.label.startswith("BCS"))
    assert "UNDETERMINED" in bcs.display_value


def test_water_still_behaves_exactly_as_before():
    """The whole aqueous path must be untouched by the solvent work."""
    report = compute_solubility(
        mol(ASPIRIN), "u",
        {"solvent": "water", "pka_values": "3.49", "dose_mg": 500.0, "compare_models": False},
    )
    assert not report.error
    assert any(f.label.startswith("Predicted solubility at pH") for f in report.facts)
    assert any(f.label == "Solubility category" for f in report.facts)


def _load_benchmark(stem: str):
    """A benchmark script, imported by path and registered in `sys.modules`
    first — a dataclass in an unregistered module raises inside
    `dataclasses`, which reads as a bug in the benchmark."""
    import importlib.util
    import sys

    path = Path(__file__).resolve().parents[1] / "benchmarks" / "solubility" / f"{stem}.py"
    spec = importlib.util.spec_from_file_location(f"openchem_benchmark_{stem}", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _nonaqueous_module():
    """The benchmark module, imported by path.

    Registered in `sys.modules` before exec: a dataclass defined in a module
    that is not there resolves its annotations against `None` and raises
    inside `dataclasses`, which reads as a bug in the benchmark rather than
    in the import.
    """
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location(
        "openchem_benchmark_nonaqueous",
        Path(__file__).resolve().parents[1] / "benchmarks" / "solubility" / "nonaqueous.py",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# --- the two open edges, closed 2026-08-16 -----------------------------


def test_the_base_bias_note_reaches_bases_and_only_bases():
    """**MEASURED AND DELIBERATELY NOT CORRECTED.** ESOL under-predicts
    bases by about half a log unit on both corpora, and
    `benchmarks/solubility/base_bias.py` put an adjustment through a
    pre-registered held-out test that returned SURFACE_ONLY. So the user is
    told, rather than silently handed a fitted constant.

    A base-bias warning on an acid is noise and on a neutral is wrong,
    which is what the other two arms pin.
    """
    def note_count(smiles: str, pka: str) -> int:
        report = compute_solubility(
            mol(smiles), "u",
            {"solvent": "water", "pka_values": pka, "compare_models": False},
        )
        fact = next(f for f in report.facts if f.label.startswith("Predicted intrinsic"))
        return sum("under-predicts BASES" in text for text in fact.limitations)

    assert note_count("CC(C)NCC(O)COc1cccc2ccccc12", "9.42") == 1   # propranolol, base
    assert note_count("CC(=O)Oc1ccccc1C(=O)O", "3.49") == 0         # aspirin, acid
    assert note_count("Cn1cnc2c1c(=O)n(C)c(=O)n2C", "") == 0        # caffeine, neutral


def test_no_base_bias_constant_is_applied_to_the_value():
    """The verdict was SURFACE_ONLY, so the number itself must be untouched
    -- the note is the whole change. `esol_logs` is the raw model, and the
    reported intrinsic logS must still equal it exactly."""
    from openchem.chem.solubility import esol_logs

    target = mol("CC(C)NCC(O)COc1cccc2ccccc12")
    report = compute_solubility(
        target, "logs", {"solvent": "water", "pka_values": "9.42", "compare_models": False}
    )
    fact = next(f for f in report.facts if f.label.startswith("Predicted intrinsic"))
    assert fact.value == pytest.approx(esol_logs(target), abs=1e-12)


def test_the_non_aqueous_fact_separates_the_three_accuracy_claims():
    """A reader must not be able to take the composite MAE as the shift's
    validated accuracy. The baseline error, the composite error and the
    shift's validation status are three different statements."""
    report = compute_solubility(
        mol(ASPIRIN), "u", {"solvent": "ethanol", "compare_models": False}
    )
    fact = next(f for f in report.facts if f.label.startswith("Predicted solubility in ethanol"))
    blob = " ".join(fact.limitations)
    assert "0.68" in blob and "0.61" in blob
    assert "NOT independently validated" in blob or "not independently validated" in blob.lower()


def test_every_benchmark_arm_carries_a_status_from_the_closed_vocabulary():
    """**THE NUMBER MUST NOT TRAVEL WITHOUT ITS CAVEAT.** The status used to
    be hand-typed into the printed title while the JSON carried none, so the
    two could disagree. One source now feeds both, and the shift arm can
    never be emitted as VALIDATED."""
    module = _nonaqueous_module()

    assert set(module.ARM_STATUS) == {"composite", "baseline_aqueous", "shift_only"}
    for arm, (status, caveat) in module.ARM_STATUS.items():
        assert isinstance(status, module.ArmStatus), f"{arm} has a free-form status"
        assert caveat.strip(), f"{arm} has no caveat"

    assert module.ARM_STATUS["shift_only"][0] is module.ArmStatus.OPTIMISTIC


def test_the_text_table_and_the_json_take_the_status_from_one_object():
    """Closes the class of bug rather than today's strings: the rendered row
    and the machine-readable field must come from the same dict."""
    module = _nonaqueous_module()

    stats = module._stats([0.5, -0.5], "shift_only")
    assert stats["status"] == "optimistic"
    assert "[OPTIMISTIC]" in module._table("shift only", stats)


def test_the_notes_reach_the_STATUS_LINE_and_not_only_a_tooltip():
    """**A FACT-LEVEL LIMITATION IS A TOOLTIP.** `FactView._add_row` puts
    `fact.limitations` into the row's tooltip; only `report.limitations`
    reaches the status line under the panel. Both notes were fact-level
    first, rendered correctly, and were invisible on screen -- found by
    grabbing the panel with every test green.
    """
    base = compute_solubility(
        mol("CC(C)NCC(O)COc1cccc2ccccc12"), "u",
        {"solvent": "water", "pka_values": "9.42", "compare_models": False},
    )
    assert any("under-predicts BASES" in text for text in base.limitations)

    acid = compute_solubility(
        mol(ASPIRIN), "u",
        {"solvent": "water", "pka_values": "3.49", "compare_models": False},
    )
    assert not any("under-predicts BASES" in text for text in acid.limitations)

    ethanolic = compute_solubility(
        mol(ASPIRIN), "u", {"solvent": "ethanol", "compare_models": False}
    )
    assert any("not independently validated" in t.lower() for t in ethanolic.limitations)


def _base_bias_result() -> dict:
    path = Path(__file__).resolve().parents[1] / "benchmarks" / "solubility" / "base_bias_result.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_the_experiment_and_production_agree_about_whether_a_constant_shipped():
    """**THE EXPERIMENT DECIDES; PRODUCTION OBEYS.** The result artifact
    carries `production_change_permitted`, and the only state in which
    `solubility.py` may apply a fitted offset is `SHIP`. This asserts the
    two cannot drift apart -- a guard against the model being "fixed" after
    an inconvenient verdict.
    """
    from openchem.chem import solubility

    result = _base_bias_result()
    shipped = result["outcome"] == "SHIP"
    assert result["production_change_permitted"] is shipped

    applies = hasattr(solubility, "ESOL_BASE_BIAS_CORRECTION_LOGS")
    assert applies is shipped, (
        "the repository state disagrees with the experiment: "
        f"outcome={result['outcome']} but a correction constant "
        f"{'exists' if applies else 'is absent'}"
    )


def test_a_non_ship_outcome_records_WHY_it_failed():
    """`insufficient_evidence` and `contrary_evidence` are opposite
    findings — "we could not show it" versus "we showed it does not work" —
    and a bare SURFACE_ONLY reads the same for both."""
    result = _base_bias_result()
    if result["outcome"] == "SURFACE_ONLY":
        assert result["evidence_reading"] in {"insufficient_evidence", "contrary_evidence"}
        assert result["reason"]


def test_the_result_artifact_is_reproducible_without_rerunning_it():
    """A fitted number that exists only in stdout is not auditable. The
    artifact must name the corpora, their fingerprints, the bootstrap
    parameters and the criteria version."""
    result = _base_bias_result()
    assert result["acceptance_criteria_version"] >= 3
    assert result["bootstrap"]["seed"] and result["bootstrap"]["replicates"] >= 1000
    assert result["bootstrap"]["resample_unit"] == "compound"
    assert result["sd_and_n_are"] == "metadata, never weights"
    for name, corpus in result["corpora"].items():
        assert corpus["sha256_16"], f"{name} has no content fingerprint"
    assert result["provenance"]["rdkit"] and result["provenance"]["date"]


def test_an_endpoint_incompatible_corpus_can_never_be_fitted():
    """AqSolDB is ~10k rows and measures a DIFFERENT endpoint — aqueous
    solubility of whatever solid form, not intrinsic solubility of the
    neutral species. Size is exactly why this needs a rule rather than
    judgement."""
    module = _load_benchmark("base_bias")

    assert module.corpus_eligibility({"target_type": "intrinsic"})[0] is module.Eligibility.ELIGIBLE
    state, why = module.corpus_eligibility({"target_type": "aqueous_solubility"})
    assert state is module.Eligibility.TEST_ONLY
    assert "endpoint_mismatch" in why


def test_the_avdeef_extractor_refuses_the_tables_that_duplicate_sc2():
    """A3 and A4 are the SC-2 tight and loose sets under other names.
    Extracting them would double-count and inflate the power of the very
    experiment they would feed."""
    module = _load_benchmark("extract_avdeef_sets")

    assert set(module.DUPLICATES_OF_KNOWN) >= {"A3", "A4"}
    assert "SC-2" in module.DUPLICATES_OF_KNOWN["A3"]
    assert set(module.WANTED) == {"avdeef_a1", "avdeef_a2"}


# --- acetic acid: a deferral whose reason rotted ----------------------------


def _mol(smiles: str):
    return Chem.MolFromSmiles(smiles)


#: Stovall 2015 Eq. (6), transcribed from the PDF. The TEST carries them
#: independently of the shipped table on purpose: a transcription oracle
#: that reads the same file it is checking asserts nothing.
_STOVALL_EQ6 = {"c": 0.175, "e": 0.174, "s": -0.454, "a": -1.073, "b": -2.789, "v": 3.725}
_STOVALL_EQ6_SE = {"c": 0.049, "e": 0.086, "s": 0.115, "a": 0.123, "b": 0.163, "v": 0.081}


def test_acetic_acid_is_no_longer_refused_as_predicted_only():
    """The deferral this closes, asserted from the outside.

    It was refused because only PREDICTED coefficients existed. A
    measured set now ships, so it must be a solvent like any other -- and
    must not still be named in the predicted-only list, which would leave
    two parts of the file disagreeing.
    """
    names = [name.lower() for name in abraham.solvent_names()]
    assert "acetic acid" in names

    payload = json.loads(
        (Path(abraham.__file__).parent / "data" / "abraham_solvents.json").read_text(
            encoding="utf-8"
        )
    )
    assert "acetic acid" not in [n.lower() for n in payload["predicted_only"]], (
        "acetic acid ships coefficients AND is still listed predicted-only"
    )


def test_the_acetic_acid_coefficients_are_the_papers_own():
    """A transcription oracle, against numbers typed here from the PDF.

    The paper is not open access, so these were read by eye -- which is
    exactly the case the Drago audit exists as a warning about, where one
    value in 53 was out by 0.01 and no averaged validation could see it.
    """
    coefficients = abraham.solvent_coefficients("acetic acid")
    for name, expected in _STOVALL_EQ6.items():
        assert getattr(coefficients, name) == pytest.approx(expected, abs=1e-9), (
            f"acetic acid's {name} is {getattr(coefficients, name)}, "
            f"not Stovall 2015 Eq. (6)'s {expected}"
        )


def test_acetic_acid_carries_the_intercept_the_predicted_table_lacks():
    """`c = 0.175`, and the reason it matters is not tidiness.

    The predicted table is the paper's `c = 0` refit, which exists to make
    solvents comparable with one another. The solubility equation needs
    the intercept, so a predicted row is the wrong PARAMETERISATION and
    not merely a less accurate one -- that was half the recorded refusal.
    """
    assert abraham.solvent_coefficients("acetic acid").c != 0.0


def test_the_measured_errors_are_what_made_this_shippable():
    """The refusal was decided by propagation; so is the acceptance.

    `sum(|coefficient error| * descriptor)` -- the same arithmetic the
    original assessment used, which is why the predicted column is
    recomputed here rather than quoted: reproducing 1.57 / 1.34 / 0.51 is
    what says this is the same measurement and not a new one that happens
    to agree.
    """
    for label, smiles, predicted_was in (
        ("aspirin", "CC(=O)Oc1ccccc1C(=O)O", 1.57),
        ("ibuprofen", "CC(C)Cc1ccc(cc1)C(C)C(=O)O", 1.34),
        ("benzene", "c1ccccc1", 0.51),
    ):
        solute = abraham.solute_descriptors(_mol(smiles))
        assert solute is not None, f"setup: no descriptors for {label}"
        terms = {k: abs(getattr(solute, k)) for k in ("e", "s", "a", "b", "v")}

        predicted = sum(
            abraham.PREDICTED_COEFFICIENT_OOB_RMSE[k] * terms[k] for k in terms
        )
        measured = sum(_STOVALL_EQ6_SE[k] * terms[k] for k in terms)

        assert predicted == pytest.approx(predicted_was, abs=0.01), (
            f"{label}: the predicted-set propagation now gives {predicted:.2f}, not the "
            f"{predicted_was} the refusal recorded -- the arithmetic moved, so the "
            "comparison below is no longer against the same thing"
        )
        assert measured < abraham.MAX_PROPAGATED_UNCERTAINTY_LOG, (
            f"{label}: measured propagation {measured:.2f} still exceeds the ceiling"
        )
        assert measured < predicted


def test_caffeines_refusal_is_about_caffeine_and_not_about_acetic_acid():
    """THE SCOPING THIS COMMIT MUST NOT OVERSTATE.

    The plan for this work listed caffeine as "was refused, now passes",
    on the coefficient-error propagation. That is true of that
    propagation and NOT true of the module, because the shipped bound is
    a different quantity: `worst_case_uncertainty` propagates the
    SOLUTE's own measurement disagreement, and caffeine's descriptors
    come from two literature sources that disagree.

    So caffeine is refused in acetic acid -- and equally in solvents that
    have shipped since long before this. Asserting that here is what
    stops a future reader reading the acceptance above as broader than it
    is.
    """
    caffeine = _mol("Cn1cnc2c1c(=O)n(C)c(=O)n2C")
    refusals = {
        solvent: isinstance(abraham.solvent_shift(caffeine, solvent), str)
        for solvent in ("acetic acid", "ethanol", "toluene", "hexane")
    }
    assert all(refusals.values()), (
        f"caffeine is no longer refused everywhere: {refusals} -- if that changed "
        "deliberately, this test is the place that said it was solvent-independent"
    )


def test_the_table_says_which_solvent_came_from_which_paper():
    """91 solvents from one source and 1 from another is a provenance claim.

    The file-level `_source_key` can no longer speak for every row, so a
    reader must be able to tell them apart without inferring it.
    """
    payload = json.loads(
        (Path(abraham.__file__).parent / "data" / "abraham_solvents.json").read_text(
            encoding="utf-8"
        )
    )
    assert payload["solvent_sources"]["acetic acid"] == "stovall2015"
    assert "stovall2015" in payload["_supplementary_source_keys"]
    assert payload["_source_key"] == "bradley2015", (
        "the majority source changed without this guard being updated"
    )
    errors = payload["solvent_standard_errors"]["acetic acid"]
    assert errors == pytest.approx(_STOVALL_EQ6_SE, abs=1e-9)
