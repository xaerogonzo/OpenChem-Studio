"""Results survive a molecule switch, a save and a reopen -- and never lie.

Reported: every selection in `MPMI.ocsproj` recomputed the always-on set,
coming back to a molecule did it again, and a saved project held no results
at all. The governing rule these tests hold the fix to:

    SAVING MAY DEGRADE GRACEFULLY. A REPLAY MUST NEVER TREAT A PARTIAL OR
    UNSUPPORTED RESULT SET AS A COMPLETE CACHE HIT.

So the most important test here is not the round trip; it is
`test_a_lost_entry_is_partial_and_the_calculators_run_again`.
"""

from __future__ import annotations

import json
import math
from dataclasses import fields, is_dataclass, replace

import pytest
from PySide6.QtCore import QThreadPool

from openchem.chem.calculation_input import input_fingerprint, resolve_calculation_input
from openchem.chem.descriptor_providers import RDKitDescriptorProvider
from openchem.chem.engine import ChemistryEngine
from openchem.domain import result_codec
from openchem.domain.calculator import DRAWING, GEOMETRY, RegistryExecution
from openchem.domain.common import CacheState
from openchem.domain.conformer import ConformerModel
from openchem.domain.molecule import MoleculeModel
from openchem.domain.project import ProjectModel
from openchem.domain.result_status import FAILED, READY, status_of
from openchem.domain.result_store import (
    BundlePart,
    BundleState,
    ResultIdentity,
    SessionResultStore,
    StoredResult,
    result_id_of,
)
from openchem.domain.scientific_result import PerAtomDataset
from openchem.events.base import EventBus
from openchem.services.project_service import RESULTS_KEY, ProjectService
from openchem.services.result_store_service import event_for


def _drain(qapp, iterations: int = 50) -> None:
    QThreadPool.globalInstance().waitForDone(20000)
    for _ in range(iterations):
        qapp.processEvents()


def _difference(original, restored, path="result") -> str | None:
    """Where two values differ, comparing TYPE at every node, or None.

    **NOT `==`, AND THAT IS THE LESSON OF THE FIRST VERSION.** `Basis` and
    `FactCategory` are str-enums, so `Basis.DETERMINISTIC == "deterministic"`
    is True: a codec that wrote every enum as a bare string passed an `==`
    sweep over 283 results and then crashed the reader on `fact.basis.value`.
    NaN is handled here too, since NaN != NaN.
    """
    if type(original) is not type(restored):
        return f"{path}: {type(original).__name__} came back as {type(restored).__name__}"
    if isinstance(original, float):
        same = (math.isnan(original) and math.isnan(restored)) or original == restored
        return None if same else f"{path}: {original!r} != {restored!r}"
    if is_dataclass(original) and not isinstance(original, type):
        for f in fields(original):
            found = _difference(getattr(original, f.name), getattr(restored, f.name), f"{path}.{f.name}")
            if found:
                return found
        return None
    if isinstance(original, dict):
        if list(original) != list(restored):
            return f"{path}: keys {list(original)[:5]} != {list(restored)[:5]}"
        for key in original:
            found = _difference(original[key], restored[key], f"{path}[{key!r}]")
            if found:
                return found
        return None
    if isinstance(original, (list, tuple)):
        if len(original) != len(restored):
            return f"{path}: length {len(original)} != {len(restored)}"
        for index, (a, b) in enumerate(zip(original, restored)):
            found = _difference(a, b, f"{path}[{index}]")
            if found:
                return found
        return None
    return None if original == restored else f"{path}: {original!r} != {restored!r}"


# --- the codec, swept rather than spot-checked ----------------------------------


@pytest.fixture(scope="module")
def every_result():
    """Every result the application produces, on three kinds of molecule.

    Drug-like, a salt (which the always-on provider partly refuses), and a
    tryptamine from the reported project -- each WITH a conformer, or every
    geometry calculator comes back FAILED and its real result type is never
    exercised.
    """
    from rdkit import Chem, RDLogger
    from rdkit.Chem import AllChem

    from openchem.bootstrap import build_service_container

    RDLogger.DisableLog("rdApp.*")
    registry = build_service_container().calculator_registry
    produced = []
    for smiles in ("CC(=O)Oc1ccccc1C(=O)O", "[Na+].[O-]C(=O)c1ccccc1", "CN1CCC[C@H]1Cc1c[nH]c2cccc(O)c12"):
        mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
        AllChem.EmbedMolecule(mol, randomSeed=0xF00D)
        try:
            AllChem.MMFFOptimizeMolecule(mol)
        except Exception:  # noqa: BLE001 - the salt has no MMFF types; geometry is still usable
            pass
        provider = RDKitDescriptorProvider()
        for produce in (provider.compute, provider.compute_alerts, provider.compute_per_atom):
            try:
                produced.extend(produce(mol, "m"))
            except Exception:  # noqa: BLE001 - a refusal is not the subject here
                pass
        for category in registry.categories():
            for definition in registry.by_category(category):
                if not isinstance(definition.execution, RegistryExecution):
                    continue
                try:
                    produced.append(registry.compute(
                        definition.calculator_id, mol, "m",
                        {p.name: p.default for p in definition.parameters},
                    ))
                except Exception:  # noqa: BLE001
                    continue
    return produced


