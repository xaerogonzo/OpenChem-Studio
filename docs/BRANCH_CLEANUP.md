# Branch cleanup, 2026-09-12

Every feature branch in this repository was deleted on 2026-09-12, leaving
`master` alone on the remote and locally. **72 branches**, all of them
already merged.

This file exists so that is reversible. A deleted branch is a deleted *ref* --
the commits are still in `master`'s history, so nothing was lost -- but the
names are how anybody finds a piece of work again, and a list of names with
nowhere to point is not a recovery.

## What was checked before deleting

Each branch's **remote tip** was verified to be an ancestor of `master`
immediately before its deletion -- not the local ref, which can lag behind a
remote that moved on. 72 verified, **0 skipped**: not one carried a commit
that is not in `master`.

`git branch -d` (not `-D`) was used for the local deletions, so git would have
refused anything unmerged as a second check. It refused none.

## Restoring one

```bash
git push origin <sha>:refs/heads/<name>
```

GitHub also keeps recently deleted branches restorable from its own UI for a
while, so this list is the third line of defence rather than the only one.

## The branches

| SHA | branch |
| --- | --- |
| `6521d45533e4e08e2db39d9956f3c2460a0bf2a7` | `alignment-geometry-and-batch-on-properties` |
| `a7f2fdf363cfe77adbe899f02da3a6a77f7d45e8` | `bonded-metallocenes` |
| `382f73fee5219277456d6ce764586e4014618bb5` | `ci-deselect-network-test` |
| `2b308aebadff3a452be3f214fb4b94d15d44a334` | `cif-ion-charges` |
| `cfb630b089c43eede9a6b82fa76874f1b390e83d` | `cip-labels-follow-the-structure` |
| `0e5e34cde8ce191ea5fdd283f196035c78e830cf` | `claude/bold-goldwasser-f543f0` |
| `6c52492d686f3006148d3ed6347eb9f4139dc620` | `claude/eloquent-mayer-8a1f1a` |
| `f17484176b8efd7d53688b6e5b40e626c3aa33af` | `claude/fix-widget-disposal-order` |
| `1c97cc69dc603dff1d2674ba9a9e9958c865ff30` | `claude/musing-swirles-01fe93` |
| `af0ef79ab297cab99d550dc18a94f046de5683d1` | `claude/pensive-napier-19b09d` |
| `393abf9c45557b7ea9961f211da487ae42494256` | `claude/youthful-boyd-ebc637` |
| `315e483b0706e98c905d2526fd197aa2f5f7980b` | `close-the-open-three` |
| `34f9d5a6f2cff3a8379b75903495a53f1ce36630` | `conformer-comparison` |
| `cdfc72e435f9df1e0a700dba3e2a46ae3c36733d` | `conformer-defaults` |
| `ac43f29b337eecea1643cff22dc78d6cc257435d` | `Conformer-fix-2` |
| `90f6a6dd488d72027a78476bf776f56201e68f96` | `constant-doc-guard` |
| `a3c68b1bb781e5db1e89c85ca7b1ff3e27a7842c` | `coordination-geometry` |
| `aa7a5510f03118d859919a164ceb5d9c8932a7ae` | `crystal-project-object` |
| `3fa861eb606bb0905cc4ffd4a87dd67ad60534fe` | `crystal-rename-delete` |
| `93cf4cb9a105825ecdbcd85a36113f8367d1d818` | `crystal-site-click` |
| `90f094ef898728ec715340a90689a96df8a9b7e6` | `declared-totals` |
| `3e0ce34701bb6da6ee7b08beaa98c9cf57646345` | `deferred-list-sweep` |
| `d29a07766ce5e1bf07ca2921f320534a06eae5a4` | `dialogs-driven-and-documented` |
| `e5133b242414d767b20cb4f865329462062f38ba` | `docs-reconciliation` |
| `2f47bb80ec1495ad16aff29ba7165fb4c3a625fc` | `document-what-the-registry-reaches` |
| `8520dab91c67519df9d23e8b8ba3ccf7418fa3cb` | `drive-consolidate-and-finish-the-contracts` |
| `bad2421668d84406489302f24feef6c20279e4de` | `driven-visual-oracle` |
| `51bb180aac1b54dd345f8faf6a546a296cbec56c` | `energetic-formulations` |
| `d59be3da30a1befd0cc0f8b4d7596d7020ea0b14` | `failed-descriptor-cell-and-hover` |
| `e8dba45d9da74503d3c1ae8c740e622dc18b825e` | `Fix-A` |
| `8167920624732c1a37faeaa54375e70331ce6761` | `fix-docs-guard-venv-walk` |
| `62ce836d74cae9036ade475be388e9dcdc8db6dd` | `fix-sha-citation` |
| `d7b8fd65a11cd5a199011e73000fce0af7540167` | `free-energy-spike` |
| `66f9ef5a6e07402ebdb70492b47c89f304bef96e` | `gaff-version-and-the-windows-wall` |
| `7a9dd00445c792f7378929ef892d4346232c8a1a` | `joback-thermophysical` |
| `f46537ed08e5c0cc58b6c8dd83883e9ad2406d28` | `jobs-panel-leaks-and-polls-forever` |
| `7a7f64c3d76783a1d79d35ca8a0177837c300bf6` | `ketcher-overrule` |
| `351fac69b3d6a69c5568636bc4f67cea9c5fa97e` | `ketcher-third-party-notices` |
| `7568752c50d501e29801a9be21004544a2a9d271` | `lattice-energy-complex-ions` |
| `a4af90e7162e85bb375737f4b2b452fa427d56bf` | `linux-job-can-report` |
| `0da570c21bb408986efb577daaaa82b71e895472` | `linux-victim-does-not-wander` |
| `6ffdfc15f496504435948b03bc074217f12de17b` | `lone-pairs-on-the-canvas` |
| `fea33eaa060ae48331e4f61038cca1864cb47f26` | `make-the-new-science-reachable` |
| `6035377330975a2fe224395ff22ac56b0b8ed3a9` | `mass-spectrometry-and-a-chart-channel` |
| `5a331abd020a30d493cd7407f93e9bbe9a8f72f1` | `openbabel-data-dir-root-cause` |
| `76bfcc9606ecc5652808a150f9a0c626a885c681` | `overlay-spatial-annotations` |
| `1984913f6c8607a6f7bf37f891d594916d27de38` | `particle-editor` |
| `21c332ea220106c1344051da18b24ac739a78310` | `Phase-7+` |
| `4488e9e4587cc1ff5ae0446cdf0a28d7ee9a6e88` | `Phase-C` |
| `b16ae271fb2ccb98770890f33fb1f909f9b8b87b` | `Phase-D` |
| `602ecc2d2eef9f869c08f5a75f1855bb1f4411f8` | `Phase_3-6` |
| `ec8b4d276a8ef1e2978802ca9b955385c6aa23fb` | `plugin-reaction-templates` |
| `df1686e24643b4a492db6deb1c166a6e3cbc19a3` | `powder-xrd` |
| `e1a21d24ee6c07e1e34e6e1bc4c7be387c5a3db5` | `Refactor-1` |
| `f5f8ae55200455fe1d02969ebab79e5eeaef5a11` | `regulatory-coverage` |
| `343b1a336da8f11cdcac85c7a0ed479ff900b117` | `replicate-affinity-range` |
| `a82ee8bfc69525db50f16d1e0609a4c535f865a7` | `rescoring-axis` |
| `a61cbc92e8f8c0c0b82d87b474f3a02566bdb8a5` | `rescoring-benchmark` |
| `5e9ebe33beeb15212f62100b0efbd8035c92e853` | `results-first-foundation` |
| `84b56a27e9eeba7b729ecc18cbdd60a5b80aa244` | `Second_phase_run` |
| `1f0cd6b231a1dd9d1f1333850341791385412713` | `solubility-base-bias` |
| `c4e908087cbfe5021ae6950df2cca98fd354484e` | `solubility-predictor` |
| `f331df8f66432f9fda0f4e1991872f20354a11d0` | `sources-registry` |
| `13b0143a5e02b0d8e005ef1b4795ff56c74f3857` | `sources-verification-2` |
| `6dd0018c9c3b495d3f52cc1a7c25eca2e625547f` | `spatial-annotations` |
| `4d38238f3e3e31dbf44499c5b8156f71d097dae7` | `stage-6-quantitative-limits` |
| `7ecaabe58619e1ed0ed397b51b1b7cbabafdba57` | `static-import-reachability` |
| `8c146c0957a2945cff71eaa6e0cdab7162af4253` | `sync-the-lockfile-to-0.10.0` |
| `a025e14a5ae12cae127970f160888f651c0613f2` | `the-package-came-from-defaults` |
| `c6155fa09c0f8216bd3182b67a9fa251577faf5e` | `untrack-pyscope-index` |
| `6cafeedcd4b5262a1964434d082b4b05624d3182` | `viewer-readiness` |
| `343a1131219eb8e6165b4b0d6de62c25abff4423` | `widen-the-presentation-channel` |

Recorded against `master` at `bf86752`.
