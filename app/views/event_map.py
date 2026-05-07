"""Global event-block map for public/shared blocks and the user's private blocks."""
import html
import os, sys

import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from db import get_deliverable_orders, get_event_blocks_for_map, get_measurement_results_for_events, get_orderable_blocks
from services.farm_service import place_order, take_delivery

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

DEFECT_FIELDS = {"Percentage of Good", "Broken Percentage", "Damaged Percentage", "Foreign Matter Percentage"}


def _query_focus_event_id():
    raw = st.query_params.get("focus_event_id")
    if isinstance(raw, list):
        raw = raw[0] if raw else None
    try:
        return int(raw) if raw else None
    except (TypeError, ValueError):
        return None


def _set_focus_event(event_id):
    st.session_state["focused_event_id"] = int(event_id)
    st.query_params["focus_event_id"] = str(int(event_id))


def _parse_id_csv(value):
    if pd.isna(value) or value in (None, ""):
        return []
    return [int(part) for part in str(value).split(",") if part.strip().isdigit()]


def _related_event_ids(row):
    related = _parse_id_csv(row.get("linked_event_ids"))
    previous = row.get("previous_event_id")
    if pd.notna(previous):
        related.append(int(previous))
    return list(dict.fromkeys(related))


def _result_cell(label, value, defect=False):
    safe_label = html.escape(label)
    safe_value = html.escape(value or "—")
    border = "#f59e0b" if defect else "#d1d5db"
    background = "#fff7ed" if defect else "#f9fafb"
    return (
        f"<div style='border:1px solid {border};border-radius:8px;padding:6px 8px;background:{background};margin:3px 0'>"
        f"<span style='color:#6b7280;font-size:11px'>{safe_label}</span><br>"
        f"<b>{safe_value}</b></div>"
    )


def _measurement_results_html(measurements):
    if not measurements:
        return "<div style='color:#6b7280'>No measurement results attached to this block.</div>"
    sections = []
    for measurement in measurements:
        chemical = "".join(_result_cell(label, value) for label, value in measurement["chemical"].items())
        classification = "".join(_result_cell(label, value) for label, value in measurement["classification"].items())
        defects = "".join(_result_cell(label, value, label in DEFECT_FIELDS) for label, value in measurement["defects"].items())
        sections.append(
            f"""
            <div style='border:1px solid #e5e7eb;border-radius:10px;padding:8px;margin-top:6px;background:#ffffff'>
              <b>Results from MEASUREMENT #{measurement['measurement_event_id']}</b><br>
              <span style='color:#6b7280;font-size:11px'>{html.escape(str(measurement.get('timestamp') or '')[:19])}</span>
              <div style='margin-top:6px'><b>Chemical properties</b>{chemical}</div>
              <div style='margin-top:6px'><b>Classification</b>{classification}</div>
              <div style='margin-top:6px'><b>Defect percentages</b>{defects}</div>
            </div>
            """
        )
    return "".join(sections)


def _links_html(related_ids):
    if not related_ids:
        return ""
    links = " ".join(
        f"<a href='?focus_event_id={event_id}' target='_top' "
        "style='display:inline-block;margin:2px;padding:4px 7px;border-radius:999px;background:#eef2ff;color:#3730a3;text-decoration:none'>"
        f"Event #{event_id}</a>"
        for event_id in related_ids
    )
    return f"<hr style='margin:6px 0'><b>Related event references</b><br>{links}"


def _render_results_cards(measurements):
    if not measurements:
        st.info("No measurement results are linked to this block yet. Older events remain readable with missing-field fallbacks.")
        return
    for measurement in measurements:
        st.markdown(f"**Results from MEASUREMENT #{measurement['measurement_event_id']}**")
        chem_cols = st.columns(5)
        for idx, (label, value) in enumerate(measurement["chemical"].items()):
            chem_cols[idx % 5].metric(label, value or "—")
        st.caption("Classification information")
        st.dataframe(pd.DataFrame([measurement["classification"]]), hide_index=True, use_container_width=True)
        st.caption("Defect percentages")
        st.dataframe(pd.DataFrame([measurement["defects"]]), hide_index=True, use_container_width=True)


