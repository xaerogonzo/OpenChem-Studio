"""MainWindow charged family compare orchestrates chem helpers; UI does not parse vectors."""

from __future__ import annotations

from pathlib import Path

import pytest

from openchem.app.main_window import MainWindow
from openchem.app.session import SessionManager
from openchem.app.settings import Settings
from openchem.bootstrap import build_service_container
from openchem.domain.common import Provenance
from openchem.domain.descriptor import DescriptorValue
from openchem.domain.quantum_chemistry_run import QuantumChemistryRun, RunStatus


_WINDOWS: list = []
_MOLBLOCK = Path("tests/fixtures/ketcher/propane_sru.mol").read_text(encoding="utf-8")


def _track(window):
    _WINDOWS.append(window)
    return window


@pytest.fixture(autouse=True)
def _close_windows():
    yield
    while _WINDOWS:
        _WINDOWS.pop().close()


def _build_window(tmp_path):
    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(tmp_path / "no_plugins_here"))
    settings.set("plugins/user_directory", str(tmp_path / "no_user_plugins_here"))
    session = SessionManager()
    return _track(MainWindow(services, settings, session))


def _descriptor(descriptor_id: str, value: float, units: str, name: str) -> DescriptorValue:
    provider = descriptor_id.split(".", 1)[0]
    return DescriptorValue(
        descriptor_id=descriptor_id,
        name=name,
        units=units,
        category="quantum_chemistry",
        provider=provider,
        molecule_uuid="m1",
        value=value,
        provenance=Provenance(created_by="core", method=provider, parameters={}),
    )


def _charged_run(run_id: str, dipole: float) -> QuantumChemistryRun:
    return QuantumChemistryRun(
        run_id=run_id,
        molecule_uuid="m1",
        calc_type="sp",
        method_basis="B3LYP def2-SVP",
        charge=1,
        multiplicity=1,
        calculation_input="geometry",
        input_fingerprint="fp",
        input_molblock=_MOLBLOCK,
        provider="orca",
        status=RunStatus.COMPLETED,
        completed_at=1.0,
        results={
            "descriptors": [
                _descriptor("orca.scf_energy", -76.4, "Hartree", "SCF Energy"),
                _descriptor("orca.dipole_moment", dipole, "Debye", "Dipole"),
            ]
        },
        output_status={},
    )


def test_family_compare_calls_geometry_once_per_run_and_shows_normalized_values(
    qapp, tmp_path, monkeypatch
):
    window = _build_window(tmp_path)
    left = _charged_run("run-left", 9.0)
    right = _charged_run("run-right", 9.0)
    geo_ids: list[str] = []
    debye_ids: list[str] = []

    def fake_geo(run, molecule):
        geo_ids.append(run.run_id)
        return f"block-{run.run_id}"

    def fake_debye(run, molblock):
        debye_ids.append((run.run_id, molblock))
        return {"run-left": 2.25, "run-right": 3.5}[run.run_id]

    monkeypatch.setattr("openchem.chem.qc_dipole.run_geometry_molblock", fake_geo)
    monkeypatch.setattr("openchem.chem.qc_dipole.com_referenced_dipole_debye", fake_debye)
    captured = []
    monkeypatch.setattr(
        window,
        "_show_named_history_compare",
        lambda rows, left_run, right_run, empty_message=None: captured.append(rows),
    )
    window._show_quantum_history_compare(left, right)
    assert geo_ids == ["run-left", "run-right"]
    assert debye_ids == [("run-left", "block-run-left"), ("run-right", "block-run-right")]
    dipole = next(row for row in captured[0] if row.label == "Dipole (COM)")
    assert dipole.left == "2.25"
    assert dipole.right == "3.5"
    assert dipole.delta == pytest.approx(1.25)
