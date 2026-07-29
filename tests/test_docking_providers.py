from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from rdkit import Chem

from openchem.chem.docking_providers import DockingProviderError, VinaDockingProvider
from openchem.chem.vina_engine import VinaEngine
from openchem.domain.docking import DockingBox
from openchem.services.progress import ProgressHandle

# Real Vina output shape (confirmed against the official documented
# format) for a single pose, fed through a FakeVinaEngine so this test
# exercises the real Open Babel receptor/ligand/pose PDBQT conversion
# pipeline (openbabel-wheel is actually installed here) without needing a
# real Vina backend (no Windows wheel available for the `vina` package —
# see chem/vina_engine.py's docstring).
FAKE_OUTPUT = """MODEL 1
REMARK VINA RESULT:    -5.2      0.000      0.000
ROOT
ATOM      1  C1  LIG     1       1.000   2.000   3.000  1.00  0.00     0.000 C
ATOM      2  C2  LIG     1       2.000   2.000   3.000  1.00  0.00     0.000 C
ENDROOT
TORSDOF 0
ENDMDL
"""

RECEPTOR_PDB = """HEADER    TEST
ATOM      1  N   ALA A   1      11.104  13.207   2.845  1.00 20.00           N
ATOM      2  CA  ALA A   1      11.999  12.040   2.945  1.00 20.00           C
ATOM      3  C   ALA A   1      13.398  12.442   2.508  1.00 20.00           C
ATOM      4  O   ALA A   1      13.598  13.601   2.128  1.00 20.00           O
END
"""


class FakeVinaEngine(VinaEngine):
    engine_id = "fake"

    def __init__(self, output: str = FAKE_OUTPUT, raise_error: bool = False) -> None:
        self._output = output
        self._raise_error = raise_error
        self.dock_calls: list[dict] = []

    def is_available(self) -> bool:
        return True

    def version(self) -> str:
        return "1.0.0-fake"

    def dock(self, receptor_pdbqt, ligand_pdbqt, box, num_poses, exhaustiveness, seed, progress):
        self.dock_calls.append(
            {
                "receptor_pdbqt": receptor_pdbqt,
                "ligand_pdbqt": ligand_pdbqt,
                "box": box,
                "num_poses": num_poses,
            }
        )
        if self._raise_error:
            raise RuntimeError("boom")
        # A real engine would have written receptor_pdbqt/ligand_pdbqt
        # (by the time dock() is called, VinaDockingProvider has already
        # created them) -- assert that here as a sanity check.
        assert Path(receptor_pdbqt).exists()
        assert Path(ligand_pdbqt).exists()
        progress.report(1.0, "done")
        return self._output


def test_dock_with_no_engine_raises_clear_error():
    provider = VinaDockingProvider(engine=None)
    mol = Chem.MolFromSmiles("CCO")
    box = DockingBox(center=(0, 0, 0), size=(20, 20, 20))

    with pytest.raises(DockingProviderError, match="No Vina docking backend"):
        provider.dock(RECEPTOR_PDB, "pdb", mol, box, 9, ProgressHandle())


def test_dock_produces_poses_via_real_openbabel_conversion():
    engine = FakeVinaEngine()
    provider = VinaDockingProvider(engine=engine)
    mol = Chem.MolFromSmiles("CCO")
    box = DockingBox(center=(1.0, 2.0, 3.0), size=(20.0, 20.0, 20.0))

    poses = provider.dock(RECEPTOR_PDB, "pdb", mol, box, 9, ProgressHandle())

    assert len(poses) == 1
    assert poses[0].binding_affinity_kcal_mol == -5.2
    assert poses[0].rmsd_lb == 0.0
    assert "V2000" in poses[0].pose_molblock or "M  END" in poses[0].pose_molblock

    assert len(engine.dock_calls) == 1
    assert engine.dock_calls[0]["box"] is box
    assert engine.dock_calls[0]["num_poses"] == 9


def test_dock_wraps_engine_errors():
    engine = FakeVinaEngine(raise_error=True)
    provider = VinaDockingProvider(engine=engine)
    mol = Chem.MolFromSmiles("CCO")
    box = DockingBox(center=(0, 0, 0), size=(20, 20, 20))

    with pytest.raises(RuntimeError, match="boom"):
        provider.dock(RECEPTOR_PDB, "pdb", mol, box, 9, ProgressHandle())


def test_dock_with_bad_receptor_text_raises_docking_error():
    engine = FakeVinaEngine()
    provider = VinaDockingProvider(engine=engine)
    mol = Chem.MolFromSmiles("CCO")
    box = DockingBox(center=(0, 0, 0), size=(20, 20, 20))

    with pytest.raises(DockingProviderError, match="Failed to prepare receptor"):
        provider.dock("not a valid structure @#$%", "pdb", mol, box, 9, ProgressHandle())


def test_engine_id_and_version_reflect_selected_engine():
    provider_with_engine = VinaDockingProvider(engine=FakeVinaEngine())
    assert provider_with_engine.engine_id == "fake"
    assert provider_with_engine.engine_version() == "1.0.0-fake"

    provider_without_engine = VinaDockingProvider(engine=None)
    assert provider_without_engine.engine_id == "none"
    assert provider_without_engine.engine_version() == "unknown"


def test_executable_path_resolver_is_consulted_not_settings_directly():
    """VinaDockingProvider must stay decoupled from openchem.app.Settings
    (chem/ is a lower layer than app/) -- it only ever calls a generic
    Callable[[], str] resolver, which DockingService supplies as a closure
    over the real Settings object."""
    calls = []

    def resolver() -> str:
        calls.append(1)
        return ""

    provider = VinaDockingProvider(executable_path_resolver=resolver)
    # No real vina/executable available in this environment, so this
    # resolves to "none" -- the point is just that the resolver got called.
    assert provider.engine_id == "none"
    assert calls == [1]


def test_last_resolved_engine_is_cached_after_dock_not_recomputed():
    """engine_id/engine_version() must describe exactly what the most
    recent dock() call actually used, read from a cache set by dock() —
    not re-resolved independently on every access. If they did re-resolve
    each time, a resolver whose return value changes between calls (e.g.
    settings changing mid-job) could make them disagree with what actually
    ran. Patches `_resolve_engine` itself to count calls, since a fixed
    `engine=` override would bypass resolution entirely and prove nothing.
    """
    engine = FakeVinaEngine()
    provider = VinaDockingProvider(executable_path_resolver=lambda: "")
    mol = Chem.MolFromSmiles("CCO")
    box = DockingBox(center=(0, 0, 0), size=(20, 20, 20))

    with patch.object(provider, "_resolve_engine", return_value=engine) as mock_resolve:
        provider.dock(RECEPTOR_PDB, "pdb", mol, box, 9, ProgressHandle())
        assert mock_resolve.call_count == 1

        assert provider.engine_id == "fake"
        assert provider.engine_version() == "1.0.0-fake"
        # engine_id/engine_version() must not have called _resolve_engine
        # again -- they read the cached _last_resolved_engine from dock().
        assert mock_resolve.call_count == 1
