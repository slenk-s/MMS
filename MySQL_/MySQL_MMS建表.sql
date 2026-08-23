-- =====================================================================
-- MMS 物料管理系统 — MySQL 数据库建表脚本（完整版）
-- 内容: 创建全部数据表 + 索引
-- 执行方式: source C:/Users/Administrator/Desktop/mms/MySQL_/MySQL_MMS建表.sql;
-- =====================================================================

-- =====================================================================
-- 01_MMS_库存明细 — 物料台账主表
-- =====================================================================
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

-- =====================================================================
-- 02_MMS_领用记录 — 物料领用/归还登记
-- =====================================================================
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

-- =====================================================================
-- 03_MMS_固定资产
-- =====================================================================
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

-- =====================================================================
-- 04_MMS_系统配置
-- =====================================================================
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

-- =====================================================================
-- 05_MMS_用户台账
-- =====================================================================
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

-- =====================================================================
-- 06_MMS_员工台账
-- =====================================================================
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
-- 完成后确认: SHOW TABLES;
-- =====================================================================