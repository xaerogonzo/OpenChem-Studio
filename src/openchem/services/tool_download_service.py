from __future__ import annotations

import json
import logging
import platform
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.error import URLError
from urllib.request import Request, urlopen

import platformdirs

from openchem.chem.vina_engine import select_vina_engine
from openchem import paths as app_paths

logger = logging.getLogger("openchem.tools")

# Public GitHub Releases API -- no auth needed for a public repo. AutoDock
# Vina's releases are Apache-2.0-licensed executables published directly by
# the Scripps Research Institute's own team, unlike ORCA (registration/EULA
# gated, no public direct-download URL -- see ExternalToolsDialog).
VINA_RELEASES_API = "https://api.github.com/repos/ccsb-scripps/AutoDock-Vina/releases/latest"
VINA_RELEASES_PAGE = "https://github.com/ccsb-scripps/AutoDock-Vina/releases"

# ORCA's distribution moved from the Max Planck-hosted orcaforum (its old
# /app.php/portal download link now 404s) to FACCTS GmbH, ORCA's commercial
# steward -- confirmed against faccts.de's own site, which points to this
# exact URL as "Downloads (for registered users)". A free account is
# required; there is no public direct-download URL, so this can only ever
# be a link, never an automated fetch (see ExternalToolsDialog).
ORCA_DOWNLOAD_PAGE = "https://www.faccts.de/customer"
ORCA_DOCS_PAGE = "https://www.faccts.de/docs"

_SKIP_SUFFIXES = (".txt", ".sha256sum", ".sha256", ".asc", ".sig", ".md5")


@dataclass(slots=True)
class VinaReleaseAsset:
    """One downloadable asset from AutoDock Vina's latest GitHub release.

    Surfaced to the user (name/url/size/version) for explicit confirmation
    in ExternalToolsDialog before `download_vina_asset` is ever called --
    this dataclass itself performs no network I/O.
    """

    version: str
    name: str
    download_url: str
    size_bytes: int


def describe_vina_status(configured_path: str) -> str:
    """One-line human-readable status for ExternalToolsDialog -- "Found:
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
    request = Request(
        VINA_RELEASES_API,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "OpenChemStudio"},
    )
    try:
        with urlopen(request, timeout=15) as response:  # noqa: S310 - fixed https GitHub API URL, not user input
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

    request = Request(asset.download_url, headers={"User-Agent": "OpenChemStudio"})
    try:
        with urlopen(request, timeout=30) as response:  # noqa: S310 - URL comes from GitHub's own API response
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
