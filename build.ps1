# =============================================================================
# build.ps1 - freeze OpenChem Studio into dist\OpenChemStudio\
# =============================================================================
#
#   uv sync --extra ai --extra network --extra openbabel --group build
#   .\build.ps1
#
# Produces a one-directory build (~1 GB) that runs on a Windows machine with
# no Python and no development environment. The size is PySide6: QtWebEngine
# alone is a full Chromium. That is expected -- do not contort the build
# trying to shrink it.
#
# The real work is in packaging\openchem.spec, which carries the reasoning
# for every bundled data file. This script is the parts that do not belong
# in a spec: prerequisite checks, clean state, and staging plugins\.
#
# What is deliberately NOT bundled: pkasolver, STOUT, the Temurin JRE, ORCA
# and Vina. Those are user-installed into the configurable data directory
# (src\openchem\paths.py) through the External Tools dialog -- they are
# multi-gigabyte, individually optional, and several are separately licensed.
# The frozen app finds them there exactly as the source build does.
# =============================================================================

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ROOT = $PSScriptRoot
$DIST = "$ROOT\dist"
$APPDIR = "$DIST\OpenChemStudio"
$SPEC = "$ROOT\packaging\openchem.spec"

Write-Host ""
Write-Host "=== OpenChem Studio - PyInstaller build ===" -ForegroundColor Cyan
Write-Host ""

# ---------- Pre-flight --------------------------------------------------------

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "uv is not on PATH. See README.md for setup."
}

& uv run --no-sync python -c "import PyInstaller" 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller is missing. Run: uv sync --extra ai --extra network --extra openbabel --group build"
}

# The AI plugin's providers import `anthropic`/`openai` lazily and the spec
# lists them as hidden imports. A hidden import that is not installed is a
# hard PyInstaller error, so catch it here with an actionable message rather
# than 200 lines into the build log.
& uv run --no-sync python -c "import anthropic, openai, requests" 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "The ai/network extras are missing. Run: uv sync --extra ai --extra network --extra openbabel --group build"
}

# ---------- Clean -------------------------------------------------------------
# A stale dist\ is actively misleading here: the failure mode being tested for
# is a MISSING data file, and last build's copy of it sitting in place looks
# exactly like success.

foreach ($stale in @($APPDIR, "$ROOT\build")) {
    if (Test-Path $stale) {
        Write-Host "  [clean] $stale" -ForegroundColor DarkGray
        Remove-Item $stale -Recurse -Force
    }
}

# ---------- Freeze ------------------------------------------------------------
# PyInstaller writes progress to stderr; with $ErrorActionPreference = "Stop"
# PowerShell turns each such line into a NativeCommandError and aborts the
# script mid-build. Suspend Stop mode around the call and check the exit code.

$prevEAP = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& uv run --no-sync python -m PyInstaller --noconfirm --distpath $DIST --workpath "$ROOT\build" $SPEC 2>&1 |
    ForEach-Object { Write-Host $_ }
$exitCode = $LASTEXITCODE
$ErrorActionPreference = $prevEAP

if ($exitCode -ne 0) {
    throw "PyInstaller failed (exit $exitCode)"
}

# ---------- Stage plugins -----------------------------------------------------
# Plugins are loaded by reading and exec'ing plugin.py as *source*
# (plugins/manager.py:_import_plugin_module), so they ship as a plain
# directory rather than as frozen modules -- and they ship BESIDE the exe,
# not inside _internal\, so a user can add or edit one without a Python
# install. PluginManager looks exactly here when sys.frozen is set.

Write-Host ""
Write-Host "  Staging plugins\ ..." -ForegroundColor Cyan
Copy-Item "$ROOT\plugins" "$APPDIR\plugins" -Recurse -Force
Get-ChildItem "$APPDIR\plugins" -Recurse -Directory -Filter "__pycache__" |
    Remove-Item -Recurse -Force

# ---------- Verify ------------------------------------------------------------
# Every check below is for something that fails SILENTLY at runtime -- a blank
# web view or an exception on a code path a smoke test would not reach. A
# build that merely compiled proves nothing.

$required = @(
    # QtWebEngine's helper process and its resource tree. Without these the
    # 2D editor and both 3D viewers render blank and the app looks fine.
    "_internal\PySide6\QtWebEngineProcess.exe",
    "_internal\PySide6\resources\qtwebengine_resources.pak",
    "_internal\PySide6\translations\qtwebengine_locales\en-US.pak",
    # The three web views' own assets.
    "_internal\openchem\resources\ketcher\dist\index.html",
    "_internal\openchem\resources\molstar\viewer.html",
    "_internal\openchem\resources\viewer3d\viewer.html",
    # The vendored namer's data, which has to sit as a SIBLING of the
    # iupac_namer package. Only the data half can be checked for on disk:
    # the package half is frozen into the PYZ archive and has no loose .py
    # files at all, so there is nothing to compare against here. Whether the
    # sibling relationship actually holds is decided by `__file__`-relative
    # resolution at runtime and can only be proved by naming a molecule --
    # bluebook\ is included as a second, deeper file because
    # perception\fg\ resolves the data directory from four levels up rather
    # than two, and a partially-copied tree would satisfy only the shallow one.
    "_internal\openchem\vendor\data\functional_groups.json",
    "_internal\openchem\vendor\data\bluebook",
    # Sidecar runner scripts, which are data rather than imports.
    "_internal\openchem\chem\pka_runner.py",
    "_internal\openchem\chem\stout_runner.py",
    # OPSIN's jar.
    "_internal\py2opsin\opsin-cli-2.9.0-jar-with-dependencies.jar",
    # RDKit's synthetic-accessibility scorer: source imported by name off
    # sys.path, which the default data collection drops. Its absence broke
    # every Physicochemical property, not just this one descriptor.
    "_internal\rdkit\Contrib\SA_Score\sascorer.py",
    # Plugins, staged above.
    "plugins\ai_assistant\plugin.py",
    "OpenChemStudio.exe"
)

$missing = @()
foreach ($rel in $required) {
    if (-not (Test-Path "$APPDIR\$rel")) { $missing += $rel }
}

if ($missing.Count -gt 0) {
    Write-Host ""
    Write-Host "  [FAIL] the build is missing files that fail silently at runtime:" -ForegroundColor Red
    $missing | ForEach-Object { Write-Host "         $_" -ForegroundColor Red }
    throw "Incomplete build"
}

$sizeGB = [math]::Round((Get-ChildItem $APPDIR -Recurse -File |
    Measure-Object -Property Length -Sum).Sum / 1GB, 2)

Write-Host ""
Write-Host "  All $($required.Count) required-file checks passed." -ForegroundColor Green
Write-Host "Build complete -> $APPDIR ($sizeGB GB)" -ForegroundColor Green
Write-Host ""
Write-Host "Launch it and confirm the 2D editor draws, both 3D viewers render," -ForegroundColor DarkGray
Write-Host "and naming returns a name. Those are the checks a file list cannot make." -ForegroundColor DarkGray
Write-Host ""

exit 0
