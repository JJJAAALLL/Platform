"""
events.py — Event ledger table for the selected organisation.
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from db import get_events, get_event_chain

def render():
    org    = st.session_state["org"]
    user   = st.session_state["user"]
    org_id = int(org["organization_id"])

    st.title(f"📋 Events — {org['name']}")
    st.caption(f"{org['org_type']}")
    st.markdown("---")

    df = get_events(org_id, user)
    if df.empty:
        st.info("No events found for this organisation.")
        return

    df["local_timestamp"] = pd.to_datetime(df["local_timestamp"])

    # ── Filters ──────────────────────────────────────────────
    col1, col2, col3 = st.columns(3)
    with col1:
        all_types = ["All"] + sorted(df["event_type"].unique().tolist())
        type_filter = st.selectbox("Event type", all_types)
    with col2:
        all_vis = ["All"] + sorted(df["visibility"].unique().tolist())
        vis_filter = st.selectbox("Visibility", all_vis)
    with col3:
        date_range = st.date_input("Date range",
            value=(df["local_timestamp"].min().date(), df["local_timestamp"].max().date()))

    filtered = df.copy()
    if type_filter != "All":
        filtered = filtered[filtered["event_type"] == type_filter]
    if vis_filter != "All":
        filtered = filtered[filtered["visibility"] == vis_filter]
    if len(date_range) == 2:
        start, end = pd.Timestamp(date_range[0]), pd.Timestamp(date_range[1])
        filtered = filtered[(filtered["local_timestamp"] >= start) &
                            (filtered["local_timestamp"] <= end)]

    st.markdown(f"**{len(filtered)} events** matching filters (out of {len(df)} total)")

    # ── Timeline chart ────────────────────────────────────────
    if not filtered.empty:
        timeline = filtered.groupby([filtered["local_timestamp"].dt.date, "event_type"]).size().reset_index()
        timeline.columns = ["date", "event_type", "count"]
        fig = px.bar(timeline, x="date", y="count", color="event_type",
                     title="Events over time", labels={"date": "Date", "count": "Count"})
        fig.update_layout(height=280, margin=dict(t=40, b=10))
        st.plotly_chart(fig, use_container_width=True)

    # ── Table ────────────────────────────────────────────────
    st.dataframe(
        filtered[["event_id","event_type","operator","role","instrument","local_timestamp","visibility","location_text","soft_data","results","linked_event_ids","amount_added_tonnes","order_amount_tonnes","delivery_status"]]
        .rename(columns={
            "event_id":       "ID",
            "event_type":     "Type",
            "operator":       "Operator",
            "role":           "Role",
            "instrument":     "Instrument",
            "local_timestamp":"Timestamp",
            "visibility":     "Visibility",
            "location_text":  "Location",
            "soft_data":      "Soft data / block note",
            "results":        "Results",
            "linked_event_ids":"Referenced event blocks",
            "amount_added_tonnes":"Stored (t)",
            "order_amount_tonnes":"Ordered (t)",
            "delivery_status":"Delivery",
        })
        .reset_index(drop=True),
        use_container_width=True,
        height=420,
    )

    # ── Chain explorer ────────────────────────────────────────
    st.markdown("---")
    st.subheader("🔗 Event chain explorer")
    st.caption("Walk backward through previous_event_id within your read permissions.")
    event_ids = filtered["event_id"].tolist()
    chosen_id = st.selectbox("Pick an event ID to trace", event_ids[:50])

    if chosen_id:
        chain_df = get_event_chain(chosen_id, user)
        if not chain_df.empty:
            st.dataframe(chain_df, use_container_width=True)
        else:
            st.info("No chain found.")
