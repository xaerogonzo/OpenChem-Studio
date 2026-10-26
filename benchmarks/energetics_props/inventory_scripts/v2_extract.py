import sys, os, re, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
import pymupdf
from fieldlib import *

PDF = sys.argv[1]
OUT = sys.argv[2]
d = pymupdf.open(PDF)

# --- entry headings: 12 pt bold at top of page (y<100); letter dividers are 1 char
heads = []
for i, pg in enumerate(d):
    for b in pg.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            txt = "".join(s["text"] for s in l["spans"] if 11.5 <= s["size"] < 20 and "Bold" in s["font"]).strip()
            if txt:
                heads.append((i, round(l["bbox"][1]), txt))
entries = []
for (i, y, t) in heads:
    if t in ("Also of interest", "Contents") or len(t) == 1:
        continue
    if entries and entries[-1]["page"] == i and y > 70 and y < 90 and entries[-1]["y"] < 70:
        entries[-1]["title"] += " " + t  # wrapped title line
        continue
    entries.append({"page": i, "y": y, "title": t})
for k, e in enumerate(entries):
    e["end"] = (entries[k + 1]["page"] - 1) if k + 1 < len(entries) else len(d) - 1

LABELS = [
    ("N", r"^N \[%\]"), ("Om", r"^Ω\(CO2\) \[%\]"), ("Tmp", r"^Tm\.?p\.?\s*\["),
    ("Tdec", r"^Tdec\.?\s*\["), ("rho", r"^ρ\s*\[g"),
    ("Hf", r"^Heat of form"), ("Hc", r"^Heat of (?!form)"), ("Tbp", r"^Tb\.p\. "), ("Tfl", r"^(Tflash|Flash point|Tflame|Specific heat|Cp )"), ("Calcd", r"^Calcd\."),
    ("Formula", r"^Formula$"), ("Mm", r"^Molecular (mass|weight)"),
]
LABELS = [(k, re.compile(p)) for k, p in LABELS]

def page_lines(i):
    lines = d[i].get_text().split("\n")
    # drop running header: first lines containing EM SPACE (header carries  )
    j = 0
    while j < min(4, len(lines)) and (" " in lines[j] or re.fullmatch(r"\d{3,4}", lines[j].strip())):
        j += 1
    return lines[j:]

for e in entries:
    lines = []
    for i in range(e["page"], e["end"] + 1):
        if i > e["page"]:
            lines += page_lines(i)
        else:
            lines += d[i].get_text().split("\n")
    # find first occurrence of each label, then slice
    pos = {}
    span = {}
    for k, rx in LABELS:
        for n, l in enumerate(lines):
            if k in pos:
                break
            if rx.search(norm(l)):
                pos[k] = n
            elif n + 1 < len(lines) and rx.search(norm(l + " " + lines[n + 1])) and not rx.search(norm(lines[n + 1])):
                pos[k] = n
                span[k] = 1
    order = sorted((n, k) for k, n in pos.items())
    vals = {}
    for idx, (n, k) in enumerate(order):
        nxt = order[idx + 1][0] if idx + 1 < len(order) else len(lines)
        vals[k] = norm(" ".join(lines[n + 1 + span.get(k, 0):nxt]))
    e["vals"] = vals
    e["has_name_anchor"] = any(l.startswith("Name [German") for l in lines)
    e["printed_page"] = e["page"] + 649
    e["formula"] = vals.get("Formula", "")
    e["src"] = "pdf-text"

def analyse(entries):
    R = {"entries": len(entries)}
    mp = [mp_features(e["vals"].get("Tmp", "")) for e in entries]
    for e, f in zip(entries, mp):
        e["mp"] = f
    return R

R = analyse(entries)
json.dump(entries, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
print(len(entries), "entries; first", entries[0]["title"], entries[0]["page"], "last", entries[-1]["title"], entries[-1]["page"], entries[-1]["end"])
miss = [(e["title"], [k for k in ("Tmp", "Tdec", "rho", "Hf") if k not in e["vals"]]) for e in entries]
print("entries with a missing label:", sum(1 for t, m in miss if m))
for t, m in miss:
    if m:
        print(" ", t, m)
