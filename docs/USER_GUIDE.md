# User Guide

A working tour of the application. For installation see
[QUICKSTART.md](QUICKSTART.md); for what each number means scientifically see
[SCIENTIFIC_LIMITATIONS.md](SCIENTIFIC_LIMITATIONS.md).

---

<!-- help:projects -->
## Projects and molecules

Everything lives in a **project**, saved as a `.ocsproj` file. A project
holds molecules; each molecule is identified by a UUID that stays stable
across renames and edits, which is what lets computed results, conformers
and provenance stay attached to the right structure.

The **Project Explorer** panel lists them. Right-click to delete or rename;
both go through the undo stack, so Ctrl+Z works on them like any structural
edit.

A project file never stores a raw RDKit molecule. It stores the molblock
plus canonical SMILES/InChI/InChIKey and metadata, and the structure is
rebuilt on load — so a project opened in a later version gets that version's
chemistry perception rather than a frozen snapshot of an older one.

**Every panel follows the selected molecule.** Selecting one in the Project
Explorer moves the 2D editor, the 3D viewer, the Properties panel, the
Quantum Chemistry panel's Molecule field and the Docking panel's Ligand
field together. If a panel could sit on a different molecule from the one
on screen, an operation could silently run on something you were not
looking at — which is exactly the bug this behaviour exists to prevent.

---

<!-- help:structure-clipboard -->
## Getting structures in and out

The **Edit** menu carries the whole-structure clipboard. Everything here is
also on the Project Explorer's right-click menu, deliberately: the context
menu is faster once you know it exists, and the menu bar is how you find
out that it does.

| Action | Notes |
|---|---|
| **Copy Structure As ▸ SMILES / InChI / InChIKey / Molfile** | SMILES is canonical and isomeric, so stereochemistry survives the round trip |
| **Paste Structure** (`Ctrl+Shift+V`) | accepts a molfile, an InChI or a SMILES without being told which |
| **Duplicate Molecule** | copies the structure into a new molecule in the same project |
| **Rename Molecule…** | also available by double-clicking the name in the Project Explorer |

**Paste detects the format by parsing it**, not by looking at it — each
reader is tried in turn and the first that yields a real molecule wins. A
`.smi` line with a name after the SMILES (`CCO ethanol`) pastes fine; a
paragraph of prose is refused rather than becoming a one-atom molecule.

It is `Ctrl+Shift+V`, not `Ctrl+V`, because Ketcher owns `Ctrl+V` inside
the drawing canvas for pasting fragments. Pasting replaces the selected
molecule's structure and goes on the undo stack, so `Ctrl+Z` brings back
what was there — **one** `Ctrl+Z`, not several.

**Inside the canvas, `Ctrl+C` and `Ctrl+V` copy and paste a selection**
rather than the whole molecule: select part of a structure, copy it, and
`Ctrl+V` gives you a floating copy that drops where you next click. It
works between two molecules as well as within one. The clipboard carries a
molfile, so a fragment copied here also pastes into any other program that
reads one.

**Duplicate is the "now make the other one" path** — draw aziridine,
duplicate it, change one bond, and you have azirine beside it without
redrawing. The copy does **not** inherit conformers, because those describe
the geometry you are about to change.

**InChIKey is the one to paste into a search engine.** It is fixed-length,
survives a URL or a spreadsheet cell unmangled, and is what most databases
index on. Most structures have no verified IUPAC name, so an identifier is
often the only unambiguous way to refer to a molecule at all.

### Identifying a structure online

**Tools > Identify Structure Online…** asks PubChem what this exact
structure is, and reports the CID, IUPAC name, formula, molecular weight
and common synonyms.

**Opening the dialog sends nothing.** It shows you exactly what would be
sent and waits for the button, because a possibly-unpublished structure
must not leave the machine as a side effect of opening a window.

It is an **exact structure match**, so a no-match means "PubChem has no
record of this precise connectivity and stereochemistry" — not "this
compound is unknown". A different tautomer, a missing stereocentre or a
salt form is a different query. The dialog says so rather than leaving you
to guess.

There is also an **Open in ChemSpider** button. That one is a browser
link rather than a built-in lookup: ChemSpider's web service needs a
per-user registered API key, so there is nothing the application can ship
that queries it on your behalf.

---

<!-- help:centre-tabs -->
## The three centre tabs

**2D Editor** — the embedded Ketcher editor. Draw, paste SMILES, import a
file. The app's own Edit and View menus proxy Ketcher's real actions
(Aromatize, Layout, Clean Up, Calculate CIP, Check Structure, Add/Remove
explicit hydrogens, its Miew 3D preview), so they are reachable from the
menu bar rather than only from the canvas.

**3D Viewer** — 3Dmol, showing conformers. Style selector
(stick / ball-and-stick / spacefill / line), conformer navigation, a
distance/angle measurement readout, and molecular surfaces (vdW, SAS, MS)
with an opacity control. Generate Conformers is here; conformers come back
sorted by energy, so conformer 1 is the lowest.

**You will often get fewer conformers than you asked for, and that is the
answer rather than a failure.** Embedding is random, so asking for ten
conformers of a molecule that has one shape produces ten copies of it.
Duplicates are pruned, and the status line says what happened —
"1 distinct conformer from 10 embedded". Aziridine and benzene have one
conformer; butane has two. Requesting more does not create more.

Two embeddings count as the same conformer when their heavy atoms and
their polar hydrogens are within 0.5 Å RMSD, compared symmetry-aware so
that the two ends of butane are not called different for having been
numbered the other way round. Hydrogens on carbon are ignored — a rotated
methyl is not a conformer — but hydrogens on N, O and S are kept, because
an O–H orientation changes hydrogen bonding and changes the energy of any
QM job you run afterwards.

**Macromolecule Viewer** — Mol\*, for proteins and nucleic acids. Cartoon
representations, chain colouring, and the receptor-residue highlighting that
docking interaction analysis feeds.

---

<!-- help:properties -->
## Finding your way around

The right-hand side has a **navigation rail**: a column of group icons,
and beside it the full names of that group's panels.

| Group | Panels |
|---|---|
| Analysis | Properties, Atom Inspector, Interactions, Structure Check |
| Compute | Quantum Chemistry, Docking, 3D Alignment, Jobs |
| Compare | Batch |
| AI | assistant panels, when a plugin provides one |
| Extensions | everything else a plugin adds |

One panel is shown at a time and it gets the whole column. Right-click any
name and **Pin to top** to keep it above the groups, so a panel you use
constantly does not need you to remember which group it is filed under.
Pins survive a restart.

