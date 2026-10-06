"""pytest plugin for `tools/suite_shards.py --count-qapp`: per test file, how many collected tests request the `qapp` fixture.

That is the criterion `pytest_runtest_logfinish` in `tests/conftest.py` uses to decide which tests are followed by a full `gc.collect()`
(`"qapp" in item.fixturenames`, the same expression), so counting it at collection time says how much hook a file will cost without
running it. Writes `{file: count}` to the path in `SUITE_QAPP_OUT`.
"""
import collections
import json
import os


def pytest_collection_finish(session):
    counts = collections.Counter()
    for item in session.items:
        if "qapp" in getattr(item, "fixturenames", ()):
            counts[item.nodeid.split("::")[0]] += 1
    with open(os.environ["SUITE_QAPP_OUT"], "w", encoding="utf-8") as fh:
        json.dump(counts, fh)
