"""Aqueous solubility, and how it varies with pH.

ChemAxon's Solubility Predictor is the shape being matched: an intrinsic
solubility, a value at a chosen pH, a Low/Moderate/High category, and a
pH-solubility curve.

**THREE QUANTITIES, THREE NAMES, NEVER INTERCHANGED.** The whole module
depends on keeping these apart, because the second is a modelling
assumption laid on top of the first and the UI will otherwise present it
as a measurement:

    model_logS0            raw ESOL / AqSolDB output
    baseline_logS          that output USED AS the neutral-baseline input
                           to Henderson-Hasselbalch
    predicted_logS_at_pH   baseline_logS + ionization adjustment

ESOL predicts the aqueous solubility of the compound as supplied. Reading
it as the neutral species' solubility is an ADDED assumption, not
something ESOL claims, so no name here implies it has become a
thermodynamic intrinsic-solubility model.

MEASURED BEFORE ANY OF THIS WAS BUILT, against literature values:

    aspirin      ESOL -2.09   AqSolDB -1.62   Marvin -1.81   exp -2.19
    ibuprofen    ESOL -3.54                                  exp -3.62
    propranolol  ESOL -3.57                                  exp -3.62
    caffeine     ESOL -0.53                                  exp -0.80

ESOL beats Marvin on Marvin's own documentation molecule. That is four
molecules and ranks nothing, which is why `benchmarks/solubility/` exists.

IT HAS SINCE BEEN RUN, against the Solubility Challenge with Delaney's
own fitting set subtracted by InChIKey (67 scored of 80):

    all      n=67  MAE 0.74  RMSE 0.98  bias -0.20
    acid     n=22  MAE 0.61            bias +0.06
    base     n=29  MAE 0.81            bias -0.52   <- systematic

RMSE 0.98 is in line with ESOL's published accuracy on compounds it was
not fitted on. **The stratification is the part that mattered**: the
aggregate bias reads as noise, and split by class the model under-predicts
BASES by half a log unit. Worth knowing before trusting a basic drug's
number, and invisible in a single MAE.

**UNCAPPED HENDERSON-HASSELBALCH IS UNUSABLE, and that is measured.**
Aspirin reaches 4.7e10 mg/mL at pH 14 -- correct arithmetic, meaningless
answer, the same failure this project already records at 40619 kcal/mol.
Hence `MAX_PH_SOLUBILITY_ADJUSTMENT_LOG_UNITS`, which is a SAFEGUARD and
not a prediction; see its comment.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from rdkit import Chem
from rdkit.Chem import Crippen, Descriptors, Lipinski

from openchem.chem.calculator_options import DEFAULT_PH, ph_grid_from
from openchem.chem.logd import assign_site_polarity, classify_ionizable_centres, ionization_log_factor
from openchem.chem.pka_providers import PKaResolution, PKaStatus
from openchem.domain.common import CacheState, Provenance
from openchem.domain.report import Detail, Fact, FactCategory, ReportResult
from openchem.domain.scientific_result import PhCurveResult
from openchem.domain.structure_issue import Basis

# --- the adjustment limit ---------------------------------------------

#: How far Henderson-Hasselbalch is allowed to raise solubility above the
#: baseline, in log units.
#:
#: **THIS IS A MODEL SAFEGUARD, NOT A PREDICTED SATURATION PLATEAU.** What
#: the code knows is "I stopped adjusting here". It does NOT know the
#: compound saturates: a real pH-solubility profile levels off where the
#: SALT precipitates, which is set by that salt's solubility product, and
#: no compound-specific Ksp or salt-precipitation model exists anywhere in
#: this application. Every fact derived from a limited value says so.
#:
#: 2.0 is where ChemAxon's own published example sits -- their aspirin
#: figures rise from -1.81 intrinsic to 0.19 at pH 7.4, exactly 2.00 log
#: units, against an unbounded HH rise of 3.91 for the same molecule. That
#: is a reason to pick this number over another arbitrary one; it is not
#: evidence that either value is physically correct.
MAX_PH_SOLUBILITY_ADJUSTMENT_LOG_UNITS = 2.0

# --- solvents ----------------------------------------------------------


@dataclass(frozen=True)
class Solvent:
    """A solvent the predictor can answer for.

    Deliberately two fields. Only water participates in any computation,
    so anything more -- Abraham/LSER coefficients in particular -- would be
    plumbing that nothing reads, and this project has been bitten before by
    machinery that looked wired up and was not.

    `docs/SOLVENT_SOLUBILITY_ASSESSMENT.md` records exactly what a second
    solvent needs and why it is not here yet.
    """

    key: str
    label: str


WATER = Solvent(key="water", label="Water")
SOLVENTS: dict[str, Solvent] = {WATER.key: WATER}


def resolve_solvent(key: str | None) -> Solvent:
    """The named solvent, or `KeyError` naming what is supported.

    Refuses rather than silently falling back to water: a user who asked
    for ethanol and got water's answer under ethanol's label has been given
    a wrong number, not a degraded one.
    """
    chosen = (key or WATER.key).strip().lower()
    if chosen not in SOLVENTS:
        supported = ", ".join(sorted(SOLVENTS))
        raise KeyError(f"No solubility model for solvent {chosen!r}. Supported: {supported}.")
    return SOLVENTS[chosen]


# --- categories --------------------------------------------------------

#: ChemAxon's documented thresholds, in mg/mL. Their page states these
#: classify INTRINSIC solubility, and their own aspirin example confirms
#: it: -1.81 logS is 2.79 mg/mL, which is the "High" they report.
LOW_MODERATE_BOUNDARY_MG_PER_ML = 0.01
MODERATE_HIGH_BOUNDARY_MG_PER_ML = 0.06


class SolubilityCategory(Enum):
    LOW = "Low"
    MODERATE = "Moderate"
    HIGH = "High"


def intrinsic_category(mg_per_ml: float) -> SolubilityCategory:
    """Category of the BASELINE solubility, following ChemAxon's thresholds.

    **THE INPUT IS THE BASELINE, NEVER THE pH-ADJUSTED VALUE.** Feeding it
    the pH-adjusted number produces a category that changes when the user
    moves a pH control, which is not what the classification means and
    which would look entirely reasonable on screen.
    `test_the_category_reads_the_baseline_not_the_ph_adjusted_value` is the
    guard, because this is a one-word edit away at any time.

    Boundaries are inclusive on the MODERATE band, so the two published
    numbers each belong to exactly one category.
    """
    if mg_per_ml < LOW_MODERATE_BOUNDARY_MG_PER_ML:
        return SolubilityCategory.LOW
    if mg_per_ml <= MODERATE_HIGH_BOUNDARY_MG_PER_ML:
        return SolubilityCategory.MODERATE
    return SolubilityCategory.HIGH


# --- units -------------------------------------------------------------


def logs_to_mol_per_l(logs: float) -> float:
    return 10.0**logs


def logs_to_mg_per_ml(logs: float, molecular_weight: float) -> float:
    """logS (log mol/L) to mg/mL.

    **NO FACTOR OF 1000, and that is the trap.** 10^logS is mol/L; times
    g/mol gives g/L; and g/L IS mg/mL, because the two thousands cancel
    (1 g/L = 1000 mg per 1000 mL). One mol/L of a 180.16 g/mol compound is
    180.16 mg/mL.

    A review of this module's plan proposed dividing by 1000 here, in the
    point it titled "the most dangerous conversion bug". It would have put
    every category one or two bands too low -- aspirin, which ChemAxon
    publishes as High, would have come out Low.
    `test_a_mole_per_litre_of_aspirin_is_180_mg_per_ml` pins it against a
    number anybody can check by hand.
    """
    if molecular_weight <= 0:
        raise ValueError(f"Molecular weight must be positive, got {molecular_weight}.")
    return 10.0**logs * molecular_weight


def mg_per_ml_to_logs(mg_per_ml: float, molecular_weight: float) -> float:
    if mg_per_ml <= 0:
        raise ValueError(f"Solubility must be positive to take its log, got {mg_per_ml}.")
    if molecular_weight <= 0:
        raise ValueError(f"Molecular weight must be positive, got {molecular_weight}.")
    return math.log10(mg_per_ml / molecular_weight)


# --- the baseline models ----------------------------------------------


def esol_logs(mol: Chem.Mol) -> float:
    """ESOL (Delaney 2004, refit coefficients) -- log mol/L.

    Confirmed live against the reference implementation
    (PatWalters/solubility) and sanity-checked against known experimental
    values (aspirin: -2.09 predicted vs -2.19 experimental; caffeine: -0.53
    vs -0.8, both within ESOL's documented accuracy).

    `mol.GetNumAtoms()` (not the heavy-atom count) to match the verified
    reference implementation and those live-checked values -- equal to the
    heavy-atom count when the molblock has no explicit Hs (the common
    case), and different only if it does.

    `Lipinski.NumRotatableBonds` rather than
    `rdMolDescriptors.CalcNumRotatableBonds` because that is the call the
    descriptor made before this was extracted. The two agreed on every
    molecule tried, but "agreed on six" is not "are the same function", and
    this file already records RDKit's strict rotatable-bond definition
    being impossible to reconstruct.
    """
    aromatic_atom_count = sum(1 for atom in mol.GetAtoms() if atom.GetIsAromatic())
    total_atoms = mol.GetNumAtoms()
    aromatic_proportion = aromatic_atom_count / total_atoms if total_atoms else 0.0
    return (
        0.2612
        - 0.7417 * Crippen.MolLogP(mol)
        - 0.0066 * Descriptors.MolWt(mol)
        + 0.0035 * Lipinski.NumRotatableBonds(mol)
        - 0.4262 * aromatic_proportion
    )


class ModelStatus(Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"  # sidecar not configured
    FAILED = "failed"  # configured, but the run errored


ESOL = "esol"
AQSOLDB = "aqsoldb"
BASELINE_MODELS = (ESOL, AQSOLDB)

MODEL_LABELS = {ESOL: "ESOL (Delaney 2004)", AQSOLDB: "AqSolDB (trained model)"}


@dataclass(frozen=True)
class ModelEstimate:
    """One baseline model's answer, with enough provenance to reproduce it.

    `version` and `artifact_sha256` matter because the ML sidecar can be
    updated underneath a saved project. Without them a stored result
    silently changes meaning when the model behind it changes -- this
    project already treats the RDKit version, force fields and generation
    parameters as scientific provenance for exactly that reason.
    """

    model: str
    status: ModelStatus
    logs0: float | None = None
    version: str = ""
    artifact_sha256: str = ""
    reason: str = ""

    @property
    def label(self) -> str:
        return MODEL_LABELS.get(self.model, self.model)


def model_logs0(mol: Chem.Mol, model: str, interpreter_path: str | None = None) -> ModelEstimate:
    """The chosen model's raw logS0, or why it could not be had.

    ESOL needs nothing and cannot be unavailable. AqSolDB runs in the ADMET
    sidecar and takes roughly 300 s, so it is never the default.
    """
    if model == ESOL:
        return ModelEstimate(model=ESOL, status=ModelStatus.AVAILABLE, logs0=esol_logs(mol))
    if model != AQSOLDB:
        raise ValueError(f"Unknown solubility model {model!r}. Known: {', '.join(BASELINE_MODELS)}.")

    from openchem.chem.admet_providers import ADVANCED, admet_available, compute_admet

    if not admet_available(interpreter_path):
        return ModelEstimate(
            model=AQSOLDB,
            status=ModelStatus.UNAVAILABLE,
            reason=(
                "The AqSolDB model runs in the ADMET environment, which is not configured. "
                "Set it up under Tools > External Tools, or choose ESOL."
            ),
        )
    try:
        endpoints = compute_admet(mol, interpreter_path, ADVANCED) or {}
    except Exception as exc:  # noqa: BLE001 - a broken sidecar is a reportable fault
        return ModelEstimate(model=AQSOLDB, status=ModelStatus.FAILED, reason=str(exc))

    value = endpoints.get("Solubility_AqSolDB")
    if value is None:
        return ModelEstimate(
            model=AQSOLDB,
            status=ModelStatus.FAILED,
            reason="The ADMET environment ran but reported no aqueous-solubility endpoint.",
        )
    return ModelEstimate(
        model=AQSOLDB,
        status=ModelStatus.AVAILABLE,
        logs0=float(value),
        version=str(endpoints.get("_model_version", "")),
        artifact_sha256=str(endpoints.get("_model_sha256", "")),
    )


# --- ionization --------------------------------------------------------


class IonizationClass(Enum):
    NEUTRAL = "neutral"
    ACID = "acid"
    BASE = "base"
    AMPHOLYTE = "ampholyte"
    UNSUPPORTED = "unsupported"


def is_single_component(mol: Chem.Mol) -> bool:
    return len(Chem.GetMolFrags(mol)) == 1


def classify_ionization(mol: Chem.Mol, resolution: PKaResolution) -> IonizationClass:
    """Which ionization regime this molecule is in, for THIS model.

    **NEUTRAL IS NEVER INFERRED FROM AN EMPTY pKa LIST.** An empty list can
    mean "nothing to ionize" or "the predictor fell over", and treating the
    second as the first would draw a confident flat line for a molecule
    whose real curve was simply never computed. Only an explicit
    `NO_IONIZABLE_CENTRES` gets NEUTRAL.

    **AN AMPHOLYTE IS REFUSED RATHER THAN MODELLED.** `compute_logd_curve`
    already records Henderson-Hasselbalch under-predicting zwitterions;
    for solubility the error runs the OTHER way and is worse. HH assumes
    the species that stays undissolved is the one with no site ionized --
    but a zwitterion's un-ionized form is the zwitterion itself, which is
    highly soluble, so the model puts the solubility minimum in the wrong
    place and reports a plausible curve for a different compound.

    **A MIXTURE IS REFUSED BEFORE ANYTHING ELSE IS ASKED.** `[Na+].[drug-]`
    is already the salt whose formation the pH correction is supposed to be
    modelling; running HH over it answers a question nobody asked, and the
    result looks entirely normal.
    """
    if not is_single_component(mol):
        return IonizationClass.UNSUPPORTED

    # **THE CHEMISTRY IS READ FIRST, AND FROM THE STRUCTURE.** Which
    # regime a molecule is in does not depend on whether a predictor was
    # installed: glycine is an ampholyte on a machine with no pkasolver,
    # and caffeine has nothing to ionize on a machine with one. Asking
    # about pKa availability first got this wrong -- glycine came back as
    # "no pKa values available" and the ampholyte refusal, which is the
    # more informative answer and the correct one, was never reached.
    acids, bases = classify_ionizable_centres(mol)
    if acids and bases:
        return IonizationClass.AMPHOLYTE
    if acids == 0 and bases == 0:
        # NEUTRAL from a STRUCTURAL fact -- no centre exists -- and never
        # from an empty pKa list, which can equally mean the predictor
        # fell over. That distinction is the whole point of `PKaStatus`.
        return IonizationClass.NEUTRAL

    if resolution.status is not PKaStatus.FOUND:
        # A single-polarity molecule whose VALUES are missing. That is a
        # missing input, not an ionization regime; the caller reports
        # `resolution.reason` rather than drawing a flat line.
        return IonizationClass.UNSUPPORTED
    return IonizationClass.ACID if acids else IonizationClass.BASE


def parse_manual_pkas(text: str) -> list[float]:
    """User-typed pKa values, e.g. `"3.49, 9.4"`.

    Raises on anything unparseable rather than skipping it -- a typo that
    silently drops a site gives a curve with one fewer inflection and no
    indication anything was ignored.
    """
    values: list[float] = []
    for chunk in text.replace(";", ",").split(","):
        piece = chunk.strip()
        if not piece:
            continue
        try:
            values.append(float(piece))
        except ValueError as exc:
            raise ValueError(f"{piece!r} is not a number. Give pKa values like '3.49, 9.4'.") from exc
    return values


def resolve_pkas(
    mol: Chem.Mol, manual_text: str = "", interpreter_path: str | None = None
) -> PKaResolution:
    """pKa values for `mol`: user-supplied first, then predicted.

    Precedence is **manual > predicted > refusal**. A chemist who knows the
    real pKa should be able to beat the predictor, which is a genuine
    advantage over the tool this feature is modelled on.

    Returns a `PKaResolution` and takes no decision about what its status
    means -- see that type's docstring for why the policy lives in callers.
    """
    manual_text = (manual_text or "").strip()
    if manual_text:
        values = parse_manual_pkas(manual_text)
        if values:
            return PKaResolution(
                status=PKaStatus.FOUND,
                values=tuple(sorted(values)),
                source="manual",
                method="user-supplied",
                input_text=manual_text,
            )

    acids, bases = classify_ionizable_centres(mol)
    if acids == 0 and bases == 0:
        return PKaResolution(
            status=PKaStatus.NO_IONIZABLE_CENTRES,
            reason="No ionizable centre, so solubility does not vary with pH.",
        )

    from openchem.chem.pka_providers import compute_pka, pka_predictor_available

    if not pka_predictor_available(interpreter_path):
        return PKaResolution(
            status=PKaStatus.UNAVAILABLE,
            reason=(
                "A pH-solubility curve needs numeric pKa values. pkasolver runs out of process "
                "from its own environment -- set it up under Tools > External Tools, or type the "
                "pKa values in yourself."
            ),
        )
    try:
        predictions = compute_pka(mol, interpreter_path) or []
    except Exception as exc:  # noqa: BLE001 - report, never crash a panel
        return PKaResolution(status=PKaStatus.FAILED, reason=str(exc))
    if not predictions:
        return PKaResolution(
            status=PKaStatus.FAILED,
            reason="The pKa predictor ran but returned no values for this structure.",
        )
    return PKaResolution(
        status=PKaStatus.FOUND,
        values=tuple(sorted(p.value for p in predictions)),
        source="predicted",
        method="pkasolver",
    )


# --- the pH profile ----------------------------------------------------


@dataclass(frozen=True)
class PhAdjustment:
    """How much ionization added to the baseline at one pH, and whether the
    safeguard bound."""

    applied: float
    uncapped: float
    limited: bool


def ph_adjustment(
    ph: float,
    pkas: list[float],
    is_acid: list[bool],
    limit: float | None = MAX_PH_SOLUBILITY_ADJUSTMENT_LOG_UNITS,
) -> PhAdjustment:
    """The ionization log factor, clamped to `limit`.

    Note the sign relative to logD: the SAME `ionization_log_factor` is
    subtracted there and added here, because ionization removes octanol
    partitioning and adds water solubility. Sharing that function is what
    makes the relationship structural instead of coincidental -- and it is
    why the multi-site correction landed in both at once.
    """
    uncapped = ionization_log_factor(ph, pkas, is_acid)
    if limit is None or uncapped <= limit:
        return PhAdjustment(applied=uncapped, uncapped=uncapped, limited=False)
    return PhAdjustment(applied=limit, uncapped=uncapped, limited=True)


def logs_at_ph(
    baseline_logs: float,
    ph: float,
    pkas: list[float],
    is_acid: list[bool],
    limit: float | None = MAX_PH_SOLUBILITY_ADJUSTMENT_LOG_UNITS,
) -> float:
    return baseline_logs + ph_adjustment(ph, pkas, is_acid, limit).applied


def profile(
    baseline_logs: float,
    ph_values: list[float],
    pkas: list[float],
    is_acid: list[bool],
    limit: float | None = MAX_PH_SOLUBILITY_ADJUSTMENT_LOG_UNITS,
) -> list[float]:
    return [logs_at_ph(baseline_logs, ph, pkas, is_acid, limit) for ph in ph_values]


# --- the ICH M9 screening window --------------------------------------

#: ICH M9's window for the high-solubility criterion. **A MODULE CONSTANT,
#: DELIBERATELY NOT `ph_range_parameters()`** -- the chart's range is the
#: user's to choose, and letting it reach this would mean widening a graph
#: silently redefined a regulatory criterion.
BCS_PH_LOW = 1.2
BCS_PH_HIGH = 6.8

#: ICH M9's reference volume, in mL.
BCS_VOLUME_ML = 250.0


@dataclass(frozen=True)
class WindowEvaluation:
    """The model's solubility across the ICH window.

    **THE MINIMUM IS AT AN ENDPOINT, BY CONSTRUCTION.** For every regime
    this module supports the adjustment is monotone in pH -- an acid's
    terms all rise with pH, a base's all fall, a neutral molecule has none
    -- so the sum is monotone and its extremum over a closed interval is at
    one end. Ampholytes, the one mixed-polarity case, are refused before
    reaching here. That is a statement about THIS model's domain, not a
    claim about chemistry, and it is why this evaluates two points instead
    of scanning a grid that could step over a minimum.
    """

    ph_low: float
    ph_high: float
    logs_low: float
    logs_high: float
    minimum_logs: float
    minimum_ph: float
    #: The safeguard bound at BOTH ends, so the DISPLAYED curve carries no
    #: pH information across the window. Reported as a fact; it no longer
    #: decides the BCS screen, which is bounded rather than capped.
    fully_limited: bool
    #: The model's raw output, which is a LOWER bound on solubility:
    #: ionization only ever adds dissolved species to the neutral ones, so
    #: `S(pH) >= S0` at every pH. (True while the solid is the free form,
    #: which is the model's scope -- salts are refused upstream.)
    baseline_logs: float
    #: The same window with NO adjustment limit, which is an UPPER bound:
    #: uncapped Henderson-Hasselbalch assumes the counter-ion salt never
    #: precipitates, so it can only overestimate.
    uncapped_minimum_logs: float


def evaluate_solubility_window(
    baseline_logs: float,
    pkas: list[float],
    is_acid: list[bool],
    ionization: IonizationClass,
    limit: float | None = MAX_PH_SOLUBILITY_ADJUSTMENT_LOG_UNITS,
) -> WindowEvaluation:
    if ionization is IonizationClass.AMPHOLYTE:
        raise ValueError(
            "An ampholyte's profile is not monotone, so its window minimum is not at an "
            "endpoint. Ampholytes are refused upstream and must not reach this function."
        )
    low = ph_adjustment(BCS_PH_LOW, pkas, is_acid, limit)
    high = ph_adjustment(BCS_PH_HIGH, pkas, is_acid, limit)
    logs_low = baseline_logs + low.applied
    logs_high = baseline_logs + high.applied
    minimum_logs, minimum_ph = min((logs_low, BCS_PH_LOW), (logs_high, BCS_PH_HIGH))
    return WindowEvaluation(
        ph_low=BCS_PH_LOW,
        ph_high=BCS_PH_HIGH,
        logs_low=logs_low,
        logs_high=logs_high,
        minimum_logs=minimum_logs,
        minimum_ph=minimum_ph,
        fully_limited=low.limited and high.limited,
        baseline_logs=baseline_logs,
        uncapped_minimum_logs=baseline_logs + min(low.uncapped, high.uncapped),
    )


def dose_number(dose_mg: float, mg_per_ml: float, volume_ml: float = BCS_VOLUME_ML) -> float | None:
    """Do = dose / (solubility x 250 mL).

    `None` for a non-positive dose or solubility rather than dividing by
    zero or returning a negative volume, both of which would render as a
    perfectly ordinary-looking number.
    """
    if dose_mg <= 0 or mg_per_ml <= 0 or volume_ml <= 0:
        return None
    return dose_mg / (mg_per_ml * volume_ml)


class BcsOutcome(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNDETERMINED = "UNDETERMINED"


class BcsReason(Enum):
    COMPUTABLE = "computable"
    MISSING_DOSE = "no therapeutic dose given"
    MODEL_UNAVAILABLE = "the baseline model is unavailable"
    PKAS_UNAVAILABLE = "no pKa values are available"
    UNSUPPORTED_SPECIES = "this species is outside the model"
    BOUNDS_STRADDLE = "the solubility bounds straddle the criterion"


@dataclass(frozen=True)
class BcsScreen:
    outcome: BcsOutcome
    reason: BcsReason
    dose_number: float | None = None
    minimum_mg_per_ml: float | None = None
    minimum_ph: float | None = None
    #: The sandwich the verdict rests on. `dose_number_high` uses the
    #: solubility FLOOR and so is the largest Do the compound can have;
    #: `dose_number_low` uses the ceiling and is the smallest.
    dose_number_high: float | None = None
    dose_number_low: float | None = None

    @property
    def display(self) -> str:
        if self.outcome is BcsOutcome.UNDETERMINED:
            return f"UNDETERMINED — {self.reason.value}"
        return self.outcome.value

    @classmethod
    def undetermined(cls, reason: BcsReason) -> BcsScreen:
        return cls(outcome=BcsOutcome.UNDETERMINED, reason=reason)


def bcs_high_solubility_screen(
    window: WindowEvaluation, dose_mg: float | None, molecular_weight: float
) -> BcsScreen:
    """ICH M9's high-solubility criterion, ESTIMATED from a model.

    **THIS IS A SCREENING ESTIMATE AND NEVER A CLASSIFICATION.** ICH M9
    requires the solubility to be established EXPERIMENTALLY over pH
    1.2-6.8 at 37 +/- 1 C, using the lowest measured value. Everything here
    is predicted at no defined temperature, so it can indicate where an
    experiment is worth doing and can never substitute for one. `Do < 1`
    also addresses only the high-solubility half of the BCS test; the
    permeability half is a separate measurement entirely.

    **THE SAFEGUARD DOES NOT DECIDE THIS, AND THAT IS THE WHOLE POINT.**
    An earlier version returned UNDETERMINED whenever the +2 adjustment
    limit bound across the window, which is the ORDINARY case for a basic
    drug -- propranolol (pKa 9.4) wants +8.20 at pH 1.2 and +2.60 at pH
    6.8, so every point saturates and the displayed spread is 0.000. That
    made the answer depend on an arbitrary constant, so a whole compound
    class got a blank.

    It is bounded instead, and both bounds are real:

        S(pH) >= S0                  ionization only ADDS dissolved
                                     species to the neutral ones
        S(pH) <= uncapped HH         which assumes the counter-ion salt
                                     never precipitates

    So the dose number is sandwiched, and each side licenses one verdict:

        Do from the FLOOR   <= 1  ->  PASS is sound (even the most
                                      pessimistic solubility clears it)
        Do from the CEILING  > 1  ->  FAIL is sound (even the most
                                      optimistic solubility misses it)
        otherwise                 ->  genuinely UNDETERMINED

    Measured across five compounds, four get a sound verdict: caffeine
    PASS (Do <= 0.007 either way), aspirin FAIL (1.36), ibuprofen FAIL
    (26.7), ketoconazole FAIL (3497). Propranolol is the honest
    UNDETERMINED -- 2.27 against 0.005 -- and now says so because its
    bounds straddle 1 rather than because our safeguard fired.

    **THE FLOOR ASSUMES THE SOLID IS THE FREE FORM.** That is the model's
    scope: salts and mixtures are refused upstream. A compound dosed as a
    salt can dissolve below its free-form solubility through the common-ion
    effect, and nothing here models that.
    """
    if dose_mg is None or dose_mg <= 0:
        return BcsScreen.undetermined(BcsReason.MISSING_DOSE)

    floor_mg_per_ml = logs_to_mg_per_ml(window.baseline_logs, molecular_weight)
    ceiling_mg_per_ml = logs_to_mg_per_ml(window.uncapped_minimum_logs, molecular_weight)
    highest = dose_number(dose_mg, floor_mg_per_ml)
    lowest = dose_number(dose_mg, ceiling_mg_per_ml)
    if highest is None or lowest is None:
        return BcsScreen.undetermined(BcsReason.MISSING_DOSE)

    minimum_mg_per_ml = logs_to_mg_per_ml(window.minimum_logs, molecular_weight)
    common = {
        "dose_number": dose_number(dose_mg, minimum_mg_per_ml),
        "minimum_mg_per_ml": minimum_mg_per_ml,
        "minimum_ph": window.minimum_ph,
        "dose_number_high": highest,
        "dose_number_low": lowest,
    }
    if highest <= 1.0:
        return BcsScreen(outcome=BcsOutcome.PASS, reason=BcsReason.COMPUTABLE, **common)
    if lowest > 1.0:
        return BcsScreen(outcome=BcsOutcome.FAIL, reason=BcsReason.COMPUTABLE, **common)
    return BcsScreen(
        outcome=BcsOutcome.UNDETERMINED, reason=BcsReason.BOUNDS_STRADDLE, **common
    )


# --- display units -----------------------------------------------------

LOG_S = "logS (log mol/L)"
MG_PER_ML = "mg/mL"
MOL_PER_L = "mol/L"
DISPLAY_UNITS = (LOG_S, MG_PER_ML, MOL_PER_L)


def in_unit(logs: float, unit: str, molecular_weight: float) -> float:
    if unit == MG_PER_ML:
        return logs_to_mg_per_ml(logs, molecular_weight)
    if unit == MOL_PER_L:
        return logs_to_mol_per_l(logs)
    return logs


def format_in_unit(logs: float, unit: str, molecular_weight: float) -> str:
    """One precision per unit, everywhere.

    A logarithm gets two decimals and a concentration gets four
    significant figures. Without a single formatter the same quantity
    appeared as `-0.53` in one row and `-0.531` in the next -- this
    project has already had one dataset render at four different
    precisions on one screen.
    """
    value = in_unit(logs, unit, molecular_weight)
    return f"{value:.2f}" if unit == LOG_S else f"{value:.4g}"


def unit_symbol(unit: str) -> str:
    """ASCII only, deliberately.

    Result lines reach Windows console streams, where a non-cp1252
    character RAISES -- this project has hit that three times in one
    session with a tick mark. "mg/mL" rather than any prettier form.
    """
    return {LOG_S: "log mol/L", MG_PER_ML: "mg/mL", MOL_PER_L: "mol/L"}.get(unit, "")


# --- the calculators ---------------------------------------------------

_SALT_LIMIT_NOTE = (
    "The pH adjustment is capped at +{limit:.2f} logS. That is a model safeguard, not a "
    "predicted saturation plateau -- no compound-specific solubility product or "
    "salt-precipitation model exists here."
)

_BCS_NOTE = (
    "A model-based screening estimate, not an experimental BCS classification. ICH M9 "
    "requires solubility measured over pH 1.2-6.8 at 37 +/- 1 C, using the lowest measured "
    "value. Dose number addresses only the high-solubility half of the BCS test; "
    "permeability is a separate measurement."
)

_ZWITTERION_NOTE = (
    "Henderson-Hasselbalch assumes the undissolved species is the one with no site ionized. "
    "A zwitterion's un-ionized form IS the zwitterion, which is highly soluble, so the model "
    "puts the solubility minimum in the wrong place. Refused rather than reported."
)


def _fact(
    label: str,
    value: object,
    display: str,
    *,
    units: str = "",
    category: FactCategory = FactCategory.STRUCTURE,
    basis: Basis = Basis.HEURISTIC,
    detail: Detail = Detail.STANDARD,
    evidence: tuple[str, ...] = (),
    limitations: tuple[str, ...] = (),
) -> Fact:
    return Fact(
        category=category,
        label=label,
        value=value,
        display_value=display,
        source="solubility",
        basis=basis,
        units=units,
        detail=detail,
        evidence=evidence,
        limitations=limitations,
    )


def _method_chain(
    estimate: ModelEstimate, resolution: PKaResolution, solvent: Solvent, ionization: IonizationClass
) -> tuple[str, ...]:
    """Every layer that produced the number, so it is auditable without
    opening provenance. A chart makes a rough prediction look
    authoritative; the chain is what says how rough."""
    if resolution.source == "manual":
        ionisation = f"user-supplied pKa {list(resolution.values)}"
    elif resolution.status is PKaStatus.FOUND:
        ionisation = f"{resolution.method} predicted pKa {[round(v, 2) for v in resolution.values]}"
    elif ionization is IonizationClass.NEUTRAL:
        ionisation = "none -- no ionizable centre"
    else:
        ionisation = "unavailable"
    chain = [
        f"Model baseline: {estimate.label}",
        f"Ionization: {ionisation}",
        f"Solvent: {solvent.label}",
    ]
    if ionization in (IonizationClass.ACID, IonizationClass.BASE):
        chain.insert(2, "Adjustment: independent-site Henderson-Hasselbalch")
        chain.insert(3, f"Adjustment limit: +{MAX_PH_SOLUBILITY_ADJUSTMENT_LOG_UNITS:.2f} logS")
    if estimate.version:
        chain.append(f"Model version: {estimate.version}")
    return tuple(chain)


@dataclass(frozen=True)
class SolubilityAnalysis:
    """Everything both calculators need, computed once."""

    solvent: Solvent
    estimate: ModelEstimate
    resolution: PKaResolution
    ionization: IonizationClass
    molecular_weight: float
    pkas: list[float]
    is_acid: list[bool]
    #: Set when the analysis cannot proceed; the calculators turn it into
    #: a FAILED result carrying this text.
    refusal: str = ""

    @property
    def baseline_logs(self) -> float | None:
        return self.estimate.logs0

    @property
    def varies_with_ph(self) -> bool:
        return self.ionization in (IonizationClass.ACID, IonizationClass.BASE)


def analyse_solubility(
    mol: Chem.Mol,
    parameters: dict | None = None,
    interpreter_path: str | None = None,
    admet_interpreter_path: str | None = None,
) -> SolubilityAnalysis:
    """The shared front half of both calculators: solvent, baseline model,
    pKa, and which ionization regime applies.

    Refusals are returned rather than raised, because a refusal is an
    answer -- "this is an ampholyte and the model does not cover it" is
    information, where a traceback is not.
    """
    parameters = parameters or {}
    empty = ModelEstimate(model=ESOL, status=ModelStatus.UNAVAILABLE)
    try:
        solvent = resolve_solvent(parameters.get("solvent"))
    except KeyError as exc:
        return SolubilityAnalysis(
            solvent=WATER, estimate=empty,
            resolution=PKaResolution(status=PKaStatus.UNAVAILABLE),
            ionization=IonizationClass.UNSUPPORTED, molecular_weight=0.0,
            pkas=[], is_acid=[], refusal=str(exc).strip("'"),
        )

    model = str(parameters.get("model", ESOL))
    interpreter = admet_interpreter_path if model == AQSOLDB else interpreter_path
    estimate = model_logs0(mol, model, interpreter)

    try:
        resolution = resolve_pkas(mol, str(parameters.get("pka_values", "")), interpreter_path)
    except ValueError as exc:
        resolution = PKaResolution(status=PKaStatus.FAILED, reason=str(exc))

    ionization = classify_ionization(mol, resolution)
    pkas, is_acid = ([], [])
    if ionization in (IonizationClass.ACID, IonizationClass.BASE):
        pkas, is_acid = assign_site_polarity(mol, list(resolution.values))

    refusal = ""
    if ionization is IonizationClass.AMPHOLYTE:
        refusal = (
            "This molecule has both acidic and basic centres, so it is an ampholyte. "
            + _ZWITTERION_NOTE
        )
    elif ionization is IonizationClass.UNSUPPORTED:
        if not is_single_component(mol):
            refusal = (
                "This structure has more than one component. A salt or mixture is already the "
                "species the pH correction models forming, so applying it again would answer a "
                "different question. Draw the single parent compound instead."
            )
        else:
            refusal = resolution.reason or "No pKa values are available for this structure."
    elif estimate.status is not ModelStatus.AVAILABLE:
        refusal = estimate.reason

    return SolubilityAnalysis(
        solvent=solvent, estimate=estimate, resolution=resolution, ionization=ionization,
        molecular_weight=Descriptors.MolWt(mol), pkas=pkas, is_acid=is_acid, refusal=refusal,
    )


def _provenance(analysis: SolubilityAnalysis, parameters: dict) -> Provenance:
    """Enough to reproduce the number, including which model artifact made
    it -- a sidecar update would otherwise change a stored result silently."""
    return Provenance(
        created_by="core",
        method=analysis.estimate.label,
        parameters={
            "model": analysis.estimate.model,
            "model_status": analysis.estimate.status.value,
            "model_version": analysis.estimate.version,
            "model_artifact_sha256": analysis.estimate.artifact_sha256,
            "pka_source": analysis.resolution.source,
            "pka_status": analysis.resolution.status.value,
            "pka_values": list(analysis.resolution.values),
            "pka_method": analysis.resolution.method,
            "pka_input_text": analysis.resolution.input_text,
            "ionization_class": analysis.ionization.value,
            "solvent": analysis.solvent.key,
            "adjustment_limit_log_units": MAX_PH_SOLUBILITY_ADJUSTMENT_LOG_UNITS,
            "ph": float(parameters.get("pH", DEFAULT_PH)),
            "dose_mg": parameters.get("dose_mg"),
            "unit": str(parameters.get("unit", LOG_S)),
        },
    )


def _baseline_facts(analysis: SolubilityAnalysis, unit: str) -> list[Fact]:
    """The three unit renderings plus the category.

    All three are emitted whatever `unit` is chosen, which is why changing
    the display unit provably cannot change the model or the category --
    the unit orders the report, it does not feed the chemistry.
    """
    baseline = analysis.baseline_logs
    assert baseline is not None
    mw = analysis.molecular_weight
    mg_per_ml = logs_to_mg_per_ml(baseline, mw)
    ordered = [unit] + [u for u in DISPLAY_UNITS if u != unit]
    facts = [
        _fact(
            f"Predicted intrinsic solubility ({unit_symbol(name)})",
            in_unit(baseline, name, mw), format_in_unit(baseline, name, mw),
            units=unit_symbol(name),
            detail=Detail.STANDARD if name == unit else Detail.ADVANCED,
            evidence=(
                "The model's own output, read as the neutral species' solubility. That reading "
                "is an added assumption, not something the model claims.",
            ),
        )
        for name in ordered
    ]
    category = intrinsic_category(mg_per_ml)
    facts.append(
        _fact(
            "Solubility category", category.value, category.value,
            evidence=(
                f"ChemAxon's thresholds on INTRINSIC solubility: below "
                f"{LOW_MODERATE_BOUNDARY_MG_PER_ML} mg/mL Low, up to "
                f"{MODERATE_HIGH_BOUNDARY_MG_PER_ML} mg/mL Moderate, above it High.",
                f"Classified from {mg_per_ml:.4g} mg/mL.",
            ),
        )
    )
    return facts


def _ph_facts(analysis: SolubilityAnalysis, unit: str, ph: float) -> list[Fact]:
    baseline = analysis.baseline_logs
    assert baseline is not None
    mw = analysis.molecular_weight
    if not analysis.varies_with_ph:
        return [
            _fact(
                f"Predicted solubility at pH {ph:g}",
                in_unit(baseline, unit, mw), format_in_unit(baseline, unit, mw),
                units=unit_symbol(unit),
                evidence=("No ionizable centre, so solubility does not vary with pH.",),
            )
        ]
    adjustment = ph_adjustment(ph, analysis.pkas, analysis.is_acid)
    value = baseline + adjustment.applied
    limitations = ()
    if adjustment.limited:
        limitations = (
            _SALT_LIMIT_NOTE.format(limit=MAX_PH_SOLUBILITY_ADJUSTMENT_LOG_UNITS)
            + f" Unclamped, Henderson-Hasselbalch asks for +{adjustment.uncapped:.2f}.",
        )
    return [
        _fact(
            f"Predicted solubility at pH {ph:g}",
            in_unit(value, unit, mw), format_in_unit(value, unit, mw),
            units=unit_symbol(unit),
            evidence=(
                f"Baseline {baseline:.2f} logS raised by {adjustment.applied:.2f} for ionization "
                f"at pH {ph:g}.",
            ),
            limitations=limitations,
        )
    ]


def _model_facts(
    analysis: SolubilityAnalysis,
    mol: Chem.Mol,
    admet_interpreter_path: str | None,
    compare: bool = True,
) -> list[Fact]:
    """The method chain, and the two models' disagreement when BOTH really
    produced a number.

    **NEVER A MANUFACTURED DELTA.** An unavailable sidecar is not a
    disagreement, and rendering it as one would invent a discrepancy
    between a number and nothing.
    """
    chain = _method_chain(analysis.estimate, analysis.resolution, analysis.solvent, analysis.ionization)
    facts = [
        _fact(
            "Method", list(chain), chain[0].split(": ", 1)[-1],
            category=FactCategory.IDENTITY, evidence=chain,
        )
    ]
    if not compare:
        return facts
    other = AQSOLDB if analysis.estimate.model == ESOL else ESOL
    path = admet_interpreter_path if other == AQSOLDB else None
    comparison = model_logs0(mol, other, path)
    if comparison.status is ModelStatus.AVAILABLE and comparison.logs0 is not None:
        delta = abs(comparison.logs0 - (analysis.baseline_logs or 0.0))
        facts.append(
            _fact(
                "Model disagreement", delta, f"{delta:.2f}", units="logS",
                detail=Detail.ADVANCED,
                evidence=(
                    f"{analysis.estimate.label}: {analysis.baseline_logs:.2f} logS",
                    f"{comparison.label}: {comparison.logs0:.2f} logS",
                    "Two models, neither selected as correct. A gap is a reason to measure.",
                ),
            )
        )
    return facts


def compute_solubility(
    mol: Chem.Mol,
    molecule_uuid: str,
    parameters: dict | None = None,
    interpreter_path: str | None = None,
    admet_interpreter_path: str | None = None,
) -> ReportResult:
    """Intrinsic solubility, the value at a chosen pH, the category, and an
    ICH M9 high-solubility screening estimate."""
    parameters = parameters or {}
    analysis = analyse_solubility(mol, parameters, interpreter_path, admet_interpreter_path)
    provenance = _provenance(analysis, parameters)
    if analysis.refusal or analysis.baseline_logs is None:
        return ReportResult(
            report_id="solubility",
            name="Solubility",
            category="solubility",
            molecule_uuid=molecule_uuid,
            cache_state=CacheState.FAILED,
            error=analysis.refusal or "No solubility model could be applied.",
            provenance=provenance,
        )

    unit = str(parameters.get("unit", LOG_S))
    if unit not in DISPLAY_UNITS:
        unit = LOG_S
    ph = float(parameters.get("pH", DEFAULT_PH))

    facts = _baseline_facts(analysis, unit)
    facts += _ph_facts(analysis, unit, ph)
    facts += _model_facts(
        analysis, mol, admet_interpreter_path,
        compare=bool(parameters.get("compare_models", True)),
    )

    limitations = [_BCS_NOTE]
    dose_mg = parameters.get("dose_mg")
    dose = float(dose_mg) if dose_mg not in (None, "") else None
    window = evaluate_solubility_window(
        analysis.baseline_logs, analysis.pkas, analysis.is_acid, analysis.ionization
    )
    screen = bcs_high_solubility_screen(window, dose, analysis.molecular_weight)

    evidence = [
        f"ICH M9 window pH {BCS_PH_LOW}-{BCS_PH_HIGH}, {BCS_VOLUME_ML:g} mL.",
        "Status: model-based, not experimental.",
    ]
    if screen.minimum_mg_per_ml is not None:
        evidence.append(
            f"Lowest predicted solubility in the window: {screen.minimum_mg_per_ml:.4g} mg/mL "
            f"at pH {screen.minimum_ph:g}."
        )
    if screen.dose_number is not None:
        evidence.append(f"Dose number Do = {screen.dose_number:.3g} (high solubility needs Do <= 1).")
    if screen.dose_number_high is not None and screen.dose_number_low is not None:
        # The sandwich the verdict rests on, shown rather than implied --
        # a reader who sees only "PASS" cannot tell a comfortable margin
        # from one that turned on the adjustment safeguard.
        evidence.append(
            f"Bounded: Do is between {screen.dose_number_low:.3g} (solubility ceiling, "
            f"uncapped ionization) and {screen.dose_number_high:.3g} (floor, the neutral "
            f"species alone). The verdict uses whichever side settles it."
        )
    facts.append(
        _fact(
            "BCS high-solubility screening estimate",
            screen.outcome.value, screen.display,
            category=FactCategory.REGULATORY,
            evidence=tuple(evidence),
            limitations=(_BCS_NOTE,),
        )
    )

    return ReportResult(
        report_id="solubility",
        name="Solubility",
        category="solubility",
        molecule_uuid=molecule_uuid,
        facts=tuple(facts),
        assumptions=_method_chain(
            analysis.estimate, analysis.resolution, analysis.solvent, analysis.ionization
        ),
        limitations=tuple(limitations),
        provenance=provenance,
    )


def compute_solubility_curve(
    mol: Chem.Mol,
    molecule_uuid: str,
    parameters: dict | None = None,
    interpreter_path: str | None = None,
    admet_interpreter_path: str | None = None,
) -> PhCurveResult:
    """Solubility against pH, with the scalar findings carried alongside.

    **A NEUTRAL MOLECULE GETS A FLAT LINE, NOT A FAILURE.** Caffeine's
    solubility genuinely does not vary with pH, and that is an answer.
    `compute_logd_curve` declines the same molecule because a flat logD
    line tells you nothing you did not already know from logP -- the
    difference is real, which is why the pKa resolver hands back a status
    and lets each caller decide instead of deciding for both.
    """
    parameters = parameters or {}
    analysis = analyse_solubility(mol, parameters, interpreter_path, admet_interpreter_path)
    provenance = _provenance(analysis, parameters)
    if analysis.refusal or analysis.baseline_logs is None:
        return PhCurveResult(
            curve_id="solubility_curve",
            name="Solubility vs pH",
            method=analysis.estimate.label,
            molecule_uuid=molecule_uuid,
            cache_state=CacheState.FAILED,
            error=analysis.refusal or "No solubility model could be applied.",
            provenance=provenance,
        )

    unit = str(parameters.get("unit", LOG_S))
    if unit not in DISPLAY_UNITS:
        unit = LOG_S
    ph = float(parameters.get("pH", DEFAULT_PH))
    grid = ph_grid_from(parameters)
    mw = analysis.molecular_weight

    logs_values = profile(analysis.baseline_logs, grid, analysis.pkas, analysis.is_acid)
    series = {f"Solubility ({unit_symbol(unit)})": [in_unit(v, unit, mw) for v in logs_values]}

    facts = _baseline_facts(analysis, unit)
    facts += _ph_facts(analysis, unit, ph)
    facts += _model_facts(
        analysis, mol, admet_interpreter_path,
        compare=bool(parameters.get("compare_models", True)),
    )

    limited = [
        v for v in (ph_adjustment(p, analysis.pkas, analysis.is_acid) for p in grid) if v.limited
    ]
    if limited:
        facts.append(
            _fact(
                "Adjustment limit",
                MAX_PH_SOLUBILITY_ADJUSTMENT_LOG_UNITS,
                f"reached at {len(limited)} of {len(grid)} sampled pH values",
                units="logS",
                limitations=(_SALT_LIMIT_NOTE.format(limit=MAX_PH_SOLUBILITY_ADJUSTMENT_LOG_UNITS),),
            )
        )

    name = f"Solubility vs pH ({analysis.estimate.label})"
    if analysis.ionization is IonizationClass.NEUTRAL:
        name = "Solubility vs pH - no ionizable centre, so it does not vary"

    return PhCurveResult(
        curve_id="solubility_curve",
        name=name,
        method=analysis.estimate.label,
        molecule_uuid=molecule_uuid,
        ph_values=grid,
        series=series,
        y_label=unit_symbol(unit),
        facts=tuple(facts),
        provenance=provenance,
    )
