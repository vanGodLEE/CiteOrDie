# 数据库迁移说明

## MinIO集成 - 添加minio_url字段

### 变更内容

在 `tasks` 表中添加了 `minio_url` 字段用于存储PDF文件在MinIO中的访问URL。

### SQL迁移脚本

```sql
-- 为tasks表添加minio_url字段
ALTER TABLE tasks ADD COLUMN minio_url VARCHAR(500) COMMENT 'MinIO存储URL';

-- 创建索引（可选，如果需要频繁查询）
CREATE INDEX idx_task_minio_url ON tasks(minio_url);
```

### 手动迁移步骤

#### Linux/Mac (Bash)

**重要**：如果遇到 `no such table: tasks` 错误，说明数据库文件还未创建。请先启动服务让数据库自动初始化，或使用Python脚本迁移。

1. **检查数据库是否存在**
   ```bash
   # 检查data目录
   ls -la data/
   
   # 如果没有tender_analysis.db，需要先创建
   # 方法1：运行一次API服务（推荐）
   python -m uvicorn app.api.main:app --reload --port 8866
   # 访问 http://localhost:8866/health 触发数据库创建
   # 然后 Ctrl+C 停止服务
   
   # 方法2：使用Python脚本（更简单）
   python migrate_db.py
   ```

2. **备份数据库**（如果已存在）
   ```bash
   cp data/tender_analysis.db data/tender_analysis.db.backup
   ```

3. **执行SQL迁移**
   ```bash
   # 注意：Linux使用 / 不是 \
   sqlite3 data/tender_analysis.db "ALTER TABLE tasks ADD COLUMN minio_url VARCHAR(500);"
   ```

4. **验证迁移**
   ```bash
   sqlite3 data/tender_analysis.db "PRAGMA table_info(tasks);"
   ```

#### Windows (PowerShell)

1. **备份数据库**
   ```powershell
   Copy-Item data\tender_analysis.db data\tender_analysis.db.backup
   ```

2. **执行SQL迁移**
   ```powershell
   # 方法1：使用Get-Content管道
   Get-Content migration.sql | sqlite3 data\tender_analysis.db
   
   # 方法2：直接执行SQL
   sqlite3 data\tender_analysis.db "ALTER TABLE tasks ADD COLUMN minio_url VARCHAR(500);"
   ```

3. **验证迁移**
   ```powershell
   sqlite3 data\tender_analysis.db "PRAGMA table_info(tasks);"
   ```

#### 使用Python脚本迁移（推荐，跨平台）

创建 `migrate_db.py` 文件：
```python
import sqlite3

# 连接数据库
conn = sqlite3.connect('data/tender_analysis.db')
cursor = conn.cursor()

try:
    # 添加minio_url字段
    cursor.execute("""
        ALTER TABLE tasks
        ADD COLUMN minio_url VARCHAR(500)
    """)
    conn.commit()
    print("✓ 迁移成功！minio_url字段已添加")
    
    # 验证
    cursor.execute("PRAGMA table_info(tasks)")
    columns = cursor.fetchall()
    print("\n当前tasks表结构：")
    for col in columns:
        print(f"  - {col[1]}: {col[2]}")
        
except sqlite3.OperationalError as e:
    if "duplicate column name" in str(e):
        print("✓ minio_url字段已存在，无需迁移")
    else:
        print(f"✗ 迁移失败: {e}")
finally:
    conn.close()
```

运行迁移：
```powershell
python migrate_db.py
```

### 自动迁移（推荐）

如果使用Alembic等迁移工具：

```python
# alembic/versions/xxx_add_minio_url.py
def upgrade():
    op.add_column('tasks', sa.Column('minio_url', sa.String(500), nullable=True))

def downgrade():
    op.drop_column('tasks', 'minio_url')
```

### 注意事项

- 该字段允许为空（nullable=True），不影响现有数据
- 新任务上传时会自动填充此字段
- 旧任务可以通过API按需补充MinIO URL