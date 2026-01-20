"""
数据库迁移脚本: 添加视觉内容描述字段

用途: 为 requirements 表添加以下字段：
  - image_caption: 图片内容描述（视觉模型分析结果）
  - table_caption: 表格内容描述（表格结构化数据）
  
执行: python scripts/migrate_add_vision_captions.py
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
            
            success_count = 0
            total_count = 2
            
            # 1. 添加 image_caption 字段
            if 'image_caption' not in columns:
                logger.info("开始迁移: 添加 image_caption 字段...")
                conn.execute(text(
                    "ALTER TABLE requirements ADD COLUMN image_caption TEXT"
                ))
                conn.commit()
                logger.success("✅ 已添加 image_caption 字段")
                success_count += 1
            else:
                logger.info("ℹ️  image_caption 字段已存在")
                success_count += 1
            
            # 2. 添加 table_caption 字段
            result = conn.execute(text("PRAGMA table_info(requirements)"))
            columns = [row[1] for row in result]
            
            if 'table_caption' not in columns:
                logger.info("开始迁移: 添加 table_caption 字段...")
                conn.execute(text(
                    "ALTER TABLE requirements ADD COLUMN table_caption TEXT"
                ))
                conn.commit()
                logger.success("✅ 已添加 table_caption 字段")
                success_count += 1
            else:
                logger.info("ℹ️  table_caption 字段已存在")
                success_count += 1
            
            # 验证迁移结果
            result = conn.execute(text("PRAGMA table_info(requirements)"))
            columns = [row[1] for row in result]
            
            if 'image_caption' in columns and 'table_caption' in columns:
                logger.success(f"✅ 验证通过: 所有字段已存在 ({success_count}/{total_count})")
                
                # 显示字段信息
                result = conn.execute(text(
                    "SELECT name, type, dflt_value FROM pragma_table_info('requirements') "
                    "WHERE name IN ('image_caption', 'table_caption')"
                ))
                logger.info("\n字段详情:")
                for row in result:
                    logger.info(f"  - {row[0]}: type={row[1]}, default={row[2]}")
                
                # 统计现有需求数量
                result = conn.execute(text("SELECT COUNT(*) FROM requirements"))
                count = result.fetchone()[0]
                logger.info(f"\n现有需求数量: {count} 条（新字段默认为NULL）")
                
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
    logger.info("数据库迁移: 添加视觉内容描述字段（caption）")
    logger.info("=" * 70)
    
    success = migrate()
    
    if success:
        logger.success("\n🎉 迁移完成！")
        logger.info("\n添加的字段:")
        logger.info("  1. image_caption (TEXT) - 图片内容描述")
        logger.info("     • 存储视觉模型对图片的分析结果")
        logger.info("     • 包含图片中的技术参数、规格要求、架构设计等")
        logger.info("     • 如果需求不来自图片，则为 NULL")
        logger.info("\n  2. table_caption (TEXT) - 表格内容描述")
        logger.info("     • 存储表格的结构化数据和分析结果")
        logger.info("     • 包含表格中的参数、指标、配置等关键信息")
        logger.info("     • 如果需求不来自表格，则为 NULL")
        logger.info("\n字段用途:")
        logger.info("  • 提升需求可追溯性：记录需求来源的视觉信息")
        logger.info("  • 支持智能分析：AI可直接理解图片/表格内容")
        logger.info("  • 便于人工审核：快速查看原始图表数据")
        logger.info("\n数据示例:")
        logger.info('  • image_caption: "系统架构图显示采用微服务架构..."')
        logger.info('  • table_caption: "技术参数表：数据库MySQL 8.0+，..."')
        logger.info("\n下一步:")
        logger.info("  1. 重启应用程序")
        logger.info("  2. 新任务会自动填充 caption 字段（如果有图片/表格）")
        logger.info("  3. 已有任务的需求 caption 字段为 NULL")
        logger.info("  4. 通过 /api/tasks/{task_id} 查询需求时可看到 caption\n")
    else:
        logger.error("\n❌ 迁移失败，请检查错误信息")
        sys.exit(1)