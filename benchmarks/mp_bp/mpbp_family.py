"""The family-grouped generalisation report (`PREREGISTRATION.md` section 8 and Amendment 3).

**A different claim from the headline, and never merged into it.** The headline asks whether a method predicts new
molecules drawn from the same chemistry it was fitted on (a hash split). This asks whether a method FITTED on some
families predicts a family it has never seen: leave one family out (section 5's 16 families, first match), fit Candidate C
on every other family's entities with the penalty already frozen by selection, and score the family left out. Joback and
Marrero-Gani take no fit, so they are scored on the same entities as references for how hard each family is, not as
generalisation tests.

No threshold was preregistered for this claim, so it carries NO verdict: it is descriptive, with intervals. It uses every
label in the corpus (including the partitions of the headline) because the split here is by family, not by hash; it
selects, tunes and gates nothing. The scoring code of the headline (`mpbp_score.py`) is not touched.

    uv run --no-sync python benchmarks/mp_bp/mpbp_family.py run --corpus D:/_scratch/mp_bp_corpus --out benchmarks/mp_bp/results_family
    uv run --no-sync python benchmarks/mp_bp/mpbp_family.py render --results benchmarks/mp_bp/results_family --write benchmarks/mp_bp/FAMILY_REPORT.md
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

CLAIM = ("generalisation to an unseen structural family: Candidate C fitted on every other family and scored on the one left "
         "out; a different claim from the hash-split headline, descriptive, with no preregistered threshold and no verdict")


def _load(name: str, path: Path):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _score():
    return _load("mpbp_score", HERE / "mpbp_score.py")


def _models():
    return _load("mpbp_models", HERE / "mpbp_models.py")


def all_rows(corpus: dict, prop: str):
    """Every primary-stratum entity with a resolved label for `prop`, across the three hash partitions."""
    score = _score()
    rows = []
    for partition in ("development", "selection", "holdout"):
        rows.extend(score.entity_rows(corpus, prop, partition))
    return rows


def leave_one_family_out(prop: str, rows, features: dict, penalty: float, all_groups: list[str], *, min_training: int = 50) -> dict:
    """Per held-out family: Candidate C fitted on the OTHER families, scored on this one.

    The baseline is the mean label over the training entities (an unseen family has no family mean of its own, so the
    preregistered fallback to the overall mean is the only baseline there is). Returns, per family and per model, the
    absolute errors and signed errors, by entity block, so a caller can pool or bootstrap them."""
    score, m = _score(), _models()
    vr = score.vr_module()
    families = sorted({e["family"] for e, _ in rows})
    out = {}
    for fam in families:
        train = [(e, r) for e, r in rows if e["family"] != fam]
        test = [(e, r) for e, r in rows if e["family"] == fam]
        fit_rows = [(features[e["identity_block"]]["joback"], r.value) for e, r in train
                    if "counts" in features[e["identity_block"]]["joback"]]
        if len(fit_rows) < min_training or not test:
            out[fam] = {"skipped": "too few training entities" if test else "no entities", "n_test": len(test)}
            continue
        fit = m.fit_candidate_c(prop, penalty, [x for x, _ in fit_rows], [y for _, y in fit_rows], all_groups)
        base_value = float(np.mean([r.value for _, r in train]))
        per_model: dict[str, dict] = {}
        for spec in score.MODELS[prop]:
            errs, signed, blocks, refused = [], [], [], 0
            base_errs = []
            for e, r in test:
                feat = features[e["identity_block"]]
                if spec["model"] == "joback":
                    p = m.joback_prediction(feat["joback"], spec["output"])
                elif spec["model"] == "marrero_gani":
                    p = m.mg_prediction(feat["mg"], spec["output"])
                else:
                    p = fit.predict(feat["joback"])
                if p.value is None:
                    refused += 1
                    continue
                errs.append(vr.absolute_error(r, p.value))
                base_errs.append(vr.absolute_error(r, base_value))
                signed.append(p.value - r.value)
                blocks.append(e["identity_block"])
            per_model[spec["model"]] = {"errors": errs, "baseline_errors": base_errs, "signed": signed, "blocks": blocks,
                                        "refused": refused, "gate_eligible": spec["gate_eligible"]}
        out[fam] = {"n_train": len(train), "n_fit": len(fit_rows), "n_test": len(test), "models": per_model,
                    "fit_unfitted_groups": list(fit.unfitted)}
    return out


def summarise(prop: str, lofo: dict, penalty: float) -> list[dict]:
    """One report per (model): pooled over all held-out families, and per family."""
    score = _score()
    reports = []
    for spec in score.MODELS[prop]:
        model = spec["model"]
        by_family, pooled_e, pooled_b, pooled_s, test_total = {}, [], [], [], 0
        for fam, entry in sorted(lofo.items()):
            test_total += entry["n_test"]
            if "skipped" in entry:
                by_family[fam] = {"skipped": entry["skipped"], "n_test": entry["n_test"]}
                continue
            mm = entry["models"][model]
            n = len(mm["errors"])
            row = {"n_test": entry["n_test"], "n_train": entry["n_train"], "n_predicted": n,
                   "coverage": n / entry["n_test"], "claim_supported": n >= score.MIN_STRATUM}
            if n:
                mae = float(np.mean(mm["errors"]))
                base = float(np.mean(mm["baseline_errors"]))
                row.update(mae=mae, baseline_mae=base, improvement=(1.0 - mae / base) if base > 0 else 0.0,
                           bias=float(np.mean(mm["signed"])), refused=mm["refused"])
                if n >= 2:
                    mae_ci, imp_ci = score.bootstrap(mm["errors"], mm["baseline_errors"])
                    row.update(mae_ci95=mae_ci, improvement_ci95=imp_ci)
                pooled_e += mm["errors"]
                pooled_b += mm["baseline_errors"]
                pooled_s += mm["signed"]
            by_family[fam] = row
        pooled = {"n_test": test_total, "n_predicted": len(pooled_e), "coverage": len(pooled_e) / test_total if test_total else 0.0}
        if pooled_e:
            mae_ci, imp_ci = score.bootstrap(pooled_e, pooled_b)
            base = float(np.mean(pooled_b))
            pooled.update(mae=float(np.mean(pooled_e)), mae_ci95=mae_ci, baseline_mae=base,
                          improvement=1.0 - float(np.mean(pooled_e)) / base, improvement_ci95=imp_ci, bias=float(np.mean(pooled_s)))
        reports.append({"claim": CLAIM, "target": prop, "model": model, "model_output": spec["output"],
                        "fitted_here": model == "candidate_c", "gate_eligible": False, "verdict": "none: no threshold was preregistered",
                        "ridge_penalty": penalty if model == "candidate_c" else None, "pooled": pooled, "by_family": by_family,
                        "bootstrap": {"resamples": score.BOOTSTRAP_RESAMPLES, "seed": score.BOOTSTRAP_SEED}})
    return reports


def run(corpus_dir: Path, out_dir: Path) -> list[dict]:
    score = _score()
    corpus = score.load_corpus(corpus_dir)
    features = json.loads((corpus_dir / "features.json").read_text(encoding="utf-8"))
    sys.path.insert(0, str(ROOT / "src"))
    from openchem.chem import joback

    penalties = json.loads((HERE / "results" / "freeze.json").read_text(encoding="utf-8"))["penalties"]
    out_dir.mkdir(parents=True, exist_ok=True)
    reports = []
    for prop in score.PROPERTIES:
        lofo = leave_one_family_out(prop, all_rows(corpus, prop), features, penalties[prop], sorted(joback.groups()))
        for rep in summarise(prop, lofo, penalties[prop]):
            reports.append(rep)
            (out_dir / f"family_{prop}_{rep['model']}.json").write_text(json.dumps(rep, indent=1, sort_keys=True), encoding="utf-8")
    return reports


# ------------------------------------------------------------------------------------------------ the document
def render(results: Path) -> str:
    props = (("normal_boiling_point", "Normal boiling point"), ("melting_point", "Melting point"))
    models = ("candidate_c", "marrero_gani", "joback")
    names = {"candidate_c": "Candidate C (fitted on the other families)", "marrero_gani": "Marrero-Gani first order (not fitted here)",
             "joback": "Joback (not fitted here)"}
    reps = {(p, m): json.loads((results / f"family_{p}_{m}.json").read_text(encoding="utf-8")) for p, _ in props for m in models}

    def table(header, rows):
        return "\n".join(["| " + " | ".join(header) + " |", "|" + "---|" * len(header)] + ["| " + " | ".join(str(c) for c in r) + " |" for r in rows])

    ci = lambda v: f"[{v[0]:.1f}, {v[1]:.1f}]"
    out = [
        "# Melting / normal-boiling-point benchmark: family-grouped generalisation report",
        "",
        ("Generated by `benchmarks/mp_bp/mpbp_family.py render` from `results_family/`; every number is read from those reports. "
        f"**{CLAIM[0].upper() + CLAIM[1:]}.** It is never merged into the headline in `RESULT.md`, and it has no verdict: no threshold was "
        "preregistered for it (`PREREGISTRATION.md` section 8, Amendment 3). The handbook labels carry the printed errors described in "
        "`CORPUS_REPORT.md`."),
        "",
        "## Pooled over every held-out family",
        "",
    ]
    for prop, title in props:
        out += [f"### {title}", "", table(
            ["method", "predicted / entities", "MAE (K)", "baseline MAE (mean of the other families)", "improvement", "bias"],
            [[names[m], f"{reps[(prop, m)]['pooled']['n_predicted']} / {reps[(prop, m)]['pooled']['n_test']}",
              f"{reps[(prop, m)]['pooled']['mae']:.1f} {ci(reps[(prop, m)]['pooled']['mae_ci95'])}",
              f"{reps[(prop, m)]['pooled']['baseline_mae']:.1f}",
              (f"{reps[(prop, m)]['pooled']['improvement']:+.0%} [{reps[(prop, m)]['pooled']['improvement_ci95'][0]:+.0%}, "
              f"{reps[(prop, m)]['pooled']['improvement_ci95'][1]:+.0%}]"), f"{reps[(prop, m)]['pooled']['bias']:+.1f}"] for m in models]), ""]
    head = {p: json.loads((HERE / "results" / f"holdout_{p}_candidate_c.json").read_text(encoding="utf-8"))["metrics"]["mae"] for p, _ in props}
    out += ["## Against the headline", "",
            table(["property", "Candidate C, hash-split holdout (`RESULT.md`)", "Candidate C, pooled unseen families", "difference"],
                  [[title, f"{head[prop]:.1f} K", f"{reps[(prop, 'candidate_c')]['pooled']['mae']:.1f} K",
                    f"{reps[(prop, 'candidate_c')]['pooled']['mae'] - head[prop]:+.1f} K"] for prop, title in props]), "",
            ("The two are on different entities and different fits, so the difference is a measure of how much of the headline depends on "
            "the family having been seen, not a paired comparison. Neither is a verdict."), ""]
    out += ["## By held-out family", "",
            ("Candidate C was fitted without the family named; the baseline is the mean over the entities it was fitted on. A family whose "
            "predicted count is under 30 supports no standalone claim."), ""]
    for prop, title in props:
        fams = sorted(reps[(prop, "candidate_c")]["by_family"])
        rows = []
        for fam in fams:
            c = reps[(prop, "candidate_c")]["by_family"][fam]
            if "skipped" in c:
                rows.append([fam, c["n_test"], "skipped: " + c["skipped"], "", "", "", ""])
                continue
            mg = reps[(prop, "marrero_gani")]["by_family"][fam]
            jb = reps[(prop, "joback")]["by_family"][fam]
            rows.append([fam, c["n_predicted"], f"{c['mae']:.1f}", f"{c['baseline_mae']:.1f}", f"{c['improvement']:+.0%}",
                         f"{mg['mae']:.1f}" if "mae" in mg else "-", f"{jb['mae']:.1f}" if "mae" in jb else "-",
                         "yes" if c["claim_supported"] else "no (n<30)"])
        out += [f"### {title}", "", table(["held-out family", "n predicted (C)", "C MAE (K)", "baseline MAE", "C improvement",
                                           "Marrero-Gani MAE", "Joback MAE", "claim supported"],
                                          [r + [""] * (8 - len(r)) for r in rows]), ""]
    out += ["## What this says and does not say", "",
            ("- The pooled comparison with `RESULT.md` is the measure of how much of Candidate C's headline accuracy depends on the family "
            "having been seen: the headline pools entities of every family, this leaves a family out."),
            ("- Marrero-Gani and Joback are reported on the same entities for scale. They were not fitted here, so their numbers do not "
            "change with the family left out; where one family is far harder for them than for Candidate C, that is a statement about the "
            "family, not about generalisation."),
            ("- Families overlap in chemistry (a nitro compound with a halogen is `nitro` here because the first match wins), so a held-out "
            "family is not chemically isolated from the others; this is the preregistered family definition, not a clean scaffold split."),
            "- Nothing here promotes a calculator or changes a verdict.", ""]
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--corpus", type=Path, required=True)
    r.add_argument("--out", type=Path, required=True)
    d = sub.add_parser("render")
    d.add_argument("--results", type=Path, required=True)
    d.add_argument("--write", type=Path, required=True)
    args = ap.parse_args(argv)
    if args.cmd == "run":
        run(args.corpus, args.out)
    else:
        args.write.write_text(render(args.results), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
