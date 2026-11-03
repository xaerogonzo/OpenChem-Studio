import sys, os, re, json, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
from fieldlib import *

HERE = os.path.dirname(os.path.abspath(__file__))


def analyse(entries):
    R = collections.OrderedDict()
    R["entries"] = len(entries)
    R["entries_with_property_text_parsed"] = sum(1 for e in entries if e.get("src") != "none")
    # --- melting point
    c = collections.Counter()
    for e in entries:
        t = e["vals"].get("Tmp", "")
        if not t:
            continue
        f = mp_features(t)
        if not f["numeric"]:
            continue
        c["numeric"] += 1
        c["dec_marker"] += f["dec"]
        c["range"] += f["range"]
        c["qualifier"] += f["qual"]
        c["any_of_these"] += (f["dec"] or f["range"] or f["qual"])
        c["with_ref"] += f["ref"]
        c["no_ref"] += (not f["ref"])
    R["Tmp"] = dict(c)
    c = collections.Counter()
    for e in entries:
        t = e["vals"].get("Tdec", "")
        if t and has_number(t):
            c["numeric"] += 1
            c["with_ref"] += has_ref(t)
            c["no_ref"] += (not has_ref(t))
    R["Tdec"] = dict(c)
    # --- density
    c = collections.Counter()
    for e in entries:
        t = e["vals"].get("rho", "")
        if not t:
            continue
        its = rho_items(t)
        if not its:
            continue
        c["numeric"] += 1
        c["crystal_any"] += any(i["crystal"] for i in its)
        c["bulk_any"] += any(i["bulk"] for i in its)
        c["tempOnly_any"] += any(i["tempOnly"] for i in its)
        c["unqualified_any"] += any(i["none"] for i in its)
        c["all_items_unqualified"] += all(i["none"] for i in its)
        c["only_crystal_labelled_no_bulk"] += (any(i["crystal"] for i in its) and not any(i["bulk"] for i in its))
        c["spgr_item_any"] += any(i["spgr"] for i in its)
        c["numeric_excluding_spgr_items"] += any(not i["spgr"] for i in its)
        c["unqualified_any_excl_spgr"] += any(i["none"] and not i["spgr"] for i in its)
        c["gives_temperature_any"] += any(i["temp"] for i in its)
        c["with_ref"] += has_ref(t)
        c["no_ref"] += (not has_ref(t))
        c["items_total"] += len(its)
        c["items_crystal"] += sum(i["crystal"] for i in its)
        c["items_bulk"] += sum(i["bulk"] for i in its)
        c["items_unqualified"] += sum(i["none"] for i in its)
    R["rho"] = dict(c)
    # --- heat of formation
    c = collections.Counter()
    units = collections.Counter()
    unit_entries = collections.defaultdict(set)
    for e in entries:
        t = e["vals"].get("Hf", "")
        if not t:
            continue
        its = hf_items(t)
        if not its:
            continue
        c["numeric"] += 1
        c["with_ref"] += has_ref(t)
        c["no_ref"] += (not has_ref(t))
        c["solid_or_liquid_label_any"] += any(i["solid"] for i in its)
        c["liquid_label_any"] += any(i["liquid"] for i in its)
        c["gas_label_any"] += any(i["gas"] for i in its)
        c["no_phase_label_any_item"] += any(not (i["solid"] or i["gas"]) for i in its)
        c["no_phase_label_all_items"] += all(not (i["solid"] or i["gas"]) for i in its)
        c["entry_label_says_calculated_any"] += any(i["calc"] for i in its)
        c["entry_label_says_experimental_any"] += any(i["expt"] for i in its)
        c["entry_label_both_in_one_item"] += any(i["both"] for i in its)
        c["entry_no_calc_or_expt_label_any_item"] += any(not (i["calc"] or i["expt"] or i["both"]) for i in its)
        c["entry_no_label_all_items"] += all(not (i["calc"] or i["expt"] or i["both"]) for i in its)
        c["entry_lit_word_any"] += any(i["lit"] for i in its)
        c["items_total"] += len(its)
        c["items_calc"] += sum(i["calc"] for i in its)
        c["items_expt"] += sum(i["expt"] for i in its)
        c["items_both"] += sum(i["both"] for i in its)
        c["items_nolabel"] += sum(not (i["calc"] or i["expt"] or i["both"]) for i in its)
        for i in its:
            units[i["unit"]] += 1
            unit_entries[i["unit"]].add(e["title"])
    R["Hf"] = dict(c)
    R["Hf_units_items"] = dict(units.most_common())
    R["Hf_units_entries"] = {k: len(v) for k, v in sorted(unit_entries.items(), key=lambda kv: -len(kv[1]))}
    # --- not-single-compound estimate
    nm = collections.Counter()
    for e in entries:
        fm = formula_metals(e.get("formula", "")) if e.get("formula") else []
        e["metals"] = fm
        k_title = bool(MIXKEY.search(e["title"]))
        nm["metal_in_formula"] += bool(fm)
        nm["mix_or_polymer_keyword_in_title"] += k_title
        nm["either"] += bool(fm) or k_title
        nm["formula_known"] += bool(e.get("formula"))
    R["not_single_organic_estimate"] = dict(nm)
    return R


def covered(e):
    if e.get("src") in ("pdf-text", "epub-text"):
        return True
    return e.get("src") == "epub-image-ocr" and e.get("ocr_complete") and bool(e.get("ocr_labels_found"))


if __name__ == "__main__":
    out = {}
    allcov = []
    for vol, fn in (("vol1", "v1_entries.json"), ("vol2", "v2_entries.json"), ("vol3", "v3_entries.json")):
        p = os.path.join(HERE, fn)
        E = json.load(open(p, encoding="utf-8"))
        cov = [e for e in E if covered(e)]
        allcov += cov
        out[vol] = {
            "entries": len(E),
            "src_tally": dict(collections.Counter(e.get("src") for e in E)),
            "ocr_entries_incomplete_or_no_labels": sum(1 for e in E if e.get("src") == "epub-image-ocr" and not covered(e)),
            "entries_covered_by_field_counts": len(cov),
            "coverage_fraction": round(len(cov) / len(E), 3),
            "counts_on_covered_entries": analyse(cov),
        }
    out["total_covered"] = analyse(allcov)
    out["total_entries"] = sum(out[v]["entries"] for v in ("vol1", "vol2", "vol3"))
    out["total_covered_entries"] = len(allcov)
    json.dump(out, open(os.path.join(HERE, "counts.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(out, ensure_ascii=False))
