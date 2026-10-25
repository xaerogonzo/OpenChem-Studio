"""Field parsing shared by the three volumes.  Operates on the VALUE text of one
property row of one entry.  Counts only; nothing here stores the book's text
beyond short snippets for hand checking."""
import re

REF = re.compile(r"\[[0-9–\-][0-9,\s–−\-]*\]")  # [4], [2, 6], [2-5], [-4]
MINUS = "−–—"


def norm(t):
    t = t.replace(" ", " ").replace("\xa0", " ").replace(" ", " ")
    t = re.sub(r"k\]", "kJ", t)  # OCR: kJ read as k]
    t = re.sub(r"\s+", " ", t).strip()
    return t


def strip_refs(t):
    return REF.sub("", t)


def has_ref(t):
    return bool(REF.search(t)) or bool(re.search(r"\[[0-9]{1,3}\s*[,–\-]?\s*[0-9]{0,3}\]", t))


def has_number(t):
    t = strip_refs(t)
    return bool(re.search(r"\d", t))


def split_items(t):
    """Split a value text at top-level commas/semicolons (not inside () or [])."""
    items, cur, dp, db = [], [], 0, 0
    for i, ch in enumerate(t):
        if ch == "(":
            dp += 1
        elif ch == ")":
            dp = max(0, dp - 1)
        elif ch == "[":
            db += 1
        elif ch == "]":
            db = max(0, db - 1)
        if ch in ",;" and dp == 0 and db == 0:
            # a thousands comma "1,840" is not a separator
            if ch == "," and i > 0 and i + 1 < len(t) and t[i - 1].isdigit() and t[i + 1].isdigit():
                cur.append(ch)
                continue
            items.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    items.append("".join(cur))
    return [x.strip() for x in items if x.strip()]


def parens(item):
    """Text inside top-level parentheses of an item (qualifier text), refs removed."""
    out, dp, cur = [], 0, []
    for ch in item:
        if ch == "(":
            dp += 1
            if dp == 1:
                continue
        elif ch == ")":
            dp -= 1
            if dp == 0:
                out.append("".join(cur))
                cur = []
                continue
        if dp >= 1:
            cur.append(ch)
    return " ".join(strip_refs(o) for o in out).strip()


# ---------------- melting point
DEC = re.compile(r"dec|explo|\bd\.|\(d\)|\bburn|ignit|sublim", re.I)
RANGE = re.compile(r"\d\s*[–—\-]\s*[−\-]?\d|\bto\b\s*\d")
QUAL = re.compile(r"[>≥<≤~≈]|\bca\.|\bapprox|\babout|\bover\b|\babove\b|\bbelow\b", re.I)


def mp_features(t):
    r = strip_refs(t)
    nop = re.sub(r"\([^)]*\)", "", r)  # outside parentheses
    nop = re.sub(r"@\s*\d+\s*[^\s,;]*", "", nop)
    return {
        "numeric": has_number(t),
        "dec": bool(DEC.search(r)),
        "range": bool(RANGE.search(nop)),
        "qual": bool(QUAL.search(nop)),
        "ref": has_ref(t),
    }


# ---------------- density
CRYST = re.compile(r"crystal|x-?\s?ray|single|pycnomet|diffraction|XRD|gas\s+displacement", re.I)
BULK = re.compile(r"bulk|press|cast|loading|pellet|\bTMD\b|theoretical|\bmax|granul|packing|powder|charge density", re.I)
TEMP = re.compile(r"@\s*[−\-]?\d+(\.\d+)?\s*(°\s?C|K\b|℃)|\b\d+\s*(°\s?C|K)\b|\bat\s+[−\-]?\d+\s*(°\s?C|K)\b|\bRT\b|room temp", re.I)


def rho_items(t):
    out = []
    for it in split_items(t):
        core = strip_refs(it)
        if not re.search(r"\d", core):
            continue
        q = parens(it)
        # label words may also follow the number w/o parentheses: "1.80 crystal"
        tail = re.sub(r"\([^)]*\)", "", core)
        tail = re.sub(r"[\d.\s±−\-–]+", " ", tail)
        tail = re.sub(r"g\s*(/|\s)?\s*cm\S*|g\s*mL\S*|kg\s*m\S*", "", tail).strip()
        lab = (q + " " + tail).strip()
        out.append({
            "crystal": bool(CRYST.search(lab)),
            "bulk": bool(BULK.search(lab)),
            "temp": bool(TEMP.search(lab)),
            "tempOnly": bool(TEMP.search(lab)) and not CRYST.search(lab) and not BULK.search(lab),
            "none": lab == "",
            "spgr": bool(re.match(r"\s*(sp\.?\s*gr|d\d)", core, re.I)),
            "ref": has_ref(it),
        })
    return out


