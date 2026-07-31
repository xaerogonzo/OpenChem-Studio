"""Interactive probe: which mol-script syntax actually colours a residue?

    uv run python scripts/molstar_overpaint_probe.py

One syntax at a time. For each, the probe clears any previous colouring,
waits for Mol* to settle, then asks you a yes/no question with two buttons.
It records your answers and prints a summary at the end -- you don't have
to remember or transcribe anything.

Why this exists: `OverpaintStructureRepresentation3DFromScript` commits
without error even when its selection matches NOTHING, and reading the
resulting state back proved unreliable too (a select-everything expression
reported zero layers while visibly working). Eyes are the only trustworthy
oracle here, so the probe's whole job is making the question unambiguous.
"""

from __future__ import annotations

import json
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from openchem.ui.widgets.molstar_viewer_backend import MolStarViewerBackend

# Three well-separated residues so a colour change on ONE is unmistakable.
_PDB = "\n".join(
    [
        "ATOM      1  N   TYR A 652      11.104  13.207   2.845  1.00 20.00           N",
        "ATOM      2  CA  TYR A 652      11.999  12.040   2.945  1.00 20.00           C",
        "ATOM      3  C   TYR A 652      13.398  12.442   2.508  1.00 20.00           C",
        "ATOM      4  O   TYR A 652      13.598  13.601   2.128  1.00 20.00           O",
        "ATOM      5  CB  TYR A 652      11.482  10.895   2.076  1.00 20.00           C",
        "ATOM      6  N   PHE A 656      18.104  13.207   2.845  1.00 20.00           N",
        "ATOM      7  CA  PHE A 656      18.999  12.040   2.945  1.00 20.00           C",
        "ATOM      8  C   PHE A 656      20.398  12.442   2.508  1.00 20.00           C",
        "ATOM      9  O   PHE A 656      20.598  13.601   2.128  1.00 20.00           O",
        "ATOM     10  CB  PHE A 656      18.482  10.895   2.076  1.00 20.00           C",
        "ATOM     11  N   GLY A 660      25.104  13.207   2.845  1.00 20.00           N",
        "ATOM     12  CA  GLY A 660      25.999  12.040   2.945  1.00 20.00           C",
        "ATOM     13  C   GLY A 660      27.398  12.442   2.508  1.00 20.00           C",
        "ATOM     14  O   GLY A 660      27.598  13.601   2.128  1.00 20.00           O",
        "END",
    ]
)

# Each entry: (label, expression, what you should see if it matches).
# The two controls at the ends are what make the run interpretable: if
# EVERYTHING fails to colour, the problem is not the selection syntax, and
# if NOTHING-selector colours something, the probe itself is broken.
_CANDIDATES: list[tuple[str, str, str]] = [
    ("CONTROL: select everything", "(sel.atom.atoms)", "ALL THREE residues red"),
    ("auth_bare", "(sel.atom.res (and (= atom.auth_comp_id TYR) (= atom.auth_seq_id 652)))", "leftmost only"),
    ("auth_quoted", '(sel.atom.res (and (= atom.auth_comp_id "TYR") (= atom.auth_seq_id 652)))', "leftmost only"),
    ("label_bare", "(sel.atom.res (and (= atom.label_comp_id TYR) (= atom.label_seq_id 652)))", "leftmost only"),
    ("auth_seq_only", "(sel.atom.res (= atom.auth_seq_id 652))", "leftmost only"),
    ("resname_only_bare", "(sel.atom.res (= atom.auth_comp_id TYR))", "leftmost only"),
    ("CONTROL: matches nothing", "(sel.atom.res (= atom.auth_seq_id 99999))", "NOTHING red"),
]

_APPLY_JS = """
(function () {
  try {
    var plugin = window.__probeViewer.plugin;
    var ST = molstar.lib.plugin.StateTransforms;
    var hier = plugin.managers.structure.hierarchy.current;
    if (!hier.structures.length) return 'NO STRUCTURE';
    var repr = hier.structures[0].components[0].representations[0];
    plugin.build().to(repr.cell.transform.ref).apply(
      ST.Representation.OverpaintStructureRepresentation3DFromScript,
      { layers: [{ script: { language: 'mol-script', expression: %s },
                   color: 0xff0000, clear: false }] }
    ).commit();
    return 'ok';
  } catch (e) { return 'ERROR ' + String(e); }
})();
"""

