"""The fourth Fukui gate: is the state the search reads f- from the kind of cation state the literature says is lowest, and how far above it is the next one? The typed references, the reading of a
state's character from ORCA's own output, and the pure judge.

`benchmarks/fukui_gate_4/PREREGISTRATION.md` says what is claimed and what a verdict does. This module is the part of it that is code, written so that the arithmetic of the verdict and the reading
of a state's character are tested on invented records and on real output before any real run exists. Nothing here runs ORCA or imports RDKit.

The first three gates asked whether the search is reproducible, complete and not a regression. None of them used a reference in which the cation states are IDENTIFIED (which orbital the hole
is in), so none could say whether the lowest state the search reads f- from is the state the experiments call lowest. This one does, for the molecules whose assigned states the literature prints:

* **C1, the kind of the lowest state.** The lowest state of an exhaustive search (a hole in every orbital from the HOMO-1 to the HOMO-7) is a sigma or a pi hole as the literature's lowest state is.
* **C2, the kind of the second.** For the three diazines, whose first four bands are n, pi, n, pi (pyridazine: n, pi, pi, n), the second distinct state is a pi hole.
* **C3, the distance.** The gap from the lowest state to the lowest state of the other kind is within `GAP_TOLERANCE_EV` of the range the sources print for it.
* **S, the near-degenerate pair.** In selenophene the two highest pi orbitals are near-degenerate: two states within the gap the sources print, both pi, one with its hole at the node of the heteroatom (a2)
  and one on it (b1), and the application's own run says so.
* **C5, the application's own search.** The search the application runs (the default job and holes in the HOMO-1, -2 and -3) finds the lowest state the exhaustive search does.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from openchem.app.fukui_gate import MAX_ATTEMPTS, ORCA_VERSION
from openchem.chem.fukui_states import LEVEL_MARGIN_EV

#: What the reachability guard accepts for a module nothing in the application imports: the gate's runner (`benchmarks/fukui_gate_4/run_gate.py`) and its tests are its only users.
REACHED_BY = (
    "tooling: imported only by benchmarks/fukui_gate_4/run_gate.py, the script that runs the fourth Fukui gate, and by its tests; the gate is not a feature of the window"
)

__all__ = [
    "A2_HETERO_LIMIT", "B1_HETERO_LIMIT", "CALIBRATION", "CLOSE_STATE_SENTENCES", "ClaimRow", "EXHAUSTIVE_OFFSETS", "GAP_TOLERANCE_EV", "GATE_SPECIES", "GateSpecies", "HARTREE_TO_EV", "LOWEST_AGREEMENT_EV",
    "MAX_ATTEMPTS", "OUT_OF_PLANE", "ORCA_VERSION", "PI_LIMIT", "PLANARITY_LIMIT_ANGSTROM", "Reference", "SIGMA_LIMIT", "State", "Verdict", "classify", "hetero_class", "judge",
    "out_of_plane_fraction", "parse_lowdin_spin", "states_of",
]

#: One Hartree in eV (the CODATA value `conceptual_dft` uses).
HARTREE_TO_EV = 27.211386245988
#: Float slack for "within" comparisons, so a value exactly on a bound is on the right side of it.
_SLACK = 1e-9

#: The holes of the exhaustive search: the HOMO-1 to the HOMO-7 (as the third gate's arm C).
EXHAUSTIVE_OFFSETS = tuple(range(1, 8))

#: Two jobs are one state when their energies are within this many eV (the third gate's reading rule, measured on 44 jobs: jobs that reached one state agreed to 0.01 eV).
STATE_MARGIN_EV = LEVEL_MARGIN_EV

# --- the reading of a state's character -------------------------------------------------------------------------------------------------------------------------------------------------

#: A state is a pi hole when at least this share of its unpaired electron's spin is in functions out of the molecular plane. Fixed from symmetry before any decided species was run: a pi
#: orbital has a nodal plane in the molecular plane, so the electron left unpaired is in pz (and the d functions with a z) and the share is 1 up to spin polarisation; a sigma hole's is 0.
#: Measured on the four molecules whose states were seen before this gate (PREREGISTRATION.md 3): 1.000 for every pi state and 0.000 for every sigma state.
PI_LIMIT = 0.75
#: A state is a sigma hole when at most this share is out of the plane. Between the two limits a state is NOT classified, and a claim that needs its class cannot be decided.
SIGMA_LIMIT = 0.25
#: In a five-membered ring with a heteroatom, a pi hole in the a2 orbital (a node through the heteroatom) leaves at most this much of the spin on the heteroatom, and one in the b1 orbital (80% on
#: it for thiophene, Schafer 1973) at least `B1_HETERO_LIMIT`. Measured on thiophene, pyrrole and furan (PREREGISTRATION.md 3): a2 states -0.071 to -0.033, b1 states 0.322 to 0.580.
A2_HETERO_LIMIT = 0.10
#: The least spin on the heteroatom of a b1 hole (see `A2_HETERO_LIMIT`); between the two limits a state is not classified.
B1_HETERO_LIMIT = 0.20
#: The reading assumes the molecular plane is xy, so a geometry that is not planar to this many Angstrom (the largest distance of an atom from its mean plane) cannot be read; the species is NOT EVALUABLE.
PLANARITY_LIMIT_ANGSTROM = 0.05

#: The heading of the block of ORCA's output that holds the spin population of every function (an open-shell job prints it by default).
_SPIN_BLOCK = "LOEWDIN REDUCED ORBITAL CHARGES AND SPIN POPULATIONS"
#: The first line of an atom's entry in that block: its index, its element and its s population (``  3 N s       :    -0.002386  s :    -0.002386``).
_ATOM_LINE = re.compile(r"^\s*(\d+)\s+([A-Z][a-z]?)\s+s\s*:\s*(-?\d+\.\d+)\s+s\s*:\s*-?\d+\.\d+\s*$")
#: A later line of an atom's entry: one function (``pz``, ``dxz`` ...) and its population, with the shell's sum after the first function of a shell.
_SHELL_LINE = re.compile(r"^\s+(pz|px|py|dz2|dxz|dyz|dx2y2|dxy)\s*:\s*(-?\d+\.\d+)(?:\s+[pd]\s*:\s*-?\d+\.\d+)?\s*$")
#: The functions whose axis is the z of the input's frame: `pz`, and the two d functions with a z in them. Their spin is out of the molecular plane when the plane is the xy plane.
OUT_OF_PLANE = ("pz", "dxz", "dyz")


def parse_lowdin_spin(segment: str, atom_count: int) -> list[dict[str, float]] | None:
    """The Loewdin spin population of each atom's functions, by shell and direction, from one job's stretch of output; None if the job printed none (a closed-shell job, or one that failed).

    ORCA prints, for an open-shell job, ``LOEWDIN REDUCED ORBITAL CHARGES AND SPIN POPULATIONS``: a ``CHARGE`` half and a ``SPIN`` half, each one entry per atom (``s``, then ``pz``, ``px``,
    ``py``, then the d functions). The spin half is what is read here. Every shell value is the population of ONE function (several s shells of an atom are already summed by ORCA), so the
    populations of all atoms and functions add to the job's unpaired-electron count. A block that holds a different number of atoms than ``atom_count`` raises ValueError rather than being read short.
    """
    begin = segment.find(_SPIN_BLOCK)
    if begin == -1:
        return None
    lines = segment[begin:].splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == "SPIN")
    except StopIteration:
        return None
    atoms: list[dict[str, float]] = []
    for raw in lines[start + 1 :]:
        line = raw.rstrip("\r")
        match = _ATOM_LINE.match(line)
        if match:
            if len(atoms) == atom_count:
                break
            atoms.append({"s": float(match.group(3))})
            continue
        shell = _SHELL_LINE.match(line)
        if shell and atoms:
            atoms[-1][shell.group(1)] = float(shell.group(2))
    if len(atoms) != atom_count:
        raise ValueError(f"the spin block lists {len(atoms)} atoms, not the molecule's {atom_count}")
    return atoms


def out_of_plane_fraction(spins: Sequence[Mapping[str, float]]) -> float:
    """The share of the unpaired electron's spin that sits in functions pointing out of the xy plane (`OUT_OF_PLANE`), summed over every atom.

    For a planar molecule oriented with its plane as xy this is the pi character of the hole. The populations add to the unpaired-electron count (1 for a doublet), so it is a fraction of that
    count up to spin polarisation, which can put a little spin of the other sign in the other class: it can lie a few hundredths outside 0 to 1.
    """
    total = sum(sum(atom.values()) for atom in spins)
    if total == 0:
        raise ValueError("the spin populations add to zero")
    return sum(atom.get(name, 0.0) for atom in spins for name in OUT_OF_PLANE) / total


def classify(fraction: float) -> str | None:
    """"pi" or "sigma" from an out-of-plane fraction, None when it is between `SIGMA_LIMIT` and `PI_LIMIT`."""
    if fraction >= PI_LIMIT - _SLACK:
        return "pi"
    if fraction <= SIGMA_LIMIT + _SLACK:
        return "sigma"
    return None


def hetero_class(spin: float) -> str | None:
    """"a2" (a pi hole with its node through the heteroatom) or "b1" (a pi hole on it) from the spin population of the heteroatom, None when between `A2_HETERO_LIMIT` and `B1_HETERO_LIMIT`."""
    if spin <= A2_HETERO_LIMIT + _SLACK:
        return "a2"
    if spin >= B1_HETERO_LIMIT - _SLACK:
        return "b1"
    return None


# --- states ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class State:
    """One distinct cation state: the jobs within `STATE_MARGIN_EV` of each other, read from the lowest of them."""

    energy_hartree: float
    above_ev: float
    out_of_plane: float
    atom_spin: tuple[float, ...]
    jobs: int
    #: Whether every job of the state falls in one class (or none does): False when the jobs of one energy disagree about pi or sigma, which no claim can be decided on.
    consistent: bool

    @property
    def kind(self) -> str | None:
        return classify(self.out_of_plane)


def states_of(jobs: Sequence[Mapping]) -> list[State]:
    """The distinct states of a search's jobs, lowest first. A job is a mapping with `energy_hartree`, `out_of_plane` and `atom_spin` (the spin population of each atom).

    Jobs are chained into one state while consecutive energies lie within `STATE_MARGIN_EV` of the previous job of the state, as the application's own reading does, so a state's jobs are
    never split by an arbitrary cut.
    """
    ordered = sorted(jobs, key=lambda job: job["energy_hartree"])
    if not ordered:
        return []
    groups: list[list[Mapping]] = [[ordered[0]]]
    for job in ordered[1:]:
        if (job["energy_hartree"] - groups[-1][-1]["energy_hartree"]) * HARTREE_TO_EV <= STATE_MARGIN_EV + _SLACK:
            groups[-1].append(job)
        else:
            groups.append([job])
    lowest = ordered[0]["energy_hartree"]
    states = []
    for group in groups:
        head = group[0]
        kinds = {classify(job["out_of_plane"]) for job in group}
        states.append(
            State(
                energy_hartree=head["energy_hartree"],
                above_ev=(head["energy_hartree"] - lowest) * HARTREE_TO_EV,
                out_of_plane=head["out_of_plane"],
                atom_spin=tuple(head["atom_spin"]),
                jobs=len(group),
                consistent=len(kinds) == 1,
            )
        )
    return states


# --- the references ----------------------------------------------------------------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Reference:
    """What the sources print for one molecule's cation states, as the claims need it."""

    #: The kind of the lowest state: "sigma" (a lone-pair hole), "pi", or None where the sources do not fix it (selenophene).
    lowest: str | None
    #: The kind of the second distinct state, for the molecules whose first bands run n, pi, ...: "pi"; None where the sources do not fix it.
    second: str | None
    #: The smallest and largest value, in eV, of the gap from the lowest state to the lowest state of the OTHER kind (to the second state for the diazines; for selenophene, between its two
    #: pi states, whichever of the two is lower). From every correlated calculation and every experiment the sources print (never a Koopmans value), at the largest basis each printed.
    gap_ev: tuple[float, float]
    #: Every value the range is made of, as printed, so the range can be checked against the sources.
    values: tuple[str, ...]


