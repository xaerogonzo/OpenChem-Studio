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
      // The overlay's POSITIONS tier: atoms may have moved (Layout, Clean
      // Up, a drag) without the chemistry changing. Placement is
      // recomputed from the struct; the counts are Python's job and are
      // reused until Python sends new ones.
      refreshElectrons(false)
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
    // Turning the molecule really does move the atoms, so the slots
    // legitimately move with them -- the POSITIONS tier, not the
    // chemistry one. `refreshElectrons` sees the changed positions key
    // and recomputes placement without re-measuring a single label.
    refreshElectrons(false)
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

// --- the electron overlay ------------------------------------------------
//
// Lone pairs, drawn on the canvas. Ketcher cannot draw them -- `lonePair`
// appears ZERO times in this bundle -- and its only annotation surfaces
// (text objects, data S-groups) are written into the molfile, so either
// would make the dots part of the molecule and fire a `change`. These dots
// are OpenChem's: one layer, `pointer-events: none`, never inserted into
// Ketcher's render tree, never serialized.
//
// **EVERYTHING IS COMPUTED IN MODEL SPACE, and that is what makes pan and
// zoom free.** Ketcher's viewport transform is scale + translate with NO
// rotation, so a label box is axis-aligned in model units just as it is on
// screen, and nothing a pan or a zoom does can change a slot. The layer's
// single <g> carries the whole viewport; a viewport change rewrites one
// transform attribute and touches no dot.
//
// The forward map is obtained by INVERTING `render.page2obj` -- the only
// mapping this build exposes, and it runs backwards. Measured accurate to
// under a pixel, and it tracks zoom exactly, because Ketcher zooms by
// changing the viewBox and page2obj already accounts for that. See
// tests/test_ketcher_viewport_transform.py for the whole gate.

const ELECTRON_STYLES = `
.openchem-electrons { position:absolute; pointer-events:none; z-index:15; overflow:visible; }
.openchem-electrons circle { fill:#1b5e20; }
.openchem-electrons .el-note {
  font:12px system-ui, sans-serif; fill:#b26a00; }
`

// Shared with chem/electron_layout.py, which judges what this produces.
// tests/test_ketcher_bundle_is_current.py asserts the numbers match; a
// constant that drifts on one side is what nothing else would notice.
const MIN_SLOT_SEPARATION_DEGREES = 40.0
const MIN_BOND_CLEARANCE_DEGREES = 25.0
const SLOT_RADIUS_FRACTION = 0.33
const PAIR_HALF_GAP_FRACTION = 0.055
const LABEL_PADDING_FRACTION = 0.05
const SLOT_STEP_DEGREES = 10.0

let electronLayer = null
let electronGroup = null
let electronNote = null
let electronWatching = false
const electronState = {
  mode: 'off',
  payload: null,
  placement: null,
  transform: null,
  labelBoxes: {},
  positionsKey: null,
}

// Counters for the WORK TIERS, so a test can assert that nothing does
// more than its tier -- a pan must not re-measure a label, and sixty
// rotation frames must not re-measure one either. Cheap enough to leave
// in: three integers, incremented where the work happens, and the only
// way to check a performance boundary that is otherwise invisible until
// somebody notices the editor has gone sticky.
const electronWork = { placements: 0, labelMeasurements: 0, transforms: 0, watchers: 0 }

function ensureElectronStyles() {
  if (document.getElementById('openchem-electron-styles')) return
  const style = document.createElement('style')
  style.id = 'openchem-electron-styles'
  style.textContent = ELECTRON_STYLES
  document.head.appendChild(style)
}

