"""Generating conformers must not require a trip to the 3D Viewer tab.

Reported three times across one session, most recently: *"you should be
able to rotate even a 2d structure in the 2d editor, I still low key am
not much of a fan having to go into a 3d viewer to even generate
conformers still. With Marvin, it was a calculator like any other, there
was no dedicated 3d viewer that was required to go into in order to do
basic functions."*

It was measurable rather than a matter of taste: generation had **one**
entry point -- a button inside `MoleculeViewer3DWidget` -- and four
separate messages elsewhere in the app told the reader to go there.
"""

from __future__ import annotations

import pytest

from openchem.app.main_window import MainWindow


@pytest.fixture(scope="module")
def window(qapp, tmp_path_factory):
    """One real window for the file; `tests/conftest.py` retains every
    MainWindow for the session on purpose."""
    from openchem.app.session import SessionManager
    from openchem.app.settings import Settings
    from openchem.bootstrap import build_service_container

    directory = tmp_path_factory.mktemp("conformer_routes")
    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(directory / "none"))
    settings.set("plugins/user_directory", str(directory / "none2"))
    return MainWindow(services, settings, SessionManager())


def _menu_entry(window, label: str):
    for text, _menu, action in window._menu_actions():
        if text == label:
            return action
    return None


def test_conformers_can_be_generated_from_the_structure_menu(window):
    """Where people already look, rather than inside a viewer they had no
    other reason to open."""
    assert _menu_entry(window, "Generate Conformers...") is not None, (
        "no Structure menu route into conformer generation"
    )


def test_the_menu_action_and_the_palette_entry_are_the_SAME_action(window):
    """**One action identity, not two routes to one service.**

    The palette reads the live `QMenuBar`, so this holds by construction
    -- which is exactly why it is worth asserting rather than assuming:
    if somebody later gives the palette its own bespoke entry, the two
    drift apart in enable state and shortcut while both appearing to
    work.
    """
    action = _menu_entry(window, "Generate Conformers...")
    matches = [
        command
        for command in window._collect_commands()
        if "Generate Conformers" in command.label
    ]

    assert matches, "the palette does not offer conformer generation"
    # `run` is the QAction's own bound `trigger`, so its `__self__` IS
    # the action -- identity, not "calls something equivalent".
    assert any(getattr(command.run, "__self__", None) is action for command in matches), (
        "the palette's entry is not the Structure menu's action"
    )


def test_generation_has_one_implementation_reached_two_ways(window):
    """The window delegates to the viewer's own method rather than
    rebuilding the dialog and the service call. Two routes to one action
    is the point; two implementations of it is the bug this project keeps
    finding."""
    import inspect

    source = inspect.getsource(MainWindow._generate_conformers)

    assert "generate_conformers()" in source
    assert "ConformerOptionsDialog" not in source, (
        "the menu route builds its own dialog instead of reusing the widget's"
    )


def test_nothing_tells_the_reader_to_go_to_the_3d_viewer_tab():
    """THE FOUR SIGNPOSTS, and a guard so they cannot come back.

    `descriptor_providers.py`, `geometry_analysis.py`,
    `projection_geometry.py` and `quantum_chemistry_panel.py` each told
    the reader to switch tabs to do a basic thing. They name the action
    now.

    Docstrings are exempt: "Send to 3D Viewer Tab" is a real feature and
    its own documentation is allowed to say so. Only strings a user can
    read are checked.
    """
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent / "src" / "openchem"
    offenders: list[tuple[str, str]] = []
    for path in root.rglob("*.py"):
        if "resources" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docstrings = set()
        for node in ast.walk(tree):
            body = getattr(node, "body", None)
            if isinstance(body, list) and body:
                first = body[0]
                if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                    if isinstance(first.value.value, str):
                        docstrings.add(id(first.value))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            if id(node) in docstrings:
                continue
            text = node.value.lower()
            # The offence is telling the reader to GO somewhere to get a
            # conformer -- not naming an action. "Send to 3D Viewer Tab"
            # is a real feature and is allowed to say what it is; a
            # message pairing the tab with conformers is the signpost.
            if "3d viewer" in text and "conformer" in text:
                offenders.append((str(path.relative_to(root)), node.value[:70]))

    assert not offenders, f"still sending the reader to another tab: {offenders}"
