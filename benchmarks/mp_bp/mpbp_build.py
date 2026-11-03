"""Build the melting / normal-boiling-point corpus from the local handbook PDFs (Phase 2 of `PREREGISTRATION.md`).

Two steps, because the PDF reader needs `pymupdf` (not a project dependency) and the rest needs the project's
environment (RDKit, OPSIN):

    uvx --with pymupdf python -I benchmarks/mp_bp/mpbp_build.py extract --library "D:/.../Sci Downloads" --out <dir>
    uv run --no-sync python benchmarks/mp_bp/mpbp_build.py build --out <dir>

`<dir>` is OUTSIDE Git (beside the library: the Lange and CRC tables are copyrighted). `extract` writes the raw
entries as printed (`raw_lange.json`, `raw_crc.json`) with the source files' SHA-256; `build` writes
`observations.jsonl` (every candidate row and its ONE disposition), `entities.jsonl`, `summary.json` (every count,
generated from the records, never typed) and `manifest.json` (entity key -> partition, which has no values and is
the one corpus artifact committed to the repository). The parser is frozen by `tests/test_mp_bp_corpus.py` before
any selection or holdout score exists; nothing here scores a method.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BUILDER_VERSION = "mp_bp-corpus-1"

#: The recency ranking behind the primary-label rule (`PREREGISTRATION.md` section 4): a handbook is a secondary
#: source, so the value comes from the most recent edition held.
EDITION_YEAR = {"crc97": 2016, "lange15": 1999}

DISPOSITIONS = (
    "accepted_melting_point",
    "accepted_normal_boiling_point",
    "evidence_only_decomposition_or_sublimation",
    "event_not_comparable",
    "pressure_incomparable",
    "parser_ambiguity",
    "identity_unresolved",
    "identity_ambiguous",
    "identity_mismatch",
    "identity_unchecked",
    "source_conflict",
)

#: The conflict threshold of the primary-label rule: values further apart than this (points), or ranges that do not
#: overlap, make the entity unresolved.
CONFLICT_K = 1.0

FAMILIES = (
    ("nitrate_ester", "[OX2][N+](=O)[O-]"),
    ("nitramine", "[NX3][N+](=O)[O-]"),
    ("nitro", "[#6][N+](=O)[O-]"),
    ("halogenated", "[F,Cl,Br,I]"),
    ("carboxylic_acid", "[CX3](=O)[OX2H1]"),
    ("ester", "[CX3](=O)[OX2][#6]"),
    ("amide", "[CX3](=O)[NX3]"),
    ("ketone_aldehyde", "[$([CX3H1](=O)[#6]),$([#6][CX3](=O)[#6])]"),
    ("alcohol_phenol", "[OX2H][#6]"),
    ("amine", "[NX3;!$(NC=O);!$(N[N+](=O)[O-])][#6]"),
    ("nitrile", "[CX2]#N"),
    ("ether", "[OD2]([#6])[#6]"),
    ("sulfur", "[#16]"),
)

_NONMETALS = frozenset(["H", "B", "C", "N", "O", "F", "Si", "P", "S", "Cl", "As", "Se", "Br", "Te", "I"])


def _load(name: str, path: Path):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ------------------------------------------------------------------------------------------------ extract
def extract(library: Path, out: Path) -> None:
    lange = _load("mpbp_lange", HERE / "mpbp_lange.py")
    crc = _load("mpbp_crc", HERE / "mpbp_crc.py")
    out.mkdir(parents=True, exist_ok=True)
    lange_path = library / "Langes Handbook of Chemistry" / "Section 01. Organic Compounds .pdf"
    crc_path = library / "CRC_Handbook_of_Chemistry_and_Physics_97.pdf"
    entries, formulas, report = lange.read_all(lange_path)
    (out / "raw_lange.json").write_text(json.dumps({
        "source": lange.SOURCE_ID, "edition": lange.EDITION, "file": lange_path.name, "sha256": sha256(lange_path),
        "report": report, "formulas": formulas, "entries": [asdict(e) for e in entries],
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    entries, report = crc.read_all(crc_path)
    (out / "raw_crc.json").write_text(json.dumps({
        "source": crc.SOURCE_ID, "edition": crc.EDITION, "file": crc_path.name, "sha256": sha256(crc_path),
        "report": report, "entries": [asdict(e) for e in entries],
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print("extracted", out)


# ------------------------------------------------------------------------------------------------ build
def _stratum(mol, name: str) -> str:
    """Which reported stratum a structure belongs to; only `primary` is in the primary gate."""
    from rdkit import Chem

    if len(Chem.GetMolFrags(mol)) > 1:
        return "multicomponent"
    if sum(a.GetFormalCharge() for a in mol.GetAtoms()) != 0:
        return "ionic"
    symbols = {a.GetSymbol() for a in mol.GetAtoms()}
    if not symbols <= _NONMETALS:
        return "organometallic_or_inorganic"
    carbon_bond = any(
        a.GetSymbol() == "C" and (a.GetTotalNumHs() > 0 or any(n.GetSymbol() == "C" for n in a.GetNeighbors()))
        for a in mol.GetAtoms()
    )
    if not carbon_bond:
        return "not_organic"
    if "poly" in name.lower():
        return "polymer"
    return "primary"


def _family(mol) -> str:
    from rdkit import Chem

    for name, smarts in FAMILIES:
        if mol.HasSubstructMatch(Chem.MolFromSmarts(smarts)):
            return name
    symbols = {a.GetSymbol() for a in mol.GetAtoms()}
    if symbols <= {"C", "H"}:
        return "aromatic_hydrocarbon" if any(a.GetIsAromatic() for a in mol.GetAtoms()) else "aliphatic_hydrocarbon"
    return "other"


def _implausible_row(mp, bp) -> str:
    """A reason when one row's own two cells cannot both be right, else "".

    A melting point at or above a normal boiling point in the SAME row (Lange's 4-bromobenzophenone prints 82 under
    boiling point and 350 under flash point: its columns are shifted) means a cell is in the wrong column, and
    neither can be trusted. Uses nothing but the row itself -- no other source, no label, no prediction.
    """
    if mp is None or bp is None or not (mp.readable and bp.readable):
        return ""
    if mp.event != "melting" or bp.event != "boiling" or bp.pressure_mmhg is not None:
        return ""
    low = mp.low if mp.low is not None else mp.value
    high = bp.high if bp.high is not None else bp.value
    if low is not None and high is not None and low >= high:
        return "implausible_row"
    return ""


def _gap(a: tuple[float, float], b: tuple[float, float]) -> float:
    return max(0.0, max(a[0], b[0]) - min(a[1], b[1]))


def _conflict(observations: list[dict]) -> bool:
    """The primary-label rule's test: any two surviving observations further apart than 1.0 K (points), or two
    ranges that do not overlap."""
    for i, a in enumerate(observations):
        for b in observations[i + 1:]:
            ia, ib = (a["low_k"], a["high_k"]), (b["low_k"], b["high_k"])
            both_ranges = a["is_range"] and b["is_range"]
            if _gap(ia, ib) > (0.0 if both_ranges else CONFLICT_K):
                return True
    return False


def build(out: Path) -> dict:
    cells = _load("mpbp_cells", HERE / "mpbp_cells.py")
    identity = _load("mpbp_identity", HERE / "mpbp_identity.py")
    sys.path.insert(0, str(ROOT / "src"))
    from rdkit import Chem

    vr = _load("validation_rows", ROOT / "tools" / "validation_rows.py")
    from openchem.chem.naming_providers import opsin_structures_for_names

    raw_lange = json.loads((out / "raw_lange.json").read_text(encoding="utf-8"))
    raw_crc = json.loads((out / "raw_crc.json").read_text(encoding="utf-8"))

    # ---- candidate source entries, one uniform shape --------------------------------------------------------
    sources = []
    for e in raw_lange["entries"]:
        sources.append({
            "source": "lange15", "entry": e["entry_id"], "page": e["pdf_page"], "name_lines": e["name_lines"],
            "extra_names": [], "formula": raw_lange["formulas"].get(e["entry_id"]), "weight": e["weight"],
            "mp_lines": e["mp_lines"], "bp_lines": e["bp_lines"], "reader": cells.read_lange,
            "cas": "", "glyphs": e["unreadable_glyphs"],
        })
    for e in raw_crc["entries"]:
        sources.append({
            "source": "crc97", "entry": e["entry_no"], "page": e["pdf_page"], "name_lines": e["name_lines"],
            "extra_names": [e["synonym_lines"]] if e["synonym_lines"] else [], "formula": e["formula"] or None,
            "weight": e["weight"], "mp_lines": e["mp_lines"], "bp_lines": e["bp_lines"], "reader": cells.read_crc,
            "cas": e["cas"], "glyphs": 0,
        })

    # ---- names -> structures, ONE OPSIN start for all of them ------------------------------------------------
    for s in sources:
        s["spellings"], s["name_problem"] = identity.name_spellings(s["name_lines"], s["extra_names"])
    unique = sorted({sp for s in sources for sp in s["spellings"]})
    print(f"resolving {len(unique)} spellings of {len(sources)} entries", file=sys.stderr)
    resolved_map: dict[str, str | None] = {}
    BATCH = 4000
    for i in range(0, len(unique), BATCH):
        for spelling, result in zip(unique[i:i + BATCH], opsin_structures_for_names(unique[i:i + BATCH])):
            resolved_map[spelling] = result.smiles if result else None

    # ---- identity, per source entry ---------------------------------------------------------------------------
    for s in sources:
        if s["name_problem"]:
            s["identity"] = identity.Identity("unresolved", reason=s["name_problem"])
        else:
            s["identity"] = identity.check(
                [(sp, resolved_map.get(sp)) for sp in s["spellings"]], s["formula"], s["weight"])

    # ---- one disposition per (entry, property) candidate row ----------------------------------------------------
    observations: list[dict] = []
    for s in sources:
        readings = {col: s["reader"](col, s[col + "_lines"]) for col in ("mp", "bp")}
        implausible = _implausible_row(readings["mp"], readings["bp"])
        for prop, column in (("melting_point", "mp"), ("normal_boiling_point", "bp")):
            reading = readings[column]
            if reading is None:
                continue
            if implausible and reading.readable:
                reading = cells.Reading(printed=reading.printed, event="unreadable", problem=implausible)
            record = {
                "record_id": f"{s['source']}:{s['entry']}:{column}", "source": s["source"], "entry": s["entry"],
                "pdf_page": s["page"], "property": prop, "printed": reading.printed, "event": reading.event,
                "notation": reading.notation, "pressure_mmhg": reading.pressure_mmhg,
                "uncertainty": reading.uncertainty, "name": " ".join(s["name_lines"]), "cas": s["cas"],
                "identity_status": s["identity"].status, "identity_reason": s["identity"].reason,
                "smiles": s["identity"].smiles, "reason": "", "disposition": "",
            }
            if not reading.readable:
                record.update(disposition="parser_ambiguity", reason=reading.problem)
            elif s["identity"].status != "ok":
                record["disposition"] = {
                    "unresolved": "identity_unresolved", "ambiguous": "identity_ambiguous",
                    "mismatch": "identity_mismatch", "unchecked": "identity_unchecked",
                }[s["identity"].status]
                record["reason"] = s["identity"].reason
            else:
                _decide(record, reading, vr)
            observations.append(record)

    # ---- entities ----------------------------------------------------------------------------------------------
    entities: dict[str, dict] = {}
    for o in observations:
        if not o["smiles"] or o["identity_status"] != "ok":
            continue
        block = vr.identity_block(o["smiles"])
        o["identity_block"] = block
        entity = entities.setdefault(block, {
            "identity_block": block, "smiles": o["smiles"], "name": o["name"], "sources": set(), "labels": {},
        })
        entity["sources"].add(o["source"])
        # The representative structure and name come from the most recent edition held.
        if o["source"] == "crc97" and entity.get("rep_source") != "crc97":
            entity.update(smiles=o["smiles"], name=o["name"], rep_source="crc97")
    for entity in entities.values():
        mol = Chem.MolFromSmiles(entity["smiles"])
        entity["stratum"] = _stratum(mol, entity["name"])
        entity["family"] = _family(mol)
        entity["partition"] = vr.partition_for(vr.split_group_key(entity["smiles"]))
    by_entity: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for o in observations:
        if o["disposition"] in ("accepted_melting_point", "accepted_normal_boiling_point"):
            by_entity[(o["identity_block"], o["property"])].append(o)
    cross_source = Counter()
    for (block, prop), obs in sorted(by_entity.items()):
        latest = max(EDITION_YEAR[o["source"]] for o in obs)
        surviving = [o for o in obs if EDITION_YEAR[o["source"]] == latest]
        label = {"n_observations": len(obs), "n_surviving": len(surviving), "edition_year": latest}
        if _conflict(surviving):
            label["status"] = "unresolved_conflict"
            for o in obs:
                o["provisional_disposition"] = o["disposition"]
                o["disposition"] = "source_conflict"
                o["reason"] = "the most recent edition's observations disagree by more than 1.0 K"
        else:
            chosen = min(surviving, key=lambda o: (o["source"], o["entry"]))
            label.update(status="resolved", record_id=chosen["record_id"], value_k=chosen["value_k"],
                         low_k=chosen["low_k"], high_k=chosen["high_k"], is_range=chosen["is_range"])
        srcs = {o["source"] for o in obs}
        if srcs == {"crc97", "lange15"}:
            crc_obs = [o for o in obs if o["source"] == "crc97"]
            lange_obs = [o for o in obs if o["source"] == "lange15"]
            agree = not _conflict([crc_obs[0], lange_obs[0]])
            cross_source[(prop, "agree" if agree else "disagree")] += 1
            label["cross_source"] = "agree" if agree else "disagree"
        else:
            label["cross_source"] = "single_source"
        entities[block]["labels"][prop] = label

    summary = _summary(sources, observations, entities, cross_source, raw_lange, raw_crc)
    manifest = {
        block: e["partition"] for block, e in sorted(entities.items())
        if any(l["status"] == "resolved" for l in e["labels"].values()) and e["stratum"] == "primary"
    }
    summary["manifest_checksum"] = vr.manifest_checksum(manifest)
    summary["builder_version"] = BUILDER_VERSION
    summary["source_files"] = {
        "lange15": {"file": raw_lange["file"], "sha256": raw_lange["sha256"], "edition": raw_lange["edition"]},
        "crc97": {"file": raw_crc["file"], "sha256": raw_crc["sha256"], "edition": raw_crc["edition"]},
    }
    with open(out / "observations.jsonl", "w", encoding="utf-8") as fh:
        for o in observations:
            fh.write(json.dumps(o, ensure_ascii=False, sort_keys=True) + "\n")
    with open(out / "entities.jsonl", "w", encoding="utf-8") as fh:
        for e in entities.values():
            fh.write(json.dumps({**e, "sources": sorted(e["sources"])}, ensure_ascii=False, sort_keys=True) + "\n")
    (out / "summary.json").write_text(json.dumps(summary, indent=1, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    (out / "manifest.json").write_text(json.dumps(manifest, indent=0, sort_keys=True), encoding="utf-8")
    return summary


def _decide(record: dict, reading, vr) -> None:
    """Event and pressure admission, using the REAL admission functions of `tools/validation_rows.py`."""
    prop = record["property"]
    event = reading.event
    if not reading.has_temperature and event in ("melting", "boiling"):
        record.update(disposition="parser_ambiguity", reason="no temperature")
        return
    value_c = reading.value if reading.value is not None else None
    low_c, high_c = reading.low, reading.high
    if event in vr.NO_LABEL_EVENTS and event != "unknown":
        reason = f"the table reports {event}, which is not a {prop.replace('_', ' ')}"
        # Built only to be validated: a record with no value, so it can never be mistaken for a label.
        vr.NoEventRecord(
            record_id=record["record_id"], smiles=record["smiles"], target_property=prop, observed_event=event,
            source_id=record["source"], locator=f"{record['source']} p{record['pdf_page']} entry {record['entry']}",
            reason=reason,
        )
        record.update(disposition="evidence_only_decomposition_or_sublimation", reason=reason)
        return
    if event == "unknown":
        record.update(disposition="event_not_comparable", reason=f"notation {reading.notation!r} is not a clean event")
        return
    pressure_pa = reading.pressure_mmhg * 101_325.0 / 760.0 if reading.pressure_mmhg is not None else None
    basis = "stated" if pressure_pa is not None else "table_convention_normal"
    to_k = lambda c: None if c is None else round(c + 273.15, 6)
    value_k = to_k(value_c if value_c is not None else (low_c + high_c) / 2.0)
    row = vr.ValidationRow(
        row_id=record["record_id"], smiles=record["smiles"], property=prop, value=value_k, units="K",
        source_id=record["source"], record_id=record["record_id"], partition="development",
        transition_type=event, value_source="secondary",
        reference_pressure_pa=pressure_pa, pressure_basis=basis if prop == "normal_boiling_point" else None,
        reported_value=reading.printed, reported_unit="C",
        range_low=to_k(low_c), range_high=to_k(high_c), normalisation_method="C to K (+273.15)",
        locator=f"{record['source']} p{record['pdf_page']} entry {record['entry']}",
    )
    refusal = (vr.admit_to_melting_point_set(row) if prop == "melting_point"
               else vr.admit_to_normal_boiling_point_set(row))
    if refusal is None:
        record.update(
            disposition="accepted_melting_point" if prop == "melting_point" else "accepted_normal_boiling_point",
            value_k=value_k, low_k=to_k(low_c) if low_c is not None else value_k,
            high_k=to_k(high_c) if high_c is not None else value_k, is_range=low_c is not None,
            pressure_basis=row.pressure_basis, reference_pressure_pa=pressure_pa,
        )
    elif "pressure" in refusal.lower():
        record.update(disposition="pressure_incomparable", reason=refusal)
    else:
        record.update(disposition="event_not_comparable", reason=refusal)


def _summary(sources, observations, entities, cross_source, raw_lange, raw_crc) -> dict:
    disp = Counter(o["disposition"] for o in observations)
    by_source = defaultdict(Counter)
    for o in observations:
        by_source[o["source"]][o["disposition"]] += 1
    ident = Counter((s["source"], s["identity"].status) for s in sources)
    resolved = defaultdict(int)
    primary = defaultdict(int)
    strata = Counter()
    families: dict[str, Counter] = {"melting_point": Counter(), "normal_boiling_point": Counter()}
    partitions: dict[str, Counter] = {"melting_point": Counter(), "normal_boiling_point": Counter()}
    unresolved = Counter()
    cross = Counter()
    for e in entities.values():
        strata[e["stratum"]] += 1
        for prop, label in e["labels"].items():
            if label["status"] == "resolved":
                resolved[prop] += 1
                if e["stratum"] == "primary":
                    primary[prop] += 1
                    cross[(prop, label["cross_source"])] += 1
                    families[prop][e["family"]] += 1
                    partitions[prop][e["partition"]] += 1
            else:
                unresolved[prop] += 1
    no_event = Counter((o["property"], o["event"]) for o in observations
                       if o["disposition"] == "evidence_only_decomposition_or_sublimation")
    return {
        "source_entries": {"lange15": sum(1 for s in sources if s["source"] == "lange15"),
                           "crc97": sum(1 for s in sources if s["source"] == "crc97")},
        "lange_pages_skipped": raw_lange["report"].get("skipped_pages", []),
        "candidate_rows": len(observations),
        "dispositions": {d: disp.get(d, 0) for d in DISPOSITIONS},
        "dispositions_by_source": {k: dict(v) for k, v in by_source.items()},
        "identity_by_source": {f"{k[0]}:{k[1]}": v for k, v in sorted(ident.items())},
        "entities_with_a_structure": len(entities),
        "entities_by_stratum": dict(strata),
        "entities_with_resolved_label": dict(resolved),
        "entities_with_resolved_label_in_primary_stratum": dict(primary),
        "entities_unresolved_by_conflict": dict(unresolved),
        "primary_stratum_by_cross_source": {f"{p}:{k}": n for (p, k), n in sorted(cross.items())},
        "primary_stratum_by_family": {p: dict(c) for p, c in families.items()},
        "primary_stratum_by_partition": {p: dict(c) for p, c in partitions.items()},
        "no_label_event_records": {f"{p}:{ev}": n for (p, ev), n in sorted(no_event.items())},
        "cross_source_agreement": {f"{p}:{k}": n for (p, k), n in sorted(cross_source.items())},
    }


def render_report(summary: dict) -> str:
    """The corpus quality report, every number read from `summary.json` (never typed)."""
    def table(header, rows):
        out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
        out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
        return "\n".join(out)

    d = summary["dispositions"]
    src = summary["dispositions_by_source"]
    fam = summary["primary_stratum_by_family"]
    lines = [
        "# Melting / normal-boiling-point corpus: quality report",
        "",
        ("Generated by `benchmarks/mp_bp/mpbp_build.py report` from the build's `summary.json`; every number below is "
        "read from the records, none is typed. **No method has been scored on this corpus.** The reference values are "
        "copyrighted handbook tables and are not in the repository; this report, the split manifest "
        "(`split_manifest.json`) and the aggregate `corpus_summary.json` are."),
        "",
        f"Builder `{summary['builder_version']}`; split manifest checksum `{summary['manifest_checksum']}`.",
        "",
        "## Sources",
        "",
        table(["source", "file", "edition", "SHA-256"], [
            (k, v["file"], v["edition"], v["sha256"]) for k, v in summary["source_files"].items()]),
        "",
        (f"Entries read: Lange {summary['source_entries']['lange15']}, CRC {summary['source_entries']['crc97']}. "
        f"Lange pages not read: {len(summary['lange_pages_skipped'])} "
        f"({', '.join(str(p['pdf_page']) for p in summary['lange_pages_skipped'])}: three are pure cross-reference "
        "pages, and one is a page of the table whose cells carry no text)."),
        "",
        "## What happened to every candidate row",
        "",
        (f"A candidate row is one (entry, property) pair with a non-empty cell: {summary['candidate_rows']} in all. "
        "Each has exactly one disposition."),
        "",
        table(["disposition", "all", "Lange", "CRC"], [
            (n, d[n], src.get("lange15", {}).get(n, 0), src.get("crc97", {}).get(n, 0)) for n in DISPOSITIONS]),
        "",
        "## Identity (per source entry)",
        "",
        table(["source : status", "entries"], sorted(summary["identity_by_source"].items())),
        "",
        "## Entities",
        "",
        f"{summary['entities_with_a_structure']} entities have an accepted structure.",
        "",
        table(["stratum", "entities"], sorted(summary["entities_by_stratum"].items())),
        "",
        "Entities with a resolved label, by property (the primary stratum is the primary gate's population):",
        "",
        table(["property", "all strata", "primary stratum", "unresolved by conflict"], [
            (p, summary["entities_with_resolved_label"].get(p, 0),
             summary["entities_with_resolved_label_in_primary_stratum"].get(p, 0),
             summary["entities_unresolved_by_conflict"].get(p, 0)) for p in ("melting_point", "normal_boiling_point")]),
        "",
        "### Partitions of the primary stratum",
        "",
        table(["property", "development", "selection", "holdout"], [
            (p, *(summary["primary_stratum_by_partition"][p].get(k, 0) for k in ("development", "selection", "holdout")))
            for p in ("melting_point", "normal_boiling_point")]),
        "",
        "### Label quality (secondary analysis, not a gate)",
        "",
        ("An entity read from both books is `agree` when the two values are within 1.0 K (ranges: overlapping), else "
        "`disagree`. Agreement is transcription consistency, not independent replication (the CRC lists the "
        "Handbook of Data on Organic Compounds and the Combined Chemical Dictionary among its sources). The primary "
        "label is the CRC value regardless; the subsets are for the sensitivity analysis."),
        "",
        table(["property : status", "primary-stratum entities"], sorted(summary["primary_stratum_by_cross_source"].items())),
        "",
        "### Families of the primary stratum (a family under 30 entities supports no standalone claim)",
        "",
    ]
    families = sorted({f for p in fam.values() for f in p})
    lines.append(table(["family", "melting_point", "normal_boiling_point", "note"], [
        (f, fam["melting_point"].get(f, 0), fam["normal_boiling_point"].get(f, 0),
         "under 30 in at least one property" if min(fam["melting_point"].get(f, 0), fam["normal_boiling_point"].get(f, 0)) < 30 else "")
        for f in families]))
    lines += [
        "",
        "## Rows with no numeric label (evidence only)",
        "",
        ("A decomposition, a melting point with decomposition or a sublimation is recorded and counted; it is never a "
        "label and never a placeholder temperature (`NoEventRecord`)."),
        "",
        table(["property : event", "rows"], sorted(summary["no_label_event_records"].items())),
        "",
        "## Known faults in the handbooks themselves",
        "",
        ("The parser reads what the page prints, and the page is sometimes wrong. Checked on the rendered pages: Lange "
        "prints 2,2,3,3-tetramethylbutane's melting point as -100.7 (it melts at +100.7), triethylborane's as -02.9 "
        "(-92.9 with a digit lost), 1,5-pentanediamine's as -129.7 (the value of pentane, one row above) and "
        "3-bromopyridine's as 142-143 (it melts at -27); 4-bromobenzophenone's row has its values one column to the "
        "right; the CRC prints 6-methyl-5-hepten-2-one's boiling point under melting point. A within-row check "
        "(a melting point at or above the normal boiling point of the same row) and a malformed-number check "
        "(02.9) refuse some of these; the rest are what the label-quality subsets above exist to measure. "
        "The corpus measures handbook values, and says so."),
        "",
    ]
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("extract")
    e.add_argument("--library", type=Path, required=True)
    e.add_argument("--out", type=Path, required=True)
    b = sub.add_parser("build")
    b.add_argument("--out", type=Path, required=True)
    r = sub.add_parser("report")
    r.add_argument("--out", type=Path, required=True)
    r.add_argument("--write", type=Path, required=True, help="where to write the markdown report")
    args = ap.parse_args(argv)
    if args.cmd == "extract":
        extract(args.library, args.out)
    elif args.cmd == "report":
        summary = json.loads((args.out / "summary.json").read_text(encoding="utf-8"))
        args.write.write_text(render_report(summary), encoding="utf-8")
    else:
        print(json.dumps(build(args.out), indent=1, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
