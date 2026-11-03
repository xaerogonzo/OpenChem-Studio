# Explainers: NMR on the tautomers of a molecule

Hand-written, and merged into `docs/CALCULATOR_REFERENCE.md` by
`tools/build_calculator_reference.py`; the format is documented in
`tools/calculator_explainers.py` and guarded by
`tests/test_calculator_explainers.py`. Every claim is one of three kinds and
says which: **published** (a registered source says it), **shipped** (what this
application's code does, read from the code, `chem/tautomer_nmr.py`) or **measured here**. Nothing on this
page is measured here: the shifts of a tautomer mixture have not been compared with measured spectra.

## orca.tautomer_nmr

### What it does
Calculates NMR chemical shifts for each tautomer of a molecule, starting from a tautomer distribution you have already run, and lays the peaks of the tautomers side by side. Where that distribution gave population percentages it also averages the carbon shifts and the shifts of hydrogens on carbon, weighted by those percentages. It answers "what would each form show in the spectrum, and where would a fast-exchanging mixture of them sit".

### How it works
Shipped: it takes the tautomers of a finished distribution in order of their energy and runs one real ORCA NMR calculation on the geometry that distribution optimized for each, so the shifts describe the same structures whose energies set the weights and nothing is embedded or optimized again. With a conformer average chosen, it runs every conformer of each tautomer's representative stereoisomer and Boltzmann-averages them atom by atom, and a tautomer with one failed conformer is failed rather than averaged over the rest. The shielding values become shifts the way an ordinary NMR calculation's do, with the cached reference for the method (or the empirical scaling); with none cached the run stops at its first result and says so, rather than printing raw shieldings as shifts.

The average is a fast-exchange average of carbons and of hydrogens bonded to carbon only. Hydrogens on nitrogen, oxygen or sulfur exchange with the solvent and with each other, so a gas-phase value for them would mislead and they are listed as not averaged. The weights are the distribution's gas-phase electronic-energy populations, with no vibrational, thermal or solvent correction, and they are used only where that distribution reported percentages.

### What the result means
Per tautomer, the peaks are what a calculation of that structure alone would give. The average is what a mixture would show if the tautomers exchanged faster than the instrument can resolve; slow exchange shows separate sets of peaks, and for that the per-tautomer peaks are the thing to read. **It is not validated.** The distribution it starts from has no validated populations, and the shifts of tautomer mixtures have not been compared with measured spectra here. A published database of experimental 1H and 13C shifts used to benchmark density-functional shifts exists [source:kwon2023], and this calculation has not been run against it.

### When to use it, when not
Use it to see how far apart the tautomers of one molecule would sit in a spectrum, or which shifts a mixture would move. Do not read the averaged numbers as measured shifts: the populations are an estimate in the gas phase and the calculation is experimental. It needs a finished tautomer distribution (run that first), an ORCA program, and the cached reference for the method (an ordinary NMR calculation at that method makes one). It costs one ORCA NMR job per tautomer, or per conformer with the conformer average.

### Search for
tautomer NMR, tautomer chemical shifts, averaged shifts

### Sources
- [source:kwon2023] -- a database of experimental 1H and 13C shifts for benchmarking calculated shifts, which this calculation has not been compared with
