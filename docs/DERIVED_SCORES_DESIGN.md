# Derived scores: a restricted formula over approved outputs: design record

**Status: design, written 2026-10-12. Slices 1 (the grammar, the evaluator and the units), 2 (the approved output table, its sweep and guards) 3a (definitions, the project-file block, the service and the evaluator) 3b (the Results reader) and 3d (the definition dialog) were built on 2026-10-14 and are described under section 11; the project-table column (3c) was built on 2026-10-15, after the descriptor defect that blocked it was fixed (#330).** It is the second half of Phase 2 of the
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
* `on_missing`: `refuse` (a missing input refuses the score) or, since slice 4c, `default` (an input that was never calculated takes the number the definition declares for it, section 7).
* `defaults`: with `on_missing: default` only, and then never empty: `(input name, number)` pairs, each in the unit its approved output carries. A definition with defaults is format 2; one without is format 1.
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
**Measured 2026-10-15 (slice 4b): none does, so the table is still empty.** The 21 approved outputs carry six units (`1`, `%`, `g/mol`, `Å^2`, `mg/mL`, `mol/L`); the polarizability, approved afterwards, adds a seventh (`Å^3`, a volume, offered in one unit and by one output). Every unit is carried by outputs that measure
one quantity, except the solubility, which is offered in two: `mg/mL` and `mol/L`, both of the one endpoint `aqueous_solubility_intrinsic`. A formula cannot name both (two inputs of one endpoint are refused as
consensus), and a conversion between them needs the molecule's molar mass, which is not a constant a table can hold. So a conversion would be built for no formula anybody can write. `tests/test_score_outputs.py` pins
this: every unit must say what it measures, and a quantity offered in two units by outputs of different endpoints turns it red, which is the moment to add an entry (or to say in writing why not).

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
* `on_missing` has two values (slice 4c). `refuse` is the rule above. `default` is **the reason in writing this record required for a second policy**: a score may read an optional input whose calculator a person has not
  run, and a person who knows what they mean by "not known" (a neutral desirability of 1, say) can say so once, in the definition, instead of leaving the whole score refused. It changes the meaning of the number
  without changing the formula, so it is the narrowest policy that does that:
  * **per input, never for the score as a whole.** A default is declared for a named input; an input with none still refuses.
  * **only for an input that was never calculated** (`InputState.NOT_RUN`). An input that was calculated and refused, failed, belongs to an earlier structure, carries another unit or is ambiguous still refuses: each of
    those is an answer about this molecule, and a default would hide it.
  * **never a score worked out from defaults alone.** At least one input must have been read, or the score is refused saying so.
  * **never silent.** Every surface that shows a number that used a default says so and names the input (section 11, 4c).
  The other policy people ask for, skipping a term, is still not offered: dropping a term from a sum silently changes what the sum is.

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

**Built (slice 4a): the assistant can read a score, with its label, its formula, every input and its limitation intact.** Scores are not stored, so `read_results` (which reads the result store) does not see
them; `read_scores` evaluates the project's definitions against the turn's frozen snapshot.

**Built (slice 4d, which amends decision 9 of section 12): the assistant can PROPOSE a score, and only a person can save one.** `propose_score` checks a model's request by exactly the rules a typed definition meets and
leaves a card in the assistant's panel; **the score exists only after the person presses Approve** on that card. The assistant still cannot create, edit or delete a definition: a proposal is not one, the approval is on an
object a tool is never handed (as a run's is), and what is saved is the definition that was shown.

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
     *(Measured on 2026-10-14, and the cause of the double storage was a defect, not a design: the 21 differed between the two inputs because the conformer's hydrogens are atoms and the drawing's are implicit, so the reader
     showed a different Synthetic Accessibility after a conformer arrived. A conformer request now computes only the ten geometric descriptors, `DescriptorProvider.geometric_descriptor_ids`; the 21 exist under the drawing
     alone. `READ_FROM` is unchanged and was right: a score reading the drawing never saw the conformer's figures.)*
   * **The table: 21 outputs** (17 descriptors, and 4 facts of `oxygen_balance` and `solubility`) under **19 endpoint tags**, approved by hand from the sweep (22 outputs under 20 tags once the polarizability was typed, 30 under 28 once the eight topology indices were, and 31 under 29 once the aromatic ring count was, and 41 under 37 once ten of the topology counts were; see their entries below). An entry is `output_id`, the unit in the language of
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
   * **3c. The project-table column** (source `score`, not `derived`) and the exports. **BUILT (2026-10-15), after a decision that the design had owed.** The question was which numbers a table column reads: the project table is filled by a batch run into its own store, and the batch used to hand every descriptor a conformer, so 7 of the 17 approved descriptors read differently in the table than in Results (`bertz_ct` by up to 2265, `sa_score` by up to 6.1, `labute_asa` by 72, `np_likeness`, `esol_logs`, `num_hba`, `num_rotatable_bonds`). The options were (A) evaluate against the session store, (B) evaluate against the table's own cells and refuse a conformer's, (C) fix the batch first and then take B. **C was taken**: #330 made every column compute on the input it declares, the drawing for every approved output, so the table's cell and Results' stored result are one number, and a parity test holds them to it. Described below.
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
   * **Drive step `score_dialog`** (`new`, `choose`, `fill`, `press`, `confirm`, `expect`) works the REAL controls (it presses Add and Remove, types into the edits and presses Save), and `benchmarks/visual/score_dialog.json` passes 18 assertions with seven shots (`score_dialog_*.png`). **One of fourteen full runs failed an assertion that the other thirteen passed** (Delete first asked "discard unsaved changes?" about a form nobody had touched, so the form was dirty when it should have been clean); it was not reproduced by a regression test written to catch it or by the thirteen runs after it. **Its cause was found in slice 4c, when a fifteen-run loop of the save sequence reproduced it twice**: the form's label had ONE EXTRA LETTER at its end (`Blend with a defaultr`, `...defaultt`), so the form really was different from the saved one. No code path in the application or the script types a letter. The step opened the window through `MainWindow.show_scores()`, which raises and ACTIVATES it, so a person typing in another window had their next key land in the dialog's Name field, which is the focused one. Measured with the new `active=` in the step's log: after the menu's route the active window is the `ScoreDialog`; after the driven route it stays the main window. **The driven step no longer activates the window** (`show_scores(activate=False)`, `WA_ShowWithoutActivating`): 0 failures in fifteen runs afterwards, against 2 in fifteen before. A person's typing is not controlled, so that is consistent with the explanation and not a proof of it. **What this does not fix**: the application takes the foreground when a driven run starts, so keys typed before the person clicks elsewhere go into whatever the main window has focused; the step now also logs the form's draft and its saved copy when a save or revert leaves it unsaved.
   * **Mutation-checked: 161 mutants of the view model, the dialog and the window wiring. **103 were caught the first time and 56 survived** (two more had a pattern that matched twice and were re-run). The survivors were: **one real defect** (a saved score emptied of everything was treated as a blank form, so choosing another score discarded the emptying without asking), **three lines that did nothing** (a `KeyError` that cannot be raised, a list elide mode that is the list's default, and an or-it-is-a-new-score clause in Save that a form with content already satisfied), **about forty missing tests** (each button's own state without a project, which the disabled panes round them had hidden from `isEnabled()`; what Save stores, owner, note and constants; that a constant that is not a number is a refusal and not a crash; the three preview subscriptions; that a closed window is read again when it is opened; the caret's width at the end of a long formula; a formula over the limit; a unit spelled another way) and **eight equivalent or untestable mutants**, left as they are: a default field for a problem no draft can raise, a unit rule on problems with a place (only the formula has one), a negative caret position (repeating a space a negative number of times is empty either way), a revert that does not mark the form clean (it leaves the saved copy as it was), a list guard two others make redundant, an outline condition that `where` already implies, a caret for any field that has a place (none has), and `raise_()` (nothing to observe offscreen). After the new tests every survivor is one of those eight.**

   **3c as built, and what the table drive and the parity test found:**
   * **A score is a column of the table, computed from the table's own cells when the table is shown, and never run.** `domain/score_table.py` (pure) reads the cell of each input's column for a row, evaluates the
     formula with the rule Results uses (`score_value.evaluate_score_with`: the evaluator now takes the reader as an argument, so the stored results and the table's cells are two readers of one rule), and returns
     a COPY of the table with the score columns added; the run's own table is never written into, because it is mutated as rows arrive. Nothing is stored, so a score defined, edited or removed changes the table at
     once without another run (`ProjectTableView.refresh_scores`, driven by `ScoreDefinitionsChanged` through `ResultsWorkspace`), and the column is in the table's exports and analytics because it is an ordinary column of
     the table they are handed (`ProjectTableView.table()` returns the scored one).
   * **A cell is read by the rules of an output**: an input that is not a column of the table, a molecule it was not computed for, a failed or refused cell, a cell with no number and a cell whose unit is not the approved one
     each refuse the score for that row and name the input; never a zero, never a skipped term, nothing converted. A table is a snapshot, and so is its score column: it is exactly as current as the cells it reads, as every other
     column is. Results is where a score is re-evaluated against the structure as it is now.
   * **The score columns are the FIRST columns after the molecule's name**, in the order the scores were defined. They were appended last at first, and the table drive's first shot showed them off the right edge of the dock
     behind thirty calculator columns: the numbers a person asked for by name are the ones they came to read.
   * **A score whose inputs the run did not compute has no column**, because every row would say the same; the table says it once, under its status line: "Scores not shown, because this run did not compute what they read: <score>
     reads <what>." A column carries a `note` (the formula, what it reads, the declared unit, the digest, where the numbers came from and the one limitation), shown on its header and in the report's methods section, and a
     cell carries a `detail` (the inputs the row's number was computed from) on its hover; both are new, optional fields of the batch's column and cell, empty for everything a calculator makes. Scores are their own group in the
     Columns menu ("Derived scores"), their header carries the suffix so it is in the CSV header, and the CSV carries the number whole.
   * **The parity test is what makes reading the table's cells safe** (`test_main_window_scores.py`): a real window, a molecule that HAS a conformer, the descriptors asked for on it as the window does, a real batch over the
     same molecule, and every approved output read both ways, state and number. It found one gap before anything shipped: a calculator that declines has only a placeholder column (`calculator:<id>`, for the rows that failed),
     so the table said "not computed" where Results said "declined"; the placeholder's cell is now read as the refusal it is, and a score on a calculator that declined for every row says why in each row instead of
     vanishing. The same test pins aspirin's Synthetic Accessibility at the drawing's 1.58 and not the conformer's 6.445.
   * **The table drive found two more** (`benchmarks/visual/score_table.json`, 12 assertions, three shots; new steps `table_scores` and a `project_table` shot): the score columns were off screen (above), and the Derived
     Scores window's Save stored the lists it passes in the definition, because `ScoreService.update` stored what it was given while `create` made tuples; a list made the definition unhashable, the parsed-formula cache
     refused it and Results said "Could not read the scores". `update` stores the same shapes `create` does.
   * **Not here, deliberately.** The older Batch panel's own table did not show scores (its view was built without a provider; `ProjectTableView` takes one: done afterwards, see "The Batch panel's own table" below), and the run picker did not tick a score's inputs for a person (done afterwards, see "Ticking what the scores read"): a
     score whose inputs were not run said so under the table, which was the whole of the help it gave. Both were small follow-ups.
   * **Mutation-checked: 102 mutants of the table module, the evaluator seam, the view and dock wiring, the window's provider, the service's edit and the report. **85 were caught the first time, 16 survived and one pattern did not match.** Eleven survivors were missing tests (that a placeholder column with no cell for a row says "not computed" and not "not a column", that a cell with no column is never a number, that a unit refusal names the unit, that a placeholder cell that did not fail is not a refusal, the four digits, the refusal's kind, the separators of a note that names two things or two scores, that a table with no columns has nothing to say, that the per-atom data and the rows are the copy's own) and **five are equivalent and left**: a descriptor's "placeholder" is its own column, a placeholder lookup with no name finds nothing, a `bool` guard on a name that is empty for a descriptor, the unread-input filter on a value that has none, and the `str()` of a name that is already a string. After the new tests every real survivor is caught.**

   **4a as built (`read_scores`, the assistant reads a score), and what driving it found:**
   * **Parts.** `domain/score_reading.py` (pure: `read_scores(turn, names, limit)` -> `ScoresView`; a name is a score id, a label or the label as shown, case-folded, and a name that matches none is `not_found`, never matched
     loosely), `TurnContext.scores` (the project's definitions, frozen with the results when the turn begins; `CalculationHost.begin_turn` captures them only when the score service holds the turn's own project),
     `PluginCalculations.read_scores` (needs no host: it reads only the frozen turn), `result_envelope.score_envelope_of` / `scores_view_envelope`, `ToolBridge.read_scores` and the sixth tool, `READ_SCORES`, with the system prompt
     and the panel's privacy note.
   * **Both halves of a read are frozen at Send.** A formula edited, a score removed or made, a calculator that finishes or another molecule selected while the reply streams changes nothing about what the turn reads; the
     next turn sees it. The evaluation is the one Results and the project table use (`score_value.evaluate_score`), so the model is told exactly what a person looking at Results is.
   * **What a model is told per score:** the label always ending "(user-defined, unvalidated)", the formula, the declared unit, the definition's digest, every input with the output it reads and the state it was read in (and
     its value and unit when it was), every constant, the freshness ("current": a score is never stored) and two caveats (the limitation the Results reader shows, and that a score is not a prediction and is never to be reported as
     an experimental or predicted property). **A value only when every input was read from CURRENT results**; otherwise `outcome: refused`, a reason naming each input that could not be read, and no `data` block, which the tool
     description tells the model never to fill with a number or a zero. A list is cut to the result caps and says how many it left out; at most 40 are read at once.
   * **What a model is never told:** the owner and the note, which are a person's free text (asserted in the real tool loop by a script that defines a score with a private owner and note), and **a molecule other than the
     selected one** (`scores` is the only argument; an undeclared argument is refused before the handler runs). **There is no call that writes a score**: the plugin handle and the tool bridge have none, and a test reads
     their public surface for any create, update, remove, define, delete, save or write.
   * **What leaves the machine changed**, and the panel now says it: a remote provider sees a score's name and formula (a person's own text) when the assistant reads it. Found by reading the drive's screenshot, not by a test: the
     note under the conversation still said only "calculator results".
   * **Verified.** 56 tests across `test_score_reading.py` (the module, the envelope, rounding, caps, refusals) and `test_ai_assistant_scores.py` (the real host's `begin_turn`, edits and removals after the turn, the tool's schema,
     description and system prompt, and a scripted provider on a real worker thread), plus the pins in `test_plugin_calculations.py` and `test_ai_assistant_bridge.py`. **`benchmarks/visual/ai_scores.json` passes 10 assertions** in the
     real window with the assistant's real Send: no scores in the project, a score with a number and one refused, the calculator the refused one waits on is NOT started by reading it, a score named by its label and a name
     that does not exist, and a model that names a molecule or asks for a score to be made is refused with nothing written. New `ai_expect` key `tool_results_exclude` (what must NOT appear in anything a tool returned).
     The drive passed on its first run: it found nothing the unit tests had not.
   * **Mutation-checked: 91 mutants** of the reading module, the envelope, the host and turn wiring, the plugin handle, the bridge and the tool. **79 were caught the first time, 10 survived and two patterns did not match (rewritten, and then caught).** Nine survivors were missing tests (that `defined` counts the project's scores and not only those named; that the default limit is the module's forty; that another project's scores are never frozen into a turn; a host with no score service; the freshness note; the caps on one score's inputs and on its constants; that scores the read limit left out are counted in the envelope too; that the bridge cuts a long list to the reply budget and says so) and **one is equivalent and left**: the host's `tuple(...)` of the store's definitions, which `build_turn_context` makes again.
   * **Not here, deliberately:** a score in `read_results` (it is not a stored result), the assistant making or changing a definition, a tool that runs the calculators a score is waiting on (it has `run_calculator` already,
     under the execution policy that decides whether a person approves first).

   **4c as built, a default for an input nobody calculated (the second `on_missing` policy), and what driving it found:**
   * **The definition.** `ScoreDefinition.defaults` (a tuple of `(input name, number)`), `ON_MISSING_DEFAULT`, `policy_for(defaults)` (which policy and format a set of defaults makes), `FORMAT_REFUSE = 1`, `FORMAT_DEFAULTS = 2`
     and `SCHEMA_VERSION = 2` (the highest format this build reads). **A definition without defaults is byte-for-byte what an earlier build wrote, with the digest it always had** (`defaults` is written and hashed only when
     there are some), and a build that reads only format 1 keeps a format-2 definition as "written by a newer version" and writes it back unchanged (tested by reading a saved project with `SCHEMA_VERSION` set to 1).
     The checks: the policy and the defaults must say the same thing, each default names an input the definition has, once, and is a finite number, and the format is the one the policy needs.
   * **The evaluation** (`score_value`): `InputState.DEFAULT`, applied in `_with_default` to an input that is `NOT_RUN` and for which the definition declares a default, and only when the stored policy is `default`
     (a policy this build does not know is read as `refuse`, never as a default). A score with no input read is refused ("worked out from defaults alone"). `ScoreValue.defaulted` lists the inputs a default stood in for.
   * **Every surface says so.** Results: the value reads `0.4775 (default used for ob)`, the evidence names the input and says the line is a default and not a result, the limitations say a default stood in, and the answer's
     provenance lists `defaulted` (for a number only: a refusal has none). The project table: the cell ends in `*`, its hover says which input and that it was not computed in this run, the column note lists the defaults and
     what `*` means, **and a score with defaults has a companion column right after it** (`inputs given a default`, text) because a CSV carries the number whole and a `*` would be lost the moment the table was exported;
     an input with a default does not make the score "not shown", unless no input at all was computed. The assistant: the outcome is `computed_with_defaults` (never `computed`), `defaults_used` names the inputs, a caveat
     says a default is not a result, and `declared_defaults` is in every read of a score that has any. The window: a default box beside each input (empty means none), a preview that says a default was used, and a typed
     default that is not a plain number outlines the inputs box.
   * **What driving the real window found, which the unit tests did not**: a refused answer's provenance said it had used a default though it had no number (a score made of nothing but a default); the unit test had checked the
     refusal's message and not its provenance. The drive also showed the dialog's default box needing a placeholder that says what it is for ("default if not calculated"), since the row has no column headings.
   * **Verified.** `benchmarks/visual/score_defaults.json` passes 11 assertions in the real window: a default typed in the real input row, previewed, saved; Results, the project table (grid, hover, column note, the real "Export CSV"
     file with the companion column) and the assistant each saying a default was used; a score of nothing but a default refused in Results and omitted from the table with its note; and, once the calculator has run, the same score
     computed with no default and the assistant told `computed`. New drive inputs: a third element of a `score_dialog` fill input is its default, `score_define` takes `defaults`, `score_results` takes `defaulted`,
     `table_scores` takes `csv_text`.
   * **Mutation-checked: 102 mutants** of the definition, the evaluator, the Results reader, the project table, the service, the assistant's envelope and tool, the window's view model and the dialog. **94 were caught the first time and 8 survived.** Seven were missing tests (that the digest of a definition without defaults is the literal master computes for it, and that a default is hashed at the precision it is declared; that a default carries its output's unit; that the table does not use defaults the evaluator would not; that the declared defaults are cut by the caps; that a default comes back to the form to twelve figures; that typing a default checks and previews again) and **one was equivalent**: a guard that only repeated one the outcome already made, removed from the code. After the new tests every survivor is caught or gone**
   * **Not here, deliberately:** a default for an input that was calculated and refused (it would hide the refusal); skipping a term; a default that varies by molecule; a default in a unit other than the output's; the
     Batch panel's own table (still no scores then; see "The Batch panel's own table").
   **4d as built, the assistant proposes a score and a person approves it, and what driving it found:**
   * **Parts.** `domain/score_proposal.py` (pure: `check_request` turns a request into a definition by the rules a typed one meets, `ProposalBook` holds proposals for a person, `card_of` says what the person is shown);
     `CalculationHost.propose_score` (any thread, **stores nothing**), `pending_scores`, and `approve_score` / `cancel_score` (GUI thread, for a button); `PluginCalculations.propose_score` and `list_score_outputs` for a tool
     and `PluginCalculationApprovals.approve_score` / `cancel_score` / `on_score_finished` for the panel only; the envelope serialisers; the seventh and eighth tools, `list_score_outputs` and `propose_score`; and the panel's
     `_ScoreCard`.
   * **What a model may say, and may not.** A request has `label`, `formula`, `result_unit`, `inputs` (`{name, output}` with an id from `list_score_outputs`), optional `constants` and `note`, and **no other key**: an owner, an id,
     a format, a policy or a default is refused by name, because none is the model's to give. Types are never coerced (a string where a number belongs, a bool, a non-finite number, an input that is not an object). The owner of
     an approved score is `AI assistant (you approved it)`, set by the application. The label is checked against the application's own names, so a model cannot call its formula "TPSA" or "CNS MPO". A refused request comes
     back in the request's own terms (the field, the rule, the place in the formula) so the model can correct it, and **nothing is shown to the person for one**.
   * **What the person sees and decides.** A card of plain text (a label, a formula or a note a model wrote is never read as markup): the label as it will be shown, the formula, each input as the application names it, each
     constant with its unit, the declared unit, **the value it gives for the selected molecule from the turn's frozen results** (or why it has none yet) and who it will say wrote it, with "Nothing is saved unless you approve".
     Approve makes the score through the same `ScoreService.create` the Derived Scores window uses, from the definition that was shown (the request is not read again), and it is refused, and says why, if the project is
     no longer the one it was proposed in or the rules now refuse it (a label that has since become too close to a calculator's name, a full project). Cancel saves nothing. Each decision is announced once, shown in the
     ledger and the transcript, and **told to the model with the user's next message**.
   * **Limits.** At most five proposals wait together, the same score proposed again while it waits is the one that waits, a proposal is bound to its project (and decided void at the next Send if the project changed), and a
     project already holding the most scores refuses a proposal.
   * **The residual risk, stated.** A model that can write a formula can write one that happens to confirm what a person hoped, and a person can approve a card without reading it. The card is built to make reading cheap
     (the formula, what each input is, the value, the owner) and the application never calls the result a prediction, but it cannot make anyone read.
   * **Verified.** **112 new tests** (`test_score_proposal.py`: the request rules, the book, the card; `test_ai_assistant_score_proposals.py`: the real host and panel with a scripted provider on a real worker thread, the real Approve and Cancel buttons, notes riding with the next message, a model that cannot save or approve) plus the pins in `test_plugin_calculations.py` and `test_ai_assistant_bridge.py`. **`benchmarks/visual/ai_score_proposals.json` passes 9 assertions** in the real window with the assistant's real Send and a real Approve and Cancel button: a proposal is a card and
     nothing is saved; Approve saves it with the assistant as owner, it is in Results like any other, and the next message carries the note; a label like the application's own name, and a formula that adds an area to a plain
     number, are refused with a field and a place; a second proposal is cancelled and nothing is saved. New drive inputs: `ai_card` takes `"card": "score"`, `ai_expect` takes `score_proposals`, `scores_stored`,
     `scores_owner` and `sent_contains`. The drive passed on its first run and found nothing the unit tests had not.
   * **Mutation-checked: 120 mutants** of the request rules, the book, the card, the host, the plugin handles, the envelopes, the bridge, the tools and the panel. **101 were caught the first time and 19 survived.** Seventeen were missing tests or code that reached around what it should have gone through (the list of outputs bypassed its own handle, a card event could add a second card, two clauses of the host did the same thing and are one now), and the tests were written: that an input or a constant may carry no extra key and a constant's name is text, the owner's words and the limit of five, a turn begun in another project, the project one short of full, an approval after both the window and the score service moved, a project with no room at approval, the ledger and transcript lines of a decision, the strip of cards, a button taking its card away even when the host announces nothing, and a listener undone on unload. **One is equivalent and left**: the bridge's `bounded_json` on a proposal's reply, which cannot exceed its budget at the sizes the definition rules allow. After the new tests every survivor is caught or gone**
   * **Not here, deliberately:** the assistant editing or deleting a score, choosing the owner, proposing a default or a policy, or a score over a geometry; and a model that approves its own proposal (there is no such call).
   **4b, a conversion entry: measured, not built** (section 4). No approved output needs one, and the guard that says when one does is in `tests/test_score_outputs.py`.

   **The polarizability, as built (the first report calculator typed for scores; a follow-up after slice 4):**
   * **The gap.** The calculator's first line was a fact whose value was the text it shows (`'18.11'`), so no score could rest on it. The design said each producer must type its own values, with a golden check that the lines people see do not move,
     and that the first worth doing were the polarizability and `topology_analysis`'s indices.
   * **What it is.** `compute_polarizability` hands over the number it already holds: the same `Fact` (label, rounded `display_value`, units `A^3`, basis) with its `value` the float. Nothing in the adapter changed, and an integer-looking line is not
     typed anywhere. The project table's cell keeps its text (`18.11`) and now holds the exact number; its exports carry it whole. Approved as `calculator:polarizability:Molecular polarizability`, unit `Å^3` carried as `A^3`, endpoint
     `molecular_polarizability` (the isotropic molecular polarizability, as a volume), a tag chosen here for review: no other approved output estimates it.
   * **Only the default answer is typed, and that is the decision.** The calculator has three estimators behind one id and one fact label (Jensen's additive scheme, Miller's ahc and ahp) and an option that computes the major microspecies, which is
     a different structure. They differ (Miller's two methods by 16% on CBr4 alone, which the method tests record), and a score reads one number under one id, so a score that read whichever ran last would change when the person changed an option, with nothing in the formula to show it. Jensen on the
     drawing is typed; the others stay text, and a score over them is refused with a reason (`accept_value`: "the result is text, not a number a score may read: only a calculator's default answer is typed as a number"), which replaced a
     message that named a Python type, because this wording is now reached by running Miller's method and not only by a defect. The same rule is the rule for the next report calculator typed.
   * **Golden check.** `tests/fixtures/polarizability_lines.json` is 91 observations (13 molecules, 7 ways of asking: the default, each method by its label, the microspecies option with and without a Miller method, and an unknown label), recorded from
     the code before the change through the registry: every line, label, unit, basis, refusal and table cell text. After the change none moved.
   * **Found while driving it.** With the producer's typing removed the project table still made a score from the rounded text (0.4404 where the Results reader refused), which is the table-versus-reader disagreement typing exists to remove: an
     output approved before its producer typed it would have passed the table and failed Results, and `test_every_approved_output_resolves_through_the_registry_with_its_declared_units` is what stops that.
   * **Measured.** Jensen gives 18.11 / 5.75 / 19.93 A^3 for aspirin / ethanol / caffeine and Miller's ahp 18.29 / 5.08 / 21.43; so Jensen is 13% above Miller on ethanol, which is the direction and about the size of the calculator's own caveat (Jensen runs roughly 11% high on saturated
     molecules); no experimental value was checked here. The score `ramp(alpha, 30, 3)` is 0.4403, 0.8981 and 0.3728, which the table, its CSV and (for aspirin) the Results reader show.
   * **Tested and driven.** `tests/test_polarizability_typed.py` (the golden check; the typed number is the one the provenance records, unrounded; Miller, the microspecies option and a failure are never typed; the table cell), the output tests (unit,
     quantity, sweep), and `tests/test_main_window_scores.py` (the real window: a score over the polarizability is the formula of the recorded number, refused after each other way of asking, and the table agrees). **Mutation-checked: 9 mutants of the
     producer and the table entry, all caught.** `benchmarks/visual/score_typed_polarizability.json`: VERDICT PASS, 5 assertions; with the typing removed it fails 2.
   * **Not here.** `topology_analysis`'s indices (the other first candidate; done, see the next entry) and the rest of the rounded-text calculators, each its own PR under the same rule.

   **The topology indices, as built (the second report calculator typed for scores; a follow-up after slice 4):**
   * **The gap.** The Topology Analysis report is 27 lines, and every fact's value was the text its line shows (`'6.11'`, `'246'`), so no score could rest on it. The design named this calculator's indices, with the polarizability, as the first worth typing.
   * **What it is.** `compute_topology_analysis` computes the eight graph indices once, writes each line from the number in the formats it always used, and gives the fact the number: Platt, hyper-Wiener, Wiener, Szeged and the Wiener polarity number as `int`
     (they count pairs, paths or edges), Randić, Balaban J and Harary as `float`. Approved as `calculator:topology_analysis:<label>`, unit `1` carried as no unit, with **eight endpoint tags of their own** (`wiener_index`, `hyper_wiener_index`, `harary_index`,
     `randic_index`, `balaban_j_index`, `szeged_index`, `platt_index`, `wiener_polarity`): they are eight different quantities, so none is a consensus of another, and the tags are for review. Each is the graph WITHOUT hydrogens of the structure the registry hands the
     calculator (the ChEMBL parent: a salt is read as its parent, and one the registry cannot reduce is refused, as before).
   * **What is not typed, and why.** The counts (atoms, bonds, ring and chain counts, the cyclomatic number, rotatable bonds, stereocentres): four are always-on descriptors already (heavy atoms, rings, rotatable bonds, stereocentres) and the rest nobody has asked for;
     typing one is a PR of its own under the same rule (ten were typed afterwards: see the entry on the topology counts). The per-atom eccentricity and distance-degree datasets stay out too (reducing one by an aggregate would make the aggregate a hidden parameter of the score).
   * **Exact types are a requirement, not a taste.** The project file's codec (`result_codec.encode`) takes only the exact types `int`, `float` and `str`. `Descriptors.BalabanJ` returns a NumPy `float64` for ordinary molecules (ethanol) and a plain `float` for a
     single atom, and the Randić index summed an empty list to the `int` 0 on a molecule with no bond: left alone, the first would have failed to SAVE a project holding the result and the second would have carried an `int` where a `float` is promised. Each
     is wrapped at the producer, `test_the_eight_indices_have_their_number_typed_and_no_other_fact_does` pins the exact type of every index on the 20 panel molecules that complete, and a mutant that leaves any one unwrapped is caught (the Balaban one too, which proves the wrapper is needed).
   * **A conformer is a different number.** Aspirin is 13 atoms as drawn (Wiener 246, Randić 6.109) and 21 with its hydrogens (Wiener 850, Randić 9.518), which the note on `DRAWING` in `domain/calculator.py` already said of the topological calculators. A score reads the
     drawing's result in Results and in the table: the existing parity test (`test_every_approved_output_reads_the_same_in_the_table_as_in_results_for_a_molecule_that_has_a_conformer`) now covers these eight, and a new window test reads a molecule that HAS a conformer and
     asserts 246 in both.
   * **Golden check.** `tests/fixtures/topology_analysis_lines.json` is 132 observations (22 molecules, six ways of asking: the default, 0, 1 and 8 decimal places, one past the end of the range and one that is not a number), recorded from the code before the change through the
     registry: every line, label, unit, basis, refusal and table-cell text. After the change none moved. (An empty drawing is not in the panel: RDKit's Balaban function raises on it before a report exists, which has nothing to do with typing.)
   * **Found while writing the tests.** The calculator's description and the module docstring said the Szeged index "strictly exceeds" the Wiener index "for a cyclic graph". It does not where every ring is a triangle: cyclopropane, oxirane, aziridine and spiropentane are
     equal (3 and 3, 3 and 3, 3 and 3, 14 and 14), and it did exceed it on every molecule with a ring of four or more atoms that was measured (cyclobutane 16 against 8, cyclopentane 20 against 15, benzene 54 against 27, cycloheptane 63 against 42, bicyclobutane 9 against 7).
     Both sentences now say that, and `test_szeged_does_not_exceed_wiener_where_every_ring_is_a_triangle` holds both halves. The identity the module validates Szeged by (equal to Wiener on any acyclic graph) is unchanged.
   * **Measured.** Aspirin / ethanol / caffeine: Randić 6.109 / 1.414 / 6.537 and Wiener 246 / 4 / 258. The scores `ramp(randic, 8, 1)` and `ramp(wiener, 300, 0)` are 0.2701 / 0.9408 / 0.2091 and 0.18 / 0.9867 / 0.14, which the table, its CSV and (for aspirin) the Results reader
     show. Asked for no decimal places the line reads `Randic index: 6` and the reader still gives 0.2701, where a score made from the text would be 0.2857; with the typing removed the table makes exactly that score from the rounded text (0.27, 0.9414, 0.2086) and Results refuses,
     which is the disagreement typing exists to remove. No literature value was checked here beyond the benzene and n-butane ones the module already pins (Wiener 27 and 10, Platt 12 and 4, Wiener polarity 3 and 1, Randić 3.000 and 1.914), which the tests now read from the typed numbers.
   * **Tested and driven.** `tests/test_topology_analysis_typed.py` (the golden check; the eight typed with their exact types and nothing else; each line is its number rounded; the number does not move with the decimal places; the values checked by hand; a single atom; a salt read as its
     parent; the explicit-hydrogen graph is another number; the table cell; a saved and reopened report; the entries approved, the counts not), the output tests (unit, quantity, sweep: 30 of 30 hold) and `tests/test_main_window_scores.py` (the real window: a score from 6.109 where the line reads 6, and a
     molecule with a conformer scored on its drawing in Results and in the table). **Mutation-checked: 16 mutants of the producer and the table entries, all caught** (one pattern first missed its target and was rerun). `benchmarks/visual/score_typed_topology.json`: VERDICT PASS, 8 assertions;
     with the typing removed it fails 5.
   * **The endpoint tags are provisional** (section 12, decision 6): accepted "for now", to be revisited; see there for what changing one moves.
   * **Not here.** The counts of this report (its aromatic ring count is not RDKit's: see the next entry) and the rest of the rounded-text calculators, each its own PR under the same rule; the next entry reads them one by one.

   **The aromatic ring count, as built (the third report calculator typed for scores; a follow-up after slice 4):**
   * **Why this one, and not the next calculator on the list.** The eight rounded-text calculators that were left were read one by one on 2026-10-16 (verdicts below). Only one thing in them is both new and wanted by a score author: the number of
     aromatic rings, which no always-on descriptor gives. It is reported by two calculators, so the first question was whether they are one number. They are not: Topology Analysis filters its rings to those whose ATOMS are all aromatic and RDKit's
     `CalcNumAromaticRings` (the BBB Score Descriptors' count) wants the ring's BONDS aromatic; across 25 molecules they differ on biphenylene (3 against 2) and azulene (2 against 0) and agree on the other 23. RDKit's is the standard definition, so
     that one is approved and Topology Analysis's is left as text (its docstring claimed to use RDKit's count, and now says what it does). If both are ever offered they must share the endpoint tag, so a formula cannot read the two.
   * **What it is.** `compute_bbb_descriptors` gives the `Aromatic rings` fact the exact `int` its line shows, for the default answer only: the major-microspecies option counts the rings of another structure under the same label, so that answer stays
     text and a score over it is refused with the reason ("the result is text ... only a calculator's default answer is typed"). Approved as `calculator:bbb_descriptors:Aromatic rings`, unit `1` carried as no unit, endpoint `aromatic_ring_count` (a tag for
     review, in the same provisional spirit as the topology ones).
   * **What of the report is not offered, and why.** The heavy atoms and the TPSA are the always-on `heavy_atom_count` and `tpsa` under other labels (the same RDKit functions, `CalcTPSA` in both); MWHBN is `(HBD + HBA) / sqrt(MW)`, whose real unit is
     `(mol/g)^0.5`, which the unit language cannot write (the reason Hansen's parameters wait), and calling it `1` would be a small lie the unit check could never catch; the pKa line comes from the optional pkasolver tool.
   * **Golden check.** `tests/fixtures/bbb_descriptors_lines.json` is 119 observations (17 molecules, 7 ways of asking: the default, 0 and 8 decimal places, one past the end of the range, one that is not a number, and the microspecies option at pH 7.4 and 2),
     recorded from the code before the change through the registry. After the change none moved. (The pKa line reads "unavailable (needs a configured pkasolver environment ...)" in the suite, where no sidecar is configured.)
   * **What driving it showed.** For an integer count the control run is weaker than for the polarizability: with the typing removed the project table still gives the right score (a text `'1'` parses to exactly 1), and only the Results reader, which refuses
     text, tells typed from untyped. The drive script fails 1 of 5 with the typing removed, and that one assertion is the typed-versus-text check; the table's equality is guarded by the existing table-versus-Results parity test.
   * **Tested and driven.** `tests/test_bbb_descriptors_typed.py` (the golden check; the count is the only typed number and an exact `int`; the microspecies answer is never typed; the line is the count at every decimal setting; the count is RDKit's on the structure
     the registry hands over; values checked by hand, sildenafil's 3 being the module's own ChemAxon example; the two counts disagree on exactly two molecules; a saved and reopened report; the table cell; the entry, and the report's other numbers not approved),
     the output tests (30 became 31; the sweep holds 31 of 31) and `tests/test_main_window_scores.py` (the real window: a score of 0.75 for aspirin, refused for the microspecies answer, and the table agreeing with Results). **Mutation-checked: 13 mutants of the producer and the table
     entry, all caught.** `benchmarks/visual/score_typed_aromatic_rings.json`: VERDICT PASS, 5 assertions on its first run.
   * **The rest of the list, measured and not shipped (2026-10-16).** Each from a run of the calculator on aspirin through the registry and a read of its source:
     * `elemental_analysis`: the labels that do not depend on the structure are the mass, exact mass and nominal mass (the numbers of `mol_wt` and `exact_mass` on aspirin) and an atom count with hydrogens; the element percentages are named by the element present, which
       the id rule of section 3 excludes.
     * `polar_surface_area`: its first line is `CalcTPSA`, the always-on descriptor's function; its second line's label carries the pH it was asked at (`Polar surface area at pH 7.4`), so its id would depend on an option.
     * `surface_analysis` and `dipole_moment`: their calculation input is the geometry, so they wait for the rule for which conformer a score reads.
     * `huckel_analysis`: its energies carry the unit `beta`, which the unit language has no symbol for, and its own note says every pi centre is treated as a carbon.
     * `mass_spectrum`: the m/z values depend on the ion and the resolution under one label, and its neutral exact mass is the exact-mass descriptor.
     * `cns_mpo`: its total is out of 5 without a pKa tool and out of 6 with one (`mpo_scores.py`), and its logD comes from that tool, so one id would carry two scales and a number the census cannot reproduce; its unit field also carries the desirability (`-> 1.00`).
   * **Not here.** The counts of Topology Analysis (including its aromatic ring count, for the reason above), and any of the six calculators above should someone want an output of one: each is its own PR, and the first four wait on a decision (the id rule, the unit, the conformer rule).

   **The topology counts, as built (the fourth typing PR; a follow-up after slice 4):**
   * **Scope.** Ten of the Topology Analysis report's counts carry their number and are approved (unit `1`, exact `int`): the bond count, the cyclomatic number, the ring atom and ring bond counts, the chain atom and chain bond counts, the carbo, hetero and fused
     ring counts and the asymmetric atom count. The scope was settled on 2026-10-16 from the measurements below.
   * **Left out, each for a measured reason.** (a) The atom, ring, rotatable-bond and chiral-centre counts are the always-on `heavy_atom_count`, `ring_count`, `num_rotatable_bonds` and `num_stereocenters` under other labels: identical on all 34 molecules compared
     (`test_the_four_counts_left_out_are_the_always_on_descriptors_under_other_labels`), so a score would gain nothing and would have to run this calculator to read what is always there. (b) The largest and smallest ring size read 0 when there is no ring (water,
     ethanol and butane all do), which a score would take for a tiny ring: the same "empty is not unknown" trap as a default of zero. (c) The aromatic, aliphatic and heteroaromatic ring counts test the ATOMS of a ring for aromaticity, which is not RDKit's count
     (biphenylene 3 against 2, azulene 2 against 0), and the one RDKit count is already approved (the previous entry).
   * **Two of the ten share a tag with an always-on descriptor, and the copy guard is why.** The cyclomatic number is identical to `ring_count` and the asymmetric atom count to `num_stereocenters` on every census row, so `identical_pairs` (two outputs with the same
     numbers must share a tag, or the consensus rule would let a formula combine a number with itself) failed on the tags of their own. They carry `ring_count` and `stereocentre_count`: a formula may read either of a pair and never both (the real window refuses it).
     They are still offered because they differ where the census has no molecule: RDKit lists cubane's six faces as six rings and the cyclomatic number is five (adamantane 4 rings against 3), and a centre can be stereogenic without being asymmetric (cubane has 0
     asymmetric atoms against 8 stereocentres, adamantane 0 against 4, trans-1,4-dimethylcyclohexane 0 against 2).
   * **The other eight tags are new and provisional**, like the topology index tags (section 12, decision 6). The ring counts are of the rings RDKit's ring information lists, and the tag descriptions say so.
   * **A side effect on the assistant, found by a test that read the whole list.** The approved table passed 40 outputs, and `list_score_outputs` capped its rows at the general item limit of 40, so the 41st (the polar surface area, last by id) fell off the
     model's list with only `left_out_for_length` to say so, and the assistant could not have proposed a score over it. The list has its own limit now (`SCORE_OUTPUT_ROWS`, 120 at full size, scaled with the caps like every other list). A row is about 215 bytes, so the
     assistant's 12000-character reply budget holds about 55 outputs before its stepped caps would shrink the list; `test_the_whole_list_of_outputs_fits_the_reply_budget_with_room_to_grow` goes red at 85% of the budget, so the approval that crosses it is
     a decision about the rows or the budget and not a silent omission. The assistant's two real-window drives (`ai_score_proposals.json`, `ai_scores.json`) pass with 41 outputs.
   * **The producer.** `compute_topology_analysis` builds the ten counts once and the lines print them, so a line and its fact cannot drift; `typed = {**indices, **counts}` replaces the facts' values. Every one is a Python `int` (the project file's codec takes only the
     exact types).
   * **Identities as well as values.** On every molecule of the panel the atom count is the ring atoms plus the chain atoms, the bonds are the ring bonds plus the chain bonds, the rings are the carbo plus the hetero, and the cyclomatic number is bonds less atoms plus one;
     and the ten counts of seven molecules (benzene, naphthalene, aspirin, caffeine, 18-crown-6, L-alanine, cubane) were worked out by hand before the test was written and passed unchanged.
   * **Golden check.** The recording made for the indices (132 observations, before any typing) covers every line of the report; after the change none moved.
   * **Tested and driven.** `tests/test_topology_analysis_typed.py` (the ten typed with exact types and nothing else; the values by hand; the identities; the four duplicates; the cage and stereocentre differences; the ring sizes), the output tests (the sweep holds 41 of 41), and
     `tests/test_main_window_scores.py` (a molecule with a conformer: aspirin has 7 atoms outside a ring as drawn and 15 over its explicit-hydrogen graph, and the score reads 7 in Results and in the table). **Mutation-checked: 17 mutants of the producer and the table
     entries, all caught.** `benchmarks/visual/score_typed_topology_counts.json`: VERDICT PASS, 9 assertions on its first run; with the counts' typing removed it fails 3 (the three reader assertions: an integer count's text parses exactly in the project table, as it does for the
     aromatic ring count). It also shows the shared tag refusing a formula that reads the cyclomatic number and the ring count.
   * **Not here.** The seven counts above that stay text, and the rest of the rounded-text calculators (`elemental_analysis`, `polar_surface_area`, `surface_analysis`, `dipole_moment`, `huckel_analysis`, `mass_spectrum`, `cns_mpo`), whose verdicts are in the entry before.

   **The Batch panel's own table, as built (a follow-up after slice 4):**
   * **Two tables, one rule.** The Results dock's project table and the older Batch panel's table are two `ProjectTableView`s over separate runs; only the first was given the project's score lookup, so one run showed a score in one table and not in the other.
     `BatchPanel` now takes the same lookup (`MainWindow._score_definitions`) and rebuilds its score columns on `ScoreDefinitionsChanged` as the dock does. Nothing else about a score changed: it is still computed from the table's own cells,
     never run, never stored, and a score whose inputs the run did not compute is named under the table.
   * **Tested** in `tests/test_project_table_scores.py` (the panel with a hand-made table: the column, the follow of a definition, the missing-input note, no provider, a detail run not replacing the table) and `tests/test_main_window_scores.py`
     (the panel's real Fill-table button and the same numbers as Results; both tables for one run agree cell for cell). **Mutation-checked: 4 mutants (the provider not handed on, no subscription, a handler that does nothing, the window not passing
     the lookup), all caught.**
   * **Driven** by `benchmarks/visual/score_batch_table.json` (new `table_scores` option `"panel": "batch"` and `shot` widget `batch_table`): VERDICT PASS, 10 assertions, and the same script with the window's argument removed fails 4 of them.
     (The run picker's half, ticking a score's inputs for a person, was done after this: see "Ticking what the scores read".)

   **Ticking what the scores read, as built (a follow-up after slice 4):**
   * **The gap.** A score is a project-table column only when the run computed what it reads, and the table could say so only afterwards. Nothing helped a person include those inputs beforehand: a score on a calculator's output
     needed that calculator ticked by hand, and an always-on box unticked or narrowed to a subset left a descriptor out.
   * **What it is.** `domain/score_run_inputs.py` (pure: `run_inputs_of(definitions)` returns the always-on property ids and the calculator ids, the id and not the fact label, that the scores read, and any output id nothing can be
     ticked for). The Properties panel's Presets menu offers "Tick what my scores read (N)" when the project has scores (`PropertyPanel.attach_score_definitions`, `tick_score_inputs`; the lookup is the window's `_score_definitions`,
     asked each time, so a score defined, edited or removed is in the next tick).
   * **Decisions.** It ADDS and never replaces or narrows: a preset means "this set" and replaces the ticks, this means "also what my scores need", so a tick the person made stays, an unticked always-on box is ticked with exactly the
     properties read, a box left at "all" stays at all and a chosen subset is widened. A calculator the launcher is not offering (hidden by default, or not in the registry) is named and left unticked, because Run selected never runs what the
     person cannot see. Scores that read only always-on properties tick no calculator, and the existing rule that Run selected is enabled by a ticked CALCULATOR stands, so the status line says so rather than the button doing something else.
   * **What driving it found.** The status line beside Run selected is one line and clips, and only the idle hint ever set its tooltip, so the part of this message that matters (what could not be ticked) was cut off with no way to read
     it: the label now keeps its tooltip equal to its text for every message. The first runs of the drive script failed for the script's own mistakes (it selected the starter molecule, index 0, which has no structure, and it expected
     the Results reader to hold a number after a project run, which fills the table and not the molecule's own results: the reader correctly said "it has not been calculated for this molecule", and the script now asserts that and then
     runs the calculator on the molecule). Hand check of the numbers: oxygen balance on the CO basis is -79.93 % for aspirin, -138.9 % for ethanol and -90.63 % for caffeine, so `ramp(ob, -150, -50)` is 0.7007, 0.1108 and 0.5937, which
     is what the table and (for aspirin) the reader show.
   * **Tested** in `tests/test_score_run_inputs.py` (the pure part, and a sweep that every approved output names something the application can tick), `tests/test_project_run.py` (the menu entry, additive ticking, the always-on box in each
     of its three states, a calculator the launcher lacks, the status and its tooltip, and the claim itself: a project run after the tick gives the score a column and the same run without it names the score under the table) and
     `tests/test_main_window_scores.py` (the real window's menu). **Mutation-checked: 26 mutants, all caught.** **Driven** by `benchmarks/visual/score_tick_inputs.json` (new `tick_score_inputs` step; `project_run` takes
     `"keep_ticks": true`): VERDICT PASS, 8 assertions; with the window's attach removed it fails 2.
   * **Not here.** The Batch panel's own property tree has no such button (it has its own ticks, and a person ticks it by hand as before).

Slice 4 is complete: 4a (the assistant reads a score), 4b (no unit conversion is needed), 4c (a default for an input nobody calculated) and 4d (the assistant proposes a score and a person approves it).

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
6. **Endpoint tags make consensus unexpressible, and a hand-reviewed list can be wrong** (section 3). **The Topology Analysis tags are PROVISIONAL**: Alex accepted the eight index tags "for now" on 2026-10-15 (#351) and
   expects to revisit them, and the eight new tags of the topology counts are held the same way. They are my judgement, were checked against no literature, and are cheap to change: a tag is never stored in a definition or a project file, so a rename or a split changes only the sentence
   beside the output in the Derived Scores window (`score_editor`), the `endpoint` the assistant is told (`list_score_outputs`) and which pairs are refused. A MERGE of two tags (Wiener with hyper-Wiener, say) is the one
   change that can touch a saved score: a definition that reads but no longer checks is kept and shown refused, never deleted, so look at the stored definitions before merging two.
7. **Outputs of experimental or hidden calculators are excluded.** It keeps one layer of "unvalidated" from
   resting on another, and it removes some of the outputs people would most like to combine.
8. **The name check is derived from the registry and cannot see a published score the application lacks.**
   Over-blocking is possible (a name containing "pKa") and is preferred to a hand-kept list that rots.
9. **The assistant can propose a definition and cannot save one** (amended in slice 4d; the first reading was "the assistant cannot author a definition"). The concern stands: a model that can write a formula can
   also write one that happens to confirm what the person hoped. What changed is that a person who wants the assistant's help writing a formula is better served by a card they read and approve than by text they retype,
   which is where a wrong unit, a dropped constant or a mistyped name enters. The residual risk is a person approving what they did not read; the card is designed to make reading cheap and cannot prevent the other.
10. **No file-level version stamp for older builds** (section 8). A build that has never heard of the `derived_scores`
    key drops the block on its next save, as it does for every other block. This is the one block a person wrote by
    hand, so it is the one place the cost is lost work, accepted while the suite is in beta; it falls only on a project that has a definition, because the block is not written otherwise. Reversible later by
    stamping only files that contain a definition.

11. **A numbers-only operand takes the unit of what it is combined with** (slice 2). It makes thresholds writable and gives up nothing the check could ever catch, since a literal has no unit to check; but it is a relaxation
    of the strictest reading of section 4, and `energy + 5` is now valid. The explicit alternative, a declared named constant with a unit (`limit = 140 Å^2`), now exists beside it
    (`domain/score_constants.py`); how the dialog offers the two is slice 3's to decide.
13. **A default is per input and only for an input never calculated** (slice 4c). It is the narrowest policy that lets a person say what "not known" means to them, and it still changes a number's meaning without changing
    the formula. Three things keep it honest: it never stands in for an answer (a refusal, a failure, an earlier structure), it never makes a score out of defaults alone, and every number that used one says so everywhere
    it is shown, including in the exported CSV. A person who defines a default of 1 for a desirability and forgets it is still reading a number that carries `*` and a column naming the input; what this cannot prevent is a
    default that is simply a bad assumption.
12. **Only typed numbers, only of the drawing** (slice 2). It excludes most report calculators until their producers type their values, and every geometry-based output until it is reviewed. Both are real losses of usefulness,
    preferred to a score that moves with a display setting, or with whichever conformer happened to be stored.

## 13. Not here, deliberately

Trained models and applicability domains (a plugin); a consensus of predictors; per-atom aggregates as inputs;
quantum-chemistry outputs and recipe outputs as inputs; scores of scores; a missing-value policy beyond refusing and a per-input default (skipping a term, a default for a refused input); sharing
definitions outside a file; and any wording that calls a score a predictor of an endpoint.
