# Derived scores: a restricted formula over approved outputs: design record

**Status: design, written 2026-10-12. Nothing in this document is built.** It is the second half of Phase 2 of the
plan in the session notes; the first half, typed recipes and the Lewis pairing, is
[`RECIPES_DESIGN.md`](RECIPES_DESIGN.md). This is the "custom predictor" idea **narrowed**: a person writes a
formula over numbers the application already computes, and the result is labelled as exactly what it is, a formula
somebody wrote, with nothing said about whether it predicts anything. A trained model is a different feature (the
plugin extension point in `ROADMAP.md`, "Future extension point: ML Calculator Plugins") and a consensus of
predictors is refused (section 6). Where a review changes this document, change it here first.

Every statement about how the application works today was read in the source on the date above and names the
function or file. Statements about what to build are decisions; the ones most worth challenging are collected in
section 12.

## 1. What exists, and what that forces

| Fact | Where | What it forces |
|---|---|---|
| **No user-formula feature exists, and nothing in `src/` calls `eval`.** Searched 2026-10-12 for derived, custom and computed columns, for formula columns, and for `eval(` and `literal_eval`: no feature, no call. The one expression-like thing is the regulatory engine's predicate language, a dict with an `op` drawn from a closed set, evaluated against a molecule to a boolean; it is the precedent for the stance here (closed operations, a malformed expression is an error) and it evaluates SMARTS, not numbers. `SOURCE_DERIVED` in the batch model is the word "derived" used for one column, the batch run's *Status*, and means "made by the batch service itself". | `chem/regulatory/predicates.py`, `domain/batch.py`, `services/batch_service.py` (`_status_column`) | This is new. A score must not reuse the source name `derived`, which already means something else. |
| **A number reaches a table through one reducer, and a report fact is addressed by its display label.** The column id of a report fact is `calculator:<calculator id>:<fact label>`. The reducer's own docstring records that, when it was written (2026-08-05), none of the calculators then registered returned a bare scalar. | `chem/result_reduction.py` (`reduce_result`, `_reduce_report`) | A formula cannot name an input by a label that is also display text: a label edit would silently re-point or break a score. This is the trap behind the lesson "a `choice` parameter stored the English on the screen". Section 3. |
| The column ids are treated as stable already: `_reduce_report` documents that its ids are byte-identical to the older parsing path's "so a saved batch table, a chart column and an exported CSV all keep working". The calculator census fails a *moved cell*. | `chem/result_reduction.py`, `tests/test_calculator_census.py` | The existing id is the natural address, and the existing census is the existing alarm for a rename. The approved table adds a named pin, so the failure says which scores it breaks. |
| **Published scores exist here as calculators, and the standard they meet is a worked example.** CNS MPO is checked against a published worked example (ChemAxon's aspirin: total 5.75, every component 1.00 except HBD 0.75), and the HBD breakpoints were chosen because that one data point discriminated between two published forms. | `chem/mpo_scores.py` module docstring | A user's formula can have none of that. It must never wear a published name, and its label must say so. |
| **"One name, two quantities" is a recorded trap, four times, and consensus scoring is refused on local evidence**: Vinardo's median change in rank correlation against Vina was +0.000 while single series swung by 0.4. | `ROADMAP.md` ("Consensus scoring. Refused on local evidence.") | Averaging two predictions of one endpoint must be unexpressible, not merely discouraged (section 6). |
| `SupportStage.EXPERIMENTAL` means "implemented, not yet validated for default use, always hidden by default". `Basis` has two values, `DETERMINISTIC` and `HEURISTIC`, deliberately without a confidence number. The tautomer feature already ships a provenance label, `VALIDATION_UNVALIDATED = "unvalidated"`. | `domain/calculator_support.py`, `domain/structure_issue.py`, `chem/tautomer_distribution.py` | The vocabulary exists. A score is `HEURISTIC`, always carries an explicit validation label in provenance, and is opt-in by construction. |
| The documentation guards derive their calculator counts from the live registry (`test_the_guide_states_the_real_number_of_calculators`), and the support-stage, reachability and census guards walk it. | `tests/test_docs_are_current.py` | A score defined at run time must **not** be a registry calculator. It would make every one of those guards depend on whatever a person typed. |
| `ReportResult` and `Fact` carry units, a basis, evidence and limitations; Phase 1's envelope has a `report` branch among its eight kinds (`descriptor`, `report`, `alert`, `per_atom`, `spectrum`, `structure_set`, `ph_curve`, `trajectory`). | `domain/report.py`, `domain/result_envelope.py` (`SUPPORTED_KINDS`) | A score's value is a `ReportResult` with one `Fact`, so it reaches the Results reader, the exports and the assistant's envelope with no new serialiser. |
| `Provenance.parameters` is a free dict on every result, and the ML-calculator note names it as where a plugin reports model version and applicability domain. | `ROADMAP.md`, `domain/common.py` | A score's formula, schema version and validation label go here, and the dict is also where a reader checks them. |

## 2. What a derived score is

A **definition** is data, owned by a project:

* `score_id`: `user.<slug>`; always namespaced.
* `label`: what the person calls it. Shown everywhere as `<label> (user-defined, unvalidated)`.
* `schema_version`: of the definition format, so a build can refuse one it does not understand (section 8).
* `inputs`: an ordered list of `(name, output_id)`, where `name` is the identifier the formula uses and `output_id`
  is a key of the **approved output table** (section 3). At most 12.
* `formula`: text in the grammar of section 4.
* `result_unit`: declared, and **checked** against the unit the formula works out to (section 4).
* `on_missing`: in this phase exactly one value, `refuse`. A second policy needs a reason in writing first.
* `owner` (free text, who wrote it), `created`, `note`.

A **value** is a function of a definition and the molecule's *current* results. It is evaluated when read, never
stored (section 8). Evaluating it yields a number with a unit, the list of inputs actually used (each with its
output id, value, unit and the identity of the result it came from), and a digest of the definition.

## 3. Approved outputs: what a formula may name

A formula may name only an entry of the **approved output table**, never a calculator, a result id or a label
typed by the person. Each entry:

| Field | Meaning |
|---|---|
| `output_id` | The existing batch column id (`descriptor:<id>` or `calculator:<id>:<fact label>`). Reused, not invented, because saved tables and exports already depend on it. |
| `unit` | Declared in the table and **checked on every evaluation** against the unit the result carries. A mismatch is a refusal, not a conversion. |
| `endpoint` | A tag naming the quantity measured, for example a partition coefficient. Two outputs that estimate the same quantity share one tag. Declared by a person, reviewed. Used by the consensus rule (section 6). |
| `since` | The application version that approved it. |

**What may be approved.** A scalar, numeric, finite value with a unit, produced by a calculator whose support
stage is `STABLE` or `LIMITED` and that is offered by default. **Not** in this phase: an `EXPERIMENTAL` or hidden
calculator's output (a formula that is itself unvalidated does not also rest on an unvalidated number); a
per-atom dataset reduced by an aggregate (the aggregate would be a hidden parameter of the score); anything from a
quantum-chemistry run (that evidence has its own identity rules, `RECIPES_DESIGN.md`); a recipe's output.

**The table is built by sweeping, then approving by hand.** A script lists every numeric scalar the registry
produces on the calculator census panel, with its unit; a person approves entries and tags their endpoints. Guards:

* every entry resolves, **through the registry**, to a finite number carrying its declared unit, on the census
  panel (a rename of a fact label turns this red, and says "this breaks scores that use it");
* no entry comes from an `EXPERIMENTAL` or hidden calculator;
* every entry has an endpoint tag, and the tags are drawn from one reviewed list.

The honest limit: the table is a hand-approved list, and an endpoint tag can be wrong. A wrong tag is a wrong
guard, found by review and by the first user who tries to average two logP estimates and is not stopped.

## 4. The grammar, and why it is a parser and not a sandbox

**There is no `eval`, no `exec`, no `compile`, and no use of Python's own parser as the evaluator.** The text is
tokenised and parsed by a small recursive-descent parser written for this purpose into a tree of frozen
dataclasses, and the tree is evaluated by walking it. Restricting Python's `ast` to a whitelist is the usual
shortcut and is declined: its failure mode is a construct nobody listed, and a grammar has no constructs nobody
listed.

```
expr   := term (("+" | "-") term)*
term   := unary (("*" | "/") unary)*
unary  := "-" unary | power
power  := atom ("^" INTEGER)?
atom   := NUMBER | NAME | NAME "(" expr ("," expr)* ")" | "(" expr ")"
```

* **Tokens.** ASCII only: a Unicode digit or a look-alike operator is a syntax error, not a number.
  `NUMBER` is decimal with an optional exponent. `NAME` is `[a-z][a-z0-9_]*`. `INTEGER` is a literal, and its
  absolute value is at most 6, so no expression can build a huge number by exponentiation.
* **Names.** A `NAME` that is not followed by `(` must be one of the definition's declared inputs. There are no
  globals, no constants by name, no attributes, no indexing, no strings, no comparisons, no conditionals.
* **Functions, a closed set of eight.** `abs(x)`, `min(a, b, ...)`, `max(a, b, ...)`, `clamp(x, lo, hi)`,
  `ramp(x, a, b)`, `sqrt(x)`, `ln(x)`, `log10(x)`, `exp(x)`. `ramp` is 0 at `a`, 1 at `b`, linear between, and
  clamped outside; the order of `a` and `b` gives the direction, so a falling desirability is `ramp(x, bad, good)`.
  It is the building block of the multiparameter scores already in the application (`chem/mpo_scores.py` uses the
  same shape) and it is what makes a weighted sum of desirabilities writable.
* **Limits.** At most 500 characters, 200 tree nodes, depth 24. Beyond that the definition is refused with the
  limit named.
* **Evaluation** is IEEE double arithmetic. A division by zero, a domain error (`sqrt` of a negative, `ln` of a
  non-positive), an overflow or any non-finite intermediate **refuses the value**, with the step named. It never
  propagates a `nan` or an `inf` into a number that looks finite.

**Units, strict and small.** A unit is a product of symbols with integer exponents, from a closed list. The
symbols are **opaque and unrelated to each other**: `eV` and `kcal` are different symbols, and `%` and `1` are
different symbols. Then:

* `+`, `-`, `min`, `max` and `clamp` require identical units;
* `*` and `/` combine exponents; `^n` multiplies them;
* `ramp(x, a, b)` requires `x`, `a` and `b` in one unit and gives the dimensionless unit;
* `sqrt`, `ln`, `log10` and `exp` require a dimensionless argument;
* a number literal is dimensionless;
* the unit the formula works out to must equal the declared `result_unit`, or the definition is refused.

**There are no implicit conversions.** A conversion between two symbols is a named, tested entry in one table, with
the constant and its source; the table starts empty and an entry is added when an approved output needs one.

**What the unit check cannot do, stated so nobody trusts it for more.** It catches adding an energy to a length,
or taking a logarithm of a dimensioned number. It cannot catch a wrong constant: a literal that is a conversion
factor in disguise passes, because a literal is dimensionless. The definition's display therefore shows the
formula with the unit beside every input, and says nothing further.

## 5. The label, and what it must never say

* Every surface shows `<label> (user-defined, unvalidated)`: the Results reader, the project table header, the
  exports, the assistant's envelope. The suffix is not removable and not part of the person's text.
* Provenance: `created_by="user"`, `method="derived_score:<schema_version>"`, and in `parameters`:
  `validation="user_defined_unvalidated"`, the formula, the schema version and the definition digest. The `Fact`
  has `basis=HEURISTIC` and carries the formula and every input (output id, value, unit, source result) as
  `evidence`, and one fixed limitation: *"A formula a person wrote. Nothing has checked it against measurements."*
* **Names.** A label is refused if its normalised form (case-folded, punctuation and spaces removed) equals, or
  contains, or is contained by, the normalised id or display name of any registered calculator or approved output
  (three characters or more, so a short token does not block everything). The comparison is **derived from the
  registry**, so it cannot rot as a hand-kept list of published names does. It cannot know a published score that
  has no calculator here. For those the namespace, the badge and the provenance carry the burden, and this
  document does not pretend the name check closes it.
* A score is never described as a prediction of an endpoint, in any string the application generates. A test
  walks the strings.

## 6. Consensus is unexpressible

**A definition with two inputs of the same `endpoint` is refused.** The message says why: two estimates of one
quantity, combined, are a consensus predictor, which this project has measured and refused (`ROADMAP.md`). This is
a structural rule, in the same family as "applying carbon-13 to every oxygen is unexpressible" rather than
validated after the fact. It does not detect a consensus built from outputs that were tagged differently by
mistake, and it does not stop a person writing the same average somewhere else; it stops the application from
offering one as a feature. If a consensus of two predictors ever earns a place, it earns it with a preregistered
benchmark showing it adds information, as a calculator, not as a formula.

## 7. Missing, refused and stale inputs

* An input is read from the molecule's **current** results only (Phase 1's `CURRENT`). A historical or
  unverifiable result is not used, and the refusal names it.
