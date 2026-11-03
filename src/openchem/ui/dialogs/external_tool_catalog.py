"""What each obtainable tool tab says and does.

The four descriptors here are almost entirely PRESENTATION -- tab titles,
multi-paragraph explanatory copy, and the body of each download
confirmation. That is why they live in `ui/` rather than next to
`services/sidecar_inventory.py`, which was the other candidate: that
module's job is what is on disk and how to remove it, and it has no
business owning user-facing prose. The two are joined by the component
`key` string, which `sidecar_inventory.find()` already takes.

Every confirmation body keeps its exact previous wording. This app's
download policy is to show what, from where and how big, then wait for an
explicit yes -- and the message text IS that policy, not a description of
it.

Built by function call rather than as module-level constants so the setup
services are imported only when the dialog is actually opened, which is
the lazy-import discipline the dialog already followed.
"""

from __future__ import annotations

from openchem.ui.dialogs.external_tool_tabs import (
    CAUTION,
    MUTED,
    Blocked,
    ExtraPath,
    InterpreterSidecar,
    ManagedAsset,
    ManagedExecutable,
    Note,
)


def java() -> ManagedAsset:
    import openchem.services.java_setup as java_setup

    def blocked() -> Blocked | None:
        existing = java_setup.system_java_home()
        if existing is None:
            return None
        # Not a failure: a Java already on this machine is always
        # preferred over installing another, so say so as good news.
        return Blocked(
            "Java already available",
            f"Java is already installed at {existing}.",
            severity="information",
        )

    def confirm_body() -> str:
        return (
            "Download a portable Java runtime?\n\n"
            f"Source: Eclipse Temurin {java_setup.FEATURE_VERSION} (JRE), via the official "
            "Adoptium release API\n"
            f"Download: about {java_setup.APPROX_DOWNLOAD_MB} MB\n"
            f"Location: {java_setup.default_install_root()}\n\n"
            "Extracted, not installed - no installer runs and no system setting changes. "
            "This unblocks OPSIN (name-to-structure parsing).\n\n"
            "Continue?"
        )

    return ManagedAsset(
        key="java",
        title="Java (Temurin)",
        action_label="Set Up Automatically...",
        remove_label="the Java runtime",
        describe_status=java_setup.describe_status,
        blocked=blocked,
        confirm_title="Install a Java runtime",
        confirm_body=confirm_body,
        run=lambda on_progress: java_setup.install(
            java_setup.default_install_root(), on_progress=on_progress
        ),
        errors=java_setup.JavaSetupError,
        finished_status=lambda home: f"Installed and verified: {home}",
        success_title="Java ready",
        success_message=lambda home: f"Runtime installed at\n{home}\n\nOPSIN can now run.",
        failure_title="Java setup failed",
        failure_status_prefix="Setup failed",
        notes=(
            Note(
                "OPSIN needs Java: it is a Java library, reached through py2opsin, and "
                "OPSIN (name-to-structure) is a Java library. Without it both are unavailable, and "
                "the error each gives on its own names neither Java nor the fix."
            ),
            Note(
                "Eclipse Temurin publishes PORTABLE archives, so this extracts a runtime into this "
                "app's data folder rather than running an installer. Nothing is registered, no "
                "system setting is changed, and deleting the folder removes it completely. A Java "
                "already on this machine is always preferred over installing another.",
                MUTED,
            ),
        ),
    )


