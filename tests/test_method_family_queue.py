"""Sequential Run-all-methods queue: request_id, frozen snapshot, selection isolation."""

from __future__ import annotations

from PySide6.QtWidgets import QDialog

import openchem.ui.panels.property_panel as property_panel_module
from openchem.chem.descriptor_providers import CALCULATOR_DEFINITIONS
from openchem.chem.engine import ChemistryEngine
from openchem.chem.geometry_charges import GEOMETRY_CHARGE_METHODS
from openchem.chem.typed_eem import RESONANCE_AVERAGED
from openchem.domain.calculator import CalculationRequest, CalculatorDefinition, RegistryExecution
from openchem.domain.molecule import MoleculeModel
from openchem.domain.project import ProjectModel
from openchem.events.base import EventBus
from openchem.events.events import CalculationFinished, MoleculeSelected
from openchem.services.calculator_registry import CalculatorRegistry
from openchem.ui.panels.property_panel import PropertyPanel


def _geometry_charge() -> CalculatorDefinition:
    return next(d for d in CALCULATOR_DEFINITIONS if d.calculator_id == "geometry_partial_charge")


class _RecordingService:
    def __init__(self) -> None:
        self.calls: list[tuple[MoleculeModel, CalculationRequest, object]] = []

    def run_calculator(self, model, request, *, snapshot=None) -> None:
        self.calls.append((model, request, snapshot))


class _FamilyDialog:
    run_family = True

    def __init__(self, definition, parent=None, **kwargs):
        self.definition = definition

    def exec(self):
        return QDialog.DialogCode.Accepted

    def parameters(self):
        return {
            "method": "qeq_rg1991_lambda_half_h_experimental",
            "resonance": RESONANCE_AVERAGED,
            "ph_dependent": False,
            "pH": 4.0,
            "include_hydrogens": True,
            "decimal_places": 3,
        }


class _OkDialog(_FamilyDialog):
    run_family = False


def _panel(qapp, monkeypatch, *, dialog=_FamilyDialog):
    monkeypatch.setattr(property_panel_module, "CalculatorSettingsDialog", dialog)
    bus = EventBus()
    registry = CalculatorRegistry()
    registry.register(_geometry_charge())
    registry.register(
        CalculatorDefinition(
            calculator_id="plain",
            display_name="Plain",
            category="identity",
            description="",
            execution=RegistryExecution(compute=lambda mol, uuid, params: None),
        )
    )
    service = _RecordingService()
    panel = PropertyPanel(bus, registry, service, ChemistryEngine())
    first = MoleculeModel(display_name="A", molblock="block-a")
    second = MoleculeModel(display_name="B", molblock="block-b")
    panel.set_project(ProjectModel(molecules=[first, second]))
    bus.publish(MoleculeSelected(molecule_uuid=first.uuid))
    return panel, bus, service, first, second


def _start_family(panel):
    panel._open_calculator(_geometry_charge())


def test_family_queue_dispatches_six_ordered_methods_with_shared_params(qapp, monkeypatch):
    panel, bus, service, molecule, _other = _panel(qapp, monkeypatch)
    _start_family(panel)
    assert len(service.calls) == 1
    assert "Running 1 of 6" in panel._batch_status.text()
    assert "EEM, Bultinck 2002" in panel._batch_status.text()

    methods = []
    remaining = None
    while service.calls:
        model, request, snapshot = service.calls.pop(0)
        methods.append(request.parameters["method"])
        remaining = {k: v for k, v in request.parameters.items() if k != "method"}
        assert remaining["include_hydrogens"] is True
        assert remaining["ph_dependent"] is False
        assert "pH" not in remaining
        assert snapshot is panel._family_queue.snapshot
        assert model is snapshot.model
        bus.publish(
            CalculationFinished(
                calculator_id=request.calculator_id,
                molecule_uuid=molecule.uuid,
                request_id=request.request_id,
            )
        )
    assert methods == list(GEOMETRY_CHARGE_METHODS)
    assert panel._family_queue is None
    assert panel._batch_status.text() == "Finished."


def test_refusal_advances_the_family_queue(qapp, monkeypatch):
    panel, bus, service, molecule, _other = _panel(qapp, monkeypatch)
    _start_family(panel)
    first = service.calls[0][1]
    bus.publish(
        CalculationFinished(
            calculator_id=first.calculator_id,
            molecule_uuid=molecule.uuid,
            request_id=first.request_id,
        )
    )
    assert len(service.calls) == 2
    assert service.calls[1][1].parameters["method"] == GEOMETRY_CHARGE_METHODS[1]
    assert "Running 2 of 6" in panel._batch_status.text()


