"""Phase D spike: does the vendored 3Dmol read a CIF and expand the cell?

Probes the REAL vendored build in a bare QWebEngineView, which CLAUDE.md
records as far faster than driving the app -- the same approach that
answered the Ketcher selection question.

Nothing here is a design. It answers three questions and stops:
  1. does 3Dmol parse the cell and the symmetry operations?
  2. does it expand to the right cell contents, unasked or on request?
  3. what does it hand back that a Python side could use?
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PySide6.QtCore import QEventLoop, QTimer, QUrl
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication

HERE = Path(__file__).parent
VIEWER = Path("src/openchem/resources/viewer3d/viewer.html").resolve()
CIF = (HERE / "halite.cif").read_text(encoding="utf-8")


def run_js(page, script: str, timeout_ms: int = 8000):
    """**Wrap anything structural in JSON.stringify.** runJavaScript on this
    Qt build returns PRIMITIVES ONLY -- an array or object arrives as '',
    indistinguishable from a script that returned nothing. That cost an
    entire probe run during the Ketcher work.
    """
    result: list = []
    loop = QEventLoop()

    def done(value):
        result.append(value)
        loop.quit()

    page.runJavaScript(script, done)
    QTimer.singleShot(timeout_ms, loop.quit)
    loop.exec()
    return result[0] if result else None


def main() -> int:
    app = QApplication(sys.argv)
    view = QWebEngineView()
    view.resize(900, 700)
    view.show()

    ready = QEventLoop()
    view.loadFinished.connect(lambda ok: ready.quit())
    view.load(QUrl.fromLocalFile(str(VIEWER)))
    QTimer.singleShot(20000, ready.quit)
    ready.exec()

    page = view.page()
    print("viewer loaded :", run_js(page, "typeof $3Dmol"))
    print("3Dmol version :", run_js(page, "String($3Dmol.version || 'unknown')"))

    # Hand the CIF to 3Dmol in a viewer of our own, so nothing depends on
    # how viewer.html happens to be wired.
    setup = """
      var host = document.createElement('div');
      // An explicitly SIZED container. 3Dmol sizes its canvas from the
      // element, and a zero-height div renders nothing while reporting
      // success -- which is what a blank screenshot looked like.
      host.style.cssText = 'position:absolute;left:0;top:0;width:800px;height:600px;';
      document.body.appendChild(host);
      window.__spike = $3Dmol.createViewer(host, {backgroundColor: 'white'});
      1
    """
    print("viewer created:", run_js(page, setup))

    cif = json.dumps(CIF)

    # (1) plain parse, no assembly request
    plain = run_js(page, f"""
      (function() {{
        var v = window.__spike; v.clear();
        var m = v.addModel({cif}, 'cif');
        var atoms = m.selectedAtoms({{}});
        return JSON.stringify({{
          n: atoms.length,
          elems: atoms.map(function(a){{return a.elem;}}),
          first: atoms.slice(0, 3).map(function(a){{
            return [a.elem, +a.x.toFixed(4), +a.y.toFixed(4), +a.z.toFixed(4)];
          }}),
          cryst: m.getCrystData ? m.getCrystData() : null
        }});
      }})()
    """)
    print("\n--- addModel(cif) with no options ---")
    print(plain)

    # (2) with the documented symmetry/assembly option
    expanded = run_js(page, f"""
      (function() {{
        var v = window.__spike; v.clear();
        var m = v.addModel({cif}, 'cif', {{doAssembly: true, duplicateAssemblyAtoms: true}});
        var atoms = m.selectedAtoms({{}});
        var counts = {{}};
        atoms.forEach(function(a){{counts[a.elem] = (counts[a.elem]||0)+1;}});
        return JSON.stringify({{
          n: atoms.length,
          counts: counts,
          coords: atoms.map(function(a){{
            return [a.elem, +a.x.toFixed(3), +a.y.toFixed(3), +a.z.toFixed(3)];
          }})
        }});
      }})()
    """)
    print("\n--- addModel(cif, {doAssembly, duplicateAssemblyAtoms}) ---")
    print(expanded)

    # (3) can it actually draw, and is a unit-cell box available?
    drew = run_js(page, """
      (function() {
        var v = window.__spike;
        try {
          v.setStyle({}, {sphere: {scale: 0.3}, stick: {radius: 0.1}});
          if (v.addUnitCell) { v.addUnitCell(v.getModel()); }
          v.zoomTo(); v.render();
          return 'rendered, addUnitCell=' + (typeof v.addUnitCell);
        } catch (e) { return 'ERROR: ' + e.message; }
      })()
    """)
    print("\n--- render ---")
    print(drew)

    # **Count ink on the canvas; do not trust a screenshot.**
    # `QWebEngineView.grab()` does not capture WebGL, so the first run of
    # this probe wrote a blank PNG while the render had in fact succeeded --
    # the same trap as `repaint()` on a never-shown widget, and answered the
    # same way: measure what was actually drawn.
    ink = run_js(page, """
      (function() {
        var c = document.querySelector('canvas');
        if (!c) return 'NO CANVAS';
        var off = document.createElement('canvas');
        off.width = c.width; off.height = c.height;
        off.getContext('2d').drawImage(c, 0, 0);
        var d = off.getContext('2d').getImageData(0, 0, c.width, c.height).data;
        var total = 0, inked = 0;
        for (var i = 0; i < d.length; i += 4) {
          total++;
          if (d[i] < 240 || d[i+1] < 240 || d[i+2] < 240) inked++;
        }
        return JSON.stringify({canvas: [c.width, c.height], inked: inked,
                               pct: +(100*inked/total).toFixed(2)});
      })()
    """, 15000)
    print("\n--- ink on the canvas ---")
    print(ink)

    # 3Dmol's own exporter, which reads the WebGL buffer properly.
    uri = run_js(page, "String(window.__spike.pngURI ? window.__spike.pngURI() : '')", 20000)
    if isinstance(uri, str) and uri.startswith("data:image/png"):
        import base64

        (HERE / "halite_render.png").write_bytes(base64.b64decode(uri.split(",", 1)[1]))
        print("screenshot written from pngURI (%d bytes of data URI)" % len(uri))
    else:
        print("pngURI unavailable:", repr(uri)[:60])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
