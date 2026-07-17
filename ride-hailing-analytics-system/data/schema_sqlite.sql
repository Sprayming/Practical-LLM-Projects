CREATE TABLE IF NOT EXISTS drivers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL, phone TEXT, city TEXT,
    register_date TEXT, driver_level TEXT, status TEXT
);

CREATE TABLE IF NOT EXISTS coupon_types (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL, face_value REAL, min_order_amount REAL,
    valid_days INTEGER, category TEXT
);

CREATE TABLE IF NOT EXISTS coupons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    coupon_type_id INTEGER NOT NULL, driver_id INTEGER NOT NULL,
    issued_at TEXT, expired_at TEXT, status TEXT,
    FOREIGN KEY (coupon_type_id) REFERENCES coupon_types(id),
    FOREIGN KEY (driver_id) REFERENCES drivers(id)
);

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    driver_id INTEGER NOT NULL, order_amount REAL,
    coupon_id INTEGER, discount_amount REAL DEFAULT 0,
    final_amount REAL, order_time TEXT,
    pickup_location TEXT, dropoff_location TEXT,
    distance_km REAL, status TEXT,
    FOREIGN KEY (driver_id) REFERENCES drivers(id)
);

CREATE TABLE IF NOT EXISTS redemptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    coupon_id INTEGER NOT NULL, order_id INTEGER NOT NULL,
    redeemed_at TEXT, amount REAL,
    FOREIGN KEY (coupon_id) REFERENCES coupons(id),
    FOREIGN KEY (order_id) REFERENCES orders(id)
);
