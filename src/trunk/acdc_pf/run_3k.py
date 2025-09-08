import VeraGridEngine as vg
from VeraGridEngine.Simulations.PowerFlow.power_flow_options import PowerFlowOptions
from VeraGridEngine.enumerations import SolverType, ConverterControlType

# Grid instantiation
grid = vg.open_file("grids/case5_3_he.veragrid")

options = PowerFlowOptions(SolverType.NR,
                           verbose=1,
                           control_q=False,
                           retry_with_other_methods=False,
                           control_taps_phase=True,
                           control_taps_modules=True,
                           max_iter=80,
                           tolerance=1e-8, )

grid.vsc_devices[1].control1 = ConverterControlType.Va_ac
grid.vsc_devices[1].control1_val = 0.0
grid.vsc_devices[1].control2_val = -40

for j in range(len(grid.vsc_devices)):
    print(grid.vsc_devices[j].name)
    print("control1:", grid.vsc_devices[j].control1)
    print("control1val:", grid.vsc_devices[j].control1_val)
    print("control2:", grid.vsc_devices[j].control2)
    print("control2val:", grid.vsc_devices[j].control2_val)

res = vg.power_flow(grid, options=options)
# print(res.converged)

# Set control parameters for VSC devices
# grid.vsc_devices[0].control1 = ConverterControlType.Pac
# grid.vsc_devices[1].control1 = ConverterControlType.Pac
# grid.vsc_devices[2].control1 = ConverterControlType.Pac
# grid.vsc_devices[3].control1 = ConverterControlType.Vm_dc
# grid.vsc_devices[3].control1_val = 1.0
# grid.vsc_devices[4].control1 = ConverterControlType.Pac
# grid.vsc_devices[5].control1 = ConverterControlType.Pac
# grid.vsc_devices[6].control1 = ConverterControlType.Pac
# grid.vsc_devices[7].control1 = ConverterControlType.Pac
# grid.vsc_devices[8].control1 = ConverterControlType.Pac
# grid.vsc_devices[9].control1 = ConverterControlType.Pac


# res = vg.power_flow(grid)
# print(res.get_bus_df())
# print(res.get_branch_df())