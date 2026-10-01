"""A from-scratch atom-equivalent scheme for gas-phase DfH, calibrated on this app's own real ORCA
install (B3LYP/def2-SVP geometry optimizations, ORCA 6.1.1) rather than reproduced from a paper -- the
option `mathieu2018_apc`'s literature.toml entry flagged as "a real, unexplored option" for Track 3's
gas-phase-Hf gap, now actually run.

**Why this exists alongside `mathieu2018_apc`.** That module's combined route (its own gas-phase model
plus `keshavarz2010_sublimation`) was computed end-to-end and checked against real measured Klapoetke
values: REJECTED for RDX/HMX/PETN (HMX and PETN miss by 50-57 kJ/mol; RDX borderline). This module asks
whether OUR OWN ab initio route, calibrated directly rather than inherited from a 2671-compound fit that
never saw a nitramine specifically, does better.

**Method**: DfH(gas) = Etot(DFT, kJ/mol) + sum_atoms AtomEquivalent(element) -- the standard
Dewar/O'Connor-style scheme this app's own `orca_engine.py` docstrings already reference for AE1/AE2 (the
mathieu2018_apc paper's OWN atom-equivalent procedure, whose calibration constants are Supporting
Information, not held). AtomEquivalent(C/H/N/O) is fit here by ordinary least squares against a small
calibration set of real molecules with primary-source experimental gas DfH -- not copied from any paper.

**Calibration set and the finding that mattered**: a first fit on 6 small molecules (water, methane,
ammonia, benzene, methanol, nitromethane, methyl nitrate -- all Lange's Handbook Table 6.1/6.3) gave an
excellent SELF-consistent fit (residuals 0.5-11 kJ/mol) but, applied to RDX/HMX/PETN, missed the real
Klapoetke condensed-phase values by 71-141 kJ/mol -- worse than `mathieu2018_apc`'s literature route.
**The calibration set had zero nitramine chemistry** (nitromethane's N is bonded to carbon; methyl
nitrate's N is bonded to an ester oxygen; neither has RDX/HMX's ring-N-N(NO2) linkage). Adding ONE real
nitramine -- dimethylnitramine (CH3)2N-NO2, DfH(gas) = -5 +/- 1 kJ/mol, NIST WebBook (Matyushin, V'yunova,
Pepekin, Apin, 1971) -- and refitting all four atom equivalents from the resulting 7-point set changed the
picture substantially: RDX cleared the accuracy bar, HMX's error roughly halved, and PETN got WORSE.

**Two follow-ups, same investigation, different questions.**

1. *Was RDX/HMX's own starting conformer the problem?* A single ETKDGv3 embed (seed 0xC0FFEE, MMFF94
   pre-optimized) was used for every ORCA job, with no conformer search -- and MMFF94 ranked that RDX
   conformer 18th of 35 (7.25 kcal/mol = 30.3 kJ/mol above an 80-conformer search's own minimum) and
   HMX's 30th of 50 (15.90 kcal/mol = 66.5 kJ/mol above). Re-running ORCA's B3LYP/def2-SVP Opt from each
   molecule's MMFF94-global-minimum conformer instead: RDX's converged Etot moved by only -4.3 kJ/mol,
   nitropiperidine's by -1.8 kJ/mol, and HMX's by **+6.1 kJ/mol -- the "better" MMFF conformer converged
   to a HIGHER DFT energy**, not a lower one. **Conclusion: conformer choice is NOT the source of
   RDX/HMX's remaining error.** The large MMFF94 energy gaps do not translate to comparable DFT energy
   gaps after ORCA's own optimization -- expected, since a force-field ranking is not a DFT ranking, but
   worth having actually checked rather than assumed. The original single-seed Etot values are kept as
   the recorded result (below) for consistency with the rest of the calibration set, which was never
   re-checked this way.

2. *Does more calibration data, specifically more of the two chemistry classes that mattered, help?*
   Added a second nitramine -- 1-nitropiperidine (a 6-membered RING nitramine, structurally much closer
   to RDX's own ring than dimethylnitramine was), DfH(gas) = -44 +/- 3 kJ/mol, NIST WebBook (Matyushin et
   al. 1971, the same source series) -- and a second nitrate ester, ethyl nitrate, DfH(gas) = -155 +/- 3
   kJ/mol, NIST WebBook (Gray, Pratt, Larkin, 1956). Refitting on the resulting 9-point set:

    compound   6-fit    7-fit(+dimethylnitramine)   9-fit(+nitropiperidine,+ethyl_nitrate)   measured         best diff
    RDX         50.1        80.4                         82.9                               66.6 / 85.0      2.1 kJ/mol
    HMX         66.0        87.8                         91.0                               116.1            25.1 kJ/mol
    PETN       -482.0      -466.3                       -458.6                              -539.0           80.4 kJ/mol

   RDX improved again (now within 2.1 kJ/mol of Klapoetke's Table 9.6 value, comfortably inside the
   ~21 kJ/mol bar against both of its measured readings). HMX improved again but is still over the bar.
   **PETN got WORSE a second time, monotonically across all three fits (46.6 -> 72.7 -> 80.4 kJ/mol as
   more nitramine/nitrate-ester data was added)** -- despite ethyl nitrate being exactly the kind of
   additional nitrate-ester data the earlier writeup called for. A one-point fluke would not do this
   twice in the same direction. The more likely explanation: PETN's own structure (a quaternary carbon
   bearing FOUR -CH2-O-NO2 arms) is not well represented by methyl/ethyl nitrate's simple primary
   alkyl-nitrate chemistry, and a purely elemental atom-equivalent scheme has no way to encode that
   structural difference -- more data of the WRONG shape for PETN specifically cannot fix this, and did
   not.

**This is a real, useful, and still explicitly NOT a validated result.** Nine calibration compounds
fitting four free parameters is a real improvement over seven (five degrees of freedom, not three), and
RDX's result is now genuinely strong evidence, not a single lucky point. PETN's monotonically worsening
error across three independent refits is equally real evidence, in the other direction, that a single
per-element atom-equivalent scheme cannot generalize to its specific structural class without a nitrate
ester more like it (a branched/quaternary-carbon polyol nitrate, not a simple primary one) in the
calibration set -- the clear, now more specific, next step for anyone continuing this.

**RETRACTED 2026-09-29 (Track 4, Gate B): the "RDX clears the bar at 2.1 kJ/mol" conclusion above did
not survive a fresh, internally-consistent recomputation, and the recorded Etot values above were
never internally consistent to begin with.** Re-running HMX's exact documented recipe (this SMILES,
ETKDGv3 seed 0xC0FFEE, MMFF94 pre-optimize, B3LYP/def2-SVP opt) gave an Etot **108 kJ/mol** away from
the value recorded above -- an order of magnitude bigger than the already-ruled-out conformer-choice
effect (6.1 kJ/mol), and bigger than the entire ~25 kJ/mol HMX residual this whole module was built to
explain. Every one of the 12 CALIBRATION_SET/TARGET_ETOT_KJMOL entries showed the same one-directional
drift when re-run (fresh always higher-energy than recorded), scaling with molecular flexibility:
0.1-0.8 kJ/mol for the rigid small molecules (methane/ammonia/benzene), 3-13 kJ/mol for the mid-sized
nitro compounds, 45-108 kJ/mol for RDX/HMX/PETN. **Root cause**: `pyproject.toml` pinned RDKit as
`>=2024.3.1`, a floating lower bound, and `uv.lock`'s resolved RDKit version changed at least twice
across this multi-session survey -- ETKDGv3 is only deterministic for a given seed WITHIN one RDKit
build, so different sessions' "same seed 0xC0FFEE" embeds were silently landing on different starting
conformers, which converged to different DFT local minima. **The 6/7/9-fit progression's whole narrative
-- that adding nitramine-specific calibration data systematically helped RDX -- was built on that drift,
not on real signal**: every compound in the original table above was computed at a different, unrecorded
point in that drift, so the fit's apparent improvement conflated genuine calibration-chemistry signal
with environment noise of comparable or larger size. `pyproject.toml` is now pinned exact
(`rdkit==2025.9.6`) to prevent this recurring.

**All 9 calibration compounds plus RDX/HMX/PETN were re-run fresh, in one sitting, under the pinned
environment**, and the atom equivalents refit on the internally-consistent result:

    compound   6-fit    7-fit(+dimethylnitramine)   9-fit(+nitropiperidine,+ethyl_nitrate)   measured         best diff
    RDX         53.4       121.2                        123.4                               66.6 / 85.0      13.2 kJ/mol (6-fit)
    HMX         68.0       158.4                        161.3                               116.1            42.3 kJ/mol (7-fit)
    PETN       -479.5      -458.5                       -451.4                              -539.0           59.5 kJ/mol (6-fit)

**The qualitative conclusion is now the OPPOSITE of the original writeup for RDX**: under consistent
data, adding nitramine/nitrate-ester calibration chemistry makes RDX's combined-route error WORSE,
monotonically (13.2 -> 36.2 -> 38.4 kJ/mol), not better -- the untargeted 6-compound fit (no nitramine
data at all) is RDX's best available result, and it is the ONLY one of the three fits that still clears
SENSITIVITY.md's ~21 kJ/mol bar. HMX is non-monotonic (48.1 -> 42.3 -> 45.2 kJ/mol) and never clears the
bar in any fit. **PETN's finding is the one part of the original writeup that survives**: its error still
gets monotonically worse as nitramine/nitrate-ester data is added (59.5 -> 80.5 -> 87.6 kJ/mol), the same
direction as before, so that specific conclusion (a purely elemental atom-equivalent scheme cannot
represent PETN's four-arm quaternary-carbon structure without a matching calibration compound) was not
an artifact of the environment drift -- it reproduces under a consistent recomputation, unlike RDX's.

**This is now, honestly, a worse-performing route than it was reported to be**, and the reason to keep
this module rather than delete it is that the drift itself -- and PETN's surviving, now doubly-confirmed
finding -- are real results worth keeping on record. Any further work on this route (a higher level of
theory, more calibration data) must start from the fresh numbers below, and must re-run the ENTIRE
calibration set together in one sitting if it changes anything, never add one new compound to the
existing (already environment-drifted) numbers.

**Reproducibility note**: the ORCA total energies below are recorded from real jobs run on this machine
(ORCA 6.1.1, B3LYP/def2-SVP, RDKit 2025.9.6 -- now pinned exact in `pyproject.toml`) -- not re-run by the
test suite, the same way this project records a paper's own printed table values rather than re-deriving
them from source data it doesn't hold. All calibration compounds and RDX/HMX/PETN use the same single
ETKDGv3-seed-0xC0FFEE seed, re-embedded fresh in the current environment; only the conformer CHECK above
(RDX/HMX/nitropiperidine, from the original, now-superseded numbers) used a wider search, and its own
qualitative conclusion (conformer choice does not explain RDX/HMX's error) is unaffected by this
correction -- the 108 kJ/mol drift is roughly 4x that conformer study's own largest gap (30.3 kJ/mol,
MMFF-ranked) and was traced to the RDKit version, not to conformer choice within one version.

**Gate B diagnostic 2026-09-29: does a higher level of theory materially change HMX's residual?** Three
real ORCA jobs, HMX only, same ETKDGv3-seed-0xC0FFEE starting geometry as the fresh baseline above:

1. B3LYP/def2-SVP opt (reproduction check): Etot = -3137634.721 kJ/mol, diff = 0.000 kJ/mol from the
   fresh baseline recorded above -- confirms the RDKit pin fix makes this genuinely reproducible now.
2. PBE0/def2-TZVP single point AT THAT SAME GEOMETRY (isolates the electronic-level effect, no geometry
   relaxation): Etot = -3139558.995 kJ/mol, a **-1924.3 kJ/mol** shift from step 1 -- large.
3. PBE0/def2-TZVP full reoptimization from the same starting geometry (adds geometry relaxation on top):
   converged cleanly (ORCA's own "HURRAY", 38 cycles). Etot = -3139462.804 kJ/mol, **+96.2 kJ/mol** from
   step 2 (geometry relaxation moved the energy HIGHER, the opposite direction from the electronic-level
   shift, and small by comparison) -- total PBE0/TZVP shift from step 1: -1828.1 kJ/mol.

**This diagnostic alone does NOT answer whether the combined-route error improves at this level.** A
shift this large and this uniform-looking is exactly the kind of thing a refit of the atom equivalents
would absorb -- what matters for the actual residual is how HMX's shift compares to the OTHER
calibration compounds' shifts at the same level, not its raw magnitude in isolation. That requires
re-running the full 9-compound calibration set (plus RDX/PETN, for a like-for-like target comparison) at
PBE0/def2-TZVP and refitting -- not yet done, and a much larger compute commitment: this single HMX
reoptimization alone took over an hour and needed a raised timeout, and PBE0/def2-TZVP is dramatically
more expensive than B3LYP/def2-SVP per geometry cycle across the board, not just for HMX. Recorded here
as a real, useful, and explicitly partial result -- not a substitute for the full refit.

**Gate B, full refit 2026-09-30: the full commitment above, actually done.** All 12 compounds (the
9-point `CALIBRATION_SET` plus RDX/HMX/PETN) re-run fresh, full geometry optimization (not a single
point), at PBE0/def2-TZVP -- same ETKDGv3 seed 0xC0FFEE, MMFF94 pre-optimize, same SMILES as the
B3LYP/def2-SVP baseline above. `fit_population` (the 9 calibration compounds) and `target_population`
(RDX, HMX, PETN) stay disjoint, unchanged from the B3LYP/def2-SVP fit. The refit itself is a reasonable
fit (RMSE 6.3 kJ/mol, MAE 5.5 kJ/mol, max abs 12.8 kJ/mol on its own 9-compound calibration set --
comparable quality to the B3LYP/def2-SVP fit, so the new level of theory is not simply failing to
converge to a sane fit). The combined-route (gas - Hsub, same `keshavarz2010_sublimation` term, held
fixed) comparison against the existing B3LYP/def2-SVP 9-point fit:

    compound   B3LYP/def2-SVP (9-fit)   PBE0/def2-TZVP (9-fit)   measured    change
    RDX          38.4 kJ/mol               41.0 kJ/mol            85.0       +2.6 (worse)
    HMX          45.2 kJ/mol               53.7 kJ/mol            116.1      +8.5 (worse)
    PETN         87.6 kJ/mol               73.7 kJ/mol           -539.0     -13.9 (improved)

(RDX's two measured readings -- 66.6 and 85.0 -- both worsen at PBE0/def2-TZVP: 41.0 vs 85.0 is still the
smaller of the pair, so the same reading is used for both levels here.)

**Conclusion: a higher level of theory does NOT materially improve the combined-route error, and makes
it worse for two of the three targets.** RDX and HMX both get slightly worse at PBE0/def2-TZVP; PETN
improves by ~14 kJ/mol but remains 73.7 kJ/mol off -- still far outside any usable accuracy bar, and this
is the first improvement of any kind PETN has shown across every intervention tried in this survey
(conformer search, more calibration data, now level of theory), yet it does not change PETN's own
structural diagnosis (a quaternary-carbon four-arm nitrate ester an elemental atom-equivalent scheme
cannot represent) -- a ~74 kJ/mol error is not a validated result by any measure used elsewhere in this
module. **Level of theory is ruled out as the fix for RDX/HMX's residual, the same way conformer choice
was ruled out earlier** (see finding 1 above). `CALIBRATION_SET` and `TARGET_ETOT_KJMOL` below stay at
B3LYP/def2-SVP, the level this whole module's fit history is built on; the PBE0/def2-TZVP numbers are
not adopted as the module's data, only recorded here and in the paired locked-in test, since they do not
represent an improvement worth switching the whole calibration history over to.

**Gate C, 2026-09-30: a second multi-site ring nitramine, and a new PETN-topology target.** A literature
search for a compound closer to RDX's/HMX's own ring-N-NO2 chemistry than any single-site nitramine
already in the set found **1,4-dinitropiperazine** (a 6-membered ring bearing TWO N-NO2 groups, one on
each ring nitrogen) with a real NIST WebBook gas-phase DfH = 58 +/- 3 kJ/mol (Pepekin, Matyushin, Lebedev,
1974, Bull. Acad. Sci. USSR, Div. Chem. Sci., 1707-1710 -- the same primary-source series already behind
`dimethylnitramine`/`nitropiperidine`). Run through this module's own real-ORCA recipe (B3LYP/def2-SVP
opt, ETKDGv3 seed 0xC0FFEE, MMFF94 pre-optimize) and added to `CALIBRATION_SET` as a TENTH point. A
second search, for a branched/quaternary-carbon nitrate ester closer to PETN's own four-arm topology
than methyl/ethyl nitrate, again found no usable GAS-phase reference for the two most obvious plain
candidates (neopentyl nitrate has no thermochemistry on NIST WebBook at all; neopentyl glycol dinitrate
has only a solid-phase combustion enthalpy, no DfH and no sublimation/vaporization data) -- but found
**metriol trinitrate** (trimethylolethane trinitrate, MTN, CAS 3032-55-1): a real explosive, a
quaternary carbon bearing THREE -CH2-ONO2 arms plus one -CH3 (one arm short of PETN's own four), with a
real NIST WebBook SOLID-phase DfH = -450.2 kJ/mol (Tavernier, 1956, Mem. Poudres, 301-327). Since MTN
has no gas-phase reference value, it cannot be a `CALIBRATION_SET` fit point -- it becomes a new TARGET,
combined-route only, exactly the role PETN itself plays (added to `TARGET_ETOT_KJMOL` as `MTN`).

**The refit result is dramatic, and its mechanism was checked, not just accepted.** Refitting on the
10-point set (adding only dinitropiperazine; MTN is a target, never a fit point) barely moves the atom
equivalents themselves -- each element's fitted value shifts by only 2-7 kJ/mol from the 9-point fit --
and the fit quality on its own calibration set is essentially unchanged (RMSE 9.0 -> 9.6 kJ/mol, still a
normal range, dinitropiperazine's own residual a middling 7.2 kJ/mol, not a near-zero residual bought at
the expense of the other nine). The design matrix's condition number even improves slightly (13.6 ->
10.7), so this is not new collinearity or instability. What makes the DOWNSTREAM effect large is that
RDX and HMX are unusually nitrogen-rich (6 and 8 N atoms respectively) -- a few-kJ/mol shift in the
nitrogen atom equivalent alone multiplies into tens of kJ/mol for these two specific targets, which is
exactly the population dinitropiperazine's own N-NO2-ring-nitrogen environment was chosen to inform.
This is a real, understood mechanism, not an unexplained coincidence.

    compound   9-fit solid (kJ/mol)   10-fit solid (kJ/mol)   measured           9-fit err   10-fit err
    RDX          123.35                  87.24                 66.6 / 85.0        38.4         2.2 (best)
    HMX          161.32                 113.18                 116.1              45.2         2.9
    PETN        -451.45                -469.85                -539.0              87.6        69.2
    MTN (new)   -440.66 (9-fit)        -451.16 (10-fit)        -450.2               9.5          1.0

RDX and HMX both go from clearly failing SENSITIVITY.md's ~21 kJ/mol bar to clearing it by roughly an
order of magnitude. PETN improves but still fails badly. **MTN, evaluated as a genuinely new target
under BOTH the old 9-fit and the new 10-fit, is remarkably well predicted either way** (9.5 kJ/mol at
the 9-fit, 1.0 kJ/mol at the 10-fit) -- far better than PETN's own result at any fit tried in this
survey, consistent with this survey's own repeated finding that PETN's specific four-arm topology, not
nitrate-ester chemistry generally, is what an elemental atom-equivalent scheme cannot represent (MTN has
only three arms and is well predicted; PETN has four and is not).

**This is genuinely promising, and explicitly NOT yet a validated conclusion.** A single new calibration
compound moving RDX and HMX this far, even with a checked, sane mechanism behind it, is exactly the
shape of result this survey has learned not to trust from one point alone (PETN's own monotonic-worsening
finding was not treated as real until it reproduced across two independent refits under the RDKit-drift
correction). The next genuinely corroborating step is a SECOND multi-site ring nitramine (a 5-membered or
different-substitution-pattern analogue) -- not declaring RDX/HMX solved on this one addition, and even a
second compound reproducing the effect would corroborate it, not validate the four-parameter model in
general.

**Gate D, 2026-10-01: searched for that second compound -- a genuine, documented negative result, not a
silent dead end.** Checked every structurally plausible ring-dinitramine isomer this session could find a
CAS number for, against NIST WebBook directly (not just a search-snippet summary):

- `1,3-dinitroimidazolidine` / 1,3-dinitro-1,3-diazacyclopentane (CAS 5754-91-6, C3H6N4O4, a 5-membered
  ring): NIST WebBook lists only a melting point and enthalpy of fusion (Hall, 1971; Domalski & Hearing,
  1996) -- no gas-phase DfH, no combustion enthalpy, no sublimation/vaporization route to derive one.
- `1,3-dinitro-1,3-diazacyclohexane` (CAS 5754-89-2, C4H8N4O4 -- an isomer of `dinitropiperazine` itself,
  same formula, different N-substitution pattern (1,3 vs 1,4) -- structurally the single best candidate
  found, if it had data): NIST WebBook's free page shows no thermochemistry at all beyond noting
  subscription-only data exists.
- `1,3-dinitro-1,3-diazacycloheptane` (CAS 5754-90-5, C5H10N4O4, a 7-membered ring): same outcome --
  melting point and fusion enthalpy only, no formation enthalpy of any kind.
- Checked the primary source behind `dinitropiperazine` itself (Pepekin, Matyushin, Lebedev, 1974, Russ.
  Chem. Bull. 23, 1707-1710) directly, not just its NIST citation: this paper's own subject is
  N,N'-dinitropiperazine, N,N'-dinitrosopiperazine, and HMX's own sublimation enthalpy -- it does not
  contain a second ring nitramine at all, so there is no sibling compound to recover from this exact
  source.
- Checked a related 2009 follow-on paper from the same research group (Russ. Chem. Bull., indexed under
  Springer journal id s11172, "secondary nitramines and n-butyldinitramine" per its own abstract; full
  author list not confirmed, not held, not registered as a source here for that reason) by abstract: it
  covers ACYCLIC bis-nitramines, not a second ring compound.
- Searched Klapoetke's own textbook (`klapotke2017`, already held, the primary source for every
  RDX/HMX/PETN measured value this survey uses) by full-text search for any of the above compound names
  or "alicyclic"/"cyclic dinitramine" -- zero hits. It simply does not discuss this chemistry.

**Conclusion: no second multi-site ring nitramine with a usable gas-phase DfH was found after a genuinely
thorough search**, not a single quick check. Gate C's own result therefore remains uncorroborated by an
independent compound -- it stands exactly where it did at the end of Track 4: a real, mechanistically
understood, but still single-point-dependent finding. This is recorded as a completed negative search, not
an abandoned one, so a future session does not have to repeat the same four candidate lookups from
scratch.

**The secondary, PETN-topology search was equally thorough and equally negative.** Checked whether
`keshavarz2006`'s or `nazari2016`'s own validation tables (already held and read) cite a branched or
quaternary-carbon nitrate ester's primary GAS-phase value directly, independent of their own
unreproducible predictive equations -- full-text search of both PDFs for "neopentyl", "trimethylol",
"metriol", "pentaerythritol", "dinitrate", "trinitrate". `nazari2016`'s own Table 1 does list metriol
trinitrate (MTN, row 123, CAS 3032-55-1) -- but as a SOLID-phase value (425.0 kJ/mol via its own ref
[34], a different secondary citation than NIST's Tavernier-1956-sourced -450.2 kJ/mol already used in
this survey as MTN's target value) in a table that is entirely solid/liquid-phase throughout, the same
`direct_condensed_Hf` route as `keshavarz2006`/`nazari2016`'s own rejected equations -- not a gas-phase
value this survey's `CALIBRATION_SET` could use. No usable gas-phase branched-nitrate-ester calibration
point exists in either source. PETN's calibration-side gap (a purely elemental scheme cannot represent
its four-arm quaternary-carbon topology without a matching calibration compound) remains open and, on
this evidence, is not close to being closed by anything currently held or freely findable.

**CRITICAL CORRECTION 2026-10-01 (Track 5): a second environment bug, found while trying to validate
geometries, invalidates Gate B's and Gate C's specific numeric conclusions above.** `OrcaQuantumEngineProvider.parse_output`
(`src/openchem/chem/orca_engine.py`) extracted the SCF energy for an `opt`/`opt_freq` job with
`_SCF_ENERGY_RE.search(output_text)` -- the FIRST `FINAL SINGLE POINT ENERGY` line in the file. A real
multi-cycle geometry optimization prints one such line PER CYCLE, not once per job (RDX alone takes 28
cycles; HMX, 41). The first one is essentially the MMFF94-preoptimized starting geometry's single-point
energy, not the DFT-converged minimum at the end. This affected every `opt`/`opt_freq` job this survey
ever ran, not just the ones in this module -- see the paired fix (`fix-orca-opt-energy-last-cycle`
branch) and its own test for the general-application side of this.

**Discovered by direct measurement, not inference.** The real ORCA job output files from the 2026-09-29
re-run were still on disk (never cleaned up). Comparing their FIRST vs. LAST `FINAL SINGLE POINT ENERGY`
line against what this module had recorded confirmed the recorded value matched the FIRST, every time,
by 0.01 kJ/mol or better -- not a coincidence, a confirmed read of the wrong line:

    compound            cycles   recorded (WRONG, first)   corrected (converged, last)   gap
    methane                  3           -106206.299               -106206.511          -0.21
    ammonia                  5           -148269.955               -148270.089          -0.13
    benzene                  3           -608933.278               -608934.040          -0.76
    methanol                 7           -303413.897               -303417.841          -3.94
    nitromethane             8           -642474.368               -642477.667          -3.30
    methyl_nitrate           7           -839626.586               -839635.943          -9.36
    dimethylnitramine       15           -890629.381               -890642.613         -13.23
    nitropiperidine         10          -1196706.729              -1196717.876         -11.15
    ethyl_nitrate            7           -942707.230               -942717.306         -10.08
    dinitropiperazine       20          -1774984.380              -1775013.153         -28.77
    RDX                     28          -2353224.239              -2353293.377         -69.14
    HMX                     41          -3137634.721              -3137743.199        -108.48
    PETN                    29          -3452150.435              -3452195.164         -44.73
    MTN                     11          -2718768.897              -2718797.444         -28.55

The gap scales with how many cycles a molecule needs -- RDX/HMX/PETN (the targets the whole survey's
accuracy claims hinge on) are the most affected, which is exactly why this stayed hidden through Gates
B and C: the small calibration molecules barely moved.

**The corrected numbers, same recipe (B3LYP/def2-SVP, ETKDGv3 seed 0xC0FFEE, MMFF94 pre-optimize),
re-fit from these converged energies (no new ORCA jobs needed -- re-extracted from the existing files):**

    compound   6-fit    7-fit(+dimethylnitramine)   9-fit(+nitropiperidine,+ethyl_nitrate)   10-fit(+dinitropiperazine)   measured
    RDX        -4.37      80.40                        82.84                                   58.51                   66.6 / 85.0
    HMX       -25.27      87.76                        91.02                                   58.57                   116.1
    PETN     -492.46    -466.30                      -458.63                                 -471.03                  -539.0
    best diff  RDX: 89.4 (6-fit) / 4.6 (7-fit) / 2.2 (9-fit) / 8.1 (10-fit)
               HMX: 141.4 (6-fit) / 28.3 (7-fit) / 25.1 (9-fit) / 57.5 (10-fit)
              PETN: 46.5 (6-fit) / 72.7 (7-fit) / 80.4 (9-fit) / 68.0 (10-fit)

**Both of Track 4's specific gate conclusions reverse under the corrected data:**

- **Gate C's "second ring nitramine clears the bar for RDX/HMX" is RETRACTED.** Adding `dinitropiperazine`
  (9-fit -> 10-fit) makes HMX dramatically WORSE (25.1 -> 57.5 kJ/mol) and RDX somewhat worse against its
  best reading (2.2 -> 8.1 kJ/mol, though both still clear the bar). The dramatic improvement Gate C
  reported was an artifact of comparing numbers that were ALL still first-cycle energies at the time --
  internally consistent with each other, which is why it passed every sanity check available then, but
  built on the wrong physical quantity throughout. `dinitropiperazine` is removed from `CALIBRATION_SET`
  accordingly; its real, measured NIST value and real ORCA job remain valid data (recorded in
  `validation_rows_energetics.py`, partition changed from `development` to `selection` -- tested
  against, not fit on, since it does not currently earn a place in the fit).
- **Gate B's "a higher level of theory does not help" is ALSO RETRACTED -- in the opposite direction.**
  Re-extracting the PBE0/def2-TZVP full-refit data (same fix, same already-on-disk job files) gives a
  9-point PBE0/def2-TZVP fit of RDX 9.15 kJ/mol (vs. 85.0) and **HMX 3.02 kJ/mol** -- HMX's best result
  anywhere in this entire survey, by a wide margin, at a level of theory Gate B's own (wrong-data)
  diagnostic had concluded made things worse. PETN improves too (62.9 vs. the corrected B3LYP/def2-SVP
  9-fit's 80.4 kJ/mol) but still fails badly. The HMX-only electronic/geometry diagnostic also shifts:
  corrected step1=-3137743.199, step3=-3139566.070 (step2, a single point, has only one energy line and
  was never affected) -- electronic-only shift -1815.8 kJ/mol, geometry-relaxation shift -7.1 kJ/mol
  (previously computed as +96.2, the WRONG SIGN -- a geometry relaxation making the energy go up is
  physically backwards for a minimization and should have been a red flag at the time).

**What survives, unretracted: PETN's own structural diagnosis.** PETN's combined-route error stays in the
60-90 kJ/mol range across EVERY fit and EVERY level of theory tried, before and after this correction --
the one finding in this whole survey that was never sensitive to either bug. MTN (three arms, not four)
stays well-predicted throughout for the same reason (9.7 kJ/mol, 9-fit). This is now the most-confirmed
result in the module: PETN's four-arm quaternary-carbon topology, not an environment bug, is what an
elemental atom-equivalent scheme cannot represent.

**A striking, and only partially resolved, loose end: the corrected 9-fit numbers above (RDX 2.2, HMX
25.1, PETN 80.4 kJ/mol) are close to -- in RDX's case, nearly identical to -- the numbers Track 3 reported
BEFORE Gate B's 2026-09-29 "RDKit-drift" retraction (RDX 2.1, HMX 25.1, PETN 80.4 at the same 9-fit).**
That retraction concluded a floating RDKit version pin caused a 108 kJ/mol HMX discrepancy between
sessions. This correction does not re-litigate that diagnosis -- the RDKit pin stays exact, for good
reason independent of this bug -- but the closeness of these numbers raises a real possibility that this
SAME parser bug, not RDKit drift, was wholly or partly responsible for that original discrepancy, and the
RDKit-drift diagnosis may have been chasing a confound. This is recorded as an open question, not a
further claim: nobody has gone back and re-run the ORIGINAL (pre-drift-fix) RDKit version with the fixed
parser to check whether it, too, reproduces these numbers. Until that is done, both explanations should
be treated as live.

**Everything above (Gates B and C's own now-retracted numbers) is left in place rather than deleted,**
the same practice this module has followed since the first RDKit-drift retraction: the chronology,
including the wrong turns, is part of the record."""

