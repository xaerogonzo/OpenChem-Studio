# Research records

What the thermophysical / density / enthalpy / detonation survey reads, and how each source is
recorded. Nothing here is a production calculator and nothing here promotes one: a method becomes a
calculator only after it has been compared with its alternatives on a common set, and the survey may
end in "not promoted".

## `literature.toml`

One `[[source]]` per paper. Two kinds of field, kept apart because they are different kinds of claim:

| Fields | What they are | Can they be wrong? |
|---|---|---|
| `printed.*` (DOI, title, venue) | what the paper says about itself, read from the file's own first page | yes, and a reader can check |
| `assigned.*` (property, role) | our reading of what the paper is for | it is a judgement, not evidence about the paper |

Rules the file follows, each learned the hard way in this project:

- **Identity comes from the file's text, never its name.** `file` is a locator in the maintainer's
  library. Two files named `gharagheizi2011*` are different papers (crystal lattice energy from the
  sublimation enthalpy, and the enthalpy of *fusion*), and one file opens on the tail of the *preceding*
  article.
- **A DOI that the paper does not print is left empty, not looked up and filled in.** Several older papers
  print a PII instead. A DOI copied from a citing paper is a claim nobody checked.
- **An access state is not a verdict.** A paper that is requested, or held only as an accepted manuscript,
  a pre-proof or a supplement, has not been rejected. There is deliberately no "rejected" state; a
  rejection is a scientific decision that records a reason, and a paywall is never one.
- **`sha256` says the file is still the one that was read**, nothing more.
- **This is an inventory, not the provenance registry.** A paper moves into `docs/sources.toml` (with a
  `used_by`, a verification level and the number it backs) the day something we ship is built from it; until
  then it is read, not cited. `tests/test_sources_are_current.py` skips this one file for that reason and no
  other, and still checks any OTHER file that cites one of these DOIs.
- **Nothing is redistributed.** The papers are not in this repository. Open-access papers still carry
  their own licences; check before transcribing any table (a Creative Commons licence printed in a paper
  is recorded in its note, and only there).
- **Counts are generated.** `python tools/index_literature.py --counts` prints them; no document quotes a
  hand-typed number of papers.

`OPENCHEM_PDF_LIBRARY=<folder> python tools/index_literature.py --check` verifies every held file against
its hash, and says so plainly when there is no library to check against.

## The four density-type quantities

The survey keeps four things apart that the literature often blurs: the **measured crystal density** a
source reports, a **predicted crystal density** (a method's output, with its temperature basis), a
**loading density** (how a particular charge was made, supplied by a person or a source), and a
**theoretical maximum density** (an explicitly declared reference-state assumption). A predicted crystal
density is never a loading density.

## `SENSITIVITY.md`

How errors in the two inputs the detonation calculator cannot estimate (a loading density and a condensed
enthalpy of formation) move its estimate, with the tool that computes it and a worked example. One compound,
said plainly: a claim about a set waits for the set.

## `tools/validation_rows.py`

The row schema and the leakage rule, before any method is compared. A validation row carries its property, value,
units, source, record id, partition (development, selection or holdout -- three, never two) and its **reference
temperature and phase**; a row without those stays out of the common evaluation set, and `admit_to_common_set` says
why. Leakage is judged on chemical identity (the first block of the InChIKey), **per model and per property**, and a
(model, property) with no recorded fit population is an *error*, not "no leakage": an unenumerated population is
unknown, and unknown must never read as clean.