@dataclass(frozen=True)
class GateSpecies:
    name: str
    smiles: str
    reference: Reference | None
    #: "decided" (never run through any probe or gate before this one), or "calibration" (seen before it, run once to check the reading, never decided).
    role: str
    #: The element symbol of the heteroatom whose spin is read for the a2/b1 claim (selenophene), or "".
    hetero: str = ""
    charge: int = 0

    @property
    def method_basis(self) -> str:
        return "B3LYP 6-31G*"


#: The two forms of the sentence with which the application's note (`chem.fukui.cation_state_sentences`) says competing states of the cation lie within its window (one state, or several): S3 needs
#: one of THESE, not any note (a note can also say the search did not run, or stopped short).
CLOSE_STATE_SENTENCES = ("Another state of the cation lies", "Other states of the cation lie")

#: The gap tolerance of C3 and S: the range the sources print, widened by this on each side. It is a little above the largest error of the four molecules seen before the gate, set against the
#: experimental gaps: 0.16 eV (pyrrole), 0.05 (thiophene), 0.03 (furan) and 0.03 (pyridine against EOM-IP-CCSDT), and sets the scale of the spread between sources for one gap (0.1 to 0.25 eV).
GAP_TOLERANCE_EV = 0.25
#: C5: the application's search must find the lowest state to within this many eV of the exhaustive search's (the state margin).
LOWEST_AGREEMENT_EV = STATE_MARGIN_EV

