"""
数据库迁移脚本：为 tasks 表添加 file_hash 字段

用途：
1. 支持上传任务幂等性
2. 通过文件哈希识别相同文件，复用计算结果
3. 避免重复分析相同的PDF文件

运行方式：
    python scripts/migrate_add_file_hash.py
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from loguru import logger
from sqlalchemy import text
from app.db.database import engine, SessionLocal

def migrate_database():
    """执行迁移"""
    logger.info("=== 开始数据库迁移：添加 file_hash 字段 ===")
    
    db = SessionLocal()
    
    try:
        # 1. 检查 file_hash 字段是否已存在
        result = db.execute(text("PRAGMA table_info(tasks)"))
        columns = [row[1] for row in result.fetchall()]
        
        if 'file_hash' in columns:
            logger.info("✓ file_hash 字段已存在，跳过创建")
        else:
            # 2. 添加 file_hash 字段
            logger.info("添加 file_hash 字段...")
            db.execute(text("""
                ALTER TABLE tasks 
                ADD COLUMN file_hash VARCHAR(64)
            """))
            db.commit()
            logger.info("✓ file_hash 字段已添加")
        
        # 3. 检查索引是否存在
        result = db.execute(text("PRAGMA index_list(tasks)"))
        indexes = [row[1] for row in result.fetchall()]
        
        if 'idx_task_file_hash' in indexes:
            logger.info("✓ file_hash 索引已存在")
        else:
            # 4. 创建索引
            logger.info("创建 file_hash 索引...")
            db.execute(text("""
                CREATE INDEX idx_task_file_hash ON tasks(file_hash)
            """))
            db.commit()
            logger.info("✓ file_hash 索引已创建")
        
        # 5. 验证迁移
        logger.info("验证迁移...")
        result = db.execute(text("PRAGMA table_info(tasks)"))
        columns = {row[1]: row[2] for row in result.fetchall()}
        
        if 'file_hash' in columns:
            logger.success(f"✅ 迁移成功！file_hash 字段类型: {columns['file_hash']}")
        else:
            logger.error("❌ 迁移失败：file_hash 字段不存在")
            return False
        
        # 6. 统计已有任务
        result = db.execute(text("SELECT COUNT(*) FROM tasks"))
        total_tasks = result.fetchone()[0]
        
        result = db.execute(text("SELECT COUNT(*) FROM tasks WHERE file_hash IS NOT NULL"))
        hashed_tasks = result.fetchone()[0]
        
        logger.info(f"📊 数据统计:")
        logger.info(f"   - 总任务数: {total_tasks}")
        logger.info(f"   - 已有哈希: {hashed_tasks}")
        logger.info(f"   - 未哈希: {total_tasks - hashed_tasks}")
        
        if total_tasks > hashed_tasks:
            logger.warning("⚠️  部分历史任务没有 file_hash，这些任务无法参与幂等性检查")
            logger.info("💡 建议：对重要的历史任务，可手动计算并更新其 file_hash")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ 迁移失败: {e}")
        logger.exception(e)
        db.rollback()
        return False
    finally:
        db.close()

if __name__ == "__main__":
    logger.add(
        "logs/migration_{time}.log",
        rotation="1 day",
        retention="7 days",
        level="DEBUG"
    )
    
    success = migrate_database()
    
    if success:
        logger.success("🎉 数据库迁移完成！")
        sys.exit(0)
    else:
        logger.error("💥 数据库迁移失败！")
        sys.exit(1)
