# The analyzer and the codebase disagreed, and the disagreement is the artifact

`audit_093105a.json` is a recorded twelve-tool tokensave audit of `master` at
`093105a`. It is here for one reason: **a future audit reporting a large move in
any of these numbers must be answerable as *the code changed* or *the resolver
changed*, and without a recorded baseline that question is not decidable.**

The obvious form of such a baseline is a list of scores. That form is worse than
useless here, because three of the twelve tools returned numbers that do not
describe this codebase at all — and each of them looks perfectly authoritative
on its own. So the file records the analyzer's **measured blind spots** beside
its raw figures, with one example each.

## The three that cannot be read as-is

**`hotspots` and `coupling(fan_in)` fold unrelated symbols together.** A call to
an unqualified common name binds to whichever project symbol shares that name,
so every `list.append` in the repository accrues to one function:
`benchmarks/docking/rank_power.py::append` is reported at **fan_in 1509**. All
nine reported hotspots are short accessors named `text`, `values`, `name`,
`connect`, `a`, `n`. A two-line `@property` named `a` does not have 273 callers.

`coupling(fan_out)` is unaffected and usable — it counts what a file references
rather than what references it, so a name collision cannot inflate it.

**`circular` and `imports` report one cycle spanning ~350 files**, which would
require `src/` to import back from `tests/`. It does not. The edge list names
the mechanism directly:

    benchmarks/assembly/fetch.py:26   import urllib.request
        resolved_file: src/openchem/services/spatial_overlay_service.py

A stdlib import bound to a project file. **So the `acyclicity` sub-score of
0.4093 is not a measurement of this codebase**, and the headline
`quality_signal: 7013` understates by however much that dimension drags the
geometric mean — over the other five it is about 0.86.

**`unsafe_patterns` returned `match_count: 0` because it searches Rust**
(`unwrap`, `panic!`, `unsafe {}`). On a Python tree that is *not applicable*,
never *clean*. The Python-equivalent scan is recorded in its place, and it is
genuinely clean: zero bare `except:`, zero `eval`/`exec`, zero `shell=True`,
zero `pickle`.

## The dead-code list needs reading, not acting on

468 symbols reported; the method half is dominated by Qt wiring. Eight
false-positive classes are recorded with an example each. Five of the eight are
**not** on the tool's own documented caveat list, and one — a function
referenced as a bare value inside a tuple literal
(`chem/structure_clipboard.py:67`) — appears to be a class nobody had
characterised before this audit.

The eight symbols that survived grep verification are listed separately, under
`grep_confirmed_genuinely_unreferenced_at_this_commit`. That qualifier is
deliberate: it is a statement about `093105a`, not a standing claim.

**`unused_imports`, by contrast, came out clean under the same scrutiny**, and
the file records the control that establishes it rather than merely asserting
it: `platformdirs` is imported in eight files and attribute-accessed in only
`paths.py` — and the report names the other six while correctly *omitting*
`paths.py`. That omission is the discriminating case, so the attribute-only
false-positive class demonstrably did not fire.

## Re-running it

`how_to_reproduce` in the JSON carries the exact twelve calls and their
arguments. The one argument that is not obvious: **exclude `resources/` and
`vendor/`** from anything scoped to our own code. The vendored Ketcher bundle is
a single 35 MB JavaScript file and dominates every unscoped ranking.

Compare against this file before drawing a conclusion from a delta, and check
the recorded `tokensave_version` first — a resolver change moves these numbers
without a line of this project's code changing.
