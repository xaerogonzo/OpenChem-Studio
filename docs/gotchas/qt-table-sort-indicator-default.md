# A fresh QHeaderView's "sort indicator" already points at column 0, descending

**Symptom.** Populate a `QTableWidget` for the first time ever, call
`setSortingEnabled(True)` afterward (the standard idiom: disable sorting
during population so Qt doesn't re-sort after every single `setItem`,
then re-enable it), and the table comes up already sorted -- on its very
first display, before any user ever touched a header. It looks like a
bug in whatever just inserted the rows, not in the sort call.

**Cause.** Measured directly (PySide6, a bare `QTableWidget`, nothing
else touched):

```python
t = QTableWidget(0, 1)
print(t.horizontalHeader().sortIndicatorSection())  # 0
print(t.horizontalHeader().sortIndicatorOrder())     # SortOrder.DescendingOrder
```

A `QHeaderView` is born with a sort indicator already set to column 0,
descending -- NOT "no sort", despite nothing having clicked it.
`QTableWidget.setSortingEnabled(True)` re-applies "whatever column the
header is currently sorted by, if any" (the Qt docs' own wording), and
that "if any" is true from the moment the widget exists. The very first
`setSortingEnabled(True)` a table ever sees therefore sorts it, silently,
by column 0 descending.

**Why it hides.** If the data you just inserted happens to already be in
ascending order by column 0, a descending auto-sort visibly reverses it
and gets noticed immediately. If it happens to already be sorted
DESCENDING by whatever you call column 0 first (or the column holds
non-comparable/short data where the difference isn't obvious), this is
invisible -- the table looks exactly like "insertion order", and only a
test or a user that checks the SPECIFIC row order (not just row count)
ever catches it. Measured in this codebase: identical population code in
two sibling widgets, one looked fine (its natural build order happened to
already read correctly after a stray descending sort) and the other did
not.

**Fix.** Clear the indicator explicitly before re-enabling, so there is
nothing for a bare `setSortingEnabled(True)` to reapply:

```python
table.setSortingEnabled(False)
# ... populate rows ...
table.horizontalHeader().setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
table.setSortingEnabled(True)
```

`-1` is Qt's own "no column" value for a sort indicator section. A
LATER, real header click still sets a real indicator and sorts normally
afterward -- this only suppresses the phantom first-population sort.

**If a table should RESET any user sort on every fresh population**
(a new run, a new spectrum, a cleared filter), the same one line does
double duty: call it every time you repopulate, not just once at
construction, and a user's earlier header click never survives into the
next dataset.
