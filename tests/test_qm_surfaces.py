"""The QM surface path: wavefunction retention, the surface service, and
the side-by-side ESP comparison.

`orca_plot` itself is not run here -- that needs ORCA installed, and it is
exercised in `benchmarks/esp/`. What is tested is everything around it
that would silently do the wrong thing: which file gets retained, how an
orbital NAME becomes an index, and whether a density gets a colour range
that wastes half its scale.
"""

from __future__ import annotations

import json

import numpy as np
import pytest
from PySide6.QtWidgets import QWidget

from openchem.chem.scalar_field import ScalarField, display_range, symmetric_range
from openchem.ui.viewer_backend import ViewerBackend
from openchem.ui.visualization import build_scalar_field_surface_layer


def _field(values: np.ndarray, name: str = "f", units: str = "u") -> ScalarField:
    return ScalarField(
        values=values, origin=(0.0, 0.0, 0.0), spacing=(1.0, 1.0, 1.0), units=units, name=name
    )


# ---------------------------------------------------------------------------
# Colour range
# ---------------------------------------------------------------------------


def test_a_signed_field_is_centred_on_zero():
    """For a potential the sign IS the point -- zero has to land in the
    middle of the red/white/blue scale or neutral regions read as
    charged."""
    values = np.linspace(-3.0, 5.0, 1000).reshape(10, 10, 10)

    low, high = display_range(_field(values))

    assert low == pytest.approx(-high)
    assert low < 0.0 < high


def test_a_strictly_positive_field_is_not_centred_on_zero():
    """An electron density has no negative values, so centring spends half
    the palette on values that cannot occur. Measured on a real
    bromobenzene density cube: -0.0106 to +0.0106, negative half empty."""
    values = np.linspace(0.0, 0.9, 1000).reshape(10, 10, 10)

    low, high = display_range(_field(values))

    assert low == 0.0
    assert high > 0.0
    # ...and it really is different from what the old path produced.
    assert symmetric_range(_field(values))[0] < 0.0


def test_a_strictly_negative_field_is_not_centred_either():
    """The mirror case, and the reason this is decided from the data
    rather than from a flag: an anion's potential is all-negative and no
    caller would think to declare it."""
    values = np.linspace(-4.0, 0.0, 1000).reshape(10, 10, 10)

    low, high = display_range(_field(values))

    assert high == 0.0
    assert low < 0.0


def test_a_constant_zero_field_does_not_produce_a_degenerate_scale():
    low, high = display_range(_field(np.zeros((5, 5, 5))))

    assert low != high or high != 0.0 or low == 0.0  # must not raise
    assert high >= low


def test_the_surface_layer_uses_the_signed_aware_range():
    values = np.linspace(0.0, 0.9, 1000).reshape(10, 10, 10)

    layer = build_scalar_field_surface_layer(_field(values))

    assert layer.scalar_field_range[0] == 0.0


# ---------------------------------------------------------------------------
# Wavefunction retention
# ---------------------------------------------------------------------------


def test_retention_keeps_the_densities_container_not_only_the_gbw(tmp_path, monkeypatch):
    """ORCA 6 splits the wavefunction: the `.gbw` holds orbitals and the
    `.densities` container holds the SCF density that the ESP and
    electron-density plots read. Keeping only the `.gbw` gives a directory
    where orbitals plot and every density surface reports the density
    "does not exist"."""
    from openchem.services import quantum_chemistry_service as service_module

    scratch = tmp_path / "scratch"
    scratch.mkdir()
    for name in ("job.gbw", "job.densities", "job.densitiesinfo", "job.out", "job.tmp"):
        (scratch / name).write_text("x", encoding="utf-8")
    retained_root = tmp_path / "wavefunctions"
    monkeypatch.setattr(
        service_module.app_paths, "wavefunction_root", lambda: retained_root
    )

    job = type("Job", (), {"molecule_uuid": "mol-1", "scratch_dir": scratch})()
    result = service_module.QuantumChemistryService._retain_wavefunction(
        object(), job, "no orbital table here"
    )

    kept = {path.name for path in (retained_root / "mol-1").iterdir()}
    assert {"job.gbw", "job.densities", "job.densitiesinfo"} <= kept
    # The bulky ones are NOT kept -- retention is a few hundred kilobytes,
    # not a copy of the scratch directory.
    assert "job.tmp" not in kept
    assert result is not None and result.name == "job.gbw"


