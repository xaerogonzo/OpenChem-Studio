"""ORCA's Local Energy Decomposition, against a real run.

The fixture below is sliced verbatim out of an ORCA 6.1.1 compound job
(`build_led_input` for BH3-CO, `! DLPNO-CCSD(T) cc-pVDZ cc-pVDZ/C
cc-pVTZ/JK TightPNO LED`, exit 0, three energies). Nothing in it was
retyped -- a fixture labelled "from a real run" with numbers typed from
memory has already cost this project once, and the loose tolerances that
hid it were the other half. The assertions here are tight enough that a
wrong fixture could not pass.
"""

from __future__ import annotations

import pytest

from openchem.chem.orca_led import (
    HARTREE_KCAL,
    build_led_input,
    estimate_led_cost,
    parse_led,
)

REAL_LED_OUTPUT = """INTER- vs INTRA-FRAGMENT CORRELATION ENERGIES (Eh)
--------------------------------------------------

                                   Fragment   1            Fragment   2            
                         ----------------------  ----------------------  
Intra strong pairs              -0.111999424262        -0.282373513315  sum=       -0.394372937577
Intra triples                   -0.001624601702        -0.008608965943  sum=       -0.010233567645
Intra weak pairs                -0.000005079723        -0.000010431532  sum=       -0.000015511255
Singles contribution            -0.000000600611        -0.000002832681  sum=       -0.000003433292
                         ----------------------  ----------------------  
                                -0.113629706298        -0.290995743471  sum=       -0.404625449769


Interaction correlation for Fragments   2 and   1:
--------------------------------------------------
Inter strong pairs               -0.035165884468 (  -22.067 kcal/mol)
Inter triples                    -0.003977111489 (   -2.496 kcal/mol)
Inter weak pairs                 -0.000024358722 (   -0.015 kcal/mol)
                          ----------------------
Total interaction                -0.039167354680 (  -24.578 kcal/mol)
 

Sum of INTRA-fragment correlation energies  =        -0.404625449769
Sum of INTER-fragment correlation energies  =        -0.039167354680
                                              ---------------------
Total correlation energy                    =        -0.443792804450

INTER- vs INTRA-FRAGMENT TOTAL ENERGIES (Eh)
--------------------------------------------

                                   Fragment   1            Fragment   2            
                         ----------------------  ----------------------  
Intra REF. energy              -26.128991518614      -112.372466810670  sum=     -138.501458329284
Intra Correlation energy        -0.113629706298        -0.290995743471  sum=       -0.404625449769
                         ----------------------  ----------------------  
                               -26.242621224912      -112.663462554142  sum=     -138.906083779053

Interaction of Fragments   2 and   1:
-------------------------------------
Interfragment reference          -0.643227862568 ( -403.631 kcal/mol)
Interfragment correlation        -0.039167354680 (  -24.578 kcal/mol)
                          ----------------------
Total interaction                -0.682395217248 ( -428.209 kcal/mol)


Sum of INTRA-fragment total energies        =      -138.906083779053
Sum of INTER-fragment total energies        =        -0.682395217248
                                              ---------------------
Total energy                                =      -139.588478996301

FINAL SUMMARY DLPNO-CCSD ENERGY DECOMPOSITION (Eh)
------------------------------------------------- 
 
Intrafragment REF. energy:                   
Intra fragment   1 (REF.)              -26.128991519     
Intra fragment   2 (REF.)              -112.372466811     

Interaction of fragments  2 and  1:  
Electrostatics (REF.)                  -0.532102458 
Exchange (REF.)                        -0.111125405 
Dispersion (strong pairs)              -0.014609556 
Dispersion (weak pairs)                -0.000024359 

Sum of non dispersive correlation terms: 
Non dispersion (strong pairs)          -0.414932699  
Non dispersion (weak pairs)            -0.000015511

MAXIMUM NO OF ITERATIONS EXCEEDED - LOCALIZATION NOT CONVERGED

E(0)                                       ...   -139.144764357

E(0)                                       ...   -139.144764357

Final correlation energy                   ...     -0.443792804

FINAL SINGLE POINT ENERGY      -139.588557161582

E(0)                                       ...    -26.358201876

E(0)                                       ...    -26.358201876

Final correlation energy                   ...     -0.118068120

FINAL SINGLE POINT ENERGY       -26.476269996270

E(0)                                       ...   -112.749117379

E(0)                                       ...   -112.749117379

Final correlation energy                   ...     -0.304804992

FINAL SINGLE POINT ENERGY      -113.053922370960
"""


