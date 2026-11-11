### CI: eight Windows suite shards after shard 1/7 timed out
- Repinned `tools/suite-shard-pins.json` with `--repin --splits=8` after PR #576's shard 1 hit the 30-minute step limit with no failing test; matrix and shard guards now expect `1/8`…`8/8`.
