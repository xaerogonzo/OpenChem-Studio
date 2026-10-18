"""The arithmetic of the Fukui gate, and nothing else (`benchmarks/fukui_gate/PREREGISTRATION.md`).

The gate asks one question: does the Fukui calculator, run through the application on real ORCA at the levels
the literature published, reproduce the published Hirshfeld condensed values and pick the documented sites?
Everything that decides the answer is here and is pure, so that it is tested with invented numbers and so that nobody,
the author included, can choose a tolerance or a pass condition after seeing a measurement:

* what the published numbers are (`OLAH`, `BULTINCK`, `THANIKAIVELAN`), typed from the PDFs;
* which of them may be a target at all (`failing_columns`, `corroboration_failures`, `decided_entries`): a column that
  must sum to 1 and does not is a misprint, and a partial column no second source supports is not a target, both
  decided by RULES that run over the typed numbers before any job exists;
* which documented site statements are decidable at the tolerance (`decidable_site_statements`);
* what PASS, PARTIAL, FAIL and NOT EVALUABLE mean (`judge`), every reason collected and none short-circuited.

The drive steps in `app/debug_drive.py` read the stored runs and call these. Nothing here starts a job.
"""

from __future__ import annotations

import dataclasses
import enum
from collections.abc import Collection, Mapping
from dataclasses import dataclass, field

#: The ORCA the gate was preregistered for. Another version is a recorded difference, not a pass.
ORCA_VERSION = "6.1.1"

#: How far a measured value may be from a published one, in f units. FIXED BY HAND in the preregistration, from the
#: literature's own scatter: independent sources at comparable levels disagree by at most 0.008 (`published_scatter`),
#: so 0.02 is two and a half times that.
TOLERANCE = 0.02

#: The largest difference between two runs that should have given the same number (the same input twice, the whole
#: chain twice) for the gate to be able to use `TOLERANCE` at all. Above it the instrument is too noisy for the claim.
FLOOR_LIMIT = 0.005

#: How far a published column that must sum to 1 may sit from 1. The tables print four decimals, so a correct column
#: is off by a few 1e-4 at most (the worst correct one here is 0.0005).
SUM_TOLERANCE = 0.001

#: How far a second source may differ and still count as corroborating a published value that could not be summed.
CORROBORATION = 0.01

#: A site statement is decided at a level only if the published values put the expected atom ahead of the next by at
#: least this multiple of the tolerance, because a tolerance wider than half the margin could turn the ordering over.
SITE_MARGIN_FACTOR = 2.0

#: How far a run's own f+ and f- may sit from summing to 1 (ORCA integrates a density on a grid, so a correct run is off
#: by a few 1e-6); more means the run is broken, which is not a chemistry result.
RUN_SUM_TOLERANCE = 1e-3

#: How many times one job may be run before ORCA is taken to be unable to compute it. A job that did not finish (a scratch
#: fault, a crash) may be repeated unchanged; a species whose three states still do not complete in this many attempts is
#: recorded as NOT COMPUTED, and counts against the calculator as a failure to reproduce.
MAX_ATTEMPTS = 3

#: Float slack for "within" and "at least" comparisons, so a value exactly on a bound is on the right side of it.
_SLACK = 1e-9

#: The four models Olah's tables print for each atom: B3LYP and HF, each with 6-311+G** ("A", diffuse) and 6-31G** ("B").
DFT_A = "B3LYP/6-311+G**"
#: B3LYP/6-31G**, one of the two levels the verdict is decided on.
DFT_B = "B3LYP/6-31G**"
#: HF/6-311+G**, a reported level.
HF_A = "HF/6-311+G**"
#: HF/6-31G**, the other level the verdict is decided on.
HF_B = "HF/6-31G**"
#: The four models of Olah's tables, in the order each atom's four values are printed.
OLAH_LEVELS = (DFT_A, DFT_B, HF_A, HF_B)
#: The levels the verdict is decided on. The diffuse-basis columns are reported, never decided: the paper's own f+ moves
#: by up to 0.1 with that basis.
DECIDED_LEVELS = (DFT_B, HF_B)
#: The level of the application's own default (the panel's), reported against the published formaldehyde values and never decided.
DEFAULT_LEVEL = "B3LYP/def2-SVP"
#: The diffuse-basis columns of Olah's tables, run and compared but never decided on.
REPORTED_LEVELS = (DFT_A, HF_A)
#: What the application is asked to run at each level (the panel's method/basis string).
METHOD_BASIS = {
    DFT_A: "B3LYP 6-311+G**",
    DFT_B: "B3LYP 6-31G**",
    HF_A: "HF 6-311+G**",
    HF_B: "HF 6-31G**",
    DEFAULT_LEVEL: "B3LYP def2-SVP",
}

