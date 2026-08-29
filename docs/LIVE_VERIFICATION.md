# Live verification: which technique owns which failure

A portable record of how this project verifies a running application, written
so another project can use it **without adopting a line of this code**.

It exists because the same pitfalls keep being rediscovered. Every claim below
was paid for by an incident, and most of the value is in the *what not to
assume* sections rather than in any implementation.

> **This standardises failure classes and evidence — not APIs, and not folder
> structure. Each project keeps its own harness.**

---

## Tier 0 — universal, and independent of GUI, language or framework

None of this is about Qt. It applies to a CLI tool, a library, or a service.

**A guard that passes while testing nothing is the default outcome, not the
exception.** Mutate before calling anything coverage: break the thing the guard
names and confirm the guard goes red. In this project that step has found a
guard testing nothing on essentially every occasion it was run — including
twice while building the very feature this document accompanies.

**A mutation that changes bytes but not behaviour is not a mutation.** Six are
on record here: an arm that added a call instead of moving one, an arm whose
edit landed inside a different function, an `if False else` that changed
nothing, an arm whose slice duplicated text rather than removing it. Assert the
edit changed *behaviour*, and compare the arm's test count against the
control's — an arm that errors out runs zero tests and greps as "no failures".

**A fixture is not big or small. It is degenerate or not, with respect to a
specific defect.** Two examples from one afternoon: a literal-ellipsis fixture
whose width short-circuit hid the difference between comparing stored text and
sniffing for a glyph, and a spanning-row fixture built with the one constructor
that cannot reach the case. Both passed. Both were found by mutation.

**An over-broad exclusion produces a GREEN suite and a smaller universe.** It
reads as a jump in coverage, never as a fault. A principled-sounding widening
here would have removed 82% of the population under test; it was measured
before it was written, not after.

**Grepping for a phrase counts the source, not the outcome.** Four instances:
a crash-marker grep that matched its own explanatory docstring; a check that
matched the comment written to explain why the thing it names is absent; an
`INFRASTRUCTURE FAILURE` string that appears in every log because the script is
echoed into it. Ask for the *result*, not for text that describes it.

**An anchored pattern can be worse than a loose one.** `^Fatal error` reported
zero markers on a run that had plainly crashed, because progress output shared
the line. Tightening looked more careful and was strictly worse.

**An inconclusive probe must raise, never report zero.** "I could not find out"
is not "it is absent". A blanket `except: return 0` here would have silently
skipped four tests on every machine while looking like it worked.

**Assert the setup.** A guard that skips on its own precondition scores as
neither pass nor fail, and a harness that only greps for failures calls it a
survivor. If a fixture must contain the case, assert that it does.

**Testing a helper is not testing the wiring.** Recorded three times. A helper
can be perfect while nothing calls it — four modules here were correct,
documented, sourced, and reachable from nothing a user could press.

**A deferral's reasons rot independently of its verdict.** Re-read the *reason*,
not the verdict, and ask what would have to be true today. Five entries here
were found stale in the reason while the verdict still looked settled; in one
case the route that finally worked was the one all three stated reasons had
ruled out.

**Absence of failure is not presence of a result.** A crashed run has no
failing tests to report, so a grep for failures returns nothing and reads as
success. Check that a *summary* exists, not that failures are missing.

---

## Tier 1 — which technique owns which failure

The single most useful thing in this document. Choosing the wrong technique
produces a guard that cannot see its own subject.

| failure class | owned by | example |
| --- | --- | --- |
| wrong value or logic | unit tests | a formula, a parser, a threshold |
| wrong **structure** in source | static analysis over the AST | a doc comment attached to the wrong constant; an undocumented control; a module nothing reaches |
| wrong **geometry** in a laid-out UI | a driven visual oracle | text clipped, overlapped, collapsed, still elided, off-screen |
| wrong **appearance over time** | golden-image diffing, drift-aware | a layout silently changing between releases |
| the residue | a human | a glyph resolving to a colour-emoji square |

**The worked example.** A doc comment here documented the constant that got
inserted *below* it, so the wrong constant carried the explanation and the right
one carried none. It was written off as "needs a human reader". It does not: the
orphaned constant is a structural signal, and a static guard finds it. But **no
screenshot could ever have found it**, because a doc comment never renders.
Getting that mapping wrong is how a project builds a check that cannot fail.

**And the residue is real, not laziness.** A glyph that resolves to a colour
emoji square was measured to be undetectable by counting coloured pixels,
because sub-pixel text rendering makes ordinary glyphs coloured too. The
answer was to stop depending on the glyph — shrink the residue by design
choice, not by a cleverer oracle.

---

## Tier 2 — the driven visual oracle, in detail

### The rule that scopes it

> **The visual oracle owns geometric invariants that are mechanically
> measurable. The screenshot owns human judgment about appearance.**

Without that line the layer drifts into "does this UI look good?", which is not
a thing a predicate can answer.

### The evidence that motivated it

