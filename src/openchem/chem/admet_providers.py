"""ADMET endpoint prediction via ADMET-AI, run out of process.

ADMET-AI (Swanson et al., MIT) is a multi-task chemprop model trained on
the Therapeutics Data Commons ADMET suite. It gives this app the two
endpoints repeatedly deferred as impossible: hERG blockade and CYP450
inhibition.

WHY OUT OF PROCESS. It needs torch, pytorch-lightning and chemprop -- a
~1 GB environment. That has no business in this project's dependency tree
or in the frozen PyInstaller build, so it lives in its own environment in
the data directory, exactly as pkasolver does. Unlike pkasolver
it resolves cleanly against modern Python (verified on 3.12 and 3.13) and
its weights ship inside the wheel, so there is no separate download and
no version archaeology.

THESE ARE PREDICTIONS, NOT MEASUREMENTS. Every value here is a model
output with real uncertainty, and this module does not dress it up as
anything else. The rule-based `hERG Risk Factors (not a prediction)`
checklist in `descriptor_providers.py` stays exactly where it is: it is
free, always available, and says which structural correlates are present
rather than guessing a probability. The two answer different questions.

Spike result, measured 2026-08-03 on the real model before any of this
was wired up -- astemizole, cisapride and terfenadine were all withdrawn
for QT prolongation via hERG block:

    astemizole   0.995      metformin     0.049
    cisapride    0.977      paracetamol   0.096
    terfenadine  0.970

An order of magnitude between known positives and known negatives, which
is what justified shipping it at all.
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

from rdkit import Chem

logger = logging.getLogger("openchem.chemistry")

#: Settings key holding the path to a Python interpreter with admet-ai
#: installed. Configured via Tools -> External Tools, same as pkasolver.
ADMET_PYTHON_SETTING = "admet/admet_python_path"

_RUNNER = Path(__file__).resolve().parent / "admet_runner.py"

#: The model ensemble loads on every invocation (see admet_runner's
#: docstring for why). Generous enough to survive a cold filesystem cache,
#: short enough not to hang a calculator forever.
_TIMEOUT_SECONDS = 300

#: The endpoints surfaced in the UI, out of the 104 the model emits.
#: Deliberately a curated subset: the raw output includes a
#: `_drugbank_approved_percentile` twin for every endpoint plus the whole
#: physicochemical block this app already computes better from RDKit, and
#: showing all 104 would bury the two that were actually asked for.
#:
#: Keys are ADMET-AI's own column names; values are what a chemist reads.
REPORTED_ENDPOINTS: dict[str, str] = {
    "hERG": "hERG blockade",
    "CYP1A2_Veith": "CYP1A2 inhibition",
    "CYP2C9_Veith": "CYP2C9 inhibition",
    "CYP2C19_Veith": "CYP2C19 inhibition",
    "CYP2D6_Veith": "CYP2D6 inhibition",
    "CYP3A4_Veith": "CYP3A4 inhibition",
    "CYP2C9_Substrate_CarbonMangels": "CYP2C9 substrate",
    "CYP2D6_Substrate_CarbonMangels": "CYP2D6 substrate",
    "CYP3A4_Substrate_CarbonMangels": "CYP3A4 substrate",
    "AMES": "Ames mutagenicity",
}


def admet_available(interpreter_path: str | None) -> bool:
    """Whether a configured interpreter exists and looks usable.

    Deliberately cheap -- existence only, no subprocess. `compute_admet`
    reports the real failure if the environment is broken, and a UI that
    spawns a torch import to grey out a menu item would be unusable.
    """
    if not interpreter_path or not str(interpreter_path).strip():
        return False
    return Path(str(interpreter_path).strip()).is_file()


def compute_admet(mol: Chem.Mol, interpreter_path: str | None) -> dict[str, float] | None:
    """Predicted ADMET endpoints, or None when no environment is set up.

    None means "not configured", which callers present as an offer to
    install. A configured-but-broken environment raises instead, because
    that is a fault the user needs to see rather than a missing optional.
    """
    if not admet_available(interpreter_path):
        return None
    smiles = Chem.MolToSmiles(mol)
    try:
        completed = subprocess.run(
            [str(interpreter_path), str(_RUNNER), smiles],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"The ADMET model did not finish within {_TIMEOUT_SECONDS}s."
        ) from exc
    except OSError as exc:
        raise RuntimeError(f"Could not run the ADMET environment: {exc}") from exc

    if completed.returncode != 0 and not completed.stdout.strip():
        tail = (completed.stderr or "").strip()[-400:]
        raise RuntimeError(f"The ADMET environment failed:\n{tail}")

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        tail = (completed.stdout or completed.stderr or "").strip()[-400:]
        raise RuntimeError(f"Unreadable output from the ADMET environment:\n{tail}") from exc

    if "error" in payload:
        raise RuntimeError(f"ADMET prediction failed: {payload['error']}")

    endpoints = payload.get("endpoints") or {}
    # Filter here rather than in the runner so that adding an endpoint to
    # REPORTED_ENDPOINTS needs no change on the far side of the process
    # boundary.
    return {k: v for k, v in endpoints.items() if k in REPORTED_ENDPOINTS}


def describe_admet_status(interpreter_path: str | None) -> str:
    if admet_available(interpreter_path):
        return f"Found: {interpreter_path} - press Test to verify"
    return (
        "Not configured. ADMET-AI predicts hERG blockade, CYP450 inhibition and "
        "Ames mutagenicity -- endpoints that need a trained model, with no honest "
        "rule-based substitute. Like pkasolver it needs its own Python environment "
        "(~1 GB, mostly PyTorch), so it is installed separately rather than shipped."
    )