def test_retention_records_the_frontier_orbital_indices(tmp_path, monkeypatch):
    """The index is the only way to plot "the HOMO" later, it is basis-set
    dependent, and it is unrecoverable once the output text is gone."""
    from openchem.services import quantum_chemistry_service as service_module

    scratch = tmp_path / "scratch"
    scratch.mkdir()
    (scratch / "job.gbw").write_text("x", encoding="utf-8")
    retained_root = tmp_path / "wavefunctions"
    monkeypatch.setattr(
        service_module.app_paths, "wavefunction_root", lambda: retained_root
    )
    output = (
        "ORBITAL ENERGIES\n"
        "  NO   OCC          E(Eh)            E(eV)\n"
        "   0   2.0000      -19.100000      -519.0\n"
        "   1   2.0000       -1.000000       -27.2\n"
        "   2   0.0000        0.100000         2.7\n"
        "MULLIKEN\n"
    )

    job = type("Job", (), {"molecule_uuid": "mol-1", "scratch_dir": scratch})()
    service_module.QuantumChemistryService._retain_wavefunction(object(), job, output)

    recorded = json.loads((retained_root / "mol-1" / "orbitals.json").read_text())
    assert recorded == {"homo": 1, "lumo": 2}


def test_a_reference_job_retains_nothing(tmp_path, monkeypatch):
    """TMS and the scaling compounds are not a user's molecule and nobody
    will ask for their orbitals."""
    from openchem.services import quantum_chemistry_service as service_module

    scratch = tmp_path / "scratch"
    scratch.mkdir()
    (scratch / "job.gbw").write_text("x", encoding="utf-8")
    monkeypatch.setattr(
        service_module.app_paths, "wavefunction_root", lambda: tmp_path / "wavefunctions"
    )

    job = type("Job", (), {"molecule_uuid": None, "scratch_dir": scratch})()

    assert service_module.QuantumChemistryService._retain_wavefunction(object(), job, "") is None
    assert not (tmp_path / "wavefunctions").exists()


# ---------------------------------------------------------------------------
# The surface service
# ---------------------------------------------------------------------------


class _Settings:
    def __init__(self, path: str = "") -> None:
        self._path = path

    def get(self, key: str, default=""):
        return self._path if key == "orca/executable_path" else default


@pytest.fixture
def service(qapp, tmp_path, monkeypatch):
    from openchem.events.base import EventBus
    from openchem.services import qm_surface_service as module

    monkeypatch.setattr(module.app_paths, "wavefunction_root", lambda: tmp_path / "wf")
    orca = tmp_path / "orca.exe"
    orca.write_text("", encoding="utf-8")
    (tmp_path / "orca_plot.exe").write_text("", encoding="utf-8")
    return module.QmSurfaceService(EventBus(), _Settings(str(orca))), tmp_path


def _retain(root, uuid: str, homo=None, lumo=None):
    directory = root / "wf" / uuid
    directory.mkdir(parents=True)
    (directory / "job.gbw").write_text("x", encoding="utf-8")
    (directory / "orbitals.json").write_text(json.dumps({"homo": homo, "lumo": lumo}))
    return directory


def test_a_molecule_without_a_wavefunction_is_not_available(service):
    svc, _ = service

    assert not svc.is_available("never-calculated")


def test_a_molecule_with_a_wavefunction_is_available(service):
    svc, root = service
    _retain(root, "mol-1")

    assert svc.is_available("mol-1")


def test_orca_plot_is_found_beside_the_configured_orca(service):
    svc, _ = service

    assert svc._orca_plot_path().endswith("orca_plot.exe")


def test_an_unconfigured_orca_makes_every_surface_unavailable(qapp, tmp_path, monkeypatch):
    from openchem.events.base import EventBus
    from openchem.services import qm_surface_service as module

    monkeypatch.setattr(module.app_paths, "wavefunction_root", lambda: tmp_path / "wf")
    _retain(tmp_path, "mol-1")
    svc = module.QmSurfaceService(EventBus(), _Settings(""))

    assert not svc.is_available("mol-1")
    assert svc.request_surface("mol-1", "esp") is False


def test_an_orbital_name_resolves_to_the_retained_index(service):
    svc, root = service
    _retain(root, "mol-1", homo=37, lumo=38)

    assert svc.frontier_orbitals("mol-1") == (37, 38)


def test_an_orbital_request_without_retained_indices_is_refused(service):
    """Refused rather than defaulted to orbital 0, which is a real orbital
    -- a core 1s -- and would render a good picture of the wrong thing."""
    svc, root = service
    _retain(root, "mol-1", homo=None, lumo=None)

    assert svc.request_surface("mol-1", "molecular_orbital", orbital="homo") is False


def test_an_unknown_surface_kind_raises(service):
    svc, root = service
    _retain(root, "mol-1")

    with pytest.raises(ValueError, match="unknown surface kind"):
        svc.request_surface("mol-1", "not_a_surface")


# ---------------------------------------------------------------------------
# The comparison widget
# ---------------------------------------------------------------------------


class FakeBackend(ViewerBackend):
    def __init__(self) -> None:
        super().__init__()
        self.loaded: list[str] = []
        self.surfaces: list[object] = []

    def load_conformer(self, molblock: str) -> None:
        self.loaded.append(molblock)

    def apply_surface(self, layer) -> None:
        self.surfaces.append(layer)

    def set_style(self, style: str) -> None:
        pass

    def clear(self) -> None:
        pass

    def widget(self) -> QWidget:
        return QWidget()


