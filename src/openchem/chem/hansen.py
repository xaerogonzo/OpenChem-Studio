"""Hansen solubility parameters by Stefanis & Panayiotou group contribution.

`[source:stefanis2008]` -- *Int J Thermophys* (2008) **29**:568-585.

    delta_d  = sum(Ni*Ci) + W*sum(Mj*Dj) + 17.3231     Eq. 24
    delta_p  = sum(Ni*Ci) + W*sum(Mj*Dj) +  7.3548     Eq. 25
    delta_hb = sum(Ni*Ci) + W*sum(Mj*Dj) +  7.9793     Eq. 26
    delta_t  = sqrt(delta_d^2 + delta_p^2 + delta_hb^2)  Eq. 4

all in (MPa)^0.5. The table is `data/hansen_groups.json`; how it was
transcribed and the six hazards in doing so are in
`tools/build_hansen_tables.py`.

**TWO PASSES WITH DIFFERENT RULES, WHICH IS THE WHOLE DESIGN.** First-order
groups (UNIFAC groups) partition the molecule exactly as Joback's do, so they
go through `claim_groups`. Second-order groups are conjugation corrections
and are built FROM adjacent first-order groups -- the paper's principle (ii),
p573 -- so they OVERLAP what the first pass already claimed and go through
`count_overlapping`, claiming nothing. Running them through the claim rule
would match almost nothing, raise no error, and return a plausible number for
a molecule whose corrections were all silently dropped.

**W IS A SWITCH, NOT A TIER.** Eq. 23 defines it as 0 for a compound with no
second-order groups and 1 for one with any, so a first-order-only answer IS
the method rather than a degraded fallback. There is no "second-order
correction unavailable" refusal, and the result still records which happened,
because a reader cannot otherwise tell a compound the corrections did not
apply to from one where they did nothing.

**THE FIRST-ORDER SPEC IS DELIBERATELY INCOMPLETE, AND THAT IS FAIL-CLOSED.**
The paper tabulates 76 first-order groups; every one this module cannot
express as a SMARTS is simply absent from `_FIRST_ORDER_SPEC`, so a molecule
needing it hits `UNCOVERED_ATOM` and is REFUSED. An unexpressed group can
therefore cost coverage and can never cost correctness -- the alternative,
approximating it with a near-miss pattern, returns a confident wrong number.
`tests/test_hansen_fragmenter.py` records which groups are covered.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
from pathlib import Path

from rdkit import Chem
from rdkit.Chem import Descriptors

from openchem.domain.common import TOTAL, CacheState, Provenance, decline_total
from openchem.domain.report import Fact, FactCategory, ReportResult
from openchem.domain.structure_issue import Basis
from openchem.chem.group_contribution import (
    build_patterns,
    claim_groups,
    count_overlapping,
    describe_uncovered,
)

_TABLE_PATH = Path(__file__).parent / "data" / "hansen_groups.json"

PARAMETERS = ("d", "p", "hb")

#: p574. Stated as a limit of the model, so it is a refusal rather than a note.
MINIMUM_CARBONS = 3


class HansenRefusal(Enum):
    """Why this method does not apply to this structure.

    A VALUE rather than a message, the shape `JobackRefusal`, `HlbRefusal`
    and `IsotopeRefusal` already use.
    """

    NOT_A_STRUCTURE = "the structure could not be read"
    NOT_A_PURE_COMPONENT = "more than one disconnected fragment"
    CHARGED = "the structure carries a net formal charge"
    NO_HEAVY_ATOMS = "the structure has no heavy atoms"
    UNCOVERED_ATOM = "an atom belongs to no Stefanis-Panayiotou group"
    TOO_FEW_CARBONS = "the model needs three or more carbons"
    NO_CONTRIBUTION = "a group in this molecule has no contribution for that parameter"


@lru_cache(maxsize=1)
def _table() -> dict:
    return json.loads(_TABLE_PATH.read_text(encoding="utf-8"))


def first_order_groups() -> dict:
    return _table()["first_order"]


def second_order_groups() -> dict:
    return _table()["second_order"]


def constants() -> dict:
    return _table()["_constants"]


# ---------------------------------------------------------------------------
# The patterns
# ---------------------------------------------------------------------------
#
# `[#6]` rather than `C` throughout: SMARTS' uppercase organic symbols match
# ALIPHATIC atoms only, so a pattern written `C` silently misses every
# aromatic carbon. Joback's spec records the same trap.
#
# Keys are the table's own canonical form -- dashes folded to ASCII, case
# folded -- because the paper spells the same group three different ways
# across its four tables. `_key` is the one place that knows.

#: AND THE TRIPLE BOND IS U+2261 IDENTICAL TO, not an ASCII `#`. The table
#: keys the two alkynes `ch≡c-` and `c≡c`, so a spec written with the SMARTS
#: character silently names a group that does not exist -- which
#: `build_patterns` catches at import, by design, rather than at match time.
_DASHES = "-‐‑‒–—−"


def _key(name: str) -> str:
    folded = "".join("-" if ch in _DASHES else ch for ch in name)
    return " ".join(folded.split()).casefold()


#: Heavy atoms each group claims. Anything absent claims one. The invariant
#: in `build_patterns` checks every entry against its SMARTS at import.
FIRST_ORDER_ATOM_COUNT = {
    _key("CH3CO"): 3, _key("CH2CO"): 3, _key("CHO (aldehydes)"): 2,
    _key("COOH"): 3, _key("CH3COO"): 4, _key("CH2COO"): 4,
    _key("HCOO"): 3, _key("COO"): 3,
    _key("CONH2"): 3, _key("CON(CH3)2"): 5,
    _key("ACOH"): 2, _key("ACNH2"): 2, _key("ACCH3"): 2, _key("ACCH2-"): 2,
    _key("ACCl"): 2, _key("ACF"): 2, _key("ACNO2"): 4,
    _key("CH3O"): 2, _key("CH2O"): 2, _key("CHO (ethers)"): 2,
    _key("CH2O (cyclic)"): 2,
    _key("CH2NH2"): 2, _key("CHNH2"): 2, _key("CH3NH"): 2, _key("CH2NH"): 2,
    _key("CH3N"): 2, _key("CH2N"): 2,
    _key("CH2SH"): 2, _key("CH3S"): 2, _key("CH2S"): 2,
    _key("CH2Cl"): 2, _key("CHCl"): 2, _key("CCl"): 2,
    _key("CHCl2"): 3, _key("CCl2"): 3, _key("CCl3"): 4,
    _key("CF"): 2, _key("CF2"): 3, _key("CF3"): 4,
    _key("CH2NO2"): 4, _key("CHNO2"): 4, _key("CH2CN"): 3,
    _key("CH2=CH-"): 2, _key("-CH=CH-"): 2, _key("CH2=C<"): 2,
    _key("-CH=C<"): 2, _key(">C=C<"): 2,
    _key("CH2=C=CH-"): 3, _key("CH2=C=C<"): 3,
    _key("CH≡C-"): 2, _key("C≡C"): 2,
    _key(">C=N-"): 2, _key("-CH=N-"): 2,
    _key("O=C=N-"): 3, _key("SO2"): 3, _key(">C=S"): 2,
    _key(">C=O (except as above)"): 2,
    _key("CN (except as above)"): 2,
    _key("C2H5O2"): 4,
}

#: (group id, SMARTS, why) in PRIORITY ORDER -- most specific first, because
#: `claim_groups` skips a match touching an already-claimed atom.
_FIRST_ORDER_SPEC: tuple[tuple[str, str, str], ...] = (
    # --- the 2-methoxyethanol group, before the OH and ether it contains ---
    # `C2H5O2` is -O-CH2-CH2-OH: two carbons, the ether oxygen and the
    # hydroxyl. Four heavy atoms, and it must outrank OH/CH2O or it is never
    # seen -- the paper's example is 2-methoxyethanol, which would otherwise
    # decompose as CH3O + 2 CH2 + OH.
    (_key("C2H5O2"), "[OX2H0][CH2][CH2][OX2H1]", "the 2-methoxyethanol group"),
    # --- amides, before the carbonyl and the amine they contain -----------
    (_key("CON(CH3)2"), "[CX3](=O)[NX3]([CH3])[CH3]",
     "N,N-dimethylamide: the whole group including both methyls"),
    (_key("CONH2"), "[CX3](=O)[NX3H2]", "primary amide"),
    # --- acids and esters, before ketone and ether ------------------------
    (_key("COOH"), "[CX3](=O)[OX2H1]", "carboxylic acid"),
    (_key("CH3COO"), "[CH3][CX3](=O)[OX2H0]", "acetate ester, methyl included"),
    (_key("CH2COO"), "[CH2][CX3](=O)[OX2H0]", "propionate-type ester"),
    (_key("HCOO"), "[CX3H1](=O)[OX2H0]", "formate ester"),
    (_key("COO"), "[CX3](=O)[OX2H0]", "any remaining ester carbonyl"),
    # --- isocyanate before the nitrile and the carbonyl -------------------
    (_key("O=C=N-"), "[OX1]=[CX2]=[NX2]", "isocyanate"),
    # --- ketones and aldehydes --------------------------------------------
    # THE ALDEHYDE GOES FIRST, AND THE KETONES REQUIRE H0 ON THE CARBONYL.
    # Written the obvious way -- `[CH3][CX3](=O)` and `[CH2][CX3](=O)` -- the
    # ketone groups also match the carbon alpha to an ALDEHYDE, because an
    # aldehyde carbonyl is a CX3 too. Measured: 1-hexanal came out
    # 1 CH3 + 3 CH2 + 1 CH2CO instead of 1 CH3 + 4 CH2 + 1 CHO, and its three
    # parameters were wrong by 1.08, 0.56 and 0.29 -- a plausible answer for
    # the wrong decomposition, which is exactly what the paper's own worked
    # example exists to catch.
    (_key("CHO (aldehydes)"), "[CX3H1]=O", "aldehyde"),
    (_key("CH3CO"), "[CH3][CX3H0](=O)", "acetyl: the carbonyl is a ketone"),
    (_key("CH2CO"), "[CH2][CX3H0](=O)", "the CH2 alpha to a KETONE, with it"),
    # --- nitro, in both the hypervalent and charge-separated forms --------
    (_key("ACNO2"), "c[NX3](=O)=O", "nitro on an aromatic ring"),
    (_key("ACNO2"), "c[NX3+](=O)[O-]", "the charge-separated aromatic nitro"),
    (_key("CH2NO2"), "[CH2][NX3](=O)=O", "nitro on a CH2"),
    (_key("CH2NO2"), "[CH2][NX3+](=O)[O-]", "charge-separated, on a CH2"),
    (_key("CHNO2"), "[CH1][NX3](=O)=O", "nitro on a CH"),
    (_key("CHNO2"), "[CH1][NX3+](=O)[O-]", "charge-separated, on a CH"),
    # --- nitrile -----------------------------------------------------------
    (_key("CH2CN"), "[CH2]C#N", "the CH2 bearing a nitrile, with it"),
    # --- aromatic substituents, before the bare aromatic carbon -----------
    (_key("ACOH"), "c[OX2H1]", "phenol: the ring carbon and its OH oxygen"),
    (_key("ACNH2"), "c[NX3H2]", "aniline nitrogen with its ring carbon"),
    (_key("ACCH3"), "c[CH3]", "toluene methyl with its ring carbon"),
    (_key("ACCH2-"), "c[CH2]", "a benzylic CH2 with its ring carbon"),
    (_key("ACCl"), "c[Cl]", "aryl chloride"),
    (_key("ACF"), "c[F]", "aryl fluoride"),
    # --- halogen clusters, most substituted first -------------------------
    (_key("CF3"), "[CX4]([F])([F])[F]", "trifluoromethyl"),
    (_key("CCl3"), "[CX4]([Cl])([Cl])[Cl]", "trichloromethyl"),
    (_key("CF2"), "[CX4]([F])[F]", "difluoro carbon"),
    (_key("CHCl2"), "[CX4H1]([Cl])[Cl]", "dichloro CH"),
    (_key("CCl2"), "[CX4H0]([Cl])[Cl]", "dichloro C"),
    (_key("CH2Cl"), "[CX4H2][Cl]", "chloromethylene"),
    (_key("CHCl"), "[CX4H1][Cl]", "chloro CH"),
    (_key("CCl"), "[CX4H0][Cl]", "chloro C"),
    (_key("CF"), "[CX4][F]", "monofluoro carbon"),
    # --- sulfur -----------------------------------------------------------
    (_key("SO2"), "[SX4](=O)=O", "sulfone"),
    (_key(">C=S"), "[CX3]=[SX1]", "thiocarbonyl"),
    (_key("CH2SH"), "[CH2][SX2H1]", "thiol on a CH2, with it"),
    (_key("CH3S"), "[CH3][SX2H0]", "methyl sulfide"),
    (_key("CH2S"), "[CH2][SX2H0]", "methylene sulfide"),
    # --- amines, most substituted first -----------------------------------
    (_key("CH2NH2"), "[CH2][NX3H2]", "primary amine on a CH2"),
    (_key("CHNH2"), "[CX4H1][NX3H2]", "primary amine on a CH"),
    (_key("CH3NH"), "[CH3][NX3H1]", "secondary amine, methyl side"),
    (_key("CH2NH"), "[CH2][NX3H1]", "secondary amine, methylene side"),
    (_key("CH3N"), "[CH3][NX3H0]", "tertiary amine, methyl side"),
    (_key("CH2N"), "[CH2][NX3H0]", "tertiary amine, methylene side"),
    # --- imines ------------------------------------------------------------
    (_key(">C=N-"), "[CX3H0]=[NX2]", "ketimine / aromatic ring nitrogen pair"),
    (_key("-CH=N-"), "[CX3H1]=[NX2]", "aldimine"),
    # --- alcohols and ethers ----------------------------------------------
    (_key("OH"), "[OX2H1]", "aliphatic hydroxyl"),
    (_key("CH2O (cyclic)"), "[CH2;R][OX2;R]", "an ether oxygen inside a ring"),
    (_key("CH3O"), "[CH3][OX2H0]", "methyl ether"),
    (_key("CH2O"), "[CH2][OX2H0]", "methylene ether"),
    (_key("CHO (ethers)"), "[CX4H1][OX2H0]", "methine ether"),
    # --- unsaturation ------------------------------------------------------
    (_key("CH2=C=CH-"), "[CH2]=[CX2]=[CH1]", "terminal allene"),
    (_key("CH2=C=C<"), "[CH2]=[CX2]=[CX3H0]", "substituted allene"),
    (_key("CH≡C-"), "[CH1]#[CX2]", "terminal alkyne"),
    (_key("C≡C"), "[CX2H0]#[CX2H0]", "internal alkyne"),
    (_key("CH2=CH-"), "[CH2]=[CH1]", "vinyl"),
    (_key("-CH=CH-"), "[CH1]=[CH1]", "1,2-disubstituted alkene"),
    (_key("CH2=C<"), "[CH2]=[CX3H0]", "1,1-disubstituted alkene"),
    (_key("-CH=C<"), "[CH1]=[CX3H0]", "trisubstituted alkene"),
    (_key(">C=C<"), "[CX3H0]=[CX3H0]", "tetrasubstituted alkene"),
    # --- the aromatic skeleton --------------------------------------------
    (_key("ACH"), "[cH1]", "an aromatic CH"),
    (_key("AC"), "[cH0]", "an aromatic carbon bearing something else"),
    # --- the aliphatic skeleton, last of the carbons ----------------------
    (_key("-CH3"), "[CX4H3]", "methyl"),
    (_key("-CH2"), "[CX4H2]", "methylene"),
    (_key("-CH<"), "[CX4H1]", "methine"),
    (_key(">C<"), "[CX4H0]", "quaternary carbon"),
    # --- the paper's own catch-alls, explicitly last -----------------------
    (_key(">C=O (except as above)"), "[CX3]=[OX1]",
     "any carbonyl the specific groups above did not claim"),
    (_key("CN (except as above)"), "[CX2]#[NX1]", "a nitrile not on a CH2"),
    (_key("I"), "[I]", "iodine"),
    (_key("Br"), "[Br]", "bromine"),
    # A vinyl chlorine is its own group and must outrank the catch-all. The
    # recursion keeps the alkene as CONTEXT: the group is the chlorine alone,
    # so a plain `[Cl][CX3]=[CX3]` would declare three atoms for one.
    (_key("Cl-(C=C)"), "[Cl;$(Cl[CX3]=[CX3])]", "chlorine on an alkene carbon"),
    (_key("Cl (except as above)"), "[Cl]", "any remaining chlorine"),
    (_key("F (except as above)"), "[F]", "any remaining fluorine"),
    (_key("SH (except as above)"), "[SX2H1]", "any remaining thiol"),
    (_key("S (except as above)"), "[SX2H0]", "any remaining sulfur"),
    (_key("O (except as above)"), "[OX2H0]", "any remaining ether oxygen"),
    (_key("NH (except as above)"), "[NX3H1]", "any remaining secondary nitrogen"),
    (_key("N (except as above)"), "[#7X3H0]", "any remaining tertiary nitrogen"),
)

SECOND_ORDER_ATOM_COUNT = {
    _key("(CH3)2-CH-"): 3,
    _key("(CH3)3-C-"): 4,
    _key("ring of 3 carbons"): 3,
    _key("ring of 5 carbons"): 5,
    _key("ring of 6 carbons"): 6,
    _key("-C=C-C=C-"): 4,
    _key("CH3-C="): 2,
    _key("-CH2-C="): 2,
    _key(">C{H or C}-C="): 2,
    _key("CH3(CO)CH2-"): 4,
    _key("Ccyclic=O"): 2,
    _key("ACCOOH"): 4,
    _key("ACHO"): 3,
    _key(">CHOH"): 2,
    _key(">C<OH"): 2,
    _key("Ccyclic-OH"): 2,
    _key("AC-O-C"): 3,
    _key("AC-O-AC"): 3,
    _key("string in cyclic"): 2,
    _key(">C{H or C}-COOH"): 4,
    _key("CH3(CO)OC{H or C}<"): 5,
    _key("(CO)C{H2}COO"): 6,
    _key("(CO)O(CO)"): 5,
    _key("-C(OH)C(OH)-"): 4,
    _key("-C(OH)C(N)"): 4,
    _key("C-O-C=C"): 4,
    _key(">N{H or C}(in cyclic)"): 1,
    _key("-S-(in cyclic)"): 1,
    _key("ACBr"): 2,
    _key("(C=C)-Br"): 1,
    _key("ACCOO"): 4,
    _key("AC(ACHm)2AC(ACHn)2"): 6,
    _key("Ocyclic-Ccyclic=O"): 3,
    _key("CcyclicHm=Ncyclic-CcyclicHn=CcyclicHp"): 3,
    _key("NcyclicHm-Ccyclic =O"): 3,
    _key("-O-CHm-O-CHn-"): 3,
    _key("C(=O)-C-C(=O)"): 5,
}

#: The correction pass. These OVERLAP the first-order groups by construction,
#: so they never claim and their order does not matter.
#:
#: THE ALKENE CONTEXT IS A RECURSIVE `$()`, NOT A THIRD ATOM. `CH3-C=` names
#: two atoms -- a methyl and the alkene carbon it sits on -- and the carbon at
#: the FAR end of the double bond is context that identifies the group without
#: being part of it. Writing it as a plain `[CH3][CX3]=[CX3]` declares three
#: atoms for a two-atom group, which `build_patterns` refuses at import. The
#: invariant is doing here exactly what it was lifted for.
_SECOND_ORDER_SPEC: tuple[tuple[str, str, str], ...] = (
    (_key("(CH3)2-CH-"), "[CH3][CX4H1][CH3]", "isopropyl"),
    (_key("(CH3)3-C-"), "[CH3][CX4H0]([CH3])[CH3]", "tert-butyl"),
    (_key("ring of 3 carbons"), "[CX4;R]1[CX4;R][CX4;R]1", "cyclopropane"),
    (_key("ring of 5 carbons"), "[CX4;R]1[CX4;R][CX4;R][CX4;R][CX4;R]1",
     "cyclopentane"),
    (_key("ring of 6 carbons"), "[CX4;R]1[CX4;R][CX4;R][CX4;R][CX4;R][CX4;R]1",
     "cyclohexane"),
    (_key("-C=C-C=C-"), "[CX3]=[CX3][CX3]=[CX3]", "conjugated diene"),
    (_key("CH3-C="), "[CH3][$([CX3]=[CX3])]", "a methyl on an alkene carbon"),
    (_key("-CH2-C="), "[CH2][$([CX3]=[CX3])]", "a methylene on an alkene carbon"),
    (_key(">C{H or C}-C="), "[CX4H0,CX4H1][$([CX3]=[CX3])]",
     "a methine or quaternary carbon on an alkene"),
    (_key("CH3(CO)CH2-"), "[CH3][CX3](=O)[CH2]", "methyl ketone with its alpha CH2"),
    (_key("Ccyclic=O"), "[CX3;R]=[OX1]", "a carbonyl inside a ring"),
    (_key("ACCOOH"), "c[CX3](=O)[OX2H1]", "benzoic-acid carboxyl"),
    (_key("ACHO"), "c[CX3H1]=O", "aromatic aldehyde"),
    (_key(">CHOH"), "[CX4H1][OX2H1]", "a secondary alcohol"),
    (_key(">C<OH"), "[CX4H0][OX2H1]", "a tertiary alcohol"),
    (_key("Ccyclic-OH"), "[CX4;R][OX2H1]", "a hydroxyl on a ring carbon"),
    (_key("AC-O-C"), "c[OX2H0][CX4]", "an aryl alkyl ether"),
    (_key("AC-O-AC"), "c[OX2H0]c", "a diaryl ether"),
    (_key("string in cyclic"), "[CX4;!R][CX4;R]",
     "an acyclic carbon hanging off a ring -- ethylcyclohexane"),
    (_key(">C{H or C}-COOH"), "[CX4H0,CX4H1][CX3](=O)[OX2H1]",
     "a branched carbon bearing a carboxyl"),
    (_key("CH3(CO)OC{H or C}<"), "[CH3][CX3](=O)[OX2][CX4H0,CX4H1]",
     "an acetate ester of a branched alcohol"),
    (_key("(CO)C{H2}COO"), "[CX3](=O)[CH2][CX3](=O)[OX2]",
     "a beta-keto ester"),
    (_key("(CO)O(CO)"), "[CX3](=O)[OX2][CX3](=O)", "an anhydride"),
    (_key("-C(OH)C(OH)-"), "[OX2H1][CX4][CX4][OX2H1]", "a vicinal diol"),
    (_key("-C(OH)C(N)"), "[OX2H1][CX4][CX4][NX3]", "a vicinal amino alcohol"),
    (_key("C-O-C=C"), "[CX4][OX2][CX3]=[CX3]", "a vinyl ether"),
    (_key(">N{H or C}(in cyclic)"), "[NX3;R]", "a nitrogen inside a ring"),
    (_key("-S-(in cyclic)"), "[SX2;R]", "a sulfur inside a ring"),
    (_key("ACBr"), "c[Br]", "aryl bromide"),
    # The alkene is CONTEXT again: the group is the bromine alone.
    (_key("(C=C)-Br"), "[Br;$(Br[CX3]=[CX3])]", "bromine on an alkene carbon"),
    (_key("ACCOO"), "c[CX3](=O)[OX2H0]", "an aryl ester carbonyl"),
    (_key("AC(ACHm)2AC(ACHn)2"), "[cH0]([cH])([cH])[cH0]([cH])[cH]",
     "a fused aromatic pair, each fusion carbon flanked by two CH -- naphthalene"),
    (_key("Ocyclic-Ccyclic=O"), "[OX2;R][CX3;R]=[OX1]", "a lactone"),
    (_key("CcyclicHm=Ncyclic-CcyclicHn=CcyclicHp"), "[cX3][nX2][cX3]",
     "an aromatic ring nitrogen between two ring carbons -- pyridine-like"),
    (_key("NcyclicHm-Ccyclic =O"), "[NX3;R][CX3;R]=[OX1]", "a lactam"),
    # THE TRAILING CARBON IS CONTEXT, and leaving it in the pattern makes a
    # SYMMETRIC acetal match twice: `[OX2][CX4][OX2][CX4]` finds methylal
    # from both ends. The acetal carbon between two oxygens is what
    # identifies the group, and it matches once.
    (_key("-O-CHm-O-CHn-"), "[OX2][CX4][OX2]", "an acetal linkage"),
    (_key("C(=O)-C-C(=O)"), "[CX3](=O)[CX4][CX3]=O", "a 1,3-dicarbonyl"),
)


@lru_cache(maxsize=1)
def _first_order_patterns():
    return build_patterns(
        _FIRST_ORDER_SPEC, set(first_order_groups()), FIRST_ORDER_ATOM_COUNT,
        "Hansen first-order",
    )


@lru_cache(maxsize=1)
def _second_order_patterns():
    return build_patterns(
        _SECOND_ORDER_SPEC, set(second_order_groups()), SECOND_ORDER_ATOM_COUNT,
        "Hansen second-order",
    )


@dataclass(frozen=True)
class Fragmentation:
    """One molecule decomposed into Stefanis-Panayiotou groups.

    `first` is empty exactly when `refusal` is set. `second` may be empty for
    a perfectly good result -- that is W=0, which is the method rather than a
    failure, and `w` records which happened.
    """

    first: dict[str, int] = field(default_factory=dict)
    second: dict[str, int] = field(default_factory=dict)
    refusal: HansenRefusal | None = None
    detail: str = ""
    molecular_weight: float = 0.0

    @property
    def applicable(self) -> bool:
        return self.refusal is None

    @property
    def w(self) -> int:
        """Eq. 23's switch: 1 when any second-order group applies."""
        return 1 if self.second else 0


