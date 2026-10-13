"""The Lewis pairing window: what it shows, what each button does, and what it never does (`RECIPES_DESIGN.md` 8).

A fake host over the REAL evaluator and real stored-run objects, so the rows, the buttons and the answer all come from
real evaluations. Nothing starts ORCA, and the one thing a job's button may do is ask for a panel.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from PySide6.QtWidgets import QComboBox, QLabel, QPushButton

from openchem.chem.lewis_pairing_eval import evaluate_lewis_pairing
from openchem.domain.lewis_pairing import LEWIS_PAIRING
from openchem.ui.dialogs.lewis_pairing_dialog import LewisPairingDialog, PairingContext, PairingHost
from tests.lewis_helpers import METHOD, borane, carbon_monoxide, member, stored_run


class FakeProject:
    """The host side, over real members: evaluation is the real evaluator, applying picks as the service does."""

    def __init__(self, *members, orca=True, conformers=1):
        self.members = {m.facts.molecule_uuid: m for m in members}
        self.selected = next(iter(self.members), None)
        self.orca = orca
        self.conformers = conformers
        self.kept = []
        self.keep_result = True
        self.calls = []

    def host(self) -> PairingHost:
        return PairingHost(
            molecules=lambda: [(m.facts.label, uuid) for uuid, m in self.members.items()],
            selected_uuid=lambda: self.selected,
            evaluate=self.evaluate,
            context=self.context,
            keep=self.keep,
        )

    def evaluate(self, first, second, *, method_basis, solvent="", role="auto", picks=None):
        self.calls.append((first, second, method_basis, solvent, role, dict(picks or {})))
        picks = picks or {}

        def with_picks(uuid, slot):
            m = self.members[uuid]
            return replace(m, facts=replace(m.facts, picks=dict(picks.get(slot, {}))))

        return evaluate_lewis_pairing(
            with_picks(first, "first"), with_picks(second, "second"), method_basis=method_basis, solvent=solvent, role=role
        )

    def context(self) -> PairingContext:
        return PairingContext(
            names={u: m.facts.label for u, m in self.members.items()},
            formal_charges={u: 0 for u in self.members},
            conformer_counts={u: self.conformers for u in self.members},
            orca_configured=self.orca,
        )

    def keep(self, run):
        self.kept.append(run)
        return self.keep_result


def _dialog(qapp, project: FakeProject) -> LewisPairingDialog:
    dialog = LewisPairingDialog(project.host())
    dialog.select_molecules("bh3", "co")
    dialog.set_parameters(role="acid")
    return dialog


def _texts(dialog) -> str:
    return "\n".join(label.text() for label in dialog.findChildren(QLabel))


def _buttons(dialog, text: str):
    return [b for b in dialog.findChildren(QPushButton) if b.text() == text]


# --- opening -----------------------------------------------------------------------------------------------------


def test_it_opens_on_the_selected_molecule_and_another_and_evaluates_at_once(qapp):
    project = FakeProject(borane(), carbon_monoxide())
    dialog = LewisPairingDialog(project.host())
    snapshot = dialog.snapshot()
    assert (snapshot["first"], snapshot["second"]) == ("bh3", "co")
    assert snapshot["status"] is not None and project.calls, "it evaluated without being asked"


def test_it_starts_on_the_first_preset_in_gas_phase_with_the_role_worked_out(qapp):
    dialog = LewisPairingDialog(FakeProject(borane(), carbon_monoxide()).host())
    snapshot = dialog.snapshot()
    assert (snapshot["method_basis"], snapshot["solvent"], snapshot["role"]) == (METHOD, "", "auto")


def test_it_is_modeless(qapp):
    assert not LewisPairingDialog(FakeProject(borane(), carbon_monoxide()).host()).isModal()


def test_with_one_molecule_it_says_a_pairing_needs_two_and_evaluates_nothing(qapp):
    project = FakeProject(borane())
    dialog = LewisPairingDialog(project.host())
    assert "needs two" in dialog.snapshot()["headline"]
    assert project.calls == [] and not dialog.snapshot()["keep_enabled"]


def test_the_second_picker_never_defaults_to_the_first_molecule(qapp):
    """The bug that the one-molecule test found: a combo selects its first item, so the lone molecule was paired
    with itself."""
    dialog = LewisPairingDialog(FakeProject(borane()).host())
    assert dialog.snapshot()["second"] is None and dialog.snapshot()["first"] == "bh3"
    two = LewisPairingDialog(FakeProject(borane(), carbon_monoxide()).host())
    assert two.snapshot()["first"] != two.snapshot()["second"]


def test_a_second_molecule_added_later_fills_an_empty_second_picker(qapp):
    project = FakeProject(borane())
    dialog = LewisPairingDialog(project.host())
    project.members["co"] = carbon_monoxide()
    dialog.refresh()
    assert (dialog.snapshot()["first"], dialog.snapshot()["second"]) == ("bh3", "co")
    assert dialog.snapshot()["status"] is not None


def test_a_second_pick_that_has_gone_leaves_the_picker_empty_and_not_on_the_first_molecule(qapp):
    """The other project has one molecule: the old second pick no longer exists, and item 0 is the first molecule."""
    project = FakeProject(borane(), carbon_monoxide())
    dialog = _dialog(qapp, project)
    project.members = {"water": member("O", "water", "water", [])}
    project.selected = "water"
    dialog.refresh()
    assert dialog.snapshot()["first"] == "water" and dialog.snapshot()["second"] is None


def test_a_deliberate_self_pairing_survives_a_refresh(qapp):
    project = FakeProject(borane(), carbon_monoxide())
    dialog = _dialog(qapp, project)
    dialog.select_molecules("co", "co")
    dialog.refresh()
    assert dialog.snapshot()["first"] == dialog.snapshot()["second"] == "co"


def test_a_molecule_can_be_paired_with_itself_when_the_person_chooses_to(qapp):
    """Water with water is a question. It is only not a default."""
    project = FakeProject(borane(), carbon_monoxide())
    dialog = _dialog(qapp, project)
    dialog.select_molecules("co", "co")
    assert dialog.snapshot()["first"] == dialog.snapshot()["second"] == "co" and dialog.snapshot()["status"] is not None


def test_with_no_molecules_it_does_not_crash(qapp):
    dialog = LewisPairingDialog(FakeProject().host())
    assert dialog.snapshot()["status"] is None and "needs two" in dialog.snapshot()["headline"]


# --- a complete answer -------------------------------------------------------------------------------------------


def test_a_complete_pairing_says_so_shows_every_job_done_and_the_answer(qapp):
    dialog = _dialog(qapp, FakeProject(borane(), carbon_monoxide()))
    snapshot = dialog.snapshot()
    assert snapshot["status"] == "completed" and snapshot["headline"].startswith("Complete.")
    assert dialog._answer.currentWidget() is dialog._facts, "the answer is what is under the jobs"
    assert [j["state"] for j in snapshot["jobs"]] == ["completed"] * 4
    assert snapshot["has_result"] and any("Frontier orbital gap" in line for line in snapshot["result_lines"])
    assert "Done:" in _texts(dialog) and "To do:" not in _texts(dialog)


def test_the_answer_gives_way_to_a_note_and_back_as_the_evidence_comes_and_goes(qapp):
    """The transition, not only the two ends: the stack must follow every evaluation."""
    dialog = _dialog(qapp, FakeProject(borane(), carbon_monoxide()))
    assert dialog._answer.currentWidget() is dialog._facts
    dialog.set_parameters(method_basis="PBE0 def2-TZVP")  # the stored runs are at another level: no answer
    assert dialog._answer.currentWidget() is dialog._no_answer and dialog._no_answer.text().startswith("No answer yet")
    dialog.set_parameters(method_basis=METHOD)
    assert dialog._answer.currentWidget() is dialog._facts


def test_a_done_job_is_one_line_naming_the_job_and_a_short_run_id(qapp):
    dialog = _dialog(qapp, FakeProject(borane(), carbon_monoxide()))
    done = [l.text() for l in dialog.findChildren(QLabel) if l.text().startswith("<b>Done:</b>")]
    assert len(done) == 4
    assert "Single point on BH3: HOMO and LUMO energies (from stored run bh3-sp)" in done[0]
    assert "To do" not in "".join(done)


def test_a_done_job_has_no_button_because_there_is_nothing_to_run(qapp):
    dialog = _dialog(qapp, FakeProject(borane(), carbon_monoxide()))
    assert _buttons(dialog, "Open the Quantum Chemistry panel for this job") == []
    assert dialog.press_job("sp_first") is False


# --- a gap -------------------------------------------------------------------------------------------------------


def test_a_missing_job_is_a_row_to_do_with_the_gap_in_words_and_what_it_would_run_with(qapp):
    dialog = _dialog(qapp, FakeProject(borane(), carbon_monoxide(hardness=False)))
    snapshot = dialog.snapshot()
    assert snapshot["status"] == "partial" and "not a complete answer" in snapshot["headline"]
    text = _texts(dialog)
    assert "To do:" in text and "Delta-SCF job on CO: hardness" in text
    assert "CO has no delta-SCF run" in text and "B3LYP def2-SVP (gas phase), charge +0" in text
    assert snapshot["has_result"], "the frontier line is still answered"


def test_a_job_with_what_it_needs_says_so_and_one_without_says_what_to_do(qapp):
    ready = _dialog(qapp, FakeProject(borane(), carbon_monoxide(hardness=False)))
    assert "Ready: a 3D conformer for CO, the ORCA executable." in _texts(ready)
    assert "Missing" not in _texts(ready)
    unready = _dialog(qapp, FakeProject(borane(), carbon_monoxide(hardness=False), orca=False, conformers=0))
    text = _texts(unready)
    assert "Missing: the ORCA executable. To fix: set its path in Tools > External Tools." in text
    assert "Missing: a 3D conformer for CO. To fix: generate conformers first" in text
    assert not unready.snapshot()["jobs"][-1]["ready"]


def test_pressing_a_jobs_button_asks_for_the_panel_for_that_molecule_and_that_calculation(qapp):
    dialog = _dialog(qapp, FakeProject(borane(), carbon_monoxide(hardness=False)))
    asked = []
    dialog.job_requested.connect(lambda uuid, calc: asked.append((uuid, calc)))
    assert dialog.press_job("dscf_second") is True
    assert asked == [("co", "delta_scf")]


def test_pressing_a_jobs_button_evaluates_nothing_and_starts_nothing(qapp):
    project = FakeProject(borane(), carbon_monoxide(hardness=False))
    dialog = _dialog(qapp, project)
    before = len(project.calls)
    dialog.press_job("dscf_second")
    assert len(project.calls) == before and project.kept == []


def test_with_nothing_stored_there_is_no_answer_and_the_window_says_why(qapp):
    project = FakeProject(member("B", "bh3", "BH3", []), member("[C-]#[O+]", "co", "CO", []))
    dialog = _dialog(qapp, project)
    snapshot = dialog.snapshot()
    assert snapshot["status"] == "blocked" and not snapshot["has_result"] and not snapshot["keep_enabled"]
    assert dialog._no_answer.text().startswith("No answer yet: No line of evidence could be evaluated")
    assert dialog._answer.currentWidget() is dialog._no_answer, "a note, not an empty facts panel with filter controls"
    assert _texts(dialog).count("To do:") == 4


# --- the form ----------------------------------------------------------------------------------------------------


def test_changing_the_method_evaluates_again_and_reports_runs_at_another_level(qapp):
    project = FakeProject(borane(), carbon_monoxide())
    dialog = _dialog(qapp, project)
    calls = len(project.calls)
    dialog.set_parameters(method_basis="PBE0 def2-TZVP")
    assert len(project.calls) == calls + 1 and project.calls[-1][2] == "PBE0 def2-TZVP"
    assert "B3LYP def2-SVP (gas phase)" in _texts(dialog) and "different scales" in _texts(dialog)


def test_the_role_and_solvent_reach_the_evaluation(qapp):
    project = FakeProject(borane(), carbon_monoxide())
    dialog = _dialog(qapp, project)
    dialog.set_parameters(solvent="Water", role="base")
    first, second, method, solvent, role, _ = project.calls[-1]
    assert (solvent, role) == ("Water", "base")


def test_a_value_that_is_not_a_choice_is_refused(qapp):
    dialog = _dialog(qapp, FakeProject(borane(), carbon_monoxide()))
    with pytest.raises(ValueError, match="not one of the choices"):
        dialog.set_parameters(method_basis="HF STO-3G")


def test_an_evaluation_that_raises_is_shown_not_thrown(qapp):
    project = FakeProject(borane(), carbon_monoxide())
    dialog = _dialog(qapp, project)

    def broken(*args, **kwargs):
        raise ValueError("molecule x is not in the open project")

    project.evaluate = broken
    dialog._host.evaluate = broken
    dialog.refresh()
    assert dialog.snapshot()["headline"] == "Cannot evaluate: molecule x is not in the open project"
    assert not dialog.snapshot()["keep_enabled"]


def test_refresh_picks_up_a_new_molecule_and_keeps_the_pair_by_uuid(qapp):
    project = FakeProject(borane(), carbon_monoxide())
    dialog = _dialog(qapp, project)
    project.members["nh3"] = member("N", "nh3", "NH3", [])
    dialog.refresh()
    assert dialog._first.findData("nh3") >= 0 and dialog._second.findData("nh3") >= 0
    assert (dialog.snapshot()["first"], dialog.snapshot()["second"]) == ("bh3", "co")


# --- choosing among runs -----------------------------------------------------------------------------------------


def _with_earlier_geometries():
    runs = [
        stored_run("co", "co-sp-new", "sp", {"orca.homo_energy": -10.17, "orca.lumo_energy": 1.0},
                   input_fingerprint="n" * 64, completed_at=9.0),
        stored_run("co", "co-sp-old", "sp", {"orca.homo_energy": -11.0, "orca.lumo_energy": 2.0},
                   input_fingerprint="o" * 64, completed_at=3.0),
        stored_run("co", "co-dscf", "delta_scf", {"orca.dscf_hardness": 8.40}),
    ]
    return FakeProject(borane(), member("[C-]#[O+]", "co", "CO", runs))


def test_an_ambiguity_offers_the_candidate_runs_and_choosing_one_settles_it(qapp):
    dialog = _dialog(qapp, _with_earlier_geometries())
    [choice] = dialog.snapshot()["choices"]
    assert choice["slot"] == "second" and choice["calc"] == "sp" and choice["candidates"] == ["co-sp-new", "co-sp-old"]
    assert dialog.snapshot()["status"] == "partial"
    dialog.choose_run("second", "sp", "co-sp-new")
    snapshot = dialog.snapshot()
    assert snapshot["status"] == "completed" and snapshot["choices"] == []
    assert any("Frontier orbital gap: 8.13 eV" in line for line in snapshot["result_lines"])


def test_the_chooser_shows_short_ids_and_keeps_the_full_id_as_what_it_chooses(qapp):
    long_id = "ab12cd34ef56" * 2 + "0123456789abcdef"
    runs = [
        stored_run("co", long_id, "sp", {"orca.homo_energy": -10.17, "orca.lumo_energy": 1.0},
                   input_fingerprint="n" * 64, completed_at=9.0),
        stored_run("co", "co-dscf", "delta_scf", {"orca.dscf_hardness": 8.40}),
    ]
    dialog = _dialog(qapp, FakeProject(borane(), member("[C-]#[O+]", "co", "CO", runs)))
    [combo] = [c for c in dialog.findChildren(QComboBox) if c.property("pick_slot")]
    assert combo.itemText(0) == long_id[:8] and combo.itemData(0) == long_id
    [use] = _buttons(dialog, "Use this run")
    use.click()
    assert dialog.snapshot()["status"] == "completed", "the full id, not the short one, is what was chosen"


def test_the_use_this_run_button_makes_the_choice_from_the_combo(qapp):
    dialog = _dialog(qapp, _with_earlier_geometries())
    [combo] = [c for c in dialog.findChildren(QComboBox) if c.property("pick_slot")]
    combo.setCurrentIndex(combo.findData("co-sp-old"))
    [use] = _buttons(dialog, "Use this run")
    use.click()
    snapshot = dialog.snapshot()
    assert snapshot["status"] == "completed"
    # BH3's LUMO -2.04 less the chosen (older) run's HOMO -11.0
    assert any("Frontier orbital gap: 8.96 eV" in line for line in snapshot["result_lines"])


def test_the_chooser_is_inside_the_job_it_settles_and_names_the_runs_by_short_id_in_the_sentence(qapp):
    """It used to sit below the jobs, out of view in a scrolled pane, and the sentence carried 32-character ids."""
    from PySide6.QtWidgets import QFrame

    dialog = _dialog(qapp, _with_earlier_geometries())
    [combo] = [c for c in dialog.findChildren(QComboBox) if c.property("pick_slot")]
    frame = combo.parentWidget()
    assert isinstance(frame, QFrame)
    labels = " ".join(l.text() for l in frame.findChildren(QLabel))
    assert "Single point on CO: HOMO and LUMO energies" in labels, "the chooser is in the single-point job's row"
    assert "co-sp-ne" in labels and "co-sp-ol" in labels and "co-sp-new" not in labels, "the short forms, 8 characters"
    assert "earlier geometry" in labels
    assert frame.findChildren(QPushButton) and any(b.text() == "Use this run" for b in frame.findChildren(QPushButton))


def test_forgetting_the_choices_returns_to_the_unchosen_evaluation(qapp):
    dialog = _dialog(qapp, _with_earlier_geometries())
    dialog.choose_run("second", "sp", "co-sp-new")
    [forget] = _buttons(dialog, "Forget my choices")
    forget.click()
    assert dialog.snapshot()["status"] == "partial" and dialog.snapshot()["choices"]
    assert _buttons(dialog, "Forget my choices") == [], "nothing left to forget"


@pytest.mark.parametrize("control", ["_solvent", "_method", "_role", "_second", "_first"])
def test_a_choice_is_forgotten_when_a_person_changes_any_control_of_the_form(qapp, control):
    """Through the combo itself, the path a person takes. `set_parameters` clears the choices on its own, so a test
    that only used it would not notice if the combo's own handler stopped doing so."""
    dialog = _dialog(qapp, _with_earlier_geometries())
    dialog.choose_run("second", "sp", "co-sp-new")
    assert dialog.snapshot()["status"] == "completed"
    combo = getattr(dialog, control)
    combo.setCurrentIndex(0 if combo.currentIndex() != 0 else 1)
    assert dialog._picks == {}


