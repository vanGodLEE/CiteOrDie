"""
数据库迁移脚本：从 requirements 表迁移到 clauses 表

功能：
1. 创建新的 clauses 表（包含新的结构化字段）
2. 从旧的 requirements 表迁移数据到 clauses 表
3. 更新 tasks 表，添加 total_clauses 字段
4. 保留 requirements 表作为视图（可选）

使用方法：
    python scripts/migrate_requirements_to_clauses.py
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text, inspect
from loguru import logger
from app.db.database import engine, get_db_session
from app.db.models import Base, Clause, Task


def check_table_exists(table_name: str) -> bool:
    """检查表是否存在"""
    inspector = inspect(engine)
    return table_name in inspector.get_table_names()


def migrate_database():
    """执行数据库迁移"""
    logger.info("=" * 60)
    logger.info("开始数据库迁移：requirements -> clauses")
    logger.info("=" * 60)
    
    db = get_db_session()
    
    try:
        # 步骤1：检查旧表是否存在
        has_requirements = check_table_exists("requirements")
        has_clauses = check_table_exists("clauses")
        
        logger.info(f"表状态检查：")
        logger.info(f"  - requirements 表存在: {has_requirements}")
        logger.info(f"  - clauses 表存在: {has_clauses}")
        
        # 步骤2：创建新的 clauses 表
        if not has_clauses:
            logger.info("\n步骤1：创建 clauses 表...")
            Base.metadata.create_all(bind=engine, tables=[Clause.__table__])
            logger.info("✓ clauses 表创建成功")
        else:
            logger.info("\n步骤1：clauses 表已存在，跳过创建")
        
        # 步骤3：添加 total_clauses 字段到 tasks 表
        logger.info("\n步骤2：更新 tasks 表...")
        total_clauses_exists = False
        try:
            # 检查 total_clauses 字段是否已存在
            inspector = inspect(engine)
            columns = [col['name'] for col in inspector.get_columns('tasks')]
            
            if 'total_clauses' not in columns:
                # SQLite 不支持 COMMENT，需要去掉
                db.execute(text("""
                    ALTER TABLE tasks 
                    ADD COLUMN total_clauses INTEGER DEFAULT 0
                """))
                db.commit()
                logger.info("✓ 添加 total_clauses 字段成功")
                total_clauses_exists = True
            else:
                logger.info("✓ total_clauses 字段已存在，跳过")
                total_clauses_exists = True
        except Exception as e:
            logger.warning(f"添加 total_clauses 字段失败: {e}")
            db.rollback()
            total_clauses_exists = False
        
        # 步骤4：迁移数据
        if has_requirements and has_clauses:
            logger.info("\n步骤3：迁移数据 requirements -> clauses...")
            
            # 检查 clauses 表是否为空
            clause_count = db.execute(text("SELECT COUNT(*) FROM clauses")).scalar()
            
            if clause_count > 0:
                logger.warning(f"⚠️  clauses 表已有 {clause_count} 条数据")
                response = input("是否清空 clauses 表并重新迁移？(yes/no): ")
                if response.lower() == 'yes':
                    db.execute(text("DELETE FROM clauses"))
                    db.commit()
                    logger.info("✓ 已清空 clauses 表")
                else:
                    logger.info("跳过数据迁移")
                    return
            
            # 执行数据迁移
            # 注意：旧表没有新的结构化字段，设置默认值
            migration_sql = """
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
                    CASE 
                        WHEN category = 'SOLUTION' THEN 'requirement'
                        WHEN category = 'QUALIFICATION' THEN 'requirement'
                        WHEN category = 'BUSINESS' THEN 'obligation'
                        WHEN category = 'FORMAT' THEN 'requirement'
                        WHEN category = 'PROCESS' THEN 'requirement'
                        ELSE 'requirement'
                    END as clause_type,
                    NULL as actor,
                    NULL as action,
                    NULL as object,
                    NULL as condition,
                    NULL as deadline,
                    NULL as metric,
                    original_text,
                    image_caption,
                    table_caption,
                    positions_json,
                    created_at
                FROM requirements
            """
            
            result = db.execute(text(migration_sql))
            db.commit()
            
            migrated_count = result.rowcount
            logger.info(f"✓ 成功迁移 {migrated_count} 条记录")
            
            # 更新 tasks 表的统计信息（如果字段存在）
            if total_clauses_exists:
                logger.info("\n步骤4：更新 tasks 表统计信息...")
                update_stats_sql = """
                    UPDATE tasks 
                    SET total_clauses = (
                        SELECT COUNT(*) 
                        FROM clauses 
                        WHERE clauses.task_id = tasks.task_id
                    )
                """
                db.execute(text(update_stats_sql))
                db.commit()
                logger.info("✓ 统计信息更新完成")
            else:
                logger.warning("\n步骤4：total_clauses 字段不存在，跳过统计信息更新")
        
        elif not has_requirements:
            logger.info("\n步骤3：未找到 requirements 表，跳过数据迁移")
        
        # 步骤5：验证迁移结果
        logger.info("\n步骤5：验证迁移结果...")
        
        if has_requirements:
            req_count = db.execute(text("SELECT COUNT(*) FROM requirements")).scalar()
            logger.info(f"  - requirements 表记录数: {req_count}")
        
        clause_count = db.execute(text("SELECT COUNT(*) FROM clauses")).scalar()
        logger.info(f"  - clauses 表记录数: {clause_count}")
        
        # 检查 tasks 表（如果字段存在）
        if total_clauses_exists:
            tasks_with_clauses = db.execute(text("""
                SELECT COUNT(*) FROM tasks WHERE total_clauses > 0
            """)).scalar()
            logger.info(f"  - 有条款的任务数: {tasks_with_clauses}")
        else:
            logger.warning("  - total_clauses 字段不存在，跳过任务统计")
        
        logger.info("\n" + "=" * 60)
        logger.info("✅ 数据库迁移完成！")
        logger.info("=" * 60)
        
        # 提示后续操作
        logger.info("\n后续操作建议：")
        logger.info("1. 验证数据完整性：检查 clauses 表中的数据是否正确")
        logger.info("2. 测试应用功能：确保所有功能正常工作")
        logger.info("3. 备份旧表：如果一切正常，可以备份 requirements 表")
        logger.info("4. 删除旧表（可选）：DROP TABLE requirements;")
        
    except Exception as e:
        logger.error(f"❌ 迁移失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        db.rollback()
        raise
    
    finally:
        db.close()


def create_backup():
    """创建 requirements 表的备份"""
    logger.info("\n创建 requirements 表备份...")
    db = get_db_session()
    
    try:
        # 检查备份表是否已存在
        if check_table_exists("requirements_backup"):
            logger.warning("备份表 requirements_backup 已存在")
            response = input("是否覆盖？(yes/no): ")
            if response.lower() == 'yes':
                db.execute(text("DROP TABLE requirements_backup"))
                db.commit()
            else:
                logger.info("跳过备份")
                return
        
        # 创建备份
        db.execute(text("""
            CREATE TABLE requirements_backup AS 
            SELECT * FROM requirements
        """))
        db.commit()
        
        backup_count = db.execute(text("SELECT COUNT(*) FROM requirements_backup")).scalar()
        logger.info(f"✓ 备份完成，共 {backup_count} 条记录")
        
    except Exception as e:
        logger.error(f"备份失败: {e}")
        db.rollback()
    
    finally:
        db.close()


def main():
    """主函数"""
    logger.info("数据库迁移工具")
    logger.info("功能：将 requirements 表迁移到新的 clauses 表")
    logger.info("")
    
    # 询问是否先备份
    if check_table_exists("requirements"):
        response = input("是否先备份 requirements 表？(yes/no): ")
        if response.lower() == 'yes':
            create_backup()
    
    # 执行迁移
    response = input("\n开始迁移？(yes/no): ")
    if response.lower() == 'yes':
        migrate_database()
    else:
        logger.info("取消迁移")


if __name__ == "__main__":
    main()