from __future__ import annotations

import numpy as np

#: (element_counts as (C, H, N, O), Etot from a real ORCA B3LYP/def2-SVP `opt` job, kJ/mol,
#: experimental gas DfH, kJ/mol -- primary source noted per row).
#:
#: RE-EXTRACTED 2026-10-01 (Track 5): these are the CONVERGED (last-cycle) energies from the exact same
#: real ORCA job.out files already on disk from the 2026-09-29 re-run -- re-parsed with the fixed
#: `parse_output`, not re-computed, since the converged energy was always in the file. See the module
#: docstring's "CRITICAL CORRECTION 2026-10-01" section: every value here was, until this fix, the energy
#: of the FIRST optimization cycle (near the MMFF94-preoptimized starting geometry), not the converged
#: minimum -- a parser bug (`src/openchem/chem/orca_engine.py`), not an ORCA or RDKit problem.
#: `dinitropiperazine` (Track 4 Gate C) is deliberately NOT included here any more -- see that section
#: for why adding it no longer looks like an improvement once the energies are correct.
CALIBRATION_SET = {
    # Lange's Handbook Table 6.1 for all experimental values below. Water was run first as a pipeline
    # feasibility check but deliberately left out of the fit -- an inorganic, non-hydride-bonded-carbon
    # molecule pulls the O atom equivalent in a direction the fit's actual use case (organic/energetic
    # C,H,N,O compounds) does not need, and every number in this module's docstring and the paired tests
    # was computed on the 7-compound organic set below.
    "methane": ((1, 4, 0, 0), -106206.511, -74.6),
    "ammonia": ((0, 3, 1, 0), -148270.089, -45.9),
    "benzene": ((6, 6, 0, 0), -608934.040, 82.6),
    "methanol": ((1, 4, 0, 1), -303417.841, -201.0),
    "nitromethane": ((1, 3, 1, 2), -642477.667, -74.3),
    "methyl_nitrate": ((1, 3, 1, 3), -839635.943, -124.4),
    # NIST WebBook (Matyushin, V'yunova, Pepekin, Apin, 1971) -- two nitramines, one acyclic, one a
    # 6-membered ring (structurally close to RDX's own ring).
    "dimethylnitramine": ((2, 6, 2, 2), -890642.613, -5.0),
    "nitropiperidine": ((5, 10, 2, 2), -1196717.876, -44.0),
    # NIST WebBook (Gray, Pratt, Larkin, 1956) -- a second, simple primary nitrate ester.
    "ethyl_nitrate": ((2, 5, 1, 3), -942717.306, -155.0),
}