#: The two functions a published number can be of: f+ (an electron added) and f- (an electron removed).
ATTACKS = ("f+", "f-")


@dataclass(frozen=True)
class Species:
    """One molecule the gate runs: the SMILES the application is given, its net charge, and the elements in the atom
    order the application embeds (heavy atoms in SMILES order, then hydrogens)."""

    name: str
    smiles: str
    charge: int
    atoms: tuple[str, ...]
    #: The label a published table gives each atom position, where the element is not enough: acetone's carbons are the carbonyl
    #: carbon ("C") and two methyl carbons ("Cm") in Olah's table. Empty means the elements are the labels.
    labels: tuple[str, ...] = ()

    @property
    def neutral(self) -> bool:
        return self.charge == 0

    @property
    def site_labels(self) -> tuple[str, ...]:
        return self.labels or self.atoms


#: The seven species the gate runs, by name: what the application is given and what it should embed.
SPECIES = {
    "CO": Species("CO", "[C-]#[O+]", 0, ("C", "O")),
    "CO2": Species("CO2", "O=C=O", 0, ("O", "C", "O")),
    "H2CO": Species("H2CO", "C=O", 0, ("C", "O", "H", "H")),
    "acetone": Species("acetone", "CC(C)=O", 0, ("C", "C", "C", "O") + ("H",) * 6, ("Cm", "C", "Cm", "O") + ("H",) * 6),
    "CN-": Species("CN-", "[C-]#N", -1, ("C", "N")),
    "NCO-": Species("NCO-", "[N-]=C=O", -1, ("N", "C", "O")),
    "CNO-": Species("CNO-", "[C-]#[N+][O-]", -1, ("C", "N", "O")),
}


# --- the published numbers ----------------------------------------------------------------------------------------------
#
# Olah, Van Alsenoy & Sannigrahi, J. Phys. Chem. A 2002, 106, 3885, Tables 1-3: stockholder (Hirshfeld) charges, f+ and f-
# for each atom under the four models of OLAH_LEVELS, four decimals. molecule -> element -> (atoms of that element,
# f+ by level, f- by level). Copied from the PDF's text layer. Only the atoms the paper tabulates are listed (formaldehyde
# and acetone omit their hydrogens), so a molecule is COMPLETE only if `OLAH_COMPLETE` says so.
#: Olah's Tables 1-3, typed: molecule -> element label -> (atoms of it, f+ by `OLAH_LEVELS`, f- by `OLAH_LEVELS`).
OLAH: dict[str, dict[str, tuple[int, tuple[float, ...], tuple[float, ...]]]] = {
    "CO": {"C": (1, (.7473, .6705, .7646, .6801), (.6966, .6883, .7003, .6931)),
           "O": (1, (.2527, .3295, .2359, .3198), (.3034, .3117, .2997, .3069))},
    "CO2": {"C": (1, (.4607, .4043, .4158, .4211), (.2250, .2193, .1736, .1649)),
            "O": (2, (.2696, .2979, .2921, .2894), (.3876, .3963, .4132, .4176))},
    "H2CO": {"C": (1, (.4278, .3948, .4446, .4038), (.2337, .2280, .2324, .2277)),
             "O": (1, (.3387, .3078, .2033, .3050), (.4379, .4319, .4817, .4779))},
    "acetone": {"C": (1, (.0474, .2388, .0370, .2761), (.1177, .1186, .1252, .1256)),
                "O": (1, (.0601, .2491, .0547, .2632), (.3756, .3735, .4437, .4438)),
                "Cm": (2, (.1025, .0547, .1043, .0489), (.0830, .0795, .0657, .0616))},
    "CN-": {"C": (1, (.6362, .5993, .8674, .6046), (.6236, .6024, .6585, .6376)),
            "N": (1, (.3638, .4007, .1326, .3954), (.3764, .3976, .3415, .3624))},
    "NCO-": {"N": (1, (.3333, .3854, .3586, .3884), (.4270, .4270, .4234, .4209)),
             "C": (1, (.3836, .3644, .3530, .3777), (.2324, .2249, .1891, .1740)),
             "O": (1, (.2832, .2501, .2883, .2339), (.3405, .3481, .3875, .4011))},
    "CNO-": {"C": (1, (.5196, .5503, .5353, .5756), (.4374, .4344, .3877, .3877)),
             "N": (1, (.1389, .2237, .1238, .2289), (.1326, .1452, .0669, .0728)),
             "O": (1, (.3415, .2501, .3409, .1955), (.4300, .4204, .5459, .5395))},
}
#: The molecules whose every atom the paper tabulates, so that each column can be summed against 1.
OLAH_COMPLETE = frozenset({"CO", "CO2", "CN-", "NCO-", "CNO-"})

