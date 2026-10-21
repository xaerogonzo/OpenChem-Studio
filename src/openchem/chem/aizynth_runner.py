"""One AiZynthFinder search, run by the USER'S planner Python and not by OpenChem's (`docs/SYNTHESIS_HELPER_DESIGN.md`, Stage 1 slice 3). Imports nothing from `openchem`: the planner lives in its own environment (Python 3.10 to 3.12, `numpy<2`, onnxruntime), which OpenChem's interpreter is never made to share.

THE CONTRACT (`chem/aizynth_planner.py` is the other half):

* ONE request document on stdin (UTF-8 JSON, schema `aizynth-request-1`): the target, the planner's configuration AS A DICTIONARY (read here as UTF-8, because the library reads a YAML file with the Windows locale codec and mis-decodes a non-ASCII path), which stock, expansion policy and filter policy to select, and the limits. No command-line argument carries data.
* ONE response document on stdout (schema `aizynth-run-1`) and NOTHING ELSE. The library may print or log anywhere, so stdout is taken away from it until the document is written; logs go to stderr.
* THE STATUS IS IN THE DOCUMENT: `completed`, `unavailable` (a named asset is not there: `kind` is `config`, `model`, `templates`, `filter` or `stock`) or `failed` (`kind` `invalid_target`, `bad_request` or `error`). The exit code is 0 for `completed` and 1 otherwise, and the parent trusts the document and checks the two agree.
* THE ASSETS ARE CHECKED HERE BEFORE THE LIBRARY IS LOADED, because the library's own messages for a missing one are poor (a policy with no template file raises `ValueError: not enough values to unpack`; an unparseable target raises `AttributeError: 'NoneType'`). A missing file is `unavailable` with the file named, a target that does not parse is `invalid_target`.
* A SECOND REQUEST, `aizynth-inspect-request-1`, READS THE PLANNER'S OWN CONFIGURATION FILE and answers `aizynth-inspect-1` without importing the library (0.2 s measured): the parsed configuration with every relative path made absolute against the file's folder, the names it offers (expansion policies, filters, stocks) and the versions installed. It exists because OpenChem has no YAML reader and the planner's environment always has one (`pyyaml` is a dependency of `aizynthfinder`), and because the file is read here as UTF-8, where the library reads it with the Windows locale codec.
* NOTHING RETRIES and no limit is changed: the limits asked for are the limits run and are echoed back. The planner has no seed, so two runs of one request can differ in their tree; the identity of what ran is in the response.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
import time
import traceback
import warnings

#: What the reachability guard accepts for a module nothing imports: the host (`chem/aizynth_planner.py`) hands this FILE to the planner's interpreter as a path, as `pka_providers` does for `pka_runner`.
REACHED_BY = (
    "script_path: handed as a path to the user's planner interpreter by chem/aizynth_planner.py, which must not import it because that environment has aizynthfinder and OpenChem's does not"
)

#: The request this script reads. Kept equal to `chem/aizynth_planner.py`'s by a test; the two files cannot share a constant because this one cannot import openchem.
REQUEST_SCHEMA = "aizynth-request-1"
#: The response this script writes.
RUN_SCHEMA = "aizynth-run-1"
#: The request that asks for the configuration to be read.
INSPECT_REQUEST_SCHEMA = "aizynth-inspect-request-1"
#: The response to it.
INSPECT_SCHEMA = "aizynth-inspect-1"

#: The packages whose versions identify a run.
_IDENTITY_PACKAGES = ("aizynthfinder", "onnxruntime", "numpy", "rdkit", "pyarrow")


def _identity(config: dict, selection: dict) -> dict:
    """What ran: the package versions, the Python, a hash of the configuration (sorted, so it does not depend on key order) and what was selected."""
    from importlib.metadata import version

    packages = {}
    for name in _IDENTITY_PACKAGES:
        try:
            packages[name] = version(name)
        except Exception:  # noqa: BLE001 - a missing package is data, not an error here
            packages[name] = None
    digest = hashlib.sha256(json.dumps(config, sort_keys=True, ensure_ascii=True).encode("utf-8")).hexdigest()
    return {"planner": "aizynthfinder", "packages": packages, "python": sys.version.split()[0], "config_sha256": digest, "selection": selection}


def _installed(name: str) -> str | None:
    from importlib.metadata import version

    try:
        return version(name)
    except Exception:  # noqa: BLE001 - a missing package is data
        return None


def _absolute(value: object, folder: str) -> object:
    """A path made absolute against the configuration file's folder; anything that is not a path string is left alone."""
    if isinstance(value, str) and value and not os.path.isabs(value):
        return os.path.normpath(os.path.join(folder, value))
    return value


