"""The third Fukui gate: does the search for other cation states make f- a function of the structure? The typed panel, the rules and the pure judge.

`benchmarks/fukui_v3/PREREGISTRATION.md` says what is claimed and what a verdict does. This module is the part of it that is code: the species, the tolerances and `judge`, which reads records
(plain mappings, written by `benchmarks/fukui_v3/run_gate.py`) and decides, so that the arithmetic of the verdict is tested on invented records before any real one exists. Nothing here
runs ORCA or imports RDKit; the atoms' symmetry classes arrive as data. It shares the second gate's tolerance, floor limit, attempt rule and ORCA version (`app/fukui_gate.py`).

Three decided arms and one that is only reported:

* **R, reproducibility.** For each of the 12 species, f- of every perturbed run (four rigid rotations and four 0.001 A displacements of one geometry, and for the species marked in `PANEL`, three
  independent optimizations) agrees with f- of the reference run to `REPRODUCIBILITY_LIMIT`, atom class by atom class.
* **C, completeness.** For each of the 12, the search the application runs (the default job and holes in the HOMO-1, -2 and -3) finds the lowest state and every state within the window that an
  exhaustive search (holes down to the HOMO-7) finds on the same geometry.
* **N, no regression.** The eight species the second gate's calculation reproduced in every number are reproduced within the second gate's tolerance by this calculation too.
* **The reported arm** never decides: how often a perturbed run reported a competing state that the reference run found, benzene's degenerate level, methane, timings.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from openchem.app import fukui_gate_2 as second
from openchem.app.fukui_gate import FLOOR_LIMIT, MAX_ATTEMPTS, ORCA_VERSION
from openchem.chem.fukui_states import CHARGE_TOLERANCE, LEVEL_MARGIN_EV, WINDOW_EV

#: What the reachability guard accepts for a module nothing in the application imports: the gate's runner (`benchmarks/fukui_v3/run_gate.py`) and its tests are its only users, as the
#: gate is run from the command line and not from the window.
REACHED_BY = (
    "tooling: imported only by benchmarks/fukui_v3/run_gate.py, the script that runs the third Fukui gate, and by its tests; the gate is not a feature of the window"
)

__all__ = [
    "CHARGE_TOLERANCE", "DISPLACEMENTS", "DISPLACEMENT_SIGMA", "EMBEDDING_SEEDS", "EXHAUSTIVE_OFFSETS", "FLOOR_LIMIT", "FLOOR_SPECIES", "MAX_ATTEMPTS", "N_SPECIES", "ORCA_VERSION", "PANEL",
    "PUBLISHED_TOLERANCE", "PanelSpecies", "REPORTED_SPECIES", "REPRODUCIBILITY_LIMIT", "ROTATIONS", "Verdict", "class_sorted_difference", "judge", "match_states",
]

#: R: the largest difference allowed, atom class by atom class, between a perturbed run's f- and the reference run's. It lies between the 0.0004 by which jobs that reached one state agreed in
#: charge and the 0.085 by which the closest two states differed (`chem.fukui_states`), and above the 0.0021 a 0.001 A displacement of benzaldehyde moved f- in the pilot
#: (`benchmarks/fukui_v3/DESIGN.md`): a tenth of the smaller difference between two states that was seen.
REPRODUCIBILITY_LIMIT = 0.01

#: N: the second gate's tolerance, kept so that "reproduces the published number" means what it meant there.
PUBLISHED_TOLERANCE = second.TOLERANCE

#: The perturbations of R: how many rigid rotations of the reference geometry each species is run on.
ROTATIONS = 4
#: How many displaced copies of the reference geometry each species is run on.
DISPLACEMENTS = 4
#: The standard deviation, in Angstrom, of the Gaussian noise added to every coordinate of a displaced copy: about the optimizer's own tolerance.
DISPLACEMENT_SIGMA = 0.001
#: The RDKit embedding seeds of the independent optimizations of the species that have them (the reference geometry's own is 7).
EMBEDDING_SEEDS = (101, 102, 103)

#: The holes of the exhaustive search C compares with: the HOMO-1 to the HOMO-7.
EXHAUSTIVE_OFFSETS = tuple(range(1, 8))

#: One Hartree in eV (the CODATA value `conceptual_dft` uses), to say how far apart two states' absolute energies are.
_HARTREE_TO_EV = 27.211386245988
#: Float slack for "within" comparisons, so a value exactly on a bound is on the right side of it.
_SLACK = 1e-9


@dataclass(frozen=True)
class PanelSpecies:
    """One molecule of the decided arms R and C."""

    name: str
    smiles: str
    charge: int
    #: "close" (a second state within the window was found by the second gate's probes), "clean" (none was), "held out" (never run through any probe or gate), "floor" or "degenerate".
    group: str
    #: Whether R also runs three independent optimizations of it.
    embeddings: bool = False
    level: str = second.LEVEL_6_31GS

    @property
    def method_basis(self) -> str:
        return second.METHOD_BASIS[self.level]

    def variants(self) -> tuple[str, ...]:
        """The runs of R, reference first: `reference`, `rotation0` ..., `displacement0` ..., and `embedding101` ... for the species that have them."""
        names = ["reference", *(f"rotation{k}" for k in range(ROTATIONS)), *(f"displacement{k}" for k in range(DISPLACEMENTS))]
        if self.embeddings:
            names += [f"embedding{seed}" for seed in EMBEDDING_SEEDS]
        return tuple(names)


#: The twelve species of R and C. The first eight are the second gate's (the four whose cation states the probes found close, and four clean ones); the last four were never run through any probe or
#: gate, chosen as pi systems with a lone pair or a methyl group, before any of them was run.
PANEL = (
    PanelSpecies("benzaldehyde", "O=Cc1ccccc1", 0, "close", embeddings=True),
    PanelSpecies("anilinium", "[NH3+]c1ccccc1", 1, "close", embeddings=True),
    PanelSpecies("thiophene", "c1ccsc1", 0, "close", embeddings=True),
    PanelSpecies("HCN", "C#N", 0, "close", embeddings=True),
    PanelSpecies("phenol", "Oc1ccccc1", 0, "clean"),
    PanelSpecies("aniline", "Nc1ccccc1", 0, "clean"),
    PanelSpecies("pyrrole", "c1cc[nH]c1", 0, "clean"),
    PanelSpecies("furan", "c1ccoc1", 0, "clean"),
    PanelSpecies("pyridine", "c1ccncc1", 0, "held out"),
    PanelSpecies("toluene", "Cc1ccccc1", 0, "held out", embeddings=True),
    PanelSpecies("naphthalene", "c1ccc2ccccc2c1", 0, "held out"),
    PanelSpecies("acetophenone", "CC(=O)c1ccccc1", 0, "held out", embeddings=True),
)

#: The two molecules the noise floors are measured on, in neither the panel nor either earlier gate.
FLOOR_SPECIES = (
    PanelSpecies("acetaldehyde", "CC=O", 0, "floor"),
    PanelSpecies("ethylene", "C=C", 0, "floor"),
)

#: Reported and never decided: benzene, whose HOMO is a degenerate pair (the averaging rule), and methane, whose cation the exploratory run showed is not a two-component level.
REPORTED_SPECIES = (
    PanelSpecies("benzene", "c1ccccc1", 0, "degenerate"),
    PanelSpecies("methane", "C", 0, "degenerate"),
)

#: N: the species the second gate's calculation reproduced in every number (27 of its 47), by the second gate's own names.
N_SPECIES = ("phenol", "aniline", "fluorobenzene", "styrene", "nitrobenzene", "acrolein", "N2O", "NO2-")


# --- R: one run against its reference ---------------------------------------------------------------------------------------------


def class_sorted_difference(first: Sequence[float], other: Sequence[float], classes: Sequence[Sequence[int]]) -> float:
    """The largest difference between two runs' per-atom values, atom class by atom class, each class's values sorted.

    Two atoms of one symmetry class (the two ortho carbons of a ring, the hydrogens of a methyl group) are the same atom up to which way a molecule was embedded, so the question is whether
    the run produced the same SET of values for the class, not whether atom 4 is atom 4: an optimization from another embedding may put a substituent on the other side of the ring.
    """
    if len(first) != len(other):
        return math.inf
    worst = 0.0
    for members in classes:
        a, b = sorted(first[index] for index in members), sorted(other[index] for index in members)
        worst = max(worst, max((abs(x - y) for x, y in zip(a, b)), default=0.0))
    return worst


@dataclass(frozen=True)
class ReproducibilityRow:
    species: str
    variant: str
    difference: float
    within: bool


# --- C: the states a search found ---------------------------------------------------------------------------------------------------


def match_states(
    wanted: Sequence[Mapping], found: Sequence[Mapping], *, energy_margin: float = LEVEL_MARGIN_EV, charge_tolerance: float = CHARGE_TOLERANCE
) -> list[Mapping]:
    """The states of `wanted` that no state of `found` matches. A state is a mapping with `energy_hartree` and `charges`; two match when their ENERGIES (absolute, so a search that missed
    the lowest state does not match the others by being measured from a higher zero) are within `energy_margin` eV and no atom's charge differs by more than `charge_tolerance`."""
    missing = []
    for state in wanted:
        if not any(
            abs(state["energy_hartree"] - other["energy_hartree"]) * _HARTREE_TO_EV <= energy_margin + _SLACK
            and len(state["charges"]) == len(other["charges"])
            and all(abs(a - b) <= charge_tolerance + _SLACK for a, b in zip(state["charges"], other["charges"]))
            for other in found
        ):
            missing.append(state)
    return missing