#: The decided molecules. Their numbers are read off the sources' tables (page images, not their extracted text), and listed in PREREGISTRATION.md 4 with the page of each.
GATE_SPECIES = (
    GateSpecies(
        "pyrimidine",
        "c1cncnc1",
        Reference(
            "sigma",
            "pi",
            (0.48, 0.80),
            (
                "ADC(3)/cc-pVDZ++ 9.991 (7b2, n), 10.473 (2b1, pi): 0.48 (Shojaei 2010 Table 1)",
                "OVGF/aug-cc-pVTZ 9.880, 10.482: 0.60 (Shojaei 2010 Table 1)",
                "PES 9.8, 10.5: 0.70 (Shojaei 2010 Table 1, column PES)",
                "He I 9.73 (n-), 10.41 (pi): 0.68 (Gleiter 1972 Table 2; the sequence n, pi, n, pi confirmed by angle-resolved spectra, Piancastelli 1983)",
                "9.7, 10.5: 0.80 (Asbrink et al. 1972, as tabulated in Stener 2011 Table 1)",
            ),
        ),
        "decided",
    ),
    GateSpecies(
        "pyrazine",
        "c1cnccn1",
        Reference(
            "sigma",
            "pi",
            (0.55, 0.80),
            (
                "He I 9.63 (n+), 10.18 (pi): 0.55 (Gleiter 1972 Table 2; the sequence n, pi, n, pi confirmed by angle-resolved spectra, Piancastelli 1983)",
                "9.4, 10.2: 0.80 (Fridh et al. 1972, as tabulated in Stener 2011 Table 1)",
            ),
        ),
        "decided",
    ),
    GateSpecies(
        "pyridazine",
        "c1ccnnc1",
        Reference(
            "sigma",
            "pi",
            (1.30, 1.52),
            (
                "He I 9.31 (n-), 10.61 (pi): 1.30 (Gleiter 1972 Table 2)",
                "9.27, 10.61: 1.34 (experiment as tabulated in Holland 2013 Table 1)",
                "NEVPT2 strongly contracted 9.182 (8b2, n), 10.683 (1a2, pi): 1.50; partially contracted 9.141, 10.659: 1.52 (Holland 2013 Table 1, cc-pVTZ)",
            ),
        ),
        "decided",
    ),
    GateSpecies(
        "imidazole",
        "c1c[nH]cn1",
        Reference(
            "pi",
            None,
            (1.23, 1.67),
            (
                "from the lowest state (3a'', pi) to the lowest sigma state (15a', n sigma), Patanen 2021 Table II, cc-pVTZ: experiment 9.1, 10.4: 1.30; best theoretical estimate 9.02, 10.30: 1.28",
                "CC3 8.85, 10.08: 1.23; EOM-IP-CCSD 8.91, 10.15: 1.24; OVGF 8.82, 10.27: 1.45; IP-ADC(3) 8.85, 10.47: 1.62; Dyson ADC(3) 8.89, 10.56: 1.67",
            ),
        ),
        "decided",
    ),
    GateSpecies(
        "pyrazole",
        "c1cc[nH]n1",
        Reference(
            "pi",
            None,
            (1.55, 1.55),
            ("from the lowest state (3a'', pi) to the lowest sigma state (15a', n sigma): 9.15, 10.7: 1.55 (Cradock, Findlay and Palmer 1973 Table 1, vertical IPs; the only source in hand)",),
        ),
        "decided",
    ),
    GateSpecies(
        "oxazole",
        "c1cocn1",
        Reference(
            "pi",
            None,
            (1.36, 1.36),
            (
                "from the lowest state (pi) to the lowest sigma state (n): 9.83, 11.19: 1.36. The energies are Palmer, Findlay and Egdell's (1977), quoted in Kobayashi 1982 Table 1 (the original is not held); "
                "the order pi, n, pi is Palmer's ab initio assignment, supported there by a perturbation-theoretic reading of the band energies and by band shape",
            ),
        ),
        "decided",
    ),
    GateSpecies(
        "selenophene",
        "c1cc[se]c1",
        Reference(
            None,
            None,
            (0.0, 0.1),
            (
                "the two highest pi orbitals, 2b1 and 1a2, near-degenerate (Schafer 1973); ADC(3) 8.7 (2b1) and 8.7 (1a2): 0.0; OVGF 8.6 (1a2) and 8.7 (2b1): 0.1; experiment 9.0 (2b1) and 9.1 (1a2): 0.1 (Trofimov 2008 Table 2; the gap is the size of the difference, whichever orbital is lower)",
            ),
        ),
        "decided",
        hetero="Se",
    ),
)