BH3CO = [
    ("B", 0.0, 0.0, 0.0),
    ("H", 1.098, 0.0, -0.320),
    ("H", -0.549, 0.951, -0.320),
    ("H", -0.549, -0.951, -0.320),
    ("C", 0.0, 0.0, 1.540),
    ("O", 0.0, 0.0, 2.670),
]
FRAGMENTS = [1, 1, 1, 1, 2, 2]


# --- the input ----------------------------------------------------------


def test_the_input_writes_three_jobs_not_one():
    """A single-point LED cannot give a binding energy: ORCA reports
    -428 kcal/mol for BH3-CO, whose bond enthalpy is near -25. The isolated
    fragments are what turn that into an interaction energy."""
    text = build_led_input(BH3CO, FRAGMENTS)
    assert text.count("$new_job") == 2
    assert text.count("* xyz") == 3


def test_the_fragment_jobs_override_the_initial_guess():
    """Without `PModel` the compound job dies at job 2 with "Input geometry
    does not match current geometry" -- ORCA restarts from the previous
    job's orbitals, and a fragment has fewer atoms. Measured: exit 55, one
    energy instead of three."""
    text = build_led_input(BH3CO, FRAGMENTS)
    jobs = text.split("$new_job")
    assert "PModel" not in jobs[0], "the complex must not need a guess override"
    for job in jobs[1:]:
        assert "PModel" in job


def test_only_the_complex_carries_the_led_keyword():
    """There is nothing to decompose in a single molecule, and ORCA stops
    if asked."""
    jobs = build_led_input(BH3CO, FRAGMENTS).split("$new_job")
    assert " LED" in jobs[0]
    for job in jobs[1:]:
        assert " LED" not in job


def test_atoms_carry_their_fragment_label_in_orcas_notation():
    complex_job = build_led_input(BH3CO, FRAGMENTS).split("$new_job")[0]
    assert "B(1)" in complex_job
    assert "C(2)" in complex_job
    assert "O(2)" in complex_job


def test_the_fragments_keep_the_geometry_they_have_in_the_complex():
    """Relaxing one would fold its relaxation energy into the decomposition
    invisibly, and the result would no longer be a vertical interaction
    energy."""
    text = build_led_input(BH3CO, FRAGMENTS)
    assert "1.540000" in text.split("$new_job")[2], "the CO fragment moved"
    assert "Opt" not in text


def test_a_mismatched_fragment_list_is_refused():
    with pytest.raises(ValueError, match="fragment labels"):
        build_led_input(BH3CO, [1, 1, 2])


@pytest.mark.parametrize("fragments", [[1] * 6, [1, 1, 2, 2, 3, 3]])
def test_led_needs_exactly_two_fragments(fragments):
    with pytest.raises(ValueError, match="two fragments"):
        build_led_input(BH3CO, fragments)


# --- the parse ----------------------------------------------------------


def test_the_decomposition_reconciles_with_the_interaction_energy():
    """The criterion this phase was gated on: the terms must add up to the
    energy difference the same output reports, or the parser is wrong."""
    result = parse_led(REAL_LED_OUTPUT)
    assert result, result.error

    total = sum(term.hartree for term in result.terms)
    assert total == pytest.approx(result.interaction_hartree, abs=1e-4)
    # The residual is the triples-partitioning gap between the LED's own
    # total and FINAL SINGLE POINT ENERGY: 0.049 kcal/mol, not slop.
    assert abs(result.residual_kcal) < 0.1


def test_the_interaction_energy_is_the_supermolecular_difference():
    result = parse_led(REAL_LED_OUTPUT)
    assert result.complex_energy == pytest.approx(-139.588557161582, abs=1e-9)
    assert result.fragment_energies == pytest.approx(
        (-26.476269996270, -113.053922370960), abs=1e-9
    )
    assert result.interaction_hartree == pytest.approx(
        -139.588557161582 + 26.476269996270 + 113.053922370960, abs=1e-12
    )
    assert result.interaction_kcal == pytest.approx(-36.62, abs=0.01)


@pytest.mark.parametrize(
    "label,kcal",
    [
        ("Electronic preparation", 380.18),
        ("Electrostatics", -333.90),
        ("Exchange", -69.73),
        ("Correlation preparation", 11.45),
        ("Dispersion", -11.68),
        ("Charge transfer and non-dispersive correlation", -12.90),
    ],
)
def test_each_term_has_the_value_the_real_run_gives(label, kcal):
    """Tight tolerances on purpose. `abs=0.01` on a hartree quantity is
    loose enough to hide a fixture typed from memory, which is how the
    delta-SCF fixture went wrong."""
    result = parse_led(REAL_LED_OUTPUT)
    term = next(t for t in result.terms if t.label == label)
    assert term.kcal == pytest.approx(kcal, abs=0.01)