def test_every_result_survives_the_codec_and_json(every_result):
    assert len(every_result) > 200, "the sweep lost most of the registry"
    lossy = []
    for result in every_result:
        back = result_codec.decode(json.loads(json.dumps(result_codec.encode(result))))
        found = _difference(result, back)
        if found:
            lossy.append(found)
    assert lossy == []


def test_every_result_kind_the_panel_files_has_an_id_and_an_event(every_result):
    for result in every_result:
        assert result_id_of(result)
        assert event_for(result) is not None


def test_an_unknown_type_is_named_as_such():
    with pytest.raises(result_codec.CodecError) as caught:
        result_codec.decode({"__type__": "os.system", "__version__": 1})
    assert caught.value.problem == result_codec.UNKNOWN_TYPE

    class NotAllowed:
        pass

    with pytest.raises(result_codec.CodecError) as caught:
        result_codec.encode(NotAllowed())
    assert caught.value.problem == result_codec.UNKNOWN_TYPE


def test_a_newer_version_is_refused_not_guessed():
    dataset = PerAtomDataset(property_id="p", name="p", units="", method="", molecule_uuid="m", values={0: 1.0})
    encoded = result_codec.encode(dataset)
    encoded["__version__"] = 99
    with pytest.raises(result_codec.CodecError) as caught:
        result_codec.decode(encoded)
    assert caught.value.problem == result_codec.UNSUPPORTED_VERSION


def test_a_damaged_entry_is_malformed():
    dataset = PerAtomDataset(property_id="p", name="p", units="", method="", molecule_uuid="m", values={})
    encoded = result_codec.encode(dataset)
    del encoded["property_id"]
    with pytest.raises(result_codec.CodecError) as caught:
        result_codec.decode(encoded)
    assert caught.value.problem == result_codec.MALFORMED


def test_int_keys_and_tuples_keep_their_types():
    dataset = PerAtomDataset(property_id="p", name="p", units="", method="", molecule_uuid="m", values={3: 0.5})
    back = result_codec.decode(json.loads(json.dumps(result_codec.encode(dataset))))
    assert list(back.values) == [3]
    assert back == dataset


# --- the fingerprint follows the input the calculator is handed ------------------


def _molecule(engine, smiles="CCO") -> MoleculeModel:
    model = MoleculeModel(display_name=smiles)
    engine.set_structure_from_smiles(model, smiles)
    return model


def _conformer(engine, model, seed) -> ConformerModel:
    from rdkit import Chem
    from rdkit.Chem import AllChem

    mol = Chem.AddHs(engine.mol_from_model(model))
    AllChem.EmbedMolecule(mol, randomSeed=seed)
    return ConformerModel(molblock=Chem.MolToMolBlock(mol), energy=float(seed))


def test_the_fingerprint_comes_from_the_same_resolution_as_the_molecule(qapp):
    engine = ChemistryEngine()
    model = _molecule(engine)
    assert input_fingerprint(engine, model, DRAWING) == resolve_calculation_input(engine, model, DRAWING).fingerprint
    # No conformer: geometry falls back to the drawing, and so does its key.
    assert input_fingerprint(engine, model, GEOMETRY) == input_fingerprint(engine, model, DRAWING)
    model.conformers = [_conformer(engine, model, 1)]
    assert input_fingerprint(engine, model, GEOMETRY) == resolve_calculation_input(engine, model, GEOMETRY).fingerprint
    assert input_fingerprint(engine, model, GEOMETRY) != input_fingerprint(engine, model, DRAWING)


def test_a_result_for_conformer_a_is_not_replayed_for_conformer_b(qapp):
    engine = ChemistryEngine()
    model = _molecule(engine)
    model.conformers = [_conformer(engine, model, 1)]
    fingerprint_a = input_fingerprint(engine, model, GEOMETRY)
    store = SessionResultStore("p")
    store.put(_stored(model.uuid, "steric", GEOMETRY, fingerprint_a))

    model.conformers = [_conformer(engine, model, 2)]
    current = {GEOMETRY: input_fingerprint(engine, model, GEOMETRY)}
    assert current[GEOMETRY] != fingerprint_a
    assert store.fresh_results(model.uuid, current) == []


# --- the store: completeness is a manifest, not a head count ---------------------


def _dataset(result_id, molecule_uuid="m", failed=False) -> PerAtomDataset:
    return PerAtomDataset(
        property_id=result_id, name=result_id, units="", method="", molecule_uuid=molecule_uuid,
        values={0: 1.0}, cache_state=CacheState.FAILED if failed else CacheState.COMPLETED,
    )


def _stored(molecule_uuid, result_id, calculation_input, fingerprint, failed=False) -> StoredResult:
    return StoredResult(
        identity=ResultIdentity(molecule_uuid, result_id, calculation_input, fingerprint, "producer"),
        result=_dataset(result_id, molecule_uuid, failed),
    )


def _complete_store(ids=("a", "b", "c")) -> SessionResultStore:
    store = SessionResultStore("project")
    for rid in ids:
        store.put(_stored("m", rid, DRAWING, "fp"))
    store.record_part("m", BundlePart("provider", "fp", tuple(ids)))
    return store


def test_a_complete_manifest_is_complete():
    assert _complete_store().bundle_state("m", "fp", {"provider"}) == (BundleState.COMPLETE, set())


