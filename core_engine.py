"""
core_engine.py – Thermodynamic & economic calculations
======================================================
All CoolProp calls, energy-balance maths, and financial
functions live here so every page shares one source of truth.
"""

import math
import numpy as np
import numpy_financial as npf
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional

try:
    import CoolProp.CoolProp as CP
except ImportError:
    CP = None

# ════════════════════════════════════════════════════════════
#  FLUID PROPERTIES (CoolProp wrappers)
# ════════════════════════════════════════════════════════════

def cp_fluid(fluid: str, T_C: float, P_kPa: float = 101.325) -> dict:
    """Return density, cp, viscosity, conductivity for a fluid at T [°C], P [kPa]."""
    T_K = T_C + 273.15
    P_Pa = P_kPa * 1000

    def _try_props(input_pair):
        """Try to get each property individually, with fallbacks."""
        results = {}
        for prop, key, fallback in [("D", "rho", 1000.0), ("C", "cp", 4180.0),
                                     ("V", "mu", 0.001), ("L", "k", 0.6)]:
            try:
                results[key] = CP.PropsSI(prop, *input_pair, fluid)
            except Exception:
                results[key] = fallback
        return results

    # First try: subcooled / superheated at given P, T
    try:
        result = _try_props(("T", T_K, "P", P_Pa))
        if result["rho"] > 10:  # sanity check
            return result
    except Exception:
        pass

    # Second try: saturated liquid (Q=0) — works for refrigerants
    try:
        result = _try_props(("T", T_K, "Q", 0))
        if result["rho"] > 10:
            return result
    except Exception:
        pass

    return {"rho": 1000.0, "cp": 4180.0, "mu": 0.001, "k": 0.6}


def saturation_pressure(fluid: str, T_C: float) -> float:
    """Saturation pressure [kPa] at temperature T [°C]."""
    try:
        return CP.PropsSI("P", "T", T_C + 273.15, "Q", 0, fluid) / 1000
    except Exception:
        return 101.325


def latent_heat(fluid: str, T_C: float) -> float:
    """Latent heat of vaporisation [J/kg] at T [°C]."""
    T_K = T_C + 273.15
    try:
        h_l = CP.PropsSI("H", "T", T_K, "Q", 0, fluid)
        h_v = CP.PropsSI("H", "T", T_K, "Q", 1, fluid)
        return h_v - h_l
    except Exception:
        return 200_000  # rough fallback


# ════════════════════════════════════════════════════════════
#  CLIMATE DATA  (simplified annual profiles)
# ════════════════════════════════════════════════════════════

CLIMATES: Dict[str, Dict] = {
    "Frankfurt (DE)":      {"T_avg": 10.4, "T_design": 35, "T_wb": 22, "RH": 0.70, "free_cool_hrs": 6800},
    "Stockholm (SE)":      {"T_avg":  6.5, "T_design": 30, "T_wb": 18, "RH": 0.72, "free_cool_hrs": 7800},
    "Amsterdam (NL)":      {"T_avg": 10.0, "T_design": 33, "T_wb": 21, "RH": 0.80, "free_cool_hrs": 7000},
    "London (UK)":         {"T_avg": 11.0, "T_design": 32, "T_wb": 20, "RH": 0.75, "free_cool_hrs": 7200},
    "Dublin (IE)":         {"T_avg":  9.8, "T_design": 28, "T_wb": 18, "RH": 0.80, "free_cool_hrs": 7600},
    "Phoenix (US-AZ)":     {"T_avg": 23.9, "T_design": 46, "T_wb": 24, "RH": 0.25, "free_cool_hrs": 2500},
    "Ashburn (US-VA)":     {"T_avg": 13.0, "T_design": 37, "T_wb": 26, "RH": 0.65, "free_cool_hrs": 5200},
    "Singapore (SG)":      {"T_avg": 27.5, "T_design": 35, "T_wb": 28, "RH": 0.84, "free_cool_hrs":  500},
    "Mumbai (IN)":         {"T_avg": 27.2, "T_design": 38, "T_wb": 28, "RH": 0.75, "free_cool_hrs":  800},
    "Riyadh (SA)":         {"T_avg": 26.0, "T_design": 48, "T_wb": 22, "RH": 0.25, "free_cool_hrs": 2000},
}


# ════════════════════════════════════════════════════════════
#  COOLING ARCHITECTURE DEFINITIONS
# ════════════════════════════════════════════════════════════

