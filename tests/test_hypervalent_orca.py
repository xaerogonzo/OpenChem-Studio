"""ORCA on a held ClF3: the input it is given, and (with a real ORCA) what it makes of the VSEPR start.

The input test needs no ORCA: it builds the real input text from the geometry the conformer pipeline made and
reads it back. The real run is skipped unless `OPENCHEM_ORCA_EXE` names an ORCA (this machine: D:/ORCA/orca.exe);
it records method, basis, convergence and the resulting angles, and does NOT assume the T-shape survives.
"""

from __future__ import annotations

import math
import os
import re
from pathlib import Path

import numpy as np
import pytest
from PySide6.QtCore import QThreadPool
from rdkit import Chem

from openchem.chem.conformer_providers import RDKitConformerProvider, search_conformers, GenerationOptions
from openchem.chem.orca_engine import OrcaQuantumEngineProvider
from openchem.chem.quantum_run_request import PreparedRun, RunChoice, RunRefusal, prepare_run, start
from openchem.chem.engine import ChemistryEngine
from openchem.domain.conformer import ConformerModel
from openchem.domain.molecule import MoleculeModel
from tests.test_chem_engine import _hypervalent_molblock

METHOD = "B3LYP def2-SVP"


def _molecule_with_conformer(engine: ChemistryEngine) -> MoleculeModel:
    molecule = MoleculeModel(display_name="ClF3")
    engine.set_structure_from_molblock(molecule, _hypervalent_molblock("Cl", "F", 3), allow_hypervalent=True)
    mol = engine.mol_from_model(molecule, allow_hypervalent=True)
    outcome = search_conformers(RDKitConformerProvider(random_seed=1), mol, True, GenerationOptions())
    conf_mol, energy = outcome.pool[0]
    molecule.conformers.append(
        ConformerModel(molblock=engine.mol_to_molblock(conf_mol), energy=energy, method="vsepr_template")
    )
    return molecule


def _choice(calc_type: str) -> RunChoice:
    return RunChoice(calc_type=calc_type, method_basis=METHOD, charge=0, multiplicity=1, provider_id="orca")


def test_a_held_clf3_conformer_is_a_valid_orca_input():
    engine = ChemistryEngine()
    molecule = _molecule_with_conformer(engine)

    prepared = prepare_run(engine, molecule, _choice("opt"))

    assert isinstance(prepared, PreparedRun), getattr(prepared, "message", prepared)
    text = OrcaQuantumEngineProvider().build_input(prepared.mol, 0, 1, METHOD, "opt")
    lines = text.splitlines()
    start_at = next(i for i, line in enumerate(lines) if line.startswith("* xyz"))
    assert lines[start_at].split() == ["*", "xyz", "0", "1"]
    atoms = []
    for line in lines[start_at + 1 :]:
        if line.strip() == "*":
            break
        symbol, x, y, z = line.split()
        atoms.append((symbol, np.array([float(x), float(y), float(z)])))
    assert [a for a, _ in atoms] == [a.GetSymbol() for a in prepared.mol.GetAtoms()]
    assert sorted(a for a, _ in atoms) == ["Cl", "F", "F", "F"]
    centre = next(p for s, p in atoms if s == "Cl")
    lengths = sorted(round(float(np.linalg.norm(p - centre)), 3) for s, p in atoms if s == "F")
    assert lengths == [1.597, 1.697, 1.697], "Angstrom coordinates, the published lengths, nothing added or dropped"
    assert not re.search(r"\bH\b", text.split("* xyz")[1]), "no hydrogen may appear"


def test_the_charge_default_and_run_preparation_do_not_refuse_a_hypervalent_conformer():
    engine = ChemistryEngine()
    molecule = _molecule_with_conformer(engine)
    assert engine.formal_charge(molecule) == 0
    prepared = prepare_run(engine, molecule, _choice("sp"))
    assert not isinstance(prepared, RunRefusal)
    assert prepared.fingerprint  # the geometry identity the result will be stamped with


ORCA = os.environ.get("OPENCHEM_ORCA_EXE", "")


@pytest.mark.skipif(not (ORCA and Path(ORCA).exists()), reason="needs a real ORCA: set OPENCHEM_ORCA_EXE")
def test_real_orca_optimizes_the_vsepr_start(qapp, tmp_path):
    from openchem.bootstrap import build_service_container
    from openchem.events.events import QuantumChemistryJobStateChanged, QuantumChemistryResultReady
    from openchem.domain.common import CacheState

    services = build_service_container()
    qc = services.quantum_chemistry_service
    qc._settings.set("orca/executable_path", ORCA)
    engine = services.chemistry_engine
    molecule = _molecule_with_conformer(engine)
    states: list[QuantumChemistryJobStateChanged] = []
    results: list[QuantumChemistryResultReady] = []
    services.event_bus.subscribe(QuantumChemistryJobStateChanged, states.append)
    services.event_bus.subscribe(QuantumChemistryResultReady, results.append)

    prepared = prepare_run(engine, molecule, _choice("opt"))
    assert isinstance(prepared, PreparedRun)
    start(qc, prepared)
    import time

    deadline = time.time() + 280
    while time.time() < deadline and not results and not any(s.state == CacheState.FAILED for s in states):
        qapp.processEvents()
        time.sleep(0.05)
    QThreadPool.globalInstance().waitForDone(5000)
    qapp.processEvents()

    failure = [s.message for s in states if s.state == CacheState.FAILED]
    assert results, failure or [s.message for s in states]
    conformer = results[-1].conformer
    assert conformer is not None and conformer.method == "orca_opt"
    mol = Chem.MolFromMolBlock(conformer.molblock, sanitize=False, removeHs=False)
    pts = [np.array(mol.GetConformer().GetAtomPosition(i)) for i in range(4)]
    centre = next(i for i, a in enumerate(mol.GetAtoms()) if a.GetSymbol() == "Cl")
    ligands = [i for i in range(4) if i != centre]
    angles = sorted(
        round(math.degrees(math.acos(float(np.dot(pts[i] - pts[centre], pts[j] - pts[centre])
              / (np.linalg.norm(pts[i] - pts[centre]) * np.linalg.norm(pts[j] - pts[centre]))))), 1)
        for n, i in enumerate(ligands) for j in ligands[n + 1 :]
    )
    lengths = sorted(round(float(np.linalg.norm(pts[i] - pts[centre])), 3) for i in ligands)
    print(f"\nORCA {METHOD}: angles {angles}, Cl-F {lengths}")
    # A T-shape has two near-90 degree angles and one near-180; the measurement is printed above, this is the shape test.
    assert angles[0] < 100 and angles[1] < 100 and angles[2] > 160
