from __future__ import annotations

import json
import logging
import platform
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.error import URLError
from openchem.net import open_url


from openchem.chem.vina_engine import select_vina_engine
from openchem import paths as app_paths

logger = logging.getLogger("openchem.tools")

# Public GitHub Releases API -- no auth needed for a public repo. AutoDock
# Vina's releases are Apache-2.0-licensed executables published directly by
# the Scripps Research Institute's own team, unlike ORCA (registration/EULA
# gated, no public direct-download URL -- see ExternalToolsPages).
VINA_RELEASES_API = "https://api.github.com/repos/ccsb-scripps/AutoDock-Vina/releases/latest"
VINA_RELEASES_PAGE = "https://github.com/ccsb-scripps/AutoDock-Vina/releases"

# ORCA's distribution moved from the Max Planck-hosted orcaforum (its old
# /app.php/portal download link now 404s) to FACCTS GmbH, ORCA's commercial
# steward -- confirmed against faccts.de's own site, which points to this
# exact URL as "Downloads (for registered users)". A free account is
# required; there is no public direct-download URL, so this can only ever
# be a link, never an automated fetch (see ExternalToolsPages).
ORCA_DOWNLOAD_PAGE = "https://www.faccts.de/customer"
ORCA_DOCS_PAGE = "https://www.faccts.de/docs"

_SKIP_SUFFIXES = (".txt", ".sha256sum", ".sha256", ".asc", ".sig", ".md5")


@dataclass(slots=True)
class VinaReleaseAsset:
    """One downloadable asset from AutoDock Vina's latest GitHub release.

    Surfaced to the user (name/url/size/version) for explicit confirmation
    in ExternalToolsPages before `download_vina_asset` is ever called --
    this dataclass itself performs no network I/O.
    """

    version: str
    name: str
    download_url: str
    size_bytes: int


def describe_vina_status(configured_path: str) -> str:
    """One-line human-readable status for ExternalToolsPages -- "Found:
    vina-executable 1.2.7" or "Not found". Kept in the services layer
    (rather than the dialog calling `select_vina_engine` itself) so the UI
    layer's dependency surface stays consistent with the rest of the
    codebase's chem/ui separation, even though `chem.vina_engine` itself
    imports neither RDKit nor Open Babel.
    """
    engine = select_vina_engine(configured_path or None)
    if engine is None:
        return "Not found"
    return f"Found: {engine.engine_id} {engine.version()}"


#: What ORCA prints when run with no input file. Used to tell the real
#: program from something else of the same name -- "ORCA" is a genuinely
#: generic name and this app already warns about the confusion elsewhere.
#: Measured against ORCA 6.1.1: exit code 0, this text on stdout.
_ORCA_NO_INPUT_MARKER = "requires the name of a parameterfile"

#: A hydrogen molecule at HF/STO-3G -- the smallest job that still proves
#: ORCA can run one. Measured at **2.9 s** end to end on ORCA 6.1.1,
#: which is what makes a Test button viable at all; anything needing a
#: real basis set would take long enough that nobody would press it.
_ORCA_TEST_INPUT = "! HF STO-3G\n* xyz 0 1\nH 0 0 0\nH 0 0 0.74\n*\n"

#: The reference energy for that job, in Hartree. Checked rather than
#: merely "did it print a number": a build that runs and computes the
#: wrong answer is the failure worth catching, and it is the one a
#: file-exists check cannot see.
_ORCA_TEST_ENERGY = -1.116759
_ORCA_TEST_TOLERANCE = 1e-4


def describe_orca_status(configured_path: str) -> str:
    """One-line status for the ORCA tab, mirroring `describe_vina_status`.

    **Deliberately does NOT run ORCA.** A status line is read on every
    visit to the tab and ORCA has no `--version` flag -- it wants an input
    file, so the cheapest real check is a whole calculation. That belongs
    behind the Test button, which the user presses on purpose; see
    `verify_orca`.
    """
    if not configured_path:
        return "Not configured"
    path = Path(configured_path)
    if not path.is_file():
        return f"Configured, but no file at {path}"
    return f"Configured: {path.name} in {path.parent}"


