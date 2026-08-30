"""Getting a unit cell onto the screen, without the UI learning chemistry.

The spike measured 3Dmol parsing a CIF and applying its symmetry, and
leaving 3 of halite's 4 chlorides outside the cell. So the app does not
hand it a CIF: Python expands, wraps and deduplicates, and the viewer
draws what it is given. These tests guard that split.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from openchem.chem.cif import read_cif
from openchem.chem.crystal_analysis import scene_as_xyz, scene_for

import conftest

HALITE = Path("spikes/crystallography/halite.cif")
VIEWER_HTML = Path("src/openchem/resources/viewer3d/viewer.html")


def _scene(path: Path = HALITE) -> dict:
    return scene_for(read_cif(path.read_text(encoding="utf-8", errors="replace")))


# --- the scene is complete, and is plain data -------------------------------


def test_the_scene_carries_everything_the_viewer_needs():
    scene = _scene()

    assert set(scene) == {"atoms", "edges", "axes", "name", "spaceGroup", "xyz"}
    assert len(scene["atoms"]) == 8
    assert len(scene["edges"]) == 12
    assert [axis["label"] for axis in scene["axes"]] == ["a", "b", "c"]


def test_the_scene_is_json_serialisable():
    """It crosses into JavaScript through `runJavaScript`, so a domain
    object anywhere in it would fail at the boundary rather than here."""
    payload = json.dumps(_scene())

    assert json.loads(payload)["name"] == "Halite"


def test_the_scene_atoms_are_the_wrapped_ones():
    """**The whole reason this path exists.** Every atom must sit inside
    the box the edges draw -- 3Dmol's own expansion put three chlorides
    outside it."""
    scene = _scene()
    limit = max(max(point) for edge in scene["edges"] for point in edge)

    for atom in scene["atoms"]:
        for value in (atom["x"], atom["y"], atom["z"]):
            assert -1e-6 <= value <= limit + 1e-6


def test_the_scene_atoms_are_the_same_ones_the_report_counted():
    """One source of truth: the picture and the density are computed from
    the same expansion, so they cannot disagree about the cell contents."""
    crystal = read_cif(HALITE.read_text(encoding="utf-8"))
    scene = scene_for(crystal)

    from collections import Counter

    assert Counter(atom["element"] for atom in scene["atoms"]) == {
        element: int(count) for element, count in crystal.composition().items()
    }


def test_each_atom_names_the_site_it_came_from():
    """Halite's four chlorides are one crystallographic site. Carrying the
    label is what lets a click answer about the site rather than the
    arbitrary image that happened to be drawn."""
    scene = _scene()

    assert {atom["site"] for atom in scene["atoms"]} == {"Na1", "Cl1"}


# --- XYZ, not a molblock ----------------------------------------------------


def test_the_geometry_is_carried_as_xyz_because_a_cell_has_no_bonds():
    """A molblock would have to invent a bond table, and inventing bonds
    across a lattice is exactly what `domain/crystal.py` exists to avoid --
    an Na-Cl contact is not a bond."""
    xyz = scene_as_xyz(_scene())
    lines = xyz.splitlines()

    assert lines[0] == "8"
    assert lines[1] == "Halite"
    assert len(lines) == 10
    assert lines[2].split()[0] == "Na"


def test_the_xyz_atom_count_matches_its_atom_lines():
    """A count that disagrees with the body makes 3Dmol read garbage or
    stop early, and it fails silently either way."""
    for path in (HALITE,):
        xyz = scene_as_xyz(scene_for(read_cif(path.read_text(encoding="utf-8"))))
        lines = xyz.splitlines()
        assert int(lines[0]) == len(lines) - 2


@pytest.mark.parametrize("code", ["1511792", "1569411"])
def test_a_real_deposition_produces_a_drawable_scene(code):
    scene = _scene(Path(f"tests/fixtures/cif/{code}.cif"))

    assert scene["atoms"]
    assert int(scene["xyz"].splitlines()[0]) == len(scene["atoms"])
    json.dumps(scene)


# --- the viewer page and the Python that calls it stay in step --------------


def test_the_viewer_page_defines_the_function_python_calls():
    """The same class of mistake `test_ketcher_bundle_is_current.py`
    catches: Python names a JS function, and if the page does not define
    it the call fails silently inside the web view with nothing in the
    Python log."""
    page = VIEWER_HTML.read_text(encoding="utf-8")
    backend = Path("src/openchem/ui/widgets/mol3d_viewer_backend.py").read_text(
        encoding="utf-8"
    )

    called = set(re.findall(r"window\.openchemViewer\.(\w+)\(", backend))
    defined = set(re.findall(r"^\s{8}(\w+): function", page, re.MULTILINE))

    assert called, "the backend should call the viewer by name"
    assert called <= defined, f"called but not defined: {sorted(called - defined)}"


def test_the_crystal_path_does_not_ask_3dmol_to_parse_a_cif():
    """`addModel(cif, 'cif')` would re-introduce the unwrapped expansion
    the whole Python side exists to replace."""
    page = VIEWER_HTML.read_text(encoding="utf-8")
    crystal_block = page.split("function drawCrystal")[1]

    assert "'cif'" not in crystal_block
    assert "doAssembly" not in crystal_block
    assert "'xyz'" in crystal_block


def test_the_crystal_view_draws_no_bonds():
    """Stick style would draw 3Dmol's guessed bonds between ions."""
    page = VIEWER_HTML.read_text(encoding="utf-8")
    crystal_block = page.split("function drawCrystal")[1]

    assert "sphere" in crystal_block
    assert "stick" not in crystal_block


