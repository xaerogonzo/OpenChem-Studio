from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from openchem.domain.docking import DockingBox
from openchem.services.progress import ProgressHandle

# Vina's own documented, stable output format: each pose is a MODEL...ENDMDL
# block containing a "REMARK VINA RESULT:  <affinity>  <rmsd_lb>  <rmsd_ub>"
# line. Confirmed against AutoDock Vina's manual/documentation; this format
# hasn't changed across Vina versions.
_RESULT_LINE_RE = re.compile(r"REMARK VINA RESULT:\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)")
_MODEL_BLOCK_RE = re.compile(r"^MODEL\s+\d+\s*\n(.*?)^ENDMDL", re.MULTILINE | re.DOTALL)

# What `--score_only` and `--local_only` print on STDOUT. Read off a real
# run of Vina 1.2.7 rather than recalled -- the line is
#
#     Estimated Free Energy of Binding   : -8.786 (kcal/mol) [=(1)+(2)+(3)-(4)]
#
# followed by a four-part breakdown this deliberately ignores: the total is
# the quantity, and parsing the parts would invite somebody to recombine
# them differently from Vina.
_SCORE_ONLY_RE = re.compile(r"Estimated Free Energy of Binding\s*:\s*(-?\d+(?:\.\d+)?)")


def parse_vina_score_output(text: str) -> float:
    """The affinity from a `--score_only` / `--local_only` run's STDOUT.

    **BOTH modes must be read from stdout, and `--local_only`'s output
    PDBQT must NOT be parsed with `parse_vina_output_pdbqt`.** That file
    looks like an ordinary pose file and its `REMARK VINA RESULT` is a
    passthrough of the INPUT pose's value, unchanged by the scoring
    function that was requested. Measured on one fentanyl pose in 5C1M:

        mode                              stdout    out-PDBQT REMARK
        --local_only --scoring vina       -8.717    -8.758
        --local_only --scoring vinardo    -5.477    -8.758

    -- identical REMARKs for two functions whose real answers are 3.2
    kcal/mol apart, and both equal to the input's own -8.758. Reading that
    file yields a VINA number labelled Vinardo, which is precisely the
    defect [source:quiroga2016]'s registry entry warns about ("a result
    LABELLED Vinardo that silently ran plain Vina is indistinguishable
    from the real thing in any table"), arriving by an unexpected route.

    Raises rather than returning a sentinel when nothing matches: a
    rescore that silently reports 0.0 is worse than one that is reported
    as failed, and the caller already has a state for failure.
    """
    match = _SCORE_ONLY_RE.search(text)
    if match is None:
        raise ValueError(
            "Vina reported no 'Estimated Free Energy of Binding' line; "
            "the run produced no score."
        )
    return float(match.group(1))


@dataclass(slots=True)
class RawPose:
    """One pose parsed out of Vina's output PDBQT, before conversion to a
    molblock (chem/docking_providers.py handles that conversion, via Open
    Babel, same as everywhere else a PDBQT needs to become RDKit-readable)."""

    pdbqt_text: str
    binding_affinity_kcal_mol: float
    rmsd_lb: float
    rmsd_ub: float


def parse_vina_output_pdbqt(text: str) -> list[RawPose]:
    """Shared by both `VinaEngine` implementations — the Python binding's
    `Vina.poses()` and the CLI executable's `--out` file both produce this
    exact MODEL/ENDMDL/REMARK VINA RESULT format, so there is exactly one
    parser, not one per engine.
    """
    poses = []
    for match in _MODEL_BLOCK_RE.finditer(text):
        block = match.group(1)
        result = _RESULT_LINE_RE.search(block)
        if result is None:
            continue
        affinity, rmsd_lb, rmsd_ub = (float(g) for g in result.groups())
        poses.append(
            RawPose(pdbqt_text=block, binding_affinity_kcal_mol=affinity, rmsd_lb=rmsd_lb, rmsd_ub=rmsd_ub)
        )
    if not poses:
        # Defensive fallback for a bare single-pose block with no MODEL
        # wrapper at all — not the normal case, but cheap to handle.
        result = _RESULT_LINE_RE.search(text)
        if result is not None:
            affinity, rmsd_lb, rmsd_ub = (float(g) for g in result.groups())
            poses.append(
                RawPose(pdbqt_text=text, binding_affinity_kcal_mol=affinity, rmsd_lb=rmsd_lb, rmsd_ub=rmsd_ub)
            )
    return poses


