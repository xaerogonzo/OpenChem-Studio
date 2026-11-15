"""The salt-composition window: modes, picks, and the standing disclaimer."""

from __future__ import annotations

from openchem.domain.salt_preview import (
    DISCLAIMER,
    MODE_ANALYZE,
    MODE_NEUTRALS,
    SaltPreview,
    make_preview,
)
from openchem.ui.dialogs.salt_composition_dialog import SaltCompositionDialog, SaltHost


class FakeProject:
    def __init__(self, *pairs: tuple[str, str]):
        self.members = list(pairs)
        self.selected = self.members[0][1] if self.members else None
        self.calls: list[tuple[str, str | None, str | None]] = []

    def host(self) -> SaltHost:
        def evaluate(mode, first, second):
            self.calls.append((mode, first, second))
            return make_preview(mode, f"{mode}:{first}:{second}", charge_valid=True)

        return SaltHost(
            molecules=lambda: self.members,
            selected_uuid=lambda: self.selected,
            evaluate=evaluate,
        )


def test_it_is_modeless(qapp):
    assert not SaltCompositionDialog(FakeProject(("a", "aa"), ("b", "bb")).host()).isModal()


def test_it_opens_on_the_selected_molecule_and_another(qapp):
    project = FakeProject(("amine", "a"), ("acid", "b"))
    dialog = SaltCompositionDialog(project.host())
    snap = dialog.snapshot()
    assert (snap["first"], snap["second"]) == ("a", "b")
    assert snap["disclaimer"] == DISCLAIMER
    assert DISCLAIMER in snap["body"]
    assert project.calls


def test_the_second_picker_never_defaults_to_the_first_molecule(qapp):
    dialog = SaltCompositionDialog(FakeProject(("amine", "a")).host())
    assert dialog.snapshot()["second"] is None and dialog.snapshot()["first"] == "a"


def test_analyze_does_not_send_a_second_molecule(qapp):
    project = FakeProject(("salt", "s"), ("other", "o"))
    dialog = SaltCompositionDialog(project.host())
    dialog.set_mode(MODE_ANALYZE)
    project.calls.clear()
    dialog.select_molecules("s", "o")
    assert project.calls[-1] == (MODE_ANALYZE, "s", None)


def test_neutrals_sends_both(qapp):
    project = FakeProject(("amine", "a"), ("acid", "b"))
    dialog = SaltCompositionDialog(project.host())
    dialog.set_mode(MODE_NEUTRALS)
    assert project.calls[-1][0] == MODE_NEUTRALS
    assert project.calls[-1][1:] == ("a", "b")


def test_one_molecule_in_a_pair_mode_says_it_needs_two(qapp):
    def evaluate(mode, first, second):
        return SaltPreview("A pair needs two molecules.", DISCLAIMER, None, mode, ())

    dialog = SaltCompositionDialog(SaltHost(
        molecules=lambda: [("amine", "a")],
        selected_uuid=lambda: "a",
        evaluate=evaluate,
    ))
    dialog.set_mode(MODE_NEUTRALS)
    assert "two" in dialog.snapshot()["headline"]
