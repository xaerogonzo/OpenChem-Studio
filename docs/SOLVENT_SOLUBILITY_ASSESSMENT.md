# Solubility in solvents other than water

**Status: assessed, foundation built, no non-aqueous number shipped.**

Requested as "solubility in other substances than water, such as acetic
acid, ethanol, a non polar solvent like hexane, similar to how NMR tables
can use different solvents". The analogy is exact — `RESIDUAL_SOLVENT_PEAKS`
in `src/openchem/chem/nmr_signals.py` really is a solvent-keyed table of
published values — and it is why the foundation looks the way it does.

## What was built

`Solvent` in `src/openchem/chem/solubility.py`, with `SOLVENTS` keyed by
name, and a `solvent` parameter on both solubility calculators. It offers
**Water only**. Anything else is refused by name rather than silently
answered with water's number, which would be a wrong answer wearing the
right label.

The record carries a key and a label and nothing else. It deliberately
does **not** carry Abraham coefficients or any other LSER machinery: only
water participates in a calculation today, so those fields would be
plumbing nothing reads, and this project has been bitten before by
machinery that looked wired up and was not (`apply_grid_shapes`, reachable
from no production code for a whole phase).

## What a second solvent actually needs

The defensible route is the **Abraham general solvation equation** (LSER):

    log P(solvent/water) = c + e·E + s·S + a·A + b·B + v·V
    log S(solvent) = log S(water) + log P(solvent/water)

The *solvent* side is not the problem — Abraham and co-workers have
published `c, e, s, a, b, v` for roughly ninety solvents, ethanol and
hexane among them. The blocker is the **solute descriptors**:

| descriptor | what it is | can we compute it? |
| --- | --- | --- |
| `V` | McGowan characteristic volume | **Yes.** Atomic volume sum minus 6.56 per bond. Fully deterministic from the structure. |
| `E` | excess molar refraction | **Approximately.** Derivable from Crippen molar refractivity, which RDKit already gives us. Needs validating against published `E` values before use. |
| `S` | dipolarity/polarizability | **No.** Needs the Platts fragment scheme or an equivalent trained model. |
| `A` | hydrogen-bond acidity | **No.** Same. |
| `B` | hydrogen-bond basicity | **No.** Same. |

Three of the five terms are unobtainable with what is in this project
today. Shipping ethanol or hexane without them would mean inventing the
numbers — the call already made against Miller polarizability, HLB and
TSEI, all of which were built and then deliberately not shipped because
they could not be validated.

## The alternative that was considered and not taken

**Hansen solubility parameters** (δD, δP, δH) are computable from group
contributions today, and published tables exist for common solvents. They
would give a *relative* miscibility or affinity ranking via the Hansen
distance Ra.

It is not shipped because it answers a different question. Ra is an
affinity score, not a solubility, and putting it beside a logS in mg/mL
would invite exactly the units-and-meaning confusion the solubility module
spends its whole docstring preventing. If it ships it should ship under
its own name, as solvent compatibility, and never as "solubility in
ethanol".

## What would close this

1. Obtain or implement the Platts fragment scheme for `S`, `A` and `B`,
   and validate the resulting descriptors against published Abraham values
   for a set of compounds nobody fitted them to.
2. Validate the `E`-from-molar-refractivity relation rather than assuming
   it.
3. Add the solvent coefficient table with a per-solvent citation, the same
   shape as `RESIDUAL_SOLVENT_PEAKS`.
4. Only then let `SOLVENTS` grow, and benchmark each new solvent
   separately — a model that works for ethanol is not thereby a model that
   works for hexane.

Until then the seam exists, is exercised by real code, and refuses
honestly.
