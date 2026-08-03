# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller one-directory build of OpenChem Studio.

Run it through `build.ps1` at the repository root rather than invoking
`pyinstaller` by hand; that script checks prerequisites and stages the
`plugins/` tree afterwards.

WHY PYINSTALLER AND NOT NUITKA. The scaffolding this replaced was a Nuitka
template. The deciding factor is not output quality -- Nuitka's would be
better -- but that almost every failure mode here is a *missing data file*
that produces a silently blank window rather than a build error, so the
build/launch/see-what-is-blank cycle gets run many times. PyInstaller's
cycle is minutes where Nuitka's is tens of minutes, and its PySide6 +
QtWebEngine hooks are far better trodden. Startup speed is not this
application's bottleneck.

EVERY `datas` ENTRY BELOW IS THERE BECAUSE SOMETHING BREAKS WITHOUT IT, and
mostly breaks *silently*. Each one says what. Do not prune this list by
inspection -- prune it by removing an entry and launching the exe.
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).parent  # noqa: F821 -- SPECPATH is injected by PyInstaller
PKG = ROOT / "src" / "openchem"

# --------------------------------------------------------------------------
# Data files
# --------------------------------------------------------------------------
datas = []

# The three web views. Ketcher (2D editor), Mol* (macromolecules) and 3Dmol
# (small-molecule 3D) are all loaded as local HTML off disk by
# ui/widgets/*_backend.py, each resolving `Path(__file__)/../../../resources`.
# Frozen, that resolves inside `_internal/openchem/`, so mirroring the source
# layout under `openchem/resources` needs no code change. Miss this and the
# app starts perfectly and every editor/viewer is a blank white rectangle.
datas += [(str(PKG / "resources"), "openchem/resources")]

# The vendored IUPAC namer's data, which MUST land as a SIBLING of
# `vendor/iupac_namer/`, not inside it. Different modules resolve it from
# different depths -- `data_loader.py` walks up two levels,
# `perception/fg/acid_infix_composition.py` walks up four -- so any freezer
# that flattens package data breaks naming. This was already got wrong once
# during vendoring; see src/openchem/vendor/VENDORING.md.
datas += [(str(PKG / "vendor" / "data"), "openchem/vendor/data")]

# Two scripts that are never imported -- they are handed as argv to a
# *sidecar* interpreter (the pkasolver / STOUT conda environments, which run
# their own Python, not ours). PyInstaller's import analysis therefore never
# sees them, and they have to ship as plain source next to their callers,
# which locate them with `Path(__file__).parent / "..._runner.py"`.
datas += [
    (str(PKG / "chem" / "pka_runner.py"), "openchem/chem"),
    (str(PKG / "chem" / "stout_runner.py"), "openchem/chem"),
]

# RDKit's own data: the atomic-properties table, ring templates and the
# SMARTS catalogues behind fragment/functional-group perception. RDKit finds
# them via RDDataDir and raises at *call* time, not import time.
datas += collect_data_files("rdkit")

# Contrib/SA_Score/sascorer.py, which is SOURCE that behaves as data. The
# synthetic-accessibility descriptor appends `RDConfig.RDContribDir/SA_Score`
# to sys.path and imports `sascorer` by name at call time
# (chem/descriptor_providers.py), so the analysis never sees the import and
# `collect_data_files` skips it -- that helper excludes .py files by default,
# which is why the line above collects the neighbouring fpscores.pkl.gz and
# not the one module that reads it. Caught only by launching the build: every
# Physicochemical property in the Properties panel read
# "No module named 'sascorer'", because one failing provider takes the whole
# rdkit descriptor batch down with it.
datas += collect_data_files(
    "rdkit", include_py_files=True, includes=["Contrib/SA_Score/*.py"]
)

# py2opsin ships OPSIN as a 14 MB jar beside its module and shells out to
# `java -jar` against it. It is data, not an import. (The JRE itself is a
# user-installed sidecar and is deliberately NOT bundled.)
datas += collect_data_files("py2opsin")

# --------------------------------------------------------------------------
# Hidden imports
# --------------------------------------------------------------------------
# Whole-package sweep of our own code. Panels, providers and the naming
# engine's perception modules are reached through registries and dynamic
# dispatch rather than literal top-level imports, so static analysis misses
# a large fraction of them, and each miss is a feature that raises
# ImportError only once a user clicks the thing.
hiddenimports = collect_submodules("openchem")

# The AI-assistant plugin imports these lazily, inside the request functions,
# so they are invisible to the analysis twice over: the plugin tree is never
# statically imported at all, and the import is not at module level. A frozen
# app has no pip, so a user cannot install them afterwards the way the
# error message ("run: uv sync --extra ai") assumes -- if they ship at all,
# they ship here.
hiddenimports += ["anthropic", "openai", "requests"]

a = Analysis(  # noqa: F821
    [str(ROOT / "packaging" / "openchem_launcher.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # tkinter is pulled in by matplotlib-adjacent transitive imports and is
    # ~10 MB of Tcl/Tk this application never uses; pytest has no business in
    # a shipped build.
    excludes=["tkinter", "pytest", "_pytest"],
    noarchive=False,
    optimize=0,
)

# --------------------------------------------------------------------------
# Qt translation trimming -- the one safe size win
# --------------------------------------------------------------------------
# PySide6 ships ~62 MB of translations. Two distinct sets live in there and
# they are NOT equally droppable:
#
#   translations/*.qm                  Qt's own UI strings for ~40 locales.
#                                      This app has no translations, so these
#                                      only ever localise stock Qt dialogs.
#                                      Safe to drop.
#   translations/qtwebengine_locales/  Chromium's locale packs. QtWebEngine
#                                      refuses to initialise without the one
#                                      matching its locale, so dropping ALL
#                                      of these is one of the ways to get
#                                      three blank web views. en-US is kept.
def _keep(entry):
    dest = entry[0].replace("\\", "/")
    if "/qtwebengine_locales/" in dest:
        return dest.endswith("en-US.pak")
    return not dest.endswith(".qm")


a.datas = [entry for entry in a.datas if _keep(entry)]

pyz = PYZ(a.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="OpenChemStudio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX corrupts Qt DLLs often enough that it is not worth it.
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "icon.ico") if (ROOT / "icon.ico").exists() else None,
)

coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="OpenChemStudio",
)
