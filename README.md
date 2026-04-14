# AI Data Center Cooling — Thermodynamic & Techno-Economic Model

A Streamlit application for parametric screening, thermodynamic digital-twin modeling, techno-economic comparison, and business-case optimization of advanced cooling architectures for AI data centers.

## Features

### A. Parametric Screening Tool
- Input rack density, climate, electricity/water price, regulation
- Scores all viable cooling architectures (air, RDHx, SP/2P cold-plate, SP/2P immersion)
- Outputs: best-fit architecture, PUE, WUE, ERF, ΔT, uptime, TCO, NPV, payback
- Radar chart comparison and 10-year TCO breakdown

### B. Thermodynamic Digital Twin
- Steady-state energy balance: rack → CDU → chiller/dry-cooler → heat recovery
- CoolProp fluid properties (water, R-1233zd(E)) at operating conditions
- Sankey energy flow diagram
- Parametric sweeps: supply temperature vs PUE, rack density vs PUE

### C. Techno-Economic Comparison
- Side-by-side comparison of 4-6 architectures across multiple climates
- Sensitivity analysis: electricity price, rack density
- NPV vs payback scatter, TCO heatmap by architecture × climate
- Full financial metrics: CapEx, OPEX, NPV, IRR, payback

### D. Business-Case Optimizer
- Evaluates Siemens Energy entry strategies: equipment sale, system integrator, thermal-as-a-service, integrated campus
- Scores by market (Germany, Nordics, EU, US, Singapore, Middle East)
- Strategic fit scoring, revenue/margin analysis, regulatory driver matrix
- Go-to-market timeline recommendation

## Thermodynamic Model

The core engine uses **CoolProp** for:
- Water/glycol properties (ρ, cp, μ, k) at operating temperatures
- Refrigerant saturation pressure and latent heat for two-phase systems (R-1233zd(E))
- Carnot-bounded chiller COP with second-law efficiency (η_II ≈ 0.55)

Energy balance per architecture:
- Single-phase: Q̇ = ṁ · cp · ΔT
- Two-phase: Q̇ = ṁ · h_fg
- Pump power: W_pump = V̇ · ΔP / η_pump
- Chiller: COP = η_II · T_evap / (T_cond - T_evap), with free-cooling fraction from climate data
- PUE = (Q_IT + W_facility) / Q_IT

## Setup

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Data Sources

- Vertiv/NVIDIA PUE studies
- Introl liquid cooling GPU guide
- Siemens Energy heat pump specifications
- Germany EnEfG, EU F-gas regulation, US AIM Act
- Microsoft zero-water datacenter design
- Industry CapEx/OPEX benchmarks from DCD, IntelMarketResearch

## File Structure

```
dc_cooling_model/
├── app.py                          # Main Streamlit entry point
├── requirements.txt
├── README.md
└── pages/
    ├── __init__.py
    ├── core_engine.py              # CoolProp thermo + financial engine
    ├── parametric_screening.py     # Page A
    ├── thermo_twin.py              # Page B
    ├── techno_economic.py          # Page C
    └── business_case.py            # Page D
```