def nmr_database() -> ManagedAsset:
    import openchem.services.nmr_database_setup as nmr_setup

    def confirm_body() -> str:
        return (
            "Download nmrshiftdb2 and build the shift index?\n\n"
            f"Source: {nmr_setup.SOURCE_FILE} from the nmrshiftdb2 project on SourceForge "
            "(open content)\n"
            f"Download: about {nmr_setup.APPROX_DOWNLOAD_MB} MB\n"
            "Kept afterwards: about 15 MB - the download is discarded once indexed\n\n"
            "Indexing takes a few minutes: every assigned atom is coded at six environment "
            "depths, so a lookup can widen when the most specific one has too little "
            "evidence.\n\n"
            "Continue?"
        )

    def success_message(stats) -> str:
        return (
            f"{stats.molecules:,} molecules\n"
            f"{stats.measurements:,} assigned shifts\n"
            f"{stats.environments:,} environments indexed"
        )

    return ManagedAsset(
        key="nmr_index",
        title="NMR Database",
        action_label="Build Index...",
        remove_label="the NMR shift database",
        describe_status=nmr_setup.describe_status,
        confirm_title="Build the NMR shift index",
        confirm_body=confirm_body,
        run=lambda on_progress: nmr_setup.build(on_progress=on_progress),
        errors=nmr_setup.NmrDatabaseSetupError,
        # The service's own status line already counts what was indexed,
        # so re-reading it beats restating it and cannot disagree with it.
        finished_status=lambda _stats: nmr_setup.describe_status(),
        success_title="NMR index built",
        success_message=success_message,
        failure_title="NMR index build failed",
        failure_status_prefix="Build failed",
        notes=(
            Note(
                "Predicts NMR shifts by looking each atom's environment up in assigned experimental "
                "spectra, rather than computing them - instant, where the ab initio path takes "
                "minutes. It also reports a per-atom confidence earned from how many measurements "
                "matched and how well they agree."
            ),
            Note(
                "Held-out accuracy, measured on molecules excluded from the index: 1.12 ppm mean "
                "error on atoms rated 'good', 3.36 on 'medium', 10.00 on 'rough'. The rating is "
                "worth reading - it is the difference between a number to trust and one to check. "
                "Coverage is not universal: an environment the database has never seen gets no "
                "prediction rather than a guess.",
                MUTED,
            ),
        ),
    )


def pkasolver() -> InterpreterSidecar:
    from openchem.chem.pka_providers import PKASOLVER_PYTHON_SETTING, describe_pka_status
    from openchem.services import pkasolver_setup as setup

    def blocked() -> Blocked | None:
        if setup.find_uv() or setup.find_fallback_python():
            return None
        return Blocked("Cannot set up automatically", setup.describe_prerequisites())

    def confirm_body() -> str:
        return (
            f"Build a pkasolver environment?\n\n"
            f"Location: {setup.default_install_root()}\n"
            f"Downloads: roughly {setup.APPROX_DOWNLOAD_MB} MB\n"
            f"Disk space when finished: about {setup.APPROX_DISK_GB} GB\n\n"
            f"Sources:\n"
            f"  • PyTorch {setup.TORCH_VERSION} (CPU) — download.pytorch.org\n"
            f"  • torch-scatter / torch-sparse — data.pyg.org (prebuilt wheels)\n"
            f"  • torch-geometric, numpy, scipy, pandas, rdkit — PyPI\n"
            f"  • pkasolver + trained models — {setup.PKASOLVER_REPO}\n\n"
            f"{setup.describe_prerequisites()}\n\n"
            f"This takes several minutes. Continue?"
        )

    return InterpreterSidecar(
        key="pkasolver",
        title="pkasolver (pKa)",
        setting_key=PKASOLVER_PYTHON_SETTING,
        action_label="Set Up Automatically...",
        remove_label="the pkasolver environment",
        browse_title="Select the pkasolver environment folder",
        locate_root=setup.default_install_root,
        test_label="Test (predicts acetic acid's pKa)...",
        testing_status="Testing (loading models, this can take a minute)...",
        describe_test=describe_pka_status,
        test_errors=RuntimeError,
        prerequisites=setup.describe_prerequisites,
        blocked=blocked,
        confirm_title="Set up pkasolver",
        confirm_body=confirm_body,
        run=lambda on_progress: setup.install(
            setup.default_install_root(), on_progress=on_progress
        ),
        errors=setup.PkasolverSetupError,
        finished_status=lambda _interpreter: (
            "Set up and verified - numeric pKa and Henderson-Hasselbalch LogD are now available."
        ),
        success_title="pkasolver ready",
        success_message=lambda interpreter: (
            f"Environment built and verified with a real prediction.\n\n{interpreter}"
        ),
        failure_title="pkasolver setup failed",
        failure_status_prefix="Setup failed",
        notes=(
            Note(
                "Unlike Vina and ORCA this is a Python interpreter, not an executable. "
                "pkasolver needs numpy<2 while OpenChem Studio runs numpy 2.x, so it "
                "runs out of process in its own virtual environment rather than being "
                "installed alongside the app."
            ),
            Note(
                "'Set Up Automatically' builds the whole environment for you and fills in the "
                "path above — it will show you exactly what gets downloaded first. If you would "
                "rather do it by hand: a Python 3.10–3.12 environment (NOT this app's own 3.13 — "
                "PyTorch 2.3.0 publishes no wheels for it) containing torch==2.3.0 (CPU), "
                "torch-geometric==2.0.1, torch-scatter and torch-sparse from "
                "https://data.pyg.org/whl/torch-2.3.0+cpu.html (prebuilt, no compiler needed), "
                "numpy<2, scipy<1.14, pandas, rdkit, plus github.com/mayrf/pkasolver on its "
                "import path. Those exact pins matter — newer torch-geometric cannot load "
                "pkasolver's trained models at all."
            ),
            Note(
                "Without this, pH-dependent protonation (Charge category) still works via "
                "Dimorphite-DL, and LogD falls back to a clearly-labelled approximation."
            ),
        ),
    )


