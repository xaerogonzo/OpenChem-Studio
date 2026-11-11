### Drive: NMR, Results, and async Inspector dumps
- `nmr_panes` and `results` emit one compact JSON object per tag (pane sizes and hide state; focus, search, jumps, report ids). `inspect` can take `"source": "result"` after `calculator` and `jobs_wait`, so a pH-charge Inspector is built from the filed dataset instead of a second synchronous `compute`.
