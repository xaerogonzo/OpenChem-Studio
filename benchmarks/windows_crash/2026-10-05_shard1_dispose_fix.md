## Windows crash rate

| arm | legs | crashed | failed | passed | crash rate | 95% interval (Wilson) | missing |
|---|---|---|---|---|---|---|---|
| as-is | 10 | 4 | 0 | 6 | 40% | 17% to 69% | 0 |
| reverted | 10 | 6 | 4 | 0 | 60% | 31% to 83% | 0 |

**as-is vs reverted: Fisher's exact p = 0.656** (4/10 against 6/10 crashed).

Two-sided, one pre-chosen sample size. Do not extend the run until this crosses 0.05; a non-significant result at this n means the difference is not large enough to see, not that there is none.

### Where the crashes were

- as-is #10: shard 1 crashed at 5%; Windows fatal exception: access violation; top frames: no frame outside pytest
- as-is #2: shard 1 crashed at 5%; Windows fatal exception: access violation; top frames: no frame outside pytest
- as-is #5: shard 1 crashed at 5%; Windows fatal exception: access violation; top frames: no frame outside pytest
- as-is #6: shard 1 crashed at 8%; Windows fatal exception: access violation; top frames: no frame outside pytest
- reverted #1: shard 1 crashed at 8%; Windows fatal exception: access violation; top frames: no frame outside pytest
- reverted #10: shard 1 crashed at 4%; Windows fatal exception: access violation; top frames: tests\conftest.py:206 dispose <- tests\test_batch_detail_dialog.py:265 widgets
- reverted #4: shard 1 crashed at 5%; Windows fatal exception: access violation; top frames: no frame outside pytest
- reverted #7: shard 1 crashed at 5%; Windows fatal exception: access violation; top frames: no frame outside pytest
- reverted #8: shard 1 crashed at 5%; Windows fatal exception: access violation; top frames: tests\test_calculator_inspector_structure.py:131 test_3d_labels_go_on_heavy_atoms_only_and_every_value_reaches_hover
- reverted #9: shard 1 crashed at 8%; Windows fatal exception: access violation; top frames: no frame outside pytest

