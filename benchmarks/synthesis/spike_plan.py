"""One AiZynthFinder search of one target, run by the PLANNER's own Python (never OpenChem's), for the Stage 0 spike (`docs/SYNTHESIS_HELPER_DESIGN.md`).

    <planner python> spike_plan.py --config config.yml --target "CC(=O)Oc1ccccc1C(=O)O" --iteration-limit 100 --time-limit 600

The contract Stage 1's runner will keep, shown here so the spike measures it: **stdout is ONE JSON document**; everything the library prints, warns or logs goes to stderr; the limits are set explicitly and echoed back; the planner's identity (versions, config file hash, the selected models and stock) rides with the result; a failure is still one JSON document with `"status": "failed"` and a reason, and a non-zero exit. Nothing here retries or changes a limit.
What it records, so that nothing is claimed that was not measured: wall-clock for the import, the configuration, the model and stock load and the search; the peak working set; the planner's own statistics; and the raw route dictionaries and scores, untouched.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
import time
import traceback
import warnings

SCHEMA = "spike-1"


def _identity(config_path: str, selection: dict) -> dict:
    from importlib.metadata import version

    with open(config_path, "rb") as handle:
        digest = hashlib.sha256(handle.read()).hexdigest()
    packages = {}
    for name in ("aizynthfinder", "onnxruntime", "numpy", "rdkit", "pyarrow"):
        try:
            packages[name] = version(name)
        except Exception:  # noqa: BLE001 - a missing package is data, not an error here
            packages[name] = None
    return {"planner": "aizynthfinder", "packages": packages, "python": sys.version.split()[0], "config_sha256": digest, "selection": selection}


def _peak_mb() -> float | None:
    try:
        import psutil

        info = psutil.Process(os.getpid()).memory_info()
        return round(getattr(info, "peak_wset", info.rss) / 1e6, 1)
    except Exception:  # noqa: BLE001
        return None


def run(args: argparse.Namespace) -> dict:
    timing: dict[str, float] = {}
    began = time.perf_counter()

    t = time.perf_counter()
    from aizynthfinder.aizynthfinder import AiZynthFinder

    timing["import_s"] = round(time.perf_counter() - t, 2)

    t = time.perf_counter()
    if args.config.lower().endswith(".json"):
        # a configuration passed as a dict, read here as UTF-8: the library reads a YAML file with the Windows locale codec, so a non-ASCII path in a .yml is mis-decoded
        with open(args.config, encoding="utf-8") as handle:
            finder = AiZynthFinder(configdict=json.load(handle))
    else:
        finder = AiZynthFinder(configfile=args.config)
    timing["configuration_s"] = round(time.perf_counter() - t, 2)

    t = time.perf_counter()
    finder.stock.select(args.stock)
    finder.expansion_policy.select(args.expansion)
    if args.filter != "none":
        finder.filter_policy.select(args.filter)
    timing["select_models_and_stock_s"] = round(time.perf_counter() - t, 2)

    finder.config.search.iteration_limit = args.iteration_limit
    finder.config.search.time_limit = args.time_limit
    finder.config.search.max_transforms = args.max_transforms
    limits = {"iteration_limit": args.iteration_limit, "time_limit": args.time_limit, "max_transforms": args.max_transforms, "return_first": finder.config.search.return_first}

    finder.target_smiles = args.target
    t = time.perf_counter()
    finder.prepare_tree()
    timing["prepare_tree_s"] = round(time.perf_counter() - t, 2)
    t = time.perf_counter()
    finder.tree_search()
    timing["search_s"] = round(time.perf_counter() - t, 2)
    t = time.perf_counter()
    finder.build_routes()
    timing["build_routes_s"] = round(time.perf_counter() - t, 2)
    statistics = finder.extract_statistics()
    routes = finder.routes
    scored = routes.dict_with_scores() if routes is not None and len(routes) else []
    timing["total_s"] = round(time.perf_counter() - began, 2)
    return {
        "schema": SCHEMA,
        "status": "completed",
        "target": args.target,
        "limits": limits,
        "identity": _identity(args.config, {"stock": args.stock, "expansion": args.expansion, "filter": args.filter}),
        "timing": timing,
        "peak_working_set_mb": _peak_mb(),
        "statistics": statistics,
        "route_count": len(scored),
        "routes": scored,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--config", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--iteration-limit", type=int, default=100)
    parser.add_argument("--time-limit", type=int, default=600, help="seconds; a safety net, the budget is the iteration limit")
    parser.add_argument("--max-transforms", type=int, default=6)
    parser.add_argument("--stock", default="zinc")
    parser.add_argument("--expansion", default="uspto")
    parser.add_argument("--filter", default="uspto", help="a filter policy key, or 'none'")
    args = parser.parse_args()

    # Stage 1's contract: the library may print or log anywhere, so stdout is taken away from it until the one document is written.
    real_stdout, sys.stdout = sys.stdout, sys.stderr
    logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
    logging.getLogger("aizynthfinder").setLevel(logging.WARNING)
    warnings.simplefilter("ignore")
    try:
        document = run(args)
        code = 0
    except Exception as error:  # noqa: BLE001 - every failure is reported as the one document
        document = {"schema": SCHEMA, "status": "failed", "target": args.target, "reason": f"{type(error).__name__}: {error}"[:400], "traceback": traceback.format_exc()[-1500:]}
        code = 1
    finally:
        sys.stdout = real_stdout
    json.dump(document, sys.stdout)
    sys.stdout.write("\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
