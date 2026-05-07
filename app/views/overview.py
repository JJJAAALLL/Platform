"""
overview.py — Organisation summary cards + analyte charts.
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from db import get_org_materials, get_results_for_org, get_last_measurement, get_events

def render():
    org = st.session_state["org"]
    user = st.session_state["user"]
    org_id = int(org["organization_id"])

    st.title(f"📊 {org['name']}")
    st.caption(f"Code: {org['code']}  ·  Type: {org['org_type']}")
    st.markdown("---")

    # ── Summary cards ────────────────────────────────────────
    last = get_last_measurement(org_id, user)
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("👥 Users",       int(org["user_count"]))
    c2.metric("🔬 Instruments", int(org["instrument_count"]))
    c3.metric("📝 Events",      int(org["event_count"]))
    c4.metric("🌾 Farm Size",   f"{org['size_ha']:.0f} ha" if pd.notna(org["size_ha"]) else "N/A")
    c5.metric("🕒 Last Scan",   last["local_timestamp"][:10] if last else "—")

    st.markdown("---")

    # ── Materials handled ────────────────────────────────────
    col_a, col_b = st.columns([1, 2])
    with col_a:
        st.subheader("Materials handled")
        mats = get_org_materials(org_id, user)
        if mats.empty:
            st.info("No materials registered.")
        else:
            for _, row in mats.iterrows():
                st.markdown(f"- **{row['name']}** `{row['category']}`")

    # ── Analyte results chart ────────────────────────────────
    with col_b:
        st.subheader("Analyte results over time")
        df = get_results_for_org(org_id, user)
        if df.empty:
            st.info("No measurement results yet.")
        else:
            df["local_timestamp"] = pd.to_datetime(df["local_timestamp"])
            analytes = df["analyte"].unique().tolist()
            selected = st.multiselect("Filter analytes", analytes, default=analytes[:3])
            filtered = df[df["analyte"].isin(selected)]
            if not filtered.empty:
                fig = px.line(filtered, x="local_timestamp", y="value",
                              color="analyte", markers=True,
                              labels={"local_timestamp": "Date", "value": "Value (%)", "analyte": "Analyte"},
                              title="Predicted analyte values")
                fig.update_layout(height=350, margin=dict(t=40, b=20))
                st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    # ── Event type distribution ──────────────────────────────
    st.subheader("Event type distribution")
    ev = get_events(org_id, user)
    if not ev.empty:
        dist = ev["event_type"].value_counts().reset_index()
        dist.columns = ["Event Type", "Count"]
        fig2 = px.bar(dist, x="Event Type", y="Count",
                      color="Event Type", title="Events by type")
        fig2.update_layout(height=300, showlegend=False, margin=dict(t=40, b=20))
        st.plotly_chart(fig2, use_container_width=True)

    # ── Farm address ────────────────────────────────────────
    if pd.notna(org.get("address")):
        st.markdown("---")
        st.subheader("Farm location details")
        c1, c2, c3 = st.columns(3)
        c1.markdown(f"**Address:** {org['address']}")
        c2.markdown(f"**Country:** {org['country']}")
        c3.markdown(f"**Coordinates:** {org['lat']:.4f}, {org['lon']:.4f}")
