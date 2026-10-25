# Brief: transcribe one reference synthesis route per paper

## What this is for

OpenChem Studio has a retrosynthesis planner (AiZynthFinder). We are testing whether it finds the SAME route a real paper reports, for compounds from journal papers published after the planner's training data. For each paper in your list you write down the paper's own synthesis of ONE compound as structured data. A program then checks your transcription (SMILES parse, atoms, OPSIN name-to-structure agreement) and runs the planner. A transcription that is wrong but plausible-looking ruins the test, so **accuracy matters more than coverage: when you are not sure, exclude the paper and say why.** Never guess a structure, a reagent or a step.

You have NO web access and need none. Your sources are plain-text files (extracted from the PDFs; the text layer holds names, procedures, scheme captions and conditions but NOT the drawn structures):

- `D:/.../scratchpad/readbundle/<stem>.main.txt` the article
- `D:/.../scratchpad/readbundle/<stem>.si.txt` its supporting information, if there is one

(The directory is `C:/Users/pmpd/AppData/Local/Temp/claude/D--Random-Projects-OpenChem-Studio--claude-worktrees-exciting-wilbur-8a3fc1/a5a67dd7-e684-45a7-abb4-eb89a528414c/scratchpad/readbundle/`.) The files are long: do NOT read them whole. Read the first ~6000 characters (title, abstract), then use Grep to find "Scheme", "Chemistry", "General procedure", "Experimental", "Synthesis of" and read those parts with offset and limit. Skip the biology.

## Step 1: choose the ONE compound (the lead rule; apply it exactly)

1. The compound the abstract (or title) names as the best, most potent, optimised, lead or featured compound.
2. If the abstract names none: the compound the paper uses for its main follow-up experiment (in vivo, docking highlight, mechanism).
3. If still none: decision = `excluded`, reason `no_lead_identifiable`.

Do NOT swap to a different compound because its route is shorter or clearer. The lead rule is fixed so the sample is not cherry-picked.

## Step 2: write its complete route from commercial starting materials

