# Cutting a release

A release is made by `.github/workflows/release.yml` on a clean Windows machine, from a
tag. It builds the zip and the installer, tests them by running them, and creates a
**draft** GitHub Release. Nothing is published until a person presses Publish.
What a release holds is in [RELEASE_CONTENTS.md](RELEASE_CONTENTS.md); how the build
checks itself is in [ARCHITECTURE.md](ARCHITECTURE.md) ("Packaging").

## Cutting one

1. **Bump the version and the changelog in one PR.** Change `version` in `pyproject.toml`,
   and move the entries under `## [Unreleased]` you are shipping to a new
   `## [<version>] — <date>` heading in `CHANGELOG.md`. Those entries become the release
   notes. `tests/test_release_workflow.py` fails if the version has no changelog section.
2. **Merge it**, and let master's checks finish green.
3. **Tag that commit** `v<version>` (exactly: `v0.11.0`, no suffix) and push the tag. From
   GitHub: Releases, Draft a new release, choose a new tag on `master`, then save it as a
   draft; or from a terminal, `git tag v0.11.0 <commit>` and `git push origin v0.11.0`.
   The workflow refuses a tag that does not match `pyproject.toml`, and a version with no
   changelog section, in the first seconds, before the long build.
4. **Wait** (about 30 minutes). The workflow builds with `build.ps1 -Release -Installer`,
   which refuses a dirty tree and smoke-tests the built app, the zip's extracted copy and
   the installed app; checks the checksums; attests where the files came from; and drafts
   the release with the zip, the installer and `SHA256SUMS.txt`.
5. **Try the draft.** Download the installer from the draft release (not from your own
   build) and go through the checklist below.
6. **Publish** the draft. That is the only step that makes it public.

## Before pressing Publish

The pipeline runs the app; it does not draw a molecule. By hand, from the downloaded
installer:

- install **per-user**, then again **for all users** (this one asks Windows for
  permission and is not automated);
- the 2D editor draws, both 3D viewers render, and a molecule gets a name;
- Help opens and F1 works on a panel;
- uninstall, ticking neither box, then reinstall: settings and tools are still there;
  uninstall again ticking both: they are gone, and your saved project files are not.

## A dry run, without a tag

Run the **release** workflow from the Actions tab (workflow_dispatch). It does the same
build and keeps the files as a downloadable artifact for 30 days; it attests nothing and
creates no release. A pull request that changes how a release is made (the workflow,
`packaging/`, `build.ps1`, `pyproject.toml`, `uv.lock`, the release tools) runs this
automatically, so a change that breaks the freeze is found in the PR.

## Checking a download

```bash
sha256sum -c SHA256SUMS.txt            # the file is the one that was built
gh attestation verify <file> --repo xaerogonzo/OpenChem-Studio
```

The checksum detects a damaged download. The attestation proves the file was produced by
this workflow from this repository, and not built or altered anywhere else. **Neither is a
code signature**: Windows SmartScreen still says "unknown publisher" the first time, and
the README tells users to choose More info, then Run anyway.

## When it fails

- The failing step names the problem. The tag and changelog checks fail first and say
  what to change.
- A failed smoke test uploads its report and the application's own log as the
  `release-evidence` artifact on the run (kept 14 days).
- Nothing partial is left: no draft is created unless the build passed. If a draft
  exists from a run you want to redo, delete the draft release and the tag, fix, and
  tag again.

## Maintaining the workflow

Every third-party action is pinned to a full commit SHA with its version in a comment,
because the workflow can create a release; Inno Setup is pinned by version and sha256.
To update a pin, resolve the new tag to its commit
(`gh api repos/<owner>/<repo>/commits/<tag> --jq .sha`), change both, and let the dry run
prove it. `tests/test_release_workflow.py` fails an unpinned action, a `${{ }}` spliced into
a shell script, a write permission outside the draft job, or anything that would publish.

## Not done yet: code signing

The files are not signed. SignPath Foundation signs open-source projects for free, from
an automated build like this one, with a manual approval for each release; it also wants
a "Code signing policy" page crediting SignPath and listing who approves, multi-factor
authentication for the team, and a disclosure of any data the program sends elsewhere
(the AI assistant and database plugins do). Applying is the next step; the workflow would
then hand the built files to SignPath before attesting them.