@dataclass(frozen=True)
class CompletenessRow:
    species: str
    #: How far the exhaustive search's lowest state lies below the application search's, in eV (0.0 when they agree).
    lowest_missed_ev: float
    #: The exhaustive search's states within the window that the application's search did not find.
    missed: tuple[Mapping, ...]
    within: bool


# --- the verdict -------------------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Verdict:
    outcome: str
    reasons: tuple[str, ...]
    reproducibility: tuple[ReproducibilityRow, ...] = ()
    completeness: tuple[CompletenessRow, ...] = ()
    regression: tuple = ()
    site_rows: tuple = ()
    arms: Mapping[str, bool] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return self.outcome == "PASS"


def _level_of(molecule: str) -> str:
    return second.ALL_SPECIES[molecule].level


def judge(
    *,
    runs: Sequence[Mapping],
    exhaustive: Sequence[Mapping],
    published_runs: Sequence[second.MeasuredRun],
    floor: float | None,
    classes: Mapping[str, Sequence[Sequence[int]]],
) -> Verdict:
    """The verdict of the three decided arms from the records of a gate run.

    `runs`: one mapping per run of R, with `species`, `variant`, `f_minus` (per atom), `completed` (False when ORCA could not compute it in `MAX_ATTEMPTS` attempts), `orca_version`, `dirty`
    (whether `src/` differed from its commit) and `commit`. `exhaustive`: one per panel species, with `species`, `completed`, and `states_application` and `states_exhaustive`, each every distinct
    state that search found on the reference geometry as {energy_hartree, charges}, lowest first. `published_runs`: the second gate's `MeasuredRun`s of the N species, made with this calculation.
    `classes`: each panel species' atom symmetry classes. `floor`: the larger of the two noise floors.

    **NOT EVALUABLE** (nothing is claimed) when the instrument or the record is not fit to decide: a floor that is missing or above `FLOOR_LIMIT`, an ORCA other than `ORCA_VERSION`, runs made from
    more than one commit or from a `src/` that differed from it, a panel species with no reference run, a run of R that was never attempted, or a species with no exhaustive record.
    **FAIL** when R fails: a run beyond the limit, or a run ORCA could not complete. **PARTIAL** when R holds for every species and C or N does not. **PASS** when all three hold.
    """
    problems: list[str] = []
    if floor is None:
        problems.append("no noise floor was measured")
    elif floor > FLOOR_LIMIT:
        problems.append(f"the noise floor {floor:.4f} is above {FLOOR_LIMIT}")
    versions = {record.get("orca_version") for record in runs}
    if versions != {ORCA_VERSION}:
        problems.append(f"the runs were made with ORCA {sorted(str(version) for version in versions)}, not {ORCA_VERSION}")
    if any(record.get("dirty") for record in runs):
        problems.append("a run was made from a src/ that differed from its commit")
    if len({record.get("commit") for record in runs}) > 1:
        problems.append("the runs were made from more than one version of the code")

    by_species: dict[str, dict[str, Mapping]] = defaultdict(dict)
    for record in runs:
        by_species[record["species"]][record["variant"]] = record
    have_exhaustive = {record["species"] for record in exhaustive}
    for species in PANEL:
        have = by_species.get(species.name, {})
        if "reference" not in have:
            problems.append(f"{species.name} has no reference run")
        absent = [variant for variant in species.variants() if variant not in have]
        if absent and "reference" in have:
            problems.append(f"{species.name}: runs never attempted: {', '.join(absent)}")
        if species.name not in have_exhaustive:
            problems.append(f"{species.name} has no exhaustive search record")
    if problems:
        return Verdict("NOT EVALUABLE", tuple(problems))

    reasons: list[str] = []
    rows: list[ReproducibilityRow] = []
    for species in PANEL:
        have = by_species[species.name]
        if not have["reference"].get("completed", True):
            reasons.append(f"R {species.name}: the reference run could not be computed")
            continue
        for variant in species.variants()[1:]:
            record = have[variant]
            if not record.get("completed", True):
                rows.append(ReproducibilityRow(species.name, variant, math.inf, False))
                reasons.append(f"R {species.name} {variant}: not computed in {MAX_ATTEMPTS} attempts")
                continue
            difference = class_sorted_difference(have["reference"]["f_minus"], record["f_minus"], classes[species.name])
            within = difference <= REPRODUCIBILITY_LIMIT + _SLACK
            rows.append(ReproducibilityRow(species.name, variant, difference, within))
            if not within:
                reasons.append(f"R {species.name} {variant}: f- differs from the reference by {difference:.4f} (limit {REPRODUCIBILITY_LIMIT})")
    reproducible = not reasons

    completeness: list[CompletenessRow] = []
    complete_reasons: list[str] = []
    for record in exhaustive:
        if not record.get("completed", True):
            completeness.append(CompletenessRow(record["species"], math.inf, (), False))
            complete_reasons.append(f"C {record['species']}: the exhaustive search could not be computed")
            continue
        application, wanted = record["states_application"], record["states_exhaustive"]
        lowest_missed = max(0.0, (application[0]["energy_hartree"] - wanted[0]["energy_hartree"]) * _HARTREE_TO_EV)
        lowest = wanted[0]["energy_hartree"]
        window = [state for state in wanted if (state["energy_hartree"] - lowest) * _HARTREE_TO_EV <= WINDOW_EV + _SLACK]
        missed = tuple(match_states(window, application))
        within = lowest_missed <= LEVEL_MARGIN_EV + _SLACK and not missed
        completeness.append(CompletenessRow(record["species"], lowest_missed, missed, within))
        if not within:
            complete_reasons.append(
                f"C {record['species']}: the exhaustive search found {len(missed)} state(s) within {WINDOW_EV} eV that the application's did not"
                + (f", and a lowest state {lowest_missed:.3f} eV lower" if lowest_missed > LEVEL_MARGIN_EV else "")
            )

    published = {(run.molecule, run.level): run for run in published_runs}
    entries = [entry for entry in second.decided_entries() if entry.molecule in N_SPECIES]
    regression_rows = second.compare(entries, published, PUBLISHED_TOLERANCE)
    regression_reasons = [
        f"N {row.molecule} {row.element} {row.attack}: {row.measured:.4f} against the published {row.published:.4f} ({row.difference:+.4f})" for row in regression_rows if not row.within
    ]
    site_rows = []
    for statement in (s for s in second.decidable_site_statements() if s.molecule in N_SPECIES):
        run = published.get((statement.molecule, _level_of(statement.molecule)))
        found = second.site_found(run, statement) if run is not None else ""
        site_rows.append({"molecule": statement.molecule, "attack": statement.attack, "expected": statement.expected, "found": found, "reproduced": found == statement.expected})
        if found != statement.expected:
            regression_reasons.append(f"N {statement.molecule} {statement.attack}: the largest value is on {found or 'no atom'}, not {statement.expected}")
    expected_numbers = second.count_numbers(entries)
    if len(regression_rows) != expected_numbers:
        regression_reasons.append(f"N: {len(regression_rows)} of the {expected_numbers} numbers could be compared (a species has no run)")

    arms = {"R": reproducible, "C": not complete_reasons, "N": not regression_reasons}
    if not reproducible:
        outcome = "FAIL"
    elif complete_reasons or regression_reasons:
        outcome = "PARTIAL"
    else:
        outcome = "PASS"
    return Verdict(outcome, (*reasons, *complete_reasons, *regression_reasons), tuple(rows), tuple(completeness), tuple(regression_rows), tuple(site_rows), arms)