def test_a_lost_entry_is_partial_and_the_calculators_run_again():
    """THE TEST THE DESIGN IS FOR. One entry made undecodable in the file."""
    data = json.loads(json.dumps(_complete_store().to_dict()))
    data["molecules"]["m"]["results"][1]["result"]["__type__"] = "report.SomethingFromTheFuture"

    loaded = SessionResultStore.from_dict(data, "project")

    state, missing = loaded.bundle_state("m", "fp", {"provider"})
    assert state is BundleState.PARTIAL
    assert missing == {"provider"}
    assert loaded.load_problems[result_codec.UNKNOWN_TYPE] == 1
    # What DID decode is still offered for display while the rerun happens.
    assert len(loaded.fresh_results("m", {DRAWING: "fp"})) == 2


def test_an_always_on_set_from_another_build_is_recomputed():
    """The user guide's promise: a later version gets its own perception."""
    store = SessionResultStore("project")
    stored = _stored("m", "a", DRAWING, "fp")
    stored.application_version = "0.9.0"
    store.put(stored)
    store.record_part("m", BundlePart("provider", "fp", ("a",)))

    assert store.bundle_state("m", "fp", {"provider"}, "0.9.0")[0] is BundleState.COMPLETE
    assert store.bundle_state("m", "fp", {"provider"}, "0.10.0")[0] is BundleState.PARTIAL
    # ...while the result itself is still there to show until the rerun lands.
    assert store.fresh_results("m", {DRAWING: "fp"})


def test_a_new_producer_makes_an_old_manifest_incomplete():
    state, missing = _complete_store().bundle_state("m", "fp", {"provider", "plugin"})
    assert state is BundleState.PARTIAL and missing == {"plugin"}


def test_an_edited_structure_is_stale():
    state, _ = _complete_store().bundle_state("m", "different", {"provider"})
    assert state is BundleState.STALE


def test_a_failure_is_done_for_the_session_but_never_saved():
    store = SessionResultStore("project")
    store.put(_stored("m", "a", DRAWING, "fp", failed=True))
    store.record_part("m", BundlePart("provider", "fp", ("a",), failed=True))
    assert store.bundle_state("m", "fp", {"provider"})[0] is BundleState.COMPLETE

    loaded = SessionResultStore.from_dict(json.loads(json.dumps(store.to_dict())), "project")
    assert loaded.bundle_state("m", "fp", {"provider"})[0] is BundleState.NONE


def test_a_producers_own_refusal_is_saved_so_reopening_is_complete():
    """"Needs a 3D conformer" is the provider's answer, not a fault to retry.

    Without this every reopened molecule with no conformer reran the whole
    always-on set: its manifest lists the shape descriptors, which fail.
    """
    store = SessionResultStore("project")
    store.put(_stored("m", "a", DRAWING, "fp"))
    store.put(_stored("m", "shape", DRAWING, "fp", failed=True))
    store.record_part("m", BundlePart("provider", "fp", ("a", "shape")))

    loaded = SessionResultStore.from_dict(json.loads(json.dumps(store.to_dict())), "project")
    assert loaded.bundle_state("m", "fp", {"provider"})[0] is BundleState.COMPLETE


def test_a_manual_failure_is_not_saved():
    store = SessionResultStore("project")
    store.put(_stored("m", "pka", DRAWING, "fp", failed=True))
    written = store.to_dict()
    assert written["molecules"] == {}


def test_an_edit_keeps_the_previous_revision_for_an_undo():
    store = _complete_store()
    store.put(_stored("m", "a", DRAWING, "edited"))
    store.record_part("m", BundlePart("provider", "edited", ("a",)))
    assert store.bundle_state("m", "fp", {"provider"})[0] is BundleState.COMPLETE
    assert store.bundle_state("m", "edited", {"provider"})[0] is BundleState.COMPLETE


def test_revisions_are_bounded():
    from openchem.domain.result_store import MAX_REVISIONS

    store = SessionResultStore("project")
    for index in range(MAX_REVISIONS + 3):
        store.put(_stored("m", "a", DRAWING, f"fp{index}"))
    assert store.fresh_results("m", {DRAWING: "fp0"}) == []
    assert len(store.fresh_results("m", {DRAWING: f"fp{MAX_REVISIONS + 2}"})) == 1


def test_a_replayed_failure_still_reads_as_failed():
    failed = _dataset("a", failed=True)
    assert status_of(event_for(failed).dataset) == FAILED
    assert status_of(event_for(_dataset("b")).dataset) == READY


def test_a_replayed_per_atom_dataset_carries_its_stored_input_identity():
    """The store is the only record of which structure a restored dataset's
    indices describe; a replay that dropped it would hand the Atom Inspector
    a dataset it must treat as unverifiable."""
    stored = _stored("m", "a", DRAWING, "fp-of-the-drawing")
    event = event_for(stored.result, identity=stored.identity)
    assert event.input_fingerprint == "fp-of-the-drawing"
    assert event.calculation_input == DRAWING


def test_a_restored_report_is_restamped_to_the_current_version():
    from openchem.domain.report import ReportResult

    report = ReportResult(molecule_uuid="m", report_id="r", name="r", structure_version=41)
    assert event_for(report, structure_version=3).report.structure_version == 3