class VinaEngine(ABC):
    """How Vina's search/scoring actually gets invoked — deliberately
    separate from `DockingProvider` (plugins/interfaces.py), which is
    about *which docking algorithm* runs. This is about *how AutoDock
    Vina itself* runs: the `vina` PyPI package requires building from
    source against Boost + MSVC on Windows (no prebuilt wheel exists,
    confirmed directly attempting `uv sync --extra docking` on this
    machine), so a Windows user with only the official Vina executable
    installed should still get a working feature. `select_vina_engine()`
    below picks whichever is actually usable at runtime.
    """

    engine_id: str

    @abstractmethod
    def is_available(self) -> bool: ...

    @abstractmethod
    def version(self) -> str: ...

    @abstractmethod
    def dock(
        self,
        receptor_pdbqt: Path,
        ligand_pdbqt: Path,
        box: DockingBox,
        num_poses: int,
        exhaustiveness: int,
        seed: int | None,
        progress: ProgressHandle,
        scoring_function: str = "vina",
    ) -> str:
        """Returns Vina's own output-PDBQT text (pass to
        `parse_vina_output_pdbqt`), reporting phase-labeled progress.

        `scoring_function` selects among the models Vina 1.2.x ships. It
        defaults to "vina" so an engine written against the earlier signature
        keeps its behaviour, and it must reach the real invocation rather than
        only the stored result -- a silently ignored value produces affinities
        LABELLED with a function that never ran, which no table can tell from
        the real thing.
        """

    def score_pose(
        self,
        receptor_pdbqt: Path,
        pose_pdbqt: Path,
        box: DockingBox,
        scoring_function: str,
        refine: bool = False,
    ) -> float:
        """Score an ALREADY-PLACED pose, without searching.

        `refine=False` is `--score_only`: the number describes the pose
        exactly as given. `refine=True` is `--local_only`: a local
        minimisation under `scoring_function` FIRST, so the number
        describes a pose that has moved and the two are different
        experiments rather than two readings of one.

        **NOT abstract**, so an engine written before rescoring existed
        keeps working: the default refuses, and a refusal is a state the
        caller renders rather than a crash. This is the same additive
        shape `dock`'s `scoring_function` parameter already uses.

        `--score_only` needs the pose to be INSIDE the box -- it scores a
        ligand where it already is, and a freshly embedded one sits at the
        origin and is rejected with "The ligand is outside the grid box".
        Passing the search's own box is therefore the safe choice; Vina's
        `--autobox` was measured to give the identical number (-5.468 both
        ways on one fentanyl pose) but makes the box a second concept for
        no gain.
        """
        raise NotImplementedError(
            f"{type(self).__name__} cannot score a pose without searching."
        )