#: The four molecules whose cation states were seen before this gate was written (the third gate's results, and the probe of PREREGISTRATION.md 3). Run once to check the reading; never decided.
CALIBRATION = (
    GateSpecies("pyridine", "c1ccncc1", None, "calibration"),
    GateSpecies("thiophene", "c1ccsc1", None, "calibration", hetero="S"),
    GateSpecies("pyrrole", "c1cc[nH]c1", None, "calibration", hetero="N"),
    GateSpecies("furan", "c1ccoc1", None, "calibration", hetero="O"),
)


# --- the verdict -----------------------------------------------------------------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ClaimRow:
    species: str
    #: "C1", "C2", "C3", "S" (its parts "S1" to "S3") or "C5".
    claim: str
    expected: str
    found: str
    holds: bool


@dataclass(frozen=True)
class Verdict:
    outcome: str
    reasons: tuple[str, ...]
    rows: tuple[ClaimRow, ...] = ()
    arms: Mapping[str, bool] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return self.outcome == "PASS"


def _within(value: float, interval: tuple[float, float]) -> bool:
    return interval[0] - GAP_TOLERANCE_EV - _SLACK <= value <= interval[1] + GAP_TOLERANCE_EV + _SLACK


def _other_kind(kind: str) -> str:
    return "pi" if kind == "sigma" else "sigma"


