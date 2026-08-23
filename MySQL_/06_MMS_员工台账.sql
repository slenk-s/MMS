-- =====================================================================
-- 06_MMS_员工台账
-- 内容: 建表 + 索引
-- 执行方式: source C:/Users/Administrator/Desktop/mms/MySQL_/06_MMS_员工台账.sql;
-- =====================================================================

-- 建表
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

-- 索引
CREATE INDEX IF NOT EXISTS `idx_employee_card` ON `MMS_员工台账`(`card_no`);
CREATE INDEX IF NOT EXISTS `idx_employee_fingerprint` ON `MMS_员工台账`(`fingerprint_id`);
CREATE INDEX IF NOT EXISTS `idx_employee_no` ON `MMS_员工台账`(`employee_no`);

-- =====================================================================
-- 完成后确认: SHOW CREATE TABLE `MMS_员工台账`\G
-- =====================================================================