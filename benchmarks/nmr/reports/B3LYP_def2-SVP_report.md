## B3LYP def2-SVP — all assigned carbons

```
strategy                n    MAE           95% CI    med   RMSE    p95   worst  sel.acc  regret  worst reg  ref
---------------------------------------------------------------------------------------------------------------
lookup_only            28   6.92 [ 4.33,  7.96]    2.40  10.34  18.73   28.98   46.4%    4.77      26.46    0
orca_only              28   3.49 [ 1.47,  4.30]    2.53   4.57   8.54   12.52   53.6%    1.33      10.48    0
hard_gate              28   5.98 [ 1.02,  7.96]    2.33   8.78  16.04   19.98   50.0%    3.82      13.51    1
warn_only              28   2.75 [ 1.02,  3.44]    1.94   3.97   8.18   12.52   82.1%    0.60      10.48    0
global_error           28   2.75 [ 1.02,  3.44]    1.94   3.97   8.18   12.52   82.1%    0.60      10.48    0
per_molecule_error     28   2.38 [ 1.02,  2.92]    1.94   3.21   6.39    8.65   85.7%    0.22       2.98    0
shrunk_error           28   2.38 [ 1.02,  2.92]    1.94   3.21   6.39    8.65   85.7%    0.22       2.98    0
flagged                28   2.38 [ 1.02,  2.92]    1.94   3.21   6.39    8.65   85.7%    0.22       2.98    0
```

### good atoms
```
strategy                n    MAE   worst  sel.acc  worst reg
lookup_only            14   0.92    3.14   78.6%       2.98
orca_only              14   2.40    8.34   21.4%       8.13
hard_gate              14   0.92    3.14   78.6%       2.98
warn_only              14   0.92    3.14   78.6%       2.98
global_error           14   0.92    3.14   78.6%       2.98
per_molecule_error     14   0.92    3.14   78.6%       2.98
shrunk_error           14   0.92    3.14   78.6%       2.98
flagged                14   0.92    3.14   78.6%       2.98
```

### medium atoms
```
strategy                n    MAE   worst  sel.acc  worst reg
lookup_only             1   2.04    2.04  100.0%       0.00
orca_only               1  12.52   12.52    0.0%      10.48
hard_gate               1   2.04    2.04  100.0%       0.00
warn_only               1  12.52   12.52    0.0%      10.48
global_error            1  12.52   12.52    0.0%      10.48
per_molecule_error      1   2.04    2.04  100.0%       0.00
shrunk_error            1   2.04    2.04  100.0%       0.00
flagged                 1   2.04    2.04  100.0%       0.00
```

### rough atoms
```
strategy                n    MAE   worst  sel.acc  worst reg
lookup_only            13  13.76   28.98    7.7%      26.46
orca_only              13   3.97    8.65   92.3%       2.50
hard_gate              13  11.73   19.98   15.4%      13.51
warn_only              13   3.97    8.65   92.3%       2.50
global_error           13   3.97    8.65   92.3%       2.50
per_molecule_error     13   3.97    8.65   92.3%       2.50
shrunk_error           13   3.97    8.65   92.3%       2.50
flagged                13   3.97    8.65   92.3%       2.50
```
