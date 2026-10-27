"""The COD crystal-density corpus of Phase B (`PREREGISTRATION.md` section 15): extract, then build. Nothing here scores a method.

    python benchmarks/energetics_props/epb_cod_corpus.py extract --archive ".../cod-cifs-mysql.txz" --index ".../cod_index.sqlite" --out ".../corpus"
    python benchmarks/energetics_props/epb_cod_corpus.py build   --out ".../corpus"
    python benchmarks/energetics_props/epb_cod_corpus.py report  --out ".../corpus" --write benchmarks/energetics_props/COD_CORPUS_REPORT.md

**extract** streams the archive once and, for every candidate entry (organic, nitrogen-containing, a diffraction density, a stated
temperature, no stated pressure), records the header fields, the cell, the component class, whether a whole molecule exists in the
cell, the groups and the family found in its connectivity, the entity key (15.3), and, where the entry could be a primary row, the bond
orders perceived from the coordinates. It runs on all cores and is meant to be run as a script (workers import this module by name).

**build** is pure: it reads the records and gives every candidate entry exactly one visible disposition (15.4), resolves entities, assigns
partitions (the 60/20/20 hash of `tools/validation_rows.py`, with the previously examined compounds forced into development, 15.6),
writes the split manifest with its checksum, the pairs the correction study (15.8) will use, and the aggregate summary.

What stays out of Git (15.2): the extracted records and the entity table (a bulk corpus). What is committed: this script, its tests, the
manifest and its checksum, the summary and the generated report. The COD data is CC0; the original authors are acknowledged in the report.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import multiprocessing as mp
import re
import sqlite3
import statistics
import sys
import tarfile
import time
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SCRIPTS = HERE / "inventory_scripts"
BUILDER_VERSION = "epb-cod-corpus-1"

#: Section 15.4 and 3.2: the temperature window, the R-factor ceiling, the spread above which repeats disagree.
WINDOW_K = (273.0, 303.0)
LOW_T_K = (80.0, 160.0)
R_MAX = 0.07
SPREAD_MAX = 0.03
#: Section 15.8: a low/room-temperature pair is kept only if the cell volume ratio V(RT)/V(low) is physically plausible.
PAIR_VOLUME_RATIO = (1.00, 1.08)
EXPLOSOPHORE = ("nitrate_ester", "nitramine", "c_nitro", "azide")
SINGLE_KINDS = ("single", "single_by_geometry")

#: Exactly one per candidate entry, in the order the rules are applied (15.4).
DISPOSITIONS = (
    "unreadable_entry",
    "accepted",
    "not_single_component",
    "no_whole_molecule",
    "no_explosophore_group",
    "temperature_outside_window",
    "r_factor_missing",
    "r_factor_above_cut",
)

_FORMULA_ATOMS = re.compile(r"([A-Z][a-z]?)([0-9.]*)")


def _load(name: str, path: Path):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _sp():
    return _load("cod_structure_pass", SCRIPTS / "cod_structure_pass.py")


def _ix():
    return _load("cod_index", SCRIPTS / "cod_index.py")


def _vr():
    return _load("validation_rows", ROOT / "tools" / "validation_rows.py")


# ------------------------------------------------------------------------------------------------ header and cell fields
_CELL_TAGS = {
    "cell_volume": "_cell_volume", "a": "_cell_length_a", "b": "_cell_length_b", "c": "_cell_length_c",
    "alpha": "_cell_angle_alpha", "beta": "_cell_angle_beta", "gamma": "_cell_angle_gamma",
}


def cell_fields(text: str) -> dict:
    """The unit cell as printed (`293(2)` -> 293.0), `None` for a missing or unreadable field. The correction study (15.8) needs the volume."""
    ix = _ix()
    found: dict[str, float | None] = {k: None for k in _CELL_TAGS}
    wanted = {tag: key for key, tag in _CELL_TAGS.items()}
    for line in text.splitlines():
        if not line.startswith("_cell_"):
            continue
        parts = line.split(None, 1)
        if len(parts) == 2 and parts[0] in wanted:
            found[wanted[parts[0]]] = ix.number(parts[1])
    return found


def formula_counts(formula: str | None) -> dict[str, int]:
    out: dict[str, int] = {}
    for el, n in _FORMULA_ATOMS.findall(formula or ""):
        try:
            out[el] = out.get(el, 0) + (int(float(n)) if n else 1)
        except ValueError:
            return {}
    return out


def _heavy(counts: dict[str, int]) -> dict[str, int]:
    return {k: v for k, v in counts.items() if k != "H"}


def _obfrag_counts(fr) -> dict[str, int]:
    from openbabel import openbabel as ob

    out: dict[str, int] = {}
    for a in ob.OBMolAtomIter(fr):
        sym = ob.GetSymbol(a.GetAtomicNum())
        out[sym] = out.get(sym, 0) + 1
    return out


# ------------------------------------------------------------------------------------------------ bond orders, perceived from coordinates
_NITRO = None


def _nitro_groups(mol) -> list[tuple[int, int, int]]:
    """`(N, O, O)` atom indices of every nitro-type group in a connectivity graph: a three-coordinate nitrogen with two terminal oxygens."""
    from rdkit import Chem

    global _NITRO
    if _NITRO is None:
        _NITRO = Chem.MolFromSmarts("[#7;X3]([#8;X1])[#8;X1]")
    probe = Chem.Mol(mol)
    for atom in probe.GetAtoms():
        atom.SetNoImplicit(True)
    probe.UpdatePropertyCache(strict=False)
    return [tuple(m) for m in probe.GetSubstructMatches(_NITRO)]


def perceive_smiles(fragment, header_formula: str) -> tuple[str | None, str]:
    """A SMILES for one whole molecule, from its coordinates and Open Babel's connectivity, or `(None, reason)`.

    Open Babel's own bond orders were measured unusable (aromatic nitrogens came out four-valent), so only its CONNECTIVITY is used and
    RDKit assigns the orders (`DetermineBondOrders`, total charge 0, charged fragments allowed). That algorithm fails on a ring that carries
    several nitro groups (TNT: "final charge 0 does not match input -2"), and nitro groups are the point of this population, so each nitro group
    is found from the connectivity, swapped for a one-atom placeholder, the rest perceived, and the group restored as `[N+](=O)[O-]`.
    Needs every hydrogen the header formula lists; a structure that cannot be perceived is refused with a coded reason (15.3)."""
    from openbabel import openbabel as ob
    from rdkit import Chem, RDLogger
    from rdkit.Chem import rdDetermineBonds, rdMolDescriptors

    RDLogger.DisableLog("rdApp.*")
    counts = _obfrag_counts(fragment)
    header = formula_counts(header_formula)
    if counts.get("H", 0) != header.get("H", 0):
        return None, "hydrogens_missing"
    rw = Chem.RWMol()
    index = {}
    positions = {}
    for a in ob.OBMolAtomIter(fragment):
        index[a.GetIdx()] = rw.AddAtom(Chem.Atom(a.GetAtomicNum()))
        positions[index[a.GetIdx()]] = (a.GetX(), a.GetY(), a.GetZ())
    for b in ob.OBMolBondIter(fragment):
        rw.AddBond(index[b.GetBeginAtomIdx()], index[b.GetEndAtomIdx()], Chem.BondType.SINGLE)
    graph = rw.GetMol()
    groups = _nitro_groups(graph)
    drop = {o for _n, o1, o2 in groups for o in (o1, o2)}
    keep = [i for i in range(graph.GetNumAtoms()) if i not in drop]
    new_index = {old: new for new, old in enumerate(keep)}
    work = Chem.RWMol()
    for old in keep:
        work.AddAtom(Chem.Atom(17 if any(old == n for n, _o1, _o2 in groups) else graph.GetAtomWithIdx(old).GetAtomicNum()))
    for bond in graph.GetBonds():
        i, j = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
        if i in new_index and j in new_index:
            work.AddBond(new_index[i], new_index[j], Chem.BondType.SINGLE)
    conf = Chem.Conformer(work.GetNumAtoms())
    for old in keep:
        conf.SetAtomPosition(new_index[old], positions[old])
    mol = work.GetMol()
    mol.AddConformer(conf)
    try:
        rdDetermineBonds.DetermineBondOrders(mol, charge=0, allowChargedFragments=True)
    except Exception as exc:  # noqa: BLE001
        return None, "perception_failed: " + type(exc).__name__
    if groups:
        final = Chem.RWMol(mol)
        for n, _o1, _o2 in groups:
            idx = new_index[n]
            atom = final.GetAtomWithIdx(idx)
            atom.SetAtomicNum(7)
            atom.SetFormalCharge(1)
            double = final.AddAtom(Chem.Atom(8))
            single = final.AddAtom(Chem.Atom(8))
            final.GetAtomWithIdx(single).SetFormalCharge(-1)
            final.AddBond(idx, double, Chem.BondType.DOUBLE)
            final.AddBond(idx, single, Chem.BondType.SINGLE)
        mol = final.GetMol()
    try:
        Chem.SanitizeMol(mol)
    except Exception as exc:  # noqa: BLE001
        return None, "perception_failed: " + type(exc).__name__
    if formula_counts(rdMolDescriptors.CalcMolFormula(mol)) != header:
        return None, "formula_mismatch"
    return Chem.MolToSmiles(mol), "perceived"


# ------------------------------------------------------------------------------------------------ one CIF -> one record (heavy; needs Open Babel)
def process_entry(code: str, text: str) -> dict:
    """Everything the build stage needs from one CIF."""
    from openbabel import openbabel as ob
    from openbabel import pybel

    sp, ix = _sp(), _ix()
    ob.obErrorLog.SetOutputLevel(0)
    header = ix.parse(text)
    rec: dict = {
        "code": code, "formula": header.get("formula"), "temperature_k": ix.number(header.get("temperature_raw")),
        "density": ix.number(header.get("density_diffrn_raw")), "r_gt": ix.number(header.get("r_gt_raw")),
        "r_all": ix.number(header.get("r_all_raw")), "pressure_raw": header.get("pressure_raw"),
        "space_group": header.get("space_group"), "z": ix.number(header.get("z_raw")), **cell_fields(text),
    }
    moiety_match = sp._MOIETY.search(text)
    moiety = moiety_match.group(1) if moiety_match else None
    kind, _n = sp.components(moiety)
    rec["components"] = kind
    rec.update(whole_molecule=False, key=None, groups=[], family=None, smiles=None, perception="not_attempted", section5_family=None)
    try:
        mol = pybel.readstring("cif", text)
    except Exception as exc:  # noqa: BLE001
        rec["error"] = "read: " + str(exc)[:80]
        return rec
    target = formula_counts(rec["formula"])
    whole = None
    union_groups: set[str] = set()
    for fr, graph in zip(mol.OBMol.Separate(), sp.graph_from_obmol(mol.OBMol)):
        union_groups.update(sp.families_from_graph(graph)["groups"])
        counts = _obfrag_counts(fr)
        # a stated single moiety proves "one molecule" (hydrogens may be unplaced); without one only the exact formula does
        whole_here = (kind == "single" and _heavy(counts) == _heavy(target)) or (kind == "unknown" and counts == target)
        if whole is None and target and whole_here:
            whole = (fr, graph)
    if whole is None:
        rec["groups"] = sorted(union_groups)
        return rec
    fr, graph = whole
    if kind == "unknown":
        rec["components"] = "single_by_geometry"
    rec["whole_molecule"] = True
    info = sp.families_from_graph(graph)
    rec["groups"] = info["groups"]
    rec["family"] = next((f for f in sp.FAMILY_ORDER[:-1] if f in info["groups"]), "other_organic")
    rec["key"] = sp.entity_key(graph)
    r = rec["r_gt"] if rec["r_gt"] is not None else rec["r_all"]
    could_be_primary = (
        rec["family"] in EXPLOSOPHORE and rec["components"] in SINGLE_KINDS and rec["temperature_k"] is not None
        and WINDOW_K[0] <= rec["temperature_k"] <= WINDOW_K[1] and r is not None and r <= R_MAX)
    if could_be_primary:
        smiles, status = perceive_smiles(fr, rec["formula"])
        rec["perception"] = status
        rec["smiles"] = smiles
        if smiles:
            try:
                rec["section5_family"] = _families().family(smiles)
            except Exception as exc:  # noqa: BLE001
                rec["section5_family"] = "error: " + type(exc).__name__
    return rec


def _families():
    return _load("epb_families", HERE / "epb_families.py")


# ------------------------------------------------------------------------------------------------ candidates and the parallel extract
def candidate_rows(index: Path) -> dict[str, dict]:
    """Organic, nitrogen-containing entries with a diffraction density, a stated temperature and no stated pressure (any temperature:
    the correction study needs the low-temperature ones)."""
    allowed = {"H", "B", "C", "N", "O", "F", "Si", "P", "S", "Cl", "Br", "I"}
    db = sqlite3.connect(index)
    out = {}
    for code, formula, t in db.execute(
        "select code, formula, temperature_k from cod where density_diffrn is not null and temperature_k is not null and pressure_raw is null"
    ):
        counts = formula_counts(formula)
        if "C" in counts and "N" in counts and set(counts) <= allowed:
            out[code] = {"temperature_k": t}
    return out


def _work(item):
    code, text = item
    try:
        return process_entry(code, text)
    except Exception as exc:  # noqa: BLE001 - one bad CIF must not stop 130,000 others, and is counted
        return {"code": code, "error": f"process: {type(exc).__name__}: {str(exc)[:80]}"}


def extract(archive: Path, index: Path, out: Path, workers: int | None = None, limit: int | None = None) -> dict:
    wanted = candidate_rows(index)
    out.mkdir(parents=True, exist_ok=True)
    workers = workers or max(1, (mp.cpu_count() or 2) - 4)
    t0 = time.time()
    n = errors = 0
    batch: list[tuple[str, str]] = []
    with mp.Pool(workers) as pool, open(out / "entries.jsonl", "w", encoding="utf-8") as fh, tarfile.open(archive, mode="r|xz") as tar:
        def flush():
            nonlocal n, errors
            for rec in pool.imap_unordered(_work, batch, chunksize=20):
                fh.write(json.dumps(rec, sort_keys=True) + "\n")
                n += 1
                errors += 1 if "error" in rec else 0
            batch.clear()
            print(f"{n} of {len(wanted)}, {errors} errors, {time.time() - t0:.0f}s", file=sys.stderr, flush=True)

        for member in tar:
            if not (member.isfile() and member.name.endswith(".cif")):
                continue
            code = Path(member.name).stem
            if code not in wanted:
                continue
            batch.append((code, tar.extractfile(member).read().decode("utf-8", errors="replace")))
            if len(batch) >= 3000:
                flush()
            if limit and n + len(batch) >= limit:
                break
        if batch:
            flush()
    return {"candidates": len(wanted), "records": n, "errors": errors, "seconds": round(time.time() - t0, 1), "workers": workers}


# ------------------------------------------------------------------------------------------------ build: pure
def _r(rec: dict) -> float | None:
    return rec["r_gt"] if rec.get("r_gt") is not None else rec.get("r_all")


def disposition(rec: dict) -> str:
    """The ONE disposition of a candidate entry, by the rules of 15.4 in their stated order."""
    if rec.get("error"):
        return "unreadable_entry"
    if rec.get("components") not in SINGLE_KINDS:
        return "not_single_component"
    if not rec.get("whole_molecule"):
        return "no_whole_molecule"
    if rec.get("family") not in EXPLOSOPHORE:
        return "no_explosophore_group"
    t = rec.get("temperature_k")
    if t is None or not WINDOW_K[0] <= t <= WINDOW_K[1]:
        return "temperature_outside_window"
    r = _r(rec)
    if r is None:
        return "r_factor_missing"
    if r > R_MAX:
        return "r_factor_above_cut"
    return "accepted"


def resolve_entity(determinations: list[dict]) -> dict:
    """The label of one entity from its eligible determinations (15.4): forms are (space group, Z) and are never combined; the label is the
    median of one form's densities; a spread over `SPREAD_MAX` is unresolved."""
    forms: dict[tuple, list[float]] = defaultdict(list)
    for d in determinations:
        forms[(d.get("space_group"), d.get("z"))].append(d["density"])
    out: dict = {"n_determinations": len(determinations), "n_forms": len(forms)}
    if len(forms) > 1:
        return {**out, "status": "unresolved_forms"}
    (densities,) = forms.values()
    spread = max(densities) - min(densities)
    if spread - SPREAD_MAX > 1e-9:          # exactly 0.03 is allowed; 1.83 - 1.80 is 0.030000000000000027 in floating point
        return {**out, "status": "unresolved_spread", "spread": spread}
    return {**out, "status": "resolved", "value": statistics.median(densities), "spread": spread, "agreeing": len(densities) >= 2}


