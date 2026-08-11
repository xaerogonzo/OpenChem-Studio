"""Where Ketcher draws an atom, and how to know it without asking the DOM.

**THE GATE for drawing lone pairs on the canvas.** The dots are
OpenChem's, in an overlay that mirrors Ketcher's viewport, so everything
rests on one question: given `atom.pp`, where is that atom on screen?
Every answer below is measured against the real vendored bundle, and each
is a way for an overlay to look plausible while sitting somewhere else.

**THE TRANSFORM CHAIN, and it collapses to one affine.**

    atom.pp (model units, 1 unit = options.bondLength = 40)
      x microModeScale        -> viewBox coordinates
      x zoom, - viewBox origin,
      + svg client origin     -> CSS pixels

`render.ps()` and `render.obj2view()` do NOT exist on this build --
`page2obj` is the only mapping exposed, and it runs the wrong way. So the
forward map is obtained by INVERTING it at two probe points:

    a = page2obj(0, 0);  b = page2obj(100, 100)
    scale  = 100 / (b.x - a.x)
    offset = -a.x * scale
    screen = pp * scale + offset

Better than deriving it by hand from `microModeScale`, `zoom` and the
viewBox, because it cannot drift when Ketcher changes how any of those
work -- measured below, it tracks a zoom exactly.

**`devicePixelRatio` is deliberately absent from that equation.**
`page2obj` takes CSS pixels and the overlay is positioned in CSS pixels,
so display scaling cancels on both sides rather than being corrected for.
(Measured at dpr 1 on this machine; the argument is why no term is
needed, not a measurement of dpr 2.)
"""

from __future__ import annotations

import json
import math

import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

from tests.test_ketcher_editor_backend import (
    _draw_two_rings_and_erase_the_first,
    _ready_backend,
    _run_js_json,
    _wait_until,
)

#: The affine, derived from `page2obj` by inversion. Every test here and
#: the production overlay use this same derivation.
FORWARD = """
  var r = window.ketcher.editor.render;
  var a = r.page2obj({clientX: 0, clientY: 0});
  var b = r.page2obj({clientX: 100, clientY: 100});
  var sx = 100 / (b.x - a.x), sy = 100 / (b.y - a.y);
  var tx = -a.x * sx, ty = -a.y * sy;
"""

#: Where Ketcher REALLY drew each labelled atom. The oracle, and the one
#: place these tests are allowed to read Ketcher's own SVG -- production
#: never does.
WORST_ERROR = FORWARD + """
  var s = window.ketcher.editor.struct();
  var root = document.querySelector('.Ketcher-root');
  var best = null, area = 0;
  root.querySelectorAll('svg').forEach(function (x) {
    var bb = x.getBoundingClientRect();
    if (bb.width * bb.height > area) { area = bb.width * bb.height; best = x; }
  });
  var texts = [];
  best.querySelectorAll('text').forEach(function (t) {
    var bb = t.getBoundingClientRect();
    var str = (t.textContent || '').trim();
    if (str) texts.push({s: str, cx: bb.left + bb.width / 2, cy: bb.top + bb.height / 2});
  });
  var worst = -1, matched = 0, sample = null;
  s.atoms.forEach(function (at) {
    if (at.label === 'C') return;          // carbons carry no label to match
    var px = at.pp.x * sx + tx, py = at.pp.y * sy + ty;
    var bd = 1e9;
    texts.forEach(function (t) {
      if (t.s !== at.label) return;
      var d = Math.hypot(t.cx - px, t.cy - py);
      if (d < bd) { bd = d; }
    });
    if (bd < 1e9) { matched++; if (bd > worst) worst = bd; }
    if (at.label === 'O' && sample === null) { sample = [px, py]; }
  });
  return JSON.stringify({scale: sx, offset: [tx, ty], worst: worst,
                         matched: matched, oxygenAt: sample,
                         zoom: r.options.zoom});
"""


def _molblock(smiles: str) -> str:
    mol = Chem.MolFromSmiles(smiles)
    AllChem.Compute2DCoords(mol)
    return Chem.MolToMolBlock(mol)


