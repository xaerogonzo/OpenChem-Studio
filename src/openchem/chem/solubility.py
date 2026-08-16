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

    aspirin      ESOL -2.09   AqSolDB -1.62   Marvin -1.81   "exp" -2.19
    ibuprofen    ESOL -3.54                                        -3.62
    propranolol  ESOL -3.57                                        -3.62
    caffeine     ESOL -0.53                                        -0.80

**AND THE ASPIRIN ROW WAS LATER OVERTURNED, so it is left here with its
correction rather than quietly edited.** That -2.19 came from the
ESOL-era literature. The Solubility Challenge 2 interlaboratory mean is
**-1.67**, SD 0.15 over 16 sources -- much better evidence. Against it,
Marvin (0.14 off) and AqSolDB (0.05) both beat ESOL (0.42), which is the
opposite of the "ESOL beats Marvin on Marvin's own documentation
molecule" this file used to claim. Four molecules rank nothing; that is
what `benchmarks/solubility/` is for.

IT HAS SINCE BEEN RUN, on two independent sets, in both cases with
Delaney's own fitting set subtracted by InChIKey:

    Solubility Challenge 1        SC-2 tight set (interlab SD 0.17)
    all   n=67  MAE 0.74          all   n=73  MAE 0.90  RMSE 1.26
    acid  n=22        0.61                              bias +0.40
    base  n=29        0.81  bias -0.52    base n=17     bias -0.42

**THE BASE BIAS REPLICATES ACROSS BOTH SETS**, at -0.52 and -0.42. One
set makes it a curiosity; two independent ones make it a property of the
model. ESOL has no ionization term at all -- Delaney's paper never
mentions ionization, amines or salts -- so it cannot tell a base from a
neutral of the same size and lipophilicity.

**AND THE NUMBER ONLY MEANS ANYTHING NEXT TO A BASELINE.** On the same 73
compounds the General Solubility Equation scores RMSE 1.18 against ESOL's
1.26 -- and the GSE needs a measured melting point this app does not
have. The endpoint is hard; our figure is ordinary for it.

**UNCAPPED HENDERSON-HASSELBALCH IS UNUSABLE, and that is measured.**
Aspirin reaches 4.7e10 mg/mL at pH 14 -- correct arithmetic, meaningless
answer, the same failure this project already records at 40619 kcal/mol.
Two bounds stop it, and they say different things: Avdeef's cited
salt-precipitation rule (`SALT_LIMIT_LOG_UNITS_ACID`/`_BASE`) and a
pure-compound ceiling that is arithmetic declining to be absurd. Whichever
binds is named on the fact.
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

# --- where the profile stops rising ------------------------------------
#
# TWO SEPARATE BOUNDS, AND THEY SAY DIFFERENT THINGS. One is chemistry
# with a citation; the other is arithmetic refusing to be nonsense. A
# value that hits either says which.

#: Avdeef's **"sdiff 3-4" approximation** (Adv Drug Deliv Rev 59:568-590,
#: doi 10.1016/j.addr.2007.05.008, section 2.2): in 0.15 M NaCl, once
#: solubility exceeds its intrinsic value by about FOUR orders of
#: magnitude for a weak ACID and THREE for a weak BASE, the sodium and
#: chloride salts respectively begin to precipitate and the profile
#: levels off.
#:
#: This replaced a symmetric +2.0 that was inferred from one ChemAxon
#: screenshot and had no source. It is asymmetric because the two salts
#: are not equally soluble, and it is cited.
#:
#: **VERIFIED AGAINST THE PAPER'S OWN WORKED EXAMPLE.** Avdeef gives
#: amiodarone intrinsic 7.9e-9 M and an estimated Ksp of 1.2e-6 M^2
#: "using the sdiff 3-4 approximation". A base takes 3: 7.9e-9 x 10^3 =
#: 7.9e-6 M, times the 0.15 M counter-ion = 1.19e-6. That reproduces
#: their figure, which is what says this reading of the rule is right.
#:
#: **IT ASSUMES A SPARINGLY-SOLUBLE COMPOUND** -- the paper's own title.
#: For a drug whose intrinsic solubility is already appreciable, four
#: more orders of magnitude is not reachable, which is why the ceiling
#: below exists.
SALT_LIMIT_LOG_UNITS_ACID = 4.0
SALT_LIMIT_LOG_UNITS_BASE = 3.0

