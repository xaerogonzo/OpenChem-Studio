"""The arithmetic of the second Fukui gate, and nothing else (`benchmarks/fukui_gate_2/PREREGISTRATION.md`).

The second gate asks of the calculation as it stands at the freeze commit (Fukui v2, `benchmarks/fukui_gate_2/DESIGN.md`): does it reproduce the published Hirshfeld condensed values of
molecules the first gate never ran (De Proft et al. 2002, Tables 4 to 6), at the levels they were published at, and pick the documented sites? Everything that decides the answer is here and is
pure, so that it is tested with invented numbers and so that nobody, the author included, can choose a tolerance or a pass condition after seeing a measurement:

* what the published numbers are (`DEPROFT`, typed from the PDF's page images, and `SABLON`, the same group's second printing of ten rings and acrolein), and what each species' atoms are called in them;
* which of them may be a target at all (`failing_columns`, `corroboration_failures`, `decided_entries`): a column that must sum to 1 and does not is a misprint, and a partial column no second printing
  supports is not a target, both decided by RULES that run over the typed numbers before any job exists;
* which documented site statements are decidable at the tolerance (`decidable_site_statements`);
* what PASS, PARTIAL, FAIL and NOT EVALUABLE mean (`judge`), every reason collected and none short-circuited.

It shares the first gate's tolerance, floor limit, attempt rule, `Row`, `SiteRow`, `Verdict` and `Outcome` (`app/fukui_gate.py`), which are the same definitions, and none of its tables: the first gate's module is a
frozen record and is not edited. The drive steps in `app/debug_drive.py` read the stored runs and call these. Nothing here starts a job.
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass

from openchem.app.fukui_gate import (
    FLOOR_LIMIT,
    MAX_ATTEMPTS,
    ORCA_VERSION,
    RUN_SUM_TOLERANCE,
    SITE_MARGIN_FACTOR,
    TOLERANCE,
    Outcome,
    Row,
    SiteRow,
    Verdict,
    noise_floor,
    repeat_differences,
    settle_attempts,
)

__all__ = [
    "ORCA_VERSION", "TOLERANCE", "FLOOR_LIMIT", "MAX_ATTEMPTS", "Outcome", "Verdict", "Row", "SiteRow", "noise_floor", "repeat_differences", "settle_attempts",
]

#: How far a published COMPLETE column (a function over every atom of a molecule) may sit from 1 (Rule A). Each of up to four printed values carries 0.0005 of rounding, and the
#: worst complete column here is 0.001 off (CO, 1.001).
SUM_TOLERANCE = 0.002

#: How far a second printing may differ from the first and still be "the same number" (Rule B): the values are printed to three decimals, so an exact reprint is equal to the digit.
SECOND_PRINTING_TOLERANCE = 0.0005

#: Acrolein's input validity (section 4): the published molecule is s-trans, and the optimized O=C-C=C dihedral must be within this many degrees of 180.
DIHEDRAL_LIMIT_DEGREES = 30.0

#: Float slack for "within" and "at least" comparisons, so a value exactly on a bound is on the right side of it.
_SLACK = 1e-9

#: How ORCA's integration grid is named in a run's provenance (`chem.orca_engine`): a run made without it is not the calculation the gate tests.
GRID = "IntAcc 6.0"
#: What a run's provenance says it computed: the four functions.
FUNCTIONS_FULL = "f+ f- f0 dual"
#: ... or f- alone, for an anion (its N+1 state is a dianion, which v2 does not run).
FUNCTIONS_ANION = "f-"

#: The level of every neutral species and the cation, the source's own, by the name a record carries.
LEVEL_6_31GS = "B3LYP/6-31G*"
#: The anions' level, the source's own (diffuse functions on the heavy atoms).
LEVEL_6_31PGS = "B3LYP/6-31+G*"
#: The application's own default preset, run in the reported arm only.
LEVEL_DEFAULT = "B3LYP/def2-SVP"
#: What the application is asked to run at each level (the panel's method/basis string).
METHOD_BASIS = {LEVEL_6_31GS: "B3LYP 6-31G*", LEVEL_6_31PGS: "B3LYP 6-31+G*", LEVEL_DEFAULT: "B3LYP def2-SVP"}

#: The two functions a published number can be of: f+ (an electron added) and f- (an electron removed).
ATTACKS = ("f+", "f-")


@dataclass(frozen=True)
class GateSpecies:
    """One molecule the gate runs: the SMILES the application is given, its net charge, the elements in the atom order the application embeds (heavy atoms in SMILES order, then hydrogens), and what a
    published table calls each atom.

    `labels` is typed per species and pinned by a test that embeds the SMILES and recomputes them from the graph: ring carbons by distance from the carbon that carries the substituent, the carbon
    bonded to the heteroatom of a five-membered ring "2" and the other "3", acrolein's carbons beta (the CH2), alpha and carbonyl, N2O's nitrogens terminal (the one drawn with the negative charge)
    and central. An atom no published table gives a number to is labelled by its element, and the hydrogens "H".
    """

    name: str
    smiles: str
    charge: int
    atoms: tuple[str, ...]
    labels: tuple[str, ...]
    #: The level this species is run at (a key of `METHOD_BASIS`).
    level: str

    @property
    def neutral(self) -> bool:
        return self.charge == 0

    @property
    def functions(self) -> str:
        """What a run of this species must say it computed: an anion has no N+1 state."""
        return FUNCTIONS_ANION if self.charge < 0 else FUNCTIONS_FULL

    @property
    def method_basis(self) -> str:
        return METHOD_BASIS[self.level]


def _species(name: str, smiles: str, charge: int, atoms: str, labels: str, level: str = LEVEL_6_31GS) -> GateSpecies:
    return GateSpecies(name, smiles, charge, tuple(atoms.split()), tuple(labels.split()), level)


#: The labels of the six ring carbons of a monosubstituted benzene in the order the application embeds them (the ipso carbon is atom 1 of the ring in every SMILES here).
_BENZENE_RING = "ipso ortho meta para meta ortho"

#: The 15 species the verdict is decided on, by name. Atom orders are what `Chem.AddHs(Chem.MolFromSmiles(smiles))` gives, which is what the application embeds.
SPECIES = {
    "HCN": _species("HCN", "C#N", 0, "C N H", "C N H"),
    "N2O": _species("N2O", "[N-]=[N+]=O", 0, "N N O", "Nt Nc O"),
    "anilinium": _species("anilinium", "[NH3+]c1ccccc1", 1, "N" + " C" * 6 + " H" * 8, f"N {_BENZENE_RING}" + " H" * 8),
    "phenol": _species("phenol", "Oc1ccccc1", 0, "O" + " C" * 6 + " H" * 6, f"O {_BENZENE_RING}" + " H" * 6),
    "aniline": _species("aniline", "Nc1ccccc1", 0, "N" + " C" * 6 + " H" * 7, f"N {_BENZENE_RING}" + " H" * 7),
    "fluorobenzene": _species("fluorobenzene", "Fc1ccccc1", 0, "F" + " C" * 6 + " H" * 5, f"F {_BENZENE_RING}" + " H" * 5),
    "benzaldehyde": _species("benzaldehyde", "O=Cc1ccccc1", 0, "O" + " C" * 7 + " H" * 6, f"O C {_BENZENE_RING}" + " H" * 6),
    "styrene": _species("styrene", "C=Cc1ccccc1", 0, "C" * 1 + " C" * 7 + " H" * 8, f"C C {_BENZENE_RING}" + " H" * 8),
    "nitrobenzene": _species("nitrobenzene", "[O-][N+](=O)c1ccccc1", 0, "O N O" + " C" * 6 + " H" * 5, f"O N O {_BENZENE_RING}" + " H" * 5),
    "pyrrole": _species("pyrrole", "c1cc[nH]c1", 0, "C C C N C" + " H" * 5, "3 3 2 N 2" + " H" * 5),
    "furan": _species("furan", "c1ccoc1", 0, "C C C O C" + " H" * 4, "3 3 2 O 2" + " H" * 4),
    "thiophene": _species("thiophene", "c1ccsc1", 0, "C C C S C" + " H" * 4, "3 3 2 S 2" + " H" * 4),
    "acrolein": _species("acrolein", "C=CC=O", 0, "C C C O" + " H" * 4, "beta alpha carbonyl O" + " H" * 4),
    "SCN-": _species("SCN-", "[S-]C#N", -1, "S C N", "S C N", LEVEL_6_31PGS),
    "NO2-": _species("NO2-", "[O-]N=O", -1, "O N O", "O N O", LEVEL_6_31PGS),
}

#: Species the reported arm runs and the verdict never reads: the first gate's two (seen), the two partial columns of Table 6, and the two anions whose columns are partial.
REPORTED_SPECIES = {
    "CO": _species("CO", "[C-]#[O+]", 0, "C O", "C O"),
    "H2CO": _species("H2CO", "C=O", 0, "C O H H", "C O H H"),
    "maleic anhydride": _species("maleic anhydride", "O=C1C=CC(=O)O1", 0, "O C C C C O O H H", "O carbonyl CH CH carbonyl O O H H"),
    "maleimide": _species("maleimide", "O=C1C=CC(=O)N1", 0, "O C C C C O N H H H", "O carbonyl CH CH carbonyl O N H H H"),
    "enolate": _species("enolate", "C=C[O-]", -1, "C C O H H H", "CH2 CHO O H H H", LEVEL_6_31PGS),
    "phenolate": _species("phenolate", "[O-]c1ccccc1", -1, "O" + " C" * 6 + " H" * 5, f"O {_BENZENE_RING}" + " H" * 5, LEVEL_6_31PGS),
}

#: The two molecules the noise floors are measured on, neither in `deproft2002`'s tables nor in the first gate: a rigid heteroaromatic ring (the route of the neutral species and the cation)
#: and an anion with extra starts (the route of the anions).
FLOOR_SPECIES = {
    "pyridine": _species("pyridine", "c1ccncc1", 0, "C C C N C C" + " H" * 5, "C C C N C C" + " H" * 5),
    "formate": _species("formate", "[O-]C=O", -1, "O C O H", "O C O H", LEVEL_6_31PGS),
}

#: Every species by name, for a record that names one.
ALL_SPECIES = {**SPECIES, **REPORTED_SPECIES, **FLOOR_SPECIES}


# --- the published numbers ----------------------------------------------------------------------------------------------------
#
#: De Proft, Van Alsenoy, Peeters, Langenaeker & Geerlings, J. Comput. Chem. 2002, 23, 1198, doi 10.1002/jcc.10067: Gaussian 98, Hirshfeld populations at B3LYP/6-31G* (6-31+G* for the anions), the Yang-Mortier
#: finite differences, three decimals, in e. Typed from the page images (the text layer scrambles the tables) on 2026-10-18 and read again against them the same day. molecule -> attack -> label -> the published
#: value(s): ONE number where every atom of the label carries it (an averaged hydrogen, two equivalent ring carbons, the two oxygens of nitrite) or an unordered PAIR where the table prints two inequivalent atoms
#: (the two ortho carbons of phenol). The labels are those of `GateSpecies`.
#:
#: Table 4 (f-): HCN, N2O, CO, H2CO, SCN-, NO2- and the enolate (printed "CH2CO-", called the enolate ion in the text; its carbons are taken in formula order, the methylene carbon first, which is a reading and
#: not a statement of the paper's). Table 5 (f-): the ring carbons of eight monosubstituted benzenes, phenolate and three five-membered rings. Table 6 (f+): formaldehyde, acrolein, maleic anhydride, maleimide.
DEPROFT: dict[str, dict[str, dict[str, tuple[float, ...]]]] = {
    "HCN": {"f-": {"H": (0.109,), "C": (0.389,), "N": (0.502,)}},
    "N2O": {"f-": {"Nt": (0.399,), "Nc": (0.173,), "O": (0.428,)}},
    "CO": {"f-": {"C": (0.687,), "O": (0.314,)}},
    "H2CO": {"f-": {"O": (0.433,), "C": (0.229,), "H": (0.169,)}, "f+": {"O": (0.308,), "C": (0.397,), "H": (0.147,)}},
    "SCN-": {"f-": {"S": (0.606,), "C": (0.115,), "N": (0.279,)}},
    "NO2-": {"f-": {"N": (0.310,), "O": (0.345,)}},
    "enolate": {"f-": {"CH2": (0.324,), "CHO": (0.131,), "O": (0.273,)}},
    "anilinium": {"f-": {"ortho": (0.067,), "meta": (0.095,), "para": (0.175,)}},
    "phenolate": {"f-": {"ortho": (0.102,), "meta": (0.057,), "para": (0.136,)}},
    "phenol": {"f-": {"ortho": (0.081, 0.091), "meta": (0.064, 0.073), "para": (0.144,)}},
    "aniline": {"f-": {"ortho": (0.080,), "meta": (0.061,), "para": (0.131,)}},
    "fluorobenzene": {"f-": {"ortho": (0.087,), "meta": (0.078,), "para": (0.158,)}},
    "benzaldehyde": {"f-": {"ortho": (0.033, 0.044), "meta": (0.044, 0.045), "para": (0.072,)}},
    "styrene": {"f-": {"ortho": (0.059, 0.065), "meta": (0.054, 0.059), "para": (0.115,)}},
    "nitrobenzene": {"f-": {"ortho": (0.118,), "meta": (0.126,), "para": (0.048,)}},
    "pyrrole": {"f-": {"2": (0.194,), "3": (0.068,)}},
    "furan": {"f-": {"2": (0.272,), "3": (0.107,)}},
    "thiophene": {"f-": {"2": (0.059,), "3": (0.138,)}},
    "acrolein": {"f+": {"beta": (0.211,), "alpha": (0.116,), "carbonyl": (0.171,)}},
    "maleic anhydride": {"f+": {"carbonyl": (0.097,), "CH": (0.145,)}},
    "maleimide": {"f+": {"carbonyl": (0.096,), "CH": (0.137,)}},
}

#: The columns that cover every atom of their molecule, so that each sums to 1 (Rule A): molecule -> attack. The rings, acrolein, the enolate and the Table 6 rings list only some atoms.
COMPLETE_COLUMNS = (("HCN", "f-"), ("N2O", "f-"), ("CO", "f-"), ("H2CO", "f-"), ("H2CO", "f+"), ("SCN-", "f-"), ("NO2-", "f-"))

#: Sablon, De Proft, Ayers & Geerlings, J. Chem. Phys. 2007, 126, 224108, doi 10.1063/1.2736698: Table III's column "f_N^- (finite difference)" for ten of the eleven rings (it has no phenolate) and Fig. 1's
#: table for acrolein, each marked in the paper as De Proft's own finite-difference Hirshfeld values at B3LYP/6-31G* (its reference 35). Typed from the page images on 2026-10-18. THE SAME GROUP'S DATA: this
#: guards against a misprint and against a transcription error, not against a difference of method.
SABLON: dict[str, dict[str, dict[str, tuple[float, ...]]]] = {
    "anilinium": {"f-": {"ortho": (0.067,), "meta": (0.095,), "para": (0.175,)}},
    "phenol": {"f-": {"ortho": (0.081, 0.091), "meta": (0.064, 0.073), "para": (0.144,)}},
    "aniline": {"f-": {"ortho": (0.080,), "meta": (0.061,), "para": (0.131,)}},
    "fluorobenzene": {"f-": {"ortho": (0.087,), "meta": (0.078,), "para": (0.158,)}},
    "benzaldehyde": {"f-": {"ortho": (0.033, 0.044), "meta": (0.044, 0.045), "para": (0.072,)}},
    "styrene": {"f-": {"ortho": (0.059, 0.065), "meta": (0.054, 0.059), "para": (0.115,)}},
    "nitrobenzene": {"f-": {"ortho": (0.118,), "meta": (0.126,), "para": (0.048,)}},
    "pyrrole": {"f-": {"2": (0.194,), "3": (0.068,)}},
    "furan": {"f-": {"2": (0.272,), "3": (0.107,)}},
    "thiophene": {"f-": {"2": (0.059,), "3": (0.138,)}},
    "acrolein": {"f+": {"beta": (0.211,), "alpha": (0.116,), "carbonyl": (0.171,)}},
}

#: Table 5's experimental column, as printed (ASCII for the printed symbols), for the reported arm: the class of position the experiment prefers. Reported beside our values and never decided on.
EXPERIMENTAL_SELECTIVITY = {
    "anilinium": "p >= m > o", "phenolate": "o, p", "phenol": "p ~ o > m", "aniline": "o, p", "fluorobenzene": "p > o > m", "benzaldehyde": "m > o >> p",
    "styrene": "o, p", "nitrobenzene": "m >> o > p", "pyrrole": "2", "furan": "2", "thiophene": "2",
}


@dataclass(frozen=True)
class Entry:
    """One published number: a source's value of one attack's condensed function for one label of one molecule."""

    source: str
    molecule: str
    attack: str
    label: str
    #: One value (every atom of the label carries it) or two (an unordered pair for two inequivalent atoms).
    values: tuple[float, ...]
    level: str


def _entries(source: str, table: Mapping[str, Mapping[str, Mapping[str, tuple[float, ...]]]], molecules: Collection[str] | None = None) -> tuple[Entry, ...]:
    out = []
    for molecule, by_attack in table.items():
        if molecules is not None and molecule not in molecules:
            continue
        species = ALL_SPECIES[molecule]
        for attack, by_label in by_attack.items():
            out.extend(Entry(source, molecule, attack, label, values, species.level) for label, values in by_label.items())
    return tuple(out)


def deproft_entries(molecules: Collection[str] | None = None) -> tuple[Entry, ...]:
    return _entries("deproft2002", DEPROFT, molecules)


def count_numbers(entries: Collection[Entry]) -> int:
    """How many published NUMBERS the entries hold (a pair is two)."""
    return sum(len(entry.values) for entry in entries)


# --- the rules that decide which published numbers may be targets ------------------------------------------------------------


def _atoms_of_label(species: GateSpecies, label: str) -> int:
    return sum(1 for candidate in species.labels if candidate == label)


def column_sum(molecule: str, attack: str) -> float:
    """The sum over every atom of a COMPLETE column: a label with one value carried by every one of its atoms counts that many times, a label with a pair counts both values."""
    if (molecule, attack) not in COMPLETE_COLUMNS:
        raise ValueError(f"{molecule}'s {attack} column omits atoms, so it cannot be summed")
    species = ALL_SPECIES[molecule]
    total = 0.0
    for label, values in DEPROFT[molecule][attack].items():
        atoms = _atoms_of_label(species, label)
        if len(values) == atoms:
            total += sum(values)
        elif len(values) == 1:
            total += atoms * values[0]
        else:
            raise ValueError(f"{molecule} {label}: {len(values)} published values for {atoms} atoms")
    return total


def failing_columns() -> tuple[tuple[str, str, float], ...]:
    """(molecule, attack, sum) of every complete column that does not sum to 1 within `SUM_TOLERANCE` (Rule A).

    A published function over all the atoms of a molecule adds to one, so such a column holds a misprint, and which entry is wrong cannot be told. The whole column is dropped."""
    bad = []
    for molecule, attack in COMPLETE_COLUMNS:
        total = column_sum(molecule, attack)
        if abs(total - 1.0) > SUM_TOLERANCE + _SLACK:
            bad.append((molecule, attack, round(total, 4)))
    return tuple(bad)


def _agrees(first: Sequence[float], second: Sequence[float]) -> bool:
    return len(first) == len(second) and all(abs(a - b) <= SECOND_PRINTING_TOLERANCE + _SLACK for a, b in zip(sorted(first), sorted(second)))


def corroboration_failures() -> tuple[tuple[str, str, str, tuple[float, ...], tuple[float, ...] | None], ...]:
    """(molecule, attack, label, first printing, second printing or None) of every number of a partial column that has no agreeing second printing (Rule B).

    Only the molecules `SABLON` reprints are looked at: a molecule with a partial column and no reprint at all (phenolate, the enolate, the Table 6 rings) is not a target and is not listed here
    as a failure, because it was never offered."""
    failed = []
    for molecule, by_attack in SABLON.items():
        for attack, by_label in by_attack.items():
            for label, first in DEPROFT[molecule][attack].items():
                second = by_label.get(label)
                if second is None or not _agrees(first, second):
                    failed.append((molecule, attack, label, first, second))
    return tuple(failed)


def decided_entries() -> tuple[Entry, ...]:
    """The published numbers the verdict is decided on, after every rule: 47.

    From the complete columns, those of the species the gate runs that Rule A did not drop (HCN, N2O, SCN-, NO2-; CO and formaldehyde are kept out because the first gate saw them). From the partial
    columns, those of the species `SABLON` reprints where the second printing agrees (Rule B)."""
    dropped = {(molecule, attack) for molecule, attack, _ in failing_columns()}
    unconfirmed = {(molecule, attack, label) for molecule, attack, label, _first, _second in corroboration_failures()}
    chosen = []
    for entry in deproft_entries(SPECIES):
        key = (entry.molecule, entry.attack)
        if key in COMPLETE_COLUMNS:
            if key in dropped:
                continue
        elif entry.molecule not in SABLON or (entry.molecule, entry.attack, entry.label) in unconfirmed:
            continue
        chosen.append(entry)
    return tuple(chosen)


def reported_entries() -> tuple[Entry, ...]:
    """The published numbers the reported arm compares and the verdict never reads: every number of the species outside the decision (the first gate's two, the Table 6 rings, the enolate, phenolate), at
    their own levels; the 13 neutral and cation species' decided numbers again at the application's default preset, relabelled with it (a different basis from the source's: a measure of basis dependence)."""
    entries = list(deproft_entries(REPORTED_SPECIES))
    for entry in decided_entries():
        if SPECIES[entry.molecule].level == LEVEL_6_31GS:
            entries.append(dataclasses.replace(entry, level=LEVEL_DEFAULT))
    return tuple(entries)


# --- the site statements ---------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class SiteStatement:
    """A documented site: the attack, the label expected to have the largest value, and the labels the statement is about (a table that lists only some atoms is restricted to those)."""

    molecule: str
    attack: str
    expected: str
    scope: tuple[str, ...]


def _statement(molecule: str, attack: str, expected: str, scope: str) -> SiteStatement:
    return SiteStatement(molecule, attack, expected, tuple(scope.split()))


#: The labels a statement about a monosubstituted benzene is restricted to: the ring carbons the source lists, not the ipso carbon, the substituent or the hydrogens.
_RING = "ortho meta para"
#: The statements of section 3: "the largest published value is on `expected`, among the labels of `scope`". Eleven are decided at T = 0.02 and four are listed and not (`undecidable_site_statements`).
SITE_STATEMENTS = (
    _statement("HCN", "f-", "N", "H C N"),
    _statement("SCN-", "f-", "S", "S C N"),
    _statement("anilinium", "f-", "para", _RING),
    _statement("phenol", "f-", "para", _RING),
    _statement("aniline", "f-", "para", _RING),
    _statement("fluorobenzene", "f-", "para", _RING),
    _statement("styrene", "f-", "para", _RING),
    _statement("pyrrole", "f-", "2", "2 3"),
    _statement("furan", "f-", "2", "2 3"),
    _statement("thiophene", "f-", "3", "2 3"),
    _statement("acrolein", "f+", "beta", "beta alpha carbonyl"),
    # listed, and left out of the decision by Rule C
    _statement("N2O", "f-", "O", "Nt Nc O"),
    _statement("NO2-", "f-", "O", "N O"),
    _statement("benzaldehyde", "f-", "para", _RING),
    _statement("nitrobenzene", "f-", "meta", _RING),
)


def _largest_per_label(molecule: str, attack: str, scope: Sequence[str]) -> dict[str, float]:
    return {label: max(DEPROFT[molecule][attack][label]) for label in scope}


def published_margin(statement: SiteStatement) -> float | None:
    """How far ahead of the next listed label the expected one is in the published numbers, or None when the published numbers do not put it first (a negative or None margin means the paper's own
    table disagrees with the statement)."""
    values = _largest_per_label(statement.molecule, statement.attack, statement.scope)
    expected = values[statement.expected]
    others = [value for label, value in values.items() if label != statement.expected]
    if not others or expected < max(others) - _SLACK:
        return None
    return expected - max(others)


def decidable_site_statements(tolerance: float = TOLERANCE) -> tuple[SiteStatement, ...]:
    """The statements the verdict may be decided on: the published margin is at least `SITE_MARGIN_FACTOR * tolerance` (so the tolerance cannot turn the ordering over) and the table puts the
    expected label first (Rule C)."""
    out = []
    for statement in SITE_STATEMENTS:
        margin = published_margin(statement)
        if margin is not None and margin >= SITE_MARGIN_FACTOR * tolerance - _SLACK:
            out.append(statement)
    return tuple(out)


def undecidable_site_statements(tolerance: float = TOLERANCE) -> tuple[tuple[SiteStatement, float | None], ...]:
    """The (statement, margin) the rules leave out, and why: a margin under the bound or no support in the table."""
    decidable = set(decidable_site_statements(tolerance))
    return tuple((statement, published_margin(statement)) for statement in SITE_STATEMENTS if statement not in decidable)


# --- what a run measured ---------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class MeasuredRun:
    """One Fukui run of one species at one level, as the application stored it."""

    molecule: str
    level: str
    #: The elements of the run's atoms, in the order of the values below.
    symbols: tuple[str, ...]
    #: Empty for an anion (v2 does not compute the N+1 state), and then f0 and the dual descriptor are empty too.
    f_plus: tuple[float, ...]
    f_minus: tuple[float, ...]
    f_zero: tuple[float, ...]
    dual: tuple[float, ...]
    charge: int
    multiplicity: int
    orca_version: str
    #: The panel's method/basis string the run used, and what the run's provenance says it was: the grid, the functions it computed and the charge of the species it took.
    method_basis: str = ""
    grid: str = ""
    functions: str = ""
    reference_charge: int | None = None
    #: Whether the run was recorded as completed.
    completed: bool = True
    #: Whether the run's input fingerprint is that of the molecule's ORCA-optimized conformer, so the states ran on the geometry the preregistration describes and not on the force-field embedding.
    on_optimized_geometry: bool = True
    #: The commit the run was made from and whether `src/` differed from it; the gate needs ONE version of the code behind every run.
    calculation_commit: str = ""
    calculation_dirty: bool = False
    #: Acrolein's optimized O=C-C=C dihedral in degrees (its input-validity check), else None.
    dihedral_degrees: float | None = None

    def values(self, attack: str) -> tuple[float, ...]:
        return self.f_plus if attack == "f+" else self.f_minus

    def labels(self) -> tuple[str, ...]:
        """What a published table calls each atom of this run: the species' own labels when the run has the atoms the species should, else the elements."""
        species = ALL_SPECIES.get(self.molecule)
        return species.labels if species is not None and species.atoms == self.symbols else self.symbols

    def of_label(self, attack: str, label: str) -> tuple[float, ...]:
        """The value of every atom a published table calls `label`."""
        return tuple(value for atom_label, value in zip(self.labels(), self.values(attack)) if atom_label == label)


def compare(entries: Collection[Entry], runs: Mapping[tuple[str, str], MeasuredRun], tolerance: float, *, decided: bool = True) -> list[Row]:
    """Each published number against the run of its molecule at its level; one `Row` per number (a published pair is two).

    A label with ONE published value is compared with every atom that carries it, and the worst difference is the row's, so two equivalent atoms that came apart are seen (the first gate's rule for CO2's
    oxygens). A label with a PAIR is matched as an unordered pair: both lists sorted, each element against its partner; it needs exactly two measured atoms. A number with no run at its level, or with
    no atom of its label, is not compared."""
    rows: list[Row] = []
    for entry in entries:
        run = runs.get((entry.molecule, entry.level))
        if run is None:
            continue
        measured = run.of_label(entry.attack, entry.label)
        if not measured:
            continue
        neutral = ALL_SPECIES[entry.molecule].neutral if entry.molecule in ALL_SPECIES else True
        if len(entry.values) == 1:
            pairs = [(entry.values[0], max(measured, key=lambda value: abs(value - entry.values[0])))]
        elif len(measured) == len(entry.values):
            pairs = list(zip(sorted(entry.values), sorted(measured)))
        else:
            continue
        for published, value in pairs:
            difference = value - published
            rows.append(Row(
                entry.source, entry.molecule, entry.label, entry.attack, entry.level, published, value, difference,
                abs(difference) <= tolerance + _SLACK, neutral, decided,
            ))
    return rows


def site_found(run: MeasuredRun, statement: SiteStatement) -> str:
    """The label of the atom with the largest measured value among the labels the statement is about."""
    best_label, best_value = "", -math.inf
    for label, value in zip(run.labels(), run.values(statement.attack)):
        if label in statement.scope and value > best_value:
            best_label, best_value = label, value
    return best_label


def dihedral_degrees(a: Sequence[float], b: Sequence[float], c: Sequence[float], d: Sequence[float]) -> float:
    """The dihedral angle a-b-c-d in degrees, from four (x, y, z) points, in [-180, 180]. Only its magnitude is used here (0 is cis, 180 trans); the sign is the right-handed one."""
    b1 = [q - p for p, q in zip(a, b)]
    b2 = [q - p for p, q in zip(b, c)]
    b3 = [q - p for p, q in zip(c, d)]

    def cross(u, v):
        return [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]]

    def dot(u, v):
        return sum(x * y for x, y in zip(u, v))

    n1, n2 = cross(b1, b2), cross(b2, b3)
    length = math.sqrt(dot(b2, b2))
    m1 = cross(n1, [x / length for x in b2])
    return math.degrees(math.atan2(dot(m1, n2), dot(n1, n2)))


def acrolein_dihedral(labels: Sequence[str], positions: Sequence[Sequence[float]]) -> float:
    """Acrolein's O=C-C=C dihedral (oxygen, carbonyl carbon, alpha carbon, beta carbon) in degrees, from the atoms' positions in the order of `GateSpecies.labels`: the input-validity check of section 4."""
    index = {label: list(labels).index(label) for label in ("O", "carbonyl", "alpha", "beta")}
    return dihedral_degrees(*(positions[index[label]] for label in ("O", "carbonyl", "alpha", "beta")))


def _within_sum_rule(run: MeasuredRun, label: str, undecided: list[str]) -> None:
    for attack in ATTACKS:
        values = run.values(attack)
        if not values:
            continue
        total = sum(values)
        if abs(total - 1.0) > RUN_SUM_TOLERANCE:
            undecided.append(f"{label}: {attack} sums to {total:.4f}, not 1")


def _run_problems(run: MeasuredRun, species: GateSpecies, label: str) -> list[str]:
    """Why one run cannot be used, or an empty list: everything section 7 lists that is a property of ONE run."""
    problems: list[str] = []
    if run.charge != species.charge:
        problems.append(f"{label} ran at charge {run.charge}, not the species' {species.charge}")
    if run.multiplicity != 1:
        problems.append(f"{label} ran at multiplicity {run.multiplicity}")
    if not run.completed:
        problems.append(f"{label} did not complete")
    if not run.on_optimized_geometry:
        problems.append(f"{label} did not run on the ORCA-optimized geometry")
    if run.symbols != species.atoms:
        problems.append(f"{label} has atoms {run.symbols}, not {species.atoms}")
    if run.method_basis != species.method_basis:
        problems.append(f"{label} used {run.method_basis!r}, the species' method is {species.method_basis!r}")
    if run.grid != GRID:
        problems.append(f"{label}: its grid is {run.grid!r}, not {GRID!r}, so it is not the calculation the gate tests")
    if run.functions != species.functions:
        problems.append(f"{label}: it computed {run.functions!r}, the species' calculation computes {species.functions!r}")
    if run.reference_charge != species.charge:
        problems.append(f"{label}: its reference charge is {run.reference_charge!r}, not the species' {species.charge}")
    if species.charge < 0 and (run.f_plus or run.f_zero or run.dual):
        problems.append(f"{label}: an anion's run holds f+, f0 or the dual descriptor, which v2 does not compute")
    _within_sum_rule(run, label, problems)
    identity = max((abs(d - (p - m)) for p, m, d in zip(run.f_plus, run.f_minus, run.dual)), default=0.0)
    if identity > _SLACK:
        problems.append(f"{label}: the dual descriptor is not f+ - f- (differs by {identity:.2e})")
    mean = max((abs(z - (p + m) / 2) for p, m, z in zip(run.f_plus, run.f_minus, run.f_zero)), default=0.0)
    if mean > _SLACK:
        problems.append(f"{label}: f0 is not the mean of f+ and f- (differs by {mean:.2e})")
    if run.calculation_dirty:
        problems.append(f"{label}: src/ differed from commit {run.calculation_commit or 'unknown'} when it ran")
    if run.molecule == "acrolein":
        if run.dihedral_degrees is None:
            problems.append(f"{label}: no O=C-C=C dihedral was recorded, so the s-trans input check cannot be made")
        elif abs(abs(run.dihedral_degrees) - 180.0) > DIHEDRAL_LIMIT_DEGREES + _SLACK:
            problems.append(f"{label}: the optimized O=C-C=C dihedral is {run.dihedral_degrees:.1f} degrees, not within {DIHEDRAL_LIMIT_DEGREES:.0f} of 180 (s-cis, not the published molecule)")
    return problems


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

    `runs` is by (molecule, level) and must hold every species at its level. NOT EVALUABLE takes precedence over everything: a gate that cannot decide does not claim a failure. Within each outcome every
    reason is collected. `floor` is the larger of the two noise floors (the neutral route's and the anion route's).
    """
    undecided: list[str] = []
    if tolerance is None or abs(tolerance - TOLERANCE) > _SLACK:
        undecided.append(f"the tolerance is {tolerance!r} and the preregistered one is {TOLERANCE}")
    if floor is None:
        undecided.append("no noise floor was measured")
    elif floor > FLOOR_LIMIT + _SLACK:
        undecided.append(f"the noise floor {floor:.4f} is above {FLOOR_LIMIT}, so a tolerance of {TOLERANCE} cannot be told from noise")
    elsewhere = sorted(set(orca_versions) - {ORCA_VERSION})
    if elsewhere or not set(orca_versions):
        undecided.append(
            f"ORCA {', '.join(elsewhere) if elsewhere else 'with no recorded version'} is not the preregistered {ORCA_VERSION}: the numbers are recorded and are not a pass"
        )
    if unfinished_runs:
        undecided.append(f"a run did not complete: {', '.join(sorted(unfinished_runs))}")
    needed = {(name, species.level) for name, species in SPECIES.items()} - set(not_computed)
    absent = sorted(needed - set(runs))
    if absent:
        undecided.append(f"no run for: {', '.join(f'{m} at {level}' for m, level in absent)}")
    for (molecule, level), run in sorted(runs.items()):
        species = SPECIES.get(molecule)
        if species is not None:
            undecided.extend(_run_problems(run, species, f"{molecule} at {level}"))
    commits = {run.calculation_commit for key, run in runs.items() if key[0] in SPECIES}
    if len(commits) > 1:
        undecided.append(f"the runs were made from {len(commits)} different commits ({', '.join(sorted(c[:10] for c in commits))}), so they are not one calculation")
    if undecided:
        return Verdict(Outcome.NOT_EVALUABLE, tuple(undecided))

    rows = compare(decided_entries(), runs, TOLERANCE)
    site_rows: list[SiteRow] = []
    for statement in decidable_site_statements(TOLERANCE):
        species = SPECIES[statement.molecule]
        run = runs.get((statement.molecule, species.level))
        if run is None:
            continue  # NOT COMPUTED: already a failure of its own, in `never`
        found = site_found(run, statement)
        site_rows.append(SiteRow(
            statement.molecule, species.level, statement.attack, statement.expected, found, published_margin(statement), found == statement.expected, species.neutral,
        ))

    never = [
        f"{molecule} at {level}: ORCA did not complete the states in {MAX_ATTEMPTS} attempts"
        for molecule, level in sorted(not_computed) if molecule in SPECIES
    ]

    def failures(neutral: bool) -> list[str]:
        return (
            [line for line in never if SPECIES[line.split(" ", 1)[0]].neutral == neutral]
            + [
                f"{r.molecule} {r.element} {r.attack} at {r.level}: {r.measured:.4f} is {r.difference:+.4f} from {r.source}'s {r.published:.4f}"
                for r in rows if r.within is False and r.neutral == neutral
            ]
            + [
                f"{s.molecule} {s.attack} at {s.level}: the largest value is on {s.found}, the documented site is {s.expected}"
                for s in site_rows if not s.reproduced and s.neutral == neutral
            ]
        )

    neutral_failures, charged_failures = failures(True), failures(False)
    charged_outside = tuple(sorted({line.split(" ", 1)[0] for line in charged_failures}))
    if neutral_failures:
        return Verdict(Outcome.FAIL, tuple(neutral_failures + charged_failures), tuple(rows), tuple(site_rows), charged_outside)
    if charged_failures:
        return Verdict(Outcome.PARTIAL, tuple(charged_failures), tuple(rows), tuple(site_rows), charged_outside)
    return Verdict(Outcome.PASS, (), tuple(rows), tuple(site_rows))


# --- from the stored runs to a verdict ---------------------------------------------------------------------------------------


def measured_from_record(record: Mapping) -> MeasuredRun:
    """The `MeasuredRun` a record of one stored run (written by the drive step `fukui_gate_record` with `"gate": 2`) describes."""
    reference = record.get("reference_charge")
    dihedral = record.get("dihedral_degrees")
    return MeasuredRun(
        molecule=str(record["species"]),
        level=str(record["level"]),
        symbols=tuple(record["symbols"]),
        f_plus=tuple(float(v) for v in record.get("f_plus") or ()),
        f_minus=tuple(float(v) for v in record["f_minus"]),
        f_zero=tuple(float(v) for v in record.get("f_zero") or ()),
        dual=tuple(float(v) for v in record.get("dual") or ()),
        charge=int(record["charge"]),
        multiplicity=int(record["multiplicity"]),
        orca_version=str(record["orca_version"]),
        method_basis=str(record.get("method_basis", "")),
        grid=str(record.get("grid", "")),
        functions=str(record.get("functions", "")),
        reference_charge=None if reference is None else int(reference),
        completed=bool(record.get("completed", True)),
        on_optimized_geometry=bool(record.get("on_optimized_geometry", False)),
        calculation_commit=str(record.get("calculation_commit", "")),
        calculation_dirty=bool(record.get("calculation_dirty", True)),
        dihedral_degrees=None if dihedral is None else float(dihedral),
    )


def judge_records(records: list[Mapping], *, floor: float | None, tolerance: float | None = TOLERANCE) -> Verdict:
    """The verdict from the records the drive wrote: attempts settled by the rule, the runs built, `judge` called.

    A conflict (two completed attempts of one job) makes the gate unable to decide and says so."""
    chosen, never, unfinished, conflicts = settle_attempts(records)
    runs = {pair: measured_from_record(record) for pair, record in chosen.items()}
    versions = {run.orca_version for run in runs.values()}
    verdict = judge(runs, tolerance=tolerance, floor=floor, orca_versions=versions, unfinished_runs=unfinished, not_computed=never)
    if conflicts:
        return Verdict(Outcome.NOT_EVALUABLE, tuple(conflicts) + verdict.reasons if verdict.outcome is Outcome.NOT_EVALUABLE else tuple(conflicts))
    return verdict


def reported_rows(runs: Mapping[tuple[str, str], MeasuredRun], tolerance: float = TOLERANCE) -> list[dict]:
    """The reported arm as plain dicts: each reported number against the run at its level, never decided on."""
    return [dataclasses.asdict(row) for row in compare(reported_entries(), runs, tolerance, decided=False)]


def reported_site_rows(runs: Mapping[tuple[str, str], MeasuredRun]) -> list[dict]:
    """The statements the rules leave out, against the runs that have them: our largest label beside the expected one, with no verdict, plus the experimental selectivity where Table 5 prints one."""
    out = []
    for statement, margin in undecidable_site_statements():
        species = SPECIES[statement.molecule]
        run = runs.get((statement.molecule, species.level))
        if run is None:
            continue
        out.append({
            "molecule": statement.molecule, "attack": statement.attack, "expected": statement.expected, "found": site_found(run, statement),
            "published_margin": margin, "experimental": EXPERIMENTAL_SELECTIVITY.get(statement.molecule), "decided": False,
        })
    return out


def share_within(rows: Sequence[Row], limit: float) -> tuple[int, int]:
    """(rows within `limit`, rows): the share of the decided numbers within a tighter bound, written and deciding nothing."""
    return sum(1 for row in rows if abs(row.difference) <= limit + _SLACK), len(rows)


@dataclass(frozen=True)
class FloorResult:
    """One noise floor: the largest difference between two runs that should have given the same number, for the same input twice and for the whole chain twice."""

    molecule: str
    same_input: float
    whole_chain: float

    @property
    def floor(self) -> float:
        return max(self.same_input, self.whole_chain)


def combined_floor(floors: Sequence[FloorResult]) -> float:
    """The floor the gate uses: the larger of the routes' (`judge`'s `floor`)."""
    if not floors:
        raise ValueError("a noise floor needs at least one route")
    return max(result.floor for result in floors)
