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

**Every reference value is sourced** — see "Where the numbers come from"
below. Nothing here is scored against a figure whose provenance is unknown.

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

## Where the numbers come from

Both open values were sourced on 2026-08-12, and the one that was in doubt
turned out to be the one that had been there all along.

**Benzene's ¹E₁ᵤ oscillator strength: 0.90.** This was marked `unsourced`
with candidates 0.9 and 1.25, because a web summary attributed **1.25** to
the CASPT2 benzene study — and the two straddle the 2× criterion, so the
verdict for that band turned on which was right.

**The 1.25 is not in that paper.** Reading Lorentzon, Malmqvist, Fülscher and
Roos (*Theor. Chim. Acta* **91** (1995) 91–108,
[doi:10.1007/BF01113865](https://doi.org/10.1007/BF01113865)), the string does
not occur anywhere in it. What it says is that the experimental values are
*"scattered in the range 0.6–1.05"*, that its own graphical integration gives
**0.80**, and that the 0.80 *includes the A₂ᵤ Rydberg band*. Refusing to write
1.25 into the reference on a search summary is the only reason this did not
become a **wrong number with a citation attached**, which is worse than an
unsourced one because it stops looking like a question.

Bolovinos et al. (*J. Mol. Spectrosc.* **103** (1984) 240–256,
[doi:10.1016/0022-2852(84)90051-1](https://doi.org/10.1016/0022-2852(84)90051-1))
gives the direct absolute measurements, Tables I and III:

| | | measured |
|---|---|---|
| benzene | ¹B₂ᵤ | *f* = 0.0013 |
| benzene | ¹B₁ᵤ | 6.19 eV, *f* = 0.090 |
| benzene | ¹E₁ᵤ | 6.96 eV, **f = 0.90** |
| pyridine | n→π* ¹B₁ | 4.59 eV, *f* = 0.003 |
| pyridine | ¹B₂ᵤ-like | 4.99 eV, *f* = 0.029 |
| pyridine | ¹B₁ᵤ-like | 6.38 eV, *f* = 0.085 |
| pyridine | ¹E₁ᵤ-like | **7.22 eV**, *f* = 0.90 |

So **ROADMAP's uncited ≈0.9 was right all along**, and benzene's ¹E₁ᵤ
intensity is a real **FAIL at 2.13–2.23×** rather than an unscorable.

### Three things the papers settled that had been decided on reasoning

All three held, which is worth recording since the alternative was to find
out they had not.

- **Summing the split components is right.** Bolovinos reports pyridine's
  E₁ᵤ-derived bands *"do not show any splitting due to the lifting of the
  ¹E₁ᵤ degeneracy"* — experiment sees **one band** where the computation
  resolves two. That is exactly what `require_degenerate: false` encodes, and
  it was chosen from symmetry before there was a measurement to check it
  against.
- **Pyridine's strong band is 7.22 eV, not the ~7.0 that was guessed.** That
  moved its error from +1.04…+1.27 to **+0.82…+1.05** — onto benzene's
  +0.84…+1.10 rather than merely near it. Pyridine is now a genuine second
  aromatic case rather than a provisional one.
- **¹B₁ᵤ is measured at *f* = 0.090 and the computation is still right to
  return 0.** It is forbidden in D₆ₕ and borrows its intensity vibronically,
  which a *vertical* calculation at a fixed geometry cannot produce by
  construction. Scoring the computed 0.0000 against 0.090 would fail the
  computation for a limitation of the approximation rather than for being
  wrong, so the criterion stays "must come back dark" and the measurement is
  recorded beside it.

### The one band it gets too WEAK

Everything else the computation overestimates. Pyridine's ¹B₁ᵤ-like band is
the exception, at **0.26–0.36×** of measured (0.022–0.031 against 0.085) —
worth knowing, because a spectrum with that band too faint is wrong in the
opposite direction from every other error here.

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
