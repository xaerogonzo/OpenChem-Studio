# UV-Vis / TD-DFT benchmark

Answers one question ROADMAP.md left open: **does a range-separated hybrid
rescue UV-Vis?** That document records UV-Vis as measured and deliberately not
shipped, and names the untried lead in the same breath — "a range-separated
hybrid such as ωB97X-D is the more promising lead than any basis change, and
**has not been tried**."

It has now been tried. **It does not rescue it, and it makes band positions
worse.**

```bash
python benchmarks/uvvis/generate.py <scratch dir> --orca "D:\ORCA\orca.exe"
python benchmarks/uvvis/score.py <scratch dir>
```

## The criteria were pre-registered

Written into `reference.json` and `score.py` **before any job ran**, because
"+0.6 eV isn't terrible" is easy to conclude once you have seen +0.6 eV.

| criterion | threshold |
|---|---|
| **Position** | \|ΔE\| ≤ 0.30 eV on every scored band |
| **Strongest-band identity** | the brightest computed root is the transition `reference.json` **declares** strongest |
| **Intensity** | *f* within 2× of experiment; a **forbidden** band must come back below *f* = 0.01 |

Three criteria, never collapsed into one score — the recorded def2-SVP /
def2-SVPD pair is exactly why. One gets position wrong and intensity right,
the other the reverse, and any average reports them as comparable when the
whole question is which failure you are choosing.

## Result

Measured 2026-08-12, ORCA 6.1.1, geometries optimised once per molecule at
B3LYP/def2-SVP and shared by every arm, `nroots 15`.

| arm | position | identity | intensity | shippable |
|---|---|---|---|---|
| B3LYP/def2-SVP *(control)* | FAIL | PASS | FAIL | **FAIL** |
| ωB97X-D3/def2-SVP | FAIL | PASS | FAIL | **FAIL** |
| ωB97X-D3/def2-SVPD | FAIL | PASS | FAIL | **FAIL** |

**The carbonyls are fine everywhere and were never the problem.**
Formaldehyde's n→π\* lands at 4.075 / 4.104 / 4.079 eV against 4.07, acetone's
at 4.446 / 4.518 / 4.531 against 4.48 — every arm inside 0.05 eV, and every
arm correctly reports both as dark (*f* < 0.01 for a symmetry-forbidden band).

**Benzene is where it fails, and ωB97X-D moves it the wrong way:**

| benzene band | exp | B3LYP/SVP | ωB97X-D/SVP | ωB97X-D/SVPD |
|---|---|---|---|---|
| ¹B₂ᵤ | 4.90 | +0.59 | **+0.73** | +0.64 |
| ¹B₁ᵤ | 6.20 | +0.27 | **+0.40** | +0.26 |
| ¹E₁ᵤ | 6.94 | +0.98 | **+1.10** | +0.84 |

A range-separated hybrid blue-shifts valence π→π\* further, which is the
opposite of what was needed. The best position achieved for the strongest band
is ωB97X-D3/def2-SVPD at **+0.84 eV**, still nearly three times the criterion.

### The one genuinely new finding: ωB97X-D fixes what diffuse functions broke

ROADMAP records that adding diffuse functions to **B3LYP** halves the position
error and destroys the intensity — *f* collapsing 0.96 → 0.083, an order of
magnitude too weak, because low-lying Rydberg states mix with the valence
π→π\* and fragment its oscillator strength.

**That collapse does not happen with ωB97X-D.** With def2-SVPD it keeps
*f* = 0.993 per component and still identifies the right strongest band:

| | position of ¹E₁ᵤ | *f* (per component) | strongest band identified |
|---|---|---|---|
| B3LYP/def2-SVPD *(recorded)* | +0.49 | **0.083** | FAIL |
| ωB97X-D3/def2-SVPD *(measured here)* | +0.84 | **0.993** | PASS |

So the range-separated hybrid does what it is supposed to do — it stops
Rydberg contamination wrecking the intensity — and pays for it with a worse
position. **The two error modes still cannot be minimised by the same
setting**, which is the refusal ROADMAP already reached, now confirmed against
the functional that was supposed to resolve it rather than only against basis
sets.

### The roots guard was broken on purpose, and it holds

Asserting that a guard works is not testing it. Benzene's real 15-root
output was truncated to 8 roots — the exact shape of the recorded failure,
where the strongest band was simply outside the requested roots and the run
still produced plausible numbers:

| | ¹B₂ᵤ | ¹B₁ᵤ | ¹E₁ᵤ | strongest-band verdict |
|---|---|---|---|---|
| 15 roots | 5.493 | 6.469 | 7.918 | PASS |
| **8 roots** | 5.493 | 6.469 | **UNSCORABLE** — "rank 3 (x2) does not exist: only 2 roots carry the declared character" | **not scored** |

**And it refused on the RANK check, not the root-count check** — which is
the interesting part. At 8 roots the computed spectrum still reaches past
6.94 eV, so "the spectrum spans the reference energy" passes happily while
the band is absent. Root count alone would not have caught this; only
locating the transition by its declared orbital character does. Anyone
tempted to simplify that gate to a span test should re-read this row.

## Two open questions, both needing a source rather than a rerun

**1. The CONVENTION is settled; the reference VALUE is not, and it decides
the verdict.**

*Settled:* ¹E₁ᵤ is doubly degenerate and ORCA reports each component as its
own root (0.9606, 0.9607). An experimental *f* is obtained by integrating
**one absorption band**, and degenerate components lie at the same energy and
cannot be separated in that integral — so the band total is comparable, and
summing is right. The CASPT2 benzene literature corroborates it from the
other side: it reports **one** computed oscillator strength for the
degenerate E₁ᵤ *state* and compares it against **one** experimental number,
so both sides are band totals. ROADMAP's "f = 0.9607 against an experimental
≈0.9 — essentially correct" compared one component against a band total,
which is why it read as near-perfect agreement.

