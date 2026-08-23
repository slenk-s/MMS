-- =====================================================================
-- 测试机架组物料管理系统 - MySQL 数据库初始化脚本
-- =====================================================================
-- 使用方式：
-- source C:/Users/Administrator/Desktop/mms_v4_3_v26/MySQL_/init.sql;
-- =====================================================================

-- =====================================================================
-- STEP 1: 创建数据库（如不存在）
-- =====================================================================
CREATE DATABASE IF NOT EXISTS `mms` DEFAULT CHARACTER SET utf8mb4 DEFAULT COLLATE utf8mb4_unicode_ci;

USE `mms`;

-- =====================================================================
-- STEP 1.5: 创建连接用户并授权（IPv4 / IPv6 / 本地 全覆盖）
-- 说明:
--   1. 创建 root 和 mms 两个用户，覆盖所有连接场景
--   2. @'%'       - 允许从任意 IPv4/IPv6 地址连接
--   3. @'::1'      - 允许从 IPv6 本地回环地址连接
--   4. @'localhost' - 允许从本地 socket/管道连接
--   5. 均授予 mms 数据库的完全操作权限
--   6. 初始密码请在使用前手动设置（安全起见未在脚本中硬编码）:
--      ALTER USER 'root'@'%' IDENTIFIED BY '你的新密码';
--      FLUSH PRIVILEGES;
-- =====================================================================

-- ---------- root 用户 ----------
CREATE USER IF NOT EXISTS 'root'@'%' IDENTIFIED BY '<YOUR_ROOT_PASSWORD>';
ALTER USER 'root'@'%' IDENTIFIED BY '<YOUR_ROOT_PASSWORD>';
GRANT ALL PRIVILEGES ON `mms`.* TO 'root'@'%' WITH GRANT OPTION;

CREATE USER IF NOT EXISTS 'root'@'::1' IDENTIFIED BY '<YOUR_ROOT_PASSWORD>';
ALTER USER 'root'@'::1' IDENTIFIED BY '<YOUR_ROOT_PASSWORD>';
GRANT ALL PRIVILEGES ON `mms`.* TO 'root'@'::1' WITH GRANT OPTION;

CREATE USER IF NOT EXISTS 'root'@'localhost' IDENTIFIED BY '<YOUR_ROOT_PASSWORD>';
ALTER USER 'root'@'localhost' IDENTIFIED BY '<YOUR_ROOT_PASSWORD>';
GRANT ALL PRIVILEGES ON `mms`.* TO 'root'@'localhost' WITH GRANT OPTION;

-- ---------- mms 用户（只拥有增删改查权限）----------
CREATE USER IF NOT EXISTS 'mms'@'%' IDENTIFIED BY '<YOUR_MMS_PASSWORD>';
ALTER USER 'mms'@'%' IDENTIFIED BY '<YOUR_MMS_PASSWORD>';
GRANT SELECT, INSERT, UPDATE, DELETE ON `mms`.* TO 'mms'@'%' WITH GRANT OPTION;

CREATE USER IF NOT EXISTS 'mms'@'::1' IDENTIFIED BY '<YOUR_MMS_PASSWORD>';
ALTER USER 'mms'@'::1' IDENTIFIED BY '<YOUR_MMS_PASSWORD>';
GRANT SELECT, INSERT, UPDATE, DELETE ON `mms`.* TO 'mms'@'::1' WITH GRANT OPTION;

CREATE USER IF NOT EXISTS 'mms'@'localhost' IDENTIFIED BY '<YOUR_MMS_PASSWORD>';
ALTER USER 'mms'@'localhost' IDENTIFIED BY '<YOUR_MMS_PASSWORD>';
GRANT SELECT, INSERT, UPDATE, DELETE ON `mms`.* TO 'mms'@'localhost' WITH GRANT OPTION;

FLUSH PRIVILEGES;

-- =====================================================================
-- STEP 2: 创建表结构
-- =====================================================================

