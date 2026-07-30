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

# ALA residue + a crystallographic water + a non-standard HETATM (zinc, a
# common cofactor) + a duplicate-altloc atom on the CB, for exercising
# receptor_prep_options end to end through the real Open Babel pipeline.
RECEPTOR_PDB_WITH_EXTRAS = """HEADER    TEST
ATOM      1  N   ALA A   1      11.104  13.207   2.845  1.00 20.00           N
ATOM      2  CA  ALA A   1      11.999  12.040   2.945  1.00 20.00           C
ATOM      3  C   ALA A   1      13.398  12.442   2.508  1.00 20.00           C
ATOM      4  O   ALA A   1      13.598  13.601   2.128  1.00 20.00           O
ATOM      5  CB AALA A   1      11.500  10.800   2.000  0.60 20.00           C
ATOM      6  CB BALA A   1      11.600  10.900   2.100  0.40 20.00           C
HETATM    7  O   HOH A   2      20.000  20.000  20.000  1.00 20.00           O
HETATM    8 ZN   ZN  A   3      25.000  25.000  25.000  1.00 20.00          ZN
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
        # A real engine would have written receptor_pdbqt/ligand_pdbqt (by
        # the time dock() is called, VinaDockingProvider has already
        # created them) -- assert that here as a sanity check, and capture
        # the receptor's actual PDBQT text now, while the scratch dir still
        # exists (VinaDockingProvider.dock's `with tempfile.TemporaryDirectory`
        # deletes it as soon as this call returns).
        assert Path(receptor_pdbqt).exists()
        assert Path(ligand_pdbqt).exists()
        self.dock_calls.append(
            {
                "receptor_pdbqt": receptor_pdbqt,
                "ligand_pdbqt": ligand_pdbqt,
                "box": box,
                "num_poses": num_poses,
                "receptor_pdbqt_text": Path(receptor_pdbqt).read_text(encoding="utf-8"),
            }
        )
        if self._raise_error:
            raise RuntimeError("boom")
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


def test_receptor_pdbqt_is_prepared_as_rigid_not_flexible():
    """Regression test: confirmed live against a real 327-atom protein that
    the default `pybel.Molecule.write("pdbqt", ...)` treats the WHOLE
    receptor as one flexible ligand-style structure, emitting
    ROOT/BRANCH/TORSDOF records and reporting "104 active torsions" -- a
    docking receptor must be rigid. `_convert_receptor_to_pdbqt` must pass
    Open Babel's rigid-receptor option (`opt={"r": None}`, the `-xr` CLI
    equivalent) so none of those records appear."""
    engine = FakeVinaEngine()
    provider = VinaDockingProvider(engine=engine)
    mol = Chem.MolFromSmiles("CCO")
    box = DockingBox(center=(0, 0, 0), size=(20, 20, 20))

    provider.dock(RECEPTOR_PDB, "pdb", mol, box, 9, ProgressHandle())

    receptor_text = engine.dock_calls[0]["receptor_pdbqt_text"]
    assert "ROOT" not in receptor_text
    assert "BRANCH" not in receptor_text
    assert "TORSDOF" not in receptor_text


def test_receptor_prep_strips_waters_by_default():
    engine = FakeVinaEngine()
    provider = VinaDockingProvider(engine=engine)
    mol = Chem.MolFromSmiles("CCO")
    box = DockingBox(center=(0, 0, 0), size=(20, 20, 20))

    provider.dock(RECEPTOR_PDB_WITH_EXTRAS, "pdb", mol, box, 9, ProgressHandle())

    receptor_text = engine.dock_calls[0]["receptor_pdbqt_text"]
    assert "HOH" not in receptor_text


def test_receptor_prep_keeps_waters_when_disabled():
    engine = FakeVinaEngine()
    provider = VinaDockingProvider(engine=engine)
    mol = Chem.MolFromSmiles("CCO")
    box = DockingBox(center=(0, 0, 0), size=(20, 20, 20))

    provider.dock(
        RECEPTOR_PDB_WITH_EXTRAS, "pdb", mol, box, 9, ProgressHandle(),
        receptor_prep_options={"strip_waters": False},
    )

    receptor_text = engine.dock_calls[0]["receptor_pdbqt_text"]
    assert "HOH" in receptor_text


def test_receptor_prep_keeps_cofactors_by_default():
    engine = FakeVinaEngine()
    provider = VinaDockingProvider(engine=engine)
    mol = Chem.MolFromSmiles("CCO")
    box = DockingBox(center=(0, 0, 0), size=(20, 20, 20))

    provider.dock(RECEPTOR_PDB_WITH_EXTRAS, "pdb", mol, box, 9, ProgressHandle())

    receptor_text = engine.dock_calls[0]["receptor_pdbqt_text"]
    assert "ZN" in receptor_text


def test_receptor_prep_strips_cofactors_when_enabled():
    engine = FakeVinaEngine()
    provider = VinaDockingProvider(engine=engine)
    mol = Chem.MolFromSmiles("CCO")
    box = DockingBox(center=(0, 0, 0), size=(20, 20, 20))

    provider.dock(
        RECEPTOR_PDB_WITH_EXTRAS, "pdb", mol, box, 9, ProgressHandle(),
        receptor_prep_options={"strip_cofactors": True},
    )

    receptor_text = engine.dock_calls[0]["receptor_pdbqt_text"]
    assert "ZN" not in receptor_text
    # A standard residue (ALA) must survive strip_cofactors -- it only
    # removes non-standard HETATM residues, not the receptor itself.
    assert "ALA" in receptor_text


def test_receptor_prep_filters_duplicate_altlocs():
    """Regression test: confirmed live that Open Babel's own PDB reader
    does NOT dedupe alternate locations -- a two-altloc atom comes back as
    two full atoms at two positions. `_filter_pdb_altlocs` must drop every
    altloc except blank/'A' before Open Babel ever reads the structure."""
    engine = FakeVinaEngine()
    provider = VinaDockingProvider(engine=engine)
    mol = Chem.MolFromSmiles("CCO")
    box = DockingBox(center=(0, 0, 0), size=(20, 20, 20))

    provider.dock(RECEPTOR_PDB_WITH_EXTRAS, "pdb", mol, box, 9, ProgressHandle())

    receptor_text = engine.dock_calls[0]["receptor_pdbqt_text"]
    # Exactly one CB atom line should survive (the 'A' altloc), not two.
    cb_lines = [line for line in receptor_text.splitlines() if " CB " in line]
    assert len(cb_lines) == 1


def test_receptor_prep_ph_is_passed_to_add_hydrogens():
    """Doesn't assert a specific protonation outcome (fragile/chemistry-
    dependent) -- just that a custom pH actually reaches AddHydrogens
    instead of always using the 7.4 default, via a spy on OBMol."""
    from openbabel import openbabel as ob

    engine = FakeVinaEngine()
    provider = VinaDockingProvider(engine=engine)
    mol = Chem.MolFromSmiles("CCO")
    box = DockingBox(center=(0, 0, 0), size=(20, 20, 20))

    calls = []
    original = ob.OBMol.AddHydrogens

    # Matches OBMol::AddHydrogens' real C++ defaults -- the ligand-prep
    # path (_convert_ligand_to_pdbqt) also calls this, via pybel's own
    # addh() wrapper, with no arguments at all.
    def spy(self, polaronly=False, correct_for_ph=False, ph=7.4):
        calls.append((polaronly, correct_for_ph, ph))
        return original(self, polaronly, correct_for_ph, ph)

    with patch.object(ob.OBMol, "AddHydrogens", spy):
        provider.dock(
            RECEPTOR_PDB, "pdb", mol, box, 9, ProgressHandle(),
            receptor_prep_options={"ph": 5.0},
        )

    # The receptor-prep call (polaronly=False, correctForPH=True, pH=5.0)
    # must be among the calls made -- the ligand-prep path's own addh()
    # call (with all defaults) is expected too and isn't what's under test.
    assert (False, True, 5.0) in calls


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