*Not settled:* the ≈0.9 has **no citation anywhere in this repository**, and
the value quoted as experimental alongside this exact energy set
(4.90/6.20/6.94/7.80) in that literature is **1.25**. The two straddle the
criterion:

| experimental *f* | vs computed ~1.92–2.00 | verdict |
|---|---|---|
| 0.9 | 2.1× | FAIL |
| **1.25** | **1.54×** | **PASS** |

So this band's intensity scores as **UNAVAILABLE**, and the arm-level
intensity verdict is unavailable with it. Reporting FAIL against a reference
whose provenance did not survive checking would blame the computation for a
defect in the reference — and I could not read the primary document, only
secondary reports of it, which is not a standard this benchmark should
accept for a number that flips its own answer.

**What would close it:** a primary source giving the gas-phase integrated
intensity of benzene's ¹E₁ᵤ band. Nothing else in the table depends on it —
position and strongest-band identity are unaffected, and both already fail.

**2. Pyridine's IDENTIFICATION was wrong and is fixed; its ENERGIES still
need a source.**
The first version declared `rank: 3` for the strong band, which locates the
B₂ᵤ-like π→π\* at 5.66 eV carrying *f* = 0.025 — not the intense band at all.
**The guard caught it** by reporting the strongest-band identity as FAIL
rather than scoring the wrong band quietly, which is what "identify by
declared orbital character, never by nearest energy" is for.

The rank structure was then measured across all three arms and is stable:

| rank | assignment | *f* |
|---|---|---|
| 1 | n→π\* ¹B₁ | ~0.006 |
| 2 | forbidden ¹A₂ | 0.000 |
| 3, 4 | B₂ᵤ / B₁ᵤ-like π→π\* | ~0.02–0.04 |
| **5, 6** | **E₁ᵤ-derived pair** | **~0.6–0.85 each** |

**Benzene's ¹E₁ᵤ is split here, and that needed a schema change.** The
nitrogen lowers the symmetry to C₂ᵥ and lifts the degeneracy — measured at
0.244 / 0.122 / 0.082 eV across the arms, all beyond the degeneracy
tolerance. It is still *one observed band* (the components overlap in a real
spectrum and an experimental *f* integrates both), so `require_degenerate:
false` sums them while refusing to pretend they are degenerate. Benzene keeps
the strict check, where D₆ₕ genuinely requires degeneracy and a split would be
a red flag. Which of ranks 5 and 6 is brighter **varies by arm**, so declaring
a single rank would have been fitting to one output.

With that fixed, pyridine corroborates benzene rather than confusing it:

| | n→π\* (exp 4.59) | strong π→π\* (exp ~7.0) | identity |
|---|---|---|---|
| B3LYP/def2-SVP | +0.21 | **+1.15** | PASS |
| ωB97X-D3/def2-SVP | +0.54 | **+1.27** | PASS |
| ωB97X-D3/def2-SVPD | +0.54 | **+1.04** | PASS |

Same shape as benzene — ωB97X-D worse than B3LYP at the same basis, and the
strong band ~1 eV too high everywhere.

**It stays `verified: false`.** The n→π\* at 4.59 eV is corroborated as an
experimental figure by an independent report, but the intense band's energy
(entered here as ~7.0) and every oscillator strength are still from no
document I have read. A primary source must supply the ¹B₁ origin, the
intense band's λ_max, and its integrated intensity.

**The rank rule is robust to the one ambiguity found while looking.** The
computation orders the two lowest states ¹B₁ then a dark state, while the
literature assignment of which of ¹A₂ and ¹B₂ comes second is not something
this could confirm. That ambiguity sits at ranks 2–3 and cannot move ranks 5
and 6, so the strong-band identification does not depend on resolving it —
checked rather than assumed, since a rank rule that quietly depended on a
disputed ordering would be exactly the fragile thing this benchmark refuses
elsewhere.

## Why this is not a shipped feature

No arm passes. Shipping would mean a default that is wrong for aromatics,
which is most of medicinal chemistry. `UvVisSpectrumResult` remains an
addition rather than a refactor whenever an arm does pass — which is what
makes deferring it safe.

## Notes for whoever runs this next

- **ORCA's own path must use native separators.** `subprocess.run(["D:/ORCA/
  orca.exe", ...])` aborts in `Startup` naming `orca_startup`, while
  `D:\ORCA\orca.exe` on the identical input terminates normally. ORCA derives
  its helper-binary directory from the path it was invoked with. Same
  mechanism as the known spaces-in-path failure, and it reads like a broken
  input file. A single-point job can survive it while an `Opt` of the same
  molecule does not, so a working probe does not clear the path.
- **ORCA prints FOUR blocks with identical row shapes** — absorption via
  electric dipole, absorption via velocity dipole, and two CD spectra. Only
  the first carries `fosc(D2)`; the CD blocks put rotatory strength in the
  same column. Parsing without bounding the block lets the last one win, which
  is how this scorer first reported a symmetry-forbidden band at *f* = 0.60
  when the real value on the same line of the same file was 0.000000029. It
  read as a dramatic functional difference and was a parser reading the wrong
  table.
- **The B3LYP arm is a control and must stay one.** It reproduces ROADMAP's
  recorded figures — 4.078 → 4.075 eV for formaldehyde, 4.444 → 4.446 for
  acetone, and benzene's ¹E₁ᵤ at 7.918 eV with *f* = 0.9607 to four decimals.
  If it stops reproducing them, the harness is wrong and no conclusion about
  any other arm is worth anything.