- **Leaves** (starting materials) are molecules the paper buys ("commercially available", "purchased", from a supplier) or uses without any preparation, plus ordinary reagents. A molecule the paper prepares, with a procedure in the article or SI, is an **intermediate** and its preparation is a step. "Prepared as previously reported [ref]" with no procedure in this paper = the route is **not explicit**: exclude with `route_not_explicit`.
- **Steps**: every reaction in the sequence counts, including deprotections, hydrolyses and the preparation of an isolated, characterised reagent. A convergent route counts every reaction in every branch. A one-pot sequence the paper reports as one procedure is one step. **If the total is more than 4 reactions, decision = `excluded`, reason `lead_route_over_4_steps`** (give the count). Steps shared by a general procedure ("General procedure B") each count once per use.
- **Reactants of a reaction**: list every molecule that supplies at least one non-hydrogen atom to the product's structure (the other building block, MeI, an acyl chloride, SOCl2 when its Cl is installed, NaNO2 when its nitrogen is installed, CO2, formaldehyde). Do NOT list hydrides, H2, catalysts, bases, acids, solvents, oxidants and reductants that leave no atom, protecting-group removal reagents. Mark an atom-supplying small reagent with `"origin": "reagent"`, a building block `"commercial"`, an intermediate made in this route `"made_here"`. Put the conditions (reagents, solvent, temperature, time) in the `conditions` text.
- **Names and SMILES for every molecule**: `name` = the name as PRINTED in the paper (experimental heading or SI), or "" if the paper gives none (then derive the structure from the text description and say so in `notes`); `smiles` = a SMILES you write carefully, with stereochemistry only where the paper states it. A program converts each printed name with OPSIN and compares it with your SMILES, so a mistyped ring or a wrong substituent position will be caught and flagged; take the care anyway. Check atom balance for every step (the product's heavy atoms must come from the listed reactants plus listed reagents).
- If the paper offers two reasonable readings (for instance an acid chloride made in situ or isolated), give the main one in `reactions` and the other in `alt_variants` (a list of complete reaction lists).
- Radiolabelling (18F, 11C), peptides, proteins, oligonucleotides, polymers, antibody or vaccine conjugates, metal complexes, organometallic or inorganic compounds, reviews and papers with no synthesis: decision = `excluded`, reason `not_small_molecule_organic` (name the kind) or `no_synthesis_in_paper`.

## Step 3: also record, for excluded papers only

`other_qualifying_compounds`: labels (up to 5) of OTHER compounds in the same paper whose complete route would be explicit and 4 steps or fewer. Do not transcribe them; just list labels, or [] if none, or null if you did not look. (This only tells us how much a looser rule would add.)

## Lessons from the first pass over 125 papers (apply them)

- If two equivalents of one molecule are incorporated into the product (a symmetric double substitution, an anhydride from two acids, a bis-alkylation), list that molecule TWICE in `reactants`. A program checks carbon balance and will flag a route that lists it once.
- A starting material the authors ISOLATE from a plant, lichen, bark or other natural source is not purchased: the route is `route_not_explicit` (the isolation is not a described step).
- A starting material the paper makes with a citation but no procedure ("as previously reported [ref]") makes the route `route_not_explicit`, even when the reactants of that step are named.
- A counter-ion or salt form (HCl, TFA) is not part of the structure compared: write the free base; do not list HCl as a reactant for a salt formation.
- A separation (chiral HPLC, recrystallisation, chromatography) is not a reaction and does not count as a step. If the lead is a single enantiomer obtained only by separation, the reference is the racemate (set the target to the racemate and say so in `notes`).
- When the paper prints its own contradictory descriptions of the lead's route (one step in the text, three in a scheme caption), exclude as `route_not_explicit`.
- Some files here are preprints or accepted manuscripts; they may lack the SI. If a needed procedure lives only in an SI that is not in the bundle, exclude as `route_not_explicit` and say which SI is missing.
- A reactant inferred from a product name (not printed anywhere as a name or a procedure) is allowed only when the product name leaves no doubt; say so in `notes`. If in doubt, exclude.
- For process or methodology papers (OPRD, catalysis) the lead is the model product or the target API the abstract names; if the paper reports a multi-step manufacturing route, count every step.

## Output: one JSON file per paper, written with the Write tool

Path: `C:/Users/pmpd/AppData/Local/Temp/claude/D--Random-Projects-OpenChem-Studio--claude-worktrees-exciting-wilbur-8a3fc1/a5a67dd7-e684-45a7-abb4-eb89a528414c/scratchpad/refs_out/<stem>.json` (create nothing else; `<stem>` is the file name without `.pdf`).

```json
{
 "paper": "<stem>",
 "decision": "route" | "excluded",
 "exclusion_reason": null | "no_lead_identifiable" | "lead_route_over_4_steps" | "route_not_explicit" | "not_small_molecule_organic" | "no_synthesis_in_paper",
 "exclusion_detail": "one or two sentences",
 "lead": {"label": "compound number or name", "why": "the sentence of the abstract / paper that names it"},
 "target": {"name": "name as printed", "smiles": "..."},
 "reactions": [
   {"step": 1,
    "product": {"label": "...", "name": "...", "smiles": "..."},
    "reactants": [{"label": "...", "name": "...", "smiles": "...", "origin": "commercial|made_here|reagent"}],
    "conditions": "...",
    "source": "where in the paper: section or page, and SI file if used"}
 ],
 "alt_variants": [],
 "other_qualifying_compounds": null,
 "notes": "anything a reviewer should know: a name you had to derive, an inconsistency in the paper, a step you are unsure of"
}
```

For an excluded paper, `target`, `reactions` may be null or [] but `lead`, `exclusion_reason` and `exclusion_detail` must be filled.

## Final message

Reply with ONE line per paper: `<stem> | route, N steps | lead <label>` or `<stem> | excluded: <reason> | <few words>`, then at most three lines of anything you want checked. No other text. The JSON files are the deliverable.
