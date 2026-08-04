# DELTA50 — wB97X-D3 def2-SVP



## Lookup bands on this corpus

```
band          n  observed MAE  expected
good        128          0.69      1.12
medium       43          4.15      3.36
rough        11         12.33     10.00
```


Held-out molecules: 2,5-Dihydrofuran, Acetaldehyde, Acetone, Anisole, Cyclobutanone, Cyclopentane, Fluorobenzene, Maleic anhydride, Methyl acetate, Oxetane, Propionitrile, THP, Toluene

## DELTA50 development - wB97X-D3 def2-SVP

```
strategy                n    MAE           95% CI    med   RMSE    p95   worst  sel.acc  regret  worst reg  ref
---------------------------------------------------------------------------------------------------------------
lookup_only           126   1.99 [ 1.21,  2.95]    0.57   4.09   9.16   21.16   66.7%    1.10      19.56    0
orca_only             126   2.12 [ 1.78,  2.50]    1.79   2.61   4.83    7.61   33.3%    1.23       6.07    0
hard_gate             126   1.10 [ 0.74,  1.56]    0.42   1.78   4.04    6.86   75.4%    0.21       3.60    3
warn_only             126   1.07 [ 0.73,  1.48]    0.42   1.69   4.04    5.44   78.6%    0.17       3.60    0
global_error          126   1.07 [ 0.73,  1.48]    0.42   1.69   4.04    5.44   78.6%    0.17       3.60    0
per_molecule_error    126   1.13 [ 0.80,  1.54]    0.61   1.71   4.04    5.44   75.4%    0.24       3.60    0
shrunk_error          126   1.07 [ 0.73,  1.48]    0.42   1.69   4.04    5.44   78.6%    0.17       3.60    0
flagged               126   1.13 [ 0.80,  1.54]    0.61   1.71   4.04    5.44   75.4%    0.24       3.60    0
disagreement_defers   126   1.30 [ 0.91,  1.76]    0.60   2.18   5.22   10.33   73.0%    0.41      10.16    0
```

### good atoms
```
strategy                n    MAE   worst  sel.acc  worst reg
lookup_only            95   0.71    5.43   80.0%       3.60
orca_only              95   2.11    7.61   20.0%       6.07
hard_gate              95   0.71    5.43   80.0%       3.60
warn_only              95   0.71    5.43   80.0%       3.60
global_error           95   0.71    5.43   80.0%       3.60
per_molecule_error     95   0.79    5.43   75.8%       3.60
shrunk_error           95   0.71    5.43   80.0%       3.60
flagged                95   0.79    5.43   75.8%       3.60
disagreement_defers    95   0.74    5.43   78.9%       3.60
```

### medium atoms
```
strategy                n    MAE   worst  sel.acc  worst reg
lookup_only            24   3.66   10.33   33.3%      10.16
orca_only              24   2.44    5.44   66.7%       2.80
hard_gate              24   2.61    6.86   50.0%       2.80
warn_only              24   2.44    5.44   66.7%       2.80
global_error           24   2.44    5.44   66.7%       2.80
per_molecule_error     24   2.44    5.44   66.7%       2.80
shrunk_error           24   2.44    5.44   66.7%       2.80
flagged                24   2.44    5.44   66.7%       2.80
disagreement_defers    24   3.51   10.33   41.7%      10.16
```

### rough atoms
```
strategy                n    MAE   worst  sel.acc  worst reg
lookup_only             7  13.67   21.16    0.0%      19.56
orca_only               7   1.26    3.60  100.0%       0.00
hard_gate               7   1.26    3.60  100.0%       0.00
warn_only               7   1.26    3.60  100.0%       0.00
global_error            7   1.26    3.60  100.0%       0.00
per_molecule_error      7   1.26    3.60  100.0%       0.00
shrunk_error            7   1.26    3.60  100.0%       0.00
flagged                 7   1.26    3.60  100.0%       0.00
disagreement_defers     7   1.26    3.60  100.0%       0.00
```


## DELTA50 held-out - wB97X-D3 def2-SVP

```
strategy                n    MAE           95% CI    med   RMSE    p95   worst  sel.acc  regret  worst reg  ref
---------------------------------------------------------------------------------------------------------------
lookup_only            56   2.70 [ 1.18,  4.66]    0.47   4.93  10.88   16.58   57.1%    1.79      14.54    0
orca_only              56   1.79 [ 1.25,  2.38]    1.10   2.33   5.03    5.42   42.9%    0.87       4.12    0
hard_gate              56   1.12 [ 0.62,  1.68]    0.47   1.73   3.70    5.42   80.4%    0.20       3.16    0
warn_only              56   1.12 [ 0.62,  1.68]    0.47   1.73   3.70    5.42   80.4%    0.20       3.16    0
global_error           56   1.12 [ 0.62,  1.68]    0.47   1.73   3.70    5.42   80.4%    0.20       3.16    0
per_molecule_error     56   1.14 [ 0.65,  1.71]    0.52   1.74   3.70    5.42   75.0%    0.23       3.16    0
shrunk_error           56   1.12 [ 0.62,  1.68]    0.47   1.73   3.70    5.42   80.4%    0.20       3.16    0
flagged                56   1.14 [ 0.65,  1.71]    0.52   1.74   3.70    5.42   75.0%    0.23       3.16    0
disagreement_defers    56   2.01 [ 0.84,  3.61]    0.52   4.06  10.08   16.58   66.1%    1.09      14.54    0
```

