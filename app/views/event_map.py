"""Global event-block map for public/shared blocks and the user's private blocks."""
import os, sys
import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from db import get_event_blocks_for_map

EVENT_COLOR = {
    "MEASUREMENT": "blue",
    "FARM_UPDATE": "green",
    "SILO_UPDATE": "orange",
    "ORDER": "red",
    "DELIVERY": "purple",
    "SOFT_DATA": "gray",
    "METHOD_UPDATE": "cadetblue",
    "CALIBRATION_UPDATE": "darkblue",
    "INSTRUMENT_UPDATE": "black",
}


def render():
    user = st.session_state["user"]
    st.title("🌍 Supply-chain Event Blocks")
    st.caption("Public/shared blocks from every organisation are visible. Private blocks are shown only when they belong to your organisation.")

    blocks = get_event_blocks_for_map(user)
    if blocks.empty:
        st.info("No map-ready event blocks found.")
        return

    event_types = sorted(blocks["event_type"].dropna().unique().tolist())
    selected = st.multiselect("Event types", event_types, default=event_types)
    visibilities = sorted(blocks["visibility"].dropna().unique().tolist())
    selected_vis = st.multiselect("Visibility", visibilities, default=visibilities)
    filtered = blocks[blocks["event_type"].isin(selected) & blocks["visibility"].isin(selected_vis)]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Blocks on map", len(filtered))
    c2.metric("Public", int((filtered["visibility"] == "PUBLIC").sum()))
    c3.metric("Shared", int((filtered["visibility"] == "SHARED").sum()))
    c4.metric("Private (own org)", int((filtered["visibility"] == "PRIVATE").sum()))

    center = [float(filtered["lat"].mean()), float(filtered["lon"].mean())] if not filtered.empty else [50, 8]
    m = folium.Map(location=center, zoom_start=5, tiles="OpenStreetMap")
    for _, row in filtered.iterrows():
        extra = ""
        if pd.notna(row.get("amount_added_tonnes")):
            extra += f"<br>🌾 Stored: <b>{row['amount_added_tonnes']:.2f} t</b>"
        if pd.notna(row.get("order_amount_tonnes")):
            extra += f"<br>🧾 Ordered: <b>{row['order_amount_tonnes']:.2f} t</b>"
        if pd.notna(row.get("delivery_status")):
            extra += f"<br>🚚 Delivery: <b>{row['delivery_status']}</b>"
        popup = f"""
        <div style='font-family:sans-serif;min-width:240px'>
          <b>{row['event_type']} #{row['event_id']}</b> <span style='color:gray'>({row['visibility']})</span><br>
          🏢 {row['organization']} · {row['org_type']}<br>
          🕒 {str(row['local_timestamp'])[:19]}<br>
          📍 {row['location_text'] or ''}
          {extra}<hr style='margin:4px'>
          {row['note'] or ''}
        </div>
        """
        folium.Marker(
            location=[float(row["lat"]), float(row["lon"])],
            tooltip=f"{row['event_type']} #{row['event_id']} ({row['visibility']})",
            popup=folium.Popup(popup, max_width=320),
            icon=folium.Icon(color=EVENT_COLOR.get(row["event_type"], "gray"), icon="cube", prefix="fa"),
        ).add_to(m)
    st_folium(m, width="100%", height=560)

    st.subheader("Visible event blocks")
    st.dataframe(
        filtered[["event_id", "event_type", "organization", "org_type", "visibility", "local_timestamp", "note"]]
        .rename(columns={"event_id": "ID", "event_type": "Type", "organization": "Organisation", "org_type": "Org Type", "visibility": "Visibility", "local_timestamp": "Timestamp", "note": "Block note"}),
        use_container_width=True,
        height=300,
    )