def admet() -> InterpreterSidecar:
    """Deliberately the same shape as the pkasolver tab.

    Both are "a Python interpreter, not an executable", and making them
    look different would imply a difference that is not there. This one is
    the simpler of the two: no pinned scientific stack to explain, because
    admet-ai resolves against modern Python with nothing to fight, and its
    weights ship inside the wheel.
    """
    from openchem.chem.admet_providers import ADMET_PYTHON_SETTING, describe_admet_test
    from openchem.services import admet_setup as setup

    def blocked() -> Blocked | None:
        if setup.find_uv() or setup.find_fallback_python():
            return None
        return Blocked("Cannot set up automatically", setup.describe_prerequisites())

    def confirm_body() -> str:
        return (
            f"Build an ADMET-AI environment?\n\n"
            f"Location: {setup.default_install_root()}\n"
            f"Downloads: roughly {setup.APPROX_DOWNLOAD_MB} MB\n"
            f"Disk space when finished: about {setup.APPROX_DISK_GB} GB\n\n"
            f"Sources:\n"
            f"  - admet-ai and PyTorch, from PyPI\n"
            f"  - Trained weights ship inside the admet-ai wheel, so there is no "
            f"separate model download to fail.\n\n"
            f"{setup.describe_prerequisites()}\n\n"
            f"This takes several minutes. Continue?"
        )

    return InterpreterSidecar(
        key="admet",
        title="ADMET (hERG/CYP)",
        setting_key=ADMET_PYTHON_SETTING,
        action_label="Set Up Automatically...",
        remove_label="the ADMET environment",
        browse_title="Select the ADMET environment folder",
        locate_root=setup.default_install_root,
        test_label="Test (predicts astemizole's hERG)...",
        testing_status="Testing (loading the model, this can take a minute)...",
        describe_test=describe_admet_test,
        test_errors=Exception,
        prerequisites=setup.describe_prerequisites,
        blocked=blocked,
        confirm_title="Set up ADMET-AI",
        confirm_body=confirm_body,
        run=lambda on_progress: setup.install(
            setup.default_install_root(), on_progress=on_progress
        ),
        errors=setup.AdmetSetupError,
        finished_status=lambda _interpreter: (
            "Set up and verified - hERG, CYP and Ames predictions are now available."
        ),
        success_title="ADMET-AI ready",
        success_message=lambda interpreter: (
            f"Environment built and verified with a real prediction.\n\n{interpreter}"
        ),
        failure_title="ADMET setup failed",
        failure_status_prefix="Setup failed",
        notes=(
            Note(
                "ADMET-AI predicts hERG blockade, CYP450 inhibition, Ames mutagenicity "
                "and -- under the calculator's Advanced tier -- Caco-2 permeability, "
                "aqueous solubility, blood-brain barrier penetration, plasma protein "
                "binding, liver injury and LD50, at no extra runtime cost. Endpoints "
                "that genuinely need a trained model, with no honest "
                "rule-based substitute. Like pkasolver this is a Python interpreter rather "
                "than an executable: it needs PyTorch (~490 MB), which has no business in "
                "this application's own dependency tree or in the frozen build, so it runs "
                "out of process in its own environment."
            ),
            Note(
                "These are PREDICTIONS, not measurements. Measured against drugs withdrawn "
                "for QT prolongation, the model separates them cleanly from safe ones "
                "(astemizole 0.995, cisapride 0.977, terfenadine 0.970; metformin 0.049, "
                "paracetamol 0.096) -- but every value carries real uncertainty, and each "
                "is shown as a probability rather than a verdict.",
                CAUTION,
            ),
            Note(
                "Without this, the rule-based 'hERG Risk Factors (not a prediction)' "
                "checklist still works -- it reports which structural correlates of hERG "
                "liability are present, offline and instantly, instead of guessing a "
                "probability. The two answer different questions and both stay available."
            ),
        ),
    )