@dataclass
class CoolingArch:
    name: str
    short: str
    max_rack_kw: float          # kW per rack
    pue_range: Tuple[float, float]
    capex_per_kw: Tuple[float, float]   # $/kW IT
    energy_saving_vs_air: float          # fraction 0-1
    water_factor: float                  # L/kWh (0 = waterless)
    retrofit_ease: str                   # Easy / Moderate / Difficult
    heat_reuse_T: float                  # °C of return water for reuse
    fan_fraction: float                  # fraction of cooling power from fans
    description: str = ""
    coolant: str = "Water"
    two_phase: bool = False

ARCHITECTURES: Dict[str, CoolingArch] = {
    "air": CoolingArch(
        "Traditional Air (CRAH/CRAC)", "Air", 20, (1.30, 1.60),
        (200, 500), 0.0, 1.8, "Existing", 30, 1.0,
        "Baseline air cooling with hot-aisle containment", "Air",
    ),
    "air_rdhx": CoolingArch(
        "Air + Rear-Door HX", "Air+RDHx", 50, (1.15, 1.35),
        (300, 800), 0.15, 1.2, "Easy", 35, 0.6,
        "Rear-door water coils offload 40-60% of rack heat", "Water",
    ),
    "sp_coldplate": CoolingArch(
        "Single-Phase Cold Plate (DLC)", "SP-DLC", 240, (1.03, 1.15),
        (500, 1500), 0.30, 0.3, "Moderate", 50, 0.15,
        "Water/glycol cold plates on CPUs/GPUs via CDU", "Water",
    ),
    "2p_coldplate": CoolingArch(
        "Two-Phase Cold Plate", "2P-DLC", 300, (1.02, 1.12),
        (1000, 2000), 0.35, 0.05, "Moderate", 55, 0.05,
        "Low-boiling refrigerant on chip; superior ΔT", "R1233zd(E)",
        two_phase=True,
    ),
    "sp_immersion": CoolingArch(
        "Single-Phase Immersion", "SP-Imm", 200, (1.02, 1.10),
        (800, 1500), 0.35, 0.02, "Difficult", 55, 0.0,
        "Servers submerged in dielectric oil", "INCOMP::ExamplePure",
        # CoolProp doesn't have dielectric oils; we use water props as proxy
    ),
    "2p_immersion": CoolingArch(
        "Two-Phase Immersion", "2P-Imm", 350, (1.01, 1.05),
        (1000, 2000), 0.40, 0.01, "Difficult", 60, 0.0,
        "Boiling dielectric captures extreme heat flux", "R1233zd(E)",
        two_phase=True,
    ),
}

# ════════════════════════════════════════════════════════════
#  REGULATION PROFILES
# ════════════════════════════════════════════════════════════

@dataclass
class RegProfile:
    name: str
    max_pue: float
    erf_target: float          # fraction by 2028
    water_restricted: bool
    fgas_gwp_limit: int        # max GWP for new equipment
    carbon_price: float        # €/tCO₂
    heat_reuse_mandate: bool
    notes: str = ""

REGULATIONS: Dict[str, RegProfile] = {
    "Germany (EnEfG)": RegProfile(
        "Germany", 1.2, 0.20, False, 150, 45,
        True, "PUE≤1.2, ERF 10%→20% by 2028, €100k fines",
    ),
    "EU (avg)": RegProfile(
        "EU average", 1.3, 0.10, False, 150, 40,
        True, "Energy Efficiency Directive + F-gas 2024",
    ),
    "Netherlands": RegProfile(
        "Netherlands", 1.2, 0.10, True, 150, 45,
        True, "Moratorium on new DCs without heat capture",
    ),
    "Singapore": RegProfile(
        "Singapore", 1.3, 0.0, True, 700, 5,
        False, "Tropical; PUE <1.3 moratorium",
    ),
    "US (federal)": RegProfile(
        "US federal", 1.6, 0.0, False, 700, 10,
        False, "AIM Act GWP<700 by 2027",
    ),
    "US (Arizona)": RegProfile(
        "US Arizona", 1.6, 0.0, True, 700, 10,
        False, "Marana bans potable water for DC cooling",
    ),
    "Nordics (avg)": RegProfile(
        "Nordics", 1.2, 0.15, False, 150, 50,
        True, "Strong district heating networks",
    ),
    "Middle East (avg)": RegProfile(
        "Middle East", 1.6, 0.0, True, 700, 0,
        False, "Extreme heat; water scarcity",
    ),
}

