-- =====================================================================
-- 04_MMS_系统配置
-- 内容: 建表 + 索引
-- 执行方式: source C:/Users/Administrator/Desktop/mms/MySQL_/04_MMS_系统配置.sql;
-- =====================================================================

-- 建表
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

-- 索引
CREATE INDEX IF NOT EXISTS `idx_config_name` ON `MMS_系统配置`(`config_name`);

-- =====================================================================
-- 完成后确认: SHOW CREATE TABLE `MMS_系统配置`\G
-- =====================================================================