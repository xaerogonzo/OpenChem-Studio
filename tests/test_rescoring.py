"""The rescoring axis: a SECOND score attached to a pose already found.

The invariants worth holding are mostly about what a rescore must NOT
touch, so most of what follows asserts the absence of an effect. The one
that would be easiest to lose is the last: a rescore's number must never
reach a ranking, because it is not on the docking affinity's scale.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from openchem.chem import rescoring
from openchem.chem.rescoring import SUPPORTED_RESCORE_FUNCTIONS, VinaPoseRescorer
from openchem.chem.vina_engine import (
    ExecutableVinaEngine,
    PythonVinaEngine,
    VinaEngine,
    parse_vina_score_output,
)
from openchem.domain.docking import (
    AS_DOCKED,
    POSE_SCORE_KEY,
    REFINE_THEN_SCORE,
    RESCORE_PROTOCOLS,
    DockingBox,
    DockingPoseModel,
    PoseScore,
    pose_score_of,
)
from openchem.plugins.interfaces import PoseRescorer, RescoreRequest

BOX = DockingBox(center=(1.0, 2.0, 3.0), size=(16.0, 16.0, 16.0))

# Vina 1.2.7's real --score_only stdout, trimmed of its citation banner.
# Copied from a run rather than composed, because the whole point of the
# parser is to read what Vina prints.
REAL_SCORE_ONLY_STDOUT = """
Scoring function : vinardo
Rigid receptor: r.pdbqt
Ligand: p.pdbqt
Grid center: X 2.0255 Y 15.9195 Z -58.7845
Grid size  : X 16 Y 17.795 Z 16.271
Grid space : 0.375
Exhaustiveness: 8
CPU: 0
Verbosity: 1

Computing Vinardo grid ... done.
Estimated Free Energy of Binding   : -5.468 (kcal/mol) [=(1)+(2)+(3)-(4)]
(1) Final Intermolecular Energy    : -7.386 (kcal/mol)
    Ligand - Receptor              : -7.386 (kcal/mol)
    Ligand - Flex side chains      : 0.000 (kcal/mol)
(2) Final Total Internal Energy    : -0.740 (kcal/mol)
    Ligand                         : -0.740 (kcal/mol)
    Flex   - Receptor              : 0.000 (kcal/mol)
    Flex   - Flex side chains      : 0.000 (kcal/mol)
