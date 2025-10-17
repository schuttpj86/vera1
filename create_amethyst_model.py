"""
Create Amethyst BESS Model from DNV Report Data
================================================
This script builds a VeraGrid model of the Amethyst ESM based on the
technical specifications from the DNV report (25-0851 rev.0).

Since we don't have the original PowerFactory .dgs file, we'll recreate
the model using the documented parameters.

Reference: 25-0851_report.md
"""
import os
import sys
import numpy as np

# Add the src directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from VeraGridEngine.Devices.multi_circuit import MultiCircuit
from VeraGridEngine.Devices import *
from VeraGridEngine.Devices.Injections.external_grid import ExternalGrid
from VeraGridEngine.Simulations.PowerFlow.power_flow_driver import PowerFlowDriver, PowerFlowOptions
from VeraGridEngine.enumerations import SolverType, ExternalGridMode
from VeraGridEngine.IO.file_handler import FileSave


def create_amethyst_model():
    """
    Create the Amethyst ESM model based on DNV report specifications
    
    System Overview:
    - 45 MW / 90 MWh Battery Energy Storage System
    - Connection: 50 kV grid (Stedin DSO)
    - 12 converter units (3.75 MW each)
    - Main transformer: 50 MVA, 52/20 kV
    - 6 unit transformers: 8.78 MVA each, 20/0.69 kV (3-winding)
    - 2 auxiliary transformers: 1.25 MVA each, 20/0.4 kV
    """
    
    print("\n" + "="*60)
    print(" Creating Amethyst ESM Model from DNV Report Data")
    print("="*60 + "\n")
    
    # Create circuit
    circuit = MultiCircuit(name="Amethyst ESM", Sbase=100.0)  # 100 MVA base
    
    # =========================================================================
    # 1. Create Buses
    # =========================================================================
    print("Creating buses...")
    
    # External grid connection point (Stedin Main Station) - 50 kV
    # This will be the slack bus - TOP of the diagram
    bus_cp = Bus(name="Connection Point (Stedin)", Vnom=50.0, vmin=0.85, vmax=1.10, is_slack=True, xpos=0, ypos=0)
    circuit.add_bus(bus_cp)
    
    # Internal 50 kV bus after cable - Going DOWN with more space
    bus_50kv = Bus(name="50kV Internal", Vnom=50.0, vmin=0.85, vmax=1.10, xpos=0, ypos=300)
    circuit.add_bus(bus_50kv)
    
    # MV busbar - 20 kV - Further DOWN after main transformer
    bus_20kv = Bus(name="20kV Busbar", Vnom=20.0, vmin=0.85, vmax=1.10, xpos=0, ypos=600)
    circuit.add_bus(bus_20kv)
    
    # Distribution busbars for converters - Spread HORIZONTALLY at same level with large spacing
    # These form a horizontal busbar at y=900
    bus_rmu1 = Bus(name="RMU MV-CB1", Vnom=20.0, xpos=-1500, ypos=900)
    bus_rmu2 = Bus(name="RMU MV-CB2", Vnom=20.0, xpos=-900, ypos=900)
    bus_rmu3 = Bus(name="RMU MV-CB3", Vnom=20.0, xpos=-300, ypos=900)
    bus_rmu4 = Bus(name="RMU MV-CB4", Vnom=20.0, xpos=300, ypos=900)
    bus_rmu5 = Bus(name="RMU MV-CB5", Vnom=20.0, xpos=900, ypos=900)
    bus_rmu6 = Bus(name="RMU MV-CB6", Vnom=20.0, xpos=1500, ypos=900)
    
    circuit.add_bus(bus_rmu1)
    circuit.add_bus(bus_rmu2)
    circuit.add_bus(bus_rmu3)
    circuit.add_bus(bus_rmu4)
    circuit.add_bus(bus_rmu5)
    circuit.add_bus(bus_rmu6)
    
    # Converter LV buses (0.69 kV) - Further DOWN, paired under each RMU
    # Much larger spacing - 12 converters at bottom level
    converter_lv_buses = []
    # Each RMU has 2 converters, positioned vertically below it with good spacing
    x_positions = [-1600, -1400,  # Under RMU1
                   -1000, -800,   # Under RMU2
                   -400, -200,    # Under RMU3
                   200, 400,      # Under RMU4
                   800, 1000,     # Under RMU5
                   1400, 1600]    # Under RMU6
    
    for i in range(12):
        bus = Bus(name=f"Converter {i+1} LV", Vnom=0.69, xpos=x_positions[i], ypos=1200)
        circuit.add_bus(bus)
        converter_lv_buses.append(bus)
    
    # Auxiliary load buses - On the far right at MV level
    bus_aux1 = Bus(name="Auxiliary Load 1", Vnom=0.4, xpos=2000, ypos=600)
    bus_aux2 = Bus(name="Auxiliary Load 2", Vnom=0.4, xpos=2400, ypos=600)
    circuit.add_bus(bus_aux1)
    circuit.add_bus(bus_aux2)
    
    print(f"  Created {len(circuit.buses)} buses")
    
    # =========================================================================
    # 2. External Grid (Slack Generator)
    # =========================================================================
    print("Creating external grid...")
    
    # Add a slack generator at the connection point
    # Following the pattern from ieee9_Kriti.py and Lynn 5 bus example
    slack_gen = Generator(
        name="Stedin Grid",
        P=0.0,  # Will be determined by power flow
        vset=1.0,  # p.u. voltage setpoint (lowercase in constructor)
        Snom=10000.0,  # Large MVA rating
        Qmin=-9999,  # Unlimited reactive power
        Qmax=9999
    )
    circuit.add_generator(bus_cp, slack_gen)
    
    # =========================================================================
    # 3. Connection Cable (50 kV - Internal ESM Connection)
    # =========================================================================
    print("Creating connection cable...")
    
    # Note: The 900m cable to Stedin is NOT part of ESM per report
    # This is a short internal connection (~50-100m) within the ESM
    # Cable type: YMeKrvaslqwd Fca 36/50 kV (from DNV Appendix F)
    length_km = 0.05  # 50m internal connection (conservative estimate)
    r_50kv_per_km = 0.0622  # Ohm/km @ max continuous conductor temp (DNV Appendix F)
    x_50kv_per_km = 0.12    # Ohm/km (trefoil arrangement, DNV Appendix F)
    c_50kv_per_km = 0.28    # µF/km (nominal capacitance, DNV Appendix F)
    
    cable_50kv = Line(
        name="50kV Internal Connection Cable",
        bus_from=bus_cp,
        bus_to=bus_50kv,
        r=r_50kv_per_km * length_km,  # Ohm
        x=x_50kv_per_km * length_km,  # Ohm
        b=2 * np.pi * 50 * c_50kv_per_km * 1e-6 * length_km,  # S (capacitance)
        rate=500.0  # MVA (well above 50 MVA transformer rating)
    )
    circuit.add_line(cable_50kv)
    
    # =========================================================================
    # 4. Main Step-Up Transformer (52/20 kV, 50 MVA)
    # =========================================================================
    print("Creating main transformer...")
    
    # From Table 1-1 in report:
    # 50 MVA, 52/20 kV, Dyn5, 8% impedance, 17 taps (±8), 1.25% per tap
    transformer_main = Transformer2W(
        name="Main Transformer 52/20kV",
        bus_from=bus_50kv,
        bus_to=bus_20kv,
        HV=52.0,  # kV
        LV=20.0,  # kV
        nominal_power=50.0,  # MVA
        copper_losses=160.0,  # kW (from report Table 1-1)
        iron_losses=18.0,  # kW (from report Table 1-1)
        no_load_current=0.0,  # Not specified
        short_circuit_voltage=8.0,  # %
        rate=50.0,  # MVA rating
        tap_module=1.0,
        tap_phase=0.0,
        active=True
    )
    # CRITICAL: Calculate R, X, G, B from design parameters
    transformer_main.fill_design_properties(
        Pcu=160.0,  # kW
        Pfe=18.0,    # kW
        I0=0.0,     # %
        Vsc=8.0,    # %
        Sbase=100.0  # MVA system base
    )
    circuit.add_transformer2w(transformer_main)
    
    # =========================================================================
    # 5. MV Distribution Cables
    # =========================================================================
    print("Creating MV distribution cables...")
    
    # Cables from main busbar to RMU distribution points
    # YMeKrvaslqwd Fca 12/20 kV 1x630 Al + as50
    # From DNV Appendix E datasheet - updated values
    r_per_km = 0.06    # Ohm/km @ max continuous conductor temp (was 0.0469 @ 20°C)
    x_per_km = 0.106   # Ohm/km (trefoil arrangement, was 0.126)
    c_per_km = 0.43    # µF/km (nominal mutual capacitance, was 0.26)
    
    # Cable lengths from report diagrams (approximate)
    cables_mv = [
        (bus_20kv, bus_rmu1, 32, "Cable to RMU1"),
        (bus_20kv, bus_rmu2, 21, "Cable to RMU2"),
        (bus_rmu2, bus_rmu3, 26, "Cable to RMU3"),
        (bus_20kv, bus_rmu4, 23, "Cable to RMU4"),
        (bus_20kv, bus_rmu5, 27, "Cable to RMU5"),
        (bus_20kv, bus_rmu6, 28, "Cable to RMU6"),
    ]
    
    for bus_from, bus_to, length_m, name in cables_mv:
        length_km = length_m / 1000.0
        cable = Line(
            name=name,
            bus_from=bus_from,
            bus_to=bus_to,
            r=r_per_km * length_km,
            x=x_per_km * length_km,
            b=2 * np.pi * 50 * c_per_km * 1e-6 * length_km,  # S
            rate=30.0  # MVA (approximate for 630 mm² cable)
        )
        circuit.add_line(cable)
    
    # =========================================================================
    # 6. Unit Transformers (20/0.69 kV, 3-winding)
    # =========================================================================
    print("Creating unit transformers...")
    
    # From Table 1-2: 8.78/4.39/4.39 MVA, 20/0.69/0.69 kV
    # For simplification, using 2-winding transformers (2 per 3-winding unit)
    # This gives us 12 transformer connections for 12 converters
    
    rmu_buses = [bus_rmu1, bus_rmu1, bus_rmu2, bus_rmu2, 
                 bus_rmu3, bus_rmu3, bus_rmu4, bus_rmu4,
                 bus_rmu5, bus_rmu5, bus_rmu6, bus_rmu6]
    
    for i, (rmu_bus, conv_bus) in enumerate(zip(rmu_buses, converter_lv_buses)):
        # Each winding: 4.39 MVA, 7.5% impedance
        transformer = Transformer2W(
            name=f"Unit Transformer {i+1}",
            bus_from=rmu_bus,
            bus_to=conv_bus,
            HV=20.0,
            LV=0.69,
            nominal_power=4.39,  # MVA
            copper_losses=30.6,  # kW (from report Table 1-2)
            iron_losses=5.61,  # kW (from report Table 1-2)
            no_load_current=0.0,
            short_circuit_voltage=7.5,  # %
            rate=4.39,  # MVA rating
            tap_module=1.0,
            active=True
        )
        # Calculate R, X, G, B from design parameters
        transformer.fill_design_properties(
            Pcu=30.6,  # kW
            Pfe=5.61,   # kW
            I0=0.0,    # %
            Vsc=7.5,   # %
            Sbase=100.0
        )
        circuit.add_transformer2w(transformer)
    
    # =========================================================================
    # 7. Battery Converters (12 units × 3.75 MW)
    # =========================================================================
    print("Creating battery converters...")
    
    # Each converter: 3.75 MW (45 MW / 12)
    # From report: ±3.631 MW active, ±1.895 Mvar reactive per converter
    # Battery capacity: 90 MWh / 12 = 7.5 MWh per converter
    
    for i, bus in enumerate(converter_lv_buses):
        battery = Battery(
            name=f"BESS Converter {i+1}",
            P=3.75,  # MW (discharging - will make model interesting!)
            Pmax=3.75,  # MW
            Pmin=-3.75,  # MW (charging, negative)
            Qmax=1.895,  # Mvar (from report case data)
            Qmin=-1.895,  # Mvar
            Enom=7.5,  # MWh
            Snom=4.0,  # MVA (approximately)
            is_controlled=False,  # PQ mode (not voltage control)
            active=True  # Enabled in simulation
        )
        circuit.add_battery(bus, battery)
    
    # =========================================================================
    # 8. Auxiliary Transformers and Loads
    # =========================================================================
    print("Creating auxiliary loads...")
    
    # From Table 1-3: 1.25 MVA, 20/0.4 kV, 6% impedance
    aux_transformers = [
        (bus_20kv, bus_aux1, "Auxiliary Transformer 1"),
        (bus_20kv, bus_aux2, "Auxiliary Transformer 2"),
    ]
    
    for bus_from, bus_to, name in aux_transformers:
        transformer = Transformer2W(
            name=name,
            bus_from=bus_from,
            bus_to=bus_to,
            HV=20.0,
            LV=0.4,
            nominal_power=1.25,
            copper_losses=11.0,  # kW (from report Table 1-3)
            iron_losses=1.62,  # kW (from report Table 1-3)
            no_load_current=0.0,
            short_circuit_voltage=6.0,  # %
            rate=1.25,  # MVA rating
            tap_module=1.0,
            active=True
        )
        # Calculate R, X, G, B from design parameters
        transformer.fill_design_properties(
            Pcu=11.0,  # kW
            Pfe=1.62,   # kW
            I0=0.0,    # %
            Vsc=6.0,   # %
            Sbase=100.0
        )
        circuit.add_transformer2w(transformer)
    
    # Auxiliary loads (from report: ~0.42 MW each)
    for i, bus in enumerate([bus_aux1, bus_aux2]):
        load = Load(
            name=f"Auxiliary Load {i+1}",
            P=0.42,  # MW
            Q=0.315,  # Mvar (estimated power factor ~0.8)
        )
        circuit.add_load(bus, load)
    
    print(f"\nModel created successfully!")
    print(f"  Buses: {len(circuit.buses)}")
    print(f"  Lines: {len(circuit.lines)}")
    print(f"  Transformers: {len(circuit.transformers2w)}")
    print(f"  Batteries: {len(circuit.batteries)}")
    print(f"  Loads: {len(circuit.loads)}")
    print(f"  Total BESS Capacity: {sum(b.P for b in circuit.batteries):.1f} MW")
    print(f"  Total Energy Storage: {sum(b.Enom for b in circuit.batteries):.1f} MWh")
    
    return circuit


