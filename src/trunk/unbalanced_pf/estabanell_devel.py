import VeraGridEngine.api as gce
from VeraGridEngine.enumerations import SolverType, ShuntConnectionType
import pandas as pd
import numpy as np

logger = gce.Logger()
grid = gce.MultiCircuit()
df_buses_lines = pd.read_csv('estabanell_grid/linies_bt_eRoots.csv', sep=";")

# Buses que no quieres
buses_to_delete = [
    57573, 57552, 117181, 117182, 57744, 58152, 58173, 58025, 58026, 57723,
    58020, 58039, 58030, 58029, 58028, 58043, 58036, 58027, 58037, 58046
]
buses_to_delete_str = [str(b) for b in buses_to_delete]

df_buses_lines = df_buses_lines[
    ~df_buses_lines["node_start"].astype(str).isin(buses_to_delete_str) &
    ~df_buses_lines["node_end"].astype(str).isin(buses_to_delete_str)
]

# -------------------------------------------------------------------------------------
#   Simplification 58022 -> 58023
# -------------------------------------------------------------------------------------
path = ["58022","58021","58024","58031","58032","58033","58034","58023"]

mask = df_buses_lines.apply(
    lambda row: (str(row["node_start"]) in path and str(row["node_end"]) in path),
    axis=1
)
df_path = df_buses_lines[mask]

# sumar impedancias y longitud
R_eq = df_path["resistencia"].sum()
X_eq = df_path["reactancia"].sum()
L_eq = df_path["longitud_cad"].sum()
Imax_eq = df_path["intensitat_admisible"].min()

# eliminar esas líneas del DataFrame original
df_buses_lines = df_buses_lines.drop(df_path.index)

# añadir la nueva línea equivalente
df_buses_lines = pd.concat([
    df_buses_lines,
    pd.DataFrame([{
        "tram": "58022_58023",
        "num_linia": "Equivalent",
        "node_start": 58022,
        "node_end": 58023,
        "resistencia": R_eq,
        "reactancia": X_eq,
        "longitud_cad": L_eq,
        "intensitat_admisible": Imax_eq
    }])
], ignore_index=True)

# ---------------------------------------------------------------------------------------------------------------------
#   Buses
# ---------------------------------------------------------------------------------------------------------------------
buses = pd.unique(df_buses_lines[["node_start", "node_end"]].values.ravel())
bus_dict = dict()
for bus in buses:
    bus = gce.Bus(name=str(bus), Vnom=0.4)
    if bus.name == str(58022):
        bus.is_slack = True
        gen = gce.Generator()
        grid.add_generator(bus=bus, api_obj=gen)
    grid.add_bus(obj=bus)
    bus_dict[int(float(bus.name))] = bus

# ---------------------------------------------------------------------------------------------------------------------
#   Lines
# ---------------------------------------------------------------------------------------------------------------------
rho_Cu = 1.72
rho_Al = 2.82
Al_to_Cu = rho_Cu / rho_Al
last_R, last_X = None, None
for _, row in df_buses_lines.iterrows():

    if row['reactancia'] == 0:
        # usa los valores de la fila anterior guardados
        R_val = last_R * Al_to_Cu
        X_val = last_X
    else:
        # usa los valores de la fila actual
        R_val = row['resistencia']
        X_val = row['reactancia']
        # actualiza memoria
        last_R, last_X = R_val, X_val

    line_type = gce.SequenceLineType(
        name=row['tram'],
        Imax=row['intensitat_admisible'] / 1e3,
        Vnom=400,
        R=R_val,
        X=X_val,
        R0=3 * R_val,
        X0=3 * X_val
    )
    grid.add_sequence_line(line_type)

    line = gce.Line(
        bus_from=bus_dict[row['node_start']],
        bus_to=bus_dict[row['node_end']],
        name=row['tram'],
        code=row['num_linia'],
        rate=row['intensitat_admisible'] * 400 / 1e6,
        length=row['longitud_cad'] / 1000
    )
    line.apply_template(line_type, grid.Sbase, grid.fBase, logger)
    grid.add_line(obj=line)

# ---------------------------------------------------------------------------------------------------------------------
#   Loads
# ---------------------------------------------------------------------------------------------------------------------
df_meters = pd.read_csv('estabanell_grid/cups_eRoots.csv', sep=";")
df_powers = pd.read_csv('estabanell_grid/Corbes_CUPS_CT-0975.csv', sep=";")

# For now, only the first measurement of each meter
df_first = df_powers.groupby("MeterID").first().reset_index()

S_sum = 0 + 0j
for _, row_meters in df_meters.iterrows():
    row_power = df_first[df_first["MeterID"] == row_meters["comptador"]]

    P = float(row_power["TotalActiveEnergyConsumed"].values[0]) - float(row_power["TotalActiveEnergyProduced"].values[0]) / 1000
    Q = float(row_power["TotalReactiveEnergyProduced"].values[0]) - float(row_power["TotalReactiveEnergyConsumed"].values[0]) / 1000

    S_sum = S_sum + (P + 1j * Q)

    if int(row_meters['tensio']) == 400:
        # Balanced
        load = gce.Load(
            name=row_meters['comptador'],
            P1=P / 3,
            Q1=Q / 3,
            P2=P / 3,
            Q2=Q / 3,
            P3=P / 3,
            Q3=Q / 3)

    elif int(row_meters['tensio']) == 230:
        # Unbalanced
        phase_probs = [1 / 3, 1 / 3, 1 / 3]
        phase = np.random.choice(["A", "B", "C"], p=phase_probs)

        if phase == "A":
            load = gce.Load(
                name=row_meters['comptador'],
                P1=P,
                Q1=Q)
        elif phase == "B":
            load = gce.Load(
                name=row_meters['comptador'],
                P2=P,
                Q2=Q)
        else:
            load = gce.Load(
                name=row_meters['comptador'],
                P3=P,
                Q3=Q)

    else:
        raise Exception("Incorrect load voltage!")

    load.conn = ShuntConnectionType.GroundedStar
    grid.add_load(bus=bus_dict[row_meters['node']], api_obj=load)

# ----------------------------------------------------------------------------------------------------------------------
# Run power flow
# ----------------------------------------------------------------------------------------------------------------------
res = gce.power_flow(grid=grid, options=gce.PowerFlowOptions(three_phase_unbalanced=True, solver_type=SolverType.NR))
print("\n", res.get_voltage_3ph_df())
print("\nConverged? ", res.converged)
print("\nIterations: ", res.iterations)

# ---------------------------------------------------------------------------------------------------------------------
#   Save Grid
# ---------------------------------------------------------------------------------------------------------------------
print()
gce.save_file(grid=grid, filename='estabanell_modified.veragrid')