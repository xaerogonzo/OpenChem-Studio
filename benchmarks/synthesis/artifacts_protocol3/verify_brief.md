# Brief: independently verify a transcribed synthesis route against its paper

## What this is for

Another reader transcribed ONE reference synthesis route from each paper below into JSON (`refs_out/<stem>.json`). A retrosynthesis planner will be tested on whether it finds exactly these routes, so a wrong reactant, a wrong product or a wrongly credited "commercial" starting material would silently ruin a test case. You are the second, independent reader. **Be sceptical: your job is to find errors, not to agree.** You have no web access. Sources are plain-text files extracted from the PDFs (the text layer holds names, procedures and scheme captions but not the drawn structures):

`C:/Users/pmpd/AppData/Local/Temp/claude/D--Random-Projects-OpenChem-Studio--claude-worktrees-exciting-wilbur-8a3fc1/a5a67dd7-e684-45a7-abb4-eb89a528414c/scratchpad/`
- `readbundle/<stem>.main.txt` the article, `readbundle/<stem>.si.txt` its SI if present
- `refs_out/<stem>.json` the transcription under test

The files are long: do not read them whole. Use Grep and Read with offset/limit.

## For each paper, in this order

1. **Lead first, blind.** Before opening the JSON, read the title and abstract and decide the lead compound by this rule: (1) the compound the abstract or title names as best/most potent/optimised/lead/featured; (2) if none, the compound used for the main follow-up experiment; (3) if neither, there is no lead. Write down your choice. THEN open the JSON and compare with its `lead`. (Co-named compounds: either is acceptable, say so.)
2. **Reaction by reaction.** For every reaction in `reactions`: find its procedure in the paper or SI. Check (a) the listed reactants are what the procedure uses (including that every molecule incorporated is listed, and listed twice if two equivalents are incorporated), (b) the product is what the procedure makes, (c) nothing listed is a base, solvent, catalyst or protecting-group reagent that supplies no atom, (d) the reaction really is one step in the paper's own numbering. Read the SMILES yourself against the printed name and the described structure; flag any ring, substituent position, stereocentre or salt/free-base error.
3. **Leaves.** For every reactant with origin `commercial`, find the sentence that supports it ("commercially available", "purchased", a supplier statement, or no preparation anywhere and the general statement that reagents were bought). Flag any leaf the paper itself makes, isolates from a natural source, or cites to another paper ("as previously reported").
4. **Step count.** Count the reactions the paper needs from commercial materials to the target. It must be 4 or fewer for the route to stand.
5. **Is the target the lead, in the form the paper isolates it** (free base vs salt does not matter; racemate vs enantiomer does)?

## Output: one JSON file per paper, written with the Write tool

Path: `.../scratchpad/refs_verify/<stem>.json` (same directory as above).

```json
{
 "paper": "<stem>",
 "my_lead": "label you chose blind, and one phrase of why",
 "lead_agrees": true | false | "co-named",
 "reactions": [{"step": 1, "ok": true | false, "issue": "" }],
 "leaf_issues": ["..."],
 "step_count_ok": true | false,
 "smiles_issues": ["..."],
 "overall": "confirmed" | "minor_issues" | "reject",
 "notes": "what a maintainer must know; quote the supporting sentence for anything you could not confirm"
}
```
`confirmed` = every point holds. `minor_issues` = the route stands but something should be edited or flagged (say what). `reject` = the route is wrong or not supportable from the paper (say why).

## Final message

One line per paper: `<stem> | confirmed|minor_issues|reject | <few words>`; then at most three lines of anything else. No other text.