#: Why the ORCA tab has no Set Up button. Stated once so the refusal, the
#: dialog title and the failure status cannot drift apart.
_ORCA_NO_AUTOMATION = (
    "ORCA's licence does not permit automated or redirected downloads, so "
    "this app cannot fetch it for you. Use the FACCTS link below, then "
    "Locate Installed or Browse."
)


def _find(root, names: tuple[str, ...]):
    """`PathRow`'s finder: the executable inside a folder the user picked.

    Imported lazily because `sidecar_env` pulls in subprocess machinery
    the catalog otherwise has no use for at import time.
    """
    from openchem.services.sidecar_env import find_program

    return find_program(root, names)


def vina() -> ManagedExecutable:
    """AutoDock Vina: the app can fetch this one.

    Its releases are public, Apache-2.0 executables published by the
    Scripps team on GitHub, so "Download" here really is the same file
    you would fetch from the releases page yourself.
    """
    import openchem.services.sidecar_inventory as sidecar_inventory
    import openchem.services.tool_download_service as tools

    def confirm_body() -> str:
        # The asset is looked up inside `run` rather than here, because
        # this text is built before any network call -- the size and
        # filename this app's download policy requires are shown in the
        # SECOND confirmation, once the release metadata is known.
        return (
            "Look up the latest AutoDock Vina release?\n\n"
            f"Source: {tools.VINA_RELEASES_PAGE}\n"
            "This only reads the release list. Nothing is downloaded until "
            "you confirm the exact file, its size and its URL.\n\n"
            "Continue?"
        )

    return ManagedExecutable(
        key="vina",
        title="AutoDock Vina",
        setting_key=sidecar_inventory.VINA_SETTING,
        browse_title="Select the folder containing Vina",
        finder=lambda root: _find(root, ("vina",)),
        path_description="Vina executable",
        describe_status=tools.describe_vina_status,
        locate=lambda: tools.locate_executable(("vina",), validate=tools.responds_as_vina),
        locate_hint="Look for Vina where installers usually put it.",
        test_label="Test (runs vina --version)...",
        testing_status="Running Vina...",
        describe_test=tools.verify_vina,
        test_errors=tools.ToolVerificationError,
        action_label="Check for Updates / Download...",
        remove_label="the AutoDock Vina download",
        confirm_title="Download AutoDock Vina",
        confirm_body=confirm_body,
        # Unused: `_VinaTab` overrides the setup click to keep the
        # two-step confirmation this app's download policy requires --
        # look up the release, THEN show the exact file, size and URL.
        run=lambda _on_progress: None,
        errors=RuntimeError,
        finished_status=lambda path: f"Installed: {path}",
        success_title="Download complete",
        success_message=lambda path: f"AutoDock Vina installed to:\n{path}",
        failure_title="Download failed",
        failure_status_prefix="Download failed",
        notes=(
            Note(
                "AutoDock Vina's official releases are public, Apache-2.0-licensed "
                "executables published on GitHub (ccsb-scripps/AutoDock-Vina) -- "
                "downloading one here is the same file you would get from the "
                "releases page yourself."
            ),
            Note(
                "Remove from Disk only ever deletes a copy this app downloaded. If you "
                "pointed the path at your own Vina, it is left alone and the Storage tab "
                "says so.",
                MUTED,
            ),
        ),
    )


