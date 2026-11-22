# Results, Properties, and Quantum Chemistry: design

**Status: design, 2026-11-16. No product code in this document.** User-facing help for *today's* behaviour is in `docs/USER_GUIDE.md` (`help:properties`, `help:results`, `help:batch`, `help:quantum-chemistry`). This note is what a later implementation must not invent on the fly.

Quantum chemistry is conceptually more calculators with extra steps. Operationally it stays a separate inspector. Results becomes the place a person *reads, compares, and deletes* history from both, without starting a job.

## 1. The user problem

Running calculators is tedious because methods and engines multiply. A learner needs one path that does not pretend a goal **Run** and **Apply to Properties** are the same button. An advanced user needs every method they actually ran kept, collapsible under the quantity it answers, independently deletable, and comparable when the inputs honestly match.

Partial Charge (3D) is the example that makes the gap visible. The calculator offers six models: EEM (Bultinck), QEq, two Ionescu EEM parameterisations, NEEMP EEM, and Jiroušková EEM. Running QEq after EEM must not throw EEM away. The selected/default view may be indicated; the others stay listed. The same rule applies to Quantum Chemistry: a B3LYP/def2-SVP ORCA job and an M06-2X job are distinct; ORCA and Psi4 never share a label even when the functional name matches (they already differ by 37 mEh on water).

A method family is never expanded because a calculator is ticked or included in a bulk run. A person may explicitly request the complete family from a calculator that declares a family axis. That action runs each declared choice in sequence, on one selected molecule and one captured input, using the same remaining settings. Ordinary OK, Run selected, and Project table Fill continue to run one method.

## 2. Learner and advanced paths (shipped controls)

**Learner**

1. **Tools ▸ Run Calculators by Goal…** (or **Run by goal…** in Properties).
2. **Run recommended** when the curated ordinary set should run now.
3. **Customise… → Apply to Properties** when the ticks should land in Properties for inspection. That copies ticks and settings and closes the wizard. **It does not run.**
4. **Run selected** or **Fill table** to execute the ordinary plan.
5. An optional Quantum radio **stages** the Quantum Chemistry panel. Inspect, then **Run** there.

**Advanced**

- Tick ordinary calculators in Properties. Choose method, model, and parameters on **that calculator's settings**, not on a new global Method combo. The registry has no single meaning for “method” that would cover every row.
- **Run selected**.
- Use the Quantum Chemistry panel directly for engine, charge, multiplicity, geometry, and **Run**.

**Apply to Properties** must never read as another Run. Quantum radios must never read as starting ORCA, Psi4, or xtb. Staging today uses `PropertyPanel.current_scope()`, not the wizard's own **Run on** box; `decide_stage()` refuses `all` and `chosen` and requires one selected molecule. That wizard-versus-Properties mismatch is a later UI fix, not something this spec authorises as a batch Quantum path.

Results does not launch or rerun calculations. Opening, filtering, comparing, or deleting must not start a job.

## 3. What exists today

