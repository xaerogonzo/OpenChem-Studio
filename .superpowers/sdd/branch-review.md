### Strengths

- The slice stays inside its boundary. Domain code does not import RDKit. `assess_pka_compatible` never calls `balance_two`. `compose_supplied_ions` never calls `assess_pka_compatible` or `formula_unit_conserved`. There is no UI, no Mode C product, no ladder adapter, and no pKa sidecar in the tests.
- `choose_ionization` and `assess_pka_compatible` follow the plan, including the order that matters: a mismatched `step_id` is `wrong_step` with no delta, and ΔpKa is conjugate acid minus acid only after medium and temperature match. Already-charged input returns `not_assessed` and drops the delta.
- The ion catalog keeps hydrogen sulfate and sulfate as different rows, stores each `ion_smiles` in `fragment_key` form (the loader raises otherwise), and refuses a charge that disagrees with the graph. `docs/sources.toml` registers `salt_ion_catalog` with no DOI. The generated sources doc is current.
- Net-charge listing does not tautomer-canonicalize. 4-hydroxybenzoic acid at charge −1 stays two graphs and is refused as `ambiguous_microspecies`. Acetic acid at −1 is acetate. The N/O/P/S gate that makes that true is explained in `salt_ionization.py`, and the comment matches this RDKit pin: a full heavy-atom pass also yields `[CH2-]C(=O)O`, `CC(O)=[OH+]`, and `CC(=O)[OH2+]`.
- Two supplied ions balance through `balance_two` only. A molecular neutral mixed into that path is `missing_proton_source`.
- Checked this session: `tests/test_salt_stoichiometry.py`, `tests/test_salt_evidence.py`, `tests/test_salt_ionization.py`, `tests/test_ionic_species.py`, `tests/test_layering.py`, and `test_no_constant_has_fallen_out_of_documentation` — 48 passed. Architecture module count, chem package-map names, and changelog fragments — 33 passed. Source-registry schema, `used_by`, generated `SOURCES.md`, shipped data tables, and the DOI sweep — 357 passed, 1 skipped.

### Issues

#### Critical (Must Fix)

None.

#### Important (Should Fix)

1. **Deprotonation ignores a hydrogen that is an atom**
   - File: `src/openchem/chem/salt_ionization.py:40-46`
   - What is wrong: `GetTotalNumHs()` defaults to `includeNeighbors=False`, so it counts the hydrogen property and misses a neighboring hydrogen atom. On `Chem.AddHs(Chem.MolFromSmiles("CC(=O)O"))` the carboxylic OH reports `GetTotalNumHs() == 0` while `GetTotalNumHs(True) == 1`, and `apply_site_transform(..., "deprotonate")` returns `invalid_site` ("that atom has no hydrogen to remove"). The plan's deprotonation rule requires an explicit or implicit hydrogen. This is the acetic-acid direction the slice exists to perform, and a molblock or drawing that stores hydrogens as atoms takes this path.
   - Why it matters: the refusal looks like a bad site. Protonation of that same oxygen does run, and the hydrogen count happens to rise by one (`[H][OH+]C(=O)C([H])([H])[H]`, site `GetTotalNumHs(True) == 2`), because the old hydrogen atom is left in place and a new hydrogen property is added. A fix that only switches on `includeNeighbors` and then calls `SetNumExplicitHs(total - 1)` will not delete the atom, and on protonation it will add a second hydrogen on top of the atoms already there.
   - Fix: count hydrogen atoms and the hydrogen property together. When removing a hydrogen, delete one neighboring H atom if one exists; otherwise lower the property. When adding one, add it in the same representation the rest of the molecule uses. `ionize_at_sites` indexes atoms on the updated molecule, so deleting an atom shifts later indexes — resolve each site before the deletion, or delete from the high index downward. Add a test on an `AddHs` acetic acid that deprotonates to the same `fragment_key` as `CC(=O)[O-]`, or to that key after the explicit hydrogens that were not removed are accounted for under the existing identity rule.

#### Minor (Nice to Have)

Ledger triage: none of these must be fixed before merge. Each was checked against the code. The explicit-hydrogen bug above is the only merge blocker.

1. **Duplicate identities in `choose_ionization` are untested**
   - File: `src/openchem/domain/salt_stoichiometry.py:202-207`
   - `dict.fromkeys` collapses duplicates, and a probe of `choose_ionization(["CC(=O)[O-]", "CC(=O)[O-]"])` returns the one string. The three shipped tests never pass a repeated string. Add that case when the file is next touched. Do not block.