# Bultinck et al., J. Chem. Phys. 2007, 127, 034102, Table I: formaldehyde, RHF/6-31G** geometry, UHF/6-31G** ions,
# plain Hirshfeld. element -> (atoms of that element, f+, f-); the hydrogens are per atom. Each column sums to 1.000.
#: Bultinck's Table I, typed: element -> (atoms of it, f+, f-), formaldehyde at HF/6-31G**.
BULTINCK: dict[str, tuple[int, float, float]] = {"C": (1, .402, .226), "H": (2, .146, .146), "O": (1, .306, .482)}

# Thanikaivelan et al., Theor. Chem. Acc. 2002, 107, 326, Table 5: formaldehyde, Hirshfeld, DMol3 BLYP/dnd. Sums .998/1.000.
#: Thanikaivelan's Table 5, typed: element -> (atoms of it, f+, f-), formaldehyde, Hirshfeld, BLYP/dnd.
THANIKAIVELAN: dict[str, tuple[int, float, float]] = {"C": (1, .395, .236), "H": (2, .150, .169), "O": (1, .303, .426)}


@dataclass(frozen=True)
class Entry:
    """One published number: a source's value of one attack's condensed function for one element of one molecule at one level."""

    source: str
    molecule: str
    element: str
    attack: str
    level: str
    value: float
    #: How many atoms of the element the molecule has (a published value is per atom).
    count: int = 1


def olah_entries() -> tuple[Entry, ...]:
    entries = []
    for molecule, atoms in OLAH.items():
        for element, (count, plus, minus) in atoms.items():
            for index, level in enumerate(OLAH_LEVELS):
                entries.append(Entry("olah2002", molecule, element, "f+", level, plus[index], count))
                entries.append(Entry("olah2002", molecule, element, "f-", level, minus[index], count))
    return tuple(entries)


def bultinck_entries() -> tuple[Entry, ...]:
    return tuple(
        Entry("bultinck2007", "H2CO", element, attack, HF_B, value, count)
        for element, (count, plus, minus) in BULTINCK.items()
        for attack, value in (("f+", plus), ("f-", minus))
    )


def reported_entries() -> tuple[Entry, ...]:
    """The published numbers the REPORTED arm compares and the verdict never reads.

    Olah's diffuse-basis columns (every one, the three that fail the sum rule included: `reported_rows` marks them), and
    formaldehyde at the application's own default level against the three sources: Olah's and Thanikaivelan's and Bultinck's
    values, each re-labelled with the default level because they are what that level is compared to."""
    entries = [e for e in olah_entries() if e.level in REPORTED_LEVELS]
    for source, table in (("thanikaivelan2002", THANIKAIVELAN), ("bultinck2007", BULTINCK)):
        for element, (count, plus, minus) in table.items():
            for attack, value in (("f+", plus), ("f-", minus)):
                entries.append(Entry(source, "H2CO", element, attack, DEFAULT_LEVEL, value, count))
    for element in ("C", "O"):
        for attack in ATTACKS:
            for level in (DFT_B,):
                position = 1 if attack == "f+" else 2
                entries.append(Entry("olah2002", "H2CO", element, attack, DEFAULT_LEVEL,
                                     OLAH["H2CO"][element][position][OLAH_LEVELS.index(level)], 1))
    return tuple(entries)


# --- the rules that decide which published numbers may be targets ------------------------------------------------------------


def column_sum(molecule: str, attack: str, level: str) -> float:
    """The sum over every atom of a COMPLETE molecule of its published value at one level."""
    if molecule not in OLAH_COMPLETE:
        raise ValueError(f"{molecule} omits atoms from the table, so its column cannot be summed")
    index = OLAH_LEVELS.index(level)
    return sum(
        count * (plus if attack == "f+" else minus)[index] for count, plus, minus in OLAH[molecule].values()
    )