def _resolved(config: dict, folder: str) -> dict:
    """The configuration with the paths of the three sections the planner needs made absolute: the policy files, the filter model and the stock."""
    out = dict(config)
    for section in ("expansion", "filter", "stock"):
        entries = config.get(section)
        if not isinstance(entries, dict):
            continue
        out[section] = {key: ([_absolute(item, folder) for item in value] if isinstance(value, list) else _absolute(value, folder)) for key, value in entries.items()}
    return out


def inspect(request: dict) -> dict:
    """Read the configuration file and say what is installed, without loading the planner."""
    path = request.get("config_path")
    if not isinstance(path, str) or not path:
        return {"schema": INSPECT_SCHEMA, "status": "failed", "kind": "bad_request", "reason": "the request has no 'config_path'"}
    packages = {name: _installed(name) for name in (*_IDENTITY_PACKAGES, "pyyaml")}
    answer = {"schema": INSPECT_SCHEMA, "packages": packages, "python": sys.version.split()[0]}
    if packages["aizynthfinder"] is None:
        return {**answer, "status": "unavailable", "kind": "planner", "reason": "aizynthfinder is not installed in this Python environment"}
    if not os.path.isfile(path):
        return {**answer, "status": "unavailable", "kind": "config", "reason": f"the configuration file is not there: {path}"}
    try:
        import yaml
    except ImportError:
        return {**answer, "status": "failed", "kind": "yaml", "reason": "this environment has no YAML reader (pyyaml), which aizynthfinder needs"}
    try:
        with open(path, encoding="utf-8") as handle:
            config = yaml.safe_load(handle)
    except Exception as error:  # noqa: BLE001 - an unreadable file is a typed answer
        return {**answer, "status": "failed", "kind": "config", "reason": f"the configuration file could not be read ({type(error).__name__}: {str(error)[:200]})"}
    if not isinstance(config, dict):
        return {**answer, "status": "failed", "kind": "config", "reason": "the configuration file is not a mapping of settings"}
    resolved = _resolved(config, os.path.dirname(os.path.abspath(path)))
    keys = {section: sorted(resolved[section]) if isinstance(resolved.get(section), dict) else [] for section in ("expansion", "filter", "stock")}
    return {**answer, "status": "ok", "config": resolved, "keys": keys}


def _peak_mb() -> float | None:
    try:
        import psutil

        info = psutil.Process(os.getpid()).memory_info()
        return round(getattr(info, "peak_wset", info.rss) / 1e6, 1)
    except Exception:  # noqa: BLE001
        return None


def _missing_asset(config: dict, request: dict) -> tuple[str, str] | None:
    """The first named file that is not there, as `(kind, reason)`, or a configuration that does not hold the key asked for."""
    expansion = (config.get("expansion") or {}).get(request["expansion"])
    if not isinstance(expansion, (list, tuple)) or len(expansion) < 2:
        return "config", f"the configuration has no expansion policy {request['expansion']!r} with a model and a template file"
    model, templates = expansion[0], expansion[1]
    if not os.path.isfile(model):
        return "model", f"the expansion policy model file is not there: {model}"
    if not os.path.isfile(templates):
        return "templates", f"the expansion policy template file is not there: {templates}"
    if request.get("filter"):
        filter_entry = (config.get("filter") or {}).get(request["filter"])
        filter_model = filter_entry[0] if isinstance(filter_entry, (list, tuple)) and filter_entry else filter_entry
        if not isinstance(filter_model, str):
            return "config", f"the configuration has no filter policy {request['filter']!r}"
        if not os.path.isfile(filter_model):
            return "filter", f"the filter policy model file is not there: {filter_model}"
    stock = (config.get("stock") or {}).get(request["stock"])
    if not isinstance(stock, str):
        return "config", f"the configuration has no stock {request['stock']!r} that is a file"
    if not os.path.isfile(stock):
        return "stock", f"the stock file is not there: {stock}"
    return None


def _bad_request(request: object) -> str | None:
    """Why a request cannot be run, or None."""
    if not isinstance(request, dict) or request.get("schema") != REQUEST_SCHEMA:
        return f"the request is not a {REQUEST_SCHEMA} document"
    for key, kind in (("target_smiles", str), ("stock", str), ("expansion", str), ("config", dict)):
        if not isinstance(request.get(key), kind) or not request[key]:
            return f"the request has no usable {key!r}"
    if request.get("filter") is not None and not isinstance(request["filter"], str):
        return "the request's 'filter' must be a name or null"
    for key in ("iteration_limit", "max_transforms"):
        value = request.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            return f"the request's {key!r} must be a positive integer"
    limit = request.get("time_limit")
    if isinstance(limit, bool) or not isinstance(limit, (int, float)) or not limit > 0:
        return "the request's 'time_limit' must be a positive number of seconds"
    if not isinstance(request.get("all_routes", False), bool):
        return "the request's 'all_routes' must be true or false"
    return None