def test_foreign_finished_event_does_not_advance_the_queue(qapp, monkeypatch):
    panel, bus, service, molecule, _other = _panel(qapp, monkeypatch)
    _start_family(panel)
    first = service.calls[0][1]
    bus.publish(
        CalculationFinished(
            calculator_id=first.calculator_id,
            molecule_uuid=molecule.uuid,
            request_id="",
        )
    )
    bus.publish(
        CalculationFinished(
            calculator_id=first.calculator_id,
            molecule_uuid=molecule.uuid,
            request_id="someone-else",
        )
    )
    assert len(service.calls) == 1
    assert panel._family_queue is not None
    assert panel._family_queue.index == 0


def test_second_family_start_is_refused(qapp, monkeypatch):
    panel, bus, service, _molecule, _other = _panel(qapp, monkeypatch)
    _start_family(panel)
    _start_family(panel)
    assert len(service.calls) == 1
    assert "Already running every method" in panel._batch_status.text()


def test_single_ok_does_not_interleave_with_an_active_family_queue(qapp, monkeypatch):
    panel, bus, service, _molecule, _other = _panel(qapp, monkeypatch, dialog=_FamilyDialog)
    _start_family(panel)
    monkeypatch.setattr(property_panel_module, "CalculatorSettingsDialog", _OkDialog)
    panel._open_calculator(_geometry_charge())
    assert len(service.calls) == 1
    assert "already running every method" in panel._batch_status.text().lower()


def test_selection_change_does_not_redirect_or_unlock_the_queue(qapp, monkeypatch):
    panel, bus, service, first, second = _panel(qapp, monkeypatch)
    _start_family(panel)
    captured = panel._family_queue.snapshot
    bus.publish(MoleculeSelected(molecule_uuid=second.uuid))
    assert panel._family_queue is not None
    assert "Running" not in panel._batch_status.text()
    request = service.calls[0][1]
    bus.publish(
        CalculationFinished(
            calculator_id=request.calculator_id,
            molecule_uuid=first.uuid,
            request_id=request.request_id,
        )
    )
    assert len(service.calls) == 2
    assert service.calls[1][2] is captured
    assert service.calls[1][1].molecule_uuid == first.uuid


def test_later_requests_keep_the_confirm_time_snapshot_after_an_edit(qapp, monkeypatch):
    panel, bus, service, molecule, _other = _panel(qapp, monkeypatch)
    _start_family(panel)
    captured = panel._family_queue.snapshot
    original = captured.model.molblock
    molecule.molblock = "edited-later"
    request = service.calls[0][1]
    bus.publish(
        CalculationFinished(
            calculator_id=request.calculator_id,
            molecule_uuid=molecule.uuid,
            request_id=request.request_id,
        )
    )
    later_model, _, later_snapshot = service.calls[1]
    assert later_snapshot is captured
    assert later_model.molblock == original
    assert later_model.molblock != molecule.molblock


def test_closing_settings_does_not_cancel_the_queue(qapp, monkeypatch):
    panel, bus, service, _molecule, _other = _panel(qapp, monkeypatch)
    _start_family(panel)
    assert panel._family_queue is not None
    assert len(service.calls) == 1


def test_ordinary_ok_still_dispatches_one_request(qapp, monkeypatch):
    panel, bus, service, _molecule, _other = _panel(qapp, monkeypatch, dialog=_OkDialog)
    panel._open_calculator(_geometry_charge())
    assert len(service.calls) == 1
    assert service.calls[0][1].parameters["method"] == "qeq_rg1991_lambda_half_h_experimental"
    assert panel._family_queue is None


def test_run_selected_does_not_expand_the_family(qapp, monkeypatch):
    panel, bus, service, molecule, _other = _panel(qapp, monkeypatch, dialog=_OkDialog)
    panel._calculator_ticks["geometry_partial_charge"].setChecked(True)
    panel._calculator_ticks["plain"].setChecked(True)
    panel._on_run_selected()
    assert [request.calculator_id for _model, request, _snap in service.calls] == [
        "geometry_partial_charge",
        "plain",
    ]
    charge = service.calls[0][1]
    assert charge.parameters["method"] == GEOMETRY_CHARGE_METHODS[0]
    assert charge.request_id == ""
