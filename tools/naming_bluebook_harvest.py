"""The Blue Book printed-PIN harvest (naming round 9, B1).

`BlueBookV2.pdf` prints the name of a structure and tags the preferred IUPAC name "(PIN)". This tool turns those printed names into a population
of (structure, printed name) rows so the engine can be asked: given this structure, do you print the book's name?

    # 1. PDF -> candidate rows. Needs pymupdf, which is NOT a project dependency: run it in a throwaway environment.
    uvx --with pymupdf python tools/naming_bluebook_harvest.py extract --pdf "D:/.../BlueBookV2.pdf" --out WORK/extract.json

    # 2. candidate rows -> the two halves. Needs the project venv (RDKit, OPSIN through py2opsin, a bare `java` on PATH).
    python tools/naming_bluebook_harvest.py build --extract WORK/extract.json

The roles are fixed by `benchmarks/naming/bluebook_protocol.toml`, which was committed before any row was looked at: NORMATIVE AUTHORITY = the
Blue Book; STRUCTURE EXTRACTION = OPSIN, an interpreter of the book's names and not an authority on them (in round 8 it read every misspelling);
ENGINE UNDER TEST = OpenChem; VALIDATION = the drawn structure on the page (a hand check, recorded separately).

**THE MERGED HARVEST IS NEVER PERSISTED.** `extract` writes a scratch file outside the repository; `build` reads it and writes exactly two
populations, `bluebook_tuning.json` (any tool may read it) and `bluebook_frozen.json` (evaluation only: registered `frozen`, refused by every tool
that enumerates populations, hashed in its meta, and its rows are never printed). A row is assigned to a half by a hash of its structure's InChIKey
WITHIN its chapter, so both halves cover every chapter, and the assignment is never revisited after the engine has seen either half.

**A NAME IS JOINED FROM LINES BY ITS OWN SYNTAX, NEVER BY ADJACENCY.** The first draft of the extraction joined the previous line of a block to
every '(PIN)' line and made 465 wrong joins out of 4,260: the previous line is usually a condensed formula, a non-preferred name or an index
number. A continuation is recognised only when the name itself is broken (it closes brackets it never opened, the previous line ends in a hyphen or
comma or leaves a bracket open, or the tail is a bare class word such as `acid`), the previous line holds only characters a name can hold, and it is
not prose. Whatever still has unbalanced brackets is dropped as a page or column split and COUNTED, never guessed at.

**EVERY DROP HAS ONE REASON AND IS REPORTED.** The reasons are the protocol's `[filters]`; the funnel (extracted -> eligible -> OPSIN-parsed ->
unseen -> tuning / frozen) is written to `benchmarks/naming/bluebook_funnel.json` with the exclusions by reason and by chemistry class, because a
family whose printed PINs OPSIN cannot read is itself data about the oracle's boundary.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
import time
import tomllib
import warnings
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BENCH = ROOT / "benchmarks" / "naming"
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "src"))

PROTOCOL = BENCH / "bluebook_protocol.toml"
TAG = "(PIN)"
TUNING_FILE = "bluebook_tuning.json"
FROZEN_FILE = "bluebook_frozen.json"
SEEN_FILE = "bluebook_seen.json"
FUNNEL_FILE = "bluebook_funnel.json"
SPLIT_SALT = "openchem-bluebook-split-v1"

# --- pure text functions: no PDF, no OPSIN, unit-tested ------------------------------------------------------------------------------------------

#: The characters a name (or a piece of one) can hold. A line with anything else (`=`, a bullet, a formula's `+`) is not a name continuation.
NAME_CHARS = re.compile("^[0-9A-Za-z,\u2032\u2033\u2034\u2019'\\-\\[\\]\\(\\)\\{\\}:;\\.\u00b7\u2013\u03bb\u03ba\u03b7\u03b1\u03b2 ]+$")
PROSE = re.compile(r"\b(the|is|are|to|for|and|of|or|in|by|with|as|be|that|this|not)\b", re.I)
CLASS_WORDS = ("acid", "oxide", "hydrate", "anhydride", "chloride", "bromide", "ester", "amide", "imide")
_LEADING_MARKER = re.compile(r"^(?:\(\d+\)|\d+\)|\([a-z]\)|Step \d+:)\s+")
_TRAILING_LABEL = re.compile(r"\s+\((?:[IVX]+|[a-z])\)$")


def unbalanced(text: str) -> int:
    """Opening minus closing brackets: positive = a bracket left open, negative = closes one it never opened."""
    return sum(text.count(c) for c in "([{") - sum(text.count(c) for c in ")]}")


def is_name_line(text: str) -> bool:
    return bool(NAME_CHARS.match(text)) and not PROSE.search(text)


def continues(previous: str, parts: list[str]) -> bool:
    """Is the line `previous` the FIRST half of the name already collected in `parts`? Decided by the name's own syntax (module docstring)."""
    if previous.endswith(TAG) or not is_name_line(previous):
        return False
    tail = unbalanced("".join(parts)) < 0
    hyphen_wrap = previous.endswith(("-", ",")) and not previous.endswith(" -")
    open_previous = unbalanced(previous) > 0
    class_word = parts[0] in CLASS_WORDS
    return tail or hyphen_wrap or open_previous or class_word