def judge(*, exhaustive: Sequence[Mapping], application: Sequence[Mapping], runs: Sequence[Mapping]) -> Verdict:
    """The verdict from the records of a gate run.

    `exhaustive`: one mapping per decided species, with `species`, `completed` (False when ORCA could not compute it in `MAX_ATTEMPTS` attempts), `jobs` (every N-1 job: `energy_hartree`,
    `out_of_plane`, `atom_spin`), `planarity` (the largest distance in Angstrom of an atom from the molecular plane) and `hetero_index` (the atom whose spin the a2/b1 reading uses, or None).
    `application`: one per decided species, with `species`, `completed`, `lowest_hartree` (the energy of the state the application reads f- from) and `note` (its cation note, "" if none).
    `runs`: every ORCA record, with `orca_version`, `dirty` (whether `src/` differed from its commit) and `commit`.

    **NOT EVALUABLE** (nothing is claimed) when the instrument or the record is not fit to decide: an ORCA other than `ORCA_VERSION`, runs made from more than one commit or from a `src/` that
    differed from it, a species with no record, a geometry beyond `PLANARITY_LIMIT_ANGSTROM`, or a state a claim needs that cannot be classified or whose jobs disagree about their class.
    **FAIL** when the search reads f- from the wrong KIND of state (C1 or C2), or a job could not be computed. **PARTIAL** when every kind is right and a distance (C3, S) or the application's own
    search (C5) is not. **PASS** when every claim holds.
    """
    problems: list[str] = []
    versions = {record.get("orca_version") for record in runs}
    if versions != {ORCA_VERSION}:
        problems.append(f"the runs were made with ORCA {sorted(str(version) for version in versions)}, not {ORCA_VERSION}")
    if any(record.get("dirty") for record in runs):
        problems.append("a run was made from a src/ that differed from its commit")
    if len({record.get("commit") for record in runs}) > 1:
        problems.append("the runs were made from more than one version of the code")
    exhaustive_by = {record["species"]: record for record in exhaustive}
    application_by = {record["species"]: record for record in application}
    for species in GATE_SPECIES:
        if species.name not in exhaustive_by:
            problems.append(f"{species.name} has no exhaustive search record")
        if species.name not in application_by:
            problems.append(f"{species.name} has no record of the application's own search")
    if problems:
        return Verdict("NOT EVALUABLE", tuple(problems))

    reasons: list[str] = []
    not_computed: list[str] = []
    rows: list[ClaimRow] = []
    evaluable_problems: list[str] = []
    for species in GATE_SPECIES:
        exhaustive_record, application_record = exhaustive_by[species.name], application_by[species.name]
        if not exhaustive_record.get("completed", True):
            not_computed.append(f"{species.name}: the exhaustive search could not be computed in {MAX_ATTEMPTS} attempts")
            continue
        if not application_record.get("completed", True):
            not_computed.append(f"{species.name}: the application's own search could not be computed in {MAX_ATTEMPTS} attempts")
            continue
        planarity = exhaustive_record.get("planarity")
        if planarity is None or planarity > PLANARITY_LIMIT_ANGSTROM + _SLACK:
            evaluable_problems.append(f"{species.name}: the geometry is not planar to {PLANARITY_LIMIT_ANGSTROM} A ({planarity}), so a state's pi or sigma character cannot be read from its spin")
            continue
        states = states_of(exhaustive_record["jobs"])
        reference = species.reference
        assert reference is not None
        # C5 first: it needs no class.
        gap_to_lowest = max(0.0, (application_record["lowest_hartree"] - states[0].energy_hartree) * HARTREE_TO_EV)
        rows.append(ClaimRow(species.name, "C5", f"the application's lowest state within {LOWEST_AGREEMENT_EV} eV of the exhaustive search's", f"{gap_to_lowest:.3f} eV above", gap_to_lowest <= LOWEST_AGREEMENT_EV + _SLACK))

        if species.hetero:
            _selenophene_claims(species, reference, states, exhaustive_record, application_record, rows, evaluable_problems)
            continue
        lowest, other_state = states[0], None
        if not lowest.consistent or lowest.kind is None:
            evaluable_problems.append(f"{species.name}: the lowest state's out-of-plane spin fraction {lowest.out_of_plane:.3f} is between {SIGMA_LIMIT} and {PI_LIMIT} or its jobs disagree: its kind cannot be read")
            continue
        rows.append(ClaimRow(species.name, "C1", f"lowest state is a {reference.lowest} hole", f"a {lowest.kind} hole ({lowest.out_of_plane:.3f} out of plane)", lowest.kind == reference.lowest))
        if reference.second is not None:
            second = states[1] if len(states) > 1 else None
            if second is None or not second.consistent or second.kind is None:
                evaluable_problems.append(f"{species.name}: the second state cannot be read (absent, unclassified or inconsistent)")
            else:
                rows.append(ClaimRow(species.name, "C2", f"second state is a {reference.second} hole", f"a {second.kind} hole ({second.out_of_plane:.3f} out of plane, {second.above_ev:.3f} eV)", second.kind == reference.second))
        wanted = _other_kind(lowest.kind)
        other_state = next((state for state in states[1:] if state.consistent and state.kind == wanted), None)
        if other_state is None:
            rows.append(ClaimRow(species.name, "C3", f"gap to the lowest {wanted} state in {reference.gap_ev} +/- {GAP_TOLERANCE_EV} eV", f"no {wanted} state found among {len(states)} states", False))
        else:
            rows.append(ClaimRow(species.name, "C3", f"gap to the lowest {wanted} state in {reference.gap_ev} +/- {GAP_TOLERANCE_EV} eV", f"{other_state.above_ev:.3f} eV", _within(other_state.above_ev, reference.gap_ev)))
    if not_computed or evaluable_problems:
        return Verdict("NOT EVALUABLE" if evaluable_problems and not not_computed else "FAIL", tuple(not_computed + evaluable_problems), tuple(rows))

    kind_rows = [row for row in rows if row.claim in ("C1", "C2", "S1")]
    distance_rows = [row for row in rows if row.claim not in ("C1", "C2", "S1")]
    reasons = [f"{row.claim} {row.species}: expected {row.expected}; found {row.found}" for row in rows if not row.holds]
    arms = {
        "kind": all(row.holds for row in kind_rows),
        "distance": all(row.holds for row in distance_rows),
    }
    if not arms["kind"]:
        outcome = "FAIL"
    elif not arms["distance"]:
        outcome = "PARTIAL"
    else:
        outcome = "PASS"
    return Verdict(outcome, tuple(reasons), tuple(rows), arms)


