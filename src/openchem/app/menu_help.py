"""The menu bar's help contracts, one dict keyed by a stable name.

Kept out of `app/main_window.py`, which is ~2900 lines before any of this.
The window's job is to BUILD the menus; what an entry MEANS is a separate
statement, and the panels already split it the same way one layer down.

ONE CONCEPT, ONE `help_id`, and three cases in here collapse:

    every dock's View toggle    ONE id, 13 renderings -- "show or hide this
                                panel" is one idea and WHICH panel differs,
                                exactly like the sixty batch tick boxes
    the three Help topics       ONE id -- "open the manual at this topic"
    explicit hydrogens          ONE id, TWO renderings: the SAME Ketcher
                                action is offered from Structure and from
                                View > 2D Structure Display under two
                                labels, deliberately, so it must not sprout
                                two contracts

`Copy Structure As` deliberately does NOT collapse. SMILES, InChI,
InChIKey and a molblock have genuinely different round-trip properties,
and choosing between them IS choosing between those properties -- which is
the one thing a reader needs said.

The four stereo-label styles and the two electron modes do not collapse
either: they are options of one setting, but each option means a different
display rule, and a reader picking between them needs the rules rather
than four copies of "sets the stereo label style".
"""

from __future__ import annotations

from openchem.ui.widgets.help_tooltip import HelpTooltip

_M = "menus"

