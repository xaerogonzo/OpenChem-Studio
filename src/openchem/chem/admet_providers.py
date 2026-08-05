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

AND WE CANNOT MEASURE THEIR ACCURACY OURSELVES, which took a benchmark to
establish and is the single most important thing to know before quoting a
number from here. ADMET-AI ships models trained on ALL of the TDC data
(their `train_tdc_admet_all.py`), separately from the scaffold-split
models they publish leaderboard figures for. So there is no TDC molecule
the shipped weights have not seen, and a TDC "test set" measures
memorisation. Measured AUROC came in above the vendor's own published
AUROC on 13 of 13 endpoints, mean +0.059, which is that showing.

Accuracy figures in `REPORTED_ENDPOINTS` are therefore the VENDOR's
held-out numbers, labelled as such. What this project measured for itself
is the confound check -- whether an endpoint beats molecular weight and
logP -- which stays valid because leakage inflates the model without
touching the baselines. `benchmarks/admet/` is the whole argument, and
demoting P-glycoprotein to Research is what it bought.

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

AMES IS THE ONE ENDPOINT WITH A REAL FREE ALTERNATIVE, so it was measured
against that rather than in isolation. Mutagenicity is where structural
alerts genuinely work -- a mutagen usually is or becomes an electrophile,
and electrophiles have recognisable substructures. Measured 2026-08-04
over 26 compounds (15 standard reference mutagens and Ames-positive
drugs, 11 with clean records), against eight textbook alert classes plus
a fused-ring rule (`benchmarks/docking/ames_panel.py`):

    ADMET-AI model      14 TP  10 TN  1 FP  1 FN     92%
    structural alerts   14 TP  10 TN  1 FP  1 FN     92%

An exact tie -- **but they fail on different compounds**, which is the
useful part. All four disagreements are instructive:

    aflatoxin B1   model right; no static alert catches it, because its
                   electrophile is an epoxide formed metabolically
    procarbazine   alerts right (hydrazine); model scored it 0.40
    paracetamol    model right; the N-aryl amide alert over-fires on a
                   drug with a clean genotoxicity record
    sucrose        alerts right; model scored it 0.53

So they are complementary rather than redundant, and combining them buys
what neither has alone:

    either flags it    sensitivity 100%   specificity  82%
    both must agree    sensitivity  87%   specificity 100%

For a genotoxicity screen sensitivity is what matters -- a missed mutagen
costs more than a compound needlessly re-tested -- so **treat a hit from
EITHER source as the screen**. The model earns its place here by catching
metabolically-activated mutagens that no substructure can express, not by
being better across the board.

Ames is also the cleanest of the three endpoints on the confound that
ruins hERG: r(prediction, heavy atoms) = -0.14, r(prediction, logP) =
+0.32. Ranked by how size-driven they are -- hERG +0.82, CYP +0.24,
Ames -0.14.
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass
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

#: Suffix ADMET-AI appends to every column to give its percentile against
#: ~2,500 approved drugs. Confirmed against a real run: `predict()` returns
#: 52 properties and 52 of these, which is where "104 columns" comes from.
PERCENTILE_SUFFIX = "_drugbank_approved_percentile"

BASIC = "basic"
ADVANCED = "advanced"
RESEARCH = "research"

#: Tier order, worst-supported last. Selecting a tier includes everything
#: above it, so "advanced" means basic + advanced.
TIERS: tuple[str, ...] = (BASIC, ADVANCED, RESEARCH)


@dataclass(frozen=True)
class Endpoint:
    """One model output, with what is known about whether to believe it.

    `evidence` is shown in the UI next to the number. It is a sentence
    about measurement, not a confidence score -- this project has no way to
    calibrate one of those, and inventing a percentage would be exactly the
    dressing-up this module's header refuses.
    """

    label: str
    tier: str
    units: str = ""
    evidence: str = ""