def _selenophene_claims(species, reference, states, exhaustive_record, application_record, rows, problems) -> None:
    """S: two states within the printed gap, both pi, one a2 and one b1 at the heteroatom, and the application's own note says there is a close state."""
    index = exhaustive_record.get("hetero_index")
    if index is None:
        problems.append(f"{species.name}: the heteroatom's index is not recorded")
        return
    if len(states) < 2:
        rows.append(ClaimRow(species.name, "S1", "two states found", f"{len(states)} state(s)", False))
        return
    pair = states[:2]
    if any(not state.consistent or state.kind is None for state in pair):
        problems.append(f"{species.name}: one of the two lowest states cannot be classified or its jobs disagree")
        return
    kinds = [state.kind for state in pair]
    classes = [hetero_class(state.atom_spin[index]) for state in pair]
    if any(c is None for c in classes) and all(kind == "pi" for kind in kinds):
        problems.append(f"{species.name}: the heteroatom's spin ({pair[0].atom_spin[index]:.3f}, {pair[1].atom_spin[index]:.3f}) is between {A2_HETERO_LIMIT} and {B1_HETERO_LIMIT} for a state")
        return
    both_pi = all(kind == "pi" for kind in kinds)
    one_each = sorted(c for c in classes if c) == ["a2", "b1"]
    rows.append(ClaimRow(species.name, "S1", "the two lowest states are pi holes, one a2 (heteroatom spin <= %.2f) and one b1 (>= %.2f)" % (A2_HETERO_LIMIT, B1_HETERO_LIMIT),
                         f"{kinds[0]}/{kinds[1]}, heteroatom spin {pair[0].atom_spin[index]:.3f} ({classes[0]}) and {pair[1].atom_spin[index]:.3f} ({classes[1]})", both_pi and one_each))
    gap = pair[1].above_ev
    rows.append(ClaimRow(species.name, "S2", f"gap between the two in {reference.gap_ev} +/- {GAP_TOLERANCE_EV} eV", f"{gap:.3f} eV", _within(gap, reference.gap_ev)))
    note = application_record.get("note", "")
    says = any(sentence.lower() in note.lower() for sentence in CLOSE_STATE_SENTENCES)
    rows.append(ClaimRow(species.name, "S3", "the application's own run says another state (or other states) of the cation lie close", "that sentence" if says else ("another note" if note else "no note"), says))