(3) Torsional Free Energy          : 1.918 (kcal/mol)
(4) Unbound System's Energy        : -0.740 (kcal/mol)
"""


class _SpyEngine(VinaEngine):
    """Records the arguments `score_pose` is called with, and answers with
    a fixed number. The RECORDING is the point: a rescore labelled Vinardo
    that ran plain Vina is indistinguishable from the real thing in any
    stored result, so the guard has to read what reached the engine."""

    engine_id = "spy"

    def __init__(self, value: float = -5.468) -> None:
        self.calls: list[dict] = []
        self._value = value

    def is_available(self) -> bool:
        return True

    def version(self) -> str:
        return "1.2.7-spy"

    def dock(self, *args, **kwargs) -> str:  # pragma: no cover - unused here
        raise AssertionError("rescoring must not run a search")

    def score_pose(self, receptor_pdbqt, pose_pdbqt, box, scoring_function, refine=False):
        self.calls.append(
            {
                "receptor": receptor_pdbqt,
                "pose": pose_pdbqt,
                "scoring_function": scoring_function,
                "refine": refine,
            }
        )
        return self._value


def _request(tmp_path: Path, poses: int = 2) -> RescoreRequest:
    receptor = tmp_path / "receptor.pdbqt"
    receptor.write_text("RECEPTOR", encoding="utf-8")
    pose_paths = []
    for index in range(poses):
        path = tmp_path / f"pose_{index}.pdbqt"
        path.write_text(f"POSE {index}", encoding="utf-8")
        pose_paths.append(path)
    return RescoreRequest(
        receptor_pdbqt=receptor,
        pose_pdbqt_paths=tuple(pose_paths),
        box=BOX,
        receptor_structure_text="ATOM",
        receptor_source_format="pdb",
        receptor_prep_options={},
        pose_molblocks=tuple("molblock" for _ in range(poses)),
    )


# ---------------------------------------------------------------- parsing


def test_the_score_is_read_from_vinas_real_stdout():
    assert parse_vina_score_output(REAL_SCORE_ONLY_STDOUT) == pytest.approx(-5.468)


def test_a_run_that_printed_no_score_raises_rather_than_returning_zero():
    """A rescore that silently reports 0.0 is a plausible number attached to
    a real pose, which no table can tell from a measurement. The caller has
    a state for failure and this must reach it."""
    with pytest.raises(ValueError, match="no 'Estimated Free Energy"):
        parse_vina_score_output("Computing Vinardo grid ... done.\n")


def test_the_parser_never_reads_a_pdbqt_remark_line():
    """**THE FINDING THIS WHOLE PARSER EXISTS FOR.** `--local_only` writes an
    output PDBQT whose `REMARK VINA RESULT` is a passthrough of the INPUT
    pose's value -- measured identical (-8.758) for two scoring functions
    whose stdout answers were 3.2 kcal/mol apart. Parsing that file would
    yield a Vina number labelled Vinardo.

    So the parser must not match a REMARK line even when handed one.
    """
    remark = "REMARK VINA RESULT:    -8.758      0.000      0.000\n"
    with pytest.raises(ValueError):
        parse_vina_score_output(remark)


# ------------------------------------------------------- the requested run


def test_the_requested_function_reaches_the_engine(tmp_path):
    """Not merely the stored result. `docs/SOURCES.md`'s quiroga2016 entry
    demands this for docking and it applies identically here."""
    spy = _SpyEngine()
    scores = VinaPoseRescorer("vinardo", engine=spy).rescore(_request(tmp_path), AS_DOCKED)
    assert [call["scoring_function"] for call in spy.calls] == ["vinardo", "vinardo"]
    assert [score.function for score in scores] == ["vinardo", "vinardo"]


def test_the_protocol_reaches_the_engine_as_the_refine_flag(tmp_path):
    spy = _SpyEngine()
    VinaPoseRescorer("vinardo", engine=spy).rescore(_request(tmp_path, 1), AS_DOCKED)
    assert spy.calls[0]["refine"] is False

    spy = _SpyEngine()
    VinaPoseRescorer("vinardo", engine=spy).rescore(_request(tmp_path, 1), REFINE_THEN_SCORE)
    assert spy.calls[0]["refine"] is True


def test_the_stored_protocol_is_the_one_that_ran(tmp_path):
    """A substituted protocol makes the stored record a lie: the two answer
    different questions and one of them moves the pose."""
    for protocol in RESCORE_PROTOCOLS:
        scores = VinaPoseRescorer("vinardo", engine=_SpyEngine()).rescore(
            _request(tmp_path, 1), protocol
        )
        assert scores[0].protocol == protocol


def test_an_unknown_protocol_raises_rather_than_defaulting(tmp_path):
    with pytest.raises(ValueError, match="Unknown rescore protocol"):
        VinaPoseRescorer("vinardo", engine=_SpyEngine()).rescore(_request(tmp_path), "typo")


def test_an_unknown_function_is_refused_at_construction():
    with pytest.raises(ValueError, match="Unsupported rescoring function"):
        VinaPoseRescorer("dkoes_scoring")


def test_every_pose_gets_its_own_score_in_order(tmp_path):
    """One score per pose, positionally aligned with the poses given. The
    caller zips these against `result.poses`, so a dropped or reordered
    entry silently attaches one pose's number to another."""
    spy = _SpyEngine()
    request = _request(tmp_path, 3)
    scores = VinaPoseRescorer("vinardo", engine=spy).rescore(request, AS_DOCKED)
    assert len(scores) == 3
    # The engine saw the poses in the order the request listed them...
    assert [call["pose"] for call in spy.calls] == list(request.pose_pdbqt_paths)
    # ...and each returned score hashes the pose at its own index.
    import hashlib

    assert [score.pose_pdbqt_sha256 for score in scores] == [
        hashlib.sha256(path.read_bytes()).hexdigest() for path in request.pose_pdbqt_paths
    ]


