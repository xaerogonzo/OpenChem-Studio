"""Properties as a function of pH.

pKa microspecies distribution, isoelectric point, logD-vs-pH, and hydrogen
bond donor/acceptor counts across the pH range -- the four consumers that
justified `PhCurveResult` when it was built.

THE SPECIATION MATH, verified before implementation:

    alpha_j(pH) = beta_j * h^(n-j) / SUM_m beta_m * h^(n-m)

with h = 10^-pH, beta_0 = 1, beta_j = product of the first j dissociation
constants. Checked live: a monoprotic acid is exactly 50/50 at its pKa,
a diprotic system's fractions sum to 1.0 at every pH and cross at 50% at
each pKa, and glycine (pKa 2.34 / 9.60) gives a computed isoelectric point
of 5.970 against the textbook 5.97.

AN ASSUMPTION WORTH KNOWING: the pKa values are treated as MACROSCOPIC,
sequential dissociation constants. pkasolver predicts per-site values,
which are closer to microscopic constants. For the monoprotic and
well-separated polyprotic molecules that dominate in practice the two
coincide; for a molecule with several similar-pKa sites the true
speciation is more complex than this. Stated rather than hidden.
"""

from __future__ import annotations

from typing import Any

from rdkit import Chem
from rdkit.Chem import Crippen, Lipinski

from openchem.chem.calculator_options import ph_grid_from
from openchem.domain.common import CacheState, Provenance
from openchem.domain.scientific_result import (
    AlertResult,
    PhCurveResult,
    StructureEntry,
    StructureSetResult,
)

PH_MIN = 0.0
PH_MAX = 14.0
PH_STEP = 0.25


def ph_grid(step: float = PH_STEP) -> list[float]:
    count = int(round((PH_MAX - PH_MIN) / step)) + 1
    return [PH_MIN + index * step for index in range(count)]


def microspecies_fractions(ph: float, pkas: list[float]) -> list[float]:
    """Fraction of each protonation state at `ph`.

    Returns `len(pkas) + 1` values: index j is the species with j protons
    removed, so index 0 is fully protonated. Sums to 1.0.
    """
    if not pkas:
        return [1.0]
    h = 10.0 ** -ph
    constants = [10.0 ** -pka for pka in sorted(pkas)]
    n = len(constants)

    beta = [1.0]
    for constant in constants:
        beta.append(beta[-1] * constant)

    terms = [beta[j] * h ** (n - j) for j in range(n + 1)]
    total = sum(terms)
    if total <= 0.0:
        return [1.0] + [0.0] * n
    return [term / total for term in terms]


def species_charges(n_acids: int, n_bases: int) -> list[int]:
    """Net charge of each protonation state.

    The fully protonated form carries +1 per basic centre (acids are
    neutral when protonated); each successive deprotonation removes one
    positive charge, so the fully deprotonated form is -1 per acidic
    centre. Verified by construction against glycine's +1 -> 0 -> -1.
    """
    total_steps = n_acids + n_bases
    return [n_bases - j for j in range(total_steps + 1)]


def net_charge_at_ph(
    ph: float, pkas: list[float], n_acids: int, n_bases: int, permanent_charge: int = 0
) -> float:
    fractions = microspecies_fractions(ph, pkas)
    charges = species_charges(n_acids, n_bases)
    # zip() truncates to the shorter list: a predictor can return a
    # different number of pKa values than the molecule has matched
    # ionizable groups, and averaging over a mismatched pairing is worse
    # than averaging over the part that does line up.
    return permanent_charge + sum(f * c for f, c in zip(fractions, charges))


def isoelectric_point(
    pkas: list[float], n_acids: int, n_bases: int, permanent_charge: int = 0
) -> float | None:
    """The pH where net charge crosses zero, by bisection.

    `None` when the charge never crosses zero anywhere in 0-14 -- a
    permanently charged molecule genuinely has no isoelectric point, and
    reporting a boundary value would invent one.
    """
    def charge(ph: float) -> float:
        return net_charge_at_ph(ph, pkas, n_acids, n_bases, permanent_charge)

    low, high = PH_MIN, PH_MAX
    if charge(low) * charge(high) > 0:
        return None
    for _ in range(80):
        middle = (low + high) / 2.0
        if charge(low) * charge(middle) <= 0:
            high = middle
        else:
            low = middle
    return (low + high) / 2.0


