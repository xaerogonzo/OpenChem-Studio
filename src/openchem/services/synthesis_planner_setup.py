"""Where the synthesis planner is and whether it works: the External Tools tab's side of AiZynthFinder, and the setting the planning service reads (`docs/SYNTHESIS_HELPER_DESIGN.md`, Stage 1 slice 7).

LOCATE-ONLY, AS DECIDED (Alex, 2026-10-19): OpenChem never downloads, installs or removes the planner. The user installs AiZynthFinder in an environment of their own (Python 3.10 to 3.12, `numpy<2`, and `pyarrow<21`, without which a fresh install does not import: measured, `docs/SYNTHESIS_HELPER_DESIGN.md` 0b), runs its `download_public_data`, and tells this application two things: the environment's Python and the configuration file that command wrote.

THE STATUS LINE STARTS NOTHING, like ORCA's and Psi4's: it reads two paths and says what is missing. WHAT IS WRONG INSIDE THE ENVIRONMENT IS FOUND BY TEST, which runs the planner for real, in order, and stops at the first thing it can name:

  1. no Python set, or none at the path                    -> "not configured" / "Python not found"
  2. no configuration file set, or none at the path        -> the same, for the file
  3. the Python does not start, or has no aizynthfinder    -> names the Python and says what to install
  4. the configuration does not read                       -> the library's YAML reader or the file is at fault
  5. the policy model, its template file, the filter model, or the stock is not where the configuration says -> that file, by name (each checked separately)
  6. a trivial search (aspirin, 20 iterations) is run for real -> the child's own last words if it fails

so a person is told "the stock file is missing: D:\\...\\zinc_stock.hdf5" and not "failed".

WHAT IS CHOSEN FROM THE CONFIGURATION: the expansion policy (`uspto` if it has one, else the first), the stock (`zinc` if it has one, else the first) and NO FILTER, the configuration the published benchmark numbers describe and the one the quality benchmark ran. Each can be set (`aizynthfinder/expansion`, `/stock`, `/filter`; "none" for no filter); a name the configuration does not have is a problem, not a silent fallback. The search limits are the benchmark's (500 iterations, a 1,800 s safety net, `max_transforms` 10) until a setting for them is a decision.

THE CONFIGURATION IS READ BY THE PLANNER'S OWN PYTHON (OpenChem has no YAML reader and the environment always has one), once per file as it stands (path, modification time, size), and the result is kept, so asking for a plan does not start a program to read a file it has already read.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from openchem.chem.aizynth_planner import PlannerInspection, PlannerSetup, inspect_environment, run_planner
from openchem.domain.synthesis_route import RouteStatus, SearchLimits, TargetIdentity
from openchem.services.tool_download_service import ToolVerificationError

#: The setting the External Tools tab writes and the planning service reads: the Python of the environment AiZynthFinder is installed in.
PYTHON_KEY = "aizynthfinder/python_path"
#: The setting for the configuration file `download_public_data` wrote.
CONFIG_KEY = "aizynthfinder/config_path"
#: Which expansion policy of the configuration to use (blank: `uspto` if it has one, else the first).
EXPANSION_KEY = "aizynthfinder/expansion"
#: Which stock of the configuration to use (blank: `zinc` if it has one, else the first).
STOCK_KEY = "aizynthfinder/stock"
#: Which filter policy to use (blank or "none": no filter, the configuration the published numbers describe).
FILTER_KEY = "aizynthfinder/filter"

#: Where a person gets the planner.
PROJECT_PAGE = "https://github.com/MolecularAI/aizynthfinder"
#: Its documentation, including how to install it and what `download_public_data` fetches.
DOCS_PAGE = "https://molecularai.github.io/aizynthfinder/"

#: The limits a plan is run with: the quality benchmark's (`benchmarks/synthesis/PREREGISTRATION.md`), measured at a median 54 s of search per target.
DEFAULT_LIMITS = SearchLimits(iteration_limit=500, time_limit_seconds=1800.0, max_transforms=10)
#: The test's trivial search: aspirin, a few iterations. It checks that the environment, the models and the stock load and answer, not what the answer is.
TEST_TARGET = "CC(=O)Oc1ccccc1C(=O)O"
#: Its limits: 20 iterations, with a generous time limit as a safety net.
TEST_LIMITS = SearchLimits(iteration_limit=20, time_limit_seconds=300.0, max_transforms=6)
#: The expansion policy preferred when the configuration has one of that name.
PREFERRED_EXPANSION = "uspto"
#: The stock preferred when the configuration has one of that name.
PREFERRED_STOCK = "zinc"
#: What a person writes in the filter setting for "no filter".
NO_FILTER = "none"
#: What an install that fails to import because of its pyarrow looks like (measured 2026-10-19), and what fixes it.
_PYARROW_HINT = " A fresh install of aizynthfinder needs pyarrow below version 21 (pip install \"pyarrow<21\" in that environment): newer ones need NumPy 2, which aizynthfinder does not support."


# --- the status line, which starts nothing -----------------------------------------------------------------------------------------------


def describe_status(python: str, config: str) -> str:
    """One line from two paths. It runs nothing: a visit to the tab starts no program (the Test button's job)."""
    if not python:
        return "Not configured: set the Python of the environment AiZynthFinder is installed in"
    if not Path(python).is_file():
        return f"Python not found at {python}"
    if not config:
        return f"Python set ({Path(python).parent}); now set the configuration file (config.yml from download_public_data)"
    if not Path(config).is_file():
        return f"Configuration file not found at {config}"
    return f"Configured: {Path(python).parent} with {Path(config).name} (use Test to check that it works)"


# --- finding it -----------------------------------------------------------------------------------------------------------------------------


#: What `importlib.metadata.version` prints for an environment that has the planner: a bare version number.
_VERSION_RE = re.compile(r"^\s*(\d+\.\d+(?:\.\d+)*)\s*$")


def responds_as_planner(python: Path | str) -> bool:
    """Whether this Python has aizynthfinder, asked by running it (`importlib.metadata`, so the library is not loaded: 0.1 s). A name match on `python.exe` proves nothing."""
    try:
        done = subprocess.run([str(python), "-I", "-c", "import importlib.metadata as m; print(m.version('aizynthfinder'))"], capture_output=True, text=True, timeout=30, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return False
    return done.returncode == 0 and _VERSION_RE.match(done.stdout or "") is not None


def _python_in(folder: Path) -> Path | None:
    for relative in ("python.exe", "Scripts/python.exe", ".venv/Scripts/python.exe", "env/Scripts/python.exe", "venv/Scripts/python.exe", "bin/python", ".venv/bin/python", "env/bin/python", "venv/bin/python"):
        candidate = folder / relative
        if candidate.is_file():
            return candidate
    return None


def find_python(root: Path) -> Path | None:
    """`PathRow`'s finder for the Python: the interpreter inside a folder the user picked (the environment, or a folder above it). Only a Python that has aizynthfinder is accepted."""
    root = Path(root)
    candidate = _python_in(root)
    return candidate if candidate is not None and responds_as_planner(candidate) else None


def find_config(root: Path) -> Path | None:
    """`PathRow`'s finder for the configuration: the `config.yml` (or `.yaml`) in the folder the user picked, or in a `data` folder beside or below it."""
    root = Path(root)
    for folder in (root, root / "data"):
        for name in ("config.yml", "config.yaml"):
            candidate = folder / name
            if candidate.is_file():
                return candidate
    return None


def locate() -> Path | None:
    """Find an environment of the planner already on this machine: `aizynthcli` (installed beside the Python of its environment) on the PATH, and its Python, checked by asking it."""
    found = shutil.which("aizynthcli")
    if found is None:
        return None
    candidate = _python_in(Path(found).parent) or _python_in(Path(found).parent.parent)
    return candidate if candidate is not None and responds_as_planner(candidate) else None


# --- what is chosen from the configuration -----------------------------------------------------------------------------------------------


def select_keys(inspection: PlannerInspection, settings) -> tuple[str | None, str | None, str | None, str]:
    """`(expansion, stock, filter, problem)`: the names to use, from the settings or the defaults, and why not if a chosen one is not in the configuration. A filter of None is no filter."""
    keys = inspection.keys

    def pick(section: str, setting_key: str, preferred: str | None) -> tuple[str | None, str]:
        names = list(keys.get(section, ()))
        wanted = (settings.get(setting_key, "") or "").strip()
        if wanted:
            return (wanted, "") if wanted in names else (None, f"the configuration has no {section} named {wanted!r} (it has: {', '.join(names) or 'none'})")
        if not names:
            return None, f"the configuration has no {section} section"
        return (preferred if preferred in names else names[0]), ""

    expansion, problem = pick("expansion", EXPANSION_KEY, PREFERRED_EXPANSION)
    if problem:
        return None, None, None, problem
    stock, problem = pick("stock", STOCK_KEY, PREFERRED_STOCK)
    if problem:
        return None, None, None, problem
    wanted_filter = (settings.get(FILTER_KEY, "") or "").strip()
    if not wanted_filter or wanted_filter.lower() == NO_FILTER:
        return expansion, stock, None, ""
    if wanted_filter not in keys.get("filter", ()):
        return None, None, None, f"the configuration has no filter named {wanted_filter!r} (it has: {', '.join(keys.get('filter', ())) or 'none'})"
    return expansion, stock, wanted_filter, ""


def assets_problem(inspection: PlannerInspection, expansion: str, stock: str, filter_name: str | None) -> tuple[str, str] | None:
    """The first named file the selection needs that is not there, as `(kind, reason)`: each of the policy model, its template file, the filter model and the stock is checked on its own."""
    config = inspection.config
    entry = (config.get("expansion") or {}).get(expansion)
    if not isinstance(entry, list) or len(entry) < 2:
        return "config", f"the expansion policy {expansion!r} does not list a model and a template file"
    if not Path(str(entry[0])).is_file():
        return "model", f"the expansion policy model file is not there: {entry[0]}"
    if not Path(str(entry[1])).is_file():
        return "templates", f"the expansion policy template file is not there: {entry[1]}"
    if filter_name:
        value = (config.get("filter") or {}).get(filter_name)
        value = value[0] if isinstance(value, list) and value else value
        if not isinstance(value, str) or not Path(value).is_file():
            return "filter", f"the filter policy model file is not there: {value}"
    stock_file = (config.get("stock") or {}).get(stock)
    if not isinstance(stock_file, str):
        return "stock", f"the stock {stock!r} is not a file this application can check"
    if not Path(stock_file).is_file():
        return "stock", f"the stock file is not there: {stock_file}"
    return None


# --- the Test button ----------------------------------------------------------------------------------------------------------------------


#: What to do about each kind of failed inspection that has an action of its own (`planner` has its own sentence).
_INSPECT_ADVICE = {
    "python": "Check the Python path.",
    "runner": "Reinstall OpenChem Studio.",
    "yaml": "Reinstall aizynthfinder in that environment.",
    "timeout": "Try again; if it keeps happening the environment may be damaged.",
}


def explain_inspection(inspection: PlannerInspection, python: str) -> str:
    """A sentence a person can act on for each way reading the configuration can fail."""
    if inspection.kind == "planner":
        return f"AiZynthFinder is not installed in {python}. Install it in that environment (pip install aizynthfinder \"pyarrow<21\") and run download_public_data, or point this at the Python of the environment where it is installed."
    advice = _INSPECT_ADVICE.get(inspection.kind, "")
    reason = inspection.reason.rstrip()
    if advice and not reason.endswith("."):
        reason += "."  # the reason is a clause from the host; the advice is its own sentence
    return f"{reason}{(' ' + advice) if advice else ''}"


def verify(python: str, config: str, settings=None, *, inspector=inspect_environment, runner=run_planner) -> str:
    """Check the planner in the order the module docstring gives, running a trivial search for real, or raise `ToolVerificationError` naming the first thing wrong."""
    if not python:
        raise ToolVerificationError("Set the Python of the environment AiZynthFinder is installed in first.")
    if not Path(python).is_file():
        raise ToolVerificationError(f"No Python at {python}.")
    if not config:
        raise ToolVerificationError("Set the configuration file (config.yml, written by download_public_data) first.")
    if not Path(config).is_file():
        raise ToolVerificationError(f"No configuration file at {config}.")
    inspection = inspector(python, config)
    if not inspection.ok:
        raise ToolVerificationError(explain_inspection(inspection, python))
    expansion, stock, filter_name, problem = select_keys(inspection, settings if settings is not None else _Defaults())
    if problem:
        raise ToolVerificationError(problem.capitalize() + ".")
    missing = assets_problem(inspection, expansion, stock, filter_name)
    if missing is not None:
        raise ToolVerificationError(f"{missing[1][:1].upper()}{missing[1][1:]}.")
    setup = PlannerSetup(python=python, config=inspection.config, stock=stock, expansion=expansion, filter=filter_name, limits=TEST_LIMITS)
    target = TargetIdentity(molecule_uuid="external-tools-test", canonical_smiles=TEST_TARGET, fingerprint="test")
    began = time.monotonic()
    result = runner(setup.request_for(TEST_TARGET), target, python=python)
    seconds = time.monotonic() - began
    if result.status in (RouteStatus.UNAVAILABLE, RouteStatus.FAILED, RouteStatus.CANCELLED):
        hint = _PYARROW_HINT if ("pyarrow" in result.reason and "NumPy" in result.reason) else ""
        raise ToolVerificationError(f"{result.reason}{hint}")
    found = f"{len(result.routes)} route{'s' if len(result.routes) != 1 else ''}" if result.routes else "no route"
    return f"{result.planner.label()} answered a trivial search (aspirin, {TEST_LIMITS.iteration_limit} iterations, {seconds:.0f} s): {found} within it. Expansion {expansion}, stock {stock}, {'no filter' if not filter_name else 'filter ' + filter_name}."


class _Defaults:
    """Settings stand-in that holds nothing, so every choice falls to its default."""

    def get(self, key: str, default=""):
        return default


@dataclass(frozen=True)
class PlannerOptions:
    """What the configuration offers and what is chosen, for the synthesis panel's three lists.

    `ok` is False when no plan can be made as things stand, and `problem` says why in a sentence (the External Tools tab's Test is what finds the cause inside the environment).
    A chosen name of None means none: `chosen_filter` None is no filter, the default.
    """

    ok: bool
    problem: str = ""
    version: str | None = None
    expansion: tuple[str, ...] = ()
    stock: tuple[str, ...] = ()
    filters: tuple[str, ...] = ()
    chosen_expansion: str | None = None
    chosen_stock: str | None = None
    chosen_filter: str | None = None


# --- the setting the planning service reads ------------------------------------------------------------------------------------------------


class SetupProvider:
    """`SynthesisPlanningService`'s `setup_provider`: the planner as the settings describe it now, or None.

    None means "not set up" (either path missing, the environment not answering, the selection not in the configuration, a named file not there) and the service
    reports every request as `unavailable`; the Test button says which. The configuration is read by the planner's own Python once per file as it stands
    (path, modification time, size) and kept.
    """

    def __init__(self, settings, *, inspector=inspect_environment) -> None:
        self._settings = settings
        self._inspector = inspector
        self._cache: tuple[tuple, PlannerInspection] | None = None
        self._lock = threading.Lock()

    def __call__(self) -> PlannerSetup | None:
        python, config = self._paths()
        if not python or not config or not Path(python).is_file() or not Path(config).is_file():
            return None
        inspection = self._inspection(python, config)
        if inspection is None or not inspection.ok:
            return None
        expansion, stock, filter_name, problem = select_keys(inspection, self._settings)
        if problem or assets_problem(inspection, expansion, stock, filter_name) is not None:
            return None
        return PlannerSetup(python=python, config=inspection.config, stock=stock, expansion=expansion, filter=filter_name, limits=DEFAULT_LIMITS)

    def is_warm(self) -> bool:
        """True when the configuration at the paths now set has already been read, so a request will not wait for it. Starts nothing."""
        python, config = self._paths()
        key = self._key(python, config) if python and config else None
        with self._lock:
            return key is not None and self._cache is not None and self._cache[0] == key

    def options(self) -> PlannerOptions:
        """What the configuration offers and what is chosen now, for the panel's three lists. May start the planner's Python (about 1.6 s the first time), so call it from a worker."""
        python, config = self._paths()
        if not python or not config or not Path(python).is_file() or not Path(config).is_file():
            return PlannerOptions(ok=False, problem=describe_status(python, config))
        inspection = self._inspection(python, config)
        if inspection is None:
            return PlannerOptions(ok=False, problem=f"The planner's Python or configuration could not be read ({python}).")
        if not inspection.ok:
            return PlannerOptions(ok=False, problem=explain_inspection(inspection, python))
        keys = inspection.keys
        expansion, stock, filter_name, problem = select_keys(inspection, self._settings)
        if not problem:
            missing = assets_problem(inspection, expansion, stock, filter_name)
            problem = "" if missing is None else missing[1]
        if problem:
            problem = f"{problem[:1].upper()}{problem[1:]}."
        return PlannerOptions(
            ok=not problem,
            problem=problem,
            version=inspection.version,
            expansion=tuple(keys.get("expansion", ())),
            stock=tuple(keys.get("stock", ())),
            filters=tuple(keys.get("filter", ())),
            chosen_expansion=expansion,
            chosen_stock=stock,
            chosen_filter=filter_name,
        )

    def _paths(self) -> tuple[str, str]:
        return (self._settings.get(PYTHON_KEY, "") or "").strip(), (self._settings.get(CONFIG_KEY, "") or "").strip()

    @staticmethod
    def _key(python: str, config: str) -> tuple | None:
        try:
            stat = Path(config).stat()
            python_stat = Path(python).stat()
        except OSError:
            return None
        return (python, config, stat.st_mtime_ns, stat.st_size, python_stat.st_mtime_ns)

    def _inspection(self, python: str, config: str) -> PlannerInspection | None:
        key = self._key(python, config)
        if key is None:
            return None
        with self._lock:
            if self._cache is not None and self._cache[0] == key:
                return self._cache[1]
        inspection = self._inspector(python, config)
        if inspection.ok:  # a failure is not kept: fixing the environment should not need a restart
            with self._lock:
                self._cache = (key, inspection)
        return inspection


__all__ = ["CONFIG_KEY", "DEFAULT_LIMITS", "EXPANSION_KEY", "FILTER_KEY", "PYTHON_KEY", "STOCK_KEY", "PlannerOptions", "SetupProvider", "assets_problem", "describe_status", "find_config", "find_python", "locate", "responds_as_planner", "select_keys", "verify"]