def join_name(parts: list[str]) -> str:
    """Join name pieces: no space after a hyphen, comma or opening bracket or before a closing one; a space between two words."""
    joined = parts[0]
    for piece in parts[1:]:
        glue = "" if joined.endswith(("-", ",", "(", "[")) or piece.startswith((")", "]", ",")) else " "
        joined = joined + glue + piece
    return re.sub(r"-\s+(?=[0-9(\[{])", "-", joined).strip()


def clean_name(raw: str) -> str:
    """A printed name without the list markers the typesetting puts in front of and behind it (`(1) `, `Step 2: `, ` (I)`)."""
    name = raw.strip()
    name = _LEADING_MARKER.sub("", name)
    name = _TRAILING_LABEL.sub("", name)
    return name.strip()


def normalise_for_opsin(name: str) -> str:
    """Primes and dashes to ASCII. py2opsin writes its input in the platform's default encoding (cp1252 here), which has no prime."""
    out = name.replace("\u2032", "'").replace("\u2033", "''").replace("\u2034", "'''").replace("\u2019", "'")
    return out.replace("\u2013", "-").replace("\u2014", "-").replace("\u2212", "-").replace("\u00ad", "")


_STEREO = re.compile(
    "\\((?:\\d+[A-Za-z]?['\u2032\u2033,]*,?)*[RSEZrsez]\\)|\\b(?:rel|cis|trans|threo|erythro|endo|exo|syn|anti)-|^[DL]-|\\(\\+\\)|\\(-\\)|\\(\u00b1\\)"
    "|[\u03b1\u03b2]-|\\b[RS]\\)|\\(([REZ])[,)]|\\d[RSEZ][,)]"
    # a locant that carries its own descriptor: (4aR,8aS), (3aR,7aS), (2R)
    "|\\(\\d+[a-z]?[RSEZrsez]['\u2032\u2033]*(?:,\\d+[a-z]?[RSEZrsez]['\u2032\u2033]*)*\\)"
)
# An isotope is a MASS NUMBER on an element: `(2H6)`, `(3H1)`, `(13C)`, `(131I)`, `[U-14C]`. Indicated hydrogen looks the same and is everywhere
# (`pyrimidin-4(3H)-one`, `anthracen-9(10H)-one`), so hydrogen counts only as 2H or 3H WITH a following atom count, and a two- or three-digit mass
# never on H. (An earlier pattern flagged all of those, and `trit` inside `trithiane`.)
_ISOTOPE = re.compile(
    r"\[[A-Za-z0-9,\-]*\d+[A-Z][a-z]?\d*\]|\bdeuter|\btrit(?:io|ium)"
    r"|\((?:\d+(?:,\d+)*-)?[23]H\d+[,)]|\((?:\d+(?:,\d+)*-)?\d{2,3}(?!H)[A-Z][a-z]?\d*[,)]|\d+[A-Z][a-z]?-label"
    # an atom or locant BEFORE the isotope: (3-2H)pyridine, (O-2H)acetic acid, (N-2H1)acetamide, (2-13C)
    r"|\((?:[A-Za-z]|\d+[a-z]?)(?:,(?:[A-Za-z]|\d+[a-z]?))*-(?:[23]H|\d{2,3}(?!H)[A-Z][a-z]?)\d*\)"
)
_RADICAL = re.compile(r"radical|ylidyne$|\(\*\)")
_POLYMER = re.compile(r"\bpoly|\bcopoly|\bblock\b")
_METAL = re.compile(
    r"ferrocene|ruthenocene|ferrat|cuprat|aurat|platinat|\bcobalt|\bnickel|\bpalladium|\btitan|\bzircon|\bchromium|\bmolybden|\btungst|\bmanganes"
    r"|\biridium|\brhodium|\bosmium"
)


