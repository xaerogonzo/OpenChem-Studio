"""NL-021 (WS3): Blue Book sources for heteroatom spiro joints (round 88 / D-384).

Sources read 2026-11-10 from BlueBookV2.pdf (IUPAC 2013). The engine's emitted names for the
D-384 shapes are pinned in ``tests/test_namer_round88_spiro_joints_to_bridged_partners_and_hetero_spiro_atoms.py``
and OPSIN-round-trip there; this file records *which book rules apply* and whether the spelling
matches the PIN examples.
"""

from __future__ import annotations

# (limitation id, Blue Book rule, pdf page, short applicability note)
NL_021_SOURCES = (
    (
        "P-24.5.2",
        183,
        "Heteroatoms in a monospiro system use skeletal-replacement ('a') prefixes before "
        "'spiro' (e.g. 3-thiaspiro[...]); the older spiro[polycycle-9,2′-[3]thiabicyclo...] "
        "format is no longer recommended.",
    ),
    (
        "P-24.5.4",
        185,
        "When both components are modified by 'a' nomenclature, spiro fusion is preferred to "
        "replacement prefixes for low locants (3,3′-dioxaspiro[...] PIN).",
    ),
    (
        "P-24.8.4.1",
        192,
        "A nonstandard-bonding-number hetero spiro atom: λ symbol at the front with the lowest "
        "spiro locant (3H-2λ5-spiro[[1,3,2]benzoxazaphosphole-2,2′-...] PIN).",
    ),
    (
        "P-73.4",
        828,
        "Cationic heterocycles may use skeletal replacement; 'azonia' is a preselected parent name "
        "(1-methyl-1-azoniabicyclo[2.2.1]heptane).",
    ),
    (
        "P-73.4 / examples",
        829,
        "Polycyclic onium spiro examples include 5-arsoniaspiro[4.4]nonane and "
        "9-phosphonia-9,9′-spirobi[fluorene] beside the λ5 spirobi PIN.",
    ),
)

# Engine pins (OPSIN read-back in round 88) vs book-style notes for the three NL-021 motifs.
SPELLINGS = (
    (
        "silicon spiro atom cited in both partners",
        "C1CC2CC1C[Si]23CCCC3",
        "spiro[silolane-1,2'-2-silabicyclo[2.2.1]heptane]",
        "OPSIN-readable; book P-24.5.2 would carry sila replacement once at the spiro level "
        "rather than sila/silolane in both brackets (no identical book PIN for this drawing).",
    ),
    (
        "azonia before a polycyclic partner",
        "C1CCC2C(C1)CC[N+]21CCC1",
        "1-azoniaspiro[cyclobutane-1,1'-octahydro-1H-indene]-1-ium",
        "Matches the P-73.4 onium-spiro pattern (<loc>-azonia...-ium).",
    ),
    (
        "phosphonia spiro",
        "C1CC[P+]2(C1)CC1CCC2C1",
        "2-phosphoniaspiro[bicyclo[2.2.1]heptane-2,1'-cyclopentane]-2-ium",
        "Matches P-829 phosphonia-spirobi style for a quaternary P+ spiro centre.",
    ),
)


def test_nl021_five_book_passages_are_recorded():
    assert len(NL_021_SOURCES) == 5
    pages = [row[1] for row in NL_021_SOURCES]
    assert pages == sorted(pages)


def test_nl021_three_engine_motifs_are_documented_with_sources():
    assert len(SPELLINGS) == 3
    smileses = {row[1] for row in SPELLINGS}
    assert len(smileses) == 3