def previously_examined_keys() -> dict[str, str]:
    """Entity keys of every compound the earlier energetics survey examined (9.2, 15.6): key -> where it came from. Loud if a source is empty."""
    from rdkit import Chem

    sp = _sp()
    smiles: dict[str, str] = {}
    ce = _load("compare_energetics", ROOT / "benchmarks" / "thermophysical" / "compare_energetics.py")
    for name, spec in ce.MOLECULES.items():
        smiles[spec["smiles"]] = f"compare_energetics:{name}"
    vre = _load("validation_rows_energetics", ROOT / "benchmarks" / "thermophysical" / "validation_rows_energetics.py")
    for row in list(vre.HF_ROWS) + list(vre.TM_ROWS):
        smiles.setdefault(row.smiles, f"validation_rows_energetics:{row.row_id}")
    kim = _load("kim2008_crystal_densities", ROOT / "benchmarks" / "thermophysical" / "kim2008_crystal_densities.py")
    for row in kim.ROWS:
        smiles.setdefault(row.smiles, f"kim2008:{row.printed_name}")
    if len(smiles) < 40:
        raise RuntimeError(f"only {len(smiles)} previously examined structures were found: a source module changed shape")
    keys: dict[str, str] = {}
    for smi, source in smiles.items():
        mol = Chem.MolFromSmiles(smi, sanitize=False)
        if mol is None:
            raise RuntimeError(f"unreadable structure {smi!r} from {source}")
        for frag in Chem.GetMolFrags(mol, asMols=True, sanitizeFrags=False):
            keys.setdefault(sp.entity_key(frag), source)
    return keys