("Compute" rather than "Quantum" because the group holds docking and
alignment too, and neither is quantum chemistry.)

Panels used to share one row of tabs, which could not fit their names —
you saw `Qu...`, `J...`, `B...`. If you are upgrading, your saved panel
layout is reset once so the old arrangement does not come back; your
window size and position are kept.

### Ctrl+Shift+P — type what you want

Press **Ctrl+Shift+P** and start typing. It searches every panel, every
calculator and every menu command at once — 113 of them — so you never have
to remember which group a panel is filed under or which menu holds a command.

Type initials: `qc` finds Quantum Chemistry, `sck` finds Structure Check.
Arrow keys move the selection without leaving the box, and Enter runs it.

Each row says where it came from, because a name alone is ambiguous —
"Geometry" is a panel, a calculator and a menu item.

**Ctrl+Shift+F** is the companion: it opens the Atom Inspector with the
cursor already in its filter box.

## Properties

The Properties panel is where most calculation happens. It has **25
collapsible categories** covering **51 registered calculators**;
Physicochemical and Identity are open by default.

Scalar descriptors compute eagerly — the whole batch finishes in well under
a millisecond, so there is no waiting and no lazy-loading complexity.
Anything that needs a parameter, or that produces per-atom data worth
looking at, gets an **Open …** button instead.

That button opens a **settings dialog built from the calculator's own
parameter list** (pH, decimal places, a SMARTS string, whatever that
calculator declares), and then a **Calculator Inspector** showing:

- the overall molecular value, where summing one is meaningful
- a 2D depiction coloured by the per-atom values, with numbers on the atoms
- the same colouring on the 3D structure, optionally painted onto a surface

The colour scale is computed once and drives both panes, so the 2D and 3D
views always agree.

### Reading a result: what the colours mean

Every result in the panel is one of four things, and the colour and the
symbol always agree — so the meaning survives colour-blindness, a
screenshot, and a copy-paste into plain text.

| | Meaning |
|---|---|
| plain grey | **Information.** A value. Molecular weight, an elemental composition, a Szeged index, a Lewis role. Most results are this. |
| ✓ green | **Checked, nothing flagged.** Only an alert catalog says this — PAINS, BRENK, mutagenicity, hERG. A report with nothing to say does not clear your molecule of anything, and says "Nothing to report." instead. |
| △ amber | **It worked, and you should look.** A catalog matched, or a regulatory screen found something. |
| ✕ red | **It failed, or the structure is invalid** — and the message says why, e.g. a 3D-only calculation on a structure with no conformer. |

Right-click anywhere in the panel for **Copy all properties**, or select
any single value with the mouse. The copied text keeps the headings and
drops the symbols.

Most calculators now report a **list of named values** rather than one run-on
line — each with its own units, and its caveats attached to the number they
qualify rather than three rows below it. Press **Details…** beside any of them
for the full report: every value, its source and basis, the evidence behind it,
and Copy/Export in Markdown, plain text, JSON or CSV.

The **Regulatory Screen** now says what it did *not* check. A molecule with no
matches lists every domain for which no ruleset is loaded, because "no matches"
without its scope is the silence that reads as reassurance.

### Running several calculators at once

Tick the box beside any **Open …** buttons you want and press **Run
selected**. They run concurrently with their default settings — no
dialogs, because answering six of those to avoid clicking six buttons is
not a saving. Use the individual button when you need non-default
settings.

Each result appears in its own category as a one-line summary
("22 atoms, −0.41 to 0.33 e"); open the calculator's button for the full
per-atom detail. The status line beside the buttons says what is running
and reads **Finished.** when the last one lands.

### Categories worth knowing about

