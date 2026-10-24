# Structure coverage: does this calculator take the molecule on screen?

Design note, written before the code (2026-10-23). The question Alex asked: can a
Properties row say, live, whether the drawn structure is something that calculator can
handle, and stay right as the drawing is edited?

## What was already there

`CalculatorDefinition.preflight` is a cheap `mol -> reason` hook that must be the very code
the calculator refuses with. `PropertyPanel._update_preflight` runs it when the structure
settles and the status chip reads "Not applicable" before any run. Three limits:

1. Only Joback declared one.
2. It could only say "refuses". "Nothing known to stop it" and "covered" were the same
   empty string, so a row could never say it was fine.
3. The rows that open another panel (the ORCA workflows, proton affinity, X-H BDE, Fukui)
   have no chip, so a hook could not reach them.

## The decision

**One mechanism, three answers, and the refusing code stays the only rule.**

`domain/structure_coverage.py` adds `Coverage`: `COVERED`, `CAVEAT` (it runs, with a stated
limit) or `REFUSES` (certain to refuse, with the reason). A hook returns one, or the old
plain string (a reason, so `REFUSES`; `""` stays "no claim"). **A hook that returns nothing
claims nothing**: the row looks exactly as it does today. A hook that raises claims nothing
either. "Covered" has to be returned on purpose by code that ran the same decision the
calculator runs.

**Scope is a free source of refusals.** `CalculatorRegistry` already applies a calculator's
`CalculatorScope` before it computes (`components.select`: a salt for a pure-substance
method, no carbon for an organic one, a metal complex for a parent-compound one). That
raises the real refusal. The registry now reports that refusal as `REFUSES` for every
calculator with such a scope, with no new rule written for any of them. It never claims
`COVERED` from the scope alone, because the calculator may refuse for its own reasons.

**Loosening a refusal loosens the indicator.** Each hook calls the calculator's own refusal
function (Griffin's `griffin_hlb`, Hansen's `fragment`, Joback's `fragment`, the oxygen
balance, proton affinity's and BDE's `check_scope`) and reads the verdict off its result.
None keeps a copy of a rule. When a refusal becomes a warning in the calculator, the hook,
which reads the same function, moves with it.

## Where it shows, and why it is not noisy

* **Registry row**: the row already ends in a status chip that says "Not run" until a run.
  The chip is the place, and no widget is added. Before a run, and only then, a hooked row
  says one of
  * `Can run` (neutral): the structure is inside what the method covers,
  * `△ With limits` (amber, the same glyph and style as the other "look at this" states):
    it will run, and the tooltip states the limit,
  * `○ Not applicable` (neutral, as before): it will refuse, and the tooltip says why.

  A row with no hook, or whose hook has no claim, still says "Not run". After a run the chip
  reports the run, as it always did.
* **Service row** (a row that opens another panel): it has no chip and no room for one (it is
  one elided button, "Name > Panel"). It gets a leading glyph from the set the panel has
  already proven it can render, `✓`, `△` or `○`, and the tooltip gets one appended sentence.
  Absent when nothing is known.
* **The support-stage star** (PR #446) is a painted mark at the row's right edge and says
  how much to trust the METHOD. This says whether the method takes THIS drawing. They are
  different questions, so they use different slots (the chip text, the name's left edge)
  and no second glyph competes at the right edge.
* **Quiet by construction**: nothing is added to a row that has no hook, nothing is
  recomputed per drag keystroke (the same settle points as before), and a hook is one
  structure pass.

## What "Can run" claims, and what it does not

It claims the STRUCTURE is acceptable. It does not claim that ORCA is installed, that a
sidecar is configured, that the answer will be accurate, or that a 3D conformer exists
(those are other states: "Needs setup", "Needs input"). The tooltip says so. Hooks are
therefore added only for calculators whose structural gate is the whole story, and the
census shows which refuse most.

## What it costs, and the switch

Alex asked for it to be switchable if it costs anything. Measured 2026-10-23 on the real registry (every
calculator that has a hook or a scope) over the 29-row census panel plus a peptide, a surfactant and a
salt, the whole pass for one settled structure (`DescriptorService.coverage_pass`, warm):

| | median | mean | worst |
|---|---|---|---|
| one call per calculator, no sharing | 10.6 ms | 23.7 ms | 141 ms (a salt) |
| scope step shared across the pass | 5.0 ms | 9.4 ms | 31 ms (a salt) |

The 141 ms was nearly all ChEMBL's parent step and the metal refusal, repeated by about twenty
calculators that take the same scope. It runs once per settled structure, on the pause after an edit and
on selection, never per drag keystroke. That is small, but it is on the UI thread and it grows with the
number of hooks, so Settings > Recalculation has **"Say whether each calculator takes the structure,
before I run it"** (`compute/structure_coverage`, on by default). Off, nothing is asked and every row
reads "Not run" as before; switching it takes effect at once.

## Follow-ups that depend on open pull requests

* Proton affinity and BDE (#447) turn "outside what was measured" into a warning. Their hooks call
  `check_scope`, which stays the refusal; once `scope_warnings` is on master the hooks return a caveat
  from it.
* Hansen (#448) computes fewer than three carbons and labels it, so `fragment` stops refusing it; the hook
  then returns a caveat from `outside_domain`. Nothing in the hook names the old refusal, so until then it
  simply follows.

## Not done

* Calculators that need a conformer (HOMA, Bird) can only be asked once a 3D structure
  exists; before that there is no claim.
* No calculator's stage or visibility is changed.