MENU_HELP: dict[str, HelpTooltip] = {
    # --- File ----------------------------------------------------------
    "new_project": HelpTooltip(
        text=(
            "Starts an empty project. The current one is closed, so anything "
            "unsaved is offered for saving first."
        ),
        tier=1, help_id="file.new_project", topic=_M, help_anchor="projects",
    ),
    "open_project": HelpTooltip(
        text=(
            "Opens a saved project and replaces the current session with it -- "
            "molecules, receptors, crystals, and the results already computed "
            "for them."
        ),
        tier=1, help_id="file.open_project", topic=_M, help_anchor="projects",
    ),
    "save_project": HelpTooltip(
        text=(
            "Writes the whole project to one file: every structure, and the "
            "results computed for them with the provenance that says how.\n\n"
            "A macromolecule and a crystal are stored as their ORIGINAL file "
            "text rather than as a parse, so a later reader improvement reaches "
            "projects that were saved before it existed."
        ),
        tier=2, help_id="file.save_project", topic=_M, help_anchor="projects",
    ),
    "new_molecule": HelpTooltip(
        text="Adds an empty molecule to the project and selects it for drawing.",
        tier=1, help_id="file.new_molecule", topic=_M, help_anchor="projects",
    ),
    "import_molecule": HelpTooltip(
        text=(
            "Reads a molecular structure file and adds it to the project as a "
            "new molecule."
        ),
        tier=1, help_id="file.import_molecule", topic=_M,
        help_anchor="structure-clipboard",
    ),
    "export_molecule": HelpTooltip(
        text=(
            "Writes the selected molecule to a structure file, in the format "
            "chosen by the extension you give it."
        ),
        tier=1, help_id="file.export_molecule", topic=_M,
        help_anchor="structure-clipboard",
    ),
    "import_macromolecule": HelpTooltip(
        text=(
            "Reads a PDB or mmCIF deposition -- a protein, nucleic acid or "
            "complex -- and adds it as a macromolecule rather than as a "
            "molecule.\n\n"
            "The deposited text is kept as it came, which is what the viewer "
            "renders and what docking runs against."
        ),
        tier=2, help_id="file.import_macromolecule", topic=_M,
        help_anchor="docking",
    ),
    "import_crystal": HelpTooltip(
        text=(
            "Reads a CIF and adds it as a CRYSTAL rather than as a molecule.\n\n"
            "Its own entry because a periodic solid is not a molecule: it has no "
            "bonds and no molecular weight, so routing a CIF through the "
            "molecule importer would put a structure into the project that every "
            "molecular calculator would then try to answer about."
        ),
        tier=2, help_id="file.import_crystal", topic=_M, help_anchor="projects",
    ),
    "receptor_library": HelpTooltip(
        text=(
            "Opens the curated docking-target catalogue. Each entry carries a "
            "prepared binding-site box, so a receptor can be fetched and docked "
            "without locating its site by hand.\n\n"
            "A fetched structure is cached locally, so it is downloaded once."
        ),
        tier=2, help_id="file.receptor_library", topic=_M, help_anchor="docking",
    ),
    "exit": HelpTooltip(
        text=(
            "Closes the application, offering to save the project first. The "
            "window size and panel layout are remembered for next time."
        ),
        tier=1, help_id="file.exit", topic=_M, help_anchor="projects",
    ),
    # --- Edit ----------------------------------------------------------
    "undo": HelpTooltip(
        text=(
            "Reverses the last change, and NAMES it -- the entry reads \"Undo "
            "Add molecule\" rather than a bare \"Undo\", so it says what is about "
            "to happen.\n\n"
            "It covers structure edits, conformer adoption and project-level "
            "changes. It does NOT cancel a calculation that has already been "
            "submitted; use the panel's own Cancel for that."
        ),
        tier=2, help_id="edit.undo", topic=_M, help_anchor="structure-clipboard",
    ),
    "redo": HelpTooltip(
        text="Re-applies the change most recently undone.",
        tier=1, help_id="edit.redo", topic=_M, help_anchor="structure-clipboard",
    ),
    "copy_smiles": HelpTooltip(
        text=(
            "Copies the selected structure to the clipboard as SMILES.\n\n"
            "Compact, readable, and it carries stereochemistry. It carries NO "
            "coordinates, so the drawing's layout and any conformer are lost in "
            "the trip."
        ),
        tier=2, help_id="edit.copy_as_smiles", topic=_M,
        help_anchor="structure-clipboard",
    ),
    "copy_inchi": HelpTooltip(
        text=(
            "Copies the selected structure to the clipboard as InChI.\n\n"
            "A canonical identifier: two different drawings of one compound give "
            "the same InChI, which SMILES does not guarantee. It carries no "
            "coordinates."
        ),
        tier=2, help_id="edit.copy_as_inchi", topic=_M,
        help_anchor="structure-clipboard",
    ),
    "copy_inchikey": HelpTooltip(
        text=(
            "Copies the selected structure as an InChIKey -- the fixed-length "
            "hash of its InChI.\n\n"
            "IT IS A LOOKUP KEY, NOT A STRUCTURE. Nothing can reconstruct the "
            "molecule from it, so it is what you search a database with and not "
            "what you move a structure between programs with."
        ),
        tier=3, help_id="edit.copy_as_inchikey", topic=_M,
        help_anchor="structure-clipboard",
    ),
    "copy_molfile": HelpTooltip(
        text=(
            "Copies the selected structure as an MDL molblock.\n\n"
            "The only one of these four that carries COORDINATES, so it is the "
            "one to use when the drawing's layout or a 3D geometry has to "
            "survive."
        ),
        tier=2, help_id="edit.copy_as_molfile", topic=_M,
        help_anchor="structure-clipboard",
    ),
    "paste_structure": HelpTooltip(
        text=(
            "Reads a structure from the clipboard -- SMILES, InChI or a molblock "
            "-- and adds it to the project as a new molecule.\n\n"
            "Deliberately NOT Ctrl+V: inside the drawing canvas Ketcher owns that "
            "key for pasting fragments, and taking it would break in-canvas "
            "editing to serve the rarer whole-structure case."
        ),
        tier=2, help_id="edit.paste_structure", topic=_M,
        help_anchor="structure-clipboard",
    ),
    "duplicate_molecule": HelpTooltip(
        text=(
            "Adds a copy of the selected molecule to the project. The copy is "
            "independent -- editing it leaves the original alone -- and it starts "
            "with no results of its own."
        ),
        tier=1, help_id="edit.duplicate_molecule", topic=_M,
        help_anchor="projects",
    ),
    "rename_molecule": HelpTooltip(
        text=(
            "Changes the selected molecule's display name. The name is a label "
            "only: it is not an identifier and nothing is looked up from it."
        ),
        tier=1, help_id="edit.rename_molecule", topic=_M, help_anchor="projects",
    ),
    # --- Structure -----------------------------------------------------
    "aromatize": HelpTooltip(
        text=(
            "Redraws rings that qualify as aromatic in the circle form, through "
            "the editor's own Aromatize.\n\n"
            "It changes the DRAWING, not the compound: the structure it "
            "represents is the same one, and it lands on the undo stack like any "
            "other edit."
        ),
        tier=2, help_id="structure.aromatize", topic=_M, help_anchor="centre-tabs",
    ),
    "dearomatize": HelpTooltip(
        text=(
            "Redraws aromatic rings in alternating single/double (Kekule) form, "
            "through the editor's own Dearomatize. The reverse of Aromatize, and "
            "the same compound either way."
        ),
        tier=2, help_id="structure.dearomatize", topic=_M,
        help_anchor="centre-tabs",
    ),
    "layout": HelpTooltip(
        text=(
            "Recomputes the drawing's coordinates from scratch, giving a clean "
            "standard depiction.\n\n"
            "IT DISCARDS THE ARRANGEMENT YOU DREW, including a layout adopted "
            "from a 3D conformer. The compound is unchanged; only its picture "
            "moves."
        ),
        tier=2, help_id="structure.layout", topic=_M, help_anchor="centre-tabs",
    ),
    "clean_up": HelpTooltip(
        text=(
            "Tidies the existing drawing -- regularises bond lengths and angles "
            "-- while keeping the arrangement broadly as you drew it. The gentler "
            "of the two: Layout starts over."
        ),
        tier=2, help_id="structure.clean_up", topic=_M, help_anchor="centre-tabs",
    ),
    "explicit_hydrogens": HelpTooltip(
        text=(
            "Adds every implicit hydrogen to the drawing as a real atom, or "
            "removes them again.\n\n"
            "THIS IS A STRUCTURE EDIT AND NOT A DISPLAY OPTION. The new hydrogens "
            "are atoms with their own indices, so the atom numbering changes and "
            "calculators that count atoms or walk the graph will answer "
            "differently.\n\n"
            "Offered from both Structure and View so it can be found either way; "
            "it is the same action in both places."
        ),
        tier=3, help_id="structure.explicit_hydrogens", topic=_M,
        help_anchor="surprises",
    ),
    "cip_labels": HelpTooltip(
        text=(
            "Shows R/S and E/Z stereo descriptors on the drawing, recomputed "
            "whenever the structure changes.\n\n"
            "A DISPLAY TOGGLE, not a one-shot annotation: the labels follow later "
            "edits instead of going stale. It adds nothing to the undo stack.\n\n"
            "A descriptor is only shown where the drawing determines one -- an "
            "undefined centre stays unlabelled rather than being guessed at."
        ),
        tier=3, help_id="structure.cip_labels", topic=_M, help_anchor="surprises",
    ),
    "generate_conformers": HelpTooltip(
        text=(
            "Generates 3D conformers for the selected molecule and opens the "
            "options for how many and how hard to search.\n\n"
            "Conformers are what every 3D calculation runs on, so this is the "
            "step between a drawing and a geometry."
        ),
        tier=2, help_id="structure.generate_conformers", topic=_M,
        help_anchor="limits-conformers",
    ),
    "isotopes": HelpTooltip(
        text=(
            "Opens the periodic table on its Isotopes tab, for the element of "
            "the atom selected in the 2D editor.\n\n"
            "Every ground state of that element, with its natural abundance, "
            "half-life and decay modes -- and applying one writes the mass "
            "number onto the selected atom without disturbing any conformers "
            "already generated."
        ),
        tier=2, help_id="structure.isotopes", topic=_M,
        help_anchor="periodic-table",
    ),
    "check_structure": HelpTooltip(
        text=(
            "Runs this application's own structure checker and shows what it "
            "found, with a quick fix where one is safe.\n\n"
            "It disagrees with the editor's built-in checker deliberately on iron "
            "oxides and hypervalent iodine, which is why both are offered."
        ),
        tier=2, help_id="structure.check_structure", topic=_M,
        help_anchor="structure-check",
    ),
    "check_structure_indigo": HelpTooltip(
        text=(
            "Runs the EDITOR's own checker (Indigo) -- the opinion the canvas "
            "draws in red.\n\n"
            "Kept beside ours and clearly labelled because the two disagree on "
            "purpose: it is worth being able to read what the canvas is "
            "complaining about without confusing it for this application's "
            "verdict."
        ),
        tier=3, help_id="structure.check_structure_indigo", topic=_M,
        help_anchor="structure-check",
    ),
    "full_lewis": HelpTooltip(
        text=(
            "Opens a full Lewis structure -- bonding pairs, lone pairs and formal "
            "charges -- drawn by this application rather than by the editor.\n\n"
            "A SNAPSHOT of the structure as it was when opened: it does not "
            "follow later edits, and says so."
        ),
        tier=3, help_id="structure.full_lewis", topic=_M, help_anchor="surprises",
    ),
    # --- View ----------------------------------------------------------
    "panel_visibility": HelpTooltip(
        text=(
            "Shows or hides this panel. One right-hand panel is shown at a time, "
            "so revealing one replaces whichever was on screen.\n\n"
            "The layout is remembered between sessions."
        ),
        tier=1, help_id="view.panel_visibility", topic=_M, help_anchor="properties",
    ),
    "panel_rail_visibility": HelpTooltip(
        text=(
            "Shows or hides the navigation rail down the side of the window.\n\n"
            "It hides the way IN to the panels rather than any one panel, so with "
            "it off the panels are reached from this menu or the command "
            "palette instead."
        ),
        tier=1, help_id="view.panel_rail_visibility", topic=_M,
        help_anchor="properties",
    ),
    "show_carbon_labels": HelpTooltip(
        text=(
            "Draws the element symbol on carbon atoms, which are normally left as "
            "bare vertices.\n\n"
            "A drawing option only: it changes nothing about the structure and "
            "nothing that is calculated from it."
        ),
        tier=2, help_id="view.show_carbon_labels", topic=_M,
        help_anchor="centre-tabs",
    ),
    "show_valence": HelpTooltip(
        text=(
            "Marks atoms whose valence is abnormal for the element.\n\n"
            "A drawing option only. It flags what the editor considers unusual "
            "and is not this application's structure check."
        ),
        tier=2, help_id="view.show_valence", topic=_M,
        help_anchor="structure-check",
    ),
    "show_stereo_flags": HelpTooltip(
        text=(
            "Shows the ABS / AND / OR stereo-group flags on the drawing.\n\n"
            "These describe whether a centre is absolutely known, or known only "
            "relative to others in its group -- a different question from the R/S "
            "descriptor itself, which is the CIP toggle."
        ),
        tier=3, help_id="view.show_stereo_flags", topic=_M,
        help_anchor="surprises",
    ),
    "stereo_label_style_iupac": HelpTooltip(
        text=(
            "Shows a stereo group's label only where it adds information, "
            "following IUPAC practice. The editor's own default."
        ),
        tier=2, help_id="view.stereo_label_style_iupac", topic=_M,
        help_anchor="surprises",
    ),
    "stereo_label_style_classic": HelpTooltip(
        text=(
            "Shows stereo group labels except where the molecule has a single "
            "group, in which case the label says nothing and is hidden."
        ),
        tier=2, help_id="view.stereo_label_style_classic", topic=_M,
        help_anchor="surprises",
    ),
    "stereo_label_style_on": HelpTooltip(
        text=(
            "Always shows a stereo group's label, including where it adds "
            "nothing -- useful when comparing two drawings that must be marked "
            "the same way."
        ),
        tier=2, help_id="view.stereo_label_style_on", topic=_M,
        help_anchor="surprises",
    ),
    "stereo_label_style_off": HelpTooltip(
        text=(
            "Never shows stereo group labels. The stereochemistry is unchanged "
            "and still applies -- only the label is hidden."
        ),
        tier=2, help_id="view.stereo_label_style_off", topic=_M,
        help_anchor="surprises",
    ),
    "electron_display_off": HelpTooltip(
        text="Draws no electron annotation on the canvas.",
        tier=1, help_id="view.electron_display_off", topic=_M,
        help_anchor="centre-tabs",
    ),
    "electron_display_lone_pairs": HelpTooltip(
        text=(
            "Draws lone pairs as dots on the canvas.\n\n"
            "Drawn by this application ON TOP of the editor, because the editor "
            "cannot draw them itself. They are a calculated annotation and are "
            "recomputed when the structure changes; they add nothing to the undo "
            "stack."
        ),
        tier=3, help_id="view.electron_display_lone_pairs", topic=_M,
        help_anchor="centre-tabs",
    ),
    "open_3d_viewer_miew": HelpTooltip(
        text=(
            "Opens the EDITOR's own 3D viewer for the current structure, in its "
            "own window.\n\n"
            "It is Ketcher's viewer, not this application's: it shows the "
            "structure as drawn and carries none of the measurement or surface "
            "tools."
        ),
        tier=2, help_id="view.open_editor_3d_viewer", topic=_M,
        help_anchor="centre-tabs",
    ),
    "send_to_3d_viewer_tab": HelpTooltip(
        text=(
            "Sends the current drawing to this application's 3D tab.\n\n"
            "A drawing has no geometry, so it needs a conformer to be shown in "
            "3D; one is generated if none exists."
        ),
        tier=2, help_id="view.send_to_3d_viewer_tab", topic=_M,
        help_anchor="centre-tabs",
    ),
    "show_oxidation_states": HelpTooltip(
        text=(
            "Overlays per-atom oxidation states on this application's own "
            "depiction in the Structure Check panel.\n\n"
            "NOT drawn on the editor canvas, which belongs to the editor and "
            "cannot be annotated. It is kept in this menu anyway, beside the "
            "other display toggles, because that is where somebody looks for it."
        ),
        tier=3, help_id="view.show_oxidation_states", topic=_M,
        help_anchor="structure-check",
    ),
    # --- Tools ---------------------------------------------------------
    "periodic_table": HelpTooltip(
        text=(
            "Opens the periodic table, with each element's properties and the "
            "sources they came from."
        ),
        tier=1, help_id="tools.periodic_table", topic=_M,
        help_anchor="periodic-table",
    ),
    "identify_structure": HelpTooltip(
        text=(
            "Looks the selected structure up in an online chemical database to "
            "find names and identifiers for it.\n\n"
            "IT SENDS THE STRUCTURE OVER THE NETWORK, so it needs a connection "
            "and it is not the right route for anything confidential."
        ),
        tier=3, help_id="tools.identify_structure", topic=_M,
        help_anchor="naming",
    ),
    "virtual_screening": HelpTooltip(
        text=(
            "Opens virtual screening -- docking a set of molecules against one "
            "receptor and ranking them.\n\n"
            "The same dialog the Batch panel's own button opens; both routes "
            "exist because either is the natural one depending on where you "
            "start."
        ),
        tier=2, help_id="tools.virtual_screening", topic=_M,
        help_anchor="batch",
    ),
    "external_tools": HelpTooltip(
        text=(
            "Opens the settings for the optional external programs -- the docking "
            "and quantum-chemistry engines.\n\n"
            "These are installed by you and are not bundled; the features that "
            "need them stay unavailable until their paths are set here."
        ),
        tier=2, help_id="tools.external_tools", topic=_M,
        help_anchor="external-tools",
    ),
    "command_palette": HelpTooltip(
        text=(
            "Opens a searchable list of everything reachable -- panels, "
            "calculators and menu entries -- and runs what you pick.\n\n"
            "It reads the live menus and the calculator registry rather than a "
            "list kept beside them, so a newly added feature is in it because it "
            "exists."
        ),
        tier=2, help_id="tools.command_palette", topic=_M, help_anchor="menus",
    ),
    "search_facts": HelpTooltip(
        text=(
            "Searches the facts computed for the current structure and jumps to "
            "the one you pick."
        ),
        tier=1, help_id="tools.search_facts", topic=_M,
        help_anchor="atom-inspector",
    ),
    # --- Plugins -------------------------------------------------------
    "reload_plugins": HelpTooltip(
        text=(
            "Re-reads the plugin folders and rebuilds what they contribute, "
            "without restarting.\n\n"
            "A plugin edited on disk takes effect here; one that fails to load "
            "reports why rather than disappearing."
        ),
        tier=2, help_id="plugins.reload", topic=_M, help_anchor="plugins",
    ),
    "open_project_plugins_folder": HelpTooltip(
        text=(
            "Opens the folder holding plugins that belong to THIS project, so "
            "they travel with it."
        ),
        tier=1, help_id="plugins.open_project_folder", topic=_M,
        help_anchor="plugins",
    ),
    "open_user_plugins_folder": HelpTooltip(
        text=(
            "Opens the folder holding plugins available in EVERY project on this "
            "machine."
        ),
        tier=1, help_id="plugins.open_user_folder", topic=_M,
        help_anchor="plugins",
    ),
    "no_plugins_installed": HelpTooltip(
        text=(
            "No plugins were found. This entry is a placeholder rather than a "
            "command -- put a plugin in one of the folders above and use Reload "
            "Plugins."
        ),
        tier=1, help_id="plugins.none_installed", topic=_M, help_anchor="plugins",
    ),
    # --- Help ----------------------------------------------------------
    "help_current_panel": HelpTooltip(
        text=(
            "Opens the manual at whichever panel is in front, rather than at a "
            "table of contents -- the question is almost always about what is on "
            "screen."
        ),
        tier=1, help_id="help.current_panel", topic=_M, help_anchor="in-app-help",
    ),
    "help_topic": HelpTooltip(
        text="Opens the manual at this topic.",
        tier=1, help_id="help.topic", topic=_M, help_anchor="in-app-help",
    ),
    "open_log_folder": HelpTooltip(
        text=(
            "Opens the folder holding this application's log files -- what to "
            "attach to a bug report."
        ),
        tier=1, help_id="help.open_log_folder", topic=_M,
        help_anchor="where-data-lives",
    ),
    "about": HelpTooltip(
        text=(
            "Shows the version, the licence, and the third-party components this "
            "application is built on."
        ),
        tier=1, help_id="help.about", topic=_M, help_anchor="in-app-help",
    ),
}
