"""The peptide dialog expands through its host and never imports RDKit."""

from __future__ import annotations

from openchem.ui.dialogs.peptide_sequence_dialog import PeptideSequenceDialog, PeptideSequenceHost


def test_a_valid_sequence_is_handed_to_insert(qapp):
    seen: dict[str, object] = {}

    def expand(text: str) -> str:
        seen["expand"] = text
        return "molblock"

    def insert(molblock: str, callback) -> None:
        seen["molblock"] = molblock
        callback(None)

    dialog = PeptideSequenceDialog(PeptideSequenceHost(expand=expand, insert_molblock=insert))
    dialog.set_sequence("AEG")
    dialog._on_insert()
    assert seen == {"expand": "AEG", "molblock": "molblock"}
    assert dialog.snapshot()["status"] == "Inserted."
    dialog.close()


def test_a_refusal_does_not_insert(qapp):
    inserted = []

    def expand(text: str) -> str:
        raise ValueError("Enter a peptide sequence.")

    dialog = PeptideSequenceDialog(
        PeptideSequenceHost(expand=expand, insert_molblock=lambda *_a: inserted.append(True))
    )
    dialog.set_sequence("")
    dialog._on_insert()
    assert inserted == []
    assert "Enter a peptide sequence" in dialog.snapshot()["status"]
    dialog.close()