#: The condition Avdeef states the rule for. Recorded because the salt
#: plateau depends on it -- Si = Ksp / [counter-ion] -- so the rule is not
#: transferable to a different ionic strength without re-deriving it.
SALT_LIMIT_COUNTER_ION_MOLAR = 0.15

#: A solute cannot outweigh the solution it is dissolved in. At roughly
#: 1 g/mL this is 1000 mg/mL, and past it the number is arithmetic rather
#: than chemistry.
#:
#: **NOT A PREDICTED SOLUBILITY, and it is the second bound for a
#: measured reason.** Applying sdiff alone puts aspirin at 11,925 mg/mL at
#: pH 7.4 -- twelve kilograms per litre -- because its uncapped rise of
#: 3.91 never reaches the acid's 4.0 and its intrinsic solubility is
#: already 1.5 mg/mL. sdiff is right for the sparingly-soluble drugs it
#: was stated for and silent about everything else; this catches the rest.
MISCIBILITY_CEILING_MG_PER_ML = 1000.0

# --- solvents ----------------------------------------------------------


@dataclass(frozen=True)
class Solvent:
    """A solvent the predictor can answer for.

    Water is the model's home: the baseline model predicts aqueous
    solubility and the whole pH apparatus is defined on it. Every other
    solvent is reached by Abraham's solvation equation from that aqueous
    value -- see `chem/abraham.py` -- which is a LOOKUP on both sides and
    therefore covers a fixed set of compounds rather than any structure.
    """

    key: str
    label: str

    @property
    def is_water(self) -> bool:
        return self.key == "water"


WATER = Solvent(key="water", label="Water")


def _build_solvents() -> dict[str, Solvent]:
    """Water plus every solvent with MEASURED Abraham coefficients.

    Built from the shipped table rather than hand-listed, so the offered
    set and the answerable set cannot drift apart -- the failure
    `inapplicable_calculators` already suffered once in this codebase.
    """
    from openchem.chem.abraham import solvent_names

    solvents = {WATER.key: WATER}
    for name in solvent_names():
        key = name.strip().lower()
        if key != "water":
            solvents[key] = Solvent(key=key, label=name)
    return solvents


SOLVENTS: dict[str, Solvent] = _build_solvents()

#: McGowan's atomic volumes, cm^3/mol. From the characteristic-volume
#: definition used throughout Abraham's solvation work.
_MCGOWAN_ATOMIC_VOLUME = {
    1: 8.71, 5: 18.32, 6: 16.35, 7: 14.39, 8: 12.43, 9: 10.48,
    14: 26.83, 15: 24.87, 16: 22.91, 17: 20.95, 35: 26.21, 53: 34.53,
}
_MCGOWAN_BOND_DECREMENT = 6.56


def mcgowan_volume(mol: Chem.Mol) -> float:
    """McGowan characteristic volume Vx, in cm^3/mol / 100.

    Atomic volumes summed over every atom INCLUDING hydrogens, minus 6.56
    per bond. Purely constitutional -- no geometry, no fitting, no
    parameters anybody chose.

    **THIS IS THE ONE ABRAHAM SOLUTE DESCRIPTOR THAT IS EXACTLY
    COMPUTABLE.** Validated against published values to four decimals on
    eight compounds, benzene 0.7164 and water 0.1673 among them; see
    `test_the_mcgowan_volume_matches_published_values`.

    **IT IS NO LONGER WHAT THE NON-AQUEOUS ROUTE RUNS ON**, and this
    docstring said otherwise for a while. `chem/abraham.py` looks up all
    five descriptors including V, because a measured value beats a computed
    one even when the computation is exact -- mixing one computed
    descriptor into four measured ones would put the two on different
    footings inside a single sum. This stays as its own descriptor row,
    where being exactly computable is the whole point.
    """
    with_hydrogens = Chem.AddHs(mol)
    try:
        total = sum(
            _MCGOWAN_ATOMIC_VOLUME[atom.GetAtomicNum()] for atom in with_hydrogens.GetAtoms()
        )
    except KeyError as exc:
        raise ValueError(
            f"No McGowan atomic volume for element {exc.args[0]}. The published set covers "
            "H, B, C, N, O, F, Si, P, S, Cl, Br and I."
        ) from exc
    return (total - _MCGOWAN_BOND_DECREMENT * with_hydrogens.GetNumBonds()) / 100.0


