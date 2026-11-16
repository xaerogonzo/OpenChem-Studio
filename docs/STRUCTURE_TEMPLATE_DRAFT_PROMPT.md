# ChatGPT prompt: draft named complete-molecule templates

**Working path:** grow the catalog in-session with isomeric SMILES and `tools/template_draft_check.py`. ChatGPT is useful for *research* (which named molecules belong in a class, stereo caveats). Dumping hundreds of rows through a chat window is the slow path.

Paste the block below into ChatGPT only if you want a *short* research list of names, not a 40-row SMILES dump. Do **one batch per reply**. Save each reply as a JSON file and run `tools/template_draft_check.py` before anything is shipped.

This is **not** a PubChem name search. The model writes **isomeric SMILES**. The checker parses them, computes InChIKey, and optionally confirms that key against PubChem. Wrong English names were the expensive part of the first 200; do not look compounds up by name.

Do not copy the reference editor’s template list, this application’s 2D editor T-button library, or any other editor’s template list.

---

## Prompt (copy from here)

```
You are drafting complete-molecule entries for OpenChem Studio’s Template Library.

Goal: name a *short* class of public-chemistry molecules that are not already shipped (the catalog is already about 2000; mixed waves have stopped). You will emit NEW names only; do not dump a 40-row SMILES table unless asked.

What a row is
- One complete molecule (or a single-salt disconnected SMILES such as [Na+].CC(=O)[O-]).
- Fields: id, name, smiles, category_id, stereo_in_name (boolean), skip_if_unspecified (boolean), notes (short string, may be empty).
- smiles MUST be RDKit-readable isomeric SMILES. If the name implies stereochemistry, the SMILES MUST contain @ and/or / \. If you cannot write that stereo, OMIT the molecule and list it under "skipped" with reason "stereo_unspecified". Do not emit a stereo-free SMILES for a named stereoisomer.
- id: snake_case stem only (e.g. limonene, not terpenoids_steroids.limonene). ASCII, unique in this batch.
- category_id: exactly one of:
  rings, amino_acids, nucleobases, sugars, cycloalkanes, heterocycles,
  solvents_reagents, alkaloids, flavonoids, vitamins, functional_groups,
  polycycles, peptide_building_blocks, allotropes, reactive_species,
  cofactors, terpenoids_steroids
  Pick the best single shelf. Do not invent a new category_id.
- Amino acids: NEUTRAL carboxylic acid + amine, not zwitterion, not residues.
- No dummy atoms (*), no query atoms, no polymers, no SRU/SUP, no peptides-as-sequences, no metal complexes / organometallics / coordination compounds, no “R-group” fragments.

Hard bans
- Do not reproduce another molecular editor’s template catalog (the reference editor, this application’s T-button library, etc.).
- Do not guess a PubChem CID. Do not invent InChIKeys. Do not look the name up and paste a canonical (stereo-stripped) SMILES.
- If you are unsure of the isomeric SMILES, skip it.

This reply’s batch
THEME: <paste one theme from the list below>
COUNT: 40
EXCLUDE: I will paste a JSON array of already-shipped {id, name} objects after this prompt. Do not repeat those ids or those chemical identities (same common name or obvious synonym).

Output ONLY valid JSON, no markdown fences:
{
  "theme": "...",
  "entries": [ { "id": "", "name": "", "smiles": "", "category_id": "", "stereo_in_name": false, "skip_if_unspecified": false, "notes": "" } ],
  "skipped": [ { "name": "", "reason": "stereo_unspecified|unsure_smiles|already_listed|out_of_scope" } ]
}

Batch themes (I will send these one at a time; do this theme only):
1. laboratory solvents and common reagents (DMF, EtOAc, hexane, TFA, TEA, …)
2. functional-group examples (small named molecules: acetone is already a solvent — prefer new groups: nitrile, amide, ester, sulfone, …)
3. extra heterocycles not already shipped (indole is ok if not listed; skip pyridine/pyrrole/furan/thiophene if excluded)
4. fused aromatics / PAHs / simple cages
5. terpenes and common steroids (named stereoisomers only, with @ in SMILES)
6. flavonoids / polyphenols / simple natural aromatics
7. fatty acids and common lipids as complete molecules (oleic with cis double bond, etc.)
8. named nucleotides / cofactors beyond ATP and NAD+ (AMP, ADP, GTP, FAD, …) with sugar stereo
9. extra alkaloids / named drugs that are ordinary organic molecules (aspirin, paracetamol, ibuprofen) — no organometallics, no B12
10. extra sugars / glycosides as named anomers with stereo
11. dyes / indicators / common pigments as complete organics (indigo, fluorescein) — skip metal complexes
12. leftover well-known organics that are still missing from the shipped exclude list

After JSON: nothing else.
```

---

## How to run a batch here

Dump what is already shipped (paste that JSON into `EXCLUDE`):

```bash
uv run --no-sync python tools/template_draft_check.py exclude
```

Save ChatGPT’s reply as e.g. `docs/template_drafts/batch-01-solvents.json` (create the folder if needed; drafts are research, not `_SHIPPED_FILES`).

Check without the network:

```bash
uv run --no-sync python tools/template_draft_check.py check docs/template_drafts/batch-01-solvents.json
```

Optional checksum: PubChem **by InChIKey**, never by name (rate-limited):

```bash
uv run --no-sync python tools/template_draft_check.py check docs/template_drafts/batch-01-solvents.json --pubchem-key
```

A row is ready to consider for shipping only when the checker says `parse` ok, not a shipped duplicate, and either stereo is not implied by the name or the SMILES carries `@` / `/` / `\`. PubChem-by-key is a checksum that the structure exists; a title mismatch is a warning, not an auto-rename.

Do not add `docs/STRUCTURE_TEMPLATE_CANDIDATES.json` to `_SHIPPED_FILES`. Promotion is still a separate PR of shipped catalog JSON.
