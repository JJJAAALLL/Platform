"""db.py - centralised database connection and access-control helpers."""
import hashlib, hmac, sqlite3
import pandas as pd

from access_control import event_access_params
from config import DB_PATH, PASSWORD_HASH_ITERATIONS, READABLE_EVENT_VISIBILITY

MEASUREMENT_RESULT_FIELDS = {
    "chemical": ["Protein", "Moisture", "Ash", "Gluten", "Sedimentation"],
    "classification": ["Variety Type", "Commodity Type"],
    "defects": [
        "Percentage of Good",
        "Broken Percentage",
        "Damaged Percentage",
        "Foreign Matter Percentage",
    ],
}

_MEASUREMENT_ALIASES = {
    "protein": "Protein",
    "moisture": "Moisture",
    "ash": "Ash",
    "gluten": "Gluten",
    "sedimentation": "Sedimentation",
    "variety": "Variety Type",
    "variety type": "Variety Type",
    "commodity": "Commodity Type",
    "commodity type": "Commodity Type",
    "good": "Percentage of Good",
    "percentage of good": "Percentage of Good",
    "broken": "Broken Percentage",
    "broken percentage": "Broken Percentage",
    "damaged": "Damaged Percentage",
    "damaged percentage": "Damaged Percentage",
    "foreign matter": "Foreign Matter Percentage",
    "foreign matter percentage": "Foreign Matter Percentage",
}


def get_con():
    con = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON;")
    return con


def get_df(sql, params=()):
    con = get_con(); df = pd.read_sql_query(sql, con, params=params); con.close(); return df


def hash_password(password, salt):
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PASSWORD_HASH_ITERATIONS,
    ).hex()


def get_login_users():
    return get_df("""
        SELECT u.username, u.full_name, u.role, o.name AS organization, o.org_type
        FROM user_account u
        JOIN organization o ON o.organization_id=u.organization_id
        ORDER BY o.name, u.full_name
    """)


def authenticate_user(username, password):
    con = get_con()
    row = con.execute("""
        SELECT u.user_id, u.organization_id, u.username, u.password_hash,
               u.password_salt, u.full_name, u.role,
               o.code AS org_code, o.name AS organization_name, o.org_type
        FROM user_account u
        JOIN organization o ON o.organization_id=u.organization_id
        WHERE u.username=?
    """, (username,)).fetchone()
    con.close()
    if not row:
        return None
    expected = hash_password(password, row["password_salt"])
    if not hmac.compare_digest(expected, row["password_hash"]):
        return None
    user = dict(row)
    user.pop("password_hash", None)
    user.pop("password_salt", None)
    return user


def get_organizations(user):
    return get_df("""
        SELECT o.organization_id, o.code, o.name, o.org_type,
            COUNT(DISTINCT u.user_id) AS user_count,
            COUNT(DISTINCT i.instrument_id) AS instrument_count,
            COUNT(DISTINCT CASE
                WHEN e.visibility IN (?, ?) OR e.organization_id=? THEN e.event_id
            END) AS event_count,
            fd.lat, fd.lon, fd.size_ha, fd.address, fd.country, fd.polygon_geojson
        FROM organization o
        LEFT JOIN user_account u ON u.organization_id=o.organization_id
        LEFT JOIN instrument i ON i.organization_id=o.organization_id
        LEFT JOIN event e ON e.organization_id=o.organization_id
        LEFT JOIN farm_detail fd ON fd.organization_id=o.organization_id
        GROUP BY o.organization_id ORDER BY o.name
    """, (
        READABLE_EVENT_VISIBILITY[0], READABLE_EVENT_VISIBILITY[1], int(user["organization_id"]),
    ))


def get_silos(org_id, user):
    return get_df("""
        SELECT s.silo_id, s.name, s.lat, s.lon, s.capacity_tonnes, m.name AS material
        FROM silo s LEFT JOIN material m ON m.material_id=s.material_id
        WHERE s.organization_id=?
    """, (org_id,))


def get_org_materials(org_id, user):
    return get_df("""
        SELECT m.name, m.category FROM org_material om
        JOIN material m ON m.material_id=om.material_id WHERE om.organization_id=?
    """, (org_id,))


def get_events(org_id, user):
    return get_df("""
        SELECT e.event_id, et.code AS event_type, u.full_name AS operator, u.role,
            i.serial_number AS instrument, e.local_timestamp, e.visibility, e.location_text
        FROM event e
        JOIN event_type et ON et.event_type_id=e.event_type_id
        LEFT JOIN user_account u ON u.user_id=e.operator_user_id
        LEFT JOIN instrument i ON i.instrument_id=e.instrument_id
        WHERE (e.visibility IN (?, ?) OR e.organization_id=?)
          AND e.organization_id=?
        ORDER BY e.local_timestamp DESC
    """, event_access_params(user, org_id))


