"""
Page D – Business-Case Optimizer
=================================
Where should Siemens Energy enter?
Equipment sale, integrator, or thermal-as-a-service?
Which countries and customer types first?
"""

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np

from engine.core_engine import (
    ARCHITECTURES, CLIMATES, REGULATIONS,
    run_thermo_model, run_financial_model,
    score_business_cases, BusinessScenario,
)


def render():
    st.markdown("# 🏢 Business-Case Optimizer")
    st.markdown(
        "Evaluate **Siemens Energy's optimal entry strategy** into the data center cooling market. "
        "The model scores four business models across geographies, leveraging "
        "Siemens Energy's existing capabilities in heat pumps, turbomachinery, and grid infrastructure."
    )

    # ── Siemens Energy capability summary ─────────────────
    with st.expander("📌 Siemens Energy Positioning (from analysis)", expanded=False):
        st.markdown("""
        **Existing assets:**
        - Industrial heat pumps up to **70 MWth** per unit, operating to **150°C**
        - Proven installations: Qwark3 Berlin (8 MWth, 85–120°C), MVV Mannheim (20 MWth, 99°C)
        - Eaton partnership for **500 MW modular power** reference designs
        - €39.1B FY2025 revenue, €138B order backlog
        - Data Centers as explicit industry solution vertical
        
        **Strategic sweet spot:** The thermal interface between DC liquid loops and district heating — 
        where no dominant player exists and regulatory mandates (Germany EnEfG, EU directives) 
        create captive demand for exactly the systems Siemens Energy manufactures.
        """)

    st.markdown("---")

    # ── Market configuration ──────────────────────────────
    st.markdown("### Market Parameters")
    col1, col2, col3 = st.columns(3)

    with col1:
        selected_markets = st.multiselect(
            "Target markets",
            list(REGULATIONS.keys()),
            default=["Germany (EnEfG)", "EU (avg)", "Nordics (avg)", "US (federal)", "Singapore"],
        )

    with col2:
        rack_kw = st.slider("Target rack density (kW)", 40, 200, 100, 10, key="bc_rack")
        n_racks = st.slider("Reference campus size (racks)", 100, 1000, 300, 50, key="bc_nracks")

    with col3:
        elec_price = st.number_input("Avg electricity ($/kWh)", 0.04, 0.35, 0.12, 0.01, key="bc_elec")
        reuse_frac = st.slider("Expected heat reuse", 0.0, 0.40, 0.15, 0.05, key="bc_reuse")

    if not selected_markets:
        st.warning("Select at least one market.")
        return

    # ── Map regulation → climate ──────────────────────────
    reg_climate_map = {
        "Germany (EnEfG)": "Frankfurt (DE)",
        "EU (avg)": "Amsterdam (NL)",
        "Netherlands": "Amsterdam (NL)",
        "Singapore": "Singapore (SG)",
        "US (federal)": "Ashburn (US-VA)",
        "US (Arizona)": "Phoenix (US-AZ)",
        "Nordics (avg)": "Stockholm (SE)",
        "Middle East (avg)": "Riyadh (SA)",
    }

    # ── Score all business cases ──────────────────────────
    all_scenarios = []
    for reg_key in selected_markets:
        clim_key = reg_climate_map.get(reg_key, "Frankfurt (DE)")
        scenarios = score_business_cases(clim_key, reg_key, rack_kw, n_racks, reuse_frac, elec_price)
        for s in scenarios:
            all_scenarios.append({
                "Market": s.country,
                "Business Model": s.model,
                "Customer": s.customer_type,
                "Annual Revenue ($M)": s.annual_revenue / 1e6,
                "Margin": f"{s.margin:.0%}",
                "Annual Profit ($M)": s.annual_revenue * s.margin / 1e6,
                "Entry Barrier": s.entry_barrier,
                "Strategic Fit (0-100)": s.strategic_fit,
                "Notes": s.notes,
                "margin_val": s.margin,
                "strategic_fit_val": s.strategic_fit,
                "revenue_val": s.annual_revenue / 1e6,
            })

    df = pd.DataFrame(all_scenarios)

    # ── Top recommendation ────────────────────────────────
    st.markdown("---")
    st.markdown("### 🏆 Top Strategic Recommendations")

    top = df.nlargest(3, "strategic_fit_val")
    for i, (_, row) in enumerate(top.iterrows()):
        medal = ["🥇", "🥈", "🥉"][i]
        st.markdown(
            f"**{medal} {row['Business Model']}** in **{row['Market']}** — "
            f"Strategic Fit: **{row['strategic_fit_val']:.0f}/100** · "
            f"Revenue: **${row['revenue_val']:.1f}M/yr** · "
            f"Margin: **{row['Margin']}** · "
            f"Barrier: {row['Entry Barrier']}"
        )
        st.caption(f"→ {row['Notes']}")

    # ── Full scoring table ────────────────────────────────
    st.markdown("### 📋 Full Business Model Scoring")

    display_cols = ["Market", "Business Model", "Customer", "Annual Revenue ($M)",
                    "Margin", "Annual Profit ($M)", "Entry Barrier",
                    "Strategic Fit (0-100)", "Notes"]
    st.dataframe(
        df[display_cols].sort_values("Strategic Fit (0-100)", ascending=False),
        use_container_width=True, hide_index=True,
    )

    # ── Strategic fit × revenue bubble chart ──────────────
    st.markdown("### 💎 Strategic Fit vs Revenue Opportunity")

    fig_bubble = px.scatter(
        df, x="Strategic Fit (0-100)", y="Annual Revenue ($M)",
        color="Business Model", symbol="Market",
        size="Annual Profit ($M)", size_max=30,
        hover_data=["Customer", "Entry Barrier", "Notes"],
        template="plotly_dark",
    )
    fig_bubble.add_vline(x=70, line_dash="dash", line_color="#3fb950", opacity=0.3,
                         annotation_text="High fit threshold")
    fig_bubble.update_layout(height=500, margin=dict(t=30))
    st.plotly_chart(fig_bubble, use_container_width=True)

    # ── Business model comparison by market ───────────────
    st.markdown("### 📊 Strategic Fit by Market & Model")

    fig_bar = px.bar(
        df.sort_values("strategic_fit_val", ascending=True),
        x="strategic_fit_val", y="Market",
        color="Business Model", barmode="group",
        orientation="h",
        labels={"strategic_fit_val": "Strategic Fit Score"},
        template="plotly_dark",
        color_discrete_sequence=px.colors.qualitative.Set2,
    )
    fig_bar.update_layout(height=450, margin=dict(t=30, l=120))
    st.plotly_chart(fig_bar, use_container_width=True)

    # ── Revenue heatmap ───────────────────────────────────
    st.markdown("### 🗺️ Revenue Potential Heatmap")

    pivot_rev = df.pivot_table(
        values="revenue_val", index="Business Model", columns="Market", aggfunc="first"
    )
    fig_heat = px.imshow(
        pivot_rev.values,
        x=pivot_rev.columns.tolist(),
        y=pivot_rev.index.tolist(),
        color_continuous_scale="Viridis",
        aspect="auto",
        labels=dict(color="Revenue ($M/yr)"),
        template="plotly_dark",
    )
    fig_heat.update_layout(height=350, margin=dict(t=30))
    st.plotly_chart(fig_heat, use_container_width=True)

    # ── Margin comparison ─────────────────────────────────
    st.markdown("### 📈 Margin × Revenue by Business Model")

    fig_margin = px.scatter(
        df, x="revenue_val", y="margin_val",
        color="Business Model", symbol="Market",
        size="strategic_fit_val", size_max=25,
        labels={"revenue_val": "Annual Revenue ($M)", "margin_val": "Margin (fraction)"},
        template="plotly_dark",
    )
    fig_margin.update_layout(height=400, margin=dict(t=30), yaxis_tickformat=".0%")
    st.plotly_chart(fig_margin, use_container_width=True)

    # ── Regulatory driver analysis ────────────────────────
    st.markdown("### 📜 Regulatory Drivers by Market")

    reg_rows = []
    for reg_key in selected_markets:
        reg = REGULATIONS[reg_key]
        reg_rows.append({
            "Market": reg.name,
            "Max PUE": reg.max_pue,
            "ERF Target": f"{reg.erf_target:.0%}",
            "Heat Reuse Mandate": "✅" if reg.heat_reuse_mandate else "❌",
            "Water Restricted": "✅" if reg.water_restricted else "❌",
            "F-Gas GWP Limit": reg.fgas_gwp_limit,
            "Carbon Price (€/t)": reg.carbon_price,
            "Notes": reg.notes,
        })

    st.dataframe(pd.DataFrame(reg_rows), use_container_width=True, hide_index=True)

    # ── Go-to-market timeline ─────────────────────────────
    st.markdown("### 🗓️ Recommended Go-to-Market Sequence")

    timeline = [
        ("Q3 2026", "Germany", "Lighthouse project with hyperscaler/colo (Qwark3 as proof point)"),
        ("Q4 2026", "Nordics", "Partner with district heating utilities; leverage Stockholm model"),
        ("Q1 2027", "Netherlands", "Capitalize on permitting requirements for heat capture"),
        ("Q2 2027", "EU broad", "Scale standardized modular product from Finspong factory"),
        ("H2 2027", "US (select)", "Target water-stressed regions (AZ, TX) with waterless cooling"),
        ("2028", "Singapore / ME", "Adapt for tropical/arid — emphasize waterless + efficiency"),
    ]

    fig_timeline = go.Figure()
    for i, (date, market, action) in enumerate(timeline):
        fig_timeline.add_trace(go.Scatter(
            x=[i], y=[0],
            mode="markers+text",
            marker=dict(size=20, color=px.colors.qualitative.Set2[i % 8]),
            text=[f"<b>{date}</b><br>{market}"],
            textposition="top center",
            hovertext=action,
            showlegend=False,
        ))

    fig_timeline.update_layout(
        xaxis=dict(showticklabels=False, showgrid=False, zeroline=False),
        yaxis=dict(showticklabels=False, showgrid=False, zeroline=False, range=[-0.5, 1.5]),
        template="plotly_dark",
        height=200,
        margin=dict(t=10, b=10, l=20, r=20),
    )
    st.plotly_chart(fig_timeline, use_container_width=True)

    for date, market, action in timeline:
        st.markdown(f"- **{date} – {market}:** {action}")

    # ── Key takeaway ──────────────────────────────────────
    st.markdown("---")
    st.markdown("### 🎯 Bottom Line")
    st.info(
        "**Highest-conviction entry: Thermal-Energy-as-a-Service** in Germany and Nordics, "
        "combining Siemens Energy's 70 MWth heat pumps with modular, prefabricated thermal recovery "
        "units deployed at data center campuses. This avoids CDU/cold-plate competition (Vertiv, Schneider) "
        "and captures value at the thermal interface between data centers and district energy networks — "
        "where mandatory heat reuse regulations create captive demand and no dominant player exists."
    )
