# Periodic EQeq: feasibility (round 3, Track 6)

Written 2026-09-15. **This is a feasibility record only.** No periodic charge
code exists or is written here. `git diff master -- src/` is empty on this
branch.

**Outcome: BLOCKED as first written; REVISED TO FEASIBLE the same evening —
see section 8.** The accompanying files arrived after this was written, so the
paragraph below records what was true when the check ran, and section 8 records
what changed. Originally blocked on source data that is not held:
- the 2012 accompanying files: the 12 MOF structures with their charges, the
  ionisation table, and the v1.00 source;
- a disorder-resolution rule, which is missing from the input path.

Section 6 names what would unblock each.

## 1. What was read

`wilmer2012.pdf` (6 pp) and `wilmer2012_si.pdf` (24 pp), from their text
layers and from renders of SI pp. 3, 4, 10 and 15 and paper p. 2. The text
layer garbles every equation, so every equation below comes from a render.

## 2. EQeq's electrostatics, as printed

**Atom energy.** The Taylor series is centred on a charge Q\* (SI eq 58):

  E_A(Q) = E_A(Q\*) + χ_Q\*(Q − Q\*) + ½ J_Q\*(Q − Q\*)²

where:
- χ_Q\* = (I_Q\*+1 + I_Q\*)/2 and J_Q\* = I_Q\*+1 − I_Q\* (paper eqs 2–3; SI eq 57);
- I_n is the n-th ionisation energy, and I_0 is the electron affinity.

**System energy** (SI eq 59), non-periodic form:

  E_Sys = Σ_k [ E_A(Q\*_k) + χ_Q\*(Q_k − Q\*_k) + ½ J_Q\*(Q_k − Q\*_k)² + ½ Σ_m≠k K Q_k Q_m / r_km + ½ Σ_m≠k E_Okm ]

- K = 1/(4π ε_R ε_0), which is 8.6225 eV·Å at ε_R = 1.67.
- Charges minimise E_Sys subject to Σ Q_k = Q_T, with Q_T = 0 in the periodic
  case (SI eqs 18–21), by one linear solve.

**Periodic Coulomb term** (SI eqs 13–15), in two forms:
- **Direct summation:** Σ over u, v, w from −L to L, Σ over m ≠ k\*, of
  K Q_k Q_m / r_km, applied if r_km < r_cut.
- **Ewald summation:** the same triple sum of K Q_k Q_m E_Wr(r_km) if
  r_km < r_cut, minus Σ_m K Q_m² / (η√π), plus the triple sum of
  K Q_k Q_m E_Wh(h_km) if h_km < h_cut.

The pieces are:
- r_km = |r⃗_km + u a⃗ + v b⃗ + w c⃗|;
- h_km = |h⃗_km + u a⃗⁻¹ + v b⃗⁻¹ + w c⃗⁻¹|;
- "m ≠ k\*" skips m = k only in the home cell.

The two Ewald terms (SI eqs 16–17):
- E_Wr(r) = erfc(r/η) / r
- E_Wh(h) = (4π/Ω) · exp(−(hη/2)²) · cos(h⃗·r⃗) / h²

**Orbital overlap term** (SI eq 64), with no extra parameter:

  E_Ok = Σ_m K Q_k Q_m · exp(−(J_km r_km / K)²) · (J_km/K − J_km² r_km / K² − 1/r_km)

where J_km is the geometric mean of the two atoms' hardnesses. SI p. 3 says
direct summation within a cutoff of "several angstroms" suffices for it.

**Inputs used for the 12 MOFs** (paper p. 3; SI S3, p. 15):
- no spherical cutoffs, L = 2 (5 × 5 × 5 cells), η = 50 Å, ε_R = 1.67 (2/ε_R = 1.2);
- hydrogen's I_0 set to −2 eV (measured +0.754 eV);
- charge centres neutral, except the metals at their oxidation states (Mg +2,
  V +4, Co +2, Ni +2, Cu +2, Zn +2, Pd +2).

The paper reports that charges changed "only negligibly" from 5 × 5 × 5 to
7 × 7 × 7 cells, where Ewald and direct summation were identical.

**Inconsistencies and open conventions, recorded and not resolved:**
1. **The starting ε_R.** SI S3 says a starting ε_R = 1.5 was found by trial
   and error. Figure S3.1's axis, 2/ε_R, runs only from 1.10 to 1.26, and
   2/1.5 = 1.33 is off it. So the scan did not include its own starting
   point.
