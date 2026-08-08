# Phase D spike — halite CIF to a rendered unit cell

**Status: the spike works.** `cif_spike.py` loads `halite.cif` into the
vendored 3Dmol in a bare `QWebEngineView` and produces `halite_render.png`
— a unit-cell box with a/b/c axes and the correct 4 Na + 4 Cl.

This directory is deliberately *not* a feature. The plan's Phase D says the
spike is the whole of Phase D until it works: no `domain/crystal.py`, no
CIF reader, no calculator, no panel, because an elegant architecture for a
problem whose shape is still unknown is exactly the rabbit hole
crystallography invites. What follows is that shape, measured.

## 1. The vendored 3Dmol already does the whole render pipeline

No new library is needed to *display* a crystal. `3Dmol-min.js` handles:

    _cell_length_a/b/c, _cell_angle_*    -> conversionMatrix3
    _atom_site_fract_x/y/z               -> Cartesian
    _symmetry_equiv_pos_as_xyz           -> operators
    doAssembly / duplicateAssemblyAtoms  -> expansion
    viewer.addUnitCell(model)            -> the box, with labelled axes

`model.getCrystData()` hands back `{a, b, c, alpha, beta, gamma, matrix}`,
so the Python side can read the cell without parsing the CIF itself.

## 2. Symmetry is NOT applied by default

    addModel(cif, 'cif')                                    2 atoms
    addModel(cif, 'cif', {doAssembly: true,
                          duplicateAssemblyAtoms: true})    8 atoms (4 Na, 4 Cl)

The bare call returns the **asymmetric unit**. A caller that forgets the
options gets a chemically meaningless two-atom "crystal" with no error —
which would look like a parsing bug and is not one.

## 3. Expansion does not wrap into the cell

Measured: **3 of the 4 chlorides land at or outside `[0, a)`**.

    Cl  2.820  5.639  5.639
    Cl  5.639  2.820  5.639
    Cl  5.639  5.639  2.820

The *set* is right — those are the 4b positions translated by lattice
vectors — but they are not the conventional cell representatives. For a
picture it means atoms sit on and beyond the box; for any analysis that
counts cell contents or coordination it is simply wrong. **Anything built
on this has to wrap for itself.**

## 4. Wrapping needs a tolerance, not a modulo

The coordinates come back rounded, so a chloride at exactly `a` reads as
`5.639` against `a = 5.6393`, and a naive `x % a` leaves it outside
because `5.639 < 5.6393`. Boundary atoms are the common case in a crystal,
not an edge case.

## 5. The app cannot load a CIF yet, and it is two changes not one

`resources/viewer3d/viewer.html` hardcodes `viewer.addModel(molblock,
'mol')`, and `ui/widgets/mol3d_viewer_backend.py` exposes only
`load_conformer(molblock)`. CIF support needs a new path in both.

## 6. WebGL defeats both of this project's screenshot habits

`QWebEngineView.grab()` returned a blank PNG while the render had in fact
succeeded, and `drawImage`-ing the canvas into a 2D context to count ink
gave **0 inked pixels of 2,520,000** for the same reason — a WebGL
drawing buffer is not readable that way without `preserveDrawingBuffer`.

**`viewer.pngURI()` is the honest check**, and it is what produced the
committed render. This is a *different* trap from the documented
"`repaint()` does not paint a widget that was never shown", and the
`conftest.ink()` recipe does not transfer to a WebGL canvas.

## 7. A minimal CIF is enough for special positions

`halite.cif` lists only the **four face-centring translations**, not the
192 operations of Fm-3m. Both sites sit on special positions whose site
symmetry is the full point group, so the centring alone generates the
correct contents. A general position would need the whole list — so
"which operators are enough" is a per-structure question, not a constant.

## Where the numbers came from

`a` is **derived from the published cell volume** rather than quoted:
V₀ = 179.34 Å³ at Z = 4 (Walker, Verma, Cranswick, Jones, Clark & Buhre,
*American Mineralogist* **89** (2004) 204–210, Table 1, attributed there to
Barrett & Wallace 1954), so a = V₀^(1/3) = 5.6393 Å.

Reading that paper needs care: its PDF text layer is **shifted by +29**
(`$PHULFDQ` decodes to `American`) *and drops every digit*, so the numbers
have to be read from a rendered image. Decoding the letters is a red
herring for a table.

**A cross-check that fell out for free:** the Na–Cl nearest-neighbour
distance is a/2 = 2.8197 Å, and the sum of the Shannon six-coordinate radii
validated in Phase C is 2.83 Å — **0.4% apart**. Phase C's data predicts
Phase D's geometry, which is expected (Shannon fitted those radii to
interatomic distances in halides) and confirms the whole derivation chain.

## What this does NOT establish

- **Only one structure, and a cubic one.** Nothing here exercises a
  non-orthogonal cell, where the conversion matrix actually earns its
  keep.
- **A hand-assembled CIF.** Real-world files carry occupancies, anisotropic
  displacement parameters, disorder, `_atom_site_symmetry_multiplicity`,
  and vendor-specific quirks. None of that is tested.
- **No mineral CIF was read from a database**, so nothing is known about
  how AMCSD or COD files differ from this one.
- **Display only.** Coordination polyhedra, packing, and density are the
  reasons to want a `domain/crystal.py`, and the spike says nothing about
  them beyond "3Dmol will not do them for you".