class PythonVinaEngine(VinaEngine):
    """Wraps the `vina` PyPI package's documented `Vina` class API
    (`set_receptor`/`set_ligand_from_file`/`compute_vina_maps`/`dock`/
    `poses`) — confirmed against the package's actual source (cached
    locally while resolving this dependency), not just its published
    docs, since the package can't be installed on this dev machine (see
    `VinaEngine`'s docstring). **Not exercised with a real import in this
    session** — this method-call sequence is verified-by-reading-source,
    not verified-by-running.
    """

    engine_id = "vina-python"

    def is_available(self) -> bool:
        try:
            import vina  # noqa: F401
        except ImportError:
            return False
        return True

    def version(self) -> str:
        import importlib.metadata

        try:
            return importlib.metadata.version("vina")
        except importlib.metadata.PackageNotFoundError:
            return "unknown"

    def dock(
        self,
        receptor_pdbqt: Path,
        ligand_pdbqt: Path,
        box: DockingBox,
        num_poses: int,
        exhaustiveness: int,
        seed: int | None,
        progress: ProgressHandle,
        scoring_function: str = "vina",
    ) -> str:
        import vina

        progress.report(0.1, "Preparing receptor")
        v = vina.Vina(sf_name=scoring_function, seed=seed if seed is not None else 0, verbosity=0)
        v.set_receptor(str(receptor_pdbqt))
        progress.report(0.3, "Preparing ligand")
        v.set_ligand_from_file(str(ligand_pdbqt))
        progress.report(0.4, "Generating grid")
        v.compute_vina_maps(center=list(box.center), box_size=list(box.size))
        progress.report(0.5, "Docking")
        v.dock(exhaustiveness=exhaustiveness, n_poses=num_poses)
        progress.report(0.9, "Scoring")
        return v.poses(n_poses=num_poses)

    def score_pose(
        self,
        receptor_pdbqt: Path,
        pose_pdbqt: Path,
        box: DockingBox,
        scoring_function: str,
        refine: bool = False,
    ) -> float:
        """**Deliberately refuses.** The binding exposes `score()` and
        `optimize()`, and writing this against them would take minutes --
        but neither has been RUN here (the `vina` package has no prebuilt
        Windows wheel, which is the whole reason this class's sibling
        exists), and `score()` returns an array of energy components whose
        ordering would be recalled rather than measured.

        A wrong index there returns a plausible number in the right units
        attached to a real pose, which is undetectable in any table. The
        refusal is visible instead: `VinaPoseRescorer` renders it as
        "unavailable", the docking result is untouched, and a configured
        executable still rescores.

        Implement it the moment a machine with the binding can check the
        answer against `ExecutableVinaEngine`'s on the same pose -- that
        comparison is the acceptance test, and it costs one run.
        """
        raise NotImplementedError(
            "The Vina Python binding's scoring path has not been verified against "
            "a real run; configure a Vina executable to rescore poses."
        )


