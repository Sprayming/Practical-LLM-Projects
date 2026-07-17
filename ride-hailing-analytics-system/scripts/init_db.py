import sys, os, random
from datetime import datetime, timedelta
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.db.connection import init_db, get_connection

CITIES = ["北京", "上海", "广州", "深圳", "杭州", "成都"]
CITY_WEIGHTS = [30, 25, 15, 12, 10, 8]
CT_DATA = [
    ("新人10元券", 10.0, 0, 30, "新人券"),
    ("满30减5", 5.0, 30, 15, "满减券"),
    ("满50减10", 10.0, 50, 20, "满减券"),
    ("8折券(上限20)", 20.0, 0, 14, "折扣券"),
    ("老用户回馈15元", 15.0, 20, 7, "回馈券"),
]

def seed():
    conn = get_connection()
    cur = conn.cursor()
    init_db()

    # Drivers
    rows = []
    for i in range(1, 61):
        rows.append((f"司机{i:03d}", f"138{i:08d}", random.choices(CITIES, weights=CITY_WEIGHTS)[0],
                     (datetime.now() - timedelta(days=random.randint(30, 1095))).strftime("%Y-%m-%d"),
                     random.choices(["普通","金牌","钻石"], weights=[50,35,15])[0],
                     random.choice(["在线","离线","休息"])))
    cur.executemany("INSERT INTO drivers VALUES (NULL,?,?,?,?,?,?)", rows)
    conn.commit()
    print(f"Drivers: {len(rows)}")

    # Coupon types
    for ct in CT_DATA:
        cur.execute("INSERT INTO coupon_types VALUES (NULL,?,?,?,?,?)", ct)
    conn.commit()
    print(f"Coupon types: {len(CT_DATA)}")

    # Coupons
    rows = []
    for did in range(1, 61):
        for _ in range(random.randint(3, 8)):
            ctid = random.randint(1, len(CT_DATA))
            days = CT_DATA[ctid-1][3]
            issued = datetime.now() - timedelta(days=random.randint(0, 60))
            rows.append((ctid, did, issued.strftime("%Y-%m-%d %H:%M:%S"),
                        (issued + timedelta(days=days)).strftime("%Y-%m-%d"),
                        random.choices(["未使用","已使用","已过期"], weights=[30,50,20])[0]))
    cur.executemany("INSERT INTO coupons VALUES (NULL,?,?,?,?,?)", rows)
    conn.commit()
    print(f"Coupons: {len(rows)}")

    # Orders + Redemptions
    redemptions = []
    oid = 0
    rows = []
    for did in range(1, 61):
        for _ in range(random.randint(10, 30)):
            oid += 1
            amt = round(random.uniform(10, 120), 2)
            ot = datetime.now() - timedelta(days=random.randint(0, 60), hours=random.randint(0, 23))
            city = random.choices(CITIES, weights=CITY_WEIGHTS)[0]
            cid = None
            dsc = 0
            if random.random() < 0.2:
                cid = random.randint(1, len(rows))  # may reference non-existent coupon, that's ok for demo
                dsc = round(amt * random.uniform(0.05, 0.3), 2)
            final = round(amt - dsc, 2)
            status = random.choices(["已完成","已取消","进行中"], weights=[80,15,5])[0]
            rows.append((did, amt, cid, dsc, final, ot.strftime("%Y-%m-%d %H:%M:%S"), city, city, round(random.uniform(1,30),2), status))
            if cid and status == "已完成":
                redemptions.append((cid, oid, ot.strftime("%Y-%m-%d %H:%M:%S"), dsc))
    cur.executemany("INSERT INTO orders VALUES (NULL,?,?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    print(f"Orders: {len(rows)}")

    cur.executemany("INSERT INTO redemptions VALUES (NULL,?,?,?,?)", redemptions)
    conn.commit()
    print(f"Redemptions: {len(redemptions)}")

    # Verify
    for t in ["drivers","coupon_types","coupons","orders","redemptions"]:
        r = conn.execute(f"SELECT COUNT(*) as c FROM {t}").fetchone()
        print(f"  {t}: {r[0]}")
    conn.close()
    print("Seed data ready!")

if __name__ == "__main__":
    seed()
