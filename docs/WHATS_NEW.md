# What's new: the assistant's calculator bridge, recipes and derived scores

**A dated tour, written on 2026-10-16, of what was built between 2026-10-12 and 2026-10-16 (pull requests #306 to #355).** It
says what each feature is, what it is for, where to find it in the application, and what it deliberately does not do. It is
a record of that moment and not a live status: [`CHANGELOG.md`](../CHANGELOG.md) is the complete list, and the design record
linked from each section says why it was built the way it was. Where a claim here carries a date, it describes that day.

## The short version

- **The AI Assistant is easy to find, and it can now look things up in the application and run the quick calculators
  itself.** It asks you first before anything slow, large or unclassified.
- **After an ORCA geometry optimisation, every later calculation uses the optimised geometry.** Before, they quietly kept
  using a force-field conformer. It now also replaces the conformer it was run on, in its slot, and the 3D viewer shows
  and marks it (#358).
- **A Lewis acid-base pairing window** that builds three separate lines of evidence from the quantum-chemistry runs you
  already made, and starts nothing by itself.
- **Derived scores:** a formula of your own over numbers the application already computes, shown as a column you can sort in
  the project table. This is the biggest piece, and the one that needs the most explaining: see the next section.
- **Decided but not built:** scores over 3D numbers (such as the shape descriptors). The rule is settled and written down.

## Derived scores: what they are for

A score turns several numbers into one that says how well a molecule fits a preference *you* hold. If you have forty molecules
and you care that each is polar enough but not too polar and has few aromatic rings, you can read two columns and apply that
rule in your head forty times, or write it once as a formula and get one column to sort by. That is all a score is: a
spreadsheet formula over numbers OpenChem has already computed, with its units checked, saved with the project, and shown in
Results.

What it is good for: **triaging a table** (sort by it, read from the top); **writing a rule of thumb down once**, so it is
applied the same way every time and travels with the project; and **handing one number to someone else** in the CSV.

What it is not: not a prediction (nothing checks a formula you wrote against measurements, so it is labelled
*user-defined, unvalidated* everywhere it appears); not something that runs calculations (it reads results that already
exist, so you run the calculators first); and not a replacement for a published score such as QED, which a calculator
computes.

The guide has a worked example from an empty project to a sorted column, in the **Derived Scores** topic of the Help window
(or [`USER_GUIDE.md`](USER_GUIDE.md), "Derived scores"). The example is a committed script that was driven through the real
window, so the numbers in it are the application's own: [`benchmarks/visual/scores_walkthrough.json`](../benchmarks/visual/scores_walkthrough.json).

What was built, in the order a person meets it:

- **The window** (**Tools ▸ Derived Scores…**) checks a formula as you type: a hand-written parser (nothing in it runs
  code), nine functions, and **units that are checked and never converted**.
- **What a formula may read** is a reviewed list of numbers the application produces, each with its unit: the always-on
  properties (molecular weight, polar surface area, logP, the hydrogen-bond counts, QED, synthetic accessibility and the
  like) and some calculators' numbers: the oxygen balance, the intrinsic solubility, the polarizability, eight graph indices
  and ten counts from Topology Analysis, and the aromatic ring count from BBB Score Descriptors. You choose from a list and
  never type an identifier. Two numbers that estimate one quantity cannot be used together, because combining two estimates
  of one thing is a consensus predictor, which this project has measured and does not offer.
- **Where it shows up:** a column of the **Project table** (and the Batch panel's own table), an entry under
  **Derived scores** in **Results** for the selected molecule, the CSV, and the report. The table is worked out from its own
  cells and follows an edit to the formula without another run.
- **Never a zero, never a silent skip.** If an input was not calculated, was refused, belongs to an earlier structure or has
  another unit, the score says which input and why. You may give an input that was *never calculated* a default, and every
  number that used one says so (a `*`, and a column beside it).
- **Presets ▸ Tick what my scores read** ticks, in Properties, the calculators your scores need.
- **The assistant can read your scores and propose a new one**, as a card; nothing is saved until you press **Approve**.
- **Why some numbers are not on the list.** A number must be a typed number (not rounded text), of the drawing, with an id
  that does not depend on the structure, and a unit the language can write. The calculators that were read for this and not
  offered, and the reason for each, are in the Derived scores design record (the entry on the aromatic ring count).
- **Decided on 2026-10-16, not built:** a score over a number that exists only for a 3D conformer will read the conformer
  every calculation already gets (the newest ORCA-optimised geometry, otherwise the lowest-energy force-field one), starting
  with the ten shape descriptors. Today a score reads the drawing only.

Read more: [`DERIVED_SCORES_DESIGN.md`](DERIVED_SCORES_DESIGN.md) (pull requests #326 to #355).

## The AI Assistant, findable, and able to use the calculators

- **Finding it.** **Plugins ▸ Open AI Assistant** is listed first. If the chosen provider needs an API key and none is
  stored, the panel says so instead of showing a blank chat. A plugin folder setting that points at nothing now warns,
  where before it turned every plugin off silently (#306).
- **What it can do.** It can search the calculators (the same rule as the launcher's Find box), describe one, read the
  results stored for the selected molecule, and run a calculator. Each number reaches the model with its method, settings,
  structure, units, freshness and caveats, and a reply that is too long loses rows, never a unit or a caveat (#307 to #309).
  ORCA numbers carry their method, basis, charge and multiplicity (#313).
- **It asks first.** How much a calculator costs was measured, and a calculator is either one the assistant may run (instant or
  short; the run is recorded in your project like one you started) or one that shows a preview with **Approve** and **Cancel**
  first. A molecule above 41 heavy atoms always asks. The assistant has no call that could approve a preview.
- **What it does not do.** It does not start ORCA or Vina: it describes the job, what it needs and whether this machine is
  ready, and you start it from its panel. A provider that cannot use tools (the Claude CLI) is not offered any.
- **Privacy.** Results, and a score's name and formula, are sent to the provider as part of the conversation, and a note
  under the box says so.
- **How far it is checked.** Every check so far used a scripted provider in the real window. **The live run on a real
  tool-capable provider has not been done** (it needs an API key).

Read more: [`AI_CALCULATION_BRIDGE.md`](AI_CALCULATION_BRIDGE.md); the **Plugins** section of the guide;
[`PLUGIN_SDK.md`](PLUGIN_SDK.md) for the plugin-side handle.

## An ORCA-optimised geometry is the geometry (#312, #358)

After an ORCA geometry optimisation, the next NMR, single point, 3D calculator or docking runs on the optimised conformer. It
used not to: the optimised conformer was stored without a force-field energy, so it sorted last and was never chosen while any
force-field conformer had an energy. The rule is now the newest quantum-optimised conformer, and otherwise the lowest MMFF94
energy; undoing the optimisation removes it and the old rule applies again. It matters for scores, too: it is the rule a score
over a 3D number will follow.

**Where it lands, and what you see (#358).** The optimised geometry replaces the conformer it was run on, in its slot, so 7 of
20 stays 7 of 20, and the 3D viewer jumps to it and marks it: `Conformer 7/20 - ORCA optimized (HF STO-3G)` in the single view,
`7 - ORCA` in a gallery cell. Details says which level of theory made it and which conformer it was optimised from, by the
number that conformer had when you pressed Run. Generating conformers again keeps it (Settings ▸ Conformers ▸ Keep
ORCA-optimized conformers, on by default). A job that finishes after you edited the structure no longer puts its geometry or
its numbers on the edited molecule; the status bar says why and the finished run stays in the history. Since then an **ORCA optimize** button in
the viewer, **Tools ▸ ORCA Geometry Optimization…** and a **Conformer** box in the Quantum Chemistry panel let you optimise a
conformer other than the canonical one (they set the panel up and start nothing), and a molecule that holds an ORCA geometry is
marked `[ORCA-optimized]` in the project list and under its name in Properties. **Generate Conformers** can also optimise the
lowest-energy conformer it just made: an unticked box in its window (Settings ▸ Conformers can start it ticked) that presses the
Quantum Chemistry panel's Run for you with whatever method the panel shows, and the result takes that conformer's place.

## The Lewis acid-base pairing (#311, #314 to #324)

**Tools ▸ Lewis Acid-Base Pairing…** asks how well matched two project molecules are as a Lewis acid and base, from quantum
runs you have already stored. It shows the Drago–Wayland enthalpy, the frontier-orbital gap and the hardness match side by
side and never as one score, each with the run its numbers came from; a missing number says what would supply it; and it
starts no calculation. A pairing you keep is listed in Results and reads *stale* when a molecule or a run it used changes.

It is the first **recipe**: an ordered plan whose steps read each other's typed outputs, with its own record in the project
file. It is the only one that ships.

How far it is checked: for borane and boron trifluoride with carbon monoxide, at B3LYP/def2-SVP on ORCA 6.1.1, the numbers
it builds from stored runs reproduce the documented ones within 0.01 eV, and the two orbital lines still disagree on purpose.
That gate was preregistered before any run ([`benchmarks/lewis_gate/PREREGISTRATION.md`](../benchmarks/lewis_gate/PREREGISTRATION.md)).
It does not cover other methods, solvents or molecules.

Read more: the **Pairing two molecules** topic of the guide; [`RECIPES_DESIGN.md`](RECIPES_DESIGN.md).

## Underneath

- **A conformer no longer changes the drawing's numbers.** Before, once a molecule had a conformer, the Results reader and the
  project table showed different values for properties that depend only on the drawing (aspirin's synthetic accessibility read
  6.445 instead of 1.58). Those are now always the drawing's; only the ten shape descriptors come from the conformer.
- **A conformer that lands while an earlier run is still going now wins**, and a molecule that is selected already holding a
  conformer shows its shape descriptors.

## Not built, not done, or deliberately not shipped (as of 2026-10-16)

- **The live provider run** for the assistant (needs an API key).
- **The assistant starting an ORCA or Vina job.** It previews only.
- **Scores over 3D numbers:** decided, not built (above).
- **Reactivity calculators from ORCA** (Fukui functions, proton affinity, bond dissociation energy) and **the synthesis
  helper:** not started. The first would each sit behind a preregistered gate and may be recorded as "measured, not shipped".
- **Calculators read for scores and not offered**, each for a measured reason (a duplicate of an always-on property, a label that
  depends on the structure or an option, a unit the language cannot write, a number that changes scale with an optional
  tool): `elemental_analysis`, `polar_surface_area`, `surface_analysis`, `dipole_moment`, `huckel_analysis`,
  `mass_spectrum` and `cns_mpo`.

## Where to look next

| | |
|---|---|
| [`USER_GUIDE.md`](USER_GUIDE.md) | The working guide: the **Derived Scores** and **Pairing** topics, and **Plugins** for the assistant |
| [`DERIVED_SCORES_DESIGN.md`](DERIVED_SCORES_DESIGN.md) | Why scores are built the way they are, slice by slice, with what was measured |
| [`RECIPES_DESIGN.md`](RECIPES_DESIGN.md) | Recipes and the Lewis pairing, and the preregistered gate |
| [`AI_CALCULATION_BRIDGE.md`](AI_CALCULATION_BRIDGE.md) | How the assistant reaches the calculators, and what it cannot do |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Where scores, recipes and the bridge sit in the layers |
