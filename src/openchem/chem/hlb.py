"""Griffin's hydrophile-lipophile balance, and where it means anything.

**"HLB" NAMES TWO MUTUALLY INCOMPATIBLE QUANTITIES, and that is why this
module answers under one name only.** Schott's commentary
([source:schott1989]) works the disagreement out arithmetically: for
surfactants whose sole hydrophilic moiety is polyoxyethylene -- over 73%
of US nonionic surfactant production -- the Davies scale "differs
substantially from the Griffin scale in the entire range of practical
applications", and "since the Griffin scale has been validated by
extensive experiments, the Davies scale is unsuitable for most nonionic
surfactants". Two scales, one informal name, and a number reported as
bare "HLB" would be ambiguous between them.

So this computes GRIFFIN HLB, says so in the result, and does not offer
Davies. That is the same call `topology_analysis` makes about the
several quantities sharing the name "steric index".

WHY IT WAS DEFERRED, AND WHAT CHANGED. `docs/VALIDATION.md` recorded "No
formulas published, no worked example, and the reference implementation's
default is a proprietary consensus method. Nothing to check a result
against." Three of those four clauses are answered by Schott, which
prints both formulas and worked constants. The fourth still stands and is
not chased: ChemAxon's default is a proprietary consensus method, so
agreeing with Marvin here is not reachable, and this reports what Griffin
defines rather than being tuned toward another tool -- the same call
`bbb_stereo` makes about its pKa disagreement.

THE DEFINITION, from Schott Eq. [1]:

    HLB_G = E / 5          E = weight percentage ethylene oxide

which is `20 * (mass of the polyoxyethylene) / (total mass)`.

THE ORACLE IS SCHOTT'S OWN CLOSED FORM, Eq. [2], not a table of
manufacturer values:

    HLB_G = 881 p / (44.05 p + A)

for p ethylene oxide units on a lipophile of mass A -- 206.3 for
octylphenol (Triton X), 186.3 for dodecanol (Brij). 881 is 20 x 44.05,
which is the same statement as Eq. [1] specialised to one chain.

**GUO 2006 IS NOT THE ORACLE, and the reason is worth stating because it
looks like one.** That paper tabulates 224 nonionic surfactants and was
the obvious acceptance set -- but it mentions Griffin ZERO times, and its
`HLB^a` column is manufacturer data: its own footnotes read "obtained
from the data reported by BASF Corp." and "by ICI Americas Inc.". Scoring
a Griffin implementation against it would compare one scale with another
and manufacture a disagreement that reads as a bug. Guo is cited here for
the Davies/ECL comparison and nothing else.

APPLICABILITY IS A RESULT, NOT A FOOTNOTE. Griffin's definition opens
"for nonionic surfactants **with polyoxyethylene as the sole hydrophilic
moiety**", so that is a structural condition rather than an editorial
caveat, and it is answered per molecule. Returning 4.14 for aspirin and
relying on documentation to say it is meaningless is the failure the
`AlertResult` migration spent a whole phase removing.

Sorbitan esters -- Span and Tween -- are OUTSIDE it, which is the case
most likely to be got wrong: Griffin's *experiments* produced their
published values, but sorbitan is a polyhydric alcohol, so Griffin's
*formula* does not apply to them. Schott says as much: Davies' group
values "were calculated exclusively from Griffin's experimental HLB
values for sorbitan esters and polysorbates... None of the surfactants
employed in the calculations had polyoxyethylene as the sole hydrophilic
moiety."
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from rdkit import Chem
from rdkit.Chem import Descriptors

from openchem.domain.common import TOTAL, CacheState, Provenance, decline_total
from openchem.domain.report import Fact, FactCategory, ReportResult
from openchem.domain.structure_issue import Basis

#: DECLARED USER-FACING. `tests/test_calculator_reachability.py` fails if
#: nothing a user can press reaches this module -- which it did not for the
#: whole of PR #41, when Griffin HLB shipped correct, guarded, sourced and
#: unreachable.
USER_FACING_PROVIDER = "Griffin HLB, through the 'HLB (Griffin)' calculator"

#: Molecular mass of one ethylene oxide repeat unit, -CH2CH2O-.
#:
#: Schott writes 44.05 in Eq. [2]; RDKit's own periodic table gives
#: 44.0526 for C2H4O. The difference is below the precision anything here
#: reports, and the paper's value is used so the closed form reproduces
#: exactly rather than to four decimals of something else.
EO_UNIT_MASS = 44.05

#: Griffin's divisor: HLB is a twentieth of the hydrophilic mass
#: fraction, i.e. weight-percent EO over five.
_GRIFFIN_SCALE = 20.0

#: One ethylene oxide unit: an ETHER oxygen, a -CH2CH2-, and the next
#: oxygen along. `-(O-CH2-CH2)p-OH` gives exactly p matches.
#:
#: **THREE THINGS HERE WERE WRONG IN THE FIRST VERSION**, and all three
#: were found by checking against Schott's closed form rather than by
#: reading the pattern:
#:
#:   * `[O][CH2][CH2]` matches a POE chain from BOTH ends, so every
#:     internal oxygen counted twice -- a C12E4 came out as 9 units;
#:   * it also matched the chain's own terminal hydroxyl, so plain
#:     DODECANOL, which has no polyoxyethylene at all, was accepted as a
#:     surfactant and given a number;
#:   * closing on the next oxygen is what makes the count a count of
#:     UNITS rather than of oxygens.
#:
#: `H0` on the leading oxygen is what excludes the hydroxyl end; the
#: trailing oxygen is deliberately unconstrained, because the last unit
#: of an ordinary POE chain closes on exactly that -OH. `uniquify` folds
#: the reverse match, which covers the same four atoms.
_EO_UNIT = Chem.MolFromSmarts("[OX2;H0;!$(O=*)]-[CH2]-[CH2]-[OX2]")


class HlbRefusal(Enum):
    """Why Griffin's HLB does not apply to this structure.

    A VALUE rather than a message, so no consumer starts matching on
    prose -- the shape `BcsReason` and `IsotopeRefusal` already use.
    """

    NO_POLYOXYETHYLENE = "no polyoxyethylene chain"
    NOT_SOLE_HYDROPHILE = "another hydrophilic moiety is present"
    NOT_A_STRUCTURE = "the structure could not be read"


#: Groups that make polyoxyethylene NOT the sole hydrophilic moiety.
#:
#: Deliberately a REFUSAL list rather than an acceptance one: the
#: condition Griffin states is about what else is present, so enumerating
#: what is allowed would silently accept the next hydrophile nobody
#: thought of. Each entry names what it excludes.
_OTHER_HYDROPHILES = (
    ("a formal charge", Chem.MolFromSmarts("[+1,+2,+3,-1,-2,-3]")),
    ("an amine", Chem.MolFromSmarts("[NX3;!$(N-C=O);!$(N=*)]")),
    ("an amide", Chem.MolFromSmarts("[NX3][CX3]=[OX1]")),
    ("a carboxylic acid", Chem.MolFromSmarts("[CX3](=O)[OX2H1]")),
    ("a sulfur oxyacid or its salt", Chem.MolFromSmarts("[#16X4](=O)(=O)[OX2,OX1-]")),
    ("a phosphorus oxyacid or its salt", Chem.MolFromSmarts("[#15](=O)([OX2,OX1-])[OX2,OX1-]")),
    # A ring carrying a hydroxyl is the sorbitan/sugar case, which is
    # exactly what puts Span and Tween outside Griffin's formula.
    ("a hydroxylated ring (a polyhydric alcohol)", Chem.MolFromSmarts("[C;R][OX2H1]")),
)


@dataclass(frozen=True)
class GriffinHlb:
    """Griffin's HLB for one structure, or why it does not apply.

    `value` is None exactly when `refusal` is set. A consumer that reads
    the number without checking is the failure this shape prevents.
    """

    value: float | None
    refusal: HlbRefusal | None
    #: Ethylene oxide units counted, for a reader checking the arithmetic.
    ethylene_oxide_units: int
    #: What else was found, when that is why it was refused.
    detail: str = ""

    @property
    def applicable(self) -> bool:
        return self.refusal is None


def _other_hydrophile(mol: Chem.Mol) -> str:
    """The first disqualifying group found, or "".

    Hydroxyls are handled separately: a polyoxyethylene chain ordinarily
    ENDS in one, so a single acyclic -OH is part of the hydrophile
    Griffin is describing rather than a second one. Two or more is a
    polyol.
    """
    for description, pattern in _OTHER_HYDROPHILES:
        if pattern is not None and mol.HasSubstructMatch(pattern):
            return description
    hydroxyls = mol.GetSubstructMatches(Chem.MolFromSmarts("[OX2H1]"))
    if len(hydroxyls) > 1:
        return f"{len(hydroxyls)} hydroxyls (a polyol)"
    return ""


def griffin_hlb(mol: Chem.Mol | None) -> GriffinHlb:
    """Griffin's HLB, or a named refusal.

    Counts ethylene oxide units by substructure and takes their mass as a
    fraction of the whole, which is Eq. [1] stated per molecule. The count
    is of NON-OVERLAPPING matches, because a run of `-OCH2CH2OCH2CH2-`
    would otherwise be counted once per starting oxygen.
    """
    if mol is None:
        return GriffinHlb(None, HlbRefusal.NOT_A_STRUCTURE, 0)

    units = len(mol.GetSubstructMatches(_EO_UNIT, uniquify=True, maxMatches=10_000))
    if not units:
        return GriffinHlb(None, HlbRefusal.NO_POLYOXYETHYLENE, 0)

    other = _other_hydrophile(mol)
    if other:
        return GriffinHlb(None, HlbRefusal.NOT_SOLE_HYDROPHILE, units, other)

    mass = Descriptors.MolWt(mol)
    if mass <= 0:  # pragma: no cover - a structure with no atoms
        return GriffinHlb(None, HlbRefusal.NOT_A_STRUCTURE, units)
    return GriffinHlb(_GRIFFIN_SCALE * units * EO_UNIT_MASS / mass, None, units)


def griffin_hlb_from_chain(units: int, lipophile_mass: float) -> float:
    """Schott Eq. [2], as a pure function: `881 p / (44.05 p + A)`.

    The ACCEPTANCE ORACLE. It reaches the answer a different way from
    `griffin_hlb` -- p and A rather than substructure counting and a
    molecular weight -- so agreement between them is a real check.

    **THE INDEPENDENCE IS PARTIAL, AND SAYING SO IS THE POINT.** Both
    routes read `_GRIFFIN_SCALE` and `EO_UNIT_MASS`, so a mutation of
    either moves them together and the comparison cannot see it --
    measured: setting the scale to 100 leaves every closed-form
    comparison passing. What anchors those two constants to the paper is
    `test_the_closed_form_is_griffins_definition_and_not_a_second_one`,
    which pins `20 x 44.05 == 881` against the number Schott prints. It is also the form Schott
    prints worked constants for, which is what makes it checkable at all:
    A = 206.3 for octylphenol, 186.3 for dodecanol.
    """
    return _GRIFFIN_SCALE * EO_UNIT_MASS * units / (EO_UNIT_MASS * units + lipophile_mass)


# ---------------------------------------------------------------------------
# The calculator, and the refusal AS the result
# ---------------------------------------------------------------------------

#: What each refusal means, in the words a user reads.
#:
#: **GENERATED FROM THE ENUM, NEVER WRITTEN AT THE PANEL.** `IsotopeRefusal`
#: is the precedent and its docstring gives the reason: a value rather than
#: a sentence, "so `if "isomer" in message` never becomes application
#: logic". A panel that invented its own prose for `NOT_SOLE_HYDROPHILE`
#: would give two wordings for one refusal, they would drift, and the help
#: layer would have nothing to attach to.
_REFUSAL_TEXT: dict[HlbRefusal, str] = {
    HlbRefusal.NO_POLYOXYETHYLENE: (
        "Griffin's HLB is defined for nonionic surfactants with polyoxyethylene as "
        "the sole hydrophilic moiety, and this structure has no polyoxyethylene "
        "chain. A number computed anyway would be an ethylene-oxide weight fraction "
        "of zero wearing a surfactant's name."
    ),
    HlbRefusal.NOT_SOLE_HYDROPHILE: (
        "Griffin's HLB requires polyoxyethylene to be the SOLE hydrophilic moiety, "
        "and this structure carries {detail} as well. Griffin's experiments produced "
        "the published values for Span and Tween, but his FORMULA does not apply to "
        "them -- sorbitan is a polyhydric alcohol."
    ),
    HlbRefusal.NOT_A_STRUCTURE: "The structure could not be read.",
}


def refusal_text(result: GriffinHlb) -> str:
    """The one place a refusal becomes prose.

    Every consumer goes through here, so a reader cannot be given two
    different explanations of one refusal.
    """
    if result.refusal is None:  # pragma: no cover - callers check first
        return ""
    return _REFUSAL_TEXT[result.refusal].format(detail=result.detail or "another hydrophile")


def compute_griffin_hlb(
    mol: Chem.Mol, molecule_uuid: str, parameters: dict[str, Any] | None = None
) -> ReportResult:
    """Griffin's HLB, or a named refusal, as the "surface" category's HLB.

    **THE REFUSAL IS THE RESULT.** Returning 4.14 for aspirin and relying
    on documentation to say it is meaningless is the failure the
    `AlertResult` migration spent a phase removing, and Griffin's own
    definition makes applicability a structural question rather than an
    editorial one.
    """
    parameters = parameters or {}
    places = int(parameters.get("decimal_places", 2))
    result = griffin_hlb(mol)

    provenance = Provenance(
        created_by="core",
        method="griffin",
        parameters={
            "decimal_places": places,
            "ethylene_oxide_units": result.ethylene_oxide_units,
            "refusal": result.refusal.name if result.refusal else None,
            TOTAL: decline_total(
                "HLB is a whole-molecule weight ratio, not a sum over atoms."
            ),
        },
    )

    if not result.applicable:
        return ReportResult(
            report_id="griffin_hlb",
            name="HLB (Griffin)",
            category="surface",
            molecule_uuid=molecule_uuid,
            cache_state=CacheState.FAILED,
            error=refusal_text(result),
            provenance=provenance,
        )

    value = result.value or 0.0
    facts = (
        Fact(
            category=FactCategory.STRUCTURE,
            label="HLB (Griffin)",
            value=value,
            display_value=f"{value:.{places}f}",
            source="griffin_hlb",
            basis=Basis.DETERMINISTIC,
            evidence=(
                "E / 5, where E is the weight percentage of ethylene oxide -- "
                "Griffin's own definition, as Schott states it in Eq. [1].",
            ),
            limitations=(
                "GRIFFIN, NOT DAVIES. The two scales share the name and disagree "
                "substantially across the whole range of practical applications, so a "
                "number reported as bare 'HLB' is ambiguous between them.",
                "Marvin's default is a proprietary consensus method and will not "
                "agree with this.",
            ),
        ),
        Fact(
            category=FactCategory.STRUCTURE,
            label="Ethylene oxide units",
            value=result.ethylene_oxide_units,
            display_value=str(result.ethylene_oxide_units),
            source="griffin_hlb",
            basis=Basis.DETERMINISTIC,
            evidence=("Non-overlapping -O-CH2-CH2-O- substructure matches.",),
        ),
    )

    return ReportResult(
        report_id="griffin_hlb",
        name="HLB (Griffin)",
        category="surface",
        molecule_uuid=molecule_uuid,
        facts=facts,
        limitations=("Griffin's scale, not Davies'. The two are not interchangeable.",),
        provenance=provenance,
    )
