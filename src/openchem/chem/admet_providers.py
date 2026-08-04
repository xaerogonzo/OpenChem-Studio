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

THAT SPIKE WAS EASIER THAN IT LOOKED, and the follow-up is the part worth
reading before trusting a number. Those five compounds put every blocker
among the large drugs and every non-blocker among the small ones, so the
prediction correlated with heavy-atom count at **r = +0.98** -- a model
that had learnt nothing but "big lipophilic molecules block hERG" scores
identically on it.

Re-measured on 19 compounds chosen to break that confound (large drugs
with no hERG liability, small ones with real liability), 2026-08-04:

    accuracy at a 0.5 threshold      15/19
    r(prediction, heavy atoms)       +0.82
    r(prediction, logP)              +0.75

    false alarms   atorvastatin 0.766   fexofenadine 0.698   cetirizine 0.552
    missed         sotalol      0.215

**THE ERRORS ARE THE CONFOUND.** Every false alarm is a large, lipophilic
molecule that does not block hERG; the single miss is a small, hydrophilic
one that does -- sotalol, a class III antiarrhythmic whose therapeutic
mechanism IS hERG block, scored 0.215. Where size and lipophilicity point
the right way the model is excellent; where they mislead, it follows them.

There IS signal beyond that, and the cleanest evidence is terfenadine
0.970 against fexofenadine 0.698. Fexofenadine is terfenadine's own
carboxylic-acid metabolite -- slightly larger, same scaffold -- marketed
precisely because terfenadine's hERG block proved fatal. A pure
size/scaffold model must score them alike; this one separates them by
0.27. It still puts fexofenadine on the wrong side of 0.5.

So: treat a high score on a large lipophilic compound as weak evidence,
and do not read a low score on a small polar one as safety. The
rule-based checklist is a useful second opinion precisely because it says
which structural factors are present instead of folding them into one
number. `benchmarks/docking/herg_sizematched.py` reruns the table.

Note these figures are NOT comparable to ADMET-AI's own published
performance, which is measured on TDC's held-out test set. This panel is
small and deliberately adversarial; it is a probe for one specific
failure mode, not an accuracy benchmark.

THE CYP ENDPOINTS HOLD UP MUCH BETTER, which is worth saying plainly
rather than letting the hERG caveat tar them. Measured 2026-08-04 on 22
drugs, five isoforms each (`benchmarks/docking/cyp_panel.py`):

    r(prediction, heavy atoms)   +0.24   (hERG: +0.82)
    r(prediction, logP)          +0.54   (hERG: +0.75)
    known inhibitors, mean peak   0.696
    renally-cleared drugs         0.071

The size confound that dominates hERG is largely absent here, and the
residual logP correlation is chemically expected rather than an artefact
-- lipophilicity genuinely drives CYP binding.

**THE PREDICTIONS ARE ISOFORM-SPECIFIC**, which is the whole clinical
point and did not have to be true. Correlations between the five isoform
predictions across compounds average +0.40 and range from -0.10
(1A2 vs 2C9, essentially independent) to +0.85 (2C19 vs 2C9). This is not
one "CYP-ness" score wearing five labels. That test needs no ground truth
at all -- it is computed from the model's own outputs. The isoforms that
do move together (2C19/2C9/3A4) are the ones with genuinely overlapping
substrate preferences.

Asked which isoform a selective inhibitor hits hardest, it ranks 8 of 11
correctly against about 2.2 by chance -- every azole and macrolide to
3A4, three of four SSRIs to 2D6, fluvoxamine to 1A2.

THE FAILURE MODE IS DETECTION, NOT RANKING. Two known inhibitors are
scored inactive on every isoform: clarithromycin 0.05 and ciprofloxacin
0.03. Clarithromycin is a textbook strong 3A4 inhibitor, and a ranking
metric flatters it because 3A4 is still its highest of five near-zero
numbers. So a LOW CYP score is the one to distrust; a high score is
well supported here.

One leak worth knowing: quinidine's SUBSTRATE prediction peaks on 2D6
(0.62) when it is a 3A4 substrate that merely INHIBITS 2D6 -- so the
substrate and inhibition endpoints are not perfectly disentangled.
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


def describe_admet_test(interpreter_path: str | None) -> str:
    """Run one real prediction and report it as a sentence.

    Lives here rather than in the dialog because it needs RDKit, and the
    UI layer may not import chemistry engines directly -- enforced by
    `tests/test_layering.py`. `stout_providers.describe_stout_test`
    already set this precedent.

    Astemizole rather than something inert: it was withdrawn for QT
    prolongation via hERG block, so a working model must score it HIGH. A
    self-test that passed on a molecule with no liability would prove only
    that the plumbing runs, which is the weaker of the two things worth
    knowing.
    """
    from rdkit import Chem

    astemizole = "COc1ccc(CCN2CCC(Nc3nc4ccccc4n3Cc3ccc(F)cc3)CC2)cc1"
    endpoints = compute_admet(Chem.MolFromSmiles(astemizole), interpreter_path)
    if endpoints is None:
        return "No interpreter configured."
    herg = endpoints.get("hERG")
    if herg is None:
        return "The model ran but produced no hERG value."
    if herg > 0.5:
        return (
            f"Working: astemizole hERG = {herg:.3f}, as expected for a drug "
            f"withdrawn for QT prolongation."
        )
    return (
        f"Ran, but astemizole scored only {herg:.3f} for hERG. It is a known "
        f"blocker, so this environment is suspect - try Set Up Automatically again."
    )
