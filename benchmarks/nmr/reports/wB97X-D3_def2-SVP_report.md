## wB97X-D3 def2-SVP - all assigned carbons

```
strategy                n    MAE           95% CI    med   RMSE    p95   worst  sel.acc  regret  worst reg  ref
---------------------------------------------------------------------------------------------------------------
lookup_only            28   6.92 [ 4.33,  7.96]    2.40  10.34  18.73   28.98   39.3%    5.36      27.51    0
orca_only              28   2.41 [ 1.27,  2.87]    1.86   3.28   5.71   10.84   60.7%    0.85       8.80    0
hard_gate              28   2.00 [ 0.89,  2.44]    1.34   3.06   5.71   10.84   75.0%    0.43       8.80    0
warn_only              28   2.00 [ 0.89,  2.44]    1.34   3.06   5.71   10.84   75.0%    0.43       8.80    0
global_error           28   2.00 [ 0.89,  2.44]    1.34   3.06   5.71   10.84   75.0%    0.43       8.80    0
per_molecule_error     28   2.00 [ 0.89,  2.44]    1.34   3.06   5.71   10.84   75.0%    0.43       8.80    0
shrunk_error           28   2.00 [ 0.89,  2.44]    1.34   3.06   5.71   10.84   75.0%    0.43       8.80    0
flagged                28   2.00 [ 0.89,  2.44]    1.34   3.06   5.71   10.84   75.0%    0.43       8.80    0
disagreement_defers    28   1.68 [ 0.89,  2.00]    1.34   2.31   4.52    6.24   78.6%    0.11       1.17    0
```

### good atoms
```
strategy                n    MAE   worst  sel.acc  worst reg
lookup_only            14   0.92    3.14   64.3%       1.17
orca_only              14   1.76    4.14   35.7%       3.68
hard_gate              14   0.92    3.14   64.3%       1.17
warn_only              14   0.92    3.14   64.3%       1.17
global_error           14   0.92    3.14   64.3%       1.17
per_molecule_error     14   0.92    3.14   64.3%       1.17
shrunk_error           14   0.92    3.14   64.3%       1.17
flagged                14   0.92    3.14   64.3%       1.17
disagreement_defers    14   0.92    3.14   64.3%       1.17
```

### medium atoms
```
strategy                n    MAE   worst  sel.acc  worst reg
lookup_only             1   2.04    2.04  100.0%       0.00
orca_only               1  10.84   10.84    0.0%       8.80
hard_gate               1  10.84   10.84    0.0%       8.80
warn_only               1  10.84   10.84    0.0%       8.80
global_error            1  10.84   10.84    0.0%       8.80
per_molecule_error      1  10.84   10.84    0.0%       8.80
shrunk_error            1  10.84   10.84    0.0%       8.80
flagged                 1  10.84   10.84    0.0%       8.80
disagreement_defers     1   2.04    2.04  100.0%       0.00
```

### rough atoms
```
strategy                n    MAE   worst  sel.acc  worst reg
lookup_only            13  13.76   28.98    7.7%      27.51
orca_only              13   2.47    6.24   92.3%       0.01
hard_gate              13   2.47    6.24   92.3%       0.01
warn_only              13   2.47    6.24   92.3%       0.01
global_error           13   2.47    6.24   92.3%       0.01
per_molecule_error     13   2.47    6.24   92.3%       0.01
shrunk_error           13   2.47    6.24   92.3%       0.01
flagged                13   2.47    6.24   92.3%       0.01
disagreement_defers    13   2.47    6.24   92.3%       0.01
```
