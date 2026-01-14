"""
数据库迁移：添加positions_json字段

为sections和requirements表添加positions_json字段，用于存储bbox坐标信息
"""

import sqlite3
from pathlib import Path
from loguru import logger

# 数据库路径
DB_PATH = Path(__file__).parent.parent / "data" / "tender_analysis.db"


def migrate():
    """执行迁移"""
    if not DB_PATH.exists():
        logger.error(f"数据库文件不存在: {DB_PATH}")
        return False
    
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    try:
        logger.info("开始数据库迁移：添加positions_json字段")
        
        # 1. 为sections表添加positions_json字段
        try:
            cursor.execute("""
                ALTER TABLE sections 
                ADD COLUMN positions_json TEXT
            """)
            logger.info("✓ sections表添加positions_json字段成功")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                logger.info("✓ sections.positions_json字段已存在，跳过")
            else:
                raise
        
        # 2. 为requirements表添加positions_json字段
        try:
            cursor.execute("""
                ALTER TABLE requirements 
                ADD COLUMN positions_json TEXT
            """)
            logger.info("✓ requirements表添加positions_json字段成功")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                logger.info("✓ requirements.positions_json字段已存在，跳过")
            else:
                raise
        
        # 提交事务
        conn.commit()
        logger.info("✓ 数据库迁移完成")
        return True
        
    except Exception as e:
        logger.error(f"数据库迁移失败: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


def verify():
    """验证迁移结果"""
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    try:
        # 检查sections表结构
        cursor.execute("PRAGMA table_info(sections)")
        sections_columns = [col[1] for col in cursor.fetchall()]
        
        # 检查requirements表结构
        cursor.execute("PRAGMA table_info(requirements)")
        requirements_columns = [col[1] for col in cursor.fetchall()]
        
        logger.info("\n验证迁移结果:")
        logger.info(f"  sections表包含positions_json: {'positions_json' in sections_columns}")
        logger.info(f"  requirements表包含positions_json: {'positions_json' in requirements_columns}")
        
        if 'positions_json' in sections_columns and 'positions_json' in requirements_columns:
            logger.info("✓ 迁移验证通过")
            return True
        else:
            logger.error("✗ 迁移验证失败")
            return False
            
    finally:
        conn.close()


if __name__ == "__main__":
    # 执行迁移
    success = migrate()
    
    if success:
        # 验证迁移
        verify()
    else:
        logger.error("迁移失败，请检查错误信息")