def _carbon_count(mol: Chem.Mol) -> int:
    return sum(1 for atom in mol.GetAtoms() if atom.GetAtomicNum() == 6)


def fragment(mol: Chem.Mol | None) -> Fragmentation:
    """Decompose a structure, refusing rather than approximating."""
    if mol is None or mol.GetNumAtoms() == 0:
        return Fragmentation(refusal=HansenRefusal.NOT_A_STRUCTURE)
    try:
        working = Chem.RemoveHs(Chem.Mol(mol))
    except Exception:
        return Fragmentation(refusal=HansenRefusal.NOT_A_STRUCTURE)

    if working.GetNumHeavyAtoms() == 0:
        return Fragmentation(refusal=HansenRefusal.NO_HEAVY_ATOMS)
    if len(Chem.GetMolFrags(working)) > 1:
        return Fragmentation(refusal=HansenRefusal.NOT_A_PURE_COMPONENT)
    if Chem.GetFormalCharge(working) != 0:
        return Fragmentation(refusal=HansenRefusal.CHARGED)
    if _carbon_count(working) < MINIMUM_CARBONS:
        return Fragmentation(
            refusal=HansenRefusal.TOO_FEW_CARBONS,
            detail=f"{_carbon_count(working)} carbon(s)",
        )

    walk = claim_groups(working, _first_order_patterns())
    if not walk.complete:
        return Fragmentation(
            refusal=HansenRefusal.UNCOVERED_ATOM,
            detail=describe_uncovered(working, walk.uncovered),
        )

    return Fragmentation(
        first=walk.counts,
        second=count_overlapping(working, _second_order_patterns()),
        molecular_weight=Descriptors.MolWt(working),
    )