def _resolve_pkas(
    mol: Chem.Mol, interpreter_path: str | None
) -> tuple[list[float], int, int, str | None]:
    """Predicted pKa values plus the molecule's acidic/basic centre counts.

    The last element is an error message when pKa is unavailable -- every
    curve here needs real pKa values, and there is no honest fallback that
    produces a curve rather than a flat line.
    """
    from openchem.chem.logd import classify_ionizable_centres
    from openchem.chem.pka_providers import compute_pka, pka_predictor_available

    n_acids, n_bases = classify_ionizable_centres(mol)
    if n_acids == 0 and n_bases == 0:
        return [], 0, 0, "This molecule has no ionizable centre, so nothing varies with pH."
    if not pka_predictor_available(interpreter_path):
        return (
            [],
            n_acids,
            n_bases,
            "Numeric pKa is needed for pH curves. pkasolver runs out of process from its own "
            "environment -- set it up under Tools > External Tools.",
        )
    try:
        pairs = compute_pka(mol, interpreter_path) or []
    except RuntimeError as exc:
        return [], n_acids, n_bases, str(exc)
    return sorted(p.value for p in pairs), n_acids, n_bases, None


def _failed_curve(curve_id: str, name: str, molecule_uuid: str, message: str) -> PhCurveResult:
    return PhCurveResult(
        curve_id=curve_id,
        name=name,
        method="pkasolver",
        molecule_uuid=molecule_uuid,
        cache_state=CacheState.FAILED,
        error=message,
        provenance=Provenance(created_by="core", method="pkasolver"),
    )


def compute_pka_distribution(
    mol: Chem.Mol, molecule_uuid: str, parameters: dict[str, Any] | None = None,
    interpreter_path: str | None = None,
) -> PhCurveResult:
    """Microspecies distribution (%) against pH -- Marvin's pKa plugin chart."""
    pkas, n_acids, n_bases, error = _resolve_pkas(mol, interpreter_path)
    if error:
        return _failed_curve("pka_microspecies", "Microspecies distribution", molecule_uuid, error)

    grid = ph_grid_from(parameters)
    rows = [microspecies_fractions(ph, pkas) for ph in grid]
    charges = species_charges(n_acids, n_bases)
    series: dict[str, list[float]] = {}
    for index in range(len(pkas) + 1):
        charge = charges[index] if index < len(charges) else None
        label = f"Species {index}" if charge is None else f"Species {index} ({charge:+d})"
        series[label] = [100.0 * row[index] for row in rows]

    return PhCurveResult(
        curve_id="pka_microspecies",
        name="Microspecies distribution (%)",
        method="pkasolver",
        molecule_uuid=molecule_uuid,
        ph_values=grid,
        series=series,
        y_label="% of total",
        # A distribution is bounded by construction; without pinning these
        # the shared widget's padding would draw an axis from -8% to 108%.
        y_min=0.0,
        y_max=100.0,
        provenance=Provenance(
            created_by="core", method="pkasolver", parameters={"pka_values": pkas}
        ),
    )


def compute_isoelectric_point(
    mol: Chem.Mol, molecule_uuid: str, parameters: dict[str, Any] | None = None,
    interpreter_path: str | None = None,
) -> PhCurveResult:
    """Net charge against pH, with the isoelectric point named."""
    pkas, n_acids, n_bases, error = _resolve_pkas(mol, interpreter_path)
    if error:
        return _failed_curve("isoelectric_point", "Isoelectric point", molecule_uuid, error)

    permanent = Chem.GetFormalCharge(mol)
    grid = ph_grid_from(parameters)
    charges = [net_charge_at_ph(ph, pkas, n_acids, n_bases, permanent) for ph in grid]
    pi = isoelectric_point(pkas, n_acids, n_bases, permanent)

    name = f"Charge vs pH — pI = {pi:.2f}" if pi is not None else "Charge vs pH — no isoelectric point in 0-14"
    return PhCurveResult(
        curve_id="isoelectric_point",
        name=name,
        method="pkasolver",
        molecule_uuid=molecule_uuid,
        ph_values=grid,
        series={"Net charge": charges},
        y_label="charge",
        provenance=Provenance(
            created_by="core", method="pkasolver", parameters={"pI": pi, "pka_values": pkas}
        ),
    )


