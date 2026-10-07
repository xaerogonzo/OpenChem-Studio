"""A stand-in for Knowledge Vista's `kv` command, so OpenChem's tests never need the real program.

It answers `--json capabilities` and nothing else, steered by environment variables so one script plays every way a configured
program can disappoint:

    FAKE_KV_MODE      ok | other_app | malformed | notenvelope | crash | hang | nocapabilities
    FAKE_KV_PROTOCOL  the protocol_version `capabilities` reports  (default 1)
    FAKE_KV_LOG       a file every invocation's argv is appended to

Run as a script: `python fake_kv.py --json capabilities`.
"""

from __future__ import annotations

import json
import os
import sys
import time


def envelope(records=None, errors=None):
    return {"schema_version": 1, "command": "capabilities", "ok": not errors, "complete": True, "records": records or [], "warnings": [], "errors": errors or [], "next_cursor": None}


def main(argv):
    if os.environ.get("FAKE_KV_LOG"):
        with open(os.environ["FAKE_KV_LOG"], "a", encoding="utf-8") as log:
            log.write(json.dumps(argv) + "\n")
    mode = os.environ.get("FAKE_KV_MODE", "ok")
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
    if mode == "nocapabilities":
        print(json.dumps(envelope(errors=[{"code": "KV_INTERNAL", "message": "x", "details": {}}])))
        return 1
    record = {"type": "capabilities", "app": "SomethingElse" if mode == "other_app" else "KnowledgeVista", "app_version": "0.0.1",
              "protocol_version": int(os.environ.get("FAKE_KV_PROTOCOL", "1")),
              "commands": [{"name": "locate", "kind": "read", "read_only": True}, {"name": "scan", "kind": "catalog", "read_only": False},
                           {"name": "stats", "kind": "read", "read_only": True}]}
    print(json.dumps(envelope([record])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
