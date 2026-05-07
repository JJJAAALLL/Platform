"""
Zeutec mock database — full build v3.
Adds: public/private event blocks, farm measurement assignment, silo/order/delivery lineage.
Run with: python build.py
"""

import hashlib, os, sqlite3, random, sys, json
from datetime import datetime, timedelta
from faker import Faker
from build_checks import ROW_COUNT_TABLES, SANITY_CHECKS
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "app"))
from config import DB_PATH, DEMO_PASSWORD, PASSWORD_HASH_ITERATIONS, SCHEMA_PATH

DB = str(DB_PATH)
fake = Faker()
random.seed(42)
Faker.seed(42)

N_USERS=60; N_INSTRUMENTS=18; N_SAMPLES=160; N_METHODS=6; N_CALIBRATIONS=18; N_EVENTS=3000

ROLE_BY_ORG_TYPE = {
    "FARMER":    ["OPERATOR","ADMIN"],
    "MILLER":    ["OPERATOR","ANALYST","ADMIN","TRADER"],
    "TRADER":    ["TRADER","ADMIN"],
    "BUYER":     ["TRADER","ADMIN"],
    "LOGISTICS": ["DRIVER","ADMIN"],
    "LAB":       ["ANALYST","OPERATOR","ADMIN"],
    "ZEUTEC":    ["ANALYST","ADMIN","OPERATOR"],
}
EVENT_TYPES_BY_ORG_TYPE = {
    "FARMER":    ["MEASUREMENT","SILO_UPDATE","SOFT_DATA","FARM_UPDATE"],
    "MILLER":    ["MEASUREMENT","SILO_UPDATE","SOFT_DATA","ORDER","FARM_UPDATE"],
    "TRADER":    ["ORDER","SOFT_DATA"],
    "BUYER":     ["ORDER","SOFT_DATA"],
    "LOGISTICS": ["DELIVERY","SOFT_DATA"],
    "LAB":       ["MEASUREMENT","METHOD_UPDATE","CALIBRATION_UPDATE","SOFT_DATA"],
    "ZEUTEC":    ["INSTRUMENT_UPDATE","METHOD_UPDATE","CALIBRATION_UPDATE","MEASUREMENT"],
}
ROLES_BY_EVENT_TYPE = {
    "MEASUREMENT":        ["OPERATOR","ANALYST"],
    "INSTRUMENT_UPDATE":  ["ADMIN","ANALYST"],
    "METHOD_UPDATE":      ["ANALYST","ADMIN"],
    "CALIBRATION_UPDATE": ["ANALYST","ADMIN"],
    "ORDER":              ["TRADER","ADMIN"],
    "DELIVERY":           ["DRIVER"],
    "SILO_UPDATE":     ["OPERATOR","ANALYST","ADMIN","TRADER","DRIVER"],
    "SOFT_DATA":          ["OPERATOR","ANALYST","ADMIN","TRADER","DRIVER"],
    "FARM_UPDATE":        ["ADMIN","OPERATOR"],
}
SCANNING = {"FARMER","MILLER","LAB","ZEUTEC"}
ANALYTES  = ["Protein","Moisture","Fat","Fiber","Starch","Ash"]
MODELS    = ["SpectraAlyzer GRAIN NEO","SpectraAlyzer VISION AI","SpectraAlyzer 2.0","SpectraAlyzer Mia"]
MATERIALS = [("WHEAT","Wheat","GRAIN"),("SOY","Soybean","GRAIN"),("CORN","Corn","GRAIN"),
             ("MILK_PD","Milk Powder","POWDER"),("OIL","Vegetable Oil","LIQUID")]
FARM_MATS = {"FARMER":["WHEAT","CORN","SOY"],"MILLER":["WHEAT","CORN"],
             "LAB":["WHEAT","SOY","CORN","MILK_PD"],"ZEUTEC":["WHEAT","SOY","CORN","MILK_PD","OIL"]}

