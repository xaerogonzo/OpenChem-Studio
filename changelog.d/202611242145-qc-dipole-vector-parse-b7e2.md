### Parse this Quantum run’s last dipole vector with origin and frame

- ORCA, Psi4, and xtb still store `{provider}.dipole_moment` in Debye from the last complete dipole block. When that block’s XYZ converts cleanly, provenance also keeps `vector` (Debye), `vector_origin` (`center_of_mass` or `cartesian_origin`), and `vector_frame` (`job_cartesian`). That replaces ORCA-only `vector_debye`. A printed magnitude is kept when the vector cannot be used. Compound ORCA jobs still store no dipole.