- Roughly **fourteen** defects here were found *only* by driving the
  application and magnifying the screenshot — every one with a fully green
  suite.
- An out-of-process UI harness disagreed with the running application **six**
  times.
- Before this work, **not one drive script was committed.** Every live check was
  written once, run once, and thrown away. The most productive technique in the
  project was its least repeatable.

### The two levels, and why they must stay apart

    the predicates    pure functions over rectangles and strings, tested
                      headless on CONSTRUCTED geometry
    the extraction    reads ACTUAL laid-out geometry and measures real fonts,
                      exercised against the running application

**Neither alone is the check.** A passing predicate suite proves rectangle
arithmetic. An extraction walk that silently returned nothing would make every
predicate vacuously happy — so the extraction gets a **population assertion**:
it must report how many things it measured, not only what was wrong.

### What not to assume

- **Do not start with screenshot assertions.** Decide the failure class first.
- **Do not let a headless geometry test read real font metrics.** A headless
  platform's default font here is more than twice as wide as the one a user
  sees, and a geometry assertion failed by 40 px on a surface that was
  measurably clean in the running application. A test that measures fonts is a
  claim about the test machine.
- **Do not build a generic rectangle-collision detector and call it overlap
  detection.** UI toolkits composite children constantly. Define the *semantic*
  objects being compared and get the association from the toolkit itself — here,
  a form layout already knows which caption belongs to which value.
- **Do not use "the text contains an ellipsis" as an elision oracle.** A value
  may legitimately contain one. Compare against the widget's own stored full
  string, and require that the room has actually come back.
- **Do not judge a scrolling surface against its own content rectangle.**
  Content extends past a viewport by definition; that comparison reports
  nothing forever.
- **Do not treat "no findings" as proof.** Confirm the oracle can still say NO.
  Here every surface is clean and the toolkit clamps every resize to a minimum,
  so no script can squeeze a real panel into a real finding — the check is a
  deliberately impossible tolerance, which turned 0 findings into 46 from the
  same geometry.
- **Do not put live state in a committed benchmark.** No current selection, no
  current project, no clock, no network, no whatever-happens-to-be-open. Two
  projects in this estate learned that separately; one had three golden scenes
  "drift" an hour later because a relative timestamp had ticked over.

### The minimum that proves a predicate works

For each predicate, two tests: it reports the defect, **and** it stays silent
on a clean surface. Without the second, returning everything passes the first.
Then mutate: invert the comparison, make it return everything, make it return
nothing. Each must be caught by the test written for it.

---

## Tier 3 — the estate, and what each project can give and take

Measured, not assumed. The flow is **not** one-way from any one project.

| project | GUI | drive harness | geometry oracle | golden diffing |
| --- | --- | --- | --- | --- |
| OpenChem Studio | yes | 52 steps | yes | no |
| Fortuna Lab | yes | 28 steps | no | no |
| TokenSave-Manager | yes | 8 steps, tested capture helper | no | no |
| KicomAI / PolyShield | yes | scene-based | no | **yes** |
| LexForge | yes | **none** | no | no |
| File Converter | yes | none | no | no |
| Vox Shifter | yes | none | no | no |
| ICO File Manager | yes | none | no | **no test suite at all** |
| Python Installer | yes | none | no | **no test suite at all** |
| Sovereign Tattoo | yes | none | no | **no test suite at all** |
| Uplift Messenger | yes | none | no | **no test suite at all** |
| External Commander Dashboard | no | — | — | — |
| Scriptor | no | — | — | — |
| Timed Shutdown | no | — | — | — |

Three things follow:

- **Four projects have a GUI and no test suite.** For those, a visual oracle is
  the fourth rung of a ladder they have not started. Tier 0 applies; Tier 2 does
  not, yet.
- **KicomAI has golden diffing and nobody else does**, including its
  drift-aware rule about which scenes may be goldens at all. That is the piece
  it gives back.
- **No project has a geometry oracle** except this one, now. All of them can
  drive or screenshot; none could *assert*.

---

## The sendoff prompts

Paste into the target project. Each is self-contained: it names a failure class,
the evidence, the invariant, the traps, and what proves the guard works. None of
them requires reading this repository.

### For a GUI project with a test suite and a drive harness