def test_saved_results_for_another_project_are_ignored_whole():
    data = _complete_store().to_dict()
    loaded = SessionResultStore.from_dict(data, "someone-else")
    assert loaded.molecule_uuids() == []
    assert loaded.load_problems["foreign_project"] == 1


def test_superseded_revisions_are_not_written():
    store = _complete_store()
    store.put(_stored("m", "old", DRAWING, "previous-structure"))
    written = store.to_dict({"m": {DRAWING: "fp"}})
    assert {r["result_id"] for r in written["molecules"]["m"]["results"]} == {"a", "b", "c"}


# --- the project file ------------------------------------------------------------


def test_the_project_file_round_trips_its_results(qapp, tmp_path):
    service = ProjectService(EventBus())
    project = ProjectModel(name="p")
    project.molecules.append(MoleculeModel(uuid="m"))
    store = _complete_store()
    store.project_uuid = project.uuid

    path = tmp_path / "p.ocsproj"
    service.save(project, path, store)
    loaded_project, loaded = service.load_document(path)

    assert loaded_project.uuid == project.uuid
    assert loaded.bundle_state("m", "fp", {"provider"})[0] is BundleState.COMPLETE
    assert all(s.restored for s in loaded.fresh_results("m", {DRAWING: "fp"}))


def test_a_project_saved_before_results_were_kept_still_opens(qapp, tmp_path):
    service = ProjectService(EventBus())
    project = ProjectModel(name="old")
    path = tmp_path / "old.ocsproj"
    service.save(project, path)
    assert RESULTS_KEY not in json.loads(path.read_text(encoding="utf-8"))

    loaded_project, loaded = service.load_document(path)
    assert loaded_project.uuid == project.uuid
    assert loaded.molecule_uuids() == []


# --- the real window: A -> B -> A computes each molecule once ---------------------


@pytest.fixture
def window(qapp, tmp_path):
    from openchem.app.main_window import MainWindow
    from openchem.app.session import SessionManager
    from openchem.app.settings import Settings
    from openchem.bootstrap import build_service_container

    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(tmp_path / "none"))
    settings.set("plugins/user_directory", str(tmp_path / "none"))
    built = MainWindow(services, settings, SessionManager())
    yield built
    built.close()


def _counting(window):
    """Count dispatches at the SERVICE, which is where "did it recompute" lives."""
    calls = {"descriptors": [], "calculators": []}
    service = window._services.descriptor_service
    real_request, real_run = service.request_descriptors, service.run_calculator

    def request(model, *args, **kwargs):
        calls["descriptors"].append((model.uuid, kwargs.get("only_providers")))
        return real_request(model, *args, **kwargs)

    def run(model, request_):
        calls["calculators"].append((model.uuid, request_.calculator_id))
        return real_run(model, request_)

    service.request_descriptors = request
    service.run_calculator = run
    return calls


def _two_molecule_project(window) -> tuple[MoleculeModel, MoleculeModel]:
    engine = window._services.chemistry_engine
    project = ProjectModel(name="two")
    a, b = _molecule(engine, "CCO"), _molecule(engine, "c1ccccc1O")
    project.molecules.extend([a, b])
    window._set_project(project)
    return a, b


def _select(window, qapp, molecule) -> None:
    from openchem.events.events import MoleculeSelected

    window._services.event_bus.publish(MoleculeSelected(molecule_uuid=molecule.uuid))
    _drain(qapp)


def test_returning_to_a_molecule_replays_instead_of_recomputing(window, qapp):
    a, b = _two_molecule_project(window)
    calls = _counting(window)

    _select(window, qapp, a)
    _select(window, qapp, b)
    shown_first = set(window._property_panel._reports)
    _select(window, qapp, a)
    _select(window, qapp, b)

    assert [uuid for uuid, _ in calls["descriptors"]] == [a.uuid, b.uuid]
    assert [uuid for uuid, _ in calls["calculators"]] == [a.uuid, b.uuid]
    # And the panel shows the same results for B on the second visit.
    assert set(window._property_panel._reports) == shown_first
    assert "substance_analysis" in shown_first


def test_an_edit_recomputes_and_an_undo_back_does_not(window, qapp):
    from openchem.events.events import MoleculeChanged

    a, _b = _two_molecule_project(window)
    _select(window, qapp, a)
    calls = _counting(window)
    engine = window._services.chemistry_engine
    original = a.molblock

    engine.set_structure_from_smiles(a, "CCN")
    window._services.event_bus.publish(MoleculeChanged(molecule_uuid=a.uuid))
    _drain(qapp)
    assert len(calls["descriptors"]) == 1

    a.molblock = original
    window._services.event_bus.publish(MoleculeChanged(molecule_uuid=a.uuid))
    _drain(qapp)
    assert len(calls["descriptors"]) == 1, "the undo back recomputed a structure whose results are held"


def test_saving_and_reopening_shows_results_before_anything_runs(window, qapp, tmp_path):
    a, _b = _two_molecule_project(window)
    _select(window, qapp, a)
    project = window._session.project
    results, fingerprints = window._current_results()
    path = tmp_path / "saved.ocsproj"
    window._services.project_service.save(project, path, results, fingerprints)

    loaded_project, loaded_results = window._services.project_service.load_document(path)
    window._set_project(loaded_project, loaded_results)
    calls = _counting(window)
    _select(window, qapp, loaded_project.find_molecule(a.uuid))

    assert calls["descriptors"] == [] and calls["calculators"] == []
    assert "substance_analysis" in window._property_panel._reports
    assert window._property_panel._descriptor_values


