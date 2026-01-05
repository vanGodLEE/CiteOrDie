"""
数据库迁移脚本: 添加时间和结果字段

用途: 为 tasks 表添加以下字段：
  - elapsed_seconds: 任务耗时（秒）
  - document_tree_json: PageIndex文档树结构（JSON）
  
执行: python scripts/migrate_add_elapsed_seconds.py
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from app.db.database import engine
from loguru import logger


def migrate():
    """执行数据库迁移"""
    try:
        with engine.connect() as conn:
            # 检查字段是否已存在
            result = conn.execute(text("PRAGMA table_info(tasks)"))
            columns = [row[1] for row in result]
            
            success_count = 0
            total_count = 2
            
            # 1. 添加 elapsed_seconds 字段
            if 'elapsed_seconds' not in columns:
                logger.info("开始迁移: 添加 elapsed_seconds 字段...")
                conn.execute(text(
                    "ALTER TABLE tasks ADD COLUMN elapsed_seconds REAL DEFAULT 0.0"
                ))
                conn.commit()
                logger.success("✅ 已添加 elapsed_seconds 字段")
                success_count += 1
            else:
                logger.info("ℹ️  elapsed_seconds 字段已存在")
                success_count += 1
            
            # 2. 添加 document_tree_json 字段
            result = conn.execute(text("PRAGMA table_info(tasks)"))
            columns = [row[1] for row in result]
            
            if 'document_tree_json' not in columns:
                logger.info("开始迁移: 添加 document_tree_json 字段...")
                conn.execute(text(
                    "ALTER TABLE tasks ADD COLUMN document_tree_json TEXT"
                ))
                conn.commit()
                logger.success("✅ 已添加 document_tree_json 字段")
                success_count += 1
            else:
                logger.info("ℹ️  document_tree_json 字段已存在")
                success_count += 1
            
            # 验证迁移结果
            result = conn.execute(text("PRAGMA table_info(tasks)"))
            columns = [row[1] for row in result]
            
            if 'elapsed_seconds' in columns and 'document_tree_json' in columns:
                logger.success(f"✅ 验证通过: 所有字段已存在 ({success_count}/{total_count})")
                
                # 显示字段信息
                result = conn.execute(text(
                    "SELECT name, type, dflt_value FROM pragma_table_info('tasks') "
                    "WHERE name IN ('elapsed_seconds', 'document_tree_json')"
                ))
                logger.info("\n字段详情:")
                for row in result:
                    logger.info(f"  - {row[0]}: type={row[1]}, default={row[2]}")
                
                return True
            else:
                logger.error("❌ 验证失败: 部分字段未找到")
                return False
                
    except Exception as e:
        logger.error(f"❌ 迁移失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


if __name__ == "__main__":
    logger.info("=" * 70)
    logger.info("数据库迁移: 添加时间和结果字段")
    logger.info("=" * 70)
    
    success = migrate()
    
    if success:
        logger.success("\n🎉 迁移完成！")
        logger.info("\n添加的字段:")
        logger.info("  1. elapsed_seconds (REAL) - 任务耗时（秒）")
        logger.info("  2. document_tree_json (TEXT) - PageIndex文档树（JSON）")
        logger.info("\n下一步:")
        logger.info("  1. 重启应用程序")
        logger.info("  2. 验证任务查询接口返回 elapsed_seconds 和 document_tree 字段")
        logger.info("  3. 创建新任务，检查数据是否正确保存")
        logger.info("  4. 重启后查询历史任务，验证数据恢复功能\n")
    else:
        logger.error("\n❌ 迁移失败，请检查错误信息")
        sys.exit(1)