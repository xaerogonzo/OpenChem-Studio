"""The toggles and notes that go with tautomer traces drawn on an NMR spectrum (P5).

A column of one checkbox per tautomer (its colour swatch, its label, and its population ONLY when the distribution
is validated, otherwise its relative energy), one for the fast-exchange average, and below them what the average
is and is not: why it is unavailable, or how many peaks it covers and which it leaves out. Each checkbox shows or
hides one trace on the `NmrSpectrumWidget` it is bound to.

Nothing here computes anything: it is built from a `TautomerOverlay` (`chem.tautomer_nmr.tautomer_overlay`) and
only ever calls the spectrum widget's view-state setters.
"""

from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from openchem.chem.tautomer_nmr import NotAveraged, TautomerOverlay, TautomerTrace
from openchem.ui.widgets.nmr_spectrum_widget import NmrSpectrumWidget

#: How many left-out peaks are listed before the rest are counted.
_LEFT_OUT_LISTED = 6


def _atom(index: int) -> str:
    """The app's one-based display numbering (`atom_index + 1`), never the raw RDKit index."""
    return str(index + 1)


def left_out_lines(not_averaged: tuple[NotAveraged, ...]) -> list[str]:
    """One line per reason, naming the atoms it applies to, so a crowded molecule gives a short list."""
    by_reason: dict[tuple[str, str], list[int]] = {}
    for item in not_averaged:
        by_reason.setdefault((item.nucleus, item.reason), []).append(item.heavy_atom)
    lines = []
    for (nucleus, reason), atoms in by_reason.items():
        symbol = "¹H" if nucleus == "1H" else "¹³C"
        lines.append(f"{symbol} on atom{'s' if len(atoms) > 1 else ''} {', '.join(_atom(a) for a in atoms)}: {reason}")
    return lines


def _trace_text(trace: TautomerTrace) -> str:
    if trace.failure:
        return f"{trace.label}  (no NMR: {trace.failure})"
    if trace.population is not None:
        return f"{trace.label}  {trace.population * 100:.1f}%"
    if trace.relative_energy_kcal is not None:
        return f"{trace.label}  +{trace.relative_energy_kcal:.2f} kcal/mol"
    return trace.label


class TautomerOverlayControls(QWidget):
    """The checkboxes and notes for `spectrum_widget`'s tautomer traces."""

    def __init__(self, spectrum_widget: NmrSpectrumWidget, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._spectrum = spectrum_widget
        self._checks: dict[str, QCheckBox] = {}
        self._rows: list[QWidget] = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._title = QLabel("Tautomer peaks (predicted, gas phase)", self)
        self._title.setStyleSheet("font-weight: bold;")
        layout.addWidget(self._title)
        self._rows_layout = QVBoxLayout()
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self._rows_layout)
        self._note = QLabel("", self)
        self._note.setWordWrap(True)
        self._note.setStyleSheet("color: #666;")
        layout.addWidget(self._note)
        self._left_out = QLabel("", self)
        self._left_out.setWordWrap(True)
        self._left_out.setStyleSheet("color: #666;")
        layout.addWidget(self._left_out)
        self.setVisible(False)

    def set_overlay(self, overlay: TautomerOverlay, element: str, method_basis: str = "") -> None:
        """Draw `overlay` on the spectrum widget and list its traces here. Replaces any earlier overlay.
        `method_basis` is what the tautomer peaks were predicted at, named in the title because it is not
        necessarily what the molecule's own spectrum was predicted at."""
        self._title.setText(
            f"Tautomer peaks (predicted at {method_basis}, gas phase)" if method_basis
            else "Tautomer peaks (predicted, gas phase)"
        )
        self._clear_rows()
        traces = list(overlay.traces)
        if overlay.average is not None:
            traces.append(overlay.average)
        self._spectrum.set_tautomer_traces(traces, element)
        for trace in traces:
            self._add_row(trace)
        if overlay.average is None:
            self._add_unavailable_average(overlay.average_note)
        self._note.setText(overlay.average_note)
        shown = left_out_lines(overlay.not_averaged)
        if len(shown) > _LEFT_OUT_LISTED:
            shown = shown[:_LEFT_OUT_LISTED] + [f"... and {len(shown) - _LEFT_OUT_LISTED} more reasons"]
        self._left_out.setText("Left out of the average:\n" + "\n".join(shown) if shown else "")
        self._left_out.setVisible(bool(shown))
        self.setVisible(True)

    def clear(self) -> None:
        self._clear_rows()
        self._spectrum.clear_tautomer_traces()
        self._note.setText("")
        self._left_out.setText("")
        self.setVisible(False)

    def checkbox_for(self, key: str) -> QCheckBox | None:
        return self._checks.get(key)

    def note_text(self) -> str:
        return self._note.text()

    def left_out_text(self) -> str:
        return self._left_out.text()

    def _clear_rows(self) -> None:
        for row in self._rows:
            self._rows_layout.removeWidget(row)
            row.setParent(None)
            row.deleteLater()
        self._rows = []
        self._checks = {}

    def _add_row(self, trace: TautomerTrace) -> None:
        row = QWidget(self)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        swatch = QLabel(row)
        swatch.setFixedSize(14, 14)
        swatch.setStyleSheet(f"background: {self._spectrum.tautomer_trace_colour(trace)}; border: 1px solid #888;")
        check = QCheckBox(_trace_text(trace), row)
        has_peaks = any(trace.peaks.get(e) for e in ("H", "C"))
        check.setChecked(has_peaks)
        check.setEnabled(has_peaks)
        if not has_peaks:
            self._spectrum.set_tautomer_trace_visible(trace.key, False)
        # Bound by key through a property, not a lambda capturing `self` (tests/test_qt_object_disposal.py).
        check.setProperty("trace_key", trace.key)
        check.toggled.connect(self._on_toggled)
        layout.addWidget(swatch)
        layout.addWidget(check, 1)
        self._rows_layout.addWidget(row)
        self._rows.append(row)
        self._checks[trace.key] = check

    def _add_unavailable_average(self, reason: str) -> None:
        """The average's row when there is none: listed, disabled, with the reason, never silently absent."""
        row = QWidget(self)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        check = QCheckBox("Fast-exchange average (not available)", row)
        check.setEnabled(False)
        check.setToolTip(reason)
        layout.addWidget(check, 1)
        self._rows_layout.addWidget(row)
        self._rows.append(row)

    def _on_toggled(self, checked: bool) -> None:
        sender = self.sender()
        key = sender.property("trace_key") if sender is not None else None
        if key:
            self._spectrum.set_tautomer_trace_visible(str(key), bool(checked))
