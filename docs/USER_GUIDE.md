# User Guide

A working tour of the application. For installation see
[QUICKSTART.md](QUICKSTART.md); for what each number means scientifically see
[SCIENTIFIC_LIMITATIONS.md](SCIENTIFIC_LIMITATIONS.md).

---

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

---

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

**Macromolecule Viewer** — Mol\*, for proteins and nucleic acids. Cartoon
representations, chain colouring, and the receptor-residue highlighting that
docking interaction analysis feeds.

---

## Properties

The Properties panel is where most calculation happens. It has **23
collapsible categories**; Physicochemical and Identity are open by default.

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

Predictions are labelled `empirical` or `ab_initio` where there is a basis
to state one — worth reading, because "Nmr" in this panel is the instant
SMARTS estimate, not the ORCA calculation.

---

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

Long jobs appear in the **Jobs** panel and can be cancelled from there.

---

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

## Things that surprise people

- **The Properties panel's Nmr row is the instant empirical estimate.** Real
  ab initio NMR is in the Quantum Chemistry panel.
- **Shape and Geometry descriptors need a conformer.** They show a "needs a
  conformer" state with a button rather than silently reporting nothing.
- **Nothing computes over the network or spends real CPU without you asking.**
  PubChem lookups, ORCA jobs, docking and conformer generation are all
  explicitly triggered.
- **Conformers are invalidated when you edit the structure**, because they
  no longer describe the molecule you have.
