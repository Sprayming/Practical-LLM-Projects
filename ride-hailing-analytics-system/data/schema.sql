-- ============================================
-- 网约车平台核心数据表
-- ============================================

-- 司机表
CREATE TABLE drivers (
    id INT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(50) NOT NULL,
    phone VARCHAR(20),
    city VARCHAR(50),
    register_date DATE,
    driver_level VARCHAR(20),  -- 普通/金牌/钻石
    status VARCHAR(20)         -- 在线/离线/休息
);

-- 卡券类型表
CREATE TABLE coupon_types (
    id INT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(100) NOT NULL,
    face_value DECIMAL(10,2),       -- 面值
    min_order_amount DECIMAL(10,2), -- 最低使用金额
    valid_days INT,                 -- 有效期天数
    category VARCHAR(50)            -- 分类：新人券/满减券/折扣券
);

-- 卡券发放表
CREATE TABLE coupons (
    id INT PRIMARY KEY AUTO_INCREMENT,
    coupon_type_id INT NOT NULL,
    driver_id INT NOT NULL,
    issued_at DATETIME,
    expired_at DATETIME,
    status VARCHAR(20),             -- 未使用/已使用/已过期
    FOREIGN KEY (coupon_type_id) REFERENCES coupon_types(id),
    FOREIGN KEY (driver_id) REFERENCES drivers(id)
);

-- 订单表
CREATE TABLE orders (
    id INT PRIMARY KEY AUTO_INCREMENT,
    driver_id INT NOT NULL,
    order_amount DECIMAL(10,2),
    coupon_id INT,
    discount_amount DECIMAL(10,2) DEFAULT 0,
    final_amount DECIMAL(10,2),
    order_time DATETIME,
    pickup_location VARCHAR(200),
    dropoff_location VARCHAR(200),
    distance_km DECIMAL(8,2),
    status VARCHAR(20),             -- 已完成/已取消/进行中
    FOREIGN KEY (driver_id) REFERENCES drivers(id),
    FOREIGN KEY (coupon_id) REFERENCES coupons(id)
);

-- 核销记录表
CREATE TABLE redemptions (
    id INT PRIMARY KEY AUTO_INCREMENT,
    coupon_id INT NOT NULL,
    order_id INT NOT NULL,
    redeemed_at DATETIME,
    amount DECIMAL(10,2),           -- 实际核销金额
    FOREIGN KEY (coupon_id) REFERENCES coupons(id),
    FOREIGN KEY (order_id) REFERENCES orders(id)
);