#: RDX, HMX, PETN, MTN Etot from the same real ORCA jobs -- no experimental gas-phase DfH exists to check
#: RDX/HMX/PETN against directly (they decompose before vaporizing); see the module docstring for how the
#: COMBINED (gas - Hsub) route was checked instead, against real condensed-phase measured values. MTN has
#: only a solid-phase measured value too (Track 4 Gate C). RE-EXTRACTED 2026-10-01 alongside
#: CALIBRATION_SET -- see that note; these are the converged (last-cycle) energies from the same job.out
#: files, not new ORCA jobs.
TARGET_ETOT_KJMOL = {
    "RDX": ((3, 6, 6, 6), -2353293.377),
    "HMX": ((4, 8, 8, 8), -3137743.199),
    "PETN": ((5, 8, 4, 12), -3452195.164),
    # Metriol trinitrate (MTN, trimethylolethane trinitrate) -- a quaternary carbon with THREE
    # -CH2-ONO2 arms plus one -CH3 (PETN has four arms, no methyl) -- added 2026-09-30, Track 4 Gate C.
    # No gas-phase reference exists (NIST WebBook gives only a solid-phase DfH), so MTN is a target,
    # never a CALIBRATION_SET fit point -- the same role PETN itself plays.
    "MTN": ((5, 9, 3, 9), -2718797.444),
}

ELEMENTS = ("C", "H", "N", "O")


def fit_atom_equivalents(calibration_set: dict[str, tuple[tuple[int, int, int, int], float, float]]) -> dict[str, float]:
    """Ordinary least squares: exp - Etot = sum_e counts[e] * AtomEquivalent[e]."""
    names = list(calibration_set)
    counts = np.array([calibration_set[n][0] for n in names], dtype=float)
    residual = np.array([calibration_set[n][2] - calibration_set[n][1] for n in names], dtype=float)
    fitted, _, _, _ = np.linalg.lstsq(counts, residual, rcond=None)
    return dict(zip(ELEMENTS, fitted))


def compute_gas_hf(counts: tuple[int, int, int, int], etot_kjmol: float, atom_equivalents: dict[str, float]) -> float:
    return etot_kjmol + sum(n * atom_equivalents[e] for n, e in zip(counts, ELEMENTS))