2. **The 2π convention of a⃗⁻¹ is not stated,** and at η = 50 Å it decides
   whether the reciprocal sum contributes at all. On a hypothetical 26 Å cubic
   cell (computed 2026-09-15):
   - with h = 1/a, the first shell's factor exp(−(hη/2)²) is 0.397;
   - with h = 2π/a, it is 1.4e-16;
   - and erfc(r/η) is still 0.46 at r = 26 Å.

   So either the reciprocal term matters, or the "Ewald" result is a damped
   direct sum plus a self term. The printed equations cannot say which.
3. **The reciprocal term is written over pair vectors h⃗_km** with a shell sum
   over reciprocal vectors. This is not the standard structure-factor form.
   It is transcribed as printed and must be read against the v1.00 source
   before it is implemented.

## 3. Oracle table

| Item | Where the paper puts it | Held? | Status |
|---|---|---|---|
| Ionisation energies, Z ≤ 84 | `ionizationData.dat` (SI p. 1, accompanying file); SI S2 shows it only as plots | no | external required, or substitutable (see below) |
| EQeq v1.00 source | `EQeq_v1_00.cpp` (SI p. 1). **S8 prints no listing**: it is one paragraph pointing at the file | no | external required |
| 12 MOF structures (CIF) | `partialQs_12MOFs_REPEAT_ChelpG_EQeq_Qeq.zip` | no | external required |
| Per-atom EQeq, REPEAT, ChelpG and AMS Qeq charges | the same zip (S5 is a one-line pointer to it) | no | external required |
| Per-MOF mean \|Q − Q_REPEAT\| | paper Table 2 (EQeq 0.11–0.24) | yes | an aggregate only, not a per-atom oracle |
| Timings, atom counts per cell | paper Table 1 | yes | a count checksum on any recovered structure |

**Structures, classified:**
- **Exact source structure:** none held.
- **Reconstructable from source:** none. Table 1's references are the
  synthesis papers, not deposited files.
- **External required:** all 12, through the ACS supporting-information zip.
- A CoRE-MOF or CSD structure of the same framework would be an independent
  substitute, never Wilmer's structure.

**The ionisation table is the one substitutable item.** SI S2 cites its two
sources: Andersen & Haugen 1999 (electron affinities, J. Phys. Chem. Ref. Data
28, 1511) and Moore 1970 (ionisation potentials, NSRDS-NBS 34). A table built
from those is an independent reconstruction, not Wilmer's file, and any
difference would move the charges; it would have to be labelled that way and
checked against SI S2's plots.

**numat/EQeq**, checked 2026-09-15 with GitHub metadata only, nothing
downloaded:
- archived as "DEPRECATED"; GitHub reports GPL-2.0;
- `main.cpp` carries author credits and no licence header;
- it adds features the 2012 paper does not have (Ewald parameter
  auto-optimisation, JSON output, a Python wrapper), so it is a later fork,
  not the v1.00 code;
- its `ionizationdata.dat` and `IRMOF-1.cif` are not demonstrated to equal the
  2012 accompanying files.

GPL-2.0 code is not vendored into this GPL-3.0-or-later repository in any
case. Running it externally, in scratch, needs Alex's permission.

## 4. Parser capability, kept apart from source fidelity

A readable CIF does not prove the structure is Wilmer's. This section
describes what `chem/cif.py` and `Crystal.expand()` do with a CIF, measured
on master 62e2c18 against the six committed COD fixtures.

**Probe:** fractional-coordinate duplicates within 1e-4 modulo 1, plus the
minimum-image Cartesian distance over all pairs. The script is not
committed; it is reproduced in section 7.

| COD id | sites | ops | special-position sites | expanded | within 1e-3 of a face | duplicates, same site | coincident, different sites | min distance |
|---|---|---|---|---|---|---|---|---|
| 1004002 | 238 | 2 | 0 | 476 | 2 | 0 | 0 | 0.490 Å |
| 1502211 | 186 | 8 | 0 | 1488 | 4 | 0 | 0 | 0.338 Å |
| 1504676 | 30 | 2 | 0 | 60 | 0 | 0 | 0 | 0.949 Å |
| 1511792 | 61 | 4 | 0 | 244 | 0 | 0 | 4 | 0.000 Å |
| 1569411 | 20 | 4 | 1 | 78 | 0 | 0 | 0 | 0.979 Å |
| 7717378 | 120 | 2 | 0 | 240 | 4 | 0 | 0 | 0.210 Å |

**What it shows:**
- **Expansion and wrapping duplicate no atom.** The special-position site
  gives 78 atoms (19 × 4 + 2), and atoms on cell faces are not doubled.
