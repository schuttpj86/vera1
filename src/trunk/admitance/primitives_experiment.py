import os
import numpy as np
import VeraGridEngine as vg

fname = os.path.join("..", "..", "..", "Grids_and_profiles", "grids", "Lynn 5 Bus (pq).gridcal")

grid = vg.open_file(fname)

pf_res = vg.power_flow(grid)

nc = vg.compile_numerical_circuit_at(grid)
adm = nc.get_admittance_matrices()

F = nc.passive_branch_data.F
T = nc.passive_branch_data.T
Vf = pf_res.voltage[F]
Vt = pf_res.voltage[T]

# Sbus = V · conj(Y x V)

Sf_alt = (Vf * np.conj(Vf * adm.yff) + Vf * np.conj(Vt * adm.yft)) * nc.Sbase
St_alt = (Vt * np.conj(Vt * adm.ytt) + Vt * np.conj(Vf * adm.ytf)) * nc.Sbase

S_alt = np.zeros(nc.nbus, dtype=complex)
for k in range(nc.nbr):
    # bothe are + because Sf and St already have the correct sign
    S_alt[F[k]] += Sf_alt[k]
    S_alt[T[k]] += St_alt[k]

print(pf_res.Sf - Sf_alt)
print(pf_res.St - St_alt)
print(pf_res.Sbus - S_alt)
print()
