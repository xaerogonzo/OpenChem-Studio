# The AI assistant's calculator bridge: design record

**Status: design, written 2026-10-12 before any assistant tool exists.** Part of Phase 1 of the plan
in the session notes. The first PR carries the pieces that need no host code (the execution policy
and the shared search) and this record. **Nothing here lets the assistant run anything yet.** The
host adapter, the tools and the consent UI are the next two PRs, and they follow this document;
where a review changes it, change it here first.

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

**A plugin gets `context.calculations`, a handle with eight operations and no objects behind it.**
It is built from a host object the window hands the `PluginManager`; a context built without one
(a headless run, a test) answers every call with a typed `UNAVAILABLE`, never an exception.

| Operation | Thread | Returns |
|---|---|---|
| `begin_turn()` | GUI | an immutable `TurnContext` (section 6), or `None` when nothing is selected |
| `catalog(query, limit)` | any | `CalculatorCard`s from the registry, by the shared search (section 7) |
| `describe(calculator_id)` | any | one card with its parameters, or `UNKNOWN` |
| `read_results(turn)` | any | the five-state view of the turn's snapshot (section 6) |
| `prepare(turn, calculator_id, parameters)` | any | a `Preparation`: validated and normalised parameters, the execution decision, and a preview, or a typed refusal. **Starts nothing.** |
| `run(turn, run_id)` | worker | for an `AUTO` preparation only: dispatches and waits (section 3) |
| `pending()` | GUI | previews awaiting approval, for the panel |
| `approve(run_id)` / `cancel(run_id)` | **GUI only** | start or drop a pending preview |

`approve` and `cancel` are not reachable from a tool. They are methods on the capability the
**panel** holds, not on the handle the tools get: the tools receive a `ToolBridge` that has the
first six. This is what makes "the model cannot approve its own request" a property of which
object a caller holds, rather than of a check somebody has to remember.

*Decision: the adapter is `app/calculation_host.py`; the handle and its types are in `plugins/`
and `domain/`; the host reaches the plugin through `PluginManager(..., calculation_host=...)`, not
through the `UIRegistry` protocol, so existing test doubles of that protocol are untouched.*

## 3. Request lifecycle, and the thread contract

```
discover -> prepare -> validate -> decide -+-> AUTO ----------------------> dispatch -> record -> serialise
                                           |
                                           +-> CONFIRM -> PREVIEWED -> approve -> dispatch -> record -> serialise
                                                              |
                                                              +-> cancel | invalidate | expire
```

One `run_id` is minted by `prepare` and carried through every step. A tool call that names a
`run_id` it did not receive from `prepare` is refused; one that repeats a `run_id` already
dispatched returns the original outcome and starts nothing.

States: `PREPARED`, `PREVIEWED` (awaiting a person), `APPROVED`, `RUNNING`, `COMPLETED`, `REFUSED`
(the calculator declined: a limit, needs input, needs setup, with its kind), `FAILED`,
`CANCELLED`, `INVALIDATED`, `TIMED_OUT`. A preview is not a job; an approved plan is not evidence
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
* Timeout: `AUTO` requests wait up to the policy's resource class (a few seconds for `INSTANT`,
  a few tens for `SHORT`); on expiry the outcome is `TIMED_OUT` as above.

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
inventory. A new read-only accessor returns every retained record for a molecule, and each is put in
exactly one state:

| State | Meaning | Never |
|---|---|---|
| `current` | its input fingerprint equals the snapshot's for that input | |
| `historical` | retained, fingerprint differs: computed on an earlier structure | shown beside current as if it still applied |
| `refused` / `failed` | the calculator declined or crashed; keeps code, kind, summary, missing inputs | read as a low value |
| `unverifiable` | no fingerprint, or the snapshot has none for its input | called fresh |
| `not_run` | nothing stored | invented as a stale record |

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

`prepare` rejects, with a typed refusal naming the parameter: an unknown calculator id; an unknown
parameter name; a value of the wrong kind; a number outside the declared minimum or maximum; a choice
that is not one of `choices` (stored codes, never the labels); a missing `required` parameter, which
is a `needs_input` refusal listing what is wanted rather than a run; a molecule over the size limit
for a run that must be `AUTO`; a `smiles` parameter that does not parse. Inactive parameters
(`enabled_by`) are dropped by the same `active_parameters` the registry uses. A scientifically
meaningful value is **never silently corrected**: it is refused. Bounded output size is enforced here
too.

## 9. The result envelope

One serialiser, type-aware, in the host layer. Every number the model receives carries: result id
and display name; method and version; the normalised parameters; the input fingerprint and which
representation it describes (drawing, a named conformer, a microspecies at a pH); units, basis or
applicability domain; status (including refusal kind) and freshness state; the caveats; and for
per-atom data the atom-index space. A summary says it is a summary and names how to read the whole
thing. A result kind with no serialiser is reported `unsupported`; it is not forced through a
generic dict. The set of supported kinds is explicit (`PerAtomDataset`, `ReportResult`/`StructureReport`,
`AlertResult`, `SpectrumResult`, `PhCurveResult`, `StructureSetResult`, `TrajectoryResult`), and a
test walks every kind the bridge claims and asserts each number has its metadata.

## 10. Recording, consent state and the system prompt

An AI-requested run is recorded through the normal path, so it appears in Results like any other.
**The assistant's system prompt currently says it cannot modify the project; that becomes false and
changes in the same PR as the first tool that runs a calculation.** The alternative (a temporary,
per-conversation result) was rejected: it would show the model a number the person cannot see, and
the two models must never be mixed. A visible ledger lists what the assistant proposed, ran and was
refused, with molecule, parameters and state. Tool output is sent to the configured provider on the
next request, so a remote provider sees calculator results; the panel says so.

## 11. Acceptance, and what is honestly out of reach until later

Phase 1 is accepted when: the handle exposes none of the container, the bus or the window; search
returns only registered ids; a turn's reads are unaffected by a selection or a result changing
mid-stream; all five states are tested separately; parameters are validated against the real
definitions; the approval path starts nothing without a GUI-side action, cannot be forged or replayed
by a fake provider, is single-dispatch, and cancel leaves nothing running; envelopes carry their
provenance.

The live run (a tool-capable provider, with the sequence **tool call received, preview prepared, no
job started, confirmation awaited** captured) needs the service preview adapter, and
`ClaudeCLIProvider` is excluded because it takes no tools. Giving it a tool protocol is a separate,
optional item with its own tests.

## 12. Slices

1. **This PR.** Execution policy and its measurements; the shared calculator search; this record. No
   assistant tool, no host code.
2. **Host and reads.** `app/calculation_host.py`, the plugin handle, the turn snapshot, the store
   accessor, validation, the serialiser, `catalog`/`describe`/`read_results`/`prepare`/`run` for
   `AUTO` registry calculators, with a fake-provider test harness.
3. **Consent and tools.** Preview, approve, cancel, ledger and status in the panel; the tool
   definitions and the changed system prompt; the service preview adapter; the privacy disclosure;
   "Explain this result".

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