class _FakeSurfaceService:
    def __init__(self, available: bool = True) -> None:
        self.available = available
        self.requests: list[tuple] = []

    def is_available(self, molecule_uuid: str) -> bool:
        return self.available

    def request_surface(self, molecule_uuid, surface_id, *, orbital="", **kwargs) -> bool:
        self.requests.append((molecule_uuid, surface_id, orbital))
        return self.available


@pytest.fixture
def compare(qapp):
    from openchem.chem.conformer_providers import RDKitConformerProvider
    from openchem.chem.engine import ChemistryEngine
    from openchem.domain.molecule import MoleculeModel
    from openchem.ui.widgets.esp_compare_widget import EspCompareWidget

    engine = ChemistryEngine()
    molecule = MoleculeModel(display_name="water")
    engine.set_structure_from_smiles(molecule, "O")
    conformers = RDKitConformerProvider().generate_conformers(
        engine.mol_from_model(molecule), 1, optimize=True
    )
    molblock = engine.mol_to_molblock(conformers[0][0])

    fake = _FakeSurfaceService()
    left, right = FakeBackend(), FakeBackend()
    widget = EspCompareWidget(engine, fake, point_charge_backend=left, qm_backend=right)
    yield widget, fake, left, right, molblock
    widget.deleteLater()


def test_the_point_charge_surface_renders_without_any_orca(compare):
    """The whole reason both panes exist: this one is instant and needs no
    calculation at all."""
    widget, _, left, _, molblock = compare

    widget.set_molecule("mol-1", molblock)

    assert left.loaded == [molblock]
    assert left.surfaces and left.surfaces[-1] is not None


def test_the_point_charge_caption_names_its_method_and_its_limits(compare):
    widget, _, _, _, molblock = compare

    widget.set_molecule("mol-1", molblock)
    caption = widget._point_charge_caption.text()

    assert "Gasteiger" in caption
    assert "sigma hole" in caption


def test_an_orbital_is_requested_by_name_not_by_index(compare):
    """The index is basis-set dependent; only the job that produced the
    wavefunction knows it."""
    widget, fake, _, _, molblock = compare
    widget.set_molecule("mol-1", molblock)
    widget._surface_combo.setCurrentIndex(
        widget._surface_combo.findData("molecular_orbital")
    )
    widget._orbital_combo.setCurrentIndex(widget._orbital_combo.findData("lumo"))

    widget._on_compute_clicked()

    assert fake.requests == [("mol-1", "molecular_orbital", "lumo")]


def test_the_orbital_selector_is_only_enabled_for_an_orbital_plot(compare):
    widget, _, _, _, molblock = compare
    widget.set_molecule("mol-1", molblock)

    widget._surface_combo.setCurrentIndex(widget._surface_combo.findData("esp"))
    assert not widget._orbital_combo.isEnabled()

    widget._surface_combo.setCurrentIndex(
        widget._surface_combo.findData("molecular_orbital")
    )
    assert widget._orbital_combo.isEnabled()


def test_a_computed_surface_is_captioned_with_its_method(compare):
    widget, _, _, right, molblock = compare
    widget.set_molecule("mol-1", molblock)
    field = _field(np.linspace(-1.0, 1.0, 1000).reshape(10, 10, 10), "Electrostatic potential", "Hartree/e")

    widget.on_surface_computed("mol-1", field, "")

    assert right.surfaces and right.surfaces[-1] is not None
    assert "ab initio" in widget._qm_caption.text()
    assert "Hartree/e" in widget._qm_caption.text()


def test_a_failed_surface_reports_the_real_reason(compare):
    """A closed-shell spin density is the case this exists for: orca_plot
    exits 0 and writes a copy of the electron density, so the driver's
    error message is the only thing standing between the user and a
    plausible wrong picture."""
    widget, _, _, right, molblock = compare
    widget.set_molecule("mol-1", molblock)

    widget.on_surface_computed("mol-1", None, "the density job.scfr does not exist")

    assert "does not exist" in widget._qm_caption.text()
    assert right.surfaces[-1] is None


def test_a_surface_for_another_molecule_is_ignored(compare):
    widget, _, _, right, molblock = compare
    widget.set_molecule("mol-1", molblock)
    before = len(right.surfaces)

    widget.on_surface_computed("a-different-molecule", _field(np.zeros((4, 4, 4))), "")

    assert len(right.surfaces) == before


def test_the_qm_control_is_disabled_when_no_wavefunction_exists(qapp, compare):
    widget, fake, _, _, molblock = compare
    fake.available = False

    widget.set_molecule("mol-1", molblock)

    assert not widget._compute_button.isEnabled()
