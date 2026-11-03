"""A general first-order group fragmenter for Marrero and Gani (2001): structure -> Table 6 group counts.

`marrero2001_table.py` holds the paper's 182 first-order groups and their contributions; this module is
the other half, the part that says WHICH groups a molecule is made of. `energetics_groups.py` is the same
job for ten of the groups; this one covers all 182 (every id has a definition, `tests/test_marrero2001_groups.py`
checks that), by the paper's own rules (p. 186, "2.1 First-order groups", criteria 5 and the golden rule):

1. **A full and disjoint splitting.** Every atom of the molecule is in exactly one group. A molecule that
   cannot be split that way is REFUSED, naming the atoms no group claimed (`GroupingRefusal.uncovered`);
   a partial sum is never returned.
2. **The golden rule.** If the same fragment can be described by more than one group, the heavier group
   (the sum of the atomic weights of its atoms, hydrogens included) is chosen: 3,3-dimethyl-2-butanone is
   CH3CO + 3 CH3 + C, not CCO + 4 CH3.
3. **Two exceptions, the paper's own second and third rules.** A substituent on an aromatic carbon is
   described by a group of the form aC-R whenever one exists (acetophenone is aC-CO + 5 aCH + CH3, not
   CH3CO + aC + 5 aCH), and ureas and amides use their own functional groups even where a lighter group is
   the heavier fit (1,3-dimethylurea is NHCONH + 2 CH3, not CONHCH3 + CH3).

**How the rules are applied.** Each group is one or more SMARTS (`_SMARTS`); every place a group matches is
a candidate (group id, set of atoms). The fragmenter then finds the disjoint cover of all atoms that is best
under one ordering: the candidates' keys `(tier, weight)` (tier 2 for aC-R groups, 1 for the rest; ureas and
amides need no tier of their own, see `_tier`) are compared heaviest first, lexicographically, so a cover is better when its heaviest group
is heavier, then its next, and so on. That is the golden rule applied to the whole molecule at once, and it
does not depend on the order the atoms are written in; `tests/test_marrero2001_groups.py` checks that.
**If two different covers are equally good (a tie between groups the paper does not rank), the molecule is
refused as `ambiguous`**, with both group lists: benzanilide is the real example (aC-CONH + aC and aC-NHCO + aC
weigh the same, and the paper does not say which it means).

**What "aromatic", "cyclic" and "acyclic" mean here, because the paper never defines them** and the
molecule's own perception (RDKit's) is not the paper's:
- *Aromatic* (`aC`, `aCH`, `aN`, `aC-R`) is a six-membered ring whose atoms are all carbon or a pyridine-type
  nitrogen and none carries a double bond out of the ring. That is the paper's own reading of its examples:
  dicoumarol's pyranone ring (`CO (cyclic)`, `O (cyclic)`, `C=C (cyclic)`, fused carbons `aC fused w/ nonaromatic
  subring`) and the five-membered rings (furan's `O (cyclic)`, imidazole's `CH=N (cyclic)`, thiophene's
  `S (cyclic)`) are NOT aromatic, although RDKit calls all of them aromatic.
- *Cyclic* groups claim atoms of a ring that is not aromatic; chain groups claim atoms outside any ring. So
  a ring nitrogen is never `CH3N`, and a chain ether oxygen is never `O (cyclic)`. Where a group would need a
  ring atom to do a chain group's job (a ketone between two ring carbons, an ethylidene ring carbon) there is
  no group and the molecule is refused.

**Choices where the paper's text under-determines a group, each recorded where it is made** (search the
comment `# ASSUMPTION`): the amide, urea and hetero-substituted S/P/halogen groups' exact atom sets are read
from their symbols and sample compounds, and every one of the 182 groups is checked against its own sample
compound's printed occurrence count in the tests. Six sample compounds are named loosely in the paper
(`EXAMPLE_ASSUMPTIONS` in the tests says which and what was taken).

Not changed here: `marrero2001_table.py`'s transcription (its symbol `aC-NCO` is printed twice by the paper,
as group 76 the isocyanate and group 99 the tertiary anilide, so a symbol cannot name a group: this module's
results are keyed by group id, and `count_groups` gives the second its id in the key).
"""

from __future__ import annotations

import importlib.util
import math
import sys
from dataclasses import dataclass
from pathlib import Path

from rdkit import Chem

_HERE = Path(__file__).resolve().parent


