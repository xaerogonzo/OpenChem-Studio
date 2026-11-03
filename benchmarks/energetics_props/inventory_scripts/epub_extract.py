"""Entries of an epub volume (vol1 / vol3).  Usage: epub_extract.py <vol: v1|v3> <outjson>
Reads the already-unzipped epub in ./ex1 or ./ex3 (unzipped by `unzip` into its own folder)
and the OCR results in ./ocr_out for chapters whose property block is an image."""
import sys, os, re, json, html, struct
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
from fieldlib import *

vol, OUT = sys.argv[1], sys.argv[2]
ex = {"v1": "ex1", "v3": "ex3"}[vol]
ROOT = os.path.join(HERE, ex, "OPS")

LABELS = [
    ("N", r"^N \[%\]"), ("Om", r"^Ω\(CO2\) \[%\]"), ("Tmp", r"^Tm\.?p\.?\s*\["),
    ("Tdec", r"^Tdec\.?\s*\["), ("rho", r"^ρ\s*\[g"),
    ("Hf", r"^Heat of form"), ("Hc", r"^Heat of combustion"),
    ("Formula", r"^(Chemical )?[Ff]ormula$"),
]
LABELS = [(k, re.compile(p)) for k, p in LABELS]
# OCR-tolerant label tests (rho is read as p / Q etc.)
OCRL = [
    ("N", re.compile(r"^N\s*\[\s*%|^\[%\]\s*N|^N\s*\[%")),
    ("Om", re.compile(r"[ΩQΩ]\s*\(?\s*CO|\(CO2?\)\s*\[")),
    ("Tmp", re.compile(r"^T\s*m\.?\s*p\.?\s*\[", re.I)),
    ("Tdec", re.compile(r"^T\s*dec\.?\s*\[", re.I)),
    ("rho", re.compile(r"^[pρΡ]\s*\[\s*g|^[pρ]\s*\[g\s*cm", re.I)),
    ("Hf", re.compile(r"^Heat of form", re.I)),
    ("Hc", re.compile(r"^Heat of (?!form)", re.I)), ("Tbp", re.compile(r"^T\s*b\.?\s*p\.?\s*\[", re.I)),
]

def text_of(s):
    s = re.sub(r"<br\s*/?>", " ", s)
    s = re.sub(r"<[^>]+>", "", s)
    return norm(html.unescape(s))

nav = open(os.path.join(ROOT, "nav.xhtml"), encoding="utf8").read()
links = re.findall(r'<a [^>]*href="([^"]+)"[^>]*>(.*?)</a>', nav, re.S)
ents = []
for h, t in links:
    t = html.unescape(re.sub(r"<[^>]+>", "", t)).strip()
    f = h.split("#")[0]
    if "chapter" not in f or len(t) <= 1 or t == "Chapter":
        continue
    ents.append({"title": t, "file": f.split("/")[-1], "anchor": h.split("#")[1] if "#" in h else ""})

def png_w(p):
    with open(p, "rb") as fh:
        d = fh.read(32)
    return struct.unpack(">II", d[16:24])

for e in ents:
    s = open(os.path.join(ROOT, "content", e["file"]), encoding="utf8").read()
    e["has_text_props"] = "Heat of formation" in s or "m.p." in s
    vals, src, formula = {}, "none", ""
    # ---------- text rows
    if "Heat of formation" in s:
        src = "epub-text"
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", s, re.S):
            tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
            if len(tds) < 2:
                continue
            lab = text_of(tds[0])
            for k, rx in LABELS:
                if k not in vals and rx.search(lab):
                    vals[k] = text_of(" ".join(tds[1:]))
            # property table: first-row 'Chemical formula' lives in Table_2 style rows too
    else:
        # ---------- OCR
        key = vol + "_" + e["file"][:-6]
        JOBS = globals().setdefault("_JOBS", {j["key"]: j for j in json.load(open(os.path.join(HERE, "jobs2.json")))})
        res = []
        complete = False
        miss_img = 0
        for im in JOBS.get(key, {}).get("imgs", [])[:8]:
            cf = os.path.join(HERE, "ocr_img", im + ".json")
            if not os.path.exists(cf):
                miss_img += 1
                continue
            ln = json.load(open(cf, encoding="utf-8"))
            res.append({"img": im, "lines": ln})
            if re.search(r"Calcd|Lit\. values|Exptl", " ".join(l[4] for l in ln)):
                complete = True
                break
        e["ocr_images_read"] = len(res)
        e["ocr_images_missing"] = miss_img
        e["ocr_complete"] = complete
        if res:
            src = "epub-image-ocr"
            lines = []  # (y_global, x, text)
            off = 0
            for r in res:
                p = os.path.join(ROOT, "graphic", r["img"])
                W, H = png_w(p)
                for (x0, y0, x1, y1, t) in r["lines"]:
                    lines.append((off + y0, x0 / W, t))
                off += H + 200
            lines.sort()
            lab_idx = []
            for n, (y, xf, t) in enumerate(lines):
                if xf < 0.12:
                    for k, rx in OCRL:
                        if rx.search(norm(t)):
                            lab_idx.append((y, k))
                            break
            lab_idx.sort()
            # stop rows: first value line starting with 'Calcd' / 'Lit. values' / table header after the labels
            stop_y = None
            for (y, xf, t) in lines:
                if re.match(r"^(Calcd|Lit\.? values|Exptl)", norm(t)) and (stop_y is None or y < stop_y):
                    if lab_idx and y > lab_idx[0][0]:
                        stop_y = y
            for n, (y, k) in enumerate(lab_idx):
                if k in vals:
                    continue
                nxt = lab_idx[n + 1][0] - 25 if n + 1 < len(lab_idx) else 10 ** 9
                if stop_y is not None and stop_y > y:
                    nxt = min(nxt, stop_y - 5)
                vs = [t for (yy, xf, t) in lines if xf >= 0.12 and y - 25 <= yy < nxt]
                vals[k] = norm(" ".join(vs))
            e["ocr_labels_found"] = [k for _, k in lab_idx]
            for (y, xf, t) in lines:
                if re.match(r"^(Chemical )?[Ff]ormula", norm(t)) and xf < 0.3:
                    vs = [tt for (yy, xx, tt) in lines if abs(yy - y) < 25 and xx >= 0.3]
                    if vs:
                        vals["Formula"] = norm(" ".join(vs))
                        break
        else:
            src = "none"
    e["vals"] = vals
    e["src"] = src
    e["formula"] = vals.get("Formula", "")
    if src == "epub-image-ocr":
        # formula row in the OCR is in the crystal table; try to read it from the first value after 'formula'
        pass

json.dump(ents, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
import collections
print(len(ents), "entries;", collections.Counter(e["src"] for e in ents))
print("first", ents[0]["title"], ents[0]["file"], "last", ents[-1]["title"], ents[-1]["file"])
miss = [e for e in ents if e["src"] != "none" and not e["vals"].get("Tmp") and "Tmp" not in e["vals"]]
print("src!=none, Tmp label not found:", len(miss))