def test_a_new_result_marks_the_session_dirty(window, qapp):
    a, _b = _two_molecule_project(window)
    assert not window._session.is_dirty
    _select(window, qapp, a)
    assert window._session.is_dirty


def _recovering(window, tmp_path):
    from openchem.services.recovery_service import RecoveryService

    service = RecoveryService(window._services.project_service, tmp_path / "recovery")
    window.enable_recovery(service, delay_ms=0)
    return service


def _fire_recovery_timer(window, qapp) -> None:
    for _ in range(20):
        qapp.processEvents()


def test_a_window_without_recovery_enabled_writes_nothing(window, qapp, tmp_path):
    a, _b = _two_molecule_project(window)
    _select(window, qapp, a)
    assert not hasattr(window, "_recovery_service")


def test_unsaved_results_reach_a_recovery_copy_and_save_removes_it(window, qapp, tmp_path):
    service = _recovering(window, tmp_path)
    a, _b = _two_molecule_project(window)
    _select(window, qapp, a)
    _fire_recovery_timer(window, qapp)

    [candidate] = service.candidates()
    _project, results = service.load(candidate)
    assert a.uuid in results.molecule_uuids()

    window.save_project_to(tmp_path / "saved.ocsproj")
    assert service.candidates() == []


def test_a_recovery_write_queued_before_save_does_not_bring_the_file_back(window, qapp, tmp_path):
    service = _recovering(window, tmp_path)
    window._recovery_timer.setInterval(60_000)  # queued, not yet fired
    a, _b = _two_molecule_project(window)
    _select(window, qapp, a)
    assert window._recovery_timer.isActive()

    window.save_project_to(tmp_path / "saved.ocsproj")
    window._session.mark_dirty()  # even dirty again, the OLD write must not land
    window._write_recovery()

    assert service.candidates() == []


def test_accepting_the_offer_restores_the_project_and_its_results(window, qapp, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    service = _recovering(window, tmp_path)
    a, _b = _two_molecule_project(window)
    _select(window, qapp, a)
    _fire_recovery_timer(window, qapp)
    lost_uuid = window._session.project.uuid

    window._set_project(ProjectModel(name="something else"))
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    calls = _counting(window)

    assert window.offer_recovery()
    assert window._session.project.uuid == lost_uuid
    assert window._session.is_dirty
    _select(window, qapp, window._session.project.find_molecule(a.uuid))
    assert calls["descriptors"] == []


def test_declining_the_offer_discards_the_copy(window, qapp, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    service = _recovering(window, tmp_path)
    a, _b = _two_molecule_project(window)
    _select(window, qapp, a)
    _fire_recovery_timer(window, qapp)
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.No))

    assert not window.offer_recovery()
    assert service.candidates() == []


def test_a_result_arriving_for_a_previous_project_is_not_kept(window, qapp):
    from openchem.events.events import ResultRecorded

    a, _b = _two_molecule_project(window)
    stranger = _stored("not-in-this-project", "x", DRAWING, "fp")
    window._services.event_bus.publish(ResultRecorded(stored=stranger))
    assert "not-in-this-project" not in window._services.result_store_service.store.molecule_uuids()


# ---------------------------------------------------------------------------
# The `functional_groups` -> `fragment_counts` rename
#
# Two producers shared one id: the RDKit fragment counter's AlertResult and
# the naming-engine annotation's PerAtomDataset. The store keys a result by
# (result id, calculation input, fingerprint), so for one molecule and one
# drawing they were THE SAME SLOT and whichever ran last replaced the other.
# ---------------------------------------------------------------------------


def _legacy_alert_entry(result_id: str = "functional_groups") -> dict:
    """A saved entry as the old build wrote it: an AlertResult under the id
    the per-atom calculator also used."""
    from openchem.domain.scientific_result import AlertResult

    alert = AlertResult(
        alert_id=result_id,
        name="Functional Groups",
        molecule_uuid="m",
        matched=["Amide (1)", "Tertiary Amine (2)", "Benzene Ring (2)"],
        category="substructure",
    )
    return {
        "result_id": result_id,
        "calculation_input": DRAWING,
        "input_fingerprint": "fp",
        "producer": "core",
        "parameters_key": "",
        "result": result_codec.encode(alert),
    }


def _saved_block(entries: list[dict]) -> dict:
    return {
        "envelope_version": 1,
        "project_uuid": "project",
        "molecules": {"m": {"bundle": {"bundle_id": "automatic", "parts": []}, "results": entries}},
    }


def test_a_legacy_fragment_count_result_is_migrated_not_dropped():
    store = SessionResultStore.from_dict(_saved_block([_legacy_alert_entry()]), "project")

    ids = {s.identity.result_id for s in store.fresh_results("m", {DRAWING: "fp"})}
    assert ids == {"fragment_counts"}, "the alert did not move to its new id"
    assert store.load_problems["migrated"] == 1
    # The PAYLOAD moved too: an entry whose own id disagrees with its slot is
    # dropped as unaddressable, so a half-migration would lose the result.
    (restored,) = store.fresh_results("m", {DRAWING: "fp"})
    assert result_id_of(restored.result) == "fragment_counts"
    assert restored.result.matched[0] == "Amide (1)"