def _load_table():
    loaded = sys.modules.get("marrero2001_table")
    if loaded is not None and hasattr(loaded, "FIRST_ORDER"):
        return loaded    # one copy of the table's exception classes, whoever loaded it first
    path = _HERE / "marrero2001_table.py"
    spec = importlib.util.spec_from_file_location("marrero2001_table", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(spec.name, module)
    spec.loader.exec_module(module)
    return module


_table = _load_table()
FIRST_ORDER = _table.FIRST_ORDER
UNIVERSAL_CONSTANTS = _table.UNIVERSAL_CONSTANTS
NoContribution = _table.NoContribution

SYMBOL: dict[int, str] = {row[0]: row[1] for row in FIRST_ORDER}
_ROW: dict[int, tuple] = {row[0]: row for row in FIRST_ORDER}
_PROPERTIES = ("Tm", "Tb", "Tc", "Pc", "Vc", "Gf", "Hf", "Hv", "Hfus")

# ---------------------------------------------------------------------------------------------------------
# SMARTS vocabulary. `X` counts every connection with hydrogens, `H` is the total hydrogen count, `R` is
# "in a ring"; the molecule these run on has had its aromaticity re-assigned to the paper's meaning
# (`_paper_view`), so `c`, `n` and `:` mean the paper's aromatic atoms and bonds.
# ---------------------------------------------------------------------------------------------------------
_ACYL = "[#6;$([#6]=[O,S,N])]"          # a carbonyl / thiocarbonyl / imine carbon
_NONACYL_C = "[#6;!$([#6]=[O,S,N])]"      # a carbon that is none of those
_NONACYL = "[!#1;!$([#6]=[O,S,N]);!$([#16]=O);!$([#15]=O)]"
_ETHER_O = f"[OX2;!R;$(O({_NONACYL_C})-{_NONACYL_C})]"
_ESTER_O = f"[OX2;!R;$(O(-[CX3]=O)-{_NONACYL_C})]"
_ACYL_C = "[CX3;H0;!R;$(C(=O)(-[#6])-[#7])]"   # amide carbon bearing a carbon
_SEC_N = f"[NX3;H1;!R;$(N(-{_NONACYL_C})-{_NONACYL_C})]"
_TERT_N = f"[NX3;H0;!R;$(N(-{_NONACYL_C})(-{_NONACYL_C})-{_NONACYL_C})]"
_O_C = "[OX2;$(O-[#6])]"
_ALK = {3: "[CX4;H3]", 2: "[CX4;H2;!R]", 1: "[CX4;H1;!R]", 0: "[CX4;H0;!R]"}


def _alk(n: int) -> str:
    return _ALK[n]


_SMARTS: dict[int, tuple[str, ...]] = {
    # --- hydrocarbons -------------------------------------------------------------------------------------
    1: (_alk(3),),
    2: (_alk(2),),
    3: (_alk(1),),
    4: (_alk(0),),
    5: ("[CX3;H2;!R]=[CX3;H1;!R]",),
    6: ("[CX3;H1;!R]=[CX3;H1;!R]",),
    7: ("[CX3;H2;!R]=[CX3;H0;!R]",),
    8: ("[CX3;H1;!R]=[CX3;H0;!R]",),
    9: ("[CX3;H0;!R]=[CX3;H0;!R]",),
    10: ("[CX3;H2;!R]=[CX2;!R]=[CX3;H1;!R]",),
    11: ("[CX3;H2;!R]=[CX2;!R]=[CX3;H0;!R]",),
    12: ("[CX3;H1;!R]=[CX2;!R]=[CX3;H1;!R]",),
    13: ("[CX2;H1;!R]#[CX2;H0;!R]",),
    14: ("[CX2;H0;!R]#[CX2;H0;!R]",),
    # --- aromatic ring atoms and aC-R ---------------------------------------------------------------------
    15: ("[cH1]",),
    16: ("[c;x3;$(c(:*)(:*):*)]",),
    17: ("[c;x3;!$(c(:*)(:*):*)]",),
    18: ("[c;H0;x2]",),
    19: ("[n]",),
    20: (f"c-{_alk(3)}",),
    21: (f"c-{_alk(2)}",),
    22: (f"c-{_alk(1)}",),
    23: (f"c-{_alk(0)}",),
    24: ("c-[CX3;H1;!R]=[CX3;H2;!R]",),
    25: ("c-[CX3;H1;!R]=[CX3;H1;!R]",),
    26: ("c-[CX3;H0;!R]=[CX3;H2;!R]",),
    27: ("c-[CX2;H0;!R]#[CX2;H1;!R]",),
    28: ("c-[CX2;H0;!R]#[CX2;H0;!R]",),
    # --- oxygen -------------------------------------------------------------------------------------------
    # OH on a non-aromatic, non-acyl carbon; a sulfonic acid's OH too (the paper's second-order group
    # aC-SO2-OH says its first-order description is aC-SO2 + OH).  # ASSUMPTION
    29: ("[OX2;H1;$(O-[#6;!c;!$(C=O)]),$([OX2;H1]-[SX4])]",),
    30: ("c-[OX2;H1]",),
    31: ("[CX3;H0;!R;$(C(-[#6])(=O)-[OX2;H1])](=O)-[OX2;H1]",),
    32: ("c-[CX3;H0;!R](=O)-[OX2;H1]",),
    # ketones: the carbonyl carbon has two carbon neighbours; the group takes the lighter-numbered one
    33: (f"{_alk(3)}-[CX3;H0;!R;$(C(=O)(-[#6])-[#6])]=O",),
    34: (f"{_alk(2)}-[CX3;H0;!R;$(C(=O)(-[#6])-[#6])]=O",),
    35: (f"{_alk(1)}-[CX3;H0;!R;$(C(=O)(-[#6])-[#6])]=O",),
    36: (f"{_alk(0)}-[CX3;H0;!R;$(C(=O)(-[#6])-[#6])]=O",),
    37: ("c-[CX3;H0;!R;$(C(=O)(-[#6])-[#6])]=O",),
    38: ("[CX3;H1;!R;$(C(-[#6])=O)]=O",),
    39: ("c-[CX3;H1;!R]=O",),
    # esters: the alkyl on the ACYL side is bundled; the alkoxy carbon is a group of its own
    40: (f"{_alk(3)}-[CX3;H0;!R](=O)-{_ESTER_O}",),
    41: (f"{_alk(2)}-[CX3;H0;!R](=O)-{_ESTER_O}",),
    42: (f"{_alk(1)}-[CX3;H0;!R](=O)-{_ESTER_O}",),
    43: (f"{_alk(0)}-[CX3;H0;!R](=O)-{_ESTER_O}",),
    44: (f"[CX3;H1;!R](=O)-{_ESTER_O}",),
    45: (f"c-[CX3;H0;!R](=O)-{_ESTER_O}",),
    46: ("c-[OX2;!R]-[CX3;H1;!R]=O",),
    47: ("c-[OX2;!R]-[CX3;H0;!R;$(C(=O)(-[#6])-[OX2])]=O",),
    48: (f"[CX3;H0;!R;$(C(=O)(-[#6])-[OX2])](=O)-{_ESTER_O}",),
    49: (f"{_alk(3)}-{_ETHER_O}",),
    50: (f"{_alk(2)}-{_ETHER_O}",),
    51: (f"{_alk(1)}-{_ETHER_O}",),
    52: (f"{_alk(0)}-{_ETHER_O}",),
    53: (f"c-{_ETHER_O}",),
    # --- nitrogen -----------------------------------------------------------------------------------------
    54: (f"{_alk(2)}-[NX3;H2]",),
    55: (f"{_alk(1)}-[NX3;H2]",),
    56: (f"{_alk(0)}-[NX3;H2]",),
    57: (f"{_alk(3)}-{_SEC_N}",),
    58: (f"{_alk(2)}-{_SEC_N}",),
    59: (f"{_alk(1)}-{_SEC_N}",),
    60: (f"{_alk(3)}-{_TERT_N}",),
    61: (f"{_alk(2)}-{_TERT_N}",),
    62: ("c-[NX3;H2]",),
    63: (f"c-[NX3;H1;!R;$(N(-{_NONACYL})-{_NONACYL})]",),
    # a nitramine's N counts (tetryl is aC-N, as `energetics_groups.py` has it)
    64: (f"c-[NX3;H0;!R;$(N(-{_NONACYL})(-{_NONACYL})-{_NONACYL})]",),
    65: ("[NX3;H2;$(N-[CX4])]",),
    66: ("[CX3;H1;!R;$(C(-[#6])=N)]=[NX2;!R]",),
    67: ("[CX3;H0;!R;$(C(-[#6])(-[#6])=N)]=[NX2;!R]",),
    68: (f"{_alk(2)}-[CX2;!R]#[NX1]",),
    69: (f"{_alk(1)}-[CX2;!R]#[NX1]",),
    70: (f"{_alk(0)}-[CX2;!R]#[NX1]",),
    71: ("c-[CX2]#[NX1]",),
    72: ("[CX2;!R]#[NX1]",),
    73: (f"{_alk(2)}-[NX2]=[CX2]=[OX1]",),
    74: (f"{_alk(1)}-[NX2]=[CX2]=[OX1]",),
    75: (f"{_alk(0)}-[NX2]=[CX2]=[OX1]",),
    76: ("c-[NX2]=[CX2]=[OX1]",),
    77: (f"{_alk(2)}-[N+](=O)[O-]",),
    78: (f"{_alk(1)}-[N+](=O)[O-]",),
    79: (f"{_alk(0)}-[N+](=O)[O-]",),
    80: ("c-[N+](=O)[O-]",),
    81: ("[N+;!$([N+]-[OX2])](=O)[O-]",),
    82: (f"{_O_C.replace('OX2', 'OX2;!R')}-[NX2]=[OX1]",),
    83: (f"{_O_C.replace('OX2', 'OX2;!R')}-[N+](=O)[O-]",),
    # --- amides and ureas ---------------------------------------------------------------------------------
    84: (f"[CX3;H1;!R](=O)-[NX3;H0;!R](-{_alk(2)})-{_alk(2)}",),
    85: (f"[CX3;H1;!R](=O)-[NX3;H1;!R]-{_alk(2)}",),
    86: (f"{_ACYL_C}(=O)-[NX3;H2]",),
    87: (f"{_ACYL_C}(=O)-[NX3;H1;!R]-{_alk(3)}",),
    88: (f"{_ACYL_C}(=O)-[NX3;H1;!R]-{_alk(2)}",),
    89: (f"{_ACYL_C}(=O)-[NX3;H0;!R](-{_alk(3)})-{_alk(3)}",),
    90: (f"{_ACYL_C}(=O)-[NX3;H0;!R](-{_alk(3)})-{_alk(2)}",),
    91: (f"{_ACYL_C}(=O)-[NX3;H0;!R](-{_alk(2)})-{_alk(2)}",),
    92: (f"{_ACYL_C}(=O)-[NX3;H1;!R]-{_ACYL_C}=O",),
    93: (f"{_ACYL_C}(=O)-[NX3;H0;!R;$(N(-[CX3]=O)(-[CX3]=O)-[#6])]-{_ACYL_C}=O",),
    94: ("c-[CX3;H0;!R](=O)-[NX3;H2]",),
    95: ("c-[NX3;H1;!R]-[CX3;H1;!R]=O",),
    96: (f"c-[NX3;H0;!R;$(N(-{_NONACYL_C})(-{_NONACYL_C})-[CX3]=O)]-[CX3;H1;!R]=O",),
    97: (f"c-[CX3;H0;!R](=O)-[NX3;H1;!R;$(N-{_NONACYL_C})]",),
    98: (f"c-[NX3;H1;!R]-{_ACYL_C}=O",),
    99: (f"c-[NX3;H0;!R;$(N(-{_NONACYL_C})(-{_NONACYL_C})-[CX3]=O)]-{_ACYL_C}=O",),
    100: ("[NX3;H1;!R]-[CX3;!R](=O)-[NX3;H1;!R]",),
    101: ("[NX3;H2]-[CX3;!R](=O)-[NX3;H1;!R]",),
    102: ("[NX3;H2]-[CX3;!R](=O)-[NX3;H0;!R]",),
    103: ("[NX3;H1;!R]-[CX3;!R](=O)-[NX3;H0;!R]",),
    104: ("[NX3;H0;!R]-[CX3;!R](=O)-[NX3;H0;!R]",),
    105: ("c-[NX3;H1;!R]-[CX3;!R](=O)-[NX3;H2]",),
    106: ("c-[NX3;H1;!R]-[CX3;!R](=O)-[NX3;H1;!R]",),
    # a secondary amide not covered by a more specific group: N-chloroacetamide is the paper's sample, so
    # the nitrogen's other substituent may be a hetero atom, which a halogen group then claims  # ASSUMPTION
    107: (f"[NX3;H1;!R]-{_ACYL_C}=O",),
    # --- halogens -----------------------------------------------------------------------------------------
    108: (f"{_alk(2)}-[Cl]",),
    109: (f"{_alk(1)}-[Cl]",),
    110: (f"{_alk(0)}-[Cl]",),
    111: (f"{_alk(1)}(-[Cl])-[Cl]",),
    112: (f"{_alk(0)}(-[Cl])-[Cl]",),
    113: (f"{_alk(0)}(-[Cl])(-[Cl])-[Cl]",),
    114: (f"{_alk(2)}-[F]",),
    115: (f"{_alk(1)}-[F]",),
    116: (f"{_alk(0)}-[F]",),
    117: (f"{_alk(1)}(-[F])-[F]",),
    118: (f"{_alk(0)}(-[F])-[F]",),
    119: (f"{_alk(0)}(-[F])(-[F])-[F]",),
    120: (f"{_alk(0)}(-[Cl])(-[Cl])-[F]",),
    121: (f"{_alk(1)}(-[Cl])-[F]",),
    122: (f"{_alk(0)}(-[Cl])(-[F])-[F]",),
    123: ("c-[Cl]",),
    124: ("c-[F]",),
    125: ("c-[I]",),
    126: ("c-[Br]",),
    127: ("[I;$(I-[#6,#7])]",),
    128: ("[Br;$(Br-[#6,#7])]",),
    129: ("[F;$(F-[#6,#7])]",),
    130: ("[Cl;$(Cl-[#6,#7])]",),
    # --- oximes, ether alcohols, hydroperoxide ------------------------------------------------------------
    131: ("[CX3;H1;!R]=[NX2;!R]-[OX2;H1]",),
    132: ("[CX3;H0;!R]=[NX2;!R]-[OX2;H1]",),
    133: ("c-[CX3;H1;!R]=[NX2;!R]-[OX2;H1]",),
    134: (f"{_ETHER_O}-{_alk(2)}-{_alk(2)}-[OX2;H1]",),
    135: (f"{_ETHER_O}-{_alk(1)}-{_alk(2)}-[OX2;H1]",),
    136: (f"{_ETHER_O}-{_alk(2)}-{_alk(1)}-[OX2;H1]",),
    137: ("[OX2;H0;!R;$(O-[#6])]-[OX2;H1]",),
    # --- sulfur -------------------------------------------------------------------------------------------
    138: (f"{_alk(2)}-[SX2;H1]",),
    139: (f"{_alk(1)}-[SX2;H1]",),
    140: (f"{_alk(0)}-[SX2;H1]",),
    141: ("c-[SX2;H1]",),
    142: ("[SX2;H1;$(S-[#6])]",),
    143: (f"{_alk(3)}-[SX2;H0;!R;$(S(-[#6])-[#6])]",),
    144: (f"{_alk(2)}-[SX2;H0;!R;$(S(-[#6])-[#6])]",),
    145: (f"{_alk(1)}-[SX2;H0;!R;$(S(-[#6])-[#6])]",),
    146: (f"{_alk(0)}-[SX2;H0;!R;$(S(-[#6])-[#6])]",),
    147: ("c-[SX2;H0;!R;$(S(-[#6])-[#6])]",),
    148: ("[SX3;H0;!R;$(S(=O)(-[#6])-[#6])]=[OX1]",),
    149: ("[SX4;H0;!R;$(S(=O)(=O)(-[#6])-[#6])](=[OX1])=[OX1]",),
    150: (f"{_O_C}-[SX3](=[OX1])-{_O_C}",),
    # sulfonate ester R-SO2-OR': the sample compound is called "dimethyl sulfonate", read as methyl
    # methanesulfonate  # ASSUMPTION
    151: (f"[SX4;$(S(-[#6])(=O)(=O)-O)](=[OX1])(=[OX1])-{_O_C}",),
    152: (f"{_O_C}-[SX4](=[OX1])(=[OX1])-{_O_C}",),
    153: ("c-[SX3;!R;$(S(=O)(-[#6])-[#6])]=[OX1]",),
    # aC-SO2 also takes a sulfonic acid (second-order aC-SO2-OH)  # ASSUMPTION
    154: ("c-[SX4;!R;$(S(=O)(=O)(-[#6])-[$([#6]),$([OX2;H1])])](=[OX1])=[OX1]",),
    # --- phosphorus ---------------------------------------------------------------------------------------
    155: ("[PX3;H1;$(P(-[#6])-[#6])]",),
    156: ("[PX3;H0;$(P(-[#6])(-[#6])-[#6])]",),
    157: (f"[PX3;H0](-{_O_C})(-{_O_C})-{_O_C}",),
    158: (f"[PX4;H1](=[OX1])(-{_O_C})-{_O_C}",),
    # "trimethylphosphonate" is read as a dimethyl alkylphosphonate, RP(=O)(OR)2  # ASSUMPTION
    159: (f"[PX4;H0;$(P(-[#6])(=O)(-O)-O)](=[OX1])(-{_O_C})-{_O_C}",),
    160: (f"[PX4;H0](=[OX1])(-{_O_C})(-{_O_C})-[OX2;H1]",),
    161: (f"[PX4;H0](=[OX1])(-{_O_C})(-{_O_C})-{_O_C}",),
    162: (f"c-[OX2]-[PX4;H0](=[OX1])(-{_O_C})-{_O_C}",),
    163: ("c-[PX3;H0;$(P(-[#6])(-[#6])-[#6])]",),
    # --- carbonate, epoxides ------------------------------------------------------------------------------
    164: (f"{_ESTER_O}-[CX3;H0;!R](=O)-{_ESTER_O}",),
    # The ring's total hydrogen count names the group (ethyl oxirane 3, 2,2-dimethyl oxirane 2). C2O's sample
    # (trimethyl oxirane) has ONE hydrogen and its symbol none; both are taken as C2O, the only
    # epoxide group left  # ASSUMPTION
    165: ("[CX4;H1;r3]1-[CX4;H2;r3]-[OX2;r3]1",),
    166: ("[CX4;H0;r3]1-[CX4;H2;r3]-[OX2;r3]1", "[CX4;H1;r3]1-[CX4;H1;r3]-[OX2;r3]1"),
    167: ("[CX4;H0;r3]1-[CX4;H1;r3]-[OX2;r3]1", "[CX4;H0;r3]1-[CX4;H0;r3]-[OX2;r3]1"),
    # --- ring (non-aromatic) groups -----------------------------------------------------------------------
    168: ("[CX4;H2;R]",),
    169: ("[CX4;H1;R]",),
    170: ("[CX4;H0;R]",),
    171: ("[CX3;H1;R]=@[CX3;H1;R]",),
    172: ("[CX3;H1;R]=@[CX3;H0;R]",),
    173: ("[CX3;H0;R]=@[CX3;H0;R]",),
    174: ("[CX3;H2;!R]=[CX3;H0;R;x2]",),
    175: ("[NX3;H1;R]",),
    176: ("[NX3;H0;R;+0]",),
    177: ("[CX3;H1;R]=@[NX2;R]",),
    178: ("[CX3;H0;R]=@[NX2;R]",),
    # an epoxide's oxygen belongs to the epoxide groups; an oxirane none of them fits (ethylene oxide) is
    # refused, not sent to the tetrahydropyran group
    179: ("[OX2;R;!r3]",),
    180: ("[CX3;R;H0;$(C=O)]=[OX1]",),
    181: ("[SX2;R]",),
    182: ("[SX4;R](=[OX1])=[OX1]",),
}

#: groups whose heavy fragment is an aromatic carbon plus the first atom(s) of its substituent
_ARYL_R = frozenset(
    {20, 21, 22, 23, 24, 25, 26, 27, 28, 30, 32, 37, 39, 45, 46, 47, 53, 62, 63, 64, 71, 76, 80}
    | {94, 95, 96, 97, 98, 99, 105, 106, 123, 124, 125, 126, 133, 141, 147, 153, 154, 162, 163}
)


def _tier(group_id: int) -> int:
    """Rank of a group's family, compared before weight: aC-R first (the paper's second rule; the aromatic
    amides and ureas are among them: N-methylbenzamide is aC-CONH, not CONHCH3), then all others.

    The paper's third rule (ureas and amides use their own groups) needs no tier here: an amide group is
    defined by an acyl carbon that carries a carbon and a urea group by a carbonyl between two nitrogens
    (`# ASSUMPTION`: the paper's own example of the trap, CONHCH3 on a urea, needs the first to be loose), so
    no amide candidate can ever take atoms a urea candidate would, and the exception holds by construction.
    Dropping a tier for them was measured to change no result (a mutation that does it survives the suite)."""
    return 2 if group_id in _ARYL_R else 1


_PATTERNS: dict[int, tuple[Chem.Mol, ...]] = {}


def _patterns() -> dict[int, tuple[Chem.Mol, ...]]:
    if not _PATTERNS:
        for gid, smarts in _SMARTS.items():
            parsed = []
            for text in smarts:
                patt = Chem.MolFromSmarts(text)
                if patt is None:
                    raise ValueError(f"group {gid} ({SYMBOL[gid]}): bad SMARTS {text!r}")
                parsed.append(patt)
            _PATTERNS[gid] = tuple(parsed)
    return _PATTERNS


# ---------------------------------------------------------------------------------------------------------
# Result and refusal types
# ---------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Fragmentation:
    """One molecule's first-order groups: `counts` is {group id: occurrences}, `assignment` one atom-level
    cover (group id, the atom indices of the `smiles` as written) that gives them."""

    smiles: str
    counts: dict[int, int]
    assignment: tuple[tuple[int, tuple[int, ...]], ...]

    def symbols(self) -> dict[str, int]:
        """`{symbol: count}` as `energetics_groups.count_groups` returns. The paper prints `aC-NCO` for two
        groups; the second (99, the tertiary anilide) is keyed `aC-NCO [99]` so the two never merge."""
        return {_symbol_key(gid): n for gid, n in self.counts.items()}


def _symbol_key(group_id: int) -> str:
    return "aC-NCO [99]" if group_id == 99 else SYMBOL[group_id]


class GroupingRefusal(ValueError):
    """The molecule cannot be described by Table 6 as a full, disjoint, unambiguous splitting.

    `reason` is one of `invalid`, `not_one_molecule`, `charged`, `uncovered` (some atom fits no group, or
    no disjoint cover exists), `ambiguous` (two covers are equally good) and `too_complex`. `uncovered` lists
    `(atom index, element, neighbour elements)` of the atoms no group claimed; `alternatives` the group-id
    lists of tied covers."""

    def __init__(self, smiles, reason, message, *, uncovered=(), alternatives=()):
        super().__init__(f"{smiles!r}: {message}")
        self.smiles = smiles
        self.reason = reason
        self.uncovered = tuple(uncovered)
        self.alternatives = tuple(alternatives)


# ---------------------------------------------------------------------------------------------------------
# The molecule, as the paper reads it
# ---------------------------------------------------------------------------------------------------------
def _paper_aromatic_rings(mol: Chem.Mol) -> list[tuple[int, ...]]:
    """Six-membered rings that are aromatic in the paper's sense (see the module docstring)."""
    rings = []
    for ring in Chem.GetSymmSSSR(mol):
        ring = tuple(ring)
        if len(ring) != 6:
            continue
        ok = True
        for idx in ring:
            atom = mol.GetAtomWithIdx(idx)
            if not atom.GetIsAromatic():
                ok = False
            elif atom.GetAtomicNum() == 7:
                # pyridine type: no H, no charge, two ring neighbours only
                ok = ok and atom.GetTotalNumHs() == 0 and atom.GetFormalCharge() == 0 and atom.GetDegree() == 2
            elif atom.GetAtomicNum() != 6:
                ok = False
            if not ok:
                break
            for bond in atom.GetBonds():
                other = bond.GetOtherAtomIdx(idx)
                if other not in ring and bond.GetBondType() == Chem.BondType.DOUBLE:
                    ok = False
        if ok:
            rings.append(ring)
    return rings


def _normalise_oxides(mol: Chem.RWMol) -> None:
    """`[S+]-[O-]` and `[P+]-[O-]` are the same bond as `S=O` / `P=O`; write them that way."""
    for bond in list(mol.GetBonds()):
        a, b = bond.GetBeginAtom(), bond.GetEndAtom()
        for s, o in ((a, b), (b, a)):
            if (s.GetSymbol() in ("S", "P") and s.GetFormalCharge() == 1
                    and o.GetSymbol() == "O" and o.GetFormalCharge() == -1 and o.GetDegree() == 1
                    and bond.GetBondType() == Chem.BondType.SINGLE):
                s.SetFormalCharge(0)
                o.SetFormalCharge(0)
                bond.SetBondType(Chem.BondType.DOUBLE)


def _paper_view(smiles: str) -> Chem.Mol:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise GroupingRefusal(smiles, "invalid", "cannot read it as a structure")
    if len(Chem.GetMolFrags(mol)) != 1:
        raise GroupingRefusal(smiles, "not_one_molecule", "more than one component (a salt or a mixture)")
    rw = Chem.RWMol(mol)
    _normalise_oxides(rw)
    mol = rw.GetMol()
    Chem.SanitizeMol(mol)
    for atom in mol.GetAtoms():
        charge = atom.GetFormalCharge()
        if charge == 0:
            continue
        # the charge-separated nitro (and nitrate) group is the one charged form Table 6 has groups for:
        # an N+ with exactly one O- among its oxygens, the rest neutral
        o_charges = sorted(nb.GetFormalCharge() for nb in atom.GetNeighbors() if nb.GetSymbol() == "O")
        nitro_n = (atom.GetSymbol() == "N" and charge == 1 and len(o_charges) >= 2
                   and o_charges.count(-1) == 1 and set(o_charges) <= {-1, 0})
        nitro_o = atom.GetSymbol() == "O" and charge == -1 and any(
            nb.GetSymbol() == "N" and nb.GetFormalCharge() == 1 for nb in atom.GetNeighbors())
        if not (nitro_n or nitro_o):
            raise GroupingRefusal(smiles, "charged", f"atom {atom.GetIdx()} ({atom.GetSymbol()}) is charged")

    hydrogens = [a.GetTotalNumHs() for a in mol.GetAtoms()]
    rings = _paper_aromatic_rings(mol)
    in_ring = {i for r in rings for i in r}
    ring_bonds = set()
    for r in rings:
        for k, idx in enumerate(r):
            bond = mol.GetBondBetweenAtoms(idx, r[(k + 1) % 6])
            ring_bonds.add(bond.GetIdx())

    Chem.Kekulize(mol, clearAromaticFlags=True)
    for atom, h in zip(mol.GetAtoms(), hydrogens, strict=True):
        atom.SetNumExplicitHs(h)
        atom.SetNoImplicit(True)
    for idx in in_ring:
        mol.GetAtomWithIdx(idx).SetIsAromatic(True)
    for bidx in ring_bonds:
        bond = mol.GetBondWithIdx(bidx)
        bond.SetBondType(Chem.BondType.AROMATIC)
        bond.SetIsAromatic(True)
    mol.UpdatePropertyCache(strict=False)
    Chem.GetSymmSSSR(mol)
    return mol


# ---------------------------------------------------------------------------------------------------------
# Candidates and the cover
# ---------------------------------------------------------------------------------------------------------
_PT = Chem.GetPeriodicTable()


def _weight(mol: Chem.Mol, atoms: tuple[int, ...]) -> float:
    total = 0.0
    for idx in atoms:
        atom = mol.GetAtomWithIdx(idx)
        total += _PT.GetAtomicWeight(atom.GetAtomicNum()) + atom.GetTotalNumHs() * 1.008
    return round(total, 3)


def _candidates(mol: Chem.Mol) -> list[tuple[int, frozenset[int], tuple[int, float]]]:
    seen = set()
    out = []
    for gid, patterns in _patterns().items():
        for patt in patterns:
            for match in mol.GetSubstructMatches(patt, uniquify=True, maxMatches=100000):
                key = (gid, frozenset(match))
                if key in seen:
                    continue
                seen.add(key)
                out.append((gid, key[1], (_tier(gid), _weight(mol, tuple(match)))))
    return out


class _TooComplex(Exception):
    pass


_STATE_BUDGET = 400_000


def _atom_order(mol: Chem.Mol) -> list[int]:
    """Breadth-first from the atom with the smallest canonical rank: only a speed choice (the answer is the
    optimum, whatever order it is searched in), but it keeps the search frontier narrow."""
    rank = list(Chem.CanonicalRankAtoms(mol, breakTies=True))
    start = min(range(mol.GetNumAtoms()), key=rank.__getitem__)
    order, seen, queue = [], {start}, [start]
    while queue:
        nxt = []
        for idx in queue:
            order.append(idx)
            for nb in sorted((n.GetIdx() for n in mol.GetAtomWithIdx(idx).GetNeighbors()), key=rank.__getitem__):
                if nb not in seen:
                    seen.add(nb)
                    nxt.append(nb)
        queue = nxt
    return order


def _best_cover(mol, cands):
    """The best full disjoint cover. Returns (None, atoms no candidate touches) when some atom has no group,
    ('none', unclaimed atoms of the best partial cover) when none exists, else (optima, None) with the
    set of distinct group-id multisets that tie for best."""
    n = mol.GetNumAtoms()
    touched = set().union(*[c[1] for c in cands]) if cands else set()
    orphans = [i for i in range(n) if i not in touched]
    if orphans:
        return None, orphans

    keys = sorted({c[2] for c in cands})
    rank = {k: r for r, k in enumerate(keys)}
    base = n + 2
    by_atom: dict[int, list] = {i: [] for i in range(n)}
    entries = []
    for gid, atoms, key in cands:
        mask = 0
        for a in atoms:
            mask |= 1 << a
        entry = (gid, mask, base ** rank[key])
        entries.append(entry)
        for a in atoms:
            by_atom[a].append(entry)

    order = _atom_order(mol)
    full = (1 << n) - 1
    memo: dict[int, object] = {}

    def first_free(mask):
        for a in order:
            if not mask >> a & 1:
                return a
        return -1

    def solve(mask):
        if mask == full:
            return 0, frozenset({()})
        if mask in memo:
            return memo[mask]
        if len(memo) > _STATE_BUDGET:
            raise _TooComplex
        atom = first_free(mask)
        best_score, best = -1, set()
        for gid, gmask, score in by_atom[atom]:
            if gmask & mask:
                continue
            child = solve(mask | gmask)
            if child is None:
                continue
            total = child[0] + score
            if total > best_score:
                best_score, best = total, set()
            if total == best_score:
                for ms in child[1]:
                    best.add(tuple(sorted(ms + (gid,))))
                    if len(best) > 8:
                        break
        result = (best_score, frozenset(best)) if best_score >= 0 else None
        memo[mask] = result
        return result

    top = solve(0)
    if top is not None:
        return top[1], None

    # no disjoint cover exists: find the cover that leaves the fewest atoms unclaimed, to name them
    memo2: dict[int, tuple[int, int, frozenset]] = {}

    def partial(mask):
        if mask == full:
            return 0, 0, frozenset()
        if mask in memo2:
            return memo2[mask]
        if len(memo2) > _STATE_BUDGET:
            raise _TooComplex
        atom = first_free(mask)
        sk = partial(mask | (1 << atom))
        best = (sk[0] - 1, sk[1], sk[2] | {atom})
        for _gid, gmask, score in by_atom[atom]:
            if gmask & mask:
                continue
            child = partial(mask | gmask)
            cand = (child[0], child[1] + score, child[2])
            if (cand[0], cand[1]) > (best[0], best[1]):
                best = cand
        memo2[mask] = best
        return best

    return "none", sorted(partial(0)[2])


def _describe(mol, indices):
    return [
        (i, mol.GetAtomWithIdx(i).GetSymbol(),
         tuple(sorted(nb.GetSymbol() for nb in mol.GetAtomWithIdx(i).GetNeighbors())))
        for i in indices
    ]


def _assignment(mol, cands, optimum) -> tuple[tuple[int, tuple[int, ...]], ...]:
    """One atom-level cover whose group ids are `optimum` (a sorted tuple); for reporting only."""
    wanted: dict[int, int] = {}
    for gid in optimum:
        wanted[gid] = wanted.get(gid, 0) + 1
    by_atom: dict[int, list] = {}
    for gid, atoms, _key in cands:
        for a in atoms:
            by_atom.setdefault(a, []).append((gid, atoms))
    order = _atom_order(mol)

    def go(claimed, remaining):
        free = next((a for a in order if a not in claimed), None)
        if free is None:
            return []
        for gid, atoms in by_atom.get(free, ()):
            if remaining.get(gid, 0) and not (atoms & claimed):
                remaining[gid] -= 1
                rest = go(claimed | atoms, remaining)
                remaining[gid] += 1
                if rest is not None:
                    return [(gid, tuple(sorted(atoms)))] + rest
        return None

    return tuple(go(frozenset(), wanted) or ())


def fragment(smiles: str) -> Fragmentation:
    """The molecule's first-order groups, or a `GroupingRefusal`: never a partial sum."""
    mol = _paper_view(smiles)
    cands = _candidates(mol)
    try:
        optima, unclaimed = _best_cover(mol, cands)
    except _TooComplex:
        raise GroupingRefusal(smiles, "too_complex", "the search for a disjoint cover exceeded its budget") from None
    if optima is None or optima == "none":
        raise GroupingRefusal(
            smiles, "uncovered",
            "no group claims atom(s) " + ", ".join(
                f"{i} ({el})" for i, el, _ in _describe(mol, unclaimed)),
            uncovered=_describe(mol, unclaimed),
        )
    if len(optima) > 1:
        alts = sorted(optima)
        raise GroupingRefusal(
            smiles, "ambiguous",
            "two equally good splittings the paper does not rank: "
            + " vs ".join("[" + ", ".join(SYMBOL[g] for g in a) + "]" for a in alts),
            alternatives=alts,
        )
    (best,) = optima
    counts: dict[int, int] = {}
    for gid in best:
        counts[gid] = counts.get(gid, 0) + 1
    return Fragmentation(smiles, counts, _assignment(mol, cands, best))


def count_groups(smiles: str) -> dict[str, int]:
    """`{group symbol: occurrences}`, the shape `energetics_groups.count_groups` returns; raises
    `GroupingRefusal` (a `ValueError`) where it cannot describe the molecule completely."""
    return fragment(smiles).symbols()


# ---------------------------------------------------------------------------------------------------------
# From groups to properties (by group id, so the duplicated `aC-NCO` symbol cannot collide)
# ---------------------------------------------------------------------------------------------------------
def first_order_sum(prop: str, counts: dict[int, int]) -> float:
    """sum N_i * C_i over Table 6, the right-hand side of the paper's Eq. (1) at the first level."""
    col = 3 + _PROPERTIES.index(prop)
    total = 0.0
    for gid, n in counts.items():
        value = _ROW[gid][col]
        if value is None:
            raise NoContribution(f"group {gid} {SYMBOL[gid]!r} has no {prop} contribution in Table 6 ('*****')")
        total += n * value
    return total


def estimate_first_order(prop: str, counts: dict[int, int]) -> float:
    """The property itself at the first level, inverting Table 1's f(X)."""
    total = first_order_sum(prop, counts)
    c = UNIVERSAL_CONSTANTS
    if prop in ("Tm", "Tb", "Tc"):
        return c[f"{prop}0"] * math.log(total)
    if prop == "Pc":
        return c["Pc1"] + (total + c["Pc2"]) ** -2
    return c[f"{prop}0"] + total


def estimate_smiles(prop: str, smiles: str) -> float:
    """`fragment` then `estimate_first_order`; a refusal or a starred contribution raises, never a number."""
    return estimate_first_order(prop, fragment(smiles).counts)
