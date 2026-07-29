from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch

import pytest

from openchem.chem.vina_engine import (
    ExecutableVinaEngine,
    PythonVinaEngine,
    RawPose,
    parse_vina_output_pdbqt,
    select_vina_engine,
)
from openchem.domain.docking import DockingBox
from openchem.services.progress import ProgressHandle

SAMPLE_OUTPUT = """MODEL 1
REMARK VINA RESULT:    -5.2      0.000      0.000
REMARK INTER + INTRA:            -6.1
ROOT
ATOM      1  C1  LIG     1      12.345  23.456  34.567  0.00  0.00     0.123 C
ENDROOT
TORSDOF 3
ENDMDL
MODEL 2
REMARK VINA RESULT:    -4.8      1.234      2.345
ROOT
ATOM      1  C1  LIG     1      13.345  24.456  35.567  0.00  0.00     0.123 C
ENDROOT
TORSDOF 3
ENDMDL
"""


def test_parse_vina_output_pdbqt_extracts_all_poses():
    poses = parse_vina_output_pdbqt(SAMPLE_OUTPUT)

    assert len(poses) == 2
    assert poses[0] == RawPose(
        pdbqt_text=poses[0].pdbqt_text, binding_affinity_kcal_mol=-5.2, rmsd_lb=0.0, rmsd_ub=0.0
    )
    assert poses[1].binding_affinity_kcal_mol == -4.8
    assert poses[1].rmsd_lb == 1.234
    assert poses[1].rmsd_ub == 2.345
    assert "ATOM      1  C1  LIG" in poses[0].pdbqt_text


def test_parse_vina_output_pdbqt_empty_text_returns_no_poses():
    assert parse_vina_output_pdbqt("") == []


def test_parse_vina_output_pdbqt_ignores_model_without_result_line():
    text = "MODEL 1\nROOT\nATOM 1 C LIG\nENDROOT\nENDMDL\n"
    assert parse_vina_output_pdbqt(text) == []


def _fake_vina_module():
    """Builds a fake `vina` module matching the real package's documented
    Vina class shape (confirmed against the actual cached source), so
    PythonVinaEngine can be exercised without the real package installed
    (no Windows wheel available -- see chem/vina_engine.py's docstring).
    """
    fake_vina_instance = MagicMock()
    fake_vina_instance.poses.return_value = SAMPLE_OUTPUT

    fake_module = types.ModuleType("vina")
    fake_module.Vina = MagicMock(return_value=fake_vina_instance)
    return fake_module, fake_vina_instance


def test_python_vina_engine_is_available_reflects_import():
    engine = PythonVinaEngine()
    with patch.dict(sys.modules, {"vina": types.ModuleType("vina")}):
        assert engine.is_available() is True

    # Simulate the real environment (no wheel) by making the import fail.
    with patch.dict(sys.modules, {"vina": None}):
        assert engine.is_available() is False


def test_python_vina_engine_dock_calls_expected_sequence():
    fake_module, fake_instance = _fake_vina_module()
    engine = PythonVinaEngine()
    box = DockingBox(center=(1.0, 2.0, 3.0), size=(20.0, 20.0, 20.0))
    progress = ProgressHandle()

    with patch.dict(sys.modules, {"vina": fake_module}):
        result = engine.dock(
            receptor_pdbqt=__import__("pathlib").Path("receptor.pdbqt"),
            ligand_pdbqt=__import__("pathlib").Path("ligand.pdbqt"),
            box=box,
            num_poses=9,
            exhaustiveness=8,
            seed=42,
            progress=progress,
        )

    assert result == SAMPLE_OUTPUT
    fake_module.Vina.assert_called_once_with(sf_name="vina", seed=42, verbosity=0)
    fake_instance.set_receptor.assert_called_once_with("receptor.pdbqt")
    fake_instance.set_ligand_from_file.assert_called_once_with("ligand.pdbqt")
    fake_instance.compute_vina_maps.assert_called_once_with(center=[1.0, 2.0, 3.0], box_size=[20.0, 20.0, 20.0])
    fake_instance.dock.assert_called_once_with(exhaustiveness=8, n_poses=9)
    fake_instance.poses.assert_called_once_with(n_poses=9)


def test_executable_vina_engine_not_available_without_configured_path():
    engine = ExecutableVinaEngine(executable_path=None)
    with patch("shutil.which", return_value=None):
        assert ExecutableVinaEngine(executable_path=None).is_available() is False


def test_executable_vina_engine_dock_invokes_subprocess(tmp_path):
    exe_path = tmp_path / "vina.exe"
    exe_path.write_text("")  # just needs to exist for is_available()
    engine = ExecutableVinaEngine(executable_path=str(exe_path))
    box = DockingBox(center=(1.0, 2.0, 3.0), size=(20.0, 20.0, 20.0))
    progress = ProgressHandle()

    def fake_run(args, capture_output, text, check):
        # Simulate Vina writing its --out file.
        out_index = args.index("--out")
        __import__("pathlib").Path(args[out_index + 1]).write_text(SAMPLE_OUTPUT, encoding="utf-8")
        return MagicMock(returncode=0)

    with patch("subprocess.run", side_effect=fake_run) as mock_run:
        result = engine.dock(
            receptor_pdbqt=tmp_path / "receptor.pdbqt",
            ligand_pdbqt=tmp_path / "ligand.pdbqt",
            box=box,
            num_poses=9,
            exhaustiveness=8,
            seed=None,
            progress=progress,
        )

    assert result == SAMPLE_OUTPUT
    args = mock_run.call_args[0][0]
    assert str(exe_path) == args[0]
    assert "--center_x" in args and "1.0" in args


def test_executable_vina_engine_not_available_raises_on_dock():
    engine = ExecutableVinaEngine(executable_path=None)
    with patch("shutil.which", return_value=None):
        with pytest.raises(RuntimeError):
            engine.dock(
                receptor_pdbqt=__import__("pathlib").Path("r.pdbqt"),
                ligand_pdbqt=__import__("pathlib").Path("l.pdbqt"),
                box=DockingBox(center=(0, 0, 0), size=(20, 20, 20)),
                num_poses=9,
                exhaustiveness=8,
                seed=None,
                progress=ProgressHandle(),
            )


def test_select_vina_engine_prefers_python_when_available():
    fake_module, _ = _fake_vina_module()
    with patch.dict(sys.modules, {"vina": fake_module}):
        engine = select_vina_engine()
    assert isinstance(engine, PythonVinaEngine)


def test_select_vina_engine_falls_back_to_executable():
    with patch.dict(sys.modules, {"vina": None}):
        with patch("shutil.which", return_value=r"C:\fake\vina.exe"):
            with patch("pathlib.Path.is_file", return_value=True):
                engine = select_vina_engine()
    assert isinstance(engine, ExecutableVinaEngine)


def test_select_vina_engine_returns_none_when_neither_available():
    with patch.dict(sys.modules, {"vina": None}):
        with patch("shutil.which", return_value=None):
            engine = select_vina_engine()
    assert engine is None
