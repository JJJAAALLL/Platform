import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from access_control import can_edit_org
from config import DB_PATH, DEMO_PASSWORD
from db import authenticate_user, get_login_users, get_organizations, get_silos
from services.farm_service import (
    PermissionDenied,
    add_silo,
    remove_silo,
    update_farm_size,
    update_silo_capacity,
)


def fetchone(sql, params=()):
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    row = con.execute(sql, params).fetchone()
    con.close()
    return row


def execute(sql, params=()):
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA foreign_keys = ON;")
    con.execute(sql, params)
    con.commit()
    con.close()


def cleanup_events(event_ids):
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA foreign_keys = ON;")
    for event_id in reversed(event_ids):
        con.execute("DELETE FROM soft_data WHERE event_id=?", (event_id,))
    for event_id in reversed(event_ids):
        con.execute("DELETE FROM event WHERE event_id=?", (event_id,))
    con.commit()
    con.close()


class BackendPermissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        login_users = get_login_users()
        cls.user = authenticate_user(login_users.iloc[0]["username"], DEMO_PASSWORD)
        cls.assert_user = unittest.TestCase()
        cls.assert_user.assertIsNotNone(cls.user)
        cls.own_org_id = int(cls.user["organization_id"])
        other = fetchone(
            """
            SELECT o.organization_id
            FROM organization o
            JOIN farm_detail fd ON fd.organization_id=o.organization_id
            JOIN silo s ON s.organization_id=o.organization_id
            WHERE o.organization_id<>?
            LIMIT 1
            """,
            (cls.own_org_id,),
        )
        cls.other_org_id = int(other["organization_id"])
        material = fetchone("SELECT material_id FROM material ORDER BY material_id LIMIT 1")
        cls.material_id = int(material["material_id"])

    def test_login_and_edit_scope(self):
        self.assertEqual(self.user["organization_id"], self.own_org_id)
        self.assertTrue(can_edit_org(self.user, self.own_org_id))
        self.assertFalse(can_edit_org(self.user, self.other_org_id))

    def test_cross_org_assets_are_readable(self):
        orgs = get_organizations(self.user)
        other_org = orgs[orgs["organization_id"] == self.other_org_id]
        self.assertFalse(other_org.empty)
        self.assertTrue(other_org.iloc[0]["lat"] == other_org.iloc[0]["lat"])
        self.assertFalse(get_silos(self.other_org_id, self.user).empty)

    def test_non_owner_cannot_mutate_other_org(self):
        before = fetchone("SELECT COUNT(*) AS n FROM silo WHERE organization_id=?", (self.other_org_id,))["n"]
        with self.assertRaises(PermissionDenied):
            add_silo(self.user, self.other_org_id, "Denied-Silo", 1.0, 1.0, 10.0, self.material_id)
        after = fetchone("SELECT COUNT(*) AS n FROM silo WHERE organization_id=?", (self.other_org_id,))["n"]
        self.assertEqual(before, after)

    def test_owner_silo_mutations_create_events(self):
        org = fetchone(
            "SELECT lat, lon FROM farm_detail WHERE organization_id=?",
            (self.own_org_id,),
        )
        silo_id, add_event_id = add_silo(
            self.user,
            self.own_org_id,
            "Test-Silo",
            org["lat"],
            org["lon"],
            100.0,
            self.material_id,
        )
        _, update_event_id = update_silo_capacity(
            self.user, self.own_org_id, silo_id, "Test-Silo", 150.0
        )
        _, remove_event_id = remove_silo(self.user, self.own_org_id, silo_id, "Test-Silo")
        notes = [
            fetchone("SELECT value_text FROM soft_data WHERE event_id=?", (event_id,))["value_text"]
            for event_id in (add_event_id, update_event_id, remove_event_id)
        ]
        self.assertTrue(all(f"silo_id={silo_id}" in note for note in notes))
        cleanup_events([add_event_id, update_event_id, remove_event_id])

    def test_owner_farm_size_update_creates_event(self):
        farm = fetchone(
            "SELECT size_ha FROM farm_detail WHERE organization_id=?",
            (self.own_org_id,),
        )
        original_size = float(farm["size_ha"])
        _, event_id = update_farm_size(self.user, self.own_org_id, original_size)
        note = fetchone("SELECT value_text FROM soft_data WHERE event_id=?", (event_id,))["value_text"]
        self.assertIn(f"organization_id={self.own_org_id}", note)
        cleanup_events([event_id])
        execute("UPDATE farm_detail SET size_ha=? WHERE organization_id=?", (original_size, self.own_org_id))


if __name__ == "__main__":
    unittest.main()