def orca() -> ManagedExecutable:
    """ORCA: the app can NOT fetch this one, and says so instead.

    **No Set Up button, deliberately.** ORCA's licence does not permit
    automated or redirected downloads, so a button here could only open a
    browser -- and a "Set Up Automatically" that cannot is worse than an
    honest link. Everything else it shares with the other tabs: a status
    line, Locate, and a Test that runs a real calculation.

    Remove from Disk is absent for the same class of reason: this app never
    installed ORCA, so nothing here has the right to delete it.
    """
    import openchem.services.tool_download_service as tools

    return ManagedExecutable(
        key="orca",
        title="ORCA",
        setting_key="orca/executable_path",
        browse_title="Select the folder ORCA is installed in",
        finder=lambda root: _find(root, ("orca",)),
        path_description="ORCA executable",
        describe_status=tools.describe_orca_status,
        locate=lambda: tools.locate_executable(("orca",), validate=tools.responds_as_orca),
        locate_hint=(
            "Search the usual install locations. Each candidate is RUN before "
            'being accepted -- "ORCA" is a common name and this machine has an '
            "unrelated Orca.exe that would otherwise be picked."
        ),
        test_label="Test (runs a 2-atom calculation)...",
        testing_status="Running a test calculation...",
        describe_test=tools.verify_orca,
        test_errors=tools.ToolVerificationError,
        obtainable=False,
        removable=False,
        vendor_links=(
            ("Get ORCA (FACCTS account required)...", tools.ORCA_DOWNLOAD_PAGE),
            ("ORCA Documentation...", tools.ORCA_DOCS_PAGE),
        ),
        # Unused by a tab that cannot obtain, but `_ToolBase` requires
        # them. Pointed at a refusal rather than at a plausible-looking
        # no-op, so a future change that shows the button fails loudly.
        action_label="Set Up Automatically...",
        remove_label="ORCA",
        confirm_title="ORCA cannot be downloaded automatically",
        confirm_body=lambda: _ORCA_NO_AUTOMATION,
        run=lambda _on_progress: (_ for _ in ()).throw(RuntimeError(_ORCA_NO_AUTOMATION)),
        errors=RuntimeError,
        finished_status=lambda _result: "",
        success_title="",
        success_message=lambda _result: "",
        failure_title="ORCA cannot be downloaded automatically",
        failure_status_prefix="Not available",
        notes=(
            Note(
                'This is the quantum-chemistry program named "ORCA" from FACCTS GmbH -- a '
                "genuinely generic name, easy to confuse with unrelated software. Its "
                'downloads used to live on a Max Planck-hosted "orcaforum" site; that link '
                "is now dead. FACCTS' own customer portal (free registration required) is "
                "the current, correct source -- OpenChem Studio can't fetch it "
                "automatically because ORCA's license doesn't allow automated/redirected "
                "downloads."
            ),
            Note(tools.describe_orca_platform_hint()),
            Note(
                "After installing, use Locate Installed or Browse to point at the ORCA "
                'executable above -- usually "orca.exe" (Windows) or "orca" (Linux/macOS) '
                "inside wherever you extracted it. Install it somewhere with no spaces in "
                "the path: ORCA's own launcher mis-handles them.",
                MUTED,
            ),
        ),
    )


#: Why the Psi4 tab has no Set Up button (locate-only: Alex, 2026-10-19). Stated once so the refusal, the dialog title and the failure status cannot drift apart.
_PSI4_NO_AUTOMATION = (
    "OpenChem Studio does not download Psi4. Install it from the Psi4 project's install page, "
    "then use Locate Installed or Browse to point at it."
)


def psi4() -> ManagedExecutable:
    """Psi4: a second quantum-chemistry engine the user installs and points at (`docs/PSI4_ENGINE_DESIGN.md`).

    **Locate-only, deliberately** (Alex, 2026-10-19): Psi4 is LGPL and could be fetched, but a pinned download is a commitment this version does not make, so there is no Set Up button
    and no Remove from Disk (this app never installed it). Everything else is the ORCA tab's: a status line, Locate, Browse and a Test that runs a real two-atom calculation.
    Locate RUNS each candidate (`psi4 --version`) before accepting it, so another program of that name is not picked.
    """
    import openchem.services.tool_download_service as tools

    return ManagedExecutable(
        key="psi4",
        title="Psi4",
        setting_key="psi4/executable_path",
        browse_title="Select the folder Psi4 is installed in",
        finder=lambda root: _find(root, ("psi4",)),
        path_description="Psi4 executable",
        describe_status=tools.describe_psi4_status,
        locate=lambda: tools.locate_executable(("psi4",), validate=tools.responds_as_psi4),
        locate_hint=(
            "Search the usual install locations. Each candidate is RUN with --version before being accepted -- "
            "a program that merely shares the name would otherwise be picked."
        ),
        test_label="Test (runs a 2-atom calculation)...",
        testing_status="Running a test calculation...",
        describe_test=tools.verify_psi4,
        test_errors=tools.ToolVerificationError,
        obtainable=False,
        removable=False,
        vendor_links=(
            ("Get Psi4...", tools.PSI4_DOWNLOAD_PAGE),
            ("Psi4 Documentation...", tools.PSI4_DOCS_PAGE),
        ),
        # Unused by a tab that cannot obtain, but `_ToolBase` requires them (the ORCA tab's reason).
        action_label="Set Up Automatically...",
        remove_label="Psi4",
        confirm_title="Psi4 is not downloaded by this app",
        confirm_body=lambda: _PSI4_NO_AUTOMATION,
        run=lambda _on_progress: (_ for _ in ()).throw(RuntimeError(_PSI4_NO_AUTOMATION)),
        errors=RuntimeError,
        finished_status=lambda _result: "",
        success_title="",
        success_message=lambda _result: "",
        failure_title="Psi4 is not downloaded by this app",
        failure_status_prefix="Not available",
        notes=(
            Note(
                "Psi4 is an open-source quantum-chemistry program (LGPL-3.0) that runs single-point energies and geometry "
                "optimizations here, as a second engine beside ORCA; choose it with the Engine box on the Quantum Chemistry panel. "
                "It runs natively on Windows: the project's install page offers a command-line installer and a conda package. "
                "A full install is large -- about 2 GB on disk (measured with the conda package, whose download is about 330 MB)."
            ),
            Note(
                "After installing, use Locate Installed or Browse to point at the folder it was installed in; the app finds "
                '"psi4.exe" inside it (with conda, in the Scripts folder of the environment). Unlike ORCA, a path with spaces is fine.',
                MUTED,
            ),
        ),
    )


