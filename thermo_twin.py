"""
Page B – Thermodynamic Digital Twin
====================================
Simplified but defensible plant model:
  rack → CDU → plant → heat recovery
Shows energy flows, Sankey diagram, CoolProp fluid properties,
and parametric sweeps.
"""

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np

from pages.core_engine import (
    ARCHITECTURES, CLIMATES,
    run_thermo_model, cp_fluid, latent_heat, saturation_pressure,
    ThermoResult,
)


def render():
    st.markdown("# 🔬 Thermodynamic Digital Twin")
    st.markdown(
        "A steady-state energy-balance model of the full thermal chain: "
        "**IT rack → liquid loop → CDU → chiller / dry-cooler → (optional) heat recovery**. "
        "Fluid properties from CoolProp."
    )

    # ── Inputs ────────────────────────────────────────────
    col1, col2 = st.columns(2)

    with col1:
        arch_key = st.selectbox(
            "Cooling Architecture",
            list(ARCHITECTURES.keys()),
            format_func=lambda k: ARCHITECTURES[k].name,
            index=2,
        )
        arch = ARCHITECTURES[arch_key]
        rack_kw = st.slider("Rack power (kW)", 10, int(arch.max_rack_kw), min(80, int(arch.max_rack_kw)), 5)
        n_racks = st.slider("Number of racks", 10, 1000, 100, 10)

    with col2:
        climate = st.selectbox("Climate", list(CLIMATES.keys()), index=0)
        T_supply = st.slider("Coolant supply temp (°C)", 10, 50, 25, 1)
        reuse_frac = st.slider("Heat reuse fraction", 0.0, 0.50, 0.10, 0.05)

    # ── Run model ─────────────────────────────────────────
    thermo = run_thermo_model(arch_key, rack_kw, n_racks, climate, T_supply, reuse_frac)

    # ── KPI row ───────────────────────────────────────────
    st.markdown("---")
    st.markdown("### Key Performance Indicators")
    k1, k2, k3, k4, k5, k6 = st.columns(6)
    k1.metric("PUE", f"{thermo.pue:.3f}")
    k2.metric("TUE", f"{thermo.tue:.3f}")
    k3.metric("WUE", f"{thermo.wue:.2f} L/kWh")
    k4.metric("ERF", f"{thermo.erf:.0%}")
    k5.metric("ΔT", f"{thermo.delta_T:.1f}°C")
    k6.metric("Coolant flow", f"{thermo.m_dot:.1f} kg/s")

    # ── Sankey diagram ────────────────────────────────────
    st.markdown("### Energy Flow (Sankey)")

    labels = [
        "Grid Power",           # 0
        "IT Equipment",         # 1
        "Useful Compute",       # 2
        "IT Heat",              # 3
        "Liquid Loop",          # 4
        "Air Loop",             # 5
        "Pumps",                # 6
        "Chiller",              # 7
        "Fans",                 # 8
        "Heat Rejection",       # 9
        "Heat Recovery",        # 10
        "Misc (UPS/BMS)",       # 11
    ]

    Q_it = thermo.Q_it
    Q_compute = Q_it * 0.85
    Q_it_heat = Q_it * 0.15 + thermo.Q_coolant + thermo.Q_air_residual - Q_it
    Q_liquid = thermo.Q_coolant
    Q_air = thermo.Q_air_residual
    W_pump = thermo.W_pump
    W_chiller = thermo.W_chiller
    W_fan = thermo.W_fan
    W_misc = Q_it * 0.02
    Q_reject = Q_liquid + W_pump + W_chiller - thermo.Q_reuse
    Q_reuse = thermo.Q_reuse

    total_grid = Q_it + thermo.W_total_facility

    source = [0, 0, 0, 0, 0, 1, 1, 3, 3, 4, 4, 5, 7]
    target = [1, 6, 7, 8, 11, 2, 3, 4, 5, 9, 10, 9, 9]
    value  = [
        Q_it,                           # grid → IT
        W_pump,                         # grid → pumps
        W_chiller,                      # grid → chiller
        W_fan,                          # grid → fans
        W_misc,                         # grid → misc
        Q_compute,                      # IT → useful compute
        Q_it - Q_compute,               # IT → IT heat
        Q_liquid,                       # IT heat → liquid
        Q_air,                          # IT heat → air
        max(Q_liquid - Q_reuse, 0),     # liquid → rejection
        max(Q_reuse, 0.01),             # liquid → recovery
        Q_air,                          # air → rejection
        W_chiller * 0.8,               # chiller → rejection (condenser)
    ]
    # Ensure no negatives
    value = [max(v, 0.01) for v in value]

    colors_node = [
        "#58a6ff", "#79c0ff", "#3fb950", "#f0883e",
        "#58a6ff", "#8b949e", "#d29922", "#f85149",
        "#d29922", "#8b949e", "#3fb950", "#6e7681",
    ]

    fig_sankey = go.Figure(go.Sankey(
        arrangement="snap",
        node=dict(
            pad=20, thickness=25,
            label=labels,
            color=colors_node,
        ),
        link=dict(
            source=source, target=target, value=value,
            color="rgba(88,166,255,0.15)",
        ),
    ))
    fig_sankey.update_layout(
        template="plotly_dark", height=450,
        margin=dict(l=20, r=20, t=30, b=20),
        font=dict(size=12),
    )
    st.plotly_chart(fig_sankey, use_container_width=True)

    # ── Power breakdown ───────────────────────────────────
    st.markdown("### Power Breakdown")
    p1, p2 = st.columns(2)

    with p1:
        fig_pie = go.Figure(go.Pie(
            labels=["IT Load", "Pumps", "Chiller", "Fans", "Misc"],
            values=[Q_it, W_pump, W_chiller, W_fan, W_misc],
            hole=0.45,
            marker_colors=["#58a6ff", "#d29922", "#f85149", "#8b949e", "#6e7681"],
        ))
        fig_pie.update_layout(template="plotly_dark", height=350, margin=dict(t=20, b=20))
        st.plotly_chart(fig_pie, use_container_width=True)

    with p2:
        st.markdown("**Facility power components:**")
        items = [
            ("IT equipment", Q_it),
            ("Pump power", W_pump),
            ("Chiller power", W_chiller),
            ("Fan power", W_fan),
            ("Misc (UPS/BMS)", W_misc),
            ("**Total from grid**", total_grid),
        ]
        for label, val in items:
            st.markdown(f"- {label}: **{val:,.0f} kW** ({val/total_grid*100:.1f}%)")

        st.markdown(f"\n- Heat recovered: **{thermo.Q_reuse:,.0f} kW** → **{thermo.Q_reuse_annual_MWh:,.0f} MWh/yr**")

    # ── CoolProp fluid property table ─────────────────────
    st.markdown("### 🧪 CoolProp Fluid Properties")
    st.caption("Properties at supply and return temperatures")

    try:
        fluid_name = "Water" if not arch.two_phase else "R1233zd(E)"
        props_supply = cp_fluid(fluid_name if fluid_name != "INCOMP::ExamplePure" else "Water", T_supply)
        props_return = cp_fluid(fluid_name if fluid_name != "INCOMP::ExamplePure" else "Water", thermo.T_return)

        df_props = pd.DataFrame({
            "Property": ["Density (kg/m³)", "Specific heat (J/kg·K)", "Viscosity (Pa·s)", "Conductivity (W/m·K)"],
            f"@ {T_supply}°C (supply)": [
                f"{props_supply['rho']:.2f}",
                f"{props_supply['cp']:.1f}",
                f"{props_supply['mu']:.6f}",
                f"{props_supply['k']:.4f}",
            ],
            f"@ {thermo.T_return:.0f}°C (return)": [
                f"{props_return['rho']:.2f}",
                f"{props_return['cp']:.1f}",
                f"{props_return['mu']:.6f}",
                f"{props_return['k']:.4f}",
            ],
        })
        st.dataframe(df_props, use_container_width=True, hide_index=True)

        if arch.two_phase:
            try:
                p_sat = saturation_pressure(fluid_name, T_supply)
                h_fg = latent_heat(fluid_name, T_supply)
                st.info(f"**{fluid_name}** at {T_supply}°C → P_sat = {p_sat:.1f} kPa, h_fg = {h_fg/1000:.1f} kJ/kg")
            except Exception:
                pass
    except Exception as e:
        st.warning(f"CoolProp lookup error: {e}")

    # ── Parametric sweep: PUE vs supply temperature ───────
    st.markdown("### 📈 Parametric Sweep: Supply Temperature → PUE")

    temps = np.arange(10, 46, 2)
    pues = []
    dTs = []
    for t in temps:
        r = run_thermo_model(arch_key, rack_kw, n_racks, climate, float(t), reuse_frac)
        pues.append(r.pue)
        dTs.append(r.delta_T)

    fig_sweep = go.Figure()
    fig_sweep.add_trace(go.Scatter(
        x=temps, y=pues, mode="lines+markers", name="PUE",
        line=dict(color="#58a6ff", width=2),
        marker=dict(size=6),
    ))
    fig_sweep.add_trace(go.Scatter(
        x=temps, y=dTs, mode="lines+markers", name="ΔT (°C)",
        yaxis="y2",
        line=dict(color="#3fb950", width=2, dash="dot"),
        marker=dict(size=6),
    ))
    fig_sweep.update_layout(
        xaxis_title="Coolant Supply Temperature (°C)",
        yaxis=dict(title="PUE", side="left"),
        yaxis2=dict(title="ΔT (°C)", side="right", overlaying="y"),
        template="plotly_dark",
        height=380,
        margin=dict(t=30),
        legend=dict(orientation="h", y=-0.2),
    )
    st.plotly_chart(fig_sweep, use_container_width=True)

    # ── Sweep: rack density → PUE ─────────────────────────
    st.markdown("### 📈 Rack Density Sweep")
    densities = np.arange(10, min(int(arch.max_rack_kw) + 10, 310), 10)
    pues_d = []
    for d in densities:
        if d <= arch.max_rack_kw:
            r = run_thermo_model(arch_key, float(d), n_racks, climate, float(T_supply), reuse_frac)
            pues_d.append(r.pue)
        else:
            pues_d.append(None)

    fig_dens = go.Figure()
    fig_dens.add_trace(go.Scatter(
        x=densities, y=pues_d, mode="lines+markers",
        line=dict(color="#d29922", width=2),
        marker=dict(size=5),
        name="PUE",
    ))
    fig_dens.add_vline(x=rack_kw, line_dash="dash", line_color="#f85149",
                       annotation_text=f"Current: {rack_kw} kW")
    fig_dens.update_layout(
        xaxis_title="Rack Power Density (kW/rack)",
        yaxis_title="PUE",
        template="plotly_dark", height=350, margin=dict(t=30),
    )
    st.plotly_chart(fig_dens, use_container_width=True)
