"""Transactional farm, measurement-assignment, and silo mutations with ledger events."""
import datetime

from access_control import can_edit_org
from config import PRIVATE_VISIBILITY, VALID_EVENT_VISIBILITY
from db import get_con


class PermissionDenied(ValueError):
    pass


def require_org_editor(user, org_id):
    if not can_edit_org(user, org_id):
        raise PermissionDenied("Only users from the same organization can edit these records.")


def create_event(cur, org_id, operator_id, event_type_code, note, visibility=PRIVATE_VISIBILITY, lat=None, lon=None, payload_json=None, linked_event_id=None, relationship="SOURCE_BLOCK"):
    if visibility not in VALID_EVENT_VISIBILITY:
        raise ValueError("Invalid event visibility.")
    et_id = cur.execute("SELECT event_type_id FROM event_type WHERE code=?", (event_type_code,)).fetchone()[0]
    prev = cur.execute(
        "SELECT event_id FROM event WHERE organization_id=? ORDER BY event_id DESC LIMIT 1",
        (org_id,),
    ).fetchone()
    prev_id = prev[0] if prev else None
    now = datetime.datetime.now(datetime.UTC).isoformat()
    cur.execute(
        """
        INSERT INTO event(event_type_id,organization_id,operator_user_id,
            local_timestamp,global_timestamp,previous_event_id,visibility,lat,lon,payload_json)
        VALUES(?,?,?,?,?,?,?,?,?,?)
        """,
        (et_id, org_id, operator_id, now, now, prev_id, visibility, lat, lon, payload_json),
    )
    event_id = cur.lastrowid
    cur.execute(
        "INSERT INTO soft_data(event_id,value_text,recorded_by_user_id) VALUES(?,?,?)",
        (event_id, note, operator_id),
    )
    if linked_event_id:
        cur.execute(
            "INSERT INTO event_link(event_id,linked_event_id,relationship) VALUES(?,?,?)",
            (event_id, linked_event_id, relationship),
        )
    return event_id


def create_farm_update_event(cur, org_id, operator_id, note, visibility=PRIVATE_VISIBILITY, lat=None, lon=None, payload_json=None, linked_event_id=None):
    return create_event(cur, org_id, operator_id, "FARM_UPDATE", note, visibility, lat, lon, payload_json, linked_event_id)


def create_silo_update_event(cur, org_id, operator_id, note, visibility=PRIVATE_VISIBILITY, lat=None, lon=None, payload_json=None, linked_event_id=None):
    return create_event(cur, org_id, operator_id, "SILO_UPDATE", note, visibility, lat, lon, payload_json, linked_event_id)


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


def assign_measurement_to_farm(user, org_id, measurement_event_id, visibility=PRIVATE_VISIBILITY):
    """Attach a floating MEASUREMENT block to this farm as a FARM_UPDATE event."""
    require_org_editor(user, org_id)
    con = get_con()
    try:
        cur = con.cursor()
        measurement = cur.execute(
            """
            SELECT e.event_id, e.organization_id, et.code
            FROM event e JOIN event_type et ON et.event_type_id=e.event_type_id
            WHERE e.event_id=?
            """,
            (measurement_event_id,),
        ).fetchone()
        if not measurement or measurement[1] != int(org_id) or measurement[2] != "MEASUREMENT":
            raise ValueError("Measurement event does not belong to this organization.")
        farm = cur.execute(
            "SELECT farm_detail_id, lat, lon FROM farm_detail WHERE organization_id=?",
            (org_id,),
        ).fetchone()
        if not farm:
            raise ValueError("Farm detail row was not found.")
        event_id = create_farm_update_event(
            cur,
            org_id,
            int(user["user_id"]),
            f"Measurement event_id={measurement_event_id} assigned to farm_detail_id={farm[0]}",
            visibility=visibility,
            lat=farm[1],
            lon=farm[2],
            payload_json=f'{{"action":"ASSIGN_MEASUREMENT_TO_FARM","measurement_event_id":{int(measurement_event_id)}}}',
            linked_event_id=measurement_event_id,
        )
        cur.execute(
            "INSERT INTO farm_measurement_assignment(farm_update_event_id,measurement_event_id,farm_detail_id) VALUES(?,?,?)",
            (event_id, measurement_event_id, farm[0]),
        )
        con.commit()
        return event_id
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def store_farm_update_in_silo(user, org_id, farm_update_event_id, silo_id, amount_added_tonnes, visibility=PRIVATE_VISIBILITY):
    """Record measured material storage in a silo as a SILO_UPDATE event."""
    require_org_editor(user, org_id)
    con = get_con()
    try:
        cur = con.cursor()
        source = cur.execute(
            """
            SELECT e.event_id, e.organization_id, et.code
            FROM event e JOIN event_type et ON et.event_type_id=e.event_type_id
            WHERE e.event_id=?
            """,
            (farm_update_event_id,),
        ).fetchone()
        if not source or source[1] != int(org_id) or source[2] != "FARM_UPDATE":
            raise ValueError("Farm update event does not belong to this organization.")
        silo = cur.execute(
            "SELECT silo_id, name, lat, lon FROM silo WHERE silo_id=? AND organization_id=?",
            (silo_id, org_id),
        ).fetchone()
        if not silo:
            raise ValueError("Silo row was not found.")
        amount = float(amount_added_tonnes)
        if amount <= 0:
            raise ValueError("Amount added must be positive.")
        event_id = create_silo_update_event(
            cur,
            org_id,
            int(user["user_id"]),
            f"Stored measured sample from FARM_UPDATE event_id={farm_update_event_id} in silo_id={silo_id}; amount_added_tonnes={amount:.2f}",
            visibility=visibility,
            lat=silo[2],
            lon=silo[3],
            payload_json=f'{{"source_farm_update_event_id":{int(farm_update_event_id)},"silo_id":{int(silo_id)},"amount_added_tonnes":{amount}}}',
            linked_event_id=farm_update_event_id,
        )
        cur.execute(
            "INSERT INTO silo_update_detail(silo_update_event_id,source_farm_update_event_id,silo_id,amount_added_tonnes,inventory_after_tonnes) VALUES(?,?,?,?,?)",
            (event_id, farm_update_event_id, silo_id, amount, amount),
        )
        con.commit()
        return event_id
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