// ONE layer for the life of the editor. Created on first use and then
// hidden and shown -- never rebuilt, because a layer per toggle is how a
// DOM quietly accumulates a hundred of them, and the rotation overlay in
// this same file already leaked a listener pair per entry.
function ensureElectronLayer() {
  if (electronLayer && electronLayer.isConnected) return electronLayer
  ensureElectronStyles()
  const host = document.querySelector('.Ketcher-root') || document.body
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg')
  svg.setAttribute('class', 'openchem-electrons')
  svg.style.pointerEvents = 'none'
  electronGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g')
  svg.appendChild(electronGroup)
  electronNote = document.createElementNS('http://www.w3.org/2000/svg', 'text')
  electronNote.setAttribute('class', 'el-note')
  electronNote.setAttribute('x', '8')
  electronNote.setAttribute('y', '18')
  svg.appendChild(electronNote)
  host.appendChild(svg)
  electronLayer = svg
  return svg
}

function ketcherCanvas() {
  const host = document.querySelector('.Ketcher-root') || document.body
  let best = null
  let area = 0
  const svgs = host.querySelectorAll('svg')
  for (let i = 0; i < svgs.length; i++) {
    if (svgs[i].classList.contains('openchem-electrons')) continue
    const rect = svgs[i].getBoundingClientRect()
    if (rect.width * rect.height > area) {
      area = rect.width * rect.height
      best = svgs[i]
    }
  }
  return best
}

// The forward map, model -> CSS pixels, by inverting page2obj at two
// probe points. Returns null when the editor is not ready to answer.
function electronTransform() {
  if (!ketcherInstance) return null
  try {
    const render = ketcherInstance.editor.render
    const a = render.page2obj({ clientX: 0, clientY: 0 })
    const b = render.page2obj({ clientX: 100, clientY: 100 })
    const sx = 100 / (b.x - a.x)
    const sy = 100 / (b.y - a.y)
    if (!isFinite(sx) || !isFinite(sy) || sx === 0) return null
    return { sx: sx, sy: sy, tx: -a.x * sx, ty: -a.y * sy }
  } catch (e) {
    return null
  }
}

function sameTransform(a, b) {
  if (!a || !b) return false
  return a.sx === b.sx && a.sy === b.sy && a.tx === b.tx && a.ty === b.ty
}

// The label Ketcher will draw, composed from the STRUCT rather than read
// back off the canvas -- `label` plus implicit hydrogens plus charge.
// Carbon is normally unlabelled, so it contributes no obstacle.
function atomLabelText(atom) {
  if (!atom || !atom.label) return ''
  if (atom.label === 'C' && !atom.charge && !atom.isotope) return ''
  let text = atom.label
  if (atom.implicitH > 0) text += atom.implicitH > 1 ? 'H' + atom.implicitH : 'H'
  if (atom.charge) text += atom.charge > 0 ? '+' : '-'
  return text
}

// Measured in OUR OWN svg at Ketcher's font size, cached per string, and
// returned in MODEL UNITS so it is zoom-invariant. Never reads Ketcher's
// DOM. `options.font` is a CSS shorthand ("30px Arial") rather than a
// family, so the size is set separately or the box comes back at 30px.
function labelBoxModelUnits(text) {
  if (!text) return null
  if (electronState.labelBoxes[text]) return electronState.labelBoxes[text]
  electronWork.labelMeasurements++
  const options = ketcherInstance.editor.render.options
  const unit = options.microModeScale || options.bondLength || 40
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg')
  svg.setAttribute('style', 'position:absolute;left:-9999px;top:0;width:200px;height:60px')
  document.body.appendChild(svg)
  const node = document.createElementNS('http://www.w3.org/2000/svg', 'text')
  node.setAttribute('font-size', options.fontsz || 13)
  node.setAttribute('font-family', 'Arial')
  node.textContent = text
  svg.appendChild(node)
  const box = node.getBBox()
  document.body.removeChild(svg)
  const padding = LABEL_PADDING_FRACTION
  const measured = {
    halfWidth: box.width / 2 / unit + padding,
    halfHeight: box.height / 2 / unit + padding,
  }
  electronState.labelBoxes[text] = measured
  return measured
}

function separationDegrees(a, b) {
  return Math.abs((((a - b + 180) % 360) + 360) % 360 - 180)
}