class ExecutableVinaEngine(VinaEngine):
    """Shells out to the official AutoDock Vina command-line executable —
    a plain blocking `subprocess.run`, not `QProcess`: this already runs
    inside a `QThreadPool` worker thread via `DockingService`
    (chem/docking_providers.py's `VinaDockingProvider`), so a blocking
    call off the GUI thread is fine; `QProcess`'s GUI-thread requirement
    is specific to 6.5's ORCA design (a much longer-running job needing
    live cancellation), not a general rule.

    **Not exercised with a real Vina binary in this session** — this
    project does not download and execute third-party executables on the
    user's behalf; installing AutoDock Vina is the user's own action,
    same treatment as ORCA.
    """

    engine_id = "vina-executable"

    def __init__(self, executable_path: str | None = None) -> None:
        self._executable_path = executable_path or shutil.which("vina") or shutil.which("vina.exe")

    def is_available(self) -> bool:
        return bool(self._executable_path) and Path(self._executable_path).is_file()

    def version(self) -> str:
        if not self.is_available():
            return "unknown"
        try:
            result = subprocess.run(
                [self._executable_path, "--version"], capture_output=True, text=True, timeout=10
            )
        except (OSError, subprocess.SubprocessError):
            return "unknown"
        return result.stdout.strip() or result.stderr.strip() or "unknown"

    def dock(
        self,
        receptor_pdbqt: Path,
        ligand_pdbqt: Path,
        box: DockingBox,
        num_poses: int,
        exhaustiveness: int,
        seed: int | None,
        progress: ProgressHandle,
        scoring_function: str = "vina",
    ) -> str:
        if not self.is_available():
            raise RuntimeError("No Vina executable configured or found on PATH.")

        progress.report(0.1, "Preparing receptor")
        with tempfile.TemporaryDirectory() as scratch_dir:
            out_path = Path(scratch_dir) / "out.pdbqt"
            args = [
                self._executable_path,
                "--receptor",
                str(receptor_pdbqt),
                "--ligand",
                str(ligand_pdbqt),
                "--center_x",
                str(box.center[0]),
                "--center_y",
                str(box.center[1]),
                "--center_z",
                str(box.center[2]),
                "--size_x",
                str(box.size[0]),
                "--size_y",
                str(box.size[1]),
                "--size_z",
                str(box.size[2]),
                "--num_modes",
                str(num_poses),
                "--exhaustiveness",
                str(exhaustiveness),
                "--out",
                str(out_path),
            ]
            if seed is not None:
                args += ["--seed", str(seed)]
            # Emitted only when it differs from Vina's own default, so the
            # command line for an ordinary run is byte-identical to before.
            if scoring_function and scoring_function != "vina":
                args += ["--scoring", scoring_function]

            progress.report(0.3, "Preparing ligand")
            progress.report(0.5, "Docking")
            subprocess.run(args, capture_output=True, text=True, check=True)
            progress.report(0.9, "Scoring")
            return out_path.read_text(encoding="utf-8")

    def score_pose(
        self,
        receptor_pdbqt: Path,
        pose_pdbqt: Path,
        box: DockingBox,
        scoring_function: str,
        refine: bool = False,
    ) -> float:
        if not self.is_available():
            raise RuntimeError("No Vina executable configured or found on PATH.")

        args = [
            self._executable_path,
            "--receptor",
            str(receptor_pdbqt),
            "--ligand",
            str(pose_pdbqt),
            "--center_x",
            str(box.center[0]),
            "--center_y",
            str(box.center[1]),
            "--center_z",
            str(box.center[2]),
            "--size_x",
            str(box.size[0]),
            "--size_y",
            str(box.size[1]),
            "--size_z",
            str(box.size[2]),
            "--local_only" if refine else "--score_only",
        ]
        # Emitted only when it differs from Vina's own default, matching
        # `dock` -- so an ordinary vina-scale rescore produces a command
        # line with no --scoring on it at all.
        if scoring_function and scoring_function != "vina":
            args += ["--scoring", scoring_function]

        # `--local_only` writes an output PDBQT when asked; it is
        # deliberately NOT requested, because that file's REMARK carries
        # the input pose's number rather than this function's. See
        # `parse_vina_score_output`. The refined COORDINATES are not kept
        # either: the pose the viewer draws stays the docked one, so a
        # refined pose would be geometry nothing displays.
        done = subprocess.run(args, capture_output=True, text=True)
        if done.returncode != 0:
            # Vina writes its real complaint to STDERR and says nothing
            # useful on stdout, so `check=True` would raise a
            # CalledProcessError naming only the exit status and the
            # argv -- which is how "the ligand is outside the grid box"
            # reads as "rescoring failed" with no way to act on it.
            raise RuntimeError(
                (done.stderr or done.stdout or "no output").strip().splitlines()[-1]
                if (done.stderr or done.stdout).strip()
                else f"Vina exited {done.returncode} with no output."
            )
        return parse_vina_score_output(done.stdout)


def select_vina_engine(executable_path: str | None = None) -> VinaEngine | None:
    """Prefers the Python binding (no subprocess, no scratch files needed)
    when it's actually importable; falls back to a configured/found
    executable; `None` if neither is usable — callers must handle that
    explicitly (`VinaDockingProvider` raises a clear error), not silently
    do nothing.
    """
    python_engine = PythonVinaEngine()
    if python_engine.is_available():
        return python_engine
    executable_engine = ExecutableVinaEngine(executable_path)
    if executable_engine.is_available():
        return executable_engine
    return None