def scope_reason(name: str, unbalanced_flag: bool) -> str | None:
    """The FIRST protocol filter that applies, or None. One reason per row, so the counts add up."""
    if not name or len(name) < 3:
        return "not_a_structure_name"
    if unbalanced_flag:
        return "page_or_column_split"
    if _STEREO.search(name):
        return "stereodescriptor"
    if _ISOTOPE.search(name):
        return "isotope"
    if _RADICAL.search(name):
        return "radical_or_ion_wildcard"
    if _POLYMER.search(name):
        return "polymer"
    if _METAL.search(name):
        return "organometallic"
    if len(PROSE.findall(name)) >= 2 and " " in name and not re.search(r"\b(?:acid|oxide|ester|amide|hydrogen|ion)\b", name):
        return "not_a_structure_name"
    if " = " in name or "\u2022" in name or "\u2192" in name:
        return "not_a_structure_name"
    if re.search(r"\(\d+/\d+(?:/\d+)?\)", name) or "\u2014" in name:
        return "not_a_structure_name"  # a co-crystal, solvate or mixture ('A' with 'B' (1/1)) is not one structure
    return None


def chemistry_class(name: str) -> str:
    """A coarse class for REPORTING what OPSIN could not read (data about the oracle's boundary); it filters nothing."""
    n = name.lower()
    if "phane" in n:
        return "phane"
    if "fulleren" in n:
        return "fullerene"
    if "anhydride" in n:
        return "anhydride"
    if re.search(r"(yl|ylidene|diyl|oyl|yloxy|ylium)$", n):
        return "substituent_group"
    if re.search(r"\b(thio|seleno|telluro)(?:peroxo|carbon)|thioperox|sulfanyl|selanyl", n):
        return "chalcogen_replaced"
    if re.search(r"[^a-z]\d[^a-z]*\(\d", n) and "spiro" in n:
        return "spiro"
    if "bicyclo" in n or "tricyclo" in n or "cyclo[" in n or "spiro" in n:
        return "von_baeyer_or_spiro"
    if re.search(r"\[\d,\d[a-z]?\]|[a-z]\[\d", n) or "fused" in n:
        return "fusion"
    if re.search(r"(phosph|arsen|antimon|silan|boran|stannan|german)", n):
        return "heteroatom_parent"
    return "other"


def chapter_of(section: str) -> int:
    """`P-65.1.2` -> 6, `P-1` -> 1, `P-101` -> 10: the chapter is the leading digits of the section number."""
    digits = re.match(r"P-(\d+)", section)
    if not digits:
        raise ValueError(f"not a Blue Book section: {section!r}")
    number = digits.group(1)
    return int(number) if len(number) == 1 else (10 if len(number) >= 3 else int(number[0]))


def split_half(inchikey: str, chapter: int) -> str:
    """`tuning` or `frozen`, by hash order WITHIN the chapter (assigned by `assign_halves`, which needs every row of the chapter)."""
    return hashlib.sha256(f"{SPLIT_SALT}:{chapter}:{inchikey}".encode("utf-8")).hexdigest()


def assign_halves(records: list[dict]) -> dict[str, str]:
    """Label -> half. Within each chapter the rows are ordered by their split hash and dealt alternately, so both halves cover every chapter
    and differ in size by at most one row per chapter."""
    by_chapter: dict[int, list[dict]] = {}
    for record in records:
        by_chapter.setdefault(record["chapter"], []).append(record)
    halves: dict[str, str] = {}
    for chapter, rows in by_chapter.items():
        for index, record in enumerate(sorted(rows, key=lambda r: split_half(r["inchikey"], chapter))):
            halves[record["label"]] = "tuning" if index % 2 == 0 else "frozen"
    return halves