// A slot is rejected outright when its DOTS would land inside the label
// box -- not when its direction points at the box, which would forbid
// every bearing on that side of a wide label like NH3+.
function slotHitsLabel(bearing, box) {
  if (!box) return false
  const radians = (bearing * Math.PI) / 180
  const radius = SLOT_RADIUS_FRACTION
  const gap = PAIR_HALF_GAP_FRACTION
  const cx = radius * Math.cos(radians)
  const cy = radius * Math.sin(radians)
  const px = -Math.sin(radians) * gap
  const py = Math.cos(radians) * gap
  const dots = [
    [cx + px, cy + py],
    [cx - px, cy - py],
  ]
  for (let i = 0; i < dots.length; i++) {
    if (Math.abs(dots[i][0]) <= box.halfWidth && Math.abs(dots[i][1]) <= box.halfHeight) {
      return true
    }
  }
  return false
}

function bondClearance(bearing, bondBearings) {
  let worst = 180
  for (let i = 0; i < bondBearings.length; i++) {
    const gap = separationDegrees(bearing, bondBearings[i])
    if (gap < worst) worst = gap
  }
  return worst
}

// **JOINTLY, NOT GREEDILY.** Picking the best slot and then the next best
// lets two nearly-equivalent candidates trade places on a tiny geometry
// change, so an oxygen's pairs swap sides for no reason the user can
// see -- the same "why did it move when I didn't move it" this project
// already earned from the conformer viewer. Scoring the SET, with a fixed
// tie-break, is what makes the answer stable.
function chooseSlots(bondBearings, labelBox, pairCount) {
  if (pairCount <= 0) return []
  const candidates = []
  for (let d = -180; d < 180; d += SLOT_STEP_DEGREES) candidates.push(d)

  const tiers = [
    { bond: MIN_BOND_CLEARANCE_DEGREES, separation: MIN_SLOT_SEPARATION_DEGREES, label: true },
    { bond: MIN_BOND_CLEARANCE_DEGREES, separation: MIN_SLOT_SEPARATION_DEGREES, label: false },
    { bond: 15, separation: 30, label: false },
    { bond: 0, separation: 20, label: false },
  ]
  for (let t = 0; t < tiers.length; t++) {
    const tier = tiers[t]
    const allowed = candidates.filter(function (bearing) {
      if (bondClearance(bearing, bondBearings) < tier.bond) return false
      if (tier.label && slotHitsLabel(bearing, labelBox)) return false
      return true
    })
    const chosen = bestCombination(allowed, bondBearings, tier.separation, pairCount)
    if (chosen) return chosen
  }
  // Nothing satisfies even the loosest tier, so spread evenly and draw
  // SOMETHING: an atom that has pairs and shows none is a lie, and a
  // crowded drawing is merely ugly.
  const evenly = []
  for (let i = 0; i < pairCount; i++) evenly.push(-180 + (360 / pairCount) * i)
  return evenly
}

function bestCombination(allowed, bondBearings, minSeparation, pairCount) {
  if (allowed.length < pairCount) return null
  let best = null
  let bestScore = -Infinity
  const chosen = []

  function score(set) {
    let total = 0
    let closest = 360
    for (let i = 0; i < set.length; i++) {
      total += bondClearance(set[i], bondBearings)
      for (let j = i + 1; j < set.length; j++) {
        const gap = separationDegrees(set[i], set[j])
        if (gap < closest) closest = gap
      }
    }
    // The spread term is what stops two pairs hugging one open side when
    // the atom has a whole free hemisphere.
    return total + (set.length > 1 ? closest : 0)
  }

  function walk(start) {
    if (chosen.length === pairCount) {
      const value = score(chosen)
      // **DETERMINISTIC TIE-BREAK**: strictly greater, and the candidates
      // are walked in ascending order, so an exact tie keeps the set with
      // the smallest bearings. Without it two equal arrangements swap on
      // a rounding difference.
      if (value > bestScore + 1e-9) {
        bestScore = value
        best = chosen.slice()
      }
      return
    }
    for (let i = start; i < allowed.length; i++) {
      const bearing = allowed[i]
      let ok = true
      for (let k = 0; k < chosen.length; k++) {
        if (separationDegrees(bearing, chosen[k]) < minSeparation) {
          ok = false
          break
        }
      }
      if (!ok) continue
      chosen.push(bearing)
      walk(i + 1)
      chosen.pop()
    }
  }

  walk(0)
  return best
}

