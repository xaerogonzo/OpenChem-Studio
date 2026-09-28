"""Marrero and Gani (2001), Fluid Phase Equilibria 183-184, 183-208 -- Tables 6 and 7,
transcribed from the rendered page images (pp. 194-200; the PDF's text layer is missing for
these pages -- see docs/research/literature.toml's marrero2001 entry).

Column order matches the paper's own table header, left to right:

    Table 6 (first-order groups):  Tm1i, Tb1i, Tc1i, Pc1i, Vc1i, Gf1i, Hf1i, Hv1i, Hfus1i
    Table 7 (second-order groups): Tm2j, Tb2j, Tc2j, Pc2j, Vc2j, Gf2j, Hf2j, Hv2j, Hfus2j

`None` is the paper's own "*****" -- a group-contribution the authors did not estimate because no
reliable experimental value was found, never a zero. `tests/test_marrero2001_table.py` checks a
sample of these against the paper's own worked examples (Appendix B) before anything is built on
this table.

Table 8 (third-order groups, for polycyclic compounds) is NOT transcribed here: it is out of scope
for the molecules this table exists to validate (RDX, HMX, TNT, PETN and the rest of the Joback
census corpus are each acyclic or single-ring).
"""

from __future__ import annotations

import math

#: id, group symbol (as printed), worked example, then the nine Table 6 columns.
FIRST_ORDER = [
    (1, "CH3", "n-Tetracontane(2)", 0.6953, 0.8491, 1.7506, 0.018615, 68.35, 2.878, -42.479, 0.217, 1.660),
    (2, "CH2", "n-Tetracontane(38)", 0.2515, 0.7141, 1.3327, 0.013547, 56.28, 8.064, -20.829, 4.910, 2.639),
    (3, "CH", "2-Methylpentane(1)", -0.3730, 0.2925, 0.5960, 0.007259, 37.50, 8.254, -7.122, 7.962, 0.134),
    (4, "C", "2,2-Dimethylbutane(1)", 0.0256, -0.0671, 0.0306, 0.001219, 16.01, 16.413, 8.928, 10.730, -1.232),
    (5, "CH2=CH", "1-Hexene(1)", 1.1728, 1.5596, 3.2295, 0.025745, 111.43, 95.738, 57.509, 4.031, 1.268),
    (6, "CH=CH", "2-Hexene(1)", 0.9460, 1.5597, 3.0741, 0.023003, 98.43, 92.656, 69.664, 9.456, 4.441),
    (7, "CH2=C", "2-Methyl-1-butene(1)", 0.7662, 1.3621, 2.7717, 0.021137, 91.40, 85.107, 61.625, 8.602, 2.451),
    (8, "CH=C", "2-Methyl-2-butene(1)", 0.1732, 1.2971, 2.5666, 0.019609, 83.89, 88.691, 81.835, 14.095, 3.032),
    (9, "C=C", "2,3-Dimethyl-2-butene(1)", 0.3928, 1.2739, 2.6391, 0.014114, 90.66, 93.119, 95.710, 19.910, 2.616),
    (10, "CH2=C=CH", "1,2-Butadiene(1)", 1.7036, 2.6840, 5.4330, 0.035483, 143.57, 229.906, 198.840, 11.310, 7.076),
    (11, "CH2=C=C", "3-Methyl-1,2-butadiene(1)", 1.5453, 2.4014, 4.8219, 0.029678, 146.36, 226.710, 208.490, None, 7.435),
    (12, "CH=C=CH", "2,3-Pentadiene(1)", 1.2850, 2.5400, None, None, None, None, None, None, 6.000),
    (13, "CH#C", "1-Pentyne(1)", 2.2276, 1.7618, 3.7897, 0.014010, 84.60, 230.029, 224.902, 6.144, -1.548),
    (14, "C#C", "3-Decyne(1)", 2.0516, 1.6767, 4.5870, 0.010888, 74.66, 216.013, 228.282, 12.540, 6.128),
    (15, "aCH", "Benzene(6)", 0.5860, 0.8365, 2.0337, 0.007260, 42.39, 26.732, 12.861, 3.683, 1.948),
    (16, "aC fused w/ aromatic ring", "Naphthalene(2)", 1.8955, 1.7324, 5.4979, 0.003564, 35.71, 20.379, 20.187, 6.631, 0.845),
    (17, "aC fused w/ nonaromatic subring", "Indane(2)", 1.2065, 1.1995, 3.1058, 0.006512, 34.65, 33.912, 30.768, 6.152, 1.095),
    (18, "aC except as above", "Benzophenone(1)", 0.9176, 1.5468, 4.5344, 0.012859, 26.47, 23.331, 24.701, 6.824, -0.531),
    (19, "aN in aromatic ring", "Pyridine(1)", 2.0438, 1.3977, 4.0954, -0.003339, 36.47, 89.902, 70.862, 9.420, 2.555),
    (20, "aC-CH3", "Toluene(1)", 1.0068, 1.5653, 3.4611, 0.020907, 97.33, 24.919, -19.258, 8.279, 2.969),
    (21, "aC-CH2", "Ethylbenzene(1)", 0.1065, 1.4925, 2.9003, 0.018082, 87.19, 31.663, 4.380, 11.981, 0.948),
    (22, "aC-CH", "Cumene(1)", -0.5197, 0.8665, 1.9512, 0.011795, 73.51, 30.393, 18.440, 13.519, -1.037),
    (23, "aC-C", "tert-Butylbenzene(1)", -0.1041, 0.5229, 0.8576, 0.011298, 67.20, 40.127, 35.297, 16.912, -2.856),
    (24, "aC-CH=CH2", "Styrene(1)", 1.2832, 2.4308, 5.7861, 0.030637, 134.69, 114.531, 77.863, None, 4.013),
    (25, "aC-CH=CH", "1-Propenylbenzene(1)", 1.7744, 2.9262, 6.5062, 0.026282, 128.84, 111.216, 88.084, None, 8.274),
    (26, "aC-C=CH2", "alpha-Methylstyrene(1)", 1.2612, 2.1472, 4.9967, 0.026371, 110.74, 115.728, 90.927, None, 3.324),
    (27, "aC-C#CH", "Phenylacetylene(1)", 1.7495, 2.3057, 6.4572, 0.019507, 112.08, 263.205, 257.448, None, 2.514),
    (28, "aC-C#C", "1-Phenyl-1-propyne(1)", None, 2.7341, None, None, None, None, None, None, None),
    (29, "OH", "1,4-Butanediol(2)", 2.7888, 2.5670, 5.2188, -0.005401, 30.61, -144.051, -178.360, 24.214, 4.786),
    (30, "aC-OH", "Phenol(1)", 5.1473, 3.3205, 9.3472, -0.008788, 50.77, -131.327, -164.191, 34.099, 8.427),
    (31, "COOH", "1,5-Pentanedioic acid(2)", 7.4042, 5.1108, 14.6038, 0.009885, 90.66, -337.090, -389.931, 17.002, 10.692),
    (32, "aC-COOH", "Benzoic acid(1)", 12.4296, 6.0677, 15.4515, 0.017100, 119.10, -312.422, -361.249, None, 14.649),
    (33, "CH3CO", "2-Butanone(1)", 2.9588, 3.1178, 7.0058, 0.025227, 127.99, -120.667, -180.604, 15.195, 8.062),
    (34, "CH2CO", "3-Pentanone(1)", 2.5232, 2.6761, 5.7157, 0.019619, 112.79, -120.425, -163.090, 19.392, 8.826),
    (35, "CHCO", "2,4-Dimethyl-3-pentanone(1)", 1.1565, 2.1748, 4.4743, 0.012487, 97.16, -116.799, -139.909, 20.350, 7.205),
    (36, "CCO", "2,2,4,4-Tetramethyl-3-pentanone(1)", 1.0638, 1.7287, None, None, None, None, None, None, None),
    (37, "aC-CO", "Acetophenone(1)", 2.9157, 3.4650, 9.4806, 0.011007, 90.69, -91.812, -106.965, 25.036, 4.852),
    (38, "CHO", "1-Hexanal(1)", 3.0186, 2.5388, 5.8013, 0.010204, 71.08, -100.882, -130.816, 12.370, None),
    (39, "aC-CHO", "Benzaldehyde(1)", 2.4744, 3.5172, 9.4795, 0.019633, 122.91, -80.222, -107.159, None, 7.273),
    (40, "CH3COO", "Butyl acetate(1)", 2.1657, 3.1228, 6.3179, 0.033812, 148.91, -306.733, -387.458, 19.342, 7.910),
    (41, "CH2COO", "Methyl Butyrate(1)", 1.6329, 2.9850, 5.9619, 0.026983, 132.89, -298.332, -364.204, 21.100, 9.479),
    (42, "CHCOO", "Ethyl isobutyrate(1)", 1.0668, 2.2869, 4.7558, 0.021990, 125.52, -301.414, -352.057, 24.937, 9.317),
    (43, "CCOO", "Ethyl 2,2-dimethylpropionate(1)", 0.3983, 1.6918, None, None, None, None, None, 23.739, None),
    (44, "HCOO", "Propyl formate(1)", 2.0223, 2.5972, 5.6064, 0.015249, 93.29, -276.878, -327.678, 15.422, 8.115),
    (45, "aC-COO", "Methyl benzoate(1)", 1.3348, 3.1952, 6.7311, 0.018948, 105.53, -291.662, -307.727, 25.206, 8.149),
    (46, "aC-OOCH", "Phenyl formate(1)", None, 0.4621, None, None, None, None, None, None, None),
    (47, "aC-OOC", "Phenyl acetate(1)", 4.8044, 3.0854, None, None, None, None, None, None, 5.875),
    (48, "COO except as above", "Ethyl acrylate(1)", 1.5038, 2.1903, 4.7346, 0.013087, 81.17, -299.803, -331.397, None, 10.573),
    (49, "CH3O", "Methyl butyl ether(1)", 1.3643, 1.7703, 3.4393, 0.020084, 88.20, -90.329, -156.062, 5.783, 5.089),
    (50, "CH2O", "Di-n-butyl ether(1)", 0.8733, 1.3368, 2.4217, 0.017954, 74.03, -105.579, -152.239, 9.997, 4.891),
    (51, "CH-O", "sec-Butyl ether(1)", 0.2461, 0.8924, 0.7889, 0.014487, 60.06, -101.207, -147.709, 14.620, 4.766),
    (52, "C-O", "tert-Butylether(1)", -0.4446, 0.4983, 0.2511, 0.005613, 52.96, -92.804, -121.608, 13.850, 2.458),
    (53, "aC-O", "Methyl phenyl ether(1)", 1.3045, 1.8522, 3.6588, 0.005115, 47.27, -83.354, -101.783, 16.151, -0.118),
    (54, "CH2NH2", "Ethylamine(1)", 3.2742, 2.7987, 8.1745, 0.011413, 117.62, 68.812, -10.703, 15.432, 13.482),
    (55, "CHNH2", "sec-Butylamine(1)", 30.8394, 2.0948, 4.2847, 0.013049, 76.36, 61.452, 0.730, 16.048, 6.283),
    (56, "CNH2", "tert-Butylamine(1)", 11.7400, 1.6525, 2.8546, 0.010790, 80.01, 55.202, 2.019, 17.257, None),
    (57, "CH3NH", "Dimethylamine(1)", 2.4034, 2.2514, 4.5529, 0.015863, 77.04, 88.512, 24.740, 11.831, 4.490),
    (58, "CH2NH", "Dipropylamine(1)", 1.7746, 1.8750, 3.2422, 0.020482, 95.15, 88.874, 23.610, 13.067, 7.711),
    (59, "CHNH", "Diisopropylamine(1)", 1.7577, 1.2317, 2.0057, 0.005329, 99.16, 73.101, 21.491, 14.048, 2.561),
    (60, "CH3N", "Methyldiethylamine(1)", 0.9607, 1.3841, 3.0106, 0.021186, 94.94, 125.906, 55.024, 9.493, 6.008),
    (61, "CH2N", "Triethylamine(1)", 0.0442, 1.1222, 2.1673, 0.027454, 74.05, 121.247, 65.331, 12.636, 1.756),
    (62, "aC-NH2", "Aniline(1)", 3.9889, 3.8298, 10.2155, 0.005335, 81.40, 66.470, 17.501, 23.335, 6.542),
    (63, "aC-NH", "N-methyl aniline(1)", 1.4837, 2.9230, 8.4081, -0.005596, 86.37, 98.195, 53.274, 23.026, 0.624),
    (64, "aC-N", "N,N-dimethyl aniline(1)", 1.7618, 2.1918, 5.8536, -0.000838, 108.39, 143.280, 115.606, 22.249, -2.576),
    (65, "NH2 except as above", "Cyclobutylamine(1)", 3.3478, 2.0315, 4.7420, 0.000571, 63.39, 42.687, -8.556, 13.425, 6.158),
    (66, "CH=N", "Acetaldazine(2)", 8.8492, 1.5332, None, None, None, None, None, None, None),
    (67, "C=N", "Ketazine(2)", 1.4621, 1.4291, None, None, None, None, None, None, None),
    (68, "CH2CN", "Propionitrile(1)", 2.5760, 4.5871, 12.9827, 0.036523, 133.62, 134.997, 99.245, 21.923, 7.303),
    (69, "CHCN", "Isobutyronitrile(1)", 2.1393, 3.9774, 8.4309, 0.029034, 134.73, 142.475, 151.390, 24.963, 9.464),
    (70, "CCN", "2,2-Dimethylpropionitrile(1)", 3.3807, 2.8870, 5.8829, 0.024654, 120.74, 142.295, 124.770, 24.967, 4.166),
    (71, "aC-CN", "Benzonitrile(1)", 5.1346, 4.1424, 10.4124, 0.020978, 119.08, 162.175, 148.968, None, 6.788),
    (72, "CN except as above", "Acrylonitrile(1)", 3.2747, 3.0972, 8.1381, 0.024346, 94.91, 130.986, 124.917, 16.639, 6.867),
    (73, "CH2NCO", "Ethyl isocyanate(1)", 4.2256, 3.4891, None, None, None, None, None, None, None),
    (74, "CHNCO", "Isopropyl isocyanate(1)", None, 3.1220, None, None, None, None, None, None, None),
    (75, "CNCO", "tert-Butyl isocyanate(1)", 9.1492, None, None, None, None, None, None, None, None),
    (76, "aC-NCO", "Phenyl isocyanate(1)", 2.2327, 3.1853, 6.5884, 0.025065, 141.24, None, None, None, None),
    (77, "CH2NO2", "1-Nitropropane(1)", 3.2131, 4.5311, 10.9507, 0.021056, 157.57, 25.783, -65.620, 29.640, 10.989),
    (78, "CHNO2", "2-Nitropropane(1)", 0.7812, 3.8069, 9.5487, 0.014899, 143.36, 16.407, -60.750, 29.173, None),
    (79, "CNO2", "2-Methyl-2-nitropropane(1)", 5.6280, 3.3059, None, None, None, None, None, None, -4.187),
    (80, "aC-NO2", "Nitrobenzene(1)", 4.3531, 4.5750, 12.1243, 0.018311, 133.06, 57.352, -22.931, 24.863, 7.572),
    (81, "NO2 except as above", "Nitrocyclohexane(1)", 3.0376, 3.2069, None, None, None, None, None, None, 6.302),
    (82, "ONO", "Butyl nitrite(1)", None, 1.8896, None, None, None, None, None, None, None),
    (83, "ONO2", "n-Butyl nitrate(1)", 2.5974, 3.2656, None, None, None, None, None, None, 9.353),
    (84, "HCON(CH2)2", "Diethylformamide(1)", None, 5.8779, None, None, None, None, None, None, None),
    (85, "HCONHCH2", "Ethylformamide(1)", None, 7.4566, None, None, None, None, None, 46.490, None),
    (86, "CONH2", "Butyramide(1)", 13.2124, 6.5652, 25.1184, 0.001467, 138.71, -127.512, -201.369, 44.240, 16.840),
    (87, "CONHCH3", "Methylacetamide(1)", 5.4720, 5.0724, 20.5590, 0.023455, 190.71, -102.912, -203.069, None, 17.429),
    (88, "CONHCH2", "Ethylacetamide(1)", 5.8825, 6.6810, None, None, None, None, None, -183.613, 52.723),
    (89, "CON(CH3)2", "Dimethylacetamide(1)", 4.1720, 6.0070, 15.4603, 0.043090, 244.71, -56.412, -188.069, 38.290, 11.553),
    (90, "CONCH3CH2", "Methylethylacetamide(1)", None, None, None, None, None, None, -48.210, None, None),
    (91, "CON(CH2)2", "Diethylacetamide(1)", None, 5.0664, None, None, None, None, None, None, None),
    (92, "CONHCO", "Diacetamide(1)", 9.1763, 7.6172, None, None, None, None, None, None, None),
    (93, "CONCO", "Methyldiacetamide", 3.2657, 5.6487, None, None, None, None, None, None, None),
    (94, "aC-CONH2", "Benzamide", 12.8071, 8.3775, None, None, None, None, None, None, 16.811),
    (95, "aC-NH(CO)H", "N-phenylformamide(1)", 5.6631, 7.3497, 19.8979, 0.023447, 162.08, -44.595, -125.052, None, 8.658),
    (96, "aC-N(CO)H", "N-methyl-N-phenylmethanamide(1)", 3.3602, 5.1373, None, None, None, None, None, None, None),
    (97, "aC-CONH", "N-methylbenzamide(1)", 6.5160, 7.5850, None, None, None, None, None, None, 10.959),
    (98, "aC-NHCO", "N-(2-methylphenyl)acetamide(1)", 9.8204, 7.4955, None, None, None, None, None, None, 4.370),
    (99, "aC-NCO", "Phenylmethylacetamide(1)", 7.2552, None, None, None, None, None, None, None, None),
    (100, "NHCONH", "N,N'-dimethylurea(1)", 9.3110, 8.9406, None, None, None, None, None, None, 9.862),
    (101, "NH2CONH", "Methylurea(1)", 14.2020, 16.3539, None, None, None, None, None, None, 12.845),
    (102, "NH2CON", "N,N-dimethylurea(1)", 13.0856, 2.0796, None, None, None, None, None, None, 10.958),
    (103, "NHCON", "Trimethylurea(1)", 8.4447, 7.1529, None, None, None, None, None, None, 12.098),
    (104, "NCON", "Tetramethylurea(1)", 3.5041, 4.1459, None, None, None, None, None, None, 9.557),
    (105, "aC-NHCONH2", "Phenylurea(1)", 13.4695, 5.7604, None, None, None, None, None, None, 16.703),
    (106, "aC-NHCONH", "N,N'-diphenylurea", 23.2570, 1.1633, None, None, None, None, None, None, 18.460),
    (107, "NHCO except as above", "N-chloroacetamide(1)", 3.0882, None, None, None, None, None, None, None, None),
    (108, "CH2Cl", "1-Chlorobutane(1)", 1.9253, 2.6364, 6.2561, 0.021419, 112.12, -19.484, -65.056, 11.754, 6.353),
    (109, "CHCl", "2-Chloropropane(1)", 1.0224, 2.0246, 4.3756, 0.015640, 100.78, -31.933, -65.127, 12.048, None),
    (110, "CCl", "2-Chloro-2-methylpropane(1)", 1.8424, 1.7049, 3.7063, 0.009187, 87.01, -37.848, -62.881, 16.597, -0.082),
    (111, "CHCl2", "1,1-Dichloroethane(1)", 2.5196, 3.3420, 7.8956, 0.028236, 159.79, -24.214, -80.812, 17.251, 6.781),
    (112, "CCl2", "2,2-Dichloropropane(1)", 3.6491, 2.9609, None, None, None, None, None, 20.473, 1.823),
    (113, "CCl3", "1,1,1-Trichloroethane", 4.4493, 3.9093, 8.8073, 0.036746, 204.71, -44.122, -105.369, 20.550, 3.492),
    (114, "CH2F", "1-Fluorobutane(1)", 1.5597, 1.5022, 3.3179, 0.023315, 87.71, -180.212, -227.469, 8.238, 7.139),
    (115, "CHF", "2-Fluorobutane(1)", 1.1289, 1.3738, 2.6702, 0.020040, 78.08, -228.239, -261.901, None, 3.917),
    (116, "CF", "2-Fluoro-2-methylpropane(1)", 2.5398, 1.0084, 2.1633, -0.010120, None, None, None, 6.739, None),
    (117, "CHF2", "1,1-Difluoroethane(1)", 2.1689, 2.2238, 3.5702, 0.031524, 102.71, -411.239, -463.901, None, 7.011),
    (118, "CF2", "Perfluorohexane(4)", 0.1312, 0.5142, 0.8543, 0.018572, 95.09, None, None, 1.621, None),
    (119, "CF3", "Hexafluoroethane(2)", 1.4828, 1.1916, 1.7737, 0.048565, 108.85, -615.333, -673.875, 7.352, 2.526),
    (120, "CCl2F", "Tetrachloro-1,2-difluoroethane(2)", 3.2035, 2.5053, 5.1653, 0.037948, 171.04, -249.020, -306.765, 8.630, 3.114),
    (121, "HCClF", "1-Chloro-1,2,2,2-tetrafluoroethane(1)", None, 2.0542, None, None, None, None, None, None, None),
    (122, "CClF2", "1,2-Dichlorotetrafluoroethane(2)", 1.7510, 1.7227, 3.0593, 0.041641, 146.01, -396.814, -458.074, 8.086, 2.156),
    (123, "aC-Cl", "Chlorobenzene(1)", 1.7134, 2.0669, 5.7046, 0.016033, 92.67, 1.985, -17.002, 11.224, 4.435),
    (124, "aC-F", "Hexafluorobenzene(6)", 0.9782, 0.7945, 1.5491, 0.014037, 54.36, -141.306, -160.965, 3.965, 2.003),
    (125, "aC-I", "Iodobenzene(1)", 2.1905, 3.7739, 12.4470, 0.014403, 131.08, 91.505, 95.048, None, 2.814),
    (126, "aC-Br", "Bromobenzene(1)", 2.4741, 2.8414, 8.4199, 0.010199, 104.12, 42.977, 38.917, 14.393, 5.734),
    (127, "I- except as above", "Iodoethane(1)", 1.9444, 3.1778, 8.5775, -0.004637, 104.28, 43.910, 47.632, 14.171, 6.103),
    (128, "Br- except as above", "Bromoethane(1)", 1.7641, 2.4231, 4.5036, -0.001460, 77.99, 5.528, -1.703, 9.888, 4.826),
    (129, "F- except as above", "Benzyl fluoride(1)", 1.2308, 0.8504, 0.8976, 0.012034, 24.62, -182.973, -201.968, None, 3.096),
    (130, "Cl- except as above", "Ethyl chloroacetate(1)", 1.5454, 1.5147, 4.0947, 0.007923, 57.77, -29.876, -46.963, None, 5.181),
    (131, "CHNOH", "Propionaldehyde oxime(1)", 3.9813, 4.5721, None, None, None, None, None, None, None),
    (132, "CNOH", "Diethyl ketoxime(1)", 3.5484, 4.0142, None, None, None, None, None, None, None),
    (133, "aC-CHNOH", "Phenyl oxime(1)", 10.5579, None, None, None, None, None, None, None, None),
    (134, "OCH2CH2OH", "2-Ethoxyethanol(1)", 2.3651, 4.8721, 10.4579, 0.025986, 159.33, -233.335, -343.903, 31.493, 8.454),
    (135, "OCHCH2OH", "2-Ethoxy-1-propanol(1)", None, 4.2329, None, None, None, None, None, None, None),
    (136, "OCH2CHOH", "1-Methoxy-2-propanol(1)", 1.5791, 3.6653, None, 0.018783, 147.66, -239.423, -333.385, None, 12.594),
    (137, "-O-OH", "tert-Butylhydroperoxide(1)", 4.8181, 3.1669, 5.8307, -0.002815, 58.01, -75.568, -125.111, None, None),
    (138, "CH2SH", "Ethanethiol(1)", 2.2992, 3.1974, 7.7300, 0.017299, 105.68, 27.469, -8.021, 16.815, 10.068),
    (139, "CHSH", "2-Propanethiol(1)", 0.9704, 2.5910, 5.8527, 0.008968, 109.36, 27.030, 3.510, 17.098, 4.266),
    (140, "CSH", "2-Methyl-2-propanethiol(1)", 4.2329, 2.0902, 4.6431, 0.005118, 94.01, 27.338, 12.589, 18.397, -0.623),
    (141, "aC-SH", "Benzenethiol(1)", 2.8464, 3.2675, 9.5115, 0.010086, 95.08, 48.905, 41.648, 17.413, 4.513),
    (142, "-SH (except as above)", "Cyclohexanethiol(1)", 0.9600, 2.3323, 7.7987, 0.006399, 57.89, 15.818, 11.339, 9.813, 5.829),
    (143, "CH3S", "Dimethylsulfide(1)", 1.7150, 2.9892, 6.9733, 0.018013, 122.03, 35.845, -3.337, 14.296, 7.497),
    (144, "CH2S", "Diethylsulfide(1)", 1.0063, 2.6524, 6.4871, 0.015254, 106.60, 42.684, 21.492, 16.965, 4.096),
    (145, "CHS", "Diisopropylsulfide(1)", 0.7892, 2.0965, None, None, None, None, None, 19.038, None),
    (146, "CS", "di-tert-Butylsulfide(1)", 1.1170, 1.6412, None, None, None, None, None, 19.996, None),
    (147, "aC-S-", "Phenyl methyl sulfide(1)", 0.9646, 2.9731, None, None, None, None, None, None, None),
    (148, "SO", "Dimethyl sulfoxide(1)", 5.3663, 6.2796, 19.8953, -0.005534, 82.36, -52.231, -71.050, None, 13.403),
    (149, "SO2", "Dimethyl sulfone(1)", 7.0778, 7.0976, 17.2586, -0.000784, 89.95, -257.608, -305.498, None, 17.748),
    (150, "SO3 (sulfite)", "Dimethyl sulfite(1)", None, 3.9199, 8.6910, 0.004240, 115.80, None, None, None, None),
    (151, "SO3 (sulfonate)", "Dimethyl sulfonate(1)", 5.8426, 6.7785, None, None, None, None, None, None, None),
    (152, "SO4 (sulfate)", "Dimethyl sulfate(1)", 3.6976, 5.5627, 18.9366, -0.027208, 144.58, -519.853, -621.412, None, None),
    (153, "aC-SO", "Phenyl methyl sulfoxide(1)", 3.9911, 6.1185, None, None, None, None, None, None, None),
    (154, "aC-SO2", "Diphenyl sulfone(1)", 5.2948, 8.4333, None, None, 135.47, -314.643, -370.493, None, 3.281),
    (155, "PH (phosphine)", "Dimethylphosphine(1)", None, 2.0536, None, None, None, None, None, None, None),
    (156, "P (phosphine)", "Trimethylphosphine(1)", None, 1.0984, None, None, None, None, None, None, None),
    (157, "PO3 (phosphite)", "Triethylphosphite(1)", 1.0306, 2.7900, None, None, None, None, None, None, None),
    (158, "PHO3 (phosphonate)", "Dimethylphosphonate(1)", None, 5.6433, None, None, None, None, None, None, None),
    (159, "PO3 (phosphonate)", "Trimethylphosphonate(1)", None, 4.5468, None, None, None, None, None, None, None),
    (160, "PHO4 (phosphate)", "Diethylphosphate(1)", 2.7461, 5.1567, None, None, None, None, None, None, None),
    (161, "PO4 (phosphate)", "Trimethylphosphate(1)", 2.0330, 3.7657, 16.9914, -0.029036, 85.59, None, -1060.325, None, None),
    (162, "aC-PO4", "Triphenylphosphate(1)", -1.7840, 2.3522, None, None, None, None, -1005.161, None, 4.256),
    (163, "aC-P", "Triphenylphosphine(1)", 0.2337, 2.9272, 38.6148, -0.126108, -142.79, None, 72.339, None, -5.654),
    (164, "CO3 (carbonate)", "Diethylcarbonate(1)", 3.6593, 2.8847, 6.6804, 0.007235, 93.56, -447.186, -516.282, 21.613, 8.363),
    (165, "C2H3O", "Ethyl oxirane(1)", 1.3135, 2.8451, 6.6418, 0.021238, 125.43, 11.149, -52.241, None, None),
    (166, "C2H2O", "2,2-Dimethyl oxirane(1)", None, 2.6124, 6.0159, 0.010678, 194.36, 1.890, -51.390, None, None),
    (167, "C2O", "Trimethyl oxirane(1)", None, 2.2036, None, None, None, None, None, None, None),
    (168, "CH2 (cyclic)", "Cyclopentane(5)", 0.5699, 0.8234, 1.8815, 0.009884, 49.24, 13.287, -18.575, 3.341, 1.069),
    (169, "CH (cyclic)", "Methylcyclopentane(1)", 0.0335, 0.5946, 1.1020, 0.007596, 44.95, 6.107, -12.464, 6.416, 2.511),
    (170, "C (cyclic)", "1,1-Dimethylcyclohexane(1)", 0.1695, 0.0386, -0.2399, 0.003268, 33.32, -0.193, -2.098, 7.017, -0.921),
    (171, "CH=CH (cyclic)", "Cyclobutene(1)", 1.1936, 1.5985, 3.6426, 0.013815, 83.91, 86.493, 59.841, 7.767, 1.185),
    (172, "CH=C (cyclic)", "1-Methylcyclopentene(1)", 0.4344, 1.2529, 3.5475, 0.010576, 70.98, 67.056, 64.295, 7.171, 2.559),
    (173, "C=C (cyclic)", "1,2-Dimethylcyclopentene(1)", 0.3048, 1.1975, None, None, None, None, None, None, None),
    (174, "CH2=C (cyclic)", "Methylene cyclohexane(1)", 0.2220, 1.5109, 4.4913, 0.019101, 83.96, None, None, None, 5.351),
    (175, "NH (cyclic)", "Cyclopentimine(1)", 3.4814, 2.1634, 5.9726, -0.003678, 51.80, 72.540, 23.138, 13.700, 8.655),
    (176, "N (cyclic)", "N-methylpyrrolidine(1)", 0.6040, 1.6541, 4.3905, -0.001179, 31.41, 83.779, 65.622, None, 0.269),
    (177, "CH=N (cyclic)", "Imidazole(1)", 5.5779, 6.5230, None, None, None, None, None, None, None),
    (178, "C=N (cyclic)", "2-Methyl-1H-imidazole(1)", 6.6382, 6.6710, None, None, None, None, None, None, None),
    (179, "O (cyclic)", "Tetrahydropyran(1)", 1.3828, 1.0245, 2.7409, -0.000387, 17.69, -114.062, -137.353, 6.877, 3.806),
    (180, "CO (cyclic)", "Cyclobutanone(1)", 3.2119, 2.8793, 12.6396, -0.000207, 57.38, -156.672, -180.166, 17.124, 6.137),
    (181, "S (cyclic)", "2-Methyl-thiophene(1)", 1.6023, 2.3256, 5.5523, 0.001540, 45.45, 12.020, 15.453, 12.262, 5.170),
    (182, "SO2 (cyclic)", "Cyclobutadiene sulfone(1)", 6.1006, None, 24.3995, 0.002487, 96.66, -241.601, -283.839, None, 9.934),
]