* A refused, failed or absent input refuses the score, naming the input and why. **Never a zero, never a skipped
  term**: dropping a term from a sum silently changes what the sum is.
* `on_missing` has one value in this phase because the other policies a person asks for (skip the term, use a
  default) change the meaning of the number without changing its label.

## 8. Persistence and evaluation

* **Definitions are project data**, in a block of their own in the project file (key `derived_scores`), with an
  envelope version of their own, so a number can be reproduced by whoever opens the file. A definition can be
  exported to and imported from a small JSON file; an imported definition is validated exactly as a typed one.
* **Definitions are not results and do not go through `result_codec`.** They are plain data with an explicit
  `to_dict` and `from_dict`; there is no class on an allow-list to construct.
* **A build that has never heard of the key drops the block on save, as it does for every block beside the
  document** (`ProjectService` writes `project.to_dict()` plus the blocks it knows; `SCHEMA_VERSION` is 1 and
  has never moved). For derived data that costs a re-evaluation. For authored work it costs the work.
  **Decision (owner, 2026-10-12): accepted for now.** The suite is in beta and compatibility with earlier builds is
  a low priority, so the file is **not** stamped with a newer `schema_version`: an older build opens a project that
  holds definitions and drops them on its next save, like every other block it does not know. If that ever matters,
  the remedy is to stamp only the files that contain a definition (`_migrate` already refuses a newer version with a
  message); it is deliberately not built.
