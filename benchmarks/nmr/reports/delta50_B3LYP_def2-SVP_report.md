# DELTA50 — B3LYP def2-SVP



## Lookup bands on this corpus

```
band          n  observed MAE  expected
good        142          0.67      1.12
medium       52          4.06      3.36
rough        13         13.51     10.00
```


Held-out molecules: 2,5-Dihydrofuran, 2-Butyne, Acetaldehyde, Acetone, Anisole, Cyclobutanone, Cyclohexane, Fluorobenzene, Isobutylene, Methyl acetate, Nitrobenzene, Oxetane, t-Butyl nitrate, t-Butylacetylene

## DELTA50 development - B3LYP def2-SVP

```
strategy                n    MAE           95% CI    med   RMSE    p95   worst  sel.acc  regret  worst reg  ref
---------------------------------------------------------------------------------------------------------------
lookup_only           145   2.24 [ 1.27,  3.45]    0.49   5.13  11.92   32.35   77.9%    1.27      30.95    0
orca_only             145   2.84 [ 2.39,  3.28]    2.28   3.45   5.75    9.21   22.1%    1.88       7.85    0
hard_gate             145   1.45 [ 0.99,  1.99]    0.52   2.66   5.43   13.99   78.6%    0.49      10.94   10
warn_only             145   1.29 [ 0.90,  1.75]    0.52   2.03   5.13    5.57   81.4%    0.32       4.58    0
global_error          145   1.29 [ 0.90,  1.75]    0.52   2.03   5.13    5.57   81.4%    0.32       4.58    0
per_molecule_error    145   1.30 [ 0.90,  1.77]    0.47   2.08   5.24    8.78   75.2%    0.33       4.38    0
shrunk_error          145   1.29 [ 0.90,  1.75]    0.52   2.03   5.13    5.57   77.2%    0.32       4.58    0
flagged               145   1.30 [ 0.90,  1.77]    0.47   2.08   5.24    8.78   75.2%    0.33       4.38    0
disagreement_defers   145   1.61 [ 1.00,  2.43]    0.49   3.14   5.56   16.58   73.8%    0.64      14.21    0
```

### good atoms
```
strategy                n    MAE   worst  sel.acc  worst reg
lookup_only           110   0.66    5.43   89.1%       3.35
orca_only             110   2.71    9.21   10.9%       7.85
hard_gate             110   0.66    5.43   89.1%       3.35
warn_only             110   0.66    5.43   89.1%       3.35
global_error          110   0.66    5.43   89.1%       3.35
per_molecule_error    110   0.71    5.43   80.0%       3.35
shrunk_error          110   0.66    5.43   83.6%       3.35
flagged               110   0.71    5.43   80.0%       3.35
disagreement_defers   110   0.71    5.43   80.0%       3.35
```

### medium atoms
```
strategy                n    MAE   worst  sel.acc  worst reg
lookup_only            28   4.66   16.58   53.6%      14.21
orca_only              28   3.41    5.57   46.4%       4.58
hard_gate              28   3.50    8.78   39.3%       4.38
warn_only              28   3.41    5.57   46.4%       4.58
global_error           28   3.41    5.57   46.4%       4.58
per_molecule_error     28   3.26    8.78   50.0%       4.38
shrunk_error           28   3.41    5.57   46.4%       4.58
flagged                28   3.26    8.78   50.0%       4.38
disagreement_defers    28   4.87   16.58   42.9%      14.21
```

### rough atoms
```
strategy                n    MAE   worst  sel.acc  worst reg
lookup_only             7  17.36   32.35    0.0%      30.95
orca_only               7   2.71    4.24  100.0%       0.00
hard_gate               7   5.80   13.99   71.4%      10.94
warn_only               7   2.71    4.24  100.0%       0.00
global_error            7   2.71    4.24  100.0%       0.00
per_molecule_error      7   2.71    4.24  100.0%       0.00
shrunk_error            7   2.71    4.24  100.0%       0.00
flagged                 7   2.71    4.24  100.0%       0.00
disagreement_defers     7   2.71    4.24  100.0%       0.00
```


## DELTA50 held-out - B3LYP def2-SVP

```
strategy                n    MAE           95% CI    med   RMSE    p95   worst  sel.acc  regret  worst reg  ref
---------------------------------------------------------------------------------------------------------------
lookup_only            62   2.55 [ 1.51,  3.93]    1.08   4.04   9.19   13.28   58.1%    1.46      12.83    0
orca_only              62   2.30 [ 1.78,  2.81]    1.69   2.85   5.18    7.81   41.9%    1.21       6.39    0
hard_gate              62   1.47 [ 1.01,  1.98]    0.82   2.13   5.15    7.81   75.8%    0.37       6.39    3
warn_only              62   1.42 [ 0.98,  1.92]    0.84   2.06   4.21    7.81   77.4%    0.32       6.39    0
global_error           62   1.42 [ 0.98,  1.92]    0.84   2.06   4.21    7.81   77.4%    0.32       6.39    0
per_molecule_error     62   1.45 [ 1.02,  1.95]    0.84   2.11   5.15    7.81   74.2%    0.36       6.39    0
shrunk_error           62   1.42 [ 0.98,  1.92]    0.84   2.06   4.21    7.81   77.4%    0.32       6.39    0
flagged                62   1.45 [ 1.02,  1.95]    0.84   2.11   5.15    7.81   74.2%    0.36       6.39    0
disagreement_defers    62   1.76 [ 1.14,  2.58]    0.84   2.76   5.44   10.08   67.7%    0.67       9.18    0
```