#: Why the xtb tab has no Set Up button (locate-only, as Psi4's is). Stated once so the refusal, the dialog title and the failure status cannot drift apart.
_XTB_NO_AUTOMATION = (
    "OpenChem Studio does not download xtb. Get the Windows build from the xtb project's releases page, "
    "then use Locate Installed or Browse to point at it."
)


def xtb() -> ManagedExecutable:
    """xtb: a third quantum-chemistry engine, the fast tight-binding one, which the user installs and points at (`docs/EXTERNAL_TOOL_CANDIDATES.md`).

    **Locate-only, deliberately**, as Psi4's is: a pinned download is a commitment this version does not make, and the Windows build is labelled a pre-release by its own project.
    Everything else is the ORCA tab's: a status line, Locate, Browse and a Test that runs a real two-atom calculation through the engine's own input and command.
    Locate RUNS each candidate (`xtb --version`) before accepting it, so another program of that name is not picked.
    """
    import openchem.services.tool_download_service as tools

    return ManagedExecutable(
        key="xtb",
        title="xtb",
        setting_key="xtb/executable_path",
        browse_title="Select the folder xtb is installed in",
        finder=lambda root: _find(root, ("xtb",)),
        path_description="xtb executable",
        describe_status=tools.describe_xtb_status,
        locate=lambda: tools.locate_executable(("xtb",), validate=tools.responds_as_xtb),
        locate_hint=(
            "Search the usual install locations. Each candidate is RUN with --version before being accepted -- "
            "a program that merely shares the name would otherwise be picked."
        ),
        test_label="Test (runs a 2-atom calculation)...",
        testing_status="Running a test calculation...",
        describe_test=tools.verify_xtb,
        test_errors=tools.ToolVerificationError,
        obtainable=False,
        removable=False,
        vendor_links=(
            ("Get xtb...", tools.XTB_DOWNLOAD_PAGE),
            ("xtb Project Page...", tools.XTB_DOCS_PAGE),
        ),
        # Unused by a tab that cannot obtain, but `_ToolBase` requires them (the ORCA tab's reason).
        action_label="Set Up Automatically...",
        remove_label="xtb",
        confirm_title="xtb is not downloaded by this app",
        confirm_body=lambda: _XTB_NO_AUTOMATION,
        run=lambda _on_progress: (_ for _ in ()).throw(RuntimeError(_XTB_NO_AUTOMATION)),
        errors=RuntimeError,
        finished_status=lambda _result: "",
        success_title="",
        success_message=lambda _result: "",
        failure_title="xtb is not downloaded by this app",
        failure_status_prefix="Not available",
        notes=(
            Note(
                "xtb is an open-source semi-empirical (tight-binding) quantum-chemistry program that runs single-point energies, geometry "
                "optimizations and frequency analyses here with GFN2-xTB or GFN1-xTB, as a third engine beside ORCA and Psi4; choose it with the "
                "Engine box on the Quantum Chemistry panel. It is far faster than DFT and less accurate. Measured against ORCA B3LYP/def2-SVP on "
                "20 molecules (2026-10-27): its structures are close (median heavy-atom deviation 0.014 A, worst 0.26 A, aspirin), so treat one as a "
                "quick, rough structure; its energy differences are not for ranking isomers or conformers (about 0.8 kcal/mol off over conformer "
                "pairs, about 4 over isomer pairs, and 82% of clearly separated pairs in the right order); and starting an ORCA optimization from "
                "an xtb structure did not reduce its cycles."
            ),
            Note(
                "After downloading the Windows build from the releases page and unzipping it, use Locate Installed or Browse to point at the "
                'folder; the app finds "xtb.exe" inside it (in its bin folder, beside the DLL it needs). A path with spaces is fine.',
                MUTED,
            ),
        ),
    )