def test_electronic_preparation_is_unfavourable():
    """Distorting a fragment's density away from its isolated form always
    costs energy. A wrong sign here means the isolated-fragment energies
    came from the wrong job -- which happened: taking the last two `E(0)`
    matches off the whole text read both from the SAME fragment and gave
    +86.99 Eh against a true +0.61."""
    result = parse_led(REAL_LED_OUTPUT)
    preparation = next(t for t in result.terms if t.label == "Electronic preparation")
    assert preparation.hartree > 0
    assert preparation.hartree == pytest.approx(0.605860925, abs=1e-6)


def test_the_summary_blocks_non_dispersion_term_is_not_reported_as_interaction():
    """`Non dispersion (strong pairs)` is -0.4149 Eh (-260 kcal/mol) and
    decomposes the TOTAL correlation energy, intra-fragment included. It is
    not an interaction term, and reporting it as one was the design this
    replaced."""
    result = parse_led(REAL_LED_OUTPUT)
    assert "-0.414932699" in REAL_LED_OUTPUT, "the fixture must contain the trap"
    for term in result.terms:
        assert abs(term.hartree) < 1.0, f"{term.label} looks like a total, not an interaction"


def test_the_localization_warning_is_surfaced():
    """It appeared twice in the reference run and the job still finished
    with plausible numbers -- which is exactly why it must be shown."""
    result = parse_led(REAL_LED_OUTPUT)
    assert any("localisation did not converge" in w for w in result.warnings)


def test_orcas_own_caveat_travels_with_the_result():
    result = parse_led(REAL_LED_OUTPUT)
    assert any("to some extent, arbitrary" in note for note in result.limitations)
    assert any("counterpoise" in note for note in result.limitations)
    assert any("vertical interaction energy" in note for note in result.limitations)


def test_an_output_with_no_led_block_is_refused_not_guessed():
    result = parse_led("FINAL SINGLE POINT ENERGY      -139.588557161582\n")
    assert not result
    assert "No LED decomposition" in result.error


def test_an_output_missing_the_fragment_jobs_says_so():
    """The single-job case -- the one that yields a plausible and wrong
    -428 kcal/mol if it is not caught."""
    complex_only = REAL_LED_OUTPUT.split("FINAL SINGLE POINT ENERGY")[0] + (
        "FINAL SINGLE POINT ENERGY      -139.588557161582\n"
    )
    result = parse_led(complex_only)
    assert not result
    assert "fragment" in result.error.lower()
    assert "-428 kcal/mol" in result.error


def test_a_big_residual_is_reported_as_a_limitation():
    """A decomposition whose parts do not add up must say so rather than
    presenting the terms as though they did."""
    broken = REAL_LED_OUTPUT.replace(
        "Electrostatics (REF.)                  -0.532102458",
        "Electrostatics (REF.)                  -0.432102458",
    )
    result = parse_led(broken)
    assert result
    assert any("do not add up" in note for note in result.limitations)


# --- the cost -----------------------------------------------------------


def test_the_cost_estimate_grows_steeply_with_size():
    small = estimate_led_cost(["B", "H", "H", "H", "C", "O"])
    large = estimate_led_cost(["C"] * 20 + ["H"] * 20)
    assert large.minutes > small.minutes * 10
    assert large.scratch_mb > small.scratch_mb * 10


def test_a_job_too_large_to_run_says_so_rather_than_starting():
    estimate = estimate_led_cost(["C"] * 40 + ["H"] * 40 + ["N"] * 10)
    assert estimate.should_warn
    assert "too large" in estimate.advice


def test_the_estimate_names_scratch_disk_not_just_time():
    """The service gives every job a `tempfile.mkdtemp`, and a full drive
    mid-run loses hours of compute with an error naming the disk rather
    than the job that filled it."""
    estimate = estimate_led_cost(["C"] * 20 + ["H"] * 20)
    assert estimate.scratch_mb > 0
    assert "scratch" in estimate.advice


def test_hartree_to_kcal_is_the_codata_value():
    assert HARTREE_KCAL == pytest.approx(627.5095, abs=1e-4)