# -------------------------------------------------------- the four states


def test_a_backend_that_cannot_score_is_INAPPLICABLE_not_a_fault(tmp_path):
    """A `VinaEngine` that never implemented `score_pose` is not a fault in
    this run or this molecule -- it is a property of the backend, so it
    renders neutral rather than red. This is the FAULT/INAPPLICABLE split
    `domain/common.py` already draws."""

    class _CannotScore(_SpyEngine):
        def score_pose(self, *args, **kwargs):
            raise NotImplementedError("no scoring here")

    scores = VinaPoseRescorer("vinardo", engine=_CannotScore()).rescore(
        _request(tmp_path, 1), AS_DOCKED
    )
    assert scores[0].value is None
    assert scores[0].inapplicable is True
    assert scores[0].error_summary == "Backend cannot rescore"


def test_a_real_failure_is_a_FAULT_and_carries_its_reason(tmp_path):
    class _Broken(_SpyEngine):
        def score_pose(self, *args, **kwargs):
            raise RuntimeError("The ligand is outside the grid box.")

    scores = VinaPoseRescorer("vinardo", engine=_Broken()).rescore(_request(tmp_path, 1), AS_DOCKED)
    assert scores[0].value is None
    assert scores[0].inapplicable is False
    assert "outside the grid box" in scores[0].error


def test_no_backend_at_all_still_returns_one_score_per_pose(tmp_path):
    """NOT an empty list. A caller that got fewer scores than poses would
    zip them silently against the wrong poses."""
    rescorer = VinaPoseRescorer("vinardo", executable_path_resolver=lambda: "")
    if rescorer.is_available():  # pragma: no cover - a machine with the binding
        pytest.skip("a Vina backend is available here, so this path is unreachable")
    scores = rescorer.rescore(_request(tmp_path, 3), AS_DOCKED)
    assert len(scores) == 3
    assert all(score.value is None and score.inapplicable for score in scores)


def test_a_failed_score_still_records_what_it_tried_to_score(tmp_path):
    """The hashes and the engine identity are what say WHICH receptor and
    pose the attempt was made against, and a failure is exactly when
    somebody will want to know."""

    class _Broken(_SpyEngine):
        def score_pose(self, *args, **kwargs):
            raise RuntimeError("nope")

    scores = VinaPoseRescorer("vinardo", engine=_Broken()).rescore(_request(tmp_path, 1), AS_DOCKED)
    assert scores[0].receptor_pdbqt_sha256
    assert scores[0].pose_pdbqt_sha256
    assert scores[0].engine == "spy"


# --------------------------------------------------------------- identity


def test_the_hashes_identify_the_files_that_were_scored(tmp_path):
    import hashlib

    request = _request(tmp_path, 2)
    scores = VinaPoseRescorer("vinardo", engine=_SpyEngine()).rescore(request, AS_DOCKED)
    expected_receptor = hashlib.sha256(request.receptor_pdbqt.read_bytes()).hexdigest()
    assert {score.receptor_pdbqt_sha256 for score in scores} == {expected_receptor}
    assert scores[0].pose_pdbqt_sha256 != scores[1].pose_pdbqt_sha256


def test_two_poses_of_one_run_share_one_receptor_hash(tmp_path):
    """The receptor is hashed ONCE per rescore, not once per pose -- work
    proportional to something the answer does not depend on."""
    scores = VinaPoseRescorer("vinardo", engine=_SpyEngine()).rescore(_request(tmp_path, 4), AS_DOCKED)
    assert len({score.receptor_pdbqt_sha256 for score in scores}) == 1


# ------------------------------------------------------ the domain object


def test_a_pose_score_round_trips_through_a_project_file():
    score = PoseScore(function="vinardo", protocol=AS_DOCKED, value=-5.47, engine="e")
    pose = DockingPoseModel("mb", -8.79, 0.0, 0.0, metadata={POSE_SCORE_KEY: score.to_dict()})
    back = pose_score_of(DockingPoseModel.from_dict(pose.to_dict()))
    assert back == score


def test_a_pose_with_no_rescore_reads_as_NOT_REQUESTED():
    assert pose_score_of(DockingPoseModel("mb", -8.79, 0.0, 0.0)) is None