def eu_lat(): return round(random.uniform(36.0,60.0),6)
def eu_lon(): return round(random.uniform(-10.0,30.0),6)

def make_polygon(clat,clon,ha):
    d = (ha**0.5)/111*0.5
    ld = d/max(0.5,abs(clat/10))
    c = [[clon-ld,clat-d],[clon+ld,clat-d],[clon+ld,clat+d],[clon-ld,clat+d],[clon-ld,clat-d]]
    return json.dumps({"type":"Polygon","coordinates":[c]})

def hash_password(password, salt):
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PASSWORD_HASH_ITERATIONS,
    ).hex()

def load_schema():
    with open(SCHEMA_PATH, "r", encoding="utf-8") as schema_file:
        return schema_file.read()

def main():
    if os.path.exists(DB): os.remove(DB); print(f"Removed {DB}")
    con = sqlite3.connect(DB)
    con.execute("PRAGMA foreign_keys=ON;")
    cur = con.cursor()
    cur.executescript(load_schema())
    print("Schema loaded.")

    org_type_by_id={}; org_ids=[]; users_by_org={}; instruments_by_org={}
    channels_by_inst={}; measurements_inst={}; soft_event_org={}

    # ORGS
    types = list(ROLE_BY_ORG_TYPE.keys())
    while len(types)<8: types.append(random.choice(list(ROLE_BY_ORG_TYPE.keys())))
    random.shuffle(types)
    for i,ot in enumerate(types,1):
        cur.execute("INSERT INTO organization(code,name,org_type)VALUES(?,?,?)",(f"ORG{i:03d}",fake.company(),ot))
        oid=cur.lastrowid; org_ids.append(oid); org_type_by_id[oid]=ot
        users_by_org[oid]=[]; instruments_by_org[oid]=[]

    # MATERIALS
    mat_ids=[]; mid_by_code={}
    for code,name,cat in MATERIALS:
        cur.execute("INSERT INTO material(code,name,category)VALUES(?,?,?)",(code,name,cat))
        mid=cur.lastrowid; mat_ids.append(mid); mid_by_code[code]=mid

    # FARM DETAIL + SILOS
    for oid,ot in org_type_by_id.items():
        if ot in SCANNING:
            lat=eu_lat(); lon=eu_lon(); size=round(random.uniform(50,2000),1)
            cur.execute("INSERT INTO farm_detail(organization_id,address,country,lat,lon,size_ha,polygon_geojson)VALUES(?,?,?,?,?,?,?)",
                (oid,fake.street_address(),fake.country(),lat,lon,size,make_polygon(lat,lon,size)))
            for s in range(random.randint(1,3)):
                mc=random.choice(FARM_MATS.get(ot,["WHEAT"]))
                cur.execute("INSERT INTO silo(organization_id,name,lat,lon,capacity_tonnes,material_id)VALUES(?,?,?,?,?,?)",
                    (oid,f"Silo-{ot[:2]}{s+1}",round(lat+random.uniform(-0.05,0.05),6),
                     round(lon+random.uniform(-0.05,0.05),6),round(random.uniform(500,10000),0),mid_by_code[mc]))
            for code in FARM_MATS.get(ot,["WHEAT"]):
                cur.execute("INSERT INTO org_material(organization_id,material_id)VALUES(?,?)",(oid,mid_by_code[code]))

    # USERS
    def add_user(oid,role):
        username = fake.unique.user_name()
        salt = fake.unique.uuid4()
        cur.execute("INSERT INTO user_account(organization_id,username,password_hash,password_salt,full_name,role)VALUES(?,?,?,?,?,?)",
            (oid,username,hash_password(DEMO_PASSWORD,salt),salt,fake.name(),role))
        users_by_org[oid].append((cur.lastrowid,role))
    for oid,ot in org_type_by_id.items():
        for role in ROLE_BY_ORG_TYPE[ot]: add_user(oid,role)
    total=sum(len(v) for v in users_by_org.values())
    while total<N_USERS:
        oid=random.choice(org_ids); add_user(oid,random.choice(ROLE_BY_ORG_TYPE[org_type_by_id[oid]])); total+=1

    # INSTRUMENTS
    scanning_orgs=[oid for oid,ot in org_type_by_id.items() if ot in SCANNING]
    def add_inst(oid):
        cur.execute("INSERT INTO instrument(organization_id,serial_number,model)VALUES(?,?,?)",
            (oid,fake.unique.bothify("ZT-####-???").upper(),random.choice(MODELS)))
        iid=cur.lastrowid; instruments_by_org[oid].append(iid)
        chs=[]
        for idx,lbl in enumerate(["NIR-SWIR","VIS-RGB"],1):
            cur.execute("INSERT INTO sensor_channel(instrument_id,channel_index,label)VALUES(?,?,?)",(iid,idx,lbl))
            chs.append(cur.lastrowid)
        channels_by_inst[iid]=chs
    for oid in scanning_orgs: add_inst(oid)
    while sum(len(v) for v in instruments_by_org.values())<N_INSTRUMENTS: add_inst(random.choice(scanning_orgs))

    # SAMPLES
    sample_ids=[]
    collectors=[(uid,role,oid) for oid,users in users_by_org.items() for uid,role in users if org_type_by_id[oid] in SCANNING]
    for _ in range(N_SAMPLES):
        uid,_,_=random.choice(collectors)
        cur.execute("INSERT INTO sample(material_id,external_ref,batch_lot,collected_by_user_id)VALUES(?,?,?,?)",
            (random.choice(mat_ids),fake.unique.bothify("LIMS-#####"),fake.bothify("LOT-###"),uid))
        sample_ids.append(cur.lastrowid)

    # METHODS + CALS
    method_ids=[]
    for i in range(N_METHODS):
        cur.execute("INSERT INTO method(name,version)VALUES(?,?)",(f"Method-{fake.word().capitalize()}-{i+1}",f"v{random.randint(1,5)}.{random.randint(0,9)}"))
        method_ids.append(cur.lastrowid)
    cals_by_analyte={a:[] for a in ANALYTES}
    def add_cal(a):
        cur.execute("INSERT INTO calibration_model(method_id,name,version,analyte)VALUES(?,?,?,?)",
            (random.choice(method_ids),f"{a}-PLS-{len(cals_by_analyte[a])+1}",f"v{random.randint(1,3)}.{random.randint(0,9)}",a))
        cals_by_analyte[a].append(cur.lastrowid)
    for a in ANALYTES: add_cal(a)
    while sum(len(v) for v in cals_by_analyte.values())<N_CALIBRATIONS: add_cal(random.choice(ANALYTES))

    # EVENT TYPES
    ET_LIST=[("MEASUREMENT","Spectrum/image captured"),("METHOD_UPDATE","Method created or updated"),
             ("CALIBRATION_UPDATE","Calibration model updated"),("INSTRUMENT_UPDATE","Instrument firmware/config update"),
             ("SOFT_DATA","Manual annotation"),("SILO_UPDATE","Measured sample stored in a silo"),
             ("ORDER","Purchase order placed"),("DELIVERY","Delivery in transit/completed"),
             ("FARM_UPDATE","Farm boundary, created farm, or measurement assignment updated")]
    et_ids={}
    for code,desc in ET_LIST:
        cur.execute("INSERT INTO event_type(code,description)VALUES(?,?)",(code,desc)); et_ids[code]=cur.lastrowid

    # EVENTS
    VIS=["PRIVATE","PRIVATE","PRIVATE","SHARED","PUBLIC"]
    last_per_org={}; ev_by_type={code:[] for code,_ in ET_LIST}
    base=datetime.now()-timedelta(days=30)
    for i in range(N_EVENTS):
        oid=random.choice(org_ids); ot=org_type_by_id[oid]
        code=random.choice(EVENT_TYPES_BY_ORG_TYPE[ot])
        pool=[(u,r) for u,r in users_by_org[oid] if r in set(ROLES_BY_EVENT_TYPE[code])]
        if not pool: code="SOFT_DATA"; pool=users_by_org[oid]
        op_id,_=random.choice(pool)
        inst_id=meth_id=samp_id=None
        if code in ("MEASUREMENT","INSTRUMENT_UPDATE"):
            insts=instruments_by_org[oid]
            if not insts: code="SOFT_DATA"
            else:
                inst_id=random.choice(insts)
                if code=="MEASUREMENT": meth_id=random.choice(method_ids); samp_id=random.choice(sample_ids)
        lt=base+timedelta(minutes=i*random.randint(5,60)); gt=lt+timedelta(seconds=random.randint(1,30))
        prev=last_per_org.get(oid)
        cur.execute("INSERT INTO event(event_type_id,organization_id,operator_user_id,instrument_id,method_id,sample_id,local_timestamp,global_timestamp,location_text,previous_event_id,visibility)VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (et_ids[code],oid,op_id,inst_id,meth_id,samp_id,lt.isoformat(),gt.isoformat(),f"{fake.city()},{fake.country_code()}",prev,random.choice(VIS)))
        eid=cur.lastrowid; last_per_org[oid]=eid; ev_by_type[code].append(eid)
        if code in ("SOFT_DATA","SILO_UPDATE","ORDER","DELIVERY","FARM_UPDATE"): soft_event_org[eid]=oid
        if code=="MEASUREMENT": measurements_inst[eid]=inst_id

    # MEASUREMENT ARTIFACTS
    meas_data_ids={}
    for eid in ev_by_type["MEASUREMENT"]:
        iid=measurements_inst[eid]; chs=channels_by_inst[iid]; dids=[]
        for _ in range(random.randint(1,2)):
            cur.execute("INSERT INTO measurement_data(event_id,sensor_channel_id,spectrum_uri)VALUES(?,?,?)",
                (eid,random.choice(chs),f"s3://zeutec-spectra/{fake.uuid4()}.parquet"))
            dids.append(cur.lastrowid)
        meas_data_ids[eid]=dids
        if random.random()<0.3:
            cur.execute("INSERT INTO measurement_image(event_id,image_uri,format)VALUES(?,?,?)",
                (eid,f"s3://zeutec-images/{fake.uuid4()}.jpg",random.choice(["JPEG","PNG","TIFF"])))
        for a in random.sample(ANALYTES,random.randint(2,4)):
            cal_id=random.choice(cals_by_analyte[a])
            cur.execute("INSERT INTO result(event_id,data_id,calibration_id,analyte,value,unit)VALUES(?,?,?,?,?,?)",
                (eid,random.choice(dids),cal_id,a,round(random.uniform(0.5,25.0),3),"%"))

    # SOFT + FARM DATA
    TMPLS={"SOFT_DATA":["Operator note: {note}","Lab reference: {note}"],
           "SILO_UPDATE":["Stored in silo {silo}, qty {qty} kg"],
           "ORDER":["Order qty {qty} kg, target price {price} EUR/t"],
           "DELIVERY":["Truck {truck}, status {status}"],
           "FARM_UPDATE":["Farm boundary updated by {user}","Silo {silo} capacity revised to {qty} tonnes"]}
    for code in ["SOFT_DATA","SILO_UPDATE","ORDER","DELIVERY","FARM_UPDATE"]:
        for eid in ev_by_type[code]:
            oid=soft_event_org[eid]; uid,_=random.choice(users_by_org[oid])
            tmpl=random.choice(TMPLS[code])
            text=tmpl.format(note=fake.sentence(nb_words=4),silo=f"S{random.randint(1,12)}",
                qty=random.randint(500,50000),price=random.randint(180,350),
                truck=fake.bothify("DE-??-####").upper(),status=random.choice(["pending","in_transit","delivered"]),
                user=fake.name())
            cur.execute("INSERT INTO soft_data(event_id,value_text,recorded_by_user_id)VALUES(?,?,?)",(eid,text,uid))


    # PUBLIC/PRIVATE EVENT BLOCK LINEAGE
    farm_rows = cur.execute("SELECT farm_detail_id, organization_id, lat, lon FROM farm_detail").fetchall()
    farm_by_org = {row[1]: {"farm_detail_id": row[0], "lat": row[2], "lon": row[3]} for row in farm_rows}
    silos_by_org = {}
    for sid, oid, lat, lon, cap in cur.execute("SELECT silo_id, organization_id, lat, lon, capacity_tonnes FROM silo").fetchall():
        silos_by_org.setdefault(oid, []).append((sid, lat, lon, cap or 0))

    # Give every event block a map coordinate, inherited from its farm/org when possible.
    for oid, info in farm_by_org.items():
        cur.execute(
            "UPDATE event SET lat=COALESCE(lat, ?), lon=COALESCE(lon, ?) WHERE organization_id=?",
            (info["lat"], info["lon"], oid),
        )

    def append_event(code, oid, operator_id, when, note, visibility="PRIVATE", lat=None, lon=None, payload=None, source_event_id=None):
        prev = last_per_org.get(oid)
        global_when = when + timedelta(seconds=random.randint(1, 30))
        cur.execute(
            """
            INSERT INTO event(event_type_id,organization_id,operator_user_id,local_timestamp,global_timestamp,
                              location_text,previous_event_id,visibility,lat,lon,payload_json)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                et_ids[code], oid, operator_id, when.isoformat(), global_when.isoformat(),
                f"{fake.city()},{fake.country_code()}", prev, visibility, lat, lon,
                json.dumps(payload or {}),
            ),
        )
        eid = cur.lastrowid
        last_per_org[oid] = eid
        ev_by_type[code].append(eid)
        soft_event_org[eid] = oid
        cur.execute("INSERT INTO soft_data(event_id,value_text,recorded_by_user_id)VALUES(?,?,?)", (eid, note, operator_id))
        if source_event_id:
            cur.execute(
                "INSERT INTO event_link(event_id,linked_event_id,relationship)VALUES(?,?,?)",
                (eid, source_event_id, "SOURCE_BLOCK"),
            )
        return eid

    farmer_orgs = [oid for oid, ot in org_type_by_id.items() if ot == "FARMER" and oid in farm_by_org]
    buyer_orgs = [oid for oid, ot in org_type_by_id.items() if ot in ("BUYER", "TRADER", "MILLER")]
    logistics_orgs = [oid for oid, ot in org_type_by_id.items() if ot == "LOGISTICS"]
    scenario_count = min(120, len(ev_by_type["MEASUREMENT"]))
    for idx, measurement_event_id in enumerate(ev_by_type["MEASUREMENT"][:scenario_count]):
        measurement = cur.execute("SELECT organization_id, sample_id, local_timestamp FROM event WHERE event_id=?", (measurement_event_id,)).fetchone()
        oid = measurement[0]
        if oid not in farm_by_org or not silos_by_org.get(oid) or "FARM_UPDATE" not in EVENT_TYPES_BY_ORG_TYPE[org_type_by_id[oid]]:
            continue
        farmer_ops = [u for u, r in users_by_org[oid] if r in ("ADMIN", "OPERATOR")]
        if not farmer_ops:
            continue
        op_id = random.choice(farmer_ops)
        farm = farm_by_org[oid]
        created_at = datetime.fromisoformat(measurement[2]) + timedelta(minutes=5)
        visibility = "PUBLIC" if idx % 3 == 0 else random.choice(["PRIVATE", "SHARED"])
        farm_update_id = append_event(
            "FARM_UPDATE", oid, op_id, created_at,
            f"Measurement event_id={measurement_event_id} assigned to farm_detail_id={farm['farm_detail_id']}",
            visibility, farm["lat"], farm["lon"],
            {"action": "ASSIGN_MEASUREMENT_TO_FARM", "measurement_event_id": measurement_event_id},
            measurement_event_id,
        )
        cur.execute(
            "INSERT INTO farm_measurement_assignment(farm_update_event_id,measurement_event_id,farm_detail_id)VALUES(?,?,?)",
            (farm_update_id, measurement_event_id, farm["farm_detail_id"]),
        )
        silo_id, silo_lat, silo_lon, cap = random.choice(silos_by_org[oid])
        amount = round(random.uniform(5, min(max(cap, 10), 250)), 2)
        silo_update_id = append_event(
            "SILO_UPDATE", oid, op_id, created_at + timedelta(minutes=15),
            f"Stored measured sample from FARM_UPDATE event_id={farm_update_id} in silo_id={silo_id}; amount_added_tonnes={amount}",
            visibility, silo_lat, silo_lon,
            {"source_farm_update_event_id": farm_update_id, "silo_id": silo_id, "amount_added_tonnes": amount},
            farm_update_id,
        )
        cur.execute(
            "INSERT INTO silo_update_detail(silo_update_event_id,source_farm_update_event_id,silo_id,amount_added_tonnes,inventory_after_tonnes)VALUES(?,?,?,?,?)",
            (silo_update_id, farm_update_id, silo_id, amount, amount),
        )
        if visibility == "PUBLIC" and buyer_orgs:
            buyer_oid = random.choice([b for b in buyer_orgs if b != oid] or buyer_orgs)
            buyer_ops = [u for u, r in users_by_org[buyer_oid] if r in ("TRADER", "ADMIN")]
            if buyer_ops:
                order_amount = round(random.uniform(1, amount), 2)
                order_id = append_event(
                    "ORDER", buyer_oid, random.choice(buyer_ops), created_at + timedelta(hours=1),
                    f"Order requested from public SILO_UPDATE event_id={silo_update_id}; amount_tonnes={order_amount}",
                    "PUBLIC", silo_lat, silo_lon,
                    {"source_event_id": silo_update_id, "seller_org_id": oid, "amount_tonnes": order_amount},
                    silo_update_id,
                )
                cur.execute(
                    "INSERT INTO order_detail(order_event_id,source_event_id,seller_org_id,amount_tonnes,status)VALUES(?,?,?,?,?)",
                    (order_id, silo_update_id, oid, order_amount, "REQUESTED"),
                )
                if logistics_orgs:
                    log_oid = random.choice(logistics_orgs)
                    drivers = [u for u, r in users_by_org[log_oid] if r == "DRIVER"]
                    if drivers:
                        delivery_id = append_event(
                            "DELIVERY", log_oid, random.choice(drivers), created_at + timedelta(hours=3),
                            f"Delivery created for ORDER event_id={order_id}; carrying history from event_id={silo_update_id}",
                            "PUBLIC", silo_lat, silo_lon,
                            {"order_event_id": order_id, "source_event_id": silo_update_id, "status": "IN_TRANSIT"},
                            order_id,
                        )
                        cur.execute(
                            "INSERT INTO delivery_detail(delivery_event_id,order_event_id,source_event_id,carrier_org_id,status)VALUES(?,?,?,?,?)",
                            (delivery_id, order_id, silo_update_id, log_oid, "IN_TRANSIT"),
                        )

    con.commit()

    print("\nRow counts:")
    for t in ROW_COUNT_TABLES:
        n=cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]; print(f"  {t:22s} {n:>5}")

    print("\nSanity checks:"); failures=0
    for label,sql in SANITY_CHECKS:
        n=cur.execute(sql).fetchone()[0]; flag="OK  " if n==0 else "FAIL"; print(f"  [{flag}] {label}: {n}")
        if n: failures+=1
    con.close()
    if failures: print(f"\n{failures} FAILED — removing DB."); os.remove(DB); sys.exit(1)
    else: print(f"\nAll checks passed. {DB} is ready.")

if __name__=="__main__": main()