def get_results_for_org(org_id, user):
    return get_df("""
        SELECT r.analyte, r.value, r.unit, e.local_timestamp, m.name AS material
        FROM result r
        JOIN event e ON e.event_id=r.event_id
        JOIN sample s ON s.sample_id=e.sample_id
        JOIN material m ON m.material_id=s.material_id
        WHERE (e.visibility IN (?, ?) OR e.organization_id=?)
          AND e.organization_id=?
        ORDER BY e.local_timestamp DESC
    """, event_access_params(user, org_id))


def get_last_measurement(org_id, user):
    con = get_con()
    row = con.execute("""
        SELECT e.local_timestamp, e.location_text FROM event e
        JOIN event_type et ON et.event_type_id=e.event_type_id
        WHERE (e.visibility IN (?, ?) OR e.organization_id=?)
          AND e.organization_id=?
          AND et.code='MEASUREMENT'
        ORDER BY e.local_timestamp DESC LIMIT 1
    """, event_access_params(user, org_id)).fetchone()
    con.close()
    return dict(row) if row else None


def get_event_chain(event_id, user):
    return get_df("""
        WITH RECURSIVE chain AS (
            SELECT e.event_id, e.previous_event_id, et.code AS event_type,
                   e.local_timestamp, e.organization_id, e.visibility, 0 AS step
            FROM event e JOIN event_type et ON et.event_type_id=e.event_type_id
            WHERE e.event_id=?
              AND (e.visibility IN (?, ?) OR e.organization_id=?)
            UNION ALL
            SELECT e.event_id, e.previous_event_id, et.code,
                   e.local_timestamp, e.organization_id, e.visibility, c.step+1
            FROM event e JOIN event_type et ON et.event_type_id=e.event_type_id
            JOIN chain c ON e.event_id=c.previous_event_id
            WHERE c.step < 20
              AND (e.visibility IN (?, ?) OR e.organization_id=?)
        )
        SELECT step, event_id, event_type, local_timestamp, previous_event_id, visibility
        FROM chain
    """, (
        int(event_id), READABLE_EVENT_VISIBILITY[0], READABLE_EVENT_VISIBILITY[1], int(user["organization_id"]),
        READABLE_EVENT_VISIBILITY[0], READABLE_EVENT_VISIBILITY[1], int(user["organization_id"]),
    ))


def get_event_blocks_for_map(user, limit=None):
    """Return every readable event block with defensive coordinate fallbacks for map rendering."""
    limit_clause = "" if limit is None else " LIMIT ?"
    params = [READABLE_EVENT_VISIBILITY[0], READABLE_EVENT_VISIBILITY[1], int(user["organization_id"])]
    if limit is not None:
        params.append(int(limit))
    return get_df(
        f"""
        SELECT e.event_id, et.code AS event_type, e.organization_id, o.name AS organization,
               o.org_type, e.local_timestamp, e.visibility, e.location_text,
               COALESCE(e.lat, src.lat, fd.lat) AS lat,
               COALESCE(e.lon, src.lon, fd.lon) AS lon,
               sd.value_text AS note, e.previous_event_id,
               GROUP_CONCAT(DISTINCT el.linked_event_id) AS linked_event_ids,
               GROUP_CONCAT(DISTINCT el.relationship) AS linked_relationships,
               sud.amount_added_tonnes, od.amount_tonnes AS order_amount_tonnes,
               dd.status AS delivery_status
        FROM event e
        JOIN event_type et ON et.event_type_id=e.event_type_id
        JOIN organization o ON o.organization_id=e.organization_id
        LEFT JOIN soft_data sd ON sd.event_id=e.event_id
        LEFT JOIN event_link el ON el.event_id=e.event_id
        LEFT JOIN event src ON src.event_id=el.linked_event_id
        LEFT JOIN farm_detail fd ON fd.organization_id=e.organization_id
        LEFT JOIN silo_update_detail sud ON sud.silo_update_event_id=e.event_id
        LEFT JOIN order_detail od ON od.order_event_id=e.event_id
        LEFT JOIN delivery_detail dd ON dd.delivery_event_id=e.event_id
        WHERE (e.visibility IN (?, ?) OR e.organization_id=?)
        GROUP BY e.event_id
        ORDER BY e.local_timestamp DESC, e.event_id DESC
        {limit_clause}
        """,
        tuple(params),
    )


