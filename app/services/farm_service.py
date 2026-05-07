"""Transactional farm and silo mutations with FARM_UPDATE ledger events."""
import datetime

from access_control import can_edit_org
from config import PRIVATE_VISIBILITY
from db import get_con


class PermissionDenied(ValueError):
    pass


def require_org_editor(user, org_id):
    if not can_edit_org(user, org_id):
        raise PermissionDenied("Only users from the same organization can edit these records.")


def create_farm_update_event(cur, org_id, operator_id, note):
    et_id = cur.execute("SELECT event_type_id FROM event_type WHERE code='FARM_UPDATE'").fetchone()[0]
    prev = cur.execute(
        "SELECT event_id FROM event WHERE organization_id=? ORDER BY event_id DESC LIMIT 1",
        (org_id,),
    ).fetchone()
    prev_id = prev[0] if prev else None
    now = datetime.datetime.utcnow().isoformat()
    cur.execute(
        """
        INSERT INTO event(event_type_id,organization_id,operator_user_id,
            local_timestamp,global_timestamp,previous_event_id,visibility)
        VALUES(?,?,?,?,?,?,?)
        """,
        (et_id, org_id, operator_id, now, now, prev_id, PRIVATE_VISIBILITY),
    )
    event_id = cur.lastrowid
    cur.execute(
        "INSERT INTO soft_data(event_id,value_text,recorded_by_user_id) VALUES(?,?,?)",
        (event_id, note, operator_id),
    )
    return event_id


def add_silo(user, org_id, name, lat, lon, capacity_tonnes, material_id):
    require_org_editor(user, org_id)
    con = get_con()
    try:
        cur = con.cursor()
        cur.execute(
            """
            INSERT INTO silo(organization_id,name,lat,lon,capacity_tonnes,material_id)
            VALUES(?,?,?,?,?,?)
            """,
            (org_id, name, lat, lon, capacity_tonnes, material_id),
        )
        silo_id = cur.lastrowid
        event_id = create_farm_update_event(
            cur,
            org_id,
            int(user["user_id"]),
            f"New silo '{name}' added with silo_id={silo_id} ({capacity_tonnes:.0f} t)",
        )
        con.commit()
        return silo_id, event_id
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def update_farm_boundary(user, org_id, polygon_geojson, note):
    require_org_editor(user, org_id)
    con = get_con()
    try:
        cur = con.cursor()
        cur.execute(
            "UPDATE farm_detail SET polygon_geojson=? WHERE organization_id=?",
            (polygon_geojson, org_id),
        )
        if cur.rowcount != 1:
            raise ValueError("Farm detail row was not found.")
        event_id = create_farm_update_event(cur, org_id, int(user["user_id"]), note)
        con.commit()
        return org_id, event_id
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def update_farm_size(user, org_id, size_ha):
    require_org_editor(user, org_id)
    con = get_con()
    try:
        cur = con.cursor()
        cur.execute("UPDATE farm_detail SET size_ha=? WHERE organization_id=?", (size_ha, org_id))
        if cur.rowcount != 1:
            raise ValueError("Farm detail row was not found.")
        event_id = create_farm_update_event(
            cur,
            org_id,
            int(user["user_id"]),
            f"Farm detail organization_id={org_id} size updated to {size_ha:.0f} ha",
        )
        con.commit()
        return org_id, event_id
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def update_silo_capacity(user, org_id, silo_id, silo_name, capacity_tonnes):
    require_org_editor(user, org_id)
    con = get_con()
    try:
        cur = con.cursor()
        cur.execute(
            "UPDATE silo SET capacity_tonnes=? WHERE silo_id=? AND organization_id=?",
            (capacity_tonnes, silo_id, org_id),
        )
        if cur.rowcount != 1:
            raise ValueError("Silo row was not found.")
        event_id = create_farm_update_event(
            cur,
            org_id,
            int(user["user_id"]),
            f"Silo '{silo_name}' silo_id={silo_id} capacity updated to {capacity_tonnes:.0f} t",
        )
        con.commit()
        return silo_id, event_id
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def remove_silo(user, org_id, silo_id, silo_name):
    require_org_editor(user, org_id)
    con = get_con()
    try:
        cur = con.cursor()
        cur.execute("DELETE FROM silo WHERE silo_id=? AND organization_id=?", (silo_id, org_id))
        if cur.rowcount != 1:
            raise ValueError("Silo row was not found.")
        event_id = create_farm_update_event(
            cur,
            org_id,
            int(user["user_id"]),
            f"Silo '{silo_name}' silo_id={silo_id} removed",
        )
        con.commit()
        return silo_id, event_id
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
