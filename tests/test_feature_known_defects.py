"""The v1 functional-group defects, FG-001 onward, and what v2 does instead.

Each row pins the v2 result THROUGH THE PROJECTIONS (what Functional Groups
shows, what Fragment Counts counts) and records what v1 produced, MEASURED on
2026-09-18 at 2bfc01b with `collect_features` and `compute_fragment_group_alert`
-- the formers are data, not assertions, because v1 is what branch B
replaces. Every expected result follows from a definition in
`feature_vocabulary.py`, cited there by Gold Book page; the row names it.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

import pytest
from rdkit import Chem

from openchem.chem.feature_vocabulary import ObjectTreatment, Projection
from openchem.chem.structural_features import detect_features, project


@dataclass(frozen=True)
class Defect:
    id: str
    smiles: str
    what: str
    #: v1, measured: Functional Groups (key[atoms]) and Fragment Counts.
    v1_functional_groups: tuple[str, ...]
    v1_fragment_counts: tuple[str, ...]
    #: v2: what Functional Groups shows, as "label[atoms]".
    shows: tuple[str, ...]
    #: v2: what Fragment Counts counts, by feature id.
    counts: dict[str, int]
    source: str


DEFECTS = (
    Defect("FG-001", "CC(=O)Nc1ccccc1",
           "an N-monosubstituted amide labelled 'secondary', and its N counted as an amine",
           ("secondary_amide[1, 2, 3, 4]",),
           ("Amide (1)", "Secondary Amine (1)", "Benzene Ring (1)"),
           ("amide[1, 2, 3]",), {"fg:carboxamide": 1},
           "amides p. 69 note 1: NH2/NHR/NR2 amides are not primary/secondary/tertiary"),
    Defect("FG-002", "Cn1c(=O)c2c(ncn2C)n(C)c1=O",
           "caffeine's ring C=O claimed as ketones, and its four N as tertiary amines",
           ("ketone[12, 13]", "ketone[2, 3]"),
           ("Tertiary Amine (4)", "Imidazole (1)"),
           ("imide[1, 2, 3, 12, 13]", "urea[1, 10, 12, 13]"),
           {"fg:imide": 1, "fg:urea": 1},
           "imides p. 710; urea P-66.1.6.1.1 (Blue Book, no Gold Book entry)"),
    Defect("FG-002b", "CCC1(c2ccccc2)C(=O)NC(=O)NC1=O",
           "phenobarbital: no functional group at all in v1",
           (), ("Amide (4)", "Secondary Amine (2)", "Benzene Ring (1)", "Urea (1)"),
           ("imide[9, 10, 11, 12, 13]", "imide[12, 13, 14, 15, 16]", "urea[11, 12, 13, 14]"),
           {"fg:imide": 2, "fg:urea": 1},
           "imides p. 710; urea P-66.1.6.1.1"),
    Defect("FG-003", "CC(=O)[O-]",
           "a carboxylate not detected by Functional Groups; counted as the ACID by Fragment Counts",
           (), ("Carboxylic Acid (1)",),
           ("carboxylate[1, 2, 3]",), {"fg:carboxylic_acid": 1},
           "carboxylic acids p. 215, anionic state"),
    Defect("FG-003b", "[O-]c1ccccc1",
           "a phenolate: nothing", (), ("Benzene Ring (1)",),
           ("phenolate[0]",), {"fg:phenol": 1}, "phenolates p. 1095"),
    Defect("FG-003c", "CS(=O)(=O)[O-]",
           "a sulfonate: nothing in either", (), (),
           ("sulfonate[1, 2, 3, 4]",), {"fg:sulfonic_acid": 1}, "sulfonic acids p. 1482"),
    Defect("FG-004", "NC(N)=O",
           "urea as an amide, and its NH2 counted as primary amines",
           ("amide[0, 1, 3]",), ("Amide (2)", "Primary Amine (2)", "Urea (1)"),
           ("urea[0, 1, 2, 3]",), {"fg:urea": 1},
           "urea P-66.1.6.1.1; a carboxamide's carbonyl bears carbon (p. 214)"),
    Defect("FG-005", "CC(OC)OC",
           "an acetal shown as two ethers", ("ether[1, 2, 3]", "ether[1, 4, 5]"), ("Ether (2)",),
           ("acetal[1, 2, 4]",), {"fg:acetal": 1}, "acetals p. 19; acetal SUPPRESSES ether"),
    Defect("FG-005b", "CC1CO1",
           "an epoxide shown as an ether, and counted as both", ("ether[1, 2, 3]",),
           ("Ether (1)", "Epoxide (1)"),
           ("epoxide[1, 2, 3]",), {"fg:epoxide": 1}, "epoxy compounds p. 522"),
    Defect("FG-006", "CC[NH3+]",
           "one protonated amine under two keys from two detectors", ("aminium[2]", "ammonium[2]"), (),
           ("primary ammonium[2]",), {"fg:primary_amine": 1},
           "amines p. 73, cationic state; one vocabulary, engine mapped into it"),
    Defect("FG-007", "CC=C", "a C=C: nothing in either", (), (),
           ("alkene (C=C)[1, 2]",), {"fg:alkene": 1}, "olefins p. 1024"),
    Defect("FG-007b", "CS(C)=O", "DMSO: nothing in either", (), (),
           ("sulfoxide[1, 3]",), {"fg:sulfoxide": 1}, "sulfoxides p. 1483"),
    Defect("FG-007c", "C[N+](C)(C)[O-]",
           "an amine oxide: nothing in Functional Groups, a tertiary amine in Fragment Counts",
           (), ("Tertiary Amine (1)",), ("amine oxide[1, 4]",), {"fg:amine_oxide": 1},
           "amine oxides p. 73"),
    Defect("FG-007d", "COOC", "a peroxide: nothing", (), (),
           ("peroxide[1, 2]",), {"fg:peroxide": 1}, "peroxides p. 1085"),
    Defect("FG-007e", "CSSC", "a disulfide: nothing", (), (),
           ("disulfide[1, 2]",), {"fg:disulfide": 1}, "polysulfides p. 1161"),
    Defect("FG-007f", "C[NH3+].[Cl-]",
           "a chloride COUNTER-ION counted as a halogen substituent (found driving master "
           "2bfc01b, not predicted); the ammonium itself counted as nothing",
           ("aminium[1]", "ammonium[1]"), ("Halogen (1)",),
           ("primary ammonium[1]",), {"fg:primary_amine": 1},
           "halogen compounds P-61.3 (a halogen on carbon); a counter-ion is a component"),
    Defect("FG-008", "CC(C)=NO",
           "an oxime as a substituted imine, and counted as a tertiary amine",
           ("substituted_imine[1, 3]",), ("Tertiary Amine (1)",),
           ("oxime[1, 3, 4]",), {"fg:oxime": 1}, "oximes p. 1052"),
    Defect("FG-008b", "c1ccccc1N=Nc1ccccc1",
           "an azo compound counted as two tertiary amines", (),
           ("Tertiary Amine (2)", "Benzene Ring (2)"),
           ("azo[6, 7]",), {"fg:azo": 1}, "azo compounds p. 139"),
    Defect("FG-008c", "C[N+](=O)[O-]", "a nitro group counted as a tertiary amine too",
           ("nitro[0, 1, 2, 3]",), ("Tertiary Amine (1)", "Nitro (1)"),
           ("nitro[1, 2, 3]",), {"fg:nitro": 1}, "nitro compounds p. 996"),
    Defect("FG-008d", "CN=[N+]=[N-]", "an azide counted as three tertiary amines",
           ("azido[0, 1, 2, 3]",), ("Tertiary Amine (3)",),
           ("azide[1, 2, 3]",), {"fg:azide": 1}, "azides p. 138"),
    Defect("FG-008e", "CN=C=O", "an isocyanate counted as a tertiary amine",
           ("isocyanato[0, 1, 2, 3]",), ("Tertiary Amine (1)",),
           ("isocyanate[1, 2, 3]",), {"fg:isocyanate": 1}, "isocyanates p. 778"),
    Defect("FG-008f", "c1ccncc1",
           "a pyridine N counted as a tertiary amine; it belongs to its ring", (),
           ("Tertiary Amine (1)", "Pyridine (1)"), (), {},
           "amines p. 73 (hydrocarbyl on N); a ring N is the heteroarene's (p. 671)"),
    Defect("FG-009", "O=C1CCCO1",
           "a lactone counted as an ester AND an ether", (), ("Ester (1)", "Ether (1)"),
           ("carboxylic ester[0, 1, 5]", "lactone[0, 1, 5]"), {"fg:lactone": 1},
           "lactones p. 817; lactone CONTAINS ester: shown nested, counted once"),
    Defect("FG-009b", "CC(=O)OC(C)=O",
           "an anhydride counted as two esters and an ether", (), ("Ester (2)", "Ether (1)"),
           ("carboxylic anhydride[1, 2, 3, 4, 6]",), {"fg:carboxylic_anhydride": 1},
           "acid anhydrides p. 21"),
)


def _shows(features) -> Counter:
    return Counter(
        f"{p.feature.label}{sorted(p.feature.atoms)}"
        for p in project(features, Projection.FUNCTIONAL_GROUPS)
        if p.treatment is not ObjectTreatment.HIDDEN
    )


def _counts(features) -> Counter:
    return Counter(
        p.feature.feature_id
        for p in project(features, Projection.FRAGMENT_COUNTS)
        if p.treatment is not ObjectTreatment.HIDDEN
    )


@pytest.mark.parametrize("defect", DEFECTS, ids=lambda d: d.id)
def test_v2_fixes_the_defect(defect):
    features = detect_features(Chem.MolFromSmiles(defect.smiles))
    assert _shows(features) == Counter(defect.shows)
    assert _counts(features) == Counter(defect.counts)


def test_every_defect_says_what_v1_did_and_why_v2_differs():
    ids = [d.id for d in DEFECTS]
    assert len(ids) == len(set(ids))
    for d in DEFECTS:
        assert d.what and d.source
        assert d.v1_functional_groups != d.shows or d.v1_fragment_counts, d.id
