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
    ) -> str:
        """Returns Vina's own output-PDBQT text (pass to
        `parse_vina_output_pdbqt`), reporting phase-labeled progress."""


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
    ) -> str:
        import vina

        progress.report(0.1, "Preparing receptor")
        v = vina.Vina(sf_name="vina", seed=seed if seed is not None else 0, verbosity=0)
        v.set_receptor(str(receptor_pdbqt))
        progress.report(0.3, "Preparing ligand")
        v.set_ligand_from_file(str(ligand_pdbqt))
        progress.report(0.4, "Generating grid")
        v.compute_vina_maps(center=list(box.center), box_size=list(box.size))
        progress.report(0.5, "Docking")
        v.dock(exhaustiveness=exhaustiveness, n_poses=num_poses)
        progress.report(0.9, "Scoring")
        return v.poses(n_poses=num_poses)


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

            progress.report(0.3, "Preparing ligand")
            progress.report(0.5, "Docking")
            subprocess.run(args, capture_output=True, text=True, check=True)
            progress.report(0.9, "Scoring")
            return out_path.read_text(encoding="utf-8")


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
