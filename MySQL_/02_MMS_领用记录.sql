-- =====================================================================
-- 02_MMS_领用记录 — 物料领用/归还登记
-- 内容: 建表 + 索引
-- 执行方式: source C:/Users/Administrator/Desktop/mms/MySQL_/02_MMS_领用记录.sql;
-- =====================================================================

-- 建表
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

-- 索引
CREATE INDEX IF NOT EXISTS `idx_borrow_card` ON `MMS_领用记录`(`card_no`);
CREATE INDEX IF NOT EXISTS `idx_borrow_code` ON `MMS_领用记录`(`material_code`);
CREATE INDEX IF NOT EXISTS `idx_borrow_name` ON `MMS_领用记录`(`material_name`);
CREATE INDEX IF NOT EXISTS `idx_borrow_material` ON `MMS_领用记录`(`material_id`);
CREATE INDEX IF NOT EXISTS `idx_borrow_returned` ON `MMS_领用记录`(`is_returned`);

-- =====================================================================
-- 完成后确认: SHOW CREATE TABLE `MMS_领用记录`\G
-- =====================================================================