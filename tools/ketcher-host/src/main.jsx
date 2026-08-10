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
let controlsIntercepted = false

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
  // Guarded: `tryWireBridge` runs from BOTH sides (whichever of Ketcher
  // and the QWebChannel finishes last), so unguarded listeners would be
  // registered twice and answer one click twice.
  if (!controlsIntercepted) {
    controlsIntercepted = true
    interceptDuplicatedControls()
    interceptUndoShortcuts()
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

// ONE OF EACH, NOT TWO.
//
// Ketcher ships its own periodic table, file open/save, About, Help,
// settings and 3D viewer, and the application has all of them already.
// Two controls that look alike and behave differently read as one
// feature that has lost half its capability depending which you pressed
// -- which is exactly how the first of them was reported: "the periodic
// table reverted to vanilla".
//
// Each entry is a `data-testid` -> bridge call. The ids are read off the
// live DOM rather than the bundle; Ketcher's own e2e tests key on them,
// so they are as stable as anything in a vendored build gets.
//
// WHAT IS DELIBERATELY ABSENT, because replacing it would lose a
// capability rather than a duplicate:
//
//   any-atom        query atoms (any / list / not-list), which the
//                   application's periodic table cannot express
//   template-lib    Ketcher's template library, which has no equivalent
//   clear-canvas    emptying the drawing is a drawing operation, and its
//                   `change` already flows into the application's undo
//                   stack, so it is undoable rather than destructive
//   polymer-toggler Ketcher can DRAW rna/dna/peptide; the Macromolecule
//                   Viewer only shows one. Intercepting would remove the
//                   only way to draw a polymer in this application.
//   settings-button Ketcher's Settings holds render options -- bond
//                   thickness, fonts, stereo labels -- of which this
//                   application proxies only a few under View > 2D
//                   Structure Display. There is no dialog here to route
//                   it to, and sending it to External Tools (ORCA and
//                   Vina paths) would answer a different question. It is
//                   a duplicate only in name.
const INTERCEPTED = {
  'period-table': 'periodicTableRequested',
  'open-file-button': 'importRequested',
  'save-file-button': 'exportRequested',
  'about-button': 'aboutRequested',
  'help-button': 'helpRequested',
  '3D Viewer button': 'viewer3dRequested',
  // Undo and redo are the two that are not merely duplication. Measured:
  // Ketcher's undo does NOT unwind the application's QUndoStack -- it
  // edits the canvas, which fires `change`, which pushes a NEW
  // EditStructureCommand. The stack grew 3 -> 4 on an undo. And undoing
  // past our own `setMolecule` empties the canvas, with the project
  // model following it to zero atoms.
  undo: 'undoRequested',
  redo: 'redoRequested',
}

// CAPTURE PHASE, and `stopPropagation` rather than only
// `preventDefault`. The handler is React's, bound at the root, so a
// bubble-phase listener runs AFTER Ketcher has already acted, and
// `preventDefault` alone would leave both the application's answer and
// Ketcher's on screen.
function interceptDuplicatedControls() {
  document.addEventListener(
    'click',
    (event) => {
      if (!bridgeObject) return
      for (const testid of Object.keys(INTERCEPTED)) {
        // `closest` because the click usually lands on an icon INSIDE
        // the button, not on the button itself.
        if (event.target.closest?.(`[data-testid="${CSS.escape(testid)}"]`)) {
          event.preventDefault()
          event.stopPropagation()
          bridgeObject[INTERCEPTED[testid]]()
          return
        }
      }
    },
    true,
  )
}

// THE KEYBOARD IS THE PATH A USER ACTUALLY TAKES, and it is a separate
// interception because a shortcut never goes near a button.
//
// Ketcher binds `Mod+z` and `Mod+Shift+z` itself (both present in the
// vendored bundle) while the application binds Ctrl+Z to its own undo
// action. Whichever has focus wins, which is the same collision that
// already forced paste onto Ctrl+Shift+V. With the canvas focused --
// the normal case while drawing -- Ketcher's wins, and Ketcher's undo is
// the one measured above that grows the application's stack instead of
// unwinding it.
//
// Captured on `document` for the same reason as the clicks, and BEFORE
// Ketcher's own handler: it registers on the editor element, which is a
// descendant.
function interceptUndoShortcuts() {
  document.addEventListener(
    'keydown',
    (event) => {
      if (!bridgeObject) return
      if (!(event.ctrlKey || event.metaKey)) return
      if (event.key.toLowerCase() !== 'z' && event.key.toLowerCase() !== 'y') return
      event.preventDefault()
      event.stopPropagation()
      // Ctrl+Y as well as Ctrl+Shift+Z: the application's redo is bound
      // to Ctrl+Y, and somebody who has learned that should not find it
      // doing nothing inside the canvas.
      const redo = event.key.toLowerCase() === 'y' || event.shiftKey
      if (redo) {
        bridgeObject.redoRequested()
      } else {
        bridgeObject.undoRequested()
      }
    },
    true,
  )
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