def get_measurement_results_for_events(event_ids, user):
    """Return original MEASUREMENT results for event blocks and their linked downstream chain."""
    ids = sorted({int(event_id) for event_id in event_ids if pd.notna(event_id)})
    if not ids:
        return {}
    values_clause = ",".join(["(?)"] * len(ids))
    sql = f"""
        WITH RECURSIVE roots(root_event_id, event_id, depth) AS (
            SELECT column1, column1, 0 FROM (VALUES {values_clause})
            UNION ALL
            SELECT roots.root_event_id, el.linked_event_id, roots.depth + 1
            FROM roots
            JOIN event_link el ON el.event_id=roots.event_id
            WHERE roots.depth < 12
        ), measurement_roots AS (
            SELECT DISTINCT roots.root_event_id, e.event_id AS measurement_event_id,
                   e.local_timestamp, e.visibility, e.organization_id,
                   COALESCE(s.batch_lot, s.external_ref, 'Unknown') AS variety_type,
                   COALESCE(m.category, 'Unknown') AS commodity_type
            FROM roots
            JOIN event e ON e.event_id=roots.event_id
            JOIN event_type et ON et.event_type_id=e.event_type_id
            LEFT JOIN sample s ON s.sample_id=e.sample_id
            LEFT JOIN material m ON m.material_id=s.material_id
            WHERE et.code='MEASUREMENT'
              AND (e.visibility IN (?, ?) OR e.organization_id=?)
        )
        SELECT mr.root_event_id, mr.measurement_event_id, mr.local_timestamp,
               mr.variety_type, mr.commodity_type, r.analyte, r.value, r.unit
        FROM measurement_roots mr
        LEFT JOIN result r ON r.event_id=mr.measurement_event_id
        ORDER BY mr.root_event_id, mr.measurement_event_id, r.analyte
    """
    params = ids + [READABLE_EVENT_VISIBILITY[0], READABLE_EVENT_VISIBILITY[1], int(user["organization_id"])]
    con = get_con()
    rows = con.execute(sql, params).fetchall()
    con.close()

    output = {}
    for row in rows:
        root_id = int(row["root_event_id"])
        measurement_id = int(row["measurement_event_id"])
        measurements = output.setdefault(root_id, {})
        measurement = measurements.setdefault(
            measurement_id,
            {
                "measurement_event_id": measurement_id,
                "timestamp": row["local_timestamp"],
                "chemical": {field: None for field in MEASUREMENT_RESULT_FIELDS["chemical"]},
                "classification": {
                    "Variety Type": row["variety_type"] or "Unknown",
                    "Commodity Type": row["commodity_type"] or "Unknown",
                },
                "defects": {field: None for field in MEASUREMENT_RESULT_FIELDS["defects"]},
            },
        )
        analyte = row["analyte"]
        if analyte:
            field = _MEASUREMENT_ALIASES.get(str(analyte).strip().lower())
            if field:
                value = row["value"]
                unit = row["unit"] or "%"
                formatted = f"{value:.2f}{unit}" if isinstance(value, (int, float)) else f"{value}{unit}"
                for section in ("chemical", "defects"):
                    if field in measurement[section]:
                        measurement[section][field] = formatted
    return {root: list(measurements.values()) for root, measurements in output.items()}


def get_floating_measurements(org_id, user):
    """Measurements that have not yet been assigned to a farm update."""
    return get_df(
        """
        SELECT e.event_id, e.local_timestamp, e.location_text, e.visibility,
               m.name AS material,
               GROUP_CONCAT(r.analyte || '=' || ROUND(r.value, 2) || COALESCE(r.unit, ''), ', ') AS results
        FROM event e
        JOIN event_type et ON et.event_type_id=e.event_type_id
        LEFT JOIN sample s ON s.sample_id=e.sample_id
        LEFT JOIN material m ON m.material_id=s.material_id
        LEFT JOIN result r ON r.event_id=e.event_id
        LEFT JOIN farm_measurement_assignment fma ON fma.measurement_event_id=e.event_id
        WHERE (e.visibility IN (?, ?) OR e.organization_id=?)
          AND e.organization_id=?
          AND et.code='MEASUREMENT'
          AND fma.measurement_event_id IS NULL
        GROUP BY e.event_id
        ORDER BY e.local_timestamp DESC
        LIMIT 100
        """,
        event_access_params(user, org_id),
    )


def get_assignable_farm_updates(org_id, user):
    return get_df(
        """
        SELECT e.event_id, e.local_timestamp, e.visibility, sd.value_text AS note
        FROM event e
        JOIN event_type et ON et.event_type_id=e.event_type_id
        LEFT JOIN soft_data sd ON sd.event_id=e.event_id
        LEFT JOIN silo_update_detail sud ON sud.source_farm_update_event_id=e.event_id
        WHERE (e.visibility IN (?, ?) OR e.organization_id=?)
          AND e.organization_id=?
          AND et.code='FARM_UPDATE'
          AND sud.source_farm_update_event_id IS NULL
        ORDER BY e.local_timestamp DESC
        LIMIT 100
        """,
        event_access_params(user, org_id),
    )
