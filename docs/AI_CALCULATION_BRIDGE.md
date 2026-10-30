# The AI assistant's calculator bridge: design record

**Status: design, written 2026-10-12, and built in three slices.** Part of Phase 1 of the plan in the
session notes. **Slice 1** (the execution policy, the shared search, this record), **slice 2**
(the host adapter, the plugin handle, the frozen turn snapshot, parameter validation, the run
ledger) and **slice 3** (the result envelope, the five tools, the consent UI, the service preview
adapter, the privacy note, "Explain Stored Results") are built; each section says "built" where it is.
**Since then three tools were added for derived scores** (`read_scores`, `list_score_outputs` and `propose_score`; `DERIVED_SCORES_DESIGN.md`, slices 4a and 4d), so the five tools described below are eight. **What is not done is the live run on a real tool-capable provider** (section 11): it needs an API key,
and every check so far used a scripted provider. Where a review changes this document, change it here first.

Every statement about how the application works today was read in the source on the date above and
cites the function. Statements about what to build are decisions, marked as such, and the ones most
worth challenging are collected at the end.

## 1. What exists, and what that forces

| Fact | Where | What it forces |
|---|---|---|
| The assistant has two tools and cannot reach a calculator. Tool handlers are module functions called as `handler(**tool_call.input)` on a worker thread, with no schema check. | `plugins/ai_assistant/tools.py` (`TOOL_REGISTRY`), `panel.py` (`_run_completion`, `_execute_tool`) | Handlers need the turn's context passed in, and a validation layer in front of them. |
| A plugin sees narrow namespaces only; `ServiceContainer`, the bus and the window are deliberately hidden. | `plugins/context.py` (`PluginContext` docstring) | The bridge is a new narrow namespace, not a back door. |
| The window owns the session (project, selected molecule); the container does not. | `app/session.py`, `bootstrap.build_service_container` | The adapter that knows the selection lives in `app/`, and reaches plugins through the context. |
| A user-started run is `DescriptorService.run_calculator(model, request)`: it freezes an `InputSnapshot` on the calling thread, runs on a `QThreadPool` worker, resolves the input and its fingerprint, adds geometry provenance, publishes a result event and then `ResultRecorded`, and always ends with `CalculationFinished`. | `services/descriptor_service.py` (`run_calculator`, `_CalculationTask._run`) | An AI run goes through exactly this, so it is recorded like any other and cannot differ in provenance. |
| `ResultStoreService` records on `ResultRecorded`, only for a molecule in the current project. | `services/result_store_service.py` (`_on_result_recorded`) | Recording needs no new code; reading needs a new accessor (section 6). |
| `EventBus.publish` goes through a Qt signal, so a handler runs on the bus's thread (the GUI thread) even when the event was published from a pool worker. | `events/base.py` (`EventBus`) | Completion can be observed on the GUI thread by subscribing, and handed to a waiting worker through a future. |
| `CalculatorRegistry.compute` raises for a `ServiceExecution` calculator; ten of the 72 registered are service-run (Docking, eight ORCA types, `lewis_hsab`). | `services/calculator_registry.py`, `bootstrap._EXTERNAL_CALCULATOR_DEFINITIONS` | Two execution classes (section 4). |
| The command-line twin of the task deliberately leaves out `_bind_settings`, so the pKa and ADMET sidecars refuse as `needs_setup` there. | `cli/calculation.py` module docstring | The bridge cannot use the CLI path; it must use the application's, which binds the configured interpreters. |
| Results are frozen dataclasses. | `domain/scientific_result.py`, `domain/report.py` | Holding references to the results in a snapshot is a value snapshot; no deep copy is needed. |
| `ClaudeCLIProvider.supports_tools` is `False`; the Anthropic and OpenAI-compatible providers are `True`, and the panel offers tools only when it is. | `plugins/ai_assistant/providers.py` | The live acceptance test needs a tool-capable provider (section 11). |
| A calculator does not validate a choice parameter: `geometry_analysis` accepted `conformer_policy="lowest_energy"`, which is not one of its choices, and ran. | measured 2026-10-12, `benchmarks/calculator_cost` | The bridge validates parameters itself (section 8); a provider's tool schema is not the boundary. |

## 2. The capability