# ---------------- heat of formation
UNITS = [
    ("kJ/mol", r"kJ\s*(/|\s|·|⋅)?\s*mol"),
    ("kJ/kg", r"kJ\s*(/|\s|·)?\s*kg"),
    ("kJ/g", r"kJ\s*(/|\s)?\s*g\b"),
    ("kcal/mol", r"kcal\s*(/|\s|·)?\s*mol"),
    ("kcal/kg", r"kcal\s*(/|\s|·)?\s*kg"),
    ("kcal/g", r"kcal\s*(/|\s)?\s*g\b"),
    ("cal/g", r"(?<!k)cal\s*(/|\s)?\s*g\b"),
    ("cal/mol", r"(?<!k)cal\s*(/|\s)?\s*mol"),
    ("J/g", r"(?<!k)\bJ\s*(/|\s)?\s*g\b"),
    ("MJ/kg", r"MJ\s*(/|\s)?\s*kg"),
    ("kcal", r"kcal\b"),
    ("kJ", r"kJ\b"),
    ("cal", r"(?<!k)cal\b"),
]
UNITS = [(n, re.compile(p, re.I)) for n, p in UNITS]
SOLID = re.compile(r"\(s\)|\bsolid|crystalline|condensed|\(c\)|\(cr\)|\(cry|\bcryst", re.I)
LIQ = re.compile(r"\(l\)|\(liq|\bliquid", re.I)
GAS = re.compile(r"\(g\)|\bgas\b|gaseous|vapou?r", re.I)
CALC = re.compile(r"calc|predict|estimat|CBS|\bG[234]\b|G3\(|EXPLO|Gaussian|B3LYP|\bDFT\b|ab initio|theor|\bemp\.|method|isodesmic|group add|Benson|computed|MP2|PM3|CCSD|\bW1\b|\bMP\b|semi-?empir", re.I)
EXPT = re.compile(r"exptl|\bexp\.|expt|experim|measured|calorimet|\bbomb|\bobs|from combustion|determined", re.I)
LITL = re.compile(r"\blit\.|literature", re.I)


def hf_items(t):
    out = []
    for it in split_items(t):
        core = strip_refs(it)
        if not re.search(r"\d", core):
            continue
        unit = "none"
        for n, rx in UNITS:
            if rx.search(core):
                unit = n
                break
        q = core
        c = bool(CALC.search(q))
        e = bool(EXPT.search(q))
        out.append({
            "unit": unit,
            "solid": bool(SOLID.search(q)) or bool(LIQ.search(q)),
            "liquid": bool(LIQ.search(q)),
            "gas": bool(GAS.search(q)),
            "calc": c and not e,
            "expt": e and not c,
            "both": c and e,
            "lit": bool(LITL.search(q)),
            "ref": has_ref(it),
        })
    return out


METALS = set("Li Na K Rb Cs Be Mg Ca Sr Ba Al Ga In Tl Sn Pb Bi Sb Zn Cd Hg Cu Ag Au Fe Co Ni Mn Cr Ti Zr V Mo W Pt Pd Ru Rh Ir Os Ce La Nd Y Sc Gd Cs Mn".split())


def formula_metals(f):
    els = re.findall(r"[A-Z][a-z]?", f)
    return sorted({e for e in els if e in METALS})


MIXKEY = re.compile(r"powder|dynamite|mixture|composition|propellant|polymer|cellulose|\bANFO\b|\bGAP\b|\bpoly|formulation|plastic|gelatin|amatol|semtex|\bcomp\b|\bPBX|\bblack\b|\btorpex|\bnitrostarch|\bpentolite|\bamanol|\bcyclotol|\boctol|\bminol|ammonal|\bPETN.*TNT|\bmelt|\bexplosive [A-Z]|\bTNT\b.*\+|\bNC\b", re.I)