def assign_partition(key: str, forced: dict[str, str]) -> tuple[str, str]:
    """`(partition, reason)`: the 60/20/20 hash of the key, except that a previously examined compound is forced into development (15.6)."""
    if key in forced:
        return "development", "previously_examined"
    return _vr().partition_for(key), "hash"


def build(records: list[dict], forced: dict[str, str]) -> dict:
    """Dispositions, entities, partitions, manifest and aggregate counts from the extracted records. Pure."""
    vr = _vr()
    disp = Counter()
    by_components = Counter()
    accepted: dict[str, list[dict]] = defaultdict(list)
    errors = 0
    for rec in records:
        errors += 1 if rec.get("error") else 0
        by_components[rec.get("components") or "error"] += 1
        d = disposition(rec)
        rec["disposition"] = d
        disp[d] += 1
        if d == "accepted":
            accepted[rec["key"]].append(rec)
    entities = {}
    for key, dets in accepted.items():
        label = resolve_entity(dets)
        partition, why = assign_partition(key, forced)
        perceived = [d for d in dets if d.get("smiles")]
        fams = Counter(d["section5_family"] for d in perceived if d.get("section5_family"))
        entities[key] = {
            "key": key, "partition": partition, "partition_reason": why, **label,
            "connectivity_family": dets[0]["family"], "section5_family": fams.most_common(1)[0][0] if fams else None,
            "structure_perceived": bool(perceived), "codes": sorted(d["code"] for d in dets)[:20], "formula": dets[0]["formula"]}
    manifest = {k: e["partition"] for k, e in sorted(entities.items()) if e["status"] == "resolved"}
    perception = Counter(d["perception"] for dets in accepted.values() for d in dets)
    summary = {
        "builder_version": BUILDER_VERSION, "records": len(records), "extract_errors": errors,
        "dispositions": {d: disp.get(d, 0) for d in DISPOSITIONS}, "components": dict(by_components),
        "entities_with_an_accepted_determination": len(entities),
        "entities_by_label_status": dict(Counter(e["status"] for e in entities.values())),
        "resolved_entities_by_partition": dict(Counter(e["partition"] for e in entities.values() if e["status"] == "resolved")),
        "resolved_entities_with_agreeing_determinations": sum(1 for e in entities.values() if e.get("agreeing")),
        "previously_examined_forced_to_development": sorted(k for k, e in entities.items() if e["partition_reason"] == "previously_examined"),
        "forced_entities": sum(1 for e in entities.values() if e["partition_reason"] == "previously_examined"),
        "perception_of_accepted_determinations": dict(perception),
        "resolved_entities_by_connectivity_family": dict(Counter(e["connectivity_family"] for e in entities.values() if e["status"] == "resolved")),
        "resolved_entities_by_section5_family": dict(Counter(e["section5_family"] or "not_perceived" for e in entities.values() if e["status"] == "resolved")),
        "manifest_checksum": vr.manifest_checksum(manifest), "manifest_entities": len(manifest),
    }
    pairs = pairs_for_study(records)
    summary["pairs"] = {k: v for k, v in pairs.items() if k != "rows"}
    return {"summary": summary, "entities": entities, "manifest": manifest, "pairs": pairs["rows"]}