#: id, group symbol, worked example, then the nine Table 7 columns.
SECOND_ORDER = [
    (1, "(CH3)2CH", "2-Methylpentane(1)", 0.1175, -0.0035, -0.0471, 0.000473, 1.71, -0.418, -0.419, -0.399, 0.396),
    (2, "(CH3)3C", "2,2,4,4-Tetramethylpentane(2)", -0.1214, 0.0072, -0.1778, 0.000340, 3.14, -2.776, -1.967, -0.417, 0.554),
    (3, "CH(CH3)CH(CH3)", "2,3,4-Trimethylpentane(2)", 0.2390, 0.3160, 0.5602, -0.003207, -3.75, 6.996, 6.065, 0.532, -1.766),
    (4, "CH(CH3)C(CH3)2", "2,2,3,4-Pentamethylpentane(2)", -0.3276, 0.3976, 0.8994, -0.008733, -10.06, 8.938, 8.078, 0.623, 0.351),
    (5, "C(CH3)2C(CH3)2", "2,2,3,3,4,4-Hexamethylpentane(2)", 3.3297, 0.4487, 1.5535, -0.016852, -8.70, 10.735, 10.535, 5.086, -1.089),
    (6, "CHn=CHm-CHp=CHk (k,m,n,p in 0..2)", "1,3-Butadiene(1)", 0.7451, 0.1097, 0.4214, 0.000792, -7.88, -6.562, -11.786, 1.632, 1.408),
    (7, "CH3-CHm=CHn (m,n in 0..2)", "2-Methyl-2-butene(3)", 0.0524, 0.0369, -0.0172, -0.000101, 0.50, -0.120, -0.048, 0.064, 0.070),
    (8, "CH2-CHm=CHn (m,n in 0..2)", "1,4-Pentadiene(2)", -0.1077, -0.0537, 0.0262, 0.000815, 0.14, 1.006, 1.449, -0.060, -0.632),
    (9, "CHp-CHm=CHn (m,n in 0..2; p in 0..1)", "3-Methyl-1-butene(1)", -0.2485, -0.0093, -0.1526, -0.000163, -2.67, 3.857, 3.964, 0.004, -0.368),
    (10, "CHCHO or CCHO", "2-Methylbutyraldehyde(1)", 0.5715, -0.1286, -1.0434, 0.005789, 10.36, -0.525, 1.514, -0.550, -0.369),
    (11, "CH3COCH2", "2-Pentanone(1)", -0.0968, -0.0215, -0.0338, -0.000111, -4.08, -1.543, 0.033, -0.403, 0.105),
    (12, "CH3COCH or CH3COC", "3-Methyl-2-pentanone(1)", -0.6024, -0.0803, -0.3658, -0.001892, 3.02, 2.202, 4.994, 0.723, 1.005),
    (13, "CHCOOH or CCOOH", "2-Methyl butanoic acid(1)", -3.1734, -0.3203, -4.7275, 0.006916, 10.56, 3.920, 1.121, 7.422, 5.475),
    (14, "CH3COOCH or CH3COOC", "Isopropyl acetate(1)", 0.2114, -0.2066, -0.5537, -0.000569, 4.28, -11.779, -12.295, -1.871, 1.208),
    (15, "CO-O-CO", "Propanoic anhydride(1)", -1.2441, -0.0500, -0.3576, 0.001812, 2.98, -16.075, -14.140, None, -2.666),
    (16, "CHOH", "2-Butanol(1)", -0.3489, -0.2825, -0.6768, 0.000246, -3.04, -5.614, -4.422, -0.206, -0.599),
    (17, "COH", "2-Methyl-2-butanol(1)", 0.3695, -0.5325, -1.5224, 0.003224, 13.98, -25.382, -25.929, -1.579, -0.459),
    (18, "CH3COCHnOH", "3-Hydroxy-2-butanone(1)", 0.9886, -0.2987, -0.3940, -0.002912, 5.17, 6.621, 8.244, None, None),
    (19, "NCCHOH or NCCOH", "2-Hydroxypropionitrile(1)", -1.1810, 0.2981, 0.3414, 0.000516, 0.68, 4.833, 0.000, None, -0.149),
    (20, "OH-CHn-COO (n in 0..2)", "Ethyl lactate(1)", -0.1526, -0.2310, None, None, None, None, None, None, None),
    (21, "CHm(OH)CHn(OH) (m,n in 0..2)", "Ethylene glycol(1)", -0.0414, 0.8854, 1.9395, -0.004712, 7.54, -1.051, -0.592, -6.611, -0.306),
    (22, "CHm(OH)CHn(-) (m,n,p in 0..2)", "2-Amino-1-butanol(1)", -0.5941, 0.5082, 1.2342, 0.002581, 5.58, -1.506, -0.959, None, -0.041),
    (23, "CHm(NH2)CHn(NH2) (m,n in 0..2)", "Ethylenediamine(1)", 0.3258, -0.0064, -3.3555, 0.000726, 20.82, 0.344, -1.443, 2.384, -1.575),
    (24, "CHm(NH)CHn(NH2) (m,n in 1..2)", "Diethylenetriamine(1)", -1.8403, 0.2318, -1.1598, 0.000157, -26.31, 3.848, 3.608, None, None),
    (25, "H2NCOCHnCHmCONH2 (m,n in 0..2)", "Butanediamide(1)", 11.5351, None, None, None, None, None, None, None, None),
    (26, "CHm(NHn)-COOH (m,n in 0..2)", "L-Alanine(1)", 12.3481, None, 62.4740, -0.002696, 17.78, 3.145, 6.598, None, 7.032),
    (27, "HOOC-CHn-COOH (n in 1..2)", "Malonic acid(1)", 0.9327, -0.1222, 1.9595, -0.001479, 12.46, -5.217, -6.058, None, 4.264),
    (28, "HOOC-CHn-CHm-COOH (n,m in 1..2)", "Succinic acid(1)", 7.5057, None, 0.7686, 0.000090, 15.17, -4.281, -6.929, None, 29.245),
    (29, "HO-CHn-COOH (n in 1..2)", "2-Hydroxyisobutyric acid(1)", -0.4531, -0.4625, None, None, None, None, None, None, None),
    (30, "NH2-CHn-CHm-COOH (n,m in 1..2)", "beta-Alanine(1)", 14.1593, None, None, None, None, None, None, None, None),
    (31, "CH3-O-CHn-COOH (n in 1..2)", "Methoxyacetic acid(1)", -2.3026, 0.9198, 0.4750, -0.001445, 7.91, -2.678, -1.727, None, None),
    (32, "HS-CH-COOH", "2-Mercaptopropionic acid(1)", -2.1535, None, None, None, None, None, None, None, None),
    (33, "HS-CHn-CHm-COOH (n,m in 1..2)", "beta-Thiolactic acid(1)", -2.7514, None, -0.2697, 0.000655, 20.43, -7.376, 7.292, None, -3.623),
    (34, "NC-CHn-CHm-CN (n,m in 1..2)", "1,2-Dicyanoethane(1)", 4.0747, 1.8957, 1.9699, 0.002330, 24.82, 18.974, 5.661, None, -8.038),
    (35, "OH-CHn-CHm-CN (n,m in 1..2)", "3-Hydroxypropanenitrile(1)", -0.9493, 1.3434, 0.2311, -0.001022, 14.50, 0.558, -3.906, None, -4.371),
    (36, "HS-CHn-CHm-SH (n,m in 1..2)", "1,2-Ethanedithiol(1)", 0.2232, 0.1815, 2.1272, 0.001321, -10.31, 6.728, 0.794, -0.683, -0.931),
    (37, "COO-CHn-CHm-OOC (n,m in 1..2)", "Ethylene glycol diacetate(1)", -0.5946, 0.3401, 1.5418, -0.003385, -2.33, 1.306, 4.025, 1.203, None),
    (38, "OOC-CHm-CHm-COO (n,m in 1..2)", "Dimethylsuccinate(1)", 2.5962, 0.5794, None, None, None, None, None, None, 2.303),
    (39, "NC-CHn-COO (n in 1..2)", "Methylcyanoacetate(1)", -0.2509, 1.2171, 2.7051, -0.001999, -0.73, None, None, None, 1.100),
    (40, "COCHnCOO (n in 1..2)", "Methylacetoacetate(1)", 0.6304, 0.2427, 0.7502, -0.000231, 1.69, 10.556, -7.261, None, None),
    (41, "CHm-O-CHn=CHp (m,n,p in 0..3)", "Ethyl vinyl ether(1)", -0.0811, 0.1399, 0.2900, -0.000432, -4.54, -10.098, -9.411, 0.372, 3.169),
    (42, "CHm=CHn-F (m,n in 0..2)", "1-Fluoro-1-propene(1)", -0.2568, 0.0591, None, None, 2.63, 14.470, 17.014, None, 2.823),
    (43, "CHm=CHn-Br (m,n in 0..2)", "1-Bromo-1-propene(1)", -0.4329, -0.3192, None, -0.010021, 2.63, 14.470, 17.014, None, 2.212),
    (44, "CHm=CHn-I (m,n in 0..2)", "1-Iodo-1-propene(1)", None, -0.3486, None, None, None, None, None, None, None),
    (45, "CHm=CHn-Cl (m,n in 0..2)", "1-Chloro-2-methylpropene(1)", 0.0446, -0.0268, -0.0188, 0.000152, 2.80, 8.207, 9.715, None, -0.480),
    (46, "CHm=CHn-CN (m,n in 0..2)", "Acrylonitrile(1)", 0.1027, 0.0653, -1.1249, 0.000893, 3.82, -8.304, -16.903, None, -0.405),
    (47, "CHn=CHm-COO-CHp (m,n,p in 0..3)", "Ethyl Acrylate(1)", 0.2117, -0.0430, -0.0880, 0.000044, 0.21, -12.085, -12.509, None, -0.014),
    (48, "CHm=CHn-CHO (m,n in 0..2)", "Propenaldehyde(1)", -0.7191, 0.1102, None, None, None, None, None, None, None),
    (49, "CHm=CHn-COOH (m,n in 0..2)", "Acrylic Acid(1)", 2.4103, 0.0667, -1.7762, -0.000763, 4.36, 10.194, 9.090, None, 1.291),
    (50, "aC-CHn-X (n in 1..2) X: Halogen", "Benzyl bromide(1)", 0.8092, 0.4537, 2.2630, 0.002464, -4.88, -8.081, -8.570, None, None),
    (51, "aC-CHn-NHm (n in 1..2; m in 0..2)", "Benzyl amine(1)", -1.0802, 0.2590, 1.4069, -0.000034, 2.50, -2.044, -3.447, 4.608, -0.639),
    (52, "aC-CHn-O- (n in 1..2)", "Benzyl ethyl ether(1)", 0.8607, -0.0425, 0.2698, -0.000417, -7.49, 6.043, 5.486, None, 0.969),
    (53, "aC-CHn-OH (n in 1..2)", "Benzyl alcohol(1)", 0.8981, 0.1005, -1.0107, 0.002944, -0.25, None, None, None, -2.754),
    (54, "aC-CHn-CN (n in 1..2)", "Benzyl cyanide(1)", 0.1088, 1.0587, 2.4950, -0.000796, -11.01, 25.157, 16.950, None, None),
    (55, "aC-CHn-CHO (n in 1..2)", "Phenyl acetaldehyde(1)", 1.9470, -0.0177, None, None, None, None, None, None, None),
    (56, "aC-CHn-SH (n in 1..2)", "Phenyl methanethiol(1)", 1.2057, 0.1702, 0.8705, 0.000183, 2.00, 16.725, 7.568, None, 0.890),
    (57, "aC-CHn-COOH (n in 1..2)", "Phenyl acetic acid(1)", 0.3666, 0.1584, None, None, None, None, None, None, -4.086),
    (58, "aC-CHn-CO- (n in 1..2)", "Phenyl acetone(1)", -0.2363, 0.3094, None, None, None, None, None, None, None),
    (59, "aC-CHn-S- (n in 1..2)", "Benzyl methyl sulfide(1)", 0.4506, 0.1030, None, None, None, None, None, None, None),
    (60, "aC-CHn-OOC-H (n in 1..2)", "Benzyl formate(1)", None, 0.2238, 1.7860, 0.004195, -3.40, 3.020, 4.145, None, None),
    (61, "aC-CHm-NO2 (n in 1..2)", "Phenyl nitromethane(1)", None, 0.5390, None, None, None, None, None, None, None),
    (62, "aC-CHn-CONH2 (n in 1..2)", "Phenyl ethanamide(1)", 2.2421, -0.2197, None, None, None, None, None, None, None),
    (63, "aC-CHn-OOC (n in 1..2)", "Benzyl acetate(1)", -0.6997, 0.0886, 1.1629, -0.000384, -7.02, 1.556, 4.066, None, None),
    (64, "aC-CHn-COO (n in 1..2)", "Methyl phenyl acetate(1)", -0.2636, 0.0352, None, None, None, None, None, None, None),
    (65, "aC-SO2-OH", "Benzenesulfonic acid(1)", -1.1057, None, None, None, None, None, None, None, None),
    (66, "aC-CH(CH3)2", "Cumene(1)", 0.0642, 0.0196, 0.1565, -0.001446, -2.04, 1.238, -0.751, 1.030, -0.270),
    (67, "aC-C(CH3)3", "tert-Butylbenzene(1)", 0.0790, 0.0494, 0.8016, -0.006495, -5.70, 0.354, -0.192, None, -0.878),
    (68, "aC-CF3", "Perfluorotoluene(1)", -10.8058, -1.5974, None, None, None, None, None, None, None),
    (69, "(CHn=C)(cyclic)-CHO (n in 0..2)", "Furfural(1)", -1.0516, 0.4267, 2.4070, -0.002650, 0.39, -6.438, -12.517, None, -1.670),
    (70, "(CHn=C)cyc-COO-CHm (n,m in 0..3)", "Methyl furanyrate(1)", -6.9427, 0.0879, None, None, None, None, None, None, None),
    (71, "(CHn=C)cyc-CO- (n in 0..2)", "2-Acetylfuran(1)", 0.6572, 0.6115, None, None, None, None, None, None, None),
    (72, "(CHn=C)cyc-CH3 (n in 0..2)", "1,2-Dimethylcyclopentene(2)", 0.0416, 0.0173, -0.2509, -0.000624, 0.03, 28.972, 24.560, None, 2.235),
    (73, "(CHn=C)cyc-CH2 (n in 0..2)", "2-Ethylfuran(1)", -0.3151, -0.0504, -1.1019, 0.003921, -4.43, -22.533, -12.044, None, 0.961),
    (74, "(CHn=C)cyc-CN (n in 0..2)", "3-Cyanofuran(1)", 1.5819, -0.2474, None, None, None, None, None, None, None),
    (75, "(CHn=C)cyc-Cl (n in 0..2)", "2-Chlorofuran(1)", -0.8604, -0.5736, None, None, None, None, None, None, None),
    (76, "CHcyc-CH3", "Methylcyclopentane(1)", -0.1326, -0.1210, -0.1233, 0.000779, 2.79, 4.178, 4.452, 0.096, 0.033),
    (77, "CHcyc-CH2", "Ethylcyclohexane(1)", -0.4669, -0.0148, 0.3816, 0.001694, -2.95, 5.332, 4.428, -0.428, -1.137),
    (78, "CHcyc-CH", "Isopropylcyclopentane(1)", -0.3548, 0.1395, 0.1093, 0.000124, 6.19, 6.084, -4.128, 0.153, 2.421),
    (79, "CHcyc-C", "tert-Butylcyclohexane(1)", -0.1727, 0.1829, None, None, None, None, None, None, None),
    (80, "CHcyc-CH=CHn (n in 1..2)", "Vinylcyclopentane(1)", 0.6817, -0.1192, None, None, None, None, None, None, None),
    (81, "CHcyc-C=CHn (n in 1..2)", "Limonene(1)", -1.0631, -0.0455, -0.2832, 0.002114, -16.97, 6.768, 10.390, None, None),
    (82, "CHcyc-Cl", "Chloro cyclopentane(1)", 0.5124, 0.2667, None, None, None, None, None, None, None),
    (83, "CHcyc-F", "Fluoro cyclohexane(1)", 2.8497, -0.1899, None, None, None, None, None, None, None),
    (84, "CHcyc-OH", "Cyclohexanol(1)", 1.3691, -0.3179, 0.8973, 0.004640, -7.73, -3.024, -8.050, 2.134, None),
    (85, "CHcyc-NH2", "Cyclohexylamine(1)", 1.5069, -0.3576, -0.9610, 0.000039, -2.50, 2.046, 3.446, -4.607, 0.328),
    (86, "CHcyc-NH-CHn (n in 0..3)", "N-methylcyclohexylamine(1)", 0.0370, -0.7458, -2.0833, -0.014535, -51.50, -11.965, 14.531, None, 0.402),
    (87, "CHcyc-N-CHn (n in 0..3)", "N,N-dimethylcyclohexanamine(1)", None, 0.1218, None, None, None, None, None, None, None),
    (88, "CHcyc-SH", "Cyclohexanethiol(1)", -0.3312, -0.0569, -0.6447, -0.000199, -2.00, -16.723, -7.569, None, -0.878),
    (89, "CHcyc-CN", "Cyanocyclopentane(1)", None, 0.4649, None, None, None, None, None, None, None),
    (90, "CHcyc-COOH", "Cyclopropanecarboxylic acid(1)", -2.0822, 0.1506, None, None, None, None, None, None, None),
    (91, "CHcyc-CO", "Methyl cyclohexyl ketone(1)", 0.7743, 0.1300, None, None, None, None, None, -0.616, None),
    (92, "CHcyc-NO2", "Nitrocyclohexane(1)", -0.8578, 0.6540, None, None, None, None, None, None, None),
    (93, "CHcyc-S-", "Methyl cyclopentyl sulfide(1)", -0.8638, 0.0043, None, None, None, None, None, None, None),
    (94, "CHcyc-CHO", "Cyclohexanecarboxaldehyde(1)", 0.5076, -0.2692, None, None, None, None, None, None, None),
    (95, "CHcyc-O-", "Methoxycyclohexane(1)", -0.3978, -0.2787, None, None, None, None, None, None, None),
    (96, "CHcyc-OOCH", "Cyclohexyl ester formic acid(1)", None, -0.2107, None, None, None, None, None, None, None),
    (97, "CHcyc-COO", "Ethyl cyclobutyrate(1)", None, 0.0926, None, None, None, None, None, None, None),
    (98, "CHcyc-OOC", "Cyclohexyl acetate(1)", -0.4666, -0.4495, -0.3450, -0.000692, -12.03, 4.358, -15.751, None, None),
    (99, "Ccyc-CH3", "1,1-Dimethyl-cyclohexane(2)", 0.1737, 0.0722, 0.1607, 0.001235, 1.95, 0.107, 0.238, 0.808, -1.237),
    (100, "Ccyc-CH2", "1-Ethyl-1-methyl-cyclopentane(1)", -1.9233, 0.0319, 0.1090, -0.000610, -5.17, 18.755, 21.498, 0.585, None),
    (101, "Ccyc-OH", "1-Methylcyclopentanol(1)", 0.7334, -0.6775, -2.1303, -0.004683, -14.40, -18.970, -21.975, None, 0.235),
    (102, ">Ncyc-CH3", "N-methyl-2-pyrrolidone(1)", -0.0383, 0.0604, -0.0003, 0.000058, None, None, None, None, None),
    (103, ">Ncyc-CH2", "N-ethylpyrrole(1)", 1.0497, -0.3080, None, None, None, None, None, None, None),
    (104, "AROMRINGs1s2", "2-Methyl-phenol(1), 2-Et-toluene(1)", -0.6388, -0.1590, -0.3161, 0.000522, 2.86, 1.577, 1.486, 1.164, -1.059),
    (105, "AROMRINGs1s3", "3-Methyl-phenol(1), 3-Et-toluene(1)", -0.6218, 0.0217, -0.0693, 0.001790, 6.54, -1.037, 0.294, -1.910, -1.059),
    (106, "AROMRINGs1s4", "4-Methyl-phenol(1), 4-Et-toluene(1)", 0.9840, 0.1007, 0.0803, 0.000467, 3.70, -0.709, 0.384, 0.331, 1.244),
    (107, "AROMRINGs1s2s3", "1,2,3-Trimethylbenzene(1)", -0.2762, -0.1647, 1.0088, -0.005598, -9.58, 7.731, 5.743, 1.433, 0.473),
    (108, "AROMRINGs1s2s4", "1,2,4-Trihydroxybenzene(1)", -0.3689, -0.1387, 0.0908, 0.000255, -2.05, -2.767, -0.449, 0.313, -0.302),
    (109, "AROMRINGs1s3s5", "3,5-Diethyltoluene(1)", -0.3841, -0.1314, -0.6412, 0.004090, -7.67, -2.148, -7.538, -0.117, -2.530),
    (110, "AROMRINGs1s2s3s4", "3-Ethyl-1,2,4-trimethylbenzene(1)", 1.7722, 0.2745, 2.1116, -0.007612, -7.04, 14.226, 12.710, None, -1.736),
    (111, "AROMRINGs1s2s3s5", "1,2,3,5-Tetramethylbenzene(1)", 0.4553, 0.1645, 0.9353, -0.001811, -0.04, 4.926, 5.220, None, -2.246),
    (112, "AROMRINGs1s2s4s5", "1,2,4,5-Tetramethylbenzene(1)", 2.0561, 0.0754, 0.6241, -0.000500, -0.04, -0.474, -1.340, None, 8.034),
    (113, "PYRIDINEs2", "2-Methylpyridine(1)", -0.5769, -0.1196, -1.0256, 0.007006, 8.68, -9.713, -9.644, -1.683, -0.786),
    (114, "PYRIDINEs3", "3-Methylpyridine(1)", -0.2556, 0.0494, 0.5784, 0.007006, 8.68, -2.523, -2.446, 0.277, 3.671),
    (115, "PYRIDINEs4", "4-Methylpyridine(1)", 1.6282, 0.1344, 0.6595, 0.001283, 14.28, -4.703, -6.466, 0.397, 5.975),
    (116, "PYRIDINEs2s3", "2,3-Dimethylpyridine(1)", -0.1341, 0.0032, None, None, None, None, None, -0.939, None),
    (117, "PYRIDINEs2s4", "2,4-Dimethylpyridine(1)", -1.6848, -0.0817, None, None, None, None, None, -1.269, None),
    (118, "PYRIDINEs2s5", "2,5-Dimethylpyridine(1)", -0.9802, -0.1564, None, None, None, None, None, -1.719, None),
    (119, "PYRIDINEs2s6", "2,6-Dimethylpyridine(1)", 0.3018, -0.5176, -2.2773, 0.008029, -50.26, -16.570, -17.778, -3.419, -1.487),
    (120, "PYRIDINEs3s4", "3,4-Dimethylpyridine(1)", 0.1018, 0.5477, None, None, None, None, None, 1.742, None),
    (121, "PYRIDINEs3s5", "3,5-Dimethylpyridine(1)", 0.2811, 0.3533, None, None, None, None, None, 0.572, None),
    (122, "PYRIDINEs2s3s6", "2,3,6-Trimethylpyridine(1)", -0.3189, -0.3888, None, None, None, None, None, -2.744, None),
]

