"""The receptor-contents dialog, and the biological-assembly opt-in.

The dialog itself predates these tests; what is covered here is the
choice it now offers, because that choice decides which object gets
docked and because "off by default" is the only thing protecting every
docking result produced so far.
"""

from __future__ import annotations


from openchem.chem.structure_assembly import AssemblyAnnotation, BiologicalAssembly
from openchem.chem.structure_summary import ChainSummary, StructureSummary
from openchem.ui.dialogs.structure_contents_dialog import StructureContentsDialog

import conftest


def _summary() -> StructureSummary:
    return StructureSummary(
        chains=(
            ChainSummary(
                chain_id="A",
                polymer_residue_count=120,
                sequence="MKTAYIAKQRQISFVKSHFSRQ",
                ligand_codes=(),
                water_count=0,
                atom_count=940,
            ),
        )
    )


def _annotation(operator_applications: int) -> AssemblyAnnotation:
    return AssemblyAnnotation(
        assemblies=(
            BiologicalAssembly(
                assembly_id="1",
                chain_ids=("A",),
                operator_applications=operator_applications,
                oligomeric_details="dimeric" if operator_applications > 1 else "monomeric",
            ),
        )
    )


def _dispose(dialog, qapp) -> None:
    conftest.dispose(dialog)
    qapp.processEvents()


def test_building_the_assembly_is_off_until_it_is_asked_for(qapp):
    """Off by default is what protects every docking result produced so
    far. Building silently would change what a saved box means without
    anybody asking for it, so a freshly opened dialog must answer False.
    """
    dialog = StructureContentsDialog(
        "receptor", _summary(), assembly=_annotation(operator_applications=2)
    )
    try:
        assert dialog.build_assembly() is False
        dialog._build_assembly_check.setChecked(True)
        assert dialog.build_assembly() is True
    finally:
        _dispose(dialog, qapp)


def test_the_option_is_not_offered_where_it_would_do_nothing(qapp):
    """A file that already holds its whole biological unit has nothing to
    build, and offering the choice invites somebody to wonder what it
    does. It must answer False even with the widget ticked.

    **Asserted against an explicit flag, never `isVisible()`.** A child of
    a window nobody has shown reports `isVisible() == False` whatever it
    was set to, so a visibility-derived answer would read False under
    every test while looking correct in the running app -- the blindness
    this project already records for `repaint()` and for
    `_help_topic_for_visible_panel`.
    """
    dialog = StructureContentsDialog(
        "receptor", _summary(), assembly=_annotation(operator_applications=1)
    )
    try:
        assert dialog._assembly_can_be_built is False
        dialog._build_assembly_check.setChecked(True)
        assert dialog.build_assembly() is False
    finally:
        _dispose(dialog, qapp)


def test_an_unannotated_structure_offers_nothing_to_build(qapp):
    """Absence of an annotation is normal -- computed models and edited
    files carry none -- and must not read as "buildable"."""
    dialog = StructureContentsDialog("receptor", _summary())
    try:
        assert dialog._assembly_can_be_built is False
        assert dialog.build_assembly() is False
    finally:
        _dispose(dialog, qapp)