```
Your project can already drive its UI without the mouse and capture it. It
cannot ASSERT anything about the result, so every live check is written once,
read once by a human, and thrown away.

Add a geometric oracle. Scope it hard:

  the oracle owns geometric invariants that are mechanically measurable
  the screenshot owns human judgment about appearance

Build it in two levels that must not merge:
  - predicates: pure functions over rectangles and strings, unit-tested on
    CONSTRUCTED geometry. Never let them measure a font -- a headless
    platform's default font can be twice the width of the real one, and then
    the test is a claim about the test machine.
  - extraction: reads actual laid-out geometry off the real widget tree and
    does all the font measurement. Give it a POPULATION assertion -- it must
    report how many things it measured, or a walk that silently returns
    nothing makes every predicate vacuously happy.

Start with the defects your project has ACTUALLY had. Ours were: text clipped
past a viewport, a value painted on top of its caption, a caption still
showing elided text after the room came back, and a caption collapsed to zero
width. All four are geometry and none of them needed a human.

What NOT to assume:
- Do not build a generic rectangle-collision detector. Layout toolkits overlap
  children legitimately. Get the caption/value association from the toolkit
  itself, not from proximity.
- Do not detect elision by looking for "..." in the text. A value may contain
  one. Compare against the widget's own stored full string AND require that
  the available width has grown enough for it.
- Do not judge a scrolling surface against its own content rectangle.
- Do not treat "no findings" as proof the check works. Force it to report --
  an impossible tolerance will do -- and confirm the findings reach your log.

Evidence required before calling it done: for each predicate, one test that it
reports the defect and one that it stays SILENT on a clean surface. Then
mutate each predicate (invert it; return everything; return nothing) and
confirm the intended test goes red. Expect to find at least one fixture too
degenerate to see its own defect; we found two.

Out of scope for a first pass: golden-image diffing, and any attempt to judge
whether something "looks right".

Do not adopt this blindly. First measure whether your project has this failure
class -- a technique that catches one class is not evidence for another.
```

### For a GUI project with tests but no drive harness

```
Your project has a UI and a test suite but no way to exercise the UI as a
user does, so a whole class of defect is invisible to you: things that are
correct in the model and wrong on the screen.

Build the harness before the oracle. The cheap version is enough:

  - a way to script the app from INSIDE the process (an env var naming a JSON
    file of steps, run on a timer once the window exists). No cursor control,
    no focus stealing, no window-manager dependency.
  - a screenshot step that works while the window is behind other windows.
  - steps that press the REAL control, not the handler behind it. A step that
    calls the handler directly proves the handler works and says nothing about
    whether the button is wired to it.

What NOT to assume:
- A step that ADDS something usually does not SELECT it. Ours cost a run that
  read as a bug in the code under test.
- A step with an unrecognised argument may be a silent no-op. Log it. We had a
  run photograph the wrong panel for an hour while the log looked healthy.
- A modal dialog opened with a blocking call will hang an unattended run
  forever. Show it non-modally.
- Do not put live state in a committed script: no current selection, no clock,
  no network, no whatever happens to be open.

Once you can drive it, the next step is asserting geometry rather than reading
screenshots by eye -- but only then.

Do not adopt this blindly. First measure whether your project has this failure
class.
```

### For a project with a GUI and no test suite

```
Do NOT start here with visual testing. It is the fourth rung of a ladder you
have not started, and a visual check bolted onto a project with no tests
produces confident screenshots of unverified behaviour.

Start with Tier 0 instead, which needs no framework and no UI:

  - a guard that passes while testing nothing is the DEFAULT outcome. Before
    trusting any test, break the thing it names and confirm it goes red.
  - a fixture is not big or small; it is degenerate or not with respect to a
    specific defect.
  - grepping for a phrase counts the source, not the outcome.
  - an inconclusive probe must raise, never report zero.
  - absence of failure is not presence of a result.

Get the logic under test first. The UI layer can wait, and will be much
cheaper once the layer beneath it is trustworthy.
```

### For a project with no GUI

```
Most of what we learned about verification is not about UIs at all. Take Tier
0 and skip the rest:

  - mutate before calling anything coverage; a green guard that tests nothing
    is the normal case, not the rare one
  - assert the edit changed BEHAVIOUR, not bytes
  - a fixture is degenerate or not with respect to a specific defect
  - an over-broad exclusion gives a green suite and a smaller universe, and
    reads as a coverage win
  - grepping for a phrase counts the source, not the outcome
  - an inconclusive probe raises; it never reports zero
  - assert the setup, so a guard cannot pass vacuously
  - testing a helper is not testing the wiring
  - a deferral's REASONS rot independently of its verdict

Do not adopt any mechanism from elsewhere without first measuring that you
have the failure class it addresses.
```

### For the project that already has golden-image diffing

```
You have something nobody else in this estate has: golden-image regression
checking, and the drift-aware rule about which scenes can be goldens at all.
That rule -- that a scene reading live data drifts for reasons unrelated to
the code -- was learned here independently as "a committed benchmark must
construct its own state". Two projects paying the same tax separately is the
strongest argument for writing it down once.

What you are missing is the layer BELOW a golden: a geometric oracle that says
WHY two images differ. A golden tells you something changed; it cannot tell
you that a value is painted on top of its caption, or that a label collapsed
to zero width. Those are mechanically measurable and do not need a baseline
image, which means they work on a brand-new screen with no golden yet.

Consider adding predicates over laid-out geometry, kept strictly separate from
the image comparison, and unit-tested on constructed rectangles rather than on
rendered output.

Do not adopt this blindly. First measure whether your project has this failure
class.
```