def test_a_choice_is_forgotten_when_the_form_changes_because_it_named_a_run_at_one_level(qapp):
    dialog = _dialog(qapp, _with_earlier_geometries())
    dialog.choose_run("second", "sp", "co-sp-new")
    dialog.set_parameters(solvent="Water")
    dialog.set_parameters(solvent="")
    assert dialog.snapshot()["status"] == "partial", "the choice did not survive a change of the form"


# --- keeping -----------------------------------------------------------------------------------------------------


def test_nothing_is_kept_until_the_person_says_so(qapp):
    project = FakeProject(borane(), carbon_monoxide())
    dialog = _dialog(qapp, project)
    assert project.kept == [] and dialog.snapshot()["keep_enabled"] and not dialog.snapshot()["kept"]
    assert "does not change the project" in _texts(dialog)


def test_keeping_files_the_shown_run_once_and_says_so(qapp):
    project = FakeProject(borane(), carbon_monoxide())
    dialog = _dialog(qapp, project)
    shown = dialog._run
    assert dialog.press_keep() is True
    assert project.kept == [shown] and dialog.snapshot()["kept"] and not dialog.snapshot()["keep_enabled"]
    assert "reads as stale" in dialog._keep_note.text()
    assert "listed in Results under each of the two molecules" in dialog._keep_note.text()
    assert dialog.press_keep() is False, "a second press has nothing to keep"