#: Illustrative only, for the refusal message. Always filtered against the
#: real table before being shown -- this must never become a second source
#: of truth about what is supported.
_FAMILIAR_SOLVENTS = ("water", "ethanol", "methanol", "acetone", "toluene", "hexane")


def solvent_choices() -> list[str]:
    """The offered solvents, WATER FIRST and the rest alphabetical.

    Not `sorted(SOLVENTS)`: water sorts **last of 91** -- measured, not
    estimated -- so a plain alphabetical list buries the default at the
    very bottom. And the aqueous path is not merely the default: it is the
    one the pH curve, the BCS screen and the whole benchmark are about.
    """
    return [WATER.key] + sorted(key for key in SOLVENTS if key != WATER.key)


def resolve_solvent(key: str | None) -> Solvent:
    """The named solvent, or `KeyError` naming what is supported.

    Refuses rather than silently falling back to water: a user who asked
    for ethanol and got water's answer under ethanol's label has been given
    a wrong number, not a degraded one.

    The message names a HANDFUL and a count rather than all 91. A refusal
    nobody reads to the end is a refusal that failed to say anything, and
    the full list is one combo box away.

    The handful is FILTERED against the table rather than hardcoded, so a
    name that ever leaves the source simply stops being offered as an
    example instead of advertising a solvent that would then be refused.
    Taking the first six alphabetically instead gives `1,9-decadiene` and
    `1-chlorobutane`, which answer "is my solvent here?" for nobody.
    """
    chosen = (key or WATER.key).strip().lower()
    if chosen not in SOLVENTS:
        # **THE SPECIFIC REASON HAS TO LIVE HERE, NOT ONLY IN
        # `solvent_shift`.** This function refuses first, so a
        # predicted-only solvent never reaches that one -- the better
        # message was written for acetic acid and was unreachable for
        # acetic acid, which is the one case it exists for.
        from openchem.chem.abraham import predicted_only_reason

        reason = predicted_only_reason(chosen)
        if reason:
            raise KeyError(reason)
        examples = [name for name in _FAMILIAR_SOLVENTS if name in SOLVENTS]
        raise KeyError(
            f"No solubility model for solvent {chosen!r}. "
            f"{len(SOLVENTS)} solvents are supported, including {', '.join(examples)}."
        )
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


class LimitKind(Enum):
    """Which bound stopped the profile rising, because they mean different
    things and a fact derived from one must not read like the other."""

    NONE = "none"
    SALT_PRECIPITATION = "salt precipitation"
    PLAUSIBILITY_CEILING = "physical plausibility"


@dataclass(frozen=True)
class AdjustmentLimit:
    """The ceiling on the ionization adjustment, in log units, and why."""

    log_units: float
    kind: LimitKind
    #: What the salt rule alone would have allowed, kept so a fact can say
    #: which of the two bit.
    salt_log_units: float


def adjustment_limit(
    ionization: IonizationClass, baseline_logs: float, molecular_weight: float
) -> AdjustmentLimit:
    """How far ionization may raise this molecule's solubility.

    The tighter of two unrelated bounds: Avdeef's salt-precipitation rule,
    which is chemistry, and the pure-compound ceiling, which is arithmetic
    declining to be absurd. Whichever binds is named, because "the salt
    precipitates here" and "past here the number is meaningless" are not
    the same statement and must not render as one.
    """
    if ionization is IonizationClass.ACID:
        salt = SALT_LIMIT_LOG_UNITS_ACID
    elif ionization is IonizationClass.BASE:
        salt = SALT_LIMIT_LOG_UNITS_BASE
    else:
        # Nothing ionizes, so nothing rises; the ceiling still applies to
        # keep the contract uniform, and never bites.
        salt = 0.0

    ceiling = mg_per_ml_to_logs(MISCIBILITY_CEILING_MG_PER_ML, molecular_weight) - baseline_logs
    if ceiling < salt:
        return AdjustmentLimit(
            log_units=max(ceiling, 0.0),
            kind=LimitKind.PLAUSIBILITY_CEILING,
            salt_log_units=salt,
        )
    kind = LimitKind.NONE if salt == 0.0 else LimitKind.SALT_PRECIPITATION
    return AdjustmentLimit(log_units=salt, kind=kind, salt_log_units=salt)