def run_power_flow(circuit: MultiCircuit, scenario="full_discharge", vset=1.0):
    """
    Run power flow for different scenarios with validation against DNV report
    
    Key validation cases from DNV Table 2-3:
    - case_00: Pmax at nominal voltage (baseline)
    - case_01: Pmax with max leading reactive
    - case_02: Pmax with max lagging reactive
    - case_03: Low power (9 MW) with leading reactive
    - case_06: Pmax with leading reactive at high voltage (1.10 p.u.)
    - case_09: Pmax with lagging reactive at low voltage (0.95 p.u.) - with curtailment
    - case_11: Pmax with lagging reactive at very low voltage (0.90 p.u.) - with curtailment
    
    Args:
        circuit: MultiCircuit object
        scenario: Scenario identifier
        vset: Slack bus voltage setpoint in p.u.
    """
    print(f"\n" + "="*60)
    print(f" Running Power Flow: {scenario}")
    print("="*60 + "\n")
    
    # Get slack generator to set voltage
    slack_gen = None
    for gen in circuit.generators:
        if gen.name == "Stedin Grid":
            slack_gen = gen
            break
    
    if slack_gen:
        slack_gen.Vset = vset  # Capital V for Vset
        print(f"  Slack voltage setpoint: {vset:.3f} p.u.")
    
    # Configure batteries based on scenario
    # Note: Battery inherits from Generator, so we set P and power_factor (Pf)
    # Q = P * tan(acos(Pf))  for lagging
    # Q = -P * tan(acos(Pf)) for leading
    
    if scenario == "case_00":
        # Case 00: Pmax at nominal voltage, PF=1
        for battery in circuit.batteries:
            battery.P = 3.75  # MW per unit
            battery.Pf = 1.0  # Unity power factor -> Q=0
            battery.is_controlled = False  # PQ mode
            
    elif scenario == "case_01":
        # Case 01: Pmax with maximum leading reactive (Q = -1.25 Mvar per unit)
        # S = sqrt(P^2 + Q^2) = sqrt(3.75^2 + 1.25^2) = 3.953 MVA
        # PF = P/S = 3.75/3.953 = 0.9487 leading
        for battery in circuit.batteries:
            battery.P = 3.75   # MW per unit
            battery.Pf = 0.9487  # Leading power factor
            # Note: VeraGrid convention - positive Pf with negative Q for leading
            battery.is_controlled = False  # PQ mode
            
    elif scenario == "case_02":
        # Case 02: Pmax with maximum lagging reactive (Q = +1.25 Mvar per unit)
        # PF = 0.9487 lagging
        for battery in circuit.batteries:
            battery.P = 3.75  # MW per unit
            battery.Pf = 0.9487  # Lagging power factor
            battery.is_controlled = False  # PQ mode
            
    elif scenario == "case_03":
        # Case 03: Low power (9 MW) with maximum leading reactive (Q = -1.25 Mvar per unit)
        # S = sqrt(0.75^2 + 1.25^2) = 1.457 MVA
        # PF = 0.75/1.457 = 0.5145 leading
        for battery in circuit.batteries:
            battery.P = 0.75   # MW per unit (9 MW / 12)
            battery.Pf = 0.5145  # Leading
            battery.is_controlled = False  # PQ mode
            
    elif scenario == "case_06":
        # Case 06: Pmax with leading reactive at high voltage
        for battery in circuit.batteries:
            battery.P = 3.75   # MW per unit
            battery.Pf = 0.9487  # Leading
            battery.is_controlled = False  # PQ mode
            
    elif scenario == "case_09":
        # Case 09: Curtailed power at low voltage (0.95 p.u.)
        # P = 3.4875 MW, Q = +1.25 Mvar
        # S = sqrt(3.4875^2 + 1.25^2) = 3.707 MVA
        # PF = 3.4875/3.707 = 0.9409 lagging
        for battery in circuit.batteries:
            battery.P = 3.4875  # MW per unit (41.85 MW / 12) - curtailed!
            battery.Pf = 0.9409  # Lagging
            battery.is_controlled = False  # PQ mode
            
    elif scenario == "case_11":
        # Case 11: Curtailed power at very low voltage (0.90 p.u.)
        for battery in circuit.batteries:
            battery.P = 3.4875  # MW per unit (41.85 MW / 12) - curtailed!
            battery.Pf = 0.9409  # Lagging
            battery.is_controlled = False  # PQ mode
            
    elif scenario == "full_charge":
        # Charging mode (not in DNV report)
        for battery in circuit.batteries:
            battery.P = -3.75  # MW per unit (negative = charge)
            battery.Pf = 1.0
            battery.is_controlled = False  # PQ mode
    
    # Power flow options
    options = PowerFlowOptions()
    options.solver_type = SolverType.NR
    options.verbose = 0
    options.tolerance = 1e-6
    options.max_iter = 20
    
    # IMPORTANT: Create driver AFTER setting battery powers
    # The driver takes a snapshot of the circuit at initialization
    pf_driver = PowerFlowDriver(grid=circuit, options=options)
    pf_driver.run()
    
    # Print results
    if pf_driver.results.converged:
        print("[OK] Power flow converged!\n")
        
        # Calculate key metrics
        total_bess_p = sum(b.P for b in circuit.batteries)
        
        # Calculate total BESS Q from P and power factor settings
        import math
        total_bess_q = 0.0
        for b in circuit.batteries:
            if abs(b.Pf - 1.0) > 0.001:  # Not unity power factor
                theta = math.acos(min(1.0, abs(b.Pf)))  # Angle
                Q_mag = abs(b.P) * math.tan(theta)
                # For leading (capacitive), we need negative Q
                # This depends on how the model interprets Pf
                # For now, assume lagging is positive Q
                total_bess_q += Q_mag if b.P > 0 else -Q_mag
        
        total_aux_p = sum(ld.P for ld in circuit.loads)
        total_aux_q = sum(ld.Q for ld in circuit.loads)
        
        # Get results at connection point (slack bus)
        buses = circuit.get_buses()
        cp_idx = 0  # Connection point is first bus
        v_cp = np.abs(pf_driver.results.voltage[cp_idx])
        
        # Power at connection point (from slack generator)
        Sbus = pf_driver.results.Sbus
        P_cp = -np.real(Sbus[cp_idx])  # Negative because generator injects power INTO grid
        Q_cp = -np.imag(Sbus[cp_idx])  # Negative because generator injects reactive power
        
        # Calculate system losses
        P_loss = P_cp - total_bess_p - total_aux_p
        
        print(f"Power Flow Results:")
        print(f"  Iterations: {pf_driver.results.iterations}")
        print(f"  Error: {pf_driver.results.error:.2e}")
        print(f"  Connection Point Voltage: {v_cp:.4f} p.u. ({v_cp * 50:.2f} kV)")
        print(f"\n  BESS Settings:")
        print(f"    Total Active Power: {total_bess_p:.2f} MW")
        print(f"    Total Reactive Power: {total_bess_q:.2f} Mvar")
        print(f"\n  Connection Point (CP) Results:")
        print(f"    Active Power at CP: {P_cp:.2f} MW")
        print(f"    Reactive Power at CP: {Q_cp:.2f} Mvar")
        print(f"\n  Auxiliary Loads:")
        print(f"    Total Aux Power: {total_aux_p:.2f} MW, {total_aux_q:.2f} Mvar")
        print(f"\n  System Losses:")
        print(f"    Total Active Losses: {P_loss:.2f} MW ({100*P_loss/P_cp:.2f}%)")
        
        return pf_driver.results, {
            'V_cp': v_cp,
            'P_cp': P_cp,
            'Q_cp': Q_cp,
            'P_bess': total_bess_p,
            'Q_bess': total_bess_q,
            'P_loss': P_loss,
            'converged': True
        }
    else:
        print(f"[FAIL] Power flow did not converge")
        print(f"  Error: {pf_driver.results.error:.2e}")
        return None, {'converged': False}