#: The paper's own threshold: Eqs. 25 and 26 are stated valid only ABOVE
#: this, and Tables 5 and 6 exist to cover below it. In (MPa)^0.5.
LOW_DELTA_THRESHOLD = 3.0

#: Eq. 24 carries no such caveat, so delta_d has no low-range table.
LOW_DELTA_PARAMETERS = ("p", "hb")

#: Table 5 writes a bare `CHO` where Table 3 writes `CHO (aldehydes)` and
#: `CHO (ethers)`, which carry different contributions. Its low-range value
#: cannot be attributed to either without a judgement the paper does not
#: make, so a molecule containing one REFUSES the low-range branch rather
#: than picking. Recorded in the table's own `_asymmetries`.
_AMBIGUOUS_IN_LOW_TABLE = frozenset({_key("CHO (aldehydes)"), _key("CHO (ethers)")})


class ParameterBasis(Enum):
    """WHICH parameter set produced a value, as a rendered fact.

    The distinction reaches the screen rather than only the provenance: a
    main-table number and a low-range number are different estimates from
    different regressions, and this project has twice shipped a result whose
    provenance was right while the panel showed two different things as one.
    """

    MAIN = "Tables 3 and 4"
    LOW = "Tables 5 and 6, the low-range parameter set"
    UNAVAILABLE = "no contribution is published"


