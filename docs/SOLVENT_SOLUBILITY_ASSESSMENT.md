# Solubility in solvents other than water

**Status: assessed against the primary sources, one descriptor solved and
shipped, the rest blocked — and the block is not where the first version
of this document said it was.**

Requested as "solubility in other substances than water, such as acetic
acid, ethanol, a non polar solvent like hexane, similar to how NMR tables
can use different solvents". The analogy is exact —
`RESIDUAL_SOLVENT_PEAKS` in `src/openchem/chem/nmr_signals.py` really is a
solvent-keyed table of published values — and it is why the foundation
looks the way it does.

## What is built

`Solvent` in `src/openchem/chem/solubility.py`, with `SOLVENTS` keyed by
name, and a `solvent` parameter on both solubility calculators. It offers
**Water only**, and anything else is refused by name rather than silently
answered with water's number.

`mcgowan_volume()` is shipped and is a real descriptor row in the
Properties panel. It is the Abraham solute volume `V`, and it is exact:
atomic volumes summed over every atom including hydrogens, minus 6.56 per
bond. Validated to four decimals against eight published values.

## The route, and where it actually stops

    log S(solvent) = log S(water) + log P(solvent/water)
    log P(solvent/water) = c + e·E + s·S + a·A + b·B + v·V

### The solute descriptors

| descriptor | status |
| --- | --- |
| `V` McGowan volume | **Solved and shipped.** Exact, validated, no parameters. |
| `E` excess molar refraction | **The textbook relation was tried and FAILS.** See below. |
| `S` dipolarity/polarizability | Needs the Platts fragment table. |
| `A` H-bond acidity | Needs the Platts fragment table. |
| `B` H-bond basicity | Needs the Platts fragment table. |

**The `E` claim in the previous version of this document was wrong, and a
measurement killed it.** It said `E` was "derivable from Crippen molar
refractivity" via `MR/10 − 2.83195·Vx + 0.52553`. Hexane *is* the alkane
reference, so its `E` is 0.000 by definition — that relation returns
**0.805** on Crippen's MR scale, and water returns 0.413 against 0.000.
A least-squares refit of the same two inputs reaches about 0.12 RMSE on
thirteen compounds, but it was fitted on them, so that figure is
optimistic and n=13 establishes nothing. `E` needs a **validated refit**,
not the textbook relation.
`test_the_textbook_excess_molar_refraction_relation_does_not_work_here`
pins that so the claim cannot drift back.

**`S`, `A` and `B` need the Platts group-contribution tables**, which are
now in hand: Platts, Butina, Abraham & Hersey 1999
([10.1021/ci980339t](https://doi.org/10.1021/ci980339t)). Table 2 gives
all 81 fragment definitions in full, so Klopman's original paper is *not*
required — that was a worry and it is resolved. Table 4 carries their
coefficients and Table 5 a separate 51-fragment set for H-bond acidity.
Roughly 480 coefficients and ~132 SMARTS patterns in total.

Two caveats on that transcription. Fragments 59–67 are intramolecular
hydrogen-bond types defined in **Figure 1**, not in text, so they cannot
be read out of the PDF's text layer. And every fragment is a SMARTS
judgement call, which is exactly where silent errors live.

### The solvent coefficients — the harder block

**Neither ethanol, hexane, nor acetic acid is in these papers.** Part 2
([10.1021/ci990427t](https://doi.org/10.1021/ci990427t)) parameterises
**octanol, cyclohexane and chloroform** and nothing else. The general
Abraham coefficient table for ~90 solvents lives elsewhere; the free UFZ
LSER database is the obvious source and needs no paywalled paper.

So the two halves are blocked independently: the solute side needs a
large, error-prone transcription, and the solvent side needs a source
that is not in these papers at all.

## The error budget, which is the reason to hesitate

Part 2 reports its own accuracy plainly: r² 0.8–0.9 and **RMS 0.7–1.0 log
unit** for the partition step, with the best octanol equation at RMS
0.674 over n=8844.

Stacked on the aqueous baseline this app already has — ESOL at RMSE
1.26 on the SC-2 tight set — a non-aqueous solubility would carry roughly

    sqrt(1.26² + 0.67²) ≈ 1.4 log units

which is a factor of about 25. For comparison, the interlaboratory noise
floor on high-quality aqueous data is 0.17 log.

That is the number to weigh against roughly 480 transcribed coefficients
and 132 hand-written SMARTS patterns, every one a place for a silent
error.

## The alternative that was considered and not taken

**Hansen solubility parameters** (δD, δP, δH) are computable from group
contributions today, with published tables for common solvents. They give
a *relative* miscibility ranking via the Hansen distance Ra.

Not shipped, because it answers a different question. Ra is an affinity
score, not a solubility, and putting it beside a logS in mg/mL would
invite exactly the units-and-meaning confusion the solubility module
spends its docstring preventing. If it ships it should ship under its own
name, as solvent compatibility, and never as "solubility in ethanol".

## What would close this

1. Obtain the Abraham **solvent** coefficients for the solvents actually
   wanted — the UFZ LSER database is free and is the first place to look.
   Without this the solute side is worth nothing.
2. Transcribe the Platts fragment tables for `S`, `A`, `B`, and read
   Figure 1 for fragments 59–67.
3. Establish a validated refit for `E`, or take it from the fragments too.
4. Validate the descriptors against published Abraham values for
   compounds nobody fitted them to, then benchmark each new solvent
   separately — a model that works for ethanol is not thereby a model that
   works for hexane.

Until then the seam exists, `V` is real, and the refusal is honest.
