# Does building the assembly change a docking result?

Two real Vina 1.2.7 runs against the shipped `VinaDockingProvider` — the
only checks of the assembly builder that go through docking rather than
through coordinates. Kept because re-running them is how a future change
to the builder, the receptor preparation or the box gets re-validated.

```bash
uv run --no-sync python spikes/assembly_docking/control_4dkl.py
uv run --no-sync python spikes/assembly_docking/interface_1hhp.py
```

`OPENCHEM_VINA` overrides the executable path. Structures are fetched
into `benchmarks/assembly/cache/`, shared with the RCSB gate. Each script
is ~10 minutes: six to nine docking runs.

## The two cases separate by an order of magnitude

**`control_4dkl.py` — the pose must NOT move.** The mu-opioid receptor's
orthosteric pocket sits inside the monomer, so the copy the assembly adds
is distant from the site. Same box for both arms, 3,690 atoms → 7,380.

    pinned seed, deposited vs built    dRMSD 0.33-0.54 A   dScore 0.008-0.014
    unpinned, same receptor twice      dRMSD 0.24-0.41 A   dScore 0.005-0.008

**`interface_1hhp.py` — the pose MUST move.** HIV-1 protease is an
obligate homodimer whose active site sits on the 2-fold, one catalytic
aspartate from each chain. 1HHP deposits one chain (758 atoms) and
annotates a dimer, so the file as deposited is half an active site. Box
centred on the dyad, same for both arms, nelfinavir as the ligand.

    seed   monomer   dimer    gain    dRMSD
       1    -6.127  -7.048   0.921    7.173
       2    -5.909  -7.237   1.328    9.095
       3    -5.900  -7.132   1.232    2.636

The dimer wins by 0.9–1.3 kcal/mol on every seed and the binding mode is
different, not nudged.

## Pin the seed, and measure the noise floor too

`VinaDockingProvider` passes `seed=None`, so the shipped app runs Vina
with a **random seed** — two runs of the same receptor already differ.
An unpinned A/B measures the search wandering, not the receptor.

Pinning alone is still not enough: changing the receptor changes the
pdbqt and therefore the search trajectory even at a fixed seed, so the
arms are not expected to be identical. The same-receptor spread is what
gives the difference a scale to be read against, which is why
`control_4dkl.py` measures it. The two 4DKL rows overlap, and that
overlap *is* the result — reported as overlapping rather than as
"identical", because at n=3 and n=2 there is nothing else to claim.

**A control that cannot fail is not a control**, which is what the 1HHP
case is for: it shows the measurement can detect a receptor change when
there is one to detect.

To pin the seed without bypassing the code under test, both scripts wrap
`ExecutableVinaEngine.dock` and inject it. The provider calls that method
**by keyword**, so a positional wrapper raises `unexpected keyword
argument 'seed'` — accept `**kwargs`.

## Incidental findings

- The two Asp25 CG atoms of the built 1HHP dimer come out at
  (43.52, 44.33, −2.62) and (44.33, 43.52, 2.62), 5.36 Å apart — a clean
  2-fold, which checks the build independently of the docking.
- `receptor_prep_options` must **omit** `ph` rather than pass `None`: the
  provider does `float(options.get("ph", default))`, so an explicit None
  reaches `float()` and raises. Not reachable from the UI, where the
  value comes from a spin box.