#: The endpoints surfaced in the UI, out of the 104 the model emits, in
#: three tiers. Keys are ADMET-AI's own column names; labels are what a
#: chemist reads.
#:
#: WHY TIERS RATHER THAN A FLAT LIST. The original ten were curated because
#: the raw output buries them under a percentile twin per endpoint and the
#: whole physicochemical block this app computes better from RDKit. That
#: reasoning still holds for the physchem block, but it also discarded
#: endpoints RDKit CANNOT produce -- Caco-2, solubility, BBB, plasma
#: protein binding, DILI, LD50 -- which cost nothing to add: same
#: subprocess, same model load, results previously dropped on the floor.
#:
#: WHAT PUT EACH ONE IN ITS TIER: `benchmarks/admet/`, run 2026-08-05
#: against TDC's ADMET Benchmark Group. Read its README before changing any
#: assignment here -- particularly the part explaining why the accuracy
#: figures quoted below are the VENDOR's held-out numbers rather than ours.
#:
#: THE SHORT VERSION. ADMET-AI ships models trained on all of TDC (their
#: `train_tdc_admet_all.py`), so we cannot measure held-out accuracy at
#: all: every TDC molecule is a training molecule. Measured AUROC came in
#: above the vendor's published scaffold-split AUROC on 13 of 13 endpoints,
#: mean +0.059, which is that leakage showing.
#:
#: What we CAN measure is whether an endpoint beats a ruler. Leakage
#: inflates the model but not the molecular-weight and logP baselines, so
#: the measured advantage is an upper bound -- and an endpoint that cannot
#: beat a ruler with the answers memorised is a ruler. That is what
#: demoted Pgp below, and it is the hERG size-confound repeating.
REPORTED_ENDPOINTS: dict[str, Endpoint] = {
    # --- Basic: the original ten, unchanged. -----------------------------
    "hERG": Endpoint("hERG blockade", BASIC),
    "CYP1A2_Veith": Endpoint("CYP1A2 inhibition", BASIC),
    "CYP2C9_Veith": Endpoint("CYP2C9 inhibition", BASIC),
    "CYP2C19_Veith": Endpoint("CYP2C19 inhibition", BASIC),
    "CYP2D6_Veith": Endpoint("CYP2D6 inhibition", BASIC),
    "CYP3A4_Veith": Endpoint("CYP3A4 inhibition", BASIC),
    "CYP2C9_Substrate_CarbonMangels": Endpoint("CYP2C9 substrate", BASIC),
    "CYP2D6_Substrate_CarbonMangels": Endpoint("CYP2D6 substrate", BASIC),
    "CYP3A4_Substrate_CarbonMangels": Endpoint("CYP3A4 substrate", BASIC),
    "AMES": Endpoint("Ames mutagenicity", BASIC),

    # --- Advanced: benchmarked, and beats a ruler by a clear margin. -----
    "Caco2_Wang": Endpoint(
        "Caco-2 permeability", ADVANCED, "log(10⁻⁶ cm/s)",
        "Vendor R² 0.71 held out; beats molecular weight and logP by 0.43 here.",
    ),
    "Solubility_AqSolDB": Endpoint(
        "Aqueous solubility", ADVANCED, "log(mol/L)",
        "Vendor R² 0.82 held out; beats molecular weight and logP by 0.18 here.",
    ),
    "HIA_Hou": Endpoint(
        "Human intestinal absorption", ADVANCED, "",
        "Vendor AUROC 0.99 held out; beats molecular weight and logP by 0.16 here.",
    ),
    "BBB_Martins": Endpoint(
        "Blood-brain barrier penetration", ADVANCED, "",
        "Vendor AUROC 0.90 held out; beats molecular weight and logP by 0.17 here.",
    ),
    "PPBR_AZ": Endpoint(
        "Plasma protein binding", ADVANCED, "%",
        "Vendor R² 0.59 held out; beats molecular weight and logP by 0.41 here.",
    ),
    "DILI": Endpoint(
        "Drug-induced liver injury", ADVANCED, "",
        "Vendor AUROC 0.88 held out; beats molecular weight and logP by 0.44 here.",
    ),
    "LD50_Zhu": Endpoint(
        "Acute toxicity LD50 (rat)", ADVANCED, "log(1/(mol/kg))",
        "Vendor R² 0.60 held out; beats molecular weight and logP by 0.55 here.",
    ),

    # --- Research: measured here, and NOT good enough to present as an
    # --- answer. Kept rather than dropped because seeing the number next
    # --- to why it is untrustworthy is more useful than its absence, which
    # --- reads as "the model does not do this".
    "Pgp_Broccatelli": Endpoint(
        "P-glycoprotein inhibition", RESEARCH, "",
        "Not validated here: logP alone scores 0.89 against the model's 0.97, "
        "so almost all of its apparent skill is lipophilicity. The same "
        "confound that undermines hERG.",
    ),
    "Bioavailability_Ma": Endpoint(
        "Oral bioavailability", RESEARCH, "",
        "Not validated here: vendor AUROC 0.72 held out, against a "
        "molecular-weight-only baseline of 0.70 on the same molecules.",
    ),
    "VDss_Lombardo": Endpoint(
        "Volume of distribution at steady state", RESEARCH, "L/kg",
        "Not validated here: vendor R² −1.21, and −0.30 even on its own "
        "training data. Negative means worse than always answering the mean.",
    ),
    "Half_Life_Obach": Endpoint(
        "Half life", RESEARCH, "hr",
        "Not validated here: vendor R² −2.39, and −0.09 even on its own "
        "training data. Negative means worse than always answering the mean.",
    ),
    "Clearance_Hepatocyte_AZ": Endpoint(
        "Hepatocyte clearance", RESEARCH, "µL/min/10⁶ cells",
        "Not validated here: vendor R² 0.26 held out — a quarter of the "
        "variance on an endpoint spanning two orders of magnitude.",
    ),
    "Clearance_Microsome_AZ": Endpoint(
        "Microsomal clearance", RESEARCH, "µL/min/mg",
        "Not validated here: vendor R² 0.28 held out.",
    ),
    "ClinTox": Endpoint(
        "Clinical trial toxicity", RESEARCH, "",
        "Not benchmarked here.",
    ),
    "Carcinogens_Lagunin": Endpoint(
        "Carcinogenicity (rodent)", RESEARCH, "",
        "Not benchmarked here.",
    ),
    "Skin_Reaction": Endpoint(
        "Skin reaction (mouse)", RESEARCH, "",
        "Not benchmarked here.",
    ),
    "PAMPA_NCATS": Endpoint(
        "PAMPA permeability", RESEARCH, "",
        "Not benchmarked here.",
    ),
}