@dataclass(frozen=True)
class ParameterValue:
    """One Hansen parameter, with the parameter set that produced it."""

    value: float | None
    basis: ParameterBasis
    reason: str = ""


def _sum_over(f: Fragmentation, which: str, *, low: bool) -> float | None:
    table = _table()
    first = table["first_order_low" if low else "first_order"]
    second = table["second_order_low" if low else "second_order"]
    # EQS. 27 AND 28: the low range has its OWN intercepts, not Eq. 25/26's
    # and not none. The paper gives them in a sentence between two figures
    # rather than beside Tables 5 and 6, so they are easy to miss -- and
    # building the branch without them puts n-hexane's delta_p at -2.009, a
    # NEGATIVE solubility parameter. With them it is 0.737 against a
    # literature 0.0.
    total = table["_low_delta"]["constants"][which] if low else constants()[which]
    for group_id, count in f.first.items():
        row = first.get(group_id)
        if row is None or row.get(which) is None:
            return None
        total += count * row[which]
    if f.w:
        for group_id, count in f.second.items():
            row = second.get(group_id)
            if row is None or row.get(which) is None:
                return None
            total += count * row[which]
    return total


def parameter_value(f: Fragmentation, which: str) -> ParameterValue:
    """One Hansen parameter, and which of the paper's parameter sets gave it.

    A `***` in a table is ABSENCE, never zero -- so a molecule containing a
    group with no published contribution gets no number, rather than a sum
    that silently omits a term.

    **THE LOW-RANGE BRANCH IS THE PAPER'S, NOT A SAFETY NET.** Eqs. 25 and 26
    are stated valid only above 3 (MPa)^0.5, and Tables 5 and 6 carry a
    SEPARATE regression for below it. So a main-table result under the
    threshold is not a small number -- it is a number outside its own
    equation's stated range, and the honest answer comes from the other
    table. `delta_d` has no such branch because Eq. 24 carries no caveat.

    Where the low-range tables cannot answer -- a group they do not list, or
    the ambiguous bare `CHO` -- the parameter is UNAVAILABLE rather than
    silently falling back to a value the paper says is out of range.
    """
    if not f.applicable:
        return ParameterValue(None, ParameterBasis.UNAVAILABLE, "the structure was refused")

    main = _sum_over(f, which, low=False)
    if main is None:
        return ParameterValue(
            None, ParameterBasis.UNAVAILABLE,
            "a group in this molecule has no published contribution for it",
        )
    if which not in LOW_DELTA_PARAMETERS or main >= LOW_DELTA_THRESHOLD:
        return ParameterValue(main, ParameterBasis.MAIN)

    ambiguous = _AMBIGUOUS_IN_LOW_TABLE & set(f.first)
    if ambiguous:
        return ParameterValue(
            None, ParameterBasis.UNAVAILABLE,
            "below 3 MPa^0.5, where the low-range table writes a bare CHO that "
            "cannot be attributed to aldehydes or ethers",
        )
    low = _sum_over(f, which, low=True)
    if low is None:
        return ParameterValue(
            None, ParameterBasis.UNAVAILABLE,
            "below 3 MPa^0.5, and the low-range table has no contribution for "
            "a group in this molecule",
        )
    return ParameterValue(low, ParameterBasis.LOW)


