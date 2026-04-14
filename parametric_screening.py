"""
Page A – Parametric Screening Tool
===================================
Input rack density, climate, prices, regulation → 
output best-fit cooling architecture with full KPIs.
"""

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd

from engine.core_engine import (
    ARCHITECTURES, CLIMATES, REGULATIONS,
    screen_architectures, CoolingArch,
)


def render():
    st.markdown("# 🔎 Parametric Screening Tool")
    st.markdown(
        "Configure your data center scenario below. "
        "The model scores **all viable cooling architectures** and ranks them by "
        "a weighted composite of TCO, reliability, efficiency, water use, and regulatory compliance."
    )

    # ── Inputs ────────────────────────────────────────────
    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("#### 🖥️ Facility")
        rack_kw = st.slider("Rack power density (kW)", 10, 300, 80, 5)
        n_racks = st.slider("Number of racks", 10, 2000, 200, 10)
        total_mw = rack_kw * n_racks / 1000
        st.metric("Total IT load", f"{total_mw:.1f} MW")

    with col2:
        st.markdown("#### 🌍 Location & Climate")
        climate = st.selectbox("Climate zone", list(CLIMATES.keys()), index=0)
        regulation = st.selectbox("Regulation regime", list(REGULATIONS.keys()), index=0)
        clim = CLIMATES[climate]
        st.caption(
            f"Avg temp: {clim['T_avg']}°C · Design: {clim['T_design']}°C · "
            f"Free-cool hrs: {clim['free_cool_hrs']:,}/yr"
        )

    with col3:
        st.markdown("#### 💵 Economics")
        elec_price = st.number_input("Electricity ($/kWh)", 0.03, 0.40, 0.12, 0.01)
        water_price = st.number_input("Water ($/kL)", 0.5, 15.0, 3.0, 0.5)
        reuse_frac = st.slider("Heat reuse fraction", 0.0, 0.50, 0.10, 0.05)

    st.markdown("---")

    # ── Run Screening ─────────────────────────────────────
    results = screen_architectures(
        rack_kw, climate, elec_price, water_price, reuse_frac, regulation, n_racks
    )

    if not results:
        st.error("No architecture supports the requested rack density. Lower the kW/rack value.")
        return

    # ── Winner banner ─────────────────────────────────────
    best = results[0]
    reg = REGULATIONS[regulation]

    st.markdown("### 🏆 Recommended Architecture")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Architecture", best["arch"].short)
    c2.metric("PUE", f"{best['thermo'].pue:.3f}")
    c3.metric("10-yr NPV", f"${best['fin'].npv_10yr:,.0f}")
    c4.metric("Payback", f"{best['fin'].payback_years:.1f} yr")

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("WUE", f"{best['thermo'].wue:.2f} L/kWh")
    c6.metric("ERF", f"{best['thermo'].erf:.0%}")
    c7.metric("ΔT", f"{best['thermo'].delta_T:.1f}°C")
    c8.metric("Uptime", f"{best['rel'].uptime_percent:.4f}%")

    if best["compliant"]:
        st.success(f"✅ Fully compliant with **{regulation}** (PUE ≤ {reg.max_pue}, ERF ≥ {reg.erf_target:.0%})")
    else:
        st.warning(f"⚠️ Does **not** fully meet **{regulation}** requirements")

    # ── Comparison table ──────────────────────────────────
    st.markdown("### 📊 All Architectures Ranked")

    rows = []
    for r in results:
        rows.append({
            "Rank": results.index(r) + 1,
            "Architecture": r["arch"].short,
            "PUE": r["thermo"].pue,
            "WUE (L/kWh)": r["thermo"].wue,
            "ERF": f"{r['thermo'].erf:.0%}",
            "ΔT (°C)": round(r["thermo"].delta_T, 1),
            "CapEx ($M)": round(r["fin"].capex / 1e6, 2),
            "Net OPEX ($M/yr)": round(r["fin"].net_annual_opex / 1e6, 2),
            "Payback (yr)": r["fin"].payback_years,
            "NPV ($M)": round(r["fin"].npv_10yr / 1e6, 2),
            "IRR (%)": r["fin"].irr_10yr,
            "Uptime (%)": r["rel"].uptime_percent,
            "Compliant": "✅" if r["compliant"] else "❌",
            "Score": r["score"],
        })

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    # ── Radar chart ───────────────────────────────────────
    st.markdown("### 🕸️ Multi-Criteria Comparison")

    categories = ["Efficiency\n(1/PUE)", "Water\n(1/WUE)", "Cost\n(1/TCO)",
                   "Reliability\n(Uptime)", "Heat Reuse\n(ERF)", "Density\nHeadroom"]

    fig = go.Figure()
    colors = px.colors.qualitative.Set2

    for i, r in enumerate(results[:5]):  # top 5
        arch = r["arch"]
        # Normalize each metric to 0-1 for radar
        eff = 1 / max(r["thermo"].pue, 1.01)
        water = 1 / max(r["thermo"].wue + 0.1, 0.1)
        cost = 1 / max(r["fin"].tco_10yr / 1e8, 0.01)
        rel = r["rel"].availability
        reuse = r["thermo"].erf * 5  # scale up
        headroom = (arch.max_rack_kw - rack_kw) / max(arch.max_rack_kw, 1)

        vals = [eff, min(water, 1), min(cost, 1), rel, min(reuse, 1), max(headroom, 0)]
        # Normalize to 0-1 range
        vmax = max(vals) if max(vals) > 0 else 1
        vals_norm = [v / vmax for v in vals]

        fig.add_trace(go.Scatterpolar(
            r=vals_norm + [vals_norm[0]],
            theta=categories + [categories[0]],
            name=arch.short,
            fill="toself",
            opacity=0.6,
            line=dict(color=colors[i % len(colors)]),
        ))

    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 1.1])),
        template="plotly_dark",
        height=480,
        margin=dict(l=80, r=80, t=40, b=40),
        legend=dict(orientation="h", y=-0.15),
    )
    st.plotly_chart(fig, use_container_width=True)

    # ── Cost breakdown bar chart ──────────────────────────
    st.markdown("### 💰 10-Year TCO Breakdown")

    tco_data = []
    for r in results[:6]:
        tco_data.append({"Architecture": r["arch"].short, "Component": "CapEx", "Value": r["fin"].capex / 1e6})
        tco_data.append({"Architecture": r["arch"].short, "Component": "Energy", "Value": r["fin"].annual_energy_cost * 10 / 1e6})
        tco_data.append({"Architecture": r["arch"].short, "Component": "Water", "Value": r["fin"].annual_water_cost * 10 / 1e6})
        tco_data.append({"Architecture": r["arch"].short, "Component": "Maintenance", "Value": r["fin"].annual_maintenance * 10 / 1e6})
        tco_data.append({"Architecture": r["arch"].short, "Component": "Heat Revenue", "Value": -r["fin"].annual_heat_revenue * 10 / 1e6})

    df_tco = pd.DataFrame(tco_data)
    fig_tco = px.bar(
        df_tco, x="Architecture", y="Value", color="Component",
        barmode="relative",
        labels={"Value": "$ Million (10yr)"},
        color_discrete_map={
            "CapEx": "#58a6ff", "Energy": "#f85149",
            "Water": "#d29922", "Maintenance": "#8b949e",
            "Heat Revenue": "#3fb950",
        },
        template="plotly_dark",
    )
    fig_tco.update_layout(height=420, margin=dict(t=30))
    st.plotly_chart(fig_tco, use_container_width=True)