def pairs_for_study(records: list[dict]) -> dict:
    """The matched low/room-temperature determinations the correction study (15.8) will use: one entity key, one form, one determination at
    80-160 K and one at 273-303 K, both single whole explosophore molecules at R of 0.07 or better, with a cell-volume ratio in the stated range."""
    groups: dict[tuple, dict[str, list[dict]]] = defaultdict(lambda: {"low": [], "rt": []})
    for rec in records:
        if rec.get("error") or not rec.get("whole_molecule") or rec.get("components") not in SINGLE_KINDS:
            continue
        if rec.get("family") not in EXPLOSOPHORE or rec.get("density") is None or rec.get("temperature_k") is None:
            continue
        r = _r(rec)
        if r is None or r > R_MAX:
            continue
        t = rec["temperature_k"]
        form = (rec["key"], rec.get("space_group"), rec.get("z"))
        if LOW_T_K[0] <= t <= LOW_T_K[1]:
            groups[form]["low"].append(rec)
        elif WINDOW_K[0] <= t <= WINDOW_K[1]:
            groups[form]["rt"].append(rec)
    rows = []
    no_volume = out_of_range = 0
    for (key, sg, z), g in groups.items():
        if not g["low"] or not g["rt"]:
            continue
        low = min(g["low"], key=lambda d: d["code"])
        rt = min(g["rt"], key=lambda d: d["code"])
        if not low.get("cell_volume") or not rt.get("cell_volume"):
            no_volume += 1
            continue
        ratio = rt["cell_volume"] / low["cell_volume"]
        if not PAIR_VOLUME_RATIO[0] <= ratio <= PAIR_VOLUME_RATIO[1]:
            out_of_range += 1
            continue
        rows.append({"key": key, "space_group": sg, "z": z, "low_code": low["code"], "rt_code": rt["code"], "t_low": low["temperature_k"],
                     "t_rt": rt["temperature_k"], "rho_low": low["density"], "rho_rt": rt["density"], "volume_ratio": ratio})
    n_matched = no_volume + out_of_range + len(rows)
    return {"matched_before_volume_cut": n_matched, "dropped_no_cell_volume": no_volume, "dropped_volume_ratio_outside": out_of_range,
            "pairs": len(rows), "rows": rows}


