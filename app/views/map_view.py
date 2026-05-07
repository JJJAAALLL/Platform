"""
map_view.py — Interactive farm map with polygon drawing + silo management.
"""
import streamlit as st
import folium
from streamlit_folium import st_folium
import pandas as pd
import json, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from access_control import can_edit_org
from db import get_silos, get_org_materials, get_last_measurement, get_con
from services.farm_service import add_silo, remove_silo, update_farm_boundary, update_farm_size, update_silo_capacity

ORG_TYPE_COLOR = {
    "FARMER": "#4CAF50", "MILLER": "#FF9800", "LAB": "#2196F3",
    "ZEUTEC": "#9C27B0", "TRADER": "#F44336", "BUYER": "#00BCD4",
    "LOGISTICS": "#795548",
}

def render():
    org    = st.session_state["org"]
    user   = st.session_state["user"]
    org_id = int(org["organization_id"])
    can_edit = can_edit_org(user, org_id)

    st.title(f"🗺️ Farm Map — {org['name']}")
    st.caption(f"{org['org_type']}  ·  {org.get('country','')}")

    # Check if this org has farm data
    has_farm = pd.notna(org.get("lat")) and pd.notna(org.get("lon"))

    if not has_farm:
        if can_edit:
            st.warning(f"No farm location data for **{org['org_type']}** organisations. "
                       "Farm details are only available for FARMER, MILLER, LAB and ZEUTEC organisations.")
        else:
            st.warning("No farm location data is registered for this organisation.")
        return

    lat       = float(org["lat"])
    lon       = float(org["lon"])
    size_ha   = float(org["size_ha"]) if pd.notna(org.get("size_ha")) else None
    poly_json = org.get("polygon_geojson")
    silos     = get_silos(org_id, user)
    mats      = get_org_materials(org_id, user)
    last      = get_last_measurement(org_id, user)
    mat_list  = ", ".join(mats["name"].tolist()) if not mats.empty else "—"
    color     = ORG_TYPE_COLOR.get(org["org_type"], "#607D8B")

    # ── Build map ────────────────────────────────────────────
    m = folium.Map(location=[lat, lon], zoom_start=12, tiles="OpenStreetMap")

    # Farm polygon
    if poly_json:
        try:
            geo = json.loads(poly_json)
            popup_html = f"""
                <div style='font-family:sans-serif;min-width:200px'>
                  <b style='font-size:14px'>{org['name']}</b><br>
                  <span style='color:gray'>{org['org_type']}</span><br><hr style='margin:4px'>
                  🌾 Size: <b>{size_ha:.0f} ha</b><br>
                  📦 Handles: <b>{mat_list}</b><br>
                  🕒 Last scan: <b>{last['local_timestamp'][:10] if last else '—'}</b><br>
                  📍 {org.get('address','')}
                </div>
            """
            folium.GeoJson(
                geo,
                name="Farm boundary",
                style_function=lambda _: {
                    "fillColor": color, "color": color,
                    "weight": 2, "fillOpacity": 0.25,
                },
                tooltip=folium.Tooltip(f"{org['name']} — {size_ha:.0f} ha"),
                popup=folium.Popup(popup_html, max_width=280),
            ).add_to(m)
        except Exception:
            pass

    # Farm centre marker
    folium.Marker(
        location=[lat, lon],
        icon=folium.Icon(color="green", icon="home", prefix="fa"),
        tooltip=f"🏠 {org['name']}",
        popup=folium.Popup(f"<b>{org['name']}</b><br>{org['address']}", max_width=200),
    ).add_to(m)

    # Silos
    for _, silo in silos.iterrows():
        silo_popup = f"""
            <div style='font-family:sans-serif;min-width:160px'>
              <b>🏭 {silo['name']}</b><br><hr style='margin:4px'>
              📦 Material: <b>{silo['material']}</b><br>
              ⚖️ Capacity: <b>{int(silo['capacity_tonnes']):,} t</b><br>
              📍 {silo['lat']:.5f}, {silo['lon']:.5f}
            </div>
        """
        folium.Marker(
            location=[float(silo["lat"]), float(silo["lon"])],
            icon=folium.Icon(color="orange", icon="database", prefix="fa"),
            tooltip=folium.Tooltip(f"🏭 {silo['name']} — {int(silo['capacity_tonnes']):,} t"),
            popup=folium.Popup(silo_popup, max_width=240),
        ).add_to(m)

    if can_edit:
        from folium.plugins import Draw
        draw = Draw(
            draw_options={
                "polyline": False, "rectangle": True, "polygon": True,
                "circle": False, "marker": False, "circlemarker": False,
            },
            edit_options={"edit": True, "remove": True},
        )
        draw.add_to(m)

    # Render map
    if can_edit:
        st.markdown("**Click on the farm or silos for details · Draw a polygon to update the farm boundary**")
    else:
        st.markdown("**Click on the farm or silos for details**")
    map_data = st_folium(m, width="100%", height=520, returned_objects=["all_drawings"])

    st.markdown("---")

    # ── Edit panel ───────────────────────────────────────────
    if not can_edit:
        st.info("You can view this organisation's farm and silo data. Only users from the same organisation can add, remove, or edit it.")
        return

    col_edit, col_silos = st.columns([1, 1])

    with col_edit:
        st.subheader("✏️ Update farm boundary")
        drawn = map_data.get("all_drawings") if map_data else None

        if drawn:
            st.success(f"✅ {len(drawn)} polygon(s) drawn on map.")
            new_poly = json.dumps(drawn[-1]["geometry"])
            note = st.text_input("Change note", value="Farm boundary updated via dashboard")
            if st.button("💾 Save boundary", type="primary"):
                record_id, event_id = update_farm_boundary(user, org_id, new_poly, note)
                st.success(f"Farm detail {record_id} boundary saved; FARM_UPDATE event {event_id} logged.")
                st.rerun()
        else:
            st.info("Draw a rectangle or polygon on the map above, then save it here.")

        st.markdown("---")
        st.subheader("📐 Edit farm size")
        new_size = st.number_input("Farm size (hectares)", min_value=0.1,
                                   value=float(size_ha) if size_ha else 100.0,
                                   step=10.0, key="farm_size")
        if st.button("💾 Save size"):
            record_id, event_id = update_farm_size(user, org_id, new_size)
            st.success(f"Farm detail {record_id} size updated to {new_size:.0f} ha; FARM_UPDATE event {event_id} logged.")
            st.rerun()

    with col_silos:
        st.subheader("🏭 Manage silos")

        # Existing silos
        if not silos.empty:
            st.markdown("**Existing silos:**")
            for _, silo in silos.iterrows():
                with st.expander(f"🏭 {silo['name']}  —  {int(silo['capacity_tonnes']):,} t  ({silo['material']})"):
                    new_cap = st.number_input("Capacity (t)", min_value=1.0,
                                              value=float(silo["capacity_tonnes"]),
                                              key=f"cap_{silo['silo_id']}")
                    c1, c2 = st.columns(2)
                    if c1.button("💾 Save", key=f"save_{silo['silo_id']}"):
                        silo_id, event_id = update_silo_capacity(
                            user, org_id, int(silo["silo_id"]), silo["name"], new_cap
                        )
                        st.success(f"Silo {silo_id} saved; FARM_UPDATE event {event_id} logged.")
                        st.rerun()
                    if c2.button("🗑️ Remove", key=f"del_{silo['silo_id']}"):
                        silo_id, event_id = remove_silo(
                            user, org_id, int(silo["silo_id"]), silo["name"]
                        )
                        st.warning(f"Silo {silo_id} removed; FARM_UPDATE event {event_id} logged.")
                        st.rerun()

        st.markdown("---")
        st.markdown("**Add new silo:**")
        con = get_con()
        all_mats = con.execute("SELECT material_id, name FROM material ORDER BY name").fetchall()
        con.close()
        mat_opts = {r["name"]: r["material_id"] for r in all_mats}

        with st.form("add_silo"):
            silo_name = st.text_input("Silo name", placeholder="e.g. Silo-NW4")
            s_lat  = st.number_input("Latitude",  value=lat,  format="%.6f", step=0.001)
            s_lon  = st.number_input("Longitude", value=lon,  format="%.6f", step=0.001)
            s_cap  = st.number_input("Capacity (tonnes)", min_value=1.0, value=1000.0, step=100.0)
            s_mat  = st.selectbox("Material stored", list(mat_opts.keys()))
            add_btn = st.form_submit_button("➕ Add silo", type="primary")

        if add_btn and silo_name:
            silo_id, event_id = add_silo(
                user, org_id, silo_name, s_lat, s_lon, s_cap, mat_opts[s_mat]
            )
            st.success(f"Silo '{silo_name}' added with ID {silo_id}; FARM_UPDATE event {event_id} logged.")
            st.rerun()