def _loaded(qapp, smiles: str, atom_count: int):
    backend = _ready_backend(qapp, shown=True)
    backend.load_molblock(_molblock(smiles))
    assert _wait_until(
        qapp,
        lambda: _run_js_json(
            qapp, backend, "return window.ketcher.editor.struct().atoms.size;"
        ) == atom_count,
        timeout_seconds=25,
    )
    return backend


def _report(qapp, backend) -> dict:
    return json.loads(_run_js_json(qapp, backend, WORST_ERROR))


# --- G1: the forward map ------------------------------------------------------


def test_inverting_page2obj_predicts_where_ketcher_drew_the_atom(qapp):
    """Sub-pixel, against the drawing itself.

    The whole overlay rests on this. If it is out by even a few pixels
    the dots sit beside their atoms, which on a crowded structure reads
    as belonging to the wrong one.
    """
    backend = _loaded(qapp, "CC(=O)Oc1ccccc1C(=O)O", 13)

    report = _report(qapp, backend)

    assert report["matched"] >= 3, report
    assert report["worst"] < 1.0, report
    # The scale is Ketcher's own bond length, which is what makes the
    # derivation legible rather than magic.
    assert report["scale"] == pytest.approx(40.0, abs=0.01), report


def test_the_forward_map_tracks_a_REAL_zoom(qapp):
    """**`ketcher.setZoom` DOES NOTHING on this build**, and believing it
    cost two gate arms.

    Both reported a comfortable zero-pixel error while the drawing had
    not moved at all -- `options.zoom` stayed 1 and every atom stayed
    put. `editor.zoom()` is the call that works. So this asserts the
    viewport MOVED before it believes any accuracy number, which is the
    lesson this project has now paid for four times.
    """
    backend = _loaded(qapp, "CC(=O)Oc1ccccc1C(=O)O", 13)
    before = _report(qapp, backend)

    inert = _run_js_json(qapp, backend, """
      try { window.ketcher.setZoom(1.5); return 'called'; }
      catch (e) { return 'error'; }
    """)
    _wait_until(qapp, lambda: False, timeout_seconds=1.2)
    unmoved = _report(qapp, backend)
    assert inert == "called"
    assert unmoved["oxygenAt"] == pytest.approx(before["oxygenAt"], abs=0.01), (
        "setZoom has started working; the overlay can hook it and this "
        "test should say so instead of recording it as inert"
    )

    _run_js_json(qapp, backend, "window.ketcher.editor.zoom(1.5); return 1;")
    _wait_until(qapp, lambda: False, timeout_seconds=1.5)
    zoomed = _report(qapp, backend)

    assert zoomed["zoom"] == pytest.approx(1.5, abs=1e-6)
    assert zoomed["scale"] == pytest.approx(60.0, abs=0.01), "40 x 1.5"
    moved = math.dist(zoomed["oxygenAt"], before["oxygenAt"])
    assert moved > 10.0, f"the drawing did not move: {moved} px"
    assert zoomed["worst"] < 1.0, zoomed


def test_zoom_and_pan_are_not_announced_so_the_overlay_must_watch(qapp):
    """Why the overlay compares the transform on an animation frame
    instead of subscribing to something.

    `zoomChanged` is in `editor.event`, which is exactly the sort of thing
    that looks like the answer. Measured: it does **not** fire for a zoom
    performed through `editor.zoom()`. And Ketcher does not pan by
    scrolling -- its client area has no overflow to scroll (`scrollWidth
    == clientWidth`), so there is no `scroll` event either; a pan is a
    viewBox change, the same as a zoom.

    Both therefore show up in exactly one place: the affine derived from
    `page2obj`. Comparing it costs 0.009 ms.
    """
    backend = _loaded(qapp, "CC(=O)Oc1ccccc1C(=O)O", 13)

    _run_js_json(qapp, backend, """
      window.__zoomEvents = 0;
      window.ketcher.editor.subscribe('zoomChanged', function () { window.__zoomEvents++; });
      return 1;
    """)
    _run_js_json(qapp, backend, "window.ketcher.editor.zoom(1.4); return 1;")
    _wait_until(qapp, lambda: False, timeout_seconds=1.5)

    assert _run_js_json(qapp, backend, "return window.__zoomEvents;") == 0
    scrolling = json.loads(_run_js_json(qapp, backend, """
      var ca = window.ketcher.editor.render.clientArea;
      ca.scrollLeft = 120;
      return JSON.stringify({canScroll: ca.scrollWidth > ca.clientWidth,
                             afterSetting: ca.scrollLeft});
    """))
    assert scrolling == {"canScroll": False, "afterSetting": 0}


