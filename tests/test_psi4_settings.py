"""Psi4's own memory and thread settings (`PSI4_MEMORY_GB`, `PSI4_THREADS`): what reaches the input and the command line, and what the Settings window offers.

Nothing here runs Psi4. A real run is the agreement check's job (`benchmarks/psi4_agreement/`); what is tested is that the person's choice reaches the two places Psi4 reads it, that the defaults leave
every input and command line as it was, and that a hand-damaged value cannot take a job down with it.
"""

from __future__ import annotations

from pathlib import Path

import conftest
import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.app.settings import PSI4_MEMORY_GB, PSI4_THREADS, Settings
from openchem.chem import psi4_engine
from openchem.chem.orca_engine import default_cores
from openchem.chem.psi4_engine import DEFAULT_MEMORY_GB, Psi4QuantumEngineProvider
from openchem.events.base import EventBus
from openchem.services.quantum_chemistry_service import QuantumChemistryService
from openchem.ui.dialogs.settings_dialog import SettingsDialog


def _water() -> Chem.Mol:
    mol = Chem.AddHs(Chem.MolFromSmiles("O"))
    AllChem.EmbedMolecule(mol, randomSeed=7)
    return mol


def _memory_line(provider: Psi4QuantumEngineProvider) -> str:
    return provider.build_input(_water(), 0, 1, "B3LYP def2-SVP", "sp").splitlines()[0]


# --- memory ---------------------------------------------------------------------------------------------------------------


def test_the_default_input_is_the_one_the_engine_always_wrote():
    """2 GB, in the same words: the agreement check's records hash the input, so a default that moved by one character would orphan them."""
    assert _memory_line(Psi4QuantumEngineProvider()) == "memory 2 GB"
    assert DEFAULT_MEMORY_GB == PSI4_MEMORY_GB.default == 2


def test_the_memory_setting_reaches_the_input():
    assert _memory_line(Psi4QuantumEngineProvider(memory_gb=lambda: 8)) == "memory 8 GB"


def test_memory_is_read_each_time_an_input_is_written():
    value = {"gb": 4}
    provider = Psi4QuantumEngineProvider(memory_gb=lambda: value["gb"])

    assert _memory_line(provider) == "memory 4 GB"
    value["gb"] = 16
    assert _memory_line(provider) == "memory 16 GB"


@pytest.mark.parametrize("asked", [0, -3])
def test_memory_below_one_gb_is_never_written(asked):
    """Psi4's own 500 MB default is what the floor exists to avoid; a provider handed less than 1 GB writes 1."""
    assert _memory_line(Psi4QuantumEngineProvider(memory_gb=lambda: asked)) == "memory 1 GB"


# --- threads --------------------------------------------------------------------------------------------------------------


def _service():
    bus = EventBus()
    settings = Settings(bus)
    return QuantumChemistryService(bus, settings), settings


def _psi4(service: QuantumChemistryService) -> Psi4QuantumEngineProvider:
    return {p.provider_id: p for p in service.engines()}["psi4"]


def _threads_of(service: QuantumChemistryService) -> int:
    provider = _psi4(service)
    args = provider.command_args("psi4.exe", Path("job.dat"))
    return int(args[args.index("-n") + 1])


def test_automatic_threads_follow_orcas_core_count_and_then_the_machines(qapp):
    service, settings = _service()

    assert settings.preference(PSI4_THREADS) == 0
    assert _threads_of(service) == default_cores()
    settings.set("orca/cores", 3)
    assert _threads_of(service) == 3


def test_a_thread_count_of_its_own_wins_over_orcas(qapp):
    service, settings = _service()
    settings.set("orca/cores", 3)

    settings.set_preference(PSI4_THREADS, 5)

    assert _threads_of(service) == 5
    settings.set_preference(PSI4_THREADS, 0)
    assert _threads_of(service) == 3, "back to automatic means ORCA's setting again"


def test_the_service_reads_the_memory_setting_when_it_writes_the_input(qapp):
    service, settings = _service()
    provider = _psi4(service)

    assert _memory_line(provider) == "memory 2 GB"
    settings.set_preference(PSI4_MEMORY_GB, 12)
    assert _memory_line(provider) == "memory 12 GB"


def test_a_damaged_memory_or_thread_value_falls_back_to_the_default(qapp):
    """A hand-edited store must not take a Psi4 job down: `Settings.preference` logs it and answers with the default."""
    service, settings = _service()
    settings.set(PSI4_MEMORY_GB.key, "lots")
    settings.set(PSI4_THREADS.key, "-4")
    provider = _psi4(service)

    assert _memory_line(provider) == "memory 2 GB"
    assert _threads_of(service) == default_cores()


def test_the_limits_are_the_ones_the_plan_chose():
    assert (PSI4_MEMORY_GB.minimum, PSI4_MEMORY_GB.default, PSI4_MEMORY_GB.maximum) == (1, 2, 512)
    assert (PSI4_THREADS.minimum, PSI4_THREADS.default, PSI4_THREADS.maximum) == (0, 0, 256)
    assert psi4_engine.DEFAULT_MEMORY_GB >= PSI4_MEMORY_GB.minimum


# --- the Settings window --------------------------------------------------------------------------------------------------


@pytest.fixture
def dialogs():
    built = []
    yield built
    for dialog in built:
        conftest.dispose(dialog)


def _dialog(dialogs, settings) -> SettingsDialog:
    dialog = SettingsDialog(settings)
    dialogs.append(dialog)
    return dialog


def test_the_settings_window_offers_both_and_stores_a_change(qapp, dialogs):
    settings = Settings(EventBus())
    dialog = _dialog(dialogs, settings)

    assert dialog._psi4_memory.value() == 2 and dialog._psi4_threads.value() == 0
    assert dialog._psi4_threads.specialValueText() == "Automatic"
    dialog._psi4_memory.setValue(6)
    dialog._psi4_threads.setValue(4)

    assert settings.preference(PSI4_MEMORY_GB) == 6 and settings.preference(PSI4_THREADS) == 4


def test_the_window_bounds_each_box_by_the_preferences_own_range(qapp, dialogs):
    dialog = _dialog(dialogs, Settings(EventBus()))

    assert (dialog._psi4_memory.minimum(), dialog._psi4_memory.maximum()) == (PSI4_MEMORY_GB.minimum, PSI4_MEMORY_GB.maximum)
    assert (dialog._psi4_threads.minimum(), dialog._psi4_threads.maximum()) == (PSI4_THREADS.minimum, PSI4_THREADS.maximum)