**A plugin gets `context.calculations`, a handle with eleven operations and no objects behind it.**
It is built from a host object the window hands the `PluginManager`; a context built without one
(a headless run, a test) answers every call with a typed `UNAVAILABLE`, never an exception.

| Operation | Thread | Returns |
|---|---|---|
| `begin_turn()` | GUI | an immutable `TurnContext` (section 6), or `None` when nothing is selected |
| `catalog(query, limit)` | any | `CalculatorCard`s from the registry, by the shared search (section 7) |
| `describe(calculator_id)` | any | one card with its parameters, or `UNKNOWN` |
| `read_results(turn, calculator_ids, include_not_current, limit)` | any | the turn's snapshot read by freshness and outcome (section 6). **Needs no host**: it reads only the frozen turn. |
| `read_scores(turn, names)` | any | the user's own derived scores (`docs/DERIVED_SCORES_DESIGN.md`, slice 4a), worked out against the turn's frozen results and the definitions frozen with them. **Needs no host.** A score is not a stored result, so `read_results` never shows one; there is no call that makes, changes or removes a score. |
| `prepare(turn, calculator_id, parameters)` | any | a `Preparation`: validated and normalised parameters, the execution decision, and a preview, or a typed refusal. **Starts nothing.** |
| `run(turn, run_id)` | worker | for an `AUTO` preparation only: dispatches and waits (section 3) |
| `pending()` | GUI | previews awaiting approval, for the panel |
| `list_score_outputs()` | any | the outputs a derived score's formula may read, with units and endpoints (`docs/DERIVED_SCORES_DESIGN.md`, slice 4d). Fixed knowledge; needs no host. |
| `propose_score(turn, request)` | any | checks a model's request for a score by the rules a typed definition meets and **leaves a card for a person**; it stores nothing and is the only score call here that can lead to a score existing. |
| `approve(run_id)` / `cancel(run_id)` | **GUI only** | start or drop a pending preview |
| `approve_score(proposal_id)` / `cancel_score(proposal_id)` | **GUI only** | make, or drop, a score the assistant proposed. The same split as a run's: a panel is given them and a tool is not. |

`approve` and `cancel` are not reachable from a tool. **Built:** they, `pending`, `state_of` and
`outcome_of` are methods of `CalculationHost` (`app/calculation_host.py`) and are absent from
`PluginCalculations` (`plugins/calculation_access.py`), the handle a plugin receives as
`context.calculations` -- a test pins the handle's public surface to exactly the six operations and
fails if an approval method is added. The panel will hold the host side in slice 3. This is what
makes "the model cannot approve its own request" a property of which object a caller holds, rather
than of a check somebody has to remember. The host also has a `finished` signal, emitted once per run
when it reaches a final state, for the panel.

**Built, as decided:** the adapter is `app/calculation_host.py`; the handle and its types are in
`plugins/` and `domain/`; the host reaches the plugin through `PluginManager(...,
calculation_host=...)`, not through the `UIRegistry` protocol, so existing test doubles of that
protocol are untouched. A context built without a host answers every call with a typed
`UNAVAILABLE`.

## 3. Request lifecycle, and the thread contract

```
discover -> prepare -> validate -> decide -+-> AUTO ----------------------> dispatch -> record -> serialise
                                           |
                                           +-> CONFIRM -> PREVIEWED -> approve -> dispatch -> record -> serialise
                                                              |
                                                              +-> cancel | invalidate | expire
```

One `run_id` is minted by `prepare` (it is the `ExecutionPlan`'s, so the plan the launcher already
builds is the plan recorded) and carried through every step. A tool call that names a `run_id` it did
not receive from `prepare` is refused (`REJECTED`, `NO_SUCH_RUN`); one from an earlier turn is refused
(`WRONG_TURN`); one that repeats a `run_id` already dispatched returns the original outcome and
starts nothing. **Built** (`domain/run_lifecycle.py`, `RunLedger`): each legal transition is a table
and each absence is pinned by a test; `claim_dispatch` is atomic and answers True to one caller of
forty racing for it.

States: `PREPARED`, `PREVIEWED` (awaiting a person), `APPROVED`, `RUNNING`, `COMPLETED`, `REFUSED`
(the calculator declined: a limit, needs input, needs setup, with its kind), `FAILED`,
`CANCELLED`, `INVALIDATED`, `TIMED_OUT`, and `REJECTED` (the request named no run it may use;
neither of the last two is a ledger state). A preview is not a job; an approved plan is not evidence
of a calculation; **only `COMPLETED` carries a number**, and a `TIMED_OUT` run is still running --
its result will arrive in Results by the normal path, and the model is told so rather than asked
to retry.

