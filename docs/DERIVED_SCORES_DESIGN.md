# Derived scores: a restricted formula over approved outputs: design record

**Status: design, written 2026-10-12. Slices 1 (the grammar, the evaluator and the units), 2 (the approved output table, its sweep and guards) 3a (definitions, the project-file block, the service and the evaluator) 3b (the Results reader) and 3d (the definition dialog) were built on 2026-10-14 and are described under section 11; the project-table column (3c) is not built, and a decision is owed on it.** It is the second half of Phase 2 of the
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
* `constants`: an ordered list of `(name, value, unit)`, named numbers with a unit that the formula uses as names (slice 2, section 11). At most 12, in the same namespace as the inputs.
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
* **Functions, a closed set of nine** (the first draft of this record counted eight and listed nine). `abs(x)`, `min(a, b, ...)`, `max(a, b, ...)`, `clamp(x, lo, hi)`,
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
* a number literal is dimensionless, **except that a numbers-only operand of `+`, `-`, `min`, `max`, `clamp` and `ramp` takes the unit of the operands that name inputs** (added in slice 2, section 11):
  without it no threshold on a quantity that has a unit could be written;
* the unit the formula works out to must equal the declared `result_unit`, or the definition is refused.

**There are no implicit conversions.** A conversion between two symbols is a named, tested entry in one table, with
the constant and its source; the table starts empty and an entry is added when an approved output needs one.

**Named constants are the strict alternative to a bare number.** A bare number adopts the unit of what it is combined with; a constant is a name with a declared unit, so it adopts nothing, a threshold in the wrong unit is
refused, and a logarithm of a dimensioned quantity is writable by dividing by a constant that carries the unit (`log10(mw / one)` with `one = 1 g/mol`).

**What the unit check cannot do, stated so nobody trusts it for more.** It catches adding an energy to a length,
or taking a logarithm of a dimensioned number. It cannot catch a wrong constant: a literal that is a conversion
factor in disguise passes, because a literal has no unit to check, and a threshold written in the wrong unit passes for the same reason. The definition's display therefore shows the
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
  definition kept as it was read, without breaking others; digest stability.
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

1. **Grammar, evaluator and units**: pure, no UI, with the oracle and the rejection matrix. Mutation-tested. **BUILT (2026-10-14).**

   **As built, and the choices the design left open:**
   * **Two modules and a tool.** `domain/score_units.py` (the unit type and its parser) and `domain/score_formula.py` (tokenizer, recursive-descent parser, the tree, the unit inference and the evaluator), both pure;
     `tools/check_score_formula.py` runs a definition and a value from the command line. The tool is what reaches the modules until slice 3, so both declare `REACHED_BY = "tooling: ..."` for the reachability guard, and that
     declaration must go when slice 3 wires them in (the guard fails a declaration on a module that has become reachable, so it cannot be forgotten).
   * **Three stages that can each refuse and none of which can return a wrong number**: `parse_formula` (syntax, limits, names, arity; a `FormulaError` with a closed `Problem` code and a character position), `check_units`
     (the unit the formula works out to against the declared one) and `evaluate` (a `Refusal` naming the step). `check_definition` is the one call the dialog and the loader make: syntax, names, units, and that no input goes unused.
   * **Numbers** are `digits`, an optional `.digits` and an optional `e[+-]digits`: `.5` and `5.` and `1e` are errors, not guessed at. **Whitespace** is space, tab and newlines. Anything outside ASCII is a syntax error.
     **An exponent** is a whole number from -6 to 6, **a sign is allowed** (`x^-2`), and `x^2^3` is refused (`(x^2)^3` is the way to write it): the grammar's single `("^" INTEGER)?` has no chain.
   * **The depth limit counts every parenthesis, unary minus and call argument as a level**, so none can hide depth, and a long chain of `+` (which nests nothing in the text) is measured after it is built; the node limit is
     counted as nodes are made, so a formula cannot build a tree it would then be refused for. 500 open parentheses are refused by the depth guard long before Python could run out of stack.
   * **A declared input the formula never uses is refused** (decided here; the design was silent): a number shown as evidence for an input the formula does not read is evidence of nothing.
   * **Units.** A unit is `1`, or `numerator` or `numerator/denominator`, each a `*`-separated product of `SYMBOL` or `SYMBOL^n`, **at most one `/`**, so there is one reading of every unit; an empty string is refused (write
     `1`) so "no unit written" cannot mean "dimensionless" by accident, and an exponent is a non-zero whole number up to 12. The symbol list is a **starter** read off the unit strings the application's results carry today; slice 2 reconciled the spellings the
     results use (`A` and `Å`, `deg` and `degrees`, `""` and `dimensionless`) per approved output, in its `carried_as`, and not in this list, and added `L`.
   * **Verified three ways.** The rejection matrix (every construct the grammar does not have, one case each); **an independent oracle**: 6000 seeded random formulas in the grammar evaluated by the product and by a separate
     evaluator written in the test over Python's own parse tree, which agree to the value or both refuse (and a second pass that Python reads the canonical text the same way, so the minimal parentheses of `render` are right
     and not merely round-trippable through our own parser); and **a guard that reads the modules' syntax trees** and fails on an import of `ast` and its relatives or a call to `eval`, `exec`, `compile` or `__import__`
     (not on `re.compile`, which compiles a regular expression), tested against each way of doing it so a clean result means something.
