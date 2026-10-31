"""The Setup guide: the first tab of Settings > External Tools.

A person opening External Tools for the first time sees ten tabs and no hint of which they need. This
tab says, for each tool, what it is for, what stops working without it, whether to bother, and the one
next thing to do, with the links to get it and to read more. The per-tool tabs behind it are unchanged.

The table is data (`GUIDE`) so that a test can hold it to the catalogue: every tool tab has exactly one
row, every Help topic named exists, and every link is one the program already names (so the privacy
statement's host list needs no new line). The live status of a row is read from the tool's own tab
(`ToolTab.status_label`), never recomputed here, so the guide cannot say "ready" about a tool whose tab
says otherwise.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

import openchem.services.knowledge_vista as kv
import openchem.services.synthesis_planner_setup as planner
import openchem.services.tool_download_service as tools
from openchem.ui.dialogs import external_tools_help as help_text
from openchem.ui.widgets.help_tooltip import apply_help_tooltip

#: The tab's catalogue key. `ExternalToolsPages.show_tool` also accepts it, so a caller can open the guide.
GUIDE_KEY = "guide"

#: The tier of a tool most people want: a feature they will meet early stops working without it.
RECOMMENDED = "Recommended"
#: The tier of a tool nothing depends on, or that only adds a second opinion or a convenience.
OPTIONAL = "Optional"
#: The tier of a tool that needs its own environment or expertise, or whose measured limits make it a specialist choice.
ADVANCED = "Advanced"

#: Help topics (`help.topic` keys) the guide links to.
HELP_INSTALLING = "installing-external-tools"
#: The Help topic describing each External Tools tab.
HELP_TOOLS = "external-tools"


@dataclass(frozen=True)
class GuideLink:
    """One hyperlink: `target` is an https address, or `help:<topic key>`."""

    label: str
    target: str


@dataclass(frozen=True)
class GuideEntry:
    """What a first-time user needs to know about one tool, in the order they need it."""

    key: str
    tier: str
    what: str
    needed_for: str
    next_step: str
    links: tuple[GuideLink, ...] = ()
    #: A limit worth knowing before spending the time, stated as measured.
    caveat: str = ""


#: One row per tool tab, in the order a first-time user should consider them (what most people need first).
GUIDE: tuple[GuideEntry, ...] = (
    GuideEntry(
        key="java",
        tier=RECOMMENDED,
        what="A Java runtime, which the name-to-structure parser (OPSIN) is written in.",
        needed_for="Typing or pasting a chemical NAME and getting a structure. Without it, name lookup is unavailable.",
        next_step="Press Set Up on the Java tab. It downloads a small portable runtime; nothing is installed on your system.",
        links=(GuideLink("Read more", f"help:{HELP_INSTALLING}"),),
    ),
    GuideEntry(
        key="vina",
        tier=RECOMMENDED,
        what="AutoDock Vina, a docking program: it tries poses of a molecule in a protein's binding site.",
        needed_for="The Docking panel and virtual screening.",
        next_step="Press Set Up Automatically on the AutoDock Vina tab. It is a public, Apache-2.0 download and the app asks before fetching it.",
        links=(
            GuideLink("Releases page", tools.VINA_RELEASES_PAGE),
            GuideLink("Read more", f"help:{HELP_TOOLS}"),
        ),
        caveat=(
            "Treat the score as a way to compare poses and rank within one series of related molecules, not as a measured binding "
            "affinity, and look at the pose before trusting it."
        ),
    ),
    GuideEntry(
        key="orca",
        tier=RECOMMENDED,
        what="ORCA, a full quantum-chemistry program (DFT and wavefunction methods). The main engine here.",
        needed_for=(
            "Quantum Chemistry: geometry optimization, NMR, orbitals, Fukui functions, proton affinity, bond dissociation. "
            "Without it those calculations are unavailable; everything else works."
        ),
        next_step=(
            "Register for the free academic download, install it somewhere whose path has NO spaces (for example C:\\ORCA), "
            "then press Locate Installed or Browse on the ORCA tab and run Test."
        ),
        links=(
            GuideLink("Download ORCA", tools.ORCA_DOWNLOAD_PAGE),
            GuideLink("ORCA manual", tools.ORCA_DOCS_PAGE),
            GuideLink("Read more", f"help:{HELP_INSTALLING}"),
        ),
        caveat="The app cannot download ORCA for you: it needs a registration and licence agreement with its authors.",
    ),
    GuideEntry(
        key="psi4",
        tier=OPTIONAL,
        what="Psi4, a second open-source quantum-chemistry program.",
        needed_for="Nothing on its own. It is a cross-check for ORCA, chosen in the Engine box on the Quantum Chemistry panel.",
        next_step="Skip it unless you want a second opinion. If you do, install it, then Locate Installed or Browse and run Test.",
        links=(GuideLink("Psi4 install page", tools.PSI4_DOWNLOAD_PAGE),),
        caveat="A full install is about 2 GB on disk.",
    ),
    GuideEntry(
        key="xtb",
        tier=ADVANCED,
        what="xtb, a very fast but approximate (tight-binding) quantum-chemistry program.",
        needed_for="Nothing on its own. It is a quick way to get a rough optimized structure, chosen in the Engine box.",
        next_step="Skip it unless you want speed over accuracy. If you do, download the Windows build, unzip it, then Locate Installed and run Test.",
        links=(
            GuideLink("xtb releases", tools.XTB_DOWNLOAD_PAGE),
            GuideLink("Read more", f"help:{HELP_TOOLS}"),
        ),
        caveat=(
            "Measured against ORCA on 20 molecules: its structures are close, but its energy differences are not reliable for ranking "
            "isomers or conformers. If you have ORCA, use ORCA for anything you will rely on."
        ),
    ),
    GuideEntry(
        key="pkasolver",
        tier=OPTIONAL,
        what="pkasolver, a machine-learning pKa predictor that runs in its own Python environment.",
        needed_for="Predicted pKa values, and calculations that depend on the charge state at a chosen pH.",
        next_step="Press Set Up Automatically on the pkasolver tab. It builds a separate environment; the app asks first and says how big it is.",
    ),
    GuideEntry(
        key="admet",
        tier=OPTIONAL,
        what="ADMET-AI, machine-learning predictions of hERG, CYP inhibition, Ames mutagenicity and related endpoints.",
        needed_for="The ADMET calculator. It needs PyTorch (about 490 MB), so it lives in an environment of its own.",
        next_step="Press Set Up Automatically on the ADMET tab. The app shows the size and asks before downloading.",
    ),
    GuideEntry(
        key="nmr_index",
        tier=OPTIONAL,
        what="An index of assigned experimental NMR spectra.",
        needed_for="The fast, lookup-based NMR shift prediction, which also reports how many measurements back each shift.",
        next_step="Press Set Up on the NMR Database tab. The app shows the download size and asks first.",
    ),
    GuideEntry(
        key="aizynthfinder",
        tier=ADVANCED,
        what="AiZynthFinder, a retrosynthesis planner: it proposes routes to a molecule from purchasable compounds.",
        needed_for="The Synthesis panel. It runs as a separate program in its own Python environment (3.10 to 3.12) with model and stock files.",
        next_step=(
            "Only for people who already work with it: install it following its own documentation, then point the tab at its Python "
            "and its configuration file and run Test."
        ),
        links=(
            GuideLink("AiZynthFinder project", planner.PROJECT_PAGE),
            GuideLink("Documentation", planner.DOCS_PAGE),
        ),
        caveat="A route is a lead to check, not a recipe. In testing it recovered the published route for about 1 in 4 recent targets.",
    ),
    GuideEntry(
        key="knowledge_vista",
        tier=OPTIONAL,
        what="Knowledge Vista, a separate program that indexes a folder of papers.",
        needed_for="Nothing in OpenChem Studio depends on it. It is for people who keep a library of papers.",
        next_step="Skip it unless you keep a paper library.",
        links=(GuideLink("Project page", kv.PROJECT_PAGE),),
    ),
)

#: "I want to..." choices: the tools each one needs (the Recommended ones first), so the page can show only those.
TASKS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Show everything", ()),
    ("Turn a chemical name into a structure", ("java",)),
    ("Dock a molecule into a protein", ("vina",)),
    ("Run quantum-chemistry calculations", ("orca", "psi4", "xtb")),
    ("Predict pKa or ADMET properties", ("pkasolver", "admet")),
    ("Predict NMR shifts", ("nmr_index", "orca")),
    ("Suggest a synthesis route", ("aizynthfinder",)),
)

#: The colour of each tier's word in a row: green for Recommended, grey for Optional, amber for Advanced.
_TIER_COLOURS = {RECOMMENDED: "#2e7d32", OPTIONAL: "#666666", ADVANCED: "#8a6d3b"}


def entry_for(key: str) -> GuideEntry | None:
    """The guide row for a catalogue key, or None."""
    for entry in GUIDE:
        if entry.key == key:
            return entry
    return None


def row_html(entry: GuideEntry, title: str, status: str) -> str:
    """One row as rich text. Every value is escaped; links are the only markup that is not."""
    colour = _TIER_COLOURS.get(entry.tier, "#666666")
    links = " &middot; ".join(
        f'<a href="{escape(link.target, quote=True)}">{escape(link.label)}</a>' for link in entry.links
    )
    parts = [
        f"<b>{escape(title)}</b> &nbsp;<span style='color:{colour}'>{escape(entry.tier)}</span>",
        escape(entry.what),
        f"<b>Needed for:</b> {escape(entry.needed_for)}",
        f"<b>What to do:</b> {escape(entry.next_step)} "
        f"<a href='tab:{escape(entry.key, quote=True)}'>Open the {escape(title)} tab</a>",
    ]
    if entry.caveat:
        parts.append(f"<span style='color:#8a6d3b'><b>Worth knowing:</b> {escape(entry.caveat)}</span>")
    if links:
        parts.append(links)
    parts.append(f"<b>Status now:</b> {escape(status)}")
    return "<br>".join(parts)


class GuideTab(QWidget):
    """The guide page. `statuses` is called on every refresh and returns catalogue key -> (tab title, status line)."""

    def __init__(self, parent: QWidget, *, statuses, open_tab, open_help, open_url) -> None:
        super().__init__(parent)
        self._statuses = statuses
        self._open_tab = open_tab
        self._open_help = open_help
        self._open_url = open_url
        self._rows: dict[str, QLabel] = {}
        self._frames: dict[str, QFrame] = {}

        intro = QLabel(
            "<b>Which of these do I need?</b><br>OpenChem Studio works without any of them. Each one adds a group of "
            "features. Start with the ones marked <span style='color:#2e7d32'>Recommended</span>; the rest are optional.",
            self,
        )
        intro.setWordWrap(True)
        intro.setTextFormat(Qt.TextFormat.RichText)

        self.task_combo = QComboBox(self)
        for label, _keys in TASKS:
            self.task_combo.addItem(label)
        apply_help_tooltip(self.task_combo, help_text.GUIDE_TASK)
        self.task_combo.currentIndexChanged.connect(self._apply_task)
        chooser = QHBoxLayout()
        chooser.addWidget(QLabel("I want to:", self))
        chooser.addWidget(self.task_combo, 1)

        body = QWidget(self)
        body_layout = QVBoxLayout(body)
        for entry in GUIDE:
            frame = QFrame(body)
            frame.setFrameShape(QFrame.Shape.StyledPanel)
            inner = QVBoxLayout(frame)
            label = QLabel(frame)
            label.setWordWrap(True)
            label.setTextFormat(Qt.TextFormat.RichText)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
            label.linkActivated.connect(self._on_link)
            inner.addWidget(label)
            body_layout.addWidget(frame)
            self._rows[entry.key] = label
            self._frames[entry.key] = frame
        body_layout.addStretch(1)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setWidget(body)

        footer = QLabel(f"<a href='help:{HELP_TOOLS}'>Read the full External Tools help</a>", self)
        footer.linkActivated.connect(self._on_link)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addLayout(chooser)
        layout.addWidget(scroll, 1)
        layout.addWidget(footer)
        self.refresh()

    def refresh(self) -> None:
        """Re-read each tool tab's own status line into its row."""
        known = self._statuses()
        for entry in GUIDE:
            title, status = known.get(entry.key, (entry.key, "unknown"))
            self._rows[entry.key].setText(row_html(entry, title, status))
        self._apply_task()

    def _apply_task(self, _index: int = 0) -> None:
        wanted = TASKS[self.task_combo.currentIndex()][1]
        for key, frame in self._frames.items():
            frame.setVisible(not wanted or key in wanted)

    def _on_link(self, target: str) -> None:
        if target.startswith("tab:"):
            self._open_tab(target[4:])
        elif target.startswith("help:"):
            self._open_help(target[5:])
        elif target.startswith("https://"):
            self._open_url(target)