- **Every pair closer than 0.7 Å is a disorder alternative.** Checked per
  pair, none has both atoms fully occupied:
  - 1511792's four coincident pairs are N2 (0.897) with N2′ (0.103);
  - the others are partial-occupancy alternatives such as C514/C524
    (0.746/0.254) and O3/O3\* (0.418/0.582).
- **Disorder is carried only as occupancy.** `_atom_site_disorder_group`
  (present in four of the six fixtures) is not read; `cif.py` lists disorder
  groups among the tags it keeps as unhandled.
- **So a charge equilibration fed `expand()` directly** would place charges on
  both alternatives, including two at 0 Å.
- **A disorder-resolution rule is required input, not a parser bug.** Its
  possible forms are one group, the major occupant, or occupancy-weighted
  sites. It is also a scientific choice, and it belongs in the identity.

## 5. Future identity fields

A periodic charge result's identity must carry all of these; the molecular
result store's identity is not reused as is:
- **cell:** cell vectors a⃗, b⃗, c⃗ (Å), and periodicity/dimensionality (3D, or
  a slab or wire with its vacuum axis);
- **atoms:** fractional coordinates, in the canonical atom order they define;
- **images:** the periodic-image and wrapping convention (the `_wrap`
  tolerance, 1e-5 in fractional units today);
- **composition:** the occupancy and disorder-resolution rule (section 4), and
  the total cell charge Q_T (zero for Ewald without a neutralising background);
- **summation:** direct or Ewald; L, r_cut, h_cut and η, with the reciprocal
  2π convention; or a Wolf/DSF damping and cutoff;
- **boundary:** tin-foil or vacuum, the surface term;
- **charge centres:** the per-element Q\* table, with its source;
- **model:** ε_R, hydrogen's I_0, the ionisation table's checksum, and the
  orbital-term form.

## 6. Unblocking, and what stays open

**Unblocking conditions:**
- **The ACS accompanying files.** They are at https://doi.org/10.1021/jz3008485
  under Supporting Information. The paper's own names:
  - `partialQs_12MOFs_REPEAT_ChelpG_EQeq_Qeq.zip`
  - `ionizationData.dat`
  - `EQeq_v1_00.cpp`

  Saved into Sci Downloads as a folder `wilmer2012_si/` beside
  `wilmer2012_si.pdf`, they would move every "external required" row to held.
- **Then, and before any implementation:**
  - open question 2 is read against `EQeq_v1_00.cpp`;
  - a disorder rule is pre-registered;
  - Table 1's atom counts are checked against the recovered CIFs.

**Ewald against Wolf** stays a future scientific comparison. It is not chosen
here: EQeq's own published setting (η = 50 Å, L = 2) is the reproduction
target, and a Wolf sum would be an application choice with its own oracle.

**Outcome (as first written):** BLOCKED, universal status BLOCKED. **Superseded
by section 8:** the structures and their per-atom charges are now held, and the
outcome is FEASIBLE with the parameter table as a named substitution. Either
way it stops at feasibility, per the plan.

## 7. Probe script (as run)

```python
import itertools, math, pathlib, sys
from openchem.chem.cif import read_cif
def frac_close(a, b, tol):
    return all(min(abs(x - y) % 1.0, 1.0 - abs(x - y) % 1.0) < tol for x, y in zip(a, b))
for path in sorted(pathlib.Path(sys.argv[1]).glob("*.cif")):
    crystal = read_cif(path.read_text(encoding="utf-8", errors="replace"))
    atoms = crystal.expand()
    special = sum(1 for s in crystal.sites
                  if len({tuple(round(v % 1.0, 6) for v in op.apply(s.position)) for op in crystal.operations}) < len(crystal.operations))
    same = cross = 0; min_cart = math.inf
    for a, b in itertools.combinations(atoms, 2):
        if frac_close(a.position, b.position, 1e-4):
            same += a.site_label == b.site_label; cross += a.site_label != b.site_label
        d = [((x - y + 0.5) % 1.0) - 0.5 for x, y in zip(a.position, b.position)]
        min_cart = min(min_cart, math.dist((0, 0, 0), crystal.lattice.to_cartesian(*d)))
    print(path.name, len(crystal.sites), len(crystal.operations), special, len(atoms), same, cross, round(min_cart, 3))
```

## 8. Update, 2026-09-15 evening: the accompanying files arrived

Alex fetched the ACS supporting information and reorganised it, so most of
section 6's unblocking condition is met. **Everything above this section is
left as written**; this section says what changed.

**What is held now**, at `Sci Downloads/wilmer2012_si/`:
- `jz3008485_si_001.pdf` — the supporting-information PDF (the file this
  document calls `wilmer2012_si.pdf` above), under its publisher name;