// A stable fingerprint of where the atoms are, so a redraw can tell a
// viewport change (nothing here moved) from a geometry change.
function atomPositionsKey(struct) {
  const parts = []
  struct.atoms.forEach(function (atom, id) {
    parts.push(id + ':' + atom.pp.x.toFixed(4) + ',' + atom.pp.y.toFixed(4))
  })
  return parts.join('|')
}

// Dots in MODEL UNITS, relative to nothing -- absolute model coordinates,
// so the layer's single transform can place all of them.
function computeElectronPlacement() {
  electronWork.placements++
  if (!ketcherInstance || !electronState.payload || electronState.payload.refused) return []
  const struct = ketcherInstance.editor.struct()
  const counts = electronState.payload.counts || {}
  // Molfile position -> pool id, by INSERTION ORDER, never sorted: the
  // inverse of molfilePosition(), and the two diverge the moment anything
  // is deleted.
  const poolIds = Array.from(struct.atoms.keys())
  const out = []

  Object.keys(counts).forEach(function (positionKey) {
    const pairs = counts[positionKey]
    if (!pairs) return
    const poolId = poolIds[parseInt(positionKey, 10)]
    if (poolId === undefined) return
    const atom = struct.atoms.get(poolId)
    if (!atom) return

    const bondBearings = []
    struct.bonds.forEach(function (bond) {
      let otherId = null
      if (bond.begin === poolId) otherId = bond.end
      else if (bond.end === poolId) otherId = bond.begin
      if (otherId === null) return
      const other = struct.atoms.get(otherId)
      if (!other) return
      bondBearings.push(
        (Math.atan2(other.pp.y - atom.pp.y, other.pp.x - atom.pp.x) * 180) / Math.PI
      )
    })

    const box = labelBoxModelUnits(atomLabelText(atom))
    const slots = chooseSlots(bondBearings, box, pairs)
    const dots = []
    slots.forEach(function (bearing) {
      const radians = (bearing * Math.PI) / 180
      const cx = atom.pp.x + SLOT_RADIUS_FRACTION * Math.cos(radians)
      const cy = atom.pp.y + SLOT_RADIUS_FRACTION * Math.sin(radians)
      const px = -Math.sin(radians) * PAIR_HALF_GAP_FRACTION
      const py = Math.cos(radians) * PAIR_HALF_GAP_FRACTION
      dots.push([cx + px, cy + py], [cx - px, cy - py])
    })
    out.push({ poolId: poolId, position: parseInt(positionKey, 10), pairs: pairs, dots: dots })
  })
  return out
}

function renderElectronDots() {
  const layer = ensureElectronLayer()
  while (electronGroup.firstChild) electronGroup.removeChild(electronGroup.firstChild)
  const placement = electronState.placement || []
  placement.forEach(function (entry) {
    entry.dots.forEach(function (dot) {
      const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle')
      circle.setAttribute('cx', dot[0])
      circle.setAttribute('cy', dot[1])
      // In model units, so the group's scale grows it with the drawing.
      circle.setAttribute('r', 0.045)
      circle.setAttribute('data-atom', String(entry.position))
      electronGroup.appendChild(circle)
    })
  })
  const payload = electronState.payload
  // The corner note, only when the mode is ON and the analysis could not
  // answer. Silence there would read as "this molecule has no lone
  // pairs", which is a claim `analyse` explicitly declined to make.
  electronNote.textContent =
    payload && payload.refused && electronState.mode !== 'off' ? payload.reason || '' : ''
  return layer
}