def failing_columns() -> tuple[tuple[str, str, str, float], ...]:
    """(molecule, attack, level, sum) of every complete column that does not sum to 1 within `SUM_TOLERANCE`.

    A published value of f over all the atoms of a molecule adds to one, so such a column holds a misprint, and which
    entry is wrong cannot be told. The whole column is dropped."""
    bad = []
    for molecule in sorted(OLAH_COMPLETE):
        for attack in ATTACKS:
            for level in OLAH_LEVELS:
                total = column_sum(molecule, attack, level)
                if abs(total - 1.0) > SUM_TOLERANCE + _SLACK:
                    bad.append((molecule, attack, level, round(total, 4)))
    return tuple(bad)


def _thanikaivelan_at(element: str, attack: str) -> float:
    count, plus, minus = THANIKAIVELAN[element]
    return plus if attack == "f+" else minus


def corroboration_failures() -> tuple[tuple[str, str, str, float, float], ...]:
    """Formaldehyde's partial Olah columns checked against the other sources. Returns the (element, attack, level,
    Olah, other) that differ by more than `CORROBORATION`; empty means every one is corroborated.

    HF/6-31G** is compared with Bultinck's (same level), B3LYP/6-31G** with Thanikaivelan's (BLYP, a numerical basis)."""
    failed = []
    for element in ("C", "O"):
        for attack in ATTACKS:
            position = 1 if attack == "f+" else 2
            hf = OLAH["H2CO"][element][position][OLAH_LEVELS.index(HF_B)]
            other_hf = BULTINCK[element][1 if attack == "f+" else 2]
            if abs(hf - other_hf) > CORROBORATION + _SLACK:
                failed.append((element, attack, HF_B, hf, other_hf))
            dft = OLAH["H2CO"][element][position][OLAH_LEVELS.index(DFT_B)]
            other_dft = _thanikaivelan_at(element, attack)
            if abs(dft - other_dft) > CORROBORATION + _SLACK:
                failed.append((element, attack, DFT_B, dft, other_dft))
    return tuple(failed)


def published_scatter() -> float:
    """The largest disagreement between independent published values of the same quantity at comparable levels: the
    evidence `TOLERANCE` was chosen from. Formaldehyde's C, O and H, f+ and f-, HF/6-31G** (Olah against Bultinck) and
    B3LYP/6-31G** against BLYP/dnd (Olah against Thanikaivelan); the hydrogen of Olah is implied by its C and O."""
    differences = []
    for position, other_index in ((1, 1), (2, 2)):
        for level, other in ((HF_B, BULTINCK), (DFT_B, THANIKAIVELAN)):
            index = OLAH_LEVELS.index(level)
            carbon = OLAH["H2CO"]["C"][position][index]
            oxygen = OLAH["H2CO"]["O"][position][index]
            hydrogen = (1.0 - carbon - oxygen) / 2.0
            differences.extend([
                abs(carbon - other["C"][other_index]),
                abs(oxygen - other["O"][other_index]),
                abs(hydrogen - other["H"][other_index]),
            ])
    return max(differences)


def decided_entries() -> tuple[Entry, ...]:
    """The published numbers the verdict is decided on, after every rule.

    At `DECIDED_LEVELS` only. From Olah: every entry of a complete molecule whose column sums to 1, and formaldehyde's C
    and O where a second source corroborates them. Acetone (partial, no second source) gives no number, only a site. From
    Bultinck: formaldehyde at HF/6-31G** (each of its columns sums to 1)."""
    dropped = {(m, a, level) for m, a, level, _ in failing_columns()}
    corroborated = set() if corroboration_failures() else {"H2CO"}
    chosen = []
    for entry in olah_entries():
        if entry.level not in DECIDED_LEVELS:
            continue
        if entry.molecule in OLAH_COMPLETE:
            if (entry.molecule, entry.attack, entry.level) in dropped:
                continue
        elif entry.molecule not in corroborated:
            continue
        chosen.append(entry)
    chosen.extend(bultinck_entries())
    return tuple(chosen)


@dataclass(frozen=True)
class SiteStatement:
    """A documented site: the attack that applies to the molecule and the element expected to have the largest value."""

    molecule: str
    attack: str
    element: str
    #: Why the site is the documented one.
    basis: str