def verify_orca(configured_path: str) -> str:
    """Run a real calculation and report the version, or raise.

    The counterpart to pkasolver's "predicts acetic acid's pKa" test: the
    point is to prove the tool WORKS, which a path check cannot. ORCA
    prints its version only inside a run, so this gets the version and the
    proof from the same three seconds.
    """
    import re
    import subprocess
    import tempfile

    path = Path(configured_path or "")
    if not path.is_file():
        raise ToolVerificationError(f"No ORCA executable at {path}")

    with tempfile.TemporaryDirectory(prefix="openchem-orca-test-") as scratch:
        job = Path(scratch) / "test.inp"
        job.write_text(_ORCA_TEST_INPUT, encoding="utf-8")
        try:
            completed = subprocess.run(
                [str(path), job.name],
                cwd=scratch,
                capture_output=True,
                text=True,
                timeout=180,
            )
        except OSError as exc:
            raise ToolVerificationError(f"Could not run {path}: {exc}") from exc
        except subprocess.TimeoutExpired as exc:
            raise ToolVerificationError(
                "ORCA did not finish a two-atom test job within 3 minutes."
            ) from exc

    output = completed.stdout or ""
    version = re.search(r"Program Version\s+(\S+)", output)
    energy = re.search(r"FINAL SINGLE POINT ENERGY\s+(-?\d+\.\d+)", output)
    if energy is None:
        tail = "\n".join(output.strip().splitlines()[-8:])
        raise ToolVerificationError(
            f"ORCA ran but produced no energy. Its last words were:\n{tail}"
        )

    value = float(energy.group(1))
    if abs(value - _ORCA_TEST_ENERGY) > _ORCA_TEST_TOLERANCE:
        raise ToolVerificationError(
            f"ORCA ran but computed {value:.6f} Eh for H2 at HF/STO-3G, where "
            f"{_ORCA_TEST_ENERGY:.6f} is expected. The executable works but is "
            "not giving the right answer."
        )
    named = f"ORCA {version.group(1)}" if version else "ORCA"
    return f"{named} ran a test calculation correctly (H2 at HF/STO-3G, {value:.6f} Eh)."


# Psi4 is LGPL-3.0 and its releases are public, so the app COULD fetch it; version 1 does not (Alex, 2026-10-19: locate-only), so these are
# links for a person to follow. The installs page is generated by the project (it offers the installer, conda and the platform choices).
#: Where a person gets Psi4 (the project's install page).
PSI4_DOWNLOAD_PAGE = "https://psicode.org/installs/"
#: The Psi4 project's home, with its manual.
PSI4_DOCS_PAGE = "https://psicode.org/"

#: Psi4's `--version` prints just the release ("1.11"), exit code 0, in 0.2 s (measured 2026-10-19, Psi4 1.11 on Windows). That is what tells it from another program called `psi4`.
_PSI4_VERSION_RE = r"^\s*(\d+\.\d+(?:\.\d+)?)\s*$"

#: The same two-atom job as ORCA's Test, in Psi4's input. Psi4 gives -1.116783 Eh for H2 at 0.74 A, HF/STO-3G, measured with Psi4 1.11 (ORCA's is -1.116759: the two STO-3G definitions differ by 2e-5 Eh).
_PSI4_TEST_ENERGY = -1.116783
#: The Test button's job: H2 at HF/STO-3G in Psi4's own input.
_PSI4_TEST_INPUT = "molecule {\n0 1\nH 0 0 0\nH 0 0 0.74\nsymmetry c1\nno_reorient\nno_com\n}\nset basis sto-3g\nset reference rhf\nenergy('scf')\n"


def describe_psi4_status(configured_path: str) -> str:
    """One-line status for the Psi4 tab. Like ORCA's it does not run the program (that is the Test button's job), so a visit to the tab starts nothing."""
    if not configured_path:
        return "Not configured"
    path = Path(configured_path)
    if not path.is_file():
        return f"Configured, but no file at {path}"
    return f"Configured: {path.name} in {path.parent}"