# --- the estimate against the jobs it was fitted to ----------------------


@pytest.mark.parametrize(
    "label,symbols,functions",
    [
        ("BH3-CO", ["B", "H", "H", "H", "C", "O"], 75),
        ("benzene-water", ["C"] * 6 + ["H"] * 6 + ["O", "H", "H"], 180),
        # Not fitted: the BH3 fragment job, whose count was used to CHECK
        # the per-element numbers rather than to derive them.
        ("BH3 alone", ["B", "H", "H", "H"], 35),
    ],
)
def test_the_basis_function_count_matches_what_orca_reported(label, symbols, functions):
    """The textbook cc-pVDZ contraction is wrong for this job -- it gives
    57 for BH3-CO where ORCA reports 75 -- so the per-element numbers come
    from ORCA's own "Number of basis functions" line."""
    assert estimate_led_cost(symbols).basis_functions == functions


def test_the_runtime_estimate_reproduces_the_measured_jobs():
    """BH3-CO ran in 15 s (23 s for the whole compound input) and
    benzene-water's complex in 595 s. Within a factor of two is all this
    claims; the exponents come from two points and cannot do better."""
    small = estimate_led_cost(["B", "H", "H", "H", "C", "O"])
    large = estimate_led_cost(["C"] * 6 + ["H"] * 6 + ["O", "H", "H"])
    assert 0.5 < small.minutes / (23.0 / 60) < 2.0
    assert 0.5 < large.minutes / (595.0 * 1.5 / 60) < 2.0


def test_the_scratch_estimate_reproduces_the_measured_peaks():
    """102 MB and 1899 MB, sampled while the jobs RAN. The residual left
    on disk afterwards is 3.3 MB for benzene-water -- a factor of 575 out,
    and what the first version of this was anchored on."""
    small = estimate_led_cost(["B", "H", "H", "H", "C", "O"])
    large = estimate_led_cost(["C"] * 6 + ["H"] * 6 + ["O", "H", "H"])
    assert small.scratch_mb == pytest.approx(102, rel=0.2)
    assert large.scratch_mb == pytest.approx(1899, rel=0.2)


def test_a_short_job_with_a_large_scratch_footprint_still_warns():
    """benzene-water is the measured case: ten minutes and 1.9 GB. Time
    alone would wave it through, and a full disk mid-run loses the job."""
    estimate = estimate_led_cost(["C"] * 6 + ["H"] * 6 + ["O", "H", "H"])
    assert estimate.minutes < 30
    assert estimate.scratch_mb > 1024
    assert estimate.should_warn
    assert "GB of scratch disk" in estimate.advice


def test_the_estimate_records_what_it_was_anchored_on():
    """A number with no provenance cannot be re-checked when it drifts."""
    estimate = estimate_led_cost(["C", "O"])
    assert "BH3-CO" in estimate.fields["anchors"]
    assert "benzene-water" in estimate.fields["anchors"]


# --- through the real engine --------------------------------------------


def _embedded(smiles: str):
    from rdkit import Chem
    from rdkit.Chem import AllChem

    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    AllChem.EmbedMolecule(mol, randomSeed=0xF00D)
    return mol


def test_led_is_offered_as_a_calculation_type():
    from openchem.chem.orca_engine import CALC_TYPE_LABELS

    assert CALC_TYPE_LABELS["Interaction energy breakdown (LED)"] == "led"


def test_the_engine_builds_a_three_job_led_input():
    from openchem.chem.orca_engine import OrcaQuantumEngineProvider

    text = OrcaQuantumEngineProvider().build_input(
        _embedded("N.B"), 0, 1, "B3LYP def2-SVP", "led"
    )
    jobs = text.split("$new_job")
    assert len(jobs) == 3
    assert " LED" in jobs[0]
    assert all(" LED" not in job for job in jobs[1:])
    assert all("PModel" in job for job in jobs[1:])


def test_the_chosen_method_and_basis_are_ignored_for_led():
    """LED is defined on DLPNO-CCSD(T). Quietly running the user's B3LYP
    would produce a job ORCA refuses, or worse, one it accepts."""
    from openchem.chem.orca_engine import OrcaQuantumEngineProvider

    text = OrcaQuantumEngineProvider().build_input(
        _embedded("N.B"), 0, 1, "B3LYP def2-SVP", "led"
    )
    assert "B3LYP" not in text
    assert "DLPNO-CCSD(T)" in text