#: The Tox21 nuclear-receptor and stress-response panel, added as one block
#: rather than eighteen hand-written entries: they share a provenance, a
#: caveat and a tier, and spelling each out would invite the list and the
#: reasoning to drift apart.
for _tox21_column, _tox21_label in {
    "NR-AR": "Androgen receptor",
    "NR-AR-LBD": "Androgen receptor (ligand-binding domain)",
    "NR-AhR": "Aryl hydrocarbon receptor",
    "NR-Aromatase": "Aromatase",
    "NR-ER": "Estrogen receptor",
    "NR-ER-LBD": "Estrogen receptor (ligand-binding domain)",
    "NR-PPAR-gamma": "PPAR-gamma",
    "SR-ARE": "Antioxidant response element",
    "SR-ATAD5": "ATAD5 genotoxicity",
    "SR-HSE": "Heat-shock response",
    "SR-MMP": "Mitochondrial membrane potential",
    "SR-p53": "p53 response",
}.items():
    REPORTED_ENDPOINTS[_tox21_column] = Endpoint(
        f"{_tox21_label} (Tox21)", RESEARCH, "",
        "Not benchmarked here. Tox21 assays are heavily imbalanced, and the "
        "vendor's own AUPRC for this panel runs 0.31-0.70.",
    )


