## Summary

Introduce `docs/session-notes/` so agents and maintainers commit **PR bodies**, **commit message drafts**, and **measurement scratch scripts** instead of leaving them as untracked repo-root files. The first bundle is the naming WS3 / NL-012 session that paired app #627 with fork #101.

## Verified

`uv run --no-sync python tools/changelog.py check` — fragments ok after adding this PR's changelog file.