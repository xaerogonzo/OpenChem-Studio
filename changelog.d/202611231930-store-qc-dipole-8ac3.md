### Store this Quantum run’s dipole magnitude in Debye

- ORCA, Psi4, and xtb keep `{provider}.dipole_moment` after SCF when the output prints a dipole, in Debye (Psi4 converts the last Multipole Moments magnitude from a.u.; xtb reads GFN1 `total (Debye)` and GFN2 `full` `tot (Debye)`). Missing output still completes SCF. Compound ORCA jobs (`delta_scf`, `led`, `fukui`) never store a dipole. Mixed compare stays empty and there is no Quantum family dipole row.
