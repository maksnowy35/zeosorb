R_UNIV = 8315.0      # J/(kmol*K) - value used in the thesis
K_B = 1.38e-23       # J/K
N_A = 6.022e23       # 1/mol

# process conditions assumed in the thesis
T_PROCESS = 373.15   # K  (100 C)
P_PROCESS = 0.8e5    # Pa (pressure averaged over filling)

# column used in the thesis
BED_HEIGHT = 2.89        # m
COLUMN_DIAMETER = 0.5    # m  (A = 0.196 m2)

# Sherwood correlation Sh = C Re^A Sc^B, "ziarna", Re < 30 (Paderewski, Tab. 3 in thesis)
SH_C, SH_A, SH_B = 0.395, 0.54, 0.33
