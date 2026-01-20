"""
数据库迁移脚本: 添加 category 字段

用途: 为 requirements 表添加 category 字段，用于需求类型分类
执行: python scripts/migrate_add_category.py
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
            result = conn.execute(text("PRAGMA table_info(requirements)"))
            columns = [row[1] for row in result]
            
            if 'category' not in columns:
                logger.info("开始迁移: 添加 category 字段...")
                
                # 添加字段
                conn.execute(text(
                    "ALTER TABLE requirements ADD COLUMN category VARCHAR(20) DEFAULT 'OTHER'"
                ))
                conn.commit()
                
                logger.success("✅ 迁移成功: 已添加 category 字段")
                
                # 验证迁移结果
                result = conn.execute(text("PRAGMA table_info(requirements)"))
                columns = [row[1] for row in result]
                
                if 'category' in columns:
                    logger.success("✅ 验证通过: category 字段已存在")
                else:
                    logger.error("❌ 验证失败: category 字段未找到")
                    return False
                
                # 显示字段信息
                result = conn.execute(text(
                    "SELECT name, type, dflt_value FROM pragma_table_info('requirements') "
                    "WHERE name = 'category'"
                ))
                for row in result:
                    logger.info(f"字段详情: name={row[0]}, type={row[1]}, default={row[2]}")
                
                # 统计现有需求数量
                result = conn.execute(text("SELECT COUNT(*) FROM requirements"))
                count = result.fetchone()[0]
                logger.info(f"现有需求数量: {count} 条（默认category='OTHER'）")
                
                return True
            else:
                logger.info("ℹ️  字段已存在，跳过迁移")
                return True
                
    except Exception as e:
        logger.error(f"❌ 迁移失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


if __name__ == "__main__":
    logger.info("=" * 70)
    logger.info("数据库迁移: 添加需求类型分类字段（category）")
    logger.info("=" * 70)
    
    success = migrate()
    
    if success:
        logger.success("\n🎉 迁移完成！")
        logger.info("\n添加的字段:")
        logger.info("  - category (VARCHAR(20)) - 需求类型分类")
        logger.info("\n需求类型说明:")
        logger.info("  • SOLUTION: 技术/服务方案（需在方案中详细响应）")
        logger.info("  • QUALIFICATION: 资质/资格/证书/授权/业绩等")
        logger.info("  • BUSINESS: 商务条款（报价、付款、合同等）")
        logger.info("  • FORMAT: 投标文件格式要求")
        logger.info("  • PROCESS: 招投标流程要求")
        logger.info("  • OTHER: 其他/不确定（需人工确认）")
        logger.info("\n下一步:")
        logger.info("  1. 重启应用程序")
        logger.info("  2. 新任务的需求会自动分类")
        logger.info("  3. 已有任务的需求默认为 'OTHER'\n")
    else:
        logger.error("\n❌ 迁移失败，请检查错误信息")
        sys.exit(1)