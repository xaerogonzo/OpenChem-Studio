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
explicit hydrogens), so they are reachable from the menu bar rather than
only from the canvas.

**Ketcher's own toolbar answers with this application, not with Ketcher.**
The editor ships a periodic table, file open/save, About, Help and a 3D
viewer, all of which this application already has — so pressing one of
them opens *ours*. There is one of each rather than two that look alike
and know different things. Its own periodic table used to open a plainer
one, which is how this was first noticed; its About showed Ketcher's
version number, and its save dialog defaulted to `.ket`, a format this
application cannot read back into a project.

Deliberately left alone, because replacing them would remove something
rather than de-duplicate it: **query atoms** (any / list / not-list),
Ketcher's **template library**, **clear canvas**, its **Settings** (render
options this app only partly mirrors under View ▸ 2D Structure Display),
and **polymer mode** — Ketcher can *draw* RNA/DNA/peptides, where the
Macromolecule Viewer only shows one.

### Seeing stereochemistry on the 2D canvas

Three separate things, and they are **not** one "show stereo labels"
switch — measured against the editor rather than assumed.

**R/S and E/Z come from a calculation.** *Structure ▸ Calculate CIP Stereo
Descriptors (R/S, E/Z)*, also offered under *View ▸ 2D Structure Display*
(the same menu item, in two places). It labels stereocentres `(R)`/`(S)`
and double bonds `(E)`/`(Z)` on the canvas. An atom whose configuration
the drawing leaves open gets **no label** — nothing invents an
assignment.

**It is computed once, on demand.** Editing the structure afterwards does
not recompute it, so a label can outlive the centre it describes; run it
again after an edit. Loading a different structure clears the labels.

The other two controls are about **enhanced stereo groups** — the ABS /
AND / OR machinery for saying "this is the drawn enantiomer" versus "a
mixture" — and neither of them shows R/S:

- **Show Stereo Flags (ABS / AND / Mixed)** — the molecule-level caption.
  A drawing imported from most file formats reads **AND Enantiomer**,
  because the file's chiral flag is 0; a structure this app derives from
  a 3D conformer reads **ABS**, because it sets that flag deliberately.
- **Stereo Group Labels (abs, &1, or1)** — the per-centre tag, with four
  settings: *IUPAC style* (the default — shown only where it adds
  something the molecule-level flag does not), *Classic* (hidden when the
  molecule has a single group), *On* (always), *Off* (never).

### Lone pairs on the canvas

**View ▸ 2D Structure Display ▸ Electron Display ▸ Lone pairs** draws
non-bonding pairs as dots. Ketcher itself cannot draw them and never
could, so these are OpenChem's: an overlay that follows the structure
through pan, zoom, rotation and editing, and which never becomes part of
the molecule. They are not in the molfile, not selectable, not exported,
and a click passes straight through them to the atom underneath. A
screenshot is the only way they leave the app.

**Nothing is drawn is not one answer, it is three**, so the status bar
says which:

| what you see | what it means |
| --- | --- |
| dots | that many non-bonding pairs |
| nothing, no message | this molecule has none — an ammonium nitrogen |
| "No lone pairs on the atoms this can speak for; N it cannot." | a mixture, usually a metal beside ordinary atoms |
| "Lone-pair analysis unavailable: …" | it declined, and says why |

The count follows the formal charge — an amine nitrogen has 1, an
ammonium nitrogen 0, an alkoxide oxygen 3 — and the same numbers are in
the **Atom Inspector** per atom, with the full reason when it declines.

**Where a pair is drawn is a convention, not a measurement.** The
placement keeps dots off the bonds and out of the atom's label and is
deterministic, so they do not jump about when you edit or turn the
molecule. It says nothing about orbital direction.

**Formal charges are not drawn by this**, because Ketcher already puts
them in the atom label.

### Full Lewis Structure

**View ▸ 2D Structure Display ▸ Full Lewis Structure…** opens a separate
window holding the textbook picture: every bonding pair as two dots,
every lone pair as two dots, explicit hydrogens, and no bond lines.

It is **not** a third setting of the overlay above, and that is why it
sits outside that group. The canvas cannot draw this at all — Ketcher has
no way to hide its bond lines, and a Lewis structure replaces each line
with dots — so this is a different picture of the same molecule, drawn by
OpenChem from the ground up.

**A delocalised bond keeps its localised part and gives up the rest.**
Benzene is not drawn as alternating singles and doubles, because the
molecule does not assert a Kekulé structure. Each ring bond gets the one
pair it has in *every* resonance contributor, and the six electrons left
over are drawn as a circle labelled with its count:

| you see | it means |
| --- | --- |
| two dots between atoms | a localised bonding pair |
| a dashed circle, labelled `6 e−` | a ring-delocalised system, and how many electrons are in it |
| a dashed outline through the atoms, labelled `2 e−` | the same for an open system — a carboxylate, a nitro group |
| a plain solid line | a connection this analysis declined to represent as electrons |
| `? e−` | the system is real and its electron count was not determined |

**Shape and line style carry the meaning, never colour** — dots, dashes
and a solid line — so the diagram survives greyscale, printing and a
screenshot.

A carboxylate therefore shows two *equivalent* C–O bonds rather than one
single and one double, and pyrrole shows its ring without claiming a
count it cannot derive.

**Four outcomes, never merged into two.** A refusal ("this structure
carries unpaired electrons") and a drawing failure are different problems
with different fixes, and a molecule that is simply large gets its
diagram plus *"may be hard to read at this size"* — never "analysis
unsupported". Anything the analysis declined to represent is listed by
name under **Analysis details**, together with the full electron budget
and every delocalised region.

**It is a snapshot and a view.** The window shows the molecule as it was
when you opened it and does not follow later edits — the header names
which molecule, and Analysis details carries the structure revision.
Nothing you do in it can change the molecule, the canvas or the undo
stack. **Copy SVG** and **Save SVG…** export the drawing as vector
artwork.

### Rotate 3D — turning a structure inside the 2D editor

**Rotate 3D**, at the top of the 2D Editor tab, turns the structure in
three dimensions and draws the result on the 2D canvas — a molecule in a
literal 3D shape, in a 2D editor. Rulers appear down the left and across
the top, and the live X/Y angles are shown both on the bar and at the
right of the blue banner.

While the mode is on, **dragging turns the molecule instead of drawing**,
which is why the banner is there and why it is a mode you switch on
rather than a modifier you hold. **Cancel** leaves it and puts the entry
geometry back; letting go of a drag commits it as one undo step, so
Ctrl+Z reverses a whole turn rather than a frame of one.

**A flat drawing has nothing to turn**, so pressing the button on one
does something different depending on what the molecule has:

| the molecule has | pressing Rotate 3D |
| --- | --- |
| a conformer selected in the 3D viewer | draws that one, then rotates |
| conformers, none selected | draws the lowest-energy one, then rotates |
| no conformers at all | offers to generate, and stops there |

The last row is deliberate. Turning an existing geometry is
visualisation; creating one is a chemical operation that can *define*
stereochemistry your drawing left open — see **What adopting a conformer
decides for you** below — so it asks first and does nothing if the answer
is no.

Rotation itself changes coordinates and nothing else: same atoms, bonds,
charges and stereocentres. If it ever appears to change one, the app
refuses the whole rotation and says so rather than committing it.

**3D Viewer** — 3Dmol, showing conformers. Style selector
(stick / ball-and-stick / spacefill / line), conformer navigation, a
distance/angle measurement readout, and molecular surfaces (vdW, SAS, MS)
with an opacity control. Conformers come back sorted by energy, so
conformer 1 is the lowest.

**Generation no longer requires this tab.** *Structure ▸ Generate
Conformers* runs the same dialog and the same service from anywhere, and
so does the command palette (Ctrl+Shift+P, "conformers"). The 3D viewer
is where you *look* at them.

**You will often get fewer conformers than you asked for, and that is the
answer rather than a failure.** Embedding is random, so asking for ten
conformers of a molecule that has one shape produces ten copies of it.
Duplicates are pruned, and the status line says what happened —
"1 distinct conformer from 10 embedded". Aziridine and benzene have one
conformer; butane has two. Requesting more does not create more.

**Some results draw themselves on a 3D model.** A calculator whose answer
is a *shape* — the dipole moment's vector, a ligand's steric cone, the
principal axes behind the molecular dimensions — opens its **Details…**
onto the stored conformer with that shape drawn on it, the way Marvin's
dipole plugin shows its arrow. The arrow's direction is the physics
(it points from the negative end toward the positive, the raw Σq·r
vector); its drawn *length* is scaled to the molecule for legibility, and
the label carries the true magnitude. Per-atom results (charges, LogP
contributions, SASA…) have always had their own 3D view in the Calculator
Inspector; this extends the same idea to results that are one geometric
object rather than one number per atom. Everything else — a formula, an
index, a pKa — deliberately gets no picture: a number with no geometry
would only be dressed up by one. The model is drawn on the *stored*
conformer, and the dialog says so: if you regenerate conformers after
calculating, rerun the calculator before trusting the picture.

**Show shapes** draws them on the conformer you are looking at. Tick it
in the 3D viewer's toolbar and any shape-valued result you have already
calculated — the dipole vector, a ligand cone, the principal axes — is
drawn on the structure on screen, turning as you turn it and following
you as you step conformers.

**In the gallery it draws in every cell**, and each one is its own
answer: the shape in a cell is recalculated for the conformer *that cell*
is showing, not copied from the selected one. Six cells of a flexible
molecule will show six different dipole arrows pointing six different
ways, each captioned with its own value beside the arrow rather than in
the status line — one line cannot honestly carry six numbers, and the
line goes on describing the page ("Conformers 1-6 of 8"). Paging
recalculates for the new page.

**Its number can differ from the Properties panel's, and both are
right.** They answer different questions:

- the **Properties panel** reports what the calculator found when it ran,
  for the conformer it ran on;
- the **3D overlay** is freshly calculated for the conformer *currently
  displayed*.

A flexible molecule genuinely has a different dipole in each conformer —
measured on ethylmorphine, 5.53 D on the lowest-energy one and 4.71 D
three conformers along — so the overlay labels its value with the
conformer it belongs to. If the two disagree, that difference is
information, not an inconsistency.

Only results you have already calculated appear; the overlay never runs
anything you did not ask for, and a molecule with no shape-valued results
leaves the control greyed out. While a conformer's shapes are being
computed nothing is drawn, rather than the previous conformer's geometry
being left on screen.

**Details…** in the 3D viewer's toolbar shows where a run's candidates
went: how many embeddings were attempted, how many embedded, how many
converged, how many distinct shapes they came to, and how many were
returned. It computes nothing — every count was recorded when the run
happened.

The row worth reading is **Distinct** against **Returned**. A flexible
molecule can find more distinct conformers than the "distinct conformers
to keep" limit, and the rest are simply not returned. They are real: they
converged, and they differ under the same criterion as the ones you kept.
The dialog says so explicitly when that is what happened, and generating
again with a higher limit returns them.

The defaults were raised (keep 10 → 20, embeddings 50 → 100) precisely
because this used to be the ordinary case: at the old settings a
drug-like molecule routinely found 12–13 distinct and silently kept 10.
At the new defaults truncation is the exception — but the limit still
exists, and the dialog still names it when it bites.

Two embeddings count as the same conformer when their heavy atoms and
their polar hydrogens are within 0.5 Å RMSD, compared symmetry-aware so
that the two ends of butane are not called different for having been
numbered the other way round. Hydrogens on carbon are ignored — a rotated
methyl is not a conformer — but hydrogens on N, O and S are kept, because
an O–H orientation changes hydrogen bonding and changes the energy of any
QM job you run afterwards.

**Generate Conformers** asks for six things. Two are counts —
embeddings to try, and distinct conformers to keep. The other four are
modelled on the controls in ChemAxon's Generate3D calculator, and are
emulations of those controls rather than of the algorithms behind them:

- **Diversity threshold (RMSD)** — how far apart two embeddings must be to
  count as different shapes. This is a sampling and de-duplication
  parameter, *not* a definition of what makes two conformers different;
  no single value is right for every molecule. 0.5 Å was fitted to butane,
  whose pairwise RMSDs really are bimodal, while a drug-like molecule's
  are a flat continuum with no gap for a threshold to sit in.
- **Optimisation** — Loose, Normal, Strict or Very strict, setting how many
  iterations and how tight a gradient each embedding is minimised to.
  These are OpenChem's levels, not numerical equivalents of Marvin's.
  Measured over 30 embeddings each of seven molecules, every level
  converged 30 of 30 and the retained count differed on only one
  molecule — ethylmorphine, where Loose found 8 against 9 elsewhere. A
  geometry that does not converge is discarded at every level.
- **Time limit** — stops *starting* new embeddings once the time is up.
  Not a hard ceiling: neither RDKit's embedder nor its minimiser can be
  interrupted part-way, so a run can overshoot by one embedding.
- **Enhanced refinement** — a second, stricter minimisation over the
  survivors. **This is not Marvin's "hyperfine"**, which runs short
  molecular dynamics before its strict optimisation; there is no MD engine
  here, and a minimiser cannot leave the basin it is already in. Measured,
  it changes nothing at Normal or above, and its one visible effect was
  recovering what a Loose run had lost, at about 25% more time. It is not
  a way to find more conformers.

**Comparing conformers.** Every conformer is superimposed on the
lowest-energy one for display, and stepping between them with `<` and `>`
keeps the camera exactly where you put it. So arranging a view and then
flipping through the set shows you the difference in shape and nothing
else. The coordinates that get saved and exported are untouched — the
superposition is a viewing aid, recomputed each time.

The energy shown is relative to the lowest (`+0.55 kcal/mol`), because the
raw force-field number is not a quantity anybody compares to anything. The
absolute value is in the tooltip.

**The gallery** shows several conformers at once, each in its own cell and
each rotatable on its own — tick *Gallery* in the 3D Viewer's toolbar. Six
cells by default (2 x 3), with 2 x 2, 3 x 3 and 3 x 4 available; `<` and `>`
page through the set rather than stepping one conformer at a time. Clicking
a cell's label selects that conformer, which is what "Use in 2D Editor"
then acts on.

Three controls make it a comparison rather than a contact sheet:

- **Lock views** ties the cells together, so turning one turns all of them.
  With the conformers already superimposed, that leaves the difference in
  shape as the only thing changing between cells.
- **Match all to selected** points every cell where the selected one is
  pointing and then lets go, so you can line them up and still inspect one
  on its own afterwards.
- **Superimpose ticked** draws the ticked conformers in one frame, each a
  different colour. Ticking is separate from clicking: one marks a
  conformer for superimposition, the other chooses which conformer the rest
  of the toolbar acts on.

**Show shapes** works here too, per cell — see *Shapes you can look at*
above. It is what turns the gallery from "these are different shapes"
into "and here is what that does to the dipole".

The gallery needs a second 3D drawing surface from your display. Where one
is not available — some remote sessions and software renderers — it says so
and goes back to showing one conformer at a time.

Conformer generation is on the **Structure** menu (and in the command
palette) as well as in the 3D Viewer, so you never have to open a viewer
to get one.

**Use in 2D Editor** takes the conformer on screen — the one you navigated
to, not the first — and hands the 2D editor **the 3D structure as you have
it rotated**. The molblock keeps its z, the editor draws its x and y, so
what you get is a projection of the geometry you were just looking at,
the way MarvinSketch draws buckminsterfullerene in perspective. Crossing
bonds are not a fault: that is what a projection of a real 3D shape looks
like. It is a single undoable step, and Ketcher holds those coordinates
through subsequent edits.

Two things it deliberately does *not* do:

- **It does not put the conformer's hydrogens in your drawing.** A
  conformer is embedded with explicit hydrogens (aspirin's is 21 atoms
  against the 13 you drew), and a drawing carrying them is a different
  structure to everything that compares one — eight of the registered
  calculators report different numbers for it. The drawing keeps its
  implicit hydrogens.
- **It does not throw away your conformers.** The structure has not
  changed, so they are all still valid and the 3D viewer keeps showing
  them.

It changes the drawing, and only the drawing. What a calculation computes
with is unaffected: anything needing 3D already uses the lowest-energy
conformer automatically, and still does. Stereochemistry survives the
round trip — turning the camera can never change an R centre into an S
one, and the drawing still declares itself a single enantiomer rather
than a relative arrangement.

**Bringing a geometry in can define stereochemistry your drawing left
open, and it says so.** A bicyclo[2.2.2] cage's bridgeheads are
unspecified in a flat drawing and assignable once the atoms have real
positions, so adopting adds `-- and defined 2 stereocentres your drawing
left open` to the status line. The molecule really has become more
specific than you drew it, and that is worth knowing rather than
discovering later.

**If a geometry would CHANGE stereochemistry you had specified, it is
refused.** An R centre that came back S is a different compound; nothing
is committed and the drawing is left as it was.

**Some angles put atoms on top of each other, and it will say so.** Look
down the bridgehead axis of a bicyclo[2.2.2] cage — quinuclidine, DABCO, a
benzobicyclo[2.2.2]octane — and its two bridges superimpose exactly. You
still get the view you asked for, with the status bar telling you to turn
the view a little and try again, rather than being given some other
orientation you did not choose.

If the viewer cannot report a camera at all, the drawing falls back to a
flat depiction laid out to follow the conformer, and says so.

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
calculator, every computed property and every menu command at once — 142 of
them — so you never have to remember which group a panel is filed under or
which menu holds a command.

It also searches words that are *not* on screen: file formats find the
importer that reads them (`cif`, `sdf`, `xyz`, `mmcif`, `pdb`), and a
calculator's own tags find it by subject, so `toxicity` reaches ADMET and
`screening` reaches Virtual Screening. A **computed property** cannot be
run — the whole batch is computed when you select a molecule — so choosing
one scrolls the Properties panel to its row instead, which is the useful
answer to "where is ESOL?".

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
looking at, gets a **button of its own** instead, labelled with the
calculator's name and a trailing `…`.

That ellipsis is a promise and it is kept: every one of them opens a
**settings dialog built from the calculator's own parameter list** (pH, decimal places, a SMARTS string, whatever that
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

Tick the box beside any calculator you want and press **Run selected**. The selection spans categories, so you can tick something from
Charge and something from Topology and run both together — they were
already running on a thread pool, so this is genuinely concurrent rather
than a queue.

Batch runs use each calculator's **declared defaults and open no dialogs**,
because answering six settings dialogs to avoid six clicks is not a saving.
No inspector windows open either. Press the calculator's own button when
you need non-default settings.

Each result appears in its own category as a one-line summary
("22 atoms, −0.41 to 0.33 e"); press the calculator's button for the full
per-atom detail. The status line beside the buttons says what is running
and reads **Finished.** when the last one lands.

**A calculator that is working says so on its own row**, whether you
started it from its button or from Run selected: the row reads
*Running…* until the result lands. Some of them take real time — the
ADMET model is about six seconds — and before this the panel showed
nothing at all for that whole stretch, then the result and its window
arrived together. It reads as a slow dialog and is not one.

### Categories worth knowing about

| Category | What's in it |
|---|---|
| Physicochemical | MW, logP, TPSA, HBD/HBA, rotatable bonds |
| Solubility | ESOL solubility, the Low/Moderate/High category, solubility at a chosen pH, the pH–solubility curve, a BCS high-solubility screening estimate, and solubility in 91 non-aqueous solvents |
| Identity | formula, exact mass, elemental composition, InChI/InChIKey |
| Naming | IUPAC name with its source and exactness label |
| Charge | Gasteiger partial charges, and charges at a chosen pH |
| Lipophilicity | logP per-atom contributions, and pH-dependent logD with its curve |
| Topology | Wiener, Randić, Balaban, Platt, Szeged, Harary, per-atom eccentricity |
| Geometry (3D) | radius of gyration, molecular radii, projection area, MMFF94/UFF/Dreiding energies, 3D alignment, molecular dynamics and intramolecular contacts |
| Surface Area | SASA (total and per-atom), vdW surface, molecular volume |
| Structure Generators | stereoisomers, tautomers, resonance forms, conformers |
| Quantum (Hückel) | orbital energies, π densities, HOMO/LUMO and the gap |
| Electronic Properties | polarizability (molecular and per-atom), orbital electronegativity, molar refractivity |
| Stereochemistry | CIP descriptors and the stereocentres they label |
| Medicinal Chemistry | Lipinski, Veber, Ghose, Egan, Pfizer 3/75, GSK 4/400, Rule of Three, QED, PAINS |
| ADMET / Regulatory | BRENK alerts, BBB, bioavailability, hERG risk factors, ML predictions if the sidecar is installed, and the regulatory ruleset screen |
| pKa | ionizable groups, and numeric pKa if the sidecar is installed |
| Substructure Search | match your own SMARTS, or browse the built-in validated patterns |
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
difference: it does not print a total for them, because summing category
ids produces a number that looks like a measurement and is not one.

### What the number at the top of the Inspector means

The headline is the **molecule's** value for the property, and the
calculator that produced it is what says so. It is never worked out by
adding up the atoms on screen, and for several calculators those two are
genuinely different numbers.

LogP is the clearest case. Crippen's method gives every atom an
increment, **hydrogens included** — but a structure drawn in the editor
keeps its hydrogens implicit, so they have no atom to carry theirs. Add
up the twenty-one labels on an aspirin-sized molecule and you get 0.86;
its LogP is 3.62. Both are right, and the Inspector says so directly:

> **LogP (Crippen): 3.624**
> 21 heavy-atom contributions sum to 0.86 - the balance (+2.77) is on
> implicit hydrogens.

The **Hydrogens** option on LogP Contribution and Molar Refractivity
Contribution decides where those increments go:

| Setting | What you see |
|---|---|
| **Heavy atoms only** (default) | the contribution of each atom as drawn; the labels will not sum to the total |
| **Increment of Hs** | each heavy atom also carries its implicit hydrogens', so the same atoms now sum to the total |
| **Explicit hydrogens** | every hydrogen is drawn with its own contribution |

They are three views of one calculation — the LogP itself is identical in
all three. "Increment of Hs" is the same option, under the same name, that
Partial Charge has always offered.

A calculator whose per-atom values have **no** meaningful molecular total
shows no headline at all. Eccentricity is one: it is the distance from an
atom to the furthest other atom, and adding thirteen of those together is
arithmetic rather than chemistry. The graph-level answers — radius and
diameter — are in Topology Analysis instead.

`locants` is the one with a real coverage caveat, and it states it rather
than rendering blank. Roughly half of all molecules name to a form that
carries no atom indices at all, and for those the locants come from ring
templates instead of from the name — so an empty or partial result is a
property of the naming path, not a failure.

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

## Molecular dynamics

**Geometry (3D) ▸ Molecular Dynamics (vacuum)** runs a short MMFF94
trajectory and opens a **player**: the frame in 3D, a scrubber, play and
pause, and the energy trace underneath with a marker on the frame you are
looking at. Clicking the trace jumps to that frame, which is usually what
you want — the interesting moment is a spike, and hunting for it again on
the slider is busywork.

**It is a vacuum run at a force field level.** No solvent, no periodic
box, no thermostat beyond the initial temperature. It is for seeing how a
structure moves and where it is floppy, not for a free energy.

A 2D depiction would have been the cheap way to show this and a useless
one: dynamics moves atoms without changing what is bonded to what, so
every frame of a vacuum run draws the same picture. The motion only exists
in three dimensions.

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

<!-- help:solubility -->
## Solubility

The **Solubility** category predicts how much of a compound dissolves —
an intrinsic (neutral-species) value, a value at a pH you choose, a
Low/Moderate/High category, a pH–solubility curve, and a BCS
high-solubility screening estimate.

Everything here is **predicted, not measured**. The baseline model is ESOL
(Delaney 2004), whose error on a druglike test set is around 1.3 log
units — a factor of twenty. Treat it as a comparison between molecules
rather than a number to put in a protocol.

### Reading the numbers

Every value appears in three units — logS, mg/mL and mol/L — because the
same solubility in different units is the single easiest thing to
misread. The row you chose is shown first; the other two are there when
you expand the detail.

**The category is computed from the intrinsic value, not the pH-adjusted
one**, which is how ChemAxon defines those thresholds: below 0.01 mg/mL
Low, up to 0.06 Moderate, above it High.

### If your molecule is a base, the panel says so

ESOL **under-predicts bases by roughly half a log unit** — measured bias
−0.59 on the Solubility Challenge (n=27) and −0.42 on a second,
independent set (n=17). Any base carries a note saying the value is likely
**low**.

**The number is not silently adjusted for it**, and that is a deliberate
decision rather than an oversight. An adjustment was fitted and put through
a held-out test whose criteria were fixed in advance; the improvement could
not be distinguished from sampling noise, so it was not applied. You are
told about the bias and left to allow for it, which is worth more than a
constant nothing has validated.

**"Not distinguishable from noise" is not "there is no bias."** The bias is
measured, it replicates on two independent sets, and the adjustment does
remove it on the compounds used to fit it. What is missing is enough
*held-out* druglike bases to show it generalises. Acids and neutral
molecules are unaffected and carry no such note.

### Choosing a solvent

The **Solvent** parameter offers **91 solvents** — water first, then the
rest alphabetically. Water is the default and is the only one the pH
machinery applies to.

Outside water the answer comes from Abraham's solvation equation, and
**both halves are looked up rather than predicted**: measured coefficients
for the solvent, measured descriptors for your compound. That makes it
accurate where it answers and narrow in what it answers for:

- **A compound nobody has measured is refused by name.** There is no
  fallback to an estimated descriptor. If you see that refusal, the model
  genuinely does not know, rather than knowing badly.
- **Two literature sources that disagree too much are also refused.**
  Aspirin in toluene is a real case: the published descriptors differ
  enough to leave more than a factor of ten in the answer, so it declines
  instead of reporting the midpoint.
- **The aqueous error carries through.** The shift is measured; what it
  moves is still an ESOL prediction, so a non-aqueous answer is never
  more reliable than the aqueous one behind it.

**Acetic acid is not available.** It appears only in the source's
*predicted* coefficient set, of which the authors say the values should
not be taken "as gospel", so it is refused rather than guessed.

### What is water-only, and why

pH, the pH–solubility curve, the Low/Moderate/High category and the BCS
screen are all **aqueous concepts**. Henderson–Hasselbalch, the pKa values
behind it, ChemAxon's thresholds and the ICH M9 window are every one of
them defined on water.

So a non-aqueous solvent gives you an intrinsic solubility and nothing
else — the category reads *"Not applicable outside water"* and the BCS
line says *ICH M9 is defined on aqueous media*. Those are deliberate
refusals, not missing features: a pH curve for a compound in hexane would
look authoritative and mean nothing.

### pKa, and supplying your own

The pH-dependent half needs pKa values. It uses the pkasolver sidecar when
it is installed, and you can **type your own** into the pKa field
(`3.49`, or `4.8, 9.4` for a diprotic) — a measured pKa always beats a
predicted one, and a manual entry overrides the predictor.

**Ampholytes and salts are refused.** A zwitterion's un-ionized form *is*
the zwitterion, which is highly soluble, so Henderson–Hasselbalch puts the
minimum in the wrong place; a drawn salt is already the species the
correction models forming. Both say so rather than producing a plausible
curve for a different compound.

### The BCS line is a screen, not a classification

ICH M9 requires solubility established **experimentally** over pH 1.2–6.8
at 37 °C, using the lowest measured value and the highest single
therapeutic dose. Everything here is predicted at no defined temperature.

It reports PASS or FAIL only when the answer holds across the whole range
the model can justify, and **UNDETERMINED with a reason** otherwise — no
dose given, no pKa available, or the bounds genuinely straddling the
criterion. Dose number addresses only the solubility half of BCS;
permeability is a separate measurement entirely.

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
  specification and the pattern transcribes it, `verified` for a named
  substance whose identity was checked against the primary text,
  `approximate` for a reading of prose that structure cannot fully carry,
  and `requires_review` for anything unresolved
- for a **precursor**, the legitimate uses it also has. Most listed
  precursors are ordinary reagents — thionyl chloride converts acids to
  acyl chlorides, triethanolamine is in a great deal of cosmetics — and a
  finding without that context reads as an accusation
- the **atoms that matched**, rendered through the same per-atom colouring
  the rest of the panel uses

**Near misses are reported as a predicate checklist**, and they are the most
useful part for a legitimate user, because regulatory boundaries are exactly
what a plain "no match" hides. Diisopropyl fluorophosphate screened against
the chemical-weapons ruleset returns no match *and* an explanation:

```
No matches in the 3 rulesets consulted
Near miss: Alkylphosphonofluoridates (Schedule 1, A.1) - has phosphoryl
  (P=O), P-F bond, O-alkyl ester, total carbons <= 10; lacks P-alkyl is
  methyl, ethyl, n-propyl or isopropyl
```

That is the real distinction — DFP genuinely is not Schedule 1, and the
missing P–C bond is why. Sarin, which has it, matches. Near misses are
capped at three, because past that the list stops explaining and becomes a
catalogue of everything the structure is not.

A near miss is only offered when at least one predicate actually matched
atoms in your structure. Without that rule, ethanol came back as a near
miss to a nerve-agent schedule on the strength of a numeric bound it
happened to satisfy, which is worse than saying nothing.

**Coverage is stated, not implied.** The count of rulesets consulted is in
the result, each ruleset's own limitations appear beside it, and every
registered domain with no ruleset loaded is listed as NOT checked. What
ships is only what could be verified and lawfully redistributed, so the
honest reading of a clean result is "these rulesets did not match", never
"nothing applies".

### Screening as of a past date

**Screen as of** (in the calculator's settings, blank by default) answers
*"was this listed when the sample was made"*. Give it a date as
`YYYY-MM-DD` and rules that took effect after it are withheld — including
from the near-miss list, so the screen never tells you a structure is one
feature away from an entry that did not yet exist.

Leave it blank and nothing changes: every loaded rule is screened, exactly
as before the field existed.

The result says which date it used, and each ruleset's coverage line says
what that date cost it — `4 of 14 rules withheld, effective after
2020-06-06; 10 applicable`. A screen that quietly dropped rules and still
reported "no matches in the 4 rulesets consulted" would be telling you far
less than it appeared to.

Three things to know before trusting a dated answer:

- **It reports when a rule *started* applying, and nothing else.** No
  ruleset here records repeal or expiry, so a substance since removed from a
  schedule still appears at any later date.
- **A ruleset with no dates is not constrained by yours.** The DEA list
  records none, so its 47 rules are reported whatever date you ask for. The
  coverage line says so; it is not confirmation that they applied then.
- **A date the application cannot read is refused**, not quietly ignored.
  The screen does not run and tells you why, because handing you today's
  answer to a question about 2019 would be worse than handing you nothing.

**What ships today is all three CWC schedules and the US DEA listed
chemicals** — two of the twelve registered domains. The other ten are
still empty and say so on every screen. Expect ordinary chemicals to appear: Schedule 3
lists phosgene, hydrogen cyanide, thionyl chloride and triethanolamine, all
of them large-scale industrial chemicals, because the schedules exist to
mark what gets declared and verified rather than what is forbidden. A
match is a listing, not an accusation, and the panel is worded that way.

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
| **Structure** | Aromatize/Dearomatize, Layout, Clean Up, explicit hydrogens, CIP stereo descriptors, Generate Conformers, Check Structure |
| **View** | Which panels are shown, and 2D Structure Display toggles |
| **Tools** | Periodic Table, Identify Structure Online, Virtual Screening, External Tools |

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

**There used to be two of these, and now there is one.** The 2D editor's
toolbar has a periodic table button of its own; pressing it opens *this*
table. Before, it opened Ketcher's plainer one, and which table you got
depended on which button you happened to press — reported, reasonably, as
the periodic table having "reverted to vanilla".

So it draws as well as explains. **Insert into drawing** arms the 2D
editor with the selected element: press it, then click the canvas where
the atom goes. That is the same gesture the editor's own table used, so
there is one way an atom reaches the canvas rather than two. The dialog
stays open, because placing three heteroatoms should not mean reopening
it between each.

**Query atoms are the one thing it cannot do.** Any-atom, and list /
not-list forms, are drawing constructs a reference table has no way to
express; the editor's own tools still place those. The dialog says so
rather than leaving you to find out.

### The atom, drawn

Above the facts table the selected element is **drawn**: shell rings around
a nucleus labelled with its protons and neutrons, and the same
configuration again as orbital boxes with spin arrows — `1s ↑↓ | 2s ↑↓ |
2p ↑ ↑ ↑`. The picture sits above the table rather than below it because
the configuration string in that table is the same information, and a
diagram explaining a line of text belongs beside it.

**The + and − buttons make ions**, and this is the part worth knowing
about. Removing an electron does *not* take one off the end of the written
configuration, because that is wrong for exactly the elements people try
first:

    Fe     [Ar] 3d⁶ 4s²
    Fe²⁺   [Ar] 3d⁶        ← 4s empties first, though it filled last
    Fe³⁺   [Ar] 3d⁵

**The diagram says where each configuration came from** — one quiet line,
so you can tell a curated value from a derived one without the interface
making a fuss about it. In practice every *ion* currently reads "general
ionisation rule": the rule was checked against 23 ions and got all of
them, so there was nothing left for a lookup table to correct and it
ships empty. Neutral atoms are the curated ones, anomalies included —
chromium is `[Ar] 3d⁵ 4s¹` and copper `[Ar] 3d¹⁰ 4s¹` because the shipped
element data says so, not because a rule derived it.

It also reports an **isoelectronic noble gas** where there is one: Na⁺, F⁻
and O²⁻ are all isoelectronic with neon. Fe²⁺ gets nothing, because
matching an electron count is not the same as being isoelectronic with
something noble — 24 electrons would make it "isoelectronic with
chromium", which is true and not what the control is offering.

**The neutron count belongs to an isotope, not an element**, so it is
labelled with the isotope it came from — silicon's nucleus is drawn with
14 neutrons and says "most abundant isotope, ²⁸Si".

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
- **`Ctrl+Z` is the application's undo everywhere, including inside the
  canvas.** Ketcher binds it too, and its undo used to *add* to the
  application's history rather than unwind it — measured, the stack grew
  from 3 to 4 on an undo — while undoing past the point where the
  structure was loaded emptied the canvas and the molecule with it. Both
  the shortcut and the toolbar button are answered by the application
  now, so there is one history.
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

**File → Import Crystal Structure...** reads a CIF, adds it to the project beside your molecules, draws one unit cell in
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

### A crystal is part of the project

An imported crystal appears in the Project Explorer marked `[crystal]`,
and is **saved with the project**. Close the app, reopen the file, click
the entry, and the cell is drawn again.

Two consequences worth knowing:

- **It is not in the molecule lists.** Compare, batch analysis and every
  calculator work from the project's molecules, and a crystal is not one
  — a molecular weight or a logP is a property of a discrete molecule
  and a periodic solid has none. The crystal report says how many
  calculators were skipped and why.
- **What is stored is the CIF text**, not a processed version of it. That
  means a project saved today reads *better* tomorrow if the CIF reader
  improves, and nothing the reader currently ignores is thrown away.

Rename a crystal by double-clicking its row, and delete it with the
Delete key or the context menu — both undoable, and undo puts a deleted
crystal back where it was rather than at the bottom. The `[crystal]`
marker is part of the display, not the name: editing the row hands the
whole string back and the marker is stripped before saving.

### Clicking an atom in the cell

**Click any sphere** and the status bar names that site's coordination
environment in one line:

    Na1 (Na): 6 neighbours (6 Cl), octahedral, nearest Na-Cl 2.820 A

A window opens alongside it with the full detail — every neighbour and
its distance, the mean, the coordination polyhedron and, under
*Everything*, all the neighbour–site–neighbour angles. Clicking a second
atom **replaces** what that window shows rather than opening another, so
you can walk around a structure comparing sites.

Two things worth knowing about the answer:

- **The neighbours are named, not just counted.** "6 (6 Cl)" and
  "3 (3 H)" are very different environments, and the composition is what
  tells you which you are looking at. If a geometry looks odd, the
  neighbour list usually explains it — see the coordination note in
  `SCIENTIFIC_LIMITATIONS.md`.
- **Several neighbours belong to next-door cells.** They are found as
  real periodic images, which is why halite's sodium has six chlorides
  even though the asymmetric unit holds one.
