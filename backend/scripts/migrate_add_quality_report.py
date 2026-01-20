"""
数据库迁移脚本：为 tasks 表添加 quality_report_json 字段

用途：
1. 存储质量报告（解析精度、原文抽取成功率等指标）
2. 支持分析质量评估和优化

运行方式：
    python scripts/migrate_add_quality_report.py
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
    logger.info("=== 开始数据库迁移：添加 quality_report_json 字段 ===")
    
    db = SessionLocal()
    
    try:
        # 1. 检查 quality_report_json 字段是否已存在
        result = db.execute(text("PRAGMA table_info(tasks)"))
        columns = [row[1] for row in result.fetchall()]
        
        if 'quality_report_json' in columns:
            logger.info("✓ quality_report_json 字段已存在，跳过创建")
        else:
            # 2. 添加 quality_report_json 字段
            logger.info("添加 quality_report_json 字段...")
            db.execute(text("""
                ALTER TABLE tasks 
                ADD COLUMN quality_report_json TEXT
            """))
            db.commit()
            logger.info("✓ quality_report_json 字段已添加")
        
        # 3. 验证迁移
        logger.info("验证迁移...")
        result = db.execute(text("PRAGMA table_info(tasks)"))
        columns = {row[1]: row[2] for row in result.fetchall()}
        
        if 'quality_report_json' in columns:
            logger.success(f"✅ 迁移成功！quality_report_json 字段类型: {columns['quality_report_json']}")
        else:
            logger.error("❌ 迁移失败：quality_report_json 字段不存在")
            return False
        
        # 4. 统计已有任务
        result = db.execute(text("SELECT COUNT(*) FROM tasks"))
        total_tasks = result.fetchone()[0]
        
        result = db.execute(text("SELECT COUNT(*) FROM tasks WHERE quality_report_json IS NOT NULL"))
        tasks_with_report = result.fetchone()[0]
        
        logger.info(f"📊 数据统计:")
        logger.info(f"   - 总任务数: {total_tasks}")
        logger.info(f"   - 有质量报告: {tasks_with_report}")
        logger.info(f"   - 无质量报告: {total_tasks - tasks_with_report}")
        
        if total_tasks > tasks_with_report:
            logger.warning("⚠️  部分历史任务没有质量报告")
            logger.info("💡 提示：重新分析这些任务将自动生成质量报告")
        
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