#: Universal constants (Table 2) and the left-hand-side function each property uses (Table 1),
#: both from the paper's TEXT layer (not the image-only group tables, so these did not need
#: rendering). The right-hand side is always the group summation (first + second + third order);
#: X0/X1/X2 name the SAME constants Table 1 calls Xn generically.
#:
#:     Tm:   exp(Tm / Tm0) = sum        -> Tm = Tm0 * ln(sum)
#:     Tb:   exp(Tb / Tb0) = sum        -> Tb = Tb0 * ln(sum)
#:     Tc:   exp(Tc / Tc0) = sum        -> Tc = Tc0 * ln(sum)
#:     Pc:   (Pc - Pc1)**-0.5 - Pc2 = sum -> Pc = Pc1 + (sum + Pc2)**-2
#:     Vc:   Vc - Vc0 = sum             -> Vc = Vc0 + sum
#:     Gf:   Gf - Gf0 = sum             -> Gf = Gf0 + sum
#:     Hf:   Hf - Hf0 = sum             -> Hf = Hf0 + sum
#:     Hv:   Hv - Hv0 = sum             -> Hv = Hv0 + sum
#:     Hfus: Hfus - Hfus0 = sum         -> Hfus = Hfus0 + sum
UNIVERSAL_CONSTANTS = {
    "Tm0": 147.450,
    "Tb0": 222.543,
    "Tc0": 231.239,
    "Pc1": 5.9827,
    "Pc2": 0.108998,
    "Vc0": 7.95,
    "Gf0": -34.967,
    "Hf0": 5.549,
    "Hv0": 11.733,
    "Hfus0": -2.806,
}