Three roles, all of which have stores after the Results history hub (#630, #631). The cache is still not job history.

### Result cache — `SessionResultStore`

Documented in `src/openchem/domain/result_store.py` as a bounded revision cache: enough to undo a handful of edits without recomputing; **not a history**.

`ResultIdentity` carries `producer` and `parameters_key`. `SessionResultStore.put()` keys the dictionary on `(result_id, calculation_input, input_fingerprint, method_version)` only. **Producer and parameters key are not in the slot key.** Recording `parameters_key` is not a parameter-aware historical store.

`CURRENT_METHOD_VERSIONS` is an algorithm/implementation revision for a short list (fragment counts, geometry analysis, surface analysis, atom SASA, steric analysis, interaction analysis). It is not the user's selected chemical method (EEM versus QEq).

`to_dict(current_fingerprints)` writes only results that still match the molecule's current drawing or geometry. `ProjectService` supplies those fingerprints on save. In memory, revisions per calculation input are capped (`MAX_REVISIONS` / Settings).

Automatic calculation bundles list the result IDs a part produced. Deleting a cache row without updating that manifest can make a restore recompute the part.

### Quantum job history — `QuantumChemistryRunStore`

Documented in `src/openchem/domain/quantum_chemistry_run.py` as a **separate, durable collection** for exactly this reason: widening the cache key would change `fresh_results()`, `_trim()`, and `bundle_state()` for every other calculator.

A run has `run_id`, molecule UUID, calculation type, provider/engine, method and basis, charge and multiplicity, calculation input and fingerprint, input molblock and conformer identity, times, terminal status, warnings, output-conformer identity, result bundle and output statuses. The unit is the **run**, not one result ID: one job may file a spectrum, descriptors, and an optimized geometry together.

Terminal runs persist unconditionally, including when the input no longer matches the current structure. In-flight `RUNNING` is not written.

Delete goes through `ResultStoreService.delete_quantum_chemistry_run()`: the project is dirty, `QuantumChemistryRunDeleted` is published, recipe answers that consumed the run become stale, **the reusable wavefunction cache is not purged**.

The Quantum Chemistry panel already has a runs combo, delete, and **Compare NMR Shifts** (two NMR runs, same molecule, refuses unsafe atom numbering). That is not general Quantum-job compare, and not cross-molecule compare.

### Property calculation history — `PropertyExecutionStore`

Documented in `src/openchem/domain/property_execution.py`. A dedicated collection, independent of `SessionResultStore.put()` keys: each ordinary calculator invocation that is history-worthy mints a `PropertyExecution` (execution id, producer, method/model, parameters key, fingerprints, status, outputs). Identical cache hits still mint a new execution. Always-on descriptors, structural alerts, and Quantum cache projections (`source_run_id`) stay current-value rows only.

`fresh_results()` still picks the best retained method version for each `(result_id, calculation_input)` slot. That projection is not the history; Results reads executions from this store.

## 4. Architecture: Option B (shipped)

Keep the cache. Keep the Quantum run store. Keep the **dedicated property-execution history**. Results is a **read-only aggregation** over typed sources; delete and compare route to the owning service.

**Rejected: Option A** (inflate `SessionResultStore` into history) unless a later implementation plan proves the cache contract — replay, trim, bundles, fingerprint save — survives unchanged. Do not count “two stores” by pretending the cache is already history.

```
Results hub (UI, no jobs)
  ├─ PropertyExecutionStore      (ordinary calculator invocations)
  ├─ QuantumChemistryRunStore
  └─ SessionResultStore          (cache / fresh projection only)
Properties  → writes cache + property executions
QC panel    → writes Quantum runs; may also file cache projections
Project table → across-molecule matrix of the Properties plan; Quantum stays off Fill
```

Do not merge property executions and Quantum runs into one generic object that loses “one calculator invocation” versus “one multi-output ab initio job.”

## 5. Identities

Do not conflate:

1. **Selected method/model** — EEM, QEq, Ionescu, NEEMP, Jiroušková; functional, basis, engine.
2. **Parameter identity** — canonical settings; today's `parameters_key` belongs here, and must actually participate in history identity.
3. **Algorithm revision** — today's `method_version` for the few result IDs that have one.

A **property execution** has its own **execution ID**, minted at invocation, not reconstructed from result IDs. One invocation may produce several outputs (a molecular summary and a per-atom table). Those outputs stay grouped under that execution.

A **Quantum job** keeps `run_id`.

**Identical repeats mint a new execution ID.** “Every job” means a second Run with the same method and parameters is a second history row. The cache may still deduplicate an identical payload in its slot; history does not collapse the two clicks. Deduplicating history is a later Settings option, not the default.

## 6. Results hub

For the selected molecule:

- **Ordinary properties**
  - Calculator / quantity
    - Method or model group (collapsible)
      - Individual execution (deletable)
        - Scalar values, per-atom results, charts, tables, viewer links
- **Quantum chemistry**
  - Calculation family
    - Individual job: engine, method/basis, charge, multiplicity, conformer, time, status (deletable)
      - Spectrum, vibrational analysis, descriptors, optimized geometry, other outputs

A historical result must never look like a fresh answer for the current structure. Fingerprint (and protonation, calculation input) mismatch is visible: labelled historical, not *(stale)* in a way that invites a silent refresh as the only story.

The Showing list may default to executions whose input still matches the current molecule, with historical groups one click away — not discarded.

The Project table remains the across-molecule matrix. Fill table still consumes the Properties plan. Quantum stays off ordinary Fill.

## 7. Retention (intended product, not the accident of today's cache)

| Question | Property execution history | Quantum run history (keep) | Result cache (keep) |
|---|---|---|---|
| Survive a changed drawing or conformer? | Yes, labelled historical | Yes | In memory until trim; **not** written on save if fingerprints differ |
| Survive save and reopen? | Yes | Yes | Only current-fingerprint rows |
| New conformer? | Separate execution if the run used that geometry | Separate run | Separate fingerprint slot |
| New protonation? | Separate execution | Separate run (input snapshot) | Different input |
| Failed / cancelled? | Terminal failures and cancellations are history; in-flight is not persisted | Same (no RUNNING in the file) | Failures are not a durable job record |
| Cap? | Settings: at most N fingerprint-mismatched property executions per molecule. 0 (default) is unlimited. Confirm uses a deletion preview (so 0→5 can ask; 5→0 never does). Current-input repeats are unbounded. | Unconditional terminal runs | Existing revision limit |

The cache continues to answer “what should Properties replay for this structure right now.” History answers “what did I run.”

## 8. Delete

**Property execution.** Confirmation names the method/model and says the execution and **all outputs belonging to it** go. Other methods for the same quantity stay. The project is dirty. Results and compare candidates update. Nothing reruns. The molecule, its conformers, and unrelated executions stay.

Because automatic bundles live on the **cache**, history delete must not punch a hole in a bundle manifest. The cache row that still represents “fresh for this structure” is a separate question (open decision 5 and 6). v1 recommendation: deleting a history execution does not rewrite bundle manifests; if that execution was also the cache's current slot, the hub stops presenting it as current and the next Run fills the cache again in the ordinary way.

**Quantum run.** Keep today's history-only delete: one `run_id`, notify, stale recipes, no wavefunction purge. Confirmation names the job. Optimized conformers already on the molecule **stay** — geometry lifecycle is not the history record's lifecycle.

**Quantum projections in the cache.** Some descriptors and per-atom datasets are filed both on the run and in `SessionResultStore`. v1 recommendation: those cache rows carry a source `run_id`. Deleting the run withdraws projections that name it. Independently computed ordinary results stay.

## 9. Compare

Adjacency in the UI is not compatibility. Refuse with an explanation rather than a numerical difference that is an artefact.

**Ordinary methods** already distinguish property id, method, and parameter key in Properties compare. Also require: same molecule *or* an explicit cross-molecule rule; same calculation input type; same structure or geometry fingerprint for per-atom work; same atom mapping; same protonation; compatible units and quantity definition.

**Quantum today:** Compare NMR Shifts, same molecule, atom-numbering refusal. That is current behaviour.

**Ordinary versus Quantum (allowlist).** The Results history picker can list both property executions and Quantum runs. A mixed pair is compared only when it matches `MIXED_QUANTITIES` in `domain/history_compare.py`: stable ids, declared units, allowed Quantum calculation types, exactly one finite number each side. Display names are not a quantity. The list ships **empty**: no mixed pair is numerically comparable yet (ordinary dipole vs QC dipole is not listed; QC runs do not store a dipole; Hückel HOMO/LUMO is in beta, QC in eV; Miller polarizability has no QC counterpart). An unlisted pair is refused: no approved shared quantity is defined. NMR remains the only Quantum *per-atom* compare.

**Still later:**

- Same molecule, different Quantum method/engine, same calculation family (e.g. two NMR jobs, two single points) as a named family rule.
- Same quantity, different molecules — **scalars only** when the allowlist row sets `allow_cross_molecule`.

Per-atom arrays and NMR signals are not aligned across molecules merely because the output type matches.

## 10. Persistence and migration

Existing project files keep `calculation_results` as the cache and `quantum_chemistry_runs` as Quantum history. The hub reads both.

Old cache rows **do not** mint fake execution IDs on open. They appear as current-value rows without a history execution until the person runs that calculator again. Quantum runs already have `run_id` and appear as jobs.

A new project block for property executions is additive. An older app that does not know the block ignores it; a newer app that finds none shows cache + Quantum only.

## 11. Performance

History is per molecule, listed in Results for the selection. Do not load every execution of every molecule to paint one Showing list. Quantum already does this. The new store should answer “executions for this UUID” without a full-project scan as the hot path.

The Settings cap drops oldest *historical* (input is fingerprintable and no longer matches) property executions after a preview confirm. Default 0 is unlimited, so shipping the control does not delete history. Current-input repeats are not counted. Quantum runs and the cache are not limited here.

## 12. Open decisions

Recorded so an implementation plan cannot skip them. Recommendations above are the default if the implementation plan does not reopen them.

1. **History across edits** — keep historical property executions after drawing/geometry change; they survive save/reopen. Cache save rule unchanged.
2. **Identical repeat** — new execution ID. Cache may still no-op an identical payload.
3. **Failed attempts** — persist terminal failure/cancel for property executions; not in-flight.
4. **Retention cap** — shipped: Settings keeps at most N historical property executions per molecule (0 = unlimited). Confirm from the deletion preview, not a numeric old-vs-new comparison. Current-input repeats unbounded. Quantum, cache, bundles, and undo are out of scope.
5. **Delete vs bundles** — history delete does not edit automatic bundle manifests.
6. **Quantum output ownership** — cache projections that name a `run_id` withdraw with that run; others stay.
7. **Conformer ownership** — Quantum delete is history only; landed geometries stay.
8. **Comparison policy** — refuse incompatible pairs. Mixed ordinary-vs-Quantum compare is an explicit allowlist (`MIXED_QUANTITIES`); it ships empty. NMR remains the only Quantum per-atom compare. Cross-molecule mixed compare requires `allow_cross_molecule` on the matching row.
9. **Migration** — no invented execution IDs for old `calculation_results`; Quantum runs map 1:1.
10. **Current versus historical display** — current = input still matches the molecule; historical is listed and labelled, not used as the fresh answer.

**Also later, not this design's first build:** wizard scope versus Properties scope for Quantum staging; a global Method combo; putting Quantum on Properties ticks or Fill table.

## 13. Non-goals of the design slice

No UI, no new storage block, no service code. Implementation starts only from a reviewed plan that cites this file.
