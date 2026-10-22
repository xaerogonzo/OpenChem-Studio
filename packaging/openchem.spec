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

import sys
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

# ChEMBL's salt and solvent lists, read from BESIDE `getparent.py` by path.
# PyInstaller collects the module and not these, so miss this and every salt's
# compound properties refuse with a FileNotFoundError dressed as a failure.
datas += [
    (str(PKG / "vendor" / "chembl_structure_pipeline" / name), "openchem/vendor/chembl_structure_pipeline")
    for name in ("salts.smi", "solvents.smi", "LICENSE.chembl-structure-pipeline")
]

# NO `docs/` ENTRY, ON PURPOSE. The in-application help is the four documents
# in `help.HELP_DOCUMENTS`, and a frozen build reads them from
# `openchem/_help_bundle.py`, which `build.ps1` generates (tools/
# build_help_bundle.py) before this spec runs, so it is collected as an
# ordinary module and lives inside the exe's archive. Shipping them loose here
# let a user save over the real help from the Help window's "Open file" button.
# A human-readable copy of `docs/` is staged beside the exe by `build.ps1`; the
# application never reads it. Miss the generated module and Help raises
# HelpUnavailable naming it, rather than opening an empty window.

# ALL of `chem/data/`, EXCEPT `regulatory/sources/`. This used to be one entry
# per file, and the list rotted the way the comment on the sidecar runners below
# warns about: a data file added to the app and not added here does not fail the
# build, it fails the first launch. Measured 2026-10-21 on a fresh build: SEVEN-
# TEEN of the files in this directory were missing (abraham_solvents.json among
# them), and the frozen app died at import with a FileNotFoundError before any
# window appeared. Nothing in the build or the test suite could see it, because
# every one of them works from a checkout. A directory entry cannot go stale.
#
# What each family of files is for, since the per-file entries carried this:
#   * hypervalent_rules.json, electronegativity.json -- the structure checker and
#     oxidation-state table; FileNotFoundError on the first structure drawn.
#   * elements.json -- the periodic-table dialog (an empty table without it).
#   * lewis_parameters.json -- Drago-Wayland E and C; optional by design, shipped
#     because silently losing the only real energy in that panel is no trade-off.
#   * eqeq_*.json, eem_ionescu2013.json -- charge models, read on first use.
#   * tautomer_validation*.json -- the criteria and the record of the run that
#     passed them; absent, every result reads `unvalidated` (safe, and invisible).
#
# `regulatory/sources/` is the hand-edited INPUT to
# tools/build_regulatory_rulesets.py and is of no use to a frozen app; shipping it
# would invite someone to edit the copy that is never read. Only `generated/` is
# shipped, and `_keep` below drops `sources/` from the directory entry.
# Miss `generated/` and the regulatory engine loads zero rulesets and reports
# "nothing was checked" -- honest, and useless.
datas += [(str(PKG / "chem" / "data"), "openchem/chem/data")]

# Scripts that are never imported -- they are handed as argv to a *sidecar*
# interpreter (the pkasolver and ADMET environments, which run their own
# Python, not ours). PyInstaller's import analysis therefore never sees them,
# and they have to ship as plain source next to their callers, which locate
# them with `Path(__file__).resolve().parent / "..._runner.py"`.
#
# KEEP THIS LIST IN STEP WITH `chem/*_runner.py`. Both ways of being wrong
# have already happened here: a `stout_runner.py` entry outlived the file
# (STOUT was removed, and a missing `datas` source aborts the build), while
# `admet_runner.py` was added to the app and never added here -- which does
# not fail the build at all, it fails the first time a user opens an ADMET
# calculator in the frozen app.
datas += [
    (str(PKG / "chem" / "pka_runner.py"), "openchem/chem"),
    (str(PKG / "chem" / "admet_runner.py"), "openchem/chem"),
    (str(PKG / "chem" / "aizynth_runner.py"), "openchem/chem"),  # handed to the USER'S planner interpreter as a path (chem/aizynth_planner.py)
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
#
# Contrib/NP_Score/npscorer.py is the SAME case and was missed the same way. The natural-product
# likeness descriptor imports `npscorer` by name from `RDContribDir/NP_Score` at call time, and
# its model (`publicnp.model.gz`) came along with the data line above while the module did not.
# Found 2026-10-22 by running the BUILT app's scores scripts: the whole rdkit descriptor batch
# failed with "No module named 'npscorer'", so every derived score that reads a descriptor had no
# value. EVERY Contrib directory the code reads is listed here, and tests/test_packaged_data.py
# fails if the code reads one that this list does not name.
datas += collect_data_files(
    "rdkit",
    include_py_files=True,
    includes=["Contrib/SA_Score/*.py", "Contrib/NP_Score/*.py"],
)

# py2opsin ships OPSIN as a 14 MB jar beside its module and shells out to
# `java -jar` against it. It is data, not an import. (The JRE itself is a
# user-installed sidecar and is deliberately NOT bundled.)
datas += collect_data_files("py2opsin")

# Open Babel's format plugins (*.obf) and its data tables. Every file format
# Open Babel reads or writes lives in one of these nine plugin libraries --
# they are dlopen'd by Open Babel's own plugin loader at import time, so
# PyInstaller's binary analysis never sees them and collected only
# `bin/openbabel-3.dll`.
#
# WHY `bin/` AND NOT WHERE THE PACKAGE SAYS. `openbabel/__init__.py` sets
# BABEL_LIBDIR to `<pkg>/lib/openbabel/3.1.0` and BABEL_DATADIR to
# `<pkg>/share/openbabel/3.1.0` -- and the wheel HAS NO `lib/` DIRECTORY AT
# ALL. Both env vars point at paths that do not exist, and Open Babel falls
# back to looking beside its own DLL, which is `bin/`. That fallback is what
# actually works in a source checkout, so the frozen build has to reproduce
# `bin/` faithfully rather than trust the documented variables.
#
# Missing, this fails in one specific place and nowhere else: `pybel` is
# imported lazily inside `docking_providers.dock()`, and with no format
# plugins `GetSupportedInputFormat()` returns entries that pybel's
# `_formatstodict` cannot split, so DOCKING dies with
# "ValueError: not enough values to unpack (expected 2, got 1)" -- an error
# that mentions neither Open Babel nor a missing file. Everything else in the
# application keeps working.
datas += collect_data_files(
    "openbabel", includes=["bin/*.obf", "bin/data/*", "share/**"]
)

# --------------------------------------------------------------------------
# Install self-check manifest
# --------------------------------------------------------------------------
# What the spec removes from the data entries above. ONE list, used by `_keep`
# below and by the manifest, so the two cannot disagree about what ships.
DROPPED_PREFIXES = ("openchem/chem/data/regulatory/sources/",)

# The app checks its own data files against the hash and size each had when
# this build was made (openchem/install_check.py; it reports, never repairs).
# The manifest is made HERE, from the `datas` list itself, so there is no second
# hand-written map of source path to installed path. It must exist before
# Analysis runs (it is collected as an ordinary module, so it lives in the exe's
# archive), and `build.ps1` deletes it afterwards and refuses to start if one is
# already lying around.
sys.path.insert(0, str(PKG.parent))
from openchem import install_check  # noqa: E402 -- needs the path line above

_INTEGRITY_MODULE = PKG / "_integrity.py"
install_check.write_module_atomically(
    _INTEGRITY_MODULE,
    install_check.build_manifest(datas, PKG, drop_prefixes=DROPPED_PREFIXES),
)

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
    if dest.startswith(DROPPED_PREFIXES):
        return False  # the hand-edited input; see the chem/data entry above
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