- `jz3008485_si_002/CrystalStructuresWithCharges/` — **48 structure files**,
  12 MOFs × 4 charge sets (EQeq, REPEAT, ChelpG, AMSQeq);
- `jz3008485_si_002/2012_Mar21_JPCLett_EQeq_AllIsothermsData_Submitted.xlsx` —
  the simulated and experimental CO2 isotherms, per MOF, one column per charge
  scheme (REPEAT, EQeq, AMS, ChelpG, experiment, and the no-charge cases), in
  excess mg/g against pressure. Read from the sheet itself, not inferred from
  its name.

**Their format**, read rather than assumed. Despite the `.mol` extension these
are not MDL molfiles; they are the RASPA-style listing the EQeq code emits:

    Molecule_name: hypotheticalMOF
      Coord_Info: Listed Cartesian None
          424                                  <- atom count
       1  7.5791  5.3369  5.3369  Mof_Zn  1.211  0  0   <- index, x, y, z, label, CHARGE
       ...
          90.0000  90.0000  90.0000            <- cell angles, at the END of the file
          0.00000  0.00000  0.00000            <- origin
          25.8320  25.8320  25.8320            <- cell lengths

So each file carries the **unit cell and the per-atom charges together**, which
is exactly what section 5's identity fields need.

**Two checksums, measured on the EQeq set (2026-09-15):**

| MOF | atoms | paper Table 1 | Σq | cell (Å) |
|---|---|---|---|---|
| HKUST-1 | 624 | 624 | −0.0000 | 26.3430³ |
| Pd(2-pymo)₂ | 252 | 252 | +0.0000 | 16.3418³ |
| IRMOF-1 | 424 | 424 | +0.0000 | 25.8320³ |
| IRMOF-3 | 472 | 472 | −0.0000 | 25.7465³ |
| Zn-MOF-74 | 162 | 162 | +0.0000 | 25.9322, 25.9322, 6.8365 |
| Ni-MOF-74 | 162 | 162 | +0.0000 | 25.7856, 25.7856, 6.7701 |
| Co-MOF-74 | 162 | 162 | −0.0000 | 25.8850, 25.8850, 6.8058 |
| Mg-MOF-74 | 162 | 162 | −0.0000 | 25.8765, 25.8765, 6.7856 |
| ZIF-8 | 276 | 276 | −0.0000 | 16.9910³ |
| MIL-47 | 72 | 72 | −0.0000 | 6.8179, 16.1430, 13.9390 |
| UMCM-150 | 354 | 354 | −0.0000 | 18.3532, 18.3532, 40.6670 |
| UMCM-150(N₂) | 330 | 330 | +0.0000 | 18.4456, 18.4456, 39.5369 |

**All 12 atom counts match the paper's Table 1 exactly**, and every EQeq charge
set sums to zero as a periodic cell must. That is the corpus identified, not
merely a set of files with plausible names.

**What is still NOT held:** `ionizationData.dat` (the ionisation and
electron-affinity table the method runs on) and `EQeq_v1_00.cpp`. Neither is in
the ACS package; the SI's first page lists them as accompanying files, and S8
points at the source rather than printing it.

**Revised oracle table:**

| Item | Held? | Status |
|---|---|---|
| 12 MOF structures with cells | **yes** | exact source structures |
| Per-atom EQeq, REPEAT, ChelpG, AMS Qeq charges | **yes** | **an exact per-atom oracle** |
| Adsorption isotherms | **yes** | context for the paper's Figure 3 |
| Ionisation/electron-affinity table | no | external required, or **substitutable** (section 3) |
| EQeq v1.00 source | no | external required |

**Revised outcome: FEASIBLE, with one named substitution.** A periodic EQeq
implementation can now be tested against the source's own charges on the
source's own structures. What it cannot yet do is use the source's own
parameter table: that would have to be rebuilt from the two references SI S2
cites (Andersen & Haugen 1999; Moore 1970), and **any such table is an
independent reconstruction and must be labelled one** — a per-atom mismatch
would then have two candidate causes, the implementation and the table, which
is precisely the ambiguity a pre-registration has to settle in advance.

**Still open, unchanged by the new files:** section 2's two conventions (the
2π convention at η = 50 Å, and the pair-vector form of the reciprocal sum) and
section 4's disorder rule. The structures here are ordered and fully occupied,
so the disorder question does not arise for *this* corpus — it returns the
moment any other CIF is used.

**This does not start an implementation.** Track 6 was scoped to feasibility,
and shipping periodic charges needs its own pre-registration, which would now
have a real oracle to state.
