from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from openchem.chem.descriptor_providers import compute_gasteiger_charges
from openchem.chem.engine import ChemistryEngine
from openchem.chem.scalar_field import electrostatic_potential_for_conformer
from openchem.ui.viewer_backend import ViewerBackend
from openchem.ui.visualization import build_scalar_field_surface_layer
from openchem.ui.widgets.mol3d_viewer_backend import Mol3DViewerBackend

#: What can be asked of `orca_plot`, in the order a chemist reaches for
#: them. Spin density is offered but will fail on a closed-shell molecule
#: -- deliberately, and with the real reason, rather than being hidden:
#: "your molecule has no unpaired electrons" is information.
_QM_SURFACES = (
    ("esp", "Electrostatic potential"),
    ("electron_density", "Electron density"),
    ("molecular_orbital", "Molecular orbital"),
    ("spin_density", "Spin density"),
)

_POINT_CHARGE_CAPTION = (
    "Point charges (Gasteiger) — instant, no ORCA. Cannot represent "
    "lone-pair directionality or a sigma hole."
)
_QM_CAPTION_IDLE = "Ab initio (ORCA) — run a calculation on this molecule first."


class EspCompareWidget(QWidget):
    """The point-charge ESP and the ab initio one, side by side.

    BESIDE, NOT INSTEAD OF, and that is the whole design. The
    point-charge surface is instant, needs no ORCA, and is a genuinely
    useful picture of gross polarity; the QM surface is minutes of
    computation away and shows structure the other cannot. Replacing one
    with the other would trade a limitation the user can reason about for
    a cost they cannot avoid. Each pane is captioned with its method,
    which is how every other number in this app is presented.

    The captions are not decoration. `benchmarks/esp/` measured what the
    left pane misses: on bromobenzene the ab initio potential changes
    SIGN around the bromine (+10.4 kcal/(mol*e) along the C-Br axis,
    -11.1 around the belt) while the point-charge model reports it as
    uniformly negative, because one charge on one atom cannot change sign
    with angle. Water's lone pairs are the same story in the other
    direction: the QM potential deepens out of the molecular plane and the
    point-charge one flattens.
    """

    def __init__(
        self,
        engine: ChemistryEngine,
        qm_surface_service,
        point_charge_backend: ViewerBackend | None = None,
        qm_backend: ViewerBackend | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._engine = engine
        self._service = qm_surface_service
        self._molecule_uuid = ""
        self._conformer_molblock = ""

        self._point_charge_backend = point_charge_backend or Mol3DViewerBackend(self)
        self._qm_backend = qm_backend or Mol3DViewerBackend(self)

        self._point_charge_caption = QLabel(_POINT_CHARGE_CAPTION, self)
        self._point_charge_caption.setWordWrap(True)
        self._qm_caption = QLabel(_QM_CAPTION_IDLE, self)
        self._qm_caption.setWordWrap(True)

        self._surface_combo = QComboBox(self)
        for surface_id, label in _QM_SURFACES:
            self._surface_combo.addItem(label, surface_id)

        self._orbital_combo = QComboBox(self)
        # HOMO and LUMO are named rather than numbered because the index
        # is basis-set dependent and meaningless to type in: for water in
        # def2-SVP the HOMO is orbital 4, for benzene it is 20. The panel
        # resolves the name against the job's own orbital occupations.
        self._orbital_combo.addItem("HOMO", "homo")
        self._orbital_combo.addItem("LUMO", "lumo")
        self._orbital_combo.setEnabled(False)
        self._surface_combo.currentIndexChanged.connect(self._on_surface_changed)

        self._compute_button = QPushButton("Compute QM surface", self)
        self._compute_button.setEnabled(False)
        self._compute_button.clicked.connect(self._on_compute_clicked)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("QM surface:", self))
        controls.addWidget(self._surface_combo)
        controls.addWidget(self._orbital_combo)
        controls.addWidget(self._compute_button)
        controls.addStretch()

        left = QVBoxLayout()
        left.addWidget(QLabel("<b>Point charge</b>", self))
        left.addWidget(self._point_charge_backend.widget())
        left.addWidget(self._point_charge_caption)

        right = QVBoxLayout()
        right.addWidget(QLabel("<b>Ab initio</b>", self))
        right.addWidget(self._qm_backend.widget())
        right.addWidget(self._qm_caption)

        panes = QHBoxLayout()
        panes.addLayout(left)
        panes.addLayout(right)

        layout = QVBoxLayout(self)
        layout.addLayout(controls)
        layout.addLayout(panes)

    # -- population ------------------------------------------------------

    def set_molecule(self, molecule_uuid: str, conformer_molblock: str) -> None:
        self._molecule_uuid = molecule_uuid
        self._conformer_molblock = conformer_molblock
        self._render_point_charge()
        if conformer_molblock:
            self._qm_backend.load_conformer(conformer_molblock)
        # The molblock is passed so a wavefunction retained for a
        # DIFFERENT structure counts as absent -- the button must not
        # offer to plot benzene's orbitals against toluene.
        available = bool(conformer_molblock) and self._service.is_available(
            molecule_uuid, conformer_molblock
        )
        self._compute_button.setEnabled(available)
        if not available:
            self._qm_caption.setText(_QM_CAPTION_IDLE)

    def _render_point_charge(self) -> None:
        if not self._conformer_molblock:
            return
        mol = self._engine.mol_from_molblock(self._conformer_molblock)
        # Recomputed on the CONFORMER, never reused from a per-atom dataset
        # on screen. `CalculatorInspectorDialog` documents why at length:
        # a heavy-atom-only charge map gives neutral acetic acid a net
        # -0.40 e and paints the whole surface red.
        charges = compute_gasteiger_charges(mol)
        field = electrostatic_potential_for_conformer(mol, charges)
        self._point_charge_backend.load_conformer(self._conformer_molblock)
        layer = build_scalar_field_surface_layer(field)
        self._point_charge_backend.apply_surface(layer)
        low, high = layer.scalar_field_range
        self._point_charge_caption.setText(
            f"{low:.1f} to {high:.1f} {field.units} — {_POINT_CHARGE_CAPTION}"
        )

    # -- QM --------------------------------------------------------------

    def _on_surface_changed(self, _index: int) -> None:
        self._orbital_combo.setEnabled(
            self._surface_combo.currentData() == "molecular_orbital"
        )

    def selected_surface_id(self) -> str:
        return self._surface_combo.currentData()

    def selected_orbital(self) -> str:
        return self._orbital_combo.currentData()

    def _on_compute_clicked(self) -> None:
        surface_id = self.selected_surface_id()
        self._qm_caption.setText(f"Computing {surface_id} …")
        self._compute_button.setEnabled(False)
        # The orbital is named, not numbered. Its INDEX is basis-set
        # dependent (water's HOMO is 4, bromobenzene's is 37) and the
        # service resolves the name against the indices retained from the
        # job that produced the wavefunction -- the only place they are
        # knowable.
        started = self._service.request_surface(
            self._molecule_uuid, surface_id, orbital=self.selected_orbital()
        )
        if not started:
            self._qm_caption.setText(
                "No wavefunction retained for this molecule, or ORCA is not "
                "configured — run a calculation on it first."
            )
            self._compute_button.setEnabled(True)

    def on_surface_computed(self, molecule_uuid: str, field, error: str) -> None:
        """Called by the host when a `QmSurfaceComputed` event arrives."""
        if molecule_uuid != self._molecule_uuid:
            return
        self._compute_button.setEnabled(True)
        if field is None:
            self._qm_caption.setText(f"Could not compute the surface: {error}")
            self._qm_backend.apply_surface(None)
            return
        layer = build_scalar_field_surface_layer(field)
        self._qm_backend.apply_surface(layer)
        low, high = layer.scalar_field_range
        self._qm_caption.setText(
            f"{low:.3g} to {high:.3g} {field.units} — {field.name}, ab initio (ORCA). "
            "Shows lone-pair directionality and sigma holes; see benchmarks/esp/."
        )