#: Why the AiZynthFinder tab has no Set Up button (locate-only: Alex, 2026-10-19). Stated once so the refusal, the dialog title and the failure status cannot drift apart.
_AIZYNTH_NO_AUTOMATION = (
    "OpenChem Studio does not download or install the synthesis planner. Install AiZynthFinder in an environment of your own, "
    "run its download_public_data command, then point this tab at that environment's Python and the configuration file it wrote."
)


def aizynthfinder() -> ManagedExecutable:
    """AiZynthFinder: the synthesis planner, a Python environment the user installs and points at (`docs/SYNTHESIS_HELPER_DESIGN.md`).

    **Locate-only, deliberately** (Alex, 2026-10-19), and **two paths rather than one**: the environment's Python and the configuration file `download_public_data` wrote, because
    the planner is a Python package with its own interpreter requirements (3.10 to 3.12, `numpy<2`) that OpenChem's interpreter does not share. The status line only reads the two paths;
    the Test button runs a real trivial search, stopping at the first thing it can name (a missing Python, a Python without the planner, a model, a template file or the stock that is not where
    the configuration says). Nothing here starts a download or removes a file.
    """
    import openchem.services.synthesis_planner_setup as planner

    return ManagedExecutable(
        key="aizynthfinder",
        title="AiZynthFinder",
        setting_key=planner.PYTHON_KEY,
        browse_title="Select the folder of the Python environment AiZynthFinder is installed in",
        finder=planner.find_python,
        path_description="Python of the AiZynthFinder environment",
        form_label="Python:",
        extra_paths=(
            ExtraPath(
                setting_key=planner.CONFIG_KEY,
                label="Configuration:",
                browse_title="Select the folder holding AiZynthFinder's config.yml",
                finder=planner.find_config,
                description="AiZynthFinder configuration file (config.yml)",
            ),
        ),
        describe_status=planner.describe_status,
        locate=planner.locate,
        locate_hint=(
            "Look for an AiZynthFinder environment already on this machine: `aizynthcli` on the PATH, and the Python beside it. "
            "The Python found is RUN to confirm that it has AiZynthFinder before it is accepted."
        ),
        test_label="Test (plans a trivial target)...",
        testing_status="Running a trivial search (this starts the planner: allow up to a minute)...",
        describe_test=planner.verify,
        test_with_settings=True,
        test_errors=planner.ToolVerificationError,
        obtainable=False,
        removable=False,
        vendor_links=(
            ("Get AiZynthFinder...", planner.PROJECT_PAGE),
            ("AiZynthFinder Documentation...", planner.DOCS_PAGE),
        ),
        # Unused by a tab that cannot obtain, but `_ToolBase` requires them (the ORCA tab's reason).
        action_label="Set Up Automatically...",
        remove_label="AiZynthFinder",
        confirm_title="AiZynthFinder is not downloaded by this app",
        confirm_body=lambda: _AIZYNTH_NO_AUTOMATION,
        run=lambda _on_progress: (_ for _ in ()).throw(RuntimeError(_AIZYNTH_NO_AUTOMATION)),
        errors=RuntimeError,
        finished_status=lambda _result: "",
        success_title="",
        success_message=lambda _result: "",
        failure_title="AiZynthFinder is not downloaded by this app",
        failure_status_prefix="Not available",
        notes=(
            Note(
                "AiZynthFinder is an open-source retrosynthesis planner (MIT licence): it proposes routes from the molecule you draw to compounds in a stock. "
                "It runs here as a separate program in an environment of its own, never inside OpenChem Studio, because it needs Python 3.10 to 3.12 and "
                "numpy below version 2. A route it returns is a hypothesis from a program trained on patent reactions: it gives no conditions or yields, "
                "and nobody has run it."
            ),
            Note(
                "Installing it is about 1 GB for the environment and about 750 MB for the models and stock that its download_public_data command fetches, "
                "and a search needs about 2.75 GB of memory with a small stock and up to 5 GB with the ZINC stock. A fresh install needs the extra pin "
                "pyarrow below version 21 (pip install \"pyarrow<21\") or it will not import. The models and the stock it fetches are published under "
                "their own licences; read them before using them.",
            ),
            Note(
                "After installing, point the first row at the environment's Python (Browse takes the environment's folder and finds the Python in it) and the second at the "
                "config.yml that download_public_data wrote. The Test button runs a real search of aspirin for a few iterations: the start-up alone takes about "
                "20 seconds. Which expansion policy, stock and filter to use is read from that file: by default the uspto policy, the zinc stock "
                "(or the first the file lists) and no filter, the configuration the project's benchmark ran.",
                MUTED,
            ),
        ),
    )