def validate_against_dnv_report(circuit: MultiCircuit):
    """
    Run validation cases from DNV report Table 2-3 and compare results
    """
    print("\n" + "="*70)
    print(" DNV REPORT VALIDATION SUITE")
    print(" Comparing against Table 2-3: Discharging Load Flow Results at CP")
    print("="*70)
    
    # DNV report expected values (from Table 2-3)
    # Format: (V_setpoint, P_bess_total, Q_bess_total, P_cp_expected, Q_cp_expected)
    dnv_cases = {
        'case_00': {
            'description': 'Pmax at Nominal Voltage (PF=1)',
            'vset': 1.00,
            'P_bess': 45.00,
            'Q_bess': 0.00,
            'P_cp_expected': 45.50,  # Approximate from DNV report
            'Q_cp_expected': 7.30,   # Approximate from DNV report
            'tolerance_p': 0.5,      # MW
            'tolerance_q': 0.5       # Mvar
        },
        'case_01': {
            'description': 'Pmax with Maximum Leading Reactive',
            'vset': 1.00,
            'P_bess': 45.00,
            'Q_bess': -15.00,
            'P_cp_expected': 45.50,
            'Q_cp_expected': -7.70,  # Leading
            'tolerance_p': 0.5,
            'tolerance_q': 0.5
        },
        'case_02': {
            'description': 'Pmax with Maximum Lagging Reactive',
            'vset': 1.00,
            'P_bess': 45.00,
            'Q_bess': 15.00,
            'P_cp_expected': 45.50,
            'Q_cp_expected': 22.30,  # Lagging
            'tolerance_p': 0.5,
            'tolerance_q': 0.5
        },
        'case_03': {
            'description': 'Low Power (9 MW) with Leading Reactive',
            'vset': 1.00,
            'P_bess': 9.00,
            'Q_bess': -15.00,
            'P_cp_expected': 9.90,
            'Q_cp_expected': -14.40,
            'tolerance_p': 0.5,
            'tolerance_q': 0.5
        },
        'case_06': {
            'description': 'Pmax with Leading Reactive at High Voltage (1.10 p.u.)',
            'vset': 1.10,
            'P_bess': 45.00,
            'Q_bess': -15.00,
            'P_cp_expected': 45.50,
            'Q_cp_expected': -7.70,
            'tolerance_p': 0.5,
            'tolerance_q': 0.5
        },
        'case_09': {
            'description': 'Curtailed Power at Low Voltage (0.95 p.u.)',
            'vset': 0.95,
            'P_bess': 41.85,  # CURTAILED due to voltage limit
            'Q_bess': 15.00,
            'P_cp_expected': 42.70,
            'Q_cp_expected': 22.30,
            'tolerance_p': 0.5,
            'tolerance_q': 0.5
        },
        'case_11': {
            'description': 'Curtailed Power at Very Low Voltage (0.90 p.u.)',
            'vset': 0.90,
            'P_bess': 41.85,  # CURTAILED due to voltage limit
            'Q_bess': 15.00,
            'P_cp_expected': 42.70,
            'Q_cp_expected': 22.30,
            'tolerance_p': 0.5,
            'tolerance_q': 0.5
        }
    }
    
    results_summary = []
    
    for case_id, case_data in dnv_cases.items():
        print(f"\n{'='*70}")
        print(f" {case_id.upper()}: {case_data['description']}")
        print(f"{'='*70}")
        print(f" Target Settings:")
        print(f"   V_setpoint: {case_data['vset']:.3f} p.u.")
        print(f"   BESS P: {case_data['P_bess']:.2f} MW")
        print(f"   BESS Q: {case_data['Q_bess']:.2f} Mvar")
        print(f" DNV Expected Results:")
        print(f"   P at CP: {case_data['P_cp_expected']:.2f} MW")
        print(f"   Q at CP: {case_data['Q_cp_expected']:.2f} Mvar")
        print(f"{'-'*70}")
        
        # Run simulation
        pf_results, metrics = run_power_flow(circuit, scenario=case_id, vset=case_data['vset'])
        
        if metrics['converged']:
            # Calculate errors
            error_p = metrics['P_cp'] - case_data['P_cp_expected']
            error_q = metrics['Q_cp'] - case_data['Q_cp_expected']
            error_p_pct = 100 * abs(error_p) / case_data['P_cp_expected']
            error_q_pct = 100 * abs(error_q) / abs(case_data['Q_cp_expected']) if case_data['Q_cp_expected'] != 0 else 0
            
            # Check if within tolerance
            pass_p = abs(error_p) <= case_data['tolerance_p']
            pass_q = abs(error_q) <= case_data['tolerance_q']
            overall_pass = pass_p and pass_q
            
            print(f"\n VALIDATION RESULTS:")
            print(f"   P at CP: {metrics['P_cp']:.2f} MW (error: {error_p:+.2f} MW, {error_p_pct:.2f}%) {'[PASS]' if pass_p else '[FAIL]'}")
            print(f"   Q at CP: {metrics['Q_cp']:.2f} Mvar (error: {error_q:+.2f} Mvar, {error_q_pct:.2f}%) {'[PASS]' if pass_q else '[FAIL]'}")
            print(f"   Status: {'PASS' if overall_pass else 'FAIL'}")
            
            results_summary.append({
                'case': case_id,
                'description': case_data['description'],
                'pass': overall_pass,
                'error_p': error_p,
                'error_q': error_q,
                'error_p_pct': error_p_pct,
                'error_q_pct': error_q_pct
            })
        else:
            print(f"\n VALIDATION RESULTS: FAIL - Did not converge")
            results_summary.append({
                'case': case_id,
                'description': case_data['description'],
                'pass': False,
                'error_p': None,
                'error_q': None,
                'error_p_pct': None,
                'error_q_pct': None
            })
    
    # Print summary
    print(f"\n{'='*70}")
    print(" VALIDATION SUMMARY")
    print(f"{'='*70}")
    
    for result in results_summary:
        status = '[PASS]' if result['pass'] else '[FAIL]'
        print(f" {result['case']:10s} - {status:10s} - {result['description']}")
        if result['pass']:
            print(f"              P error: {result['error_p_pct']:.2f}%,  Q error: {result['error_q_pct']:.2f}%")
    
    total_cases = len(results_summary)
    passed_cases = sum(1 for r in results_summary if r['pass'])
    
    print(f"\n{'='*70}")
    print(f" OVERALL VALIDATION: {passed_cases}/{total_cases} cases passed")
    if passed_cases == total_cases:
        print(f" *** MODEL FULLY VALIDATED AGAINST DNV REPORT ***")
    else:
        print(f" Model needs adjustment - {total_cases - passed_cases} case(s) failed")
    print(f"{'='*70}\n")
    
    return results_summary


def main():
    """
    Main function
    """
    print("\n" + "="*70)
    print(" Amethyst ESM Model Creation and Analysis")
    print(" Based on DNV Report 25-0851 rev.0")
    print("="*70)
    
    # Create the model
    circuit = create_amethyst_model()
    
    # Save the base model
    output_file = "Amethyst_ESM_Model.veragrid"
    print(f"\nSaving model to: {output_file}")
    file_saver = FileSave(circuit, output_file)
    file_saver.save()
    print("[OK] Model saved!")
    
    # Run DNV validation suite
    validation_results = validate_against_dnv_report(circuit)
    
    print("\n" + "="*70)
    print(" Analysis Complete!")
    print("="*70)
    print("\nNext steps:")
    print(f"  1. Open '{output_file}' in VeraGrid GUI")
    print("  2. Review validation results above")
    print("  3. If all cases pass, model is fully validated!")
    print("  4. Explore the model topology")
    print("  5. Run additional power flow scenarios")
    print("  6. Compare with DNV report findings (25-0851_report.md)")
    print("  7. Perform reactive power capability studies")
    print("  8. Export results for validation\n")


if __name__ == "__main__":
    main()