| Category | What's in it |
|---|---|
| Physicochemical | MW, logP, TPSA, HBD/HBA, rotatable bonds, ESOL solubility |
| Identity | formula, exact mass, elemental composition, InChI/InChIKey |
| Naming | IUPAC name with its source and exactness label |
| Charge | Gasteiger partial charges, and charges at a chosen pH |
| LogP / LogD / Molar Refractivity | per-atom contributions, and pH-dependent logD |
| Topology | Wiener, Randić, Balaban, Platt, Szeged, Harary, per-atom eccentricity |
| Geometry (3D) | radius of gyration, molecular radii, projection area and radius, MMFF94/UFF/Dreiding energies |
| Surface Area | SASA (total and per-atom), vdW surface, molecular volume |
| Structure Generators | stereoisomers, tautomers, resonance forms, conformers |
| Quantum (Hückel) | orbital energies, π densities, HOMO/LUMO and the gap |
| Medicinal Chemistry | Lipinski, Veber, Ghose, Egan, Pfizer 3/75, GSK 4/400, Rule of Three, QED, PAINS |
| ADMET / Toxicity | BRENK alerts, BBB, bioavailability, hERG risk factors, and ML predictions if the sidecar is installed |
| pKa | ionizable groups, and numeric pKa if the sidecar is installed |
| Substructure Search | match your own SMARTS, or browse the built-in validated patterns |
| Regulatory | screen the structure against loaded regulatory rulesets — see [Regulatory screening](#regulatory-screening) |
| NMR | the instant empirical shift estimate — *not* the ORCA calculation |

Predictions are labelled `empirical` or `ab_initio` where there is a basis
to state one — worth reading, because the NMR row in this panel is the
instant estimate, and real ab initio NMR lives in the Quantum Chemistry
panel.

### Structural annotation

Four calculators answer "how is this molecule organised?" rather than
"what number does it have", and all four render as per-atom colouring in
the Calculator Inspector:

| Calculator | What it colours |
|---|---|
| `ring_systems` | each ring system as one colour, with fused, bridged and spiro atoms distinguished |
| `stereocenters` | R and S in fixed distinct colours, with unassigned centres in grey |
| `functional_groups` | each detected group by type, labelled at its anchor atom |
| `locants` | the IUPAC locant on each atom, coloured by where the number came from |

These are **categorical, not continuous**, and the Inspector knows the
difference: it does not print an "Overall" total for them, because summing
category ids produces a number that looks like a measurement and is not
one.

`locants` is the one with a real coverage caveat, and it states it rather
than rendering blank. Roughly half of all molecules name to a form that
carries no atom indices at all, and for those the locants come from ring
templates instead of from the name — so an empty or partial result is a
property of the naming path, not a failure.

### Running several calculators at once

Each calculator row has a tick box, and **Run selected** runs everything
ticked. The selection spans categories, so you can tick something from
Charge and something from Topology and run both together — they were
already running on a thread pool, so this is genuinely concurrent rather
than a queue.

Batch runs use each calculator's **declared defaults and open no dialogs**.
Six settings dialogs to avoid six clicks is not a saving, and no inspector
windows are opened either — the results land in the panel as usual. If you
want to configure one, run it on its own with **Open …**.

---

<!-- help:atom-inspector -->
## Atom Inspector

Everything the app knows about **one atom**, gathered in one place. Sixteen
per-atom properties already existed across eight different panels and
dialogs; this is the view that answers "tell me everything about atom 7"
without visiting each of them.

**It never calculates.** Opening it starts nothing and costs nothing — it
shows what has already been computed, gathered as results arrive. An
inspector that launched ORCA when you clicked an atom would be a
calculator launcher, and you would stop trusting it.

The atom table on the left is the primary navigation and works with no 3D
structure at all, which is the normal state right after drawing something.
Selecting an atom in the 3D viewer, or in the 2D editor, selects its row.

Facts are grouped by **what kind of fact they are** — Identity, Electronic,
Topology, Spectroscopy and so on — not by which calculator produced them,
because four consecutive "Lewis" headings is not how anyone thinks about an
atom. Identity and Electronic are open by default and the rest are
collapsed; there can be well over a hundred facts on a well-studied atom.

Each fact carries its basis and, where one exists, a link to the tool that
owns it — with the parameters filled in, so "open NMR" means "open NMR,
select this nucleus, highlight its peak". The search box filters by text
("ring", "aromatic", "Lewis") once scrolling becomes the bottleneck.

**Copy report** exports the whole thing as Markdown, plain text, JSON or
CSV.

### Bonds and molecules

The **Show** selector switches the same view between three subjects.

**Bond** lists every bond as `C3=O4` and reports its order, aromaticity and
conjugation, which rings it belongs to and whether it is where two are
fused, its measured length, and whether BRICS would cut there — that last
one meaning a known reaction class could *form* the bond, which is a
synthesis statement and not a claim that it is weak. Each end links
straight to that atom's own report.

**You can pick a bond in either viewer.** In the 2D editor, click it — the
selection comes straight through. In the 3D viewer, click its two atoms in
turn: 3Dmol can only report atoms, so two bonded ones is how a bond gets
named there. Clicking an atom that is not bonded to the first simply
starts the pick over.

**A bond length appears only when the coordinates are genuinely 3D.** A 2D
depiction has coordinates too and they are drawing units — every bond in a
layout comes out about the same length whatever its order — so a flat
structure shows no length rather than a fabricated one.

**Molecule** is everything at once: formula, mass and identifiers, the
counts, whatever descriptors have been computed, structural alerts, a
one-line structure-check summary, Lewis character, and which spectra exist.
It needs no selection, so the row list is hidden for it.

Plugins can contribute to all three: a `FactProvider` implements whichever
of the atom, bond and molecule hooks it has something to say through, and
appears alongside the built-in facts without either side knowing about the
other.

---

<!-- help:interactions -->
## Interactions

Two questions about how a structure interacts, one panel.

**Between two molecules** — pick a Lewis acid and a base and get three
independent lines of evidence: a Drago–Wayland enthalpy estimate where both
partners are in the parameter table, whether the HSAB hard/soft pairing is
favourable, and the frontier-orbital gap where a quantum calculation has
run.

**There is deliberately no combined score.** The three answer different
questions and which one is informative depends on the pair — and on the
case the feature was built for they *disagree*: borane and BF₃ against
carbon monoxide come out opposite ways on the orbital gap and the hardness
proxy. Averaging them would have split the difference on a case where one
line is simply right.

**Within one molecule** — the Intramolecular tab finds internal hydrogen
bonds, π-stacking and metal contacts, listing each with what kind it is,
which atoms are involved and how far apart they are.

Finding nothing is a result and says so. If there is no 3D conformer the
panel names *that* as what is missing, rather than reporting no contacts —
a molecule with no geometry has not been checked, which is a different
statement from a molecule with no contacts.

---

<!-- help:docking -->
## Docking

In the **Docking** panel:

1. **Choose a receptor** — from a file, or from the curated library of 49
   targets, which come with binding-site boxes already validated by
   redocking their own crystallographic ligands.
2. **Inspect the structure's contents.** The Contents dialog lists every
   chain with its residue count and type, and lets you untick chains to
   exclude them. This matters more than it looks: a deposit often contains
   a crystallisation chaperone, a second copy of the receptor, or a fusion
   partner, and leaving them in changes the result.
3. **Set the search box.** Derive it from a bound ligand (the reliable
   option) or place it manually in the 3D view. The app refuses to run a box
   that contains no receptor atoms rather than returning empty results.
4. **Run**, and read the poses: ranked by score, each with a per-pose
   interaction analysis — hydrogen bonds, clashes and the specific receptor
   residues involved, which paint onto the macromolecule viewer.

Prep options (alternate-location filtering, symmetry-copy removal, hydrogen
addition) are shared between the receptor Vina receives and the receptor the
analysis reads back. That is deliberate and load-bearing; see
[ARCHITECTURE.md](ARCHITECTURE.md).

Read [SCIENTIFIC_LIMITATIONS.md](SCIENTIFIC_LIMITATIONS.md#docking) before
drawing conclusions from a score.

---

<!-- help:quantum-chemistry -->
## Quantum chemistry

The **Quantum Chemistry** panel drives ORCA. Pick a calculation type —
single point, geometry optimisation, optimisation + frequencies, NMR, or NMR
with spin-spin coupling — plus charge, multiplicity and a method/basis
string (the presets are editable; anything you type, including dispersion or
solvation keywords, is passed through and is part of the calibration cache
key).

**Calibrate Reference (TMS)** runs the reference calculation once per
method/basis and caches it, so subsequent NMR jobs return real ppm shifts
rather than raw shielding constants. Until you do, results are labelled as
raw shielding — not silently presented as shifts.

NMR results arrive with several views: a **1D signals** tab (grouped
equivalent protons, integration, multiplicity, a clickable peak spectrum,
and shifts drawn on the 2D structure), plus **HSQC / HMBC / COSY** tabs with
both a cross-peak table and a scatter plot. Clicking a peak highlights the
atoms; clicking an atom selects the peak.

<!-- help:led -->
### Breaking an interaction energy apart (LED)

**Interaction energy breakdown (LED)** answers "*why* do these two stick
together" rather than "how strongly". It splits the interaction into
electrostatics, exchange, dispersion, charge transfer, and the cost of
distorting each partner from its isolated shape — so an adduct held by
dispersion and one held by electrostatics look different even when the
total is the same.

**Draw the two partners as separate species.** They are the fragments: a
Lewis acid and its base, a hydrogen-bonded pair. A single connected
molecule is refused, because there are then no partners to decompose an
interaction between.

**Then put them where they actually sit.** Generating 3D coordinates for a
structure drawn as two separate species does *not* push them apart — there
is nothing connecting them for the embedder to work with, so they come out
stacked on top of each other. A run like that is refused rather than
computed: the numbers it would produce are arithmetically correct and
physically meaningless (measured: an interaction energy of +40 619
kcal/mol from partners 0.15 Å apart).

The job runs the complex *and* both partners on their own, in one go. That
is not optional thoroughness — a decomposition of the complex by itself is
not a binding energy, and ORCA's own "total interaction" line for BH₃·CO
reads −428 kcal/mol against a real bond enthalpy near −25.

Three things the result tells you that are easy to skip past:

- **The terms are shown with a residual.** They should add up to the
  interaction energy; the small leftover is reported rather than hidden, so
  you can see the decomposition is complete rather than take it on trust.
- **The partitioning is arbitrary and says so.** ORCA's own wording is
  carried on the result: only the total energy is an observable. Compare
  terms *between* similar systems rather than reading one in isolation.
- **No counterpoise correction**, and the fragments are held at their
  geometry in the complex. So this is a vertical interaction energy, and it
  is more negative than a bond dissociation energy would be.

**Check the cost estimate before starting.** DLPNO-CCSD(T) is steep:
measured, a water dimer took 15 seconds, a pentane dimer 21 minutes, and a
benzene dimer 44 minutes and **6 GB of scratch disk**. Anything drug-sized
is not a candidate, and the panel says so rather than letting you find out
hours in — refusing outright when the job would need more disk than a
machine is likely to have.

**Aromatic partners cost about three times what their size suggests.** The
estimate knows this, but it is worth knowing yourself: a π-stacked pair is
the expensive case, and it is usually the one you want.

<!-- help:ir-spectra -->
### IR spectra and normal modes

An **optimisation + frequencies** job fills the **IR** tab: a stick
spectrum, and a table of every mode with its wavenumber, IR intensity and
character (stretch / bend / torsion). Select a mode and press **Animate
mode** to watch it — the optimised geometry is displaced along that mode's
eigenvector and played through the 3D viewer.

Two things the spectrum shows that are easy to miss elsewhere:

- **Grey sticks at the baseline are IR-silent modes.** They are real
  vibrations that symmetry forbids from absorbing (CO₂'s symmetric
  stretch, 20 of benzene's 30 modes). "No mode here" and "a mode that
  cannot absorb" are different facts.
- **A red banner means imaginary frequencies**, and it is the most
  important thing on the panel. A negative wavenumber means the geometry
  is a saddle point rather than a minimum — so **every thermochemistry
  number from that same job is invalid**, with nothing in the numbers
  themselves to say so. Re-optimise before trusting the enthalpy or free
  energy.

The y-axis is absorption intensity in km/mol, not transmittance.
Transmittance needs a path length and a concentration from a sample that
was never prepared; choosing them would put an invented calibration on the
axis. Frequencies are raw harmonic values, labelled as harmonic — see
`benchmarks/ir/`.

**An experimental spectrum can be overlaid.** Import a JCAMP-DX file and it
is drawn against the computed one on a shared axis. The reconciliation is
done rather than assumed: a transmittance spectrum is converted to
absorbance, percent and fractional scales are told apart, and the two
series are put on a common wavenumber axis before anything is drawn. Where
the computed peaks sit relative to the measured ones is then a real
comparison rather than two plots that happen to share a picture.

<!-- help:surfaces -->
### Surfaces — point charge beside ab initio

The **Surfaces** tab shows two electrostatic potential maps side by side,
each labelled with its method.

The **left** pane is the point-charge potential from Gasteiger charges. It
is instant and needs no ORCA at all. The **right** pane is the ab initio
one, plotted by `orca_plot` from the wavefunction the calculation left
behind; the same control also plots the electron density, the HOMO or LUMO
(named, not numbered — the index depends on the basis set), and the spin
density.

They are shown together rather than one replacing the other because they
fail differently, and `benchmarks/esp/` measured how. They agree on gross
polarity (r = +0.80 to +0.99 over surface points), but on bromobenzene the
ab initio potential changes **sign** around the bromine — positive along
the C–Br axis, negative around its belt — while the point-charge model
reports that atom as uniformly negative, because one charge on one atom
cannot change sign with angle. Water's lone pairs are the same story: the
ab initio potential deepens out of the molecular plane and the
point-charge one flattens.

A QM surface needs a calculation to have been run on that molecule first —
any type will do, including a plain single point. Asking for a spin
density on a closed-shell molecule is refused rather than answered: ORCA
would write a file containing a copy of the electron density under a
spin-density name.

**The wavefunction is kept after a job finishes**, in a content-addressed
store keyed by structure, method/basis and calculation type rather than by
the molecule's identity. So it survives the molecule being deleted, and the
same structure computed the same way in another project lands on the same
entry.

**That store is read back when the per-molecule copy misses.** Re-import a
compound, open another project containing it, or delete and re-add a
molecule, and the new molecule has no wavefunction of its own — but the
store may hold one for exactly that structure, and a surface plots from it
instead of costing another ORCA run.

The match is on the **exact structure**, never on the molecule. That is
what keeps it safe: edit a molecule from benzene to toluene and the
wavefunction retained under its own id is refused as stale, and a stored
one only serves if it was computed for toluene. A structure miss stays a
miss and you get a recalculation, which is the right answer.

NMR reference and scaling calibrations are cached separately per
method/basis, which is why `Calibrate Reference (TMS)` is a one-off rather
than a per-job cost.

---

<!-- help:alignment -->
## 3D alignment

The **3D Alignment** panel superimposes molecules onto a reference so their
shapes can be compared directly.

Pick a **reference** molecule, tick the **probes** to align onto it, choose
a method and an accuracy level, and run. The reference is a deliberate
choice and does *not* follow the Project Explorer selection — the probe
checkboxes are defined against it, so re-pointing it whenever you clicked
elsewhere would reshuffle your selection underneath you.

Higher accuracy levels generate more conformers per probe and allow the
maximum-common-substructure search more time. That is the trade: alignment
quality against wall clock.

---

<!-- help:jobs -->
## Jobs and the console

Anything that takes real time — ORCA calculations, docking runs, conformer
generation, batch runs, sidecar installs — is a **job**. Jobs appear in the
**Jobs** panel with their state and a progress message, and can be
cancelled from there.

Cancellation is honest about being best-effort. A job is stopped between
steps rather than mid-step, because the underlying tools are not
preemptible in the middle of a call; a cancelled job reports as failed with
"Cancelled by user" rather than as a short successful run.

The **Console** panel is the application's log as it happens. It is worth
looking at when something surprises you — the conformer pruner, for
instance, records exactly how many embeddings collapsed into how many
distinct shapes there.

---

<!-- help:in-app-help -->
## Getting help inside the application

Press **F1** for help on the panel you are working in, or click the **?**
in any panel's title bar. **Help > User Guide** opens the same window at
the top.

The help window is not a separate manual. **It renders these documents
directly** — this page is `docs/USER_GUIDE.md`, and the footer of every
help page names the file it came from. There is exactly one copy of this
text, which is the point: a documentation pass updates what the application
shows, with no second place to remember.

The search box searches the **body text**, not just the headings, and ranks
what it finds. Searching "Vina" returns four sections including the one
explaining why its score is not a binding free energy — a word that appears
in no heading anywhere in these documents. Matches are highlighted in the
page and the view scrolls to the first one.

F1 and the **?** answer slightly different questions, which is worth
knowing when they disagree. The **?** is bound to its own panel and is
always right about which panel it belongs to. F1 follows **keyboard
focus** — so if you click a panel's tab to bring it forward but then press
F1 without clicking inside it, you get help for whatever you last typed in.

---

<!-- help:compare -->
## Compare

Tick two or more molecules and see their values side by side — one row per
property, one column per molecule.

**It never calculates anything.** The values are the ones other panels have
already computed, so opening Compare is free and a blank cell means *that
calculator has not run for that molecule* — not that it has no value. Run
what you want in Properties first; the columns fill in as results arrive.

**Differences only** is the reason to open it. Two related structures agree
on most of a long table, so hiding the rows where they match leaves the
handful that answer the question. Aspirin against salicylic acid comes down
to a few rows rather than sixty.

A property one molecule has and another does not counts as a difference, and
stays visible — a missing value is usually the interesting thing.

If every property matches, the panel says so rather than looking empty: two
molecules agreeing on everything computed is a result, not a blank screen.

**Copy table** puts the whole thing on the clipboard as tab-separated text,
which pastes straight into a spreadsheet.

You can also reach this from any report: right-click it and choose
**Compare with…**.

---

<!-- help:batch -->
## Batch mode

Everything else in the app answers a question about the molecule you have
selected. The **Batch** panel answers it about all of them.

Tick any set of descriptors, structural-alert catalogs and calculators, and
run them across every molecule in the project. The results arrive as a
sortable table, filling row by row as it goes. Each cell keeps the
provenance and the empirical/ab-initio label the single-molecule views
carry — hover a cell to see what produced that number, with what
parameters.

A calculator that reports several numbers becomes several columns; Topology
Analysis alone contributes 27. A calculator that reports prose (an IUPAC
name, a stereo summary) becomes a text column and is not offered to the
analytics, because a count of prose lines is not a property of a molecule.

**Export** is a second, separate path from File > Export Molecule. CSV
carries the numbers at full precision for the next tool; the Markdown
report carries the table *plus* what produced every column, how it was
parameterised, and how many molecules it failed for and why.

**Analyse…** opens four views over the finished table:

- **Correlation** — any numeric column against any other, with Pearson,
  Spearman and n stated on the plot. "Correlate against everything" ranks
  every other column by how strongly it tracks the one you picked. This is
  the check that matters: a predicted property whose strongest correlate is
  molecular weight is measuring size. Molecular weight and Labute surface
  area come out at r = +0.98 across a real 181-molecule set, which is the
  scale of confound this exists to find.
- **Chemical space** — PCA over the numeric columns, standardised, so a
  column measured in hundreds cannot become the first component by units
  alone. The explained variance is stated, and so are the descriptors that
  dominate each axis, because "PC1" on its own means nothing. Deterministic:
  the same project always gives the same picture.
- **Clustering** — Butina over Morgan fingerprints at a Tanimoto threshold
  you choose. Higher is stricter. Cluster membership then colours the
  chemical-space plot.
- **Distributions** — a histogram and summary statistics for any column,
  with the median drawn rather than only reported.
- **Per-atom** — two molecules, one per-atom property, compared atom by
  atom. Appears when the run produced per-atom data for at least two
  molecules.

The Per-atom tab answers a different question from the rest of the dialog:
not "which columns move together across the project" but "which *atoms*
differ between these two structures". Aspirin against salicylic acid shows
`+0` down the shared benzene ring and the real difference at the one oxygen
that changes — the ester against the phenol.

**The atoms are matched by structure, not by index.** Aspirin's carbonyl
carbon is atom 8 and salicylic acid's is atom 2; lining up index against
index would subtract an oxygen from a carbon and report a confident number
for it. Matching is by maximum common substructure, and aromatic bonds only
match aromatic ones — so benzene will not map onto a sugar chain, and a
comparison between molecules with nothing in common comes back nearly
empty rather than nearly identical.

Atoms with no counterpart are **left out and counted**, not shown as zero:
the note under the table says how many matched and reminds you that the
rest are exactly where the two structures genuinely differ. Categorical
properties (ring system, functional group) are shown but never subtracted —
the difference between two category ids is a number that means nothing.

**Virtual screening** docks every molecule in the project into one receptor,
one at a time, and ranks them. Take a target from File > Receptor Library
and the binding site comes with it. The scores rank ligands against one
receptor; they are not binding free energies and do not convert to a Kd.

---

<!-- help:structure-check -->
## The structure checker

The **Structure Check** panel says what is wrong with a structure, why it
thinks so, and — where a repair exists — offers it as a button. The light in
the status bar tells you there is something to look at; clicking it opens the
panel. `Ctrl+Shift+K` and **Edit ▸ Check Structure…** do the same.

Checks run on every edit, so what you are reading always describes the
structure in front of you rather than the one you had five edits ago.

### Red, amber and blue mean different things

- **Error** is reserved for structures that cannot exist — an impossible
  valence, two atoms drawn at the same point.
- **Warning** is for things a chemist does on purpose *sometimes*: a carbene,
  a net charge, an undefined stereocentre, a bond that looks too short.
- **Note** is information — an isotope label, explicit hydrogens, an
  expanded octet we accepted and want to explain.

A checker that called every deliberate drawing an error would teach you to
ignore errors, which is why the line is drawn there.

### "Definite" and "judgement"

Every finding says which it is. **Definite** means it follows from the
structure itself: a valence count is right or the periodic table is wrong.
**Judgement** means a threshold somebody chose is involved — bond lengths,
crowding, bond angles — and a perfectly good drawing can trip it.

There is no percentage anywhere in this panel. A "70% confident" on a
bond-length heuristic would be a number nobody measured.

### Where it disagrees with the drawing canvas

The 2D editor is Ketcher, and the red circles it draws come from Indigo's
valence model, which we cannot change or even read. So the panel is a second
opinion, and it says so when it differs:

- **Iron oxides.** FeO, Fe₂O₃ and Fe₃O₄ are all flagged in the canvas and
  are all fine. A transition metal has no defined valence, so main-group
  octet arithmetic does not apply to it.
- **Hypervalent iodine.** IF₇ is a real compound that RDKit itself refuses;
  the panel accepts it and cites the rule. I(CH₃)₆ is refused, because
  ligands are added in pairs and iodine reaches 1, 3, 5 or 7 but never 6.
  I(CH₃)₇ is refused for a different reason: iodine only reaches 7 with
  fluorine, chlorine or oxygen around it.

When a structure is accepted here but RDKit will not sanitize it, you get a
second, separate warning — because descriptors, naming and 3D generation all
go through sanitization, and "this is fine" followed by a page of blank
properties would be misleading.

**Edit ▸ Check Structure in the Editor (Indigo)…** opens Ketcher's own
checker if you want to see the canvas's reasoning directly.

### Fixes

Each fix says what it costs before you press it:

| Safety | Meaning |
|---|---|
| **Safe** | the structure means the same thing afterwards |
| **Reversible** | it changes the drawing, not the chemistry |
| **Lossy** | atoms or bonds go away |

"Keep the largest fragment" is lossy — on a salt it removes the counter-ion,
changing the compound's identity, formula and mass. Every fix goes on the
undo stack, so `Ctrl+Z` brings back exactly what was there.

### Oxidation states

Tick **Show oxidation states** in the panel — or **View ▸ Structure Display ▸
Show Oxidation States** — and the depiction labels every heavy atom. Iron(III)
oxide reads `Fe +3` and `O −2`; iron(II) oxide reads `Fe +2`.

They are labelled on *our* depiction rather than in the drawing canvas,
because the canvas is Ketcher and cannot be annotated. **Oxidation States**
is also a calculator in the Properties panel, where it renders the same way
every other per-atom property does.

**An oxidation state is a bookkeeping formalism, not a measurement.** No
instrument reads +3 off an iron atom. The rule is IUPAC's: give each bond's
electrons to the more electronegative atom, split bonds between like atoms
evenly, add the formal charge. It describes the structure *as drawn*.

#### It refuses rather than guesses

That refusal is the feature, and magnetite is why. Fe₃O₄ is one Fe(II) and two
Fe(III); the rule reports **+3, +4, +3** — inventing an oxidation state iron
does not have here, missing the mixed valence, and putting the wrong number on
whichever iron the structure happened to be drawn around. So instead of a
number you get the reason there isn't one.

Four situations are declined, each found by measurement rather than assumed:

| Declined | Because |
|---|---|
| Mixed-valence frameworks (Fe₃O₄) | the rule cannot resolve them, and its answer depends on the drawing |
| Transition-metal organometallics (Cr(CO)₆, ferrocene) | back-bonding is invisible to it — it gives Cr(CO)₆ a chromium of +6, where the answer is 0 |
| Electron-deficient bridges (the boranes) | a bridging hydrogen is not sharing a pair with either neighbour |
| Metal clusters | the bonding is delocalised over the metal framework |

Equally deliberately, four things are *not* declined, because the rule gets
them right: **Hg₂Cl₂** at Hg(+1) each, **methyllithium** at Li(+1),
**Grignards** at Mg(+2), and **Fe₂O₃** at Fe(+3) each. Refusing every
metal–metal bond would have thrown away calomel; refusing every metal–carbon
bond would have thrown away methyllithium. The line falls where the
measurements put it.

Ferrocene shows the "as drawn" point plainly. Written as an ion pair — a bare
Fe²⁺ beside two cyclopentadienide anions — it is a classical ionic description
and iron is +2, correctly. Written with iron bonded into the rings it is η⁵
coordination, which this rule cannot describe, and it is declined.

One limitation is documented rather than ruled on: a charge drawn on one atom
of a delocalised ring makes that ring's per-atom states depend on where the
charge was typed. A rule refusing "a charge on an aromatic ring" would also
refuse pyridinium, where the charge really is on the nitrogen, and nothing
here separates the two cases.

### It offers a redraw only when a redraw would help

Every other drawing complaint says something looks wrong. **Layout
suggestion** generates the alternative and compares, so it can tell "this
drawing is bad" from "this drawing is bad *and I can do better*" — and it
reports both counts rather than a score:

> A fresh layout would draw this with 0 crossing bonds instead of 2.

Morphine is the case that shows why it matters. Its standard depiction has one
bond crossing — that is the price of drawing a fused polycyclic flat — and
regenerating it still has one. So the crossing is flagged, and no redraw is
offered, because accepting one would cost you your layout and fix nothing.

A structure with 3D coordinates is never offered a flat redraw. Its bonds
cross in projection from most angles, and replacing real geometry with a
drawing is data loss rather than a tidy-up.

### Ignoring a check

Right-click a finding to **Fix** it, **Copy message**, or **ignore that check
for this molecule**. Query atoms, reaction templates and teaching examples are
drawn wrong on purpose, and there has to be a way to say so.

Ignoring is recorded, not hidden: the check reappears under **Not checked**
with "suppressed for this molecule", so a later reader can tell a waived check
from a passed one. It applies to that molecule alone.

### Checks that did not run

A structure that will not sanitize makes every aromaticity and stereo
question downstream of it meaningless. Rather than answer them badly, the
panel lists those checkers under **Not checked** with the reason — usually
RDKit's own sentence, which is normally the most useful thing available
about a structure it refuses.

---

<!-- help:regulatory -->
## Regulatory screening

The **Regulatory** category in the Properties panel screens a structure
against the regulatory rulesets that ship with the application, and reports
what matched, from which instrument, and how confident that reading is.

It answers **"what frameworks appear to apply to this structure?"** — not
"is this legal?". That distinction runs through the whole feature, and the
wording follows from it.

**The result never says "not controlled", and never says "compliant".** It
says *"No matches in the N rulesets consulted"*. Those are different
claims: the first is a legal conclusion the application is in no position
to reach, and the second would be read as one. What the engine actually
knows is which rulesets it loaded and what they did or did not match.

Each finding carries:

- the **authority and instrument**, with the section cited and a verbatim
  quote of the legal text
- the **match type** — `identity` (this exact substance), `structural_family`
  (the regulation defines a family and this is in it), `analogue` (close to
  a listed substance, explicitly *not* a determination), or `precursor`
- a **confidence** — `exact` where the regulation is itself a structural
  specification, down to `requires_review` for anything unresolved
- the **atoms that matched**, rendered through the same per-atom colouring
  the rest of the panel uses

**Near misses are reported as a predicate checklist**, and they are the most
useful part for a legitimate user, because regulatory boundaries are exactly
what a plain "no match" hides. Diisopropyl fluorophosphate screened against
the chemical-weapons ruleset returns no match *and* an explanation:

```
No matches in the 1 ruleset consulted
Near miss: Alkylphosphonofluoridates (Schedule 1, A.1)
  - has phosphoryl (P=O), P-F bond, O-alkyl ester; lacks P-alkyl bond
```

That is the real distinction — DFP genuinely is not Schedule 1, and the
missing P–C bond is why. Sarin, which has it, matches.

A near miss is only offered when at least one predicate actually matched
atoms in your structure. Without that rule, ethanol came back as a near
miss to a nerve-agent schedule on the strength of a numeric bound it
happened to satisfy, which is worse than saying nothing.

**Coverage is stated, not implied.** The count of rulesets consulted is in
the result, and rulesets carry their effective date, source citation and
known limitations. What ships is only what could be verified and lawfully
redistributed, so the honest reading of a clean result is "these rulesets
did not match", never "nothing applies".

---

<!-- help:naming -->
## Naming

Structure-to-name works offline. Known compounds resolve against PubChem
when you have network; everything else is named by the vendored
deterministic IUPAC engine, and every generated name is verified by parsing
it back with OPSIN before you see it.

Names carry their **source** and whether they are `exact`, `derived` or
`parsed`. They are never merged into one unattributed answer — if two
sources disagree, you see that.

The reverse direction (paste an IUPAC name, get a structure) is available as
an import affordance, via OPSIN. Both directions need Java, installable from
External Tools.

---

<!-- help:menus -->
## Where things live in the menus

Following Marvin, **Edit** is about the document and **Structure** is about
the structure:

| Menu | Holds |
|---|---|
| **Edit** | Undo/redo, Copy Structure As, Paste Structure, Duplicate, Rename |
| **Structure** | Aromatize/Dearomatize, Layout, Clean Up, explicit hydrogens, Calculate CIP, Check Structure |
| **View** | Which panels are shown, and 2D Structure Display toggles |
| **Tools** | Periodic Table, Identify Structure Online, External Tools |

The structure operations used to sit under Edit, between "Redo" and "Copy
Structure As", where neither group was easy to find.

**Several things are deliberately reachable more than one way.** Check
Structure is on the Structure menu, on the Project Explorer's right-click menu,
and by clicking the status-bar indicator. Copy SMILES is on the Edit menu and
the right-click menu. The menu bar is how you find out something exists; the
right-click is how you use it afterwards. Copy SMILES was reported as missing
back when it lived in only one of the two.

---

<!-- help:periodic-table -->
## The periodic table

**Tools ▸ Periodic Table…** opens a reference table. It stays open while you
work, and selecting an element shows:

- its electron configuration, in the conventional shell order (iron reads
  `[Ar] 3d⁶ 4s²`, not the order the shells are filled in)
- group, period, block and category
- relative atomic mass, van der Waals and covalent radii
- Pauling electronegativity
- the oxidation states it is commonly found in
- **its naturally occurring isotopes, with abundances** — ⁵⁶Fe 91.75%, and so on

That last one is the part most periodic tables in drawing programs leave out.
It came free: RDKit's own tables carry the full abundance data, so none of it
is hand-entered.

**This is not the table you draw with.** The 2D editor's toolbar has its own,
which places atoms and can express query forms (Single / List / Not List) that
a reference table has no way to say. This one answers questions instead; it
offers **Copy symbol** and nothing that would place an atom.

### It says when something is not known

Oganesson has been made a handful of atoms at a time. Its common oxidation
states are **not established**, it has **no accepted electronegativity value**,
and it has **no naturally occurring isotopes** — and the table says each of
those in words, because a blank row would read as a bug rather than as a fact.

Technetium is the more familiar case: element 43 has no stable isotope, which
is why there is a gap in the table where you would expect one.

Iron reads "no defined valence", which is normal for a metal and is the same
fact the structure checker acts on when it declines to do octet arithmetic on
iron oxides.

Colour marks category, but never on its own — the category is written out in
the detail pane and in every cell's tooltip.

---

<!-- help:external-tools -->
## External tools

**Tools > External Tools** has seven tabs: AutoDock Vina, ORCA, pkasolver,
ADMET, Java (Temurin), NMR Database, and Storage.

Each tab tells you what is currently detected, installs or configures the
tool, and has a **Test** button that runs the tool for real rather than
checking a file exists — ORCA's runs a two-atom calculation and reports the
version it got back, Vina's runs `--version`, pkasolver's predicts acetic
acid's pKa. A path that exists proves nothing; these prove the tool works.

**Locate Installed** searches the usual install locations for you. It *runs*
each candidate before accepting it, which matters more than it sounds: "ORCA"
is a common name, and on a real machine this search found an unrelated
`Orca.exe` in a Windows Installer cache before the right one.

**Remove from Disk** appears only where this app installed the tool itself.
Vina it downloads, so it can remove it — and if you pointed the path at your
own Vina instead, it leaves that alone and says so. ORCA has no Remove button
at all: you installed it, so nothing here will delete it.

**ORCA is the one tool this app cannot fetch for you.** Its licence does not
permit automated or redirected downloads, so that tab offers a link to FACCTS'
customer portal rather than a Set Up button that could only apologise.

Storage lets you move the data directory and uninstall any sidecar.

None are required. The features they unlock degrade to a labelled "not
installed" state.

---

<!-- help:plugins -->
## Plugins

Three plugins ship: **AI Assistant**, **Database Search** and **Reaction
Prediction**. Enable or disable them from the plugin manager.

Plugins are loaded as source from a `plugins/` directory beside the
application, so you can add or edit one without a Python install. They
extend the app through the same interfaces the core uses — descriptor
providers, calculators, panels, importers — rather than through a separate
lesser API.

See [PLUGIN_SDK.md](PLUGIN_SDK.md) to write one.

---

<!-- help:surprises -->
## Things that surprise people

- **The Properties panel's NMR row is the instant empirical estimate.** Real
  ab initio NMR is in the Quantum Chemistry panel.
- **Shape and Geometry descriptors need a conformer.** They show a "needs a
  conformer" state with a button rather than silently reporting nothing.
- **"Min/max projection area" is measured on the three principal planes**,
  not searched over every orientation, so a molecule whose true narrowest
  view lies off-axis reads a little high. Each of those facts says so in its
  own tooltip, and the figures are exact for the case with a closed form —
  a single atom's shadow comes out as πr² to within 0.13%.
- **Three force field energies are shown, and none of them is comparable
  to another.** MMFF94, UFF and Dreiding are three different scales. Use
  one of them to compare conformers of the same molecule; comparing
  across the three, or between two different molecules, says nothing.
- **The Dreiding energy is computed here, not by a library.** No Python
  chemistry package implements Dreiding, so it is implemented from the
  1990 paper and checked against all eight rotational barriers that
  paper publishes. It leaves out charges and hydrogen bonds — as the
  paper's own reported results do — so read it as conformational strain
  rather than as an interaction energy.
- **Nothing computes over the network or spends real CPU without you asking.**
  PubChem lookups, ORCA jobs, docking and conformer generation are all
  explicitly triggered. Opening the Identify Structure Online dialog sends
  nothing until you press the button.
- **Conformers are invalidated when you edit the structure**, because they
  no longer describe the molecule you have. Duplicating a molecule does not
  carry them across, for the same reason.
- **Asking for ten conformers can correctly give you one.** Duplicates are
  pruned; a rigid molecule has one shape however many times you embed it.
- **A regulatory result of "no matches" is about the rulesets consulted**,
  not about the law. The wording says which.
- **`Ctrl+V` in the drawing canvas is Ketcher's paste, not the
  application's.** Whole-structure paste is `Ctrl+Shift+V`.
- **A molecule with no verified IUPAC name is normal.** The naming engine
  stays silent rather than emitting a name that will not parse back, so an
  empty Naming row is a refusal and not a failure.
- **Generating 3D coordinates for two separate species does not push them
  apart.** There is nothing connecting them, so they come out stacked on
  top of each other rather than side by side. Anything that reasons about
  how two partners sit together — the LED breakdown most of all — needs you
  to place them yourself.

## Knowing what a structure IS

The Properties panel carries an identity header above the results, and it
changes shape with what you have drawn:

    Sodium chloride                    Ferrocene
    NaCl          Ionic salt           C10H10Fe      Organometallic
    Formula unit  Na+ - Cl-            Metal centre  Fe(II)
    Charge        0                    Ligands       2 x eta5-Cp
    Components    2                    Donor atoms   10

The header is always there — you do not have to run anything to get it.
The full **Substance & Bonding** result, with the evidence behind the
verdict, is in the Structure section of the panel like any other
calculator.

### It tells you what it cannot tell you

Draw `[Na+].[Cl-].[K+].[Br-]` and the header refuses:

    Ambiguous ionic components
    the structure does not encode which ions constitute the same formula
    unit

That is not a bug. It could be NaCl + KBr, or NaBr + KCl, or a mixture of
four ions, and nothing in a drawing decides between them. Two disconnected
neutral components (`CCO.c1ccccc1`) get a third answer again — a mixture,
which is a different statement from "ambiguous".

### Ionic associations are not bonds

`[Na+].[Cl-]` has no bond in it, and the app will not add one. The
relationship between the two ions is reported as an *association*, and it
never carries a length: a distance between ions needs a real 3D structure,
and even then it is a contact measurement rather than a bond length.

### Coordination without geometry

From a flat drawing the app reports a complex's metal, its ligands, their
hapticity, and two separate counts — how many ligands are bound, and how
many ligand atoms are bound. It does **not** report "octahedral", because
that is a claim about angles and a 2D drawing has none. Generate a 3D
structure if you need a geometry.

Ferrocene is the case that shows why the two counts are separate: two
ligands, ten donor atoms. A single "coordination number: 10" would invite
you to read it as ten ligands.

### Metal-ligand bonds drawn as plain bonds

If you draw a metal complex with ordinary single bonds to its donor atoms
— as you might for Amavadin's vanadium — the Structure Check panel offers
**"Draw metal bonds as coordinate bonds"**. It marks each metal-ligand
bond as dative, which is the usual convention and stops the metal's
valence being over-counted. Nothing is added or removed, both drawings are
in normal use, and the change lands on the undo stack like any other.

The app never applies it for you. Perception describes what you drew; a
quick fix is an offer.

### Bond polarity, and what it is not

Select a bond and the Bond Inspector reports the **electronegativity
difference** across it and which end carries the negative charge — for
C–Li that is the *carbon*, which is the whole reason organolithiums behave
as they do.

It does not report a "percentage ionic character". That number comes from a
rule of thumb, and printing it to two decimals would claim a precision
nobody measured. The formula is named in the fact's limitations if you want
to apply it yourself.

### Ions that do not add up

If you draw charged components whose charges do not cancel — two sodiums
against one chloride — Structure Check says so specifically:

    The charged components do not cancel: +2 from the cations against
    -1 from the anions, leaving +1.

A single charged species is different and gets the ordinary "net charge"
note instead; a deliberate ammonium ion is not an error.

### Lattice energy

For a salt of two simple monatomic ions the Substance & Bonding result
carries an estimated lattice energy, marked with a `~` because it is an
estimate. It is accurate to about 5% for alkali halides — consistently on
the low side — and to about 2% for oxides and sulfides.

You will not get one for sodium acetate or ammonium nitrate. Polyatomic
ions need a different kind of radius, and the app would rather say nothing
than give you a number that looks right.

## Opening a crystal structure

**File → Import Crystal Structure...** reads a CIF, draws one unit cell in
the 3D Viewer, and opens a report of what can be said about it.

It is a separate action from *Import Molecule* on purpose. A crystal is
not a molecule: it has no bonds, no molecular weight and no logP, and
putting one into the project tree would invite every molecular calculator
to answer about it. The report says which calculators do not apply rather
than leaving you wondering why the Properties panel is empty.

The picture shows **one unit cell**, with the cell edges and the a/b/c
axes. Atoms are drawn as spheres and **no bonds are drawn**, because a
periodic solid does not have them — the Na–Cl contact in halite is an
ionic association, not a bond.

The report gives the cell, the space group, the atoms per unit cell
(fractional where a site is partly occupied), the X-ray density, and a
coordination number per crystallographic site with the distances it was
derived from.

The cell is fitted to the viewer when it is drawn. It sits a little above
centre in the panel; scroll to zoom and drag to rotate as with any
structure.
