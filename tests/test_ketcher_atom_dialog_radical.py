"""Probe: what does Ketcher's own Atom Properties dialog write when a person picks a Radical (the path `test_ketcher_radical_roundtrip.py` did not click)?

The dialog is reached the way a person reaches it with the select tool: hover the atom and press `/` (the bundle's `handleSlashKey`; a double click opens only the one-field "Label Edit"
box, and the context menu never appeared for synthetic or Qt right-clicks). Every step after that is a real Qt mouse press on the real element: the Radical field, its option, Apply.
Measured 2026-11-24 on the vendored build: the field offers a blank, Monoradical, Diradical (singlet) and Diradical (triplet), and they write the molfile radical codes 2, 1 and 3, the
blank none. So the dialog, the KET property and the molfile agree, and the multiplicity chain of OS1 to OS3 holds for a radical set by the person in the editor.
"""

from __future__ import annotations

import json

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest

from openchem.chem.engine import ChemistryEngine
from openchem.chem.open_shell import rad_codes
from openchem.domain.molecule import MoleculeModel
from tests.test_ketcher_editor_backend import _get_molblock_sync, _ready_backend, _run_js, _run_js_json, _wait_until
from tests.test_ketcher_radical_roundtrip import LONE_C

ENGINE = ChemistryEngine()

#: The dropdown's options by their test id, and the radical code each writes into the molfile.
FINDING_OPTIONS = {"Monoradical": 2, "Diradical (singlet)": 1, "Diradical (triplet)": 3}
#: The multiplicity the application then derives for that lone carbon.
FINDING_MULTIPLICITY = {"Monoradical": 2, "Diradical (singlet)": 1, "Diradical (triplet)": 3}


def _pause(qapp, seconds: float) -> None:
    _wait_until(qapp, lambda: False, timeout_seconds=seconds)


def _centre(qapp, backend, script_body: str) -> QPoint:
    spot = _run_js_json(qapp, backend, script_body)
    assert "__error" not in spot, spot
    return QPoint(int(spot["x"]), int(spot["y"]))


def _atom_position(qapp, backend) -> QPoint:
    return _centre(
        qapp,
        backend,
        "const t = [...document.querySelectorAll('svg text')].find(e => e.textContent === 'C'); const b = t.getBoundingClientRect();"
        " return {x: Math.round(b.left + b.width / 2), y: Math.round(b.top + b.height / 2)};",
    )


def _pick_radical(qapp, backend, option: str) -> None:
    """Open the Atom Properties dialog on the lone atom and choose `option` in its Radical field with real mouse presses, then Apply."""
    view = backend.widget()
    target = view.focusProxy() or view
    atom = _atom_position(qapp, backend)
    _run_js(qapp, backend, "window.ketcher.editor.tool('select'); window.ketcher.editor.selection(null); 1")
    QTest.mouseMove(target, QPoint(atom.x() - 120, atom.y() - 120))
    _pause(qapp, 0.3)
    QTest.mouseMove(target, atom)
    _pause(qapp, 0.6)
    QTest.keyClick(target, Qt.Key_Slash)
    assert _wait_until(qapp, lambda: bool(_run_js(qapp, backend, "!!document.querySelector('[data-testid=\"label-input\"]')")), timeout_seconds=10), "the Atom Properties dialog did not open"

    field = _centre(
        qapp,
        backend,
        "const l = [...document.querySelectorAll('label')].find(e => e.textContent.startsWith('Radical')); const b = l.querySelector('div').getBoundingClientRect();"
        " return {x: Math.round(b.left + b.width / 2), y: Math.round(b.top + b.height / 2)};",
    )
    QTest.mouseClick(target, Qt.LeftButton, Qt.NoModifier, field)
    _pause(qapp, 0.6)
    chosen = _centre(
        qapp,
        backend,
        "const o = document.querySelector('[data-testid=\"%s-option\"]'); const b = o.getBoundingClientRect(); return {x: Math.round(b.left + b.width / 2), y: Math.round(b.top + b.height / 2)};" % option,
    )
    QTest.mouseClick(target, Qt.LeftButton, Qt.NoModifier, chosen)
    _pause(qapp, 0.4)
    apply = _centre(
        qapp,
        backend,
        "const b = document.querySelector('[data-testid=\"OK\"]').getBoundingClientRect(); return {x: Math.round(b.left + b.width / 2), y: Math.round(b.top + b.height / 2)};",
    )
    QTest.mouseClick(target, Qt.LeftButton, Qt.NoModifier, apply)
    _pause(qapp, 1.0)


def _drawn_lone_carbon(qapp, backend) -> None:
    plain = LONE_C.replace("M  RAD  1   1   {code}\n", "")
    _run_js(qapp, backend, "window.ketcher.setMolecule(%s); 1" % json.dumps(plain))
    _pause(qapp, 1.5)


@pytest.mark.parametrize("option", list(FINDING_OPTIONS))
def test_a_radical_chosen_in_ketchers_atom_dialog_is_written_as_its_molfile_code(qapp, option):
    backend = _ready_backend(qapp, shown=True)
    _drawn_lone_carbon(qapp, backend)
    _pick_radical(qapp, backend, option)
    returned = _get_molblock_sync(qapp, backend, timeout_seconds=10) or ""
    assert rad_codes(returned) == {0: FINDING_OPTIONS[option]}, f"{option}: {rad_codes(returned)!r}"

    model = MoleculeModel(display_name="drawn")
    ENGINE.set_structure_from_molblock(model, returned)
    assert ENGINE.default_multiplicity(model) == FINDING_MULTIPLICITY[option]
