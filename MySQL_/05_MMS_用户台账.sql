-- =====================================================================
-- 05_MMS_用户台账
-- 内容: 建表 + 索引
-- 执行方式: source C:/Users/Administrator/Desktop/mms/MySQL_/05_MMS_用户台账.sql;
-- =====================================================================

-- 建表
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

-- 索引
CREATE INDEX IF NOT EXISTS `idx_users_username` ON `MMS_用户台账`(`username`);

-- =====================================================================
-- 完成后确认: SHOW CREATE TABLE `MMS_用户台账`\G
-- =====================================================================