* **A definition this build does not understand** (a newer `schema_version` or envelope) is **carried through
  unchanged on save** and shown as "written by a newer version, not evaluated". Ignoring it with a warning, which
  is what happens to a newer QC-run block, would delete a person's work on the next save, and a formula is
  authored where a QC run is derived.
* **Values are not stored.** They are a function of the definition and the current results, are cheap, and a stored
  copy could only disagree with its inputs. What a read records is the evidence (inputs, units, source results,
  digest).
* **Evaluation** is pure and runs wherever it is asked, on a frozen read of the molecule's current results. It does
  not run a calculator: a score never starts work, so it has no execution policy to decide.
* **Surfaces.** The Results reader (a one-fact report), the project table (a column with source `score`, not
  `derived`), the exports. A definition editor with live validation is the one new dialog.

## 9. The assistant

The assistant can read a score through the envelope's `report` branch, with its label, its evidence and its
limitation intact, **once** there is a read for it: scores are not stored, so `read_results` (which reads the
result store) does not see them. A `read_scores` that evaluates against the turn's frozen snapshot is a separate,
small step and is not assumed. **The assistant cannot create or edit a definition in this phase.** A formula
written by a model is an agent-authored predictor, and that is a decision for its own review, not a side effect.
It may suggest formula text in conversation, for a person to enter.

