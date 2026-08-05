# ESP benchmark — ab initio vs point charges, on the same conformer

Scores what `chem/cube.py` reads from a real `orca_plot` run against the
point-charge potential `chem/scalar_field.py` has been computing all along,
**on the same conformer and the same grid**.

```bash
python benchmarks/esp/generate.py <work dir>   # real ORCA, ~10 min for the set
python benchmarks/esp/score.py    <work dir>   # seconds
```

B3LYP/def2-SVP, the same level as `benchmarks/ir/`. Surface points are
those within ±25 % of the 0.002 e/Bohr³ isodensity surface — Bader's
definition, and the one essentially every published ESP map uses. Whole-grid
statistics would be dominated by the region near the nuclei, where the
potential is enormous, both methods are meaningless, and nothing is ever
rendered.

## Why agreement alone would prove nothing

Two methods that both put negative potential near oxygen will correlate
whatever their shape, so a high `r` is a sanity check, not a result. The
result is the **specific disagreement**, at exactly the two features
`scalar_field.py`'s docstring names.

## 1. Gross agreement — the sanity check

| molecule | n surface points | r |
|---|---|---|
| water | 1342 | **+0.990** |
| benzene | 2772 | +0.978 |
| methane | 1753 | +0.909 |
| fluorobenzene | 2715 | +0.800 |
| chlorobenzene | 2959 | +0.939 |
| bromobenzene | 3230 | +0.906 |

The two methods agree on gross polarity everywhere. Point charges are not
a bad model of a molecular ESP; they are a model that misses two specific
things.

## 2. The sigma hole — a sign change point charges cannot produce

ESP on the halogen's own surface patch, binned by angle from the C–X bond
axis extended beyond the halogen. 0° is the sigma hole; 90° is the
equatorial belt.

| | 0–30° (cap) | 60–90° (belt) | cap − belt |
|---|---|---|---|
| **fluorobenzene** QM | −16.32 | −12.29 | **−4.03** |
| **chlorobenzene** QM | +2.36 | −11.50 | **+13.85** |
| **bromobenzene** QM | **+10.35** | **−11.10** | **+21.46** |
| bromobenzene point charge | −5.69 | −4.45 | −1.24 |

kcal/(mol·e).

**Bromobenzene's QM potential changes SIGN around a single atom** —
positive along the bond axis, negative around the belt, 21.5 kcal/mol
apart. The point-charge model puts one charge on that bromine, so its
potential around that atom is monotonic in distance and **cannot** change
sign with angle. It reports the bromine as uniformly negative, which is
exactly the failure the docstring predicted.

### The falsifiable part, and it held

A sigma hole is not a quirk of bromine — it is a periodic trend, and it
should deepen F < Cl < Br. Measured: **−4.03 → +13.85 → +21.46**,
monotonic. And **fluorobenzene has no sigma hole at all** (the cap is
*more* negative than the belt), which is the textbook exception: fluorine
is the one halogen that does not act as a halogen-bond donor. Three
molecules were run in place of the one the plan asked for precisely so
this could come out wrong, and it did not.

## 3. Water's lone pairs — the two methods trend in opposite directions

ESP on the oxygen's surface, on the side away from the hydrogens, binned
by angle out of the H–O–H plane. The lone pairs sit above and below that
plane.

| out-of-plane angle | QM | point charge |
|---|---|---|
| 0–15° | −30.02 | −21.39 |
| 15–30° | −32.14 | −21.24 |
| 30–45° | −34.09 | −20.44 |
| 45–60° | −34.92 | −18.94 |
| 60–90° | **−35.14** | **−17.75** |

The QM potential gets **more** negative out of plane (−30.0 → −35.1),
finding the lone pairs. The point-charge potential gets **less** negative
(−21.4 → −17.8). They do not merely differ in magnitude: they run in
**opposite directions**, so the point-charge surface points a hydrogen-bond
acceptor site in the wrong place.

## What this licenses, and what it does not

It licenses removing the flat "no lone-pair directionality or sigma holes"
caveat from README.md *for the ab initio path*, and it is cited there. It
does **not** license removing it from the point-charge path, which is still
the default, is still instant, and still has both limitations exactly as
described — which is why the app shows the two side by side and labels
each with its method rather than replacing one with the other.

Everything here is one method and one basis on six small molecules. It is
evidence that the QM path reads real structure the point-charge path
cannot, not a general accuracy claim about either.
