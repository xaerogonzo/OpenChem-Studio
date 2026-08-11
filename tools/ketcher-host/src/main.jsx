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


// The rotation overlay's styles, injected rather than kept in a stylesheet:
// this bundle has no CSS of its own beyond Ketcher's, and a second file
// would be one more thing to remember to ship.
const ROTATION_STYLES = `
.openchem-rotate { position:absolute; inset:0; z-index:20; cursor:grab;
                   background:rgba(25,118,210,0.03); }
.openchem-rotate:active { cursor:grabbing; }
.openchem-rotate .rot-banner {
  position:absolute; top:0; left:0; right:0; height:24px; line-height:24px;
  background:#1976d2; color:#fff; font:12px system-ui, sans-serif;
  padding:0 10px; box-sizing:border-box; pointer-events:none; }
.openchem-rotate .rot-readout { float:right; font-variant-numeric:tabular-nums; }
.openchem-rotate .rot-ruler { position:absolute; pointer-events:none;
  font:10px system-ui, sans-serif; color:#1976d2; }
.openchem-rotate .rot-top { top:24px; left:0; right:0; height:16px;
  border-bottom:1px solid rgba(25,118,210,0.35); }
.openchem-rotate .rot-left { top:40px; left:0; bottom:0; width:34px;
  border-right:1px solid rgba(25,118,210,0.35); }
.openchem-rotate .rot-top .rot-tick { position:absolute; transform:translateX(-50%); }
.openchem-rotate .rot-left .rot-tick { position:absolute; left:2px;
                                       transform:translateY(-50%); }
`

function ensureRotationStyles() {
  if (document.getElementById('openchem-rotate-styles')) return
  const style = document.createElement('style')
  style.id = 'openchem-rotate-styles'
  style.textContent = ROTATION_STYLES
  document.head.appendChild(style)
}

// --- 3D rotation mode --------------------------------------------------
//
// "we need the rotation rulers and live angle readouts too inside the 2d
// editor definitely", against a MarvinSketch screenshot.
//
// **MEASURED BEFORE IT WAS BUILT** (the gate in
// tests/test_ketcher_holds_3d_coordinates.py and its spike):
//
//   an atom's `pp` really carries a z, populated from a 3D molfile
//   mutating positions + render.update fires NO `change` event
//   Ketcher's own undo history is unchanged by the preview
//   selection and the active tool survive, and atom 3 is still atom 3
//   getMolfile afterwards reports the NEW coordinates
//   ~32 ms per redraw at 20 atoms, ~40 ms at 32
//
// The last one is why a drag coalesces onto animation frames instead of
// redrawing per mouse event: at 30 ms a frame, a queue of mousemoves
// would run further and further behind the pointer.
//
// **ANGLES ARE ABSOLUTE FROM ENTRY, applied to a snapshot** rather than
// accumulated frame to frame. That is what makes re-entering read 0, 0
// and what stops repeated drags drifting.
let rotationBase = null       // [{id, x, y, z}] as the mode was entered
let rotationAngles = {x: 0, y: 0}
let rotationFrame = null
let rotationOverlay = null

function enterRotationMode() {
  if (!ketcherInstance) return
  const struct = ketcherInstance.editor.struct()
  rotationBase = []
  struct.atoms.forEach(function (atom, id) {
    rotationBase.push({id: id, x: atom.pp.x, y: atom.pp.y, z: atom.pp.z || 0})
  })
  rotationAngles = {x: 0, y: 0}
  ensureRotationStyles()
  buildRotationOverlay()
  reportRotation()
}

function leaveRotationMode(restore) {
  if (restore && rotationBase) applyRotation(0, 0)
  rotationBase = null
  rotationAngles = {x: 0, y: 0}
  if (rotationOverlay) {
    // **THE WINDOW LISTENERS COME OFF WITH IT.** A drag has to follow the
    // pointer outside the overlay, so mousemove/mouseup live on `window`
    // -- and a version of this that only removed the element left one
    // pair behind per entry, for the life of the page. They were inert
    // (each closure checks its own `dragging`), which is exactly why
    // nothing would ever have noticed.
    if (rotationOverlay.__openchemDetach) rotationOverlay.__openchemDetach()
    rotationOverlay.remove()
    rotationOverlay = null
  }
}

// Applied to the SNAPSHOT, never to the current positions. Composition is
// R_x . R_y, matching chem/camera_orientation.py's `rotation_from_degrees`
// -- the two must agree, because Python is what finally writes the
// molblock and a different order there would move the structure again on
// commit.
function applyRotation(xDegrees, yDegrees) {
  if (!rotationBase || !ketcherInstance) return
  const rx = (xDegrees * Math.PI) / 180
  const ry = (yDegrees * Math.PI) / 180
  const cx = Math.cos(rx), sx = Math.sin(rx)
  const cy = Math.cos(ry), sy = Math.sin(ry)
  const struct = ketcherInstance.editor.struct()

  // Rotate about the CENTROID, so the structure turns in place instead of
  // swinging around whatever the origin happens to be.
  let mx = 0, my = 0, mz = 0
  rotationBase.forEach(function (p) { mx += p.x; my += p.y; mz += p.z })
  mx /= rotationBase.length; my /= rotationBase.length; mz /= rotationBase.length

  rotationBase.forEach(function (p) {
    const atom = struct.atoms.get(p.id)
    if (!atom) return
    const x0 = p.x - mx, y0 = p.y - my, z0 = p.z - mz
    // R_y first, then R_x -- the same order Python composes.
    const x1 = x0 * cy + z0 * sy
    const z1 = -x0 * sy + z0 * cy
    const y2 = y0 * cx - z1 * sx
    const z2 = y0 * sx + z1 * cx
    atom.pp.x = x1 + mx
    atom.pp.y = y2 + my
    atom.pp.z = z2 + mz
  })
  ketcherInstance.editor.render.update(true)
}