def test_after_the_rename_both_producers_coexist():
    """The defect was that they could not. Both under one molecule and one
    fingerprint, distinct, neither overwriting the other -- through a real
    save and reload."""
    from openchem.domain.scientific_result import AlertResult

    store = SessionResultStore("project")
    alert = AlertResult(
        alert_id="fragment_counts", name="Fragment Counts", molecule_uuid="m",
        matched=["Amide (1)"], category="substructure",
    )
    dataset = PerAtomDataset(
        property_id="functional_groups", name="Functional Groups", units="",
        method="iupac-namer-perception", molecule_uuid="m", values={0: 1.0},
    )
    for result in (alert, dataset):
        store.put(StoredResult(
            identity=ResultIdentity("m", result_id_of(result), DRAWING, "fp", "core"),
            result=result,
        ))

    reloaded = SessionResultStore.from_dict(store.to_dict(), "project")

    by_id = {s.identity.result_id: s.result for s in reloaded.fresh_results("m", {DRAWING: "fp"})}
    assert set(by_id) == {"fragment_counts", "functional_groups"}
    assert by_id["fragment_counts"].matched == ["Amide (1)"]
    assert by_id["functional_groups"].values == {0: 1.0}


# ---------------------------------------------------------------------------
# Fragment Counts changed METHOD (vocabulary v2, 2026-09-18)
#
# Plan B2: v1 and v2 never share a slot, a v1 record stays readable and is
# labelled as the legacy method, v2 saves and reloads with its method, and
# nothing replays both under one id.
# ---------------------------------------------------------------------------


def _fragment_counts(matched, name="Fragment Counts"):
    from openchem.domain.scientific_result import AlertResult

    return AlertResult(alert_id="fragment_counts", name=name, molecule_uuid="m",
                       matched=matched, category="substructure")


def test_a_v1_fragment_count_loads_as_the_legacy_method_and_says_so():
    from openchem.domain.result_store import LEGACY_METHOD_VERSIONS

    entry = _legacy_alert_entry("fragment_counts")
    store = SessionResultStore.from_dict(_saved_block([entry]), "project")

    (restored,) = store.fresh_results("m", {DRAWING: "fp"})
    legacy, label = LEGACY_METHOD_VERSIONS["fragment_counts"]
    assert restored.identity.method_version == legacy == "legacy-rdkit-fr-v1"
    assert restored.result.name == label and "legacy" in label
    assert restored.result.matched[0] == "Amide (1)", "the v1 content must survive as it was"
    assert store.load_problems["legacy_method"] == 1


def test_a_v2_fragment_count_saves_and_reloads_with_its_method():
    from openchem.domain.result_store import FRAGMENT_COUNTS_METHOD
    from openchem.services.result_identity import make_identity

    alert = _fragment_counts(["amide (1)"])
    identity = make_identity(molecule_uuid="m", result=alert, calculation_input=DRAWING,
                             input_fingerprint="fp", producer="core")
    assert identity.method_version == FRAGMENT_COUNTS_METHOD
    store = SessionResultStore("project")
    store.put(StoredResult(identity=identity, result=alert))

    saved = store.to_dict()
    (entry,) = saved["molecules"]["m"]["results"]
    assert entry["method_version"] == FRAGMENT_COUNTS_METHOD
    (restored,) = SessionResultStore.from_dict(saved, "project").fresh_results("m", {DRAWING: "fp"})
    assert restored.identity.method_version == FRAGMENT_COUNTS_METHOD
    assert restored.result.name == "Fragment Counts"


def test_the_current_method_never_silently_replaces_a_legacy_one_and_only_it_is_replayed():
    from openchem.domain.result_store import FRAGMENT_COUNTS_METHOD
    from openchem.services.result_identity import make_identity

    store = SessionResultStore.from_dict(_saved_block([_legacy_alert_entry("fragment_counts")]), "project")
    alert = _fragment_counts(["amide (1)"])
    store.put(StoredResult(
        identity=make_identity(molecule_uuid="m", result=alert, calculation_input=DRAWING,
                               input_fingerprint="fp", producer="core"),
        result=alert,
    ))

    methods = sorted(e["method_version"] for e in store.to_dict()["molecules"]["m"]["results"])
    assert methods == ["legacy-rdkit-fr-v1", FRAGMENT_COUNTS_METHOD], "a method overwrote the other"
    (replayed,) = store.fresh_results("m", {DRAWING: "fp"})
    assert replayed.result.matched == ["amide (1)"], "a view got the legacy method, or both"


def test_a_legacy_result_cannot_vouch_for_the_automatic_set():
    from openchem.domain.result_store import BundlePart

    store = SessionResultStore.from_dict(_saved_block([_legacy_alert_entry("fragment_counts")]), "project")
    store.record_part("m", BundlePart("rdkit-alerts", "fp", ("fragment_counts",)))
    state, missing = store.bundle_state("m", "fp", {"rdkit-alerts"})
    assert missing == {"rdkit-alerts"}, "a v1 count stood in for the set that now computes v2"