### good atoms
```
strategy                n    MAE   worst  sel.acc  worst reg
lookup_only            33   0.63    3.66   81.8%       3.16
orca_only              33   1.76    5.41   18.2%       4.12
hard_gate              33   0.63    3.66   81.8%       3.16
warn_only              33   0.63    3.66   81.8%       3.16
global_error           33   0.63    3.66   81.8%       3.16
per_molecule_error     33   0.67    3.66   72.7%       3.16
shrunk_error           33   0.63    3.66   81.8%       3.16
flagged                33   0.67    3.66   72.7%       3.16
disagreement_defers    33   0.67    3.66   72.7%       3.16
```

### medium atoms
```
strategy                n    MAE   worst  sel.acc  worst reg
lookup_only            19   4.78   16.58   26.3%      14.54
orca_only              19   1.80    5.42   73.7%       1.67
hard_gate              19   1.80    5.42   73.7%       1.67
warn_only              19   1.80    5.42   73.7%       1.67
global_error           19   1.80    5.42   73.7%       1.67
per_molecule_error     19   1.80    5.42   73.7%       1.67
shrunk_error           19   1.80    5.42   73.7%       1.67
flagged                19   1.80    5.42   73.7%       1.67
disagreement_defers    19   4.35   16.58   47.4%      14.54
```

### rough atoms
```
strategy                n    MAE   worst  sel.acc  worst reg
lookup_only             4   9.99   13.28    0.0%      10.50
orca_only               4   1.93    2.77  100.0%       0.00
hard_gate               4   1.93    2.77  100.0%       0.00
warn_only               4   1.93    2.77  100.0%       0.00
global_error            4   1.93    2.77  100.0%       0.00
per_molecule_error      4   1.93    2.77  100.0%       0.00
shrunk_error            4   1.93    2.77  100.0%       0.00
flagged                 4   1.93    2.77  100.0%       0.00
disagreement_defers     4   1.93    2.77  100.0%       0.00
```


## DELTA50 all - wB97X-D3 def2-SVP

```
strategy                n    MAE           95% CI    med   RMSE    p95   worst  sel.acc  regret  worst reg  ref
---------------------------------------------------------------------------------------------------------------
lookup_only           182   2.21 [ 1.44,  3.09]    0.53   4.37  10.08   21.16   63.7%    1.31      19.56    0
orca_only             182   2.02 [ 1.72,  2.33]    1.69   2.53   4.85    7.61   36.3%    1.12       6.07    0
hard_gate             182   1.11 [ 0.80,  1.46]    0.47   1.77   4.02    6.86   76.9%    0.21       3.60    3
warn_only             182   1.08 [ 0.79,  1.41]    0.47   1.70   4.02    5.44   79.1%    0.18       3.60    0
global_error          182   1.08 [ 0.79,  1.41]    0.47   1.70   4.02    5.44   79.1%    0.18       3.60    0
per_molecule_error    182   1.14 [ 0.85,  1.45]    0.55   1.72   4.02    5.44   75.3%    0.24       3.60    0
shrunk_error          182   1.08 [ 0.79,  1.41]    0.47   1.70   4.02    5.44   79.1%    0.18       3.60    0
flagged               182   1.14 [ 0.85,  1.45]    0.55   1.72   4.02    5.44   75.3%    0.24       3.60    0
disagreement_defers   182   1.52 [ 1.05,  2.11]    0.55   2.89   5.43   16.58   70.9%    0.62      14.54    0
```

### good atoms
```
strategy                n    MAE   worst  sel.acc  worst reg
lookup_only           128   0.69    5.43   80.5%       3.60
orca_only             128   2.02    7.61   19.5%       6.07
hard_gate             128   0.69    5.43   80.5%       3.60
warn_only             128   0.69    5.43   80.5%       3.60
global_error          128   0.69    5.43   80.5%       3.60
per_molecule_error    128   0.76    5.43   75.0%       3.60
shrunk_error          128   0.69    5.43   80.5%       3.60
flagged               128   0.76    5.43   75.0%       3.60
disagreement_defers   128   0.72    5.43   77.3%       3.60
```

### medium atoms
```
strategy                n    MAE   worst  sel.acc  worst reg
lookup_only            43   4.15   16.58   30.2%      14.54
orca_only              43   2.15    5.44   69.8%       2.80
hard_gate              43   2.25    6.86   60.5%       2.80
warn_only              43   2.15    5.44   69.8%       2.80
global_error           43   2.15    5.44   69.8%       2.80
per_molecule_error     43   2.15    5.44   69.8%       2.80
shrunk_error           43   2.15    5.44   69.8%       2.80
flagged                43   2.15    5.44   69.8%       2.80
disagreement_defers    43   3.88   16.58   44.2%      14.54
```

### rough atoms
```
strategy                n    MAE   worst  sel.acc  worst reg
lookup_only            11  12.33   21.16    0.0%      19.56
orca_only              11   1.50    3.60  100.0%       0.00
hard_gate              11   1.50    3.60  100.0%       0.00
warn_only              11   1.50    3.60  100.0%       0.00
global_error           11   1.50    3.60  100.0%       0.00
per_molecule_error     11   1.50    3.60  100.0%       0.00
shrunk_error           11   1.50    3.60  100.0%       0.00
flagged                11   1.50    3.60  100.0%       0.00
disagreement_defers    11   1.50    3.60  100.0%       0.00
```