# ════════════════════════════════════════════════════════════
#  THERMODYNAMIC MODEL  –  rack → CDU → plant → heat recovery
# ════════════════════════════════════════════════════════════

@dataclass
class ThermoResult:
    """Full result from the thermodynamic digital twin."""
    # Energy flows (kW)
    Q_it: float             # IT heat load
    Q_coolant: float        # heat captured by liquid loop
    Q_air_residual: float   # remaining air-side heat
    W_pump: float           # pumping power
    W_chiller: float        # chiller compressor power
    W_fan: float            # fan power (CRAH / rack fans)
    W_total_facility: float # total non-IT facility power
    # Temperatures (°C)
    T_supply: float
    T_return: float
    delta_T: float
    # Flow
    m_dot: float            # coolant mass flow kg/s
    # Metrics
    pue: float
    tue: float              # TUE = 1 / (IT useful / total)
    wue: float              # L/kWh
    erf: float              # fraction reused
    # Heat recovery
    Q_reuse: float          # kW recovered
    Q_reuse_annual_MWh: float


def run_thermo_model(
    arch_key: str,
    rack_kw: float,
    n_racks: int,
    climate_key: str,
    T_supply_C: float = 25.0,
    reuse_fraction: float = 0.0,
    chiller_cop_nominal: float = 5.0,
) -> ThermoResult:
    """
    Simplified but defensible steady-state plant model.
    Rack → CDU (liquid loop) → chiller/dry-cooler → optional heat recovery.
    """
    arch = ARCHITECTURES[arch_key]
    clim = CLIMATES[climate_key]

    Q_it = rack_kw * n_racks  # total IT load kW

    # ── Liquid / air split ────────────────────────────────
    liquid_capture = 1.0 - arch.fan_fraction
    Q_coolant = Q_it * liquid_capture
    Q_air = Q_it * arch.fan_fraction

    # ── Coolant loop ──────────────────────────────────────
    # Use CoolProp for water properties at supply T
    if arch.two_phase:
        # Two-phase: use latent heat for flow calc
        fluid = arch.coolant if arch.coolant != "INCOMP::ExamplePure" else "R1233zd(E)"
        try:
            h_fg = latent_heat(fluid, T_supply_C)
        except Exception:
            h_fg = 180_000
        m_dot = Q_coolant * 1000 / h_fg if h_fg > 0 else 1.0
        delta_T = 5.0  # 2-phase: near-isothermal
        T_return = T_supply_C + delta_T
    else:
        props = cp_fluid("Water", T_supply_C)
        cp_w = props["cp"]
        target_dT = max(8, min(25, rack_kw / 8))  # heuristic ΔT
        delta_T = target_dT
        T_return = T_supply_C + delta_T
        m_dot = (Q_coolant * 1000) / (cp_w * delta_T) if delta_T > 0 else 1.0

    # ── Pumping power ─────────────────────────────────────
    # Simplified: ΔP ~ 150-300 kPa, η_pump ~ 0.70
    dP = 200_000  # Pa
    if arch.two_phase:
        rho = 1100  # rough liquid density
    else:
        rho = cp_fluid("Water", (T_supply_C + T_return) / 2)["rho"]
    V_dot = m_dot / rho  # m³/s
    eta_pump = 0.70
    W_pump = (V_dot * dP / eta_pump) / 1000  # kW

    # ── Fan power (air-side residual) ─────────────────────
    fan_specific = 0.04  # kW per kW of air-side cooling (efficient fans)
    W_fan = Q_air * fan_specific * (1 + arch.fan_fraction)

    # ── Chiller / free-cooling logic ──────────────────────
    T_ambient = clim["T_avg"]
    free_cool_threshold = T_supply_C - 5  # need ambient < supply-5 for dry cooler

    frac_free = clim["free_cool_hrs"] / 8760
    if arch.water_factor < 0.1:
        # Waterless / closed loop → dry cooler only
        frac_mechanical = 1 - frac_free
    else:
        frac_mechanical = 1 - frac_free

    # Chiller COP adjusted for conditions
    T_cond = max(T_ambient + 10, 35)
    T_evap = T_supply_C
    carnot_cop = (T_evap + 273.15) / max((T_cond - T_evap), 5)
    eta_carnot = 0.55
    cop_actual = min(carnot_cop * eta_carnot, chiller_cop_nominal)
    cop_actual = max(cop_actual, 2.5)

    Q_reject = Q_coolant  # total heat to reject
    W_chiller_mech = Q_reject / cop_actual
    W_chiller = W_chiller_mech * frac_mechanical + (W_pump * 0.3) * frac_free  # free cool still needs some pump work

    # ── Total facility power ──────────────────────────────
    W_misc = Q_it * 0.02  # lighting, UPS losses, BMS
    W_total_facility = W_pump + W_chiller + W_fan + W_misc

    # ── PUE / TUE ─────────────────────────────────────────
    pue = (Q_it + W_total_facility) / Q_it if Q_it > 0 else 1.0
    # Clamp PUE to architecture range
    pue = max(arch.pue_range[0], min(pue, arch.pue_range[1] * 1.1))

    # TUE: accounts for IT equipment efficiency too
    it_useful_fraction = 0.85  # ~85% of IT power does useful compute
    tue = pue / it_useful_fraction

    # ── WUE ───────────────────────────────────────────────
    wue = arch.water_factor * (1 - frac_free * 0.5)  # less water when free-cooling

    # ── Heat recovery ─────────────────────────────────────
    Q_reuse = Q_coolant * reuse_fraction
    erf = reuse_fraction
    Q_reuse_annual = Q_reuse * 8760 / 1000  # MWh/yr

    return ThermoResult(
        Q_it=Q_it, Q_coolant=Q_coolant, Q_air_residual=Q_air,
        W_pump=W_pump, W_chiller=W_chiller, W_fan=W_fan,
        W_total_facility=W_total_facility,
        T_supply=T_supply_C, T_return=T_return, delta_T=delta_T,
        m_dot=m_dot,
        pue=round(pue, 3), tue=round(tue, 3),
        wue=round(wue, 3), erf=round(erf, 3),
        Q_reuse=Q_reuse, Q_reuse_annual_MWh=round(Q_reuse_annual, 1),
    )