@pytest.mark.parametrize("smiles,count", [("CCO", 1), ("O.O.O", 3)])
def test_a_structure_that_is_not_two_species_is_refused_with_what_to_do(smiles, count):
    """The fragments ARE the disconnected components, so this refusal is
    the correct one rather than an arbitrary limit -- a single connected
    molecule has no partners to decompose an interaction between."""
    from openchem.chem.orca_engine import OrcaQuantumEngineProvider

    with pytest.raises(ValueError, match="two separate species") as caught:
        OrcaQuantumEngineProvider().build_input(
            _embedded(smiles), 0, 1, "B3LYP def2-SVP", "led"
        )
    assert str(count) in str(caught.value)
    assert "separate molecules" in str(caught.value)


# --- feeding the existing adduct evidence --------------------------------


def test_the_decomposition_becomes_adduct_evidence_with_no_shape_change():
    """`AdductEvidence` was built as an unranked list with no combined
    score so that terms like these could join it later -- its own docstring
    names "electrostatic, dispersion, Pauli and charge-transfer terms"."""
    from openchem.chem.orca_led import led_evidence

    evidence = led_evidence(parse_led(REAL_LED_OUTPUT))
    labels = {line.label for line in evidence}
    assert "Electrostatics" in labels
    assert "Dispersion" in labels
    assert "Interaction energy (DLPNO-CCSD(T))" in labels
    assert all(line.units == "kcal/mol" for line in evidence)


def test_no_evidence_line_claims_to_be_a_combined_score():
    """The total is the supermolecular energy difference, not a weighted
    sum of the others dressed up as a ranking."""
    from openchem.chem.orca_led import led_evidence

    evidence = led_evidence(parse_led(REAL_LED_OUTPUT))
    total = next(line for line in evidence if line.line == "led_total")
    assert total.value == pytest.approx(-36.62, abs=0.01)
    assert "counterpoise" in total.note


def test_a_failed_decomposition_still_produces_a_line_that_says_why():
    """An absent line is invisible; a line with no value and a reason is
    the convention the other evidence lines already follow."""
    from openchem.chem.orca_led import led_evidence

    (line,) = led_evidence(parse_led("no LED here"))
    assert line.value is None
    assert not line
    assert "No LED decomposition" in line.note


def test_every_evidence_line_carries_what_the_term_means():
    from openchem.chem.orca_led import led_evidence

    evidence = led_evidence(parse_led(REAL_LED_OUTPUT))
    for line in evidence:
        assert line.note, f"{line.label} has no explanation"


# --- descriptors out of parse_output ------------------------------------


def _led_mol():
    from rdkit import Chem
    from rdkit.Chem import AllChem

    mol = Chem.AddHs(Chem.MolFromSmiles("N.B"))
    AllChem.EmbedMolecule(mol, randomSeed=0xF00D)
    return mol


def test_the_interaction_energy_reaches_the_descriptors():
    from openchem.chem.orca_engine import OrcaQuantumEngineProvider

    descriptors, conformer = OrcaQuantumEngineProvider().parse_output(
        REAL_LED_OUTPUT, _led_mol(), "mol-1", "led"
    )
    by_id = {d.descriptor_id: d for d in descriptors}
    assert by_id["orca.led_interaction"].value == pytest.approx(-36.62, abs=0.01)
    assert by_id["orca.led_dispersion"].value == pytest.approx(-11.68, abs=0.01)
    assert conformer is None, "an LED job optimises nothing"


def test_no_koopmans_descriptors_are_produced_from_an_led_output():
    """An LED output holds THREE orbital tables, and the frontier parsers
    take the last -- which is the second FRAGMENT's. Koopmans numbers from
    it would be about a different species and would look entirely
    reasonable. Same trap delta-SCF already documents for the anion."""
    from openchem.chem.orca_engine import OrcaQuantumEngineProvider

    descriptors, _ = OrcaQuantumEngineProvider().parse_output(
        REAL_LED_OUTPUT, _led_mol(), "mol-1", "led"
    )
    ids = {d.descriptor_id for d in descriptors}
    assert not any("homo" in i or "lumo" in i or "hardness" in i for i in ids), ids