def responds_as_psi4(path: Path | str) -> bool:
    """Whether this really is Psi4, asked by running `psi4 --version`: Psi4 prints its release number and nothing else (exit 0).

    **A NAME MATCH IS NOT ENOUGH**, for the reason `responds_as_orca` records: a program called `psi4` that is not this one must not be accepted by Locate.
    """
    import re
    import subprocess

    try:
        completed = subprocess.run([str(path), "--version"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0 and re.match(_PSI4_VERSION_RE, completed.stdout or "") is not None


def verify_psi4(configured_path: str) -> str:
    """Run a real two-atom calculation and report the version, or raise: the counterpart to `verify_orca`.

    Checked against the known energy, because a build that runs and computes the wrong answer is the failure a file check cannot see.
    """
    import re
    import subprocess
    import tempfile

    path = Path(configured_path or "")
    if not path.is_file():
        raise ToolVerificationError(f"No Psi4 executable at {path}")
    with tempfile.TemporaryDirectory(prefix="openchem-psi4-test-") as scratch:
        job = Path(scratch) / "test.dat"
        job.write_text(_PSI4_TEST_INPUT, encoding="utf-8")
        try:
            completed = subprocess.run([str(path), "-n", "1", "-o", "stdout", job.name], cwd=scratch, capture_output=True, text=True, timeout=180)
        except OSError as exc:
            raise ToolVerificationError(f"Could not run {path}: {exc}") from exc
        except subprocess.TimeoutExpired as exc:
            raise ToolVerificationError("Psi4 did not finish a two-atom test job within 3 minutes.") from exc
    output = completed.stdout or ""
    # A failed run prints "Psi4 encountered an error" (and exits 1): the marker in the text is what counts, as in the engine's own parser.
    if "Psi4 encountered an error" in output:
        tail = "\n".join(line for line in output.strip().splitlines() if line.strip() and not line.startswith("***"))[-600:]
        raise ToolVerificationError(f"Psi4 ran but reported an error:\n{tail}")
    energy = re.search(r"^\s+Total Energy =\s+(-?\d+\.\d+)", output, re.MULTILINE)
    if energy is None:
        tail = "\n".join(output.strip().splitlines()[-8:])
        raise ToolVerificationError(f"Psi4 ran but produced no energy. Its last words were:\n{tail}")
    value = float(energy.group(1))
    if abs(value - _PSI4_TEST_ENERGY) > _ORCA_TEST_TOLERANCE:
        raise ToolVerificationError(
            f"Psi4 ran but computed {value:.6f} Eh for H2 at HF/STO-3G, where {_PSI4_TEST_ENERGY:.6f} is expected. The executable works but is not giving the right answer."
        )
    version = re.search(r"Psi4 (\d+\.\d+(?:\.\d+)?) release", output)
    named = f"Psi4 {version.group(1)}" if version else "Psi4"
    return f"{named} ran a test calculation correctly (H2 at HF/STO-3G, {value:.6f} Eh)."


#: Where a person gets xtb (the project's releases page, which carries the Windows build). The app does not fetch it: locate-only, as Psi4 is.
XTB_DOWNLOAD_PAGE = "https://github.com/grimme-lab/xtb/releases"
#: The xtb project's home.
XTB_DOCS_PAGE = "https://github.com/grimme-lab/xtb"

#: What xtb's `--version` prints, among other banner lines, with exit code 0 (measured with xtb 6.7.1pre on Windows): `* xtb version 6.7.1pre (5071a88) compiled by ...`.
_XTB_VERSION_RE = r"\*\s+xtb version (\S+)"

#: GFN2-xTB's energy for H2 at 0.74 A, measured with xtb 6.7.1pre through the provider's own input and command (a build that computes another number is not giving the right answer).
_XTB_TEST_ENERGY = -0.981984


def describe_xtb_status(configured_path: str) -> str:
    """One-line status for the xtb tab. It does not run the program (that is the Test button's job), so a visit to the tab starts nothing."""
    if not configured_path:
        return "Not configured"
    path = Path(configured_path)
    if not path.is_file():
        return f"Configured, but no file at {path}"
    return f"Configured: {path.name} in {path.parent}"


def responds_as_xtb(path: Path | str) -> bool:
    """Whether this really is xtb, asked by running `xtb --version`: it prints a banner with `xtb version N` (exit 0).

    **A NAME MATCH IS NOT ENOUGH**, for the reason `responds_as_orca` records. The output is decoded as UTF-8 (the banner is, and Windows' default code page is not).
    """
    import re
    import subprocess

    try:
        completed = subprocess.run([str(path), "--version"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0 and re.search(_XTB_VERSION_RE, completed.stdout or "") is not None


def verify_xtb(configured_path: str) -> str:
    """Run a real two-atom calculation through the engine's OWN input and command, and report the version, or raise.

    Going through `XtbQuantumEngineProvider` rather than a hand-written command means the Test exercises what a run uses: the `job.inp` name, the Turbomole block, the header the command is read back from.
    Checked against the known energy, because a build that runs and computes the wrong answer is the failure a file check cannot see.
    """
    import re
    import subprocess
    import tempfile

    from rdkit import Chem
    from rdkit.Geometry import Point3D

    from openchem.chem.xtb_engine import XtbOutputError, XtbQuantumEngineProvider

    path = Path(configured_path or "")
    if not path.is_file():
        raise ToolVerificationError(f"No xtb executable at {path}")
    h2 = Chem.AddHs(Chem.MolFromSmiles("[H][H]"))
    conformer = Chem.Conformer(2)
    conformer.SetAtomPosition(0, Point3D(0.0, 0.0, 0.0))
    conformer.SetAtomPosition(1, Point3D(0.0, 0.0, 0.74))
    h2.RemoveAllConformers()
    h2.AddConformer(conformer)
    provider = XtbQuantumEngineProvider(threads=lambda: 1)
    with tempfile.TemporaryDirectory(prefix="openchem-xtb-test-") as scratch:
        job = Path(scratch) / "job.inp"
        job.write_text(provider.build_input(h2, 0, 1, "GFN2-xTB", "sp"), encoding="utf-8")
        try:
            completed = subprocess.run(
                provider.command_args(str(path), job), cwd=scratch, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
            )
        except OSError as exc:
            raise ToolVerificationError(f"Could not run {path}: {exc}") from exc
        except subprocess.TimeoutExpired as exc:
            raise ToolVerificationError("xtb did not finish a two-atom test job within 2 minutes.") from exc
    output = completed.stdout or ""
    try:
        descriptors, _conformer = provider.parse_output(output, h2, "xtb-test", "sp")
    except XtbOutputError as exc:
        tail = "\n".join(output.strip().splitlines()[-8:])
        raise ToolVerificationError(f"xtb ran but did not give a result: {exc}\nIts last words were:\n{tail}") from exc
    value = descriptors[0].value
    if abs(value - _XTB_TEST_ENERGY) > _ORCA_TEST_TOLERANCE:
        raise ToolVerificationError(
            f"xtb ran but computed {value:.6f} Eh for H2 with GFN2-xTB, where {_XTB_TEST_ENERGY:.6f} is expected. The executable works but is not giving the right answer."
        )
    version = re.search(_XTB_VERSION_RE, output)
    named = f"xtb {version.group(1)}" if version else "xtb"
    return f"{named} ran a test calculation correctly (H2 with GFN2-xTB, {value:.6f} Eh)."


class ToolVerificationError(RuntimeError):
    """A configured tool is present but did not work when asked to."""


def verify_vina(configured_path: str) -> str:
    """Run the configured Vina and report what it says it is.

    Cheaper than ORCA's test because Vina HAS a `--version`, so there is
    no calculation to run -- but it is still a run rather than a file
    check, for the same reason: a path that exists proves nothing about
    what is at the end of it.
    """
    if not configured_path:
        raise ToolVerificationError("No Vina executable configured.")
    if not Path(configured_path).is_file():
        raise ToolVerificationError(f"No file at {configured_path}")
    engine = select_vina_engine(configured_path)
    if engine is None:
        raise ToolVerificationError(
            f"{Path(configured_path).name} did not identify itself as Vina or QuickVina."
        )
    return f"Works: {engine.engine_id} {engine.version()}"


def _search_roots() -> list[Path]:
    """Where a user-installed program plausibly lives on this platform.

    Only ordinary install locations -- this never walks a whole drive,
    because a scan that takes a minute is one people cancel and then
    distrust.
    """
    roots: list[Path] = []
    system = platform.system()
    if system == "Windows":
        drives = [Path(f"{letter}:/") for letter in "CDEFG" if Path(f"{letter}:/").exists()]
        for drive in drives:
            roots.extend([drive, drive / "Program Files", drive / "Program Files (x86)"])
    else:
        roots.extend([Path("/opt"), Path("/usr/local"), Path("/usr/local/bin"), Path.home()])
    roots.append(app_paths.subdirectory("tools"))
    return [root for root in roots if root.is_dir()]


def responds_as_orca(path: Path | str) -> bool:
    """Whether this really is FACCTS' ORCA, asked by running it.

    **A NAME MATCH IS NOT ENOUGH, and this is not hypothetical.** Searching
    this machine for "orca" found

        C:\\Windows\\Installer\\{62A84A8B-...}\\Orca.exe

    before it found the real one -- an unrelated program in an MSI cache.
    Configuring that would produce a quantum-chemistry tool that fails in
    a way naming neither the cause nor the fix, which is exactly the
    confusion the ORCA tab already warns about in prose.

    Run with no arguments ORCA asks for an input file and exits 0, so this
    costs no calculation.
    """
    import subprocess

    try:
        completed = subprocess.run(
            [str(path)], capture_output=True, text=True, timeout=20
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return _ORCA_NO_INPUT_MARKER in ((completed.stdout or "") + (completed.stderr or ""))


def responds_as_vina(path: Path | str) -> bool:
    """Whether this is really AutoDock Vina.

    `select_vina_engine` already runs `--version` and recognises both Vina
    and QuickVina, so identity is its question rather than a second one
    asked differently here.
    """
    return select_vina_engine(str(path)) is not None


def locate_executable(
    names: tuple[str, ...],
    *,
    validate: Callable[[Path], bool],
    extra_roots: tuple[Path, ...] = (),
    search_roots: tuple[Path, ...] | None = None,
) -> Path | None:
    """Find an already-installed executable, and CHECK it is the right one.

    `validate` is required rather than optional on purpose -- see
    `responds_as_orca` for the wrong file this returned when identity was
    taken on trust. `find_program` does the per-directory work and knows
    the platform's suffix rules, so this only decides where to look.

    `search_roots` replaces the platform's usual install locations. It
    exists for tests: one that leaves it out walks real drives, and the
    first version of `test_locating_runs_each_candidate...` did exactly
    that -- **14 s warm and four minutes cold**, for a question about a
    single temporary directory.
    """
    from openchem.services.sidecar_env import find_program

    roots = _search_roots() if search_roots is None else list(search_roots)
    seen: set[Path] = set()
    for root in (*extra_roots, *roots):
        try:
            found = find_program(root, names)
        except OSError:
            continue
        if found is None:
            continue
        candidate = Path(found)
        if candidate in seen:
            continue
        seen.add(candidate)
        if validate(candidate):
            return candidate
    return None


def describe_orca_platform_hint() -> str:
    """OS/architecture-specific pointer for which ORCA build to pick on the
    FACCTS download portal -- "ORCA" alone is too generic a name to know
    what you're looking for once you're staring at seven differently-named
    .zip/.tar.xz files (Windows/Linux/macOS x x86_64/arm64 x MPI variant).

    Grounded in the actual asset-naming pattern from a real ORCA 6.1.1
    download page (e.g. "Orca.6.1.1.Win64_msmpi.zip",
    "orca_6_1_1_macosx_arm64_openmpi411.tar.bz2") -- not guessed. The
    "_autoci" Windows variants' exact purpose is intentionally NOT
    explained here: it isn't documented anywhere this app has verified, so
    guessing would be worse than saying nothing.
    """
    system = platform.system()
    is_arm = platform.machine().lower() in ("arm64", "aarch64")

    if system == "Windows":
        return (
            "You're on Windows. Look for a build named like "
            "\"Orca.<version>.Win64_msmpi.zip\" -- that's the standard build "
            "most people want. It also requires Microsoft MPI installed "
            "separately (search \"Microsoft MPI download\") for parallel "
            "runs. Builds with \"_autoci\" in the name are a different, "
            "less-documented variant -- if you're not sure you need one, "
            "use the plain msmpi build instead."
        )
    if system == "Darwin":
        keyword, friendly = ("arm64", "Apple Silicon") if is_arm else ("intel", "Intel")
        return f'You\'re on macOS ({friendly}). Look for a build matching "macosx_{keyword}".'
    keyword = "arm64" if is_arm else "x86-64"
    return f'You\'re on Linux ({keyword}). Look for a build matching "linux_{keyword.replace("-", "_")}".'


def _platform_keyword() -> str:
    system = platform.system()
    if system == "Windows":
        return "win"
    if system == "Darwin":
        return "mac"
    return "linux"


def fetch_latest_vina_release() -> VinaReleaseAsset:
    """Queries GitHub's public Releases API for the newest AutoDock Vina
    release and picks the asset matching this platform.

    Raises RuntimeError (with a message safe to show directly in the UI) on
    any network failure, unparseable response, or missing platform asset.
    Performs blocking network I/O -- callers must run this off the GUI
    thread (see `openchem.plugins.async_task.run_async`, the same helper
    every other network-touching panel in this codebase already uses).
    """
    try:
        with open_url(  # noqa: S310 - fixed https GitHub API URL, not user input
            VINA_RELEASES_API, timeout=15, headers={"Accept": "application/vnd.github+json"}
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (URLError, OSError) as exc:
        raise RuntimeError(f"Could not reach GitHub: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Unexpected response from GitHub: {exc}") from exc

    version = str(payload.get("tag_name", "unknown"))
    keyword = _platform_keyword()
    for asset in payload.get("assets", []):
        name = str(asset.get("name", ""))
        lowered = name.lower()
        if keyword not in lowered or lowered.endswith(_SKIP_SUFFIXES):
            continue
        return VinaReleaseAsset(
            version=version,
            name=name,
            download_url=str(asset.get("browser_download_url", "")),
            size_bytes=int(asset.get("size", 0)),
        )

    raise RuntimeError(
        f"No {keyword} executable found in the latest AutoDock Vina release ({version}). "
        f"Visit {VINA_RELEASES_PAGE} to download it manually."
    )


def download_vina_asset(
    asset: VinaReleaseAsset, progress_callback: Callable[[int, int], None] | None = None
) -> Path:
    """Downloads `asset` into OpenChem Studio's own per-user tools directory
    and returns the resulting path.

    The CALLER is responsible for getting the user's explicit, per-download
    confirmation (exact URL, version, and size, per this app's own
    file-download policy) before invoking this -- this function performs
    the download unconditionally as soon as it's called. Same
    configured data root (see `openchem/paths.py`)
    `PluginManager` already uses for the equivalent "app-managed, per-user
    files" concept (see `plugins/manager.py`).
    """
    dest_dir = app_paths.subdirectory("tools") / "vina"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / asset.name

    try:
        # noqa: S310 - URL comes from GitHub's own API response
        with open_url(asset.download_url, timeout=30) as response:
            total = asset.size_bytes or int(response.headers.get("Content-Length", 0) or 0)
            downloaded = 0
            with open(dest_path, "wb") as out_file:
                while True:
                    chunk = response.read(65536)
                    if not chunk:
                        break
                    out_file.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback is not None:
                        progress_callback(downloaded, total)
    except (URLError, OSError) as exc:
        dest_path.unlink(missing_ok=True)
        raise RuntimeError(f"Download failed: {exc}") from exc

    if platform.system() != "Windows":
        dest_path.chmod(dest_path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    return dest_path
