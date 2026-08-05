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
    InterpreterSidecar,
    ManagedAsset,
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
                "ADMET-AI predicts hERG blockade, CYP450 inhibition and Ames mutagenicity "
                "-- endpoints that genuinely need a trained model, with no honest "
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
