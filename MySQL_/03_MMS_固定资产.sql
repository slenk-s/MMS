-- =====================================================================
-- 03_MMS_固定资产
-- 内容: 建表 + 索引
-- 执行方式: source C:/Users/Administrator/Desktop/mms/MySQL_/03_MMS_固定资产.sql;
-- =====================================================================

-- 建表
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

-- 索引
CREATE INDEX IF NOT EXISTS `idx_asset_no` ON `MMS_固定资产`(`asset_no`);
CREATE INDEX IF NOT EXISTS `idx_asset_name` ON `MMS_固定资产`(`asset_name`);

-- =====================================================================
-- 完成后确认: SHOW CREATE TABLE `MMS_固定资产`\G
-- =====================================================================