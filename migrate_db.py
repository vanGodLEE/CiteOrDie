"""
数据库迁移脚本 - 添加minio_url字段

使用方法：
    python migrate_db.py
"""

import sqlite3
from pathlib import Path


def migrate():
    """执行数据库迁移"""
    # 数据库文件路径
    db_path = Path("data/tender_analysis.db")
    
    if not db_path.exists():
        print(f"✗ 数据库文件不存在: {db_path}")
        print("  提示：如果是首次运行，数据库会在首次使用API时自动创建")
        return
    
    # 备份数据库
    backup_path = db_path.with_suffix('.db.backup')
    import shutil
    shutil.copy(db_path, backup_path)
    print(f"✓ 数据库已备份: {backup_path}")
    
    # 连接数据库
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    try:
        # 检查字段是否已存在
        cursor.execute("PRAGMA table_info(tasks)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'minio_url' in columns:
            print("✓ minio_url字段已存在，无需迁移")
            return
        
        # 添加minio_url字段
        print("正在添加minio_url字段...")
        cursor.execute("""
            ALTER TABLE tasks 
            ADD COLUMN minio_url VARCHAR(500)
        """)
        conn.commit()
        print("✓ 迁移成功！minio_url字段已添加")
        
        # 验证迁移
        cursor.execute("PRAGMA table_info(tasks)")
        columns_after = cursor.fetchall()
        print("\n当前tasks表结构：")
        for col in columns_after:
            col_name = col[1]
            col_type = col[2]
            marker = " [新增]" if col_name == "minio_url" else ""
            print(f"  - {col_name}: {col_type}{marker}")
        
    except sqlite3.OperationalError as e:
        print(f"✗ 迁移失败: {e}")
        print(f"  正在恢复备份...")
        shutil.copy(backup_path, db_path)
        print(f"  ✓ 已恢复备份")
    except Exception as e:
        print(f"✗ 发生错误: {e}")
    finally:
        conn.close()


if __name__ == "__main__":
    print("=" * 60)
    print("数据库迁移 - 添加minio_url字段")
    print("=" * 60)
    migrate()
    print("=" * 60)