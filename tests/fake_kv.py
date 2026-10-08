"""A stand-in for Knowledge Vista's `kv` command, so OpenChem's tests never need the real program or a real library.

It speaks only the slice of the integration contract (Knowledge Vista docs/INTEGRATION.md) that OpenChem calls -- `--json capabilities` and
`--json locate <sha256>` -- and is steered by environment variables, one failure mode each:

    FAKE_KV_PROTOCOL   the protocol_version `capabilities` reports            (default 1)
    FAKE_KV_MODE       the older name for FAKE_KV_LOCATE; also `ok` (= found) and `other_app` (capabilities names another program)
    FAKE_KV_LOCATE     found | missing | root_offline | unknown | ambiguous | malformed | notenvelope | wrongbytes | hang | crash | nocapabilities
    FAKE_KV_PATH       the absolute path `found` names (several, separated by `|`)
    FAKE_KV_DOC        the document id `found` reports
    FAKE_KV_LOG        a file every invocation's argv is appended to, so a test can say exactly what was asked

Run as a script: `python fake_kv.py --json locate <sha256>`.
"""

from __future__ import annotations

import json
import os
import sys
import time


def envelope(command, records=None, errors=None):
    return {"schema_version": 1, "command": command, "ok": not errors, "complete": True, "records": records or [], "warnings": [], "errors": errors or [], "next_cursor": None}


def main(argv):
    if os.environ.get("FAKE_KV_LOG"):
        with open(os.environ["FAKE_KV_LOG"], "a", encoding="utf-8") as log:
            log.write(json.dumps(argv) + "\n")
    # FAKE_KV_MODE is the older name (the External Tools tab tests); FAKE_KV_LOCATE the newer. `ok` means the same as `found`.
    mode = os.environ.get("FAKE_KV_MODE") or os.environ.get("FAKE_KV_LOCATE", "found")
    mode = "found" if mode == "ok" else mode
    if "capabilities" in argv and os.environ.get("FAKE_KV_MODE") in ("hang", "crash", "malformed", "notenvelope"):
        # The External Tools tab asks only `capabilities`, so for it FAKE_KV_MODE breaks THAT call. The locate tests set FAKE_KV_LOCATE instead and
        # need `capabilities` to keep answering while `locate` fails.
        if mode == "hang":
            time.sleep(60)
        if mode == "crash":
            print("Traceback (most recent call last): boom", file=sys.stderr)
            return 3
        print("this is not json" if mode == "malformed" else "[]")
        return 0
    if "capabilities" in argv:
        if mode == "nocapabilities":
            print(json.dumps(envelope("capabilities", errors=[{"code": "KV_INTERNAL", "message": "x", "details": {}}])))
            return 1
        record = {"type": "capabilities", "app": "SomethingElse" if mode == "other_app" else "KnowledgeVista", "app_version": "0.0.1",
                  "protocol_version": int(os.environ.get("FAKE_KV_PROTOCOL", "1")),
                  "commands": [{"name": "locate", "kind": "read", "read_only": True}, {"name": "scan", "kind": "catalog", "read_only": False},
                               {"name": "stats", "kind": "read", "read_only": True}]}
        print(json.dumps(envelope("capabilities", [record])))
        return 0
    sha = argv[argv.index("locate") + 1]
    if mode == "hang":
        time.sleep(60)
    if mode == "crash":
        print("Traceback (most recent call last): boom", file=sys.stderr)
        return 3
    if mode == "malformed":
        print("this is not json")
        return 0
    if mode == "notenvelope":
        print("[]")
        return 0
    if mode == "unknown":
        print(json.dumps(envelope("locate", errors=[{"code": "KV_NOT_FOUND", "message": "nothing", "details": {}}])))
        return 1
    if mode == "ambiguous":
        print(json.dumps(envelope("locate", errors=[{"code": "KV_AMBIGUOUS", "message": "several", "details": {"candidates": []}}])))
        return 1
    paths = [p for p in os.environ.get("FAKE_KV_PATH", "").split("|") if p]
    status = {"found": "available", "missing": "missing", "root_offline": "root_offline"}[mode if mode in ("found", "missing", "root_offline") else "found"]
    locations = [{"absolute_path": p, "relative_path": os.path.basename(p), "root": "lib", "root_id": "r", "root_status": "unavailable" if mode == "root_offline" else "online",
                  "root_path": os.path.dirname(p), "state": "active", "on_disk": None if mode == "root_offline" else mode != "missing"} for p in paths]
    record = {"type": "location", "artifact_id": "0" * 64 if mode == "wrongbytes" else sha, "document_id": os.environ.get("FAKE_KV_DOC", "d" * 32), "status": status,
              "uri": f"knowledgevista://document/{os.environ.get('FAKE_KV_DOC', 'd' * 32)}", "locations": locations}
    print(json.dumps(envelope("locate", [record])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