def protocol_sha256() -> str:
    return hashlib.sha256(PROTOCOL.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def structure_strings(source: str) -> set[str]:
    """Every string constant in Python source that RDKit reads as a molecule with at least three heavy atoms: the structures a test file
    mentions. Deliberately over-inclusive (a word that happens to parse marks a structure `seen`), because a false 'seen' shrinks the pool and
    a false 'unseen' leaks a target into the held-out half."""
    from rdkit import Chem, RDLogger

    RDLogger.DisableLog("rdApp.*")
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and 3 <= len(node.value) <= 200 and " " not in node.value:
            mol = Chem.MolFromSmiles(node.value)
            if mol is not None and mol.GetNumHeavyAtoms() >= 3:
                found.add(Chem.MolToSmiles(mol))
    return found


# --- extract: PDF -> candidate rows (needs pymupdf) -----------------------------------------------------------------------------------------------

_SECTION = re.compile(r"^(P-\d+(?:\.\d+)*)\s+[A-Z]")


def extract(pdf: Path, out: Path) -> None:
    import pymupdf

    doc = pymupdf.open(str(pdf))
    rows: list[dict] = []
    section = "P-1"
    for pno in range(doc.page_count):
        page = doc[pno]
        width, height = page.rect.width, page.rect.height
        lines = []
        for bno, block in enumerate(page.get_text("dict")["blocks"]):
            if block.get("type") != 0:
                continue
            for line in block["lines"]:
                text = "".join(span["text"] for span in line["spans"]).replace("\u00a0", " ").strip()
                if text:
                    x0, y0, x1, y1 = line["bbox"]
                    lines.append({"b": bno, "x0": x0, "y0": y0, "x1": x1, "y1": y1, "text": text})
        for index, ln in enumerate(lines):
            heading = _SECTION.match(ln["text"])
            if heading:
                section = heading.group(1)
            if not ln["text"].endswith(TAG):
                continue
            parts = [ln["text"][: -len(TAG)].rstrip()]
            used = [ln]
            j = index - 1
            while j >= 0 and lines[j]["b"] == ln["b"] and len(used) < 4 and continues(lines[j]["text"], parts):
                parts.insert(0, lines[j]["text"])
                used.insert(0, lines[j])
                j -= 1
            name = join_name(parts)
            x0, y0 = min(u["x0"] for u in used), min(u["y0"] for u in used)
            x1, y1 = max(u["x1"] for u in used), max(u["y1"] for u in used)
            rows.append(
                {
                    "page": pno + 1, "section": section, "chapter": chapter_of(section), "raw_name": name, "wrapped": len(used) > 1,
                    "parts": [u["text"] for u in used] if len(used) > 1 else None,
                    "bbox": [round(x0, 1), round(y0, 1), round(x1, 1), round(y1, 1)],
                    "page_size": [round(width, 1), round(height, 1)],
                    "near_page_edge": bool(x0 < 45 or y0 < 45 or x1 > width - 45 or y1 > height - 45),
                }
            )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"pdf_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(), "pages": doc.page_count, "rows": rows}, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"extracted {len(rows)} '{TAG}' lines from {doc.page_count} pages -> {out}")


# --- build: candidate rows -> the two halves (needs the project venv) -------------------------------------------------------------------------------


def _opsin_batch(names: list[str]) -> tuple[dict[str, str], set[str]]:
    """Name -> SMILES for the names OPSIN reads, and the set it read WITH an APPEARS_AMBIGUOUS warning. A chunk that warns is re-run name by
    name only to attribute the warning (the JVM start dominates the cost, so a clean chunk is one call)."""
    from openchem.chem import naming_providers as providers

    parsed: dict[str, str] = {}
    ambiguous: set[str] = set()
    for start in range(0, len(names), 100):
        chunk = names[start : start + 100]
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            results = providers.opsin_structures_for_names(chunk)
        for name, result in zip(chunk, results):
            if result is not None:
                parsed[name] = result.smiles
        if any("APPEARS_AMBIGUOUS" in str(w.message) for w in caught):
            for name in chunk:
                with warnings.catch_warnings(record=True) as one:
                    warnings.simplefilter("always")
                    providers.opsin_structures_for_names([name])
                if any("APPEARS_AMBIGUOUS" in str(w.message) for w in one):
                    ambiguous.add(name)
    return parsed, ambiguous


def _seen_structures() -> tuple[set[str], set[str], str]:
    """Canonical SMILES of every structure the project has already looked at, the InChIKeys of the same, and the text a printed name is matched
    against. Frozen populations are consulted through their membership HASHES, never their rows."""
    import naming_populations as populations
    from rdkit import Chem, RDLogger
    from rdkit.Chem import inchi

    RDLogger.DisableLog("rdApp.*")
    smiles: set[str] = set()
    for population in populations.tuning():
        if not (BENCH / population.file).exists() or population.file.startswith("bluebook_"):
            continue
        smiles |= {Chem.MolToSmiles(m) for row in populations.load(population.key) if (m := Chem.MolFromSmiles(row["smiles"])) is not None}
    text = ""
    for name in ("adjudication.toml", "charged_panel.toml", "charged_panel_adjudication.toml", "charged_panel_r8.toml", "charged_panel_r8_adjudication.toml"):
        path = BENCH / name
        if path.exists():
            body = path.read_text(encoding="utf-8")
            text += "\n" + body
            for value in re.findall(r'"([^"\n]{3,200})"', body):
                if " " not in value and (mol := Chem.MolFromSmiles(value)) is not None and mol.GetNumHeavyAtoms() >= 3:
                    smiles.add(Chem.MolToSmiles(mol))
    for path in (ROOT / "tests" / "test_namer_known_defects.py", ROOT / "tests" / "fixtures" / "naming_cation_shapes.txt"):
        if path.exists():
            body = path.read_text(encoding="utf-8")
            text += "\n" + body
            smiles |= structure_strings(body) if path.suffix == ".py" else {
                Chem.MolToSmiles(m) for line in body.splitlines() if line.strip() and not line.startswith("#")
                if (m := Chem.MolFromSmiles(line.split("\t")[0])) is not None
            }
    keys = {inchi.MolToInchiKey(Chem.MolFromSmiles(s)) for s in smiles if Chem.MolFromSmiles(s) is not None}
    return smiles, keys, text.lower()


def seen(canonical: str, inchikey: str, targets: list[str], seen_smiles: set[str], seen_keys: set[str], seen_text: str, membership: dict) -> bool:
    """Has the project already looked at this structure or this printed name? The union is deliberately conservative: a false 'seen' shrinks the
    pool, a false 'unseen' leaks a target into the held-out half. Structural first (canonical SMILES, then InChIKey, so a tautomer or a different
    spelling still matches), then textual (the printed name appears in an adjudication, a panel or a D-row), then the OTHER frozen populations by
    hash. **The harvest's own frozen half is excluded from that last check**: a rebuild would otherwise read its previous output as already seen and
    lose half of its pool (measured: 2,273 unseen became 1,137 on the second run)."""
    from naming_populations import membership_hash

    return (
        canonical in seen_smiles
        or inchikey in seen_keys
        or any(t.lower() in seen_text for t in targets)
        or any(membership_hash(canonical, salt) in hashes for key, (salt, hashes) in membership.items() if not key.startswith("bluebook_"))
    )


def build(extract_path: Path, out_dir: Path) -> None:
    import naming_populations as populations
    from rdkit import Chem, RDLogger
    from rdkit.Chem import inchi

    RDLogger.DisableLog("rdApp.*")
    payload = json.loads(extract_path.read_text(encoding="utf-8"))
    rows = payload["rows"]
    funnel: dict = {"extracted": len(rows), "dropped": Counter(), "opsin_unparsable_by_class": Counter(), "protocol_sha256": protocol_sha256()}

    eligible = []
    for row in rows:
        name = clean_name(row["raw_name"])
        reason = scope_reason(name, unbalanced(name) != 0)
        if reason is None and not normalise_for_opsin(name).isascii():
            reason = "opsin_unparsable"  # a name py2opsin cannot even WRITE (lambda, kappa, eta): reported with the unparsable, by class
            funnel["opsin_unparsable_by_class"]["not_ascii_for_opsin"] += 1
        if reason:
            funnel["dropped"][reason] += 1
            continue
        eligible.append({**row, "name": name, "opsin_name": normalise_for_opsin(name)})
    funnel["eligible"] = len(eligible)

    names = sorted({r["opsin_name"] for r in eligible})
    parsed, ambiguous = _opsin_batch(names)
    by_structure: dict[str, dict] = {}
    for row in eligible:
        opsin_name = row["opsin_name"]
        if opsin_name not in parsed:
            funnel["dropped"]["opsin_unparsable"] += 1
            funnel["opsin_unparsable_by_class"][chemistry_class(row["name"])] += 1
            continue
        if opsin_name in ambiguous:
            funnel["dropped"]["opsin_ambiguous"] += 1
            continue
        mol = Chem.MolFromSmiles(parsed[opsin_name])
        if mol is None:
            funnel["dropped"]["opsin_unparsable"] += 1
            funnel["opsin_unparsable_by_class"]["smiles_unreadable"] += 1
            continue
        canonical = Chem.MolToSmiles(mol)
        record = by_structure.setdefault(
            canonical,
            {"smiles": canonical, "inchikey": inchi.MolToInchiKey(mol), "chapter": row["chapter"], "pages": [], "targets": [], "wrapped": False,
             "near_page_edge": False, "sections": [], "locations": []},
        )
        if row["name"] not in record["targets"]:
            record["targets"].append(row["name"])
        record["pages"].append(row["page"])
        record["locations"].append({"page": row["page"], "bbox": row["bbox"], "page_size": row["page_size"], "printed": row["name"]})
        record["sections"].append(row["section"])
        record["wrapped"] |= row["wrapped"]
        record["near_page_edge"] |= row["near_page_edge"]
    funnel["opsin_parsed_structures"] = len(by_structure)

    seen_smiles, seen_keys, seen_text = _seen_structures()
    # The harvest's OWN frozen half is not 'seen': a rebuild would otherwise read its previous output as already-looked-at structures and lose half of
    # its pool (measured: unseen 2273 became 1137 on the second run). Every OTHER frozen population is consulted by hash.
    membership = populations.frozen_membership()
    records: list[dict] = []
    seen_records: list[dict] = []
    for canonical, record in sorted(by_structure.items()):
        # A label names one STRUCTURE (its canonical SMILES), never a skeleton: the first InChIKey block is shared by charge and protonation
        # variants, and the whole key by tautomers, so a label from either collided on 11 and 14 rows in the first build. The SPLIT still hashes the
        # InChIKey, so tautomers land in the same half and a near-duplicate never straddles the frozen boundary.
        record["label"] = "bb-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]
        record["retained_name_only"] = all(not re.search(r"[\d-]", t) for t in record["targets"])
        record["multiple_printed_alternatives"] = len(record["targets"]) > 1
        is_seen = seen(canonical, record["inchikey"], record["targets"], seen_smiles, seen_keys, seen_text, membership)
        (seen_records if is_seen else records).append(record)
    funnel["seen"] = len(seen_records)
    funnel["unseen"] = len(records)

    halves = assign_halves(records)
    tuning = [r for r in records if halves[r["label"]] == "tuning"]
    frozen = [r for r in records if halves[r["label"]] == "frozen"]
    funnel["tuning"], funnel["frozen"] = len(tuning), len(frozen)
    funnel["chapters"] = {
        str(c): {"tuning": sum(1 for r in tuning if r["chapter"] == c), "frozen": sum(1 for r in frozen if r["chapter"] == c),
                 "seen": sum(1 for r in seen_records if r["chapter"] == c)}
        for c in range(1, 11)
    }

    def population_row(record: dict) -> dict:
        target = record["targets"][0]
        return {
            "label": record["label"], "category": "bluebook", "smiles": record["smiles"], "kekule_smiles": None, "has_stereo": False,
            # The stage tool scores `pubchem_name`; for this population it holds the BOOK's printed PIN (see benchmarks/naming/README.md). The
            # printed names, every page they appear on, and the oracle flags are the B1-specific fields below.
            "pubchem_name": target, "pubchem_cid": None, "pubchem_name_kind": "Blue Book printed PIN (OPSIN-parsed structure)",
            "pubchem_target_status": "TRUSTED", "preferred_target_status": "ABSENT", "preferred_name": None,
            "accepted_printed_targets": record["targets"], "pages": sorted(set(record["pages"])), "sections": sorted(set(record["sections"])),
            "chapter": record["chapter"], "inchikey": record["inchikey"],
            # where each printed occurrence sits on its page, so a hand check can be reproduced (page, the name's bounding box, the page size)
            "locations": record["locations"],
            "features": {"wrapped": record["wrapped"], "near_page_edge": record["near_page_edge"], "retained_name_only": record["retained_name_only"],
                         "long_name": len(target) > 60, "nested_brackets": "[" in target or target.count("(") >= 2,
                         "has_locants": bool(re.search(r"\d[,-]|-\d", target))},
            "oracle_risk": [flag for flag, on in (("retained_name_only", record["retained_name_only"]),
                                                  ("multiple_printed_alternatives", record["multiple_printed_alternatives"])) if on],
        }

    out_dir.mkdir(parents=True, exist_ok=True)
    digests = {}
    for file_name, group in ((TUNING_FILE, tuning), (FROZEN_FILE, frozen)):
        body = json.dumps([population_row(r) for r in sorted(group, key=lambda r: r["label"])], indent=1, ensure_ascii=False)
        (out_dir / file_name).write_text(body, encoding="utf-8")
        digests[file_name] = hashlib.sha256(body.replace("\r\n", "\n").encode("utf-8")).hexdigest()
    (out_dir / SEEN_FILE).write_text(
        json.dumps([{**population_row(r), "seen": True} for r in sorted(seen_records, key=lambda r: r["label"])], indent=1, ensure_ascii=False), encoding="utf-8"
    )
    funnel["dropped"], funnel["opsin_unparsable_by_class"] = dict(sorted(funnel["dropped"].items())), dict(sorted(funnel["opsin_unparsable_by_class"].items()))
    (out_dir / FUNNEL_FILE).write_text(json.dumps(funnel, indent=1), encoding="utf-8")

    import rdkit

    for file_name, group, is_frozen in ((TUNING_FILE, tuning, False), (FROZEN_FILE, frozen, True)):
        meta = {
            "artifact_schema_version": 1, "variant": "bluebook", "selection_rule": (
                "every '(PIN)' name in BlueBookV2.pdf that passes the protocol's scope filters, is read by OPSIN without an ambiguity warning, and whose structure "
                "the project has not already looked at; assigned to a half by a hash of the InChIKey within its chapter (tools/naming_bluebook_harvest.py)"
            ),
            "engine_consulted": False, "selection_time": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "rows": len(group), "heldout_sha256": digests[file_name],
            "protocol_sha256": funnel["protocol_sha256"], "pdf_sha256": payload["pdf_sha256"], "rdkit_version": rdkit.__version__,
            "stage": "the harvest is scored by tools/naming_stage_artifact.py like any population; `pubchem_name` holds the book's printed PIN",
        }
        if is_frozen:
            meta["membership_salt"] = populations.MEMBERSHIP_SALT
            meta["membership_sha256"] = populations.membership_hashes(group)
            meta["inspection_policy"] = (
                "evaluation only: assigned before any naming round 9 diagnosis of this population, never inspected row by row, loaded only by "
                "naming_stage_artifact.py --final-evaluation"
            )
        else:
            meta["status"] = "TUNING"
        (out_dir / file_name.replace(".json", ".meta.json")).write_text(json.dumps(meta, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in funnel.items() if k != "chapters"}, indent=1))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    e = sub.add_parser("extract", help="PDF -> candidate rows (needs pymupdf)")
    e.add_argument("--pdf", type=Path, required=True)
    e.add_argument("--out", type=Path, required=True, help="a scratch path OUTSIDE the repository: the merged harvest is never committed")
    b = sub.add_parser("build", help="candidate rows -> the two population halves")
    b.add_argument("--extract", type=Path, required=True)
    b.add_argument("--out-dir", type=Path, default=BENCH)
    args = parser.parse_args()
    if args.command == "extract":
        if ROOT in args.out.resolve().parents:
            parser.error("the merged extraction is never written inside the repository")
        extract(args.pdf, args.out)
    else:
        build(args.extract, args.out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