def render_report(summary: dict) -> str:
    def table(header, rows):
        return "\n".join(["| " + " | ".join(header) + " |", "|" + "---|" * len(header)] + ["| " + " | ".join(str(c) for c in r) + " |" for r in rows])

    s = summary
    lines = [
        "# Phase B crystal density: the COD corpus (counts only)",
        "",
        ("Generated by `benchmarks/energetics_props/epb_cod_corpus.py report` from the build's `corpus_summary.json`; every number is read from the records. "
        "**No method has been scored and no label compared with a prediction.** The corpus itself (thousands of rows) is kept beside the COD archive, "
        "outside the repository (`PREREGISTRATION.md` 15.2); this report, the split manifest and the aggregate summary are committed. "
        "The Crystallography Open Database is dedicated to the public domain (CC0); the authors of the original structures are acknowledged "
        "through the COD codes the corpus keeps for every entity."),
        "",
        f"Builder `{s['builder_version']}`; split manifest checksum `{s['manifest_checksum']}` ({s['manifest_entities']} entities).",
        "",
        "## What happened to every candidate entry",
        "",
        (f"{s['records']} candidate entries (organic, nitrogen-containing, a diffraction density, a stated temperature, no stated pressure); "
        f"{s['extract_errors']} could not be read. Each has exactly one disposition, applied in this order."),
        "",
        table(["disposition", "entries"], [(d, s["dispositions"][d]) for d in DISPOSITIONS]),
        "",
        "Component class of every candidate: " + ", ".join(f"{k} {v}" for k, v in sorted(s["components"].items())) + ".",
        "",
        "## Entities",
        "",
        f"{s['entities_with_an_accepted_determination']} entities have at least one accepted determination (an entity is one heavy-atom connectivity, `PREREGISTRATION.md` 15.3).",
        "",
        table(["label status (15.4)", "entities"], sorted(s["entities_by_label_status"].items())),
        "",
        table(["partition", "resolved entities"], sorted(s["resolved_entities_by_partition"].items())),
        "",
        (f"{s['resolved_entities_with_agreeing_determinations']} resolved entities have at least two determinations within 0.03 g/cm3 (the agreeing subset, a side check). "
        f"{s['forced_entities']} entities are forced into development as previously examined compounds (15.6)."),
        "",
        "Families of the resolved entities (connectivity groups; first match):",
        "",
        table(["family", "entities"], sorted(s["resolved_entities_by_connectivity_family"].items())),
        "",
        "Section 5 families, where bond orders could be perceived from the coordinates (nitroaromatic and nitroaliphatic are separated here):",
        "",
        table(["family", "entities"], sorted(s["resolved_entities_by_section5_family"].items())),
        "",
        "Bond-order perception for the accepted determinations (a structure that cannot be perceived stays in the corpus and is refused by the methods that need bond orders):",
        "",
        table(["perception", "determinations"], sorted(s["perception_of_accepted_determinations"].items())),
        "",
        "## Low/room-temperature pairs for the correction study (15.8)",
        "",
        table(["step", "count"], [("matched on key, form, 80-160 K and 273-303 K", s["pairs"]["matched_before_volume_cut"]),
                                  ("dropped: no cell volume", s["pairs"]["dropped_no_cell_volume"]),
                                  ("dropped: volume ratio outside [1.00, 1.08]", s["pairs"]["dropped_volume_ratio_outside"]),
                                  ("pairs kept", s["pairs"]["pairs"])]),
        "",
        "## What this does not say",
        "",
        "- Entries and entities are counted, not verified: no disorder, polymorph, hydrate or fit-quality review beyond the rules of 15.4 has been applied.",
        "- A compound that carries one of the four groups is not thereby an energetic material; the claim is about organic crystals that carry such a group.",
        "- COD overlaps the Cambridge Structural Database, so CSD-trained density methods stay unevaluable (15.7).",
        "",
    ]
    return "\n".join(lines)