# ════════════════════════════════════════════════════════════
#  FINANCIAL / TECHNO-ECONOMIC MODEL
# ════════════════════════════════════════════════════════════

@dataclass
class FinancialResult:
    capex: float            # total $
    capex_per_kw: float
    annual_energy_cost: float
    annual_water_cost: float
    annual_maintenance: float
    annual_opex: float
    annual_heat_revenue: float  # from waste heat sale
    net_annual_opex: float
    payback_years: float
    npv_10yr: float
    irr_10yr: float
    tco_10yr: float
    # Comparison
    savings_vs_air: float   # annual $ saved vs air baseline


def run_financial_model(
    arch_key: str,
    thermo: ThermoResult,
    elec_price: float = 0.12,    # $/kWh
    water_price: float = 3.0,    # $/kL
    heat_sale_price: float = 40, # $/MWh (district heating)
    discount_rate: float = 0.08,
    n_years: int = 10,
    carbon_price: float = 40,    # $/tCO₂
    grid_carbon: float = 0.4,    # kgCO₂/kWh
) -> FinancialResult:
    arch = ARCHITECTURES[arch_key]

    # CapEx
    mid_capex_rate = (arch.capex_per_kw[0] + arch.capex_per_kw[1]) / 2
    capex = mid_capex_rate * thermo.Q_it

    # Annual energy
    total_power = thermo.Q_it + thermo.W_total_facility
    annual_energy_kwh = total_power * 8760
    annual_energy_cost = annual_energy_kwh * elec_price

    # Water
    annual_water_L = thermo.wue * annual_energy_kwh  # L
    annual_water_cost = (annual_water_L / 1000) * water_price

    # Maintenance (% of capex)
    maint_rate = 0.03 if "immersion" not in arch_key else 0.04
    annual_maintenance = capex * maint_rate

    # Carbon cost
    annual_carbon = (annual_energy_kwh / 1000) * grid_carbon * carbon_price  # tCO₂

    annual_opex = annual_energy_cost + annual_water_cost + annual_maintenance + annual_carbon

    # Heat sale revenue
    annual_heat_revenue = thermo.Q_reuse_annual_MWh * heat_sale_price

    net_annual_opex = annual_opex - annual_heat_revenue

    # ── Baseline (air) comparison ─────────────────────────
    air_arch = ARCHITECTURES["air"]
    air_mid_capex = (air_arch.capex_per_kw[0] + air_arch.capex_per_kw[1]) / 2
    air_capex = air_mid_capex * thermo.Q_it
    air_pue_mid = (air_arch.pue_range[0] + air_arch.pue_range[1]) / 2
    air_total_power = thermo.Q_it * air_pue_mid
    air_annual_energy = air_total_power * 8760 * elec_price
    air_annual_water = air_arch.water_factor * air_total_power * 8760 / 1000 * water_price
    air_annual_maint = air_capex * 0.03
    air_annual_carbon = (air_total_power * 8760 / 1000) * grid_carbon * carbon_price
    air_annual_opex = air_annual_energy + air_annual_water + air_annual_maint + air_annual_carbon

    savings_vs_air = air_annual_opex - net_annual_opex

    # ── Investment metrics ────────────────────────────────
    incremental_capex = max(capex - air_capex, 1)
    if savings_vs_air > 0:
        payback = incremental_capex / savings_vs_air
    else:
        payback = 99.0

    # NPV & IRR
    cashflows = [-incremental_capex] + [savings_vs_air] * n_years
    npv = npf.npv(discount_rate, cashflows)
    try:
        irr = npf.irr(cashflows)
        if irr is None or np.isnan(irr):
            irr = 0.0
    except Exception:
        irr = 0.0

    tco = capex + net_annual_opex * n_years  # undiscounted for simplicity

    return FinancialResult(
        capex=round(capex),
        capex_per_kw=round(mid_capex_rate),
        annual_energy_cost=round(annual_energy_cost),
        annual_water_cost=round(annual_water_cost),
        annual_maintenance=round(annual_maintenance),
        annual_opex=round(annual_opex),
        annual_heat_revenue=round(annual_heat_revenue),
        net_annual_opex=round(net_annual_opex),
        payback_years=round(payback, 2),
        npv_10yr=round(npv),
        irr_10yr=round(irr * 100, 1) if irr else 0.0,
        tco_10yr=round(tco),
        savings_vs_air=round(savings_vs_air),
    )