def _target_readable(smiles: str) -> bool:
    from rdkit import Chem, rdBase

    with rdBase.BlockLogs():
        return Chem.MolFromSmiles(smiles) is not None


def run(request: dict) -> dict:
    """The response document for one request. Raises only for a genuine fault, which `main` reports as `failed`."""
    problem = _bad_request(request)
    if problem:
        return {"schema": RUN_SCHEMA, "status": "failed", "kind": "bad_request", "reason": problem}
    config = request["config"]
    missing = _missing_asset(config, request)
    if missing:
        return {"schema": RUN_SCHEMA, "status": "unavailable", "kind": missing[0], "reason": missing[1]}
    if not _target_readable(request["target_smiles"]):
        return {"schema": RUN_SCHEMA, "status": "failed", "kind": "invalid_target", "reason": "the target structure could not be read"}

    timing: dict[str, float] = {}
    began = time.perf_counter()
    stage = time.perf_counter()
    from aizynthfinder.aizynthfinder import AiZynthFinder

    timing["import_s"] = round(time.perf_counter() - stage, 2)
    stage = time.perf_counter()
    finder = AiZynthFinder(configdict=json.loads(json.dumps(config)))  # a copy: the library consumes the dictionary it is given
    finder.stock.select(request["stock"])
    finder.expansion_policy.select(request["expansion"])
    if request.get("filter"):
        finder.filter_policy.select(request["filter"])
    timing["load_s"] = round(time.perf_counter() - stage, 2)

    finder.config.search.iteration_limit = request["iteration_limit"]
    finder.config.search.time_limit = request["time_limit"]
    finder.config.search.max_transforms = request["max_transforms"]
    all_routes = bool(request.get("all_routes", False))
    if all_routes:
        finder.config.post_processing.all_routes = True
    limits = {"iteration_limit": request["iteration_limit"], "time_limit": request["time_limit"], "max_transforms": request["max_transforms"], "all_routes": all_routes}

    finder.target_smiles = request["target_smiles"]
    stage = time.perf_counter()
    finder.prepare_tree()
    finder.tree_search()
    timing["search_s"] = round(time.perf_counter() - stage, 2)
    stage = time.perf_counter()
    finder.build_routes()
    timing["build_routes_s"] = round(time.perf_counter() - stage, 2)
    routes = finder.routes
    scored = routes.dict_with_scores() if routes is not None and len(routes) else []
    timing["total_s"] = round(time.perf_counter() - began, 2)
    return {
        "schema": RUN_SCHEMA,
        "status": "completed",
        "target": request["target_smiles"],
        "limits": limits,
        "identity": _identity(config, {"stock": request["stock"], "expansion": request["expansion"], "filter": request.get("filter") or "none"}),
        "timing": timing,
        "peak_working_set_mb": _peak_mb(),
        "statistics": finder.extract_statistics(),
        "routes": scored,
    }


def main() -> int:
    # The library may print or log anywhere, so stdout is taken away from it until the one document is written.
    real_stdout, sys.stdout = sys.stdout, sys.stderr
    logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
    logging.getLogger("aizynthfinder").setLevel(logging.WARNING)
    warnings.simplefilter("ignore")
    try:
        try:
            request = json.loads(sys.stdin.buffer.read().decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as error:
            document = {"schema": RUN_SCHEMA, "status": "failed", "kind": "bad_request", "reason": f"the request is not readable JSON ({type(error).__name__})"}
        else:
            document = inspect(request) if isinstance(request, dict) and request.get("schema") == INSPECT_REQUEST_SCHEMA else run(request)
    except Exception as error:  # noqa: BLE001 - every failure is reported as the one document
        document = {"schema": RUN_SCHEMA, "status": "failed", "kind": "error", "reason": f"{type(error).__name__}: {error}"[:400], "traceback": traceback.format_exc()[-1500:]}
    finally:
        sys.stdout = real_stdout
    sys.stdout.write(json.dumps(document, ensure_ascii=True))
    sys.stdout.write("\n")
    sys.stdout.flush()
    return 0 if document.get("status") in ("completed", "ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