## 10. Tests

* **Grammar rejection**, each its own case: attribute access, indexing, a string, a comparison, a conditional, a
  keyword, an unknown function, a function used as a value, a name that is not an input, a Unicode digit, a
  look-alike operator, `__import__`, an exponent of 7, `9^9^9`, 501 characters, 201 nodes, depth 25, an empty
  expression, a trailing operator, unbalanced parentheses.
* **An independent oracle.** Random expressions in the grammar evaluated by this evaluator and by a separate,
  simple evaluator written in the test over Python's own parse tree for the arithmetic subset; they must agree to
  the last bit or both refuse. (The oracle lives in the test and never in the product, which keeps the rule that
  nothing in the product evaluates Python.)
* **Units**: each rule in section 4 accepted and refused once; `result_unit` mismatch; an opaque-symbol case
  (`eV` plus `kcal` refused); dimensionless-argument rules.
* **Refusals**: division by zero, `ln(0)`, `sqrt(-1)`, overflow, a non-finite input; each names its step; none
  returns a number.
* **The approved table**: every entry resolves through the registry on the census panel with its declared unit;
  a renamed label turns it red; no `EXPERIMENTAL` or hidden source; every entry has a tag from the reviewed list;
  a fixture with two same-endpoint inputs is refused.
* **Names**: a collision with a registered display name, an id, a substring of one; a normalisation case; a name
  that is fine.