# ════════════════════════════════════════════════════════════
#  RELIABILITY MODEL
# ════════════════════════════════════════════════════════════

@dataclass
class ReliabilityResult:
    mtbf_hours: float
    mttr_hours: float
    availability: float       # fraction
    uptime_percent: float
    annual_downtime_hours: float


def estimate_reliability(arch_key: str, redundancy: str = "N+1") -> ReliabilityResult:
    """Simplified reliability estimate based on architecture and redundancy."""
    base_mtbf = {
        "air":          80_000,
        "air_rdhx":     70_000,
        "sp_coldplate": 55_000,
        "2p_coldplate": 45_000,
        "sp_immersion": 50_000,
        "2p_immersion": 40_000,
    }
    base_mttr = {
        "air":          2.0,
        "air_rdhx":     3.0,
        "sp_coldplate": 4.0,
        "2p_coldplate": 5.0,
        "sp_immersion": 6.0,
        "2p_immersion": 8.0,
    }
    redundancy_factor = {"N": 1.0, "N+1": 2.5, "2N": 6.0}

    mtbf = base_mtbf.get(arch_key, 50_000) * redundancy_factor.get(redundancy, 1.0)
    mttr = base_mttr.get(arch_key, 4.0)

    availability = mtbf / (mtbf + mttr)
    uptime = availability * 100
    annual_down = (1 - availability) * 8760

    return ReliabilityResult(
        mtbf_hours=round(mtbf),
        mttr_hours=mttr,
        availability=round(availability, 7),
        uptime_percent=round(uptime, 5),
        annual_downtime_hours=round(annual_down, 2),
    )


# ════════════════════════════════════════════════════════════
#  SCREENING / RANKING
# ════════════════════════════════════════════════════════════