### good atoms
```
strategy                n    MAE   worst  sel.acc  worst reg
lookup_only            32   0.74    2.82   84.4%       2.28
orca_only              32   2.45    6.01   15.6%       4.72
hard_gate              32   0.74    2.82   84.4%       2.28
warn_only              32   0.74    2.82   84.4%       2.28
global_error           32   0.74    2.82   84.4%       2.28
per_molecule_error     32   0.78    2.82   75.0%       2.28
shrunk_error           32   0.74    2.82   84.4%       2.28
flagged                32   0.78    2.82   75.0%       2.28
disagreement_defers    32   0.78    2.82   75.0%       2.28
```

### medium atoms
```
strategy                n    MAE   worst  sel.acc  worst reg
lookup_only            24   3.36   10.08   37.5%       9.18
orca_only              24   2.11    7.81   62.5%       6.39
hard_gate              24   2.23    7.81   58.3%       6.39
warn_only              24   2.11    7.81   62.5%       6.39
global_error           24   2.11    7.81   62.5%       6.39
per_molecule_error     24   2.13    7.81   66.7%       6.39
shrunk_error           24   2.11    7.81   62.5%       6.39
flagged                24   2.13    7.81   66.7%       6.39
disagreement_defers    24   2.93   10.08   50.0%       9.18
```

### rough atoms
```
strategy                n    MAE   worst  sel.acc  worst reg
lookup_only             6   9.03   13.28    0.0%      12.83
orca_only               6   2.28    5.21  100.0%       0.00
hard_gate               6   2.28    5.21  100.0%       0.00
warn_only               6   2.28    5.21  100.0%       0.00
global_error            6   2.28    5.21  100.0%       0.00
per_molecule_error      6   2.28    5.21  100.0%       0.00
shrunk_error            6   2.28    5.21  100.0%       0.00
flagged                 6   2.28    5.21  100.0%       0.00
disagreement_defers     6   2.28    5.21  100.0%       0.00
```


## DELTA50 all - B3LYP def2-SVP

```
strategy                n    MAE           95% CI    med   RMSE    p95   worst  sel.acc  regret  worst reg  ref
---------------------------------------------------------------------------------------------------------------
lookup_only           207   2.33 [ 1.55,  3.29]    0.60   4.83  10.25   32.35   72.0%    1.33      30.95    0
orca_only             207   2.68 [ 2.30,  3.04]    2.23   3.28   5.75    9.21   28.0%    1.68       7.85    0
hard_gate             207   1.46 [ 1.09,  1.87]    0.70   2.51   5.43   13.99   77.8%    0.45      10.94   13
warn_only             207   1.33 [ 1.02,  1.68]    0.74   2.04   5.12    7.81   80.2%    0.32       6.39    0
global_error          207   1.33 [ 1.02,  1.68]    0.74   2.04   5.12    7.81   80.2%    0.32       6.39    0
per_molecule_error    207   1.34 [ 1.02,  1.71]    0.67   2.09   5.28    8.78   74.9%    0.34       6.39    0
shrunk_error          207   1.33 [ 1.02,  1.68]    0.74   2.04   5.12    7.81   77.3%    0.32       6.39    0
flagged               207   1.34 [ 1.02,  1.71]    0.67   2.09   5.28    8.78   74.9%    0.34       6.39    0
disagreement_defers   207   1.65 [ 1.16,  2.23]    0.67   3.03   5.56   16.58   72.0%    0.65      14.21    0
```

### good atoms
```
strategy                n    MAE   worst  sel.acc  worst reg
lookup_only           142   0.67    5.43   88.0%       3.35
orca_only             142   2.65    9.21   12.0%       7.85
hard_gate             142   0.67    5.43   88.0%       3.35
warn_only             142   0.67    5.43   88.0%       3.35
global_error          142   0.67    5.43   88.0%       3.35
per_molecule_error    142   0.73    5.43   78.9%       3.35
shrunk_error          142   0.68    5.43   83.8%       3.35
flagged               142   0.73    5.43   78.9%       3.35
disagreement_defers   142   0.73    5.43   78.9%       3.35
```

### medium atoms
```
strategy                n    MAE   worst  sel.acc  worst reg
lookup_only            52   4.06   16.58   46.2%      14.21
orca_only              52   2.81    7.81   53.8%       6.39
hard_gate              52   2.92    8.78   48.1%       6.39
warn_only              52   2.81    7.81   53.8%       6.39
global_error           52   2.81    7.81   53.8%       6.39
per_molecule_error     52   2.74    8.78   57.7%       6.39
shrunk_error           52   2.81    7.81   53.8%       6.39
flagged                52   2.74    8.78   57.7%       6.39
disagreement_defers    52   3.97   16.58   46.2%      14.21
```

### rough atoms
```
strategy                n    MAE   worst  sel.acc  worst reg
lookup_only            13  13.51   32.35    0.0%      30.95
orca_only              13   2.51    5.21  100.0%       0.00
hard_gate              13   4.18   13.99   84.6%      10.94
warn_only              13   2.51    5.21  100.0%       0.00
global_error           13   2.51    5.21  100.0%       0.00
per_molecule_error     13   2.51    5.21  100.0%       0.00
shrunk_error           13   2.51    5.21  100.0%       0.00
flagged                13   2.51    5.21  100.0%       0.00
disagreement_defers    13   2.51    5.21  100.0%       0.00
```