* **Persistence**: a definition round trip; an unknown schema version carried through a save unchanged; a damaged
  definition skipped without breaking others; digest stability.
* **Never zero**: an absent, refused and historical input each refuses the score, and a mutant that substitutes
  zero is caught.
* **The label**: every surface that shows a score shows the suffix (walked, not listed); no generated string calls
  a score a prediction.
* **The registry is untouched**: defining a score does not change `CALCULATOR_DEFINITIONS`, the calculator count,
  or any reference document.
* **No evaluator of Python**: a test parses the score modules' own syntax trees and fails on an import of `ast`,
  or a call to `eval`, `exec` or `compile`. It reads the tree, not the text, because a text scan would match this
  rule's own docstring (the lesson "three guards I wrote matched the prose explaining their own rule").

A driven run follows the UI slice, builds its own state, and ends in a verdict.

## 11. Slices

1. **Grammar, evaluator and units**: pure, no UI, with the oracle and the rejection matrix. Mutation-tested.
2. **The approved output table and its sweep and guards**: through the registry, on the census panel.
3. **Definitions, persistence, evaluation on read, and the surfaces**: the project block, the Results one-fact
   report, the project-table column, the exports, the definition dialog, its help topic (a new surface needs one,
   and a guard checks), the drive script.
4. **Later, each its own review**: `read_scores` for the assistant; assistant-authored definitions, if ever; any
   second `on_missing` policy; any conversion entry.

## 12. Decisions most worth challenging

1. **A hand-written parser instead of a whitelisted `ast`.** More code to own and to test, in exchange for a
   language with no construct nobody listed. The oracle test is what makes that code trustworthy.
2. **Strict, opaque units with no conversions.** It will refuse a formula a chemist finds obviously fine, because
   two energies are in different units. The alternative, quiet conversion, is the silent change of meaning this
   project keeps meeting.
3. **Scores are not registry calculators.** They are missing from the calculator reference, the goals, the launcher
   and the assistant's calculator search, by design (section 1, row on the guards). It is a real loss of findability.
4. **Values are never stored.** Simple and honest; a project opened in a build that lacks an input's calculator
   shows the definition and no value.
5. **Definitions are project-scoped.** A person's favourite scores do not follow them from project to project
   except by export and import. The alternative (per user) makes a number unreproducible by anyone else.
6. **Endpoint tags make consensus unexpressible, and a hand-reviewed list can be wrong** (section 3).
7. **Outputs of experimental or hidden calculators are excluded.** It keeps one layer of "unvalidated" from
   resting on another, and it removes some of the outputs people would most like to combine.
8. **The name check is derived from the registry and cannot see a published score the application lacks.**
   Over-blocking is possible (a name containing "pKa") and is preferred to a hand-kept list that rots.
9. **The assistant cannot author a definition.** A model that can write a formula can also write one that
   happens to confirm what the person hoped.
10. **No file-level version stamp for older builds** (section 8). A build that has never heard of the `derived_scores`
    key drops the block on its next save, as it does for every other block. This is the one block a person wrote by
    hand, so it is the one place the cost is lost work, accepted while the suite is in beta. Reversible later by
    stamping only files that contain a definition.

## 13. Not here, deliberately

Trained models and applicability domains (a plugin); a consensus of predictors; per-atom aggregates as inputs;
quantum-chemistry outputs and recipe outputs as inputs; scores of scores; a second missing-value policy; sharing
definitions outside a file; and any wording that calls a score a predictor of an endpoint.
