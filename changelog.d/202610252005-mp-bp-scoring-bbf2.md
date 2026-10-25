### Research: the scorer for the melting- and boiling-point benchmark

- `benchmarks/mp_bp/mpbp_score.py` and `mpbp_models.py` score Joback, Marrero-Gani and a project-owned refit of Joback's groups against the handbook corpus, with the preregistered gate (error ceilings, improvement over a development-only family baseline, coverage, at least 300 paired entities, 10,000-resample bootstrap) and a PASS / FAIL / NOT EVALUABLE verdict.
- The holdout is scored once, in code: it refuses without an explicit flag, if any file that decides a score changed since the freeze, or a second time. Nothing user-facing changes.
