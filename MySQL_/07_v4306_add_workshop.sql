-- =====================================================================
-- v4306 MySQL 数据迁移：为三张核心表添加 workshop（车间）字段
-- =====================================================================
-- 版本: v4306  (2026-08-23)
-- 说明:
--   1. 支持分车间管理，为 MMS_库存明细 / MMS_领用记录 / MMS_固定资产 添加 workshop 列
--   2. 使用存储过程动态判断表/列是否存在，已存在则跳过
--   3. 对已存在数据回填默认值 '默认车间'
--   4. 兼容性：MySQL 5.7 / 8.0 均适用
-- 执行方式:
--   USE `mms`;
--   source C:/Users/Administrator/Desktop/mms/MySQL_/07_v4306_add_workshop.sql;
-- =====================================================================

-- 创建辅助存储过程：判断列是否存在
DELIMITER /

DROP PROCEDURE IF EXISTS `column_exists` /

CREATE PROCEDURE `column_exists`(
    IN p_table VARCHAR(64),
    IN p_column VARCHAR(64),
    OUT p_exists TINYINT
)
BEGIN
    SELECT COUNT(*) INTO p_exists
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = p_table
      AND COLUMN_NAME = p_column;
END /

-- 库存明细迁移
DROP PROCEDURE IF EXISTS `migrate_inventory` /
CREATE PROCEDURE `migrate_inventory`()
BEGIN
    DECLARE v_table VARCHAR(64) DEFAULT 'MMS_库存明细';
    DECLARE v_exists TINYINT;
    DECLARE v_table_exists TINYINT;

    SELECT COUNT(*) INTO v_table_exists
    FROM information_schema.TABLES
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = v_table;

    IF v_table_exists = 1 THEN
        CALL column_exists(v_table, 'workshop', v_exists);
        IF v_exists = 0 THEN
            ALTER TABLE `MMS_库存明细` ADD COLUMN `workshop` VARCHAR(255) DEFAULT '默认车间' AFTER `id`;
            UPDATE `MMS_库存明细` SET `workshop` = '默认车间' WHERE `workshop` IS NULL OR `workshop` = '';
        END IF;
    END IF;
END /

-- 领用记录迁移
DROP PROCEDURE IF EXISTS `migrate_borrow` /
CREATE PROCEDURE `migrate_borrow`()
BEGIN
    DECLARE v_table VARCHAR(64) DEFAULT 'MMS_领用记录';
    DECLARE v_exists TINYINT;
    DECLARE v_table_exists TINYINT;

    SELECT COUNT(*) INTO v_table_exists
    FROM information_schema.TABLES
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = v_table;

    IF v_table_exists = 1 THEN
        CALL column_exists(v_table, 'workshop', v_exists);
        IF v_exists = 0 THEN
            ALTER TABLE `MMS_领用记录` ADD COLUMN `workshop` VARCHAR(255) DEFAULT '默认车间' AFTER `id`;
            UPDATE `MMS_领用记录` SET `workshop` = '默认车间' WHERE `workshop` IS NULL OR `workshop` = '';
        END IF;
    END IF;
END /

-- 固定资产迁移
DROP PROCEDURE IF EXISTS `migrate_assets` /
CREATE PROCEDURE `migrate_assets`()
BEGIN
    DECLARE v_table VARCHAR(64) DEFAULT 'MMS_固定资产';
    DECLARE v_exists TINYINT;
    DECLARE v_table_exists TINYINT;

    SELECT COUNT(*) INTO v_table_exists
    FROM information_schema.TABLES
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = v_table;

    IF v_table_exists = 1 THEN
        CALL column_exists(v_table, 'workshop', v_exists);
        IF v_exists = 0 THEN
            ALTER TABLE `MMS_固定资产` ADD COLUMN `workshop` VARCHAR(255) DEFAULT '默认车间' AFTER `id`;
            UPDATE `MMS_固定资产` SET `workshop` = '默认车间' WHERE `workshop` IS NULL OR `workshop` = '';
        END IF;
    END IF;
END /

DELIMITER ;

-- 执行迁移
CALL `migrate_inventory`();
CALL `migrate_borrow`();
CALL `migrate_assets`();

-- 清理辅助存储过程
DROP PROCEDURE IF EXISTS `column_exists`;
DROP PROCEDURE IF EXISTS `migrate_inventory`;
DROP PROCEDURE IF EXISTS `migrate_borrow`;
DROP PROCEDURE IF EXISTS `migrate_assets`;

-- =====================================================================
-- 完成！
-- =====================================================================