def test_only_a_declared_result_id_carries_a_method():
    """Every other result's identity -- and so every saved project's keys --
    is unchanged by the field's existence."""
    from openchem.services.result_identity import make_identity

    dataset = PerAtomDataset(property_id="functional_groups", name="Functional Groups", units="",
                             method="m", molecule_uuid="m", values={})
    identity = make_identity(molecule_uuid="m", result=dataset, calculation_input=DRAWING,
                             input_fingerprint="fp", producer="core")
    assert identity.method_version == ""
    store = SessionResultStore("project")
    store.put(StoredResult(identity=identity, result=dataset))
    (entry,) = store.to_dict()["molecules"]["m"]["results"]
    assert "method_version" not in entry


@pytest.mark.parametrize("earlier", ["automatic/v1", "automatic/v2"])
def test_an_earlier_automatic_set_is_not_replayed_by_the_current_build(earlier):
    """The saved manifest names the set it vouches for; a v1 or a v2 manifest
    cannot vouch for the v3 set (fifteen more features), so the always-on work
    reruns."""
    from openchem.domain.result_store import AUTOMATIC_BUNDLE_ID

    assert AUTOMATIC_BUNDLE_ID == "automatic/v3"
    block = _saved_block([_legacy_alert_entry("fragment_counts")])
    block["molecules"]["m"]["bundle"] = {
        "bundle_id": earlier,
        "parts": [{"part_id": "rdkit-alerts", "input_fingerprint": "fp", "result_ids": ["fragment_counts"]}],
    }
    store = SessionResultStore.from_dict(block, "project")
    state, missing = store.bundle_state("m", "fp", {"rdkit-alerts"})
    assert missing == {"rdkit-alerts"}


# ---------------------------------------------------------------------------
# Fragment Counts changed METHOD again (vocabulary v3, 2026-09-20)
#
# A saved v2 project must open, keep what it held, never be upgraded by
# rewriting a string, and be recalculated under v3 identities.
# ---------------------------------------------------------------------------

V2_METHOD = "structural-features-v2"


def _v2_alert_entry(matched=("Amide (1)", "Tertiary Amine (2)")) -> dict:
    """An entry as the v2 build wrote it: the method is recorded explicitly."""
    from openchem.domain.scientific_result import AlertResult

    alert = AlertResult(alert_id="fragment_counts", name="Fragment Counts", molecule_uuid="m",
                        matched=list(matched), category="substructure")
    return {
        "result_id": "fragment_counts",
        "calculation_input": DRAWING,
        "input_fingerprint": "fp",
        "producer": "core",
        "parameters_key": "",
        "method_version": V2_METHOD,
        "result": result_codec.encode(alert),
    }


def _put_current_fragment_counts(store, matched):
    from openchem.services.result_identity import make_identity

    alert = _fragment_counts(matched)
    store.put(StoredResult(
        identity=make_identity(molecule_uuid="m", result=alert, calculation_input=DRAWING,
                               input_fingerprint="fp", producer="core"),
        result=alert,
    ))


def test_a_v2_fragment_count_is_shown_labelled_until_the_current_one_exists():
    from openchem.domain.result_store import SUPERSEDED_METHOD_VERSIONS

    store = SessionResultStore.from_dict(_saved_block([_v2_alert_entry()]), "project")
    label = SUPERSEDED_METHOD_VERSIONS["fragment_counts"][V2_METHOD]
    assert "previous method" in label

    (shown,) = store.fresh_results("m", {DRAWING: "fp"})
    assert shown.identity.method_version == V2_METHOD
    assert shown.result.name == label, "an earlier method must not pass as the current one"
    assert shown.result.matched == ["Amide (1)", "Tertiary Amine (2)"], "its content must survive as it was"
    assert store.load_problems["legacy_method"] == 1

    _put_current_fragment_counts(store, ["amide (1)", "thiocarbamate (1)"])
    (now,) = store.fresh_results("m", {DRAWING: "fp"})
    assert now.result.matched == ["amide (1)", "thiocarbamate (1)"], "the v2 result was replayed beside v3"
    assert any(e["method_version"] == V2_METHOD for e in store.to_dict()["molecules"]["m"]["results"]), (
        "the v2 result was dropped instead of kept"
    )


def test_a_project_holding_v1_and_v2_results_shows_the_newer_and_keeps_both():
    """Both earlier methods are in the file (a project saved by v1, opened and
    saved by v2, opened by v3). One slot shows ONE of them, the newer, never
    both under one id; and the current method, once it exists, shows alone."""
    from openchem.domain.result_store import FRAGMENT_COUNTS_METHOD

    store = SessionResultStore.from_dict(
        _saved_block([_legacy_alert_entry("fragment_counts"), _v2_alert_entry()]), "project")

    (shown,) = store.fresh_results("m", {DRAWING: "fp"})
    assert shown.identity.method_version == V2_METHOD, "the older legacy result was shown"

    _put_current_fragment_counts(store, ["amide (1)", "thiocarbamate (1)"])
    (replayed,) = store.fresh_results("m", {DRAWING: "fp"})
    assert replayed.identity.method_version == FRAGMENT_COUNTS_METHOD
    methods = sorted(e["method_version"] for e in store.to_dict()["molecules"]["m"]["results"])
    assert methods == ["legacy-rdkit-fr-v1", V2_METHOD, FRAGMENT_COUNTS_METHOD]


