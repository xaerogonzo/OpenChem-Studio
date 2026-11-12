### Spec Compliance

- Spec compliant. `identifier_type = "bibliographic"` is the resolved registry type. No DOI in the JSON or the registry identifier.
- The review package is one commit, `7b87e211`, on base `638e5ed5`, message `Catalog named salt ions as graphs, with sulfate and hydrogen sulfate kept apart.` Files: `ionic_species.json`, `ionic_species.py`, `tests/test_ionic_species.py`, `docs/sources.toml`, `docs/SOURCES.md`, and a one-line `CLAUDE.md` key-files entry.
- This review did not re-run pytest. The implementer report states collection failed with `ModuleNotFoundError` (exit 2), then `tests/test_ionic_species.py` 4 passed, and `test_every_used_by_path_is_tracked_in_git` plus those four tests 5 passed after the JSON was tracked. `tools/build_sources_doc.py --check` was run in this review: `SOURCES.md is current (327 sources).` The recorded source hash matches `docs/sources.toml`.

Checked against the brief and `docs/SALT_COMPOSITION_DESIGN.md` (ionic-species registry, lines 384–398):

- Twelve rows, exact ids: `chloride`, `bromide`, `iodide`, `hydrogen_sulfate`, `sulfate`, `dihydrogen_phosphate`, `hydrogen_phosphate`, `phosphate`, `acetate`, `nitrate`, `ammonium`, `pyridinium`.
- `ion_smiles` is the `fragment_key` spelling. Hydrogen sulfate is `O=S(=O)([O-])O` (charge −1) and sulfate is `O=S(=O)([O-])[O-]` (charge −2). The three phosphates and nitrate are likewise rewritten; the halides, acetate, ammonium, and pyridinium already matched the brief.
- Load path is `Path(__file__).resolve().parent / "data" / "ionic_species.json"`. A charge that is not `fragment_formal_charge` raises `ValueError` naming the id. A stored ion SMILES that is not `fragment_key` raises as well. `REACHED_BY` is `tooling:`, a kind the reachability test accepts.
- `row_by_id("hexafluorophosphate")` is `None`. Presence of chloride is not a pharmaceutical allow-list. No pKa field.
- `salt_ion_catalog` is `kind = "dataset"`, `status = "shipped"`, `verification = "citation"`, `used_by` the JSON path. The structures-only paragraph is `reason` as specified and also `note`, because `tools/build_sources_doc.py` prints `reason` only when status is not `shipped` (`_render_entry_detail`). The generated page shows that paragraph and an empty DOI cell, which is how a bibliographic identifier is indexed.

`parent_smiles` stays the brief’s written SMILES. That matches the rewrite sentence, which names `ion_smiles` only, and the mandated round-trip test, which checks `row.ion_smiles` only. Sulfuric acid, phosphoric acid, and nitric acid parents are not the `fragment_key` form. That is a plan limit, not a miss against the listed parent strings.

The report’s `test_no_module_level_function_is_referenced_only_by_its_own_def` failure on `chem/salt_ionization.py::ionize_at_sites` is outside this diff. This commit does not define or call that function.

### Strengths

- Hydrogen sulfate and sulfate are different graphs and different charges (`ionic_species.json` hydrogen_sulfate and sulfate rows; `test_ionic_species.py:11-16`).
- The loader fails closed on a disagreeing charge, and the test proves it by rewriting the catalog on disk and expecting `ValueError` that names `chloride` (`ionic_species.py:65-74`, `test_ionic_species.py:35-44`). It also refuses a non-key ion SMILES, so Mode B’s `fragment_key` cannot miss a stored spelling (`ionic_species.py:75-78`).
- The registry entry does not invent a DOI. Bibliographic is a legal `identifier_type` (`tests/test_sources_are_current.py` `IDENTIFIER_TYPES`). The data table’s `_source_key` is `salt_ion_catalog`, so the shipped-data walk has a registry row.

### Issues

#### Critical (Must Fix)

None.

#### Important (Should Fix)

None.

#### Minor (Nice to Have)

- `tests/test_ionic_species.py:11-32` — the three brief tests plus the charge refusal do not lock the twelve ids or the rewritten SMILES. Dropping `phosphate`, or replacing `nitrate` with another charge −1 key, would still pass. The JSON currently holds the twelve graphs the brief names.
- `src/openchem/chem/ionic_species.py:79-81` — `parent_smiles` is accepted as any string. A parent that does not parse still loads. The shipped parents are the brief’s SMILES.

### Recommendations

- Compare a parent to a drawing with `fragment_key(MolFromSmiles(parent_smiles))`, not by string equality. `OS(=O)(=O)O`, `OP(=O)(O)O`, and `O[N+](=O)[O-]` are the brief’s spellings; their keys are `O=S(=O)(O)O`, `O=P(O)(O)O`, and `O=[N+]([O-])O`.
- Leave the parent strings as shipped. Rewriting them would depart from the brief’s listed parents and from the test the brief required.

### Assessment

**Task quality:** Approved

**Reasoning:** The catalog is twelve named ion graphs, with hydrogen sulfate and sulfate kept apart, an absent ion returned as missing, and a bibliographic source entry that carries no DOI. Ion identity is the fragment key; parent identity is the brief’s written SMILES and has to be keyed before a later match.