#: The documented sites (section 3 of the preregistration), each from Olah's text and each supported by the paper's own numbers.
SITE_STATEMENTS = (
    SiteStatement("CO", "f-", "C", "protonation at carbon (HCO+ is more stable than HOC+ by about 38 kcal/mol)"),
    SiteStatement("CO2", "f-", "O", "protonation at oxygen"),
    SiteStatement("H2CO", "f-", "O", "protonation at oxygen"),
    SiteStatement("H2CO", "f+", "C", "nucleophilic addition at the carbonyl carbon"),
    SiteStatement("acetone", "f-", "O", "protonation at oxygen"),
    SiteStatement("CN-", "f-", "C", "protonation at carbon (HCN is more stable than HNC)"),
    SiteStatement("NCO-", "f-", "N", "protonation at nitrogen (HNCO is more stable than HOCN by about 28.5 kcal/mol)"),
)


def published_margin(statement: SiteStatement, level: str) -> float | None:
    """How far ahead of the next TABULATED atom the expected element is in the published numbers at `level`, or None when
    the published numbers do not put it first (or the paper lists nothing at that level for it). A negative or None
    margin means the paper's own table disagrees with the statement."""
    atoms = OLAH.get(statement.molecule)
    if atoms is None:
        return None
    index = OLAH_LEVELS.index(level)
    position = 1 if statement.attack == "f+" else 2
    values = {element: entry[position][index] for element, entry in atoms.items()}
    if statement.element not in values:
        return None
    ordered = sorted(values.values(), reverse=True)
    expected = values[statement.element]
    if expected < ordered[0] - _SLACK:
        return None
    return expected - ordered[1] if len(ordered) > 1 else None


def decidable_site_statements(tolerance: float = TOLERANCE) -> tuple[tuple[SiteStatement, str], ...]:
    """(statement, level) pairs the verdict may be decided on: the published margin is at least
    `SITE_MARGIN_FACTOR * tolerance` at that level (so the tolerance cannot turn the ordering over) and the paper's own
    numbers put the expected element first. The rest are listed by `undecidable_site_statements`."""
    pairs = []
    for statement in SITE_STATEMENTS:
        for level in DECIDED_LEVELS:
            margin = published_margin(statement, level)
            if margin is not None and margin >= SITE_MARGIN_FACTOR * tolerance - _SLACK:
                pairs.append((statement, level))
    return tuple(pairs)


def undecidable_site_statements(tolerance: float = TOLERANCE) -> tuple[tuple[SiteStatement, str, float | None], ...]:
    """The (statement, level, margin) the rules leave out, and why: a margin under the bound or no support in the table."""
    decidable = set(decidable_site_statements(tolerance))
    return tuple(
        (statement, level, published_margin(statement, level))
        for statement in SITE_STATEMENTS
        for level in DECIDED_LEVELS
        if (statement, level) not in decidable
    )


# --- what a run measured ---------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class MeasuredRun:
    """One Fukui run of one species at one level, as the application stored it."""

    molecule: str
    level: str
    #: The elements of the run's atoms, in the order of the values below.
    symbols: tuple[str, ...]
    f_plus: tuple[float, ...]
    f_minus: tuple[float, ...]
    f_zero: tuple[float, ...]
    dual: tuple[float, ...]
    charge: int
    multiplicity: int
    orca_version: str
    #: Whether the run was recorded as completed.
    completed: bool = True
    #: Whether the run's input fingerprint is that of the molecule's ORCA-optimized conformer, so the three states ran on
    #: the geometry the preregistration describes and not on the force-field embedding.
    on_optimized_geometry: bool = True

    def values(self, attack: str) -> tuple[float, ...]:
        return self.f_plus if attack == "f+" else self.f_minus

    def labels(self) -> tuple[str, ...]:
        """What a published table calls each atom of this run: the species' own labels when the run has the atoms the species
        should (acetone's carbonyl carbon is not its methyl carbons), else the elements."""
        species = SPECIES.get(self.molecule)
        return species.site_labels if species is not None and species.atoms == self.symbols else self.symbols

    def of_element(self, attack: str, element: str) -> tuple[float, ...]:
        """The value of every atom a published table calls `element` (by label, so acetone's three carbons are two labels).
        A first version matched the element symbol, and compared acetone's carbonyl carbon with whichever of its three carbons
        was farthest from the published value (PREREGISTRATION.md 11.6)."""
        return tuple(v for label, v in zip(self.labels(), self.values(attack)) if label == element)


