# EEM and QEq through Open Babel: what was measured before building

Step 5a of the "EEM and QEq on the stored conformer" plan (ROADMAP, "Next
up"). The plan had findings committed whatever they showed, and a stop rule
fixed before measuring. **The stop rule fired for QEq.** EEM passed it, but
its parameter file only partly matches the paper it is labelled with.
Nothing in the application changed.

```bash
uv run --no-sync python benchmarks/charges/datadir_arms.py
uv run --no-sync python benchmarks/charges/oracle.py eem,qeq
uv run --no-sync python benchmarks/charges/oracle.py eem2015ha,eem2015hm,eem2015hn,eem2015ba,eem2015bm,eem2015bn
uv run --no-sync python benchmarks/charges/eem_parameters_vs_bultinck.py
```

Open Babel runs in a child process (`openbabel_child.py`) every time, because
one arm crashes the interpreter. Measured 2026-09-14 on Windows with
openbabel-wheel 3.1.1.23 (module 3.1.0). The installed `eem.txt` and `qeq.txt`
equal Open Babel's `openbabel-3-1-1` tag byte for byte, apart from line
endings. Upstream master's `eem.cpp` and `qeq.cpp` differ from that tag only in
build and style changes (checked 2026-09-14).

## 1. The data directory, root-caused

| arm | EEM | QEq |
|---|---|---|
| the wheel's own setting | file not opened, all charges 0 | file not opened, **crash** |
| set in the shell, Windows path | same | same |
| **set from Python after `import openbabel`** | **computes** | **computes** |
| set in the shell, POSIX path | file not opened | crash |
| set from Python after import, POSIX path | file not opened | crash |

- **A value set in the shell does not survive.** The wheel's `__init__` sets
  `BABEL_DATADIR` after loading the library. The library reads the variable
  when it opens a file, from the same environment Python writes to, so a value
  set after import is the one it sees.
- **"No parameters found for: C 1" is not a second defect.** It follows
  "Cannot open file with parameters: eem.txt": with no file, the parameter
  table is empty. The ROADMAP entry of the same day said the file opened and
  the run still failed. That was wrong, and the entry now carries the
  correction.
- **The crash is QEq's, whatever the path style.** A POSIX path was blamed
  first. The measurement says QEq crashes whenever `qeq.txt` cannot be opened
  (exit code 0xC0000005), and EEM never does. The source shows why:
  `QEqCharges::GetParameters` tests `Z < _parameters.size()-1`, which wraps to
  the largest unsigned value on an empty table, and then indexes it.

So both methods can run without changing Open Babel's behaviour anywhere
else: in a child process that sets the variable for itself. The stop rule's
first condition does not fire.

## 2. The implementations, against independent solves

Tolerances were fixed in `preregistration.md` before the solves ran. Both
sides read one serialized molblock, so a difference can only be
implementation. The set: 13 molecules, neutral, cationic, anionic and
zwitterionic, with H, C, N, O, F, S, Cl and Br.

| method | worst max \|Open Babel - solve\| | tolerance | verdict |
|---|---|---|---|
| EEM (`eem.txt`) | 2.9e-15 e | 1e-4 e | passes |
| EEM, each of the six `eem2015*` sets | 7.2e-14 e or less | 1e-4 e | passes |
| QEq | **8.0 e** | 1e-4 e | **STOP** |

**Open Babel's QEq charges have the wrong sign.**
- On every neutral molecule they are the exact negative of the solve, to
  4e-6 e. On a charged molecule they are neither.
- The cause: `qeq.cpp` puts +chi on the right-hand side, and the stationarity
  condition of the energy it documents needs -chi.
- Methanol comes out with O at +1.36 and the hydroxyl H at -0.83.
- Rappé & Goddard's own Table IV prints QEq charges of O -0.66 and H(O) +0.36
  for methanol. Those are on their geometry, with hydrogen's charge
  dependence, which Open Babel leaves out by its own note.
- Upstream master computes the same thing.

The solve with the sign corrected is not Rappé–Goddard's QEq either. Compared
with Table IV for the two molecules it shares with this set (informational
only, as `preregistration.md` fixed; the geometries differ):

| atom | Table IV QEq | Open Babel | sign-corrected solve |
|---|---|---|---|
| methanol O | -0.66 | +1.36 | -1.36 |
| methanol H(O) | +0.36 | -0.83 | +0.83 |
| methanol C | -0.15 | -0.75 | +0.75 |
| formamide N | -0.63 | +2.91 | -2.91 |
| formamide C | +0.39 | -2.79 | +2.79 |
| formamide O | -0.42 | +1.22 | -1.22 |

Open Babel gets every formamide heavy atom's sign wrong. Correcting the sign
fixes those signs, but the magnitudes are two to seven times the paper's.
**Why was not measured.** Three things differ, and none was isolated: the
geometry, and the two departures from the paper that `qeq.cpp` declares
(Gaussian orbitals, and hydrogen's hardness held at its neutral value).

## 3. The parameters, against their sources

**`qeq.txt` against Rappé & Goddard 1991 Table I (rendered at 300 dpi):**
- chi and J match for all sixteen elements the table prints.
- The radius column is not the table's R. It is the Gaussian screening radius
  `qeq.cpp` credits to Chen & Martínez 2009, by design. That paper was not
  checked.

**`eem.txt` against Bultinck et al. 2002, part II, Table 2 (Mulliken,
B3LYP/6-31G\*, rendered at 300 dpi).** `eem.cpp` labels it "Bultinck
B3LYP/6-31G*/MPA". The file stores chi\* and 2eta\* in Hartree, and is read back
in eV to the printed two decimals.

| element | agrees? | file, in eV | Table 2 |
|---|---|---|---|
| H | yes | | |
| N | yes | | |
| F | yes | | |
| C | **no** | eta\* 8.971, chi\*-chi\*H 4.253 | 9.00, 4.26 |
| O | **no** | eta\* 14.811, chi\*-chi\*H 14.261 | 14.34, 13.72 |

Beyond those five elements:
- **Twelve elements carry carbon's exact pair**: Li, B, Na, Mg, Si, P, Cl,
  K, Ca, Fe, Cu and Zn. S, Br and I have values Table 2 does not print.
- **The `* *` row is hydrogen's pair**, so any element the file does not list
  is silently computed as hydrogen.
- The file came into Open Babel in 2015 as a move of values already in its
  source (commit `ea01909f9`). The `eem2015*` sets came in with a commit that
  names no paper (`66bd04c16`). Ionescu et al. 2015 describes the tool that
  ships such sets and prints no values, so none of the six has been checked
  against a source.

**Bultinck et al. 2002 part I** (J. Phys. Chem. A 106, 7887) is not held, and
C and O may come from it. That is unchecked, not settled.

## What this leaves for a decision

- **QEq:** implement it here (Rappé–Goddard with Slater integrals and
  hydrogen's charge dependence, checked against Table IV), or leave it out.
  The plan's fallback was the first.
- **EEM:** the arithmetic is exact, but a set is not labelled with a source it
  does not match. It needs part I to check C and O, and the source paper for
  the `eem2015` sets if one of those is to be offered. Either way, an element
  with no parameters of its own has to be refused, never computed as hydrogen.
