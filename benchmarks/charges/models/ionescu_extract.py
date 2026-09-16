"""TRIAGE: freeze Ionescu 2013 Table S1 as a fixture, read POSITIONALLY (by x/y), never in reading order.

    uvx --with pymupdf python extract_s1.py <ci400448n_si_001.pdf> <out.csv>
"""
import csv, io, pathlib, re, sys
import pymupdf

doc = pymupdf.open(sys.argv[1])
rows = {}
for x0, y0, x1, y1, word, *_ in doc[0].get_text("words"):
    word = word.replace("\u200b", "").strip()
    if word:
        rows.setdefault(round((y0 + y1) / 2), []).append(((x0 + x1) / 2, word))
lines = [(y, [(x, w) for x, w in sorted(rows[y])]) for y in sorted(rows)]

number = re.compile(r"^-?\d+\.\d+$")
out, section = [], None
models, ks, half_top = [], [], None
for y, cells in lines:
    words = [w for _, w in cells]
    if words[:2] == ["EEM", "model"]:
        models = words[2:]
        ks, half_top = [], y
        continue
    if words and words[0] == "k" and half_top is not None:
        ks = [w for w in words if number.match(w)]
        continue
    if len(words) >= 3 and number.match(words[1]) and models:
        atom_type = words[0]
        values = [w for w in words[1:] if number.match(w)]
        assert len(values) == 2 * len(models), (atom_type, len(values), len(models))
        for index, model in enumerate(models):
            out.append([model, atom_type, ks[index], values[2 * index], values[2 * index + 1]])
assert len({m for m, *_ in out}) == 24, sorted({m for m, *_ in out})
buffer = io.StringIO()
writer = csv.writer(buffer, lineterminator="\n")
writer.writerow(["model", "atom_type", "kappa", "A", "B"])
writer.writerows(out)
header = ("# Ionescu et al. 2013 (doi 10.1021/ci400448n) Table S1, all 24 EEM models.\n"
          "# Read positionally from ci400448n_si_001.pdf by benchmarks/charges/models/ionescu_extract.py:\n"
          "# words are clustered by row (y) and ordered by column (x), never taken in PDF reading order.\n"
          "# kappa is the table's k; A and B are its per-atom-type parameters, in the paper's units.\n")
pathlib.Path(sys.argv[2]).write_text(header + buffer.getvalue(), encoding="utf-8", newline="\n")
print(f"{len(out)} rows, {len({m for m, *_ in out})} models")
for model in sorted({m for m, *_ in out}):
    types = [r[1] for r in out if r[0] == model]
    print(f"  {model:22} k={[r[2] for r in out if r[0] == model][0]} types {len(types)}: {' '.join(types)}")