def compute_logd_curve(
    mol: Chem.Mol, molecule_uuid: str, parameters: dict[str, Any] | None = None,
    interpreter_path: str | None = None,
) -> PhCurveResult:
    """logD across the pH range -- the shipped single-pH `logd` calculator
    sampled, reusing its exact Henderson-Hasselbalch implementation rather
    than a second copy of the formula.

    KNOWN LIMITATION, ZWITTERIONS. Henderson-Hasselbalch logD assumes the
    species that partitions is the one with NO site ionized. For an
    amphoteric molecule that assumption breaks: glycine at pH 7 is
    essentially all zwitterion (+NH3-CH2-COO-), and the wholly un-ionized
    form is vanishingly rare, so the model returns a far more negative
    logD than experiment (roughly -4.7 here against a measured value near
    -3.2, because real zwitterions do partition a little).

    The curve makes this much more visible than the single-pH calculator
    did, which is why it is written down rather than left for someone to
    rediscover. Modelling it properly needs a separate partition
    coefficient for the zwitterion, which no data source here provides.
    Monoprotic acids and bases -- the overwhelmingly common drug-like case
    -- are unaffected, and were checked against ibuprofen and propranolol.
    """
    from openchem.chem.logd import logd_from_pkas

    pkas, _n_acids, _n_bases, error = _resolve_pkas(mol, interpreter_path)
    if error:
        return _failed_curve("logd_curve", "LogD vs pH", molecule_uuid, error)

    grid = ph_grid_from(parameters)
    values = [logd_from_pkas(mol, ph, pkas) for ph in grid]
    if any(value is None for value in values):
        return _failed_curve(
            "logd_curve", "LogD vs pH", molecule_uuid, "No ionizable centre to vary with pH."
        )

    return PhCurveResult(
        curve_id="logd_curve",
        name=f"LogD vs pH (LogP = {Crippen.MolLogP(mol):.2f})",
        method="pkasolver",
        molecule_uuid=molecule_uuid,
        ph_values=grid,
        series={"logD": [float(value) for value in values]},
        y_label="logD",
        provenance=Provenance(
            created_by="core", method="pkasolver", parameters={"pka_values": pkas}
        ),
    )


def compute_hbond_vs_ph(
    mol: Chem.Mol, molecule_uuid: str, parameters: dict[str, Any] | None = None,
    interpreter_path: str | None = None,
) -> PhCurveResult:
    """Hydrogen-bond donor and acceptor counts against pH.

    Counted on the DOMINANT microspecies at each pH via Dimorphite-DL,
    which is honest about what it is: Marvin describes a weighted average
    over all microspecies, and computing that would need each microspecies'
    actual structure rather than just its fraction. Named accordingly so
    the two are not confused.

    Needs no pKa predictor -- Dimorphite-DL alone gives the dominant form,
    so this curve works without the optional pkasolver install.
    """
    from openchem.chem.pka_providers import protonate_at_ph

    # Coarser than the other curves: this one builds a real structure per
    # point rather than evaluating a closed form. Measured at ~2 ms per
    # call, so 29 points is still imperceptible.
    grid = ph_grid_from(parameters, step=0.5)
    donors: list[float] = []
    acceptors: list[float] = []
    for ph in grid:
        try:
            species = protonate_at_ph(mol, ph)
        except Exception:  # noqa: BLE001 - fall back to the drawn form for this point
            species = mol
        donors.append(float(Lipinski.NumHDonors(species)))
        acceptors.append(float(Lipinski.NumHAcceptors(species)))

    return PhCurveResult(
        curve_id="hbond_vs_ph",
        name="H-bond donors/acceptors vs pH (dominant microspecies)",
        method="dimorphite_dl",
        molecule_uuid=molecule_uuid,
        ph_values=grid,
        series={"Donors": donors, "Acceptors": acceptors},
        y_label="count",
        y_min=0.0,
        provenance=Provenance(created_by="core", method="dimorphite_dl"),
    )


def compute_major_microspecies(
    mol: Chem.Mol, molecule_uuid: str, parameters: dict[str, Any] | None = None
) -> StructureSetResult:
    """The dominant protonation form at a given pH -- Marvin's Major
    Microspecies plugin. Returned as a one-entry structure set so it gets
    the grid's depiction for free."""
    from openchem.chem.pka_providers import protonate_at_ph
    from rdkit.Chem import AllChem

    parameters = parameters or {}
    ph = float(parameters.get("pH", 7.4))
    try:
        species = protonate_at_ph(mol, ph)
    except Exception as exc:  # noqa: BLE001 - report, never crash
        return StructureSetResult(
            set_id="major_microspecies",
            name="Major microspecies",
            method="dimorphite_dl",
            molecule_uuid=molecule_uuid,
            cache_state=CacheState.FAILED,
            error=str(exc),
            provenance=Provenance(created_by="core", method="dimorphite_dl"),
        )

    prepared = Chem.Mol(species)
    if prepared.GetNumConformers() == 0:
        AllChem.Compute2DCoords(prepared)
    smiles = Chem.MolToSmiles(species)
    return StructureSetResult(
        set_id="major_microspecies",
        name=f"Major microspecies at pH {ph:g}",
        method="dimorphite_dl",
        molecule_uuid=molecule_uuid,
        entries=[
            StructureEntry(
                molblock=Chem.MolToMolBlock(prepared),
                label=f"{smiles} (charge {Chem.GetFormalCharge(species):+d})",
                metadata={"smiles": smiles, "pH": ph},
            )
        ],
        provenance=Provenance(created_by="core", method="dimorphite_dl", parameters={"pH": ph}),
    )
