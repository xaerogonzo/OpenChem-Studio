"""The IR view, and the routing bug that publishing IR spectra exposed.

`test_a_vibrational_spectrum_never_reaches_the_nmr_path` is the one worth
keeping longest. `SpectrumComputed` carries every spectrum type, and the
quantum panel's handler read `spectrum.values` unconditionally --  which
`VibrationalSpectrumResult` leaves deliberately empty, because an IR peak
belongs to a normal mode rather than to an atom. Nothing raised: the
result rendered as an NMR table with no rows and a 1D signal view built
from no signals, presented as success.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QWidget

from openchem.chem.engine import ChemistryEngine
from openchem.domain.scientific_result import (
    VibrationalMode,
    VibrationalSpectrumResult,
)
from openchem.ui.viewer_backend import ViewerBackend
from openchem.ui.widgets.ir_view_widget import IrViewWidget

WATER_MODES = (
    VibrationalMode(
        wavenumber_cm1=1637.7,
        ir_intensity_km_mol=55.3,
        character="bend",
        displacements=((0.0, 0.0, 0.07), (0.0, 0.43, -0.56), (0.0, -0.43, -0.56)),
    ),
    VibrationalMode(
        wavenumber_cm1=3787.2,
        ir_intensity_km_mol=4.67,
        character="stretch",
        displacements=((0.0, 0.0, 0.05), (0.0, 0.56, 0.43), (0.0, -0.56, 0.43)),
    ),
)


class FakeViewerBackend(ViewerBackend):
    """Records calls instead of driving a real QWebEngineView -- the same
    seam `test_nmr_view_widget.py` uses."""

    def __init__(self) -> None:
        super().__init__()
        self.loaded_molblocks: list[str] = []

    def load_conformer(self, molblock: str) -> None:
        self.loaded_molblocks.append(molblock)

    def set_style(self, style: str) -> None:
        pass

    def clear(self) -> None:
        pass

    def widget(self) -> QWidget:
        return QWidget()


def _spectrum(modes=WATER_MODES, warning: str = "") -> VibrationalSpectrumResult:
    return VibrationalSpectrumResult(
        spectrum_type="ir",
        name="IR Spectrum",
        units="cm-1",
        method="orca",
        molecule_uuid="uuid",
        modes=modes,
        imaginary_warning=warning,
    )


@pytest.fixture
def water_conformer():
    """A real 3D water, built through the conformer service the app uses
    rather than hand-written, so the atom order matches what a real job
    would hand the view."""
    from openchem.chem.conformer_providers import RDKitConformerProvider
    from openchem.domain.molecule import MoleculeModel

    engine = ChemistryEngine()
    molecule = MoleculeModel(display_name="water")
    engine.set_structure_from_smiles(molecule, "O")
    mol = engine.mol_from_model(molecule)
    conformers = RDKitConformerProvider().generate_conformers(mol, 1, optimize=True)
    return engine, engine.mol_to_molblock(conformers[0][0])


@pytest.fixture
def view(qapp, water_conformer):
    """Destroyed deterministically per test -- a QTimer left running would
    keep pushing frames into a backend belonging to a dead widget."""
    engine, _ = water_conformer
    backend = FakeViewerBackend()
    widget = IrViewWidget(engine, backend=backend)
    yield widget, backend
    widget.stop()
    widget.deleteLater()


def test_the_mode_table_lists_every_mode(view, water_conformer):
    widget, _ = view
    _, molblock = water_conformer

    widget.set_spectrum(_spectrum(), molblock)

    assert widget._table.rowCount() == 2
    assert "1637.7" in widget._table.item(0, 0).text()
    assert widget._table.item(0, 1).text() == "55.30"
    assert widget._table.item(0, 2).text() == "bend"


def test_an_imaginary_mode_is_listed_even_though_it_is_not_plotted(view, water_conformer):
    """The plot excludes it -- a negative wavenumber is not a band. The
    TABLE is a record of what the calculation found, and dropping the row
    would make the row count disagree with ORCA's own mode numbering."""
    widget, _ = view
    _, molblock = water_conformer
    modes = (VibrationalMode(wavenumber_cm1=-1436.0, character="bend"),) + WATER_MODES

    widget.set_spectrum(_spectrum(modes), molblock)

    assert widget._table.rowCount() == 3
    assert "imaginary" in widget._table.item(0, 0).text()