2. **`EvidenceRecord`, mixed origin, and both temperatures `None` are untested**
   - File: `src/openchem/domain/salt_evidence.py:51-56` and `91-101`
   - Nothing constructs `EvidenceRecord`. The optional `evidence_for_supplied_ions` helper was left out; the plan marked it optional.
   - Comparable conditions are implemented as specified: origin is not read, and `None != None` is false, so two missing temperatures still record. A probe with measured/predicted origins, both temperatures `None`, and different ionic strengths returned `recorded`, delta `1.5`, and both origins still on the values. A regression that treats `None` as "missing temperature" would not be caught. Add those two assertions later. Do not block.

3. **The supplied-ion pKa test does not call `compose_supplied_ions`**
   - File: `tests/test_salt_evidence.py:23-31`
   - The test only calls `assess_pka_compatible(already_charged=True)`, which `test_already_charged_input_is_not_assessed` already covers. The plan's own snippet is written that way. The composition function does not import `salt_evidence`. The decoupling holds in the source; the test name overclaims. Do not block.

4. **`ionize_at_sites` has no test**
   - File: `src/openchem/chem/salt_ionization.py:54-67`; `tests/test_salt_ionization.py` never imports it.
   - A probe of both OH sites on `OS(=O)(=O)O` returned `O=S(=O)([O-])[O-]`, the catalog sulfate key. Implicit-hydrogen multi-site works. The explicit-hydrogen bug above is in `apply_site_transform`, which this function calls. Add the sulfate case with the explicit-hydrogen fix. Do not block on its own.

5. **Net-charge enumeration is limited to N/O/P/S**
   - File: `src/openchem/chem/salt_ionization.py:70-87`
   - The plan's algorithm sketch says every heavy atom, once in each direction. The code protonates N/P (and any atom that already carries a negative charge) and deprotonates N/O/P/S that have a hydrogen (and any atom that already carries a positive charge). Neutral carbon and neutral oxygen-as-base are omitted, so acetic acid at −1 stays a single structure and acetic acid at +1 stays `net_charge_only`. A full heavy-atom pass makes both of those tests fail on this RDKit. Thiol deprotonation is included (`CCS` → `CC[S-]`); sulfide and ether protonation are not (`CSC` and `COC` at +1 are empty). A named `SiteTransform` can still protonate those atoms.
   - This is a deliberate narrowing so the plan's acetic tests can pass. Reverting it without rewriting those tests would auto-refuse acetate. Put one sentence in the ionization table in `docs/SALT_COMPOSITION_DESIGN.md` so a later slice does not "restore" every heavy atom and lose acetate. The function docstring at `salt_ionization.py:90-96` should name the element gate too. Do not block.

6. **Catalog parent SMILES are the brief's spelling, not `fragment_key`**
   - File: `src/openchem/chem/data/ionic_species.json` (parents on the sulfate, phosphate, and nitrate rows); loader enforces the key only for `ion_smiles` at `src/openchem/chem/ionic_species.py:75-78`
   - Measured parent vs `fragment_key`: `OS(=O)(=O)O` → `O=S(=O)(O)O`, `OP(=O)(O)O` → `O=P(O)(O)O`, `O[N+](=O)[O-]` → `O=[N+]([O-])O`. Chloride, bromide, iodide, acetate, ammonium, and pyridinium parents already match. No function compares `parent_smiles` to a graph yet. The plan's JSON block wrote those parent strings, and the fragment-key rule in the plan names `ion_smiles`. Canonicalize the parents before any later slice joins on parent identity. Do not block.

### Recommendations

- Fix explicit-hydrogen deprotonation in this branch, with a test that would have failed today on `AddHs` acetic acid.
- When that test file is open, add the duplicate-identity case, the both-`None` temperature case, the mixed-origin case, and one `ionize_at_sites` assertion for sulfate.
- Add the N/O/P/S enumeration rule to the ionization table in `docs/SALT_COMPOSITION_DESIGN.md`.

### Assessment

**Ready to merge?** With fixes

**Ready to open a PR?** After the explicit-hydrogen deprotonation fix is on the branch. The six ledger notes are accurate and can ship as follow-up tests or a design sentence; they are not merge blockers.

**Reasoning:** Library behavior matches the plan: unique structures are accepted, net charge and ambiguous microspecies are refused, supplied ions balance without a proton inventory, pKa stays a named-step record, and the catalog is graphs rather than a whitelist. Deprotonation does not see a hydrogen stored as an atom, which is the one break in the site-transform rule. The slice tests and the doc/source guards that cover this diff passed.
