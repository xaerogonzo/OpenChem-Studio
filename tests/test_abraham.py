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
    """The paper also predicts coefficients for 293 solvents and says of
    those "not as gospel". Only its 91 measured ones ship."""
    assert len(solvent_names()) == 91
    for required in ("ethanol", "hexane", "methanol", "1-octanol", "toluene"):
        assert solvent_coefficients(required) is not None


def test_acetic_acid_is_absent_and_that_is_deliberate():
    """It appears only in the paper's PREDICTED set. Offering it would mean
    shipping a number its own authors decline to stand behind."""
    assert solvent_coefficients("acetic acid") is None


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
    assert "91 solvents" in outcome


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
