-- =====================================================================
-- 01_MMS_库存明细 — 物料台账主表
-- 内容: 建表 + 索引
-- 执行方式: source C:/Users/Administrator/Desktop/mms/MySQL_/01_MMS_库存明细.sql;
-- =====================================================================

-- 建表
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

-- 索引
CREATE INDEX IF NOT EXISTS `idx_materials_code` ON `MMS_库存明细`(`material_code`);
CREATE INDEX IF NOT EXISTS `idx_materials_name` ON `MMS_库存明细`(`material_name`);
CREATE INDEX IF NOT EXISTS `idx_materials_location` ON `MMS_库存明细`(`location`);

-- =====================================================================
-- 完成后确认: SHOW CREATE TABLE `MMS_库存明细`\G
-- =====================================================================