function scheduleRotation() {
  // Coalesced onto one animation frame: a redraw costs ~30 ms, so one
  // per mousemove would fall progressively behind the pointer.
  if (rotationFrame !== null) return
  rotationFrame = window.requestAnimationFrame(function () {
    rotationFrame = null
    applyRotation(rotationAngles.x, rotationAngles.y)
    reportRotation()
  })
}

function reportRotation() {
  if (bridgeObject) bridgeObject.rotationAngles(rotationAngles.x, rotationAngles.y)
  if (rotationOverlay) {
    const readout = rotationOverlay.querySelector('.rot-readout')
    if (readout) {
      readout.textContent =
        'X ' + Math.round(rotationAngles.x) + '°   Y ' + Math.round(rotationAngles.y) + '°'
    }
  }
}

// Rulers along the top and left, and a banner. The mode deliberately
// steals the drag gesture, so it has to be unmistakable that drawing is
// not what a drag will do.
// The DRAWING SURFACE, not the whole editor.
//
// **PICKED BY AREA, never by class name.** Ketcher's canvas has no stable
// public selector and its toolbars are full of small inline `<svg>` icons,
// so "the biggest svg under the root" identifies it without depending on
// a Ketcher internal that a version bump would rename. Measured in the
// running app: covering the whole root instead drew the degree ruler
// straight across the toolbars, which reads as a broken overlay rather
// than as an inert toolbar.
//
// Returns null when there is nothing to measure, and the caller then
// covers everything -- a mode that fails to cover the canvas would let a
// drag draw a bond, which is far worse than an untidy ruler.
function canvasBounds(host) {
  const outer = host.getBoundingClientRect()
  let best = null, bestArea = 0
  const svgs = host.querySelectorAll('svg')
  for (let i = 0; i < svgs.length; i++) {
    const rect = svgs[i].getBoundingClientRect()
    const area = rect.width * rect.height
    if (area > bestArea) { bestArea = area; best = rect }
  }
  if (!best || bestArea < 100) return null
  return {
    left: best.left - outer.left,
    top: best.top - outer.top,
    width: best.width,
    height: best.height
  }
}

function positionRotationOverlay(overlay) {
  const bounds = canvasBounds(overlay.parentNode)
  if (!bounds) return
  overlay.style.left = bounds.left + 'px'
  overlay.style.top = bounds.top + 'px'
  overlay.style.right = 'auto'
  overlay.style.bottom = 'auto'
  overlay.style.width = bounds.width + 'px'
  overlay.style.height = bounds.height + 'px'
}

function buildRotationOverlay() {
  const host = document.querySelector('.Ketcher-root') || document.body
  const overlay = document.createElement('div')
  overlay.className = 'openchem-rotate'
  overlay.innerHTML =
    '<div class="rot-banner">3D rotation — drag to turn' +
    '<span class="rot-readout">X 0°   Y 0°</span></div>' +
    '<div class="rot-ruler rot-top"></div><div class="rot-ruler rot-left"></div>'
  host.appendChild(overlay)
  rotationOverlay = overlay
  positionRotationOverlay(overlay)
  drawRulerTicks(overlay)

  let dragging = false
  let startX = 0, startY = 0, baseX = 0, baseY = 0
  overlay.addEventListener('mousedown', function (event) {
    dragging = true
    startX = event.clientX; startY = event.clientY
    baseX = rotationAngles.x; baseY = rotationAngles.y
    event.preventDefault()
  })
  const onMove = function (event) {
    if (!dragging) return
    // Half a degree per pixel: a full turn is a comfortable drag across
    // a typical canvas rather than a flick.
    rotationAngles.y = baseY + (event.clientX - startX) * 0.5
    rotationAngles.x = baseX + (event.clientY - startY) * 0.5
    scheduleRotation()
  }
  const onUp = function () {
    if (!dragging) return
    dragging = false
    if (bridgeObject) bridgeObject.rotationFinished()
  }
  const onResize = function () { positionRotationOverlay(overlay) }
  window.addEventListener('mousemove', onMove)
  window.addEventListener('mouseup', onUp)
  window.addEventListener('resize', onResize)
  overlay.__openchemDetach = function () {
    window.removeEventListener('mousemove', onMove)
    window.removeEventListener('mouseup', onUp)
    window.removeEventListener('resize', onResize)
  }
}

function drawRulerTicks(overlay) {
  const top = overlay.querySelector('.rot-top')
  const left = overlay.querySelector('.rot-left')
  for (let degrees = -180; degrees <= 180; degrees += 30) {
    const horizontal = document.createElement('span')
    horizontal.className = 'rot-tick'
    horizontal.style.left = (50 + degrees / 3.6) + '%'
    horizontal.textContent = degrees + '°'
    top.appendChild(horizontal)
    const vertical = document.createElement('span')
    vertical.className = 'rot-tick'
    vertical.style.top = (50 + degrees / 3.6) + '%'
    vertical.textContent = degrees + '°'
    left.appendChild(vertical)
  }
}

function handleKetcherInit(ketcher) {
  ketcherInstance = ketcher
  window.ketcher = ketcher // used by Python's fire-and-forget runJavaScript calls (e.g. setMolecule)
  // The rotation mode is driven from Python. **This assignment is what
  // keeps the code in the bundle at all**: without a reference reachable
  // from the entry point, vite tree-shakes every rotation function away
  // and the feature is silently absent -- which is exactly what
  // test_ketcher_bundle_is_current.py caught the first time round.
  window.openchemRotation = {
    enter: enterRotationMode,
    leave: leaveRotationMode,
    angles: function () {
      return JSON.stringify(rotationAngles)
    },
  }
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