_CLEAR_JS = """
(function () {
  try {
    var plugin = window.__probeViewer.plugin;
    var refs = [];
    plugin.state.data.cells.forEach(function (c, ref) {
      if (c.transform.transformer.id && /overpaint/i.test(c.transform.transformer.id)) refs.push(ref);
    });
    if (!refs.length) return 'nothing to clear';
    var b = plugin.build();
    refs.forEach(function (r) { b.delete(r); });
    b.commit();
    return 'cleared ' + refs.length;
  } catch (e) { return 'ERROR ' + String(e); }
})();
"""

# Mol* commits asynchronously and repaints on its own schedule. Waiting
# between clear -> apply -> "now look" is what removes the ambiguity that
# made the first version of this probe unreadable.
_SETTLE_MS = 1200


class Probe(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Mol* overpaint probe")
        self.resize(1150, 820)
        self._index = -1
        self._answers: list[tuple[str, str]] = []

        self._backend = MolStarViewerBackend(self)

        self._heading = QLabel("Loading structure…", self)
        self._heading.setStyleSheet("font-size: 17px; font-weight: bold; padding: 4px;")
        self._heading.setWordWrap(True)
        self._detail = QLabel("", self)
        self._detail.setStyleSheet("font-size: 13px; padding: 2px 4px;")
        self._detail.setWordWrap(True)

        self._yes = QPushButton("YES — I see red", self)
        self._no = QPushButton("NO — nothing changed", self)
        self._yes.clicked.connect(lambda: self._answer("MATCHED"))
        self._no.clicked.connect(lambda: self._answer("no match"))
        self._set_buttons(False)

        self._summary = QTextEdit(self)
        self._summary.setReadOnly(True)
        self._summary.setMaximumHeight(150)
        self._summary.setPlaceholderText("Results appear here as you answer — paste this back to Claude when done.")

        buttons = QHBoxLayout()
        buttons.addWidget(self._yes)
        buttons.addWidget(self._no)
        buttons.addStretch()

        layout = QVBoxLayout(self)
        layout.addWidget(self._heading)
        layout.addWidget(self._detail)
        layout.addLayout(buttons)
        layout.addWidget(self._backend.widget(), stretch=1)
        layout.addWidget(self._summary)

        self._backend.load_macromolecule(_PDB, "pdb")
        QTimer.singleShot(4500, self._begin)

    def _set_buttons(self, enabled: bool) -> None:
        self._yes.setEnabled(enabled)
        self._no.setEnabled(enabled)

    def _begin(self) -> None:
        self._backend._page.runJavaScript("window.__probeViewer = viewer; 'ok';")
        self._advance()

    def _advance(self) -> None:
        self._index += 1
        if self._index >= len(_CANDIDATES):
            self._finish()
            return
        label, expression, expectation = _CANDIDATES[self._index]
        self._set_buttons(False)
        self._heading.setText(f"[{self._index + 1}/{len(_CANDIDATES)}]  {label} — applying…")
        self._detail.setText(expression)

        # clear -> settle -> apply -> settle -> ask. Chained on timers
        # rather than fired back-to-back, so nothing is being asked about
        # a frame that hasn't rendered yet.
        self._backend._page.runJavaScript(_CLEAR_JS)
        QTimer.singleShot(_SETTLE_MS, lambda: self._apply(label, expression, expectation))

    def _apply(self, label: str, expression: str, expectation: str) -> None:
        self._backend._page.runJavaScript(_APPLY_JS % json.dumps(expression))
        QTimer.singleShot(_SETTLE_MS, lambda: self._ask(label, expectation))

    def _ask(self, label: str, expectation: str) -> None:
        self._heading.setText(f"[{self._index + 1}/{len(_CANDIDATES)}]  {label}   →   LOOK NOW")
        self._detail.setText(
            f"{_CANDIDATES[self._index][1]}\n\nIf this syntax works you should see: {expectation}"
        )
        self._set_buttons(True)

    def _answer(self, verdict: str) -> None:
        label = _CANDIDATES[self._index][0]
        self._answers.append((label, verdict))
        self._summary.setPlainText(
            "\n".join(f"{name:28s} {result}" for name, result in self._answers)
        )
        self._advance()

    def _finish(self) -> None:
        self._set_buttons(False)
        self._heading.setText("Done — paste the results below back to Claude.")
        self._detail.setText("")
        lines = [f"{name:28s} {result}" for name, result in self._answers]
        self._summary.setPlainText("\n".join(lines))


def main() -> int:
    app = QApplication(sys.argv)
    probe = Probe()
    probe.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