# --- the backend queues and excludes correctly ------------------------------


class _FakePage:
    def __init__(self) -> None:
        self.scripts: list[str] = []

    def runJavaScript(self, script: str, *_args) -> None:  # noqa: N802 - Qt name
        self.scripts.append(script)


@pytest.fixture
def backend(qapp):
    from openchem.ui.widgets.mol3d_viewer_backend import Mol3DViewerBackend

    widget = Mol3DViewerBackend()
    yield widget
    view = widget.widget()
    conftest.dispose(view)


def test_a_crystal_requested_before_the_page_is_ready_is_queued(backend):
    """`runJavaScript` before `loadFinished` is silently dropped, which is
    why every loader here queues."""
    backend._page_ready = False
    backend.load_crystal(_scene())

    assert backend._pending_crystal is not None


def test_loading_a_molecule_cancels_a_queued_crystal(backend):
    """One molecule, one ensemble, or one unit cell -- never a mixture.
    Whichever call came last is what the user asked for."""
    backend._page_ready = False
    backend.load_crystal(_scene())
    backend.load_conformer("dummy molblock")

    assert backend._pending_crystal is None
    # A queued load carries its camera decision with it, since the
    # structure key it was compared against will have moved on by the time
    # the page is ready. The molblock is the half this test is about.
    assert backend._pending_molblock[0] == "dummy molblock"


def test_loading_a_crystal_cancels_a_queued_molecule(backend):
    backend._page_ready = False
    backend.load_conformer("dummy molblock")
    backend.load_crystal(_scene())

    assert backend._pending_molblock is None
    assert backend._pending_crystal is not None


def test_the_queued_crystal_is_replayed_once_the_page_loads(backend):
    fake = _FakePage()
    backend._page = fake
    backend._page_ready = False
    backend.load_crystal(_scene())

    backend._on_load_finished(True)

    assert any("loadCrystal" in script for script in fake.scripts)
    assert backend._pending_crystal is None


def test_the_backend_sends_the_scene_it_was_given_unchanged(backend):
    """It is a pass-through. Any transformation here would be chemistry in
    `ui/`, and would let the picture drift from the report."""
    fake = _FakePage()
    backend._page = fake
    backend._page_ready = True
    scene = _scene()

    backend.load_crystal(scene)

    (script,) = fake.scripts
    sent = json.loads(script[len("window.openchemViewer.loadCrystal(") : -len(");")])
    assert sent == scene


# --- layering ---------------------------------------------------------------


def test_the_viewer_widget_does_not_import_the_chemistry_layer():
    """`show_crystal` takes a built scene precisely so that it does not
    have to."""
    import ast

    source = Path("src/openchem/ui/widgets/molecule_viewer3d_widget.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    imported = {n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}

    assert not any(name.startswith(("rdkit", "openchem.chem")) for name in imported)


def test_a_backend_without_crystal_support_says_so_rather_than_crashing(qapp):
    """MolStar is a sibling backend with no crystal path. An
    AttributeError raised from inside a signal handler is a much worse
    failure than a message naming the backend."""
    from PySide6.QtWidgets import QWidget

    from openchem.ui.widgets.molecule_viewer3d_widget import MoleculeViewer3DWidget

    class _Bare(QWidget):
        """A backend with no crystal path, as MolStar's is."""

    viewer = MoleculeViewer3DWidget.__new__(MoleculeViewer3DWidget)
    QWidget.__init__(viewer)
    viewer._backend = _Bare()

    with pytest.raises(NotImplementedError, match="_Bare"):
        viewer.show_crystal(_scene())

    viewer.setParent(None)
    viewer.deleteLater()
