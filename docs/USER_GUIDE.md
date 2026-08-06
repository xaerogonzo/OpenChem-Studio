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

### Categories worth knowing about

| Category | What's in it |
|---|---|
| Physicochemical | MW, logP, TPSA, HBD/HBA, rotatable bonds, ESOL solubility |
| Identity | formula, exact mass, elemental composition, InChI/InChIKey |
| Naming | IUPAC name with its source and exactness label |
| Charge | Gasteiger partial charges, and charges at a chosen pH |
| LogP / LogD / Molar Refractivity | per-atom contributions, and pH-dependent logD |
| Topology | Wiener, Randić, Balaban, Platt, Szeged, Harary, per-atom eccentricity |
| Geometry (3D) | radius of gyration, molecular radii, MMFF94 and UFF energies |
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

<!-- help:external-tools -->
## External tools

**Tools > External Tools** has seven tabs: AutoDock Vina, ORCA, pkasolver,
ADMET, Java (Temurin), NMR Database, and Storage.

Each tab tells you what is currently detected, installs or configures the
tool, and has a Test button that runs a real calculation rather than just
checking a file exists. Storage lets you move the data directory and uninstall
any sidecar.

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