def test_a_malformed_stored_rescore_does_not_make_the_result_unopenable():
    """A hand-edited project file must not take the docking affinity with
    it. Absent is the safe reading; the affinity beside it is unaffected."""
    pose = DockingPoseModel("mb", -8.79, 0.0, 0.0, metadata={POSE_SCORE_KEY: {"function": "x"}})
    assert pose_score_of(pose) is None
    assert pose.binding_affinity_kcal_mol == -8.79


def test_an_unknown_protocol_cannot_be_stored():
    with pytest.raises(ValueError):
        PoseScore(function="vinardo", protocol="whatever")


def test_a_pose_score_must_name_its_function():
    with pytest.raises(ValueError):
        PoseScore(function="", protocol=AS_DOCKED)


# ------------------------------------------------- what it must not touch


def test_the_python_engine_refuses_rather_than_guessing(tmp_path):
    """**A DELIBERATE REFUSAL, ASSERTED SO IT STAYS ONE.** The binding
    exposes `score()`, and writing this against it from memory would return
    a plausible number in the right units attached to a real pose -- the
    one failure mode nothing downstream can detect. It is implemented the
    day somebody can check it against the executable's answer."""
    with pytest.raises(NotImplementedError):
        PythonVinaEngine().score_pose(tmp_path, tmp_path, BOX, "vinardo")


def test_the_base_engine_refuses_so_an_older_engine_keeps_working(tmp_path):
    """`score_pose` is NOT abstract. An engine written before rescoring
    existed must still satisfy `VinaEngine`, and its refusal becomes a
    visible state rather than an import-time error."""

    class _Old(VinaEngine):
        engine_id = "old"

        def is_available(self):
            return True

        def version(self):
            return "0"

        def dock(self, *args, **kwargs):
            return ""

    assert isinstance(_Old(), VinaEngine)
    with pytest.raises(NotImplementedError):
        _Old().score_pose(tmp_path, tmp_path, BOX, "vina")


def test_the_executable_engine_never_asks_for_a_local_only_output_file():
    """Requesting `--out` on a `--local_only` run would produce a file whose
    REMARK carries the input pose's number. Not asking for it is what makes
    the wrong parser unreachable rather than merely unused."""
    source = inspect.getsource(ExecutableVinaEngine.score_pose)
    assert "--out" not in source


def test_no_rescoring_code_parses_a_pose_file_for_its_score():
    """The two parsers must not be confused. `parse_vina_output_pdbqt` reads
    a REMARK; nothing on the rescoring path may call it."""
    source = Path(rescoring.__file__).read_text(encoding="utf-8")
    assert "parse_vina_output_pdbqt" not in source


def test_the_rescorer_declares_the_surface_it_reaches():
    """`tests/test_calculator_reachability.py` walks every module; a
    user-facing one has to say what a user presses to reach it."""
    assert hasattr(rescoring, "USER_FACING_PROVIDER")
    assert rescoring.USER_FACING_PROVIDER.strip()


def test_vina_itself_is_offered_as_a_rescorer():
    """Not a redundant entry: rescoring the top pose with the function that
    produced it reproduces that pose's affinity, which is the acceptance
    test for the whole path."""
    assert "vina" in SUPPORTED_RESCORE_FUNCTIONS


def test_the_rescorer_implements_the_published_interface():
    assert issubclass(VinaPoseRescorer, PoseRescorer)
    assert not (set(PoseRescorer.__abstractmethods__) - set(dir(VinaPoseRescorer)))


def test_the_request_carries_the_originals_and_not_only_the_prepared_files():
    """The narrow half of the ABC's design. A request carrying only PDBQTs
    would make `PoseRescorer` a Vina-shaped hole: a rescorer from another
    family needs the structure text and the molblocks to build its own
    inputs, and there would be no way to give them to it."""
    fields = set(RescoreRequest.__dataclass_fields__)
    assert {"receptor_structure_text", "receptor_source_format", "pose_molblocks"} <= fields
    assert {"receptor_pdbqt", "pose_pdbqt_paths"} <= fields
