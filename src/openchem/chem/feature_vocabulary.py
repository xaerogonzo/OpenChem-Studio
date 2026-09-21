"""The structural-feature vocabulary, v3: what each feature IS, before any pattern.

**WHY THIS FILE HOLDS NO SMARTS.** A pattern says what matches; this file says
what a match is supposed to MEAN, and it was written and committed before the
patterns so the patterns are checked against it rather than the other way
round. Every feature carries:

* a stable ``feature_id`` (``fg:`` a functional group, ``sf:`` a structural
  feature). Ids are never reused for a different meaning;
  ``VOCABULARY_VERSION`` changes instead.
* a DEFINITION from a named source, with the page, and the structural
  formula that source writes. The normative source is the IUPAC Gold Book
  (Compendium of Chemical Terminology, version 2.3.1, 2012-03-23)
  [source:iupac_goldbook], whose class names come from the 1995 glossary of
  class names [source:moss1995]. Pages are the Gold Book's own "N of
  1622", which is a page HEADER -- measured, and every page here agrees with
  the Gold Book's index. Where the Gold Book has no entry (ureas, guanidines,
  halogen compounds; checked in its index and in the 1995 glossary), the
  definition is the Blue Book's and says so.
* an OPERATIONALISATION note: a citation does not specify a SMARTS, so each
  feature says how its definition is read, including every edge case that
  was a decision.
* ROLES: the named atoms of the feature. The atom set of an instance is the
  atoms that carry the functionality -- heteroatoms and the carbons the
  definition makes special (carbonyl, C=N, C#N, acetal, C=C, oxirane ring) --
  and never the R groups. That is the same marking Ertl's algorithm makes
  ([source:ertl2017], p. 2), so the cross-check compares like with like.
* CHARGE STATES it can be detected in, with the label each one reads as. A
  carboxylate is a carboxylic acid in the anionic state, not a separate
  category (plan, pushback 3), but it is not LABELLED "carboxylic acid".

**NOT GOVERNED BY THE BLUE BOOK.** A feature may exist structurally without
being a principal characteristic group, and the naming engine's group types
are a second, independent vocabulary. They reach this one only through
``ENGINE_GROUP_MAP``, which must name every engine type (a test fails on a
new unmapped one).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class FeatureCategory(str, Enum):
    """What KIND of thing a feature is.

    A benzene ring and an amide are both worth showing and are not the same
    kind of claim, and code downstream must not have to infer that from a
    key's spelling. Ionic forms are NOT a category: a carboxylate is a
    carboxylic acid in the anionic state (see `ChargeState`).
    """

    FUNCTIONAL_GROUP = "functional_group"
    RING_SYSTEM = "ring_system"
    STRUCTURAL_FEATURE = "structural_feature"


#: Part of every instance's identity. Bumped when a feature's MEANING changes,
#: so a stored result can never be reinterpreted by a later definition.
#: v3 (2026-09-20) added fifteen features and two relations; no v2 feature's
#: definition changed, but a saved v2 set omits what v3 would now detect, so
#: it must not vouch for a v3 one.
VOCABULARY_VERSION = "openchem-structural-features-v3"

#: Measured page count, the denominator every Gold Book page is out of.
GOLD_BOOK_PAGES = 1622


class DefinitionSource(str, Enum):
    """Which document a definition is read from. Values are `docs/sources.toml` keys."""

    GOLD_BOOK = "iupac_goldbook"
    BLUE_BOOK = "iupac2013"


@dataclass(frozen=True)
class Definition:
    source: DefinitionSource
    #: The headword exactly as printed.
    term: str
    #: Gold Book: its own page number (of 1622). Blue Book: the pdf page.
    page: int
    #: The structure the entry writes, verbatim where it writes one. A formula,
    #: never the prose -- the prose is the source's, and one line of it is what
    #: gets quoted in review, not stored.
    formula: str
    #: Blue Book only: the rule number.
    section: str = ""


class ChargeState(str, Enum):
    """The sign of the summed formal charge over an instance's atoms.

    Measured off the structure as drawn, never inferred: the detector reads
    the molecule it is given, and choosing the pH-relevant form is upstream's
    job (`structure_annotation` receives the pH-selected structure). A nitro
    group or an N-oxide is NEUTRAL here -- its charges cancel inside it.
    """

    NEUTRAL = "neutral"
    ANIONIC = "anionic"
    CATIONIC = "cationic"


@dataclass(frozen=True)
class FeatureDefinition:
    feature_id: str
    category: FeatureCategory
    #: Label per charge state it can be detected in. The keys ARE the
    #: permitted charge states: a detection in any other state is a defect.
    labels: dict[ChargeState, str]
    #: Role names, in order. Fixture SMILES mark an atom of role i (1-based)
    #: of instance k (0-based) with atom-map number 10*k + i.
    roles: tuple[str, ...]
    definition: Definition
    operationalisation: str
    #: Onium centres are one feature whose label depends on the element.
    label_by_element: dict[str, str] = field(default_factory=dict)


def _gb(term: str, page: int, formula: str) -> Definition:
    return Definition(DefinitionSource.GOLD_BOOK, term, page, formula)


def _bb(term: str, page: int, section: str, formula: str) -> Definition:
    return Definition(DefinitionSource.BLUE_BOOK, term, page, formula, section)


#: Short forms for the FEATURES table, which is unreadable spelled out.
_N, _A, _C = ChargeState.NEUTRAL, ChargeState.ANIONIC, ChargeState.CATIONIC
#: Short forms for the FEATURES table, as above.
_FG, _SF = FeatureCategory.FUNCTIONAL_GROUP, FeatureCategory.STRUCTURAL_FEATURE


def _f(fid, labels, roles, definition, note, category=_FG, by_element=None):
    if isinstance(labels, str):
        labels = {_N: labels}
    return FeatureDefinition(
        feature_id=fid,
        category=category,
        labels=labels,
        roles=tuple(roles),
        definition=definition,
        operationalisation=note,
        label_by_element=by_element or {},
    )


#: The vocabulary, IN DECLARED ORDER. This order is the display and counting
#: order of every projection, so two runs and two atom orderings agree.
FEATURES: tuple[FeatureDefinition, ...] = (
    # --- acids and their derivatives -------------------------------------
    _f("fg:carboxylic_acid", {_N: "carboxylic acid", _A: "carboxylate"},
       ("carbonyl_c", "carbonyl_o", "hydroxy_o"),
       _gb("carboxylic acids", 215, "RC(=O)OH"),
       "R is carbon or hydrogen (formic acid is one); a carbonyl carbon bearing N "
       "or O is carbamic or carbonic acid and is excluded. Anionic when the "
       "hydroxy oxygen is O-."),
    _f("fg:thiocarboxylic_acid", {_N: "thiocarboxylic acid", _A: "thiocarboxylate"},
       ("acyl_c", "acyl_x", "acid_x"),
       _gb("thiocarboxylic acids", 1537, "RC(=O)SH, RC(=S)OH, RC(=S)SH"),
       "The monothio acids (either tautomer, drawn as it is) and the dithio "
       "acids the entry lists. R is carbon or H, as for a carboxylic acid: a "
       "carbonyl carbon bearing N or O is a thiocarbamic or thiocarbonic acid. "
       "Anionic when the single-bonded chalcogen is S- or O-. The esters are "
       "fg:thioester."),
    _f("fg:carboxylic_ester", "carboxylic ester",
       ("carbonyl_c", "carbonyl_o", "ester_o"),
       _gb("esters", 528, "R'C(=O)(OR)"),
       "The carboxylic-acid esters of the Gold Book's wider class: R' is carbon "
       "or H and R is carbon. The sulfonic, sulfuric, phosphoric and carbonic "
       "esters the same entry includes are their own features, so no ester "
       "oxygen is described twice. A ring ester is also a lactone."),
    _f("fg:lactone", "lactone", ("carbonyl_c", "carbonyl_o", "ring_o"),
       _gb("lactones", 817, "1-oxacycloalkan-2-one"),
       "A carboxylic ester whose carbonyl carbon and ester oxygen share a ring."),
    _f("fg:carbonate_ester", "carbonate ester",
       ("carbonyl_c", "carbonyl_o", "ester_o"),
       _gb("esters", 528, "RkE(=O)l(OH)m ester, E = C, k = 0"),
       "Carbonic acid is an oxoacid of the entry's form, so its esters are "
       "esters proper. Carbonyl carbon bearing two O, at least one of them "
       "bonded to carbon."),
    _f("fg:carboxylic_anhydride", "carboxylic anhydride",
       ("acyl_c", "acyl_o", "bridge_o"),
       _gb("acid anhydrides", 21, "acyl-O-acyl"),
       "Two carbonyl carbons on one oxygen. Only carboxylic anhydrides; a "
       "sulfonic anhydride is rare enough to leave to the Ertl report."),
    _f("fg:acyl_halide", "acyl halide", ("acyl_centre", "oxo_o", "halogen"),
       _gb("acyl halides", 33, "CH3COCl; CH3S(=O)2Cl"),
       "The entry's own examples include methanesulfonyl chloride, so a sulfonyl "
       "halide is one. The halogen is therefore not also a halo substituent."),
    _f("fg:carboxamide", "amide", ("carbonyl_c", "carbonyl_o", "amide_n"),
       _gb("carboxamides", 214, "RC(=O)NR2"),
       "R on the carbonyl is carbon or H (so a urea or carbamate is not one). "
       "On N, anything but N or O (those are hydrazides and hydroxamic acids): "
       "the amides entry generically includes N-acyl and N-sulfonyl amides, "
       "'one, two or three acyl groups on a given nitrogen'. "
       "NOT labelled primary/secondary/tertiary: the Gold Book's amides entry "
       "(p. 69, note 1) says NH2/NHR/NR2 amides must not be distinguished by "
       "those words, which mean one, two or three ACYL groups (FG-001)."),
    _f("fg:lactam", "lactam", ("carbonyl_c", "carbonyl_o", "amide_n"),
       _gb("lactams", 815, "1-azacycloalkan-2-one"),
       "A carboxamide whose carbonyl carbon and nitrogen share a ring. The "
       "entry's analogue clause would admit a cyclic urea; that is a urea "
       "here, the more specific description."),
    _f("fg:imide", "imide", ("carbonyl_c", "carbonyl_o", "imide_n"),
       _gb("imides", 710, "diacyl derivatives of ammonia or primary amines"),
       "Sense 1 only: a nitrogen bearing two acyl (C=O) groups, of any kind, "
       "ring or chain. Sense 2 (additive R3N+-N-R) is not this feature."),
    _f("fg:urea", "urea", ("carbonyl_c", "carbonyl_o", "urea_n"),
       _bb("urea", 660, "P-66.1.6.1.1", "H2N-CO-NH2"),
       "The Gold Book has no ureas entry (index and 1995 glossary checked). "
       "Carbonyl carbon bearing two nitrogens, any substitution, ring or chain."),
    _f("fg:thiourea", "thiourea", ("thiocarbonyl_c", "thiocarbonyl_s", "urea_n"),
       _bb("urea", 662, "P-66.1.6.1.3", "H2N-CS-NH2"),
       "The Gold Book has no thioureas entry either (index and 1995 glossary "
       "checked). The chalcogen analogue named in the same Blue Book section."),
    _f("fg:carbamate", {_N: "carbamate", _A: "carbamate"}, ("carbonyl_c", "carbonyl_o", "amide_n", "ester_o"),
       _gb("carbamates", 201, "R2NC(=O)OR'"),
       "Esters (R' carbon) and salts (O-) of carbamic acids. The carbonyl "
       "carbon bears exactly one N and one O."),
    _f("fg:thiocarbamate", {_N: "thiocarbamate", _A: "thiocarbamate"},
       ("carbonyl_c", "carbonyl_x", "amide_n", "ester_x"),
       _bb("carbamothioic acids", 600, "P-65.2.1.2", "H2N-CS-OH; H2N-CO-SH"),
       "The Gold Book has no thiocarbamate entry: its carbamates entry (p. 201) "
       "names the oxygen compounds, and the chalcogen analogues of carbamic acid "
       "are the Blue Book's, by functional replacement (O-thio, S-thio and "
       "dithio). Esters (the single-bonded chalcogen bears carbon) and salts "
       "(S- or O-), as carbamate; the free acids are not detected, and at least "
       "one chalcogen is sulfur. Ring or chain: rhodanine's N-C(=S)-S is one. "
       "The single-bonded chalcogen needs a SECOND carbon (the carbonyl carbon "
       "satisfies a lone `bonded to carbon`), which is also why a thiuram "
       "disulfide's S-S is not two of these: the Blue Book names it a "
       "trithiodicarbonic diamide (p. 663)."),
    _f("fg:thioester", "thioester", ("acyl_c", "acyl_x", "ester_x"),
       _gb("esters", 528, "R'C(=S)(OR), R'C(=O)(SR)"),
       "The chalcogen esters the esters entry names: thiono (C=S)-O, thiolo "
       "C(=O)-S and dithio. Carbonyl carbon bears carbon or H."),
    _f("fg:thioamide", "thioamide", ("thiocarbonyl_c", "thiocarbonyl_s", "amide_n"),
       _gb("amides", 69, "thio-amides (chalcogen replacement analogues)"),
       "RC(=S)NR2 with R carbon or H."),
    _f("fg:hydroxamic_acid", "hydroxamic acid",
       ("carbonyl_c", "carbonyl_o", "amide_n", "hydroxy_o"),
       _gb("hydroxamic acids", 700, "RC(=O)NHOH"),
       "'And hydrocarbyl derivatives thereof', so N and O may both carry "
       "carbon. B0 excluded the O-alkyl ones; the Ertl cross-check found that "
       "wrong against the entry's own words (N-alkoxy amides, 0.09% of ChEMBL)."),
    _f("fg:hydrazide", "hydrazide", ("carbonyl_c", "carbonyl_o", "amide_n", "terminal_n"),
       _gb("hydrazides", 693, "RC(=O)NHNH2"),
       "Carbohydrazides and sulfonohydrazides; the terminal N single-bonded."),
    # --- carbonyl and imino carbon ---------------------------------------
    _f("fg:aldehyde", "aldehyde", ("carbonyl_c", "carbonyl_o"),
       _gb("aldehydes", 54, "RC(=O)H"),
       "Carbonyl carbon with exactly one H and one carbon (formaldehyde, with "
       "two H, is included)."),
    _f("fg:ketone", "ketone", ("carbonyl_c", "carbonyl_o"),
       _gb("ketones", 805, "R2C=O"),
       "Carbonyl carbon bonded to two carbons and nothing else, ring or chain, "
       "including a ring C=O RDKit perceives as aromatic (a pyranone, a "
       "quinone). The entry's note excludes R3SiC(=O)R."),
    _f("fg:thioketone", "thioketone", ("thiocarbonyl_c", "thiocarbonyl_s"),
       _gb("thioketones", 1537, "R2C=S"),
       "As ketone, with S."),
    _f("fg:thioaldehyde", "thioaldehyde", ("carbonyl_c", "thiocarbonyl_s"),
       _gb("thioaldehydes", 1536, "RC(=S)H"),
       "As aldehyde, with S: a carbonyl-type carbon with exactly one H and one "
       "carbon, or two H (thioformaldehyde)."),
    _f("fg:amidine", {_N: "amidine", _C: "amidinium"}, ("amidine_c", "imino_n", "amino_n"),
       _gb("carboxamidines", 214, "RC(=NR)NR2"),
       "R on carbon is carbon or H, so guanidine (three N) is excluded."),
    _f("fg:guanidine", {_N: "guanidine", _C: "guanidinium"},
       ("guanidine_c", "imino_n", "amino_n"),
       _bb("guanidine", 675, "P-66.4.1.2.1.1", "H2N-C(=NH)-NH2"),
       "The Gold Book has no guanidines entry. Carbon bearing three nitrogens, "
       "one double-bonded; cationic when protonated (delocalised, any N)."),
    _f("fg:imidate", "imidate (imidic acid or ester)", ("imidate_c", "imino_n", "o"),
       _gb("imidic acids", 710, "RC(=NR)(OH)"),
       "The carboximidic acids ('tautomers of amides') and their O-hydrocarbyl "
       "esters, which the esters entry's note names as esters though not esters "
       "proper. Carbon bears C or H (so an isourea is not one); the drawn "
       "tautomer is kept -- an acyclic lactim is this, the amide is a carboxamide."),
    _f("fg:thioimidate", "thioimidate", ("imidate_c", "imino_n", "s"),
       _bb("carboximidothioate", 628, "P-65.6.3.3.7.1", "C6H5-C(=NH)-S-CH3"),
       "The Gold Book has no entry for the sulfur analogue of an imidate: its "
       "imidic acids entry (p. 710) replaces =O by =NR in oxoacids and names "
       "oxygen. The S-hydrocarbyl esters of carboximidothioic acids, ring or "
       "chain (a 2-thiazoline is one). The S-H form is a thiol as drawn, "
       "and so is not detected here. Carbon bears C or H, so an "
       "isothiourea is not one."),
    _f("fg:isourea", "isourea", ("isourea_c", "imino_n", "amino_n", "o"),
       _gb("isoureas", 799, "H2NC(=NH)OH"),
       "And its hydrocarbyl derivatives: O-alkylisoureas included."),
    _f("fg:isothiourea", "isothiourea",
       ("isothiourea_c", "imino_n", "amino_n", "s"),
       _bb("carbamimidothioic acid", 662, "P-66.1.6.1.3.2", "H2N-C(=NH)-SH"),
       "The Gold Book has no isothiourea entry: its isoureas entry (p. 799) "
       "names the oxygen compound. The chalcogen analogue named in the same "
       "Blue Book section as the thiourea. S-hydrocarbyl derivatives only, ring "
       "or chain (a 2-amino-2-thiazoline is one); the S-H form is a thiol as "
       "drawn, the tautomer of a thiourea."),
    _f("fg:imine", {_N: "imine", _C: "iminium"}, ("imine_c", "imine_n"),
       _gb("imines", 712, "RN=CR2 (R = H, hydrocarbyl)"),
       "Sense 1 only. N bears H or carbon, carbon bears H or carbon, so oximes, "
       "hydrazones and amidines are excluded. Cationic is the iminium "
       "compounds entry (p. 712, R2C=N+R2)."),
    _f("fg:oxime", "oxime", ("imine_c", "imine_n", "hydroxy_o"),
       _gb("oximes", 1052, "R2C=NOH"),
       "O-substituted oximes (oxime ethers) are included: the O may carry carbon."),
    _f("fg:hydrazone", "hydrazone", ("imine_c", "imine_n", "amino_n"),
       _gb("hydrazones", 694, "R2C=NNR2"), "As written."),
    _f("fg:nitrone", "nitrone", ("imine_c", "imine_n", "oxide_o"),
       _gb("nitrones", 996, "R2C=N+(O-)R'"),
       "The N-oxide of an imine; R' may be H (the entry includes it). Added "
       "after the Ertl cross-check found chlordiazepoxide's claimed by nothing."),
    _f("fg:carbodiimide", "carbodiimide", ("central_c", "n"),
       _gb("carbodiimides", 205, "HN=C=NH"), "And hydrocarbyl derivatives."),
    _f("fg:isocyanate", "isocyanate", ("n", "c", "o"),
       _gb("isocyanates", 778, "RN=C=O"), "As written."),
    _f("fg:isothiocyanate", "isothiocyanate", ("n", "c", "s"),
       _gb("isothiocyanates", 792, "RN=C=S"), "As written."),
    _f("fg:cyanate", "cyanate", ("cyanate_c", "cyanate_n", "ester_o"),
       _gb("cyanates", 363, "ROCN"),
       "The esters of cyanic acid (R carbon); the entry also names its salts, "
       "but the cyanate ANION has no organyl group and is reported as a "
       "component, as carbon disulfide is. The esters entry's own note "
       "separates it from R-NCO (fg:isocyanate)."),
    _f("fg:thiocyanate", "thiocyanate", ("thiocyanate_c", "thiocyanate_n", "ester_s"),
       _gb("thiocyanates", 1537, "RSC#N"),
       "The esters of thiocyanic acid, S bonded to carbon; the thiocyanate "
       "ANION is a component, not a group. Not the isothiocyanate R-NCS."),
    _f("fg:nitrile", "nitrile", ("nitrile_c", "nitrile_n"),
       _gb("nitriles", 995, "RC#N"),
       "Both atoms: the entry notes the suffix denotes only N, but the group a "
       "chemist points at is the C#N."),
    _f("fg:cyanamide", "cyanamide", ("cyano_c", "cyano_n", "amino_n"),
       _bb("cyanamide", 663, "P-66.1.6.2", "NC-NH2"),
       "The Gold Book has no cyanamides entry. The amides of cyanic acid, the "
       "Blue Book's 'substitution is allowed on the -NH2 group': the N is "
       "neutral, single-bonded to the cyano carbon and to nothing that makes it "
       "aromatic. A C=N nitrogen carrying the cyano group (cyanoguanidine drawn "
       "as the imino tautomer) is a cyano-substituted imine, not an amide of "
       "cyanic acid, and the drawn tautomer is what is read. Not a nitrile "
       "(fg:nitrile needs carbon on the C#N)."),
    _f("fg:isocyanide", "isocyanide", ("n", "c"),
       _gb("isocyanides", 778, "RN+#C-"), "As written."),
    # --- oxygen ----------------------------------------------------------
    _f("fg:alcohol", {_N: "alcohol", _A: "alkoxide"}, ("hydroxy_o",),
       _gb("alcohols", 53, "R3COH"),
       "OH on a SATURATED carbon, which is the definition's own word: an OH on "
       "C=C is an enol and on an arene a phenol. Anionic is the alkoxides "
       "entry (p. 59)."),
    _f("fg:phenol", {_N: "phenol", _A: "phenolate"}, ("hydroxy_o",),
       _gb("phenols", 1095, "ArOH"),
       "OH on a carbon of a benzene or other ARENE ring, the entry's words: "
       "the carbon's smallest ring is all carbon, so quinolin-5-ol is a phenol "
       "and pyridin-2-ol is not (see heteroarenol). Anionic is the phenolates "
       "entry (p. 1095)."),
    _f("fg:heteroarenol", {_N: "heteroarenol", _A: "heteroarenolate"}, ("hydroxy_o",),
       _gb("esters", 528, "alcohol, phenol, heteroarenol, or enol"),
       "No entry of its own: the esters entry names the class beside phenols, "
       "and the phenols entry (p. 1095) covers arenes only. OH on an aromatic "
       "carbon whose smallest ring holds a heteroatom. The drawn tautomer is "
       "kept: pyridin-2-ol is this, pyridin-2(1H)-one is a lactam."),
    _f("fg:enol", "enol", ("hydroxy_o", "vinyl_c"),
       _gb("enols", 512, "HOCR'=CR2"),
       "OH on a non-aromatic C=C; the C=C is part of the enol."),
    _f("fg:ether", "ether", ("ether_o",),
       _gb("ethers", 528, "ROR (R != H)"),
       "Both R hydrocarbyl: an O next to C=O/C=S/C=N or to S, P, N is an "
       "ester, acid or other feature. A non-aromatic oxygen only -- a furan O "
       "belongs to its ring -- but the neighbours may be aromatic (anisole). "
       "R3SiOR is not an ether (the entry says so): see silyl ether."),
    _f("fg:epoxide", "epoxide", ("ring_o", "ring_c"),
       _gb("epoxy compounds", 522, "saturated three-membered cyclic ether"),
       "The epoxides subclass only (oxirane); a larger cyclic ether is an ether."),
    _f("fg:acetal", "acetal", ("acetal_c", "acetal_o"),
       _gb("acetals", 19, "R2C(OR')2 (R' != H)"),
       "Includes ketals (p. 803, a subclass). Saturated carbon, two single-"
       "bonded O, each bonded to carbon."),
    _f("fg:hemiacetal", "hemiacetal", ("acetal_c", "hydroxy_o", "ether_o"),
       _gb("hemiacetals", 667, "R2C(OH)OR'"),
       "Includes lactols and hemiketals."),
    _f("fg:aminal", "aminal", ("aminal_c", "n"),
       _gb("aminals", 72, "R2C(NR2)2"),
       "Saturated carbon, two single-bonded trivalent N. Any such N, acylated "
       "included (an amide N-CH2-N is still two N on one carbon); the N stay "
       "the amines or amides they are."),
    _f("fg:hemiaminal", "hemiaminal", ("aminal_c", "o", "n"),
       _gb("hemiaminals", 667, "R2C(OH)NR2; R2C(OR')NR2"),
       "Both: alpha-amino alcohols and the hemiaminal ethers the entry names "
       "(R' != H, not acyl). The O is the hemiaminal's; the N stays its amine."),
    _f("fg:thioacetal", "thioacetal", ("acetal_c", "s", "o"),
       _gb("thioacetals", 1536, "R2C(OR')(SR'); R2C(SR')2"),
       "Mono- and dithioacetals, R' carbon. An N,S-acetal is not one; the Gold "
       "Book names none."),
    _f("fg:acylal", "acylal", ("acylal_c", "ester_o", "carbonyl_c", "carbonyl_o"),
       _gb("acylals", 34, "diesters of geminal diols, e.g. benzylidene diacetate"),
       "Saturated carbon bearing two single-bonded O, each acylated by a "
       "carboxylic acyl (carbon or H on the carbonyl); ring or chain, so "
       "Meldrum's acid is the cyclic acylal of acetone. One ester and one ether O "
       "is not a diester; a monoester (the second O bears H) is not either."),
    _f("fg:peroxide", "peroxide", ("peroxy_o",),
       _gb("peroxides", 1085, "ROOR"), "Both R organyl."),
    _f("fg:hydroperoxide", "hydroperoxide", ("peroxy_o", "hydroxy_o"),
       _gb("hydroperoxides", 699, "ROOH"),
       "R any organyl, acyl included (the entry: those are peroxy acids)."),
    # --- nitrogen --------------------------------------------------------
    _f("fg:primary_amine", {_N: "primary amine", _C: "primary ammonium"},
       ("amine_n",), _gb("amines", 73, "RNH2"),
       "R hydrocarbyl: N bonded only to H and to carbons that carry no =O, =S "
       "or =N (those are amides, amidines, ...). Aryl counts (aniline). "
       "Cationic is the protonated amine, R-NH3+."),
    _f("fg:secondary_amine", {_N: "secondary amine", _C: "secondary ammonium"},
       ("amine_n",), _gb("amines", 73, "R2NH"),
       "As primary, two carbons; a ring N (piperidine) counts -- the ring is "
       "reported too, as a ring system."),
    _f("fg:tertiary_amine", {_N: "tertiary amine", _C: "tertiary ammonium"},
       ("amine_n",), _gb("amines", 73, "R3N"),
       "As primary, three carbons. Not an aromatic ring N (pyridine), which "
       "belongs to its ring."),
    _f("fg:quaternary_ammonium", {_C: "quaternary ammonium"}, ("ammonium_n",),
       _gb("quaternary ammonium compounds", 1217, "(R4N+)Y-"),
       "Four hydrocarbyl groups; C=N+ is iminium instead (the entry says so)."),
    _f("fg:amine_oxide", "amine oxide", ("amine_n", "oxide_o"),
       _gb("amine oxides", 73, "R3N+-O-"),
       "Non-aromatic N; the heteroarene N-oxide is its own structural feature."),
    _f("fg:hydroxylamine", "hydroxylamine", ("amine_n", "hydroxy_o"),
       _gb("hydroxylamines", 701, "H2N-OH"),
       "And hydrocarbyl derivatives; N not acylated (that is a hydroxamic acid)."),
    _f("fg:hydrazine", "hydrazine", ("n",),
       _gb("hydrazines", 693, "H2NNH2"),
       "Both N single-bonded and not acylated (the entry: acyl makes a "
       "hydrazide, alkylidene a hydrazone)."),
    _f("fg:azo", "azo", ("azo_n",), _gb("azo compounds", 139, "PhN=NPh"),
       "Both N substituents hydrocarbyl."),
    _f("fg:azide", "azide", ("n",), _gb("azides", 138, "-N=N+=N-"),
       "Sense 1: the N3 group on carbon."),
    _f("fg:diazo", "diazo", ("diazo_c", "n"),
       _gb("diazo compounds", 409, "=N+=N- on carbon"), "As written."),
    _f("fg:diazonium", {_C: "diazonium"}, ("n",),
       _gb("diazonium salts", 409, "RN+#N"), "As written."),
    _f("fg:nitro", "nitro", ("nitro_n", "nitro_o"),
       _gb("nitro compounds", 996, "-NO2"),
       "On carbon, nitrogen or oxygen (a nitrate ester), as the entry allows."),
    _f("fg:nitroso", "nitroso", ("nitroso_n", "nitroso_o"),
       _gb("nitroso compounds", 997, "-NO"), "On carbon, nitrogen or oxygen."),
    # --- sulfur ----------------------------------------------------------
    _f("fg:thiol", {_N: "thiol", _A: "thiolate"}, ("sulfanyl_s",),
       _gb("thiols", 1538, "RSH"),
       "R carbon, and not acyl (a thioacid). Anionic is the thiolates entry."),
    _f("fg:sulfide", "sulfide (thioether)", ("sulfide_s",),
       _gb("sulfides", 1479, "RSR (R != H)"),
       "Both R hydrocarbyl; a non-aromatic S (thiophene S belongs to its ring)."),
    _f("fg:disulfide", "disulfide", ("s",),
       _gb("polysulfides", 1161, "R-[S]n-R"),
       "n = 2 only. The entry notes some chemists exclude disulfides; this "
       "vocabulary includes them, which is the entry's primary reading."),
    _f("fg:sulfenic_acid", {_N: "sulfenic acid", _A: "sulfenate"}, ("s", "o"),
       _gb("sulfenic acids", 1478, "RSOH (R != H)"),
       "R hydrocarbyl. The Blue Book discards the name for 'thioperoxol' "
       "(P-56.2) but the Gold Book's class stands, and this vocabulary follows "
       "the Gold Book. Anionic is the sulfenate. An O-hydrocarbyl compound "
       "R-S-O-R' is not this: no source names it as a class."),
    _f("fg:sulfenamide", "sulfenamide", ("s", "amide_n"),
       _gb("sulfenamides", 1477, "RSNR2"),
       "Sulfenic acids with -OH replaced by -NR2. The N is neutral and "
       "trivalent and carries no double bond; an N-acyl one is still a "
       "sulfenamide, the entry restricting nothing on N. Neither S nor N is "
       "aromatic: an aromatic S-N (isothiazole, and the benzisothiazolinone "
       "RDKit perceives aromatic) is the ring system's."),
    _f("fg:sulfoxide", "sulfoxide", ("s", "o"),
       _gb("sulfoxides", 1483, "R2S=O"), "Both R carbon."),
    _f("fg:sulfinic_acid", {_N: "sulfinic acid", _A: "sulfinate"},
       ("s", "oxo_o", "hydroxy_o"),
       _gb("sulfinic acids", 1480, "RS(=O)OH"),
       "S-hydrocarbyl, the entry's own words; the parent HS(=O)OH has no organyl "
       "group. Anionic is the sulfinate."),
    _f("fg:sulfinic_ester", "sulfinic ester", ("s", "oxo_o", "ester_o"),
       _gb("esters", 528, "RkE(=O)l(OH)m ester, E = S, l = 1"),
       "Sulfinic acid has l = 1, so its esters are esters proper of the entry. "
       "S carbon, O carbon; a sulfite (S bears no carbon) is not one."),
    _f("fg:sulfinamide", "sulfinamide", ("s", "oxo_o", "amide_n"),
       _gb("sulfinamides", 1480, "RS(=O)NR2"),
       "As the entry writes it; R carbon, N not bonded to N (a sulfinohydrazide "
       "is not in this version)."),
    _f("fg:sulfone", "sulfone", ("s", "o"),
       _gb("sulfones", 1482, "RS(=O)2R"), "Both R carbon."),
    _f("fg:sulfonic_acid", {_N: "sulfonic acid", _A: "sulfonate"},
       ("s", "oxo_o", "hydroxy_o"),
       _gb("sulfonic acids", 1482, "RS(=O)2OH"), "R carbon."),
    _f("fg:sulfonic_ester", "sulfonic ester", ("s", "oxo_o", "ester_o"),
       _gb("esters", 528, "R'S(=O)2(OR)"), "Both R carbon."),
    _f("fg:sulfate_ester", {_N: "sulfate ester", _A: "sulfate ester"},
       ("s", "oxo_o", "ester_o", "acid_o"),
       _gb("esters", 528, "RkE(=O)l(OH)m ester, E = S, k = 0"),
       "Mono- or di-esters of sulfuric acid; a monoester is often drawn as O-."),
    _f("fg:sulfonamide", "sulfonamide", ("s", "oxo_o", "amide_n"),
       _gb("sulfonamides", 1481, "RS(=O)2NR'2"), "R carbon."),
    _f("fg:sulfamide", "sulfamide", ("s", "oxo_o", "amide_n"),
       _gb("amides", 69, "RkE(=O)l(OH)m amide, E = S, k = 0"),
       "Sulfuric acid is an oxoacid of the amides entry's form, so N-SO2-N is an "
       "amide of it, as carbonic diamide is; a sulfonamide's S bears carbon."),
    _f("fg:sulfamate", {_N: "sulfamate", _A: "sulfamate"}, ("s", "oxo_o", "amide_n", "o"),
       _gb("sulfamic acids", 1477, "H2NS(=O)2OH"),
       "The acid, its N-hydrocarbyl derivatives (the entry), its salts and its "
       "O-esters (the esters entry): N-SO2-O."),
    # --- phosphorus, boron, silicon --------------------------------------
    _f("fg:phosphonic_acid", {_N: "phosphonic acid", _A: "phosphonate"},
       ("p", "oxo_o", "hydroxy_o"),
       _gb("phosphonic acids", 1100, "RP(=O)(OH)2"),
       "P-hydrocarbyl; at least one OH (or O-) and no O-carbon ester."),
    _f("fg:phosphinic_acid", {_N: "phosphinic acid", _A: "phosphinate"},
       ("p", "oxo_o", "hydroxy_o"),
       _gb("phosphinic acids", 1099, "H2P(=O)OH"),
       "Its P-hydrocarbyl derivatives: one OH (or O-) and two C, or C and H."),
    _f("fg:phosphonate_ester", "phosphonate ester", ("p", "oxo_o", "ester_o", "acid_o"),
       _gb("esters", 528, "RkE(=O)l(OH)m ester, E = P"),
       "P bearing one carbon, =O, and at least one O-carbon."),
    _f("fg:phosphate_ester", {_N: "phosphate ester", _A: "phosphate ester"},
       ("p", "oxo_o", "ester_o", "acid_o"),
       _gb("esters", 528, "(HO)2P(=O)(OR)"),
       "P bearing four O, at least one bonded to carbon."),
    _f("fg:phosphine", "phosphine", ("p",),
       _gb("phosphines", 1099, "R3P"), "Trivalent P with H or carbon only."),
    _f("fg:phosphine_oxide", "phosphine oxide", ("p", "o"),
       _gb("phosphine oxides", 1099, "R3P=O"), "Three carbons on P."),
    _f("fg:boronic_acid", "boronic acid", ("b", "hydroxy_o"),
       _gb("boronic acids", 179, "RB(OH)2"),
       "R carbon. No anionic state: the boronate anion is a tetrahedral "
       "RB(OH)3-, a different drawing, not RB(OH)O-."),
    _f("fg:boronic_ester", "boronic ester", ("b", "ester_o"),
       _gb("boronic acids", 179, "RB(OR')2"),
       "Not an 'ester proper' by the esters entry's note (boronic acid has no "
       "=O); named from the boronic acids entry, R and R' carbon (pinacol "
       "boronates)."),
    _f("fg:silanol", "silanol", ("si", "hydroxy_o"),
       _gb("silanols", 1377, "R3SiOH"), "Sense 2, the common one."),
    _f("fg:silyl_ether", "silyl ether", ("si", "ether_o"),
       _gb("ethers", 528, "R3SiOR"),
       "The ethers entry's own parenthesis: silicon analogues of ethers. The "
       "O bears carbon; the Si's R is unrestricted, so a trialkoxysilane's "
       "three Si-O-C are three (found by the Ertl cross-check)."),
    _f("fg:siloxane", "siloxane", ("si", "o"),
       _gb("siloxanes", 1379, "H3Si[OSiH2]nOSiH3"),
       "Si-O-Si; hydrocarbyl derivatives included, as the entry says."),
    # --- halogen ---------------------------------------------------------
    _f("fg:fluoro", "fluoro", ("halogen",),
       _bb("halogen compounds", 507, "P-61.3.1", "fluoro prefix"),
       "The Gold Book has no class entry for halogen compounds. Halogen bonded "
       "to carbon; on an acyl carbon it is an acyl halide instead."),
    _f("fg:chloro", "chloro", ("halogen",),
       _bb("halogen compounds", 507, "P-61.3.1", "chloro prefix"),
       "As fluoro: the Gold Book has no class entry for halogen compounds."),
    _f("fg:bromo", "bromo", ("halogen",),
       _bb("halogen compounds", 507, "P-61.3.1", "bromo prefix"),
       "As fluoro: the Gold Book has no class entry for halogen compounds."),
    _f("fg:iodo", "iodo", ("halogen",),
       _bb("halogen compounds", 507, "P-61.3.1", "iodo prefix"),
       "As fluoro: the Gold Book has no class entry for halogen compounds. A "
       "hypervalent iodine (iodonium) is an onium centre."),
    # --- carbon ----------------------------------------------------------
    _f("fg:alkene", "alkene (C=C)", ("c",),
       _gb("olefins", 1024, "C=C, apart from the formal ones in aromatic compounds"),
       "The olefins entry, not alkenes (p. 59), which is a hydrocarbon CLASS "
       "(acyclic CnH2n) rather than a group. Every non-aromatic C=C between "
       "NEUTRAL carbons: a charged carbon is the carbocation or carbanion it "
       "is (a vinyl cation or phenylium matched as a cationic alkene)."),
    _f("fg:alkyne", "alkyne (C#C)", ("c",),
       _gb("acetylenes", 19, "C#C"),
       "The acetylenes entry for the same reason; every C#C between neutral "
       "carbons (an acetylide is a carbanion)."),
    # --- charged centres -------------------------------------------------
    _f("fg:onium", {_C: "onium"}, ("onium_centre",),
       _gb("onium compounds", 1027, "sulfonium, phosphonium, oxonium, iodonium, ..."),
       "Senses 1-2 for every family EXCEPT nitrogen, which is covered by the "
       "amine charge states and quaternary ammonium.",
       by_element={"S": "sulfonium", "P": "phosphonium", "O": "oxonium",
                   "I": "iodonium", "Se": "selenonium", "As": "arsonium",
                   "Br": "bromonium", "Cl": "chloronium"}),
    # --- structural features ---------------------------------------------
    _f("sf:aromatic_nh", "aromatic N-H (pyrrole type)", ("n",),
       _gb("heteroarenes", 671, "-NH- replacing a vinylene group"),
       "The divalent heteroatom the heteroarenes entry describes: an aromatic "
       "N bearing H.", category=_SF),
    _f("sf:heteroarene_n_oxide", "heteroarene N-oxide", ("n", "o"),
       _gb("heteroarenes", 671, "heteroarene N with an exocyclic O-"),
       "The Gold Book has no N-oxides entry, and amine oxides are 'derived from "
       "amines', which a pyridine is not. An aromatic N+ bearing O-.",
       category=_SF),
    _f("sf:alpha_beta_unsaturated_carbonyl", "alpha,beta-unsaturated carbonyl",
       ("carbonyl_c", "carbonyl_o", "alpha_c", "beta_c"),
       _gb("conjugated system (conjugation)", 322, "CH2=CH-C#N (alternating bonds)"),
       "C=C-C=O with the C=C non-aromatic: a conjugated system in the entry's "
       "original sense. Shown beside the groups it overlaps (the Michael "
       "acceptor motif), never instead of them.", category=_SF),
    _f("sf:carbocation", {_C: "carbocation"}, ("c",),
       _gb("carbocation", 205, "cation with an even-electron carbon centre"),
       "A carbon with formal charge +1.", category=_SF),
    _f("sf:acylium_ion", {_C: "acylium ion"}, ("acyl_c", "acyl_o"),
       _gb("acyl species", 33, "R-C+=O, R-C#O+ (acyl cations)"),
       "The entry's acyl cations, synonym acylium ions, formally derived from an "
       "oxoacid by removal of HO-. The entry leaves the acid-generating element "
       "open; this version reads carbon only: a carbon with two neighbours, one "
       "of them a terminal O, drawn as C+=O or as C#O+ (the two resonance "
       "forms). The C+=O form is also a carbocation, and says so (CONTAINS).",
       category=_SF),
    _f("sf:carbanion", {_A: "carbanion"}, ("c",),
       _gb("carbanion", 201, "anion with an even-electron carbon centre"),
       "A carbon with formal charge -1 (cyclopentadienide, acetylide).",
       category=_SF),
)

#: Lookup by id; ids are unique (`validate_vocabulary` checks).
FEATURE_BY_ID: dict[str, FeatureDefinition] = {f.feature_id: f for f in FEATURES}
#: Declared position, the sort key every projection orders its output by.
FEATURE_ORDER: dict[str, int] = {f.feature_id: i for i, f in enumerate(FEATURES)}


# --- relations ---------------------------------------------------------------


class RelationKind(str, Enum):
    """What one feature is to another, as CHEMISTRY -- not as display.

    A relation holds between two instances when the object's atoms are a
    subset of the subject's (SUPPRESSES, CONTAINS) or when they intersect
    (OVERLAPS). EXCLUDES is an invariant: the two may never be detected on
    the same atoms, and a detection that does is a pattern defect.
    """

    SUPPRESSES = "suppresses"   # the object is not the primary description of its atoms
    CONTAINS = "contains"       # the subject is a specific kind of the object
    OVERLAPS = "overlaps"       # both are primary descriptions
    EXCLUDES = "excludes"


@dataclass(frozen=True)
class FeatureRelation:
    subject: str
    kind: RelationKind
    object: str
    why: str


#: Short forms for the RELATIONS table.
_S, _K, _O, _X = (RelationKind.SUPPRESSES, RelationKind.CONTAINS,
                  RelationKind.OVERLAPS, RelationKind.EXCLUDES)

#: Every declared relation between two features. Each SUPPRESSES, CONTAINS
#: and OVERLAPS entry has an overlap fixture in the coverage matrix; EXCLUDES
#: entries are invariants checked over every fixture.
RELATIONS: tuple[FeatureRelation, ...] = (
    FeatureRelation("fg:lactam", _K, "fg:carboxamide", "a lactam is a cyclic carboxamide (p. 815)"),
    FeatureRelation("fg:lactone", _K, "fg:carboxylic_ester", "a lactone is a cyclic ester (p. 817)"),
    FeatureRelation("fg:imide", _S, "fg:carboxamide",
                    "the diacyl nitrogen is one imide, not two amides (p. 710)"),
    FeatureRelation("fg:imide", _S, "fg:lactam", "a cyclic imide is not described as a lactam"),
    FeatureRelation("fg:epoxide", _S, "fg:ether", "an epoxide is a cyclic ether (p. 522)"),
    FeatureRelation("fg:acetal", _S, "fg:ether", "an acetal is a diether of a geminal diol (p. 19)"),
    FeatureRelation("fg:hemiacetal", _S, "fg:ether", "its ether oxygen belongs to the hemiacetal"),
    FeatureRelation("fg:hemiacetal", _S, "fg:alcohol", "its OH belongs to the hemiacetal"),
    FeatureRelation("fg:enol", _S, "fg:alkene", "an enol is an alkenol; its C=C is part of it (p. 512)"),
    FeatureRelation("fg:hemiaminal", _S, "fg:alcohol", "its OH belongs to the hemiaminal (p. 667)"),
    FeatureRelation("fg:hemiaminal", _S, "fg:ether", "a hemiaminal ether's O belongs to it (p. 667)"),
    FeatureRelation("fg:thioacetal", _S, "fg:sulfide", "a thioacetal's S belongs to it (p. 1536)"),
    FeatureRelation("fg:thioacetal", _S, "fg:ether", "a monothioacetal's O belongs to it (p. 1536)"),
    *(FeatureRelation("fg:acyl_halide", _S, f"fg:{x}",
                      "the halogen of an acyl halide is not a halo substituent")
      for x in ("fluoro", "chloro", "bromo", "iodo")),
    FeatureRelation("sf:alpha_beta_unsaturated_carbonyl", _O, "fg:alkene",
                    "the motif is reported beside its C=C, not instead of it"),
    FeatureRelation("sf:alpha_beta_unsaturated_carbonyl", _O, "fg:ketone",
                    "the motif is reported beside its carbonyl, not instead of it"),
    FeatureRelation("fg:alcohol", _X, "fg:phenol", "saturated vs aromatic carbon"),
    FeatureRelation("fg:alcohol", _X, "fg:enol", "saturated vs vinylic carbon"),
    FeatureRelation("fg:phenol", _X, "fg:enol", "aromatic vs non-aromatic C=C"),
    FeatureRelation("fg:phenol", _X, "fg:heteroarenol", "the carbon's smallest ring: carbocyclic vs hetero"),
    FeatureRelation("fg:primary_amine", _X, "fg:secondary_amine", "H count on N"),
    FeatureRelation("fg:primary_amine", _X, "fg:tertiary_amine", "H count on N"),
    FeatureRelation("fg:secondary_amine", _X, "fg:tertiary_amine", "H count on N"),
    FeatureRelation("fg:aldehyde", _X, "fg:ketone", "one H vs none"),
    FeatureRelation("fg:carboxamide", _X, "fg:urea", "a urea's carbonyl carbon bears no carbon"),
    FeatureRelation("fg:carboxylic_ester", _X, "fg:carbamate", "a carbamate's carbonyl bears N"),
    # v3. Each is justified by the SOURCE'S definition, not by "more specific".
    FeatureRelation("fg:acylal", _S, "fg:carboxylic_ester",
                    "an acylal is a diester of a geminal diol, described once as "
                    "an acylal, as an acetal is a diether (p. 34)"),
    FeatureRelation("sf:acylium_ion", _K, "sf:carbocation",
                    "an acylium ion is a carbocation of a particular kind (p. 33)"),
)

#: Which (subject category, kind, object category) may be declared. Anything
#: else is rejected at import. RING_SYSTEM CONTAINS FUNCTIONAL_GROUP holds
#: generically -- ring systems are open-ended names from the ring perception,
#: not vocabulary entries -- so it is applied by category, never declared.
ALLOWED_CATEGORY_RELATIONS: frozenset[tuple[FeatureCategory, RelationKind, FeatureCategory]] = frozenset({
    (FeatureCategory.RING_SYSTEM, RelationKind.CONTAINS, FeatureCategory.FUNCTIONAL_GROUP),
    (FeatureCategory.STRUCTURAL_FEATURE, RelationKind.OVERLAPS, FeatureCategory.FUNCTIONAL_GROUP),
    # An acylium ion is a carbocation of a particular kind (v3): both are
    # structural features, so a specific one may contain the general one.
    (FeatureCategory.STRUCTURAL_FEATURE, RelationKind.CONTAINS, FeatureCategory.STRUCTURAL_FEATURE),
    (FeatureCategory.FUNCTIONAL_GROUP, RelationKind.SUPPRESSES, FeatureCategory.FUNCTIONAL_GROUP),
    (FeatureCategory.FUNCTIONAL_GROUP, RelationKind.CONTAINS, FeatureCategory.FUNCTIONAL_GROUP),
    (FeatureCategory.FUNCTIONAL_GROUP, RelationKind.EXCLUDES, FeatureCategory.FUNCTIONAL_GROUP),
})


# --- projections -------------------------------------------------------------


class Projection(str, Enum):
    FUNCTIONAL_GROUPS = "functional_groups"
    FRAGMENT_COUNTS = "fragment_counts"
    ATOM_INSPECTOR = "atom_inspector"


class ObjectTreatment(str, Enum):
    """What a projection does with the OBJECT of a relation that holds."""

    HIDDEN = "hidden"                 # not shown / not counted
    SHOWN = "shown"                   # shown and counted like any other
    SHOWN_NESTED = "shown_nested"     # shown under its subject
    SHOWN_NON_PRIMARY = "shown_non_primary"


#: Each projection declares how it reads each relation kind (plan B0 table).
#: The subject is always shown; this says what happens to the object.
PROJECTION_POLICY: dict[Projection, dict[RelationKind, ObjectTreatment]] = {
    Projection.FUNCTIONAL_GROUPS: {
        RelationKind.SUPPRESSES: ObjectTreatment.HIDDEN,
        RelationKind.CONTAINS: ObjectTreatment.SHOWN_NESTED,
        RelationKind.OVERLAPS: ObjectTreatment.SHOWN,
    },
    Projection.FRAGMENT_COUNTS: {
        RelationKind.SUPPRESSES: ObjectTreatment.HIDDEN,
        # A lactam is counted as a lactam and NOT also as an amide.
        RelationKind.CONTAINS: ObjectTreatment.HIDDEN,
        RelationKind.OVERLAPS: ObjectTreatment.SHOWN,
    },
    Projection.ATOM_INSPECTOR: {
        RelationKind.SUPPRESSES: ObjectTreatment.SHOWN_NON_PRIMARY,
        RelationKind.CONTAINS: ObjectTreatment.SHOWN,
        RelationKind.OVERLAPS: ObjectTreatment.SHOWN,
    },
}


# --- the naming engine's vocabulary -------------------------------------------

#: Engine group type -> the feature ids an instance of it may correspond to.
#: The engine's types answer a nomenclature question and are a second
#: detector here, never a definition. Where a type spans several features
#: (the engine's `ester` covers lactones) every candidate is listed.
ENGINE_GROUP_MAP: dict[str, tuple[str, ...]] = {
    "carboxylic_acid": ("fg:carboxylic_acid",),
    "diazonium": ("fg:diazonium",),
    "aminium": ("fg:primary_amine", "fg:secondary_amine", "fg:tertiary_amine",
                "fg:quaternary_ammonium"),
    "peroxy_acid": ("fg:hydroperoxide",),
    "sulfonic_acid": ("fg:sulfonic_acid",),
    "phosphonic_acid": ("fg:phosphonic_acid",),
    "boronic_acid": ("fg:boronic_acid",),
    "carbamate": ("fg:carbamate",),
    "ester": ("fg:carboxylic_ester", "fg:lactone"),
    "sulfonate_ester": ("fg:sulfonic_ester",),
    "thioester": ("fg:thioester",),
    "thionoester": ("fg:thioester",),
    "dithioester": ("fg:thioester",),
    "acyl_chloride": ("fg:acyl_halide",),
    "acyl_bromide": ("fg:acyl_halide",),
    "acyl_fluoride": ("fg:acyl_halide",),
    "acyl_iodide": ("fg:acyl_halide",),
    "acyl_isothiocyanate": ("fg:isothiocyanate",),
    "sulfonyl_chloride": ("fg:acyl_halide",),
    "sulfonyl_bromide": ("fg:acyl_halide",),
    "sulfonyl_fluoride": ("fg:acyl_halide",),
    "sulfonyl_iodide": ("fg:acyl_halide",),
    # The engine names urea as carbonic diamide, so its amide types land on
    # ureas too (measured: NC(N)=O, and a diarylurea's secondary_amide).
    "amide": ("fg:carboxamide", "fg:lactam", "fg:urea"),
    "secondary_amide": ("fg:carboxamide", "fg:lactam", "fg:urea"),
    "tertiary_amide": ("fg:carboxamide", "fg:lactam", "fg:urea"),
    "imidamide": ("fg:amidine",),
    "sulfonamide": ("fg:sulfonamide",),
    "thioamide": ("fg:thioamide", "fg:thiourea"),
    "secondary_thioamide": ("fg:thioamide",),
    "tertiary_thioamide": ("fg:thioamide",),
    "hydroxamic_acid": ("fg:hydroxamic_acid",),
    "hydrazide": ("fg:hydrazide",),
    "nitrile": ("fg:nitrile",),
    "aldehyde": ("fg:aldehyde",),
    "ketone": ("fg:ketone",),
    "thione": ("fg:thioketone",),
    "alcohol": ("fg:alcohol", "fg:enol"),
    "phenol": ("fg:phenol", "fg:heteroarenol"),
    "peroxol": ("fg:hydroperoxide",),
    "thiol": ("fg:thiol",),
    "amine": ("fg:primary_amine",),
    "secondary_amine": ("fg:secondary_amine",),
    "tertiary_amine": ("fg:tertiary_amine",),
    "imine": ("fg:imine",),
    "substituted_imine": ("fg:imine",),
    "fluoro": ("fg:fluoro",),
    "chloro": ("fg:chloro",),
    "bromo": ("fg:bromo",),
    "iodo": ("fg:iodo",),
    "nitro": ("fg:nitro",),
    "nitroso": ("fg:nitroso",),
    "nitrooxy": ("fg:nitro",),
    "nitrosooxy": ("fg:nitroso",),
    "azido": ("fg:azide",),
    "diazo": ("fg:diazo",),
    "isothiocyanato": ("fg:isothiocyanate",),
    "isocyanato": ("fg:isocyanate",),
    "isocyano": ("fg:isocyanide",),
    "hydroperoxy": ("fg:hydroperoxide",),
    "guanidino": ("fg:guanidine",),
    "urea": ("fg:urea",),
    "sulfonatooxy": ("fg:sulfate_ester",),
    "ring_tertiary_amine": ("fg:tertiary_amine",),
    "ring_secondary_amine": ("fg:secondary_amine",),
    "aromatic_amine_nh": ("sf:aromatic_nh",),
    # v3: types that were unmapped in v2 because the vocabulary had no feature.
    "carbothioic_O_acid": ("fg:thiocarboxylic_acid",),
    "carbothioic_S_acid": ("fg:thiocarboxylic_acid",),
    "carbodithioic_acid": ("fg:thiocarboxylic_acid",),
    "thionocarbamate": ("fg:thiocarbamate",),
    "carbamothioate": ("fg:thiocarbamate",),
    "dithiocarbamate": ("fg:thiocarbamate",),
    "thial": ("fg:thioaldehyde",),
    "cyanato": ("fg:cyanate",),
    "thiocyanato": ("fg:thiocyanate",),
    "sulfinic_acid": ("fg:sulfinic_acid",),
    "sulfinamide": ("fg:sulfinamide",),
    # The engine's `sulfenate` is R-S-O-, the anion of a sulfenic acid.
    "sulfenate": ("fg:sulfenic_acid",),
}

#: Why the selenium and tellurium engine types are unmapped.
_CHALCOGEN = ("a selenium or tellurium analogue; the Gold Book names these only "
              "by extension of their oxygen/sulfur parents, and none occurs in "
              "either naming corpus")
#: Why the non-sulfonic sulfur oxoacid engine types are unmapped.
_S_ACID = ("a sulfur oxoacid or amide outside the sulfonic family; no Gold Book "
           "class entry, and none occurs in either naming corpus")
#: Engine types with NO feature in this vocabulary, each with why. An
#: instance of one is still shown -- labelled as the naming engine's term,
#: under the namespace ``iupac:`` -- so an unusual group is never silently
#: dropped; it is just not claimed by a definition this vocabulary has.
ENGINE_GROUP_FALLBACK: dict[str, str] = {
    **{t: _CHALCOGEN for t in (
        "selenonic_acid", "seleninic_acid", "telluronic_acid", "tellurinic_acid",
        "selenonimidic_acid", "selenonodiimidic_acid", "sulfenoselenoate",
        "tellurosulfenate", "selenonate", "telluronate", "seleninate",
        "tellurinate", "tellurolate", "selenolate", "selenonamide",
        "seleninamide", "telluronamide", "tellurinamide", "carboselenoic_Se_acid",
        "selone", "tellone", "selenol")},
    **{t: _S_ACID for t in (
        "sulfinimidic_acid", "sulfonimidic_acid",
        "sulfonodiimidic_acid", "sulfinothioic_O_acid", "sulfonothioic_S_acid",
        "sulfinohydrazonic_acid", "sulfonohydrazonic_acid",
        "sulfenothioate", "sulfonothioamide", "sulfonodithioamide",
        "sulfinothioamide", "sulfinimidamide", "sulfonimidamide",
        "sulfonodiimidamide", "sulfinohydrazonamide", "sulfonohydrazonamide",
        "sulfinohydrazonohydrazide", "sulfonatoamino")},
    "arsonic_acid": "no Gold Book class entry; arsenic oxoacids are out of scope",
    "carboximidic_acid": ("the imidic-acid tautomer of an amide; the vocabulary "
                          "preserves the drawn tautomer but defines no feature for "
                          "this rare one"),
    "carboximidothioic_acid": ("as carboximidic_acid, with sulfur: the S-H form is a "
                               "thiol as drawn (fg:thioimidate reads S-hydrocarbyl "
                               "esters only)"),
    "iodyl": "a hypervalent iodine group; not in this version",
    "iodosyl": "a hypervalent iodine group; not in this version",
}


#: Classes CONSIDERED for the vocabulary and refused, each with why. A structured
#: status rather than a silence: "not detected" and "never looked at" are
#: different claims, and the Ertl cross-check (`ertl_mapping.toml`) reports
#: the atoms of the first two as uncovered. A class comes off this table only
#: by getting a definition from a named source.
EXCLUDED_CLASSES: dict[str, str] = {
    "N,S-acetal": (
        "R2C(NR2)(SR'), penicillin's thiazolidine carbon. No source names the "
        "class: the Gold Book's aminals (p. 72) are N,N, its hemiaminals (p. 667) "
        "N,O and its thioacetals (p. 1536) S,S and S,O, and neither the 1995 "
        "glossary nor the Blue Book has an N,S entry (searched). Ertl's algorithm "
        "marks the carbon, which is the oracle's finding and does not make it a "
        "class; a definition written here would be this vocabulary's own. The "
        "amine or amide and the sulfide on it are covered."),
    "sulfenic ester (sulfenate, R-S-O-R')": (
        "The Gold Book's sulfenic acids entry (p. 1478) is RSOH, and its esters "
        "entry needs an oxoacid with l != 0, which a sulfenic acid lacks; the "
        "Blue Book (P-63.4.2) names R-S-O-R' with the sulfanyloxy prefix, not "
        "as a class."),
    "thiuram disulfide": (
        "R2N-C(=S)-S-S-C(=S)-NR2: the Blue Book names it a trithiodicarbonic "
        "diamide (P-66.1.6.3, p. 663), so it is neither two thiocarbamates (each "
        "S bears S, not carbon) nor a disulfide of two organyl groups."),
    "sulfinohydrazide": (
        "RS(=O)NR-NR2: the hydrazide analogue of a sulfinamide. Sulfonohydrazides "
        "are hydrazides in v2; the sulfinic one has no Gold Book entry and does "
        "not occur in either corpus."),
    "selenium and tellurium analogues": (
        "Named by the Gold Book only by extension of their oxygen and sulfur "
        "parents, and none occurs in either naming corpus."),
    "hypervalent iodine (iodosyl, iodyl)": (
        "The Gold Book has no entry for the I=O or IO2 groups (searched; its "
        "'hypervalent' entry is the bonding description, not a class). The "
        "iodonium centre is fg:onium."),
    "arsenic oxoacids": (
        "The Gold Book names arsonic and arsinic acids only inside other "
        "entries, with no headword of their own (searched), so there is no "
        "definition to operationalise; arsenic is out of scope."),
    "inorganic species with no organyl group": (
        "Water, ammonia, borates, phosphoric acid, carbon disulfide, the cyanate "
        "and thiocyanate anions, azide ion: every class here is defined on "
        "organyl groups, so these are reported as components of the structure."),
    "aromatic ring heteroatoms": (
        "A ring system by design (heteroarenes, Gold Book p. 671), never a "
        "functional group; the pyrrole-type [nH] is sf:aromatic_nh."),
}


#: Where the two vocabularies DISAGREE, and the definition settles it, as
#: (engine type, v2 feature the same atoms are, or None for "no feature") ->
#: why. Found by running both detectors over the naming corpora; the
#: cross-check test fails on any disagreement not listed here, so a new one
#: is a decision someone has to write down rather than drift.
ENGINE_DISAGREEMENTS: dict[tuple[str, str | None], str] = {
    ("ketone", "fg:lactam"): (
        "a ring C=O beside a ring N: the engine's oxo prefix, a lactam here "
        "(p. 815). FG-002, the defect this vocabulary exists to fix (caffeine)"),
    ("ketone", "fg:imide"): "a ring C=O between two acyl N bonds is an imide (p. 710); FG-002",
    ("ketone", "fg:urea"): "caffeine's C2=O bears two N: a urea, not a ketone; FG-002",
    ("ketone", "fg:lactone"): "a coumarin's C=O beside the ring O is a lactone (p. 817); FG-002",
    ("ketone", "fg:carboxamide"): (
        "a carbonyl on a ring or azo NITROGEN (indometacin's N-acylindole): the engine names it a PSEUDOKETONE, suffix 'one' "
        "(P-64.3.2, p. 567, naming round 8), where the Gold Book class of the same atoms is an amide"),
    ("amine", "fg:guanidine"): "an NH2 of a guanidine is part of the guanidine, not an amine",
    ("secondary_amine", "fg:guanidine"): "as amine: an N of a guanidine",
    ("tertiary_amine", "fg:guanidine"): "as amine: an N of a guanidine (metformin)",
    ("boronic_acid", None): "boric acid B(OH)3 is not a boronic acid, RB(OH)2 with R carbon (p. 179)",
    ("phosphonic_acid", None): "phosphoric acid is not a phosphonic acid, RP(=O)(OH)2 (p. 1100)",
}


def validate_vocabulary() -> list[str]:
    """Every inconsistency in the declarations above, as sentences.

    Called at import (below), so a malformed vocabulary cannot load.
    """
    problems: list[str] = []
    seen: set[str] = set()
    for f in FEATURES:
        if f.feature_id in seen:
            problems.append(f"{f.feature_id}: declared twice")
        seen.add(f.feature_id)
        prefix = {"fg": FeatureCategory.FUNCTIONAL_GROUP,
                  "sf": FeatureCategory.STRUCTURAL_FEATURE}.get(f.feature_id.split(":")[0])
        if prefix is not f.category:
            problems.append(f"{f.feature_id}: id namespace does not match category {f.category.value}")
        if not f.labels:
            problems.append(f"{f.feature_id}: no charge state")
        if not f.roles or len(set(f.roles)) != len(f.roles):
            problems.append(f"{f.feature_id}: roles missing or repeated")
        if len(f.roles) > 9:
            problems.append(f"{f.feature_id}: more than 9 roles cannot be map-numbered")
        d = f.definition
        if d.source is DefinitionSource.GOLD_BOOK and not 1 <= d.page <= GOLD_BOOK_PAGES:
            problems.append(f"{f.feature_id}: Gold Book page {d.page} out of range")
        if d.source is DefinitionSource.BLUE_BOOK and not d.section.startswith("P-"):
            problems.append(f"{f.feature_id}: Blue Book definition without a rule number")
        if not d.term or not d.formula or not f.operationalisation:
            problems.append(f"{f.feature_id}: definition incomplete")
    for r in RELATIONS:
        for end in (r.subject, r.object):
            if end not in FEATURE_BY_ID:
                problems.append(f"relation {r}: unknown feature {end}")
        if r.subject in FEATURE_BY_ID and r.object in FEATURE_BY_ID:
            triple = (FEATURE_BY_ID[r.subject].category, r.kind, FEATURE_BY_ID[r.object].category)
            if triple not in ALLOWED_CATEGORY_RELATIONS:
                problems.append(f"relation {r.subject} {r.kind.value} {r.object}: "
                                f"category combination not allowed")
        if r.subject == r.object:
            problems.append(f"relation {r.subject}: relates to itself")
    for engine_type, targets in ENGINE_GROUP_MAP.items():
        if engine_type in ENGINE_GROUP_FALLBACK:
            problems.append(f"engine type {engine_type}: both mapped and unmapped")
        for t in targets:
            if t not in FEATURE_BY_ID:
                problems.append(f"engine type {engine_type}: maps to unknown {t}")
    for (engine_type, feature_id), why in ENGINE_DISAGREEMENTS.items():
        if engine_type not in ENGINE_GROUP_MAP:
            problems.append(f"disagreement for unmapped engine type {engine_type}")
        if feature_id is not None and feature_id not in FEATURE_BY_ID:
            problems.append(f"disagreement names unknown feature {feature_id}")
        if feature_id in ENGINE_GROUP_MAP.get(engine_type, ()):
            problems.append(f"{engine_type} -> {feature_id} is mapped, not a disagreement")
    for p, policy in PROJECTION_POLICY.items():
        missing = {RelationKind.SUPPRESSES, RelationKind.CONTAINS, RelationKind.OVERLAPS} - set(policy)
        if missing:
            problems.append(f"projection {p.value}: no treatment for {sorted(m.value for m in missing)}")
    return problems


#: Checked once, at import, so a malformed vocabulary cannot load at all.
_PROBLEMS = validate_vocabulary()
if _PROBLEMS:  # pragma: no cover - the test suite calls validate_vocabulary itself
    raise ValueError("feature vocabulary is inconsistent:\n  " + "\n  ".join(_PROBLEMS))