def test_the_transform_compare_is_cheap_enough_to_run_every_frame(qapp):
    """0.009 ms, against a 16 ms frame. Measured rather than assumed,
    because "watch it every frame" is the kind of decision that gets
    reversed on a guess about cost."""
    backend = _loaded(qapp, "CC(=O)Oc1ccccc1C(=O)O", 13)

    timing = json.loads(_run_js_json(qapp, backend, """
      var r = window.ketcher.editor.render;
      function fwd() {
        var a = r.page2obj({clientX: 0, clientY: 0});
        var b = r.page2obj({clientX: 100, clientY: 100});
        var sx = 100 / (b.x - a.x);
        return {sx: sx, tx: -a.x * sx};
      }
      var t0 = performance.now();
      for (var i = 0; i < 2000; i++) { fwd(); }
      return JSON.stringify({ms: (performance.now() - t0) / 2000});
    """))

    assert timing["ms"] < 0.5, timing


# --- G4: Ketcher already draws the charge -------------------------------------


def test_ketcher_already_draws_the_formal_charge_so_we_must_not(qapp):
    """The reason there is no "show formal charges" option.

    Measured on `C[NH3+]`: the canvas renders `C H 3 N H 3 +`. Drawing a
    second charge beside Ketcher's would be the "two of everything"
    failure this project keeps removing.
    """
    backend = _loaded(qapp, "C[NH3+]", 2)

    drawn = json.loads(_run_js_json(qapp, backend, """
      var root = document.querySelector('.Ketcher-root');
      var best = null, area = 0;
      root.querySelectorAll('svg').forEach(function (x) {
        var bb = x.getBoundingClientRect();
        if (bb.width * bb.height > area) { area = bb.width * bb.height; best = x; }
      });
      var out = [];
      best.querySelectorAll('text').forEach(function (t) {
        var s = (t.textContent || '').trim();
        if (s) out.push(s);
      });
      return JSON.stringify(out);
    """))

    assert "+" in drawn, drawn


# --- G5: the forward index map ------------------------------------------------


def test_a_molfile_position_maps_to_a_pool_id_by_INSERTION_ORDER(qapp):
    """The payload is keyed by molfile position; Ketcher keys by pool id.

    **Measured on an EDITED structure, never a fresh load.** A pool
    rebuilt by `setMolecule` is dense, so the two agree by coincidence and
    a test on one proves nothing -- which is exactly how this shipped
    wrong on the reverse mapping. Two rings, the first deleted, leaves
    six atoms whose pool ids are 6..11 against molfile positions 0..5.

    Insertion order, NEVER sorted: undo re-inserts a deleted atom under
    its original id at the END of the Map, so a sorted implementation is
    plausible and wrong -- see `molfilePosition()` in `main.jsx`, which
    this is the inverse of.
    """
    backend = _ready_backend(qapp, shown=True)
    state = _draw_two_rings_and_erase_the_first(qapp, backend)

    assert state["atoms"] == [6, 7, 8, 9, 10, 11], state

    forward = json.loads(_run_js_json(qapp, backend, """
      var ids = Array.from(window.ketcher.editor.struct().atoms.keys());
      var out = {};
      ids.forEach(function (poolId, position) { out[position] = poolId; });
      return JSON.stringify(out);
    """))

    assert forward == {"0": 6, "1": 7, "2": 8, "3": 9, "4": 10, "5": 11}


# --- G6: label metrics without reading Ketcher's DOM --------------------------