-- 物料台账主表
CREATE TABLE IF NOT EXISTS `MMS_库存明细` (
    `id` VARCHAR(64) PRIMARY KEY,
    `location` VARCHAR(255) DEFAULT '',
    `shelf_no` VARCHAR(255) DEFAULT '',
    `material_code` VARCHAR(255) NOT NULL UNIQUE,
    `material_name` VARCHAR(255) NOT NULL,
    `stock_qty` INT DEFAULT 0,
    `reserved_qty` INT DEFAULT 0,
    `unit` VARCHAR(50) DEFAULT 'PCS',
    `real_image` TEXT,
    `last_update` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

-- 领用登记记录表（v19: 新增归还相关字段）
CREATE TABLE IF NOT EXISTS `MMS_领用记录` (
    `id` VARCHAR(64) PRIMARY KEY,
    `record_no` VARCHAR(255) NOT NULL UNIQUE,
    `material_id` VARCHAR(64) NOT NULL,
    `material_code` VARCHAR(255) NOT NULL,
    `material_name` VARCHAR(255) NOT NULL,
    `qty` INT DEFAULT 1,
    `card_no` VARCHAR(255) NOT NULL,
    `dept` VARCHAR(255),
    `user_name` VARCHAR(255),
    `phone` VARCHAR(50),
    `action_type` VARCHAR(50) DEFAULT '领用',
    `out_time` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `operator` VARCHAR(255),
    `in_time` DATETIME,
    `confirm_person` VARCHAR(255) COMMENT '接收人（原确认人）',
    `return_person` VARCHAR(255) COMMENT '实际归还人',
    `return_qty` INT DEFAULT 0 COMMENT '归还数量',
    `good_qty` INT DEFAULT 0 COMMENT '好板数',
    `damage_qty` INT DEFAULT 0 COMMENT '坏板数',
    `damage_status` VARCHAR(50) DEFAULT '' COMMENT '补单状态: 待补单/已补单',
    `mixed_qty` INT DEFAULT 0 COMMENT '混板数量',
    `mixed_remark` VARCHAR(20) DEFAULT '' COMMENT '混板备注',
    `is_returned` TINYINT(1) DEFAULT 0,
    `is_archived` TINYINT(1) DEFAULT 0 COMMENT '软删除标记',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

-- 固定资产表
CREATE TABLE IF NOT EXISTS `MMS_固定资产` (
    `id` VARCHAR(64) PRIMARY KEY,
    `asset_no` VARCHAR(255) NOT NULL UNIQUE,
    `asset_name` VARCHAR(255) NOT NULL,
    `category` VARCHAR(255),
    `purchase_date` DATE,
    `status` VARCHAR(50) DEFAULT '在用',
    `location` VARCHAR(255),
    `location_image` TEXT COMMENT '位置图片路径',
    `value` DECIMAL(12, 2),
    `remark` TEXT,
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

-- 配置清单表
CREATE TABLE IF NOT EXISTS `MMS_系统配置` (
    `id` VARCHAR(64) PRIMARY KEY,
    `config_name` VARCHAR(255) NOT NULL UNIQUE,
    `item_type` VARCHAR(50),
    `content` TEXT,
    `sort_order` INT DEFAULT 0,
    `is_active` TINYINT(1) DEFAULT 1,
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

-- 用户表
CREATE TABLE IF NOT EXISTS `MMS_用户台账` (
    `id` VARCHAR(64) PRIMARY KEY,
    `username` VARCHAR(255) NOT NULL UNIQUE,
    `password` VARCHAR(255) NOT NULL,
    `display_name` VARCHAR(255) DEFAULT '',
    `role` ENUM('admin', 'user') DEFAULT 'user' COMMENT 'admin|user',
    `is_active` TINYINT(1) DEFAULT 1,
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

-- =====================================================================
-- STEP 3: 创建索引（兼容 MySQL 5.7 / 8.0）
-- =====================================================================
-- 使用存储过程动态判断索引是否存在，避免重复创建报错
DELIMITER /

DROP PROCEDURE IF EXISTS `create_index_if_not_exists` /

CREATE PROCEDURE `create_index_if_not_exists`(
    IN p_table VARCHAR(64),
    IN p_index VARCHAR(64),
    IN p_columns VARCHAR(512)
)
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = p_table
          AND INDEX_NAME = p_index
    ) THEN
        SET @sql = CONCAT('CREATE INDEX ', p_index, ' ON ', p_table, '(', p_columns, ')');
        PREPARE stmt FROM @sql;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
    END IF;
END
/

DELIMITER ;

-- 调用存储过程创建索引
CALL `create_index_if_not_exists` (
    'MMS_库存明细',
    'idx_materials_code',
    'material_code'
);

CALL `create_index_if_not_exists` (
    'MMS_库存明细',
    'idx_materials_name',
    'material_name'
);

CALL `create_index_if_not_exists` (
    'MMS_库存明细',
    'idx_materials_location',
    'location'
);

CALL `create_index_if_not_exists` (
    'MMS_领用记录',
    'idx_borrow_card',
    'card_no'
);

CALL `create_index_if_not_exists` (
    'MMS_领用记录',
    'idx_borrow_code',
    'material_code'
);

CALL `create_index_if_not_exists` (
    'MMS_领用记录',
    'idx_borrow_name',
    'material_name'
);

CALL `create_index_if_not_exists` (
    'MMS_领用记录',
    'idx_borrow_material',
    'material_id'
);

CALL `create_index_if_not_exists` (
    'MMS_领用记录',
    'idx_borrow_returned',
    'is_returned'
);

CALL `create_index_if_not_exists` (
    'MMS_固定资产',
    'idx_asset_no',
    'asset_no'
);

CALL `create_index_if_not_exists` (
    'MMS_固定资产',
    'idx_asset_name',
    'asset_name'
);

CALL `create_index_if_not_exists` (
    'MMS_系统配置',
    'idx_config_name',
    'config_name'
);

CALL `create_index_if_not_exists` (
    'MMS_用户台账',
    'idx_users_username',
    'username'
);

-- 清理存储过程
DROP PROCEDURE IF EXISTS `create_index_if_not_exists`;

-- =====================================================================
-- STEP 4: 初始化数据
-- =====================================================================

-- 预置系统配置项
INSERT IGNORE INTO
    `MMS_系统配置` (
        `id`,
        `config_name`,
        `item_type`,
        `content`,
        `sort_order`
    )
VALUES
    -- 同步设置（含运行模式）
    (
        'cfg_APP_MODE',
        'APP_MODE',
        'sync',
        'online',
        0
    ),
    -- 数据库连接
    (
        'cfg_MYSQL_HOST',
        'MYSQL_HOST',
        'database',
        'localhost',
        1
    ),
    (
        'cfg_MYSQL_PORT',
        'MYSQL_PORT',
        'database',
        '3306',
        2
    ),
    (
        'cfg_MYSQL_USER',
        'MYSQL_USER',
        'database',
        'root',
        3
    ),
    (
        'cfg_MYSQL_PASSWORD',
        'MYSQL_PASSWORD',
        'database',
        '',
        4
    ),
    (
        'cfg_MYSQL_DATABASE',
        'MYSQL_DATABASE',
        'database',
        'mms',
        5
    ),
    (
        'cfg_MYSQL_CHARSET',
        'MYSQL_CHARSET',
        'database',
        'utf8mb4',
        6
    ),
    -- 同步设置
    (
        'cfg_SYNC_INTERVAL',
        'SYNC_INTERVAL_SECONDS',
        'sync',
        '30',
        10
    ),
    (
        'cfg_SYNC_RETRY',
        'SYNC_RETRY_MAX',
        'sync',
        '3',
        11
    ),
    (
        'cfg_SYNC_BATCH',
        'SYNC_BATCH_SIZE',
        'sync',
        '50',
        12
    ),
    (
        'cfg_FULL_SYNC',
        'FULL_SYNC_INTERVAL_MINUTES',
        'sync',
        '30',
        13
    ),
    (
        'cfg_NETWORK_CHECK',
        'NETWORK_CHECK_INTERVAL_SECONDS',
        'sync',
        '10',
        14
    ),
    -- 预警设置
    (
        'cfg_STALE_DAYS',
        'STALE_DAYS_THRESHOLD',
        'alert',
        '90',
        20
    ),
    (
        'cfg_EXPIRE_DAYS',
        'CHECK_EXPIRE_DAYS',
        'alert',
        '7',
        21
    ),
    (
        'cfg_LOW_STOCK',
        'LOW_STOCK_THRESHOLD',
        'alert',
        '10',
        22
    ),
    (
        'cfg_AUTO_EXPORT',
        'AUTO_EXPORT_ENABLED',
        'alert',
        '0',
        23
    ),
    -- Web 查询服务
    (
        'cfg_WEB_ENABLED',
        'WEB_QUERY_ENABLED',
        'web_query',
        '0',
        50
    ),
    (
        'cfg_WEB_HOST',
        'WEB_QUERY_HOST',
        'web_query',
        'localhost',
        51
    ),
    (
        'cfg_WEB_PORT',
        'WEB_QUERY_PORT',
        'web_query',
        '8000',
        52
    ),
    (
        'cfg_WEB_API_BASE',
        'WEB_QUERY_API_BASE',
        'web_query',
        '/api',
        53
    ),
    (
        'cfg_WEB_API_KEY',
        'WEB_QUERY_API_KEY',
        'web_query',
        '',
        54
    ),
    (
        'cfg_WEB_TIMEOUT',
        'WEB_QUERY_TIMEOUT',
        'web_query',
        '10',
        55
    ),
    (
        'cfg_WEB_USE_HTTPS',
        'WEB_QUERY_USE_HTTPS',
        'web_query',
        '0',
        56
    );

-- 默认管理员账号（占位记录，用于同步）
-- 注意：真实密码由应用层 local_db.py 的 create_default_admin() 在首次启动时随机生成并哈希存储
INSERT IGNORE INTO
    `MMS_用户台账` (
        `id`,
        `username`,
        `password`,
        `display_name`,
        `role`,
        `is_active`
    )
VALUES (
        'admin_default_001',
        'admin',
        '',
        '系统管理员',
        'admin',
        1
    );

-- =====================================================================
-- 完成！
-- =====================================================================

-- =====================================================================
-- STEP 5: 数据迁移（清理已废弃的配置项）
-- 版本: v4305  (2026-08-23)
-- 说明:
--   1. 配置页面已移除"页面设置"组（窗口标题/日志级别）和"仓库设置"组
--   2. 这些配置项不再由应用读写，从数据库中清理避免残留
--   3. 同时清理旧版中文键名（历史遗留）与对应的英文键名
--   4. NETWORK_CHECK_INTERVAL_SECONDS 的 item_type 从 'ui' 修正为 'sync'
-- =====================================================================
DELETE FROM `MMS_系统配置`
WHERE `config_name` IN (
    'WINDOW_TITLE', 'LOG_LEVEL',
    'WAREHOUSE_NAME', 'DEFAULT_UNIT', 'DEFAULT_OPERATOR',
    '仓库名称', '默认单位', '默认操作员'
);

-- 修正 NETWORK_CHECK_INTERVAL_SECONDS 的分组归属（从 ui 改为 sync）
UPDATE `MMS_系统配置`
SET `item_type` = 'sync', `sort_order` = 14
WHERE `config_name` = 'NETWORK_CHECK_INTERVAL_SECONDS'
  AND (`item_type` = 'ui' OR `sort_order` = 32);