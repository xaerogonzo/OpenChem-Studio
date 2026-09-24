# Calculator maturity: stages, visibility, and how a calculator moves

Read this before classifying a calculator, changing a stage, or promoting one.
It is a maintainer's document (like ARCHITECTURE.md it is not part of the in-app
help); the user-facing statement is each calculator's section of
[CALCULATOR_REFERENCE.md](CALCULATOR_REFERENCE.md) and the *Calculators* page of
Settings.

## Two axes, and a third thing that is not either

A calculator declares a `CalculatorSupport` (`src/openchem/domain/calculator_support.py`):

| Axis | Values | What it says |
|---|---|---|
| **Stage** | `EXPERIMENTAL`, `LIMITED`, `STABLE` | the maturity of **this application's implementation** of the method |
| **Default visibility** | `SHOWN`, `HIDDEN` | whether the Properties launcher offers it **by default** — a discovery policy |

They are separate on purpose. Detonation (Kamlet–Jacobs) is `STABLE` — its
arithmetic is checked against the source's own tables — and `HIDDEN`, because it
is a specialist estimate that needs two numbers no structure can supply. Merging
the axes would have to call it one or the other.

**Stage never speaks for the published method.** `EXPERIMENTAL` means "this
implementation is not yet validated for default use", never "the literature is
unsure". `LIMITED` describes a scope that leaves out much of what people draw, and
does not apologise for it.

**Runtime availability is a third thing and is not declared here.** Whether
Kamlet–Jacobs can run *right now* depends on what has been typed, and whether a
sidecar model can run depends on this machine. That lives in a result's refusal
kind (`domain/refusal_kinds.py`: limit, needs input, needs setup), which is what
the launcher's chip says. A `STABLE` calculator may still need input or refuse a
structure; a hidden one is not unavailable.

## What the declaration obliges

Enforced today, by `tests/test_calculator_support.py`:

- A calculator that is not `STABLE`, or is hidden by default, must give a
  `support_reason`. Settings shows it beside the calculator ("Why hidden?").
- An `EXPERIMENTAL` calculator is never shown by default.
- Every built-in calculator has a help section of its own in the reference, and no
  two share one.
- Every built-in calculator is either classified or named in `LEGACY_UNCLASSIFIED`,
  and **that list only shrinks**. Classifying a calculator means giving it a
  `support` and deleting its name from the list in the same change; a recorded copy
  in the test refuses a name being added.
- A reason is a claim, so the ones that can be checked are (the Joback reason is
  run against RDX, HMX, TNT and PETN through the real calculator).

Enforced by review only: that the stage is *earned*. See below.

## What hiding does and does not do

Visibility controls **discovery only**. A hidden calculator stays documented and
searchable, its stored results stay readable, and offering one never runs it.
Effective visibility is the calculator's default, overridden by the master toggle
("Offer calculators that are hidden by default") and then by the person's own
choice for that calculator; the definition is never mutated
(`is_visible` in `calculator_support.py` is the one function the launcher, the
Settings page and "Run selected" all read).

A change of stage or visibility **alone does not change calculation identity**: it
is metadata about the calculator, not about the calculation. A change to the
method, its parameters or its model does, and reaches stored results through the
identity key as it always has.

## Moving between stages

Legal moves: `EXPERIMENTAL → LIMITED → STABLE`, any stage to retired
(`domain/calculator_taxonomy.RETIREMENTS`), and back a stage **with a documented
reason**. A promotion is one change carrying the metadata, the evidence and the
changelog entry together; coverage growth alone never promotes.

A calculator earns `STABLE` (for the scope it declares) when, each with something
a reviewer can open:

1. the **source authority** is identified, and the citation is in
   `docs/sources.toml`;
2. the **formula is implemented and independently checked** (a second derivation or
   the source's own worked examples);
3. the **source's tables are reproduced**, row by row, in fixtures;
4. the **declared scope is encoded** and structures outside it **refuse cleanly**
   with a coded, classified refusal — no fault on the calculator census corpus;
5. an **independent held-out result** is recorded, with coverage *and* accuracy,
   stratified (an aggregate error alone can hide a poor energetic or ionic class);
6. **units and provenance** are tested, and **limitations are explicit** in the
   reference section;
7. a **regression fixture** is frozen.

Promotion may be property-specific (one output of a multi-output calculator), and
"not promoted" is a valid outcome of an evaluation: the goal is to evaluate, and to
graduate only what earns it.

## Classifying a calculator

Assignment comes from **evidence**, not from a guess about what a calculator ought to
be. The calculator census lists calculators whose refusals are scope limits; a stage
is proposed from that and signed off. Nothing is classified because it "feels"
experimental. Until a calculator is classified it is treated as `STABLE` and shown,
which is what it was before this declaration existed.
