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
      if (atoms && atoms.length === 1) {
        bridgeObject.atomSelected(atoms[0])
      }
      if (bonds && bonds.length === 1) {
        // Ketcher's bond ids are dense and in molfile order, which is the
        // order RDKit reads them in too -- verified by loading the same
        // molblock into both and comparing every (begin, end) pair.
        bridgeObject.bondSelected(bonds[0])
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
