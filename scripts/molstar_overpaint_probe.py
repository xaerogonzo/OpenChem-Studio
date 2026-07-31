"""Interactive probe: does Mol* residue overpainting actually work?

Run it, look at the window, answer one question. Nothing here touches the
app's own code paths destructively -- it drives the REAL
`MolStarViewerBackend` with a small synthetic 3-residue peptide, then tries
several candidate mol-script selection syntaxes one at a time.

    uv run python scripts/molstar_overpaint_probe.py

Why this exists: `OverpaintStructureRepresentation3DFromScript` commits
without error even when its selection matches NOTHING -- verified during
Phase 24, where a select-everything expression still reported zero layers
on readback. So "it didn't throw" proves nothing, and reading the state
back proved unreliable too. The only trustworthy signal left is your eyes:
a residue either turns red on screen or it doesn't.
"""

from __future__ import annotations

import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from openchem.ui.widgets.molstar_viewer_backend import MolStarViewerBackend

# Three well-separated residues so a colour change on ONE of them is
# unmistakable. TYR652 is the target throughout -- it is also the residue
# real hERG/binding-site analysis cares about, which makes the numbering
# familiar rather than arbitrary.
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

# Candidate selection syntaxes. The differences that matter: auth_* (author
# numbering, what a PDB file literally says) vs label_* (mmCIF canonical
# numbering), and whether string literals need quoting in mol-script.
_CANDIDATES: list[tuple[str, str]] = [
    ("auth_quoted", '(sel.atom.res (and (= atom.auth_comp_id "TYR") (= atom.auth_seq_id 652)))'),
    ("auth_bare", "(sel.atom.res (and (= atom.auth_comp_id TYR) (= atom.auth_seq_id 652)))"),
    ("label_quoted", '(sel.atom.res (and (= atom.label_comp_id "TYR") (= atom.label_seq_id 652)))'),
    ("auth_seq_only", "(sel.atom.res (= atom.auth_seq_id 652))"),
    ("resname_only_quoted", '(sel.atom.res (= atom.auth_comp_id "TYR"))'),
    ("EVERYTHING (control)", "(sel.atom.atoms)"),
]

_JS_TEMPLATE = """
(function () {
  try {
    var plugin = window.__probeViewer.plugin;
    var ST = molstar.lib.plugin.StateTransforms;
    var hier = plugin.managers.structure.hierarchy.current;
    if (!hier.structures.length) return 'NO STRUCTURE LOADED';
    var repr = hier.structures[0].components[0].representations[0];
    plugin.build().to(repr.cell.transform.ref).apply(
      ST.Representation.OverpaintStructureRepresentation3DFromScript,
      { layers: [{ script: { language: 'mol-script', expression: %s },
                   color: 0xff0000, clear: false }] }
    ).commit();
    return 'committed';
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
    var b = plugin.build();
    refs.forEach(function (r) { b.delete(r); });
    b.commit();
    return 'cleared ' + refs.length;
  } catch (e) { return 'ERROR ' + String(e); }
})();
"""


class Probe(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Mol* overpaint probe — does TYR652 turn red?")
        self.resize(1100, 760)
        self._index = 0

        self._backend = MolStarViewerBackend(self)
        self._status = QLabel("Loading structure…", self)
        self._status.setWordWrap(True)
        self._status.setStyleSheet("font-size: 14px; padding: 6px;")

        self._next = QPushButton("Try next syntax →", self)
        self._next.clicked.connect(self._apply_next)
        self._next.setEnabled(False)
        self._clear = QPushButton("Clear colouring", self)
        self._clear.clicked.connect(lambda: self._run(_CLEAR_JS, "cleared"))

        row = QHBoxLayout()
        row.addWidget(self._next)
        row.addWidget(self._clear)
        row.addStretch()

        layout = QVBoxLayout(self)
        layout.addWidget(self._status)
        layout.addLayout(row)
        layout.addWidget(self._backend.widget())

        self._backend.load_macromolecule(_PDB, "pdb")
        # Mol*'s viewer is created asynchronously; give the structure a
        # moment to render before exposing the viewer handle the JS needs.
        QTimer.singleShot(4000, self._ready)

    def _ready(self) -> None:
        self._backend._page.runJavaScript("window.__probeViewer = viewer; 'ok';")
        self._next.setEnabled(True)
        self._status.setText(
            "Structure loaded: TYR652, PHE656, GLY660 (three separated blobs).\n"
            "Click 'Try next syntax' and watch whether the LEFTMOST residue (TYR652) turns RED."
        )

    def _apply_next(self) -> None:
        if self._index >= len(_CANDIDATES):
            self._status.setText("All syntaxes tried. Tell Claude which ones (if any) coloured anything.")
            self._next.setEnabled(False)
            return
        name, expression = _CANDIDATES[self._index]
        self._index += 1
        self._run(_CLEAR_JS, None)
        js = _JS_TEMPLATE % _js_string(expression)
        self._run(js, None)
        remaining = len(_CANDIDATES) - self._index
        self._status.setText(
            f"[{self._index}/{len(_CANDIDATES)}]  {name}\n"
            f"{expression}\n\n"
            f"Does TYR652 (leftmost) look RED right now?   ({remaining} left)"
        )

    def _run(self, js: str, done_message: str | None) -> None:
        def _back(result):
            if done_message:
                self._status.setText(f"{done_message}: {result}")

        self._backend._page.runJavaScript(js, _back)


def _js_string(value: str) -> str:
    import json

    return json.dumps(value)


def main() -> int:
    app = QApplication(sys.argv)
    probe = Probe()
    probe.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