def render():
    user = st.session_state["user"]
    st.title("🌍 Supply-chain Event Blocks")
    st.caption("Public/shared blocks from every organisation are visible. Private blocks are shown only when they belong to your organisation.")

    with st.expander("➕ Generate ORDER or DELIVERY blocks from interactions", expanded=False):
        orderable = get_orderable_blocks(user)
        c_order, c_delivery = st.columns(2)
        with c_order:
            st.markdown("**Place order**")
            if orderable.empty:
                st.info("No public/shared farm or silo source blocks from other organisations are available to order.")
            else:
                source_labels = {
                    f"#{int(row['event_id'])} · {row['event_type']} · {row['seller']} · {str(row['local_timestamp'])[:19]} · {row.get('note') or ''}": int(row["event_id"])
                    for _, row in orderable.iterrows()
                }
                selected_source = st.selectbox("Source block", list(source_labels.keys()))
                order_amount = st.number_input("Order amount (t)", min_value=0.01, value=10.0, step=1.0)
                order_visibility = st.selectbox("Order visibility", ["PRIVATE", "SHARED", "PUBLIC"], index=1)
                if st.button("🧾 Generate ORDER block"):
                    event_id = place_order(user, source_labels[selected_source], order_amount, order_visibility)
                    _set_focus_event(event_id)
                    st.success(f"ORDER event {event_id} created and linked to source block {source_labels[selected_source]}.")
                    st.rerun()
        with c_delivery:
            st.markdown("**Take delivery**")
            deliverable = get_deliverable_orders(user)
            if deliverable.empty:
                st.info("No readable undelivered order blocks are available.")
            else:
                order_labels = {
                    f"#{int(row['order_event_id'])} · {row['buyer']} ← {row['seller']} · {float(row['amount_tonnes']):.2f} t · {str(row['local_timestamp'])[:19]}": int(row["order_event_id"])
                    for _, row in deliverable.iterrows()
                }
                selected_order = st.selectbox("Order block", list(order_labels.keys()))
                delivery_visibility = st.selectbox("Delivery visibility", ["PUBLIC", "SHARED", "PRIVATE"], key="delivery_visibility")
                if st.button("🚚 Generate DELIVERY block"):
                    event_id = take_delivery(user, order_labels[selected_order], delivery_visibility)
                    _set_focus_event(event_id)
                    st.success(f"DELIVERY event {event_id} created for ORDER {order_labels[selected_order]}.")
                    st.rerun()

    blocks = get_event_blocks_for_map(user)
    if blocks.empty:
        st.info("No event blocks found.")
        return

    focused_event_id = st.session_state.get("focused_event_id") or _query_focus_event_id()
    if focused_event_id not in set(blocks["event_id"].astype(int).tolist()):
        focused_event_id = None

    event_types = sorted(blocks["event_type"].dropna().unique().tolist())
    selected = st.multiselect("Event types", event_types, default=event_types)
    visibilities = sorted(blocks["visibility"].dropna().unique().tolist())
    selected_vis = st.multiselect("Visibility", visibilities, default=visibilities)
    filtered = blocks[blocks["event_type"].isin(selected) & blocks["visibility"].isin(selected_vis)].copy()
    if focused_event_id and focused_event_id not in set(filtered["event_id"].astype(int).tolist()):
        focused = blocks[blocks["event_id"].astype(int) == focused_event_id]
        filtered = pd.concat([focused, filtered], ignore_index=True).drop_duplicates("event_id")

    map_ready = filtered.dropna(subset=["lat", "lon"]).copy()
    missing_coords = len(filtered) - len(map_ready)
    public_total = int((blocks["visibility"] == "PUBLIC").sum())
    public_map_ready = int((map_ready["visibility"] == "PUBLIC").sum())

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Blocks rendered", len(map_ready))
    c2.metric("Public rendered", public_map_ready, help=f"{public_total} public blocks are readable before filters/fallback coordinates.")
    c3.metric("Shared", int((map_ready["visibility"] == "SHARED").sum()))
    c4.metric("Private (own org)", int((map_ready["visibility"] == "PRIVATE").sum()))
    if missing_coords:
        st.warning(f"{missing_coords} readable block(s) have no event, linked-event, or organisation coordinate fallback and cannot be placed on the map.")

    focus_row = map_ready[map_ready["event_id"].astype(int) == int(focused_event_id)] if focused_event_id else pd.DataFrame()
    if not focus_row.empty:
        center = [float(focus_row.iloc[0]["lat"]), float(focus_row.iloc[0]["lon"])]
        zoom = 12
    else:
        center = [float(map_ready["lat"].mean()), float(map_ready["lon"].mean())] if not map_ready.empty else [50, 8]
        zoom = 5

    if map_ready.empty:
        st.subheader("Visible event blocks")
        st.dataframe(
            filtered[["event_id", "event_type", "organization", "org_type", "visibility", "local_timestamp", "previous_event_id", "linked_event_ids", "note"]]
            .rename(columns={"event_id": "ID", "event_type": "Type", "organization": "Organisation", "org_type": "Org Type", "visibility": "Visibility", "local_timestamp": "Timestamp", "previous_event_id": "Previous", "linked_event_ids": "Linked Events", "note": "Block note"}),
            use_container_width=True,
            height=300,
        )
        return

    measurement_results = get_measurement_results_for_events(map_ready["event_id"].tolist(), user)
    block_locations = {int(row["event_id"]): (float(row["lat"]), float(row["lon"])) for _, row in map_ready.iterrows()}
    m = folium.Map(location=center, zoom_start=zoom, tiles="OpenStreetMap")

    for _, row in map_ready.iterrows():
        event_id = int(row["event_id"])
        related_ids = _related_event_ids(row)
        for related_id in related_ids:
            if focused_event_id == event_id and related_id in block_locations:
                folium.PolyLine(
                    [block_locations[event_id], block_locations[related_id]],
                    color="#7c3aed",
                    weight=4,
                    opacity=0.75,
                    tooltip=f"Event #{event_id} relates to #{related_id}",
                ).add_to(m)
        extra = ""
        if pd.notna(row.get("amount_added_tonnes")):
            extra += f"<br>🌾 Stored: <b>{row['amount_added_tonnes']:.2f} t</b>"
        if pd.notna(row.get("order_amount_tonnes")):
            extra += f"<br>🧾 Ordered: <b>{row['order_amount_tonnes']:.2f} t</b>"
        if pd.notna(row.get("delivery_status")):
            extra += f"<br>🚚 Delivery: <b>{html.escape(str(row['delivery_status']))}</b>"
        highlight = focused_event_id == event_id
        popup = f"""
        <div style='font-family:sans-serif;min-width:280px;max-width:360px'>
          <b>{html.escape(str(row['event_type']))} #{event_id}</b> <span style='color:gray'>({html.escape(str(row['visibility']))})</span><br>
          🏢 {html.escape(str(row['organization']))} · {html.escape(str(row['org_type']))}<br>
          🕒 {html.escape(str(row['local_timestamp'])[:19])}<br>
          📍 {html.escape(str(row['location_text'] or ''))}
          {extra}<hr style='margin:4px'>
          {html.escape(str(row['note'] or ''))}
          {_links_html(related_ids)}
          <hr style='margin:6px 0'><b>Results</b>
          {_measurement_results_html(measurement_results.get(event_id, []))}
        </div>
        """
        folium.Marker(
            location=[float(row["lat"]), float(row["lon"])],
            tooltip=f"{row['event_type']} #{event_id} ({row['visibility']})",
            popup=folium.Popup(popup, max_width=420),
            icon=folium.Icon(color=EVENT_COLOR.get(row["event_type"], "gray"), icon="cube", prefix="fa"),
        ).add_to(m)
        if highlight:
            folium.CircleMarker(
                location=[float(row["lat"]), float(row["lon"])],
                radius=18,
                color="#7c3aed",
                weight=5,
                fill=True,
                fill_color="#c4b5fd",
                fill_opacity=0.35,
                tooltip=f"Focused event #{event_id}",
            ).add_to(m)

    st_folium(m, width="100%", height=560, key=f"event-map-{focused_event_id or 'all'}")

    st.subheader("Trace event relationships")
    event_options = map_ready["event_id"].astype(int).tolist()
    default_index = event_options.index(int(focused_event_id)) if focused_event_id in event_options else 0
    selected_focus = st.selectbox("Focus, center, and highlight an event block", event_options, index=default_index)
    if selected_focus and selected_focus != focused_event_id:
        _set_focus_event(selected_focus)
        st.rerun()

    selected_row = map_ready[map_ready["event_id"].astype(int) == int(selected_focus)].iloc[0]
    related_ids = _related_event_ids(selected_row)
    st.caption("Parent, source, linked, and previous event references are clickable. Selecting one recenters the map and draws visible relationship lines when both blocks have coordinates.")
    if related_ids:
        cols = st.columns(min(4, len(related_ids)))
        for idx, related_id in enumerate(related_ids):
            if cols[idx % len(cols)].button(f"↩ Event #{related_id}", key=f"related-{selected_focus}-{related_id}"):
                _set_focus_event(related_id)
                st.rerun()
    else:
        st.info("This block does not reference another event block.")

    st.markdown("### Results")
    _render_results_cards(measurement_results.get(int(selected_focus), []))

    st.subheader("Visible event blocks")
    st.dataframe(
        filtered[["event_id", "event_type", "organization", "org_type", "visibility", "local_timestamp", "previous_event_id", "linked_event_ids", "note"]]
        .rename(columns={"event_id": "ID", "event_type": "Type", "organization": "Organisation", "org_type": "Org Type", "visibility": "Visibility", "local_timestamp": "Timestamp", "previous_event_id": "Previous", "linked_event_ids": "Linked Events", "note": "Block note"}),
        use_container_width=True,
        height=300,
    )