def run_build(out: Path) -> dict:
    records = [json.loads(line) for line in (out / "entries.jsonl").read_text(encoding="utf-8").splitlines()]
    built = build(records, previously_examined_keys())
    (out / "entities.json").write_text(json.dumps(built["entities"], sort_keys=True), encoding="utf-8")
    (out / "pairs.json").write_text(json.dumps(built["pairs"], sort_keys=True), encoding="utf-8")
    (out / "manifest.json").write_text(json.dumps(built["manifest"], sort_keys=True, indent=0), encoding="utf-8")
    (out / "corpus_summary.json").write_text(json.dumps(built["summary"], sort_keys=True, indent=1), encoding="utf-8")
    return built["summary"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("extract")
    e.add_argument("--archive", type=Path, required=True)
    e.add_argument("--index", type=Path, required=True)
    e.add_argument("--out", type=Path, required=True)
    e.add_argument("--workers", type=int, default=None)
    e.add_argument("--limit", type=int, default=None)
    b = sub.add_parser("build")
    b.add_argument("--out", type=Path, required=True)
    r = sub.add_parser("report")
    r.add_argument("--out", type=Path, required=True)
    r.add_argument("--write", type=Path, required=True)
    args = ap.parse_args(argv)
    if args.cmd == "extract":
        print(extract(args.archive, args.index, args.out, args.workers, args.limit))
    elif args.cmd == "build":
        print(json.dumps(run_build(args.out), indent=1, sort_keys=True))
    else:
        args.write.write_text(render_report(json.loads((args.out / "corpus_summary.json").read_text(encoding="utf-8"))), encoding="utf-8")
    return 0


if __name__ == "__main__":
    mp.freeze_support()
    raise SystemExit(main())