def endpoints_for_tier(tier: str) -> dict[str, Endpoint]:
    """Every endpoint at `tier` or better, so "advanced" includes "basic".

    An unrecognised tier falls back to basic rather than raising: this
    value arrives from a saved calculator parameter, and a stale settings
    file should degrade to the conservative set rather than break the
    calculator.
    """
    cutoff = TIERS.index(tier) if tier in TIERS else 0
    allowed = set(TIERS[: cutoff + 1])
    return {
        column: endpoint
        for column, endpoint in REPORTED_ENDPOINTS.items()
        if endpoint.tier in allowed
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


def compute_admet(
    mol: Chem.Mol, interpreter_path: str | None, tier: str = BASIC
) -> dict[str, float] | None:
    """Predicted ADMET endpoints at `tier`, or None when no environment is
    set up.

    None means "not configured", which callers present as an offer to
    install. A configured-but-broken environment raises instead, because
    that is a fault the user needs to see rather than a missing optional.

    The returned dict carries each endpoint AND its
    `_drugbank_approved_percentile` twin where the model supplied one. The
    twin is the context the app otherwise lacks -- "is 0.62 unusual for an
    approved drug?" -- and it costs nothing, having been computed and
    discarded until now.

    `tier` changes only which columns are kept. The subprocess, the model
    load and the ~300s are identical for all three, because the model
    always predicts all 104.
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
    wanted = endpoints_for_tier(tier)
    return {
        column: value
        for column, value in endpoints.items()
        if column in wanted
        or (column.endswith(PERCENTILE_SUFFIX)
            and column[: -len(PERCENTILE_SUFFIX)] in wanted)
    }


#: What each tier heading tells the reader about how much to trust the
#: block underneath it. The Research wording is the important one: these
#: numbers are shown BECAUSE hiding them reads as "the model cannot do
#: this", which is a different and false claim.
_TIER_HEADINGS: dict[str, str] = {
    BASIC: "Toxicity and metabolism",
    ADVANCED: "ADME — benchmarked in benchmarks/admet/, 2026-08-05",
    RESEARCH: "Research — NOT validated here; read the note under each",
}


def _ordinal(value: float) -> str:
    """"92nd", not "92th".

    11-13 are the reason this is not a lookup on the last digit alone --
    they take "th" while 1, 2 and 3 take "st", "nd", "rd".
    """
    number = int(round(value))
    if 11 <= number % 100 <= 13:
        return f"{number}th"
    suffix = {1: "st", 2: "nd", 3: "rd"}.get(number % 10, "th")
    return f"{number}{suffix}"


def endpoint_lines(endpoints: dict[str, float], parameters: dict | None = None) -> list[str]:
    """Render predictions as the text lines the Property panel shows.

    Grouped by tier, because a Caco-2 number and a Tox21 number deserve
    very different amounts of belief and a flat list says they do not.
    Percentiles are folded into their own endpoint's line rather than
    listed separately -- they are context for that number ("is this
    unusual for an approved drug?"), and as free-standing rows they would
    double the length of the block and read as more predictions.
    """
    from openchem.chem.calculator_options import fmt

    lines: list[str] = []
    for tier in TIERS:
        columns = [
            column for column in endpoints
            if not column.endswith(PERCENTILE_SUFFIX)
            and REPORTED_ENDPOINTS.get(column) is not None
            and REPORTED_ENDPOINTS[column].tier == tier
        ]
        if not columns:
            continue

        # Probabilities sort worst-first -- the whole reason someone opens
        # this is to find what will bite. Endpoints carrying units are
        # regressions on unrelated scales, so ordering them by magnitude
        # would be meaningless; they follow, by name.
        unitless = sorted(
            (c for c in columns if not REPORTED_ENDPOINTS[c].units),
            key=lambda c: -endpoints[c],
        )
        measured = sorted(
            (c for c in columns if REPORTED_ENDPOINTS[c].units),
            key=lambda c: REPORTED_ENDPOINTS[c].label,
        )

        lines.append(f"[{_TIER_HEADINGS[tier]}]")
        for column in unitless + measured:
            endpoint = REPORTED_ENDPOINTS[column]
            units = f" {endpoint.units}" if endpoint.units else ""
            text = f"  {endpoint.label}: {fmt(endpoints[column], parameters)}{units}"
            percentile = endpoints.get(column + PERCENTILE_SUFFIX)
            if percentile is not None:
                text += f"  ({_ordinal(percentile)} percentile among approved drugs)"
            lines.append(text)
            if endpoint.evidence:
                lines.append(f"    {endpoint.evidence}")
    return lines


def describe_admet_status(interpreter_path: str | None) -> str:
    if admet_available(interpreter_path):
        return f"Found: {interpreter_path} - press Test to verify"
    return (
        "Not configured. ADMET-AI predicts hERG blockade, CYP450 inhibition, Ames "
        "mutagenicity and an ADME block (Caco-2, solubility, blood-brain barrier, "
        "plasma protein binding, liver injury, LD50) -- endpoints that need a "
        "trained model, with no honest rule-based substitute. Like pkasolver it "
        "needs its own Python environment (~1 GB, mostly PyTorch), so it is "
        "installed separately rather than shipped."
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
