"""TRIAGE 2.8: freeze Ionescu 2013 Table S2 as a fixture, read POSITIONALLY.

    uvx --with pymupdf python ionescu_s2_extract.py <ci400448n_si_002.pdf> <out.csv>

The page is one tall column of metric groups. Each group prints four model names, then 36 data rows:
12 QM schemes for the training set, 12 for insulin, 12 for ubiquitin, in that order. THE DATASET LABEL
PRINTS IN THE MIDDLE OF ITS SECTION, so it is never read; the dataset comes from how many times the group
has already printed that scheme.
"""
import csv, io, pathlib, re, sys
import pymupdf

METRICS = {"Ravg": "R_avg", "RMSDavg": "RMSD_avg", "Davg": "D_avg"}
#: The groups cycle in this order; one group header prints its metric without repeating the model names.
GROUPS = ["E-MPA", "E-NPA", "E-HiI", "EX-MPA", "EX-NPA", "EX-HiI"]
SUFFIXES = ["6-31G*/gas", "6-31G*/PCM", "6-31G**/gas", "6-31G**/PCM"]
DATASETS = ("training_set", "insulin", "ubiquitin")
number = re.compile(r"^\d\.\d+$")

doc = pymupdf.open(sys.argv[1])
#: Cluster words into rows with a tolerance. A few rows print their scheme name and their four values
#: one unit apart in y, and exact rounding splits those into two half-rows that then match nothing.
ROW_TOLERANCE = 2.0
#: The page carries a rotated "Downloaded from pubs.acs.org ... September 2026" watermark down its right
#: edge, at x beyond every table column. Its words otherwise anchor row clusters of their own and displace
#: real rows, so they are dropped by position before anything is clustered.
TABLE_RIGHT_EDGE = 300.0
placed = []
for x0, y0, x1, y1, word, *_ in doc[0].get_text("words"):
    word = word.replace("\u200b", "").strip()
    if word and (x0 + x1) / 2 <= TABLE_RIGHT_EDGE:
        placed.append(((y0 + y1) / 2, (x0 + x1) / 2, word))
rows, current, anchor = {}, None, None
for y, x, word in sorted(placed):
    if anchor is None or y - anchor > ROW_TOLERANCE:
        anchor = y
        current = rows.setdefault(round(anchor), [])
    current.append((x, word))

#: Column centres, from the one group header that prints all four model names with their x positions.
#: A value belongs to a column when it is within this many points of that centre.
COLUMN_TOLERANCE = 20.0
out, models, columns, metric, group_index, seen_in_group = [], None, None, None, 0, []
for y in sorted(rows):
    cells = sorted(rows[y])
    words = [w for _, w in cells]
    if words[0] in METRICS:
        metric = METRICS[words[0]]
        named = [(x, w) for x, w in cells if w.startswith(("E-", "EX-"))]
        if named:
            models = [w for _, w in named]
            columns = [x for x, _ in named]
        else:  # one header prints its metric without repeating the names; the groups cycle in a fixed order
            models = [f"{GROUPS[group_index % len(GROUPS)]}/{s}" for s in SUFFIXES]
        group_index += 1
        seen_in_group = []
        continue
    schemes = [w for _, w in cells if "/" in w and not w.startswith(("E-", "EX-"))]
    if not (schemes and models and columns and metric):
        continue
    # Pick each column's value by POSITION. The last row of a group can share its cluster with the next
    # group's header, so "exactly four numbers on the row" drops three real rows; proximity does not.
    picked = []
    for centre in columns:
        near = [(abs(x - centre), w) for x, w in cells if number.match(w) and abs(x - centre) <= COLUMN_TOLERANCE]
        picked.append(min(near)[1] if near else None)
    if all(picked):
        # The dataset comes from how often this group has already printed THIS scheme: each group lists all
        # 12 schemes for the training set, then for insulin, then for ubiquitin. Counting rows instead would
        # shift every later dataset if a single row were ever missed.
        dataset = DATASETS[seen_in_group.count(schemes[0])]
        seen_in_group.append(schemes[0])
        for value, model in zip(picked, models):
            out.append([model, schemes[0], dataset, metric, value])

assert len(out) == 24 * 12 * 3 * 3, len(out)
buffer = io.StringIO()
writer = csv.writer(buffer, lineterminator="\n")
writer.writerow(["model", "qm_scheme", "dataset", "metric", "value"])
writer.writerows(out)
pathlib.Path(sys.argv[2]).write_text(
    "# Ionescu et al. 2013 (doi 10.1021/ci400448n) Table S2, read positionally from ci400448n_si_002.pdf\n"
    "# by benchmarks/charges/models/ionescu_s2_extract.py: every model x QM scheme x dataset x metric cell.\n"
    "# Internal validation is the cell where the model's own scheme is the row (E-MPA/6-31G*/gas vs MPA/6-31G*/gas).\n"
    + buffer.getvalue(), encoding="utf-8", newline="\n")
print(f"{len(out)} cells")