@dataclass(frozen=True)
class Row:
    """One comparison: a published number, the measured one, and whether it is within tolerance."""

    source: str
    molecule: str
    element: str
    attack: str
    level: str
    published: float
    measured: float
    difference: float
    within: bool | None
    neutral: bool
    #: Whether the verdict is decided on it; a reported row never moves the verdict.
    decided: bool = True


@dataclass(frozen=True)
class SiteRow:
    molecule: str
    level: str
    attack: str
    expected: str
    found: str
    margin_published: float | None
    reproduced: bool
    neutral: bool


class Outcome(str, enum.Enum):
    PASS = "pass"
    #: Every neutral species reproduced and at least one charged one did not.
    PARTIAL = "partial"
    FAIL = "fail"
    #: The gate could not decide: a tolerance other than the preregistered one, a noisy instrument, another ORCA, a run
    #: that did not complete or did not run on the optimized geometry, a run whose own sum rule fails. Nothing is claimed.
    NOT_EVALUABLE = "not_evaluable"


@dataclass(frozen=True)
class Verdict:
    outcome: Outcome
    reasons: tuple[str, ...]
    rows: tuple[Row, ...] = field(default_factory=tuple)
    site_rows: tuple[SiteRow, ...] = field(default_factory=tuple)
    #: The charged species that did not reproduce, when the outcome is PARTIAL.
    anions_outside: tuple[str, ...] = field(default_factory=tuple)


def compare(entries: Collection[Entry], runs: Mapping[tuple[str, str], MeasuredRun], tolerance: float, *, decided: bool = True) -> list[Row]:
    """Each published entry against the run of its molecule at its level. An entry has one measured value per atom of
    the element (a CO2 oxygen has two, equal by symmetry); the largest difference is the row's, so a symmetric pair that
    came apart is seen. An entry with no run at that level is not compared."""
    rows = []
    for entry in entries:
        run = runs.get((entry.molecule, entry.level))
        if run is None:
            continue
        measured = run.of_element(entry.attack, entry.element)
        if not measured:
            continue
        worst = max(measured, key=lambda value: abs(value - entry.value))
        difference = worst - entry.value
        rows.append(Row(
            entry.source, entry.molecule, entry.element, entry.attack, entry.level, entry.value, worst, difference,
            abs(difference) <= tolerance + _SLACK, SPECIES[entry.molecule].neutral if entry.molecule in SPECIES else True,
            decided,
        ))
    return rows


