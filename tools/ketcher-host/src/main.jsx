import React from 'react'
import { createRoot } from 'react-dom/client'
import { Editor } from 'ketcher-react'
import { StandaloneStructServiceProvider } from 'ketcher-standalone'
import 'ketcher-react/dist/index.css'

const structServiceProvider = new StandaloneStructServiceProvider()

// Bridges the Ketcher editor instance to the Python side (see
// ui/widgets/ketcher_editor_backend.py) once both Ketcher and the
// QWebChannel transport are ready. Either can finish first, so each side
// checks whether the other is already available before wiring the
// 'change' -> structureEdited(molfile) forwarding.
let ketcherInstance = null
let bridgeObject = null
let notifiedReady = false

// Where does this pool id sit in the molfile Ketcher would write?
//
// KETCHER'S SELECTION REPORTS POOL IDS, AND A POOL ID IS NOT A POSITION.
// `Pool` extends Map and hands out ids from a `nextId` counter that only
// ever increments -- both `add` and `newId` return `this.nextId++` -- so an
// id is a permanent identity handle and a freed one is NEVER reused. The
// molfile is positional, and RDKit numbers its atoms by reading it in
// order, so the two agree only until the first atom is removed.
//
// Measured on the real vendored build: draw two benzenes, erase the first,
// and the surviving six-atom ring carries pool ids 6..11 while its molfile
// is six atoms numbered 1..6. Clicking two of its vertices sent 8 and 10,
// and the Atom Inspector answered "Atom 9 is in the 3D structure but not in
// the structure as drawn -- pick a heavy atom" about a carbon. Bonds have
// exactly the same offset, and there it is worse: the index stays in range,
// so the panel silently reports a DIFFERENT bond rather than declining.
//
// A fresh `setMolecule` rebuilds the pool from zero. That is why every
// earlier probe saw ids and positions agree -- each one loaded a molblock
// and read the ids straight back -- and why this shipped. Identical on the
// previous vite 5 bundle, so it is Ketcher's data model, not the bundler.
//
// INSERTION ORDER, NEVER SORTED. Undo re-inserts a deleted atom under its
// ORIGINAL id at the END of the Map, so the ids can run [1,2,3,4,5,0].
// Measured on a C-N-O-F-S-P chain with the carbon deleted and restored: the
// molfile comes out N O F S P C, matching insertion order exactly, and
// sorting the ids would have been wrong in all six positions.
function molfilePosition(pool, poolId) {
  return Array.from(pool.keys()).indexOf(poolId)
}

function tryWireBridge() {
  if (!ketcherInstance || !bridgeObject) return
  if (!notifiedReady) {
    notifiedReady = true
    bridgeObject.ketcherReady()
  }
  try {
    ketcherInstance.editor.subscribe('change', () => {
      ketcherInstance.getMolfile().then((molfile) => {
        bridgeObject.structureEdited(molfile)
      })
    })
  } catch (e) {
    console.error('[ketcher-host] failed to subscribe to change event', e)
  }

  // Which atom is selected, for the Atom Inspector.
  //
  // `selectionChange` is NOT on ketcher.subscribe's switch -- that facade
  // only knows 'change' and 'libraryUpdate' -- but it IS on the editor's
  // own event object, confirmed by probing the real vendored build rather
  // than by reading the minified bundle. `editor.selection()` returns null
  // when nothing is selected, so the payload is nullable and the guard
  // below is load-bearing.
  //
  // Only single-atom selections are forwarded. The inspector describes ONE
  // atom, and a marquee across half the structure is a different gesture
  // that would otherwise make it flicker through whatever came last.
  // THE DISPATCHED ARGUMENT IS USELESS HERE -- read the selection back off
  // the editor instead. `selectionChange` is a PipelineSubscription, which
  // feeds each handler the PREVIOUS handler's return value rather than the
  // original payload. Ketcher registers its own handler first and that one
  // returns nothing, so anything added afterwards receives `undefined`.
  // Measured: a probe handler saw `typeof sel === 'undefined'` on every
  // dispatch while the event itself fired correctly.
  //
  // 'change' above does not have this problem because it is a plain
  // Subscription, which is why the two look like they should behave the
  // same and do not.
  try {
    ketcherInstance.editor.event.selectionChange.add(() => {
      const selection = ketcherInstance.editor.selection()
      if (!selection) return
      const struct = ketcherInstance.editor.struct()
      const atoms = selection.atoms
      const bonds = selection.bonds
      // Single atoms and single bonds only: the inspector describes ONE
      // subject, and a marquee across half the structure would make it
      // flicker through whatever came last.
      //
      // The selection object carries ONLY the keys that have something in
      // them -- clicking a bond gives `{bonds: [0]}` with no `atoms` key at
      // all -- so both are checked rather than assuming one shape.
      // Confirmed against the real vendored build.
      //
      // Both ids go through molfilePosition() -- see there for why sending
      // them raw told a user who had clicked a carbon to pick a heavy atom.
      if (atoms && atoms.length === 1) {
        const position = molfilePosition(struct.atoms, atoms[0])
        if (position >= 0) bridgeObject.atomSelected(position)
      }
      if (bonds && bonds.length === 1) {
        const position = molfilePosition(struct.bonds, bonds[0])
        if (position >= 0) bridgeObject.bondSelected(position)
      }
    })
  } catch (e) {
    console.error('[ketcher-host] failed to subscribe to selectionChange', e)
  }
}

function handleKetcherInit(ketcher) {
  ketcherInstance = ketcher
  window.ketcher = ketcher // used by Python's fire-and-forget runJavaScript calls (e.g. setMolecule)
  tryWireBridge()
}

if (window.qt && window.qt.webChannelTransport) {
  // eslint-disable-next-line no-undef
  new QWebChannel(window.qt.webChannelTransport, (channel) => {
    bridgeObject = channel.objects.bridge
    // Exposed so Python-injected scripts can route a Promise's resolved
    // value back through the bridge: QWebEnginePage.runJavaScript's own
    // callback does NOT await Promises in this Qt build, it returns
    // immediately with an empty result. See getMolblock() in
    // ui/widgets/ketcher_editor_backend.py.
    window.__openchemBridge = bridgeObject
    tryWireBridge()
  })
}

function App() {
  return (
    <Editor
      staticResourcesUrl=""
      structServiceProvider={structServiceProvider}
      errorHandler={(message) => console.error('[ketcher]', message)}
      onInit={handleKetcherInit}
    />
  )
}

createRoot(document.getElementById('root')).render(<App />)