def test_the_imaginary_warning_is_shown_prominently(view, water_conformer):
    """`isHidden()`, not `isVisible()`. A child of a widget that was never
    shown reports `isVisible() == False` no matter what `setVisible(True)`
    was called on it -- the same class of trap as `repaint()` doing
    nothing on an unshown widget (CLAUDE.md). `isHidden()` reports the
    explicit state, which is what this is about."""
    widget, _ = view
    _, molblock = water_conformer

    widget.set_spectrum(_spectrum(warning="1 imaginary mode: this is a saddle point"), molblock)

    assert not widget._warning_label.isHidden()
    assert "saddle point" in widget._warning_label.text()


def test_no_warning_label_when_the_geometry_is_a_minimum(view, water_conformer):
    widget, _ = view
    _, molblock = water_conformer

    widget.set_spectrum(_spectrum(), molblock)

    assert widget._warning_label.isHidden()


def test_clicking_a_peak_selects_its_table_row(view, water_conformer):
    widget, _ = view
    _, molblock = water_conformer
    widget.set_spectrum(_spectrum(), molblock)

    widget._on_peak_clicked(1)

    assert widget.selected_mode() == 1


def test_animation_pushes_frames_through_the_viewer(view, water_conformer):
    widget, backend = view
    _, molblock = water_conformer
    widget.set_spectrum(_spectrum(), molblock)
    backend.loaded_molblocks.clear()

    widget._table.selectRow(0)
    widget._animate_button.setChecked(True)
    for _ in range(3):
        widget._advance_frame()

    assert len(backend.loaded_molblocks) == 3
    # Successive frames must actually differ, or the "animation" is the
    # equilibrium geometry redrawn.
    assert len(set(backend.loaded_molblocks)) == 3


def test_stopping_restores_the_equilibrium_geometry(view, water_conformer):
    widget, backend = view
    _, molblock = water_conformer
    widget.set_spectrum(_spectrum(), molblock)
    widget._table.selectRow(0)
    widget._animate_button.setChecked(True)
    widget._advance_frame()

    widget.stop()

    assert backend.loaded_molblocks[-1] == molblock
    assert not widget._animate_button.isChecked()
    assert not widget._timer.isActive()


def test_a_mode_without_displacements_does_not_animate(view, water_conformer):
    widget, _ = view
    _, molblock = water_conformer
    widget.set_spectrum(_spectrum((VibrationalMode(wavenumber_cm1=1600.0),)), molblock)

    widget._table.selectRow(0)
    widget._animate_button.setChecked(True)

    assert not widget._timer.isActive()


def test_animation_is_disabled_without_a_conformer(view):
    """Nothing to displace, so the control must not offer to."""
    widget, _ = view

    widget.set_spectrum(_spectrum(), "")

    assert not widget._animate_button.isEnabled()


# ---------------------------------------------------------------------------
# The panel routing regression
# ---------------------------------------------------------------------------


def test_a_vibrational_spectrum_never_reaches_the_nmr_path(qapp, monkeypatch):
    """A `VibrationalSpectrumResult` must route to the IR view. Before the
    dispatch existed it fell through to the NMR handler, which read the
    deliberately-empty `values` and rendered an empty NMR spectrum as a
    successful result."""
    from openchem.ui.panels import quantum_chemistry_panel as panel_module

    routed: dict[str, object] = {}
    monkeypatch.setattr(
        panel_module.QuantumChemistryPanel,
        "_update_ir_view",
        lambda self, spectrum: routed.setdefault("ir", spectrum),
    )
    monkeypatch.setattr(
        panel_module.QuantumChemistryPanel,
        "_update_nmr_view",
        lambda self, spectrum: routed.setdefault("nmr", spectrum),
    )
    monkeypatch.setattr(
        panel_module.QuantumChemistryPanel,
        "_update_correlation_tabs",
        lambda self, spectrum: routed.setdefault("correlation", spectrum),
    )
    monkeypatch.setattr(
        panel_module.QuantumChemistryPanel,
        "_update_hybrid_tab",
        lambda self, spectrum: routed.setdefault("hybrid", spectrum),
    )

    spectrum = _spectrum()
    panel = panel_module.QuantumChemistryPanel.__new__(panel_module.QuantumChemistryPanel)
    panel._pending_molecule_uuid = "uuid"

    from openchem.events.events import SpectrumComputed

    panel_module.QuantumChemistryPanel._on_spectrum_computed(
        panel, SpectrumComputed(spectrum=spectrum)
    )

    assert routed.get("ir") is spectrum
    assert "nmr" not in routed
    assert "correlation" not in routed
    assert "hybrid" not in routed