@dataclass(frozen=True)
class PhAdjustment:
    """How much ionization added to the baseline at one pH, and whether a
    bound stopped it."""

    applied: float
    uncapped: float
    limited: bool


def ph_adjustment(
    ph: float,
    pkas: list[float],
    is_acid: list[bool],
    limit: float | None = None,
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
    limit: float | None = None,
) -> float:
    return baseline_logs + ph_adjustment(ph, pkas, is_acid, limit).applied


def profile(
    baseline_logs: float,
    ph_values: list[float],
    pkas: list[float],
    is_acid: list[bool],
    limit: float | None = None,
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
    limit: float | None = None,
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
    # Its OWN reason, and not UNSUPPORTED_SPECIES, which is what it borrowed
    # at first. That one says the MOLECULE is outside the model, which is
    # false and actively misleading here -- aspirin in ethanol is perfectly
    # well supported; ICH M9 is simply a criterion about aqueous media. A
    # refusal that names the wrong cause sends the reader to fix the wrong
    # thing.
    NON_AQUEOUS_SOLVENT = "ICH M9 is defined on aqueous media"


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

_SALT_LIMIT_NOTES = {
    LimitKind.SALT_PRECIPITATION: (
        "The rise is limited to +{limit:.1f} logS, where the counter-ion salt is expected to "
        "start precipitating -- Avdeef's 'sdiff 3-4' approximation (4 for an acid, 3 for a "
        "base) in 0.15 M NaCl. It is an approximation for sparingly-soluble drugs, not this "
        "compound's measured solubility product."
    ),
    LimitKind.PLAUSIBILITY_CEILING: (
        "The rise is limited to +{limit:.1f} logS by a pure-compound ceiling of "
        "{ceiling:.0f} mg/mL -- a solute cannot outweigh the solution holding it. This is "
        "arithmetic refusing to be nonsense, not a predicted saturation point, and it means "
        "the salt rule never bound for this molecule."
    ),
}

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
    estimate: ModelEstimate,
    resolution: PKaResolution,
    solvent: Solvent,
    ionization: IonizationClass,
    molecular_weight: float = 1.0,
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
        limit = adjustment_limit(ionization, estimate.logs0 or 0.0, molecular_weight or 1.0)
        chain.insert(3, f"Adjustment limit: +{limit.log_units:.1f} logS ({limit.kind.value})")
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
    #: `log Ss - log Sw` for a non-aqueous solvent, or None for water.
    shift: object = None

    @property
    def baseline_logs(self) -> float | None:
        """The baseline in the REQUESTED solvent.

        For water this is the model's own output. For anything else it is
        that value moved by Abraham's solvation equation -- which is why
        the category and every derived number below follow the solvent
        rather than silently describing water.
        """
        if self.estimate.logs0 is None:
            return None
        if self.shift is None:
            return self.estimate.logs0
        return self.estimate.logs0 + self.shift.log_shift

    @property
    def varies_with_ph(self) -> bool:
        """**pH IS AN AQUEOUS CONCEPT.** Henderson-Hasselbalch, the pKa
        values behind it and the ICH window are all defined on water, so a
        non-aqueous solvent gets an intrinsic solubility and no pH story
        at all rather than a curve that would look authoritative and mean
        nothing."""
        return self.solvent.is_water and self.ionization in (
            IonizationClass.ACID,
            IonizationClass.BASE,
        )

    @property
    def limit(self) -> AdjustmentLimit:
        """The bound for THIS molecule -- class-dependent, so it cannot be
        a module constant the way the old symmetric cap was."""
        return adjustment_limit(
            self.ionization, self.baseline_logs or 0.0, self.molecular_weight or 1.0
        )


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

    # A non-aqueous solvent is reached by lookup on BOTH sides, so it can
    # fail in ways water never does -- an unmeasured compound, or two
    # literature sources that disagree too much to average.
    shift = None
    if not solvent.is_water:
        from openchem.chem.abraham import solvent_shift

        outcome = solvent_shift(mol, solvent.label)
        if isinstance(outcome, str):
            return SolubilityAnalysis(
                solvent=solvent, estimate=estimate, resolution=resolution,
                ionization=ionization, molecular_weight=Descriptors.MolWt(mol),
                pkas=[], is_acid=[], refusal=outcome,
            )
        shift = outcome

    refusal = ""
    if not solvent.is_water:
        # Nothing downstream applies Henderson-Hasselbalch here, so a
        # missing pKa and an ampholyte are both irrelevant. Requiring them
        # anyway refused aspirin in ethanol for want of a number the
        # calculation never uses.
        if estimate.status is not ModelStatus.AVAILABLE:
            refusal = estimate.reason
        return SolubilityAnalysis(
            solvent=solvent, estimate=estimate, resolution=resolution,
            ionization=ionization, molecular_weight=Descriptors.MolWt(mol),
            pkas=[], is_acid=[], refusal=refusal, shift=shift,
        )
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
        shift=shift,
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
            "adjustment_limit_log_units": analysis.limit.log_units,
            "adjustment_limit_kind": analysis.limit.kind.value,
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
    aqueous = analysis.solvent.is_water
    ordered = [unit] + [u for u in DISPLAY_UNITS if u != unit]

    # **THE ROW MUST NAME THE SOLVENT WHEN IT IS NOT WATER.** `baseline_logs`
    # already carries the Abraham shift, so an unqualified "intrinsic
    # solubility" row was reporting an ETHANOL number in an aqueous
    # calculation's wording. Found by rendering the panel; every test passed.
    if aqueous:
        heading = "Predicted intrinsic solubility"
        evidence = (
            "The model's own output, read as the neutral species' solubility. That reading "
            "is an added assumption, not something the model claims.",
        )
    else:
        heading = f"Predicted solubility in {analysis.solvent.label}"
        evidence = (
            f"Aqueous baseline {analysis.estimate.logs0:.2f} logS moved by "
            f"{analysis.shift.log_shift:+.2f} via Abraham's solvation equation.",
            "Both the solvent coefficients and the solute descriptors are measured values; "
            "the AQUEOUS baseline is still a prediction, so its error carries through.",
        )
    facts = [
        _fact(
            f"{heading} ({unit_symbol(name)})",
            in_unit(baseline, name, mw), format_in_unit(baseline, name, mw),
            units=unit_symbol(name),
            detail=Detail.STANDARD if name == unit else Detail.ADVANCED,
            evidence=evidence,
        )
        for name in ordered
    ]

    if not aqueous:
        # **THE THRESHOLDS ARE AQUEOUS AND SAYING SO IS THE WHOLE POINT.**
        # ChemAxon states Low/Moderate/High for INTRINSIC (aqueous)
        # solubility; they encode expectations about dissolution in the gut,
        # not about a compound's behaviour in ethanol. Classifying 52.81
        # mg/mL in ethanol as "High" would borrow an aqueous verdict's
        # authority for a different question -- the same mistake the BCS
        # screen is scoped against one function below, missed here until the
        # panel was rendered.
        #
        # Emitted as an explicit refusal rather than omitted: a MISSING row
        # reads as "not computed yet", where the point is that it does not
        # apply.
        return facts + [
            _fact(
                "Solubility category", "n/a", "Not applicable outside water",
                evidence=(
                    "ChemAxon's Low/Moderate/High thresholds are defined on INTRINSIC AQUEOUS "
                    "solubility. There is no published equivalent for other solvents, and "
                    "reusing the aqueous numbers would be inventing one.",
                ),
            )
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
    if not analysis.solvent.is_water:
        # No pH LABEL at all, rather than a pH-labelled row carrying an
        # aqueous number's clothes.
        #
        # And NO ROW AT ALL, because `_baseline_facts` now names the solvent
        # itself. This used to emit a fourth row carrying the same number as
        # the three unit rows above it -- outside water there is no pH
        # adjustment, so "baseline" and "at pH" coincide exactly and the
        # panel repeated one value four times. Visible the moment it was
        # rendered; invisible to every test, which read labels rather than
        # asking whether two rows said the same thing.
        return []
    if not analysis.varies_with_ph:
        return [
            _fact(
                f"Predicted solubility at pH {ph:g}",
                in_unit(baseline, unit, mw), format_in_unit(baseline, unit, mw),
                units=unit_symbol(unit),
                evidence=("No ionizable centre, so solubility does not vary with pH.",),
            )
        ]
    limit = analysis.limit
    adjustment = ph_adjustment(ph, analysis.pkas, analysis.is_acid, limit.log_units)
    value = baseline + adjustment.applied
    limitations = ()
    if adjustment.limited:
        limitations = (
            _SALT_LIMIT_NOTES[limit.kind].format(
                limit=limit.log_units, ceiling=MISCIBILITY_CEILING_MG_PER_ML
            )
            + f" Unlimited, Henderson-Hasselbalch asks for +{adjustment.uncapped:.2f}.",
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
    chain = _method_chain(
        analysis.estimate, analysis.resolution, analysis.solvent, analysis.ionization,
        analysis.molecular_weight,
    )
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
    if not analysis.solvent.is_water:
        # ICH M9 is a criterion about aqueous media. Reporting it for a
        # solubility in hexane would be a regulatory-shaped answer to a
        # question the regulation does not ask.
        screen = BcsScreen.undetermined(BcsReason.NON_AQUEOUS_SOLVENT)
        window = None
    else:
        window = evaluate_solubility_window(
            analysis.baseline_logs, analysis.pkas, analysis.is_acid, analysis.ionization,
            # The DISPLAYED minimum honours the bound; the verdict does not
            # read it at all (see `bcs_high_solubility_screen`).
            limit=analysis.limit.log_units,
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
            analysis.estimate, analysis.resolution, analysis.solvent, analysis.ionization,
            analysis.molecular_weight,
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

    if not analysis.solvent.is_water:
        return PhCurveResult(
            curve_id="solubility_curve",
            name="Solubility vs pH",
            method=analysis.estimate.label,
            molecule_uuid=molecule_uuid,
            cache_state=CacheState.FAILED,
            error=(
                f"pH is an aqueous concept, so there is no solubility-versus-pH curve in "
                f"{analysis.solvent.label}. The Solubility calculator reports an intrinsic "
                f"value there instead."
            ),
            provenance=provenance,
        )

    unit = str(parameters.get("unit", LOG_S))
    if unit not in DISPLAY_UNITS:
        unit = LOG_S
    ph = float(parameters.get("pH", DEFAULT_PH))
    grid = ph_grid_from(parameters)
    mw = analysis.molecular_weight
    limit = analysis.limit

    # The DRAWN curve must honour the same bound the facts describe.
    # Caught by rendering it: the facts said "limited at +3.0 logS" while
    # the chart climbed to 1.8e8 mg/mL, because this call was the one site
    # the resolved limit had not been threaded into. A fact and a picture
    # disagreeing is worse than either being wrong alone.
    logs_values = profile(
        analysis.baseline_logs, grid, analysis.pkas, analysis.is_acid, limit.log_units
    )
    series = {f"Solubility ({unit_symbol(unit)})": [in_unit(v, unit, mw) for v in logs_values]}

    facts = _baseline_facts(analysis, unit)
    facts += _ph_facts(analysis, unit, ph)
    facts += _model_facts(
        analysis, mol, admet_interpreter_path,
        compare=bool(parameters.get("compare_models", True)),
    )

    limited = [
        v
        for v in (
            ph_adjustment(p, analysis.pkas, analysis.is_acid, limit.log_units) for p in grid
        )
        if v.limited
    ]
    if limited:
        facts.append(
            _fact(
                f"Adjustment limit ({limit.kind.value})",
                limit.log_units,
                f"+{limit.log_units:.1f} logS, reached at {len(limited)} of {len(grid)} sampled pH values",
                units="logS",
                limitations=(
                    _SALT_LIMIT_NOTES[limit.kind].format(
                        limit=limit.log_units, ceiling=MISCIBILITY_CEILING_MG_PER_ML
                    ),
                ),
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
