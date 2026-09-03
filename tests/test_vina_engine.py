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


# --- score_pose: the argv is the thing ---------------------------------------

_SCORE_ONLY_STDOUT = (
    "Computing Vinardo grid ... done.\n"
    "Estimated Free Energy of Binding   : -5.468 (kcal/mol) [=(1)+(2)+(3)-(4)]\n"
    "(1) Final Intermolecular Energy    : -7.386 (kcal/mol)\n"
)


def _score_engine(tmp_path):
    exe_path = tmp_path / "vina.exe"
    exe_path.write_text("")
    return ExecutableVinaEngine(executable_path=str(exe_path)), exe_path


def _score_argv(tmp_path, scoring_function, refine=False):
    engine, exe_path = _score_engine(tmp_path)
    box = DockingBox(center=(1.0, 2.0, 3.0), size=(16.0, 16.0, 16.0))
    with patch(
        "subprocess.run",
        return_value=MagicMock(returncode=0, stdout=_SCORE_ONLY_STDOUT, stderr=""),
    ) as mock_run:
        value = engine.score_pose(
            tmp_path / "receptor.pdbqt", tmp_path / "pose.pdbqt", box,
            scoring_function, refine=refine,
        )
    return mock_run.call_args[0][0], value


def test_the_requested_scoring_function_reaches_the_COMMAND_LINE(tmp_path):
    """**THIS GUARD EXISTS BECAUSE ITS ABSENCE SURVIVED A MUTATION.**

    `tests/test_rescoring.py` already asserts the function reaches "the
    engine" -- through a SPY engine, which is the rescorer's wiring and not
    this one's. Deleting `--scoring` from the argv here left that test
    green, and the result is a score LABELLED Vinardo that ran plain Vina,
    which `docs/SOURCES.md`'s quiroga2016 entry names as indistinguishable
    from the real thing in any table. Testing a helper is not testing the
    wiring.
    """
    args, _ = _score_argv(tmp_path, "vinardo")
    assert "--scoring" in args
    assert args[args.index("--scoring") + 1] == "vinardo"


def test_vina_is_left_off_the_command_line_because_it_is_vinas_own_default(tmp_path):
    """The narrow half. "Always emit --scoring" satisfies the guard above and
    changes the argv of every ordinary run; the shipped rule matches `dock`'s,
    which omits it at the default."""
    args, _ = _score_argv(tmp_path, "vina")
    assert "--scoring" not in args


def test_score_only_and_local_only_are_the_two_protocols_on_the_argv(tmp_path):
    as_docked, _ = _score_argv(tmp_path, "vinardo", refine=False)
    assert "--score_only" in as_docked and "--local_only" not in as_docked

    refined, _ = _score_argv(tmp_path, "vinardo", refine=True)
    assert "--local_only" in refined and "--score_only" not in refined


def test_no_output_file_is_ever_requested_for_a_scored_pose(tmp_path):
    """`--local_only` will write one, and its REMARK carries the INPUT
    pose's number rather than the requested function's. Not asking for it is
    what keeps the wrong parser unreachable."""
    for refine in (False, True):
        args, _ = _score_argv(tmp_path, "vinardo", refine=refine)
        assert "--out" not in args


def test_the_box_reaches_the_command_line(tmp_path):
    """--score_only scores a ligand where it already is and refuses one
    outside the box, so the box is not optional decoration here."""
    args, _ = _score_argv(tmp_path, "vinardo")
    for flag in ("--center_x", "--center_y", "--center_z", "--size_x", "--size_y", "--size_z"):
        assert flag in args


def test_the_score_comes_back_parsed_from_stdout(tmp_path):
    _, value = _score_argv(tmp_path, "vinardo")
    assert value == pytest.approx(-5.468)


def test_a_failing_vina_reports_its_own_message_not_an_exit_status(tmp_path):
    """`check=True` would raise a CalledProcessError naming only the exit
    status and the argv, which is how "PDBQT parsing error: Unexpected
    multi-MODEL tag" reads as "rescoring failed" with nothing to act on --
    measured, that message cost a debugging round until it was surfaced."""
    engine, _ = _score_engine(tmp_path)
    box = DockingBox(center=(1.0, 2.0, 3.0), size=(16.0, 16.0, 16.0))
    with patch(
        "subprocess.run",
        return_value=MagicMock(
            returncode=1, stdout="", stderr="PDBQT parsing error: Unexpected multi-MODEL tag found."
        ),
    ):
        with pytest.raises(RuntimeError, match="multi-MODEL"):
            engine.score_pose(
                tmp_path / "r.pdbqt", tmp_path / "p.pdbqt", box, "vinardo"
            )


def test_score_pose_without_an_executable_refuses(tmp_path):
    engine = ExecutableVinaEngine(executable_path=None)
    box = DockingBox(center=(1.0, 2.0, 3.0), size=(16.0, 16.0, 16.0))
    with patch("shutil.which", return_value=None):
        with pytest.raises(RuntimeError, match="No Vina executable"):
            ExecutableVinaEngine(executable_path=None).score_pose(
                tmp_path / "r.pdbqt", tmp_path / "p.pdbqt", box, "vinardo"
            )
