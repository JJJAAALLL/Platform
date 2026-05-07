"""Sanity-check metadata used by build.py after seeding the mock database."""

ROW_COUNT_TABLES = [
    "organization",
    "farm_detail",
    "silo",
    "org_material",
    "user_account",
    "instrument",
    "sensor_channel",
    "material",
    "sample",
    "method",
    "calibration_model",
    "event_type",
    "event",
    "measurement_data",
    "measurement_image",
    "result",
    "soft_data",
]

SANITY_CHECKS = [
    (
        "Rule 4  operator org==event org",
        "SELECT COUNT(*) FROM event e JOIN user_account u ON u.user_id=e.operator_user_id WHERE u.organization_id!=e.organization_id",
    ),
    (
        "Rule 5  instrument org==event org",
        "SELECT COUNT(*) FROM event e JOIN instrument i ON i.instrument_id=e.instrument_id WHERE i.organization_id!=e.organization_id",
    ),
    (
        "Rule 6  channel belongs to event instrument",
        "SELECT COUNT(*) FROM measurement_data md JOIN event e ON e.event_id=md.event_id JOIN sensor_channel sc ON sc.sensor_channel_id=md.sensor_channel_id WHERE sc.instrument_id!=e.instrument_id",
    ),
    (
        "Rule 7  role allowed for event type",
        "SELECT COUNT(*) FROM event e JOIN event_type et ON et.event_type_id=e.event_type_id JOIN user_account u ON u.user_id=e.operator_user_id WHERE (et.code='MEASUREMENT' AND u.role NOT IN('OPERATOR','ANALYST'))OR(et.code='INSTRUMENT_UPDATE' AND u.role NOT IN('ADMIN','ANALYST'))OR(et.code='METHOD_UPDATE' AND u.role NOT IN('ANALYST','ADMIN'))OR(et.code='CALIBRATION_UPDATE' AND u.role NOT IN('ANALYST','ADMIN'))OR(et.code='ORDER' AND u.role NOT IN('TRADER','ADMIN'))OR(et.code='DELIVERY' AND u.role NOT IN('DRIVER'))OR(et.code='FARM_UPDATE' AND u.role NOT IN('ADMIN','OPERATOR'))",
    ),
    (
        "Rule 8  event type allowed for org",
        "SELECT COUNT(*) FROM event e JOIN event_type et ON et.event_type_id=e.event_type_id JOIN organization o ON o.organization_id=e.organization_id WHERE (o.org_type='FARMER' AND et.code NOT IN('MEASUREMENT','STORAGE_UPDATE','SOFT_DATA','FARM_UPDATE'))OR(o.org_type='MILLER' AND et.code NOT IN('MEASUREMENT','STORAGE_UPDATE','SOFT_DATA','ORDER','FARM_UPDATE'))OR(o.org_type='TRADER' AND et.code NOT IN('ORDER','SOFT_DATA'))OR(o.org_type='BUYER' AND et.code NOT IN('ORDER','SOFT_DATA'))OR(o.org_type='LOGISTICS' AND et.code NOT IN('DELIVERY','SOFT_DATA'))OR(o.org_type='LAB' AND et.code NOT IN('MEASUREMENT','METHOD_UPDATE','CALIBRATION_UPDATE','SOFT_DATA'))OR(o.org_type='ZEUTEC' AND et.code NOT IN('INSTRUMENT_UPDATE','METHOD_UPDATE','CALIBRATION_UPDATE','MEASUREMENT'))",
    ),
    (
        "Rule 9  instruments scanning orgs only",
        "SELECT COUNT(*) FROM instrument i JOIN organization o ON o.organization_id=i.organization_id WHERE o.org_type NOT IN('FARMER','MILLER','LAB','ZEUTEC')",
    ),
    (
        "Rule 10a result data_id same event",
        "SELECT COUNT(*) FROM result r JOIN measurement_data md ON md.data_id=r.data_id WHERE md.event_id!=r.event_id",
    ),
    (
        "Rule 10b analyte==calibration analyte",
        "SELECT COUNT(*) FROM result r JOIN calibration_model c ON c.calibration_id=r.calibration_id WHERE r.analyte!=c.analyte",
    ),
    (
        "Rule 11 prev event same org",
        "SELECT COUNT(*) FROM event e JOIN event prev ON prev.event_id=e.previous_event_id WHERE prev.organization_id!=e.organization_id",
    ),
    (
        "Rule 12 soft recorder org==event org",
        "SELECT COUNT(*) FROM soft_data sd JOIN event e ON e.event_id=sd.event_id JOIN user_account u ON u.user_id=sd.recorded_by_user_id WHERE u.organization_id!=e.organization_id",
    ),
    (
        "Rule 13 user role matches org",
        "SELECT COUNT(*) FROM user_account u JOIN organization o ON o.organization_id=u.organization_id WHERE (o.org_type='FARMER' AND u.role NOT IN('OPERATOR','ADMIN'))OR(o.org_type='MILLER' AND u.role NOT IN('OPERATOR','ANALYST','ADMIN','TRADER'))OR(o.org_type='TRADER' AND u.role NOT IN('TRADER','ADMIN'))OR(o.org_type='BUYER' AND u.role NOT IN('TRADER','ADMIN'))OR(o.org_type='LOGISTICS' AND u.role NOT IN('DRIVER','ADMIN'))OR(o.org_type='LAB' AND u.role NOT IN('ANALYST','OPERATOR','ADMIN'))OR(o.org_type='ZEUTEC' AND u.role NOT IN('ANALYST','ADMIN','OPERATOR'))",
    ),
    (
        "Farm detail scanning orgs only",
        "SELECT COUNT(*) FROM farm_detail fd JOIN organization o ON o.organization_id=fd.organization_id WHERE o.org_type NOT IN('FARMER','MILLER','LAB','ZEUTEC')",
    ),
    (
        "Silos scanning orgs only",
        "SELECT COUNT(*) FROM silo s JOIN organization o ON o.organization_id=s.organization_id WHERE o.org_type NOT IN('FARMER','MILLER','LAB','ZEUTEC')",
    ),
]
