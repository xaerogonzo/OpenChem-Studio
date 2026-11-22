## Summary

- Ships carboplatin, oxaliplatin, and cis-[PtCl2(en)] under `coordination_complexes` as connected molblocks (dative N/O→Pt). Insert keeps all three; haptic ferrocene stays out because Insert still returns an empty molfile.
- Freezes those three drawings in the Ketcher coordination probe (`addFragment` and `setMolecule`) and pins connectedness, dative counts, cis Cl–Pt–Cl on the en analog, and oxaliplatin's two chiral centres.
- Does not add polymer S-groups or a peptide sequence expander. Those wait on Insert preserving S-groups and on a measured sequence builder.

## After merge

Polymer templates and a peptide creator stay parked; they are a later session, not a follow-up commit on this branch.

## Verified

`uv run --no-sync python -m pytest tests/test_structure_templates.py tests/test_ketcher_coordination_roundtrip.py tests/test_changelog_fragments.py tests/test_no_competitor_names.py -q` on this tree: 59 passed in 57.38s.

`uv run --no-sync python tools/changelog.py check`: 76 fragments ok.