def test_a_label_box_can_be_measured_without_touching_ketchers_dom(qapp):
    """The lone pair has to avoid the atom's LABEL, and `NH3+` occupies
    nothing like the space `N` does.

    The label text is composed from `editor.struct()` -- `label`,
    `implicitH`, `charge` -- and measured in a throwaway `<text>` in our
    own SVG at `render.options.fontsz`. Measured against the sum of the
    pieces Ketcher really drew: 34.3 px estimated, 34.0 px drawn.

    **`options.font` is a CSS shorthand ("30px Arial"), not a family**,
    so the size must be set separately or the box comes back at 30px.

    The drawn pieces are gathered BY PROXIMITY to the nitrogen, not by
    "is this character in the string". The first version did the latter
    and swept up the methyl's own `H` and `3` from `C[NH3+]`, scoring 50.6
    against a correct 34.0 -- a fixture with another labelled atom nearby
    proves less than it looks.
    """
    backend = _loaded(qapp, "C[NH3+]", 2)

    result = json.loads(_run_js_json(qapp, backend, FORWARD + """
      var o = window.ketcher.editor.render.options;
      var svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      svg.setAttribute('style', 'position:absolute;left:-9999px;top:0;width:200px;height:60px');
      document.body.appendChild(svg);
      var t = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      t.setAttribute('font-size', o.fontsz);
      t.setAttribute('font-family', 'Arial');
      t.textContent = 'NH3+';
      svg.appendChild(t);
      var estimated = t.getBBox().width;
      document.body.removeChild(svg);

      var root = document.querySelector('.Ketcher-root');
      var best = null, area = 0;
      root.querySelectorAll('svg').forEach(function (x) {
        var bb = x.getBoundingClientRect();
        if (bb.width * bb.height > area) { area = bb.width * bb.height; best = x; }
      });
      // Each drawn piece belongs to its NEAREST atom. A fixed radius does
      // not work: the '+' of NH3+ sits 26 px out, past half a bond
      // length, while the methyl's own H is only 40 px away.
      var atoms = [];
      window.ketcher.editor.struct().atoms.forEach(function (a, id) {
        atoms.push({id: id, label: a.label, x: a.pp.x * sx + tx, y: a.pp.y * sy + ty});
      });
      var nitrogen = atoms.filter(function (a) { return a.label === 'N'; })[0];
      var drawn = 0, pieces = [];
      best.querySelectorAll('text').forEach(function (node) {
        var s = (node.textContent || '').trim();
        if (!s) return;
        var bb = node.getBoundingClientRect();
        var cx = bb.left + bb.width / 2, cy = bb.top + bb.height / 2;
        var owner = null, bd = 1e9;
        atoms.forEach(function (a) {
          var d = Math.hypot(cx - a.x, cy - a.y);
          if (d < bd) { bd = d; owner = a; }
        });
        if (owner && owner.id === nitrogen.id) { drawn += bb.width; pieces.push(s); }
      });
      return JSON.stringify({fontsz: o.fontsz, estimated: estimated,
                             drawn: drawn, pieces: pieces});
    """))

    assert result["fontsz"] == 13
    assert sorted(result["pieces"]) == ["+", "3", "H", "N"], result
    assert result["estimated"] == pytest.approx(result["drawn"], abs=2.0), result


def test_the_label_text_is_composed_from_the_struct_not_the_canvas(qapp):
    """`N` + implicit hydrogens + charge, all of it on the atom object --
    so the overlay never has to read what Ketcher rendered."""
    backend = _loaded(qapp, "C[NH3+]", 2)

    atoms = json.loads(_run_js_json(qapp, backend, """
      var out = [];
      window.ketcher.editor.struct().atoms.forEach(function (a, id) {
        out.push({id: id, label: a.label, implicitH: a.implicitH, charge: a.charge});
      });
      return JSON.stringify(out);
    """))

    nitrogen = next(a for a in atoms if a["label"] == "N")
    assert nitrogen["implicitH"] == 3
    assert nitrogen["charge"] == 1
