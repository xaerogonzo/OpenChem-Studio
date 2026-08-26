# Report-line parser sweep

The evidence base for changing either string parser. It exists because
those two parsers judge free-text lines written across 59 calculators,
so "which lines does this change affect" is not answerable by reading
the producers — and reading them is how a regression ships.

```bash
uv run --no-sync python benchmarks/report_lines/sweep.py
uv run --no-sync python benchmarks/report_lines/sweep.py --refused
uv run --no-sync python benchmarks/report_lines/sweep.py --candidate '[-+]?\d+(?:[.,]\d+)*'
```

Roughly two minutes — it embeds ten molecules and runs every in-process
calculator over each. Current population: **484 distinct lines**, of
which `chem/report_adapter._MEASUREMENT` refuses 76 and
`chem/result_reduction.parse_reported_numbers` accepts 56 as numeric
batch columns.

## The two parsers are not interchangeable

They look like duplicates and are not, which is why the sweep reports
both rather than picking one.

| | `report_adapter._MEASUREMENT` | `result_reduction.parse_reported_numbers` |
| --- | --- | --- |
| job | recover a label so the row reads like every other row | decide whether a batch column is numeric |
| output | strings, formatting preserved | a `float` |
| a line it cannot split | still becomes a `Fact`, whole | is simply absent |
| `"Pi system: 10 atoms, 10 pi electrons"` | label + display text | **refused** — a column of atom counts headed "Pi system" is worse than none |

So the presentation parser is deliberately the looser of the two. Do not
"align" them by making one call the other; the numeric one is allowed to
refuse things the presentation one must still show.

## Why it exists — the measurement that changed a decision

Fixing `"Dipole Z: +0.16 Debye"` (the parser accepted a leading minus and
not a leading plus), the first candidate added a `(?=\s|$)` boundary so a
comma-separated value list could not mis-split. It is the obvious fix and
the sweep refused it:

    candidate: [-+]?\d+(?:[.,]\d+)*(?:[eE][-+]?\d+)?(?=\s|$)
      newly REFUSED  : 36
        5   Orbital energies (beta): +2.00, ...   <- the intent
        31  C: 23.79%   Percent buried volume: 13.30%

Elemental analysis and percent buried volume attach their unit directly
to the digits, so requiring whitespace after a number refuses both
calculators outright. **A newly refused line is not automatically a
regression and not automatically the intent** — the exit code only tells
you to look.

Run backwards, the sweep also reproduces the bug it was built for: the
pre-fix pattern refuses exactly the 18 lines that differ from an accepted
one by nothing but a `+` sign.

```bash
uv run --no-sync python benchmarks/report_lines/sweep.py --candidate='-?\d[\d.,eE+-]*' --quiet
```

## What it does not cover

**Only `bootstrap.CALCULATOR_DEFINITIONS`** — every in-process
calculator. The discovery-only `ServiceExecution` entries in
`bootstrap._EXTERNAL_CALCULATOR_DEFINITIONS` (Docking, Quantum Chemistry)
are driven by their own panels and emit lines this script never sees, so
a parser change touching those needs separate evidence.

`molecules.json` is chosen for **parser** coverage, not chemistry, and
every entry records which line shapes it is there to produce — so a later
edit can tell a deliberate case from a decorative one. Two-letter element
symbols, a positive Hückel HOMO and a long orbital-energy list are each
there because a specific parser branch depends on them. The embedding
seed is pinned so a diff between two sweeps is readable; a SMILES that
fails to parse is a hard error rather than a skip, because a silently
dropped molecule silently removes coverage.