def screen_architectures(
    rack_kw: float,
    climate_key: str,
    elec_price: float,
    water_price: float,
    reuse_fraction: float,
    reg_key: str,
    n_racks: int = 100,
) -> List[Dict]:
    """Score all architectures for the given scenario and return ranked list."""
    reg = REGULATIONS[reg_key]
    results = []

    for key, arch in ARCHITECTURES.items():
        # Skip if architecture can't handle the density
        if rack_kw > arch.max_rack_kw:
            continue

        thermo = run_thermo_model(key, rack_kw, n_racks, climate_key,
                                  reuse_fraction=reuse_fraction)
        fin = run_financial_model(key, thermo, elec_price, water_price,
                                  carbon_price=reg.carbon_price)
        rel = estimate_reliability(key, "N+1")

        # Compliance check
        pue_ok = thermo.pue <= reg.max_pue
        erf_ok = thermo.erf >= reg.erf_target or not reg.heat_reuse_mandate
        water_ok = arch.water_factor < 0.5 if reg.water_restricted else True
        compliant = pue_ok and erf_ok and water_ok

        # Composite score (lower = better)
        score = (
            fin.tco_10yr / 1e6 * 0.35            # cost weight
            + (1 - rel.availability) * 1e6 * 0.20  # reliability weight
            + thermo.pue * 10 * 0.15               # efficiency weight
            + thermo.wue * 5 * 0.10                # water weight
            + (0 if compliant else 50) * 0.20       # compliance penalty
        )

        results.append({
            "key": key,
            "arch": arch,
            "thermo": thermo,
            "fin": fin,
            "rel": rel,
            "compliant": compliant,
            "score": round(score, 2),
        })

    results.sort(key=lambda x: x["score"])
    return results


# ════════════════════════════════════════════════════════════
#  BUSINESS MODEL SCORING
# ════════════════════════════════════════════════════════════

@dataclass
class BusinessScenario:
    model: str        # "equipment_sale", "integrator", "thermal_as_service"
    country: str
    customer_type: str  # "hyperscale", "colo", "enterprise", "sovereign"
    annual_revenue: float
    margin: float
    market_size: float
    entry_barrier: str
    strategic_fit: float   # 0-100
    notes: str = ""


def score_business_cases(
    climate_key: str,
    reg_key: str,
    rack_kw: float = 100,
    n_racks: int = 200,
    reuse_fraction: float = 0.15,
    elec_price: float = 0.12,
) -> List[BusinessScenario]:
    """Evaluate Siemens Energy entry models for a given market."""
    reg = REGULATIONS[reg_key]

    # Run reference thermo for the market
    thermo = run_thermo_model("sp_coldplate", rack_kw, n_racks, climate_key,
                              reuse_fraction=reuse_fraction)
    Q_total_MW = thermo.Q_it / 1000

    scenarios = []

    # Model 1: Equipment sale (heat pumps, heat exchangers)
    equip_revenue = Q_total_MW * 0.3 * 1_200_000  # 30% capture × ~$1.2M/MW
    equip_margin = 0.25
    scenarios.append(BusinessScenario(
        "Equipment Sale", reg.name,
        "All", equip_revenue, equip_margin,
        Q_total_MW * 50,
        "Low" if reg.heat_reuse_mandate else "Medium",
        55 + (15 if reg.heat_reuse_mandate else 0),
        "Sell heat pumps & exchangers to DC operators / integrators",
    ))

    # Model 2: System integrator
    integ_revenue = Q_total_MW * 0.5 * 2_000_000
    integ_margin = 0.18
    scenarios.append(BusinessScenario(
        "System Integrator", reg.name,
        "Hyperscale / Colo", integ_revenue, integ_margin,
        Q_total_MW * 80,
        "Medium",
        70 + (10 if reg.heat_reuse_mandate else 0),
        "Turnkey thermal recovery: CDU interface → heat pump → district heating",
    ))

    # Model 3: Thermal-as-a-Service
    heat_revenue_annual = thermo.Q_reuse_annual_MWh * 45  # $/MWh avg
    taas_margin = 0.35
    scenarios.append(BusinessScenario(
        "Thermal-Energy-as-a-Service", reg.name,
        "Colo / Sovereign", heat_revenue_annual, taas_margin,
        Q_total_MW * 120,
        "High" if not reg.heat_reuse_mandate else "Low (regulation creates demand)",
        85 + (15 if reg.heat_reuse_mandate else -10),
        "Own recovery infra, sell heat to district networks; 15-20yr contracts",
    ))

    # Model 4: Integrated power+cooling campus
    campus_revenue = Q_total_MW * 3_500_000
    scenarios.append(BusinessScenario(
        "Integrated Campus (Power+Cooling)", reg.name,
        "Hyperscale / Sovereign", campus_revenue, 0.15,
        Q_total_MW * 200,
        "High",
        60 + (20 if Q_total_MW > 50 else 0),
        "Grid + generation + cooling + recovery; leverages Eaton partnership",
    ))

    scenarios.sort(key=lambda s: s.strategic_fit, reverse=True)
    return scenarios
