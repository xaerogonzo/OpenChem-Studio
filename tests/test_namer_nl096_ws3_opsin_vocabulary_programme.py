"""NL-096 (WS3): OPSIN-extracted ring vocabulary is loaded and deliberately ungated.

Alex's 2026-09-19 decision (naming round 5, N5): refuse the whole vocabulary would drop
pyridine along with paracetamol. Counts match the plan row; audit of individual parents
was not attempted in this programme batch.
"""

from __future__ import annotations

from openchem.vendor.iupac_namer.data_loader import get_fusion_components, get_rings_from_opsin

RINGS_FROM_OPSIN = 705
FUSION_COMPONENTS = 821


def test_nl096_vocabulary_file_counts():
    assert len(get_rings_from_opsin()) == RINGS_FROM_OPSIN
    assert len(get_fusion_components()) == FUSION_COMPONENTS


def test_nl096_fusion_table_rows_are_structured():
    fusion = get_fusion_components()
    assert len(fusion) == FUSION_COMPONENTS
    for row in list(fusion.values())[:25]:
        assert isinstance(row, dict)
        assert row.get("parent_name")