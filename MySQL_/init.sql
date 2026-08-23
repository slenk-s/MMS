-- =====================================================================
-- 物料管理系统 - MySQL 数据库初始化脚本
-- =====================================================================
-- 执行方式: source C:/Users/Administrator/Desktop/mms/MySQL_/init.sql;
-- =====================================================================

-- =====================================================================
-- STEP 1: 创建数据库
-- =====================================================================
CREATE DATABASE IF NOT EXISTS `mms` DEFAULT CHARACTER SET utf8mb4 DEFAULT COLLATE utf8mb4_unicode_ci;

USE `mms`;

-- =====================================================================
-- STEP 2: 创建连接用户并授权（IPv4 / IPv6 / 本地全覆盖）
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

-- ---------- mms 用户 ----------
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
-- STEP 3: 创建表结构
-- =====================================================================

-- 库存明细主表
CREATE TABLE IF NOT EXISTS `MMS_库存明细` (
    `id` VARCHAR(64) PRIMARY KEY COMMENT '主键',
    `workshop` VARCHAR(255) DEFAULT '默认车间' COMMENT '车间',
    `location` VARCHAR(255) DEFAULT '' COMMENT '存放位置',
    `shelf_no` VARCHAR(255) DEFAULT '' COMMENT '货架号',
    `material_code` VARCHAR(255) NOT NULL UNIQUE COMMENT '物料编码',
    `material_name` VARCHAR(255) NOT NULL COMMENT '物料名称',
    `stock_qty` INT DEFAULT 0 COMMENT '库存数量',
    `reserved_qty` INT DEFAULT 0 COMMENT '预留数量',
    `unit` VARCHAR(50) DEFAULT 'PCS' COMMENT '单位',
    `real_image` TEXT COMMENT '实物图片路径',
    `last_update` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '最后更新时间',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间'
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

-- 领用登记记录表
CREATE TABLE IF NOT EXISTS `MMS_领用记录` (
    `id` VARCHAR(64) PRIMARY KEY COMMENT '主键',
    `workshop` VARCHAR(255) DEFAULT '默认车间' COMMENT '车间',
    `record_no` VARCHAR(255) NOT NULL UNIQUE COMMENT '记录编号',
    `material_id` VARCHAR(64) NOT NULL COMMENT '关联物料主键',
    `material_code` VARCHAR(255) NOT NULL COMMENT '物料编码',
    `material_name` VARCHAR(255) NOT NULL COMMENT '物料名称',
    `qty` INT DEFAULT 1 COMMENT '领用数量',
    `card_no` VARCHAR(255) NOT NULL COMMENT '工卡号',
    `dept` VARCHAR(255) COMMENT '部门',
    `user_name` VARCHAR(255) COMMENT '姓名',
    `phone` VARCHAR(50) COMMENT '联系电话',
    `action_type` VARCHAR(50) DEFAULT '领用' COMMENT '操作类型',
    `out_time` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '出库时间',
    `operator` VARCHAR(255) COMMENT '操作员',
    `in_time` DATETIME COMMENT '入库时间',
    `confirm_person` VARCHAR(255) COMMENT '接收人',
    `return_person` VARCHAR(255) COMMENT '实际归还人',
    `return_qty` INT DEFAULT 0 COMMENT '归还数量',
    `good_qty` INT DEFAULT 0 COMMENT '好板数',
    `damage_qty` INT DEFAULT 0 COMMENT '坏板数',
    `damage_status` VARCHAR(50) DEFAULT '' COMMENT '补单状态',
    `mixed_qty` INT DEFAULT 0 COMMENT '混板数量',
    `mixed_remark` VARCHAR(20) DEFAULT '' COMMENT '混板备注',
    `is_returned` TINYINT(1) DEFAULT 0 COMMENT '是否已归还',
    `is_archived` TINYINT(1) DEFAULT 0 COMMENT '软删除标记',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间'
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

-- 固定资产表
CREATE TABLE IF NOT EXISTS `MMS_固定资产` (
    `id` VARCHAR(64) PRIMARY KEY COMMENT '主键',
    `workshop` VARCHAR(255) DEFAULT '默认车间' COMMENT '车间',
    `asset_no` VARCHAR(255) NOT NULL UNIQUE COMMENT '资产编号',
    `asset_name` VARCHAR(255) NOT NULL COMMENT '资产名称',
    `category` VARCHAR(255) COMMENT '资产类别',
    `purchase_date` DATE COMMENT '购置日期',
    `status` VARCHAR(50) DEFAULT '在用' COMMENT '状态',
    `location` VARCHAR(255) COMMENT '存放位置',
    `location_image` TEXT COMMENT '位置图片路径',
    `value` DECIMAL(12, 2) COMMENT '资产价值',
    `remark` TEXT COMMENT '备注',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间'
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

-- 系统配置表
CREATE TABLE IF NOT EXISTS `MMS_系统配置` (
    `id` VARCHAR(64) PRIMARY KEY COMMENT '主键',
    `config_name` VARCHAR(255) NOT NULL UNIQUE COMMENT '配置名称',
    `item_type` VARCHAR(50) COMMENT '分类',
    `content` TEXT COMMENT '配置内容',
    `sort_order` INT DEFAULT 0 COMMENT '排序',
    `is_active` TINYINT(1) DEFAULT 1 COMMENT '是否启用',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间'
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

-- 用户台账表
CREATE TABLE IF NOT EXISTS `MMS_用户台账` (
    `id` VARCHAR(64) PRIMARY KEY COMMENT '主键',
    `username` VARCHAR(255) NOT NULL UNIQUE COMMENT '用户名',
    `password` VARCHAR(255) NOT NULL COMMENT '密码',
    `display_name` VARCHAR(255) DEFAULT '' COMMENT '显示名称',
    `role` ENUM('admin', 'user') DEFAULT 'user' COMMENT '角色: 管理员|普通用户',
    `is_active` TINYINT(1) DEFAULT 1 COMMENT '是否启用',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间'
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

-- 员工台账表
CREATE TABLE IF NOT EXISTS `MMS_员工台账` (
    `id` VARCHAR(64) PRIMARY KEY COMMENT '主键',
    `employee_no` VARCHAR(255) NOT NULL UNIQUE COMMENT '工号',
    `name` VARCHAR(255) NOT NULL COMMENT '姓名',
    `dept` VARCHAR(255) DEFAULT '' COMMENT '部门',
    `phone` VARCHAR(50) DEFAULT '' COMMENT '联系电话',
    `fingerprint_id` VARCHAR(255) DEFAULT '' COMMENT '指纹编号',
    `card_no` VARCHAR(255) DEFAULT '' COMMENT '工卡号',
    `is_active` TINYINT(1) DEFAULT 1 COMMENT '是否启用',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间'
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

-- =====================================================================
-- STEP 4: 创建索引
-- =====================================================================

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
END /

DELIMITER ;

-- 库存明细索引
CALL `create_index_if_not_exists` ('MMS_库存明细', 'idx_materials_code', 'material_code');
CALL `create_index_if_not_exists` ('MMS_库存明细', 'idx_materials_name', 'material_name');
CALL `create_index_if_not_exists` ('MMS_库存明细', 'idx_materials_location', 'location');

-- 领用记录索引
CALL `create_index_if_not_exists` ('MMS_领用记录', 'idx_borrow_card', 'card_no');
CALL `create_index_if_not_exists` ('MMS_领用记录', 'idx_borrow_code', 'material_code');
CALL `create_index_if_not_exists` ('MMS_领用记录', 'idx_borrow_name', 'material_name');
CALL `create_index_if_not_exists` ('MMS_领用记录', 'idx_borrow_material', 'material_id');
CALL `create_index_if_not_exists` ('MMS_领用记录', 'idx_borrow_returned', 'is_returned');

-- 固定资产索引
CALL `create_index_if_not_exists` ('MMS_固定资产', 'idx_asset_no', 'asset_no');
CALL `create_index_if_not_exists` ('MMS_固定资产', 'idx_asset_name', 'asset_name');

-- 系统配置索引
CALL `create_index_if_not_exists` ('MMS_系统配置', 'idx_config_name', 'config_name');

-- 用户台账索引
CALL `create_index_if_not_exists` ('MMS_用户台账', 'idx_users_username', 'username');

-- 员工台账索引
CALL `create_index_if_not_exists` ('MMS_员工台账', 'idx_employee_card', 'card_no');
CALL `create_index_if_not_exists` ('MMS_员工台账', 'idx_employee_fingerprint', 'fingerprint_id');
CALL `create_index_if_not_exists` ('MMS_员工台账', 'idx_employee_no', 'employee_no');

DROP PROCEDURE IF EXISTS `create_index_if_not_exists`;

-- =====================================================================
-- STEP 5: 初始化数据
-- =====================================================================

-- 预置系统配置项
INSERT IGNORE INTO `MMS_系统配置` (
    `id`, `config_name`, `item_type`, `content`, `sort_order`
) VALUES
    -- 运行模式
    ('cfg_APP_MODE', 'APP_MODE', 'sync', 'online', 0),

    -- 数据库连接
    ('cfg_MYSQL_HOST', 'MYSQL_HOST', 'database', 'localhost', 1),
    ('cfg_MYSQL_PORT', 'MYSQL_PORT', 'database', '3306', 2),
    ('cfg_MYSQL_USER', 'MYSQL_USER', 'database', 'root', 3),
    ('cfg_MYSQL_PASSWORD', 'MYSQL_PASSWORD', 'database', '', 4),
    ('cfg_MYSQL_DATABASE', 'MYSQL_DATABASE', 'database', 'mms', 5),
    ('cfg_MYSQL_CHARSET', 'MYSQL_CHARSET', 'database', 'utf8mb4', 6),

    -- 同步设置
    ('cfg_SYNC_INTERVAL', 'SYNC_INTERVAL_SECONDS', 'sync', '30', 10),
    ('cfg_SYNC_RETRY', 'SYNC_RETRY_MAX', 'sync', '3', 11),
    ('cfg_SYNC_BATCH', 'SYNC_BATCH_SIZE', 'sync', '50', 12),
    ('cfg_FULL_SYNC', 'FULL_SYNC_INTERVAL_MINUTES', 'sync', '30', 13),
    ('cfg_NETWORK_CHECK', 'NETWORK_CHECK_INTERVAL_SECONDS', 'sync', '10', 14),

    -- 预警设置
    ('cfg_STALE_DAYS', 'STALE_DAYS_THRESHOLD', 'alert', '90', 20),
    ('cfg_EXPIRE_DAYS', 'CHECK_EXPIRE_DAYS', 'alert', '7', 21),
    ('cfg_LOW_STOCK', 'LOW_STOCK_THRESHOLD', 'alert', '10', 22),
    ('cfg_AUTO_EXPORT', 'AUTO_EXPORT_ENABLED', 'alert', '0', 23),

    -- Web 查询服务
    ('cfg_WEB_ENABLED', 'WEB_QUERY_ENABLED', 'web_query', '0', 50),
    ('cfg_WEB_HOST', 'WEB_QUERY_HOST', 'web_query', 'localhost', 51),
    ('cfg_WEB_PORT', 'WEB_QUERY_PORT', 'web_query', '8000', 52),
    ('cfg_WEB_API_BASE', 'WEB_QUERY_API_BASE', 'web_query', '/api', 53),
    ('cfg_WEB_API_KEY', 'WEB_QUERY_API_KEY', 'web_query', '', 54),
    ('cfg_WEB_TIMEOUT', 'WEB_QUERY_TIMEOUT', 'web_query', '10', 55),
    ('cfg_WEB_USE_HTTPS', 'WEB_QUERY_USE_HTTPS', 'web_query', '0', 56);

-- 默认管理员账号（占位记录，真实密码由应用层首次启动时随机生成）
INSERT IGNORE INTO `MMS_用户台账` (
    `id`, `username`, `password`, `display_name`, `role`, `is_active`
) VALUES (
    'admin_default_001', 'admin', '', '系统管理员', 'admin', 1
);

-- =====================================================================
-- STEP 6: 数据迁移（清理已废弃的配置项）
-- 版本: v4305  (2026-08-23)
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

-- =====================================================================
-- 完成！
-- =====================================================================