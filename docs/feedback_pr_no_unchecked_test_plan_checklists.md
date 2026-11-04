# PR bodies: no unchecked test-plan checkboxes

Alex (2026-11-04): Cursor agents often open PRs with a **Test plan** full of `- [ ]` items (CI shards, merge fork, and so on). Those read like a todo list for him unless the agent checks them off as work completes. He does not want that system.

**Why:** GitHub renders unchecked boxes as work left for the reader. The agent usually cannot tick CI or merge steps inside the PR description as they happen, so the boxes stay empty and imply Alex owns the list.

**How to apply (agents opening PRs on this repo):**

1. **Do not** add a `## Test plan` section with markdown checkboxes for CI, merging, or fork ports unless the agent will update the PR body and mark each box `[x]` in the same session before handoff.
2. **Do** record verification as plain prose under **Verified** (or **Measured** on naming rounds): what command ran, on which tree, and the outcome (`42 passed`, `gh pr checks 545` all green, and so on). No checkbox syntax.
3. **Do** put merge order and fork links under **Cross-links** or **After merge** as sentences, not todos (`Merge app #N when green, then fork #M` is fine; `- [ ] Merge fork` is not).
4. Naming rounds follow `docs/NAMING_ROUNDS.md` step 6: scanned / Fixed / Decisions / Not changed / Measured — still no checklists.

This extends [feedback-pr-bodies-state-decisions-not-questions](WORKING_AGREEMENTS.md#feedback-pr-bodies-state-decisions-not-questions): the PR is a record of decisions and measurements, not a shared task board.