def test_a_v2_result_is_never_upgraded_by_rewriting_its_method():
    """Through a load, a recalculation, a save and another load: the v2 entry
    still says v2 and still holds v2's counts. Relabelling it would assert a
    detection nobody ran."""
    from openchem.domain.result_store import CURRENT_METHOD_VERSIONS, SUPERSEDED_METHOD_VERSIONS

    current = CURRENT_METHOD_VERSIONS["fragment_counts"]
    assert V2_METHOD != current and current not in SUPERSEDED_METHOD_VERSIONS["fragment_counts"], (
        "a method cannot be both current and superseded"
    )
    store = SessionResultStore.from_dict(_saved_block([_v2_alert_entry()]), "project")
    _put_current_fragment_counts(store, ["amide (1)", "thiocarbamate (1)"])
    saved = store.to_dict()
    by_method = {e["method_version"]: e for e in saved["molecules"]["m"]["results"]}
    assert set(by_method) == {V2_METHOD, current}

    again = SessionResultStore.from_dict(saved, "project")
    again_methods = {e["method_version"] for e in again.to_dict()["molecules"]["m"]["results"]}
    assert again_methods == {V2_METHOD, current}
    v2_payload = result_codec.decode(by_method[V2_METHOD]["result"])
    assert v2_payload.matched == ["Amide (1)", "Tertiary Amine (2)"]


def test_a_v2_manifest_cannot_vouch_for_the_v3_set():
    block = _saved_block([_v2_alert_entry()])
    block["molecules"]["m"]["bundle"] = {
        "bundle_id": "automatic/v2",
        "parts": [{"part_id": "rdkit-alerts", "input_fingerprint": "fp", "result_ids": ["fragment_counts"]}],
    }
    store = SessionResultStore.from_dict(block, "project")
    state, missing = store.bundle_state("m", "fp", {"rdkit-alerts"})
    assert missing == {"rdkit-alerts"}, "a v2 count stood in for the set that now computes v3"


def test_recalculation_writes_v3_identities():
    from openchem.domain.result_store import FRAGMENT_COUNTS_METHOD

    assert FRAGMENT_COUNTS_METHOD == "structural-features-v3"
    store = SessionResultStore.from_dict(_saved_block([_v2_alert_entry()]), "project")
    _put_current_fragment_counts(store, ["amide (1)"])
    (current,) = store.fresh_results("m", {DRAWING: "fp"})
    assert current.identity.method_version == "structural-features-v3"


def test_the_canonical_feature_cache_is_keyed_by_the_vocabulary_version(monkeypatch):
    """The cache is process-local and the version a module constant, so a stale
    set cannot occur today; the key makes that a checked claim. Changing the
    version must MISS, not return the set a different vocabulary made."""
    from rdkit import Chem

    from openchem.chem import structure_annotation

    mol = Chem.MolFromSmiles("CC(=O)Nc1ccccc1")
    structure_annotation._canonical_features_cached.cache_clear()
    first = structure_annotation.canonical_features(mol)
    assert structure_annotation.canonical_features(mol) is first, "the same version must hit"
    monkeypatch.setattr(structure_annotation, "VOCABULARY_VERSION", "openchem-structural-features-vTEST")
    other = structure_annotation.canonical_features(mol)
    assert other is not first, "a different vocabulary version returned the cached set"
    structure_annotation._canonical_features_cached.cache_clear()


def test_no_two_result_producers_declare_the_same_id():
    """The guard for the next collision, built from the STORE's own key
    function over every producer family that writes into it.

    Not a hand-maintained list of ids: `result_id_of` is what the store
    files by, so anything it can name has to be unique here.
    """
    from rdkit import Chem

    from openchem.chem.descriptor_providers import CALCULATOR_DEFINITIONS, RDKitDescriptorProvider

    # A molecule with enough groups that every always-on catalog answers.
    mol = Chem.MolFromSmiles("CC(=O)Oc1ccccc1C(=O)O")
    seen: dict[str, str] = {}

    def claim(result_id: str, owner: str) -> None:
        assert result_id not in seen, (
            f"{result_id!r} is declared by both {seen[result_id]} and {owner}; "
            "the store keys results by this id, so they would overwrite each other"
        )
        seen[result_id] = owner

    for definition in CALCULATOR_DEFINITIONS:
        claim(definition.calculator_id, f"calculator {definition.calculator_id}")
    for alert in RDKitDescriptorProvider().compute_alerts(mol, "m"):
        claim(result_id_of(alert), f"always-on alert {alert.name}")
    from openchem.domain.result_store import MIGRATED_RESULT_IDS, RETIRED_RESULT_IDS

    for retired in RETIRED_RESULT_IDS:
        claim(retired, "RETIRED_RESULT_IDS")
    for (old_id, payload_type), new_id in MIGRATED_RESULT_IDS.items():
        assert new_id in seen, f"{new_id!r} is a migration target that nothing produces"
        # The old id may legitimately still be produced -- by the OTHER
        # producer that shared it, which is why the migration is keyed by the
        # payload type. What must not happen is the old id still being
        # produced BY THAT PAYLOAD TYPE, which would mean the rename did not
        # take. `functional_groups` is exactly this case: the per-atom
        # calculator keeps the id, the AlertResult moved away.
        owner = seen.get(old_id, "")
        assert not (payload_type == "AlertResult" and "alert" in owner), (
            f"{old_id!r} is still produced as an {payload_type} by {owner}"
        )
