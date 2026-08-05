"""The help window: a topic list, and the repository's markdown rendered.

QTextBrowser RATHER THAN A WEB VIEW, and that is a considered choice. Qt's
own markdown importer renders everything these documents use -- verified
against the real content, including GitHub pipe tables, fenced code blocks
and links -- so a web view would buy nothing and cost a great deal. Every
`QWebEngineView` spawns Chromium helper processes, and this project has
already had to write a test fixture to stop them accumulating (see
`dispose_web_engine_views` in tests/conftest.py). Help is the last place
worth paying that for.

Links are intercepted rather than followed. A relative link between the
documents (`USER_GUIDE.md#docking`) navigates inside this window, so the
cross-references the documents already contain keep working; an http link
goes to the browser, because rendering the open web in a help pane is
neither wanted nor safe.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from openchem import help as help_docs

logger = logging.getLogger("openchem.ui")

_DOCUMENT_LABELS = {
    "QUICKSTART.md": "Getting started",
    "USER_GUIDE.md": "Using the application",
    "SCIENTIFIC_LIMITATIONS.md": "What the numbers do and do not mean",
}

#: Short forms, for search-result rows where the full label would be
#: longer than the topic title it is qualifying.
_DOCUMENT_TAGS = {
    "QUICKSTART.md": "Setup",
    "USER_GUIDE.md": "Guide",
    "SCIENTIFIC_LIMITATIONS.md": "Limitations",
}


class HelpDialog(QDialog):
    """Non-modal, so it can be read WHILE using the thing it describes.

    A modal help window is close to useless for an application like this
    one -- the reason to open the docking section is to work through the
    docking panel with it visible.
    """

    def __init__(self, parent: QWidget | None = None, topic_key: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle("OpenChem Studio Help")
        self.resize(940, 680)
        self.setWindowFlag(Qt.WindowType.Window, True)

        self._query = ""
        self._current_key = ""
        self._current_document = ""
        self._filter = QLineEdit(self)
        self._filter.setPlaceholderText("Search the documentation...")
        self._filter.setClearButtonEnabled(True)
        self._filter.textChanged.connect(self._apply_filter)

        self._list = QListWidget(self)
        self._list.currentItemChanged.connect(self._on_topic_changed)

        self._view = QTextBrowser(self)
        self._view.setOpenLinks(False)
        self._view.setOpenExternalLinks(False)
        self._view.anchorClicked.connect(self._on_link)

        self._whole_document_button = QPushButton("Read the whole document", self)
        self._whole_document_button.clicked.connect(self._show_whole_document)

        self._status = QLabel("", self)
        self._status.setWordWrap(True)

        left = QWidget(self)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(self._filter)
        left_layout.addWidget(self._list, 1)

        right = QWidget(self)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(self._view, 1)
        controls = QHBoxLayout()
        controls.addWidget(self._whole_document_button)
        controls.addStretch(1)
        right_layout.addLayout(controls)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([260, 680])

        close_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        close_box.rejected.connect(self.close)

        layout = QVBoxLayout(self)
        layout.addWidget(splitter, 1)
        layout.addWidget(self._status)
        layout.addWidget(close_box)

        self._populate()
        self.show_topic(topic_key)

    # --- population --------------------------------------------------------

    def _populate(self) -> None:
        self._list.clear()
        current_document = ""
        for topic in help_docs.topics():
            if topic.document != current_document:
                current_document = topic.document
                header = QListWidgetItem(_DOCUMENT_LABELS.get(topic.document, topic.document))
                # A non-selectable separator row, so the list reads as
                # three grouped sections rather than twenty flat entries.
                header.setFlags(Qt.ItemFlag.NoItemFlags)
                font = header.font()
                font.setBold(True)
                header.setFont(font)
                self._list.addItem(header)
            # Sub-topics are indented so `IR spectra` visibly belongs to
            # `Quantum chemistry` rather than looking like a peer.
            indent = "    " * max(0, topic.level - 2)
            item = QListWidgetItem(f"{indent}{topic.title}")
            item.setData(Qt.ItemDataRole.UserRole, topic.key)
            self._list.addItem(item)

    def _apply_filter(self, text: str) -> None:
        """Show topics matching `text` anywhere in their body, best first.

        Two modes, because they want different layouts. With no query the
        list is the table of contents -- grouped by document, in document
        order, which is how you browse. With a query it becomes ranked
        search results with snippets, because relevance beats document
        order once you have asked a question.

        Keeping the group headers in browse mode is not decoration: two
        documents legitimately have a section called "Docking" -- how the
        panel works, and what its scores are worth.
        """
        query = text.strip()
        self._query = query
        if not query:
            self._populate()
            self.show_topic(self._current_key)
            self._status.setText(self._source_note())
            return

        hits = help_docs.search(query)
        self._list.clear()
        for hit in hits:
            # The document tag is on every row because search results have
            # no group headers to carry it, and the two "Docking" sections
            # -- how the panel works, and what its scores are worth -- are
            # both legitimate answers to searching "vina". Without the tag
            # they are two identical rows.
            label = f"{hit.topic.title}  -  {_DOCUMENT_TAGS.get(hit.topic.document, hit.topic.document)}"
            if not hit.in_title:
                label = f"{label}  ({hit.occurrences})"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, hit.topic.key)
            # The snippet goes in the tooltip rather than the row: a
            # two-line row makes the list unscannable, and the reason a
            # result matched is a follow-up question, not the first one.
            item.setToolTip(f"{_DOCUMENT_LABELS.get(hit.topic.document, hit.topic.document)}\n{hit.snippet}")
            self._list.addItem(item)

        if not hits:
            self._view.setMarkdown(f"Nothing in the documentation matches **{query}**.")
            self._status.setText("No matches.")
            return
        self._status.setText(f"{len(hits)} topic(s) mention '{query}'.")
        self._list.setCurrentRow(0)

    # --- navigation --------------------------------------------------------

    def show_topic(self, key: str) -> None:
        """Select and display `key`, falling back to the first topic."""
        target = key
        if not target:
            available = help_docs.topics()
            if not available:
                self._view.setMarkdown("Help is unavailable: no documents were found.")
                return
            target = available[0].key
        for row in range(self._list.count()):
            item = self._list.item(row)
            if item.data(Qt.ItemDataRole.UserRole) == target:
                self._list.setCurrentItem(item)
                return
        logger.warning("No help topic keyed %r", target)
        self._status.setText(f"No help topic named '{target}'.")

    def _on_topic_changed(self, current: QListWidgetItem | None, _previous) -> None:
        if current is None:
            return
        key = current.data(Qt.ItemDataRole.UserRole)
        if key is None:
            return
        try:
            topic = help_docs.topic(key)
            self._view.setMarkdown(help_docs.topic_markdown(key))
        except help_docs.HelpUnavailable as exc:
            self._view.setMarkdown(f"This help topic could not be loaded.\n\n`{exc}`")
            return
        self._current_key = key
        self._current_document = topic.document
        self._highlight_query()
        if not self._query:
            self._status.setText(self._source_note())

    def _source_note(self) -> str:
        if not self._current_document:
            return ""
        return f"docs/{self._current_document} - edit that file to change this page."

    def _highlight_query(self) -> None:
        """Mark every occurrence of the query and scroll to the first.

        Without this a search result opens at the top of a section that
        may be several screens long, leaving the reader to find the word
        themselves -- which is most of the work they were asking the search
        to do.
        """
        self._view.moveCursor(QTextCursor.MoveOperation.Start)
        if not self._query:
            self._view.setExtraSelections([])
            self._view.verticalScrollBar().setValue(0)
            return

        palette = self._view.palette()
        highlight = QTextCharFormat()
        # The palette's own highlight colours, so this stays legible under
        # a dark theme instead of being hard-coded yellow-on-black.
        highlight.setBackground(palette.highlight())
        highlight.setForeground(palette.highlightedText())

        selections: list[QTextEdit.ExtraSelection] = []
        cursor = QTextCursor(self._view.document())
        while True:
            cursor = self._view.document().find(self._query, cursor)
            if cursor.isNull():
                break
            selection = QTextEdit.ExtraSelection()
            selection.cursor = cursor
            selection.format = highlight
            selections.append(selection)
        self._view.setExtraSelections(selections)
        if selections:
            # Scrolls the view to the first hit.
            self._view.setTextCursor(selections[0].cursor)
            self._view.ensureCursorVisible()
        else:
            self._view.verticalScrollBar().setValue(0)

    def _show_whole_document(self) -> None:
        document = getattr(self, "_current_document", "")
        if not document:
            return
        try:
            self._view.setMarkdown(help_docs.document_markdown(document))
        except help_docs.HelpUnavailable as exc:
            self._view.setMarkdown(f"Could not load the document.\n\n`{exc}`")
            return
        self._view.verticalScrollBar().setValue(0)

    def _on_link(self, url: QUrl) -> None:
        """Keep cross-document links inside the help window.

        The documents link to each other by filename and anchor, which is
        what makes them readable on GitHub. Those links have to keep
        working here, so a relative one is resolved to a topic instead of
        being handed to a browser that would find no such file.
        """
        if url.scheme() in ("http", "https"):
            QDesktopServices.openUrl(url)
            return
        fragment = url.fragment()
        if fragment:
            for topic in help_docs.topics():
                # GitHub slugifies a heading into the anchor, so match on
                # the slug rather than expecting our key to appear in a
                # link somebody wrote for GitHub.
                if fragment in (topic.key, _slug(topic.title)):
                    self.show_topic(topic.key)
                    return
        path = url.path().rsplit("/", 1)[-1]
        if path in help_docs.HELP_DOCUMENTS:
            for topic in help_docs.topics():
                if topic.document == path:
                    self.show_topic(topic.key)
                    return
        self._status.setText(f"That link points outside the help documents ({url.toString()}).")


def _slug(title: str) -> str:
    """GitHub's heading-to-anchor rule, near enough for link matching."""
    kept = [character.lower() for character in title if character.isalnum() or character in " -"]
    return "".join(kept).strip().replace(" ", "-")