2. **The approved output table and its sweep and guards**: through the registry, on the census panel. **BUILT (2026-10-14).**

   **As built, what the sweep measured, and the one thing it made slice 1 change:**
   * **Three pieces.** `domain/score_outputs.py` (the table, `check_inputs`, `accept_value`, `values_by_name`; pure), `tools/sweep_score_outputs.py` (observes the census run through a new `observer` hook on
     `tools/calculator_census.py`, lists every typed number with its unit and the input it came from, and `--check` holds the table to what the registry produced) and `tests/test_score_outputs.py`. Like the formula
     modules the table declares `REACHED_BY = "tooling: ..."` until slice 3.
   * **What the panel produced** (29 rows; the always-on set and every registry calculator; the sidecars and the NMR database absent, as in the census): **191 numeric outputs: 31 descriptors, and 160 facts of `bird_aromaticity`, `geometry_analysis`, `griffin_hlb`, `hansen_solubility`, `hbond_sites`, `homa_aromaticity`, `joback_properties`, `logd`, `oxygen_balance`, `solubility`, `substance_analysis` and `torsion_table`.**
     Most of the facts cannot be ids: 96 are torsions (named by their atoms) and 22 are ring aromaticity values (named by ring size and composition), and five ids are carried by two facts of one report. The sweep marks
     those ambiguous and the guard refuses them.
   * **First finding: most report calculators do not carry a number.** A `Fact`'s value is `Any`, and many calculators put a string there that is already rounded by the person's decimal-places setting
     (`polar_surface_area` carries `'63.60'`; `cns_mpo`, `topology_analysis`, `surface_analysis`, `polarizability`, `dipole_moment`, `bbb_descriptors`, `elemental_analysis`, `huckel_analysis` and `mass_spectrum` do the same), and the
     batch table's `_as_float` parses it back. **A score rests only on a number the producer typed** (`int` or `float`, not a `bool`, finite): a score over a rounded string would change when a display setting did. Those twelve
     are the only report calculators on the panel that carry any typed number (of 31); the others have to type their values before they can be approved.
   * **Second finding: the always-on descriptors are stored twice.** 21 of the 31 run on both the drawing and a geometry and store one result for each under one id (10 run only on a geometry). A score must read exactly one, so
     **an approved output is read from the drawing** (`READ_FROM`). Geometry-based outputs (shape descriptors, force-field energies, projections) are a separate review: a number of one conformer is a number of that conformer.
   * **The table: 21 outputs** (17 descriptors, and 4 facts of `oxygen_balance` and `solubility`) under **19 endpoint tags**, approved by hand from the sweep. An entry is `output_id`, the unit in the language of
     `score_units`, **`carried_as`** (the exact string the result carries), the endpoint, and `approved` (a date: the design said `since`, an application version, which is not known when the entry is written).
     **Not approved, and why:** both `logd` outputs (see the next bullet); `hbond_sites` Donors and Acceptors and the solubility calculator's log mol/L (each measured identical to an always-on output on every census row where both exist, 25 of 25 and 16 of 16, and available only after an
     extra calculator run, so they add a way to refuse and no information); every output of a hidden or experimental calculator (Joback is limited and hidden by default); `mcgowan_volume` (its unit, `cm³/mol ÷ 100`, cannot be written) and Hansen's parameters (`MPa^0.5`:
     exponents are whole numbers); `molar_refractivity` (it carries no unit, and the sweep is not the place to supply one); formal charge, `np_likeness_confidence`, and the substance counts; every output whose id depends on the
     structure; and every geometry-based output.
   * **`logd` was approved and then withdrawn, and the reason is the lesson.** `LogD at pH 7.4` is one method, Henderson-Hasselbalch (with no ionizable centre by the application's own rule it is trivially LogP, which is the same
     method with nothing to ionize). `LogD at pH 7.4 (approximation)` is a different and weaker estimator (the dominant microspecies' LogP) and is labelled so on purpose. Which one a molecule gets depends on whether
     it has an ionizable centre and, if it has, on whether pkasolver is configured. On the census panel (no sidecars) the plain id therefore exists only for the 16 non-ionizable molecules, where it equals LogP, and the
     approximation for the 9 ionizable ones (methylhydrazine, phenylhydrazine, aspirin, haloperidol, imipramine, ibuprofen, glycine, metformin, a tripeptide); four salts and complexes fail. **So the panel can only show the
     plain id in its degenerate case, and a guard that cannot exercise an entry's main path is not guarding it.** The rule this gives: an output whose main path needs an optional tool cannot be approved until the
     census can run that tool. Folding the two into one stable id would be the wrong repair: it would hide the weaker estimator behind a clean name.
   * **Two outputs that agree on every shared row must share a tag** (`identical_pairs`, in the sweep and in the tests). The ESOL descriptor and the solubility calculator's log mol/L were identical on 16 of 16 rows, and a
     tag that was merely remembered would have let a formula combine a number with itself. It catches a copy and not two methods that estimate one quantity, which differ in value and which only a person can tag.
   * **Spellings are reconciled per entry, not by a table of synonyms.** The application writes one unit several ways (`A^2` and `Å²`, `deg` and `degrees`, and no unit at all for a logarithm). An entry declares both the unit
     and the string it must carry, and `accept_value` refuses any other string and converts nothing. `""` is accepted only for an entry declared `1`, and a logarithm (`log mol/L`, logP, logD) is declared `1`. A producer that changes
     its units turns a score into a refusal, not into a different number.
   * **The two rules, in code.** `check_inputs` returns the units a definition's inputs have, or a `FormulaError`: a bad name, an output that is not approved (`Problem.OUTPUT`), one output under two names, and two outputs of one
     endpoint (`Problem.CONSENSUS`, saying why). `values_by_name` reads a value for each input or refuses naming the one that has none: never a zero, never a skipped term.
   * **Guards.** Every entry resolves, through the registry on the census panel, to a finite number on at least five rows carrying `carried_as`; none comes from a calculator that is not stable or limited and offered by default;
     and a rename of a fact label turns it red and says which scores it breaks. The control arms run **real** calculators: Joback (a number the panel really produced, refused as hidden) and `polar_surface_area` (an id that exists
     whose value is text, refused). The endpoint groups and every unit are written out in the test, so changing either is a decision made where a reviewer sees it.
   * **What slice 1 needed (found by writing the first example against a real output).** The unit rule "a number is dimensionless, and `ramp` needs x, a and b in one unit" made `ramp(tpsa, 140, 60)` a refusal, so **no threshold
     on any quantity that has a unit could be written**, which is the whole use of `ramp` and of `clamp`. **A numbers-only operand of `+`, `-`, `min`, `max`, `clamp` and `ramp` now takes the unit of the operands that name inputs**
     (`score_formula._adopt`). Nothing is converted and nothing is guessed (the other operands decide it); two named inputs in different units are still refused, a dimensioned argument of `ln`, `log10`, `sqrt` or `exp` is still
     refused, and a wrong constant is still not caught, as before. **A consequence stands:** a logarithm of a dimensioned quantity cannot be written at all, because there is no way to divide by a unit.
   * **Named constants, added after the review** (`domain/score_constants.py`, pure): `Constant(name, value, unit)`, at most 12, under the rule for input names and in the inputs' namespace, a finite number (never a bool), a unit
     from the same language. A constant is used as a name, so it adopts nothing: `ramp(tpsa, hi, lo)` with `hi = 140 Å^2` is accepted, with `hi = 140 nm^2` it is refused, and `log10(mw / one)` with `one = 1 g/mol` is
     dimensionless. One nothing uses is refused like an input nothing uses. `check_inputs` and `values_by_name` take them, and `tools/check_score_formula.py` has `--constant NAME=NUMBER,UNIT`. 23 mutants, all caught.
   * **Left for later, each with its reason.** (1) *How the dialog offers a bare number and a named constant* is slice 3's. (2) *Typing the values of the report calculators that carry rounded text* (bbb_descriptors, cns_mpo,
     dipole_moment, elemental_analysis, huckel_analysis, mass_spectrum, polar_surface_area, polarizability, surface_analysis, topology_analysis on the census panel) is a change to each producer, and **it has no shortcut**:
     typing integer-looking text in the adapter (`report_adapter._split`) would be wrong, because an integer-looking line is not necessarily an integer quantity (with `decimal_places=0` a rounded Randic index reads `6`). Each
     producer must build typed `Fact`s itself, with a golden-file check that the lines people see do not move, and the batch table and its exports would then carry the unrounded number. The first worth doing are
     `polarizability` and `topology_analysis`'s indices, and only when someone wants them in a score; most of the rest repeat an always-on descriptor. (3) *Geometry-based outputs* need a
     rule for which conformer a score reads. (4) *An output whose main path needs an optional tool* (logD's pKa path, anything from the pKa or ADMET sidecars) waits until the census can run that tool.
   * **Mutation-checked: 57 mutants** of the adoption rule, the table's rules, the table's own entries and the sweep. 56 were caught; the survivor is equivalent (`abs` or `ln` adopting a unit: a one-argument call has nothing to adopt from). The limits of the sweep survived at first for slice 1's reason (the tests read them by name), so they are pinned as numbers.
3. **Definitions, persistence, evaluation on read, and the surfaces**, in four parts (the recipes went the same way):
   * **3a. Definitions, the project block, the service and the evaluator. BUILT (2026-10-14).** Described below.
   * **3b. The Results reader. BUILT (2026-10-14).** Described below.
   * **3c. The project-table column** (source `score`, not `derived`) and the exports. **NOT BUILT, AND A DECISION IS OWED (found 2026-10-14).** The project table is filled by a batch run into its own `BatchResultStore`, apart from the
     session result store the Results reader reads, and `BatchService._fill_row` hands every descriptor a conformer when one exists. **Measured on the census panel, 7 of the 17 approved descriptors give a different number on a conformer
     than on the drawing** (`bertz_ct` by up to 2265, `sa_score` by up to 6.1, `labute_asa` by 72, `np_likeness`, `esol_logs`, `num_hba`, `num_rotatable_bonds`; an explicit-hydrogen molecule changes what these count), so a score computed from the
     table's own cells would silently differ between molecules with and without a conformer: the "number of one conformer" trap that decision 12 avoids. The same defect is visible in Results today (after a conformer exists, aspirin's
     Synthetic Accessibility reads 6.445 where it read 1.58; queued as its own task). Options: **(A)** evaluate the column against the session store, the drawing's current results: honest and the same as Results, but a project run does not fill the session
     store, so cells read "not calculated" until a molecule has been selected; **(B)** evaluate against the table's cells and refuse any cell computed on a conformer (the batch would stamp which input each cell used); **(C)** first fix the batch to
     compute structure-level descriptors on the drawing, then take (B) with the stamp. **Recommendation: C, then B; build nothing until the descriptor defect is fixed.** Scores already say, in their evidence, that they were read from the drawing.
   * **3d. The definition dialog. BUILT (2026-10-14).** Tools > Derived Scores...; live validation, a bare number and a named constant both offered with the stricter one said, its help topic and the drive script. Described below.

   **3a as built, and the choices the design left open:**
   * **Five modules.** `domain/score_definition.py` (`ScoreDefinition`, its stored form, the label and field rules, the digest, ids), `domain/score_definition_store.py` (a project's definitions and the `derived_scores` block),
     `domain/score_value.py` (reading the inputs and evaluating: `evaluate_score`), `services/score_service.py` (the host's side) and the `ScoreDefinitionsChanged` event. All pure but the service, which is built by `bootstrap`
     and is why the four formula modules are now reachable and lose their `REACHED_BY = "tooling: ..."` declarations.
   * **A score id is `user.<slug>`, made by the service from the label and never changed**, so a label can be edited without losing the score's identity; `_2`, `_3` are added when the slug is taken, counting ids a kept entry holds.
     **The suffix `(user-defined, unvalidated)` is not stored**: `display_label` adds it, so editing the label cannot remove it.
   * **The label may not be close to a name the application provides**: equal to, containing or contained by (case, accents and punctuation removed, three characters or more) the id or display name of any registered calculator, or the
     name of an approved output. The registry's names are read when the check runs, and the approved outputs' from the table. It runs when a definition is made or edited and **not when a value is read**: a calculator registered
     later can make an old label look like a name, and that is a reason to ask for a new label, not to refuse a number.
   * **Nothing a person wrote is dropped because this build cannot read it.** A definition from a newer format, a damaged one (the design said "skipped"), and a block from a newer envelope are each kept as they were read and written
     back unchanged (`KeptEntry`); a store holding a foreign block refuses every change. An id that is only being carried is never handed out again.
   * **The block is written only when there is something to write.** A project that never used scores is byte for byte the file it always was, so an older build opening it loses nothing: the cost design section 12 decision 10
     accepted (an older build drops a block it does not know) now falls only on a person who authored a score.
   * **A value is read from the molecule's current results only, by the assistant's own classification** (`turn_snapshot.classify_results`: one rule for what "current" means). An input refuses the score, naming the input, when
     nothing was ever calculated, when only results of an earlier structure exist, when the current result is a refusal or a failure, when the fact is missing or held twice, when the producer did not type it as a finite number,
     when it carries another unit (nothing is converted), and **when two current results computed with different settings give different numbers** (the score will not guess between two pH values). Only the drawing is read.
     Every unread input is named, not only the first. A zero is a number.
   * **The service never starts a calculation.** `create`, `update` and `remove` check the definition under the label and formula rules and publish `ScoreDefinitionsChanged`, which the window turns into "this project has unsaved
     work" (a definition is never also a result); `values_for(model)` classifies the molecule's stored results and evaluates every definition.
   * **The window carries the store through File > Save, File > Open, recovery and the drive harness's `open_project`.** `ProjectDocument` gained its fifth field; five tests that unpacked it positionally now read it by
     attribute, which is what its docstring asked for.
   * **Verified.** The evaluator is tested on every way an input can fail to be read (each refuses with no number), the store on carrying everything it cannot read through a save, and the whole route runs: the real always-on
     descriptors compute, the project saves its results and a score, reopens, and the score has its value without anything running. **Mutation-checked: 132 mutants** of the definition rules, the store, the evaluator, the service and the wiring through File > Save, Open and recovery. 130 were caught (the limits survived at first because the tests read them by name, as in slices 1 and 2, and one real gap: nothing had another calculator's records present while the wanted one was absent); one was removed by simplifying a comparison every successful read had already made, and one is equivalent (the blank-molecule guard before asking for fingerprints only avoids a pointless exception).
   **3b as built, and what driving the real application found:**
   * **A score is a `ScoreAnswer`** (`domain/score_answer.py`, a `ReportResult` subclass, built by `ScoreService.answers_for` each time the reader refreshes and never stored, the way `RecipeAnswer` is). **It is one fact** under a
     new category, `FactCategory.DERIVED` ("Derived scores", ordered last, open by default), labelled `<label> (user-defined, unvalidated)`, basis HEURISTIC, with the formula, every input (name, value, unit, the output and the stored
     result it was read from), every constant and the digest as the evidence that the value's tooltip shows, and the one limitation, "A formula a person wrote. Nothing has checked it against measurements.", in the footer.
     `Provenance` says `created_by="user"`, `method="derived_score:<format>"` and `validation="user_defined_unvalidated"`.
   * **A score with no number is a refusal in the application's own vocabulary** (a failed report of kind `NEEDS_INPUT`, so it counts and reads as every other refusal): the line above the facts names each input that could not be read
     and why, and the footer says the formula once, as one sentence. It is never stale, because it is evaluated against the structure as it is now: after an edit its inputs are no longer current and it refuses, which says so.
   * **Driving the real application found a defect no unit test had**: a calculator finished and the score stayed empty. A result's own event (`ReportComputed` and its kin) reaches the reader **before** the result store has recorded it,
     so a score waiting for that result evaluated too early and was never told to look again. The panel now schedules one coalesced re-read when a result is recorded for the molecule shown (`ResultRecorded` arrives after the store has
     it; a flood of descriptors is one refresh), and the regression test fails without it. The same run showed the label rule working as designed (an example label "TPSA window" was refused as too close to `tpsa`: decision 8), and a
     footer that ran the per-input lines together, now one sentence.
   * **Drive steps `score_define` and `score_results`** and `benchmarks/visual/score_results.json` (12 assertions; shots `score_results_value.png`, `score_results_refused.png`, `score_results_list.png`). **Mutation-checked: 56 mutants** of the projection, the service's reader entries and the panel wiring: 55 caught, one removed as dead code (an unread input's line, unreachable once the footer stopped carrying per-input lines). The survivors were all in the wiring (nothing had tested the entries with no project or a stranger, the panel with only scores attached, or that the re-read after a recorded result is deferred and not synchronous), plus a refusal code the tests read by name.
   **3d as built, and what driving the real window found:**
   * **Four parts.** `domain/score_editor.py` (pure: the `Draft` a form holds as strings, `check_draft` -> `DraftCheck(ok, message, problem, where, position, worked_out)`, the picker's `output_choices` (the approved table in words, each with its unit and what it measures), `suggest_name`, `pointer_lines`), `ui/dialogs/score_dialog.py` (`ScoreDialog` and `ScoreHost`), `ScoreService.preview` (the value a draft would have, stored nowhere) and the Tools-menu entry with its wiring in `main_window.py`. One modeless window, raised when it is already open.
   * **The dialog knows no rules.** It asks `check_draft` after every keystroke, which asks the very `check_score_definition` that `ScoreService.create` and the project loader ask, so what it says while a person types is what Save and Open will say. A problem is shown with the box it belongs to outlined (one outline round the whole group for the inputs and for the constants) and, for a syntax or unit problem inside the formula, a caret under the place. A rule that knows the box says so (`FormulaError.field`: the label, an input name, the owner, the note); otherwise the problem's code decides.
   * **Nothing is stored until Save.** Typing changes a draft; Save makes or changes the score (an edit keeps its id), Revert puts the saved one back, changing which score is shown while the form has unsaved changes asks first, Delete asks, and a score a build cannot use (a newer format, a damaged one) is listed with its reason and cannot be chosen, and is written back as it was.
   * **The preview is a read, not a run.** The last line shows what the draft gives for the molecule selected in the project, read from its CURRENT results through the same reader a saved score uses (`ScoreService.preview`), so a draft whose input nobody calculated says which, and the window has its number when the calculator finishes (it re-reads on `MoleculeSelected`, `MoleculeChanged` and `ResultRecorded`, and never opens itself). `ScoreHost` holds lookups and the three writes of the score service and nothing that could start a calculation, and a test fails if typing, saving or previewing asks the descriptor service for anything.
   * **The two ways to write a threshold are both offered, and the window says which is stricter**: a bare number in the formula takes the unit of what it is added to or compared with; a named constant (name, value, unit) carries its own and is checked strictly. A constant's value is spelled as a number in the formula is (`14.` and `.5` are problems, not guessed at): the first version accepted `14.`, which the formula grammar refuses, and the drive found it because it typed one.
   * **What driving the real window found, none of it visible to the unit tests that were green** (each is fixed and pinned): a unit clash inside the formula (`psa + logp`) was pinned on the Unit box and drew no caret, because the unit problem was mapped to a field by its code alone (a unit problem that has a place in the formula is the formula's; one without, the declared unit, is the unit box's); a constant `14.` checked; the picker said "(mol/L) (mol/L)" for an output whose title already carries its unit; the longest picker entry (ninety characters) sized the combo box and made the whole form scroll sideways; an outline set on a combo box replaces the style's drawing and squashed its arrow, so the groups are outlined in frames; and the caret was drawn under the edit, a few pixels off the text it pointed at, because the edit's padding is the style's, so it is now drawn under a copy of the formula in the same monospaced font. The list also showed a sideways scroll bar for a label that is always followed by "(user-defined, unvalidated)": it elides, with the full text in the tooltip.
   * **Drive step `score_dialog`** (`new`, `choose`, `fill`, `press`, `confirm`, `expect`) works the REAL controls (it presses Add and Remove, types into the edits and presses Save), and `benchmarks/visual/score_dialog.json` passes 18 assertions with seven shots (`score_dialog_*.png`). **One of fourteen full runs failed an assertion that the other thirteen passed** (Delete first asked "discard unsaved changes?" about a form nobody had touched, so the form was dirty when it should have been clean); it was not reproduced by a regression test written to catch it or by the thirteen runs after it, and **its cause is not known**. The drive step now logs the form's draft and its saved copy whenever a step starts with the form dirty, so a recurrence can be traced.
   * **Mutation-checked: 161 mutants of the view model, the dialog and the window wiring. **103 were caught the first time and 56 survived** (two more had a pattern that matched twice and were re-run). The survivors were: **one real defect** (a saved score emptied of everything was treated as a blank form, so choosing another score discarded the emptying without asking), **three lines that did nothing** (a `KeyError` that cannot be raised, a list elide mode that is the list's default, and an or-it-is-a-new-score clause in Save that a form with content already satisfied), **about forty missing tests** (each button's own state without a project, which the disabled panes round them had hidden from `isEnabled()`; what Save stores, owner, note and constants; that a constant that is not a number is a refusal and not a crash; the three preview subscriptions; that a closed window is read again when it is opened; the caret's width at the end of a long formula; a formula over the limit; a unit spelled another way) and **eight equivalent or untestable mutants**, left as they are: a default field for a problem no draft can raise, a unit rule on problems with a place (only the formula has one), a negative caret position (repeating a space a negative number of times is empty either way), a revert that does not mark the form clean (it leaves the saved copy as it was), a list guard two others make redundant, an outline condition that `where` already implies, a caret for any field that has a place (none has), and `raise_()` (nothing to observe offscreen). After the new tests every survivor is one of those eight.**

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
    hand, so it is the one place the cost is lost work, accepted while the suite is in beta; it falls only on a project that has a definition, because the block is not written otherwise. Reversible later by
    stamping only files that contain a definition.

11. **A numbers-only operand takes the unit of what it is combined with** (slice 2). It makes thresholds writable and gives up nothing the check could ever catch, since a literal has no unit to check; but it is a relaxation
    of the strictest reading of section 4, and `energy + 5` is now valid. The explicit alternative, a declared named constant with a unit (`limit = 140 Å^2`), now exists beside it
    (`domain/score_constants.py`); how the dialog offers the two is slice 3's to decide.
12. **Only typed numbers, only of the drawing** (slice 2). It excludes most report calculators until their producers type their values, and every geometry-based output until it is reviewed. Both are real losses of usefulness,
    preferred to a score that moves with a display setting, or with whichever conformer happened to be stored.

## 13. Not here, deliberately

Trained models and applicability domains (a plugin); a consensus of predictors; per-atom aggregates as inputs;
quantum-chemistry outputs and recipe outputs as inputs; scores of scores; a second missing-value policy; sharing
definitions outside a file; and any wording that calls a score a predictor of an endpoint.