function applyElectronTransform(transform) {
  if (!electronLayer || !transform) return
  electronWork.transforms++
  const canvas = ketcherCanvas()
  if (canvas) {
    const host = electronLayer.parentNode.getBoundingClientRect()
    const rect = canvas.getBoundingClientRect()
    electronLayer.style.left = rect.left - host.left + 'px'
    electronLayer.style.top = rect.top - host.top + 'px'
    electronLayer.style.width = rect.width + 'px'
    electronLayer.style.height = rect.height + 'px'
  }
  const rect = canvas ? canvas.getBoundingClientRect() : { left: 0, top: 0 }
  // The layer is positioned at the canvas, so the group's translate is
  // the transform's offset relative to that corner.
  electronGroup.setAttribute(
    'transform',
    'translate(' +
      (transform.tx - rect.left) +
      ',' +
      (transform.ty - rect.top) +
      ') scale(' +
      transform.sx +
      ',' +
      transform.sy +
      ')'
  )
  electronState.transform = transform
}

// The tier dispatcher. Nothing does more than its tier: a viewport change
// rewrites one transform attribute, a geometry change recomputes
// placement, and the chemistry is recomputed by PYTHON only when the
// structure revision changes -- never here.
function refreshElectrons(force) {
  if (electronState.mode === 'off') {
    // **EMPTIED, not merely hidden.** Hiding alone leaves the previous
    // molecule's dots in the DOM, invisible and stale -- so any future
    // path that shows the layer before recomputing would flash the wrong
    // structure's electrons. The layer survives; its contents do not.
    if (electronLayer) {
      electronLayer.style.display = 'none'
      while (electronGroup.firstChild) electronGroup.removeChild(electronGroup.firstChild)
      electronNote.textContent = ''
    }
    electronState.placement = null
    electronState.positionsKey = null
    return
  }
  const layer = ensureElectronLayer()
  layer.style.display = ''
  const struct = ketcherInstance ? ketcherInstance.editor.struct() : null
  const key = struct ? atomPositionsKey(struct) : null
  if (force || key !== electronState.positionsKey) {
    electronState.positionsKey = key
    electronState.placement = computeElectronPlacement()
    renderElectronDots()
  }
  const transform = electronTransform()
  if (transform && !sameTransform(transform, electronState.transform)) {
    applyElectronTransform(transform)
  }
}

// Pan and zoom are announced by NOTHING -- `zoomChanged` does not fire for
// a real zoom, and Ketcher does not pan by scrolling, so there is no
// scroll event either. Both are viewBox changes, and both show up in the
// derived affine. Comparing it costs 0.009 ms against a 16 ms frame, so
// the layer watches. One loop for the life of the page.
function watchElectronViewport() {
  if (electronWatching) return
  electronWatching = true
  electronWork.watchers++
  const tick = function () {
    if (electronState.mode !== 'off' && ketcherInstance) {
      const transform = electronTransform()
      if (transform && !sameTransform(transform, electronState.transform)) {
        applyElectronTransform(transform)
      }
    }
    window.requestAnimationFrame(tick)
  }
  window.requestAnimationFrame(tick)
}

function setElectronOverlay(payload) {
  electronState.payload = payload
  electronState.mode = payload ? payload.mode || 'pairs' : 'off'
  electronState.positionsKey = null
  refreshElectrons(true)
  watchElectronViewport()
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
  // Same reason as the rotation assignment above: without a reference
  // reachable from the entry point vite tree-shakes the whole overlay
  // away and the feature is silently absent.
  window.openchemElectrons = {
    set: setElectronOverlay,
    refresh: function () {
      refreshElectrons(true)
    },
    work: function () {
      return JSON.stringify(electronWork)
    },
    resetWork: function () {
      electronWork.placements = 0
      electronWork.labelMeasurements = 0
      electronWork.transforms = 0
      return 1
    },
    state: function () {
      return JSON.stringify({
        mode: electronState.mode,
        refused: !!(electronState.payload && electronState.payload.refused),
        placement: (electronState.placement || []).map(function (entry) {
          return { position: entry.position, pairs: entry.pairs, dots: entry.dots }
        }),
      })
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
