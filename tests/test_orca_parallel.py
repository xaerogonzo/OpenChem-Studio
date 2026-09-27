from __future__ import annotations

from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.app.settings import Settings
from openchem.chem import orca_engine
from openchem.chem.orca_engine import (
    AUTO_CORES_CAP,
    OrcaQuantumEngineProvider,
    add_parallel_block,
    default_cores,
)
from openchem.events.base import EventBus
from openchem.services import quantum_chemistry_service as service_module
from openchem.services.quantum_chemistry_service import QuantumChemistryService


def _water():
    mol = Chem.AddHs(Chem.MolFromSmiles("O"))
    AllChem.EmbedMolecule(mol, randomSeed=1)
    return mol


def test_the_pal_block_goes_straight_after_the_keyword_line():
    text = "! B3LYP def2-SVP NMR\n* xyz 0 1\nO 0 0 0\n*\n"
    lines = add_parallel_block(text, 8).split("\n")
    assert lines[0] == "! B3LYP def2-SVP NMR"
    assert lines[1] == "%pal nprocs 8 end"
    assert lines[2] == "* xyz 0 1"


def test_one_core_leaves_the_input_untouched():
    text = "! HF STO-3G\n* xyz 0 1\nO 0 0 0\n*\n"
    assert add_parallel_block(text, 1) == text


def test_the_automatic_core_count_is_capped_at_what_was_measured(monkeypatch):
    monkeypatch.setattr(orca_engine.os, "cpu_count", lambda: 64)
    assert default_cores() == AUTO_CORES_CAP
    monkeypatch.setattr(orca_engine.os, "cpu_count", lambda: 1)
    assert default_cores() == 1


def test_orca_says_it_can_run_parallel():
    assert OrcaQuantumEngineProvider.supports_parallel is True


def _service():
    bus = EventBus()
    settings = Settings(bus)
    return QuantumChemistryService(bus, settings, providers={}), settings


def test_without_mpi_a_job_is_always_serial(qapp, monkeypatch):
    """A parallel input with no mpiexec aborts in Startup rather than running
    slowly, so the setting must not be able to ask for it."""
    service, settings = _service()
    settings.set("orca/cores", 16)
    monkeypatch.setattr(service_module, "find_mpi_bin", lambda: None)
    assert service._effective_cores() == 1


def test_with_mpi_the_setting_wins_and_zero_means_automatic(qapp, monkeypatch):
    service, settings = _service()
    monkeypatch.setattr(service_module, "find_mpi_bin", lambda: "C:/mpi")
    settings.set("orca/cores", 6)
    assert service._effective_cores() == 6
    settings.set("orca/cores", 0)
    assert service._effective_cores() == default_cores()
