"""Check ChatGPT (or other) template drafts: parse, stereo, duplicates.

    python tools/template_draft_check.py exclude
    python tools/template_draft_check.py check path.json
    python tools/template_draft_check.py check path.json --pubchem-key

Drafts are research JSON. This does not write shipped catalogs.
PubChem is asked by InChIKey only, never by name.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SHIPPED_DIR = ROOT / "src" / "openchem" / "chem" / "data" / "structure_templates"

#: Tokens in a display name that mean the SMILES must carry stereo.
#: Parentheses match CIP labels such as (R), (S), or (1R,4R) — not any
#: letter r/s inside a substituent name ((4-chlorophenyl), (propyl)).
_STEREO_IN_NAME = re.compile(
    r"(?ix)"
    r"\b(?:cis|trans|endo|exo|syn|anti|anomer)\b"
    r"|[αβ]\b"
    r"|\b(?:alpha|beta)-"
    r"|\b[LD]-"
    r"|\((?:[0-9]+)?[RS](?:\s*,\s*[0-9]*[RS])*\)"
)

_STEREO_IN_SMILES = re.compile(r"[@/\\]")


def name_implies_stereo(name: str) -> bool:
    """True when the English (or IUPAC-ish) name claims a stereoisomer."""
    return bool(_STEREO_IN_NAME.search(name or ""))


def smiles_has_stereo(smiles: str) -> bool:
    """True when the SMILES writes tetrahedral or double-bond stereo."""
    return bool(_STEREO_IN_SMILES.search(smiles or ""))


def load_shipped_index() -> dict[str, Any]:
    """Shipped stems, names, and InChIKeys for duplicate checks."""
    from rdkit.Chem.inchi import MolToInchiKey

    from openchem.chem.engine import ChemistryEngine

    engine = ChemistryEngine()
    stems: list[dict[str, str]] = []
    keys: dict[str, str] = {}
    ids: set[str] = set()
    names: set[str] = set()
    for path in sorted(SHIPPED_DIR.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        category = raw["id"]
        for entry in raw.get("entries") or []:
            eid = entry["id"]
            stem = eid.split(".", 1)[1] if "." in eid else eid
            name = entry["name"]
            smiles = entry.get("smiles") or ""
            ids.add(stem)
            names.add(name.casefold())
            inchikey = ""
            if smiles:
                mol = engine.mol_from_smiles(smiles)
                inchikey = MolToInchiKey(mol)
                keys[inchikey] = eid
            stems.append(
                {
                    "id": stem,
                    "shipped_id": eid,
                    "name": name,
                    "category_id": category,
                    "inchikey": inchikey,
                }
            )
    return {"entries": stems, "ids": ids, "names": names, "inchikeys": keys}


def _parse_draft_file(path: Path) -> list[dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict) and isinstance(raw.get("entries"), list):
        return raw["entries"]
    raise ValueError(f"{path}: expected a list or an object with 'entries'")


def check_entry(entry: dict[str, Any], shipped: dict[str, Any]) -> dict[str, Any]:
    """One draft row: parse, stereo gate, duplicate against shipped."""
    from rdkit.Chem.inchi import MolToInchiKey

    from openchem.chem.engine import ChemistryEngine, InvalidStructureError

    stem = str(entry.get("id") or "").strip()
    name = str(entry.get("name") or "").strip()
    smiles = str(entry.get("smiles") or "").strip()
    category = str(entry.get("category_id") or "").strip()
    row: dict[str, Any] = {
        "id": stem,
        "name": name,
        "category_id": category,
        "status": "ok",
        "reasons": [],
        "inchikey": "",
    }
    if not stem or not name or not smiles or not category:
        row["status"] = "refused"
        row["reasons"].append("missing id, name, smiles, or category_id")
        return row
    if "*" in smiles:
        row["status"] = "refused"
        row["reasons"].append("dummy atom")
        return row
    if stem in shipped["ids"] or name.casefold() in shipped["names"]:
        row["status"] = "duplicate_shipped"
        row["reasons"].append("id or name already shipped")
    stereo_name = bool(entry.get("stereo_in_name")) or name_implies_stereo(name)
    if stereo_name and not smiles_has_stereo(smiles):
        row["status"] = "needs_stereo"
        row["reasons"].append("name implies stereo but SMILES has no @ / or \\")
    engine = ChemistryEngine()
    try:
        mol = engine.mol_from_smiles(smiles)
    except InvalidStructureError as exc:
        row["status"] = "refused"
        row["reasons"].append(f"parse: {exc}")
        return row
    if any(atom.GetAtomicNum() == 0 for atom in mol.GetAtoms()):
        row["status"] = "refused"
        row["reasons"].append("dummy or query atom")
        return row
    key = MolToInchiKey(mol)
    row["inchikey"] = key
    if key in shipped["inchikeys"]:
        row["status"] = "duplicate_shipped"
        row["reasons"].append(f"same InChIKey as {shipped['inchikeys'][key]}")
    return row


def check_drafts(path: Path) -> dict[str, Any]:
    """Score every entry in a draft file against the shipped catalog."""
    shipped = load_shipped_index()
    entries = _parse_draft_file(path)
    seen_ids: set[str] = set()
    seen_keys: dict[str, str] = {}
    rows = []
    for entry in entries:
        row = check_entry(entry, shipped)
        stem = row["id"]
        if stem in seen_ids:
            row["status"] = "duplicate_draft"
            row["reasons"].append("id repeated in this file")
        seen_ids.add(stem)
        key = row.get("inchikey") or ""
        if key and key in seen_keys:
            row["status"] = "duplicate_draft"
            row["reasons"].append(f"same InChIKey as draft {seen_keys[key]}")
        if key:
            seen_keys[key] = stem
        rows.append(row)
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    return {"file": str(path), "n": len(rows), "counts": counts, "rows": rows}


def _pubchem_by_inchikey(inchikey: str) -> dict[str, Any]:
    from openchem.net import open_url

    quoted = urllib.parse.quote(inchikey, safe="")
    url = (
        "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/inchikey/"
        f"{quoted}/property/Title,MolecularFormula,IsomericSMILES,InChIKey/JSON"
    )
    with open_url(url, timeout=25) as response:
        payload = json.loads(response.read().decode("utf-8"))
    props = (payload.get("PropertyTable") or {}).get("Properties") or []
    if not props:
        return {"found": False}
    rec = props[0]
    return {
        "found": True,
        "cid": rec.get("CID"),
        "title": rec.get("Title"),
        "formula": rec.get("MolecularFormula"),
        "isomeric_smiles": rec.get("IsomericSMILES"),
        "inchikey": rec.get("InChIKey"),
    }


def attach_pubchem(report: dict[str, Any]) -> None:
    """Fill PubChem-by-key on rows that parsed. Sleeps between calls."""
    for row in report["rows"]:
        if row["status"] == "refused" or not row.get("inchikey"):
            row["pubchem"] = {"found": False, "skipped": True}
            continue
        try:
            row["pubchem"] = _pubchem_by_inchikey(row["inchikey"])
        except Exception as exc:  # noqa: BLE001 — network/parse, report and continue
            row["pubchem"] = {"found": False, "error": str(exc)}
        time.sleep(0.25)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("exclude", help="print shipped {id, name} JSON for the ChatGPT prompt")
    check = sub.add_parser("check", help="score a draft JSON file")
    check.add_argument("path", type=Path)
    check.add_argument(
        "--pubchem-key",
        action="store_true",
        help="confirm each InChIKey on PubChem (never look up by name)",
    )
    args = parser.parse_args(argv)
    if args.cmd == "exclude":
        shipped = load_shipped_index()
        payload = [{"id": e["id"], "name": e["name"]} for e in shipped["entries"]]
        json.dump(payload, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
        return 0
    report = check_drafts(args.path)
    if args.pubchem_key:
        attach_pubchem(report)
    json.dump(report, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    bad = report["n"] - report["counts"].get("ok", 0)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