**Threads, stated because the tool loop runs on a pool worker.**

* The worker never touches a widget, a dialog or a mutable model. It calls handle methods that are
  safe from any thread and gets immutable values back.
* `run` (an `AUTO` request): the worker posts the request to a `QObject` that lives on the GUI
  thread, through a queued signal, and waits on a `concurrent.futures.Future` with a timeout. On the
  GUI thread the host calls `DescriptorService.run_calculator` -- the normal path -- and
  completes the future from its `CalculationFinished` and `ResultRecorded` subscriptions. The GUI
  thread is never blocked, and the worker is blocked only for a bounded time.
* A `CONFIRM` request returns `AWAITING_APPROVAL` to the model and **the turn ends there**. The
  model is told the preview is on screen and to wait. On `approve` the GUI thread dispatches; when
  the run completes, the outcome is appended to the conversation as a new, system-originated
  tool-result message with its own value snapshot, and the person decides whether to continue. No
  worker waits on an ORCA job, and an arriving result cannot cause a second dispatch.
* Timeout: `AUTO` requests wait up to the policy's resource class (**built**: 15 s for `INSTANT`,
  60 s for `SHORT`, `WAIT_SECONDS` in the host); on expiry the outcome is `TIMED_OUT` as above.
* **Built, and worth saying because it differs from the first sketch:** the worker does not claim
  the run. It posts the request, and the GUI thread claims it inside `_start`, *after* re-checking the
  plan against the live molecule. A claim made on the worker, before the check, would leave a run
  `RUNNING` that must then be voided, and `RUNNING` has no way out but a result. The check is the
  fingerprint of the input the plan was made on and the project it was made in; if either has moved,
  the run is `INVALIDATED` and nothing starts, whether the request came from `run` or from a person's
  Approve.
* **Known limit, built as is:** the bus carries no run id, so a completion is matched to its run by
  (calculator, molecule) and the result by its parameter identity. If a person runs the same
  calculator on the same molecule with *different* settings in the same few milliseconds, their
  "finished" can be taken for the AI's and the outcome reported as a failure. The AI's own result is
  still recorded normally and a later read finds it; nothing is lost, only mis-described.

## 4. Two execution classes

* **Registry-run** (62 calculators): `DescriptorService.run_calculator`, as above. Phase 1 can
  start these.
* **Service-run** (10): never through `compute()`. Phase 1 ships a **preview adapter only**: it
  reads the service's requirements (is the executable configured, what method and basis, which
  inputs it needs, which files it would write) and returns a no-side-effects plan, or the real
  reason it cannot (not configured, no 3D structure). Dispatching one waits for its own adapter and
  confirmed-approval path, in a later phase; until then `describe` marks it `preview_only`.
  **If the preview cannot be made without building the dispatch adapter, the live ORCA-preview
  acceptance test moves with it rather than being claimed early.**

## 5. Execution policy (built in the first PR)

`domain/execution_policy.py` and `domain/builtin_execution_policies.py`. A calculator is
`AUTO` (a model may start it) or `CONFIRM` (a person approves a preview). The class, the external
programs and the effects beyond a stored result are separate fields, because a cheap flag answers
four different questions with one word.

**Measured, not estimated** (`benchmarks/calculator_cost/`, 2026-10-12, three molecules up to 41
heavy atoms). 57 of 72 are `AUTO` (43 instant, 14 short) and 15 need approval. The findings that
shaped it, each of which a default-settings sweep alone would have got wrong:

* every registry calculator ran in under 1.3 s at its defaults -- and **four scale measurably
  with a parameter**: `hbond_vs_ph` is 0.6 s at a 0.5 pH step and 16.7 s at 0.01; molecular dynamics 0.17 s
  at 1,000 steps and 16.6 s at 100,000; Geometry (3D) with `conformer_policy=always` 29.7 s at 200
  conformers against 1.1 s with `never`; the stereoisomer enumerator 1.1 s at a 2,000 cap and 2.9 s at
  10,000. Each carries its measured bound, and a request outside it becomes a preview with the reason,
  not a refusal.
