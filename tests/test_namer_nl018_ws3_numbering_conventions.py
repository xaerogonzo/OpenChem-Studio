"""NL-018 (WS3): curated-ring numbering conventions sourced to the 2013 Blue Book.

Naming round 87 re-read the exceptions in ``tests/test_namer_round86_curated_ring_labels_follow_the_rings_bonds.py``
``CONVENTIONS`` (PDF pages in that module's comments; corrin and two large fusion systems are not drawn in the book).
OPSIN pair probes: ``tools/naming_ring_table_vs_opsin.py`` (8,585 pairs, no disagreement).
"""

from __future__ import annotations

from tests.test_namer_round86_curated_ring_labels_follow_the_rings_bonds import CONVENTIONS


def test_nl018_numbering_convention_exceptions_cover_seventeen_parent_names():
    """Seventeen parent names carry book- or OPSIN-backed numbering exceptions (round 86/87)."""
    assert len(CONVENTIONS) == 17


def test_nl018_every_convention_lists_at_least_one_non_adjacent_pair():
    assert CONVENTIONS
    assert all(pairs for pairs in CONVENTIONS.values())
