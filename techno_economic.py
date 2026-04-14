"""
Page C – Techno-Economic Comparison
=====================================
Compare 4–6 architectures under multiple scenarios.
Side-by-side financials, sensitivity analysis, scenario matrix.
"""

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np

from pages.core_engine import (
    ARCHITECTURES, CLIMATES, REGULATIONS,
    run_thermo_model, run_financial_model, estimate_reliability,
)


def render():
    st.markdown("# 💰 Techno-Economic Comparison")
    st.markdown(
        "Compare cooling architectures across **multiple scenarios** — "
        "varying electricity price, climate, regulation, and rack density."
    )

    # ── Scenario configuration ────────────────────────────
    st.markdown("### Scenario Setup")

    col1, col2 = st.columns(2)

    with col1:
        selected_archs = st.multiselect(
            "Architectures to compare",
            list(ARCHITECTURES.keys()),
            default=["air", "air_rdhx", "sp_coldplate", "2p_coldplate", "sp_immersion"],
            format_func=lambda k: ARCHITECTURES[k].short,
        )

    with col2:
        selected_climates = st.multiselect(
            "Climate zones",
            list(CLIMATES.keys()),
            default=["Frankfurt (DE)", "Phoenix (US-AZ)", "Singapore (SG)"],
        )

    c1, c2, c3 = st.columns(3)
    with c1:
        rack_kw = st.slider("Rack density (kW)", 10, 250, 80, 10, key="te_rack")
        n_racks = st.slider("Number of racks", 50, 1000, 200, 50, key="te_nracks")
    with c2:
        elec_price = st.number_input("Electricity ($/kWh)", 0.03, 0.40, 0.12, 0.01, key="te_elec")
        water_price = st.number_input("Water ($/kL)", 0.5, 15.0, 3.0, 0.5, key="te_water")
    with c3:
        reuse_frac = st.slider("Heat reuse", 0.0, 0.40, 0.10, 0.05, key="te_reuse")
        heat_sale = st.number_input("Heat sale price ($/MWh)", 0, 100, 40, 5)

    if not selected_archs or not selected_climates:
        st.warning("Select at least one architecture and one climate zone.")
        return

    st.markdown("---")

    # ── Run all combinations ──────────────────────────────
    all_results = []
    for clim_key in selected_climates:
        for arch_key in selected_archs:
            arch = ARCHITECTURES[arch_key]
            if rack_kw > arch.max_rack_kw:
                continue

            thermo = run_thermo_model(arch_key, rack_kw, n_racks, clim_key,
                                      reuse_fraction=reuse_frac)
            fin = run_financial_model(arch_key, thermo, elec_price, water_price,
                                      heat_sale_price=heat_sale)
            rel = estimate_reliability(arch_key)

            all_results.append({
                "Climate": clim_key.split("(")[0].strip(),
                "Architecture": arch.short,
                "arch_key": arch_key,
                "PUE": thermo.pue,
                "WUE": thermo.wue,
                "ERF": thermo.erf,
                "ΔT (°C)": thermo.delta_T,
                "CapEx ($M)": fin.capex / 1e6,
                "OPEX ($M/yr)": fin.net_annual_opex / 1e6,
                "TCO 10yr ($M)": fin.tco_10yr / 1e6,
                "Payback (yr)": fin.payback_years,
                "NPV ($M)": fin.npv_10yr / 1e6,
                "IRR (%)": fin.irr_10yr,
                "Energy ($M/yr)": fin.annual_energy_cost / 1e6,
                "Water ($M/yr)": fin.annual_water_cost / 1e6,
                "Heat Rev ($M/yr)": fin.annual_heat_revenue / 1e6,
                "Savings vs Air ($M/yr)": fin.savings_vs_air / 1e6,
                "Uptime (%)": rel.uptime_percent,
                "MTBF (kh)": rel.mtbf_hours / 1000,
                "MTTR (h)": rel.mttr_hours,
            })

    if not all_results:
        st.error("No valid architecture-climate combinations found.")
        return

    df = pd.DataFrame(all_results)

    # ── Summary table ─────────────────────────────────────
    st.markdown("### 📋 Full Comparison Matrix")
    display_cols = [c for c in df.columns if c != "arch_key"]
    st.dataframe(
        df[display_cols].style.format({
            "PUE": "{:.3f}", "WUE": "{:.2f}", "ERF": "{:.0%}",
            "ΔT (°C)": "{:.1f}", "CapEx ($M)": "${:.2f}M",
            "OPEX ($M/yr)": "${:.2f}M", "TCO 10yr ($M)": "${:.2f}M",
            "Payback (yr)": "{:.1f}", "NPV ($M)": "${:.2f}M",
            "IRR (%)": "{:.1f}%", "Uptime (%)": "{:.4f}%",
        }),
        use_container_width=True, hide_index=True,
    )

    # ── TCO comparison chart ──────────────────────────────
    st.markdown("### 📊 10-Year TCO Comparison")

    fig_tco = px.bar(
        df, x="Architecture", y="TCO 10yr ($M)", color="Climate",
        barmode="group",
        color_discrete_sequence=px.colors.qualitative.Set2,
        template="plotly_dark",
    )
    fig_tco.update_layout(height=420, margin=dict(t=30), yaxis_title="TCO ($ Million, 10yr)")
    st.plotly_chart(fig_tco, use_container_width=True)

    # ── NPV comparison ────────────────────────────────────
    st.markdown("### 📈 NPV vs Payback Period")

    fig_npv = px.scatter(
        df, x="Payback (yr)", y="NPV ($M)",
        color="Architecture", symbol="Climate",
        size="CapEx ($M)", size_max=25,
        template="plotly_dark",
        hover_data=["PUE", "IRR (%)"],
    )
    fig_npv.add_hline(y=0, line_dash="dash", line_color="#8b949e", opacity=0.5)
    fig_npv.add_vline(x=3, line_dash="dash", line_color="#3fb950", opacity=0.3,
                      annotation_text="3yr payback target")
    fig_npv.update_layout(height=450, margin=dict(t=30))
    st.plotly_chart(fig_npv, use_container_width=True)

    # ── Sensitivity: electricity price ────────────────────
    st.markdown("### ⚡ Sensitivity: Electricity Price Impact on OPEX")

    elec_range = np.arange(0.04, 0.35, 0.02)
    sens_data = []
    ref_climate = selected_climates[0]

    for ep in elec_range:
        for arch_key in selected_archs:
            arch = ARCHITECTURES[arch_key]
            if rack_kw > arch.max_rack_kw:
                continue
            thermo = run_thermo_model(arch_key, rack_kw, n_racks, ref_climate,
                                      reuse_fraction=reuse_frac)
            fin = run_financial_model(arch_key, thermo, float(ep), water_price,
                                      heat_sale_price=heat_sale)
            sens_data.append({
                "Elec Price ($/kWh)": round(ep, 2),
                "Architecture": arch.short,
                "Net OPEX ($M/yr)": fin.net_annual_opex / 1e6,
            })

    df_sens = pd.DataFrame(sens_data)
    fig_sens = px.line(
        df_sens, x="Elec Price ($/kWh)", y="Net OPEX ($M/yr)",
        color="Architecture", template="plotly_dark",
        markers=True,
    )
    fig_sens.add_vline(x=elec_price, line_dash="dash", line_color="#f85149",
                       annotation_text="Current price")
    fig_sens.update_layout(height=400, margin=dict(t=30))
    st.plotly_chart(fig_sens, use_container_width=True)

    # ── Sensitivity: rack density ─────────────────────────
    st.markdown("### 🔥 Sensitivity: Rack Density Impact on TCO")

    dens_range = np.arange(20, 260, 20)
    dens_data = []

    for d in dens_range:
        for arch_key in selected_archs:
            arch = ARCHITECTURES[arch_key]
            if d > arch.max_rack_kw:
                continue
            thermo = run_thermo_model(arch_key, float(d), n_racks, ref_climate,
                                      reuse_fraction=reuse_frac)
            fin = run_financial_model(arch_key, thermo, elec_price, water_price,
                                      heat_sale_price=heat_sale)
            dens_data.append({
                "Rack Density (kW)": int(d),
                "Architecture": arch.short,
                "TCO 10yr ($M)": fin.tco_10yr / 1e6,
                "PUE": thermo.pue,
            })

    df_dens = pd.DataFrame(dens_data)
    fig_dens = px.line(
        df_dens, x="Rack Density (kW)", y="TCO 10yr ($M)",
        color="Architecture", template="plotly_dark", markers=True,
    )
    fig_dens.update_layout(height=400, margin=dict(t=30))
    st.plotly_chart(fig_dens, use_container_width=True)

    # ── Heatmap: architecture × climate ───────────────────
    if len(selected_climates) > 1 and len(selected_archs) > 1:
        st.markdown("### 🗺️ Heatmap: NPV by Architecture × Climate")

        pivot = df.pivot_table(
            values="NPV ($M)", index="Architecture", columns="Climate", aggfunc="first"
        )
        fig_heat = px.imshow(
            pivot.values,
            x=pivot.columns.tolist(),
            y=pivot.index.tolist(),
            color_continuous_scale="RdYlGn",
            aspect="auto",
            labels=dict(color="NPV ($M)"),
            template="plotly_dark",
        )
        fig_heat.update_layout(height=350, margin=dict(t=30))
        st.plotly_chart(fig_heat, use_container_width=True)