def judge(
    runs: Mapping[tuple[str, str], MeasuredRun],
    *,
    tolerance: float | None,
    floor: float | None,
    orca_versions: Collection[str],
    unfinished_runs: Collection[str] = (),
    not_computed: Collection[tuple[str, str]] = (),
) -> Verdict:
    """The verdict, decided by the conditions of the preregistration and no others.

    `runs` is by (molecule, level) and must hold every species at every decided level. NOT EVALUABLE takes precedence
    over everything: a gate that cannot decide does not claim a failure. Within each outcome every reason is collected.
    """
    undecided: list[str] = []
    if tolerance is None or abs(tolerance - TOLERANCE) > _SLACK:
        undecided.append(f"the tolerance is {tolerance!r} and the preregistered one is {TOLERANCE}")
    if floor is None:
        undecided.append("no noise floor was measured")
    elif floor > FLOOR_LIMIT + _SLACK:
        undecided.append(
            f"the noise floor {floor:.4f} is above {FLOOR_LIMIT}, so a tolerance of {TOLERANCE} cannot be told from noise"
        )
    elsewhere = sorted(set(orca_versions) - {ORCA_VERSION})
    if elsewhere or not set(orca_versions):
        undecided.append(
            f"ORCA {', '.join(elsewhere) if elsewhere else 'with no recorded version'} is not the preregistered "
            f"{ORCA_VERSION}: the numbers are recorded and are not a pass"
        )
    if unfinished_runs:
        undecided.append(f"a run did not complete: {', '.join(sorted(unfinished_runs))}")
    needed = {(name, level) for name in SPECIES for level in DECIDED_LEVELS} - set(not_computed)
    absent = sorted(needed - set(runs))
    if absent:
        undecided.append(f"no run for: {', '.join(f'{m} at {level}' for m, level in absent)}")
    for (molecule, level), run in sorted(runs.items()):
        label = f"{molecule} at {level}"
        if molecule in SPECIES and run.charge != SPECIES[molecule].charge:
            undecided.append(f"{label} ran at charge {run.charge}, not the species' {SPECIES[molecule].charge}")
        if run.multiplicity != 1:
            undecided.append(f"{label} ran at multiplicity {run.multiplicity}")
        if not run.completed:
            undecided.append(f"{label} did not complete")
        if not run.on_optimized_geometry:
            undecided.append(f"{label} did not run on the ORCA-optimized geometry")
        if molecule in SPECIES and run.symbols != SPECIES[molecule].atoms:
            undecided.append(f"{label} has atoms {run.symbols}, not {SPECIES[molecule].atoms}")
        for attack in ATTACKS:
            total = sum(run.values(attack))
            if abs(total - 1.0) > RUN_SUM_TOLERANCE:
                undecided.append(f"{label}: {attack} sums to {total:.4f}, not 1")
        identity = max((abs(d - (p - m)) for p, m, d in zip(run.f_plus, run.f_minus, run.dual)), default=0.0)
        if identity > _SLACK:
            undecided.append(f"{label}: the dual descriptor is not f+ - f- (differs by {identity:.2e})")
        mean = max((abs(z - (p + m) / 2) for p, m, z in zip(run.f_plus, run.f_minus, run.f_zero)), default=0.0)
        if mean > _SLACK:
            undecided.append(f"{label}: f0 is not the mean of f+ and f- (differs by {mean:.2e})")
    if undecided:
        return Verdict(Outcome.NOT_EVALUABLE, tuple(undecided))

    used_tolerance = TOLERANCE
    rows = compare(decided_entries(), runs, used_tolerance)
    site_rows: list[SiteRow] = []
    for statement, level in decidable_site_statements(used_tolerance):
        run = runs.get((statement.molecule, level))
        if run is None:
            continue  # NOT COMPUTED: already a failure of its own, in `never`
        values = run.values(statement.attack)
        top = max(range(len(values)), key=lambda i: values[i])
        site_rows.append(SiteRow(
            statement.molecule, level, statement.attack, statement.element, run.symbols[top],
            published_margin(statement, level), run.symbols[top] == statement.element,
            SPECIES[statement.molecule].neutral,
        ))

    never = [
        f"{molecule} at {level}: ORCA did not complete the three states in {MAX_ATTEMPTS} attempts"
        for molecule, level in sorted(not_computed) if molecule in SPECIES
    ]
    neutral_failures = [line for line in never if SPECIES[line.split(" ", 1)[0]].neutral] + [
        f"{r.molecule} {r.element} {r.attack} at {r.level}: {r.measured:.4f} is {r.difference:+.4f} from {r.source}'s {r.published:.4f}"
        for r in rows if r.within is False and r.neutral
    ] + [
        f"{s.molecule} {s.attack} at {s.level}: the largest value is on {s.found}, the documented site is {s.expected}"
        for s in site_rows if not s.reproduced and s.neutral
    ]
    anion_failures = [line for line in never if not SPECIES[line.split(" ", 1)[0]].neutral] + [
        f"{r.molecule} {r.element} {r.attack} at {r.level}: {r.measured:.4f} is {r.difference:+.4f} from {r.source}'s {r.published:.4f}"
        for r in rows if r.within is False and not r.neutral
    ] + [
        f"{s.molecule} {s.attack} at {s.level}: the largest value is on {s.found}, the documented site is {s.expected}"
        for s in site_rows if not s.reproduced and not s.neutral
    ]
    anions_outside = tuple(sorted({line.split(" ", 1)[0] for line in anion_failures}))
    if neutral_failures:
        return Verdict(Outcome.FAIL, tuple(neutral_failures + anion_failures), tuple(rows), tuple(site_rows), anions_outside)
    if anion_failures:
        return Verdict(Outcome.PARTIAL, tuple(anion_failures), tuple(rows), tuple(site_rows), anions_outside)
    return Verdict(Outcome.PASS, (), tuple(rows), tuple(site_rows))


def noise_floor(*repeats: Mapping[str, float]) -> float:
    """The largest difference between any two runs that should have given the same number (the same input twice, the whole
    chain twice). Each repeat is `repeat_differences` of two runs."""
    values = [d for repeat in repeats for d in repeat.values()]
    if not values:
        raise ValueError("a noise floor needs at least one repeat")
    return max(values)