def test_a_new_evaluation_is_a_new_answer_that_can_be_kept_again(qapp):
    project = FakeProject(borane(), carbon_monoxide())
    dialog = _dialog(qapp, project)
    dialog.press_keep()
    dialog.refresh()
    assert dialog.snapshot()["keep_enabled"] and not dialog.snapshot()["kept"]


def test_a_keep_that_fails_is_reported_and_the_answer_stays_unkept(qapp):
    project = FakeProject(borane(), carbon_monoxide())
    project.keep_result = False
    dialog = _dialog(qapp, project)
    dialog.press_keep()
    assert "could not be kept" in dialog._keep_note.text() and not dialog.snapshot()["kept"]
    assert dialog.snapshot()["keep_enabled"], "so it can be tried again"


def test_an_answer_with_no_result_cannot_be_kept(qapp):
    project = FakeProject(member("B", "bh3", "BH3", []), member("[C-]#[O+]", "co", "CO", []))
    dialog = _dialog(qapp, project)
    assert dialog.press_keep() is False and project.kept == []


def test_the_jobs_scroll_apart_from_the_answer_so_the_answer_keeps_its_room(qapp):
    """Four jobs with their requirements are taller than a screen; the answer must not be what gives way."""
    from PySide6.QtWidgets import QScrollArea, QSplitter

    dialog = _dialog(qapp, FakeProject(member("B", "bh3", "BH3", []), member("[C-]#[O+]", "co", "CO", [])))
    assert isinstance(dialog._splitter, QSplitter) and isinstance(dialog._jobs_scroll, QScrollArea)
    assert dialog._splitter.widget(0) is dialog._jobs_scroll and dialog._splitter.widget(1) is dialog._answer
    assert not dialog._splitter.childrenCollapsible()


def test_the_plan_the_window_renders_is_the_shipped_one(qapp):
    """A job row exists for each service step of the recipe; if the recipe grows a job the window must show it."""
    dialog = _dialog(qapp, FakeProject(borane(), carbon_monoxide()))
    steps = [s.step_id for s in LEWIS_PAIRING.steps if s.kind.value == "service"]
    assert [j["step"] for j in dialog.snapshot()["jobs"]] == steps