def parameter(f: Fragmentation, which: str) -> float | None:
    """The bare number, for callers that do not need the basis."""
    return parameter_value(f, which).value


def total_parameter(f: Fragmentation) -> float | None:
    """Eq. 4, the Pythagorean combination -- never a plain sum."""
    parts = [parameter(f, which) for which in PARAMETERS]
    if any(part is None for part in parts):
        return None
    return math.sqrt(sum(part * part for part in parts))


def refusal_text(f: Fragmentation) -> str:
    if f.refusal is None:
        return ""
    text = f.refusal.value
    if f.detail:
        text += f" -- {f.detail}"
    return text


# ---------------------------------------------------------------------------
# The calculator
# ---------------------------------------------------------------------------

_LABELS = {
    "d": "Dispersion (delta-d)",
    "p": "Polar (delta-p)",
    "hb": "Hydrogen bonding (delta-hb)",
}

UNITS = "MPa^0.5"


def compute_hansen(
    mol: Chem.Mol | None,
    molecule_uuid: str = "",
    parameters: dict | None = None,
) -> ReportResult:
    """The three Hansen parameters and their total, or why not.

    **THE THIRD ARGUMENT IS THE REGISTRY'S PARAMETER DICT, NOT A VALUE.**
    Written as `decimal_places: int` this passes every direct-import test --
    they use the default -- and fails the moment a user presses the button,
    because `RegistryExecution` hands the whole dict across. Measured in the
    running app: `TypeError: int() argument ... not 'dict'`, with 62 unit
    tests green. Same shape as the recorded case where a registration bound
    to a shadowed two-argument function.
    """
    f = fragment(mol)
    places = max(0, min(6, int((parameters or {}).get("decimal_places", 2))))

    provenance = Provenance(
        created_by="core",
        method="stefanis_panayiotou_2008",
        parameters={
            "decimal_places": places,
            "first_order_groups": dict(sorted(f.first.items())) if f.applicable else None,
            "second_order_groups": dict(sorted(f.second.items())) if f.applicable else None,
            "W": f.w if f.applicable else None,
            "refusal": f.refusal.name if f.refusal else None,
            TOTAL: decline_total(
                "delta-t is not the sum of the three: Eq. 4 combines them in "
                "QUADRATURE, sqrt(d^2 + p^2 + hb^2). Adding them gives a larger "
                "number that means nothing, and it is reported as its own fact."
            ),
        },
    )

    if not f.applicable:
        return ReportResult(
            report_id="hansen_solubility",
            name="Hansen Solubility Parameters",
            category="solubility",
            molecule_uuid=molecule_uuid,
            cache_state=CacheState.FAILED,
            error=refusal_text(f),
            provenance=provenance,
        )

    order = (
        "first-order groups and second-order corrections (W=1)"
        if f.w
        else "first-order groups only (W=0), which is the method for a compound "
        "with no second-order groups rather than a partial answer"
    )

    facts: list[Fact] = []
    for which in PARAMETERS:
        value = parameter_value(f, which)
        if value.value is None:
            facts.append(Fact(
                category=FactCategory.STRUCTURE,
                label=_LABELS[which],
                value=None,
                display_value="not available",
                units="",
                source="hansen_solubility",
                basis=Basis.HEURISTIC,
                limitations=(value.reason,),
            ))
            continue
        facts.append(Fact(
            category=FactCategory.STRUCTURE,
            label=_LABELS[which],
            value=value.value,
            display_value=f"{value.value:.{places}f}",
            units=UNITS,
            source="hansen_solubility",
            # HEURISTIC: the group sum is deterministic given the table, but
            # the number it estimates is a regression -- the paper reports
            # r2 = 0.925 for delta_p over 350 data points.
            basis=Basis.HEURISTIC,
            evidence=(f"From {value.basis.value}, with {order}.",),
            limitations=(
                (
                    "BELOW 3 MPa^0.5 this comes from the paper's SEPARATE "
                    "low-range regression (Eqs. 27 and 28), not from Eqs. 25 "
                    "and 26 -- a different fit, not the same one extended.",
                )
                if value.basis is ParameterBasis.LOW
                else ()
            ),
        ))

    total = total_parameter(f)
    if total is not None:
        facts.append(Fact(
            category=FactCategory.STRUCTURE,
            label="Total (Hildebrand, delta-t)",
            value=total,
            display_value=f"{total:.{places}f}",
            units=UNITS,
            source="hansen_solubility",
            basis=Basis.HEURISTIC,
            evidence=("Eq. 4: the three parameters combined in quadrature.",),
            limitations=(
                "NOT the sum of the three above. Adding them gives a larger "
                "number that means nothing.",
            ),
        ))

    decomposition = ", ".join(f"{n}x {first_order_groups()[g]['printed']}"
                              for g, n in sorted(f.first.items()))
    if f.second:
        decomposition += "  |  corrections: " + ", ".join(
            f"{n}x {second_order_groups()[g]['printed']}"
            for g, n in sorted(f.second.items())
        )
    facts.append(Fact(
        category=FactCategory.STRUCTURE,
        label="Group decomposition",
        value=decomposition,
        display_value=decomposition,
        units="",
        source="hansen_solubility",
        basis=Basis.DETERMINISTIC,
        evidence=(f"W = {f.w}: {order}.",),
    ))

    return ReportResult(
        report_id="hansen_solubility",
        name="Hansen Solubility Parameters",
        category="solubility",
        molecule_uuid=molecule_uuid,
        cache_state=CacheState.COMPLETED,
        facts=tuple(facts),
        provenance=provenance,
        limitations=(
            "A GROUP-CONTRIBUTION ESTIMATE, not a measurement. The paper reports "
            "r2 = 0.925 for delta-p over 350 data points and 375 for delta-hb; "
            "errors of one to three MPa^0.5 are ordinary.",
            "The model is stated for organic compounds with three or more carbon "
            "atoms, excluding the characteristic group's own atom.",
        ),
    )