#: column index (into a FIRST_ORDER/SECOND_ORDER row tuple, past id/symbol/example) for each
#: property, in the paper's own left-to-right order.
_PROPERTIES = ("Tm", "Tb", "Tc", "Pc", "Vc", "Gf", "Hf", "Hv", "Hfus")


class UncoveredGroup(KeyError):
    """A requested group symbol is not one of the paper's own rows -- never silently 0."""


class NoContribution(ValueError):
    """The paper printed '*****' for this (group, property): unknown, never 0."""


def _row_by_symbol(rows, symbol):
    matches = [r for r in rows if r[1] == symbol]
    if len(matches) != 1:
        raise UncoveredGroup(f"{symbol!r} matched {len(matches)} rows in this table, not 1")
    return matches[0]


def group_sum(prop: str, assignment: dict[str, int], *, second_order: dict[str, int] | None = None) -> float:
    """The raw group summation (right-hand side of the paper's Eq. (1)) for `prop`.

    `assignment` is {first-order group symbol: occurrence count}, covering every atom in the
    molecule exactly once (this function does not check that -- the caller's decomposition is the
    claim being made, same as the paper's own worked examples in Appendix B). `second_order` is the
    same shape against Table 7, for molecules where a second-order group applies; omit it to report
    the first-order approximation only, exactly as the paper reports it before showing a refinement.

    Raises `NoContribution` for a (group, prop) the paper starred out -- an unknown contribution,
    never a silent 0 (mirrors `tools/validation_rows.py`'s `UnknownFitPopulation` rule).
    """
    col = 3 + _PROPERTIES.index(prop)
    total = 0.0
    for symbol, count in assignment.items():
        row = _row_by_symbol(FIRST_ORDER, symbol)
        value = row[col]
        if value is None:
            raise NoContribution(f"group {symbol!r} has no {prop} contribution in Table 6 ('*****')")
        total += count * value
    for symbol, count in (second_order or {}).items():
        row = _row_by_symbol(SECOND_ORDER, symbol)
        value = row[col]
        if value is None:
            raise NoContribution(f"group {symbol!r} has no {prop} contribution in Table 7 ('*****')")
        total += count * value
    return total


def estimate(prop: str, assignment: dict[str, int], *, second_order: dict[str, int] | None = None) -> float:
    """The property value itself, inverting Table 1's f(X) for `prop` from `group_sum`."""
    total = group_sum(prop, assignment, second_order=second_order)
    c = UNIVERSAL_CONSTANTS
    if prop == "Tm":
        return c["Tm0"] * math.log(total)
    if prop == "Tb":
        return c["Tb0"] * math.log(total)
    if prop == "Tc":
        return c["Tc0"] * math.log(total)
    if prop == "Pc":
        return c["Pc1"] + (total + c["Pc2"]) ** -2
    if prop == "Vc":
        return c["Vc0"] + total
    if prop == "Gf":
        return c["Gf0"] + total
    if prop == "Hf":
        return c["Hf0"] + total
    if prop == "Hv":
        return c["Hv0"] + total
    if prop == "Hfus":
        return c["Hfus0"] + total
    raise ValueError(f"not one of the paper's nine properties: {prop!r}")
