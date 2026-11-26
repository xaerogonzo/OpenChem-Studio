### GitHub MERGED is not on master

- Agents opening or merging stacked follow-up PRs now have a gotcha and a working-agreement: GitHub **MERGED** means merged into the PR's **base**. After the parent squash-merges, retarget the child to `master` before Merge. Measured on #652 and #656, which showed MERGED while `origin/master` still lacked the work.