* **alignment is slow on real molecules**: a 41-heavy-atom molecule took 0.6 s aligned to a 13-atom
  reference and **31 s aligned to a 28-atom one**, which then took 46 s with MCS, and 74 to 104 s on
  `Accurate` and 109 to 163 s with both across four runs. `CONFIRM`.
* four calculators only *refused* at their defaults; they were re-run with real inputs.
* what was not measured (ADMET-AI, OPSIN, Markush output size) is filed `CONFIRM` and says so. The
  pkasolver figure is the one the roadmap recorded, cited as such.
* a molecule above 41 heavy atoms, the largest measured, is `CONFIRM` whatever the calculator.

The policy is attached by the composition root and never looked up by id at decision time, so a
plugin that registers under a built-in's id does not inherit its permission; an unclassified plugin
calculator needs approval.

## 6. The turn snapshot, and what "current" means

**A turn is one user message and the assistant's reply to it.** `begin_turn()` runs on the GUI
thread at the moment of Send and captures a `TurnContext`: the molecule's uuid, name and canonical
SMILES; its current input fingerprint for each calculation input; and **the stored result records
themselves** (frozen, so references are values). Every tool call in the turn reads that and nothing
else. `read_results` takes no molecule argument -- the model cannot ask about another molecule, and
selecting one mid-stream changes nothing. A result that completes during the turn does not change
what `read_results` returns; the explicit outcome of a `run` the model requested is returned by
that call, which is the model's own request and not a read of the store.

`SessionResultStore.fresh_results` returns only records whose fingerprint matches, so it is not an
inventory. **Built:** `SessionResultStore.all_results` is the read-only accessor for every retained
record, and `domain/turn_snapshot.py` classifies each one.

**The five states of the first sketch are two axes, and this is a refinement of it:** *freshness*
(`current`, `historical`, `unverifiable`) and *outcome* (`computed`, `refused`, `failed`). A
refusal that no longer matches the structure is a historical refusal, which a single list of five
could not say. `not_run` is the absence of any record and is reported per calculator.

| Freshness | Meaning | Never |
|---|---|---|
| `current` | its input fingerprint equals the snapshot's **and** it is the record the application itself would replay (`fresh_results`), so a superseded method stored beside the current one is not offered as current | |
| `historical` | retained, fingerprint differs (an earlier structure), or a superseded method version | shown beside current as if it still applied |
| `unverifiable` | no fingerprint on the record, or none in the snapshot for its input | called fresh |

| Outcome | Meaning | Never |
|---|---|---|
| `computed` | it produced a result (which may hold no values: that is still a result) | |
| `refused` | the method declined: a limit, a missing input, a missing setup; keeps its kind | read as a low value |
| `failed` | it broke | |
| `not_run` (per calculator) | nothing stored | invented as a stale record |

`read_results` returns current entries by default; the others only when asked for, each carrying
its freshness, and a requested calculator with nothing stored is `not_run` while one with only
not-current records is `only_not_current`. Neither becomes a value.

## 7. Discovery returns runnability, not just existence

`catalog` and `describe` return a `CalculatorCard` built from the registry and its own metadata:
id, name, category and group label, description, tags, support stage and default visibility with the
reason, registry- or service-run, the execution policy, **what this route can do with it now**
(`auto`, `needs_approval`, `preview_only`, `blocked` with the reason), the parameters with kinds,
choices, bounds and defaults, and which are required. A hidden, service-only or unsupported
calculator is never described as immediately runnable.

The search is `domain/calculator_search.py`, the rule the launcher's Find box now uses: every word
of the query must appear in the name, description, heading or tags, case-folded; empty matches all;
a miss is an empty list; order is the browse order. (The launcher changed in the first PR: it used
the whole query as one substring, so "lewis adduct" and "adduct lewis" disagreed.)

## 8. Validation before anything is prepared

**Built** (`domain/calculation_bridge.py`, `validate_parameters`). `prepare` rejects, with a typed
problem naming the parameter and **all of them at once** (a model that fixes one and resubmits to
find the next burns turns): an unknown calculator id; an unknown parameter name; a value of the wrong
kind (a string where a number belongs, a boolean where a number belongs, NaN or infinity); a whole-
number setting given a fraction; a number outside the declared minimum or maximum; a choice that is
not one of `choices`; a boolean that is not a boolean; text over 4,000 characters; a `smiles`
parameter that does not parse; a `required` parameter not given or left at its placeholder (a
density of 0.0 is no density), which is a `needs_input` problem naming what is wanted.

