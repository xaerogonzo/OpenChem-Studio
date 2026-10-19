"""Many AiZynthFinder searches in ONE warm process, run by the PLANNER's own Python (never OpenChem's), for the synthesis benchmark (`PREREGISTRATION.md`).

    <planner python> plan_batch.py --config config.json --stock n1 --targets targets.json --out run1.jsonl --run-label r1

`targets.json` is a list of `{"id": <int>, "smiles": "..."}`. **One JSON object per line is appended to `--out` and flushed as each target finishes**, so a killed run keeps what it did, and a restart skips every `(id, run label)` already there. A target that fails (an unparseable SMILES, a crash in the search) is a line with `"status": "failed"` and its reason, and the batch goes on: a failure is a missing result, never a silent skip.
Limits are set explicitly from the arguments and echoed in every line; nothing retries or changes a limit. The planner's identity rides in every line. Logs go to stderr.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import traceback
import warnings

from spike_plan import _identity, _peak_mb  # the identity and memory helpers of the spike runner (same directory)

SCHEMA = "batch-1"


def _done(path: str) -> set[tuple[int, str]]:
    if not os.path.exists(path):
        return set()
    done = set()
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                record = json.loads(line)
                done.add((record["id"], record["run_label"]))
    return done


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--config", required=True)
    parser.add_argument("--targets", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--run-label", required=True)
    parser.add_argument("--iteration-limit", type=int, default=500)
    parser.add_argument("--time-limit", type=int, default=1800, help="seconds; a safety net, the budget is the iteration limit")
    parser.add_argument("--max-transforms", type=int, default=10)
    parser.add_argument("--stock", required=True)
    parser.add_argument("--expansion", default="uspto")
    parser.add_argument("--filter", default="none", help="a filter policy key, or 'none'")
    args = parser.parse_args()

    warnings.simplefilter("ignore")
    logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
    logging.getLogger("aizynthfinder").setLevel(logging.WARNING)
    real_stdout, sys.stdout = sys.stdout, sys.stderr  # the library may print; the batch speaks only through the output file

    with open(args.targets, encoding="utf-8") as handle:
        targets = json.load(handle)
    done = _done(args.out)
    todo = [t for t in targets if (t["id"], args.run_label) not in done]
    print(f"{len(done)} done, {len(todo)} to run", file=sys.stderr, flush=True)
    if not todo:
        real_stdout.write(json.dumps({"schema": SCHEMA, "status": "completed", "ran": 0}) + "\n")
        return 0

    began = time.perf_counter()
    from aizynthfinder.aizynthfinder import AiZynthFinder

    if args.config.lower().endswith(".json"):
        with open(args.config, encoding="utf-8") as handle:
            finder = AiZynthFinder(configdict=json.load(handle))
    else:
        finder = AiZynthFinder(configfile=args.config)
    finder.stock.select(args.stock)
    finder.expansion_policy.select(args.expansion)
    if args.filter != "none":
        finder.filter_policy.select(args.filter)
    finder.config.search.iteration_limit = args.iteration_limit
    finder.config.search.time_limit = args.time_limit
    finder.config.search.max_transforms = args.max_transforms
    limits = {"iteration_limit": args.iteration_limit, "time_limit": args.time_limit, "max_transforms": args.max_transforms}
    identity = _identity(args.config, {"stock": args.stock, "expansion": args.expansion, "filter": args.filter})
    startup = round(time.perf_counter() - began, 2)

    ran = failed = 0
    with open(args.out, "a", encoding="utf-8", newline="\n") as out:
        for target in todo:
            record = {"schema": SCHEMA, "id": target["id"], "run_label": args.run_label, "target": target["smiles"], "limits": limits, "identity": identity, "startup_s": startup}
            started = time.perf_counter()
            try:
                finder.target_smiles = target["smiles"]
                finder.prepare_tree()
                finder.tree_search()
                finder.build_routes()
                routes = finder.routes
                record.update(status="completed", statistics=finder.extract_statistics(), routes=routes.dict_with_scores() if routes is not None and len(routes) else [])
                record["route_count"] = len(record["routes"])
            except Exception as error:  # noqa: BLE001 - a failed target is a recorded line, and the batch goes on
                record.update(status="failed", reason=f"{type(error).__name__}: {error}"[:400], traceback=traceback.format_exc()[-1200:])
                failed += 1
            record["seconds"] = round(time.perf_counter() - started, 2)
            record["peak_working_set_mb"] = _peak_mb()
            out.write(json.dumps(record) + "\n")
            out.flush()
            ran += 1
            print(f"{target['id']} {record['status']} {record['seconds']} s", file=sys.stderr, flush=True)
    real_stdout.write(json.dumps({"schema": SCHEMA, "status": "completed", "ran": ran, "failed": failed}) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
