-- ============================================================================
-- 数据库迁移脚本：从 requirements 表迁移到 clauses 表
-- 
-- 功能：
-- 1. 创建新的 clauses 表（包含新的结构化字段）
-- 2. 从旧的 requirements 表迁移数据到 clauses 表
-- 3. 更新 tasks 表，添加 total_clauses 字段
-- 
-- 使用方法：
--   sqlite3 data/tender_analysis.db < migration_clauses.sql
-- ============================================================================

-- 步骤1：备份旧的 requirements 表（可选）
-- DROP TABLE IF EXISTS requirements_backup;
-- CREATE TABLE requirements_backup AS SELECT * FROM requirements;

-- 步骤2：创建新的 clauses 表
CREATE TABLE IF NOT EXISTS clauses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id VARCHAR(36) NOT NULL,
    matrix_id VARCHAR(50) NOT NULL,
    section_id VARCHAR(50),
    section_title VARCHAR(500),
    page_number INTEGER,
    
    -- 新增：条款结构化字段
    clause_type VARCHAR(20) NOT NULL,  -- obligation/requirement/prohibition/deliverable/deadline/penalty/definition
    actor VARCHAR(100),                -- supplier/buyer/system/organization/role
    action VARCHAR(100),               -- submit/provide/ensure/record/comply/禁止...
    object VARCHAR(200),               -- document/feature/KPI/material
    condition TEXT,                    -- if/when/unless等条件描述
    deadline VARCHAR(200),             -- 具体日期、相对时间、周期性要求
    metric VARCHAR(200),               -- 具体数值、范围、比较运算符
    
    -- 原文内容
    original_text TEXT NOT NULL,
    
    -- 视觉扩展字段
    image_caption TEXT,
    table_caption TEXT,
    
    -- 位置信息
    positions_json TEXT,
    
    -- 时间戳
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    
    -- 外键约束
    FOREIGN KEY (task_id) REFERENCES tasks(task_id)
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_clause_task_id ON clauses(task_id);
CREATE INDEX IF NOT EXISTS idx_clause_matrix_id ON clauses(matrix_id);
CREATE INDEX IF NOT EXISTS idx_clause_section_id ON clauses(section_id);
CREATE INDEX IF NOT EXISTS idx_clause_type ON clauses(clause_type);

-- 步骤3：添加 total_clauses 字段到 tasks 表（如果不存在）
-- 注意：如果字段已存在会报错，可以忽略
ALTER TABLE tasks ADD COLUMN total_clauses INTEGER DEFAULT 0;

-- 步骤4：从 requirements 表迁移数据到 clauses 表
-- 注意：旧表没有新的结构化字段，设置默认值
INSERT INTO clauses (
    task_id,
    matrix_id,
    section_id,
    section_title,
    page_number,
    clause_type,
    actor,
    action,
    object,
    condition,
    deadline,
    metric,
    original_text,
    image_caption,
    table_caption,
    positions_json,
    created_at
)
SELECT 
    task_id,
    matrix_id,
    section_id,
    section_title,
    page_number,
    -- 根据旧的 category 字段映射到新的 clause_type
    CASE 
        WHEN category = 'SOLUTION' THEN 'requirement'
        WHEN category = 'QUALIFICATION' THEN 'requirement'
        WHEN category = 'BUSINESS' THEN 'obligation'
        WHEN category = 'FORMAT' THEN 'requirement'
        WHEN category = 'PROCESS' THEN 'requirement'
        ELSE 'requirement'
    END as clause_type,
    NULL as actor,      -- 新字段，暂时为空
    NULL as action,     -- 新字段，暂时为空
    NULL as object,     -- 新字段，暂时为空
    NULL as condition,  -- 新字段，暂时为空
    NULL as deadline,   -- 新字段，暂时为空
    NULL as metric,     -- 新字段，暂时为空
    original_text,
    image_caption,
    table_caption,
    positions_json,
    created_at
FROM requirements;

-- 步骤5：更新 tasks 表的统计信息
UPDATE tasks 
SET total_clauses = (
    SELECT COUNT(*) 
    FROM clauses 
    WHERE clauses.task_id = tasks.task_id
);

-- 步骤6：验证迁移结果
SELECT 
    'requirements 表记录数' as description, 
    COUNT(*) as count 
FROM requirements
UNION ALL
SELECT 
    'clauses 表记录数' as description, 
    COUNT(*) as count 
FROM clauses
UNION ALL
SELECT 
    '有条款的任务数' as description, 
    COUNT(*) as count 
FROM tasks 
WHERE total_clauses > 0;

-- ============================================================================
-- 迁移完成后的可选操作
-- ============================================================================

-- 可选：删除旧的 requirements 表（请先确认数据迁移成功！）
-- DROP TABLE requirements;

-- 可选：重命名 requirements 表为 requirements_old
-- ALTER TABLE requirements RENAME TO requirements_old;

-- ============================================================================
-- 说明
-- ============================================================================
-- 
-- 迁移后的数据结构：
-- 1. clauses 表包含所有新的结构化字段（type, actor, action, object, condition, deadline, metric）
-- 2. 旧数据的这些字段暂时为 NULL，需要后续通过 LLM 重新提取
-- 3. tasks 表新增 total_clauses 字段，记录条款总数
-- 4. 保留了原有的 image_caption, table_caption, positions_json 等字段
-- 
-- 后续步骤：
-- 1. 验证数据完整性
-- 2. 测试应用功能
-- 3. 如果需要，可以删除或重命名旧的 requirements 表
-- 4. 对于已有数据，可以选择重新运行分析以填充新字段
-- 
-- ============================================================================