def test_every_led_descriptor_carries_the_caveat_and_the_residual():
    """On the decomposition terms specifically. The SCF energy from the same
    job is the complex's total energy -- a plain observable that needs no
    caveat about a partitioning it takes no part in."""
    from openchem.chem.orca_engine import OrcaQuantumEngineProvider

    descriptors, _ = OrcaQuantumEngineProvider().parse_output(
        REAL_LED_OUTPUT, _led_mol(), "mol-1", "led"
    )
    led_descriptors = [d for d in descriptors if d.descriptor_id.startswith("orca.led_")]
    assert len(led_descriptors) == 7, "one total plus six terms"
    for descriptor in led_descriptors:
        caveat = descriptor.provenance.parameters["caveat"]
        assert "to some extent, arbitrary" in caveat
        assert "localisation did not converge" in caveat
        assert descriptor.provenance.parameters["residual_kcal"] == pytest.approx(
            0.049, abs=0.01
        )


def test_an_unusable_led_output_raises_rather_than_reporting_a_number():
    from openchem.chem.orca_engine import OrcaOutputError, OrcaQuantumEngineProvider

    single_job = REAL_LED_OUTPUT.split("FINAL SINGLE POINT ENERGY")[0] + (
        "FINAL SINGLE POINT ENERGY      -139.588557161582\n"
    )
    with pytest.raises(OrcaOutputError, match="fragment"):
        OrcaQuantumEngineProvider().parse_output(
            single_job, _led_mol(), "mol-1", "led"
        )


# --- the pre-launch cost gate --------------------------------------------


def test_a_single_molecule_is_stopped_before_any_job_is_requested(monkeypatch):
    """The refusal arrives as a dialog rather than as a failed job in the
    log, because the user can act on the first and not the second."""
    from PySide6.QtWidgets import QMessageBox

    from openchem.ui.panels import quantum_chemistry_panel as module

    shown = []
    monkeypatch.setattr(
        QMessageBox, "information", lambda *a, **k: shown.append(a[2] if len(a) > 2 else "")
    )
    confirm = module.QuantumChemistryPanel._confirm_led_cost
    assert confirm(None, _single_molecule()) is False
    assert shown, "nothing was shown"
    assert "two separate species" in shown[0]


def test_an_expensive_job_asks_first_and_no_means_no(monkeypatch):
    """A dialog that appears and then starts the job anyway is worse than
    no dialog: it looks like a safeguard and is not one."""
    from PySide6.QtWidgets import QMessageBox

    from openchem.ui.panels import quantum_chemistry_panel as module

    asked = []

    def refuse(*args, **kwargs):
        asked.append(args[2] if len(args) > 2 else "")
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(QMessageBox, "question", refuse)
    confirm = module.QuantumChemistryPanel._confirm_led_cost
    assert confirm(None, _two_big_fragments()) is False
    assert asked
    assert "scratch disk" in asked[0]


def test_saying_yes_lets_the_job_through(monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from openchem.ui.panels import quantum_chemistry_panel as module

    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes
    )
    confirm = module.QuantumChemistryPanel._confirm_led_cost
    assert confirm(None, _two_big_fragments()) is True


def test_a_cheap_two_fragment_job_is_not_interrupted(monkeypatch):
    """BH3-CO runs in seconds. Asking about it would train the user to
    dismiss the dialog that matters."""
    from PySide6.QtWidgets import QMessageBox

    from openchem.ui.panels import quantum_chemistry_panel as module

    def fail(*args, **kwargs):
        raise AssertionError("a 15-second job should not prompt")

    monkeypatch.setattr(QMessageBox, "question", fail)
    monkeypatch.setattr(QMessageBox, "information", fail)
    confirm = module.QuantumChemistryPanel._confirm_led_cost
    assert confirm(None, _bh3co()) is True


def _single_molecule():
    from rdkit import Chem

    return Chem.AddHs(Chem.MolFromSmiles("CCO"))


def _bh3co():
    from rdkit import Chem

    return Chem.AddHs(Chem.MolFromSmiles("B.[C-]#[O+]"))


def _two_big_fragments():
    from rdkit import Chem

    return Chem.AddHs(Chem.MolFromSmiles("c1ccc2ccccc2c1.c1ccc2ccccc2c1"))


def test_the_fragment_count_comes_from_the_chem_layer():
    """So the UI can decide whether an LED job is runnable without
    importing RDKit. `tests/test_layering.py` forbids that and caught the
    first version of the confirmation dialog doing it."""
    from openchem.chem.orca_led import estimate_led_cost_for

    two = estimate_led_cost_for(_two_big_fragments())
    assert two.fragment_count == 2
    assert two.runnable

    one = estimate_led_cost_for(_single_molecule())
    assert one.fragment_count == 1
    assert not one.runnable
    # The cost fields are still filled in, so a caller that ignores
    # `runnable` gets numbers rather than zeros.
    assert one.basis_functions > 0
