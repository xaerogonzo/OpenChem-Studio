# Recipes: typed dependencies between calculators, and the Lewis pairing as the first one: design record

**Status: design, written 2026-10-12. Nothing in this document is built.** It is the first half of Phase 2 of the
plan in the session notes; the second half, user-defined derived scores, is
[`DERIVED_SCORES_DESIGN.md`](DERIVED_SCORES_DESIGN.md). Phase 1 (the assistant's calculator bridge,
[`AI_CALCULATION_BRIDGE.md`](AI_CALCULATION_BRIDGE.md)) is merged and this record builds on its vocabulary:
`Freshness`, the execution policy, the turn snapshot, the consent state machine. Where a review changes this
document, change it here first.

Every statement about how the application works today was read in the source on the date above and names the
function or file. Statements about what to build are decisions, and the ones most worth challenging are collected in
section 13. Three findings that are not decisions, but that the design had to be built around, are in section 14;
A and B have since been fixed (#312, #313) and the section says what changed.

## 1. What exists, and what that forces

| Fact | Where | What it forces |
|---|---|---|
| A goal is a flat list of calculators that run side by side: no step reads another step's output. `PropertyPanel.run_goal` never consults the execution policy, so the assistant reads goals as knowledge only. | `domain/calculator_goals.py`, `AI_CALCULATION_BRIDGE.md` section 14 | A recipe is a different object. It does not extend `Goal`, and `Goal` does not grow dependencies. |
| `compute_lewis_adduct` hands `predict` no quantum value. Its `one_way` calls `predict(acid, base, acid_uuid=..., base_uuid=...)` and nothing else, so in the application the frontier-gap and HSAB lines always read "not available". The only place all three lines are filled in is `tests/test_lewis_adduct.py`, from constants typed in by hand. | `chem/lewis_adduct.py` (`compute_lewis_adduct`, `one_way`) | This is the precise shape of "disconnected", and it is what the first recipe supplies. |
| `predict` already takes `acid_lumo_ev`, `base_homo_ev`, `acid_hardness`, `base_hardness`, each optional and independent, and treats `None` as "not available". `resolve_roles` is public and has, deliberately, no rule that uses hardness. | `chem/lewis_adduct.py` (`predict`, `resolve_roles`) | No equation is written. Orientation comes from `resolve_roles`, and the recipe only supplies numbers. |
| The documented pair, B3LYP/def2-SVP: BH3 LUMO -2.04 eV, eta 6.77; BF3 LUMO +0.73, eta 9.29; CO HOMO -10.17, eta 8.40. Frontier gap 8.13 (BH3) and 10.90 eV (BF3); \|d eta\| 1.63 and 0.89 eV. The two lines **disagree on purpose** and a test pins it. | `tests/test_lewis_adduct.py` (`test_the_two_orbital_lines_disagree_on_carbon_monoxide`), `_hsab_line`'s docstring | The regression pair (section 10), and the reason the lines are never combined. |
| The two Koopmans-or-delta-SCF families have **different descriptor ids**. `orca.homo_energy`, `orca.lumo_energy`, `orca.hardness` and the rest come from every calc type except `delta_scf` and `led`; `orca.dscf_hardness` and the rest come from `delta_scf` only. A compound job prints three orbital tables and the frontier parsers take the last, so Koopmans values are deliberately not emitted for it. | `chem/orca_engine.py` (`_CONCEPTUAL_DFT_FIELDS`, `_DELTA_SCF_FIELDS`, the branch in `parse_output`) | A binding names a descriptor id and a method. It never binds "hardness", because Koopmans hardness inverts ammonia and phosphine (`chem/conceptual_dft.py`). |
| A finished ORCA job is recorded in **two places that say different amounts**. The `QuantumChemistryRun` in `QuantumChemistryRunStore` (held by `ResultStoreService.qc_runs`) has the molecule uuid, calc type, **method and basis**, charge, multiplicity, `calculation_input`, `input_fingerprint`, `input_molblock`, solvent, status, `output_conformer_id` and the descriptors, and is kept unconditionally. Separately, `_record_descriptors` also files each descriptor in `SessionResultStore` as a "current/latest value", so Results can show it after a reselect; that copy is keyed by descriptor id, input kind and input fingerprint with **no method or basis in the key**, so it holds **one current value per calculator** and a later run at another level replaces the earlier one. Since #313 its provenance does say what it came from (`run_calc_type`, `run_method_basis`, `run_charge`, `run_multiplicity`, `run_provider` and `run_id`, the `RUN_*` names in `domain/common.py`), which closed finding B (section 14); the key was left alone. Nothing classifies a run as fresh or stale. | `domain/quantum_chemistry_run.py`, `services/quantum_chemistry_service.py` (`_record_descriptors`), `services/result_store_service.py` | Only the run store keeps every level of theory a molecule was computed at; the cached copy keeps the latest. The recipe reads runs, never the cached descriptors, and computes freshness for them itself (section 5). |
| `QuantumChemistryRun` is a plain mutable dataclass, not a frozen one. | `domain/quantum_chemistry_run.py` | Phase 1's "holding references to frozen results is a value snapshot" does not hold for runs. Evidence is **copied** into an immutable record when it is read. |
| `QuantumChemistryRun.input_conformer_id` is declared and **never set**: `_new_run` fills the other fields and no code writes this one. What identifies a run's geometry is `input_fingerprint`, which for the `GEOMETRY` input is SHA-256 over the kind, the conformer id and the molblock, and `input_molblock`, the exact text submitted. | `services/quantum_chemistry_service.py` (`_new_run`), `chem/calculation_input.py` (`resolve_calculation_input`) | "Same geometry" is `input_fingerprint` equality. The recipe does not read `input_conformer_id`. |
| The Quantum Chemistry panel submits `resolve_calculation_input(GEOMETRY)`, the canonical conformer. Since #312 `canonical_conformer` prefers the newest quantum-optimized conformer (`QUANTUM_OPTIMIZED_METHODS`, today `orca_opt`), so a job after an ORCA optimization runs on the optimized geometry, and the result event carries the submitted fingerprint so the window can give the optimized conformer the source's way back to the drawing's atoms. | `ui/panels/quantum_chemistry_panel.py` (the run handler), `chem/calculation_input.py` (`canonical_conformer`, `with_source_atom_map`) | Finding A (section 14) is closed. A run's `input_fingerprint` still says which conformer it ran on; the recipe still reads that and never assumes it. |
| Phase 1's turn snapshot, tools and envelope read `SessionResultStore` only. `calculation_host.py` names the quantum service only to say whether ORCA is configured. So the assistant can read the *latest* ORCA descriptors (the cached copy above), now with their calculation type, method and basis, charge and multiplicity (#313), and **cannot see an ORCA run**, so it cannot see a number that a later run at another level has replaced. | `domain/turn_snapshot.py`, `domain/result_envelope.py`, `app/calculation_host.py` | A recipe reading runs is a new read path. The assistant seeing recipe results is a later slice (section 9), not an assumption. |
| Dispatching a service-run (ORCA) calculator is deliberately **not built**: Phase 1 ships a preview adapter only. The existing entry is `QuantumChemistryService.request_calculation(mol, molecule_uuid, calc_type, charge, multiplicity, method_basis, provider_id, input_fingerprint, calculation_input)`; one job per molecule uuid (`JobManager.try_start`); completion is a `QuantumChemistryRunCompleted` event. | `AI_CALCULATION_BRIDGE.md` section 4, `services/quantum_chemistry_service.py` | Two stages (section 8): a recipe that evaluates over stored runs and says what is missing, then, separately, one that can start the missing jobs. |
| A QC run was given its own store because the revision cache drops a result whose fingerprint no longer matches the molecule when a project is saved, and its key has no room for parameters. | `domain/quantum_chemistry_run.py` module docstring | The same argument applies to a recipe run, and the same remedy (section 6). |
| The result codec constructs only allow-listed dataclasses from six named modules, versions every type, and refuses a layout newer than the build. The QC block has an envelope version of its own, and a newer block is ignored with a warning. | `domain/result_codec.py`, `domain/quantum_chemistry_run.py`, `services/project_service.py` (`QC_RUNS_KEY`) | A new record either joins the allow-list or carries an envelope of its own. Section 6. |
| `report_from_fields` turns lines of text into facts by parsing them. A calculator that wants units, a basis, evidence or limitations on a number builds `Fact`s directly. | `chem/report_adapter.py` | A recipe's result builds `Fact`s. It does not pass numbers through a string. |
| Parameters of a registry calculator are validated by `validate_parameters` before anything is prepared. | `domain/calculation_bridge.py` | A recipe step's parameters go through the same validator, not a second one. |

## 2. What a recipe is, and is not

A **recipe** is an ordered plan whose steps read each other's typed outputs. It is **code with data, versioned,
shipped with the application**; in this phase no person and no model writes one. (A user-defined formula is a
different feature with a different safety argument: `DERIVED_SCORES_DESIGN.md`.)

* **Definition** (`Recipe`): an id, a **version string** that is never repointed (a change of meaning is a new
  string, the rule `CURRENT_METHOD_VERSIONS` already follows), the question it answers, its **slots**, its
  **steps**, its result, and its stated caveats.
* **Slot**: a named input. In this phase a slot is a project molecule, referenced by uuid and recorded with its
  fingerprints. It is never a SMILES. (`compute_lewis_adduct` takes its partner as a SMILES on purpose, so a batch
  column stays replayable; a recipe needs the opposite, because quantum evidence is attached to a molecule.)
* **Step**, of three kinds, because they behave differently and the execution policy treats them differently:
  1. **Registry step**: a registered calculator, started as Phase 1 starts one, with its own execution policy.
  2. **Service step**: one ORCA job (calc type, method and basis, charge, multiplicity). Always `CONFIRM`:
     `ExecutionPolicy` refuses `AUTO` for any program in `HEAVY_TOOLS`, and this record does not weaken that.
  3. **Evaluate step**: a pure function over bound values. In process, instant, no external program.
* **Binding**: `(target, source, transform)`. The source is a slot, a **recipe parameter** (a choice made once for the
  whole recipe, such as the one method every step shares), or a named output of an **earlier** step, so a cycle
  cannot be written. The transform is from a **closed table** that starts with one member, `identity`. A unit
  conversion is added as its own reviewed entry with the constant it uses and a test, never as a function a recipe
  author supplies.
* **Output type**: closed: a scalar with a unit, a code from a declared set, a reference to a stored run, a report.
  A scalar's unit is part of its type, and two scalars of different units are different types.

**Validated before it can run**, at import time for a shipped recipe and again for each instance: every reference
resolves backwards; the target accepts the type; units are equal; each registry step's parameters pass
`validate_parameters`; each step has a stated execution policy; the recipe version is unique. A recipe that fails
validation is a failing test, not a recipe that runs and refuses. (Built in slice 1: a registry step states no
policy of its own and takes its calculator's, so a calculator nobody classified is an *unclassified step*; a service
step must name a heavy program and be approved by a person; an evaluate step must be pure, instant and in process;
a step on a molecule binds exactly one; and no step produces a molecule, which is a slot's type alone.)

**Not here:** no `eval`, no expression language (that is the other record), no dynamic import, no plugin-registered
recipes, no loops or branches in a plan. A branch is two recipes.

## 3. Bindings fail closed, and what blocks what

Every binding ends in exactly one of eight states, and the state is recorded with the reason:

| State | Meaning | Blocks the steps that need it? |
|---|---|---|
| `BOUND` | A value of the declared type was found and passed every compatibility rule. | no |
| `MISSING` | Nothing in the project matches. Not "zero", not "unknown": absent. | yes, unless the binding is declared **optional** |
| `REFUSED` | The producer declined (a limit, a missing input). The refusal's kind and text are kept. | yes |
| `FAILED` | The producer broke. | yes |
| `STALE` | The evidence describes a structure the molecule no longer has (section 5). | yes |
| `UNVERIFIABLE` | The record lacks what a comparison needs (no fingerprint, no molblock). Never called fresh. | yes |
| `INCOMPATIBLE` | Values exist but may not be combined: different method, solvent, or descriptor family. The rule that failed is named. | yes |
| `AMBIGUOUS` | More than one record could be meant and nothing says which (several earlier geometries, none picked). The candidates are named. | yes |

**A failed prerequisite never becomes a default.** An unbound value reaches `predict` as `None`, which is what
`predict` already means by "not available"; it is never `0.0`. **A present-but-wrong binding is never reported as
an absent one:** "no hardness run exists" and "a hardness run exists but at a different method" are different
sentences, and the second one tells the person what to do.

**What optional relaxes (settled while building slice 1).** The table above says "unless optional" on `MISSING` only.
An optional binding relaxes **every** state but `BOUND`, because the value handed to the step is `None` in each (a
stale or incompatible number is never handed over in its place) and the state is still recorded, which is what
`PairEvidence` means by "a value or `None` with the state that explains the `None`". A required binding blocks in
every state but `BOUND`.

**Optional bindings** exist for one reason: the Lewis lines are independent evidence, and `predict`'s contract is
that nothing fails because one line is unavailable. A binding is optional only where the step's own contract says
its input may be absent, and the recipe's result says, per line, which binding was in which state. A recipe in
which some lines are available and others are not is **partial**, and is shown as partial. It is never shown as
complete with the gaps hidden.

**A stale result is never silently replaced by the newest result of the same id.** If a newer compatible record
exists, the recipe says so as an offer ("run R2 is newer and compatible; evaluate again to use it"), and the
recorded answer is left as it was recorded.

## 4. The Lewis pairing

**Slots.** `first` and `second`: neutral names, because **orientation is not the order the person supplied**. The
recipe's `role` parameter uses the calculator's own codes (`auto`, `acid`, `base`) and means "the role of `first`",
exactly as `compute_lewis_adduct`'s means "this molecule". `resolve_roles` decides, and its answer, its basis and
the attempts it made are recorded.

**The one method.** A required parameter, `method_basis`, from the same preset list the Quantum Chemistry panel
offers (`METHOD_BASIS_PRESETS`), with the first preset as the default, as the `lewis_hsab` entry already does. The
recipe **does not look for the method that happens to have evidence**: a guess that picks one method for one
molecule and another for its partner is the failure this record exists to prevent. The interface can list the
methods for which evidence exists. It does not choose.

**Evidence per molecule `m`**, all at `method_basis`:

| What | Qualifying record | Gives |
|---|---|---|
| frontier energies | a `COMPLETED` or `COMPLETED_WITH_WARNINGS` run of `m` with calc type `sp` | `orca.homo_energy`, `orca.lumo_energy` (eV) |
| hardness | the same for calc type `delta_scf` | `orca.dscf_hardness` (eV) |

* **Why `sp` and not `opt`.** An optimization's orbital table is the *optimized* geometry's, and the run does not
  keep that geometry (only the id of the conformer it produced). A single point's orbital table is the geometry
  it was submitted with, which the run does record. The documented fixtures took their frontier energies from an
  optimization's own table; whether a single point at that geometry gives the same numbers is a **measured
  condition of the gate** (section 10), not an assumption.
* **Why `orca.dscf_hardness` and never `orca.hardness`.** Section 1, the row on the two descriptor families. A molecule with only a Koopmans
  hardness gets the HSAB line "not available: needs a delta-SCF run", which is what `_hsab_line` already says.
* **Within one line, both molecules' values must share `method_basis` and solvent**, or the binding is
  `INCOMPATIBLE` for that line and the rule is named. Hardness from different levels of theory is not a
  difference, it is two scales.
* **Frontier and hardness of one molecule at different inputs** is a stated caveat, not a block: the lines are
  independent evidence, and each is shown with the run and the input it came from. The report says whether the
  two share an input (`input_fingerprint` equality). This is a judgement: a difference of degree is a caveat and
  a difference of scale is a refusal.
* **Several qualifying runs.** Candidates are the runs of `m` with the right calc type and method, sorted
  into *current* (the run's input is the molecule's current geometry input, section 5), *historical* and
  *unverifiable*. Only a current run is used. Every current run is by definition at one input, so several of
  them are **repeats of the same job**: the newest is used, the others are named in the manifest, and the
  largest spread among their values is recorded as a number, so a surprising one is visible without a threshold
  having been invented. Historical runs are never used unless the person picks one **by run id**; asking to use
  "an earlier geometry" when several exist is `AMBIGUOUS`, the candidates are listed, and the pick, once made,
  is recorded as an explicit input.

**Evaluation.** Pure, instant, in process. The step takes the two molecules, the requested role, and a
`PairEvidence` holding, for `first` and `second`, `(homo_ev, lumo_ev, hardness_ev)` each as a value or `None`
with the state that explains the `None`. It calls `resolve_roles`, and for each admissible orientation calls
`predict` with the acid's LUMO and hardness and the base's HOMO and hardness. **The same evidence serves both
orientations of an unresolved pair**, because each molecule carries both a HOMO and a LUMO; the orientation
decides which number is read from which molecule, and nothing else.

**How the evidence reaches `predict`** (decision, section 13, item 2). `compute_lewis_adduct` keeps its signature
and its output, byte for byte. Its body after the parameter checks moves into one function that takes an optional
`PairEvidence`; the registered calculator passes none, and the recipe passes one. Two renderers would drift apart,
and putting six numeric fields into the calculator's visible parameters would add an unprovenanced channel into a
result that sits beside a published-looking enthalpy.

**Built (slice 2a).** `chem.lewis_adduct.lewis_report(mol, uuid, partner, role, evidence=None)` is that function;
`tests/test_lewis_adduct_pin.py` holds the calculator to a recording made from the code before it moved (21 calls
reaching every branch, compared as a projection of lines, facts, error, state and provenance, not as an encoding).
`domain.lewis` has the types, and they are strict at the door rather than in the binder alone:
an `EvidenceValue` is either `BOUND` (a number in eV with the copied `Evidence`, which must agree with it) or
a gap (no number, a reason in words); a `MoleculeEvidence` refuses any hardness that is not `orca.dscf_hardness` (the
Koopmans value is never accepted), frontier energies that do not come from a `sp` run and a hardness that does
not come from a `delta_scf` run; and a `PairEvidence` refuses two numbers on different methods or solvents in
any pairing a line uses, in either orientation. The evidence is appended to the report as facts (one per number,
or per gap with its state and reason), so a line that reads "not available" says which of "nothing run", "another
method" and "earlier geometries to choose between" it is. The partner's uuid is not passed: the acid and base uuids
never leave `predict`, so there was nothing to observe.

**What the result is.** A report built from `Fact`s directly: the role and how it was decided; per orientation the
three lines, each with its value, unit, basis, and the run ids and inputs behind it; per molecule the evidence
block and the binding state of each item; the existing assumptions and limitations unchanged, including the CO
disagreement and the sterics gap. **There is no field that combines the lines**, and a test asserts the absence as
`test_there_is_no_combined_score` already does for `LewisAdduct`.

## 5. When is a quantum run "current"?

Phase 1's `Freshness` has three values and this record keeps them, but a run needs its own rule, because the
result store's rule (the result's fingerprint equals the molecule's current input fingerprint) does not describe
a run well. Two things are being asked, and they are separate:

* **Does it still describe this molecule?** The run's `input_molblock` is parsed and its canonical identity
  (constitution, charge, isotopes, stereochemistry) is compared with the molecule's current drawing. A difference
  is `STALE`, cause `structure_edited`. The comparison needs the chemistry layer, so it is made by the host, not
  by the pure model.
* **Is it at the geometry a run would use now?** The run's `input_fingerprint` equals the fingerprint the
  resolver gives today for the same input kind. If not, but the constitution matches, the run is `HISTORICAL`: it
  describes an earlier geometry of the same molecule. It is **not used by default**, and the person may choose it
  by run id. A deleted conformer does not make a run stale; the run keeps the geometry it was given.

A run with no `input_fingerprint`, or no `input_molblock`, is `UNVERIFIABLE`.

## 6. Persistence: a recipe run is its own record (decision)

| | A. A report in `SessionResultStore`, with a manifest in `Provenance.parameters` | B. A dedicated, versioned `RecipeRun` in its own durable collection |
|---|---|---|
| Fits the store's key | no: that key is one molecule, one calculator, one fingerprint; a recipe has two molecules | yes: its own key |
| Survives an edit | **no**: `SessionResultStore.to_dict` drops a result whose fingerprint no longer matches, which is exactly when the person needs to read "stale, because the structure was edited" | yes: retained unconditionally, as QC runs are |
| Manifest is typed and versioned | no: `parameters` is a free dict, and the plan requires the manifest and codec version to be pinned | yes |
| Holds a partial outcome (some steps done, one refused) | no | yes, per step |
| Cost | none | a new record, a new project key, a codec decision, a reader |

**Decision: B**, following the precedent of `QuantumChemistryRunStore` point for point. **Not both:**
`SessionResultStore` never holds a recipe's result, so there is no second copy to disagree with the first. A
completed run is *projected* into the places a person looks (the Results list, the batch table) by reading the
`RecipeRun`, the way a QC run is a record of its own that the panels read.

**The record** (`RecipeRun`; names are proposals):

* `run_id`, `recipe_id`, `recipe_version`, created time, an overall status: completed, partial, blocked, failed,
  cancelled. (A run that was in flight when the project closed is not written, as for a QC run.)
* **inputs**: per slot, the molecule uuid, the constitution key and the drawing fingerprint at the time.
* **steps**: per step its state (pending, ready, blocked, running, completed, refused, failed, skipped) and, for a
  blocked or refused step, the reason in words and the kind.
* **consumed evidence**: per item the **copied values** (descriptor id, value, unit), the run id, the run's
  calc type, method and basis, charge, multiplicity, solvent, `input_fingerprint`, and which binding state it was
  in. The numbers are kept so the answer can still be read when the run they came from has since been deleted.
* the **result**: the report, encoded with `result_codec`.
* **As built (slice 1).** Also kept: the recipe parameters chosen; for each binding its state, its reason in words,
  the candidate run ids when it was `AMBIGUOUS`, and the copied evidence; and the run is immutable, so a rerun cannot
  alter it. **A run built `COMPLETED` while any step is unfinished or any binding is not `BOUND` is refused**, when it
  is built and when it is read from a file, and `classify` is the one place the status is decided. The store
  reports what it could not read through `load_problems` as well as the log, so a dropped run is never silent, and
  `ResultStoreService.record_recipe_run` tells the session it has something unsaved, because a recipe run is never
  also a result in the store and nothing else would.
* an **envelope version** of its own, in a block of its own in the project file. A newer block is ignored with a
  warning; a damaged run is skipped without breaking the others; neither is silent. Two things can be unknown to a
  later build: the envelope, and the recipe version. A run whose recipe version this build does not have is
  **shown as recorded and never re-evaluated**, labelled with the version that wrote it. That is the rule that
  stops a reopened project reinterpreting an old answer with newer calculator methods.

**A build that has never heard of the key drops the block on save**, as it does for every block beside the
document (`ProjectService` writes `project.to_dict()` plus the blocks it knows; `SCHEMA_VERSION` is 1 and has
never moved). For a recipe run that costs a re-evaluation, because the evidence is in the QC-run block and the
rest is derived from it, so no version stamp is proposed here. (The other record argues the opposite for
authored data.)

**Staleness is derived when it is read, never stored.** A stored flag rots; a comparison of the manifest with the
project today cannot. What is stored is the manifest.

## 7. Staleness, and what a rerun is

A recipe run is **stale** when the recorded answer no longer describes the project. Each cause is named:
`structure_edited` (a slot's constitution changed), `molecule_removed` (a slot's molecule is no longer in the
project; added in slice 1, the design had no word for it), `evidence_removed` (a consumed run is no longer in the
project; the recorded numbers stay on screen as recorded), `recipe_version_unknown`. A newer compatible run is
**not** staleness (section 3). It is an offer.

A slot with no constitution key to compare, because the run recorded none or the host could not compute one now, is
listed as **unverifiable** and is neither stale nor "unchanged".

**A rerun is a new `RecipeRun` with a new plan.** It never mutates the old one. The plan lists what is missing and
what would supply it, step by step with its execution policy. In this phase a plan whose missing steps are ORCA
jobs ends at the preview (section 8). **A stale recipe never relaunches ORCA or Vina by itself**, and a partial
run keeps its successful steps: a retry plans only the rest, and the old steps are referenced, not repeated.

## 8. What can run, and what waits (two stages, stated honestly)

**Stage A, no new dispatch.** The recipe evaluates over stored runs. For anything missing or incompatible it
returns the gap list, each gap as a sentence ("CO has no delta-SCF run at B3LYP def2-SVP"), and, for the work that
would fill it, the **service preview Phase 1 already produces** (what the job would do, whether ORCA is
configured, an *Open* button for the Quantum Chemistry panel). The person runs the jobs where they run them
today. Nothing is started by the recipe. This is complete, useful and honest, and everything in the gate can be
done in this stage, because the drive harness already has a step (`qc_run`) that presses the real Run button with
real ORCA.

**Stage B, a service dispatch adapter.** One approval of an exact plan of jobs (molecule, fingerprint, calc type,
method and basis, charge and multiplicity), dispatched once each on the GUI thread through
`QuantumChemistryService.request_calculation`, completing through `QuantumChemistryRunCompleted`. The approval
binds the exact list; a job outside it needs a new approval. This is also what lets the assistant's
`run_calculator` start an ORCA job after consent, which Phase 1 deferred. **It is its own design review and its
own PR**, and nothing in this record relies on it. Its known constraints from the source: one job per molecule
uuid at a time, an existing cancel path, and the geometry rule (an ORCA-optimized conformer is the next job's
input, finding A in section 14).

## 9. The assistant (not built here)

`list_goals` stays knowledge. A recipe tool would be `describe` (read the definition and its gaps), `read` (a
`RecipeRun` through the envelope), and `prepare` returning a plan whose service steps are previews; running
anything heavy stays a person's action. Three things are needed first: the turn snapshot extended to hold copies
of the runs of the molecules in scope (the level of theory is already stamped on the cached descriptors, section 14
finding B, but only the latest value per calculator is held), an envelope branch for a recipe report, and Stage B.
None is a reason to shape the recipe model differently, and none is claimed.

## 10. The gate: BH3 and BF3 with carbon monoxide, on real ORCA

Fixed in the commit that adds the gate script, **before the pair is run**, and not changed afterwards.

* **Question.** Does the recipe, fed only by stored runs at one method, reproduce the documented numbers, with
  the two lines left as they are?
* **Method and version.** B3LYP/def2-SVP, the ORCA version the fixtures were produced with (6.1.1, from the
  comments in `tests/test_lewis_adduct.py`; the run records the version it used and a different one is a
  recorded difference, not a pass).
* **Set-up.** For each of BH3 (`B`), BF3 (`FB(F)F`), CO (`[C-]#[O+]`): one ORCA geometry optimization, the
  optimized conformer being the canonical one since #312, then an `sp` and a `delta_scf` run at that geometry,
  through the application's own path. The script asserts it with `conformer_report` (`canonical_method: orca_opt`)
  before each run, and each run's `input_fingerprint` must equal the optimization's output conformer's. `role = acid` for the borane
  (the documented orientation).
* **Quantities.** Per pair, the frontier gap and \|d eta\| (4 numbers), and the six per-molecule inputs behind them.
* **The noise floor first.** The same `sp` and `delta_scf` input is run twice for CO and the difference is
  recorded. It is the lower bound for the tolerance below.
* **Tolerance T, chosen inside a window that is derived and not guessed.** The documented values carry two
  decimals, so a derived difference is good to about 0.01 eV: **T is at least 0.01 eV and at least the measured
  repeat difference.** The smallest margin the claims rest on is the ordering of \|d eta\|, 1.63 against 0.89, which
  is 0.74 eV; a tolerance of half that or more could let the two orderings swap, so **T is below 0.37 eV**. T is
  fixed inside [0.01, 0.37] eV from the noise floor, in the commit, before the pair runs.
* **PASS** requires all of: each of the four per-pair numbers within T of its documented value; frontier gap
  (BH3) below frontier gap (BF3); \|d eta\| (BF3) below \|d eta\| (BH3) (the **disagreement must reproduce**; a
  recipe that "fixes" it has altered the chemistry); no field combining the lines; the role recorded as `user`.
* **FAIL, decided in advance.** If a number misses T, the documented values stay the documented values, the
  recipe's numbers are published beside them with the difference, and the word "reproduces" is not used. T is not
  widened. If the single-point and the optimization's own table differ by more than T, that is a finding about the
  documented procedure, reported as such.

## 11. Tests

Domain tests need no Qt and no ORCA, and run against fakes built from real `QuantumChemistryRun` objects:

* every binding state, once each, and what each blocks (section 3);
* **distinct sentinel values for the two molecules**, so the acid's LUMO and the base's HOMO provably come from
  the right ones, and a mutant that reads one molecule's frontier values for the other fails;
* **slot order does not change the evidence**: `(A, B, auto)` and `(B, A, auto)` give the same per-orientation
  lines;
* method mismatch between partners names the failed rule, and the other lines survive;
* a Koopmans-only molecule never gets a numeric HSAB line;
* structure edited then undone: stale, then current again (because staleness is derived);
* a deleted run: stale with a cause, recorded numbers still shown;
* repeats of one job (the newest used, the others and the spread recorded), and several historical runs with no
  pick (`AMBIGUOUS`, then the pick recorded);
* a `RecipeRun` round trip for completed, partial, blocked and stale; an unknown recipe version shown and not
  re-evaluated; a newer envelope ignored with a warning; one damaged run skipped without breaking the others;
* `compute_lewis_adduct` returns the **same report as before** when called with no evidence (a pin, since the
  body was moved);
* the closed transform table: only `identity`; the validator rejects an unknown transform, a forward reference,
  a unit mismatch and an unclassified step;
* every mutation of the evidence mapping is caught (the project's mutation discipline).

A driven run (`OPENCHEM_DRIVE`) that builds its own state, with `expect_*` assertions and a PASS verdict, comes
with the UI slice. It will need a drive step for the pairing, which the harness does not have.

## 12. Slices

1. **The recipe model, the run record and the staleness rules** (built): pure, with the validator, the closed
   transform table, `RecipeRun`, its store, its envelope and the project key (`recipe_runs`). No UI, no ORCA, no
   chemistry. `domain/recipe.py`, `domain/recipe_run.py`, `ResultStoreService.record_recipe_run`.
2. **Lewis evidence** (**built**): `PairEvidence`, the shared body of `compute_lewis_adduct` (2a), the binder over
   `QuantumChemistryRunStore`, the evaluator, the host service and the shipped recipe (2b).

   **As built in 2b, and where it differs from or settles the text above:**
   * **The solvent is a recipe parameter, like the method** (default gas phase). The design said the two molecules'
     values "must share method and solvent"; making the solvent explicit means they do by construction, and a run at
     another solvent is reported as `INCOMPATIBLE` with the levels it does have, the same sentence as for a method.
   * **`AMBIGUOUS` covers an earlier-geometry run when no pick is made**, one or several. The text said "several earlier
     geometries"; with one, the open question is still "use that one, or compute again".
   * **A pick is keyed by calculation type** (`sp` or `delta_scf`), so one choice supplies both frontier numbers, and it
     can choose a current or an earlier run but never one of another structure (`STALE`) or one that kept no input to
     compare (`UNVERIFIABLE`).
   * **A run at a charge other than the drawing's net formal charge is `INCOMPATIBLE`** (a different species), and current
     runs at two multiplicities are `AMBIGUOUS`. Neither was in the text; both are one wrong number away.
   * **A failed run is `FAILED` with the reason it recorded**, a cancelled one is `MISSING` with a note that it was
     cancelled: a person who ran something should not be told nothing was run.
   * **Does a run still describe the drawing** is two functions, not one: a KEY recorded in a run and compared later
     (stereo exactly as the drawing specifies it, so adding a wedge reads as an edit), and a COMPARISON of a stored 3D
     input with the drawing (constitution, charge and isotopes, then only the stereo the drawing specifies, because a
     conformer of an unspecified centre has some stereo perceived from its coordinates and that is not an edit).
   * **A pair for which no line can be evaluated is `BLOCKED` with no result**, not a report of three "not available".
   * **A step record in this stage:** each of the four jobs is `COMPLETED` (a stored run supplied it) or `BLOCKED` (with
     the gap as a sentence); the evaluating step is `COMPLETED`, `REFUSED` with kind `limit`, or `BLOCKED`.
   * **`RecipeService.evaluate_lewis_pairing` records nothing**, so looking at a pairing does not change the project;
     whoever asks records it. The result is filed as `lewis_pairing`, and its facts are relabelled with the report,
     because `ReportResult.matched` omits a label only when it equals the report's name.
   * The method presets and solvents moved to `domain/quantum_methods.py`, and the shipped list to
     `domain/recipe_catalogue.py`, for the layering and the import cycle that would otherwise result.
3. **Host and UI**: a pairing entry, the gap list with the service preview, the result in Results, the help
   topic every new surface needs, the drive step and script. **3a is built** (the window, below), and so is
   **3b** (the result in Results, after the 3a list).

   **As built in 3a, and the choices the design left open:**
   * **The entry is Tools > Lewis Acid-Base Pairing..., opening one modeless window** (`ui/dialogs/lewis_pairing_dialog.py`),
     beside "Run Calculators by Goal...", which is the same kind of door. Not a dock panel: a thirteenth dock changes the
     layout every other panel is arranged in, and a pairing is something a person opens, reads and closes.
   * **It re-evaluates on its own and saves nothing.** Every control change, finished quantum-chemistry run, structure edit
     and project change evaluates again (cheap, and only while the window is showing); **Keep** is the one button that files
     an answer, and only an answer with a result can be kept. Looking never marks the project unsaved.
   * **The service preview is a row per job, in the vocabulary Phase 1 already uses** (`Requirement`: what it needs,
     whether it is there NOW, and what to do when it is not), built by `domain/recipe_preview.py`: what the job would run
     with (level of theory, charge), whether ORCA is configured and the molecule has a conformer, and a button that opens
     the Quantum Chemistry panel on that molecule, that calculation and that level. It starts nothing.
   * **The sentence above the jobs never makes a partial answer sound complete**, and a pairing where nothing could be
     evaluated shows the jobs and no report.
   * **An ambiguity is a chooser per molecule and calculation** (one choice serves both frontier numbers), showing short run
     ids with the full id as what is chosen; any change of the form forgets the choices, because they name runs at one level.
   * **The second picker never defaults to the first molecule.** With one molecule in the project it used to, and the window
     evaluated a molecule against itself instead of saying a pairing needs two. Pairing a molecule with itself stays possible
     on purpose.
   * Verified on real ORCA in the real window: `benchmarks/visual/lewis_pairing.json` (ammonia and water, four stored jobs,
     Keep, save, reopen, then a new geometry and a choice). The BH3/BF3/CO pair is deliberately NOT used there: its numbers
     belong to the gate (section 10), whose tolerance is fixed before the pair is run.
   **As built in 3b, and the choices the design left open:**
   * **The kept answer is a `RecipeAnswer`** (`domain/recipe_answer.py`): a `ReportResult` built from the kept run each time the
     reader refreshes, so ordering, search, copy and export apply to it unchanged. `RecipeService.answers_for(molecule, version)`
     builds it, `PropertyPanel._reader_entries` appends it, and nothing is stored: the session result store never holds it (the
     decision of section 6, asserted in `tests/test_recipe_service.py` and in the real window).
   * **It is listed under every molecule that took part**, re-stamped with the one being looked at, because the reader drops anything
     stamped with another molecule. Its report id is `<recipe>:<run id>`, so two kept runs never share one; the same pair kept twice
     at one level is told apart by a short run id in the title.
   * **Staleness is `assess`, read at each refresh, and the reader's one rule marks it.** The reader's rule is "structure version is
     not the current one"; a pairing is about two molecules, so a stale answer is stamped with a version no structure can have
     (`STALE_STAMP`, -1) and the cause travels in `stale_note`, which the reader prints in place of its generic line. A slot that
     could not be compared is not stale; it is a limitation ("could not check whether the structure of X was edited since").
   * **`Assessment` carries its findings as data** (`edited_slots`, `removed_slots`, `removed_run_ids`) so the sentences name molecules
     and runs, not slots.
   * **A deleted quantum-chemistry run had no event.** The Quantum Chemistry panel called `qc_runs.delete` on the store, so nothing told the
     reader or the pairing window, and the session was not marked unsaved. `ResultStoreService.delete_quantum_chemistry_run` is now
     the one way a run goes; it marks the session and publishes `QuantumChemistryRunDeleted`. Keeping publishes `RecipeRunRecorded`.
   * **The reader re-reads on a finished edit** (`MoleculeChanged`, not during an edit) as well as during one, coalesced, because the
     recomputation that follows an edit is not certain to produce a result event and a kept answer must not wait for one.
   * **Not done:** the batch/project table does not show kept answers (a table of calculators over molecules has no column for a
     two-molecule record), and the assistant cannot read them (section 9).
4. **The gate** (section 10): preregistration commit, noise floor, the pair, the verdict recorded whichever way.
5. **Later, each its own design review**: Stage B (the dispatch adapter), the snapshot extended to runs, the
   assistant's recipe tools.

## 13. Decisions most worth challenging

1. **A dedicated `RecipeRun` store rather than a report with a manifest** (section 6). It costs a record, a key and a
   reader. The alternative loses the answer exactly when its staleness is the thing to read.
2. **Evidence reaches `predict` by a shared function with an optional `PairEvidence`, not through the calculator's
   parameters** (section 4). The cost is that the recipe's evaluator is not a registered calculator and is not in
   the calculator reference.
3. **Koopmans hardness is never accepted for the HSAB line**, although it is free from a job that has already run.
   The cost is one more ORCA job per molecule. The reason is a measured inversion of ammonia and phosphine.
4. **Frontier energies come from a single point, not an optimization** (section 4). The documented numbers came
   from an optimization's table, so the gate tests the equivalence rather than assuming it.
5. **Historical geometry is a gap the person may override, not evidence the recipe uses** (section 5). It will
   send some people to the panel to run something they feel they already ran.
6. **Staleness is derived at read, and a newer compatible run is an offer** (sections 3 and 7). A stored flag
   would be simpler and would rot.
7. **Stage A first** (section 8): the one-approval experience is later than the evaluation. The alternative is to
   hold the recipe until a dispatch adapter exists, which would delay the part that needs no new risk.

## 14. Findings the design is built around (not decisions)

**A. An ORCA-optimized geometry does not become the next run's geometry.** `_parse_optimized_conformer` builds the
conformer with `energy=None`; the window adds it beside the existing conformers; and `canonical_conformer` sorts a
conformer without an energy last, choosing one only when **no** conformer has an energy. Measured 2026-10-12 on
real objects (a probe under an empty data root, three conformers):

```
before the ORCA optimization: canonical -> method='mmff' energy=-3.2
after the ORCA optimization is added: canonical -> method='mmff' energy=-3.2
the optimized conformer is the canonical one: False
optimized conformer alone: canonical -> method='orca_opt' energy=None
```

So on a molecule that also had conformers with a recorded energy (Generate Conformers records one unless told not
to optimize), an `opt` followed by a `delta_scf` in the panel ran the second job on the **force-field** conformer, not on
the geometry just optimized, while the documented BH3/CO numbers were computed at an ORCA geometry.

**Resolved by #312 (2026-10-12), at the owner's decision.** `canonical_conformer` now returns the newest conformer
whose method is in `QUANTUM_OPTIMIZED_METHODS` (today `orca_opt`), and falls back to the old lowest-MMFF-energy rule
when there is none. Newest, not lowest, because an ORCA energy and an MMFF energy are not on one scale. Adding the
conformer already recomputed the 3D calculators and undo removes it, so the previous choice comes back with it. The
optimized conformer is built without the way back to the drawing's atoms, which would have cost every per-atom 3D
result its atom map once it became the input; the result event now carries the fingerprint the job was submitted
with and the window copies the map from that conformer (and leaves it "not recorded" when the source is gone,
unmapped or has a different atom count). Verified on real ORCA in the real window by
`benchmarks/visual/qm_optimized_geometry_is_used.json` (the single point after an optimization was submitted with the
optimized conformer's fingerprint). The recipe still reads each run's `input_fingerprint` and says which geometry it
used; it does not assume the rule.

**B. The assistant is told an ORCA number without its level of theory.** `_record_descriptors` files the descriptors in the
result store, so Phase 1's `read_results` can return them, and `parse_output` gives them `Provenance(method='orca',
parameters={'orca_version': ...})` because the provider is never handed the method and basis. Measured 2026-10-12 by running the
engine tests' own single-point fixture through `parse_output`, wrapping it as the service does, and serialising it with the Phase 1
envelope:

```
provenance.method    : 'orca'
provenance.parameters: {'orca_version': 'unknown'}
"method": {"name": "orca", "version": "", "created_by": "core", ...}
"parameters": {}
envelope mentions of method/basis/charge/multiplicity/calc type: []
```

The envelope's promise that every number carries its method and settings holds for registry calculators and **not** for these.
B3LYP/def2-SVP and HF/STO-3G were indistinguishable in it, and the cache key has no method in it either. The run has all of it.

**Resolved by #313 (2026-10-12).** The service stamps `run_calc_type`, `run_method_basis`, `run_charge`,
`run_multiplicity`, `run_provider` and `run_id` (the `RUN_*` names in `domain/common.py`) into the provenance before the
result event and before `_record_descriptors`, and the Phase 1 envelope's `parameters` shows the first four (bounded
to 32 entries). The identity and the cache key are unchanged, so the store **still keeps one current value per
calculator**: a later run at another level replaces the earlier one, and the assistant sees only the latest. The recipe
does not depend on either fix, because it reads runs.

**C. The Lewis calculator has never shown a frontier or HSAB line in the application.** Section 1, the row on `compute_lewis_adduct`. Nothing
is broken: the lines are labelled "not available" and say what to run. It is the reason this is a wiring task and
not a chemistry task.