The single translation it makes is a choice's *display label* to its stored code, reported in
`adjustments`, because the stored code is what identifies a result. A value for a switched-off
setting (`enabled_by`) is kept and reported as ignored. Nothing else is corrected: a scientifically
meaningful value is refused, never replaced.

**The normalised parameters are the settings dialog's dict**: every declared parameter in order,
defaults filled in, a float setting stored as a float (`parameters_key` serialises `7` and `7.0`
differently, so an unnormalised `7` would be a different calculation from the dialog's `7.0`). A test
pins that an AI run's `parameters_key` equals the dialog's for the same settings. The motivating
measurement is real: `geometry_analysis` ran with `conformer_policy="lowest_energy"`, which is not one
of its choices, so the calculator cannot be trusted to refuse it.

**A change from the first sketch:** there is no "no conformer" pre-check. `GEOMETRY` means "prefer
real 3D coordinates" and falls back to the drawing, so a molecule without a conformer still has a
fingerprint, and the calculators that need one refuse on their own, with their own words. That refusal
is what a person would get, so it is recorded and passed through (`REFUSED`, with its code and kind).

## 9. The result envelope

**Built (slice 3): `domain/result_envelope.py`.** `envelope_of` serialises one result,
`results_view_envelope` a turn's whole read and `outcome_envelope` a run's outcome; `Caps` and `CAP_STEPS`
are the size steps `plugins/ai_assistant/bridge.py::bounded_json` walks down until a reply fits
`REPLY_BUDGET`, so a reply is shortened by dropping rows and never by dropping a unit or a caveat, and says
`shortened_for_length` when it did. `tests/test_result_envelope.py` walks every supported kind. The design:

One serialiser, type-aware, in the host layer. Every number the model receives carries: result id
and display name; method and version; the normalised parameters; the input fingerprint and which
representation it describes (drawing, a named conformer, a microspecies at a pH); units, basis or
applicability domain; status (including refusal kind) and freshness state; the caveats; and for
per-atom data the atom-index space. For a result a service ran (an ORCA job has no registry dialog dict)
the parameters are the job's calculation type, method and basis, charge and multiplicity, stamped from its
submission snapshot (`domain.common.RUN_SETTINGS`); they are provenance, never part of the result's identity,
so the store key does not move. A summary says it is a summary and names how to read the whole
thing. A result kind with no serialiser is reported `unsupported`; it is not forced through a
generic dict. The set of supported kinds is explicit (`PerAtomDataset`, `ReportResult`/`StructureReport`,
`AlertResult`, `SpectrumResult`, `PhCurveResult`, `StructureSetResult`, `TrajectoryResult`), and a
test walks every kind the bridge claims and asserts each number has its metadata.

## 10. Recording, consent state and the system prompt

An AI-requested run is recorded through the normal path, so it appears in Results like any other.
**Built (slice 3): the system prompt no longer says the assistant cannot modify the project.** It says
what the five tools do, that a preview waits for the person and the assistant cannot approve it, that a
run is recorded in the project, and that no number is stated that a tool did not return. The alternative (a temporary,
per-conversation result) was rejected: it would show the model a number the person cannot see, and
the two models must never be mixed. A visible ledger lists what the assistant proposed, ran and was
refused, with molecule, parameters and state (built: a wrapping list under the cards, one row per request,
updated as the run moves). Tool output is sent to the configured provider on the next request, so a remote
provider sees calculator results; the panel says so (built: `AIPrivacyNote`, which names the provider). **Reading a score (derived scores slice 4a) sends its name and formula, which are a person's own text, too; the owner and note are never sent, and the note says so.**
The outcome of a run the person approved reaches the model as a note on the NEXT message, never as a
fabricated tool result.

## 11. Acceptance, and what is honestly out of reach until later

Phase 1 is accepted when: the handle exposes none of the container, the bus or the window; search
returns only registered ids; a turn's reads are unaffected by a selection or a result changing
mid-stream; all five states are tested separately; parameters are validated against the real
definitions; the approval path starts nothing without a GUI-side action, cannot be forged or replayed
by a fake provider, is single-dispatch, and cancel leaves nothing running; envelopes carry their
provenance.

The live run (a tool-capable provider, with the sequence **tool call received, preview prepared, no
job started, confirmation awaited** captured) is **not done**: the service preview adapter it waited on is
built, but it needs a provider key, and `ClaudeCLIProvider` is excluded because it takes no tools. Every
check so far, including `benchmarks/visual/ai_assistant_tools.json`, used a scripted provider, which proves
everything around a model (the turn freeze, the loop on its worker thread, the host, the cards and their
real buttons, the notes) and nothing about whether a real model calls the tools well. Giving the CLI
provider a tool protocol is a separate, optional item with its own tests.

## 12. Slices

1. **Built (#307).** Execution policy and its measurements; the shared calculator search; this record.
2. **Built.** `app/calculation_host.py`, the plugin handle (`context.calculations`), the turn snapshot,
   `SessionResultStore.all_results`, parameter validation, the run ledger,
   `catalog`/`describe`/`read_results`/`prepare`/`run` for registry calculators, and
   approve/cancel on the host. Verified three ways: 134 unit tests across five files, a 15-run flakiness
   check of the threaded ones, and `benchmarks/visual/ai_bridge_run.json`, which drives the real
   window from a real worker thread (13 assertions). **Not in this slice:** the serialiser, any tool,
   the panel's consent UI.
3. **Built (this PR).** `domain/result_envelope.py` (51 tests); `plugins/ai_assistant/bridge.py` and
   `calculation_tools.py` (`find_calculators`, `list_goals`, `describe_calculator`, `read_results`, `run_calculator`) with
   argument validation in `tools.py`; the panel's preview card, Approve and Cancel (through
   `context.calculation_approvals`, which a tool is never given), ledger, status, privacy note and the
   notes that go with the next message (30 tests); the service preview adapter, so an ORCA or Vina
   calculator is DESCRIBED (what it needs, whether this machine is ready, an "Open" button for the panel
   that owns it) and nothing is started; the "Explain Stored Results" menu entry; and `list_goals`, the goal
   wizard's question-to-calculators table as read-only knowledge (section 14). Verified by
   `benchmarks/visual/ai_assistant_tools.json` against the real window (14 assertions), which found two
   defects no unit test could (`docs/LESSONS.md`, the plugin-panel entry). **Not done:** the live provider run.

4. **Built (2026-10-30): reading the ORCA runs** (`read_quantum_runs`, section 15). The dispatch adapter that lets a person's Approve start an ORCA job is the slice after it and is not built.

## 13. Decisions most worth challenging

1. **Approval-gated work ends the turn** instead of the worker waiting. It makes ORCA safe and
   simple, and it makes the assistant unable to chain "run it, then explain it" inside one turn.
   The cost is one more message from the person.
2. **The size ceiling is the largest molecule measured (41 heavy atoms), not a round number.** It
   sends many real drug molecules to approval. The remedy is a bigger measured panel, not a bigger
   number.
3. **Sidecar calculators (pKa and relatives) are `AUTO`** on the strength of the roadmap's recorded
   3 s cold call. They start a local interpreter. If that is more than "cheap" should mean, move them
   to `CONFIRM`; it is one line each in `builtin_execution_policies.py`.
4. **A stored AI-run result appears in Results**, so the model can leave the project changed. The
   alternative is ruled out above, but the consequence is real.
5. **The capability reaches plugins through `PluginManager`, not the `UIRegistry` protocol.** It
   keeps the protocol's test doubles working; it also means a second front end would pass a host
   explicitly.

## 15. Reading the quantum-chemistry runs (2026-10-30; `domain/quantum_run_snapshot.py`, `result_envelope.run_envelope`, the `read_quantum_runs` tool)

**What was missing, measured by reading the code and not assumed.** An ORCA job leaves its numbers in TWO places. Its descriptors and per-atom datasets are filed in the general result store (`QuantumChemistryService._record_descriptors`), so `read_results` already offers an SCF energy with its method and basis. Everything else is only in the run history (`QuantumChemistryRunStore`): a job that FAILED or was CANCELLED (there is no result to file), the warnings a finished job came back with, a spectrum, a vibrational analysis, and which of several runs at different methods a number came from. The assistant could see none of that, so "did my NMR job finish?" and "why is there no IR?" had no answer. The first sketch of this slice said the assistant could not see any ORCA result; that was wrong, and the paragraph above is what is true.

**Decisions.**
* **A run is frozen with the turn** like a result: `begin_turn` classifies the molecule's runs against the same fingerprints (`TurnContext.runs`), and a job that ends while the reply streams changes nothing it was told. `RunEntry` copies the scalar fields and holds the frozen result objects, because `QuantumChemistryRun` itself is mutable.
* **Freshness is the result's axis.** `current` when the input fingerprint equals the turn's for the same kind of input, `historical` when it differs, `unverifiable` when there is nothing to compare it with. The turn holds fingerprints for the drawing and the stored conformer only, so an ENSEMBLE run is `unverifiable` and says so, never current by guess.
* **Two levels, because a header is never dropped and numbers are large.** With no arguments the tool lists the CURRENT runs as headers (calculation, method and basis, charge and multiplicity, how it ended, warnings, and each output with its status and names), no numbers, at most 10, newest first; the others are counted. With `run_ids` it returns those runs with their numbers, through the serialisers a stored result of that kind uses (`result_envelope.data_of`, factored out of `envelope_of` so there is one), **at most three at a time**: measured against the 12,000-character reply budget, ten long analyses asked for by id came to 14,193 characters at the smallest detail step, because every run carries a header. The reply says how many it left out.
* **A failed or cancelled run has no numbers even if asked for,** and an output the run records as not produced, inapplicable or failed says that and holds no value.
* **An infrared analysis is its modes.** A vibrational spectrum is a `SpectrumResult` whose per-atom `values` are empty on purpose, so the serialiser that tells a per-atom spectrum told it as "0 peaks". It now has its own branch (`wavenumber_cm1`, `ir_intensity_km_mol`, `character`, the count of imaginary modes and the warning), for a stored result as well as for a run.
* **What is never sent:** the structure ORCA was given (`input_molblock`), the wavefunction cache key, ORCA's own output. A run's warnings are the application's own sentences, bounded by the caps.
* **A kind with no serialiser** (the tautomer bundles, a Boltzmann ensemble's extra outputs) is named `unsupported` and its numbers are not offered, as for a stored result.
* **The tool starts nothing and cannot:** `ToolBridge.read_quantum_runs` reads the turn and needs no host; the system prompt and the tool description say a person starts ORCA from the Quantum Chemistry panel.

**Not here: dispatch.** Letting a person's Approve start a job needs the panel's request-building (conformer resolution, the open-shell Fukui refusal, ensemble averaging, the LED cost question and the panel's own pending state) in one place that both the Run button and the assistant call. That extraction is the next slice and is decided (2026-10-30): it is done first, as a refactor with the button's behaviour pinned, and only then does a card's Approve use it.

Tested by `tests/test_quantum_run_snapshot.py` (freshness, outcome, frozen, reading, the envelope, with the real provider's reading of a real single-point and a real frequency output) and `tests/test_ai_assistant_quantum_runs.py` (the real host, the real plugin and tool loop, the budget), driven by `benchmarks/visual/ai_quantum_runs.json`.

## 14. Goals: the wizard's table, as knowledge and never as a way to run

`domain/calculator_goals.py` holds the goal wizard's table: a question a person brings ("Where is the
charge, and how polar is it?"), and the calculators the application chose to answer it, each with a
one-line reason and a role (recommended or optional). The assistant had no equivalent, only a keyword
search. `list_goals` gives it the table as read-only knowledge (`GoalCard`, `goal_cards` in
`domain/calculation_bridge.py`; `CalculationHost.goals()`; `context.calculations.goals()`), with each
entry's route read from the live registry.

**It does not run a goal.** `PropertyPanel.run_goal` builds an execution plan and starts the batch
route, and it never consults the execution policy: a run on one molecule starts every calculator in
the goal with no question at all (`_start_single_run`), and a project run asks only above 200
calculations. A tool that called it would bypass the rule this whole design exists for (ORCA and large
molecules ask first). So a goal is a list of calculators to reach for, and each one is run through
`run_calculator`, checked, gated and recorded on its own. The wizard's caveat is sent with every reply:
the lists are editorial, not a validated protocol.

**Decision most worth challenging:** the assistant cannot run "the recommended set" in one step, which
costs a model several calls where the wizard needs one click. The remedy, if it is wanted, is a typed
recipe (the plan's Phase 2), where each step carries its own policy decision, not a call to `run_goal`.
