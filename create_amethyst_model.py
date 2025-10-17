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
        vset=1.0,  # p.u. voltage setpoint
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


def run_power_flow(circuit: MultiCircuit, scenario="full_discharge"):
    """
    Run power flow for different scenarios
    
    Scenarios:
    - full_discharge: 45 MW discharge (Case 00 from report)
    - full_charge: 45 MW charge
    - reactive_test: Test reactive power capability
    """
    print(f"\n" + "="*60)
    print(f" Running Power Flow: {scenario}")
    print("="*60 + "\n")
    
    # Configure batteries based on scenario
    if scenario == "full_discharge":
        # Case 00: 45 MW discharge at PF=1
        for battery in circuit.batteries:
            battery.P = 3.75  # MW per unit
            battery.Pf = 1.0  # Unity power factor
            battery.is_controlled = False  # PQ mode
            
    elif scenario == "full_charge":
        # Charging mode
        for battery in circuit.batteries:
            battery.P = -3.75  # MW per unit (negative = charge)
            battery.Pf = 1.0
            battery.is_controlled = False  # PQ mode
            
    elif scenario == "reactive_leading":
        # Case 01: 45 MW + 15 Mvar leading (capacitive)
        for battery in circuit.batteries:
            battery.P = 3.75
            battery.Pf = 0.9487  # cos(arctan(-15/45)) ≈ 0.9487 leading
            battery.is_controlled = False  # PQ mode
            
    elif scenario == "reactive_lagging":
        # Case 02: 45 MW + 15 Mvar lagging (inductive)
        for battery in circuit.batteries:
            battery.P = 3.75
            battery.Pf = 0.9487  # cos(arctan(15/45)) ≈ 0.9487 lagging
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
        
        # Debug: print battery powers as set
        print("Battery Powers (as set):")
        for i, bat in enumerate(circuit.batteries[:3]):  # Show first 3
            print(f"  {bat.name}: P={bat.P:.2f} MW, Pf={bat.Pf:.3f}, Active={bat.active}")
        print(f"  ... ({len(circuit.batteries)} total batteries)\n")
        
        # Get results at key buses
        buses = circuit.get_buses()
        cp_idx = 0  # Connection point
        v_cp = np.abs(pf_driver.results.voltage[cp_idx])
        
        print(f"Power Flow Results:")
        print(f"  Iterations: {pf_driver.results.iterations}")
        print(f"  Error: {pf_driver.results.error:.2e}")
        print(f"  Voltage array shape: {pf_driver.results.voltage.shape}")
        print(f"  Sbus shape: {pf_driver.results.Sbus.shape}")
        print(f"  Connection Point Voltage: {v_cp:.4f} p.u. ({v_cp * 50:.2f} kV)")
        
        # Power flows
        Sbus = pf_driver.results.Sbus
        print(f"  Sbus min/max: {np.min(np.abs(Sbus)):.4f} / {np.max(np.abs(Sbus)):.4f} MVA")
        P_gen = np.sum(np.real(Sbus[Sbus.real > 0]))
        P_load = -np.sum(np.real(Sbus[Sbus.real < 0]))
        P_loss = np.sum(np.real(pf_driver.results.losses))
        
        Q_gen = np.sum(np.imag(Sbus[Sbus.imag > 0]))
        Q_load = -np.sum(np.imag(Sbus[Sbus.imag < 0]))
        
        print(f"  Active Power Generation: {P_gen:.2f} MW")
        print(f"  Active Power Load: {P_load:.2f} MW")
        print(f"  Active Power Losses: {P_loss:.2f} MW")
        print(f"  Reactive Power Generation: {Q_gen:.2f} Mvar")
        print(f"  Reactive Power Load: {Q_load:.2f} Mvar")
        
        return pf_driver.results
    else:
        print(f"[FAIL] Power flow did not converge")
        print(f"  Error: {pf_driver.results.error:.2e}")
        return None


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

    
    # Run different scenarios
    scenarios = [
        ("full_discharge", "Full Discharge (45 MW, PF=1)"),
        ("full_charge", "Full Charge (-45 MW, PF=1)"),
        ("reactive_leading", "Discharge with Leading Reactive (45 MW, -15 Mvar)"),
        ("reactive_lagging", "Discharge with Lagging Reactive (45 MW, +15 Mvar)"),
    ]
    
    print("\n" + "="*60)
    print(" Running Test Scenarios")
    print("="*60)
    
    for scenario_id, description in scenarios:
        print(f"\n{description}")
        print("-" * 60)
        results = run_power_flow(circuit, scenario_id)
    
    print("\n" + "="*70)
    print(" Analysis Complete!")
    print("="*70)
    print("\nNext steps:")
    print(f"  1. Open '{output_file}' in VeraGrid GUI")
    print("  2. Explore the model topology")
    print("  3. Run additional power flow scenarios")
    print("  4. Compare with DNV report findings (25-0851_report.md)")
    print("  5. Perform reactive power capability studies")
    print("  6. Export results for validation\n")


if __name__ == "__main__":
    main()
