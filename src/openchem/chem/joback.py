"""Joback & Reid group contributions [source:joback1987].

Eleven pure-component properties from a structure alone: normal boiling and
freezing points, the three critical constants, standard enthalpy and Gibbs
energy of formation, ideal-gas heat capacity as a function of temperature,
enthalpies of vaporization and fusion, and liquid viscosity.

The table lives in `data/joback_groups.json` with each row's own printed
identity; `tests/test_joback_table.py` gates it against the paper's own
worked example. This module is the FRAGMENTER -- the part the paper does not
supply -- plus the equations of its Table II.

WHAT THE PAPER DOES NOT GIVE YOU
================================

**Joback prints group NAMES, not SMARTS.** "—CH2— (nonring)" and ">C=O
(ring)" are unambiguous to a chemist reading a table and are not a machine
specification, so every pattern below is this project's reading of a printed
label. That is why the acceptance test runs the paper's own worked example
end to end from a SMILES rather than from hand-supplied group counts: a
fragmenter that is subtly wrong still produces plausible numbers.

**ONE THING THAT WOULD OTHERWISE HAVE BEEN GUESSED IS SETTLED BY THE PAPER.**
An aromatic ring could plausibly map to the ring `—CH2—`/`>CH—` increments or
to the ring `=CH—`/`=C<` ones. Table IV decomposes p-dichlorobenzene as
4x `=CH— (ring)` + 2x `=C< (ring)` + 2x `—Cl`, so the sp2 reading is the
paper's own and not an inference.

HOW THE FRAGMENTATION WORKS
===========================

Patterns are tried in the order declared. A match claims its atoms; a match
overlapping an already-claimed atom is skipped. **Every heavy atom must end
up claimed exactly once** -- Joback is additive over a partition of the
molecule, so partial coverage is not a worse answer, it is a different
quantity. An unclaimed atom is a REFUSAL naming the atom.

Order is therefore load-bearing and each entry below says why it sits where
it does. The general rule: multi-atom groups before the single-atom groups
they contain, and specific before general.

WHERE JOBACK GENUINELY CANNOT ANSWER
====================================

Recorded because each is a refusal a reader will otherwise take for a bug:

- **There is no `>N— (ring)` group.** The nitrogen block has `>NH (ring)`
  and `—N= (ring)` but no ring tertiary amine, so N-methylpiperidine and
  N-methylpyrrole have no decomposition. Mapping them onto the nonring value
  is the obvious repair and is an invention; this refuses instead.
- **A dash in Table III means no contribution, not zero.** `—N= (nonring)`
  has no Vc, no Tf, no Gform and no heat capacity. A molecule containing one
  gets the properties it can support and a named refusal for the rest,
  rather than a sum that silently treats absent as 0.
- **Sulfoxides, sulfones and other hypervalent sulfur** have no group -- the
  table stops at `—SH` and `—S—`.
- Joback is for a **pure, neutral component**, so a salt, a mixture and a
  charged species are all refused before fragmentation starts.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
from pathlib import Path

from typing import Any

from rdkit import Chem

from openchem.chem.group_contribution import (
    build_patterns,
    claim_groups,
    describe_uncovered,
)
from rdkit.Chem import Descriptors

from openchem.domain.common import TOTAL, CacheState, Provenance, decline_total
from openchem.domain.report import Fact, FactCategory, ReportResult
from openchem.domain.structure_issue import Basis

#: DECLARED USER-FACING. `tests/test_calculator_reachability.py` fails if
#: nothing a user can press reaches this module -- which is exactly what
#: happened to four correct, guarded, sourced modules in PR #41.
USER_FACING_PROVIDER = (
    "Joback & Reid group contributions, through the "
    "'Thermophysical Properties (Joback)' calculator"
)

_DATA = Path(__file__).parent / "data" / "joback_groups.json"

#: Table VI (p240): the paper's own average absolute error per property,
#: which is what a declared uncertainty on a result must be built from.
#: Tf has no percent error worth quoting -- the paper says outright that Tb
#: and especially Tf "are not accurate and should be considered as only very
#: approximate".
PAPER_ABSOLUTE_ERROR = {
    "Tb": (12.9, "K"),
    "Tf": (22.6, "K"),
    "Tc": (4.8, "K"),
    "Pc": (2.1, "bar"),
    "Vc": (7.5, "cm3/mol"),
    "Hform": (8.4, "kJ/mol"),
    "Gform": (8.4, "kJ/mol"),
    "Hvap": (1.27, "kJ/mol"),
    "Hfus": (2.0, "kJ/mol"),
}

#: The paper's stated validity windows (p238).
CP_RANGE_K = (273.0, 1000.0)
VISCOSITY_MAX_REDUCED_T = 0.7


class JobackRefusal(Enum):
    """Why Joback does not apply to this structure.

    A VALUE rather than a message, so no consumer starts matching on prose --
    the shape `HlbRefusal`, `BcsReason` and `IsotopeRefusal` already use.
    """

    NOT_A_STRUCTURE = "the structure could not be read"
    NOT_A_PURE_COMPONENT = "more than one disconnected fragment"
    CHARGED = "the structure carries a net formal charge"
    NO_HEAVY_ATOMS = "the structure has no heavy atoms"
    UNCOVERED_ATOM = "an atom belongs to no Joback group"
    NO_CONTRIBUTION = "a group in this molecule has no contribution for that property"


# ---------------------------------------------------------------------------
# The patterns
# ---------------------------------------------------------------------------
#
# `[#6]`/`[#7]` rather than `C`/`N` throughout: SMARTS' uppercase organic
# symbols match ALIPHATIC atoms only, so `[CX3H1;R]` silently misses every
# aromatic CH -- which is most of the ring carbons anybody will feed this.
#
# `X` counts total connections INCLUDING hydrogens, which is what makes an
# H count and a connection count together pin a Joback label: benzene's CH
# is X3/H1, chlorobenzene's C-Cl is X3/H0.

_SPEC: tuple[tuple[str, str, str], ...] = (
    # --- multi-atom groups, before the single atoms they contain ----------
    # Nitro in both the hypervalent and the charge-separated form. FIRST,
    # because otherwise its nitrogen reads as `-N=` and its oxygens as `=O`.
    ("-NO2", "[NX3](=[OX1])=[OX1]", "nitro, hypervalent form"),
    ("-NO2", "[NX3+](=[OX1])[OX1-]", "nitro, charge-separated form"),
    # Acid before ester before ketone: all three centre on a CX3 carbonyl,
    # and each later pattern is the earlier one with a substituent removed.
    ("-COOH", "[CX3](=[OX1])[OX2H1]", "carboxylic acid: C, =O and -OH"),
    # The ester's R' is deliberately NOT in the pattern -- matching it would
    # claim a carbon that is its own group.
    ("-COO-", "[CX3](=[OX1])[OX2H0]", "ester: C, =O and the bridging -O-"),
    ("-CN", "[CX2]#[NX1]", "nitrile: C and N together"),
    # Aldehyde before ketone -- they differ only in the carbon's H count.
    ("O=CH-", "[#6X3H1](=[OX1])", "aldehyde: C and its =O"),
    ("ring>C=O", "[#6X3H0;R](=[OX1])", "ring ketone: the C is in the ring, the O is not"),
    (">C=O", "[#6X3H0;!R](=[OX1])", "ketone"),
    # --- oxygen -----------------------------------------------------------
    # Phenol before alcohol: the paper separates them, and the only thing
    # telling them apart is what the oxygen is attached to.
    # Recursive, so the match is the oxygen ALONE. `[OX2H1][c]` also claims
    # the aromatic carbon, which is its own `ring=C<` group -- phenol then
    # fragments to five CH and an OH, losing its ipso carbon entirely and
    # still returning a number.
    ("-OH(phenol)", "[OX2H1;$([OX2H1]c)]", "hydroxyl on an aromatic carbon"),
    ("-OH(alcohol)", "[OX2H1]", "any other hydroxyl"),
    ("ring-O-", "[OX2H0;R]", "ether oxygen in a ring"),
    ("-O-", "[OX2H0;!R]", "ether oxygen"),
    # "=O (except as above)" is the paper's own wording, so this must be the
    # LAST oxygen pattern -- it is defined by what has already been claimed.
    ("=O", "[OX1]", "a doubly-bonded oxygen none of the above claimed"),
    # --- nitrogen ---------------------------------------------------------
    # By hydrogen count then by ring membership, which is how Table III's
    # nitrogen block is itself organised.
    ("-NH2", "[#7X3H2]", "primary amine"),
    ("ring>NH", "[#7X3H1;R]", "secondary amine in a ring (pyrrole's NH included)"),
    (">NH", "[#7X3H1;!R]", "secondary amine"),
    # NOTE the asymmetry: there is no `>N- (ring)` in the paper, so a ring
    # tertiary nitrogen falls through to the coverage check and is refused.
    (">N-", "[#7X3H0;!R]", "tertiary amine, non-ring only -- the paper has no ring form"),
    ("=NH", "[#7X2H1]", "imine NH"),
    ("ring-N=", "[#7X2H0;R]", "ring imine nitrogen (pyridine's N included)"),
    ("-N=", "[#7X2H0;!R]", "imine nitrogen"),
    # --- sulfur -----------------------------------------------------------
    # `[#16]` and not `S`, for the same reason the carbons use `[#6]`:
    # uppercase S is aliphatic-only, and thiophene's sulfur is aromatic.
    ("-SH", "[#16X2H1]", "thiol"),
    ("ring-S-", "[#16X2H0;R]", "thioether in a ring, aromatic included"),
    ("-S-", "[#16X2H0;!R]", "thioether"),
    # --- halogens ---------------------------------------------------------
    ("-F", "[F]", "fluorine"),
    ("-Cl", "[Cl]", "chlorine"),
    ("-Br", "[Br]", "bromine"),
    ("-I", "[I]", "iodine"),
    # --- carbon -----------------------------------------------------------
    # Last, because every carbonyl, nitrile and carboxyl carbon above is a
    # carbon too, and has already been claimed by a more specific group.
    ("-CH3", "[#6X4H3]", "methyl"),
    ("ring-CH2-", "[#6X4H2;R]", "sp3 CH2 in a ring"),
    ("-CH2-", "[#6X4H2;!R]", "sp3 CH2"),
    ("ring>CH-", "[#6X4H1;R]", "sp3 CH in a ring"),
    (">CH-", "[#6X4H1;!R]", "sp3 CH"),
    ("ring>C<", "[#6X4H0;R]", "sp3 quaternary carbon in a ring"),
    (">C<", "[#6X4H0;!R]", "sp3 quaternary carbon"),
    ("=CH2", "[#6X3H2]", "terminal alkene CH2"),
    # Aromatic carbons land here, which Table IV settles rather than infers.
    ("ring=CH-", "[#6X3H1;R]", "sp2 CH in a ring, aromatic included"),
    ("=CH-", "[#6X3H1;!R]", "sp2 CH"),
    ("ring=C<", "[#6X3H0;R]", "sp2 substituted carbon in a ring, aromatic included"),
    ("=C<", "[#6X3H0;!R]", "sp2 substituted carbon"),
    # Allene and alkyne carbons are both X2; the bond order separates them.
    # All three recursive, so each match is ONE carbon. Writing the partner
    # into the pattern claims it as well: `[#6X2H1]#*` swallowed propyne's
    # internal alkyne carbon, which then contributed nothing and put Tb 27 K
    # low -- a wrong answer rather than a refusal, which is the failure mode
    # this whole module is arranged to avoid.
    ("=C=", "[#6X2H0;$([#6X2](=*)=*)]", "cumulated diene centre"),
    ("#CH", "[#6X2H1;$([#6X2]#*)]", "terminal alkyne CH"),
    ("#C-", "[#6X2H0;$([#6X2]#*)]", "internal alkyne carbon"),
)


@lru_cache(maxsize=1)
def _table() -> dict:
    return json.loads(_DATA.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def groups() -> dict[str, dict]:
    """The shipped table, keyed by group id."""
    return {g["id"]: g for g in _table()["groups"]}


#: How many heavy atoms each Joback group IS.
#:
#: **THIS IS THE INVARIANT THAT CATCHES A PATTERN CLAIMING ITS NEIGHBOURS**,
#: and it is here because three patterns did exactly that on the first run:
#: `[OX2H1][c]` swallowed phenol's ipso carbon, and `[#6X2H1]#*` swallowed
#: propyne's internal alkyne carbon. Neither produced a refusal -- the atom
#: WAS claimed, just by the wrong group -- so the full-coverage check could
#: not see either, and both returned a confident wrong number. Propyne's Tb
#: came out 27 K low.
#:
#: Coverage says every atom is claimed once. This says every group claims the
#: atoms it is made of. Only the pair is sound.
GROUP_ATOM_COUNT = {
    "-NO2": 3,      # N and both oxygens
    "-COOH": 3,     # C, =O, -OH
    "-COO-": 3,     # C, =O, the bridging -O-
    "-CN": 2,       # C and N
    "O=CH-": 2,     # C and its =O
    ">C=O": 2,
    "ring>C=O": 2,
}


@lru_cache(maxsize=1)
def _patterns() -> tuple[tuple[str, Chem.Mol, str], ...]:
    """Compiled once, and validated by `group_contribution.build_patterns`.

    The validation moved there when Hansen arrived so the atom-count
    invariant would travel with the walk rather than be left for the next
    fragmenter's author to remember -- it caught three bugs here, two of
    which produced wrong answers rather than refusals.
    """
    return build_patterns(_SPEC, set(groups()), GROUP_ATOM_COUNT, "Joback")


@dataclass(frozen=True)
class Fragmentation:
    """One molecule decomposed into Joback groups, or why it could not be.

    `counts` is empty exactly when `refusal` is set.
    """

    counts: dict[str, int] = field(default_factory=dict)
    refusal: JobackRefusal | None = None
    #: What could not be covered, when that is why it was refused.
    detail: str = ""
    #: TOTAL atoms, hydrogens included -- Eq. (5) needs this and every other
    #: equation is a bare group sum, which is what makes it easy to miss.
    n_atoms: int = 0
    molecular_weight: float = 0.0

    @property
    def applicable(self) -> bool:
        return self.refusal is None

    def total(self, column: str) -> float | None:
        """Sum one Table III column over the fragmentation.

        None when any group present has NO contribution for that column --
        the paper's dash. Absent is not zero, and a caller that adds it as
        zero gets a plausible number for a property Joback declines.
        """
        table = groups()
        running = 0.0
        for group_id, n in self.counts.items():
            value = table[group_id][column]
            if value is None:
                return None
            running += n * value
        return running

    def groups_without(self, column: str) -> list[str]:
        """Which groups are why `total(column)` is None -- for the message."""
        table = groups()
        return sorted(g for g in self.counts if table[g][column] is None)


def fragment(mol: Chem.Mol | None) -> Fragmentation:
    """Decompose a structure into Joback groups.

    Refuses rather than approximating. See the module docstring for the four
    kinds of structure Joback genuinely cannot answer for.
    """
    if mol is None or mol.GetNumAtoms() == 0:
        return Fragmentation(refusal=JobackRefusal.NOT_A_STRUCTURE)

    try:
        working = Chem.RemoveHs(Chem.Mol(mol))
    except Exception:
        return Fragmentation(refusal=JobackRefusal.NOT_A_STRUCTURE)

    if working.GetNumHeavyAtoms() == 0:
        return Fragmentation(refusal=JobackRefusal.NO_HEAVY_ATOMS)

    # A salt, a solvate or a drawn mixture is not a pure component, and the
    # equations would happily return a number for the union of two molecules.
    if len(Chem.GetMolFrags(working)) > 1:
        return Fragmentation(refusal=JobackRefusal.NOT_A_PURE_COMPONENT)

    if Chem.GetFormalCharge(working) != 0:
        return Fragmentation(refusal=JobackRefusal.CHARGED)

    walk = claim_groups(working, _patterns())
    if not walk.complete:
        return Fragmentation(
            refusal=JobackRefusal.UNCOVERED_ATOM,
            detail=describe_uncovered(working, walk.uncovered),
        )
    counts = walk.counts

    n_atoms = working.GetNumHeavyAtoms() + sum(
        a.GetTotalNumHs() for a in working.GetAtoms()
    )
    return Fragmentation(
        counts=counts,
        n_atoms=n_atoms,
        molecular_weight=Descriptors.MolWt(working),
    )


# ---------------------------------------------------------------------------
# Table II, equations (2)-(12)
# ---------------------------------------------------------------------------


def boiling_point(f: Fragmentation) -> float | None:
    """Eq. (2). The paper calls this and Tf "only very approximate"."""
    s = f.total("tb")
    return None if s is None else 198.2 + s


def freezing_point(f: Fragmentation) -> float | None:
    """Eq. (3)."""
    s = f.total("tf")
    return None if s is None else 122.5 + s


def critical_temperature(f: Fragmentation, boiling_point_k: float | None = None) -> float | None:
    """Eq. (4), which takes Tb.

    **The paper prefers an EXPERIMENTAL Tb and says so.** Its own worked
    example uses the measured 447 K for p-dichlorobenzene to get 681 K, and
    notes that the estimated 443 K would give 675 K -- "in other situations,
    large errors were found when using the estimated value of Tb". Pass one
    when you have it; the estimate is the fallback, not the intent.
    """
    s = f.total("tc")
    if s is None:
        return None
    tb = boiling_point_k if boiling_point_k is not None else boiling_point(f)
    if tb is None:
        return None
    denominator = 0.584 + 0.965 * s - s * s
    if denominator <= 0:
        return None
    return tb / denominator


def critical_pressure(f: Fragmentation) -> float | None:
    """Eq. (5). Uses the TOTAL atom count, hydrogens included."""
    s = f.total("pc")
    if s is None:
        return None
    base = 0.113 + 0.0032 * f.n_atoms - s
    return None if base == 0 else base ** -2


def critical_volume(f: Fragmentation) -> float | None:
    """Eq. (6)."""
    s = f.total("vc")
    return None if s is None else 17.5 + s


def enthalpy_of_formation(f: Fragmentation) -> float | None:
    """Eq. (7). Ideal gas at 298 K."""
    s = f.total("hform")
    return None if s is None else 68.29 + s


def gibbs_energy_of_formation(f: Fragmentation) -> float | None:
    """Eq. (8). Ideal gas, unit fugacity, 298 K."""
    s = f.total("gform")
    return None if s is None else 53.88 + s


def heat_capacity(f: Fragmentation, temperature_k: float) -> float | None:
    """Eq. (9). Ideal gas, J/mol/K. Valid 273-1000 K per the paper."""
    a, b, c, d = (f.total(x) for x in ("a", "b", "c", "d"))
    if None in (a, b, c, d):
        return None
    t = temperature_k
    return (a - 37.93
            + (b + 0.210) * t
            + (c - 3.91e-4) * t ** 2
            + (d + 2.06e-7) * t ** 3)


def enthalpy_of_vaporization(f: Fragmentation) -> float | None:
    """Eq. (10). At the normal boiling point."""
    s = f.total("hvap")
    return None if s is None else 15.30 + s


def enthalpy_of_fusion(f: Fragmentation) -> float | None:
    """Eq. (11)."""
    s = f.total("hfus")
    return None if s is None else -0.88 + s


def liquid_viscosity(f: Fragmentation, temperature_k: float) -> float | None:
    """Eq. (12), N s/m2. Valid from Tf to a reduced temperature of ~0.7."""
    a, b = f.total("eta_a"), f.total("eta_b")
    if a is None or b is None or temperature_k <= 0:
        return None
    return f.molecular_weight * math.exp((a - 597.82) / temperature_k + b - 11.202)


def refusal_text(result: Fragmentation) -> str:
    """One sentence saying what Joback could not do, and why.

    Generated in ONE place so `if "refused" in message` never becomes
    application logic -- the shape `IsotopeRefusal.refuse_isomer` already
    uses.
    """
    if result.refusal is None:
        return ""
    if result.refusal is JobackRefusal.UNCOVERED_ATOM:
        return (
            f"Joback has no group for {result.detail}. The method is additive over a "
            "complete decomposition, so a partial sum would be a different quantity "
            "rather than a rougher answer. Note the table has no ring tertiary amine "
            "and stops at divalent sulfur."
        )
    if result.refusal is JobackRefusal.NOT_A_PURE_COMPONENT:
        return (
            "Joback estimates properties of a pure component, and this structure is "
            "more than one disconnected fragment."
        )
    if result.refusal is JobackRefusal.CHARGED:
        return "Joback's groups are parameterised for neutral species."
    if result.refusal is JobackRefusal.NO_CONTRIBUTION:
        return (
            f"Joback's table prints no contribution for {result.detail} -- a dash, "
            "which means absent rather than zero."
        )
    return "This structure could not be read."


# ---------------------------------------------------------------------------
# The registered calculator
# ---------------------------------------------------------------------------

#: Order the facts are reported in, and the accessor for each.
#:
#: Tc is absent here because it takes an argument -- see `compute_joback`.
_SCALAR_FACTS: tuple[tuple[str, str, str, str], ...] = (
    ("Boiling point (normal)", "Tb", "K", "boiling_point"),
    ("Freezing point (normal)", "Tf", "K", "freezing_point"),
    ("Critical pressure", "Pc", "bar", "critical_pressure"),
    ("Critical volume", "Vc", "cm3/mol", "critical_volume"),
    ("Enthalpy of formation (ideal gas, 298 K)", "Hform", "kJ/mol", "enthalpy_of_formation"),
    ("Gibbs energy of formation (ideal gas, 298 K)", "Gform", "kJ/mol", "gibbs_energy_of_formation"),
    ("Enthalpy of vaporization (at Tb)", "Hvap", "kJ/mol", "enthalpy_of_vaporization"),
    ("Enthalpy of fusion", "Hfus", "kJ/mol", "enthalpy_of_fusion"),
)


def _display(value: float, places: int) -> str:
    """Fixed decimals, EXCEPT where they would destroy the number.

    Liquid viscosity is around 1e-4 N s/m2, so the panel's ordinary two
    decimal places render p-dichlorobenzene's 7.26e-4 as "0.00" -- a value
    that reads as zero rather than as small. Found by looking at the rendered
    facts, which is the only thing that shows it.
    """
    if value != 0 and abs(value) < 10 ** -places:
        return f"{value:.{max(places, 2)}e}"
    return f"{value:.{places}f}"


def compute_joback(
    mol: Chem.Mol, molecule_uuid: str, parameters: dict[str, Any] | None = None
) -> ReportResult:
    """Eleven Joback properties, or a named refusal.

    **THE REFUSAL IS THE RESULT**, as it is for Griffin HLB. Joback is
    additive over a complete decomposition, so a molecule with an atom in no
    group has no answer rather than a rough one -- and returning a partial
    sum would be a different quantity wearing the same label.

    **EACH PROPERTY CARRIES THE PAPER'S OWN ERROR**, from its Table VI, and
    Tb and Tf additionally carry the paper's own words about them: it calls
    them "not accurate" and "only very approximate", which is a stronger
    caveat than an error bar alone conveys.
    """
    parameters = parameters or {}
    places = int(parameters.get("decimal_places", 2))
    temperature = float(parameters.get("temperature_k", 298.15))
    experimental_tb = parameters.get("experimental_boiling_point_k")
    experimental_tb = float(experimental_tb) if experimental_tb else None

    f = fragment(mol)

    provenance = Provenance(
        created_by="core",
        method="joback_reid_1987",
        parameters={
            "decimal_places": places,
            "temperature_k": temperature,
            "experimental_boiling_point_k": experimental_tb,
            "groups": dict(sorted(f.counts.items())) if f.applicable else None,
            "refusal": f.refusal.name if f.refusal else None,
            TOTAL: decline_total(
                "These are eleven different quantities in eight different units. "
                "Nothing here sums to anything."
            ),
        },
    )

    if not f.applicable:
        return ReportResult(
            report_id="joback_properties",
            name="Thermophysical Properties (Joback)",
            category="thermophysical",
            molecule_uuid=molecule_uuid,
            cache_state=CacheState.FAILED,
            error=refusal_text(f),
            provenance=provenance,
        )

    facts: list[Fact] = []
    declined: list[str] = []

    def add(label: str, key: str, units: str, value: float | None, *,
            evidence: tuple[str, ...] = (), limitations: tuple[str, ...] = ()) -> None:
        if value is None:
            declined.append(f"{label} ({', '.join(f.groups_without(_COLUMN[key]))} has no contribution)")
            return
        error = PAPER_ABSOLUTE_ERROR.get(key)
        lim = list(limitations)
        if error:
            lim.append(
                f"The paper's own average absolute error for this property is "
                f"{error[0]} {error[1]}, over its regression set."
            )
        facts.append(Fact(
            category=FactCategory.STRUCTURE,
            label=label,
            value=value,
            display_value=_display(value, places),
            units=units,
            source="joback_properties",
            # HEURISTIC and not DETERMINISTIC: the group SUM is deterministic
            # given the table, but the number it estimates is a regression
            # fitted to a few hundred compounds, which is a different claim.
            basis=Basis.HEURISTIC,
            evidence=evidence,
            limitations=tuple(lim),
        ))

    # Tc first, because it is the one that takes an input and the one whose
    # accuracy depends on it.
    tc = critical_temperature(f, experimental_tb)
    add("Critical temperature", "Tc", "K", tc,
        evidence=(
            "Eq. (4), from "
            + ("the experimental boiling point supplied." if experimental_tb
               else "the ESTIMATED boiling point, no experimental value supplied."),
        ),
        limitations=() if experimental_tb else (
            "ESTIMATED Tb WAS USED. The paper prefers an experimental one and warns "
            "that 'large errors were found when using the estimated value of Tb'. "
            "Measured over 34 of Lange's critical-property entries, estimating Tb "
            "takes this property's error from the paper's 4.8 K to about 20 K, and "
            "the whole difference is Tb propagating through Eq. (4).",
        ))

    for label, key, units, accessor in _SCALAR_FACTS:
        extra: tuple[str, ...] = ()
        if key in ("Tb", "Tf"):
            extra = (
                "The paper calls its boiling and freezing point estimates 'not "
                "accurate' and 'only very approximate', and notes that freezing "
                "point depends strongly on conformation -- it does not distinguish "
                "cis from trans.",
            )
        add(label, key, units, globals()[accessor](f), limitations=extra)

    cp = heat_capacity(f, temperature)
    add(f"Ideal-gas heat capacity at {temperature:g} K", "Cp", "J/mol/K", cp,
        limitations=() if CP_RANGE_K[0] <= temperature <= CP_RANGE_K[1] else (
            f"{temperature:g} K is outside the paper's stated range of "
            f"{CP_RANGE_K[0]:g}-{CP_RANGE_K[1]:g} K.",
        ))

    eta = liquid_viscosity(f, temperature)
    add(f"Liquid viscosity at {temperature:g} K", "eta_L", "N s/m2", eta,
        limitations=(
            "Valid from the freezing point to a reduced temperature of about 0.7 "
            "(the paper, p238). Nothing here checks that bound for you.",
        ))

    decomposition = ", ".join(f"{n}x {g}" for g, n in sorted(f.counts.items()))
    facts.append(Fact(
        category=FactCategory.STRUCTURE,
        label="Group decomposition",
        value=decomposition,
        display_value=decomposition,
        source="joback_properties",
        basis=Basis.DETERMINISTIC,
        evidence=(
            f"{f.n_atoms} atoms in total, hydrogens included -- which is what "
            "Eq. (5) uses for the critical pressure.",
        ),
    ))

    limitations = [
        "Group contribution, not measurement. Joback has no way to tell "
        "structural isomers apart when they share a group count -- the paper says "
        "so of cis and trans explicitly.",
    ]
    if declined:
        limitations.append(
            "Joback's table prints no contribution for: " + "; ".join(declined)
            + ". A dash there means absent, not zero, so those are withheld rather "
            "than summed as nothing."
        )

    return ReportResult(
        report_id="joback_properties",
        name="Thermophysical Properties (Joback)",
        category="thermophysical",
        molecule_uuid=molecule_uuid,
        facts=tuple(facts),
        limitations=tuple(limitations),
        provenance=provenance,
    )


#: Property key -> the Table III column it sums, for the withheld message.
_COLUMN = {
    "Tb": "tb", "Tf": "tf", "Tc": "tc", "Pc": "pc", "Vc": "vc",
    "Hform": "hform", "Gform": "gform", "Hvap": "hvap", "Hfus": "hfus",
    "Cp": "a", "eta_L": "eta_a",
}
