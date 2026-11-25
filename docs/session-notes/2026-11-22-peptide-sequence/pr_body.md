## Summary

- Structure ▸ Peptide Sequence expands uppercase one-letter (`AEG`) or hyphenated three-letter (`Ala-Glu-Gly`) input into one connected atomistic L-peptide and inserts it through `insert_template_molblock` (2.0 Å right, one undo). It is not a Template Library category and not Ketcher polymer mode.
- Production builder is RDKit `MolFromSequence` on 2025.09.6 (measured: AEG 19 heavy atoms, two amides, InChIKey `PAIHPOGPJVUFJY-WDSKDSINSA-N`; Arg/His match the catalog by InChIKey with different tautomer SMILES). Grammar is the 20 standard residues, minimum length 2; D-residues, U, O, B/J/X/Z, `*`, HELM, and single residues are named refusals.
- Polymer S-groups are not in this PR. The existing Ketcher round-trip probe still shows `addFragment` dropping `M  STY`.

## Cross-links

Polymer catalog and S-group-preserving insert stay a later PR. No fork work.

## Verified

Base `cf25f565` (`origin/master`). Builder choice: `MolFromSequence` (not condensation; `MolFromFASTA` matched and was not kept as a second path).

`uv run --no-sync python -m pytest tests/test_peptide_sequence.py tests/test_peptide_sequence_dialog.py tests/test_peptide_sequence_insert.py tests/test_ketcher_sgroup_roundtrip.py tests/test_tooltip_coverage.py -q` → 63 passed, including Ketcher insert of AG / AEG / ACDEFGHIKL and the S-group regression probe.

`uv run --no-sync python -m pytest tests/test_menu_layout.py tests/test_keyboard_shortcuts.py tests/test_changelog_fragments.py tests/test_dialog_help_contracts.py -q` → passed aside from `test_suite_shards.py::test_the_glob_agrees_with_what_git_tracks` while the new files were still untracked.

2-mer / 3-mer / 10-mer insertion: Ketcher `getMolfile` kept one component, amide count n−1, heavy atoms 10 / 19 / 79.

OPENCHEM_DRIVE of `benchmarks/visual/peptide_sequence.json` was not launched in this session (starting the GUI was blocked); the Ketcher insert tests cover empty and occupied canvases on the same `insert_template_molblock` path.

Limitations: D/noncanonical/cyclic/capped peptides are refused; N-terminal proline is a secondary amine (pinned); polymer templates remain out.