#: Why the Knowledge Vista tab has no Set Up button: it is a separate program this app neither installs nor owns. Stated once so the refusal, the
#: dialog title and the failure status cannot drift apart.
_KV_NO_AUTOMATION = (
    "Knowledge Vista is a separate program that OpenChem Studio does not install for you. Get it from its project page, "
    "then use Locate Installed or Browse to point at the `kv` executable."
)


def knowledge_vista() -> ManagedExecutable:
    """Knowledge Vista (`kv`): an OPTIONAL companion that keeps track of where the PDFs a project reads are, however they are renamed.

    **Nothing in OpenChem Studio needs it.** The tab says so, because every other tab here is a tool some feature cannot run without,
    and this one is the exception. Like ORCA it is not fetched by this app -- it is a separate program with its own project and
    release -- so there is no Set Up button and no Remove from Disk, only Locate, Browse, a Test that asks the program what it is, and
    a link to its page.
    """
    import openchem.services.knowledge_vista as kv
    import openchem.services.tool_download_service as tools

    return ManagedExecutable(
        key="knowledge_vista",
        title="Knowledge Vista",
        setting_key=kv.SETTING_KEY,
        browse_title="Select the folder Knowledge Vista (kv) is installed in",
        finder=lambda root: _find(root, ("kv",)),
        path_description="Knowledge Vista executable (kv)",
        describe_status=kv.describe_status,
        locate=lambda: tools.locate_executable(("kv",), validate=kv.responds_as_knowledge_vista),
        locate_hint=(
            "Search the usual install locations. Each candidate is RUN with `capabilities` before being accepted -- "
            '"kv" is a short name and an unrelated program of that name would otherwise be picked.'
        ),
        test_label="Test (asks kv what it is)...",
        testing_status="Asking Knowledge Vista what it is...",
        describe_test=kv.verify,
        test_errors=kv.KnowledgeVistaUnavailable,
        obtainable=False,
        removable=False,
        vendor_links=(("Get Knowledge Vista...", kv.PROJECT_PAGE),),
        action_label="Set Up Automatically...",
        remove_label="Knowledge Vista",
        confirm_title="Knowledge Vista cannot be installed from here",
        confirm_body=lambda: _KV_NO_AUTOMATION,
        run=lambda _on_progress: (_ for _ in ()).throw(RuntimeError(_KV_NO_AUTOMATION)),
        errors=RuntimeError,
        finished_status=lambda _result: "",
        success_title="",
        success_message=lambda _result: "",
        failure_title="Knowledge Vista cannot be installed from here",
        failure_status_prefix="Not available",
        notes=(
            Note(
                "Optional. Knowledge Vista indexes a folder of PDFs by what they contain and recognises each file by its content, so a "
                "paper keeps its identity when its file is renamed or moved. It is for people who keep a library of papers: nothing in "
                "OpenChem Studio depends on it, and the application behaves exactly as it did before it existed whether or not it is "
                "set up."
            ),
            Note(
                "Setting it up here only records where `kv` is and lets you check that it works. OpenChem Studio does not send it "
                "documents and does not read its library.",
                MUTED,
            ),
        ),
    )
