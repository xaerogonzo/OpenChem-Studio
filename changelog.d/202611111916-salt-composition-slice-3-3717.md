### Salt composition, slice 3 (library, no UI)

- Fully specified ionization (site transforms; net charge alone refused;
  several microspecies at one charge listed, not picked), two supplied ions
  as given, a small cited ion catalog, and `pka_compatible` as named-step
  evidence that never feeds `balance_two`. Still no panel and not a crystal.
- Site ionization counts a bonded hydrogen atom. `GetTotalNumHs()` does not,
  so an `AddHs` acetic acid refused deprotonation and a protonation could
  stack an explicit-H property on the real hydrogen.