def repeat_differences(first: MeasuredRun, second: MeasuredRun) -> dict[str, float]:
    """|first - second| for each atom's f+, f- , f0 and dual. The two must be the same species and level."""
    if (first.molecule, first.level, first.symbols) != (second.molecule, second.level, second.symbols):
        raise ValueError("a repeat measures the same species at the same level")
    out: dict[str, float] = {}
    for name in ("f_plus", "f_minus", "f_zero", "dual"):
        for index, (a, b) in enumerate(zip(getattr(first, name), getattr(second, name))):
            out[f"{name}[{index}]"] = abs(a - b)
    return out


# --- from the stored runs to a verdict ---------------------------------------------------------------------------------------


def measured_from_record(record: Mapping) -> MeasuredRun:
    """The `MeasuredRun` a record of one stored run (written by the drive step `fukui_gate_record`) describes."""
    return MeasuredRun(
        molecule=str(record["species"]),
        level=str(record["level"]),
        symbols=tuple(record["symbols"]),
        f_plus=tuple(float(v) for v in record["f_plus"]),
        f_minus=tuple(float(v) for v in record["f_minus"]),
        f_zero=tuple(float(v) for v in record["f_zero"]),
        dual=tuple(float(v) for v in record["dual"]),
        charge=int(record["charge"]),
        multiplicity=int(record["multiplicity"]),
        orca_version=str(record["orca_version"]),
        completed=bool(record.get("completed", True)),
        on_optimized_geometry=bool(record.get("on_optimized_geometry", False)),
    )


def settle_attempts(records: list[Mapping]) -> tuple[dict[tuple[str, str], Mapping], set[tuple[str, str]], list[str], list[str]]:
    """Which record stands for each (species, level), after the rule for repeats.

    Returns (chosen, not_computed, unfinished, conflicts). A pair with exactly one COMPLETED attempt is chosen. A pair with
    none, after `MAX_ATTEMPTS` attempts, is NOT COMPUTED; with fewer it is UNFINISHED (the gate cannot decide yet). A pair with
    two completed attempts is a CONFLICT: a repeat of a job that finished is not an attempt, it is a second draw, and the
    gate does not choose between them."""
    by_pair: dict[tuple[str, str], list[Mapping]] = {}
    for record in records:
        by_pair.setdefault((str(record["species"]), str(record["level"])), []).append(record)
    chosen: dict[tuple[str, str], Mapping] = {}
    never: set[tuple[str, str]] = set()
    unfinished: list[str] = []
    conflicts: list[str] = []
    for pair, attempts in sorted(by_pair.items()):
        done = [a for a in attempts if a.get("completed")]
        label = f"{pair[0]} at {pair[1]}"
        if len(done) > 1:
            conflicts.append(f"{label} has {len(done)} completed attempts")
        elif done:
            chosen[pair] = done[0]
        elif len(attempts) >= MAX_ATTEMPTS:
            never.add(pair)
        else:
            unfinished.append(label)
    return chosen, never, unfinished, conflicts


def judge_records(records: list[Mapping], *, floor: float | None, tolerance: float | None = TOLERANCE) -> Verdict:
    """The verdict from the records the drive wrote: attempts settled by the rule, the runs built, `judge` called.

    A conflict (two completed attempts of one job) makes the gate unable to decide and says so."""
    chosen, never, unfinished, conflicts = settle_attempts(records)
    runs = {pair: measured_from_record(record) for pair, record in chosen.items()}
    versions = {run.orca_version for run in runs.values()}
    verdict = judge(
        runs, tolerance=tolerance, floor=floor, orca_versions=versions,
        unfinished_runs=unfinished, not_computed=never,
    )
    if conflicts:
        return Verdict(Outcome.NOT_EVALUABLE, tuple(conflicts) + verdict.reasons if verdict.outcome is Outcome.NOT_EVALUABLE else tuple(conflicts))
    return verdict


def reported_rows(runs: Mapping[tuple[str, str], MeasuredRun], tolerance: float = TOLERANCE) -> list[dict]:
    """The reported arm as plain dicts: each reported entry against the run at its level, never decided on.

    `suspect` marks a row whose published column fails the sum rule: it is a misprint's neighbour and is shown, not trusted."""
    failing = {(m, a, level) for m, a, level, _ in failing_columns()}
    out = []
    for row in compare(reported_entries(), runs, tolerance, decided=False):
        item = dataclasses.asdict(row)
        item["suspect"] = (row.molecule, row.attack, row.level) in failing
        out.append(item)
    return out
