# Structure template library

OpenChem-owned catalog of complete molecules for the 2D editor. Not Ketcher's
template button, not the reference editor, and not a peptide or polymer builder.

## What it is

A person opens **Structure > Template Library…**, picks a shipped or user
template, and Inserts it onto the current drawing. The fragment is placed to
the right of what is already there. The change is one undo step.

Ketcher's own template library and polymer mode stay as they are
(`docs/USER_GUIDE.md`). This library does not replace them.

## Representation

A `TemplateEntry` has **exactly one** of `smiles` or `molblock`. Both or
neither is refused.

- Shipped entries are SMILES.
- User drawings and imported molfiles keep a 2D molblock.

Optional: `description`, `tags` (search aliases), `source` (a key in
`docs/sources.toml` when there is one). `kind` is `complete_molecule` in this
slice.

A category has a stable `id` and a display `title`. `origin` is `shipped` or
`user` and is not a free string: user JSON cannot claim `shipped`. User
category ids start with `user:`. Duplicate titles are allowed; duplicate ids
are not.

## Catalog

Shipped JSON lives under `src/openchem/chem/data/structure_templates/`, loaded
the same way as the other `chem/data` tables (`Path(__file__).parent / "data"`).
PyInstaller already copies all of `chem/data/`. User data is never stored there.

Shipped categories, all **complete molecules** (no dummy `*` attachment points).
Each molecule appears in **one** category. The research inventory in
`docs/STRUCTURE_TEMPLATE_CANDIDATES.json` is not loaded.

| id | contents |
|---|---|
| `rings` | benzene, cyclohexane, cyclopentane, pyridine, pyrrole, furan, thiophene |
| `amino_acids` | 20 proteinogenic L-amino acids plus glycine, **neutral** (carboxylic acid + amine, not zwitterion), expanded free molecules, not residues |
| `nucleobases` | titled Nucleic acids: free bases plus named ribo and 2'-deoxy nucleosides |
| `sugars` | named anomers (gluco, galacto, manno, xylo, ribo, fructo, 2-deoxyribo) with recorded ring form |
| `cycloalkanes` | C3–C12 monocycles except cyclopentane and cyclohexane (those stay in Rings), plus methylcyclopentane and methylcyclohexane |
| `heterocycles` | common heterocycles not already in Rings or Nucleic acids, including 12-/15-/18-crown-6 |
| `solvents_reagents` | water, common solvents, acetic acid, toluene |
| `alkaloids` | protoalkaloids (mescaline, hordenine), methylxanthines, and (1R,2S)-ephedrine; morphine-class stereoisomers stay in the research inventory |
| `flavonoids` | named aglycones and subclass parents |
| `vitamins` | named vitamers |
| `functional_groups` | phenol, aniline, benzaldehyde, and similar complete examples |
| `polycycles` | fused aromatics and cage hydrocarbons |
| `peptide_building_blocks` | Fmoc/Boc amino acids; not a sequence builder |
| `allotropes` | molecular allotropes (two Lewis drawings of O2, ozone, S6, S8, P4). Polymeric red P is not a template |
| `reactive_species` | superoxide, hydroxyl, hydrogen peroxide, NO, NO2, N2O |

`nucleobases` is titled **Nucleic acids** and holds free bases plus named nucleosides. Each molecule still has one `category_id`.

Singlet oxygen is the closed-shell drawing `O=O` (PubChem CID 977). Triplet oxygen is the diradical `[O][O]`. They share an InChIKey. PubChem name-search "singlet oxygen" is atomic oxygen CID 159832 and is not used. Full Lewis structure and the lone-pair overlay already refuse unpaired electrons on a main-group atom; calculator coverage for radicals is not this slice (the hypervalent opt-in in `ChemistryEngine` is the pattern for a later session).

A candidate is promoted only when PubChem identity is verified, `editor_eligible`
is true, and stereochemistry is `verified` or `not_applicable`, except named
nucleosides whose InChIKey still has to match the candidate. Coordination
compounds and morphine-class `stereochemistry_not_reviewed` identities stay listed, not shipped.

A dummy atom (`*`) is a wildcard in the molecule. Bonding to it does not
consume an attachment point. Fragments that need that behaviour are not
shipped until a real attach operation exists.

## Placement

Insert is **immediate**, not click-to-place. Incoming coordinates matter:
Ketcher's `addFragment` uses the molblock's positions (`tests/test_ketcher_editor_backend.py`
already offsets a second benzene so it does not merge).

- Occupied canvas: translate the template to the right of the current 2D
  bounds with a gap of **2.0 Å**. Internal geometry and stereo are kept. The
  existing drawing is not rewritten.
- Empty canvas: insert the template's own 2D coordinates through `addFragment`
  so the first insert is still one undoable edit.

## Insertion and undo

`EditorBackend.add_fragment(molblock, callback)` talks to
`window.ketcher.addFragment`. Qt's `runJavaScript` does not await promises, so
completion comes back through QWebChannel (`fragmentReady`), the same pattern
as `getMolfile`.

If the editor is not ready, the call is **refused** (a sentence on the
callback). It is not queued.

There is **no** `setMolecule` fallback. That is a document load;
`_loading_token` would suppress `edited` and skip undo.

One insert is one `EditStructureCommand`. Change events during the insert are
settled the same way a load is, then `edited` fires once.

Live canvas for **Add to My Templates** is `MoleculeEditorWidget.get_molblock`,
not `MoleculeModel.molblock`.

## User library

`data_root() / structure_templates / library.json`, version 1. Imports (JSON,
`.mol`, `.sdf`, a folder of those) are copied into that file. The original
path is provenance only.

Unsupported features (query atoms, S-groups, dummy atoms) are refused with a
named reason. A broken record does not empty the library. Writes are
temp-file then `os.replace`. Tests set `OPENCHEM_DATA_ROOT`.

## Not in this slice

Peptide sequence expansion (`Ala-Glu-Gly`), polymer S-groups, a pinned
category toolbar, nested subcategories, click-to-fuse attachment, Ketcher
“use as 2D clean template”, unpaired-electron calculator coverage.
